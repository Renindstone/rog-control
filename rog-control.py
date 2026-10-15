#!/usr/bin/env python3
"""ROG Control: a small Armoury Crate replacement for the ROG Harpe Ace Mini on Linux."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from rogmouse import device as dev  # noqa: E402
from rogmouse.hid import DeviceAsleep, MouseError  # noqa: E402

APP_ID = "io.github.rogcontrol.HarpeAceMini"


def rgba(color):
    c = Gdk.RGBA()
    c.red, c.green, c.blue, c.alpha = color[0] / 255, color[1] / 255, color[2] / 255, 1.0
    return c


def to_rgb(c):
    return (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def string_combo(title, labels, subtitle=None):
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
    if subtitle:
        row.set_subtitle(subtitle)
    return row


class Debouncer:
    """Delays a write until the user stops dragging/typing for a moment."""

    def __init__(self, delay_ms=400):
        self.delay = delay_ms
        self.pending = {}

    def __call__(self, key, fn):
        if key in self.pending:
            GLib.source_remove(self.pending[key])

        def fire():
            del self.pending[key]
            fn()
            return GLib.SOURCE_REMOVE

        self.pending[key] = GLib.timeout_add(self.delay, fire)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="ROG Control")
        self.set_default_size(560, 720)
        self.mouse = None
        self.loading = False
        self.debounce = Debouncer()

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)

        self.toolbar = Adw.ToolbarView()
        self.toasts.set_child(self.toolbar)

        self.header = Adw.HeaderBar()
        self.toolbar.add_top_bar(self.header)

        self.profile_dd = Gtk.DropDown.new_from_strings([f"Perfil {i + 1}" for i in range(dev.PROFILE_COUNT)])
        self.profile_dd.set_tooltip_text("Perfil guardado en el mouse")
        self.profile_dd.connect("notify::selected", self.on_profile)
        self.header.pack_start(self.profile_dd)

        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Volver a leer el mouse")
        refresh.connect("clicked", lambda *_: self.connect_mouse())
        self.header.pack_end(refresh)

        self.battery_label = Gtk.Label(css_classes=["dim-label", "numeric"])
        self.header.pack_end(self.battery_label)

        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        self.header.set_title_widget(switcher)
        self.switcher_bar = Adw.ViewSwitcherBar(stack=self.stack)
        self.toolbar.add_bottom_bar(self.switcher_bar)

        self.outer = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.outer.add_named(self.stack, "main")
        self.outer.add_named(self.build_missing_page(), "missing")
        self.toolbar.set_content(self.outer)

        self.build_performance_page()
        self.build_buttons_page()
        self.build_lighting_page()
        self.build_power_page()
        self.build_receiver_page()

        # Narrow windows (tiling WMs like Hyprland) get the switcher at the bottom.
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 520sp"))
        bp.add_setter(switcher, "visible", False)
        bp.add_setter(self.switcher_bar, "reveal", True)
        self.add_breakpoint(bp)

        GLib.timeout_add_seconds(60, self.poll_battery)
        self.connect_mouse()

    # ---- pages ---------------------------------------------------------

    def build_missing_page(self):
        status = Adw.StatusPage(
            icon_name="input-mouse-symbolic",
            title="No se encontró el mouse",
            description="Conecta el ROG Harpe Ace Mini por cable o con el ROG Omni Receiver.",
        )
        self.missing_status = status
        retry = Gtk.Button(label="Reintentar", halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"])
        retry.connect("clicked", lambda *_: self.connect_mouse())
        status.set_child(retry)
        return status

    def build_performance_page(self):
        page = Adw.PreferencesPage()

        self.info_group = Adw.PreferencesGroup(title="Dispositivo")
        self.info_rows = {}
        for key, title in (("model", "Modelo"), ("conn", "Conexión"), ("fw", "Firmware")):
            row = Adw.ActionRow(title=title, css_classes=["property"])
            self.info_rows[key] = row
            self.info_group.add(row)
        page.add(self.info_group)

        dpi = Adw.PreferencesGroup(
            title="DPI",
            description="Marca el nivel activo. El botón DPI del mouse recorre los cuatro niveles.",
        )

        self.dpi_rows = []
        group_leader = None
        for i in range(dev.DPI_PRESET_MAX):
            row = Adw.ActionRow(title=f"Nivel {i + 1}")
            radio = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if group_leader:
                radio.set_group(group_leader)
            else:
                group_leader = radio
            radio.connect("toggled", self.on_active_dpi, i)
            row.add_prefix(radio)
            row.set_activatable_widget(radio)

            adj = Gtk.Adjustment(lower=dev.DPI_MIN, upper=dev.DPI_MAX, step_increment=dev.DPI_STEP, page_increment=400)
            spin = Gtk.SpinButton(adjustment=adj, numeric=True, valign=Gtk.Align.CENTER, width_chars=6)
            spin.connect("value-changed", self.on_dpi_value, i)
            row.add_suffix(spin)

            color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
            color.set_tooltip_text("Color del indicador de este nivel")
            color.connect("notify::rgba", self.on_dpi_color, i)
            row.add_suffix(color)

            dpi.add(row)
            self.dpi_rows.append((row, radio, spin, color))
        page.add(dpi)

        sensor = Adw.PreferencesGroup(title="Sensor")
        self.polling_row = string_combo("Tasa de sondeo", [])
        self.polling_row.connect("notify::selected", self.on_polling)
        sensor.add(self.polling_row)

        self.liftoff_row = string_combo(
            "Distancia de despegue",
            list(dev.LIFT_OFF.values()),
            "Cambiarla reinicia la calibración de superficie",
        )
        self.liftoff_row.connect("notify::selected", self.on_liftoff)
        sensor.add(self.liftoff_row)

        self.snap_row = Adw.SwitchRow(title="Angle snapping", subtitle="Corrige los movimientos a líneas rectas")
        self.snap_row.connect("notify::active", self.on_snapping)
        sensor.add(self.snap_row)

        lo, hi, step = dev.ANGLE_TUNING_RANGE
        self.angle_row = Adw.SpinRow(
            title="Ajuste de ángulo",
            subtitle="Grados de rotación del sensor",
            adjustment=Gtk.Adjustment(lower=lo, upper=hi, step_increment=step, page_increment=step),
            snap_to_ticks=True,
        )
        self.angle_row.connect("notify::value", self.on_angle)
        sensor.add(self.angle_row)
        page.add(sensor)

        self.stack.add_titled_with_icon(page, "performance", "Rendimiento", "input-mouse-symbolic")

    def build_buttons_page(self):
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Asignación de botones")

        self.action_codes = []
        labels = []
        for gname, items in dev.BUTTON_ACTION_GROUPS:
            for code, label in items:
                self.action_codes.append(code)
                labels.append(label if gname == "Mouse" else f"{gname}: {label}")

        self.button_rows = []
        for slot, (_, name) in enumerate(dev.BUTTON_SLOTS):
            row = string_combo(name, labels)
            row.set_enable_search(True)
            row.connect("notify::selected", self.on_button, slot)
            if slot == 0:
                # Remapping the primary button away would leave the user without a way to click.
                row.set_sensitive(False)
                row.set_subtitle("Bloqueado para no quedarte sin clic")
            group.add(row)
            self.button_rows.append(row)

        reset = Gtk.Button(label="Restablecer", valign=Gtk.Align.CENTER, css_classes=["flat"])
        reset.connect("clicked", self.on_reset_buttons)
        group.set_header_suffix(reset)
        page.add(group)

        tip = Adw.PreferencesGroup(
            description="Tip: F13–F24 no existen en la mayoría de teclados. Asígnalas a un botón "
            "y luego crea un atajo en Hyprland (bind = , F13, exec, …) para lanzar lo que quieras."
        )
        page.add(tip)
        self.stack.add_titled_with_icon(page, "buttons", "Botones", "input-keyboard-symbolic")

    def build_lighting_page(self):
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Iluminación del logo")
        self.led_modes = list(dev.LED_MODES.keys())
        self.led_mode_row = string_combo("Efecto", list(dev.LED_MODES.values()))
        self.led_mode_row.connect("notify::selected", self.on_lighting)
        group.add(self.led_mode_row)

        self.led_bright_row = Adw.ActionRow(title="Brillo")
        self.led_bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.led_bright.set_hexpand(True)
        self.led_bright.set_draw_value(True)
        self.led_bright.set_value_pos(Gtk.PositionType.LEFT)
        self.led_bright.connect("value-changed", self.on_lighting)
        self.led_bright_row.add_suffix(self.led_bright)
        group.add(self.led_bright_row)

        self.led_color_row = Adw.ActionRow(title="Color")
        self.led_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        self.led_color.connect("notify::rgba", self.on_lighting)
        self.led_color_row.add_suffix(self.led_color)
        group.add(self.led_color_row)
        page.add(group)
        self.stack.add_titled_with_icon(page, "lighting", "Iluminación", "weather-clear-symbolic")

    def build_power_page(self):
        page = Adw.PreferencesPage()
        status = Adw.PreferencesGroup(title="Batería")
        self.batt_row = Adw.ActionRow(title="Nivel")
        self.batt_bar = Gtk.LevelBar(min_value=0, max_value=100, valign=Gtk.Align.CENTER, width_request=160)
        self.batt_row.add_suffix(self.batt_bar)
        status.add(self.batt_row)
        page.add(status)

        group = Adw.PreferencesGroup(title="Ahorro de energía", description="Solo aplica en modo inalámbrico.")
        self.poweroff_codes = list(dev.POWER_OFF.keys())
        self.poweroff_row = string_combo("Apagado automático", list(dev.POWER_OFF.values()), "Tiempo de inactividad antes de dormir")
        self.poweroff_row.connect("notify::selected", self.on_energy)
        group.add(self.poweroff_row)

        self.lowbatt_row = string_combo(
            "Aviso de batería baja",
            ["Desactivado" if v == 0 else f"{v} %" for v in dev.LOW_BATTERY_LEVELS],
            "El logo parpadea al llegar a este nivel",
        )
        self.lowbatt_row.connect("notify::selected", self.on_energy)
        group.add(self.lowbatt_row)
        page.add(group)
        self.stack.add_titled_with_icon(page, "power", "Energía", "battery-good-symbolic")

    def build_receiver_page(self):
        self.receiver_stack = Gtk.Stack()
        wired = Adw.StatusPage(
            icon_name="network-wireless-symbolic",
            title="ROG Omni Receiver",
            description="El mouse está conectado por cable. Conecta el receptor y desconecta el cable "
            "para ver su estado aquí.\n\nLos ajustes de las otras pestañas se guardan en el mouse, "
            "así que también se aplican cuando usas el receptor.",
        )
        self.receiver_stack.add_named(wired, "wired")

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="ROG Omni Receiver")
        self.rx_booster_row = Adw.ActionRow(title="Polling Rate Booster", css_classes=["property"])
        group.add(self.rx_booster_row)
        self.rx_serial_row = Adw.ActionRow(title="Mouse emparejado", css_classes=["property"])
        group.add(self.rx_serial_row)
        page.add(group)
        note = Adw.PreferencesGroup(
            description="Emparejar dispositivos y actualizar el firmware del receptor no está "
            "soportado: un error ahí podría dejar inservible el receptor."
        )
        page.add(note)
        self.receiver_stack.add_named(page, "omni")
        self.stack.add_titled_with_icon(self.receiver_stack, "receiver", "Receptor", "network-wireless-symbolic")

    # ---- device <-> UI -------------------------------------------------

    def connect_mouse(self):
        if self.mouse:
            self.mouse.close()
            self.mouse = None
        try:
            self.mouse = dev.HarpeAceMini()
            self.mouse.read_all()
        except DeviceAsleep:
            self.show_missing("El mouse está dormido", "Muévelo o haz clic para despertarlo y pulsa Reintentar.")
            return
        except MouseError as e:
            self.show_missing("No se encontró el mouse", str(e))
            return
        self.outer.set_visible_child_name("main")
        self.profile_dd.set_sensitive(True)
        self.refresh_ui()

    def show_missing(self, title, desc):
        if self.mouse:
            self.mouse.close()
            self.mouse = None
        self.missing_status.set_title(title)
        self.missing_status.set_description(desc)
        self.outer.set_visible_child_name("missing")
        self.profile_dd.set_sensitive(False)
        self.battery_label.set_label("")

    def refresh_ui(self):
        s = self.mouse.state
        self.loading = True
        try:
            self.profile_dd.set_selected(s.profile)
            self.info_rows["model"].set_subtitle(s.model)
            self.info_rows["conn"].set_subtitle("ROG Omni Receiver (2.4 GHz)" if s.omni else "Cable USB")
            self.info_rows["fw"].set_subtitle(s.firmware)

            for i, (row, radio, spin, color) in enumerate(self.dpi_rows):
                spin.set_value(s.dpis[i].dpi)
                color.set_rgba(rgba(s.dpis[i].color))
                radio.set_active(i == s.active_dpi)

            self.polling_choices = list(self.mouse.polling_choices().items())
            self.polling_row.set_model(Gtk.StringList.new([f"{hz} Hz" for _, hz in self.polling_choices]))
            idx = [i for i, _ in self.polling_choices]
            self.polling_row.set_selected(idx.index(s.polling) if s.polling in idx else len(idx) - 1)
            self.liftoff_row.set_selected(s.lift_off)
            self.snap_row.set_active(s.angle_snapping)
            self.angle_row.set_value(s.angle_tuning)

            for slot, row in enumerate(self.button_rows):
                code = s.buttons[slot]
                if code in self.action_codes:
                    row.set_selected(self.action_codes.index(code))

            self.led_mode_row.set_selected(self.led_modes.index(s.led_mode))
            self.led_bright.set_value(s.led_brightness)
            self.led_color.set_rgba(rgba(s.led_color))
            self.update_led_sensitivity()

            self.poweroff_row.set_selected(self.poweroff_codes.index(s.power_off))
            lb = min(dev.LOW_BATTERY_LEVELS, key=lambda v: abs(v - s.low_battery))
            self.lowbatt_row.set_selected(dev.LOW_BATTERY_LEVELS.index(lb))

            self.receiver_stack.set_visible_child_name("omni" if s.omni else "wired")
            self.rx_booster_row.set_subtitle("Activado (hasta 8000 Hz)" if s.booster else "Desactivado (hasta 1000 Hz)")
            self.rx_serial_row.set_subtitle(f"{s.model} · {s.serial}")
        finally:
            self.loading = False
        self.update_battery()

    def update_battery(self):
        s = self.mouse.state
        if s.battery < 0:
            self.battery_label.set_label("")
            return
        icon = "⚡ " if s.charging else ""
        self.battery_label.set_label(f"{icon}{s.battery} %")
        self.batt_bar.set_value(s.battery)
        self.batt_row.set_subtitle(f"{s.battery} %" + (" · cargando" if s.charging else ""))

    def poll_battery(self):
        if self.mouse:
            try:
                self.mouse.read_battery()
                self.update_battery()
            except DeviceAsleep:
                pass
            except MouseError:
                self.show_missing("Se perdió la conexión", "Vuelve a conectar el mouse y pulsa Reintentar.")
        return GLib.SOURCE_CONTINUE

    def apply(self, fn, *args, ok=None):
        """Run a write on the mouse and report failures as a toast."""
        if self.loading or not self.mouse:
            return
        try:
            fn(*args)
            if ok:
                self.toasts.add_toast(Adw.Toast(title=ok, timeout=1))
        except DeviceAsleep:
            self.toasts.add_toast(Adw.Toast(title="El mouse está dormido: muévelo y vuelve a intentarlo"))
        except MouseError as e:
            self.toasts.add_toast(Adw.Toast(title=f"Error: {e}"))

    # ---- handlers ------------------------------------------------------

    def on_profile(self, dd, _):
        if self.loading or not self.mouse:
            return
        self.apply(self.mouse.set_profile, dd.get_selected(), ok=f"Perfil {dd.get_selected() + 1} activo")
        self.refresh_ui()

    def on_active_dpi(self, radio, i):
        if radio.get_active():
            self.apply(self.mouse.set_active_dpi, i)

    def on_dpi_value(self, spin, i):
        if self.loading:
            return
        self.debounce(("dpi", i), lambda: self.apply(self.mouse.set_dpi, i, int(spin.get_value())))

    def on_dpi_color(self, button, _, i):
        if self.loading:
            return
        spin = self.dpi_rows[i][2]
        self.apply(self.mouse.set_dpi, i, int(spin.get_value()), to_rgb(button.get_rgba()))

    def on_polling(self, row, _):
        if self.loading or row.get_selected() >= len(self.polling_choices):
            return
        self.apply(self.mouse.set_polling, self.polling_choices[row.get_selected()][0])

    def on_liftoff(self, row, _):
        self.apply(self.mouse.set_lift_off, row.get_selected())

    def on_snapping(self, row, _):
        self.apply(self.mouse.set_angle_snapping, row.get_active())

    def on_angle(self, row, _):
        if self.loading:
            return
        self.debounce("angle", lambda: self.apply(self.mouse.set_angle_tuning, int(row.get_value())))

    def on_button(self, row, _, slot):
        self.apply(self.mouse.set_button, slot, self.action_codes[row.get_selected()])

    def on_reset_buttons(self, *_):
        self.apply(self.mouse.reset_buttons, ok="Botones restablecidos")
        self.refresh_ui()

    def update_led_sensitivity(self):
        mode = self.led_modes[self.led_mode_row.get_selected()]
        self.led_color_row.set_sensitive(mode in dev.LED_MODES_WITH_COLOR)
        self.led_bright_row.set_sensitive(mode != 0xF0)

    def on_lighting(self, *_):
        if self.loading:
            return
        self.update_led_sensitivity()
        mode = self.led_modes[self.led_mode_row.get_selected()]
        self.debounce(
            "led",
            lambda: self.apply(
                self.mouse.set_lighting, mode, int(self.led_bright.get_value()), to_rgb(self.led_color.get_rgba())
            ),
        )

    def on_energy(self, *_):
        self.apply(
            self.mouse.set_energy,
            self.poweroff_codes[self.poweroff_row.get_selected()],
            dev.LOW_BATTERY_LEVELS[self.lowbatt_row.get_selected()],
        )


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        win = self.props.active_window or MainWindow(self)
        win.present()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))

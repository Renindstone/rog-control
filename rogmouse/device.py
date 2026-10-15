"""High-level settings API for the ROG Harpe Ace Mini (wired 0b05:1b63 or via ROG Omni Receiver).

Byte layouts were confirmed against the real mouse with probe.py and cross-checked
with libratbag's ASUS driver and G-Helper's Harpe Ace Mini model. Offsets below
are into the 64-byte response with the report ID already stripped.
"""

from dataclasses import dataclass, field

from .hid import KNOWN_MICE, MouseError, open_first

DPI_STEP = 50
DPI_MIN = 100
DPI_MAX = 42000
PROFILE_COUNT = 5
DPI_PRESET_MAX = 4

# index on the wire -> Hz. 2000+ only exist with the Omni receiver's booster.
POLLING_RATES = {0: 125, 1: 250, 2: 500, 3: 1000, 4: 2000, 5: 4000, 6: 8000}

LIFT_OFF = {0: "Baja", 1: "Alta"}

# minutes; 0xFF = never
POWER_OFF = {0: "1 min", 1: "2 min", 2: "3 min", 3: "5 min", 4: "10 min", 0xFF: "Nunca"}
LOW_BATTERY_LEVELS = [0, 10, 20, 30, 40, 50]

LED_MODES = {
    0x00: "Estático",
    0x01: "Respiración",
    0x02: "Ciclo de color",
    0x04: "Reactivo",
    0x06: "Estado de batería",
    0xF0: "Apagado",
}
LED_MODES_WITH_COLOR = {0x00, 0x01, 0x04}
LED_ZONE_ALL = 0x03

ANGLE_TUNING_RANGE = (-20, 20, 5)

# Physical buttons: (source code, name). Codes are little-endian u16, high byte 0x01 = mouse.
BUTTON_SLOTS = [
    (0x01F0, "Clic izquierdo"),
    (0x01F1, "Clic derecho"),
    (0x01F2, "Clic de rueda"),
    (0x01E4, "Lateral atrás"),
    (0x01E5, "Lateral adelante"),
    (0x01E6, "Botón DPI"),
    (0x01E8, "Rueda arriba"),
    (0x01E9, "Rueda abajo"),
]


def _keyboard_actions():
    keys = []
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        keys.append((0x04 + i, ch))
    for i, ch in enumerate("1234567890"):
        keys.append((0x1E + i, ch))
    keys += [
        (0x28, "Enter"), (0x29, "Esc"), (0x2A, "Retroceso"), (0x2B, "Tab"), (0x2C, "Espacio"),
        (0x2D, "-"), (0x2E, "="), (0x2F, "["), (0x30, "]"), (0x33, ";"), (0x34, "'"),
        (0x36, ","), (0x37, "."), (0x38, "/"),
    ]
    keys += [(0x3A + i, f"F{i + 1}") for i in range(12)]
    keys += [(0x68 + i, f"F{i + 13}") for i in range(12)]
    keys += [
        (0x49, "Insert"), (0x4A, "Inicio"), (0x4B, "Re Pág"), (0x4C, "Supr"), (0x4D, "Fin"),
        (0x4E, "Av Pág"), (0x4F, "Flecha derecha"), (0x50, "Flecha izquierda"),
        (0x51, "Flecha abajo"), (0x52, "Flecha arriba"),
    ]
    keys += [(0x59 + i, f"Num {i + 1}") for i in range(9)] + [(0x62, "Num 0"), (0x63, "Num .")]
    keys += [
        (0xE0, "Ctrl izq."), (0xE1, "Shift izq."), (0xE2, "Alt izq."), (0xE3, "Super izq."),
        (0xE4, "Ctrl der."), (0xE5, "Shift der."), (0xE6, "Alt der."), (0xE7, "Super der."),
    ]
    return keys


# (group, [(action code, label)])
BUTTON_ACTION_GROUPS = [
    ("Mouse", [
        (0x01F0, "Clic izquierdo"),
        (0x01F1, "Clic derecho"),
        (0x01F2, "Clic central"),
        (0x01E3, "Doble clic"),
        (0x01E4, "Atrás"),
        (0x01E5, "Adelante"),
        (0x01E6, "Cambiar DPI"),
        (0x01E7, "DPI objetivo (mantener)"),
        (0x01E8, "Rueda arriba"),
        (0x01E9, "Rueda abajo"),
        (0x0000, "Desactivado"),
    ]),
    ("Multimedia", [
        (0x00F6, "Subir volumen"),
        (0x00F5, "Bajar volumen"),
        (0x00F4, "Silenciar"),
        (0x00F0, "Reproducir/Pausa"),
        (0x00F1, "Detener"),
        (0x00F2, "Siguiente pista"),
        (0x00F3, "Pista anterior"),
    ]),
    ("Teclado", _keyboard_actions()),
]
BUTTON_ACTIONS = {code: label for _, items in BUTTON_ACTION_GROUPS for code, label in items}


@dataclass
class DpiPreset:
    dpi: int
    color: tuple = (255, 255, 255)


@dataclass
class MouseState:
    model: str = ""
    omni: bool = False
    firmware: str = ""
    serial: str = ""
    profile: int = 0
    active_dpi: int = 0  # 0-based
    dpis: list = field(default_factory=list)
    polling: int = 3
    booster: bool = False
    angle_snapping: bool = False
    angle_tuning: int = 0
    lift_off: int = 0
    buttons: list = field(default_factory=list)  # action code per BUTTON_SLOTS entry
    led_mode: int = 0
    led_brightness: int = 50
    led_color: tuple = (255, 0, 0)
    battery: int = -1
    charging: bool = False
    power_off: int = 0xFF
    low_battery: int = 20


def _u16(b, i):
    return b[i] | (b[i + 1] << 8)


def _s16(b, i):
    v = _u16(b, i)
    return v - 0x10000 if v & 0x8000 else v


class HarpeAceMini:
    def __init__(self):
        self.t, self.pid = open_first()
        self.state = MouseState(model=KNOWN_MICE.get(self.pid, "ROG Harpe Ace Mini"), omni=self.t.omni)

    def close(self):
        self.t.close()

    # ---- reading -------------------------------------------------------

    def read_all(self):
        s = self.state
        r = self.t.query(0x0012)
        s.firmware = f"{r[6]}.{r[5]:02x}.{r[4]:02x}"
        s.profile = r[10]
        s.active_dpi = max(r[11] - 1, 0)

        try:
            r = self.t.query(0x1212, b"\x02")
            s.serial = bytes(r[4:16]).decode("ascii", "replace").strip("\0")
        except MouseError:
            pass

        r = self.t.query(0x0412, b"\x00")
        raw_rate = r[12]
        hi = raw_rate >> 4
        s.polling = hi if (s.omni and hi) else raw_rate & 0x07
        s.angle_snapping = r[16] == 1
        s.angle_tuning = _s16(r, 18)

        r = self.t.query(0x0412, b"\x02")  # separate X/Y presets; we use X
        dpis = [_u16(r, 4 + i * 4) * DPI_STEP + DPI_STEP for i in range(DPI_PRESET_MAX)]
        r = self.t.query(0x0412, b"\x03")
        colors = [tuple(r[4 + i * 3 : 7 + i * 3]) for i in range(DPI_PRESET_MAX)]
        s.dpis = [DpiPreset(d, c) for d, c in zip(dpis, colors)]

        r = self.t.query(0x0612)
        s.lift_off = r[7] if r[7] in LIFT_OFF else 0

        r = self.t.query(0x0512, b"\x00")
        s.buttons = [_u16(r, 4 + i * 2) for i in range(len(BUTTON_SLOTS))]

        r = self.t.query(0x0312, b"\x00")
        s.led_mode = r[4] if r[4] in LED_MODES else 0xF0
        s.led_brightness = r[5]
        s.led_color = tuple(r[6:9])

        self.read_battery()

        if s.omni:
            try:
                r = self.t.query(0x207D, b"\x02")
                s.booster = r[4] == 1
            except MouseError:
                s.booster = False
        return s

    def read_battery(self):
        s = self.state
        r = self.t.query(0x0712)
        s.battery = r[4]
        s.power_off = r[5] if r[5] in POWER_OFF else 0xFF
        s.low_battery = r[6]
        s.charging = r[9] > 0
        return s.battery, s.charging

    def polling_choices(self):
        top = 6 if (self.state.omni and self.state.booster) else 3
        return {i: hz for i, hz in POLLING_RATES.items() if i <= top}

    # ---- writing -------------------------------------------------------
    # Every setter writes the value and then asks the mouse to persist it
    # to the active onboard profile (0x0350), like Armoury Crate does.

    def _set(self, cmd, params):
        self.t.query(cmd, bytes(params))

    def save(self):
        self.t.query(0x0350)

    def set_profile(self, index):
        self._set(0x0250, [index])
        self.state.profile = index
        return self.read_all()

    def set_dpi(self, preset, dpi, color=None):
        dpi = max(DPI_MIN, min(DPI_MAX, round(dpi / DPI_STEP) * DPI_STEP))
        color = color or self.state.dpis[preset].color
        enc = (dpi - DPI_STEP) // DPI_STEP
        self._set(0x3151, [preset, 0, enc & 0xFF, enc >> 8, *color])
        self.save()
        self.state.dpis[preset] = DpiPreset(dpi, tuple(color))

    def set_active_dpi(self, preset):
        self._set(0x3151, [0x09, 0, preset + 1])
        self.save()
        self.state.active_dpi = preset

    def set_polling(self, index):
        self._set(0x3151, [0x04, 0, index])
        self.save()
        self.state.polling = index

    def set_angle_snapping(self, enabled):
        self._set(0x3151, [0x06, 0, 1 if enabled else 0])
        self.save()
        self.state.angle_snapping = enabled

    def set_angle_tuning(self, degrees):
        v = degrees & 0xFFFF
        self._set(0x3151, [0x0B, 0, v & 0xFF, v >> 8])
        self.save()
        self.state.angle_tuning = degrees

    def set_lift_off(self, level):
        # Note: the mouse also resets its surface calibration when this is written.
        self._set(0x3551, [0xFF, 0, 0xFF, level])
        self.save()
        self.state.lift_off = level

    def set_button(self, slot, action):
        src = BUTTON_SLOTS[slot][0]
        self._set(0x2151, [0, 0, src & 0xFF, src >> 8, action & 0xFF, action >> 8])
        self.save()
        self.state.buttons[slot] = action

    def reset_buttons(self):
        for i, (src, _) in enumerate(BUTTON_SLOTS):
            self._set(0x2151, [0, 0, src & 0xFF, src >> 8, src & 0xFF, src >> 8])
            self.state.buttons[i] = src
        self.save()

    def set_lighting(self, mode, brightness, color):
        brightness = max(0, min(100, int(brightness)))
        self._set(0x2851, [LED_ZONE_ALL, 0, mode, brightness, *color, 0, 0, 0])
        self.save()
        s = self.state
        s.led_mode, s.led_brightness, s.led_color = mode, brightness, tuple(color)

    def set_energy(self, power_off, low_battery):
        self._set(0x3751, [0, 0, power_off, 0, low_battery])
        self.save()
        self.state.power_off, self.state.low_battery = power_off, low_battery

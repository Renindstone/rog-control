"""Low-level hidraw transport for ASUS ROG mice (wired and via ROG Omni Receiver).

Protocol notes come from libratbag's ASUS driver (src/asus.c, MIT licensed):
every request and response is a 64-byte packet whose first two bytes are the
command (little endian on the wire, e.g. GET_SETTINGS 0x0412 -> 12 04). Behind
the Omni receiver the same packet is sent with report ID 0x03 prepended.
"""

import glob
import os
import select

VENDOR_ASUS = 0x0B05
PID_OMNI_RECEIVER = 0x1ACE

# Known wired product IDs -> model name. Anything else from ASUS that exposes
# the vendor interface is still tried, these only give nicer names.
KNOWN_MICE = {
    0x1B63: "ROG Harpe Ace Mini",
}

PACKET_SIZE = 64
STATUS_ERROR = b"\xff\xaa"  # 0xaaff little endian: sleeping / disconnected / invalid


class MouseError(Exception):
    pass


class DeviceNotFound(MouseError):
    pass


class DeviceAsleep(MouseError):
    pass


def _hid_id(node):
    try:
        with open(f"/sys/class/hidraw/{node}/device/uevent") as f:
            for line in f:
                if line.startswith("HID_ID="):
                    _, vid, pid = line.strip().split("=")[1].split(":")
                    return int(vid, 16), int(pid, 16)
    except OSError:
        pass
    return None, None


def _report_descriptor(node):
    try:
        with open(f"/sys/class/hidraw/{node}/device/report_descriptor", "rb") as f:
            return f.read()
    except OSError:
        return b""


def find_candidates():
    """Return [(devpath, pid, omni)] for ASUS vendor-defined HID interfaces."""
    found = []
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        node = os.path.basename(path)
        vid, pid = _hid_id(node)
        if vid != VENDOR_ASUS:
            continue
        desc = _report_descriptor(node)
        omni = pid == PID_OMNI_RECEIVER
        # Wired mice: usage page 0xFF01 without report IDs.
        # Omni receiver: vendor page with report ID 0x03 (0x85 0x03).
        if desc.startswith(b"\x06\x01\xff") or (omni and b"\x85\x03" in desc and b"\x06" in desc):
            found.append((f"/dev/{node}", pid, omni))
    return found


class Transport:
    def __init__(self, devpath, omni):
        self.devpath = devpath
        self.omni = omni
        try:
            self.fd = os.open(devpath, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as e:
            raise MouseError(
                f"Sin permiso para abrir {devpath}. Instala la regla udev (install-udev.sh)."
            ) from e

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            try:
                os.read(self.fd, 128)
            except BlockingIOError:
                break

    def query(self, cmd, params=b"", timeout=0.5):
        """Send a command and return the 64-byte response (without report ID)."""
        packet = bytearray(PACKET_SIZE)
        packet[0] = cmd & 0xFF
        packet[1] = (cmd >> 8) & 0xFF
        packet[2 : 2 + len(params)] = params
        if self.omni:
            out = bytes([0x03]) + bytes(packet[: PACKET_SIZE - 1])
        else:
            out = bytes(packet)

        self._drain()
        os.write(self.fd, out)

        while True:
            ready = select.select([self.fd], [], [], timeout)[0]
            if not ready:
                raise MouseError(f"Sin respuesta al comando {cmd:#06x}")
            data = os.read(self.fd, 128)
            if self.omni:
                if not data or data[0] != 0x03:
                    continue  # unrelated report from another interface/report ID
                data = data[1:]
            data = bytes(data).ljust(PACKET_SIZE, b"\0")
            if data[:2] == STATUS_ERROR:
                raise DeviceAsleep("El mouse está dormido o desconectado")
            # Responses echo the command bytes; skip stray reports that don't.
            if data[0] == packet[0] and data[1] == packet[1]:
                return data
            if data[0] == packet[0] and data[1] == 0:
                return data


def open_first():
    """Open the first ASUS mouse that answers. Wired is preferred over the receiver."""
    cands = find_candidates()
    if not cands:
        raise DeviceNotFound("No se encontró ningún mouse ASUS ROG")
    cands.sort(key=lambda c: c[2])  # wired (omni=False) first
    last_err = None
    for devpath, pid, omni in cands:
        try:
            t = Transport(devpath, omni)
        except MouseError as e:
            last_err = e
            continue
        try:
            t.query(0x0012)
            return t, pid
        except MouseError as e:
            last_err = e
            t.close()
    raise last_err or DeviceNotFound("Ningún dispositivo respondió")

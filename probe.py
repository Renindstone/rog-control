#!/usr/bin/env python3
"""Read-only diagnostic: dumps what the mouse answers to GET (0x12 xx) commands.

Nothing here writes settings; only 0x12 "get" requests are sent.
"""

import sys

from rogmouse.hid import MouseError, Transport, find_candidates


def hexline(b):
    return " ".join(f"{x:02x}" for x in b.rstrip(b"\0") or b"\0")


def main():
    cands = find_candidates()
    if not cands:
        print("No se encontró ningún dispositivo ASUS con interfaz de configuración.")
        return 1
    for devpath, pid, omni in cands:
        print(f"### {devpath}  pid={pid:04x}  omni={omni}")
        try:
            t = Transport(devpath, omni)
        except MouseError as e:
            print("   ", e)
            continue
        requests = [(0x0012, b"")]
        requests += [(0x0412, bytes([p])) for p in (0, 1, 2)]
        requests += [(0x0512, bytes([g])) for g in (0, 1)]
        requests += [(0x0312, bytes([i])) for i in (0, 1, 2)]
        requests += [(0x1212, bytes([2]))]
        # sweep the remaining "get" group for unknown settings
        requests += [((sub << 8) | 0x12, b"") for sub in range(0x01, 0x20) if sub not in (0x03, 0x04, 0x05, 0x12)]
        for cmd, params in requests:
            try:
                r = t.query(cmd, params, timeout=0.3)
                print(f"  {cmd & 0xff:02x} {cmd >> 8:02x} {hexline(params):<3} -> {hexline(r)}")
            except MouseError as e:
                print(f"  {cmd & 0xff:02x} {cmd >> 8:02x} {hexline(params):<3} -> ({e})")
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

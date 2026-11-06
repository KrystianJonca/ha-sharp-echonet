"""Sharp KIN42 (0x013501) property layout, as verified live on 2026-11-06. No HA imports."""
from __future__ import annotations

EPC_POWER = 0x80
EPC_FAULT = 0x88
EPC_INSTANT_POWER = 0x84
EPC_ENERGY = 0x85
EPC_FIRMWARE = 0x8B
EPC_PRODUCT_CODE = 0x8C
EPC_AIRFLOW = 0xA0
EPC_POLLUTION = 0xC0
EPC_SENSORS = 0xF1  # 40-byte Sharp sensor blob
EPC_STATUS2 = 0xF2  # 40-byte Sharp blob (tank flag)
EPC_STATUS = 0xF3  # 27-byte Sharp state/command blob
EPC_NODE_ID = 0x83  # on node profile 0x0EF001

POLL_EPCS = [
    EPC_POWER, EPC_AIRFLOW, EPC_POLLUTION, EPC_INSTANT_POWER, EPC_ENERGY,
    EPC_FAULT, EPC_SENSORS, EPC_STATUS2, EPC_STATUS,
]

POWER_ON = b"\x30"
POWER_OFF = b"\x31"

# F3[4] mode codes -> preset keys (translated in strings.json)
MODES: dict[int, str] = {
    0x10: "auto",
    0x20: "ai_auto",
    0x11: "night",
    0x13: "pollen",
    0x40: "plasmacluster",
    0x14: "silent",
    0x15: "medium",
    0x16: "high",
}
MODE_CODES = {v: k for k, v in MODES.items()}
# Manual fan speeds, lowest first (A0 levels 1 / 5 / 7)
SPEED_PRESETS = ["silent", "medium", "high"]

F3_LEN = 27
TANK_EMPTY_CODE = 0x0A


def cmd_mode(mode_key: str) -> bytes:
    b = bytearray(F3_LEN)
    b[0], b[1], b[4] = 0x01, 0x01, MODE_CODES[mode_key]
    return bytes(b)


def cmd_humidify(on: bool) -> bytes:
    b = bytearray(F3_LEN)
    b[1] = 0x09
    b[15] = 0xFF if on else 0x00
    return bytes(b)


def _u(raw: dict[int, bytes], epc: int, start: int, length: int) -> int | None:
    v = raw.get(epc)
    if v is None or len(v) < start + length:
        return None
    return int.from_bytes(v[start : start + length], "big")


def is_on(raw: dict[int, bytes]) -> bool | None:
    v = raw.get(EPC_POWER)
    return None if v is None else v == POWER_ON


def _when_on(raw, value):
    """Sharp blobs read 0 while the unit is off; report unknown instead."""
    return value if is_on(raw) else None


def mode(raw) -> str | None:
    return _when_on(raw, MODES.get(_u(raw, EPC_STATUS, 4, 1)))


def humidify(raw) -> bool | None:
    v = _u(raw, EPC_STATUS, 15, 1)
    return None if v is None else v == 0xFF


def temperature(raw) -> int | None:
    v = _u(raw, EPC_SENSORS, 3, 1)
    if v is None:
        return None
    return _when_on(raw, v - 256 if v > 127 else v)


def humidity(raw) -> int | None:
    return _when_on(raw, _u(raw, EPC_SENSORS, 4, 1))


def pm25(raw) -> int | None:
    v = _u(raw, EPC_SENSORS, 27, 2)
    # Bit 15 is set for a while after power-on (sensor warming up), e.g. 0x8001.
    if v is None or v & 0x8000:
        return None
    return _when_on(raw, v)


def air_quality_level(raw) -> int | None:
    return _when_on(raw, _u(raw, EPC_SENSORS, 5, 1))


def filter_usage(raw) -> int | None:
    return _u(raw, EPC_SENSORS, 21, 4)


def tank_empty(raw) -> bool | None:
    v = _u(raw, EPC_STATUS2, 0, 1)
    return None if v is None else _when_on(raw, v == TANK_EMPTY_CODE)


def pollution(raw) -> bool | None:
    v = raw.get(EPC_POLLUTION)
    return None if v is None else v == b"\x41"


def fault(raw) -> bool | None:
    v = raw.get(EPC_FAULT)
    return None if v is None else v == b"\x41"


def power_w(raw) -> int | None:
    return _u(raw, EPC_INSTANT_POWER, 0, 2)


def energy_wh(raw) -> int | None:
    return _u(raw, EPC_ENERGY, 0, 4)


def ascii_prop(v: bytes | None) -> str | None:
    if not v:
        return None
    return v.split(b"\x00", 1)[0].decode("ascii", "replace").strip() or None


def mac_from_node_id(v: bytes | None) -> str | None:
    """0x83 = FE + maker(3) + id(13); Sharp puts the EUI-64 of the MAC in the last 8 bytes."""
    if not v or len(v) < 17:
        return None
    eui = v[-8:]
    if eui[3:5] != b"\xff\xfe":
        return None
    return ":".join(f"{b:02x}" for b in eui[:3] + eui[5:])

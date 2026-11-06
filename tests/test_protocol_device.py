"""Tests for the HA-independent modules (protocol.py, device.py).

They are loaded straight from their files so Home Assistant is not needed:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "sharp_echonet"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"sharp_echonet_{name}", PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


proto = _load("protocol")
dev = _load("device")


def f1(temp=0, hum=0, level=0, pm=0, counter=0) -> bytes:
    b = bytearray(40)
    b[3], b[4], b[5] = temp & 0xFF, hum, level
    b[21:25] = counter.to_bytes(4, "big")
    b[27:29] = pm.to_bytes(2, "big")
    return bytes(b)


def raw(on=True, props: dict[int, bytes] | None = None) -> dict[int, bytes]:
    r = {dev.EPC_POWER: dev.POWER_ON if on else dev.POWER_OFF}
    r.update(props or {})
    return r


class FrameTests(unittest.TestCase):
    def test_round_trip(self):
        data = proto.build_frame(0x1234, proto.AIR_CLEANER_EOJ, proto.ESV_GET, [(0x80, b""), (0xF3, b"\x01\x02")])
        self.assertEqual(data[:2], b"\x10\x81")
        frame = proto.parse_frame(data)
        self.assertEqual(frame.tid, 0x1234)
        self.assertEqual(frame.seoj, proto.CONTROLLER_EOJ)
        self.assertEqual(frame.deoj, proto.AIR_CLEANER_EOJ)
        self.assertEqual(frame.esv, proto.ESV_GET)
        self.assertEqual(frame.props, [(0x80, b""), (0xF3, b"\x01\x02")])

    def test_rejects_garbage_and_truncation(self):
        self.assertIsNone(proto.parse_frame(b"\x00" * 20))
        self.assertIsNone(proto.parse_frame(b"\x10\x81\x00"))
        good = proto.build_frame(1, proto.AIR_CLEANER_EOJ, proto.ESV_GET_RES, [(0xF1, bytes(40))])
        self.assertIsNone(proto.parse_frame(good[:-1]))


class DecodeTests(unittest.TestCase):
    def test_power(self):
        self.assertTrue(dev.is_on(raw(True)))
        self.assertFalse(dev.is_on(raw(False)))
        self.assertIsNone(dev.is_on({}))

    def test_sensors_unknown_while_off(self):
        r = raw(False, {dev.EPC_SENSORS: f1(temp=21, hum=40, pm=5)})
        self.assertIsNone(dev.temperature(r))
        self.assertIsNone(dev.humidity(r))
        self.assertIsNone(dev.pm25(r))

    def test_sensors(self):
        r = raw(True, {dev.EPC_SENSORS: f1(temp=22, hum=45, level=1, pm=12, counter=1234)})
        self.assertEqual(dev.temperature(r), 22)
        self.assertEqual(dev.humidity(r), 45)
        self.assertEqual(dev.pm25(r), 12)
        self.assertEqual(dev.air_quality_level(r), 1)
        self.assertEqual(dev.filter_usage(r), 1234)

    def test_negative_temperature(self):
        self.assertEqual(dev.temperature(raw(True, {dev.EPC_SENSORS: f1(temp=-3)})), -3)

    def test_pm25_warming_up(self):
        self.assertIsNone(dev.pm25(raw(True, {dev.EPC_SENSORS: f1(pm=0x8001)})))

    def test_short_blob(self):
        self.assertIsNone(dev.pm25(raw(True, {dev.EPC_SENSORS: bytes(10)})))

    def test_mode_and_humidify(self):
        f3 = bytearray(dev.F3_LEN)
        f3[4], f3[15] = 0x40, 0xFF
        r = raw(True, {dev.EPC_STATUS: bytes(f3)})
        self.assertEqual(dev.mode(r), "plasmacluster")
        self.assertTrue(dev.humidify(r))
        f3[4] = 0x99
        self.assertIsNone(dev.mode(raw(True, {dev.EPC_STATUS: bytes(f3)})))

    def test_tank_and_lamps(self):
        self.assertTrue(dev.tank_empty(raw(True, {dev.EPC_STATUS2: b"\x0a" + bytes(39)})))
        self.assertFalse(dev.tank_empty(raw(True, {dev.EPC_STATUS2: bytes(40)})))
        self.assertTrue(dev.pollution({dev.EPC_POLLUTION: b"\x41"}))
        self.assertFalse(dev.pollution({dev.EPC_POLLUTION: b"\x42"}))
        self.assertFalse(dev.fault({dev.EPC_FAULT: b"\x42"}))

    def test_commands(self):
        m = dev.cmd_mode("night")
        self.assertEqual(len(m), dev.F3_LEN)
        self.assertEqual(m[:5], b"\x01\x01\x00\x00\x11")
        self.assertFalse(any(m[5:]))
        h = dev.cmd_humidify(True)
        self.assertEqual((h[1], h[15]), (0x09, 0xFF))
        self.assertEqual(dev.cmd_humidify(False)[15], 0x00)

    def test_ascii_and_mac(self):
        self.assertEqual(dev.ascii_prop(b"KIN42\x00\x00\x00"), "KIN42")
        self.assertIsNone(dev.ascii_prop(b"\x00\x00"))
        node = b"\xfe\x00\x00\x05" + bytes(5) + bytes.fromhex("0211223344fffe55")
        node = node[:9] + bytes.fromhex("aabbccfffe112233")
        self.assertEqual(dev.mac_from_node_id(node), "aa:bb:cc:11:22:33")
        self.assertIsNone(dev.mac_from_node_id(b"\xfe" + bytes(16)))


class FakeTransport:
    """Times out `fail` times, then answers with `reply`."""

    def __init__(self, fail: int, reply):
        self.fail, self.reply, self.calls = fail, reply, 0

    async def async_request(self, host, deoj, esv, props, timeout):
        self.calls += 1
        if self.calls <= self.fail:
            raise proto.EchonetTimeout(host)
        return self.reply


class DeviceTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_get_retries_then_succeeds(self):
        reply = proto.Frame(1, proto.AIR_CLEANER_EOJ, proto.CONTROLLER_EOJ, proto.ESV_GET_RES, [(0x80, b"\x30")])
        t = FakeTransport(fail=2, reply=reply)
        d = proto.EchonetDevice(t, "192.0.2.1", retries=3)
        self.assertEqual(self.run_async(d.async_get([0x80])), {0x80: b"\x30"})
        self.assertEqual(t.calls, 3)

    def test_get_gives_up(self):
        t = FakeTransport(fail=5, reply=None)
        d = proto.EchonetDevice(t, "192.0.2.1", retries=2)
        with self.assertRaises(proto.EchonetTimeout):
            self.run_async(d.async_get([0x80]))
        self.assertEqual(t.calls, 2)

    def test_set_rejected(self):
        reply = proto.Frame(1, proto.AIR_CLEANER_EOJ, proto.CONTROLLER_EOJ, proto.ESV_SETC_SNA, [(0xF3, b"\x01")])
        d = proto.EchonetDevice(FakeTransport(0, reply), "192.0.2.1")
        with self.assertRaises(proto.EchonetRejected):
            self.run_async(d.async_set({0xF3: b"\x01"}))

    def test_get_all_rejected(self):
        reply = proto.Frame(1, proto.AIR_CLEANER_EOJ, proto.CONTROLLER_EOJ, proto.ESV_GET_SNA, [(0x80, b"")])
        d = proto.EchonetDevice(FakeTransport(0, reply), "192.0.2.1")
        with self.assertRaises(proto.EchonetRejected):
            self.run_async(d.async_get([0x80]))


if __name__ == "__main__":
    unittest.main()

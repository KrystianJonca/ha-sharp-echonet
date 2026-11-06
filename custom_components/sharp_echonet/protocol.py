"""Minimal async ECHONET Lite client (UDP 3610, unicast). No Home Assistant imports."""
from __future__ import annotations

import asyncio
import errno
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

PORT = 3610
MULTICAST_GROUP = "224.0.23.0"
CONTROLLER_EOJ = bytes.fromhex("05ff01")
NODE_PROFILE_EOJ = bytes.fromhex("0ef001")
AIR_CLEANER_EOJ = bytes.fromhex("013501")

ESV_SETC = 0x61
ESV_GET = 0x62
ESV_SETC_SNA = 0x51
ESV_GET_SNA = 0x52
ESV_SET_RES = 0x71
ESV_GET_RES = 0x72
ESV_INF = 0x73
ESV_INFC = 0x74
ESV_INFC_RES = 0x7A

DEFAULT_TIMEOUT = 2.0
DEFAULT_RETRIES = 3


class EchonetError(Exception):
    """Base error."""


class EchonetTimeout(EchonetError):
    """Device did not answer."""


class EchonetRejected(EchonetError):
    """Device answered with an SNA (rejected / not available)."""


class PortInUse(EchonetError):
    """UDP 3610 is already bound by something else."""


@dataclass(slots=True)
class Frame:
    tid: int
    seoj: bytes
    deoj: bytes
    esv: int
    props: list[tuple[int, bytes]]


def build_frame(tid: int, deoj: bytes, esv: int, props: list[tuple[int, bytes]]) -> bytes:
    out = bytearray(b"\x10\x81")
    out += tid.to_bytes(2, "big") + CONTROLLER_EOJ + deoj
    out += bytes([esv, len(props)])
    for epc, edt in props:
        out += bytes([epc, len(edt)]) + edt
    return bytes(out)


def parse_frame(data: bytes) -> Frame | None:
    if len(data) < 12 or data[0] != 0x10 or data[1] != 0x81:
        return None
    opc = data[11]
    props: list[tuple[int, bytes]] = []
    i = 12
    for _ in range(opc):
        if i + 2 > len(data):
            return None
        epc, pdc = data[i], data[i + 1]
        if i + 2 + pdc > len(data):
            return None
        props.append((epc, bytes(data[i + 2 : i + 2 + pdc])))
        i += 2 + pdc
    return Frame(int.from_bytes(data[2:4], "big"), bytes(data[4:7]), bytes(data[7:10]), data[10], props)


InfCallback = Callable[[dict[int, bytes]], None]


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, owner: EchonetTransport) -> None:
        self._owner = owner

    def datagram_received(self, data: bytes, addr) -> None:
        self._owner._handle(data, addr[0])

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("ECHONET socket error: %s", exc)


class EchonetTransport:
    """One UDP socket bound to 3610, shared by all devices."""

    def __init__(self) -> None:
        self._transport: asyncio.DatagramTransport | None = None
        self._pending: dict[tuple[str, int], asyncio.Future[Frame]] = {}
        self._listeners: dict[str, list[InfCallback]] = {}
        self._tid = 0

    async def async_start(self) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No SO_REUSEADDR on purpose: a second binder on Linux would silently
            # steal unicast replies. We want a clear error instead.
            # A just-closed transport frees its socket on a later loop iteration
            # (e.g. during an integration reload), so retry EADDRINUSE briefly.
            for attempt in range(10):
                try:
                    sock.bind(("0.0.0.0", PORT))
                    break
                except OSError as err:
                    if err.errno != errno.EADDRINUSE:
                        raise EchonetError(f"Cannot bind UDP {PORT}: {err}") from err
                    if attempt == 9:
                        raise PortInUse(f"UDP port {PORT} is already in use: {err}") from err
                    await asyncio.sleep(0.2)
            try:
                mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError as err:  # push is optional
                _LOGGER.debug("Could not join %s: %s", MULTICAST_GROUP, err)
            sock.setblocking(False)
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _Protocol(self), sock=sock
            )
        except BaseException:
            sock.close()
            raise

    def close(self) -> None:
        if self._transport:
            self._transport.close()
            self._transport = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(EchonetError("transport closed"))
        self._pending.clear()

    def register_listener(self, host: str, callback: InfCallback) -> Callable[[], None]:
        self._listeners.setdefault(host, []).append(callback)

        def _remove() -> None:
            cbs = self._listeners.get(host, [])
            if callback in cbs:
                cbs.remove(callback)

        return _remove

    def _next_tid(self) -> int:
        self._tid = (self._tid % 0xFFFF) + 1
        return self._tid

    def _handle(self, data: bytes, host: str) -> None:
        frame = parse_frame(data)
        if frame is None:
            return
        fut = self._pending.get((host, frame.tid))
        if fut is not None and not fut.done() and frame.esv not in (ESV_INF, ESV_INFC):
            fut.set_result(frame)
            return
        if frame.esv in (ESV_INF, ESV_INFC) and frame.seoj == AIR_CLEANER_EOJ:
            _LOGGER.debug("INF from %s: %s", host, [(hex(e), v.hex()) for e, v in frame.props])
            if frame.esv == ESV_INFC and self._transport:
                ack = build_frame(frame.tid, frame.seoj, ESV_INFC_RES, [(e, b"") for e, _ in frame.props])
                self._transport.sendto(ack, (host, PORT))
            props = {e: v for e, v in frame.props if v}
            for cb in list(self._listeners.get(host, [])):
                try:
                    cb(props)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("INF listener failed")

    async def async_request(
        self, host: str, deoj: bytes, esv: int, props: list[tuple[int, bytes]], timeout: float
    ) -> Frame:
        if self._transport is None:
            raise EchonetError("transport not started")
        tid = self._next_tid()
        fut: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
        self._pending[(host, tid)] = fut
        try:
            self._transport.sendto(build_frame(tid, deoj, esv, props), (host, PORT))
            async with asyncio.timeout(timeout):
                return await fut
        except TimeoutError as err:
            raise EchonetTimeout(f"no reply from {host}") from err
        finally:
            self._pending.pop((host, tid), None)


class EchonetDevice:
    """One ECHONET node, with request serialization and retries."""

    def __init__(
        self,
        transport: EchonetTransport,
        host: str,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.transport = transport
        self.host = host
        self._timeout = timeout
        self._retries = retries
        self._lock = asyncio.Lock()

    async def _request(self, deoj: bytes, esv: int, props: list[tuple[int, bytes]]) -> Frame:
        last: Exception | None = None
        async with self._lock:
            for attempt in range(self._retries):
                try:
                    return await self.transport.async_request(self.host, deoj, esv, props, self._timeout)
                except EchonetTimeout as err:
                    last = err
                    _LOGGER.debug("%s: timeout (attempt %d/%d)", self.host, attempt + 1, self._retries)
                    if attempt < self._retries - 1:
                        await asyncio.sleep(0.3)
        raise last or EchonetTimeout(self.host)

    async def async_get(self, epcs: list[int], eoj: bytes = AIR_CLEANER_EOJ) -> dict[int, bytes]:
        frame = await self._request(eoj, ESV_GET, [(e, b"") for e in epcs])
        if frame.esv not in (ESV_GET_RES, ESV_GET_SNA):
            raise EchonetError(f"unexpected ESV 0x{frame.esv:02x}")
        result = {e: v for e, v in frame.props if v}
        if not result:
            raise EchonetRejected(f"Get rejected for {[hex(e) for e in epcs]}")
        return result

    async def async_set(self, props: dict[int, bytes], eoj: bytes = AIR_CLEANER_EOJ) -> None:
        frame = await self._request(eoj, ESV_SETC, list(props.items()))
        if frame.esv == ESV_SET_RES:
            return
        if frame.esv == ESV_SETC_SNA:
            rejected = [hex(e) for e, v in frame.props if v]
            raise EchonetRejected(f"SetC rejected for {rejected}")
        raise EchonetError(f"unexpected ESV 0x{frame.esv:02x}")

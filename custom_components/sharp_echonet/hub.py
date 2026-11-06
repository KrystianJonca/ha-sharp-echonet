"""Shared UDP 3610 socket (one per HA instance, ref-counted)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.util.hass_dict import HassKey

from .protocol import EchonetTransport


@dataclass
class _Hub:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    transport: EchonetTransport | None = None
    users: int = 0


HUB_KEY: HassKey[_Hub] = HassKey("sharp_echonet_hub")


async def async_acquire_transport(hass: HomeAssistant) -> EchonetTransport:
    """Return the shared transport, starting it if needed. Raises PortInUse."""
    hub = hass.data.setdefault(HUB_KEY, _Hub())
    async with hub.lock:
        if hub.transport is None:
            transport = EchonetTransport()
            await transport.async_start()
            hub.transport = transport
        hub.users += 1
        return hub.transport


async def async_release_transport(hass: HomeAssistant) -> None:
    hub = hass.data.get(HUB_KEY)
    if hub is None:
        return
    async with hub.lock:
        hub.users -= 1
        if hub.users <= 0 and hub.transport is not None:
            hub.transport.close()
            hub.transport = None
            hub.users = 0

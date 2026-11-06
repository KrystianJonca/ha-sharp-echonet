"""Polling coordinator with optimistic writes and INF push merging."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import device as dev
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, REFRESH_AFTER_WRITE
from .protocol import NODE_PROFILE_EOJ, EchonetDevice, EchonetError, EchonetTransport

_LOGGER = logging.getLogger(__name__)

type SharpConfigEntry = ConfigEntry[SharpCoordinator]
Raw = dict[int, bytes]


class SharpCoordinator(DataUpdateCoordinator[Raw]):
    """Holds the raw property map; entities decode via device.py."""

    config_entry: SharpConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SharpConfigEntry, transport: EchonetTransport) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.device = EchonetDevice(transport, entry.data[CONF_HOST])
        self.model: str | None = None
        self.firmware: str | None = None
        self.module: str | None = None
        self.mac: str | None = None
        self._unsub_inf: Callable[[], None] | None = transport.register_listener(
            entry.data[CONF_HOST], self._handle_inf
        )
        self._refresh_task: asyncio.Task | None = None
        self._write_gen = 0

    async def _async_setup(self) -> None:
        try:
            info = await self.device.async_get([dev.EPC_PRODUCT_CODE, dev.EPC_FIRMWARE])
            self.model = dev.ascii_prop(info.get(dev.EPC_PRODUCT_CODE))
            self.firmware = dev.ascii_prop(info.get(dev.EPC_FIRMWARE))
        except EchonetError as err:
            raise UpdateFailed(f"Cannot reach purifier: {err}") from err
        try:
            node = await self.device.async_get(
                [dev.EPC_NODE_ID, dev.EPC_PRODUCT_CODE], eoj=NODE_PROFILE_EOJ
            )
            self.mac = dev.mac_from_node_id(node.get(dev.EPC_NODE_ID))
            self.module = dev.ascii_prop(node.get(dev.EPC_PRODUCT_CODE))
        except EchonetError:
            _LOGGER.debug("Node profile info unavailable")

    async def _async_update_data(self) -> Raw:
        try:
            return await self.device.async_get(dev.POLL_EPCS)
        except EchonetError as err:
            raise UpdateFailed(f"Purifier not responding: {err}") from err

    @callback
    def _handle_inf(self, props: Raw) -> None:
        # Merge without async_set_updated_data: that would reschedule the poll
        # timer (frequent INFs would starve polling of F1/F2/0x84/0x85) and
        # force last_update_success=True.
        if self.data is None or not props:
            return
        self.data = {**self.data, **props}
        self.async_update_listeners()

    async def async_write(
        self, props: Raw, optimistic: Callable[[Raw], None] | None = None
    ) -> None:
        """SetC, apply an optimistic patch, then read back shortly after."""
        try:
            await self.device.async_set(props)
        except EchonetError as err:
            raise HomeAssistantError(f"Purifier rejected or did not answer: {err}") from err
        if optimistic is not None and self.data is not None:
            data = dict(self.data)
            optimistic(data)
            self.async_set_updated_data(data)
        self._schedule_refresh_after_write()

    @callback
    def _schedule_refresh_after_write(self) -> None:
        # Never cancel a running read-back (cancelling inside async_refresh
        # leaves last_update_success=False). Instead keep one task and let it
        # read again if more writes happened while it was waiting/reading.
        self._write_gen += 1
        if self._refresh_task and not self._refresh_task.done():
            return

        async def _later() -> None:
            while True:
                gen = self._write_gen
                await asyncio.sleep(REFRESH_AFTER_WRITE)
                await self.async_refresh()
                if gen == self._write_gen:
                    return

        self._refresh_task = self.config_entry.async_create_background_task(
            self.hass, _later(), "sharp_echonet refresh after write"
        )

    async def async_shutdown(self) -> None:
        if self._unsub_inf:
            self._unsub_inf()
            self._unsub_inf = None
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        await super().async_shutdown()


def patch_f3(data: Raw, index: int, value: int) -> None:
    """Optimistically patch one byte of the F3 status blob."""
    f3 = bytearray(data.get(dev.EPC_STATUS, bytes(dev.F3_LEN)))
    if len(f3) > index:
        f3[index] = value
        data[dev.EPC_STATUS] = bytes(f3)

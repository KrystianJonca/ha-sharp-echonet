"""Humidify switch (F3 command 0x0009, state in F3[15])."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import device as dev
from .coordinator import SharpConfigEntry, patch_f3
from .entity import SharpEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SharpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([SharpHumidifySwitch(entry.runtime_data)])


class SharpHumidifySwitch(SharpEntity, SwitchEntity):
    _attr_translation_key = "humidify"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "humidify")

    @property
    def available(self) -> bool:
        # Only tested with the unit running; the F3 blob is all zeros when off.
        return super().available and dev.is_on(self.raw) is True

    @property
    def is_on(self) -> bool | None:
        return dev.humidify(self.raw)

    async def _set(self, on: bool) -> None:
        await self.coordinator.async_write(
            {dev.EPC_STATUS: dev.cmd_humidify(on)}, lambda d: patch_f3(d, 15, 0xFF if on else 0x00)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

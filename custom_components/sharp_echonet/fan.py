"""Fan: power, 3 manual speeds (Silent/Medium/High), all F3 modes as presets."""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import device as dev
from .const import POWER_ON_SETTLE
from .coordinator import SharpConfigEntry, patch_f3
from .entity import SharpEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SharpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([SharpPurifierFan(entry.runtime_data)])


class SharpPurifierFan(SharpEntity, FanEntity):
    _attr_name = None  # the device's main entity
    _attr_translation_key = "purifier"
    _attr_supported_features = (
        FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
    )
    _attr_speed_count = len(dev.SPEED_PRESETS)
    _attr_preset_modes = list(dev.MODES.values())

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "fan")

    @property
    def is_on(self) -> bool | None:
        return dev.is_on(self.raw)

    @property
    def preset_mode(self) -> str | None:
        return dev.mode(self.raw)

    @property
    def percentage(self) -> int | None:
        if dev.is_on(self.raw) is False:
            return 0
        mode = dev.mode(self.raw)
        if mode in dev.SPEED_PRESETS:
            return ordered_list_item_to_percentage(dev.SPEED_PRESETS, mode)
        return None  # automatic modes pick their own speed

    async def _power(self, on: bool) -> None:
        await self.coordinator.async_write(
            {dev.EPC_POWER: dev.POWER_ON if on else dev.POWER_OFF},
            lambda d: d.__setitem__(dev.EPC_POWER, dev.POWER_ON if on else dev.POWER_OFF),
        )

    async def _set_mode(self, mode: str) -> None:
        if dev.is_on(self.raw) is not True:
            await self._power(True)
            await asyncio.sleep(POWER_ON_SETTLE)
        code = dev.MODE_CODES[mode]
        await self.coordinator.async_write(
            {dev.EPC_STATUS: dev.cmd_mode(mode)}, lambda d: patch_f3(d, 4, code)
        )

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        if preset_mode is not None:
            await self._set_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._power(True)  # resumes the last mode

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._power(False)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self._power(False)
            return
        await self._set_mode(percentage_to_ordered_list_item(dev.SPEED_PRESETS, percentage))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._set_mode(preset_mode)

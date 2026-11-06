"""Binary sensors: pollution lamp, fault, water tank empty."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import device as dev
from .coordinator import SharpConfigEntry
from .entity import SharpEntity


@dataclass(frozen=True, kw_only=True)
class SharpBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[int, bytes]], bool | None]


DESCRIPTIONS = (
    SharpBinaryDescription(
        key="pollution",
        translation_key="pollution",
        # GAS renders as Detected/Clear instead of On/Off
        device_class=BinarySensorDeviceClass.GAS,
        value_fn=dev.pollution,
    ),
    SharpBinaryDescription(
        key="tank_empty",
        translation_key="tank_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=dev.tank_empty,
    ),
    SharpBinaryDescription(
        key="fault",
        translation_key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=dev.fault,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SharpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(SharpBinarySensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class SharpBinarySensor(SharpEntity, BinarySensorEntity):
    entity_description: SharpBinaryDescription

    def __init__(self, coordinator, description: SharpBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.raw)

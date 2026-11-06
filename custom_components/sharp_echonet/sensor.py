"""Sensors: temperature, humidity, PM2.5, air quality level, filter counter, power, energy."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDensity,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import device as dev
from .coordinator import SharpConfigEntry
from .entity import SharpEntity


@dataclass(frozen=True, kw_only=True)
class SharpSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[int, bytes]], int | None]


DESCRIPTIONS = (
    SharpSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=dev.temperature,
    ),
    SharpSensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=dev.humidity,
    ),
    SharpSensorDescription(
        key="pm25",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=dev.pm25,
    ),
    SharpSensorDescription(
        key="air_quality_level",
        translation_key="air_quality_level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=dev.air_quality_level,
    ),
    SharpSensorDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=dev.power_w,
    ),
    SharpSensorDescription(
        key="energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=dev.energy_wh,
    ),
    SharpSensorDescription(
        key="filter_usage",
        translation_key="filter_usage",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=dev.filter_usage,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SharpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(SharpSensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class SharpSensor(SharpEntity, SensorEntity):
    entity_description: SharpSensorDescription

    def __init__(self, coordinator, description: SharpSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        return self.entity_description.value_fn(self.raw)

"""Base entity: one device per purifier."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SharpCoordinator


class SharpEntity(CoordinatorEntity[SharpCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SharpCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.mac)} if coordinator.mac else set(),
            manufacturer="Sharp",
            model=coordinator.model,
            name=entry.title,
            sw_version=coordinator.firmware,
            hw_version=coordinator.module,
        )

    @property
    def raw(self) -> dict[int, bytes]:
        return self.coordinator.data or {}

"""Diagnostics download: raw property hex, for decoding unknown bytes later."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import SharpConfigEntry

TO_REDACT = {CONF_HOST, "mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SharpConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    return async_redact_data(
        {
            "entry_data": dict(entry.data),
            "options": dict(entry.options),
            "model": c.model,
            "firmware": c.firmware,
            "module": c.module,
            "mac": c.mac,
            "last_update_success": c.last_update_success,
            "raw": {f"0x{k:02X}": v.hex() for k, v in (c.data or {}).items()},
        },
        TO_REDACT,
    )

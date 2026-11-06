"""Sharp air purifier over local ECHONET Lite (no cloud)."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import PLATFORMS
from .coordinator import SharpConfigEntry, SharpCoordinator
from .hub import async_acquire_transport, async_release_transport
from .protocol import PortInUse


async def async_setup_entry(hass: HomeAssistant, entry: SharpConfigEntry) -> bool:
    try:
        transport = await async_acquire_transport(hass)
    except PortInUse as err:
        raise ConfigEntryNotReady(
            f"{err}. Is another ECHONET Lite integration (e.g. echonetlite) running?"
        ) from err
    # HA runs on_unload callbacks on unload *and* on any failed/retried setup,
    # so the port is always released. The coordinator registers its own shutdown.
    entry.async_on_unload(lambda: async_release_transport(hass))

    coordinator = SharpCoordinator(hass, entry, transport)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SharpConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: SharpConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

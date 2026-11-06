"""Config flow: enter the host, validate by reading 0x8C == KIN42."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from . import device as dev
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SUPPORTED_MODEL,
)
from .coordinator import SharpConfigEntry
from .hub import async_acquire_transport, async_release_transport
from .protocol import NODE_PROFILE_EOJ, EchonetDevice, EchonetError, PortInUse

_LOGGER = logging.getLogger(__name__)


class SharpEchonetConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                # Replies are matched on the sender address, so it must be a
                # literal IPv4 in canonical form (no hostnames, no IPv6).
                host = str(ipaddress.IPv4Address(user_input[CONF_HOST].strip()))
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
                host = None
        if user_input is not None and host is not None:
            try:
                model, unique_id = await self._async_probe(host)
            except PortInUse:
                errors["base"] = "port_in_use"
            except EchonetError:
                errors["base"] = "cannot_connect"
            else:
                if model != SUPPORTED_MODEL:
                    errors["base"] = "unsupported_model"
                    placeholders["model"] = model or "unknown"
                else:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    return self.async_create_entry(title=f"Sharp {model}", data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}), user_input
            ),
            errors=errors,
            description_placeholders=placeholders or {"model": SUPPORTED_MODEL},
        )

    async def _async_probe(self, host: str) -> tuple[str | None, str]:
        transport = await async_acquire_transport(self.hass)
        try:
            device = EchonetDevice(transport, host)
            info = await device.async_get([dev.EPC_PRODUCT_CODE])
            model = dev.ascii_prop(info.get(dev.EPC_PRODUCT_CODE))
            # Identity must not depend on the IP (DHCP changes would create a
            # duplicate entry), so the node ID is required; a failure here
            # surfaces as cannot_connect and the user can simply retry.
            node = await device.async_get([dev.EPC_NODE_ID], eoj=NODE_PROFILE_EOJ)
            node_id = node[dev.EPC_NODE_ID]
            mac = dev.mac_from_node_id(node_id)
            return model, format_mac(mac) if mac else node_id.hex()
        finally:
            await async_release_transport(self.hass)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: SharpConfigEntry) -> OptionsFlow:
        return SharpEchonetOptionsFlow()


class SharpEchonetOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )

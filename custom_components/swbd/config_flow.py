"""Discover and validate a SWBD rocker without changing its settings."""

from typing import Any

import probatio as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .client import SwbdClient
from .const import DOMAIN, MODELS


class SwbdConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._devices: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}
        self._discovery: bluetooth.BluetoothServiceInfoBleak | None = None

    async def _validate(self, address: str) -> bool:
        client = SwbdClient(
            lambda: bluetooth.async_ble_device_from_address(self.hass, address, connectable=True),
            address,
            lambda state: None,
            lambda: None,
        )
        try:
            await client.async_update()
        except (BleakError, TimeoutError, OSError, ValueError):
            return False
        finally:
            await client.async_stop()
        return True

    async def async_step_bluetooth(
        self,
        discovery_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> ConfigFlowResult:
        if discovery_info.name not in MODELS:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": MODELS[discovery_info.name]}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        errors = {}
        if user_input is not None:
            if await self._validate(self._discovery.address):
                return self._create(self._discovery)
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "name": MODELS[self._discovery.name],
                "address": self._discovery.address,
            },
        )

    def _create(self, info: bluetooth.BluetoothServiceInfoBleak) -> ConfigFlowResult:
        return self.async_create_entry(
            title=f"{MODELS[info.name]} ({info.address[-5:]})",
            data={CONF_ADDRESS: info.address, "local_name": info.name},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        configured = self._async_current_ids()
        for info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
            if info.name in MODELS and info.address not in configured:
                self._devices[info.address] = info
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if address in self._devices and await self._validate(address):
                return self._create(self._devices[address])
            errors["base"] = "cannot_connect"
        if not self._devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{MODELS[info.name]} ({address})"
                            for address, info in self._devices.items()
                        }
                    )
                }
            ),
        )

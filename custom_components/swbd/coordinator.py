"""Home Assistant state and Bluetooth lifecycle."""

import logging
from datetime import timedelta

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import SwbdClient
from .const import DOMAIN
from .protocol import RockerState

_LOGGER = logging.getLogger(__name__)


class SwbdCoordinator(DataUpdateCoordinator[RockerState]):
    """Push notifications plus a periodic state query and reconnect."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=30),
        )
        self.address = entry.data["address"]
        self.name = entry.title
        self.local_name = entry.data.get("local_name", "")
        self.client = SwbdClient(
            lambda: bluetooth.async_ble_device_from_address(hass, self.address, connectable=True),
            self.name,
            self._state_received,
            self._disconnected,
        )

    @callback
    def _state_received(self, state: RockerState) -> None:
        self.async_set_updated_data(state)

    @callback
    def _disconnected(self) -> None:
        self.async_set_update_error(UpdateFailed("Bluetooth connection lost"))

    async def _async_update_data(self) -> RockerState:
        try:
            return await self.client.async_update()
        except (BleakError, TimeoutError, OSError, ValueError) as err:
            raise UpdateFailed(f"Cannot read rocker state: {err}") from err

    async def async_set_field(self, field: str, value: int | bool) -> None:
        try:
            state = await self.client.async_set_field(field, value)
        except (BleakError, TimeoutError, OSError, ValueError) as err:
            self.async_set_update_error(UpdateFailed(str(err)))
            raise HomeAssistantError(f"Cannot change rocker setting: {err}") from err
        self.async_set_updated_data(state)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.async_stop()

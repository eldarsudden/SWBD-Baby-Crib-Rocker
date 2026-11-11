"""Direct Bluetooth integration for SWBD crib rockers."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .coordinator import SwbdCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SWITCH]
type SwbdConfigEntry = ConfigEntry[SwbdCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SwbdConfigEntry) -> bool:
    coordinator = SwbdCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        async def shutdown(event: Event) -> None:
            await coordinator.async_shutdown()

        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown))
    except BaseException:
        await coordinator.async_shutdown()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SwbdConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unloaded

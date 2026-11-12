"""Direct Bluetooth integration for SWBD crib rockers."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from .const import ALL_CONTROLS, DOMAIN, MODEL_CONTROLS
from .coordinator import SwbdCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SWITCH]
type SwbdConfigEntry = ConfigEntry[SwbdCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SwbdConfigEntry) -> bool:
    if entry.data.get("local_name") not in MODEL_CONTROLS:
        raise ConfigEntryError("This SWBD model has no confirmed Bluetooth LE support")
    coordinator = SwbdCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        # Earlier versions created sensor controls for Паинька too. Remove only
        # those known, integration-owned entries so they do not linger unavailable.
        registry = er.async_get(hass)
        unsupported_ids = {
            f"{coordinator.address}_{key}" for key in ALL_CONTROLS - coordinator.supported_controls
        }
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.platform == DOMAIN and entity.unique_id in unsupported_ids:
                registry.async_remove(entity.entity_id)
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

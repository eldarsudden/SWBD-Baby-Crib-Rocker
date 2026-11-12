"""Rocker and motion sensor switches."""

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwbdConfigEntry
from .coordinator import SwbdCoordinator
from .entity import SwbdEntity

PARALLEL_UPDATES = 0
DESCRIPTIONS = (
    SwitchEntityDescription(key="enabled", translation_key="enabled", icon="mdi:cradle"),
    SwitchEntityDescription(
        key="motion_enabled", translation_key="motion_enabled", icon="mdi:motion-sensor"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwbdConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SwbdSwitch(coordinator, description)
        for description in DESCRIPTIONS
        if description.key in coordinator.supported_controls
    )


class SwbdSwitch(SwbdEntity, SwitchEntity):
    def __init__(self, coordinator: SwbdCoordinator, description: SwitchEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return getattr(self.coordinator.data, self.entity_description.key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_field(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_field(self.entity_description.key, False)

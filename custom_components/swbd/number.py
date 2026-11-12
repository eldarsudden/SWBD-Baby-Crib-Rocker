"""Rocker power, microphone sensitivity, and device timer."""

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwbdConfigEntry
from .coordinator import SwbdCoordinator
from .entity import SwbdEntity

PARALLEL_UPDATES = 0
DESCRIPTIONS = (
    NumberEntityDescription(
        key="speed",
        translation_key="speed",
        icon="mdi:speedometer",
        native_min_value=1,
        native_max_value=6,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="sensitivity",
        translation_key="sensitivity",
        icon="mdi:microphone",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="hours",
        translation_key="hours",
        icon="mdi:timer-outline",
        native_min_value=0,
        native_max_value=23,
        native_step=1,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key="minutes",
        translation_key="minutes",
        icon="mdi:timer-outline",
        native_min_value=0,
        native_max_value=59,
        native_step=1,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwbdConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SwbdNumber(coordinator, description)
        for description in DESCRIPTIONS
        if description.key in coordinator.supported_controls
    )


class SwbdNumber(SwbdEntity, NumberEntity):
    def __init__(self, coordinator: SwbdCoordinator, description: NumberEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return getattr(self.coordinator.data, self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        if not float(value).is_integer():
            raise HomeAssistantError("Rocker settings require whole numbers")
        await self.coordinator.async_set_field(self.entity_description.key, int(value))

"""Select entities for Sleep Number BLE foundation presets."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PRESET_NAMES, SIDE_LEFT, SIDE_RIGHT
from .coordinator import SleepNumberBLECoordinator
from .entity import SleepNumberBLEEntity


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    async_add_entities(
        [
            FoundationPresetSelect(coordinator, SIDE_LEFT, "Foundation Preset Left"),
            FoundationPresetSelect(coordinator, SIDE_RIGHT, "Foundation Preset Right"),
        ]
    )


class FoundationPresetSelect(SleepNumberBLEEntity, SelectEntity):
    """Foundation preset selector for one side."""

    _attr_icon = "mdi:bed-outline"
    _attr_options = list(PRESET_NAMES.keys())
    _attr_current_option = None

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_foundation_preset_{side_str}"

    async def async_select_option(self, option: str) -> None:
        """Activate a foundation preset for this side."""
        preset_val = PRESET_NAMES.get(option)
        if preset_val is None:
            return
        await self.coordinator.async_set_preset(preset_val, self._side)

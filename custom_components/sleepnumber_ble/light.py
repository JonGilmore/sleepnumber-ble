"""Light entity for Sleep Number BLE underbed light."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SleepNumberBLECoordinator
from .entity import SleepNumberBLEEntity


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    async_add_entities(
        [
            UnderbedLightEntity(coordinator),
        ]
    )


class UnderbedLightEntity(SleepNumberBLEEntity, LightEntity):
    """Underbed light control."""

    _attr_name = "Underbed Light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: SleepNumberBLECoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_underbed_light"

    @property
    def is_on(self) -> bool | None:
        """Return light state from polled data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.underbed_light_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the underbed light on."""
        await self.coordinator.async_set_underbed_light(True)
        # Optimistic update while waiting for next poll
        if self.coordinator.data:
            self.coordinator.data.underbed_light_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the underbed light off."""
        await self.coordinator.async_set_underbed_light(False)
        if self.coordinator.data:
            self.coordinator.data.underbed_light_on = False
            self.async_write_ha_state()

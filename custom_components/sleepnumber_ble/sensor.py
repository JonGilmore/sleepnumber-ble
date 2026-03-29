"""Sensor entities for Sleep Number BLE."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SleepNumberBLECoordinator
from .entity import SleepNumberBLEEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    # No sensor entities for now - sleep number values are on the number entities.
    # Bed presence (occupancy) could be added later via func=24/25.
    async_add_entities([])

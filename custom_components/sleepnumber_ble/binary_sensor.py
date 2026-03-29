"""Binary sensor entities for Sleep Number BLE (bed presence/occupancy)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIDE_LEFT, SIDE_RIGHT
from .coordinator import SleepNumberBLECoordinator
from .entity import SleepNumberBLEEntity


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    async_add_entities(
        [
            BedPresenceSensor(coordinator, SIDE_LEFT, "Bed Presence Left"),
            BedPresenceSensor(coordinator, SIDE_RIGHT, "Bed Presence Right"),
        ]
    )


class BedPresenceSensor(SleepNumberBLEEntity, BinarySensorEntity):
    """Bed presence (occupancy) sensor for one side."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_presence_{side_str}"

    @property
    def is_on(self) -> bool | None:
        """Return True if someone is in bed on this side."""
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            return self.coordinator.data.left_present
        return self.coordinator.data.right_present

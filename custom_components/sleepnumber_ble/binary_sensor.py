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
            BedOccupiedSensor(coordinator, "Bed Occupied"),
        ]
    )


class BedPresenceSensor(SleepNumberBLEEntity, BinarySensorEntity):
    """Bed presence (occupancy) sensor for one side.

    Uses func=24 which is broken on firmware 0.4.x (always returns False).
    Kept for diagnostics and in case future firmware fixes it.
    """

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_entity_registry_enabled_default = False

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


class BedOccupiedSensor(SleepNumberBLEEntity, BinarySensorEntity):
    """Bed occupied sensor derived from underbed auto-light state.

    When the bed's auto-light feature is enabled, the underbed light turns on
    when someone gets out of bed. This sensor inverts that signal:
      light OFF = someone in bed = occupied (True)
      light ON  = bed empty = not occupied (False)

    Requires auto-light to be enabled in the SleepIQ app. This is whole-bed
    (not per-side) since the underbed light is a single unit.
    """

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator: SleepNumberBLECoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.address}_bed_occupied"

    @property
    def is_on(self) -> bool | None:
        """Return True if bed is occupied (light is off)."""
        if self.coordinator.data is None:
            return None
        if self.coordinator.data.underbed_light_on is None:
            return None
        # Light ON = out of bed = not occupied
        # Light OFF = in bed = occupied
        return not self.coordinator.data.underbed_light_on

"""Sensor entities for Sleep Number BLE — func=97 chamber/occupancy diagnostics."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIDE_LEFT, SIDE_RIGHT
from .coordinator import SleepNumberBLECoordinator
from .entity import SleepNumberBLEEntity

CHAMBER_TYPE_NAMES = {
    0: "Standard",
    1: "Kid",
    2: "HeadTilt",
    3: "Genie",
}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    async_add_entities(
        [
            ChamberOccupancySensor(coordinator, SIDE_LEFT, "Left Occupancy (f97)"),
            ChamberOccupancySensor(coordinator, SIDE_RIGHT, "Right Occupancy (f97)"),
            ChamberPresenceSensor(coordinator, SIDE_LEFT, "Left Chamber Present (f97)"),
            ChamberPresenceSensor(
                coordinator, SIDE_RIGHT, "Right Chamber Present (f97)"
            ),
            ChamberTypeSensor(coordinator, SIDE_LEFT, "Left Chamber Type (f97)"),
            ChamberTypeSensor(coordinator, SIDE_RIGHT, "Right Chamber Type (f97)"),
            ChamberRefreshSensor(coordinator, SIDE_LEFT, "Left Refresh State (f97)"),
            ChamberRefreshSensor(coordinator, SIDE_RIGHT, "Right Refresh State (f97)"),
        ]
    )


class ChamberOccupancySensor(SleepNumberBLEEntity, SensorEntity):
    """func=97 occupancy value (bytes 4/6). May not be populated on firmware 0.4.x."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = True

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_f97_occupancy_{side_str}"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            return self.coordinator.data.left_occupancy
        return self.coordinator.data.right_occupancy


class ChamberPresenceSensor(SleepNumberBLEEntity, SensorEntity):
    """func=97 chamber presence (bytes 0/2). 1 = chamber detected."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = True

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_f97_chamber_present_{side_str}"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            return self.coordinator.data.left_chamber_present
        return self.coordinator.data.right_chamber_present


class ChamberTypeSensor(SleepNumberBLEEntity, SensorEntity):
    """func=97 chamber type code (bytes 1/3). 0=Standard, 1=Kid, etc."""

    _attr_entity_registry_enabled_default = True

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_f97_chamber_type_{side_str}"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            code = self.coordinator.data.left_chamber_type
        else:
            code = self.coordinator.data.right_chamber_type
        if code is None:
            return None
        return CHAMBER_TYPE_NAMES.get(code, f"Unknown ({code})")


class ChamberRefreshSensor(SleepNumberBLEEntity, SensorEntity):
    """func=97 refresh state (bytes 5/7). May not be populated on firmware 0.4.x."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = True

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_f97_refresh_{side_str}"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            return self.coordinator.data.left_refresh_state
        return self.coordinator.data.right_refresh_state

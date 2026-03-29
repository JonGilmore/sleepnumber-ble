"""Number entities for Sleep Number BLE."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up number entities."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    async_add_entities(
        [
            SleepNumberEntity(coordinator, SIDE_LEFT, "Firmness Control Left"),
            SleepNumberEntity(coordinator, SIDE_RIGHT, "Firmness Control Right"),
        ]
    )


class SleepNumberEntity(SleepNumberBLEEntity, NumberEntity):
    """Sleep number firmness control (0-100) for one side."""

    _attr_native_min_value = 5
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:bed"

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_firmness_{side_str}"

    @property
    def native_value(self) -> float | None:
        """Return current sleep number."""
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            return self.coordinator.data.left_sleep_number
        return self.coordinator.data.right_sleep_number

    async def async_set_native_value(self, value: float) -> None:
        """Set sleep number."""
        await self.coordinator.async_set_sleep_number(self._side, int(value))


class HeadPositionEntity(SleepNumberBLEEntity, NumberEntity):
    """Head position control (0-100) for one side."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:angle-acute"

    def __init__(
        self, coordinator: SleepNumberBLECoordinator, side: int, name: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._side = side
        self._attr_name = name
        side_str = "left" if side == SIDE_LEFT else "right"
        self._attr_unique_id = f"{coordinator.address}_head_position_{side_str}"

    @property
    def native_value(self) -> float | None:
        """Return current head position."""
        if self.coordinator.data is None:
            return None
        if self._side == SIDE_LEFT:
            return self.coordinator.data.left_head_position
        return self.coordinator.data.right_head_position

    async def async_set_native_value(self, value: float) -> None:
        """Set head position (keeps foot at current value)."""
        foot = 0
        if self.coordinator.data:
            if self._side == SIDE_LEFT:
                foot = self.coordinator.data.left_foot_position
            else:
                foot = self.coordinator.data.right_foot_position
        await self.coordinator.async_set_foundation_position(
            self._side, int(value), foot
        )


class FootPositionEntity(SleepNumberBLEEntity, NumberEntity):
    """Foot position control (0-100) - shared between both sides."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:angle-acute"

    def __init__(self, coordinator: SleepNumberBLECoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.address}_foot_position"

    @property
    def native_value(self) -> float | None:
        """Return current foot position (from left side - feet are shared)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.left_foot_position

    async def async_set_native_value(self, value: float) -> None:
        """Set foot position (sends to left side, feet are shared)."""
        head = 0
        if self.coordinator.data:
            head = self.coordinator.data.left_head_position
        await self.coordinator.async_set_foundation_position(
            SIDE_LEFT, head, int(value)
        )

"""Base entity for Sleep Number BLE."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SleepNumberBLECoordinator


class SleepNumberBLEEntity(CoordinatorEntity[SleepNumberBLECoordinator]):
    """Base entity for Sleep Number BLE devices."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SleepNumberBLECoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Sleep Number Bed",
            manufacturer="Sleep Number",
            model="360",
        )

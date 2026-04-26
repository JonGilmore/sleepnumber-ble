"""Data coordinator for Sleep Number BLE."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .protocol import BedStatus, SleepNumberBed

_LOGGER = logging.getLogger(__name__)

# Full status poll (firmness, positions, light)
FULL_POLL_INTERVAL = timedelta(seconds=300)

# Fast poll after a set operation
FAST_POLL_INTERVAL = 10
FAST_POLL_COUNT = 12


class SleepNumberBLECoordinator(DataUpdateCoordinator[BedStatus]):
    """Coordinator that polls the bed for status."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{address}",
            update_interval=FULL_POLL_INTERVAL,
            always_update=False,
        )
        self.address = address
        self.bed = SleepNumberBed(address)
        self._ble_lock = asyncio.Lock()
        self._fast_poll_remaining = 0
        self._fast_poll_cancel = None

    def _get_device(self):
        """Get the BLE device, trying connectable first.

        Returns None only if no device is found AND we don't already have
        a persistent connection. When the bed is connected, HA's scanner
        may stop seeing advertisements, so the lookup can return None even
        though the connection is healthy.
        """
        device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            device = async_ble_device_from_address(
                self.hass, self.address, connectable=False
            )
        return device

    def _require_device(self) -> None:
        """Raise if we have no BLE device and no existing connection."""
        if self.bed.is_connected:
            return
        device = self._get_device()
        if device is None:
            raise UpdateFailed(f"Bed {self.address} not found via Bluetooth")

    def _start_fast_polling(self) -> None:
        """Start fast polling after a set operation."""
        self._fast_poll_remaining = FAST_POLL_COUNT
        self._schedule_fast_poll()

    @callback
    def _schedule_fast_poll(self) -> None:
        """Schedule the next fast poll."""
        if self._fast_poll_cancel:
            self._fast_poll_cancel()
        if self._fast_poll_remaining > 0:
            self._fast_poll_cancel = async_call_later(
                self.hass, FAST_POLL_INTERVAL, self._fast_poll_callback
            )

    async def _fast_poll_callback(self, _now) -> None:
        """Fast poll callback."""
        self._fast_poll_remaining -= 1
        _LOGGER.debug("Fast poll (%d remaining)", self._fast_poll_remaining)
        await self.async_request_refresh()

        if self.data and not self._bed_busy(self.data):
            _LOGGER.debug("Bed settled, stopping fast poll")
            self._fast_poll_remaining = 0
        elif self._fast_poll_remaining > 0:
            self._schedule_fast_poll()

    @staticmethod
    def _bed_busy(data: BedStatus) -> bool:
        """True if pump or foundation is actively moving."""
        return data.left_pumping or data.right_pumping or data.foundation_moving

    async def _async_update_data(self) -> BedStatus:
        """Full status fetch from the bed."""
        async with self._ble_lock:
            self._require_device()
            device = self._get_device()

            _LOGGER.debug("Full poll from %s", self.address)
            status = await self.bed.async_connect_and_read(device)
            if status is None:
                raise UpdateFailed("Failed to read bed status")

            return status

    async def async_set_sleep_number(self, side: int, value: int) -> None:
        """Set sleep number, update optimistically, and start fast polling."""
        async with self._ble_lock:
            self._require_device()
            device = self._get_device()

            success = await self.bed.async_set_sleep_number(device, side, value)
            if not success:
                raise UpdateFailed("Failed to set sleep number")

        if self.data:
            if side == 0:
                self.data.left_sleep_number = value
            else:
                self.data.right_sleep_number = value
            self.async_set_updated_data(self.data)

        self._start_fast_polling()

    async def async_set_preset(self, preset: int, side: int | None = None) -> None:
        """Set foundation preset."""
        async with self._ble_lock:
            self._require_device()
            device = self._get_device()

            success = await self.bed.async_set_preset(device, preset, side)
            if not success:
                raise UpdateFailed("Failed to set preset")

        self._start_fast_polling()

    async def async_set_underbed_light(self, on: bool) -> None:
        """Turn underbed light on or off."""
        async with self._ble_lock:
            self._require_device()
            device = self._get_device()

            success = await self.bed.async_set_underbed_light(device, on)
            if not success:
                raise UpdateFailed("Failed to set underbed light")

    async def async_set_foundation_position(
        self, side: int, head: int, foot: int
    ) -> None:
        """Set foundation position and refresh."""
        async with self._ble_lock:
            self._require_device()
            device = self._get_device()

            success = await self.bed.async_set_foundation_position(
                device, side, head, foot
            )
            if not success:
                raise UpdateFailed("Failed to set foundation position")

        self._start_fast_polling()

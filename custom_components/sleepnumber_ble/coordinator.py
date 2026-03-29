"""Data coordinator for Sleep Number BLE."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval, async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .protocol import BedStatus, SleepNumberBed

_LOGGER = logging.getLogger(__name__)

# Full status poll (firmness, presence, positions)
FULL_POLL_INTERVAL = timedelta(seconds=300)

# Presence-only poll (lightweight, just func=24 per side)
PRESENCE_POLL_INTERVAL = timedelta(seconds=20)

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
        self._presence_unsub = None

    async def async_setup(self) -> None:
        """Start presence polling."""
        self._presence_unsub = async_track_time_interval(
            self.hass, self._async_poll_presence, PRESENCE_POLL_INTERVAL
        )

    async def async_shutdown(self) -> None:
        """Stop presence polling."""
        if self._presence_unsub:
            self._presence_unsub()
            self._presence_unsub = None

    def _get_device(self):
        """Get the BLE device, trying connectable first."""
        device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            device = async_ble_device_from_address(
                self.hass, self.address, connectable=False
            )
        return device

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

        if self.data and not self.data.left_pumping and not self.data.right_pumping:
            _LOGGER.debug("Pump idle, stopping fast poll")
            self._fast_poll_remaining = 0
        elif self._fast_poll_remaining > 0:
            self._schedule_fast_poll()

    async def _async_poll_presence(self, _now=None) -> None:
        """Lightweight presence-only poll on a fast interval."""
        if self._ble_lock.locked():
            _LOGGER.debug("Skipping presence poll, BLE busy")
            return

        async with self._ble_lock:
            device = self._get_device()
            if device is None:
                return

            result = await self.bed.async_read_presence(device)
            if result is None:
                return

            if self.data is None:
                return

            left_changed = self.data.left_present != result[0]
            right_changed = self.data.right_present != result[1]

            if left_changed or right_changed:
                self.data.left_present = result[0]
                self.data.right_present = result[1]
                _LOGGER.debug(
                    "Presence changed: L=%s R=%s",
                    self.data.left_present,
                    self.data.right_present,
                )
                self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> BedStatus:
        """Full status fetch from the bed."""
        async with self._ble_lock:
            device = self._get_device()
            if device is None:
                raise UpdateFailed(f"Bed {self.address} not found via Bluetooth")

            _LOGGER.debug("Full poll from %s", self.address)
            status = await self.bed.async_connect_and_read(device)
            if status is None:
                raise UpdateFailed("Failed to read bed status")

            return status

    async def async_set_sleep_number(self, side: int, value: int) -> None:
        """Set sleep number, update optimistically, and start fast polling."""
        async with self._ble_lock:
            device = self._get_device()
            if device is None:
                raise UpdateFailed(f"Bed {self.address} not available via Bluetooth")

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
            device = self._get_device()
            if device is None:
                raise UpdateFailed(f"Bed {self.address} not available via Bluetooth")

            success = await self.bed.async_set_preset(device, preset, side)
            if not success:
                raise UpdateFailed("Failed to set preset")

    async def async_set_underbed_light(self, on: bool) -> None:
        """Turn underbed light on or off."""
        async with self._ble_lock:
            device = self._get_device()
            if device is None:
                raise UpdateFailed(f"Bed {self.address} not available via Bluetooth")

            success = await self.bed.async_set_underbed_light(device, on)
            if not success:
                raise UpdateFailed("Failed to set underbed light")

    async def async_set_foundation_position(
        self, side: int, head: int, foot: int
    ) -> None:
        """Set foundation position and refresh."""
        async with self._ble_lock:
            device = self._get_device()
            if device is None:
                raise UpdateFailed(f"Bed {self.address} not available via Bluetooth")

            success = await self.bed.async_set_foundation_position(
                device, side, head, foot
            )
            if not success:
                raise UpdateFailed("Failed to set foundation position")

        await self.async_request_refresh()

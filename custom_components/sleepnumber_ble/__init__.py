"""Sleep Number BLE integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import SleepNumberBLECoordinator

_LOGGER = logging.getLogger(__name__)

type SleepNumberBLEConfigEntry = ConfigEntry[SleepNumberBLECoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SleepNumberBLEConfigEntry) -> bool:
    """Set up Sleep Number BLE from a config entry."""
    address = entry.data["address"]
    coordinator = SleepNumberBLECoordinator(hass, address)

    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_setup()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SleepNumberBLEConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: SleepNumberBLECoordinator = entry.runtime_data
    await coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

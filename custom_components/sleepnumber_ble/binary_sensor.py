"""Binary sensor entities for Sleep Number BLE."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    _hass: HomeAssistant,
    _entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    # Presence detection is not available over BLE on firmware 0.4.x.
    # func=24/25 always return 0, func=97 returns no occupancy data.
    async_add_entities([])

"""Config flow for Sleep Number BLE integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SleepNumberBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sleep Number BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle Bluetooth discovery."""
        _LOGGER.debug(
            "Discovered Sleep Number bed: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None
        if user_input is not None:
            return self.async_create_entry(
                title=f"Sleep Number ({self._discovery_info.address})",
                data={"address": self._discovery_info.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovery_info.name or self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual configuration (fallback)."""
        if user_input is not None:
            await self.async_set_unique_id(user_input["address"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Sleep Number ({user_input['address']})",
                data={"address": user_input["address"]},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=config_entries.vol.Schema({
                config_entries.vol.Required("address"): str,
            }),
        )

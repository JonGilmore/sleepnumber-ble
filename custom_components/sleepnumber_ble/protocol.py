"""Sleep Number MCR BLE protocol implementation."""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    MCR_CMD_FOUNDATION,
    MCR_CMD_PUMP,
    MCR_FUNC_FORCE_IDLE,
    MCR_FUNC_FOUNDATION_OUTLET_READ,
    MCR_FUNC_INIT,
    MCR_FUNC_OUTLET,
    MCR_FUNC_PRESET,
    MCR_FUNC_READ,
    MCR_FUNC_SET,
    MCR_RX_UUID,
    MCR_STATUS_FOUNDATION,
    MCR_STATUS_PUMP,
    MCR_SYNC,
    MCR_TX_UUID,
    OUTLET_UNDERBED_LIGHT,
    SIDE_LEFT,
    SIDE_RIGHT,
)

_LOGGER = logging.getLogger(__name__)

MCR_FUNC_FOUNDATION_STATUS = 18  # cmd=0x42: live foundation status (15-byte payload)


@dataclass
class BedStatus:
    """Current bed status."""

    left_sleep_number: int = 0
    right_sleep_number: int = 0
    left_pumping: bool = False
    right_pumping: bool = False
    # Underbed light
    underbed_light_on: bool | None = None
    # Foundation positions (0-100). Read via cmd=0x42 func=18 byte indices 2/4/6/8.
    # Side mapping (rH/rF/lH/lF) is a best-guess hypothesis from a single Android
    # BT HCI capture and may be wrong — verify with diverse position captures.
    right_head_position: int = 0
    right_foot_position: int = 0
    left_head_position: int = 0
    left_foot_position: int = 0
    # True while any foundation actuator is in motion (preset, position set).
    foundation_moving: bool = False


def _mcr_crc(data: bytes) -> int:
    """Calculate MCR Fletcher-style CRC."""
    s, r = 0, 0
    for b in data:
        s += b
        r += s
    return r & 0xFFFF


def _build_mcr(
    cmd_type: int,
    sub: int,
    status: int,
    func_code: int,
    side: int,
    payload: bytes = b"",
) -> bytes:
    """Build an MCR frame."""
    header = bytes(
        [
            cmd_type,
            0x00,
            0x00,
            (sub >> 8) & 0xFF,
            sub & 0xFF,
            status,
            0x00,
            0x00,
            func_code,
            (side << 4) | (len(payload) & 0x0F),
        ]
    )
    body = header + payload
    crc = _mcr_crc(body)
    return MCR_SYNC + body + struct.pack(">H", crc)


def _parse_pump_status(data: bytes) -> dict | None:
    """Parse a pump status notification into a dict."""
    if len(data) < 17 or data[0] != 0x16 or data[1] != 0x16:
        return None
    hdr = data[2:]
    if (hdr[8] & 0x7F) != MCR_FUNC_READ or (hdr[9] & 0x0F) < 5:
        return None
    return {
        "left_sleep_number": hdr[11],
        "right_sleep_number": hdr[12],
        "left_pumping": hdr[13] != 0,
        "right_pumping": hdr[14] != 0,
    }


def _parse_foundation_status(notifications: list[bytes]) -> dict | None:
    """Parse foundation status from cmd=0x42 func=18 response.

    Response is 15 bytes split across notifications (MTU=23 only fits ~10 payload
    bytes per frame). Layout reverse-engineered from an Android BT HCI capture:

        byte 0:  status flags — bit 0 = 1 while any actuator is moving
        byte 2:  head position (verified for the side currently being moved)
        byte 4:  position (hypothesized: foot)
        byte 6:  position (hypothesized: other-side head)
        byte 8:  position (hypothesized: other-side foot)
        byte 10: redundant moving flag (1 = moving, 0 = settled)
        byte 14: appears to be a max/target value (0x44 idle, 0x64=100 once active)

    The byte 2/4/6/8 → side+actuator mapping is a hypothesis from a single capture
    (snore on side=1 only moved byte 2). Verify with diverse captures.
    """
    payload = b""
    found = False
    for data in notifications:
        if not found:
            if len(data) < 12 or data[0] != 0x16 or data[1] != 0x16:
                continue
            hdr = data[2:]
            func = hdr[8] & 0x7F
            if func != MCR_FUNC_FOUNDATION_STATUS:
                continue
            payload = hdr[10:]
            found = True
        else:
            # Continuation fragments do not start with sync bytes
            if len(data) >= 2 and data[0] == 0x16 and data[1] == 0x16:
                break
            payload += data

    if not found or len(payload) < 11:
        return None

    moving = bool(payload[0] & 0x01) or (len(payload) > 10 and payload[10] != 0)
    return {
        "foundation_moving": moving,
        "right_head_position": payload[2],
        "right_foot_position": payload[4],
        "left_head_position": payload[6],
        "left_foot_position": payload[8],
    }


def _bed_address_from_mac(mac: str) -> int:
    """Derive MCR bed address from BLE MAC address (last 2 bytes)."""
    parts = mac.upper().replace("-", ":").split(":")
    return (int(parts[-2], 16) << 8) | int(parts[-1], 16)


class SleepNumberBed:
    """Communicate with a Sleep Number bed over BLE."""

    def __init__(self, address: str) -> None:
        """Initialize with BLE MAC address."""
        self._address = address
        self._bed_addr = _bed_address_from_mac(address)
        self._notifications: list[bytes] = []
        self._notify_event: asyncio.Event = asyncio.Event()
        self._client: BleakClient | None = None

    @property
    def bed_address(self) -> int:
        """Return the MCR bed address."""
        return self._bed_addr

    @property
    def is_connected(self) -> bool:
        """Return True if we have a live BLE connection."""
        return self._client is not None and self._client.is_connected

    def _notification_handler(self, _sender: int, data: bytearray) -> None:
        """Handle BLE notifications."""
        _LOGGER.debug("Notification received: %s", bytes(data).hex(" "))
        self._notifications.append(bytes(data))
        self._notify_event.set()

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.debug("BLE connection lost to %s", self._address)
        self._client = None

    async def _ensure_connected(self, device: BLEDevice | None) -> BleakClient:
        """Return an existing connected client, or establish a new connection.

        device can be None if we already have a connection (the scanner may not
        see the bed while it's connected since it stops advertising).
        """
        if self._client is not None and self._client.is_connected:
            return self._client

        if device is None:
            raise BleakError("No BLE device available to connect")

        _LOGGER.debug("Connecting to bed at %s", device.address)
        client = await establish_connection(
            BleakClient,
            device,
            self._address,
            max_attempts=3,
            disconnected_callback=self._on_disconnect,
        )
        _LOGGER.debug("Connected, MTU=%s", client.mtu_size)

        await client.start_notify(MCR_TX_UUID, self._notification_handler)

        # Init handshake
        self._notifications.clear()
        self._notify_event.clear()
        result = await self._send_raw(
            client,
            _build_mcr(
                MCR_CMD_PUMP, 0x0000, MCR_STATUS_PUMP, MCR_FUNC_INIT, 0, b"\x00" * 8
            ),
            timeout=10.0,
        )
        if not result:
            _LOGGER.warning("Init handshake failed")
            await client.disconnect()
            raise BleakError("Init handshake failed")

        self._client = client
        return client

    async def async_disconnect(self) -> None:
        """Disconnect from the bed."""
        client = self._client
        self._client = None
        if client and client.is_connected:
            try:
                await client.disconnect()
            except BleakError:
                _LOGGER.debug("Error during disconnect", exc_info=True)

    async def _send_raw(
        self, client: BleakClient, data: bytes, timeout: float = 10.0
    ) -> list[bytes]:
        """Send data and wait for notification response (no reconnect logic)."""
        self._notifications.clear()
        self._notify_event.clear()
        _LOGGER.debug("Writing %d bytes: %s", len(data), data.hex(" "))

        written = False
        for response_mode, desc in [(True, "with-response"), (False, "no-response")]:
            try:
                await client.write_gatt_char(MCR_RX_UUID, data, response=response_mode)
                _LOGGER.debug("Write (%s) succeeded", desc)
                written = True
                break
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.debug("Write (%s) failed: %s", desc, e)

        if not written:
            _LOGGER.warning("All write modes failed")
            return []

        try:
            await asyncio.wait_for(self._notify_event.wait(), timeout=timeout)
            await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            _LOGGER.debug("No notification within %ss", timeout)

        return list(self._notifications)

    async def _send(
        self,
        device: BLEDevice | None,
        data: bytes,
        timeout: float = 10.0,
    ) -> list[bytes]:
        """Send data with automatic connect and one retry on failure."""
        client = await self._ensure_connected(device)
        try:
            return await self._send_raw(client, data, timeout)
        except (BleakError, asyncio.TimeoutError):
            _LOGGER.debug("Send failed, reconnecting", exc_info=True)
            await self.async_disconnect()
            client = await self._ensure_connected(device)
            return await self._send_raw(client, data, timeout)

    async def async_connect_and_read(
        self, device: BLEDevice | None
    ) -> BedStatus | None:
        """Connect (if needed), read all status."""
        try:
            status = BedStatus()

            # Read pump status (func=18)
            result = await self._send(
                device,
                _build_mcr(
                    MCR_CMD_PUMP,
                    self._bed_addr,
                    MCR_STATUS_PUMP,
                    MCR_FUNC_READ,
                    0x0F,
                ),
            )
            pump = None
            for data in result:
                pump = _parse_pump_status(data)
                if pump:
                    break

            if pump:
                status.left_sleep_number = pump["left_sleep_number"]
                status.right_sleep_number = pump["right_sleep_number"]
                status.left_pumping = pump["left_pumping"]
                status.right_pumping = pump["right_pumping"]
                _LOGGER.debug(
                    "Pump: L=%s R=%s",
                    status.left_sleep_number,
                    status.right_sleep_number,
                )
            else:
                _LOGGER.warning("Failed to parse pump status")
                return None

            # Read foundation status (cmd=0x42 func=18) — gives positions + movement flag
            result = await self._send(
                device,
                _build_mcr(
                    MCR_CMD_FOUNDATION,
                    self._bed_addr,
                    MCR_STATUS_FOUNDATION,
                    MCR_FUNC_FOUNDATION_STATUS,
                    0,
                ),
                timeout=5.0,
            )
            foundation = _parse_foundation_status(result)
            if foundation:
                status.foundation_moving = foundation["foundation_moving"]
                status.right_head_position = foundation["right_head_position"]
                status.right_foot_position = foundation["right_foot_position"]
                status.left_head_position = foundation["left_head_position"]
                status.left_foot_position = foundation["left_foot_position"]
                _LOGGER.debug(
                    "Foundation: moving=%s LH=%s LF=%s RH=%s RF=%s",
                    status.foundation_moving,
                    status.left_head_position,
                    status.left_foot_position,
                    status.right_head_position,
                    status.right_foot_position,
                )
            else:
                _LOGGER.debug("Foundation status unavailable")

            # Read underbed light state via foundation (func=20, side=3)
            result = await self._send(
                device,
                _build_mcr(
                    MCR_CMD_FOUNDATION,
                    self._bed_addr,
                    MCR_STATUS_FOUNDATION,
                    MCR_FUNC_FOUNDATION_OUTLET_READ,
                    OUTLET_UNDERBED_LIGHT,
                ),
                timeout=3.0,
            )
            for data in result:
                if (
                    len(data) >= 13
                    and data[0] == 0x16
                    and data[1] == 0x16
                    and (data[10] & 0x7F) == MCR_FUNC_FOUNDATION_OUTLET_READ
                    and (data[11] & 0x0F) >= 1
                ):
                    status.underbed_light_on = data[12] != 0
                    _LOGGER.debug("Underbed light: %s", status.underbed_light_on)
                    break

            return status
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error communicating with bed at %s", self._address)
            return None

    async def async_force_idle(self, device: BLEDevice | None) -> bool:
        """Send ForceIdle to stop any in-progress pump adjustment."""
        try:
            await self._send(
                device,
                _build_mcr(
                    MCR_CMD_PUMP,
                    self._bed_addr,
                    MCR_STATUS_PUMP,
                    MCR_FUNC_FORCE_IDLE,
                    0,
                ),
                timeout=3.0,
            )
            return True
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug("Error sending force idle", exc_info=True)
            return False

    async def async_set_sleep_number(
        self, device: BLEDevice | None, side: int, value: int
    ) -> bool:
        """Set sleep number for one side. Sends ForceIdle first to stop any current adjustment."""
        value = max(5, min(100, value))
        try:
            # Stop any in-progress adjustment first
            await self._send(
                device,
                _build_mcr(
                    MCR_CMD_PUMP,
                    self._bed_addr,
                    MCR_STATUS_PUMP,
                    MCR_FUNC_FORCE_IDLE,
                    0,
                ),
                timeout=2.0,
            )

            await self._send(
                device,
                _build_mcr(
                    MCR_CMD_PUMP,
                    self._bed_addr,
                    MCR_STATUS_PUMP,
                    MCR_FUNC_SET,
                    side,
                    bytes([0x00, value]),
                ),
                timeout=5.0,
            )
            return True
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error setting sleep number")
            return False

    async def async_set_preset(
        self, device: BLEDevice | None, preset: int, side: int | None = None
    ) -> bool:
        """Activate a foundation preset.

        If side is None, sends to both sides. Otherwise sends to specified side only.
        """
        sides = [SIDE_LEFT, SIDE_RIGHT] if side is None else [side]
        try:
            for s in sides:
                await self._send(
                    device,
                    _build_mcr(
                        MCR_CMD_FOUNDATION,
                        self._bed_addr,
                        MCR_STATUS_FOUNDATION,
                        MCR_FUNC_PRESET,
                        s,
                        bytes([preset, 0x00]),
                    ),
                    timeout=3.0,
                )
            return True
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error setting preset")
            return False

    async def async_set_underbed_light(
        self, device: BLEDevice | None, on: bool
    ) -> bool:
        """Turn underbed light on or off."""
        try:
            mode = 1 if on else 0
            await self._send(
                device,
                _build_mcr(
                    MCR_CMD_FOUNDATION,
                    self._bed_addr,
                    MCR_STATUS_FOUNDATION,
                    MCR_FUNC_OUTLET,
                    OUTLET_UNDERBED_LIGHT,
                    bytes([mode, 0, 0]),
                ),
                timeout=3.0,
            )
            return True
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error setting underbed light")
            return False

    async def async_set_foundation_position(
        self, device: BLEDevice | None, side: int, head: int, foot: int
    ) -> bool:
        """Set foundation head and foot position for one side (0-100)."""
        head = max(0, min(100, head))
        foot = max(0, min(100, foot))
        try:
            await self._send(
                device,
                _build_mcr(
                    MCR_CMD_FOUNDATION,
                    self._bed_addr,
                    MCR_STATUS_FOUNDATION,
                    MCR_FUNC_SET,
                    side,
                    bytes([head, 0, foot, 0]),
                ),
                timeout=5.0,
            )
            return True
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error setting foundation position")
            return False

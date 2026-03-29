# Sleep Number Bed BLE Protocol Reference

Reverse-engineered from the SleepIQ Android app v5.3.32 and live testing against an
I8 Flextop King / 360 FlexFit 2 bed (BAM module firmware 0.4.1d9).

## Overview

Sleep Number 360 beds contain a **BAM module** (BLE + WiFi) that exposes a BLE GATT
server using the **MCR (Multi-Channel Radio)** binary protocol. This document describes
how to communicate with the bed over BLE to read status and control firmness, foundation
presets, and other features.

The Android app also contains a higher-level "Bamkey" text protocol and a "FuzionBLE"
library with different UUIDs (`09d23fae-...`). These may be used on newer bed firmwares.
The I8/360 FlexFit 2 with BAM firmware 0.4.x uses the MCR binary protocol described here.

---

## Device Information

| Field          | Value                                             |
| -------------- | ------------------------------------------------- |
| BLE Name       | MAC address as string (e.g., `64:db:a0:07:dd:02`) |
| Manufacturer   | Select Comfort/BAM                                |
| Model          | SMART Sleep Smart Pump                            |
| Firmware       | 0.4.1d9                                           |
| Hardware       | EVT3                                              |
| WiFi + BLE MAC | Same address for both radios                      |

---

## BLE GATT Structure

### Service

| UUID                                   | Description      |
| -------------------------------------- | ---------------- |
| `ffffd1fd-388d-938b-344a-939d1f6efee0` | MCR UART Service |

### Characteristics

| Name       | UUID      | Properties             | Handle | Description              |
| ---------- | --------- | ---------------------- | ------ | ------------------------ |
| **MCR TX** | `...fee1` | Notify                 | 0x0021 | Bed → Client (responses) |
| **MCR RX** | `...fee2` | Write-Without-Response | 0x0025 | Client → Bed (commands)  |

**Note:** Despite MCR RX advertising only `write-without-response`, when using an
ESPHome BLE Proxy, you **must** use `write-with-response` mode. The proxy silently
drops write-without-response packets.

### Standard Services Also Present

| UUID     | Service                                                              |
| -------- | -------------------------------------------------------------------- |
| `0x1800` | Generic Access (device name, appearance)                             |
| `0x1801` | Generic Attribute (service changed indication)                       |
| `0x180A` | Device Information (manufacturer, model, serial, firmware, hardware) |

---

## Connection Flow

```
1. Scan for BLE device advertising service UUID ffffd1fd-388d-938b-344a-939d1f6efee0
   (the bed advertises its MAC address as its BLE name)
2. Connect to GATT server
3. Subscribe to notifications on MCR TX characteristic (UUID ...fee1)
4. Optionally bond via BLE encryption (not strictly required for basic operation)
5. Send MCR init handshake
6. Bed responds with its MCR address (derived from last 2 bytes of MAC)
7. Send MCR commands using the bed address
8. Disconnect when done (connect-on-demand model works well)
```

**MTU:** Stays at 23 bytes (bed does not negotiate higher). Max write payload = 20 bytes.
Responses >20 bytes are split across multiple BLE notifications.

---

## MCR Frame Format

All communication uses MCR frames written to MCR RX and received from MCR TX.

### Wire Format

```
[0x16][0x16] + [10-byte header] + [0-15 byte payload] + [CRC_MSB][CRC_LSB]
```

Total frame size: 14 to 29 bytes.

### Header (10 bytes)

```
Byte 0:   Command type
            0x02 = Pump commands (firmness)
            0x42 = Foundation commands (presets, positions)
Byte 1-2: Target address (big-endian, usually 0x0000)
Byte 3-4: Sub-address (big-endian, bed MCR address for commands, 0x0000 for init)
Byte 5:   Status / device class
            0x02 = Pump operations
            0x42 = Foundation operations
Byte 6-7: Echo address (big-endian, usually 0x0000)
Byte 8:   Function code (see tables below)
Byte 9:   Upper nibble = side selector (0=left, 1=right)
          Lower nibble = payload length (0-15)
```

### CRC Calculation (Fletcher-style)

```python
def mcr_crc(data: bytes) -> int:
    """Calculate over header + payload (NOT sync bytes)."""
    s, r = 0, 0
    for b in data:
        s += b
        r += s
    return r & 0xFFFF
```

CRC is appended as 2 bytes, big-endian, after the payload.

### MCR Address

The bed's MCR address is derived from the last 2 bytes of its BLE MAC address.

Example: MAC `64:DB:A0:07:DD:02` → MCR address `0xDD02`

---

## Init Handshake

**Must be sent first** before any other commands. The bed ignores queries without this.

### Request

```
cmd=0x02, target=0x0000, sub=0x0000, status=0x02, func=0, payload=8 zero bytes
```

**Hex:** `16 16 02 00 00 00 00 02 00 00 00 08 00 00 00 00 00 00 00 00 00 86`

### Response

```
cmd=0x01, target=BED_ADDR, echo=BED_ADDR, func=0|0x80 (response bit set)
```

The response contains the bed's MCR address in the target and echo fields.

---

## Pump / Firmness Commands

### Read Pump Status (func=18)

```python
frame = build_mcr(cmd=0x02, sub=BED_ADDR, status=0x02, func=18, side=0x0F)
```

**Response payload (5 bytes):**

```
[pump_on, left_sleep_number, right_sleep_number, left_pumping, right_pumping]
```

| Byte | Description                 | Range    |
| ---- | --------------------------- | -------- |
| 0    | Pump controller active      | 0 or 1   |
| 1    | Left sleep number           | 0-100    |
| 2    | Right sleep number          | 0-100    |
| 3    | Left side actively pumping  | 0 = idle |
| 4    | Right side actively pumping | 0 = idle |

### Set Sleep Number (func=17)

```python
def build_set_sn(side, value):
    """side: 0=left, 1=right. value: 0-100."""
    payload = bytes([0x00, value])
    header = bytes([
        0x02, 0x00, 0x00,                      # cmd, target
        (BED_ADDR >> 8), BED_ADDR & 0xFF,       # sub = bed address
        0x02, 0x00, 0x00,                       # status=0x02 (pump), echo
        17,                                     # func=17 (SET)
        (side << 4) | len(payload),             # side selector | payload len
    ])
    # ... add CRC and sync bytes
```

**Important:**

- Only one side can be adjusted at a time
- Wait for the pump to finish (poll func=18, check bytes 3-4 are both 0) before
  setting the other side
- The pump takes 30-90+ seconds to adjust, depending on the delta

---

## Foundation / Preset Commands

### Activate Preset (func=21)

```python
def build_preset(side, preset_val):
    """side: 0=left, 1=right."""
    payload = bytes([preset_val, 0x00])
    header = bytes([
        0x42, 0x00, 0x00,                      # cmd=0x42 (foundation)
        (BED_ADDR >> 8), BED_ADDR & 0xFF,       # sub = bed address
        0x42, 0x00, 0x00,                       # status=0x42 (FOUNDATION!)
        21,                                     # func=21 (activate preset)
        (side << 4) | len(payload),             # side | payload len
    ])
    # ... add CRC and sync bytes
```

**CRITICAL:** Foundation commands use `status=0x42` (byte 5), NOT `0x02`.
This identifies the command as targeting the foundation controller, not the pump.

### Preset Values

| Preset     | Value | Physical Behavior                          |
| ---------- | ----- | ------------------------------------------ |
| Favorite   | 1     | Moves both heads + feet (whole bed)        |
| Read       | 2     | Moves both heads + feet (whole bed)        |
| Watch TV   | 3     | Moves both heads + feet (whole bed)        |
| **Flat**   | **4** | Lowers THIS side's head + shared feet only |
| **Zero G** | **5** | Moves both heads + feet (whole bed)        |
| **Snore**  | **6** | Raises THIS side's head only, feet go down |

### Foundation Physical Behavior

- **Each side has its own head actuator** (independent)
- **Feet are shared** between both sides (one actuator)
- Whole-bed presets (Zero-G, Read, Watch TV, Favorite) move everything
- Flat only lowers the selected side's head + feet
- Snore only raises the selected side's head
- **Cannot lower both heads simultaneously** - when going from Zero-G to Flat,
  one side flattens per command. Send Flat to each side sequentially.

---

## MCR Function Code Reference (Verified)

Tested with `cmd=0x02, sub=BED_ADDR, status=0x02`:

### Functions That Return Data

| Func   | Response Payload                        | Interpretation                |
| ------ | --------------------------------------- | ----------------------------- |
| **18** | `[pump_on, L_SN, R_SN, L_pump, R_pump]` | **Pump Status** (5 bytes)     |
| **20** | `[sleep_number, pressure]`              | Pressure reading (2 bytes)    |
| **26** | `[pump_on, L_SN, R_SN, ?]`              | Sleep Number (short, 4 bytes) |
| 3      | `[0xFE, 0, 0, 0, 0, 0, 0]`              | Configuration flags (7 bytes) |
| 5      | 11 bytes (all zeros when flat)          | Foundation positions          |
| 34     | 15+ bytes (split across notifications)  | Full system status            |

### Functions That Return Empty ACK

| Func   | Notes                            |
| ------ | -------------------------------- |
| 1      | Device ACK                       |
| 2      | Device ACK                       |
| 6      | Status ACK                       |
| 17     | **SET function** (write values)  |
| 21     | **Activate preset** (foundation) |
| 22     | Preset store                     |
| 32     | System setting                   |
| 38, 39 | Unknown                          |

### Functions With No Response

4, 7-16, 19, 23-25, 27-31, 33, 35-37, 40

### Command Type Variations

The same function codes work across all three command types:

- `cmd=0x02` → response has `cmd=0x01`
- `cmd=0x42` → response has `cmd=0x41`
- `cmd=0x92` → response has `cmd=0x16`

Foundation operations (presets, positions) use `cmd=0x42` with `status=0x42`.
Pump operations (firmness) use `cmd=0x02` with `status=0x02`.

---

## Response Format

Responses arrive as BLE notifications on MCR TX. Same frame structure as requests.

Key differences in response headers:

- **Byte 8** has bit 7 set (`flags | 0x80`) indicating this is a response
- **Target/echo** fields contain the bed's MCR address
- **Status** field contains the bed's device ID (typically `0x01` for pump, `0x41` for foundation)

---

## Known Addresses

| Address  | Meaning                                              |
| -------- | ---------------------------------------------------- |
| `0xDD02` | Bed pump/foundation controller (last 2 bytes of MAC) |
| `0x0002` | BLE client controller (our source ID for pump)       |
| `0x0042` | BLE client controller (our source ID for foundation) |
| `0x0000` | Broadcast / init target                              |

---

## ESPHome BLE Proxy Notes

When communicating through an ESPHome Bluetooth Proxy:

1. **Must use `write-with-response`** even though the characteristic only advertises
   `write-without-response`. The ESP-IDF BLE stack silently drops WNR packets through
   the proxy.
2. **Use `bleak-retry-connector`** (`establish_connection()`) for reliable connections
   instead of raw `BleakClient()`.
3. **Connection locking** is essential - only one BLE connection to the bed at a time.
   Concurrent connections cause `BluetoothConnectionDroppedError`.
4. **Notifications work correctly** through the proxy once the write issue is resolved.

---

## Home Assistant Integration Architecture

```
HA UI (number/select entities)
    ↓
SleepNumberBLECoordinator (DataUpdateCoordinator, asyncio.Lock)
    ↓
SleepNumberBed (protocol.py)
    ↓
bleak_retry_connector → BleakClient
    ↓
ESPHome BLE Proxy (ESP32)
    ↓
Sleep Number Bed (BLE GATT)
```

- Polls every 120 seconds for firmness status
- Fast-polls every 10 seconds after a set operation until pump is idle
- Optimistic updates for firmness slider (shows target immediately)
- Foundation presets are fire-and-forget (no state readback available)

---

## Bed Presence / Occupancy (func=24)

```python
# Query per-side: side=0 for left, side=1 for right
frame = build_mcr(cmd=0x02, sub=BED_ADDR, status=0x02, func=24, side=SIDE)
```

**Response payload (1 byte):**

- `[1]` = occupied (someone in bed)
- `[0]` = empty

func=25 returns identical data and may be redundant.

---

## Push Notifications (Not Supported)

Thorough analysis of the decompiled app confirms the bed is **purely request/response**.
There are no unsolicited push notifications for presence changes or any other state.

Evidence from APK analysis:

- The app's UartManager routes ALL BLE notifications through two paths:
  1. `mo14867s()` - broadcast to observers (but the only observer ignores messages in PERSISTENT mode)
  2. `m15009a()` - match against pending requests (unmatched messages are silently dropped)
- The PERSISTENT connection mode exists for faster polling, not for receiving push data
- The app polls for presence the same way we do

A 2+ minute passive listening test with someone in the bed confirmed: zero unsolicited
notifications received. Polling is the only option.

---

## Unexplored Areas

- ~~Bed presence/occupancy detection~~ - **SOLVED:** func=24, per-side, see above
- ~~Push notifications~~ - **NOT SUPPORTED:** bed is purely request/response
- **Foundation position readback** - func=5 returns 11 bytes but always zeros (may need
  different addressing or cmd type)
- **Massage control** - func=17 with cmd=0x42 and 12-byte payload (from decompiled code)
- **Underbed lights** - mentioned in decompiled code but not yet tested
- **Foot warming** - temperature control available on some models
- **Responsive Air** - automatic pressure adjustment feature

---

## Appendix: Bamkey Protocol (Newer Firmware)

The Android app also contains a text-based "Bamkey" protocol for newer bed firmwares
that use the FuzionBLE service (`09d23fae-90e6-44c2-95b6-0b3d0f1abf25`). This protocol
uses 4-character command codes (e.g., `SYCG`, `PSNS`, `ACTG`) with space-delimited text
arguments, wrapped in FuzionBLE blob frames (`"fUzIoN"` preamble + CRC32). Over 130
commands were found in the decompiled app. The I8/360 bed tested here does NOT use this
protocol - it uses the binary MCR protocol described above.

---

## Appendix: Decompilation Reference

The protocol was reverse-engineered from:

- **APK:** `com.selectcomfort.SleepIQ` v5.3.32
- **Tools:** `jadx` (Java decompilation), `apktool` (resource extraction)
- **Key packages:**
  - `com.fuzionble.implementation` - FuzionBLE library
  - `com.selectcomfort.blelib.mcr.manager` - MCR protocol implementation
  - `com.selectcomfort.bedcontrolframework.fuzion.bamkey` - Bamkey text commands
  - `ye/` - MCR message classes (PumpStatus, FoundationActivatePreset, etc.)
  - `p038Be/C0301b.java` - UART BLE manager

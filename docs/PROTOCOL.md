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

### Pump Functions (cmd=0x02, status=0x02)

| Func   | Response Payload                        | Interpretation                            |
| ------ | --------------------------------------- | ----------------------------------------- |
| **18** | `[pump_on, L_SN, R_SN, L_pump, R_pump]` | **Pump Status** (5 bytes)                 |
| **24** | `[0]` per side (always)                 | Bed Presence flag — **BROKEN, always 0**  |
| **26** | `[pump_on, L_SN, R_SN, ?]`              | Sleep Number short (4 bytes)              |
| 3      | `[0xFE, 0, 0, 0, 0, 0, 0]`              | Config/capability flags (7 bytes)         |
| 4      | 14 bytes (left only)                    | Unknown                                   |
| 5      | 11 bytes (zeros when flat)              | Foundation positions (not side-dependent) |
| 19     | `[5, 5]`                                | **SetSleepNumberAsFavorite** (WRITE, stores favorite)  |
| 20     | `[5, 5]`                                | **GetSleepNumberFavorite** (read, per-side favorite SN) |
| 22     | `[90, 19, 4, 160, 49, 1, 2, 40]` (left) | **Stored preset positions** (8 bytes)     |
| 25     | `[0]` per side (always)                 | Bed presence (dup of 24) — **also broken**|
| 34     | `[0, 0, 0, 4, 160, 83, 20, 88]`         | Full system status (15 bytes, fragmented) |
| 39     | `[0, 0, 0, 0, 0]` (left only)           | Unknown                                   |

### Foundation Functions (cmd=0x42, status=0x42)

| Func   | Response Payload                        | Interpretation                             |
| ------ | --------------------------------------- | ------------------------------------------ |
| **18** | `[67, 100, 100, 76, 76, 0, 0, 0]` (15b) | **Foundation Status** (positions/features) |
| **21** | (empty ACK)                             | **Activate Preset** (write command)        |
| 3      | `[254]` (left), `[255]` (right)         | Device capability flags                    |
| 5      | 11 bytes (zeros when flat)              | Foundation positions                       |
| 17     | (empty ACK)                             | **SET position** (write, see safety note)  |
| 19     | (empty ACK)                             | Foundation outlet control                  |
| 20     | `[0, 0, 0]` (right only)                | Foot warming status (0s = not installed)   |
| 22     | (empty ACK)                             | Store preset                               |
| 26     | `[67, 0, 0, 0, 0, 0, 0, 0]` (11 bytes)  | Massage status (zeros = off)               |

### New Pump Functions from APK Decompilation (Not Yet Tested)

| Func   | App Class Name          | Type    | Payload                  | Interpretation                             |
| ------ | ----------------------- | ------- | ------------------------ | ------------------------------------------ |
| **97** | GetChamberTypesCall     | **READ** | send `[0, 0]`, side=2  | **Chamber types + OCCUPANCY** (8 bytes)    |

**func=97 (GetChamberTypes) is the most promising lead for presence detection.**

From decompiled `GetChamberTypesCall.kt` (`C9871k.java`):

```
MCR Request:  cmd=0x02, status=0x02, func=97, side=2, payload=[0, 0]

Response (8 bytes):
  byte[0] = rightChamberPresence   (chamber detected: 0 or 1)
  byte[1] = rightChamberTypeCode   (0=STANDARD, 1=KID, 2=HEADTILT, 3=GENIE)
  byte[2] = leftChamberPresence    (chamber detected: 0 or 1)
  byte[3] = leftChamberTypeCode
  byte[4] = rightSideOccupancy     ← OCCUPANCY (person in bed)
  byte[5] = rightSideRefreshState
  byte[6] = leftSideOccupancy      ← OCCUPANCY (person in bed)
  byte[7] = leftSideRefreshState

If response < 8 bytes, occupancy fields (bytes 4-7) default to 0.
```

The app also has a cloud API fallback (`GetChamberTypesResponse`) with identical
fields: `leftChamberOccupancy`, `rightChamberOccupancy`, `leftChamberRefreshedState`,
`rightChamberRefreshedState`. Both BLE and cloud return the same structure.

**Note:** side=2 in byte 9 upper nibble is unusual (normally 0=left, 1=right,
0x0F=both). This may be a "query both chambers" addressing mode.

**Tested 2026-03-30:** Firmware 0.4.x returns only 4 bytes `[1, 0, 1, 0]` —
chamber presence and type for both sides (both STANDARD, both present), but
**does NOT include the occupancy bytes (4-7)**. The response is static
regardless of actual bed occupancy. The app handles this gracefully:
`bArr.length < 8 ? (byte) 0 : bArr[4]` — occupancy defaults to 0 on short
responses, and the app falls back to the cloud API for presence.

**Conclusion:** func=97 confirms the bed has two STANDARD chambers but does
not provide occupancy data on firmware 0.4.x.

### New Foundation Functions from APK Decompilation

| Func   | App Class Name                 | Type     | Interpretation                                |
| ------ | ------------------------------ | -------- | --------------------------------------------- |
| **37** | GetFoundationSystemStatusCall  | **READ** | Foundation system status (side=0, no payload) |
| **40** | GetPinchStateCall              | **READ** | Anti-pinch sensor state (per-side)            |
| **42** | GetFootWarmingStatusCall       | **READ** | Foot warming temp/status (per-side)           |
| 36     | (FoundationSystemSetting)      | WRITE    | Foundation system config                      |
| 41     | SetFootWarmingStatusCall       | WRITE    | Set foot warming (per-side, 3-byte payload)   |

### Sense & Do Functions (cmd=0x32, status=0x32)

"Sense & Do" controls smart outlet integration, **not pressure sensing** (the name is
misleading). It is a simple feature toggle — no sensor data.

| Func   | App Class Name     | Type     | Interpretation                       |
| ------ | ------------------ | -------- | ------------------------------------ |
| **18** | GetSenseAndDoCall  | **READ** | Query outlet on/off (1 byte: isOn)   |
| 20     | SetSenseAndDoCall  | WRITE    | Toggle outlet on/off (2-byte payload)|

### Smart Outlet Functions (cmd=0x92, status=0x92)

| Func   | App Class Name           | Type     | Interpretation                    |
| ------ | ------------------------ | -------- | --------------------------------- |
| **18** | GetSmartOutletStatusCall | **READ** | Query all outlet states           |
| 19     | SmartOutletChange        | READ     | Outlet state (already documented) |

### Device Management Functions (cmd=0x72, status=0x72)

| Func   | App Class Name           | Type     | Interpretation                    |
| ------ | ------------------------ | -------- | --------------------------------- |
| **18** | GetNodeListCall          | **READ** | List connected MCR nodes          |
| 17     | DoFoundationShortBindCall| WRITE    | Bind/pair foundation (1-byte payload) |

### Pump Empty ACK Functions (cmd=0x02)

| Func | Notes                                |
| ---- | ------------------------------------ |
| 1    | Device ACK                           |
| 2    | ForceIdle / interrupt adjustment     |
| 6    | Status ACK                           |
| 17   | **SET sleep number** (write command) |
| 32   | System setting                       |

### Command Type Variations

Different command types target different subsystems:

| Cmd    | Status | Response Prefix | Subsystem                                |
| ------ | ------ | --------------- | ---------------------------------------- |
| `0x02` | `0x02` | `0x01`          | Pump/pressure                            |
| `0x42` | `0x42` | `0x41`          | Foundation/motors                        |
| `0x32` | `0x32` | —               | Sense & Do (smart outlet toggle, NOT sensing) |
| `0x72` | `0x72` | —               | Device management (node list, binding)   |
| `0x92` | `0x92` | `0x16`          | Smart outlet                             |

### Safety Warning

> **DO NOT send func=17 with cmd=0x42 (foundation SET) without a properly formatted
> payload.** The bed will interpret missing or zero payload bytes as position values and
> attempt to move actuators to extreme positions, potentially damaging the motors.

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

## Bed Presence / Occupancy

### func=24/25 — BROKEN (Always Returns 0)

```python
# These do NOT work on firmware 0.4.x
frame = build_mcr(cmd=0x02, sub=BED_ADDR, status=0x02, func=24, side=SIDE)
```

Tested 2026-03-30 with controlled in/out-of-bed transitions on both sides.
func=24 and func=25 both return `[0]` regardless of actual bed occupancy.
A long-running monitor (sampling every ~15s) confirmed no change across multiple
get-in/get-out cycles. These are dead on firmware 0.4.x.

### func=97 (GetChamberTypes) — UNTESTED, Promising

The decompiled SleepIQ app reveals `GetChamberTypesCall` (func=97, cmd=0x02),
which returns an 8-byte response including per-side `leftSideOccupancy` and
`rightSideOccupancy` fields. This is the same data available through the cloud
API's `/bed/familyStatus` endpoint (`BedSideStatus.isInBed`).

See "New Pump Functions from APK Decompilation" above for byte layout.

**This has not been tested yet.** It requires sending a 2-byte payload `[0, 0]`
with side=2 (unusual addressing). The app treats it as a read-only GET call.

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

## Unexplored / Partially Explored Areas

- **Bed presence/occupancy** — **NOT AVAILABLE over BLE on firmware 0.4.x.**
  func=24/25 always return 0. func=97 returns chamber type only (4 bytes),
  not the full 8-byte response with occupancy fields. The app falls back to
  the cloud REST API (`/bed/familyStatus`) for presence on this firmware.
- ~~Push notifications~~ — **NOT SUPPORTED:** bed is purely request/response
- **Foundation position readback** — func=5 returns 11 bytes but always zeros (may need
  different addressing or cmd type)
- **Massage control** — func=17 with cmd=0x42 and 12-byte payload (from decompiled code)
- ~~Underbed lights~~ — **IMPLEMENTED:** cmd=0x92 func=19 for read, cmd=0x42 func=19 for write
- **Foot warming** — func=42 read, func=41 write (cmd=0x42). Not tested.
- **Responsive Air** — automatic pressure adjustment feature (Bamkey/FuzionBLE only,
  not available on MCR firmware 0.4.x)
- **Foundation system status** — func=37 (cmd=0x42), read. Not tested.
- **Pinch state** — func=40 (cmd=0x42), anti-pinch sensor. Not tested.
- **Node list** — func=18 (cmd=0x72), lists connected MCR nodes. Not tested.
- **Sense & Do** — func=18 (cmd=0x32), smart outlet toggle. Not useful for presence.

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

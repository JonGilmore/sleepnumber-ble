# Sleep Number BLE

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for **local BLE control** of Sleep Number 360 beds. No cloud connection required - communicates directly with the bed's BAM module over Bluetooth Low Energy.

WARNING: This project is in an extreme alpha phase. Use at your own risk.

## Features

- **Firmness Control** - Set sleep number (0-100) independently for each side
- **Foundation Presets** - Activate Flat, Zero G, Snore, Read, Watch TV, and Favorite positions per side
- **Bed Presence Detection** - Binary sensors indicating occupancy per side (polled every 20 seconds)
- **Underbed Light** - On/off control
- **Auto Discovery** - Automatically discovers Sleep Number beds via BLE service
- **ESPHome BLE Proxy Support** - Works through ESPHome Bluetooth Proxy devices

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add this repository URL with category **Integration**
4. Search for "Sleep Number BLE" and install
5. Restart Home Assistant
6. The bed should be automatically discovered

### Manual

1. Copy `custom_components/sleepnumber_ble/` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Requirements

- Home Assistant 2024.1+
- A Bluetooth adapter accessible to HA (local or [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html))
- Sleep Number 360 bed with BAM module

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| Firmness Control Left | Number (5-100) | Sleep number for left side |
| Firmness Control Right | Number (5-100) | Sleep number for right side |
| Foundation Preset Left | Select | Preset position for left side |
| Foundation Preset Right | Select | Preset position for right side |
| Bed Presence Left | Binary Sensor | Occupancy detection for left side |
| Bed Presence Right | Binary Sensor | Occupancy detection for right side |
| Underbed Light | Light | On/off control for underbed light |

## Foundation Presets

| Preset | Behavior |
|--------|----------|
| Flat | Lowers selected side's head + shared feet |
| Zero G | Raises both heads + feet (whole bed) |
| Snore | Raises selected side's head slightly |
| Read | Reading position (whole bed) |
| Watch TV | TV watching position (whole bed) |
| Favorite | Saved favorite position (whole bed) |

## Known Limitations

- **No push notifications** - The bed is purely request/response. All state must be polled.
 - Because of this, instant presence detection does _not_ seem feasible (at the moment). Currently, it is polled.
- **Preset state** - The bed doesn't report current preset position via BLE. Selectors are fire-and-forget.

## Tested Hardware

| Field | Value |
|-------|-------|
| Bed | I8, Flextop King, 360 FlexFit 2 |
| BAM Firmware | 0.4.1d9 |
| BLE Proxy | EverythingSmartHome EP1 |

## Protocol Documentation

For full protocol details, see [PROTOCOL.md](PROTOCOL.md).

## AI Disclaimer

AI was used to assist in inspecting how the Android APK handles BLE pairing and communication as well as creating documentation and troubleshooting steps. Python was heavily influenced by the use of AI as well.

## License

This project is not affiliated with Sleep Number Corporation. Use at your own risk.

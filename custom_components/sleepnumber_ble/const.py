"""Constants for Sleep Number BLE integration."""

DOMAIN = "sleepnumber_ble"

# BLE UUIDs
SERVICE_UUID = "ffffd1fd-388d-938b-344a-939d1f6efee0"
MCR_TX_UUID = "ffffd1fd-388d-938b-344a-939d1f6efee1"  # Notify (bed → us)
MCR_RX_UUID = "ffffd1fd-388d-938b-344a-939d1f6efee2"  # Write  (us → bed)

# MCR protocol constants
MCR_SYNC = bytes([0x16, 0x16])
MCR_CMD_PUMP = 0x02
MCR_CMD_FOUNDATION = 0x42
MCR_STATUS_PUMP = 0x02
MCR_STATUS_FOUNDATION = 0x42
MCR_FUNC_INIT = 0
MCR_FUNC_FORCE_IDLE = 2
MCR_FUNC_SET = 17
MCR_FUNC_READ = 18
MCR_FUNC_PRESET = 21

MCR_CMD_SMART_OUTLET = 0x92
MCR_STATUS_SMART_OUTLET = 0x02

# Sides
SIDE_LEFT = 0
SIDE_RIGHT = 1

# Foundation presets
PRESET_FAVORITE = 1
PRESET_READ = 2
PRESET_WATCH_TV = 3
PRESET_FLAT = 4
PRESET_ZERO_G = 5
PRESET_SNORE = 6

PRESET_NAMES = {
    "Favorite": PRESET_FAVORITE,
    "Read": PRESET_READ,
    "Watch TV": PRESET_WATCH_TV,
    "Flat": PRESET_FLAT,
    "Zero G": PRESET_ZERO_G,
    "Snore": PRESET_SNORE,
}

MCR_FUNC_PRESENCE = 24
MCR_FUNC_CHAMBER_TYPES = 97
MCR_FUNC_OUTLET = 19

# Outlet IDs (byte 9 upper nibble)
OUTLET_UNDERBED_LIGHT = 3

PLATFORMS = ["binary_sensor", "light", "number", "select", "sensor"]

"""Constants for the Sharp ECHONET Lite integration."""
from homeassistant.const import Platform

DOMAIN = "sharp_echonet"
PLATFORMS = [Platform.FAN, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.SENSOR]

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300

SUPPORTED_MODEL = "KIN42"
# Delay before reading back after a write (the unit is briefly busy after SetC)
REFRESH_AFTER_WRITE = 2.0
# Delay between power-on and a mode change in the same action
POWER_ON_SETTLE = 1.0

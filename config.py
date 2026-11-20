SSID = "wifi-ssid-goes-here"
PSK = "wifi-password-goes-here"

WIFI_CONNECT_TIMEOUT = 30 # seconds to wait per connect attempt before giving up
WDT_TIMEOUT_MS = 16000    # RP2040 hardware WDT max is ~8388ms, RP2350 is double at ~16777ms. 0 to disable WDT.

# Console logging: "debug" for development/troubleshooting with a console
# attached; "warning" or "off" for production. Absent => "info".
LOG_LEVEL = "info"

UDP_PORT = 11235
MCAST_GROUP = "239.0.0.1"

SLEEP = 10

BASE_URL = "http://iotplotter.com/api/v2/feed/"
API_KEY = "api-key-goes-here"
FEED_ID = "feed-id-goes-here"
FEED_ENABLED = False

# Per-sensor names and calibration offsets, keyed by sensor ID: the
# DS18B20 ROM code, or the SHT3x serial (check the log on first boot
# for the ID). "offset" is in degrees C; "rh_offset" is in %RH
# (humidity sensors only).
SENSOR = {}
SENSOR["default"] = {"name": "DefaultSensorName", "offset": 0.0}
SENSOR["0000000000000001"] = {"name": "SomeSensorName"}
SENSOR["0000000000000002"] = {"name": "SomeOtherSensorName"}
# SENSOR["20e80802"] = {"name": "SomeRoom", "offset": 0.0, "rh_offset": 0.0}

# DS18B20 sensors on a 1-Wire bus. None to disable.
# Absent => enabled on GPIO_PIN (or 15), for older config files.
ONEWIRE = {"pin": 15}

# SHT3x (SHT30/31/35) temperature + humidity on I2C. None/absent => disabled.
# "name" is optional: used if the sensor's ID has no entry in SENSOR.
SHT3X = None
# SHT3X = {"i2c": 1, "sda": 26, "scl": 27, "freq": 100000, "addr": 0x44, "model": "sht30", "name": "SomeRoom"}

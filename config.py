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

# Per-sensor names and calibration offsets, keyed by sensor ID: the
# DS18B20 ROM code, the SHT3x serial or the SCD4x serial (check the log
# on first boot for the ID). "offset" is in degrees C; "rh_offset" is in
# %RH (humidity sensors only).
#
# "name" is a location, not a probe: several sensors can share one name,
# but each quantity at a location must come from exactly one sensor (a
# clash is logged as an error at boot).
#
# "publish" (optional) lists which quantities go in the sensor's packets,
# from "temperature", "humidity" and "co2". Defaults by model:
# ds18b20 -> temperature; sht30/31/35 -> temperature, humidity;
# scd40/41/43 -> co2 only. Every measured value is still logged at debug.
SENSOR = {}
SENSOR["default"] = {"name": "DefaultSensorName", "offset": 0.0}
SENSOR["0000000000000001"] = {"name": "SomeSensorName"}
SENSOR["0000000000000002"] = {"name": "SomeOtherSensorName"}
# SENSOR["20e80802"] = {"name": "SomeRoom", "offset": 0.0, "rh_offset": 0.0}
# SENSOR["1cab65073b57"] = {"name": "SomeRoom"}
# e.g. take RH from the SCD41 instead of the SHT30 in the same room:
# SENSOR["1cab65073b57"] = {"name": "SomeRoom", "publish": ["co2", "humidity"]}
# SENSOR["20e80802"] = {"name": "SomeRoom", "publish": ["temperature"]}

# DS18B20 sensors on a 1-Wire bus. None to disable.
# Absent => enabled on GPIO_PIN (or 15), for older config files.
ONEWIRE = {"pin": 15}

# SHT3x (SHT30/31/35) temperature + humidity on I2C. None/absent => disabled.
# "name" is optional: used if the sensor's ID has no entry in SENSOR.
SHT3X = None
# SHT3X = {"i2c": 1, "sda": 26, "scl": 27, "freq": 100000, "addr": 0x44, "model": "sht30", "name": "SomeRoom"}

# SCD4x (SCD40/41/43) CO2 (+ its own temperature/RH) on I2C. None/absent => disabled.
# "temperature_offset" (C, >= 0) and "altitude" (m) are optional and written to the
# sensor at boot only (not persisted). "model" is optional (read from the sensor if
# absent). "name" is an optional fallback name, as for SHT3X.
# SHT3X and SCD4X may share a bus; if they use the same "i2c" controller they must
# use the same sda/scl pins.
SCD4X = None
# SCD4X = {"i2c": 0, "sda": 20, "scl": 21, "freq": 100000, "addr": 0x62, "name": "SomeRoom"}

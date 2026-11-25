# Pico Temperature Monitor

A Raspberry Pi Pico-based temperature monitoring system that reads from DS18B20 temperature sensors, SHT3x temperature + humidity sensors and/or SCD4x CO2 sensors and broadcasts the data via UDP multicast. To log or graph the data in a service such as IoTPlotter, Prometheus or a database, run a receiver on the network that listens for the UDP packets and forwards them.

## Features

- **Multi-sensor support**: Automatically detects and reads from multiple DS18B20 temperature sensors
- **WiFi connectivity**: Connects to WiFi networks with automatic reconnection
- **UDP multicast**: Broadcasts sensor readings (temperature, humidity and CO2, as configured) to the local network
- **Configurable sensors**: Custom names and calibration offsets for each sensor
- **Humidity**: Optional SHT3x (SHT30/31/35) temperature + humidity probe over I2C
- **CO2**: Optional Sensirion SCD4x (SCD40/41/43) CO2 sensor over I2C
- **Locations**: Several sensors can report under one name, with each quantity (temperature, humidity, CO2) chosen from one of them
- **Log levels**: Verbose console output for development, quiet in production

## Hardware Requirements

- Raspberry Pi Pico W (or Pico 2 W); Wi-Fi is required
- DS18B20 temperature sensor(s), and/or an SHT3x (SHT30/31/35) probe, and/or an SCD4x (SCD40/41/43) CO2 sensor
- 4.7kΩ pull-up resistor (if not built into the sensor)
- Jumper wires for connections

## Wiring

Connect your DS18B20 sensor(s) to the Pico:

- **VCC** → 3.3V (Pin 36)
- **GND** → GND (Pin 38)
- **Data** → GPIO Pin 15 (Pin 20) - configurable in `config.py`
- **Pull-up resistor**: 4.7kΩ between Data and VCC

### SHT3x (I2C)

Example (Pico 2 W, I2C1; matches the commented `SHT3X` example in `config.py`):

- **VCC** (red) → 3.3V OUT (Pin 36)
- **GND** (black) → GND (Pin 33)
- **SDA** (white) → GP26 (Pin 31)
- **SCL** (yellow) → GP27 (Pin 32)

Sealed SHT30 probes usually include pull-ups. 100 kHz is used by default for margin on longer cables.

### SCD4x (I2C)

Example (Pico 2 W, I2C0; matches the commented `SCD4X` example in `config.py`):

- **VCC** → 3.3V OUT (Pin 36)
- **GND** → GND (Pin 28)
- **SDA** → GP20 (Pin 26)
- **SCL** → GP21 (Pin 27)

The SCD4x can share a bus with an SHT3x (addresses 0x62 and 0x44 don't clash). Sensors on the same I2C controller must use the same SDA/SCL pins: config that puts one controller on two pin pairs logs an error and skips the second sensor.

## Installation

1. Copy the following from this repo to your Pico
   - `main.py`
   - `config.py`
   - `itk_pico/temperature.py`
   - `itk_pico/wifi.py`
   - `itk_pico/logger.py`
   - `kdmp/__init__.py`
   - `kdmp/log.py`
   - `kdmp/sensors/__init__.py`
   - `kdmp/sensors/base.py`
   - `kdmp/sensors/sht3x.py`
   - `kdmp/sensors/scd4x.py`

2. Configure your settings in `config.py`:
   ```python
   SSID = "your-wifi-network"
   PSK = "your-wifi-password"
   ONEWIRE = {"pin": 15}  # Pin connected to DS18B20 data line; None to disable
   SHT3X = None           # or {"i2c": 1, "sda": 26, "scl": 27, "addr": 0x44}
   SCD4X = None           # or {"i2c": 0, "sda": 20, "scl": 21, "addr": 0x62}
   UDP_PORT = 11235
   MCAST_GROUP = "239.0.0.1"
   SLEEP = 10  # Seconds between readings
   ```

## Configuration

### Basic WiFi Setup

Edit `config.py` with your WiFi credentials:

```python
SSID = "your-wifi-network"
PSK = "your-wifi-password"
```

### Sensor Configuration

Configure individual sensors with custom names and calibration offsets:

```python
SENSOR = {}
SENSOR["default"] = {"name": "DefaultSensorName", "offset": 0.0}
SENSOR["0000000000000001"] = {"name": "LivingRoom", "offset": -0.5}
SENSOR["0000000000000002"] = {"name": "Bedroom", "offset": 0.2}
```

- `name`: Friendly name for the sensor
- `offset`: Temperature offset in Celsius for calibration
- `rh_offset`: Humidity offset in %RH (humidity sensors only)
- `publish`: Which quantities go in this sensor's packets (optional, see below)

Sensors are keyed by ID: the DS18B20 ROM code, the SHT3x serial number or the SCD4x serial number. The IDs found are logged at boot.

### Glossary

- **unit**: one Pico (or other board) running the firmware. A unit can have several sensors attached.
- **sensor**: one physical sensor chip or probe attached to a unit (a DS18B20, SHT30, SCD41...). It's identified in packets by `sensor` (the DS18B20 ROM code or the chip serial) and `model`.
- **location**: what a reading is *about*, set by `name` (e.g. `Kitchen`, `BoilerFlow`). Several sensors can report for the same location.
- **measurement**: one quantity: `temperature`, `humidity`, `co2`.
- **reading**: one packet. One sensor's published measurements for its location at one moment.

The receiver ([prometheus_temperature_exporter](https://github.com/karldyson/prometheus_temperature_exporter)) uses the same terms. Its `sensor_name` label carries the location (`name`), not the sensor.

### Locations and published quantities

A `name` is a **location** (a measurement point), not a probe. Several sensors can share a name, but each quantity at a location must come from exactly one sensor. Packets are still sent one per physical sensor, so several packets can carry the same `name`.

Each sensor publishes a default set of quantities based on its model:

| Model | Published by default |
|---|---|
| `ds18b20` | `temperature` |
| `sht30` / `sht31` / `sht35` | `temperature`, `humidity` |
| `scd40` / `scd41` / `scd43` | `co2` |

Set `publish` to override this, for example to take humidity from the SCD41 instead of the SHT30:

```python
SENSOR["1cab65073b57"] = {"name": "MainBedroom", "publish": ["co2", "humidity"]}
SENSOR["20e80802"]     = {"name": "MainBedroom", "publish": ["temperature"]}
```

Unknown names in `publish` are logged as a warning and ignored. Quantities the sensor doesn't measure are ignored. Every measured value is still logged at debug level, whether published or not.

At boot the firmware logs where each location's values come from, for example `Kitchen: temperature, humidity <- 20e80802 (sht30); co2 <- 1cab65073b57 (scd41)`. If two sensors publish the same quantity under the same name, it logs an **error** naming both sensors. Both still send, so no data is lost. A common cause is several DS18B20 probes with no `SENSOR` entry, which all fall back to `SENSOR["default"]["name"]`.

Example: a kitchen unit with clamp probes on the boiler flow and return pipes, plus an SHT30 and an SCD41 for the room:

```python
ONEWIRE = {"pin": 15}
SHT3X = {"i2c": 1, "sda": 26, "scl": 27, "addr": 0x44}
SCD4X = {"i2c": 0, "sda": 20, "scl": 21, "addr": 0x62}
SENSOR["28aa..."]      = {"name": "BoilerFlow"}
SENSOR["28bb..."]      = {"name": "BoilerReturn"}
SENSOR["20e80802"]     = {"name": "Kitchen"}   # sht30: temperature + humidity
SENSOR["1cab65073b57"] = {"name": "Kitchen"}   # scd41: co2
```

That sends four packets per loop, with no conflicts.

### Sensor Buses

```python
ONEWIRE = {"pin": 15}   # DS18B20 bus; None to disable (absent => enabled on GPIO_PIN/15)
SHT3X = {"i2c": 1, "sda": 26, "scl": 27, "freq": 100000, "addr": 0x44, "model": "sht30", "name": "Fallback"}
SCD4X = {"i2c": 0, "sda": 20, "scl": 21, "freq": 100000, "addr": 0x62, "name": "Fallback"}
```

Only the buses that are configured are initialised, so an I2C-only unit should set `ONEWIRE = None`.

`SCD4X` also accepts `"model"` (normally read from the sensor), `"temperature_offset"` (°C, ≥ 0, replaces the sensor's own built-in offset) and `"altitude"` (metres above sea level, for CO2 compensation). The two settings are written to the sensor at every boot and never stored on it, so `config.py` stays the source of truth.

### Logging

```python
LOG_LEVEL = "info"   # "debug" with a console attached; "warning" or "off" in production
```

## Usage

1. Upload files to your Pico
2. Run `main.py` (happens automatically if Pico is not connected to your USB port)
3. The system will:
   - Scan for the configured sensors (DS18B20, SHT3x and/or SCD4x)
   - Connect to WiFi
   - Read the sensors every 10 seconds (configurable)
   - Send data to the network via UDP multicast

## Data Format

The system sends one JSON message per sensor reading via UDP multicast. A packet carries only the quantities that sensor publishes:

```json
{
  "type": "reading",
  "model": "sht30",
  "name": "LivingRoom",
  "sensor": "20e80802",
  "temperature": 22.5,
  "humidity": 49.9,
  "offset": -0.5,
  "rh_offset": 0.0,
  "fw": "1.24.1",
  "version": "3.0.0"
}
```

```json
{"type": "reading", "model": "scd41", "name": "LivingRoom", "sensor": "1cab65073b57", "co2": 466, "fw": "1.24.1", "version": "3.0.0"}
```

- `type`: `"reading"`. Firmware older than 2.0.0 sends `"temperature"` and has no `model`, `humidity` or `fw` fields.
- `model`: `"ds18b20"`, `"sht30"` (or `sht31`/`sht35`), or `"scd40"`/`"scd41"`/`"scd43"` (`"scd4x"` if the variant couldn't be read)
- `temperature` / `humidity`: With the configured offsets applied, rounded to 2 decimal places. Present only if the sensor publishes them. **From 3.0.0, `temperature` isn't guaranteed**: an SCD4x packet carries only `co2` by default.
- `co2`: CO2 in ppm (integer), present only if published (from 3.0.0).
- `offset` / `rh_offset`: The offsets that were applied, so a receiver can recover the raw values. Present only alongside `temperature` / `humidity` respectively.
- `fw`: MicroPython release (`os.uname().release`)
- `version`: Firmware version (`VERSION` in `main.py`)

Firmware before 2.1.0 also sent `"type": "status"` packets carrying IoTPlotter feed results. Those are gone now that the feed has been removed.

## Network Configuration

- **UDP Port**: 11235 (configurable)
- **Multicast Group**: 239.0.0.1 (configurable)
- **Broadcast Interval**: 10 seconds (configurable)

## Troubleshooting

### No sensors detected
- Check wiring connections
- Verify pull-up resistor is connected
- Ensure sensor is powered (3.3V)
- Check GPIO pin configuration in `config.py`

### WiFi connection issues
- Verify SSID and password in `config.py`
- Check WiFi signal strength
- Ensure network allows Pico connections

### SCD4x not reading
- The first loop after boot logs "no new data yet": the sensor makes a new reading every ~5 s.
- After repeated failures the firmware re-initialises the sensor. If it logs that a full power cycle may be needed, unplug the unit: a soft reset doesn't remove the sensor's power.
- Its temperature reads a few degrees high for a minute or two after start-up (self-heating). That's one reason it publishes only CO2 by default.

### No UDP data received
- Verify multicast group and port settings
- Check firewall settings on receiving devices
- Ensure devices are on the same network

## Project Structure

```
pico-temperature/
├── main.py              # Main application entry point
├── config.py            # Configuration settings
├── kdmp/               # Reusable MicroPython package (submodule): logging, sensors
│   ├── log.py
│   └── sensors/        # base.py (driver interface), sht3x.py, scd4x.py
├── itk_pico/           # ITK Pico MicroPython framework (being phased out)
│   ├── temperature.py   # DS18B20 sensor interface
│   ├── wifi.py         # WiFi connectivity
│   ├── logger.py       # Logging utilities
│   └── ...
└── README.md           # This file
```

## Copyright

Copyright (c) 2025 Karl Dyson

This project is based on the ITK Pico MicroPython framework by Eugene Tkachenko.

## License

Licensed under the Apache License, Version 2.0. See the LICENSE file for details.


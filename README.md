# Pico Temperature Monitor

A Raspberry Pi Pico-based temperature monitoring system that reads from DS18B20 temperature sensors and/or SHT3x temperature + humidity sensors and broadcasts the data via UDP multicast. Optionally sends data to IoT feed services like IoTPlotter.

## Features

- **Multi-sensor support**: Automatically detects and reads from multiple DS18B20 temperature sensors
- **WiFi connectivity**: Connects to WiFi networks with automatic reconnection
- **UDP multicast**: Broadcasts sensor readings (temperature, and humidity where measured) to the local network
- **IoT integration**: Optional integration with IoTPlotter for data logging
- **Configurable sensors**: Custom names and calibration offsets for each sensor
- **Humidity**: Optional SHT3x (SHT30/31/35) temperature + humidity probe over I2C
- **Log levels**: Verbose console output for development, quiet in production

## Hardware Requirements

- Raspberry Pi Pico W (or Pico 2 W); Wi-Fi is required
- DS18B20 temperature sensor(s), and/or an SHT3x (SHT30/31/35) probe
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

2. Configure your settings in `config.py`:
   ```python
   SSID = "your-wifi-network"
   PSK = "your-wifi-password"
   ONEWIRE = {"pin": 15}  # Pin connected to DS18B20 data line; None to disable
   SHT3X = None           # or {"i2c": 1, "sda": 26, "scl": 27, "addr": 0x44}
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

Sensors are keyed by ID: the DS18B20 ROM code, or the SHT3x serial number. The IDs found are logged at boot.

### Sensor Buses

```python
ONEWIRE = {"pin": 15}   # DS18B20 bus; None to disable (absent => enabled on GPIO_PIN/15)
SHT3X = {"i2c": 1, "sda": 26, "scl": 27, "freq": 100000, "addr": 0x44, "model": "sht30", "name": "Fallback"}
```

Only the buses that are configured are initialised, so an SHT3x-only unit should set `ONEWIRE = None`.

### Logging

```python
LOG_LEVEL = "info"   # "debug" with a console attached; "warning" or "off" in production
```

### IoT Feed Integration (Optional)

To enable IoT feed logging:

```python
BASE_URL = "http://iotplotter.com/api/v2/feed/"
API_KEY = "your-api-key"
FEED_ID = "your-feed-id"
FEED_ENABLED = True
```

## Usage

1. Upload files to your Pico
2. Run `main.py` (happens automatically if Pico is not connected to your USB port)
3. The system will:
   - Scan for the configured sensors (DS18B20 and/or SHT3x)
   - Connect to WiFi
   - Start reading temperatures every 10 seconds (configurable)
   - Send data to the network via UDP multicast
   - Optionally send data to IoT Plotter API

## Data Format

The system sends one JSON message per sensor reading via UDP multicast:

```json
{
  "type": "reading",
  "model": "sht30",
  "name": "LivingRoom",
  "sensor": "20e80802",
  "temperature": 22.5,
  "humidity": 49.9,
  "offset": -0.5,
  "fw": "1.24.1",
  "version": "2.0.0"
}
```

- `type`: `"reading"`. Firmware older than 2.0.0 sends `"temperature"` and has no `model`, `humidity` or `fw` fields.
- `model`: `"ds18b20"` or `"sht30"`
- `humidity`: Only present for sensors that measure it, with `rh_offset` applied
- `fw`: MicroPython release (`os.uname().release`)
- `version`: Firmware version (`VERSION` in `main.py`)

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
│   └── sensors/        # base.py (driver interface), sht3x.py
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


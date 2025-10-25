# Pico Temperature Monitor

A Raspberry Pi Pico-based temperature monitoring system that reads from DS18B20 temperature sensors and broadcasts the data via UDP multicast. Optionally sends data to IoT feed services like IoTPlotter.

## Features

- **Multi-sensor support**: Automatically detects and reads from multiple DS18B20 temperature sensors
- **WiFi connectivity**: Connects to WiFi networks with automatic reconnection
- **UDP multicast**: Broadcasts temperature data to the local network
- **IoT integration**: Optional integration with IoTPlotter for data logging
- **Configurable sensors**: Custom names and calibration offsets for each sensor

## Hardware Requirements

- Raspberry Pi Pico (or Pico 2)
- DS18B20 temperature sensor(s)
- 4.7kΩ pull-up resistor (if not built into the sensor)
- Jumper wires for connections

## Wiring

Connect your DS18B20 sensor(s) to the Pico:

- **VCC** → 3.3V (Pin 36)
- **GND** → GND (Pin 38)
- **Data** → GPIO Pin 15 (Pin 20) - configurable in `config.py`
- **Pull-up resistor**: 4.7kΩ between Data and VCC

## Installation

1. Copy the following from this repo to your Pico
   - `main.py`
   - `config.py`
   - `itk_pico/temperature.py`
   - `itk_pico/wifi.py`
   - `itk_pico/logger.py`

2. Configure your settings in `config.py`:
   ```python
   SSID = "your-wifi-network"
   PSK = "your-wifi-password"
   GPIO_PIN = 15  # Pin connected to DS18B20 data line
   UDP_PORT = 9999
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
   - Scan for connected DS18B20 sensors
   - Connect to WiFi
   - Start reading temperatures every 10 seconds (configurable)
   - Send data to the network via UDP multicast
   - Optionally send data to IoT Plotter API

## Data Format

The system sends JSON messages via UDP multicast:

```json
{
  "name": "LivingRoom",
  "sensor": "0000000000000001",
  "temperature": 22.5,
  "offset": -0.5
}
```

## Network Configuration

- **UDP Port**: 9999 (configurable)
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
├── itk_pico/           # ITK Pico MicroPython framework
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


# Changelog

All notable changes to this project are recorded here. Version numbers are the `VERSION` constant in `main.py`, which every UDP packet carries.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [Semantic Versioning](https://semver.org/): a major bump means a breaking change to the packet format or the config.

## [3.0.0] - 2026-11-25

### ⚠️ Breaking
- `temperature` is no longer in every reading packet. A packet now carries only the quantities its sensor publishes, and an SCD4x packet carries only `co2` by default. Receivers must skip quantities a packet doesn't contain. With no `publish` setting, DS18B20 and SHT3x packets are exactly as before.

### Added
- SCD4x (SCD40/41/43) CO2 sensor over I2C, set up with the `SCD4X` config dict. It runs in periodic mode, so reads never block. Its ID is the 48-bit serial and its model is read from the sensor. Optional `temperature_offset` and `altitude` are written to the sensor at boot and never stored on it. It re-initialises itself after repeated read failures.
- A `co2` field (int, ppm) in reading packets.
- A per-sensor `publish` list in `SENSOR` that chooses which of `temperature`, `humidity` and `co2` go in that sensor's packets. Defaults by model: DS18B20 → temperature; SHT3x → temperature + humidity; SCD4x → co2. Every measured value is still logged at debug level.
- A boot-time location check: a `name` is a location, and each quantity at a location must come from exactly one sensor. Clashes are logged as errors (both sensors keep sending), and each location's sources are logged at info level.
- README glossary of unit, sensor, location, measurement and reading, shared word for word with the receiver's README.
- Sensors on the same I2C controller share one bus. Configuring one controller on two different pin pairs logs an error and skips the second sensor.

### Notes
- The receiver (`prometheus_temperature_exporter`) needs a `co2` gauge to export CO2.
- Requires kdmp 0.2.0 (`v0.2.0`), which adds `kdmp/sensors/scd4x.py` and `SensorDriver.quantities`; copy the updated `kdmp/sensors/*.py` to units.

## [2.1.0] - 2026-11-20

### Removed
- The IoTPlotter feed. The firmware no longer makes HTTP requests. To send readings to IoTPlotter or any other service, run a receiver that listens for the UDP packets and forwards them.
- `"type": "status"` packets. They only ever carried the result of the feed's POST request.
- The `BASE_URL`, `API_KEY`, `FEED_ID`, `FEED_ENABLED` and `PICO_NAME` config settings. Older per-device configs that still contain them load fine, because nothing reads them any more.

### Added
- An `rh_offset` field in reading packets that carry `humidity`. It matches the existing `offset` field, so receivers can work out the raw humidity.

### Changed
- `temperature` and `humidity` are rounded to 2 decimal places after the offsets are added. Packets no longer carry float noise like `20.419999999999998`.

## [2.0.0] - 2026-11-20

### ⚠️ Breaking
- Reading packets now have `"type": "reading"`. Before this release they had `"type": "temperature"`. Receivers need to accept both until every unit is upgraded.

### Added
- SHT3x (SHT30/31/35) temperature and humidity sensor over I2C, set up with the `SHT3X` config dict.
  - Each probe's ID is its serial number. If the serial can't be read, the ID is based on the board and bus position instead.
  - CRC errors and I/O errors are retried once, then that reading is skipped. A bad value is never sent.
- Reading packets have new fields:
  - `model`: `ds18b20` or `sht30`.
  - `humidity`: included only when the sensor measures it, with the per-sensor `rh_offset` applied.
  - `fw`: the MicroPython release, from `os.uname().release`.
- `LOG_LEVEL` config setting: `debug`, `info`, `warning`, `error` or `off`. The `itk_pico` Wi-Fi logging goes quiet as well when the level is `warning` or higher.
- `ONEWIRE` config dict for the DS18B20 bus. `None` disables the bus.
- [kdmp](https://github.com/karldyson/kdmp) submodule: a reusable MicroPython package that isn't tied to any one board. It provides the logger, the sensor driver interface and the SHT3x driver. Its `kdmp/*.py` files must be copied to the board along with the others.
- `CLAUDE.md` with project context, and a `.gitignore`.

### Changed
- Only the sensor buses enabled in config are initialised. An SHT3x-only unit no longer fails at boot because no DS18B20 was found.
- The main loop works the same way for every sensor type: one packet per reading from each enabled driver. Each driver gets its own watchdog feed.
- Sensor names are resolved in this order: `SENSOR[id]`, then the bus's fallback `name`, then `SENSOR["default"]`, then `DefaultSensor<n>`. Any sensor ID first seen after boot is resolved as soon as it appears.
- The template `config.py` uses `UDP_PORT = 11235`. Deployed units keep whatever their own config sets.
- `config.py` files without `ONEWIRE` still work: 1-Wire runs on `GPIO_PIN` (default 15), and SHT3x stays off.

### Fixed
- Startup crashed with a `TypeError` when `config.SENSOR` had no `"default"` entry. It was concatenating a string and an int.

## [1.0.1] - 2026-08-30

### Fixed
- Updated the `itk_pico` submodule to get its `wifi.py` rewrite.
  - The Wi-Fi connect wait now gives up after `timeout` seconds and feeds the watchdog while it waits. Before this, a unit could hang forever with its LED stuck on after a power cut if the router was slow to come back.
  - Lost connections are now retried with an exponential backoff, capped at 300 seconds.
  - The submodule now matches the `timeout`/`wdt` arguments that `main.py` has been passing since 1.0.0.

## [1.0.0] - 2026-08-29

First versioned release.

### Added
- `VERSION` constant, sent as `"version"` in every UDP packet so that unit firmware can be tracked remotely (for example via Prometheus and Grafana).
- Optional hardware watchdog (`WDT_TIMEOUT_MS`; `0` disables it). The main loop's sleep is split into 1-second chunks so the watchdog keeps being fed.
- `WIFI_CONNECT_TIMEOUT` config setting. `main.py` passes it, together with the watchdog, to `wifi.connect()` and `try_reconnect_if_lost()`. It retries the first connection every 5 seconds and feeds the watchdog between attempts. The time limit itself only took effect in 1.0.1; see above.

### Changed
- Better error handling: a failed multicast send is logged instead of crashing the loop, and the socket is always closed.

## Before 1.0.0 (unversioned)

- 2026-05: The initial Wi-Fi connect is retried. The `itk_pico` temperature module now supports friendly names and several probes on one bus.
- 2025-12: Refactoring and consistent tab indentation.
- 2025-10: First version.
  - DS18B20 temperature readings broadcast as JSON over UDP multicast.
  - Per-sensor names and calibration offsets.
  - Optional IoTPlotter feed.
  - Added the README, the Apache 2.0 licence and the `itk_pico` submodule.

[3.0.0]: https://github.com/karldyson/pico-temperature/compare/v2.1.0...v3.0.0
[2.1.0]: https://github.com/karldyson/pico-temperature/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/karldyson/pico-temperature/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/karldyson/pico-temperature/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/karldyson/pico-temperature/releases/tag/v1.0.0

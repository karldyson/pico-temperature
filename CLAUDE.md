# Pico Temperature — Claude Context

## Project overview

MicroPython firmware for a Raspberry Pi Pico W (or Pico 2 W). Reads DS18B20 1-Wire temperature sensors, an SHT3x I2C temperature + humidity sensor and/or an SCD4x I2C CO2 sensor, and broadcasts the readings as JSON over UDP multicast. The firmware has no HTTP or cloud output. Forwarding to services such as IoTPlotter, Prometheus or a database is the job of a separate receiver that listens for the packets (the built-in IoTPlotter feed was removed in 2.1.0).

**Direction: moving from `itk_pico` to `kdmp`.** `kdmp` is the author's own reusable MicroPython package, included as a submodule. It isn't tied to any particular board and targets both the Pico and the ESP32. The author is migrating so that the code can run on more kinds of board and so that the author controls the architectural choices. That isn't a criticism of `itk_pico`: thanks to Eugene Tkachenko, whose framework inspired this project and was its starting point. New reusable code (sensor drivers, logging, and later Wi-Fi/UDP/networking) goes into `kdmp`, never into `itk_pico`, and must not import from `itk_pico`. `itk_pico` is still used for Wi-Fi and, via a temporary `DS18B20Bus` adapter in `main.py`, for DS18B20 sensors until those are migrated.

## Repo layout

```
pico-temperature/
├── main.py              Entry point — no boot.py exists, MicroPython runs main.py directly
├── config.py             Per-device settings, committed with placeholder values
├── kdmp/                 Git submodule — reusable board-agnostic package (see kdmp/CLAUDE.md)
│   ├── log.py            Levelled logger (kdmp.log.get(name), set_level from config.LOG_LEVEL)
│   └── sensors/          base.py (SensorDriver: ids()/read() -> list of readings, quantities), sht3x.py, scd4x.py
├── itk_pico/             Git submodule — legacy framework code, being phased out
│   ├── wifi.py           Wi-Fi connect/reconnect (bounded timeout + watchdog feed)
│   ├── temperature.py    DS18B20 1-Wire sensor interface
│   ├── logger.py         Logger.print() — no-op when disabled
│   └── ...
├── LICENSE / itk_pico/LICENSE   Apache 2.0
└── README.md
```

`kdmp` is a separate git repo, checked out here as a submodule and also as a standalone clone. The private file imported below gives that clone's local path. Use the same workflow as for itk_pico below: edit the standalone copy, commit and push it, then bump the submodule pointer here.

`itk_pico` is a real, separate git repo (github.com/karldyson/itk_pico), checked out both as this repo's submodule (`pico-temperature/itk_pico/`) and as a standalone clone. **When changing anything under `itk_pico/`, edit the standalone copy, commit and push it there first, then bump the submodule pointer in `pico-temperature`** (`git -C itk_pico pull`, then commit the updated gitlink here). Editing only the submodule checkout in place leaves the standalone copy stale and the change unpushed.

## Deployment

There is no build step. Files are copied directly onto the Pico's MicroPython filesystem (see `README.md` Installation section for the exact file list: `main.py`, `config.py`, the `itk_pico/*.py` files in use, and `kdmp/__init__.py`, `kdmp/log.py`, `kdmp/sensors/*.py`, which includes `scd4x.py`). Before copying changed code to a unit, **bump `VERSION` in `main.py`** — it's sent in every UDP message specifically so units can be identified by firmware version without physically consoling into them (e.g. via a Prometheus label sourced from the UDP collector).

`config.py` holds **per-device** settings, not code version info: Wi-Fi credentials (`SSID`/`PSK`), `LOG_LEVEL`, sensor buses (`ONEWIRE = {"pin": 15}`, where absent means enabled on `GPIO_PIN` and `None` means off; `SHT3X = {...}` and `SCD4X = {...}`, where absent or `None` means off), per-sensor names/offsets/`rh_offset`/`publish` (`SENSOR` dict, keyed by DS18B20 ROM ID, SHT3x serial or SCD4x serial), and multicast/UDP settings. Older per-device configs may still contain the removed feed settings (`BASE_URL`, `API_KEY`, `FEED_ID`, `FEED_ENABLED`, `PICO_NAME`). Nothing reads them any more, so they're harmless.

## Architecture / boot flow

No `boot.py` — MicroPython runs `main.py` on power-up directly.

1. `kdmp.log.set_level(config.LOG_LEVEL)` runs first, and itk_pico's `Logger` is enabled only at `info` or `debug`.
2. LED (`Pin("LED", Pin.OUT)`) and hardware watchdog (`WDT(timeout=config.WDT_TIMEOUT_MS)`, or disabled if `WDT_TIMEOUT_MS <= 0`) are initialised.
3. `build_drivers()` creates only the buses that config enables (`DS18B20Bus` wraps itk_pico's `TemperatureSensor`, which raises if it finds no devices, so the adapter catches that; then `kdmp.sensors.sht3x.SHT3x`, then `kdmp.sensors.scd4x.SCD4x`). I2C objects come from `_get_i2c()`, which keeps one per controller: sensors on the same controller share it, and a second pin pair on a controller in use is an error and that sensor is skipped (re-initialising a controller with other pins silently re-maps it).
4. `resolve()` maps each ID to a name, offsets and a `publish` set from `config.SENSOR`. The name precedence is `SENSOR[id]`, then the driver's fallback `name`, then `SENSOR["default"]`, then `DefaultSensor<n>`. `publish` is `SENSOR[id]["publish"]` if set (unknown names warned and ignored), else `DEFAULT_PUBLISH[model]` in `main.py`, else everything the driver measures (`driver.quantities`); it's always limited to what the sensor measures.
5. `check_locations()`: a `name` is a **location**, not a probe. Each quantity at a location must come from exactly one sensor. A clash is logged as an error naming every sensor involved (both keep sending), and one info line per location shows where each value comes from.
6. Initial Wi-Fi connect loop: `wifi.connect(...)` with a bounded `timeout`, retried every 5s on failure (feeding the watchdog between attempts) — never blocks forever.
7. Main `while True:` loop: feed watchdog → LED on → `wifi.try_reconnect_if_lost(...)` → for each driver, feed the watchdog and call `read()` → debug-log every measured quantity, then multicast one packet per reading (`type: "reading"`) with only the published quantities, or nothing if none are published → LED off → sleep, chunked into ~1s increments (feeding the watchdog each chunk).

## Known gotchas (from a field Wi-Fi-hang investigation)

- Units were getting stuck (LED permanently on, no recovery) after a power outage when the router was slow to come back — traced to an **unbounded** `while not wlan.isconnected(): ...` loop in `wifi.py`'s `connect()`. Fixed by adding a `timeout` parameter that returns `False` after `config.WIFI_CONNECT_TIMEOUT` seconds instead of looping forever, plus a hardware watchdog as a last-resort backstop.
- **Never call `wifi.connect()` or `wifi.try_reconnect_if_lost()` without a timeout**, and don't reintroduce an unbounded connect-wait loop.
- The RP2040 hardware watchdog's max timeout is ~8388ms (RP2350 is ~16777ms); `config.WDT_TIMEOUT_MS` must respect whichever chip is in use. Any section that can run longer than that must periodically call `wdt.feed()` — this is why the end-of-loop `sleep(config.SLEEP)` is chunked into 1s increments rather than a single `sleep()` call.
- `wdt` can be `None` (when `config.WDT_TIMEOUT_MS <= 0`) — always guard `wdt.feed()` calls with `if wdt is not None:`.
- The SCD4x NACKs everything if left in a bad state until it's **fully power-cycled**; a soft reset doesn't remove its power. The kdmp driver re-initialises after repeated failures and logs that a power cycle may be needed.
- While the SCD4x is in periodic measurement, only `read_measurement`, `get_data_ready_status`, `stop_periodic_measurement` and the ambient-pressure commands are allowed (see `kdmp/CLAUDE.md`). Its temperature reads a few °C high for a minute or two after (re)start.
- `multicast()` wraps the socket send in try/except `OSError` so a transient network error doesn't crash the main loop.

## UDP message format

JSON over UDP multicast to `config.MCAST_GROUP:config.UDP_PORT`, one packet per physical sensor reading, all with `type: "reading"`. Several packets can share a `name` (a location).

- Each packet carries `model` (`ds18b20`, `sht30`/`sht31`/`sht35`, `scd40`/`scd41`/`scd43`/`scd4x`), `name`, `sensor`, `fw` (`os.uname().release`) and `version` (the `VERSION` constant in `main.py`).
- It carries only the sensor's **published** quantities (`publish`; model defaults in `DEFAULT_PUBLISH`):
  - `temperature` with `offset` applied, plus the `offset` field
  - `humidity` with `rh_offset` applied, plus the `rh_offset` field (added in 2.1.0)
  - `co2` as an int, in ppm (added in 3.0.0)
- Values are rounded to 2 dp **after** the offsets are added.
- A reading with nothing published sends no packet.
- Firmware before 2.1.0 also sent `type: "status"` packets with the IoTPlotter feed result. Those are gone.

Firmware older than 2.0.0 sends `type: "temperature"` with no `model`, `humidity` or `fw`, so receivers must accept both types until every unit is upgraded. Consumers depend on `type`, `name` and `version`, so keep those stable. **From 3.0.0 `temperature` is no longer in every packet** (an SCD4x packet carries only `co2` by default); receivers must skip quantities a packet doesn't contain.

```json
{"type": "reading", "model": "sht30", "name": "LivingRoom", "sensor": "20e80802", "temperature": 22.5, "humidity": 49.9, "offset": -0.5, "rh_offset": 0.0, "fw": "1.24.1", "version": "3.0.0"}
{"type": "reading", "model": "scd41", "name": "LivingRoom", "sensor": "1cab65073b57", "co2": 466, "fw": "1.24.1", "version": "3.0.0"}
```

## What NOT to do

- Don't remove watchdog feeding from any loop, or lengthen a sleep/wait beyond `config.WDT_TIMEOUT_MS` without chunking it.
- Don't reintroduce an unbounded Wi-Fi connect-wait loop.
- Don't add a build/deploy step unless the user explicitly asks for one — deployment is manual file copy today.
- Don't put firmware/code version info in `config.py` — that file is per-device settings only; version lives in `main.py`.
- Don't put new code into `itk_pico` or import `itk_pico` from `kdmp`. In `main.py`, log with `kdmp.log`, not `itk_pico.logger`.
- Don't edit `kdmp/*.py` only inside the submodule checkout. Edit the standalone kdmp clone.
- Don't edit `itk_pico/*.py` only inside the submodule checkout — edit the standalone itk_pico clone, push there, then bump the submodule pointer here.

## Machine-specific notes (private, not committed)

@~/.claude/local/pico-temperature.md

# Pico Temperature — Claude Context

## Project overview

MicroPython firmware for a Raspberry Pi Pico W (or Pico 2 W). Reads DS18B20 1-Wire temperature sensors and/or an SHT3x I2C temperature + humidity sensor, broadcasts readings as JSON over UDP multicast, and optionally POSTs them to an IoTPlotter feed (the feed, `PICO_NAME` and `FEED_ENABLED` are due to be removed).

**Direction: moving from `itk_pico` to `kdmp`.** `kdmp` is the author's own reusable MicroPython package, included as a submodule. It isn't tied to any particular board and targets both the Pico and the ESP32. The author is migrating so that the code can run on more kinds of board and so that the author controls the architectural choices. That isn't a criticism of `itk_pico`: thanks to Eugene Tkachenko, whose framework inspired this project and was its starting point. New reusable code (sensor drivers, logging, and later Wi-Fi/UDP/networking) goes into `kdmp`, never into `itk_pico`, and must not import from `itk_pico`. `itk_pico` is still used for Wi-Fi and, via a temporary `DS18B20Bus` adapter in `main.py`, for DS18B20 sensors until those are migrated.

## Repo layout

```
pico-temperature/
├── main.py              Entry point — no boot.py exists, MicroPython runs main.py directly
├── config.py             Per-device settings, committed with placeholder values
├── kdmp/                 Git submodule — reusable board-agnostic package (see kdmp/CLAUDE.md)
│   ├── log.py            Levelled logger (kdmp.log.get(name), set_level from config.LOG_LEVEL)
│   └── sensors/          base.py (SensorDriver: ids()/read() -> list of readings), sht3x.py
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

There is no build step. Files are copied directly onto the Pico's MicroPython filesystem (see `README.md` Installation section for the exact file list: `main.py`, `config.py`, the `itk_pico/*.py` files in use, and `kdmp/__init__.py`, `kdmp/log.py`, `kdmp/sensors/*.py`). Before copying changed code to a unit, **bump `VERSION` in `main.py`** — it's sent in every UDP message specifically so units can be identified by firmware version without physically consoling into them (e.g. via a Prometheus label sourced from the UDP collector).

`config.py` holds **per-device** settings, not code version info: Wi-Fi credentials (`SSID`/`PSK`), `LOG_LEVEL`, sensor buses (`ONEWIRE = {"pin": 15}`, where absent means enabled on `GPIO_PIN` and `None` means off; `SHT3X = {...}`, where absent or `None` means off), per-sensor names/offsets/`rh_offset` (`SENSOR` dict, keyed by DS18B20 ROM ID or SHT3x serial), multicast/UDP settings, and IoT feed config (`BASE_URL`/`API_KEY`/`FEED_ID`/`FEED_ENABLED`). Real per-device config also needs `PICO_NAME` (referenced in `main.py` status messages but not present in the template `config.py` — must be added when configuring a physical unit).

## Architecture / boot flow

No `boot.py` — MicroPython runs `main.py` on power-up directly.

1. `kdmp.log.set_level(config.LOG_LEVEL)` runs first, and itk_pico's `Logger` is enabled only at `info` or `debug`.
2. LED (`Pin("LED", Pin.OUT)`) and hardware watchdog (`WDT(timeout=config.WDT_TIMEOUT_MS)`, or disabled if `WDT_TIMEOUT_MS <= 0`) are initialised.
3. `build_drivers()` creates only the buses that config enables (`DS18B20Bus` wraps itk_pico's `TemperatureSensor`, which raises if it finds no devices, so the adapter catches that; then `kdmp.sensors.sht3x.SHT3x`). `resolve()` maps each ID to a name and offsets from `config.SENSOR`. The precedence is `SENSOR[id]`, then the driver's fallback `name`, then `SENSOR["default"]`, then `DefaultSensor<n>`.
4. Initial Wi-Fi connect loop: `wifi.connect(...)` with a bounded `timeout`, retried every 5s on failure (feeding the watchdog between attempts) — never blocks forever.
5. Main `while True:` loop: feed watchdog → LED on → `wifi.try_reconnect_if_lost(...)` → for each driver, feed the watchdog and call `read()` → multicast one packet per reading (`type: "reading"`) → optional IoTPlotter POST + multicast status (`type: "status"`) → LED off → sleep, chunked into ~1s increments (feeding the watchdog each chunk).

## Known gotchas (from a field Wi-Fi-hang investigation)

- Units were getting stuck (LED permanently on, no recovery) after a power outage when the router was slow to come back — traced to an **unbounded** `while not wlan.isconnected(): ...` loop in `wifi.py`'s `connect()`. Fixed by adding a `timeout` parameter that returns `False` after `config.WIFI_CONNECT_TIMEOUT` seconds instead of looping forever, plus a hardware watchdog as a last-resort backstop.
- **Never call `wifi.connect()` or `wifi.try_reconnect_if_lost()` without a timeout**, and don't reintroduce an unbounded connect-wait loop.
- The RP2040 hardware watchdog's max timeout is ~8388ms (RP2350 is ~16777ms); `config.WDT_TIMEOUT_MS` must respect whichever chip is in use. Any section that can run longer than that must periodically call `wdt.feed()` — this is why the end-of-loop `sleep(config.SLEEP)` is chunked into 1s increments rather than a single `sleep()` call.
- `wdt` can be `None` (when `config.WDT_TIMEOUT_MS <= 0`) — always guard `wdt.feed()` calls with `if wdt is not None:`.
- `multicast()` wraps the socket send in try/except `OSError` so a transient network error doesn't crash the main loop.

## UDP message format

JSON over UDP multicast to `config.MCAST_GROUP:config.UDP_PORT`. There are two message types, and both carry `"version"` (the `VERSION` constant in `main.py`).

- **`type: "reading"`**: one packet per sensor reading. It carries `model` (`ds18b20` or `sht30`) and `fw` (`os.uname().release`), plus `humidity` (with `rh_offset` applied) when the sensor measures it.
- **`type: "status"`**: the IoTPlotter feed result.

Firmware older than 2.0.0 sends `type: "temperature"` with no `model`, `humidity` or `fw`, so receivers must accept both types until every unit is upgraded. Consumers depend on `type`, `name`, `temperature` and `version`, so keep those stable from now on.

```json
{"type": "reading", "model": "sht30", "name": "LivingRoom", "sensor": "20e80802", "temperature": 22.5, "humidity": 49.9, "offset": -0.5, "fw": "1.24.1", "version": "2.0.0"}
{"type": "status", "name": "<PICO_NAME>", "status": "API 200 ...", "version": "2.0.0"}
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

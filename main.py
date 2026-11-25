# Author: Karl Dyson https://karld.blog
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# See the LICENSE file for the full text of the license.
#
# Last Updated: November 2026
#

import config
from kdmp import log

# Set the log level before anything else logs. "debug" for development
# with a console attached; "warning" or "off" for production units.
log.set_level(getattr(config, "LOG_LEVEL", "info"))
_log = log.get("main")

from itk_pico.wifi import WiFi
from itk_pico.logger import Logger
from kdmp.sensors.sht3x import SHT3x
from kdmp.sensors.scd4x import SCD4x
from time import sleep
import json
import os
import socket
from machine import Pin, I2C, WDT

# itk_pico (Wi-Fi) still logs via its own Logger; keep it in step with
# our level until Wi-Fi handling moves into kdmp.
Logger.set_enabled(log.get_level() <= log.INFO)

## Sub routines ##

def multicast(message_dict):
	# ...and encode it into JSON
	message = json.dumps(message_dict)

	sock = None

	try:

		# create the UDP socket
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

		# ...and turn it into a multicast packet
		if hasattr(socket, "IP_MULTICAST_TTL"):
			sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

		# send the packet to the network
		sock.sendto(message, (config.MCAST_GROUP, config.UDP_PORT))
		_log.debug("sent multicast to %s:%s :: %s", config.MCAST_GROUP, config.UDP_PORT, message)
	except OSError as e:
		_log.warning("multicast send failed: %s", e)
	finally:
		if sock is not None:
			try:
				# ...and close the socket
				sock.close()
			except OSError:
				pass

	# end of multicast


class DS18B20Bus:
	"""Temporary adapter giving itk_pico's TemperatureSensor the
	kdmp.sensors driver interface (ids() / read() -> list of readings).
	Goes away when DS18B20 support is migrated into kdmp."""

	model = "ds18b20"
	quantities = ("temperature",)

	def __init__(self, pin):
		self._sensor = None
		try:
			from itk_pico.temperature import TemperatureSensor
			self._sensor = TemperatureSensor(pin)
		except Exception as e:
			_log.error("1-Wire on GPIO %s: %s", pin, e)

	def ids(self):
		if self._sensor is None:
			return []
		return list(self._sensor.get_device_friendly_names().keys())

	def read(self):
		if self._sensor is None:
			return []
		try:
			temps = self._sensor.get_temperatures()
		except Exception as e:
			_log.error("1-Wire read failed: %s", e)
			return []
		readings = []
		for sensor_id, t in temps.items():
			if t is None:
				continue
			readings.append({"sensor": sensor_id, "model": self.model, "temperature": t})
		return readings


# One I2C object per controller. Initialising the same controller twice
# with different pins silently re-maps it, so sensors sharing a
# controller must share its pins and its I2C object.
_i2c_buses = {}

def _get_i2c(cfg, what):
	"""The I2C object for cfg's controller, created on first use. Returns
	None (and logs an error) if the controller is already in use on
	different pins."""
	ctrl = cfg["i2c"]
	pins = (cfg["sda"], cfg["scl"])
	if ctrl in _i2c_buses:
		used_pins, i2c = _i2c_buses[ctrl]
		if used_pins != pins:
			_log.error("%s: I2C%s is already in use on SDA/SCL GP%s/GP%s, not GP%s/GP%s; skipping %s",
				what, ctrl, used_pins[0], used_pins[1], pins[0], pins[1], what)
			return None
		return i2c
	i2c = I2C(ctrl, sda=Pin(pins[0]), scl=Pin(pins[1]), freq=cfg.get("freq", 100000))
	_i2c_buses[ctrl] = (pins, i2c)
	_log.info("I2C%s on SDA GP%s, SCL GP%s", ctrl, pins[0], pins[1])
	return i2c


def build_drivers():
	"""Initialise only the sensor buses config enables.
	Returns a list of (driver, fallback_name) tuples."""
	drivers = []

	# 1-Wire: absent => enabled on GPIO_PIN (back-compat); None => disabled
	onewire = getattr(config, "ONEWIRE", "absent")
	if onewire == "absent":
		onewire = {"pin": getattr(config, "GPIO_PIN", 15)}
	if onewire:
		_log.info("1-Wire enabled on GPIO %s", onewire["pin"])
		drivers.append((DS18B20Bus(onewire["pin"]), onewire.get("name")))

	# SHT3x: absent/None => disabled
	sht = getattr(config, "SHT3X", None)
	if sht:
		try:
			i2c = _get_i2c(sht, "SHT3x")
			if i2c is not None:
				drv = SHT3x(i2c, addr=sht.get("addr", 0x44), bus=sht["i2c"], model=sht.get("model", "sht30"))
				drivers.append((drv, sht.get("name")))
		except Exception as e:
			_log.error("SHT3x init failed: %s", e)

	# SCD4x (SCD40/41/43): absent/None => disabled
	scd = getattr(config, "SCD4X", None)
	if scd:
		try:
			i2c = _get_i2c(scd, "SCD4x")
			if i2c is not None:
				drv = SCD4x(i2c, addr=scd.get("addr", 0x62), bus=scd["i2c"], model=scd.get("model"),
					temperature_offset=scd.get("temperature_offset"), altitude=scd.get("altitude"))
				drivers.append((drv, scd.get("name")))
		except Exception as e:
			_log.error("SCD4x init failed: %s", e)

	if not drivers:
		_log.warning("No sensors enabled in config")
	return drivers


# Quantities a packet can carry, and which of them each model publishes
# unless SENSOR[id]["publish"] says otherwise. A model not listed here
# publishes everything its driver measures.
QUANTITIES = ("temperature", "humidity", "co2")
DEFAULT_PUBLISH = {
	"ds18b20": ("temperature",),
	"sht30": ("temperature", "humidity"),
	"sht31": ("temperature", "humidity"),
	"sht35": ("temperature", "humidity"),
	"scd40": ("co2",),
	"scd41": ("co2",),
	"scd43": ("co2",),
	"scd4x": ("co2",),
}

_resolved = {}
_default_counter = [0]

def resolve(sensor_id, fallback_name=None, model=None, measured=QUANTITIES):
	"""Name, offsets and published quantities for a sensor ID, from
	config.SENSOR. Name precedence: SENSOR[id] > driver fallback name >
	SENSOR["default"] > DefaultSensor<n>. Published quantities:
	SENSOR[id]["publish"] if set, else DEFAULT_PUBLISH[model], else all
	measured; always limited to what the sensor measures."""
	if sensor_id in _resolved:
		return _resolved[sensor_id]

	sensors_cfg = getattr(config, "SENSOR", {})
	default = sensors_cfg.get("default", {})
	specific = sensors_cfg.get(sensor_id, {})

	name = specific.get("name") or fallback_name or default.get("name")
	if not name:
		_default_counter[0] += 1
		name = "DefaultSensor%d" % _default_counter[0]

	if "publish" in specific:
		wanted = []
		for q in specific["publish"]:
			if q in QUANTITIES:
				wanted.append(q)
			else:
				_log.warning("Sensor %s: unknown quantity %r in publish, ignored (known: %s)", sensor_id, q, ", ".join(QUANTITIES))
	else:
		wanted = DEFAULT_PUBLISH.get(model, measured)
	# keep QUANTITIES order; silently drop what this sensor doesn't measure
	publish = tuple(q for q in QUANTITIES if q in wanted and q in measured)

	cfg = {
		"name": name,
		"model": model,
		"offset": specific.get("offset", default.get("offset", 0.0)),
		"rh_offset": specific.get("rh_offset", default.get("rh_offset", 0.0)),
		"publish": publish,
	}
	_resolved[sensor_id] = cfg
	_log.info("Sensor %s (%s); Name: %s; Offset: %s; RH offset: %s; Publish: %s", sensor_id, model, cfg["name"],
		cfg["offset"], cfg["rh_offset"], ", ".join(publish) or "nothing")
	return cfg


def check_locations():
	"""A name is a location; each quantity at a location must come from
	exactly one sensor. Log an error for each clash (both sensors keep
	sending) and one info line per location showing where its values
	come from."""
	locations = {}
	for sensor_id, cfg in _resolved.items():
		quantities = locations.setdefault(cfg["name"], {})
		for q in cfg["publish"]:
			quantities.setdefault(q, []).append((sensor_id, cfg["model"]))

	for name in sorted(locations):
		quantities = locations[name]
		for q in QUANTITIES:
			sources = quantities.get(q, [])
			if len(sources) > 1:
				_log.error("Location %s: %s is published by %d sensors (%s). Give each sensor its own SENSOR "
					"entry/name, or set \"publish\" so only one of them sends %s.", name, q, len(sources),
					", ".join("%s (%s)" % s for s in sources), q)

		# group quantities by source sensor for a readable summary
		by_sensor = []
		for q in QUANTITIES:
			for src in quantities.get(q, []):
				for entry in by_sensor:
					if entry[0] == src:
						entry[1].append(q)
						break
				else:
					by_sensor.append((src, [q]))
		_log.info("%s: %s", name, "; ".join("%s <- %s (%s)" % (", ".join(qs), src[0], src[1]) for src, qs in by_sensor) or "nothing published")


## Main code ##

# Bump this by hand whenever main.py or a deployed itk_pico/*.py or
# kdmp/*.py file changes, before redeploying to units. Sent in every UDP
# message so unit versions can be tracked without consoling into each device.
VERSION = "3.0.0"

# MicroPython release, also sent in every UDP message
FW = os.uname().release

led = Pin("LED", Pin.OUT)

# Hardware watchdog: if the loop below ever stalls for longer than this
# without feeding it, the board resets itself. Last-resort recovery for
# a wedged Wi-Fi driver or any other unforeseen hang.
if config.WDT_TIMEOUT_MS > 0:
	wdt = WDT(timeout=config.WDT_TIMEOUT_MS)
	_log.info("WDT initialised to %sms", config.WDT_TIMEOUT_MS)
else:
	wdt = None
	_log.info("WDT disabled (timeout is %s)", config.WDT_TIMEOUT_MS)

_log.info("Firmware %s, MicroPython %s", VERSION, FW)

# initialise the enabled sensor drivers and resolve names/offsets for
# every sensor found (check the log on first boot for IDs to add to
# config.SENSOR)
drivers = build_drivers()
for driver, fallback_name in drivers:
	for sensor_id in driver.ids():
		resolve(sensor_id, fallback_name, driver.model, driver.quantities)
check_locations()

# Initialise the WiFi
wifi = WiFi()

# Connect to the WiFi
while not wifi.connect(config.SSID, config.PSK, timeout=config.WIFI_CONNECT_TIMEOUT, wdt=wdt):
	_log.warning("Initial connect failed, retrying...")
	sleep(5)
	if wdt is not None:
		wdt.feed()

# ...and start the main loop
_log.info("Starting main loop...")
while True:
	if wdt is not None:
		wdt.feed()

	# Turn the LED on so we have some external indication of progress
	led.on()

	# Check we're still connected to the wifi...
	wifi.try_reconnect_if_lost(timeout=config.WIFI_CONNECT_TIMEOUT, wdt=wdt)

	for driver, fallback_name in drivers:
		if wdt is not None:
			wdt.feed()

		for reading in driver.read():
			sensor_id = reading["sensor"]
			cfg = resolve(sensor_id, fallback_name, reading["model"], driver.quantities)
			publish = cfg["publish"]

			message_dict = {"type": "reading", "model": reading["model"], "name": cfg["name"], "sensor": sensor_id, "fw": FW, "version": VERSION}

			# apply the fudge factor(s) to the received values; round after
			# the addition so packets don't carry float noise. Every measured
			# value is logged; only the published ones go in the packet.
			parts = []
			if "co2" in reading:
				parts.append("co2 %s ppm%s" % (reading["co2"], " [pub]" if "co2" in publish else ""))
				if "co2" in publish:
					message_dict["co2"] = int(reading["co2"])
			if "temperature" in reading:
				temperature = round(reading["temperature"] + cfg["offset"], 2)
				parts.append("T %s C%s" % (temperature, " [pub]" if "temperature" in publish else ""))
				if "temperature" in publish:
					message_dict["temperature"] = temperature
					message_dict["offset"] = cfg["offset"]
			if "humidity" in reading:
				humidity = round(reading["humidity"] + cfg["rh_offset"], 2)
				parts.append("RH %s %%%s" % (humidity, " [pub]" if "humidity" in publish else ""))
				if "humidity" in publish:
					message_dict["humidity"] = humidity
					message_dict["rh_offset"] = cfg["rh_offset"]

			sent = [q for q in QUANTITIES if q in message_dict]
			_log.debug("Sensor %s (%s, %s): %s -> published: %s", sensor_id, cfg["name"], reading["model"], ", ".join(parts), ", ".join(sent) or "nothing")

			# and multicast it, unless there's nothing to send
			if sent:
				multicast(message_dict)
			else:
				_log.debug("Sensor %s: nothing to publish, no packet sent", sensor_id)

	# ...and sleep
	_log.debug("Sleeping for %s seconds", config.SLEEP)
	led.off()
	# Sleep in small increments, feeding the watchdog each time, since
	# config.SLEEP may exceed the hardware watchdog's max timeout.
	remaining = config.SLEEP
	while remaining > 0:
		if wdt is not None:
			wdt.feed()

		chunk = min(1, remaining)
		sleep(chunk)
		remaining -= chunk

# vim: noet ts=4

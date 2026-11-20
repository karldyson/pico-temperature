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
			i2c = I2C(sht["i2c"], sda=Pin(sht["sda"]), scl=Pin(sht["scl"]), freq=sht.get("freq", 100000))
			drv = SHT3x(i2c, addr=sht.get("addr", 0x44), bus=sht["i2c"], model=sht.get("model", "sht30"))
			drivers.append((drv, sht.get("name")))
		except Exception as e:
			_log.error("SHT3x init failed: %s", e)

	if not drivers:
		_log.warning("No sensors enabled in config")
	return drivers


_resolved = {}
_default_counter = [0]

def resolve(sensor_id, fallback_name=None):
	"""Name and offsets for a sensor ID, from config.SENSOR. Precedence:
	SENSOR[id] > driver fallback name > SENSOR["default"] > DefaultSensor<n>."""
	if sensor_id in _resolved:
		return _resolved[sensor_id]

	sensors_cfg = getattr(config, "SENSOR", {})
	default = sensors_cfg.get("default", {})
	specific = sensors_cfg.get(sensor_id, {})

	name = specific.get("name") or fallback_name or default.get("name")
	if not name:
		_default_counter[0] += 1
		name = "DefaultSensor%d" % _default_counter[0]

	cfg = {
		"name": name,
		"offset": specific.get("offset", default.get("offset", 0.0)),
		"rh_offset": specific.get("rh_offset", default.get("rh_offset", 0.0)),
	}
	_resolved[sensor_id] = cfg
	_log.info("Sensor %s; Name: %s; Offset: %s; RH offset: %s", sensor_id, cfg["name"], cfg["offset"], cfg["rh_offset"])
	return cfg

## Main code ##

# Bump this by hand whenever main.py or a deployed itk_pico/*.py or
# kdmp/*.py file changes, before redeploying to units. Sent in every UDP
# message so unit versions can be tracked without consoling into each device.
VERSION = "2.1.0"

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
		resolve(sensor_id, fallback_name)

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
			cfg = resolve(sensor_id, fallback_name)

			# apply the fudge factor(s) to the received values; round after
			# the addition so packets don't carry float noise
			temperature = round(reading["temperature"] + cfg["offset"], 2)

			message_dict = {"type": "reading", "model": reading["model"], "name": cfg["name"], "sensor": sensor_id, "temperature": temperature, "offset": cfg["offset"], "fw": FW, "version": VERSION}

			if "humidity" in reading:
				message_dict["humidity"] = round(reading["humidity"] + cfg["rh_offset"], 2)
				message_dict["rh_offset"] = cfg["rh_offset"]

			_log.debug("Sensor: %s; Name: %s; Temp: %s; RH: %s", sensor_id, cfg["name"], temperature, message_dict.get("humidity"))

			# and multicast it
			multicast(message_dict)

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

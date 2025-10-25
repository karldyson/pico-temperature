# Author: Karl Dyson https://karld.blog
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# See the LICENSE file for the full text of the license.

from itk_pico.temperature import TemperatureSensor
from itk_pico.wifi import WiFi
from itk_pico.logger import Logger
from time import sleep
import json
import config
import requests

# initialise a temperature sensor object
temperature_sensor = TemperatureSensor(config.GPIO_PIN)

# initialise the sensor config dictionary with friendly names
sensor_config = temperature_sensor.get_device_friendly_names()

# loop around the sensors
sensor_counter = 1
for sensor in sensor_config:
    Logger.print(f"Initialising sensor {sensor} details...")

    # set them each to the default
    if "default" in config.SENSOR.keys():
        sensor_config[sensor]["name"] = config.SENSOR["default"]["name"]
    else:
        sensor_config[sensor]["name"] = "DefaultSensor" + sensor_counter
        sensor_counter += 1

    # if the sensor has specific settings in the config, use those
    if sensor in config.SENSOR.keys():
        if "name" in config.SENSOR[sensor].keys():
            sensor_config[sensor]["name"] = config.SENSOR[sensor]["name"]

    Logger.print(f"Sensor {sensor}; Name: {sensor_config[sensor]['name']}") 

# Initialise the WiFi
wifi = WiFi()

# Connect to the WiFi
wifi.connect(config.SSID, config.PSK)

# Initialise the feed URL
if hasattr(config, "BASE_URL") and config.BASE_URL and hasattr(config, "FEED_ID") and config.FEED_ID:
    feed_url = config.BASE_URL + config.FEED_ID
    Logger.print("Feed URL:", feed_url)
else:
    FEED_ENABLED = False
    Logger.print("No feed details, disabling feed")

# Initialise the API headers
headers = {'api-key': config.API_KEY}

# ...and start the main loop
Logger.print("Starting main loop...")
while True:
    # Check we're still connected to the wifi...
    wifi.try_reconnect_if_lost()
    
    # Loop through the sensors getting the current temperatures
    sensors = temperature_sensor.get_temperature()

    # Initialise the API payload dictionary
    payload = {}
    payload["data"] = {}

    # Loop through each of the sensors
    for sensor in sensors:
        
        # get the friendly name and the fudge factor from the config
        sensor_name = sensor_config[sensor]["name"]

        # apply the fudge factor to the received temperature value
        temperature = sensors[sensor]

        # ...some debug output
        Logger.print(f"Sensor: {sensor}; Name: {sensor_name}; Temp: {temperature}")

        # add to API payload
        payload["data"][sensor_name] = []
        payload["data"][sensor_name].append({"value": sensors[sensor]})
    
    # if the feed is enabled, send the payload to the API endpoint
    if config.FEED_ENABLED:
        response = requests.post(feed_url, headers=headers, data=json.dumps(payload))
        Logger.print(f"API response: {response.status_code} {response.text}")

    # ...and sleep
    Logger.print(f"Sleeping for {config.SLEEP} seconds")
    sleep(config.SLEEP)

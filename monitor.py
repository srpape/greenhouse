#!/usr/bin/env python
import sys 
import RPi.GPIO as GPIO 
from time import sleep 
import Adafruit_DHT 
import urllib2 
import RPi.GPIO as rpi
from pyepsolartracer.client import EPsolarTracerClient
from pyepsolartracer.registers import registers, coils
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pyepsolartracer.registers import registerByName
import os
from astral import Astral
from datetime import datetime
import pytz
import traceback

# ThingSpeak API key
myAPI = "VCSUZQYZSA2ZFVSR"
baseURL = 'https://api.thingspeak.com/update?api_key=%s' % myAPI 

# Email settings
SENDMAIL = "/usr/sbin/sendmail"  # sendmail location
FROM = "papes@greenhouse"
TO = ["srpape@gmail.com"]

# GPIO DHT22 sensor
gpio = 23

# Fan on temperature
fanOnTemperature = 86.0

# Turn the fan off when the temperature falls below this temp
fanOffTemperature = 83.0

# Stop draining the battery if it's under the given percentage
minimumBattery = 25

# Resume draining the battery if it reaches this percentage
minimumBatteryRecovery = 30

# For tracking sunrise/sunset times
city_name = "New York"

#
# Global variables
#
lastRH = 0.0
lastTemp = 0.0
pvCurrent = 0.0
loadCurrent = 0.0
batteryLevel = 0.0
batteryCurrent = 0.0
batteryVoltage = 0.0
fanRunning = False

astral = Astral()
astral.solar_depression = 'civil'
city = astral[city_name]

# configure the client logging
import logging
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)


def generateBody():
    result = "RH: " + str(lastRH) + " %\n"
    result += "Temp: " + str(lastTemp) + " F\n"
    result += "Battery SOC: " + str(batteryLevel) + " %\n"
    result += "PV Amps: " + str(pvCurrent) + " A\n"
    result += "Load Amps: " + str(loadCurrent) + " A\n"
    result += "Battery Amps: " + str(batteryCurrent) + " A\n"
    result += "Battery Voltage: " + str(batteryVoltage) + " V\n"
    result += "Fan Running: " + str(fanRunning) + "\n"
    return result


def sendMail(subject, body):
    body += generateBody()
    
    # Prepare actual message
    message = "From: %s\nTo: %s\nSubject: Greenhouse Monitor - %s\n\n%s" % (FROM, ", ".join(TO), subject, body)
    
    try:
        # Send it
        p = os.popen("%s -t -i" % SENDMAIL, "w")
        p.write(message)
        p.close()
    except Exception as e:
        print "Send mail failed: ", str(e)
        pass


# Convert C to F
def celsiusToFahrenheit(c):
    return (1.8 * c) + 32


# Read temperature data
def updateClimateData():
    global lastRH
    global lastTemp
    
    RH, T = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, gpio)
    RH = round(RH, 1) 
    T = round(T, 1) 
    lastRH = RH
    lastTemp = celsiusToFahrenheit(T)


# Read PV information
def updateSolarData(client):
    global pvCurrent
    global loadCurrent
    global batteryLevel
    global batteryCurrent
    global batteryVoltage
    
    # If we fail to read the value, assume it's unchanged
    try:
        pvCurrent = float(client.read_input("Charging equipment input current"))
    except Exception:
        pass

    try:
        loadCurrent = float(client.read_input("Discharging equipment output current"))
    except Exception:
        pass

    try: 
        batteryLevel = float(client.read_input("Battery SOC"))
    except Exception:
        pass

    try:
        batteryCurrent = float(client.read_input("Battery Current"))
    except Exception:
        pass

    try:
        batteryVoltage= float(client.read_input("Charging equipment output voltage"))
    except Exception:
        pass


def logData():
    try:
        f = urllib2.urlopen(baseURL + "&field1=%s&field2=%s&field3=%s&field4=%s&field5=%s&field6=%s&field7=%s" % (str(lastRH), str(lastTemp), str(pvCurrent), str(loadCurrent), str(batteryLevel), str(batteryCurrent), str(batteryVoltage))) 
        f.close()
    except Exception:
        # For some reason the data was not accepted
        # ThingSpeek gives a lot of 500 errors 
        pass

    
# Set the load on or off (True or False)
def setLoad(client, value):
    global fanRunning
    
    if not client.write_output("Manual control the load", value):
        print "WARNING: Fan control failed!"
        sendMail("WARNING: Fan control failed!", "")
    else:
        fanRunning = value


# Decide if we should be running the fan or not
def controlFan(client):
    sun = city.sun(local=True)
    now = datetime.now(pytz.timezone(city.timezone))
    sunrise = sun['sunrise']
    sunset = sun['sunset']
            
    # Is the fan already on?
    if fanRunning:
        # The fan is currently on

        # Are we after sunset? If so, turn off the fan.
        if now > sunset:
            print "Disabling fan due to sunset"
            sendMail("Disabling fan due to sunset", "")
            setLoad(client, False)
        # Are we below the turn-off threshold?
        elif lastTemp < fanOffTemperature:
            print "Disabling fan due to temperature"
            #sendMail("Disabling fan due to temperature", "")
            setLoad(client, False)
        # Is the battery level too low?
        elif batteryLevel < minimumBattery:
            print "Disabling fan due to battery level"
            sendMail("Disabling fan due to battery level", "")
            setLoad(client, False)            
    else:
        # The fan is not already on
        
        # Only turn on the fan if we're in the daytime range
        if now > sunrise and now < sunset:        
            # Are we above the turn-on threshold?
            if lastTemp > fanOnTemperature:
                if batteryLevel > minimumBatteryRecovery:
                    print "Enabling fan due to temperature"
                    #sendMail("Enabling fan due to temperature", "")
                    setLoad(client, True)
                else:
                    sendMail("Unable to enable fan due to low battery", "")
                    print "Unable to enable fan due to low battery"


def main(): 
    global fanRunning
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(gpio, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    serialclient = ModbusClient(method='rtu', port='/dev/ttyXRUSB0', baudrate=115200, stopbits=1, bytesize=8, timeout=0.5)
    client = EPsolarTracerClient(serialclient=serialclient)
    client.connect()

    # Query the initial fan state
    fanRunning = bool(int(client.read_input("Manual control the load")))
    
    updateClimateData()
    updateSolarData(client)
    sendMail("Starting", "")

    
    try: 
        while True:
            updateClimateData()
            updateSolarData(client)
            controlFan(client)
            logData()
            sleep(30)
    except Exception:
        error = traceback.format_exc()
        sendMail("Crash", error)
        print error
        print 'exiting.'
        client.close()


# call main 
if __name__ == '__main__': 
    main()  


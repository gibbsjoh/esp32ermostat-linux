# Fork of esp32ermostat to full-fat Python on Linux (RPi, but could work with boards with compatible GPIO pins)

import time
import socket
import json
import requests
import asyncio
import VisionFive.gpio as GPIO
import dht11
from configvars import *


# set up socket for http server
thisSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
thisSocket.setblocking(False) # need to set non blocking so async works!
thisSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
thisSocket.bind(('', 8080))
thisSocket.listen(5)


# define a pin for relay control
GPIO.setmode(GPIO.BCM) # Use Broadcom pin numbering
GPIO.setwarnings(False)
relayPin = 44
GPIO.setup(relayPin, GPIO.OUT)
# to turn on: GPIO.output(relayPin, GPIO.HIGH)
# to turn off: GPIO.output(relayPin, GPIO.LOW)

# start with boiler off
GPIO.output(relayPin, GPIO.LOW)

# added local dht11 rather than using remote sensor
dht11Pin = 61
localTempSensor = dht11.DHT11(pin=dht11Pin)

# try to read most recent target temp from file, otherwise set to 19
try:
    with open("target.txt","r") as theFile:
        targetTemp = int(theFile.read())
except:
    targetTemp = defaultTemp # target temp for the boiler to achieve if not stored - set to something around what you'd usually have

# get the temp every 30 seconds and create a rolling average over 5 mins
# Store the last 10 readings (5 minutes at 30s intervals)
tempBuffer = []
bufferIndex = 0
bufferFilled = False

# load the html
def web_page():
    file = open('index.html', 'r')
    html = file.read()
    file.close()
    return html

html = web_page()

def getTempFromSensor():
    # get the current temp from the pi pico
    # it'll return JSON: {"temp":12.345}
    global sensorURL
    global targetTemp
    global tempSensorType
    # if tempSensorType == "remote":
    #     try:
    #         response = requests.get(sensorURL)
    #         responseJSON = json.loads(response.text)
    #         theTempReading = responseJSON["temp"]
    #         returnMe = round(float(theTempReading),1)
    #     except:
    #         returnMe = targetTemp # if the sensor stops responding, use whatever the target was last time
    # else:
    #     sensorReading = localTempSensor.read()
    #     if sensorReading.is_valid():
    #         theTemp = sensorReading.temperature
    #         returnMe = theTemp
    #     else:
    #         print("Error: %d" % sensorReading.error_code)
    #         returnMe = 0
    returnMe = 20
    return returnMe

def writeTargetToFile(targetTemp):
    # writes the target temp to target.txt, so we can read this on reboot
    with open("target.txt","w") as theFile:
        theFile.write(str(targetTemp))

def addCurrentTempToBuffer():
    global bufferIndex, bufferFilled

    temp = getTempFromSensor()
    print(temp)
    if temp > 0:
        if len(tempBuffer) < bufferSize:
            tempBuffer.append(temp)
            if len(tempBuffer) == bufferSize:
                bufferFilled = True
        else:
            tempBuffer[bufferIndex] = temp
            bufferIndex = (bufferIndex + 1) % bufferSize
        print(tempBuffer)

def getRunningAverage():
    if not tempBuffer:
        return None
    theAverageTemp = round(sum(tempBuffer) / len(tempBuffer),1)
    #print("Current average:", theAverageTemp)
    return theAverageTemp

async def getTempLoop():
    while True:
        addCurrentTempToBuffer()
        await asyncio.sleep(55)   # 55‑second interval
        
def parseRequest(theRequest):
    returnMe = {}
    reqString = theRequest.decode() # convert bytes to a string
    print(type(reqString))
    theList = reqString.split()[1]
    theArguments = theList.replace("?","").replace("&","\n").replace("/","")
    if theArguments != "favicon":
        for thisArg in theArguments.splitlines():
            try:
                thisKey = thisArg.split("=")[0]
                thisValue = thisArg.split("=")[1]
                returnMe[thisKey] = thisValue
            except:
                pass
        if not "show" in returnMe:
            returnMe["show"] = "json"
    else:
        returnMe["show"] = "json"
    return returnMe


# webserver notes:
# if no arguments are passed in the URL, then return OK
# arguments structure:
# theurl.com:8080/?show -> "webpage" or "json"
#       -> If "webpage", show HTML
#       -> If "json", return status JSON
#       -> other variables can be set: target (set target temp) and overrideThermoNow (sets boiler to on for specified time period)

async def webServer():
    ## set vars that are global ##
    global targetTemp
    global html
    global boilerOnOff
    global thisSocket
    global overrideThermo
    global overrideMaxMins
    global overrideStartTime
    overrideThermoNow = 0

    # set up socket
    while True:
        # wrap the accept() in a try statement in case this function isn't currently the current task in the async business
        try:
            conn, addr = thisSocket.accept()
        except OSError:
            await asyncio.sleep(0.1)
            continue

        #print('Got a connection from %s' % str(addr))
        conn.setblocking(False)
            # Non-blocking recv
        try:
            request = conn.recv(1024)
        except OSError:
            # No data yet → yield and retry next loop
            conn.close()
            await asyncio.sleep(0.01)
            continue
        
        # parse the URL parameter
        theParameter = parseRequest(request)
        # now we have a JSON array of arguments, do things based thereon
        # get the param name and value
        for pKey in theParameter:
            globals()[pKey] = theParameter[pKey]

        targetTemp = target if target is not None else targetTemp
        showMe = show
        roomTemp = getRunningAverage()
        
        # target temp will be set from the var setting above, no need to set it
        
        # set vars for boiler control
        if overrideThermoNow == 1:
            # is it a value change
            overrideThermoNow = 0
            if overrideThermo == 0:
                overrideThermo = 1
                overrideStartTime = time.monotonic()
                GPIO.output(relayPin, GPIO.HIGH)
                boilerOnOff = "On"
        elif overrideThermoNow == 2:
            # manually turn off before 20 mins
            overrideThermoNow = 0
            overrideThermo = 0
            GPIO.output(relayPin, GPIO.LOW)
            boilerOnOff = "Off"

        if showMe == "json":
            response = {"boilerStatus":boilerOnOff,"targetTemp":targetTemp,"roomTemp":roomTemp}
            response = str(response)
            theHeader = "HTTP/1.1 200 OK\nContent-Type: application/json\nConnection: close\n\n"
        elif showMe == "webpage":
            # set boiler status text
            response = (
            html.replace("{boilerStatus}", boilerOnOff)
                .replace("{targetTemp}", str(targetTemp))
                .replace("{roomTemp}", str(getRunningAverage()))
                .replace("{orDisplayString}", orDisplayString)
                )
            theHeader = "HTTP/1.1 200 OK\nContent-Type: text/html\nConnection: close\n\n"
        
        conn.send(theHeader.encode())
        conn.sendall(response.encode())
        conn.close()
        
        await asyncio.sleep(1)
        
async def boilerControl():
    global targetTemp
    global boilerOnOff
    global overrideThermo
    global overrideStartTime
    global overrideMaxMins
    # get the average temperature
    # compare it to the target temp
    # turn boiler on or off accordingly
    while True:
        #print("Called boiler loop")
        currentAverage = getRunningAverage()

        if overrideThermo == 1:
            # check time elapsed since it was set
            timeNow = time.monotonic()
            #print(timeNow)
            #print(overrideStartTime)
            #print(timeNow - overrideStartTime)
            #print(overrideMaxMins)
            if timeNow - overrideStartTime > (overrideMaxSeconds):
                # turn on and start timer
                overrideThermo = 0
                overrideStartTime = 1
                GPIO.output(relayPin, GPIO.LOW)
                boilerOnOff = "Off"
        elif ( currentAverage > targetTemp and overrideThermo == 0 ):
            GPIO.output(relayPin, GPIO.LOW)
            #print("Turning boiler off")
            boilerOnOff = "Off"
        elif ( currentAverage < targetTemp ):
            GPIO.output(relayPin, GPIO.HIGH)
            #print("Turning boiler on")
            boilerOnOff = "On"
        await asyncio.sleep(20)


async def main():
    # main function to tie it all togetrher
    asyncio.create_task(getTempLoop())
    asyncio.create_task(boilerControl())
    asyncio.create_task(webServer())
    # asyncio.create_task(updateDisplay())
    
# run main() forever AND EVER AND EVER
loop = asyncio.new_event_loop()
# loop = asyncio.get_event_loop()  
loop.create_task(main())  # Create a task to run the main function
loop.run_forever()  # Run the event loop indefinitely
    

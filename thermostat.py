# Fork of esp32ermostat to full-fat Python on Linux (RPi, but could work with boards with compatible GPIO pins)

import time
import socket
import json
import requests
import asyncio
import RPi.GPIO as GPIO
import dht11


# set up socket for http server
thisSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
thisSocket.setblocking(False) # need to set non blocking so async works!
thisSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
thisSocket.bind(('', 8080))
thisSocket.listen(5)

# variables
forceOn = 0 # forceOn lets you turn on the boiler irrespective of temperature

# define a pin for relay control
GPIO.setmode(GPIO.BCM) # Use Broadcom pin numbering
GPIO.setwarnings(False)
relayPin = 18
GPIO.setup(relayPin, GPIO.OUT)
# to turn on: GPIO.output(relayPin, GPIO.HIGH)
# to turn off: GPIO.output(relayPin, GPIO.LOW)

# start with boiler off
GPIO.output(relayPin, GPIO.LOW)
boilerOnOff = "Off"

# added local dht11 rather than using remote sensor
dht11Pin = 5
localTempSensor = dht11.DHT11(pin=dht11Pin)
tempSensorType = "local"

# variable for overriding thermostat to manually turn on heat
overrideThermo = 0
overrideMaxMins = 20
overrideMaxSeconds = overrideMaxMins * 60 # will revert to thermo control after this many minutes
overrideStartTime = 1 # using epoch time, set to 1 so we have declared the variable
targetTemp = 19 # target temp for the boiler to achieve - set to something around what you'd usually have

# get the temp every 30 seconds and create a rolling average over 5 mins
# Store the last 10 readings (5 minutes at 30s intervals)
bufferSize = 10
tempBuffer = []
bufferIndex = 0
bufferFilled = False

sensorURL = "http://192.168.0.248"

useDisplay = 0

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
    if tempSensorType == "remote":
        try:
            response = requests.get(sensorURL)
            responseJSON = json.loads(response.text)
            theTempReading = responseJSON["temp"]
            returnMe = round(float(theTempReading),1)
        except:
            returnMe = targetTemp # if the sensor stops responding, use whatever the target was last time
    else:
        sensorReading = localTempSensor.read()
        if sensorReading.is_valid():
            theTemp = sensorReading.temperature
            returnMe = theTemp
        else:
            print("Error: %d" % sensorReading.error_code)
            returnMe = 0
    return returnMe

def dechunk(raw):
    out = ""
    while raw:
        pos = raw.find("\r\n")
        size = int(raw[:pos], 16)
        if size == 0:
            break
        start = pos + 2
        end = start + size
        out += raw[start:end]
        raw = raw[end+2:]
    return out


def parseRequest(theRequest):
    reqString = theRequest.decode() # convert bytes to a string
    theList = reqString.split()
    theArgument = theList[1]
    if theArgument != "/":
        theArgKey = theArgument.replace("/","").split("=")[0]
        theArgValue = theArgument.replace("/","").split("=")[1]
        returnMe = {theArgKey:theArgValue}
    else:
        returnMe = {"0":"0"}
    print(returnMe)
    return returnMe

# function to get target temp value from the request from the setup webpage
def get_target_value(theRequest):
    reqString = theRequest.decode() # convert bytes to a string
    key = "?target=" # set what we're looking for
    idx = reqString.find(key)
    if idx == -1:
        return None # returns None if called w/out the temp setting

    start = idx + len(key)
    end = reqString.find(" ", start)  # end of URL path
    if end == -1:
        end = len(reqString)

    return reqString[start:end]

def get_override_value(theRequest):
    reqString = theRequest.decode() # convert bytes to a string
    key = "?override=" # set what we're looking for
    idx = reqString.find(key)
    if idx == -1:
        return None # returns None if called w/out this parameter

    start = idx + len(key)
    end = reqString.find(" ", start)  # end of URL path
    if end == -1:
        end = len(reqString)

    return reqString[start:end]

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

# the 2 line display logic isn't needed for now but we'll keep some of it anyway
# async def updateDisplay():
#     # updates the status display every 25 seconds
#     global targetTemp
#     global boilerOnOff
#     #global lcd
#     while True:
#         line1 = "Target: " + str(targetTemp)
#         line2 = "Boiler is: " + boilerOnOff.upper()
#         # lcd.clear()
#         # lcd.move_to(0, 0)
#         # lcd.putstr(line1)
#         # lcd.move_to(0, 1)
#         # lcd.putstr(line2)
        
#         await asyncio.sleep(25)

async def getTempLoop():
    while True:
        addCurrentTempToBuffer()
        await asyncio.sleep(55)   # 55‑second interval
        
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

async def displayWebPage():
    # shows the control web page
    global targetTemp
    global html
    global boilerOnOff
    global thisSocket
    global overrideThermo
    global overrideMaxMins
    global overrideStartTime
    overrideThermoNow = 0
    #print("Webserver listening")
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

        # check for which key has been passed
        for pKey in theParameter:
            if pKey == "?target":
                targetTemp = float(theParameter[pKey])
            elif pKey == "?override":
                overrideThermoNow = int(theParameter[pKey])

        # if overrideThermoNow = 1, check if boiler on and time since it was set on manually 
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

        # set boiler status text
        response = (
        html.replace("{boilerStatus}", boilerOnOff)
            .replace("{targetTemp}", str(targetTemp))
            .replace("{roomTemp}", str(getRunningAverage()))
            )
        theHeader = "HTTP/1.1 200 OK\nContent-Type: text/html\nConnection: close\n\n"
        conn.send(theHeader.encode())
        conn.sendall(response.encode())
        conn.close()

        await asyncio.sleep(1)


async def main():
    # main function to tie it all togetrher
    asyncio.create_task(getTempLoop())
    asyncio.create_task(boilerControl())
    asyncio.create_task(displayWebPage())
    # asyncio.create_task(updateDisplay())
    
# run main() forever AND EVER AND EVER
loop = asyncio.new_event_loop()
# loop = asyncio.get_event_loop()  
loop.create_task(main())  # Create a task to run the main function
loop.run_forever()  # Run the event loop indefinitely
    

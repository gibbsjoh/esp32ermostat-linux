# testing webserver functions to make it better!

import time
import socket
import json
import requests
import asyncio

def web_page():
    file = open('index.html', 'r')
    html = file.read()
    file.close()
    return html

html = web_page()

def parseRequest(theRequest):
    returnMe = {}
    reqString = theRequest #.decode() # convert bytes to a string
    theList = reqString.split()[1]
    print(theList)
    theArguments = theList.replace("?","").replace("&","\n").replace("/","")
    print(theArguments)
    if theArguments != "":
        for thisArg in theArguments.splitlines():
            thisKey = thisArg.split("=")[0]
            thisValue = thisArg.split("=")[1]
            returnMe[thisKey] = thisValue
        if not "return" in returnMe:
            returnMe["return"] = "json"
    else:
        returnMe["return"] = "json"
    return returnMe


# webserver notes:
# if no arguments are passed in the URL, then return OK
# arguments structure:
# theurl.com:8080/?return -> "webpage" or "json"
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

async def main():
    # main function to tie it all together
    asyncio.create_task(webServer())
    # asyncio.create_task(updateDisplay())
    
# run main() forever AND EVER AND EVER
loop = asyncio.new_event_loop()
# loop = asyncio.get_event_loop()  
loop.create_task(main())  # Create a task to run the main function
loop.run_forever()  # Run the event loop indefinitely
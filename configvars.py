# configuration for variables eg sensor type, timings etc.
# variables
forceOn = 0 # forceOn lets you turn on the boiler irrespective of temperature

boilerOnOff = "Off"

tempSensorType = "local"

defaultTemp = 19

# variable for overriding thermostat to manually turn on heat
overrideThermo = 0
overrideMaxMins = 20
overrideMaxSeconds = overrideMaxMins * 60 # will revert to thermo control after this many minutes
overrideStartTime = 1 # using epoch time, set to 1 so we have declared the variable

bufferSize = 10

sensorURL = "http://192.168.0.248"

relayPin = 18
dht11Pin = 5
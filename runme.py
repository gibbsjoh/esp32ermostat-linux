# file to determine platform and call the appropriate file eg thermostat.py for RPi or thermostat-vf2 for VisionFive 2 (riscv64)

from machine import platform

thisArch = platform()

if thisArch == "riscv64":
    import raspberrypi.thermostat as thermostat-vf2
elif thisArch == "aarch64" or thisArch == "armv7l":
    import raspberrypi.thermostat as thermostat


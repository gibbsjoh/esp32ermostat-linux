# file to determine platform and call the appropriate file eg thermostat.py for RPi or thermostat-vf2 for VisionFive 2 (riscv64)

from platform import machine

thisArch = machine()

if thisArch == "riscv64":
    from visionfive2 import thermostat_vf2 as thermostat
elif thisArch == "aarch64" or thisArch == "armv7l":
    from raspberrypi import thermostat


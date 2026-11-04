import bluetooth

from neopixel import NeoPixel
from machine import Pin
np = NeoPixel(Pin(15),2)

NAME = b"ESPmia"

# look at the EXPECTED string - 
# that is the advertiser's payload without its last byte - the data:
# name field (length, type 0x09, name) + manufacturer field header
# (length 4, type 0xFF, company ID)
EXPECTED = bytes([len(NAME) + 1, 0x09]) + NAME + bytes([4, 0xFF, 0xFF, 0xFF])

ble = bluetooth.BLE()
ble.active(True)

last_state = None

def irq(event, data):
    global last_state
    if event == 5:  # scan result
        addr_type, addr, adv_type, rssi, adv_data = data
        adv = bytes(adv_data)
        
        # uncomment the line below at your own risk :)
        # print(addr_type, addr, adv_type, rssi, adv_data)
        
        # Look at how we have defined EXPECTED value - it is everything we sent
        if adv[:-1] == EXPECTED:
            state = adv[-1]
            if state != last_state:
                last_state = state
                if state == 1:
                    np[0] = [10,0,10]
                elif state == 0:
                    np[0] = [0,0,0]
                np.write()
                    

ble.irq(irq)

# Scan forever (0), listening 30 ms out of every 30 ms (all the time)
ble.gap_scan(0, 30_000, 30_000)


import time
while True:
    print("I am the best") # or whatever positive reinforcement you need :) 
    time.sleep(0.5)
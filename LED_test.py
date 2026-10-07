from machine import Pin
import time

led = Pin(26, Pin.OUT, Pin.PULL_UP)

try:
    while True:
        led.value(1)  # your code here
        time.sleep(0.1)
finally:
    led.value(0)  # always runs when the code stops
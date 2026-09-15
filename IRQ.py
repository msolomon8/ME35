from machine import Pin
from time import ticks_ms, ticks_diff
import neopixel

btn = Pin(34, Pin.IN, Pin.PULL_UP) 
DEBOUNCE_MS = 200
last_press = 0

def button_handler(pin):
    global last_press
    now = ticks_ms()
    if ticks_diff(now, last_press) > DEBOUNCE_MS:
        if (pin.value() == 0):
            last_press = now
            print("Button pressed!")
            lights = neopixel.NeoPixel(Pin(15),2)
            lights[0] = (20,0,20)
            lights[1] = (0,0,0)
            lights.write()


btn.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
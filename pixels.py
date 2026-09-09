import neopixel #importing the library
import time
from machine import Pin # another way of importing a library
lights = neopixel.NeoPixel(Pin(15),2) # 0 is the Pin for neopixel and 4 is the number of light
lights[0] = (20,0,20) # set the color of 0th light to purple 
lights[1] = (0,0,0)
lights.write()

from machine import ADC, Pin
import time
lightsensor = ADC(Pin(33))
print(lightsensor.read_u16())

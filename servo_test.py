from machine import Pin, PWM
import time
s = PWM(Pin(4), freq=50)
s.duty_u16(int(1500 * 65535 / 20000))   # hold at 90 degrees
time.sleep(30)
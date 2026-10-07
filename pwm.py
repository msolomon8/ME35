from machine import Pin, PWM
import time
pwm = PWM(Pin(4), freq=50, duty_u16=0)

#0 degrees
pwm.duty_ns(1500*1000)
time.sleep(1)

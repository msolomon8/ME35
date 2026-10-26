# check_tail.py - find the safe angles for the tail servo (pin 4)
from machine import Pin, PWM
import time

servo = PWM(Pin(4), freq=50)

def tail(angle):
    """Move the tail. 0-180 degrees; 90 should be roughly upright."""
    angle = max(0, min(180, angle))
    us = 500 + angle * 2000 / 180          # 0.5 ms .. 2.5 ms pulse
    servo.duty_ns(int(us * 1000))

tail(90)
print("Tail at 90. Now type tail(<angle>) in the Shell below,")
print("e.g. tail(70), tail(60)... and tail(110), tail(120)...")
print("Stop just before the tail hits anything on each side.")
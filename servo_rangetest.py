# servo_sweep.py -- sweep each servo from 0 to 180 degrees so you can watch the arm (MicroPython, ESP32)
#
# One servo at a time; the other one gets no pulses (limp).
# Pauses at 0, 45, 90, 135, 180 and prints the angle. Ctrl+C stops and goes limp.

from machine import Pin, PWM
import time

SERVO_PINS = [4, 5]   # servo 1 (shoulder), servo 2 (elbow)
MIN_US = 500
MAX_US = 2500
STEP_DELAY = 0.03     # seconds per 1-degree step
HOLD = 3              # seconds to pause at each 45-degree mark

servos = [PWM(Pin(p), freq=50, duty_u16=0) for p in SERVO_PINS]


def write(pwm, deg):
    us = MIN_US + deg * (MAX_US - MIN_US) / 180
    pwm.duty_u16(int(us * 65535 / 20000))


try:
    for i, pwm in enumerate(servos):
        print("\n=== Servo {} (pin {}) ===".format(i + 1, SERVO_PINS[i]))
        for deg in range(0, 181):
            write(pwm, deg)
            if deg % 45 == 0:
                print("servo {} at {} deg".format(i + 1, deg))
                time.sleep(HOLD)
            else:
                time.sleep(STEP_DELAY)
        pwm.duty_u16(0)   # go limp before testing the next servo
finally:
    for pwm in servos:
        pwm.duty_u16(0)
    print("\nservos off")
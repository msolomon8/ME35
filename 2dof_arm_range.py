# range_demo.py -- show the arm's full range of motion, including how far down it reaches
# (MicroPython, ESP32)
#
# Moves both servos together through a set of waypoints (servo angles), 1 degree at a time,
# and prints where the tip is. Ctrl+C stops and goes limp.
#
# Calibration used (from your sweep):
#   Servo 1: 0 = right, 90 = up, 180 = left              -> theta1 = servo1
#   Servo 2: 90 = straight, 180 = tilts left (CCW)       -> theta2 = servo2 - 90

from machine import Pin, PWM
import math
import time

L1 = 87.52   # mm
L2 = 80      # mm

SERVO1_PIN = 4
SERVO2_PIN = 5
MIN_US = 500
MAX_US = 2500

STEP_DELAY = 0.03   # seconds per 1-degree step
HOLD = 2            # seconds to pause at each waypoint

# (servo1, servo2) waypoints
WAYPOINTS = [
    (90, 90),    # straight up
    (0, 90),     # sweep right, fully extended (tip at 167.52, 0)
    (0, 0),      # bend elbow down on the right (tip at 87.52, -80) -- lowest point, right
    (0, 90),     # straighten
    (90, 90),    # back to straight up
    (180, 90),   # sweep left, fully extended (tip at -167.52, 0)
    (180, 180),  # bend elbow down on the left (tip at -87.52, -80) -- lowest point, left
    (180, 90),   # straighten
    (90, 90),    # home
]


def make_servo(pin):
    return PWM(Pin(pin), freq=50, duty_u16=0)


def write(pwm, deg):
    deg = max(0, min(180, deg))
    us = MIN_US + deg * (MAX_US - MIN_US) / 180
    pwm.duty_u16(int(us * 65535 / 20000))


def tip(s1, s2):
    """Forward kinematics: servo angles -> tip (x, y) in mm."""
    t1 = math.radians(s1)
    t2 = math.radians(s2 - 90)
    x = L1 * math.cos(t1) + L2 * math.cos(t1 + t2)
    y = L1 * math.sin(t1) + L2 * math.sin(t1 + t2)
    return x, y


servo1 = make_servo(SERVO1_PIN)
servo2 = make_servo(SERVO2_PIN)

try:
    s1, s2 = WAYPOINTS[0]
    write(servo1, s1)
    write(servo2, s2)
    time.sleep(HOLD)

    for t1, t2 in WAYPOINTS[1:]:
        steps = max(abs(t1 - s1), abs(t2 - s2))
        for i in range(1, steps + 1):          # both servos move together
            write(servo1, s1 + (t1 - s1) * i / steps)
            write(servo2, s2 + (t2 - s2) * i / steps)
            time.sleep(STEP_DELAY)
        s1, s2 = t1, t2
        x, y = tip(s1, s2)
        print("servo1 = {:>3}, servo2 = {:>3} -> tip at ({:.1f}, {:.1f})".format(s1, s2, x, y))
        time.sleep(HOLD)
finally:
    servo1.duty_u16(0)
    servo2.duty_u16(0)
    print("servos off")
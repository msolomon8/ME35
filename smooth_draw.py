# arm_ik.py -- light painting with a two-link arm (MicroPython, ESP32)
#
# The LED is the "pen": it is on only while drawing, and the tip moves at a
# constant speed so every part of the line gets the same amount of light.
# Self-contained: no other files needed.

from machine import Pin, PWM
import math
import time

# ---- Arm setup ------------------------------------------------------------
L1 = 87.52   # mm, first link
L2 = 80      # mm, second link

points = [(-21.00,121.00),(-16.83,131.00),(-12.28,131.00),(-6.21,130.30),(0.62,131.00),(8.21,132.00),(15.79,132.00),(23.38,131.70),(30.21,130.00),(33.24,127.00),(35.52,122.00),(37.03,119.20),(38.55,119.50),(39.31,125.00),(39.69,133.00),(40.45,140.00),(43.10,142.00),(46.14,143.50),(48.79,146.00),(47.66,147.50),(41.59,145.00),(33.24,142.50),(23.38,140.00),(12.00,139.00),(0.62,139.00),(-10.76,140.00),(-20.62,141.00),(-27.45,145.00),(-30.48,144.00),(-33.52,140.00),(-34.66,133.00),(-33.52,126.00),(-30.86,124.00),(-27.83,127.00),(-25.93,135.00),(-27.45,145.00),(-29.72,149.50),(-44.90,141.00),(-54.00,134.50),(-34.66,133.00)]

ELBOW_UP = True

# ---- Drawing speed --------------------------------------------------------
DRAW_SPEED = 30     # mm/s with LED on. Higher = shorter exposure, but corners round off
TRAVEL_SPEED = 80   # mm/s with LED off, moving between strokes
STEP_MM = 0.5       # path is split into steps this long; smaller = smoother
SETTLE = 0.3        # s to let the arm settle before the LED turns on
DOT_TIME = 0.3      # s the LED stays on for a single-point stroke
COUNTDOWN = 3       # s countdown before drawing, to open the shutter

# ---- Pins -----------------------------------------------------------------
SERVO1_PIN = 4    # shoulder servo
SERVO2_PIN = 5    # elbow servo
LED_PIN = 26      # the light-painting LED

# ---- LED brightness (PWM) ---------------------------------------------------
LED_BRIGHTNESS = 10   # percent, 0-100. Lower it if the line looks thick or blown out
LED_FREQ = 5000       # Hz. Keep this high: at low frequencies the moving LED
                      # flickers and the photo shows a dashed line

# ---- Servo calibration (from the 0-180 sweep) ------------------------------
MIN_US = 500      # pulse for 0 degrees
MAX_US = 2400     # pulse for 180 degrees
OFFSET1 = 0       # servo 1: 0 = right, 90 = up
DIR1 = 1
OFFSET2 = 90      # servo 2: 90 = straight, 180 = tilts left (CCW)
DIR2 = 1
# ---------------------------------------------------------------------------

def hypot(x, y):
    """Distance formula (MicroPython's math module often has no hypot)."""
    return math.sqrt(x * x + y * y)


R_MIN = math.sqrt(L1**2 + L2**2) + 0.01   # ~118.6 mm: elbow at its 90 deg limit
R_MAX = L1 + L2                           # 167.52 mm: arm straight


class Servo(object):
    """Standard hobby servo on one signal pin (50 Hz)."""

    PERIOD_US = 20000   # 50 Hz

    def __init__(self, signal, min_us=MIN_US, max_us=MAX_US):
        self.min_us = min_us
        self.max_us = max_us
        self.pwm = PWM(Pin(signal), freq=50, duty_u16=0)

    def angle(self, degrees):
        degrees = max(0, min(180, degrees))
        us = self.min_us + degrees * (self.max_us - self.min_us) / 180
        self.pwm.duty_u16(int(us * 65535 / self.PERIOD_US))

    def off(self):
        self.pwm.duty_u16(0)  # stop sending pulses: servo goes limp


def ik(x, y, l1, l2, elbow_up=True):
    """Return (theta1, theta2) in degrees, or None if (x, y) is out of reach."""
    c2 = (x**2 + y**2 - l1**2 - l2**2) / (2 * l1 * l2)
    if 1 < c2 < 1.000001:        # floating-point rounding at full reach
        c2 = 1.0
    elif -1.000001 < c2 < -1:
        c2 = -1.0
    if c2 < -1 or c2 > 1:
        return None
    s2 = math.sqrt(1 - c2**2)
    if not elbow_up:
        s2 = -s2
    theta2 = math.atan2(s2, c2)
    theta1 = math.atan2(y, x) - math.atan2(l2 * s2, l1 + l2 * c2)
    return math.degrees(theta1), math.degrees(theta2)


def to_servo(theta, offset, direction):
    """Convert a joint angle to a servo angle, or None if outside 0-180."""
    a = round(offset + direction * theta, 2)
    if a < 0 or a > 180:
        return None
    return a


def reachable(x, y):
    """Pull a point onto the reachable ring, keeping its direction from the shoulder."""
    r = hypot(x, y)
    if r == 0:
        return 0, R_MIN
    rc = min(max(r, R_MIN), R_MAX)
    return x * rc / r, y * rc / r


def move_to(x, y):
    x, y = reachable(x, y)
    r = ik(x, y, L1, L2, ELBOW_UP)
    if r is None:
        return
    a1 = to_servo(r[0], OFFSET1, DIR1)
    a2 = to_servo(r[1], OFFSET2, DIR2)
    if a1 is not None and a2 is not None:
        servo1.angle(a1)
        servo2.angle(a2)


def walk(p0, p1, speed):
    """Move the tip in a straight line from p0 to p1 at a constant speed (mm/s)."""
    dist = hypot(p1[0] - p0[0], p1[1] - p0[1])
    n = max(1, int(dist / STEP_MM))
    delay = dist / n / speed
    for i in range(1, n + 1):
        move_to(p0[0] + (p1[0] - p0[0]) * i / n, p0[1] + (p1[1] - p0[1]) * i / n)
        time.sleep(delay)


def split_strokes(pts):
    strokes, cur = [], []
    for p in pts:
        if p is None:
            if cur:
                strokes.append(cur)
            cur = []
        else:
            cur.append(p)
    if cur:
        strokes.append(cur)
    return strokes


def path_length(stroke):
    return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(stroke, stroke[1:]))


strokes = split_strokes(points)

# Estimate how long the exposure needs to be
draw_t = sum(path_length(s) / DRAW_SPEED if len(s) > 1 else DOT_TIME for s in strokes)
travel_t = sum(hypot(b[0][0] - a[-1][0], b[0][1] - a[-1][1]) / TRAVEL_SPEED + SETTLE
               for a, b in zip(strokes, strokes[1:]))
print("{} stroke(s). Drawing takes about {:.1f} s -- set the exposure a little longer."
      .format(len(strokes), draw_t + travel_t))

servo1 = Servo(SERVO1_PIN)
servo2 = Servo(SERVO2_PIN)
led = PWM(Pin(LED_PIN), freq=LED_FREQ, duty_u16=0)


def led_on():
    led.duty_u16(int(65535 * LED_BRIGHTNESS / 100))


def led_off():
    led.duty_u16(0)


led_off()

try:
    cur = strokes[0][0]
    move_to(*cur)
    time.sleep(1)                     # arm reaches the start with the LED off
    for i in range(COUNTDOWN, 0, -1):
        print("starting in", i)
        time.sleep(1)

    for si, stroke in enumerate(strokes):
        if si > 0:                     # pen up: move to the next stroke in the dark
            walk(cur, stroke[0], TRAVEL_SPEED)
            cur = stroke[0]
            time.sleep(SETTLE)
        led_on()                   # pen down
        if len(stroke) == 1:
            time.sleep(DOT_TIME)
        for p in stroke[1:]:
            walk(cur, p, DRAW_SPEED)
            cur = p
        led_off()                   # pen up
    print("done")
finally:
    led_off()
    servo1.off()
    servo2.off()
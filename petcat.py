# petcat.py - Mochi the treat-dispensing desk cat (ME35 midterm)
#
#   Pet her head (push it forward)      -> treat + tail sways 45-135
#   Double-tap the desk                 -> study mode on/off: tail creeps from
#                                          90 to 180 as a timer, buzzes, treat
#   No pets for a while                 -> she falls asleep; a pet wakes her
#
# Needs pet_lis3dh.py (accelerometer driver) saved on the board too.
# BEFORE POWER-ON: line a catch slot up, and leave the head upright.
 
from machine import Pin, PWM, ADC, I2C
import math
import time
 
# =====================================================================
# SETTINGS - all pins and tuning numbers
# =====================================================================
# tail servo
TAIL_PIN = 4
TAIL_MIN = 45               # furthest safe angle one way
TAIL_MAX = 180              # furthest safe angle the other way
TAIL_UP = 90                # straight up
SWAY_LO = 45                # pet sway goes between these two angles
SWAY_HI = 135
SWAY_HZ = 1.0               # sways per second
SWAY_MS = 3000              # how long she sways after a treat
TAIL_RELAX_MS = 600         # stop powering the servo once it's been still this
                            # long (stops the whirring). If the tail sags,
                            # set this to 0 to keep it powered.
 
# treat catch (DC motor + encoder)
MOTOR_PIN = 13
ENC_A_PIN = 32
HALF_TURN = 970            # encoder counts slot-to-slot
DISPENSE_FAST = 40          # % power for most of the turn
DISPENSE_SLOW = 25          # % power for the last part
DISPENSE_SLOW_ZONE = 250
DISPENSE_LEAD = 15          # cut power this many counts early (it coasts ~15)
DISPENSE_STALL_MS = 400
DISPENSE_TIMEOUT_MS = 3000
 
# head (Grove Thumb Joystick)
JOY_PET_PIN = 26            # forward/back axis (push forward = pet)
JOY_PUSH_DELTA = 8000       # moved this far from upright = pushed (full ~16800)
JOY_RELEASE_DELTA = 3000    # back within this = upright again
PET_MIN_MS = 60             # must stay forward this long (ignores blips)
 
# accelerometer (Grove LIS3DHTR)
I2C_SDA = 21
I2C_SCL = 22
ACCEL_ADDR = 0x19
TAP_THRESHOLD = 30          # lower = more sensitive (your hard taps hit ~110)
TAP_TIME_LIMIT = 30         # a tap must be shorter than this (x 2.5 ms = 75 ms)
DOUBLE_TAP_MIN_MS = 120     # 2nd tap must come at least this long after the 1st
DOUBLE_TAP_MAX_MS = 700     # ...and no later than this
TAP_QUIET_MS = 1500         # ignore taps this long after petting/moving
 
# timers (in seconds)
STUDY_EVERY_S = 10          # study-mode treat every... (30 * 60 = 30 minutes)
SLEEP_AFTER_S = 60          # no pets this long -> sleep (5 * 60 = 5 minutes)
STUDY_EVERY_MS = STUDY_EVERY_S * 1000
SLEEP_AFTER_MS = SLEEP_AFTER_S * 1000
 
# =====================================================================
# PWM OUTPUTS - always made together, motor first, both at 50 Hz.
# If they're made separately, an old run can leave the motor and tail on
# the same PWM channel, so moving one moves the other.
# shutdown() turns both fully off so stopping the code can't twitch them.
# =====================================================================
_pwm = None
 
def outputs():
    """Returns (motor_pwm, tail_pwm), creating both if needed."""
    global _pwm
    if _pwm is None:
        motor = PWM(Pin(MOTOR_PIN), freq=50)
        motor.duty_u16(0)
        tail = PWM(Pin(TAIL_PIN), freq=50)
        tail.duty_u16(0)
        _pwm = (motor, tail)
    return _pwm
 
def shutdown():
    """Motor off, servo off, both pins released and held low."""
    global _pwm
    if _pwm is not None:
        for p in _pwm:
            try:
                p.duty_u16(0)
                p.deinit()
            except Exception:
                pass
        _pwm = None
    Pin(MOTOR_PIN, Pin.OUT, value=0)
    Pin(TAIL_PIN, Pin.OUT, value=0)
 
 
# =====================================================================
# TAIL - one servo. Set a mood, then call update() every loop.
# When the tail has been still for TAIL_RELAX_MS it stops sending pulses,
# so the servo relaxes instead of whirring.
# =====================================================================
class Tail:
    def __init__(self):
        self.pwm = outputs()[1]
        self.angle = TAIL_UP
        self.written = TAIL_UP
        self.mode = "up"
        self.t0 = time.ticks_ms()
        self.last = self.t0
        self.dur = 0
        self.progress = 0.0
        self.relaxed = False
        self.last_write = self.t0
        self._pulse(TAIL_UP)
 
    def _pulse(self, a):
        a = max(TAIL_MIN, min(TAIL_MAX, a))       # never leave the safe range
        self.pwm.duty_ns(int((500 + a * 2000 / 180) * 1000))   # 0.5-2.5 ms
        self.written = a
        self.relaxed = False
        self.last_write = time.ticks_ms()
 
    def relax(self):
        self.pwm.duty_ns(0)                        # no pulses = servo goes quiet
        self.relaxed = True
 
    def _start(self, mode, dur_ms=0):
        self.mode = mode
        self.dur = dur_ms
        self.t0 = time.ticks_ms()
 
    # ---- moods ----
    def up(self):               self._start("up")          # stand straight up
    def sway(self, ms=SWAY_MS): self._start("sway", ms)    # happy: 45 <-> 135
    def droop(self, ms=3000):   self._start("droop", ms)   # sad: lowers, holds
    def sleep(self):            self._start("sleep")       # lowers slowly, rests
    def buzz(self, ms=1000):    self._start("buzz", ms)    # fast shiver at the top
 
    def study(self, progress):                             # 0..1 = 90 -> 180
        if self.mode != "study":
            self._start("study")
        self.progress = max(0.0, min(1.0, progress))
 
    def busy(self):
        return self.mode in ("sway", "droop", "buzz")
 
    def still(self):
        """True when the tail isn't moving (so desk taps are real taps)."""
        return not self.busy() and abs(self._target(0) - self.angle) < 2
 
    def _target(self, t):
        if self.mode == "sway":
            mid = (SWAY_LO + SWAY_HI) / 2
            return mid + (SWAY_HI - SWAY_LO) / 2 * math.sin(2 * math.pi * SWAY_HZ * t)
        if self.mode == "droop" or self.mode == "sleep":
            return TAIL_MIN
        if self.mode == "buzz":
            return TAIL_MAX - 5 + 5 * math.sin(2 * math.pi * 8 * t)
        if self.mode == "study":
            return TAIL_UP + (TAIL_MAX - TAIL_UP) * self.progress
        return TAIL_UP
 
    def update(self):
        now = time.ticks_ms()
        t = time.ticks_diff(now, self.t0) / 1000
        dt = time.ticks_diff(now, self.last) / 1000
        self.last = now
        if self.dur and t * 1000 >= self.dur:      # timed mood finished
            self.up()
            t = 0
        rate = {"sway": 400, "buzz": 600, "droop": 60,
                "sleep": 20, "study": 30}.get(self.mode, 90)   # deg/s
        target = self._target(t)
        step = rate * dt
        self.angle += max(-step, min(step, target - self.angle))
        if abs(self.angle - self.written) >= 0.5:
            self._pulse(self.angle)                # moving: keep sending pulses
        elif (TAIL_RELAX_MS and not self.relaxed and not self.busy()
              and time.ticks_diff(now, self.last_write) > TAIL_RELAX_MS):
            self.relax()                           # still: let the servo rest
 
 
# =====================================================================
# DISPENSER - DC motor + encoder. One half turn = one treat.
# Position is counted from power-on, so small errors never add up.
# =====================================================================
class Dispenser:
    def __init__(self):
        self.motor = outputs()[0]
        self.motor.duty_u16(0)
        self.enc = Pin(ENC_A_PIN, Pin.IN, Pin.PULL_UP)
        self.edges = 0          # encoder pulses since power-on
        self.slot = 0           # half turns since power-on
 
    def speed(self, pct):
        self.motor.duty_u16(int(max(0, min(100, pct)) * 65535 / 100))
 
    def stop(self):
        self.motor.duty_u16(0)
 
    def count_for(self, ms):
        """Keep counting pulses for `ms` (e.g. while it coasts)."""
        read = self.enc.value
        last = read()
        end = time.ticks_add(time.ticks_ms(), ms)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            v = read()
            if v != last:
                last = v
                self.edges += 1
 
    def dispense(self):
        """Turn to the next slot. Returns "ok", "jammed" or "timeout"."""
        self.slot += 1
        target = self.slot * HALF_TURN
        slow_at = target - DISPENSE_SLOW_ZONE
        read = self.enc.value
        last = read()
        n = self.edges
        n_check = n
        loops = 0
        t0 = time.ticks_ms()
        last_move = t0
        slowed = False
        result = "ok"
        try:
            self.speed(DISPENSE_FAST)
            while n < target - DISPENSE_LEAD:
                v = read()                         # poll the encoder
                loops += 1
                if v != last:
                    last = v
                    n += 1
                    if not slowed and n >= slow_at:
                        self.speed(DISPENSE_SLOW)
                        slowed = True
                if loops & 255 == 0:               # check timers now and then
                    now = time.ticks_ms()
                    if n != n_check:
                        n_check = n
                        last_move = now
                    elif time.ticks_diff(now, last_move) > DISPENSE_STALL_MS:
                        result = "jammed"
                        break
                    if time.ticks_diff(now, t0) > DISPENSE_TIMEOUT_MS:
                        result = "timeout"
                        break
        finally:
            self.stop()                            # motor ALWAYS stops
        self.edges = n
        self.count_for(300)                        # count the coast
        return result
 
    def error(self):
        return self.edges - self.slot * HALF_TURN
 
 
# =====================================================================
# HEAD - sits on the joystick. update() returns "pet" or None.
# The head stays forward until you push it back up; a pet counts the moment
# it goes forward, and the next pet needs it upright again first.
# =====================================================================
class Head:
    def __init__(self):
        self.adc = ADC(Pin(JOY_PET_PIN))
        self.adc.atten(ADC.ATTN_11DB)              # full 0-3.3 V range
        self.rest = self._average()                # calibrate: head upright
        self.state = "rest"                        # "rest" or "forward"
        self.t_start = 0
        self.sent = False
        self.last_activity = time.ticks_ms()
 
    def _average(self, n=40):
        total = 0
        for _ in range(n):
            total += self.adc.read_u16()
            time.sleep_ms(5)
        return total // n
 
    def offset(self):
        """How far the head is from upright (bigger = pushed further)."""
        return abs(self.adc.read_u16() - self.rest)
 
    def update(self):
        now = time.ticks_ms()
        off = self.offset()
        if self.state == "rest":
            if off > JOY_PUSH_DELTA:
                self.state, self.t_start, self.sent = "forward", now, False
            return None
        self.last_activity = now
        if off < JOY_RELEASE_DELTA:
            self.state = "rest"                    # upright again
        elif not self.sent and time.ticks_diff(now, self.t_start) >= PET_MIN_MS:
            self.sent = True
            return "pet"
        return None
 
    def ms_since_activity(self):
        return time.ticks_diff(time.ticks_ms(), self.last_activity)
 
 
# =====================================================================
# DOUBLE TAP - the chip detects single taps in hardware (pet_lis3dh);
# two of them DOUBLE_TAP_MIN_MS..MAX_MS apart count as a double tap.
# =====================================================================
class DoubleTap:
    def __init__(self, acc):
        from pet_lis3dh import TAP_SINGLE
        self.acc = acc
        self.SINGLE = TAP_SINGLE
        acc.set_tap(TAP_SINGLE, threshold=TAP_THRESHOLD, time_limit=TAP_TIME_LIMIT)
        acc.tapped()                       # clear any old tap
        self.first = None                  # time of the first tap
        self.count = 0                     # single taps seen (for testing)
 
    def update(self):
        """Call every loop. Returns True once per double tap."""
        now = time.ticks_ms()
        if self.first is not None and time.ticks_diff(now, self.first) > DOUBLE_TAP_MAX_MS:
            self.first = None              # too slow - forget the first tap
        if self.acc.tapped() != self.SINGLE:
            return False
        self.count += 1
        if self.first is None:
            self.first = now               # this is tap 1
            return False
        if time.ticks_diff(now, self.first) < DOUBLE_TAP_MIN_MS:
            return False                   # same tap still vibrating
        self.first = None
        return True                        # tap 2 - double tap!
 
 
# =====================================================================
# SOUND - optional (BUZZER_PIN = None means silent)
# =====================================================================
BUZZER_PIN = None
_buzz = None
 
def beep(*notes):
    """beep((freq, ms), (freq, ms), ...)  - short, blocking"""
    global _buzz
    if BUZZER_PIN is None:
        return
    if _buzz is None:
        _buzz = PWM(Pin(BUZZER_PIN), freq=1000, duty_u16=0)
    for f, ms in notes:
        _buzz.freq(f)
        _buzz.duty_u16(20000)
        time.sleep_ms(ms)
        _buzz.duty_u16(0)
 
 
# =====================================================================
# MAIN PROGRAM - modes: "awake", "asleep", "study"
# =====================================================================
def run():
    tail = Tail()
    disp = Dispenser()
    head = Head()                      # calibrates - don't touch the head!
 
    taps = None
    try:
        from pet_lis3dh import LIS3DH
        i2c = I2C(0, sda=Pin(I2C_SDA), scl=Pin(I2C_SCL), freq=400000)
        taps = DoubleTap(LIS3DH(i2c, address=ACCEL_ADDR))
    except Exception as e:
        print("Accelerometer not working, study mode off:", e)
 
    mode = "awake"
    last_interaction = time.ticks_ms()
    last_motion = time.ticks_ms()      # when Mochi herself last moved a lot
    study_start = 0
    treat_pending = False              # study timer done: buzz, then treat
    print("Mochi is awake!")
    beep((880, 80), (1175, 120))
 
    def give_treat():
        nonlocal last_motion
        result = disp.dispense()
        last_motion = time.ticks_ms()
        if result == "ok":
            print("Treat!")
            tail.sway()
            beep((1047, 80), (1319, 80), (1568, 120))
        else:
            print("Dispenser", result, "- check the catch")
            tail.droop(1500)
 
    try:
        while True:
            now = time.ticks_ms()
            event = head.update()
 
            # ---- double tap? (ignored right after petting or Mochi moving) ----
            tap = False
            if taps:
                double = taps.update()  # always check, so old taps get cleared
                quiet = (head.state == "rest"
                         and head.ms_since_activity() > TAP_QUIET_MS
                         and time.ticks_diff(now, last_motion) > TAP_QUIET_MS
                         and tail.still())
                tap = double and quiet
 
            # ---- head: pet ----
            if event == "pet":
                last_interaction = now
                if mode == "asleep":
                    mode = "awake"
                    print("*yawn* ...I'm up!")
                    tail.up()
                    beep((600, 60), (1200, 120))
                elif mode == "study":
                    print("Study time! Treat comes on the timer.")
                else:
                    give_treat()
 
            # ---- double tap: study mode on/off ----
            if tap:
                last_interaction = now
                if mode == "study":
                    mode = "awake"
                    treat_pending = False
                    print("Study mode OFF")
                    tail.up()
                    beep((1175, 80), (880, 120))
                else:
                    mode = "study"
                    study_start = now
                    print("Study mode ON - treat every", STUDY_EVERY_S, "s")
                    tail.study(0)
                    beep((880, 80), (1175, 120))
 
            # ---- timers ----
            if mode == "study":
                if treat_pending and not tail.busy():      # buzz finished
                    treat_pending = False
                    give_treat()
                    study_start = time.ticks_ms()          # next countdown
                elif (not treat_pending and not tail.busy()
                      and time.ticks_diff(now, study_start) >= STUDY_EVERY_MS):
                    print("Study break - here's a treat!")
                    tail.buzz()
                    beep((1568, 100), (1568, 100), (1568, 100))
                    treat_pending = True
            elif mode == "awake":
                if time.ticks_diff(now, last_interaction) > SLEEP_AFTER_MS:
                    mode = "asleep"
                    print("zzz... (pet me to wake me)")
                    beep((523, 200), (392, 400))
 
            # ---- tail pose for the current mode (after any sway/droop ends) ----
            if not tail.busy():
                if mode == "asleep" and tail.mode != "sleep":
                    tail.sleep()
                elif mode == "study" and not treat_pending:
                    tail.study(time.ticks_diff(now, study_start) / STUDY_EVERY_MS)
                elif mode == "awake" and tail.mode != "up":
                    tail.up()
            if tail.busy():
                last_motion = now          # tail moving shakes the body - not a tap
 
            tail.update()
            time.sleep_ms(20)
    finally:
        shutdown()                     # motor + servo fully off when stopped
 
 
if __name__ == "__main__":
    run()
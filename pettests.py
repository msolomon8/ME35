# tests.py - test each part of Mochi on its own. Run this file, then type
# one of the commands below in Thonny's Shell. Ctrl+C stops a test.
import time
from machine import I2C, Pin
import petcat as mochi

def _run_tail(tail, seconds, label):
    print(label)
    end = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        tail.update()
        time.sleep_ms(20)

def tail():
    """Plays every tail move (~30 s), then relaxes the servo."""
    t = mochi.Tail()
    try:
        t.up();    _run_tail(t, 2, "up (then relaxes - should go quiet)")
        t.sway();  _run_tail(t, 4, "pet sway 45-135")
        t.droop(); _run_tail(t, 5, "droop (used if the catch jams)")
        t.sleep(); _run_tail(t, 6, "sleeping")
        t.up();    _run_tail(t, 2, "wake up")
        print("study countdown 90 -> 180 (sped up to 8 s)")
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < 8000:
            t.study(time.ticks_diff(time.ticks_ms(), start) / 8000)
            t.update()
            time.sleep_ms(20)
        t.buzz();  _run_tail(t, 1.5, "buzz - treat time!")
        t.up();    _run_tail(t, 3, "done")
    finally:
        mochi.shutdown()           # servo + motor fully off

def head():
    """Leave the head upright while it starts. Prints PET."""
    h = mochi.Head()
    print("Resting value:", h.rest)
    n = 0
    while True:
        if h.update():
            print(">>> PET")
        n += 1
        if n % 25 == 0:
            print("offset %5d | %s" % (h.offset(), h.state))
        time.sleep_ms(20)

def dispenser(n=4):
    """Line a slot up first. Drops n treats."""
    d = mochi.Dispenser()
    try:
        for i in range(n):
            r = d.dispense()
            print("treat", i + 1, ":", r, "| error", d.error())
            if r != "ok":
                break
            time.sleep_ms(1500)
    finally:
        mochi.shutdown()

def _accel():
    from pet_lis3dh import LIS3DH
    i2c = I2C(0, sda=Pin(mochi.I2C_SDA), scl=Pin(mochi.I2C_SCL), freq=400000)
    return LIS3DH(i2c, address=mochi.ACCEL_ADDR)

def peaks(seconds=10):
    """Tap the desk: shows how hard each tap hits + a suggested threshold."""
    acc = _accel()
    end = time.ticks_add(time.ticks_ms(), seconds * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        peak = 0
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < 500:
            peak = max(peak, abs(acc.magnitude() - 1.0))
        if peak > 0.05:
            print("peak %.2f g  -> threshold about %d" % (peak, int(peak * 0.6 * 64)))

def taps(threshold=None):
    """Prints each single tap and each double tap."""
    if threshold:
        mochi.TAP_THRESHOLD = threshold
    d = mochi.DoubleTap(_accel())
    print("Threshold", mochi.TAP_THRESHOLD, "- tap the desk")
    seen = 0
    while True:
        if d.update():
            print(">>> DOUBLE TAP")
        elif d.count != seen:
            print("tap")
        seen = d.count
        time.sleep_ms(10)

# ---- calibrate counts per half turn (fixes slot drift) ----
_cal = None

def spin_turns(k=10):
    """Line a slot up first. Spins ~k half turns and stops a bit short."""
    global _cal
    _cal = mochi.Dispenser()
    goal = k * mochi.HALF_TURN - 150
    try:
        _cal.speed(35)
        read = _cal.enc.value
        last = read()
        t0 = time.ticks_ms()
        while _cal.edges < goal and time.ticks_diff(time.ticks_ms(), t0) < 20000:
            v = read()
            if v != last:
                last = v
                _cal.edges += 1
    finally:
        _cal.stop()
    _cal.count_for(400)
    if _cal.edges < 50:
        print("Motor barely moved - is it powered? Try spin_turns() again after Stop.")
    print("Stopped at", _cal.edges, "- now jog() until a slot lines up exactly")

def jog(pct=30, ms=80):
    """Small nudge forward. If it doesn't move, try jog(35)."""
    before = _cal.edges
    try:
        _cal.speed(pct)
        _cal.count_for(ms)
    finally:
        _cal.stop()
    _cal.count_for(300)
    print("moved", _cal.edges - before, "-> total", _cal.edges)

def result(k=10):
    print("HALF_TURN = %d   (put this in mochi.py)" % round(_cal.edges / k))
    
def tapdebug(threshold=10, seconds=15):
    """Shows what the tap detector sees. Tap the desk next to Mochi."""
    from pet_lis3dh import TAP_SINGLE
    acc = _accel()
    # Part 1: how big is a tap once gravity is filtered out?
    acc._write8(0x21, 0x0C)        # high-pass filter on the readings too
    acc._read8(0x26)
    print("Part 1: tap the desk a few times (5 s)...")
    best = 0
    end = time.ticks_add(time.ticks_ms(), 5000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        x, y, z = acc.acceleration()
        best = max(best, abs(x), abs(y), abs(z))
    print("Biggest tap: %.2f g = %d threshold units" % (best, best / 0.0156))
    # Part 2: does the chip's own tap detector fire? (single taps, easy settings)
    acc.set_tap(TAP_SINGLE, threshold=threshold, time_limit=30)
    acc.tapped()
    print("Part 2: single taps now, threshold", threshold, "...")
    end = time.ticks_add(time.ticks_ms(), seconds * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        src = acc._read8(0x39)               # CLICK_SRC register
        if src & 0x40:
            print("TAP detected! CLICK_SRC = 0x%02X" % src)
        time.sleep_ms(10)
    print("done")

print("""Tests:  tail()   head()   dispenser()   peaks()   taps()
Calibrate the catch:  spin_turns()  then jog() ... then result()""")
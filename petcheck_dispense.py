# check_dispense.py v4 - polling encoder, safe stop, jam detection
from machine import Pin, PWM
import time

HALF_TURN = 1000

motor = PWM(Pin(13), freq=1000)
motor.duty_u16(0)
enc_a = Pin(32, Pin.IN, Pin.PULL_UP)

edges = 0
slot = 0

def speed(pct):
    pct = max(0, min(100, pct))
    motor.duty_u16(int(pct * 65535 / 100))

def stop():
    motor.duty_u16(0)

def _count_for(ms):
    """Keep counting pulses after the motor stops (coasting)."""
    global edges
    read = enc_a.value
    last = read()
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        v = read()
        if v != last:
            last = v
            edges += 1

def dispense(fast=40, slow=25, slow_zone=250, lead=40,
             timeout_ms=3000, stall_ms=400):
    global edges, slot
    slot += 1
    target = slot * HALF_TURN
    read = enc_a.value
    last = read()
    n = edges
    n_at_check = n
    loops = 0
    t0 = time.ticks_ms()
    last_move = t0
    slowed = False
    result = "ok"
    try:
        speed(fast)
        while n < target - lead:
            v = read()
            loops += 1
            if v != last:
                last = v
                n += 1
                if not slowed and n >= target - slow_zone:
                    speed(slow)
                    slowed = True
            if loops & 255 == 0:                 # every 256 reads, check timers
                now = time.ticks_ms()
                if n != n_at_check:
                    n_at_check = n
                    last_move = now
                elif time.ticks_diff(now, last_move) > stall_ms:
                    result = "JAMMED (no pulses for %d ms)" % stall_ms
                    break
                if time.ticks_diff(now, t0) > timeout_ms:
                    result = "TIMEOUT"
                    break
    finally:
        stop()                                   # motor ALWAYS stops
    edges = n
    off = n
    elapsed = max(1, time.ticks_diff(time.ticks_ms(), t0))
    _count_for(400)
    print("slot %d: %s | target %d | off at %d | coasted to %d | error %+d | %d checks/s"
          % (slot, result, target, off, edges, edges - target, loops * 1000 // elapsed))
    return result == "ok"

def test(n=6, pause_ms=1500, **kw):
    try:
        for i in range(n):
            if not dispense(**kw):
                break
            time.sleep_ms(pause_ms)
    finally:
        stop()

def jog(pct=30, ms=60):
    try:
        speed(pct); time.sleep_ms(ms)
    finally:
        stop()

stop()
print("Line up a slot, then type: test()")
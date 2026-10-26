# check_motor.py - DC motor (pin 13) + encoder (pins 32, 39)
from machine import Pin, PWM
import time

motor = PWM(Pin(13), freq=1000)
motor.duty_u16(0)

enc_a = Pin(32, Pin.IN, Pin.PULL_UP)
enc_b = Pin(39, Pin.IN)          # pins 34-39 have no internal pull-up
count = 0

def _on_edge(p):
    global count
    # A changed: compare with B to tell direction
    if enc_a.value() == enc_b.value():
        count += 1
    else:
        count -= 1

enc_a.irq(_on_edge, Pin.IRQ_RISING | Pin.IRQ_FALLING)

def speed(pct):
    """0-100 % power, one direction."""
    pct = max(0, min(100, pct))
    motor.duty_u16(int(pct * 65535 / 100))

def stop():
    speed(0)

def hand_test(seconds=15):
    """Motor off. Turn the catch by hand from one slot to the next."""
    global count
    stop(); count = 0
    print("Turn the catch by hand exactly half a turn (slot to slot)...")
    end = time.ticks_add(time.ticks_ms(), seconds * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        print("count =", count, " A =", enc_a.value(), " B =", enc_b.value())
        time.sleep_ms(300)

def spin(pct=40, ms=400):
    """Short test run: does the motor move, and which way does count go?"""
    global count
    count = 0
    speed(pct); time.sleep_ms(ms); stop()
    time.sleep_ms(300)
    print("power", pct, "% for", ms, "ms -> count =", count)

def run_counts(target, pct=40, timeout_ms=3000):
    """Run until the encoder moves `target` counts, then stop."""
    global count
    count = 0
    t0 = time.ticks_ms()
    speed(pct)
    while abs(count) < target:
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            print("Timeout! Jammed or too little power?")
            break
    stop()
    at_stop = abs(count)
    time.sleep_ms(400)
    print("target", target, "| stopped at", at_stop, "| coasted to", abs(count))

print("Ready. In the Shell type: hand_test(), spin(), run_counts(N)")
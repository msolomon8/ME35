# ================== MOTOR TEST (Cytron Robo ESP32, MicroPython) ==================
# Hold the robot off the table (or prop it up) for tests 1-4.
# Press button 34 to move to the next test. Watch the printout and the wheels.
 
import time
from machine import Pin, PWM
 
# --- same pins as main.py ---
def _pwm(p): return PWM(Pin(p), freq=1000, duty_u16=0)
M1A, M1B, M2A, M2B = _pwm(12), _pwm(13), _pwm(14), _pwm(27)
 
LEFT_SIGN  = 1    # set to -1 if the left wheel spins backwards on "forward"
RIGHT_SIGN = 1    # set to -1 if the right wheel spins backwards on "forward"
 
def _set(pa, pb, speed):
    speed = max(-100, min(100, speed))
    duty = int(abs(speed) * 655.35)
    if speed >= 0: pa.duty_u16(duty); pb.duty_u16(0)
    else:          pa.duty_u16(0);    pb.duty_u16(duty)
 
def drive(left, right):
    _set(M1A, M1B, LEFT_SIGN * left)
    _set(M2A, M2B, RIGHT_SIGN * right)
 
def stop(): drive(0, 0)
 
btn = Pin(34, Pin.IN)
def next_test(msg):
    stop()
    print("\n>>", msg, "  (press button 34)")
    idle = btn.value()
    while btn.value() == idle: time.sleep_ms(10)
    while btn.value() != idle: time.sleep_ms(10)
 
def run(label, l, r, ms=1500):
    print("  ", label, "-> drive(%d, %d)" % (l, r))
    drive(l, r); time.sleep_ms(ms); stop(); time.sleep_ms(400)
 
try:
    # 1) Each motor alone: checks wiring and direction
    next_test("TEST 1: LEFT motor only")
    run("left forward", 50, 0)
    run("left backward", -50, 0)
 
    next_test("TEST 2: RIGHT motor only")
    run("right forward", 0, 50)
    run("right backward", 0, -50)
    print("  Wrong wheel moved? Swap the M1/M2 connectors.")
    print("  'Forward' spun backward? Set LEFT_SIGN/RIGHT_SIGN = -1 (also in main.py).")
 
    # 2) Both together
    next_test("TEST 3: both forward, then turns")
    run("forward", 50, 50)
    run("turn right (left wheel faster)", 50, 20)
    run("turn left (right wheel faster)", 20, 50)
    run("backward", -50, -50)
 
    # 3) Find the minimum speed that actually moves the wheels
    next_test("TEST 4: speed ramp - note when wheels START moving")
    for s in range(0, 101, 10):
        print("   speed", s); drive(s, s); time.sleep_ms(600)
    stop()
    print("  Keep BASE in main.py well above the start speed.")
 
    # 4) On the floor: drives straight? Spin timing?
    next_test("TEST 5 (ON THE FLOOR): drive straight 2 s - does it veer?")
    run("straight", 40, 40, 2000)
    print("  Veers? Lower the faster side, e.g. drive(40, 37).")
 
    next_test("TEST 6 (ON THE FLOOR): spin in place - tune SPIN_MS for 360")
    for ms in (1200, 1600, 2000):
        print("   spin", ms, "ms"); drive(50, -50); time.sleep_ms(ms); stop(); time.sleep(1.5)
    print("  Put the closest value into SPIN_MS in main.py.")
 
    print("\nDone!")
finally:
    stop()
 

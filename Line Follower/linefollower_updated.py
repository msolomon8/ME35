# linefollower.py - Cytron Robo ESP32, MicroPython
# LINE FOLLOWING ONLY: edge sensor = P steering (auto-tuned KP). No color sensing yet.
#   import linefollower; linefollower.run(debug=True)
#   linefollower.tune(kp=12, base=25, auto=True)   # change + save settings
#   linefollower.recalibrate()                      # forget saved calibration
#   linefollower.reset()                            # back to default speed / KP
# Buttons: 34 = record / GO / STOP, 35 (on CYAN) = next starting KP
# Lights: ORANGE 2 s = press 34 to recalibrate | WHITE edge on white | YELLOW edge on black
#         PURPLE robot centered (edge on half/half) | CYAN ready | red blink = sensor error
import time, json, os, neopixel
from machine import Pin, PWM, SoftI2C, I2C

# ---------------- CONFIG ----------------
DEFAULTS    = {'kp': 15, 'base': 28, 'auto': True}   # base = forward speed %, lower = slower
KP_STEPS    = [10, 12, 15, 18, 22, 26, 30, 35, 40]
KP_MIN, KP_MAX = 10, 40   # auto-tune can't make steering too weak for curves anymore
MAX_TURN    = 22       # steering limit (was 15 - too weak for sharper curves)
CURVE_SLOW  = 0.25     # slow down up to 25% while turning hard (was 50% -> too little power, got stuck)
TURN_SMOOTH = 0.5      # 0..1: how fast steering follows the sensor (lower = smoother, 1 = no smoothing)
INNER_MIN   = 0        # inner wheel never goes below this (0 = can stop, never stalls in weak reverse)
TRIM        = 0        # + if it drifts left on a straight with no steering, - if right
LEFT_SIGN, RIGHT_SIGN, STEER_SIGN = -1, 1, -1   # STEER -1 = edge sensor on the RIGHT edge of the tape
LOOP_MS     = 20       # control period (sensors only update every ~40 ms anyway)

# ---------------- STORAGE ----------------
def _load(fn, d):
    try:
        with open(fn) as f: return json.load(f)
    except Exception: return d
def _save(fn, d):
    with open(fn, 'w') as f: json.dump(d, f)
SETTINGS = 'lf_settings2.json'     # new file name -> starts from the new defaults above
S = _load(SETTINGS, {}); [S.setdefault(k, v) for k, v in DEFAULTS.items()]
def tune(**kw): S.update(kw); _save(SETTINGS, S); print("saved", S)
def reset(): tune(**DEFAULTS)      # back to the default speed / KP
def recalibrate():
    try: os.remove('edge_calib.json')
    except OSError: pass

# ---------------- EDGE SENSOR (TCS34725 @0x29 or VEML6040 @0x10) ----------------
class Sensor:
    def __init__(s, i2c):
        s.i2c, found = i2c, i2c.scan()
        if 0x29 in found:
            s.a = 0x29
            for r, v in ((0, 1), (0, 3), (1, 0xFC), (0x0F, 1)):
                i2c.writeto_mem(0x29, 0x80 | r, bytes([v])); time.sleep_ms(3)
        elif 0x10 in found:
            s.a = 0x10; i2c.writeto_mem(0x10, 0, b'\x00\x00')
        else: raise RuntimeError("sensor missing " + str(found))
    def read(s):                                       # (r, g, b, brightness)
        if s.a == 0x29:
            d = s.i2c.readfrom_mem(0x29, 0xB4, 8)
            return (d[2] | d[3] << 8, d[4] | d[5] << 8, d[6] | d[7] << 8, d[0] | d[1] << 8)
        return tuple(int.from_bytes(s.i2c.readfrom_mem(0x10, r, 2), 'little') for r in (8, 9, 10, 11))
    def avg(s, n=20):
        t = [0] * 4
        for _ in range(n):
            t = [a + b for a, b in zip(t, s.read())]; time.sleep_ms(45)
        return [v / n for v in t]

def _edge_bus():                   # EDGE sensor (straddles the tape edge) = Grove 21/22, hardware I2C
    b = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
    if b.scan(): return b
    raise RuntimeError("edge sensor missing on Grove 21/22")

def _front_bus():                  # FRONT sensor (on the tape, for colors later) = Grove 33/32 - not used yet
    for scl, sda in ((32, 33), (33, 32)):
        b = SoftI2C(scl=Pin(scl), sda=Pin(sda), freq=100000)
        if b.scan(): return b
    raise RuntimeError("front sensor missing on Grove 33/32")

# ---------------- OUTPUTS ----------------
_m = [PWM(Pin(p), freq=1000, duty_u16=0) for p in (14, 27, 12, 13)]   # LEFT = M2 (14,27), RIGHT = M1 (12,13)
def _motor(a, b, v):
    v = max(-100, min(100, v)); d = int(abs(v) * 655.35)
    a.duty_u16(d if v > 0 else 0); b.duty_u16(d if v < 0 else 0)
def drive(l, r): _motor(_m[0], _m[1], LEFT_SIGN * (l + TRIM)); _motor(_m[2], _m[3], RIGHT_SIGN * (r - TRIM))
def stop(): drive(-TRIM, TRIM)

np, buzz = neopixel.NeoPixel(Pin(15), 2), PWM(Pin(23), freq=1000, duty_u16=0)
def leds(*c): np[0] = np[1] = c; np.write()
def tone(f, ms): buzz.freq(f); buzz.duty_u16(20000); time.sleep_ms(ms); buzz.duty_u16(0)
def beeps(n):
    for _ in range(n): tone(1800, 70); time.sleep_ms(110)

b34, b35 = Pin(34, Pin.IN), Pin(35, Pin.IN)
I34, I35 = b34.value(), b35.value()
def p34(): return b34.value() != I34
def p35(): return b35.value() != I35
def _release(f):
    while f(): time.sleep_ms(10)
    time.sleep_ms(30)
def wait34(msg, c):
    print(">>", msg); leds(*c)
    while not p34(): time.sleep_ms(10)
    _release(p34); leds(0, 0, 0); tone(1500, 80)

# ---------------- CALIBRATION (edge sensor: white / black / half-and-half) ----------------
def _calibrate(e):
    wait34("EDGE on WHITE", (20, 20, 20)); ew = e.avg()
    wait34("EDGE on BLACK", (30, 30, 0));  eb = e.avg()
    wait34("Robot CENTERED: EDGE on half/half", (30, 0, 30)); eh = e.avg()
    cal = {'ew': ew[3], 'eb': eb[3], 'eh': eh[3]}
    print("edge white %d  half %d  black %d" % (ew[3], eh[3], eb[3]))
    if not eb[3] < eh[3] < ew[3]: print("WARNING: edge half/half should be between black and white")
    _save('edge_calib.json', cal); beeps(2); return cal

# ---------------- RUN ----------------
def run(debug=False):
    stop()
    try: edge = Sensor(_edge_bus())
    except RuntimeError as err:
        print(err)
        while True: leds(80, 0, 0); time.sleep_ms(150); leds(0, 0, 0); time.sleep_ms(150)

    cal = _load('edge_calib.json', None)
    if cal and 'eh' not in cal: cal = None             # old-format file -> recalibrate
    if cal:                                            # 2 s window to recalibrate
        leds(40, 15, 0); t = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t) < 2000 and not p34(): time.sleep_ms(10)
        if p34(): _release(p34); cal = None
        leds(0, 0, 0)
    if not cal: cal = _calibrate(edge)
    W, B = max(cal['ew'], cal['eb']), min(cal['ew'], cal['eb'])   # white is always the brighter one
    print("CALIBRATION  white=%d  half=%d  black=%d" % (W, cal['eh'], B))

    # ---- EDGE: 0 = black, 1 = white ----
    # target = where half/half sits between black and white (from calibration, 0.5 if it looks wrong)
    target = (cal['eh'] - B) / (W - B) if W - B >= 20 else 0.5
    if not 0.15 < target < 0.85:
        print("half/half reading looks off -> using target 0.5"); target = 0.5
    print("target = %.2f" % target)
    rng = [B, W]                                       # live black/white levels, updated while driving

    def norm(v):
        lo, hi = rng
        # stretch the range toward new extremes (partly, so one glare spike can't wreck it)
        if v < lo: rng[0] = lo = lo + 0.3 * (v - lo)
        if v > hi: rng[1] = hi = hi + 0.3 * (v - hi)
        if hi - lo < 20: return target                 # can't tell black from white yet -> go straight
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))

    def error(n):
        # EQUAL steering both ways: full white = +1 and full black = -1, even if the
        # half/half target isn't exactly in the middle. (Before, if target was e.g. 0.7,
        # white could only give +0.3 -> weak turns in one direction.)
        if n >= target: return (n - target) / (1 - target)
        return (n - target) / target

    while True:
        # ---- READY (cyan): 35 = next KP, 34 = GO ----
        print("READY kp=%s base=%s auto=%s" % (S['kp'], S['base'], S['auto'])); leds(0, 30, 30)
        while not p34():
            if p35():
                _release(p35)
                i = next((j for j, k in enumerate(KP_STEPS) if k > S['kp']), 0)
                tune(kp=KP_STEPS[i]); beeps(i + 1); leds(0, 30, 30)
            time.sleep_ms(10)
        _release(p34); leds(0, 0, 0); beeps(3)

        kp, base, dbg_t = float(S['kp']), S['base'], 0
        sm_turn = 0.0                                  # smoothed steering
        win_t, win_e, win_n, flips, last_s = time.ticks_ms(), 0, 0, 0, 0
        while True:
            t0 = now = time.ticks_ms()
            if p34():                                  # STOP
                stop(); _release(p34); tone(800, 150)
                if S['auto']: tune(kp=round(kp, 1))
                break

            # steering from the edge sensor
            raw = edge.read()[3]
            err = error(norm(raw))                     # -1 (all black) .. 0 (on edge) .. +1 (all white)
            turn = max(-MAX_TURN, min(MAX_TURN, STEER_SIGN * kp * err))
            if S['auto']:                              # auto-tune KP every 1 s
                win_e += abs(err); win_n += 1
                s = (err > 0.15) - (err < -0.15)
                if s and last_s and s != last_s: flips += 1
                last_s = s or last_s
                dt = time.ticks_diff(now, win_t)
                if dt > 1000:
                    osc, me = flips * 1000 / dt, win_e / max(win_n, 1)
                    if osc > 2.5: kp *= 0.92               # wobbling -> softer
                    elif me > 0.3 and osc < 1: kp *= 1.05  # drifting -> stronger
                    kp = max(KP_MIN, min(KP_MAX, kp))
                    win_t, win_e, win_n, flips = now, 0, 0, 0
            sm_turn += TURN_SMOOTH * (turn - sm_turn)  # ease into / out of turns instead of jerking
            turn = sm_turn
            b = base * (1 - CURVE_SLOW * abs(turn) / MAX_TURN)   # a bit slower in curves
            drive(max(INNER_MIN, b + turn), max(INNER_MIN, b - turn))

            if debug and time.ticks_diff(now, dbg_t) > 150:
                dbg_t = now
                print("raw=%5d black=%5d white=%5d err=%+.2f kp=%.1f turn=%+5.1f speed=%.0f"
                      % (raw, rng[0], rng[1], err, kp, turn, b))
            time.sleep_ms(max(0, LOOP_MS - time.ticks_diff(time.ticks_ms(), t0)))
        stop(); leds(0, 0, 0)

if __name__ == "__main__":
    run(debug=True)

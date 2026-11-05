# Line_follower.py - Cytron Robo ESP32, MicroPython
# EDGE sensor (Grove 21/22) does EVERYTHING: P+D steering
# AND color patches (it rides the tape edge, so it passes over every patch).
# The front sensor (Grove 33/32) ALSO looks for colors (USE_FRONT = True).
# Kp and Kd auto-tune while driving (AUTO_TUNE = True below) - no shell commands needed.
#   Optional shell commands:
#   import Line_follower as lf; lf.run(debug=True)
#   lf.tune(kp=12, base=25)                         # change + save settings
#   lf.tune(colors=False)                           # colors off / on
#   lf.recalibrate()                                # redo calibration next run
#   lf.reset()                                      # back to default speed / KP / KD
#   lf.colortest()                                  # live: what the sensors see
# Buttons: 34 = record / GO / STOP, 35 (on CYAN) = next starting KP
# Calibration: press 34, SLIDE the sensor along while it ticks, long beep = done.
#   WHITE edge on white | YELLOW edge on black | PURPLE robot centered (edge half on tape edge)
#   RED / GREEN / BLUE edge sensor half on that patch, like when driving
#   ORANGE 2 s at start = press 34 to recalibrate | CYAN ready | red blink = sensor error
import time, json, os, neopixel, network, espnow
from machine import Pin, PWM, SoftI2C, I2C

# ---------------- CONFIG ----------------
DEFAULTS    = {'kp': 15, 'kd': 0.1, 'base': 24, 'auto': True, 'colors': True}   # >>> KD: kd starts at 0.3
AUTO_TUNE   = True     # >>> auto-tune Kp AND Kd while driving (False = keep them fixed)
KP_STEPS    = [10, 12, 15, 18, 22, 26, 30, 35, 40]
KP_MIN, KP_MAX = 10, 40   # auto-tune can't make steering too weak for curves anymore
KD_MIN, KD_MAX = 0.05, 1.0   # >>> KD: auto-tune keeps kd in this range
MAX_TURN    = 22       # steering limit (was 15 - too weak for sharper curves)
CURVE_SLOW  = 0.35     # slow down up to 25% while turning hard (was 50% -> too little power, got stuck)
TURN_SMOOTH = 0.7      # 0..1: how fast steering follows the sensor (lower = smoother, 1 = no smoothing)
INNER_MIN   = 0        # inner wheel never goes below this (0 = can stop, never stalls in weak reverse)
TRIM        = 0        # + if it drifts left on a straight with no steering, - if right
LEFT_SIGN, RIGHT_SIGN, STEER_SIGN = -1, 1, -1   # STEER -1 = edge sensor on the RIGHT edge of the tape
LOOP_MS     = 20       # control period (sensors only update every ~40 ms anyway)
# --- colors (edge sensor) ---
COLOR_FRAC  = 0.5      # patch counts at 50% of how colorful it looked during calibration
NOISE_X     = 2.0      # ...and at least 2x the black/white/half noise level
COLOR_HITS  = 2        # this many NEW readings in a row of the SAME color = a patch
BRIGHT_TOL  = 0.3      # a color reading's brightness must be within 30% of that patch's calibrated range
ONCE_EACH   = True     # each color can trigger once per lap (there is 1 red, 1 green, 1 blue patch)
USE_FRONT   = True     # front sensor (Grove 33/32) ALSO looks for colors
FRONT_FILE  = 'front_cal_v3.json'
PASS_MS     = 400      # after the action, drive straight this long to get off the patch
COOLDOWN_MS = 1500     # ignore colors this long after an action (one patch = one action)
SERVO_PIN   = 4
USE_COMMS   = True    # True once STATION_MAC is filled in (extra credit)
STATION_MAC = b' \x9b\xa9t\x81\\'

# ---------------- STORAGE ----------------
def _load(fn, d):
    try:
        with open(fn) as f: return json.load(f)
    except Exception: return d
def _save(fn, d):
    with open(fn, 'w') as f: json.dump(d, f)
SETTINGS = 'lf_settings3.json'     # >>> new file -> fresh start from DEFAULTS (kp 15, kd 0.3)
S = _load(SETTINGS, {}); [S.setdefault(k, v) for k, v in DEFAULTS.items()]
S['auto'] = AUTO_TUNE              # >>> always use the AUTO_TUNE setting from the code
def tune(**kw): S.update(kw); _save(SETTINGS, S); print("saved", S)
def reset(): tune(**DEFAULTS)      # back to the default speed / KP / KD
def recalibrate():
    for fn in (CAL_FILE, FRONT_FILE):
        try: os.remove(fn)
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

def _front_bus():                  # FRONT sensor (on the tape, for colors) = Grove 33/32
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

# ---------------- CALIBRATION: EDGE sensor does steering AND colors ----------------
COLORS = ('RED', 'GREEN', 'BLUE')
CAL_FILE = 'edge_cal_v2.json'

def _collect(e, msg, c, n=30):
    """Press 34, then SLIDE the robot/sensor along that surface while it ticks. Long beep = done."""
    wait34(msg + " -> press 34, slide until the long beep", c)
    out = []
    for i in range(n):
        out.append(list(e.read()))
        if i % 4 == 0: buzz.freq(2500); buzz.duty_u16(8000)
        time.sleep_ms(35); buzz.duty_u16(0); time.sleep_ms(40)
    tone(1200, 300); return out

def _med(xs):
    xs = sorted(xs); return xs[len(xs) // 2]

def _calibrate(e):
    cal = {'WHITE': _collect(e, "EDGE on WHITE", (20, 20, 20)),
           'BLACK': _collect(e, "EDGE on BLACK tape - slide along it", (30, 30, 0)),
           'HALF':  _collect(e, "Robot CENTERED: EDGE half on tape edge - slide along the line", (30, 0, 30))}
    for n, c in zip(COLORS, ((40, 0, 0), (0, 40, 0), (0, 0, 40))):
        cal[n] = _collect(e, "EDGE half on the " + n + " patch (like when driving) - slide along it", c)
    w, h, b = (_med([v[3] for v in cal[k]]) for k in ('WHITE', 'HALF', 'BLACK'))
    print("edge white %d  half %d  black %d" % (w, h, b))
    if not b < h < w: print("WARNING: half should be between black and white - redo with the sensor on the tape edge")
    _save(CAL_FILE, cal); beeps(2); return cal

def _calibrate_front(f):
    fc = {'WHITE': _collect(f, "FRONT on WHITE", (8, 8, 8)),
          'BLACK': _collect(f, "FRONT on BLACK tape - slide along it", (15, 15, 0))}
    for n, c in zip(COLORS, ((40, 0, 0), (0, 40, 0), (0, 0, 40))):
        fc[n] = _collect(f, "FRONT on the " + n + " patch - slide around on it", c)
    _save(FRONT_FILE, fc); beeps(2); return fc

def _make_color_check(cal, label):
    # white-balance each channel; colorfulness = distance from the black<->white line
    # (black, white and every gray mix = 0). A reading counts as a color only if:
    #   1) it is colorful enough (bar set from YOUR calibration data),
    #   2) it points in that color's direction, and
    #   3) its BRIGHTNESS is in the range that patch had during calibration (kills most false reds).
    plain_keys = [k for k in ('WHITE', 'BLACK', 'HALF') if k in cal]
    avg = lambda k: [sum(v[i] for v in cal[k]) / len(cal[k]) for i in range(4)]
    W = [max(x, 1) for x in avg('WHITE')[:3]]
    def wb(v): return (v[0] / W[0], v[1] / W[1], v[2] / W[2])
    kb = wb(avg('BLACK')); seg = [1 - x for x in kb]; seg2 = sum(x * x for x in seg) or 1e-9
    def dev(v):
        h = wb(v)
        t = max(0.0, min(1.0, sum((a - b) * s for a, b, s in zip(h, kb, seg)) / seg2))
        return [a - (b + t * s) for a, b, s in zip(h, kb, seg)]
    def col(v): return sum(x * x for x in dev(v))
    def unit(d):
        m = sum(x * x for x in d) ** 0.5 or 1e-9
        return [x / m for x in d]
    ref = {n: unit(dev(avg(n))) for n in COLORS}
    pl = sorted(col(v) for k in plain_keys for v in cal[k])
    noise = pl[int(len(pl) * 0.9)]
    patch = {n: _med([col(v) for v in cal[n]]) for n in COLORS}
    need = {n: max(NOISE_X * noise, COLOR_FRAC * patch[n], 0.001) for n in COLORS}
    blo = {n: min(v[3] for v in cal[n]) * (1 - BRIGHT_TOL) for n in COLORS}
    bhi = {n: max(v[3] for v in cal[n]) * (1 + BRIGHT_TOL) for n in COLORS}
    def check(v):                  # -> (ratio, color). ratio > 1 = on a patch
        d = dev(v); u = unit(d)
        n = max(COLORS, key=lambda k: sum(a * b for a, b in zip(u, ref[k])))
        if not blo[n] <= v[3] <= bhi[n]: return 0.0, n          # wrong brightness for that patch
        if sum(a * b for a, b in zip(u, ref[n])) < 0.8: return 0.0, n   # not really that color's direction
        return sum(x * x for x in d) / need[n], n
    print("%s noise=%.4f" % (label, noise))
    for n in COLORS:
        hit = sum(1 for v in cal[n] if check(v)[0] > 1 and check(v)[1] == n)
        print("%s %-5s bar=%.4f bright %d..%d -> %d/%d calibration samples detected" % (
            label, n, need[n], blo[n], bhi[n], hit, len(cal[n])))
    fa = sum(1 for k in plain_keys for v in cal[k] if check(v)[0] > 1)
    print("%s false alarms on black/white samples: %d/%d" % (label, fa, len(pl)))
    return check

def colortest():
    """Live printout of what BOTH sensors see."""
    cal, fc = _load(CAL_FILE, None), _load(FRONT_FILE, None)
    if not cal: print("calibrate first: run()"); return
    e = Sensor(_edge_bus()); ce = _make_color_check(cal, "EDGE ")
    f = Sensor(_front_bus()) if (USE_FRONT and fc) else None
    cf = _make_color_check(fc, "FRONT") if f else None
    while True:
        r, n = ce(e.read()); line = "EDGE %-5s %5.2f" % (n if r > 1 else "-", r)
        if f: r, n = cf(f.read()); line += "   FRONT %-5s %5.2f" % (n if r > 1 else "-", r)
        print(line + "   (needs > 1)"); time.sleep_ms(200)

# ---------------- ACTIONS ----------------
servo = PWM(Pin(SERVO_PIN), freq=50, duty_u16=0)
def red_action():                  # servo waves back and forth
    leds(60, 0, 0)
    for a in (30, 150, 30, 150, 30, 150, 90):
        servo.duty_u16(int((500 + a / 180 * 2000) / 20000 * 65535)); time.sleep_ms(350)
    servo.duty_u16(0); leds(0, 0, 0)
def green_action():                # Twinkle Twinkle
    leds(0, 60, 0)
    for f, ms in ((523, 300), (523, 300), (784, 300), (784, 300), (880, 300), (880, 300), (784, 600)):
        tone(f, ms); time.sleep_ms(40)
    leds(0, 0, 0)
def blue_action():                 # NeoPixel chase + flash
    for i in range(10):
        np[0], np[1] = ((0, 0, 90), (0, 0, 0)) if i % 2 else ((0, 0, 0), (0, 0, 90)); np.write(); time.sleep_ms(120)
    for _ in range(3): leds(0, 0, 90); time.sleep_ms(100); leds(0, 0, 0); time.sleep_ms(100)
ACTIONS = {'RED': red_action, 'GREEN': green_action, 'BLUE': blue_action}

_en, _id = None, 0
def signal(color):                 # tell the station (extra credit)
    global _en, _id
    if not USE_COMMS: return
    if not _en:
        w = network.WLAN(network.STA_IF)
        w.active(True)
        w.disconnect()             # not on any Wi-Fi -> same channel as the station
        _en = espnow.ESPNow(); _en.active(True); _en.add_peer(STATION_MAC)
    _id += 1; want = ("ACK,%d" % _id).encode()
    for _ in range(3):
        try: _en.send(STATION_MAC, "%s,%d" % (color, _id))
        except OSError: pass
        t = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t) < 300:
            if _en.recv(50)[1] == want:
                tone(2000, 60); print("station ACK for", color); return True
    print("no ACK from station for", color)
    return False

# ---------------- RUN ----------------
def run(debug=False):
    stop()
    try: edge = Sensor(_edge_bus())
    except RuntimeError as err:
        print(err)
        while True: leds(80, 0, 0); time.sleep_ms(150); leds(0, 0, 0); time.sleep_ms(150)
    front = None
    if USE_FRONT:
        try: front = Sensor(_front_bus()); print("FRONT sensor found (Grove 33/32)")
        except RuntimeError as err: print("front sensor not found - edge only", err)
    cal, fc = _load(CAL_FILE, None), _load(FRONT_FILE, None)
    if cal:                                            # 2 s window to recalibrate
        leds(40, 15, 0); t = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t) < 2000 and not p34(): time.sleep_ms(10)
        if p34(): _release(p34); cal = fc = None
        leds(0, 0, 0)
    if not cal: cal = _calibrate(edge)
    if front and not fc: fc = _calibrate_front(front)
    check = _make_color_check(cal, "EDGE ")
    fcheck = _make_color_check(fc, "FRONT") if front else None
    W, B, H = (_med([v[3] for v in cal[k]]) for k in ('WHITE', 'BLACK', 'HALF'))
    W, B = max(W, B), min(W, B)
    print("CALIBRATION  white=%d  half=%d  black=%d" % (W, H, B))
    cal = {'eh': H}

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
        # half/half target isn't exactly in the middle.
        if n >= target: return (n - target) / (1 - target)
        return (n - target) / target

    while True:
        # ---- READY (cyan): 35 = next KP, 34 = GO ----
        print("READY kp=%s kd=%s base=%s auto=%s colors=%s" % (S['kp'], S['kd'], S['base'], S['auto'], S['colors']))   # >>> KD: shows kd
        leds(0, 30, 30)
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
        cool, ratio = time.ticks_ms(), 0.0
        st = {'edge': [0, None, None], 'front': [0, None, None]}   # per sensor: hits, color, last reading
        done = set()                                   # colors already handled this lap
        kd = float(S['kd'])                            # >>> KD: derivative gain (auto-tuned below)
        last_err, last_t, last_raw, d_err = 0.0, time.ticks_ms(), None, 0.0   # >>> KD: memory for D
        while True:
            t0 = now = time.ticks_ms()
            if p34():                                  # STOP
                stop(); _release(p34); tone(800, 150)
                if S['auto']: tune(kp=round(kp, 1), kd=round(kd, 2))   # >>> KD: save tuned kd too
                break

            # ---- color check on BOTH sensors (each needs COLOR_HITS new readings of the same color) ----
            ev = edge.read(); raw = ev[3]
            found = None
            if S['colors'] and time.ticks_diff(now, cool) > 0:
                for key, sensor, chk, v in (('edge', edge, check, ev),
                                            ('front', front, fcheck, front.read() if front else None)):
                    if not chk or v == st[key][2]: continue           # no sensor / not a new reading
                    st[key][2] = v
                    r, n = chk(v)
                    if r > 1 and not (ONCE_EACH and n in done):
                        st[key][0] = st[key][0] + 1 if st[key][1] == n else 1
                        st[key][1] = n
                        if debug: print("  %s sees %s (ratio %.1f, %d in a row)" % (key, n, r, st[key][0]))
                        if st[key][0] >= COLOR_HITS: found = n
                    else:
                        st[key][0], st[key][1] = 0, None
            if found:
                stop(); print("COLOR", found, "- stopping")
                signal(found)                          # tell the station before the action
                ACTIONS[found]()
                done.add(found)
                if len(done) == len(COLORS): done = set()   # all three seen -> next lap starts fresh
                drive(base, base); time.sleep_ms(PASS_MS)   # roll off the patch
                cool = time.ticks_add(time.ticks_ms(), COOLDOWN_MS)
                st = {'edge': [0, None, None], 'front': [0, None, None]}; sm_turn = 0.0
                d_err, last_raw, last_t = 0.0, None, time.ticks_ms()   # >>> KD: fresh start after the stop
                continue
            if st['edge'][0]:                          # edge sensor might be on a patch -> don't steer on it
                sm_turn += TURN_SMOOTH * (0 - sm_turn)
                drive(base, base); time.sleep_ms(LOOP_MS); continue

            # ---- steering from the edge sensor ----
            err = error(norm(raw))                     # -1 (all black) .. 0 (on edge) .. +1 (all white)
            # >>> KD: how fast the error is changing - only on a NEW sensor reading,
            # because the sensor updates every ~40 ms but the loop runs every 20 ms
            if raw != last_raw:
                dt = time.ticks_diff(now, last_t) / 1000          # seconds since last new reading
                if dt > 0:
                    d_err = (err - last_err) / dt
                last_err, last_t, last_raw = err, now, raw
            turn = max(-MAX_TURN, min(MAX_TURN, STEER_SIGN * (kp * err + kd * d_err)))   # >>> KD: P + D
            if S['auto']:                              # auto-tune KP (and KD) every 1 s
                win_e += abs(err); win_n += 1
                s = (err > 0.15) - (err < -0.15)
                if s and last_s and s != last_s: flips += 1
                last_s = s or last_s
                dt = time.ticks_diff(now, win_t)
                if dt > 1000:
                    osc, me = flips * 1000 / dt, win_e / max(win_n, 1)
                    if osc > 2.5:
                        kp *= 0.92                     # wobbling -> softer (same as before)
                        kd *= 0.9                      # >>> KD: fast wobble -> D may be over-reacting, ease it off
                    elif osc >= 1 and me > 0.3:
                        kd *= 1.1                      # >>> KD: slow big swings -> more damping
                    elif me > 0.3 and osc < 1:
                        kp *= 1.05                     # drifting -> stronger (same as before)
                    kp = max(KP_MIN, min(KP_MAX, kp))
                    kd = max(KD_MIN, min(KD_MAX, kd))  # >>> KD: keep kd in range
                    win_t, win_e, win_n, flips = now, 0, 0, 0
            sm_turn += TURN_SMOOTH * (turn - sm_turn)  # ease into / out of turns instead of jerking
            turn = sm_turn
            b = base * (1 - CURVE_SLOW * abs(turn) / MAX_TURN)   # a bit slower in curves
            drive(max(INNER_MIN, b + turn), max(INNER_MIN, b - turn))

            if debug and time.ticks_diff(now, dbg_t) > 150:
                dbg_t = now
                print("raw=%5d black=%5d white=%5d err=%+.2f d=%+6.1f kp=%.1f kd=%.2f turn=%+5.1f speed=%.0f"   # >>> KD: shows d and kd
                      % (raw, rng[0], rng[1], err, d_err, kp, kd, turn, b))
            time.sleep_ms(max(0, LOOP_MS - time.ticks_diff(time.ticks_ms(), t0)))
        stop(); leds(0, 0, 0)

if __name__ == "__main__":
    run(debug=True)

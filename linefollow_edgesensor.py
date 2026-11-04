# ================== EDGE COLOR SENSOR TEST (Cytron Robo ESP32, MicroPython) ==================
# Edge sensor on Grove 33/32 (SoftI2C). Motors are NOT used - move the robot by hand.
# Steps: 1) finds the sensor  2) calibrate white/black with button 34  3) live readout
 
import time
from machine import Pin, SoftI2C, PWM
 
ADDRS = (0x29, 0x10)   # 0x29 = TCS34725, 0x10 = VEML6040
btn  = Pin(34, Pin.IN)
buzz = PWM(Pin(23), freq=1500, duty_u16=0)
 
def beep(): buzz.duty_u16(20000); time.sleep_ms(80); buzz.duty_u16(0)
 
def wait_button(msg):
    print("\n>>", msg, " (press button 34)")
    idle = btn.value()
    while btn.value() == idle: time.sleep_ms(10)
    while btn.value() != idle: time.sleep_ms(10)
    beep()
 
# ---------- 1) FIND THE SENSOR (tries both pin orders) ----------
i2c = ADDR = None
for scl, sda in ((32, 33), (33, 32)):
    bus = SoftI2C(scl=Pin(scl), sda=Pin(sda), freq=100000)
    found = bus.scan()
    print("scl=%d sda=%d -> scan:" % (scl, sda), found)
    for a in ADDRS:
        if a in found:
            i2c, ADDR = bus, a
            print("FOUND sensor at 0x%02X. Use SoftI2C(scl=Pin(%d), sda=Pin(%d)) in main.py" % (a, scl, sda))
            break
    if i2c: break
if i2c is None:
    raise SystemExit("Edge sensor NOT found - check the Grove cable/port (33/32) and power.")
 
if ADDR == 0x29:   # ----- TCS34725 -----
    def w(reg, val): i2c.writeto_mem(ADDR, 0x80 | reg, bytes([val]))
    w(0x00, 0x01); time.sleep_ms(3); w(0x00, 0x03)   # power on + enable
    w(0x01, 0xFC); w(0x0F, 0x01)                     # ~10 ms integration, 4x gain
    def read():
        d = i2c.readfrom_mem(ADDR, 0x80 | 0x20 | 0x14, 8)
        return (d[2] | d[3] << 8, d[4] | d[5] << 8, d[6] | d[7] << 8, d[0] | d[1] << 8)
else:              # ----- VEML6040 (R, G, B, White) -----
    i2c.writeto_mem(ADDR, 0x00, bytes([0x00, 0x00]))  # 40 ms integration, auto mode, ON
    time.sleep_ms(50)
    def _r(reg):
        d = i2c.readfrom_mem(ADDR, reg, 2)
        return d[0] | d[1] << 8
    def read():                                       # white channel used as "clear"
        return (_r(0x08), _r(0x09), _r(0x0A), _r(0x0B))
print("Sensor type:", "TCS34725" if ADDR == 0x29 else "VEML6040")
 
def avg(n=30):
    s = [0, 0, 0, 0]
    for _ in range(n):
        for i, v in enumerate(read()): s[i] += v
        time.sleep_ms(12)
    return [v / n for v in s]
 
# ---------- 2) CALIBRATE ----------
wait_button("Put the edge sensor on WHITE")
W = avg(); print("white:", [int(v) for v in W])
wait_button("Put the edge sensor fully on BLACK tape")
B = avg(); print("black:", [int(v) for v in B])
if W[3] - B[3] < 50:
    print("WARNING: white and black are very close - lower the sensor (5-10 mm) or shield it from light.")
 
def features(v):
    # color "shares" (brightness removed) + overall brightness 0..1
    r, g, b, c = v
    rn, gn, bn = r / max(W[0], 1), g / max(W[1], 1), b / max(W[2], 1)
    s = rn + gn + bn or 1
    norm = (c - B[3]) / max(W[3] - B[3], 1)
    return (rn / s, gn / s, bn / s, norm)
 
# Record what each color ACTUALLY looks like to this sensor (sensor FULLY on the patch)
SAMPLES = {'WHITE': features(W), 'BLACK': features(B)}
wait_button("Put the sensor HALF on black tape, HALF on white (the split)")
v = avg(); SAMPLES['EDGE'] = features(v)
print("EDGE", [int(x) for x in v], "features", ["%.2f" % f for f in SAMPLES['EDGE']])
for name in ('RED', 'GREEN', 'BLUE'):
    wait_button("Put the sensor FULLY on the %s patch" % name)
    v = avg(); SAMPLES[name] = features(v)
    print(name, [int(x) for x in v], "features", ["%.2f" % f for f in SAMPLES[name]])
 
def classify(r, g, b, c):
    f = features((r, g, b, c))
    best, bestd = None, 1e9
    for name, s in SAMPLES.items():                    # nearest calibrated sample wins
        d = 4 * ((f[0]-s[0])**2 + (f[1]-s[1])**2 + (f[2]-s[2])**2) + (f[3]-s[3])**2
        if d < bestd: best, bestd = name, d
    # A color only counts if the reading is CLOSE to that color's sample.
    # Gray in-between readings (like the split) can't be mistaken for a color.
    if best in ('RED', 'GREEN', 'BLUE') and bestd > MAX_COLOR_DIST:
        best = 'EDGE' if 0.15 < f[3] < 0.85 else ('BLACK' if f[3] <= 0.15 else 'WHITE')
    return best, f[:3]
 
MAX_COLOR_DIST = 0.02   # raise if real patches show up as EDGE/BLACK, lower if false colors appear
 
# ---------- 3) LIVE READOUT ----------
wait_button("Live mode: slide the sensor across the tape edge and over each color patch")
print("norm: 0 = black, 1 = white, aim for ~0.5 on the edge.  Ctrl+C to stop.\n")
fastest = 999
hits, last = 0, None
while True:
    t0 = time.ticks_us()
    r, g, b, c = read()
    dt = time.ticks_diff(time.ticks_us(), t0) / 1000
    fastest = min(fastest, dt)
    norm = (c - B[3]) / max(W[3] - B[3], 1)
    col, sh = classify(r, g, b, c)
    hits = hits + 1 if col == last else 1; last = col
    if col in ('RED', 'GREEN', 'BLUE') and hits < 3: col = col.lower() + "?"   # not confirmed yet
    bar = "#" * int(max(0, min(1, norm)) * 20)
    print("r%5d g%5d b%5d c%5d | norm %.2f %-20s | shares %.2f %.2f %.2f | %-5s | read %.1f ms"
          % (r, g, b, c, norm, bar, sh[0], sh[1], sh[2], col, dt))
    time.sleep_ms(100)
 
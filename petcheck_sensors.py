# check_sensors.py - Round 0: find the accelerometer and joystick
from machine import Pin, SoftI2C, ADC
import time, os

print("Board:", os.uname().machine)

# ---------- 1. Look for the accelerometer on both pin pairs ----------
accel = None  # (i2c, address, chip)

def try_i2c(sda, scl):
    try:
        i2c = SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=100000)
        found = i2c.scan()
        print("I2C on SDA=%d SCL=%d found:" % (sda, scl), [hex(a) for a in found])
        for addr in found:
            if addr in (0x18, 0x19):
                if i2c.readfrom_mem(addr, 0x0F, 1)[0] == 0x33:
                    return (i2c, addr, "LIS3DH")
            if addr in (0x53, 0x1D):
                if i2c.readfrom_mem(addr, 0x00, 1)[0] == 0xE5:
                    return (i2c, addr, "ADXL345")
    except Exception as e:
        print("I2C on SDA=%d SCL=%d failed: %s" % (sda, scl, e))
    return None

for sda, scl in ((25, 26), (26, 25), (21, 22), (22, 21)):
    accel = try_i2c(sda, scl)
    if accel:
        print(">>> Accelerometer:", accel[2], "at", hex(accel[1]),
              "on SDA=%d SCL=%d" % (sda, scl))
        break
if not accel:
    print(">>> No accelerometer found - check wiring/power")

# ---------- 2. Look for the joystick (analog) ----------
joy = []
for p in (21, 22, 25, 26):
    try:
        a = ADC(Pin(p))
        a.atten(ADC.ATTN_11DB)          # full 0-3.3 V range
        print("Pin %d can read analog: %d" % (p, a.read_u16()))
        joy.append((p, a))
    except Exception as e:
        print("Pin %d cannot read analog (%s)" % (p, e))

# ---------- 3. Start the accelerometer so we can read it ----------
def accel_read():
    i2c, addr, chip = accel
    if chip == "LIS3DH":
        b = i2c.readfrom_mem(addr, 0x28 | 0x80, 6)
        div = 16380
    else:
        b = i2c.readfrom_mem(addr, 0x32, 6)
        div = 256
    v = [int.from_bytes(b[i:i+2], "little") for i in (0, 2, 4)]
    v = [(x - 65536 if x > 32767 else x) / div for x in v]
    return v

if accel:
    i2c, addr, chip = accel
    if chip == "LIS3DH":
        i2c.writeto_mem(addr, 0x20, b"\x77")   # 400 Hz, XYZ on
        i2c.writeto_mem(addr, 0x23, b"\x88")   # +-2 g, high res
    else:
        i2c.writeto_mem(addr, 0x31, b"\x08")   # full resolution
        i2c.writeto_mem(addr, 0x2D, b"\x08")   # measure mode

# ---------- 4. Live readings for 20 s ----------
print("\nFor 20 s: push the head forward, let it return, press it down,")
print("and tap the desk. Watch the numbers change.\n")
end = time.ticks_add(time.ticks_ms(), 20000)
while time.ticks_diff(end, time.ticks_ms()) > 0:
    line = ""
    for p, a in joy:
        line += "pin%d=%5d  " % (p, a.read_u16())
    if accel:
        x, y, z = accel_read()
        line += "| accel x=%5.2f y=%5.2f z=%5.2f g" % (x, y, z)
    print(line)
    time.sleep_ms(200)
print("Done")
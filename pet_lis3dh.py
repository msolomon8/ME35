"""
lis3dh.py - small MicroPython driver for the ST LIS3DH / LIS3DHTR accelerometer
(Seeed Grove 3-Axis Digital Accelerometer, LIS3DHTR).

  I2C address: 0x19 (default on the Grove board), 0x18 if SDO is tied to GND
  WHO_AM_I register (0x0F) must read 0x33

Features used for Mochi:
  - acceleration() -> (x, y, z) in g
  - tilt()         -> (pitch, roll) in degrees
  - set_tap()/tapped() -> hardware single/double tap ("click") detection

Sources (cite these in the portfolio):
  - Seeed wiki: Grove 3-Axis Digital Accelerometer (LIS3DHTR) - address, voltage
  - ST LIS3DH datasheet - register map (CTRL_REG1/4, OUT_X_L, CLICK_*)
  - ST AN3308 LIS3DH application note, Sec. 8 "Click and double-click recognition"
  - Adafruit CircuitPython LIS3DH driver - counts-per-g dividers and suggested
    tap thresholds per range (ported/simplified here for MicroPython)
"""
from micropython import const
import struct
import math

# ---- registers (ST LIS3DH datasheet) ----
_WHO_AM_I = const(0x0F)
_CTRL_REG1 = const(0x20)      # ODR + axis enable
_CTRL_REG3 = const(0x22)      # interrupt routing to INT1 pin
_CTRL_REG4 = const(0x23)      # BDU, full scale, high-res
_OUT_X_L = const(0x28)        # 6 data bytes X,Y,Z (little endian)
_CLICK_CFG = const(0x38)      # which axes / single vs double
_CLICK_SRC = const(0x39)      # what happened (read clears latch)
_CLICK_THS = const(0x3A)      # threshold, bit7 = latch
_TIME_LIMIT = const(0x3B)     # max tap length      (1 LSB = 1/ODR)
_TIME_LATENCY = const(0x3C)   # dead time after tap (1 LSB = 1/ODR)
_TIME_WINDOW = const(0x3D)    # window for 2nd tap  (1 LSB = 1/ODR)
_AUTO_INC = const(0x80)       # set MSB of register address for multi-byte reads

RANGE_2G = const(0)
RANGE_4G = const(1)
RANGE_8G = const(2)
RANGE_16G = const(3)
_COUNTS_PER_G = (16380, 8190, 4096, 1365)   # left-justified 16-bit data

ODR_100HZ = const(0b0101)
ODR_200HZ = const(0b0110)
ODR_400HZ = const(0b0111)

TAP_NONE = const(0)
TAP_SINGLE = const(1)
TAP_DOUBLE = const(2)


class LIS3DH:
    def __init__(self, i2c, address=0x19, data_rate=ODR_400HZ):
        self.i2c = i2c
        self.address = address
        who = self._read8(_WHO_AM_I)
        if who != 0x33:
            raise OSError("LIS3DH not found at 0x%02X (WHO_AM_I=0x%02X). "
                          "Check wiring, or try address 0x18." % (address, who))
        # data rate + enable X, Y, Z
        self._write8(_CTRL_REG1, (data_rate << 4) | 0x07)
        self._range = RANGE_2G
        self.set_range(RANGE_2G)

    # ---------- low level ----------
    def _read8(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def _write8(self, reg, val):
        self.i2c.writeto_mem(self.address, reg, bytes([val & 0xFF]))

    # ---------- configuration ----------
    def set_range(self, r):
        """RANGE_2G / 4G / 8G / 16G. Also turns on block data update + high-res."""
        self._range = r
        self._write8(_CTRL_REG4, 0x80 | (r << 4) | 0x08)

    # ---------- readings ----------
    def acceleration(self):
        """Return (x, y, z) in g."""
        buf = self.i2c.readfrom_mem(self.address, _OUT_X_L | _AUTO_INC, 6)
        x, y, z = struct.unpack("<hhh", buf)
        d = _COUNTS_PER_G[self._range]
        return x / d, y / d, z / d

    def magnitude(self):
        x, y, z = self.acceleration()
        return math.sqrt(x * x + y * y + z * z)

    def tilt(self):
        """(pitch, roll) in degrees. Flat on the desk is about (0, 0)."""
        x, y, z = self.acceleration()
        pitch = math.degrees(math.atan2(-x, math.sqrt(y * y + z * z)))
        roll = math.degrees(math.atan2(y, z))
        return pitch, roll

    # ---------- hardware tap detection (AN3308 sec. 8) ----------
    def set_tap(self, tap, threshold, time_limit=10, time_latency=20,
                time_window=255, axes="xyz"):
        """
        tap: TAP_NONE (off), TAP_SINGLE, or TAP_DOUBLE
        threshold: 1-127, 1 LSB = full_scale/128 (about 16 mg at 2 g).
                   Adafruit suggests 40-80 at 2 g, 20-40 at 4 g; desk taps
                   through a table may need lower - tune with tune_taps().
        time_* registers are in samples (1/ODR): at 400 Hz, 1 LSB = 2.5 ms.
        """
        if tap == TAP_NONE:
            self._write8(_CLICK_CFG, 0)
            self._write8(_CTRL_REG3, 0)
            return
        bits = 0
        shift = 0 if tap == TAP_SINGLE else 1      # single = XS/YS/ZS, double = XD/YD/ZD
        if "x" in axes:
            bits |= 1 << (0 + shift)
        if "y" in axes:
            bits |= 1 << (2 + shift)
        if "z" in axes:
            bits |= 1 << (4 + shift)
        self._write8(_CTRL_REG3, 0x80)                     # also route click to INT1 pin
        self._write8(_CLICK_CFG, bits)
        self._write8(_CLICK_THS, 0x80 | (threshold & 0x7F))  # bit7 = latch until read
        self._write8(_TIME_LIMIT, time_limit)
        self._write8(_TIME_LATENCY, time_latency)
        self._write8(_TIME_WINDOW, time_window)

    def tapped(self):
        """Poll this often (every ~20 ms). Returns TAP_NONE, TAP_SINGLE or TAP_DOUBLE.
        Reading CLICK_SRC clears the latched event."""
        src = self._read8(_CLICK_SRC)
        if not src & 0x40:          # IA: no event
            return TAP_NONE
        if src & 0x20:              # DClick
            return TAP_DOUBLE
        if src & 0x10:              # SClick
            return TAP_SINGLE
        return TAP_NONE

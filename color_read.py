from machine import I2C, Pin
import time
import veml6040

# sensor is wired to SDA = D33, SCL = D32 (same as robot_listener.py)
i2c = I2C(0, sda=Pin(33), scl=Pin(32), freq=400000)
print("I2C devices:", i2c.scan())    # should print [16]

sensor = veml6040.VEML6040(i2c)
sensor.trigger_measurement()
time.sleep(0.2)                      # give it time for the first fresh reading

SAMPLES = 20
# readings to average per surface


def average_white():
    # average several readings so one noisy value doesn't throw off the result
    total = 0
    for _ in range(SAMPLES):
        red, green, blue, white = sensor.read_rgbw()
        total += white
        time.sleep(0.1)
    return total // SAMPLES


# ---- step 1: guided calibration ----
input("Put the sensor over the FLOOR, then press Enter...")
floor = average_white()
print("Floor white =", floor)

input("Put the sensor over the BLACK finish line, then press Enter...")
black = average_white()
print("Black white =", black)

level = (floor + black) // 2
print()
print("Copy this into robot_listener.py:")
print("BLACK_LEVEL =", level)
if floor - black < 200:
    print("Warning: floor and black are very close - lower the sensor or check the wiring")
print()

# ---- step 2: live readout (Ctrl+C to stop) ----
print("Live readings - move the sensor around to double-check")
while True:
    red, green, blue, white = sensor.read_rgbw()
    label = "BLACK" if white < level else "floor"
    print("R:", red, " G:", green, " B:", blue, " W:", white, " ->", label)
    time.sleep(0.2)

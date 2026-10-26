# main.py -- Digital Twin, one ESP32 (based on encoder_two_servos / servo_follow.py)
# Encoders -> servos 4 & 5 (Arm 1) -> Onshape -> servos 18 & 19 (Arm 2)
# Needs encoder_updated.py on the board next to this file.
import encoder_updated
import time
# --- added for Onshape ---
import math, json, network, binascii
import requests

encoder_updated.Servo.MIN_US = 500     # pulse for 0 degrees  (tested: works)
encoder_updated.Servo.MAX_US = 2500    # pulse for 180 degrees (tested: works)

# ---- Pin setup: change these to match your wiring ------------------------
ENC1_A, ENC1_B = 39, 32    # encoder on DC motor 1
ENC2_A, ENC2_B = 25, 33    # encoder on DC motor 2
SERVO1_PIN = 4             # Arm 1 servo 1
SERVO2_PIN = 5             # Arm 1 servo 2
SERVO3_PIN = 18            # Arm 2 servo 1  (added)
SERVO4_PIN = 19            # Arm 2 servo 2  (added)
# --------------------------------------------------------------------------

COUNTS_PER_REV = 4000
GAIN = 0.5
START_ANGLE = 90           # servo angle at start = 0 deg in Onshape
SMOOTH = 0.15
DEADBAND = 2.0

# ======================= added: Onshape settings =======================
SSID = "tufts_eecs"
PASSWORD = "foundedin1883"

api_url = "https://cad.onshape.com/api/v17/assemblies/d/26a12a44495346c36beb1f55/w/ae24b412e997007f0c6243c8/e/35020c0205794a00575006db/matevalues"
access_key = "on_2hrsKM23UKKS6woHCDqzV"
secret_key = "1LqrWBiFd9AHC7FDzu86yMxMuuZbO963P49lLmbOb7AIOxDK"
headers = {'Accept': 'application/json;charset=UTF-8;qs=0.09',
           'Content-Type': 'application/json',
           'Authorization': 'Basic ' + binascii.b2a_base64((access_key + ":" + secret_key).encode()).decode().strip()}

MATE1, MATE2 = "Revolute 1", "Revolute 2"   # mate names exactly as in Onshape

# Onshape angle = DIR * (servo angle - 90) + OFFSET   (tune to line up CAD with the real arm)
OFFSET1, DIR1 = 90, 1
OFFSET2, DIR2 = 90, 1
SETTLE_MS = 300            # send to Onshape once Arm 1 has been still this long
# =======================================================================

enc1 = encoder_updated.Count(ENC1_A, ENC1_B)
enc2 = encoder_updated.Count(ENC2_A, ENC2_B)
servo1 = encoder_updated.Servo(SERVO1_PIN)
servo2 = encoder_updated.Servo(SERVO2_PIN)
servo3 = encoder_updated.Servo(SERVO3_PIN)   # added: Arm 2
servo4 = encoder_updated.Servo(SERVO4_PIN)   # added: Arm 2

enc1.reset()
enc2.reset()

def counts_to_angle(counts):
    turned = counts * 360 / COUNTS_PER_REV
    return max(0, min(180, START_ANGLE + GAIN * turned))

MIN_COUNT = -int(90 / (GAIN * 360 / COUNTS_PER_REV))
MAX_COUNT = int(90 / (GAIN * 360 / COUNTS_PER_REV))

def clamp_count(enc):
    if enc.counter < MIN_COUNT:
        enc.counter = MIN_COUNT
    elif enc.counter > MAX_COUNT:
        enc.counter = MAX_COUNT


# ======================= added: Onshape functions =======================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Connected! IP address:", wlan.ifconfig()[0])

def read_onshape():
    """Returns {mate name: (mate entry, angle in degrees)} or None on error"""
    response = requests.get(api_url, headers=headers)
    status = response.status_code
    data = response.json()
    response.close()
    if "mateValues" not in data:
        print("Onshape error:", status, data)
        return None
    mates = {}
    for mate in data["mateValues"]:
        mates[mate["mateName"]] = (mate, mate.get("rotationZ", 0) * 180 / math.pi)
    return mates

def post_onshape(mates, d1, d2):
    m1 = mates[MATE1][0]
    m2 = mates[MATE2][0]
    m1["rotationZ"] = d1 * math.pi / 180
    m2["rotationZ"] = d2 * math.pi / 180
    response = requests.post(api_url, headers=headers, data=json.dumps({"mateValues": [m1, m2]}))
    if response.status_code != 200:
        print("Onshape post error:", response.status_code, response.text)
    response.close()

def to_onshape(servo, offset, d):
    return d * (servo - 90) + offset

def from_onshape(cad, offset, d):
    return 90 + (cad - offset) / d

connect_wifi()
mates = read_onshape()
if mates:
    print("Mates found:", list(mates.keys()))
else:
    print("Onshape not working -- Arm 1 will still follow the encoders")
# =======================================================================

servo1.angle(START_ANGLE)
servo2.angle(START_ANGLE)
servo3.angle(START_ANGLE)
servo4.angle(START_ANGLE)
s1 = s2 = START_ANGLE         # smoothed angles
last1 = last2 = START_ANGLE   # last angles actually sent to the servos

# added: for "has Arm 1 stopped moving?"
last_move = time.ticks_ms()
synced = True

try:
    while True:
        clamp_count(enc1)
        clamp_count(enc2)
        c1 = enc1.value()
        c2 = enc2.value()

        s1 += SMOOTH * (counts_to_angle(c1) - s1)
        s2 += SMOOTH * (counts_to_angle(c2) - s2)

        if abs(s1 - last1) >= DEADBAND:
            servo1.angle(s1)
            last1 = s1
            last_move = time.ticks_ms()     # added
            synced = False                  # added
        if abs(s2 - last2) >= DEADBAND:
            servo2.angle(s2)
            last2 = s2
            last_move = time.ticks_ms()     # added
            synced = False                  # added

        # ---- added: once Arm 1 stops moving: Arm 1 -> Onshape -> Arm 2 ----
        if mates and not synced and time.ticks_diff(time.ticks_ms(), last_move) > SETTLE_MS:
            post_onshape(mates, to_onshape(last1, OFFSET1, DIR1), to_onshape(last2, OFFSET2, DIR2))
            cad = read_onshape()
            if cad:
                o1, o2 = cad[MATE1][1], cad[MATE2][1]
                servo3.angle(from_onshape(o1, OFFSET1, DIR1))
                servo4.angle(from_onshape(o2, OFFSET2, DIR2))
                print("Arm1:", round(last1), round(last2), "-> Onshape:", round(o1, 1), round(o2, 1), "-> Arm2")
            synced = True
        # -------------------------------------------------------------------

        time.sleep(0.02)
except KeyboardInterrupt:
    servo1.off()
    servo2.off()
    servo3.off()
    servo4.off()
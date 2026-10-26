# main.py -- Digital Twin, one ESP32
# Encoders -> servos 4 & 5 (Arm 1) -> Onshape -> servos 18 & 19 (Arm 2)

#libraries
import time, math, json, network, binascii
import requests
from machine import Pin, PWM

#setting up SSID and password
SSID = "tufts_eecs"
PASSWORD = "foundedin1883"

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Connected! IP address:", wlan.ifconfig()[0])
    return wlan

connect_wifi()


# ---------------- Settings ----------------
api_url = "https://cad.onshape.com/api/v17/assemblies/d/26a12a44495346c36beb1f55/w/ae24b412e997007f0c6243c8/e/35020c0205794a00575006db/matevalues"
access_key = "on_2hrsKM23UKKS6woHCDqzV"
secret_key = "1LqrWBiFd9AHC7FDzu86yMxMuuZbO963P49lLmbOb7AIOxDK"
headers = {'Accept': 'application/json;charset=UTF-8;qs=0.09',
           'Content-Type': 'application/json',
           'Authorization': 'Basic ' + binascii.b2a_base64((access_key + ":" + secret_key).encode()).decode().strip()}

MATE1, MATE2 = "Revolute 1", "Revolute 2"   # mate names exactly as in Onshape

# ---------------- Alignment (tune these) ----------------
# Onshape angle = DIR * (servo angle - 90) + OFFSET
# OFFSET = the Onshape mate angle when the real arm is in its start pose (servo at 90)
# DIR = 1 or -1, flip if the CAD joint turns the opposite way from the real one
OFFSET1, DIR1 = 0, 1
OFFSET2, DIR2 = 0, 1
SETTLE_MS = 300     # update Onshape once Arm 1 has been still this long
MOVE_COUNTS = 10    # encoder must move more than this to count as real movement (~1.2 deg)

# ---------------- Encoders ----------------
class Count:
    def __init__(self, A, B):
        self.A = Pin(A, Pin.IN)
        self.B = Pin(B, Pin.IN)
        self.counter = 0
        self.A.irq(self.cb, Pin.IRQ_FALLING | Pin.IRQ_RISING)
        self.B.irq(self.cb, Pin.IRQ_FALLING | Pin.IRQ_RISING)

    def cb(self, pin):
        if self.A.value() != self.B.value():
            if pin == self.A:
                self.counter -= 1
            else:
                self.counter += 1
        else:
            if pin == self.A:
                self.counter += 1
            else:
                self.counter -= 1

count1 = Count(32, 39)
count2 = Count(25, 26)

# ---------------- Servos ----------------
pwm1 = PWM(Pin(4), freq=50)     # Arm 1
pwm2 = PWM(Pin(5), freq=50)
pwm3 = PWM(Pin(18), freq=50)    # Arm 2
pwm4 = PWM(Pin(19), freq=50)

MIN_MS = 0.5
MAX_MS = 2.5

for p in (pwm1, pwm2, pwm3, pwm4):
    p.duty_u16(int(1.5 * 65535 / 20))     # start at 90

def set_servo(pwm, angle, flip=False):
    angle = max(0, min(180, angle))
    if flip:
        angle = 180 - angle
    pulse_ms = MIN_MS + (angle / 180) * (MAX_MS - MIN_MS)
    pwm.duty_u16(int(pulse_ms / 20 * 65535))

# servo angle <-> Onshape angle
def to_onshape(servo, offset, d):
    return d * (servo - 90) + offset

def from_onshape(cad, offset, d):
    return 90 + (cad - offset) / d

# ---------------- Onshape ----------------
def read_onshape():
    """Returns {mate name: (mate entry, angle in degrees)} or None if Onshape gave an error"""
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
    body = {"mateValues": [m1, m2]}
    response = requests.post(api_url, headers=headers, data=json.dumps(body))
    status = response.status_code
    if status != 200:
        print("Onshape post error:", status, response.text)
    response.close()
    return status

mates = read_onshape()
if mates:
    print("Mates found:", list(mates.keys()))
    print("Onshape now:", mates[MATE1][1], mates[MATE2][1])
else:
    print("Onshape not working -- Arm 1 will still follow the encoders")

last_c1, last_c2 = count1.counter, count2.counter
last_a1 = last_a2 = 90
last_move = time.ticks_ms()
synced = False

# ---------------- Main loop ----------------
while True:
    # 1) Encoders -> Arm 1 (only move a servo if the angle changed at least 1 degree)
    angle1 = max(0, min(180, 90 + count1.counter * 360 / 2935))
    angle2 = max(0, min(180, 90 + count2.counter * 360 / 2935))
    if abs(angle1 - last_a1) >= 1:
        set_servo(pwm1, angle1)
        last_a1 = angle1
    if abs(angle2 - last_a2) >= 1:
        set_servo(pwm2, angle2, flip=True)
        last_a2 = angle2

    # 2) Once Arm 1 really moved and then stopped: Arm 1 -> Onshape -> Arm 2
    if abs(count1.counter - last_c1) > MOVE_COUNTS or abs(count2.counter - last_c2) > MOVE_COUNTS:
        last_c1, last_c2 = count1.counter, count2.counter
        last_move = time.ticks_ms()
        synced = False
    elif mates and not synced and time.ticks_diff(time.ticks_ms(), last_move) > SETTLE_MS:
        d1 = to_onshape(last_a1, OFFSET1, DIR1)
        d2 = to_onshape(last_a2, OFFSET2, DIR2)
        post_onshape(mates, d1, d2)

        cad = read_onshape()
        if cad:
            o1, o2 = cad[MATE1][1], cad[MATE2][1]
            set_servo(pwm3, from_onshape(o1, OFFSET1, DIR1))
            set_servo(pwm4, from_onshape(o2, OFFSET2, DIR2), flip=True)
            print("Arm1: %.1f, %.1f -> Onshape: %.1f, %.1f -> Arm2" % (last_a1, last_a2, o1, o2))
        synced = True

    time.sleep(0.01)
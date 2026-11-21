# HW9: robot driven over MQTT (ESP32 MicroPython, same bot as HW8; run from Thonny, save to the board as main.py)
#
# Topics:  ME35/speed      0-100           -> only sets speed, never starts the bot
#          ME35/direction  forward/backward/left/right/stop
#          ME35/led/0, ME35/led/1  {"r":..,"g":..,"b":..}   (NeoPixels on pin 15)
# If WiFi or the broker is lost: motors stop and the LEDs blink red until it reconnects.

import time, json, network, machine, ubinascii
from machine import Pin, PWM, Timer
import neopixel
from umqtt.simple import MQTTClient
import secrets


# ---------- fill these in ----------
#SSID= "Justin\u2019s iPhone (4)"
#PASSWORD= "685237902"
SSID = secrets.SSID
PASSWORD = secrets.PWD
BROKER = "10.5.13.148"   # for practice; on demo day put the instructor's broker IP here

# Topic prefix. Demo day MUST be "ME35". For practice on the public broker, change it
# (and PREFIX in send_commands.py) to something unique, e.g. "ME35_practice_group3",
# so other people's messages don't drive your bot.
PREFIX = "ME35"

# Motor pins from HW8 (BLE RC Car/Listener_Robot.py): Motor1(12,13) = right, Motor2(14,27) = left.
# The first pin of each pair is the one driven to make that wheel go FORWARD.
# If a wheel spins the wrong way, swap its two numbers.
LEFT_A, LEFT_B = 27, 14
RIGHT_A, RIGHT_B = 12, 13
# -----------------------------------

DEFAULT_SPEED = 20
CLIENT_ID = b"bot-" + ubinascii.hexlify(machine.unique_id())
HEARTBEAT_TOPIC = b"hb/" + CLIENT_ID     # our own topic, outside ME35/, to prove the link is alive
HEARTBEAT_EVERY = 1000                   # ms
LOST_AFTER = 4000                        # ms without our heartbeat echo -> connection lost

# ---------- hardware ----------
pixels = neopixel.NeoPixel(Pin(15), 2)
PWM(Pin(23), freq=1000, duty_u16=0)      # built-in buzzer: keep it quiet

def make_pwm(pin):
    p = PWM(Pin(pin))
    p.freq(500)                          # same as HW8
    p.duty_u16(0)
    return p

la, lb, ra, rb = (make_pwm(p) for p in (LEFT_A, LEFT_B, RIGHT_A, RIGHT_B))

def set_motor(a, b, power):
    """power -100..100"""
    duty = int(abs(power) * 65535 / 100)
    if power > 0:
        a.duty_u16(duty); b.duty_u16(0)
    elif power < 0:
        a.duty_u16(0); b.duty_u16(duty)
    else:
        a.duty_u16(0); b.duty_u16(0)

def drive(left, right):
    set_motor(la, lb, left)
    set_motor(ra, rb, right)

def set_led(i, r, g, b):
    pixels[i] = (r, g, b)
    pixels.write()

# ---------- robot state ----------
speed = DEFAULT_SPEED
direction = "stop"
led_colors = [(0, 0, 0), (0, 0, 0)]

def apply_motion():
    s = speed
    if direction == "forward":
        drive(s, s)
    elif direction == "backward":
        drive(-s, -s)
    elif direction == "left":           # rotate in place
        drive(-s, s)
    elif direction == "right":
        drive(s, -s)
    else:
        drive(0, 0)

def clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))

last_heartbeat = 0
online = False          # True while we think WiFi + MQTT are up

def on_message(topic, msg):
    global speed, direction, last_heartbeat
    topic = topic.decode()
    text = msg.decode().strip()

    if topic == HEARTBEAT_TOPIC.decode():
        last_heartbeat = time.ticks_ms()
        return

    print(topic, text)
    try:
        if topic == PREFIX + "/speed":
            speed = clamp(float(text), 0, 100)
            # Only re-apply if already moving: a speed message never starts the bot.
            if direction != "stop":
                apply_motion()

        elif topic == PREFIX + "/direction":
            d = text.lower().strip('"')
            if d in ("forward", "backward", "left", "right", "stop"):
                direction = d
                apply_motion()

        elif topic.startswith(PREFIX + "/led/"):
            i = int(topic.split("/")[-1])
            if i in (0, 1):
                c = json.loads(text)
                rgb = (clamp(c.get("r", 0), 0, 255),
                       clamp(c.get("g", 0), 0, 255),
                       clamp(c.get("b", 0), 0, 255))
                led_colors[i] = rgb
                set_led(i, *rgb)
    except Exception as e:
        print("bad message:", topic, text, e)

# ---------- connection ----------
wlan = network.WLAN(network.STA_IF)

def blink_once(on):
    for i in range(2):
        pixels[i] = (255, 0, 0) if on else (0, 0, 0)
    pixels.write()

# Watchdog: runs on a hardware timer, so it still works even if the network code
# gets stuck waiting on a dead connection. If our heartbeat hasn't come back for
# LOST_AFTER ms (or WiFi is down) it stops the motors and blinks red.
blink_state = False

def watchdog(t):
    global blink_state, direction
    if not online:
        return                  # connect() is handling the blinking itself
    if wlan.isconnected() and time.ticks_diff(time.ticks_ms(), last_heartbeat) <= LOST_AFTER:
        return
    direction = "stop"
    drive(0, 0)
    blink_state = not blink_state
    blink_once(blink_state)

Timer(0).init(period=300, mode=Timer.PERIODIC, callback=watchdog)

def connect():
    """Connect WiFi + MQTT, blinking red the whole time it's not connected."""
    global last_heartbeat, online
    online = False
    on = False
    # boot.py (or an earlier run) may have joined a different network. Leave it,
    # otherwise we'd skip connecting to SSID and never notice the hotspot going away.
    try:
        current = wlan.config("ssid") if wlan.isconnected() else None
    except Exception:
        current = None
    if current is not None and current != SSID:
        print("On the wrong WiFi (" + str(current) + "), switching to", SSID)
        wlan.disconnect()
        time.sleep(1)
    while True:
        drive(0, 0)
        if not wlan.isconnected():
            # Reset the WiFi radio first. On ESP32, calling connect() while an old
            # attempt (e.g. from before a soft reboot) is still running gives
            # "Wifi Internal State Error".
            try:
                wlan.disconnect()
            except OSError:
                pass
            wlan.active(False)
            time.sleep(1)
            wlan.active(True)
            time.sleep(1)
            print("Connecting to WiFi", SSID, "...")
            try:
                wlan.connect(SSID, PASSWORD)
            except OSError as e:
                print("WiFi connect:", e)
            t0 = time.ticks_ms()
            while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15000:
                on = not on; blink_once(on); time.sleep(0.3)
            if not wlan.isconnected():
                print("WiFi failed, status:", wlan.status(), "- retrying")
                continue
        print("WiFi:", wlan.ifconfig()[0])
        try:
            c = MQTTClient(CLIENT_ID, BROKER, keepalive=10)
            c.set_callback(on_message)
            c.connect()
            c.subscribe((PREFIX + "/#").encode())
            c.subscribe(HEARTBEAT_TOPIC)
            print("MQTT connected to", BROKER)
            last_heartbeat = time.ticks_ms()
            online = True
            # restore whatever colors the instructor last set
            for i in range(2):
                pixels[i] = led_colors[i]
            pixels.write()
            return c
        except Exception as e:
            print("MQTT connect failed:", e)
            for _ in range(6):
                on = not on; blink_once(on); time.sleep(0.3)

# ---------- main loop ----------
client = connect()
last_sent = 0
while True:
    try:
        client.check_msg()          # non-blocking; runs on_message
        now = time.ticks_ms()
        if time.ticks_diff(now, last_sent) > HEARTBEAT_EVERY:
            client.publish(HEARTBEAT_TOPIC, b"1")
            last_sent = now
        if not wlan.isconnected() or time.ticks_diff(now, last_heartbeat) > LOST_AFTER:
            raise OSError("connection lost")
        time.sleep_ms(10)
    except Exception as e:
        print("Lost connection:", e)
        online = False
        direction = "stop"
        drive(0, 0)
        try:
            client.disconnect()
        except Exception:
            pass
        client = connect()          # blinks red until it's back


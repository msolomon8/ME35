# Yeller (peripheral) - joystick remote

from BLE_CEEO import Yell
from machine import ADC, Pin, PWM          # NEW: PWM for the buzzer
import neopixel                            # NEW
import time
import json

NAME = "Justin"
buffer = b""
event = None                               # NEW: latest event from the robot ("finish" / "rearm")

# Joystick setup - change pin numbers to match your wiring
x_axis = ADC(Pin(32))
y_axis = ADC(Pin(39))
x_axis.atten(ADC.ATTN_11DB)     # lets the ADC read the full 0-3.3 V range
y_axis.atten(ADC.ATTN_11DB)

CENTER = 32768
DEADZONE = 12000                # how far from center before it counts as a move


# NEW: ---- NeoPixels (change 15 if your remote board's LEDs are on another pin) ----
pixels = neopixel.NeoPixel(Pin(15), 2)


def set_lights(rgb):
    pixels[0] = rgb
    pixels[1] = rgb
    pixels.write()


# NEW: ---- buzzer + melody player (change 23 if your buzzer is on another pin) ----
buzzer = PWM(Pin(23), freq=1000, duty_u16=0)
BEEP_DUTY = 2000
NOTE_GAP = 25

C4, D4, E4, F4, G4, A4, B4 = 262, 294, 330, 349, 392, 440, 494
REST = 0

melody = []
melody_i = 0
melody_next = 0


def play_melody(notes, beat_ms):
    global melody, melody_i, melody_next
    steps = []
    for freq, beats in notes:
        ms = int(beats * beat_ms)
        if freq:
            steps.append((freq, ms - NOTE_GAP))
            steps.append((0, NOTE_GAP))
        else:
            steps.append((0, ms))
    melody = steps
    melody_i = 0
    melody_next = time.ticks_ms()
    buzzer.duty_u16(0)


def update_melody(now):
    global melody, melody_i, melody_next
    if not melody or time.ticks_diff(now, melody_next) < 0:
        return
    if melody_i >= len(melody):
        buzzer.duty_u16(0)
        melody = []
        return
    freq, ms = melody[melody_i]
    melody_i += 1
    if freq:
        buzzer.freq(freq)
        buzzer.duty_u16(BEEP_DUTY)
    else:
        buzzer.duty_u16(0)
    melody_next = time.ticks_add(now, ms)


LA_CUCARACHA = [
    (C4, 1), (C4, 1), (C4, 1), (F4, 3), (A4, 2), (REST, 1),
    (C4, 1), (C4, 1), (C4, 1), (F4, 3), (A4, 2), (REST, 1),
    (F4, 1), (F4, 1), (E4, 1), (E4, 1), (D4, 1), (D4, 1), (C4, 4),
]


def get_command():
    x = x_axis.read_u16() - CENTER      # negative = one way, positive = the other
    y = y_axis.read_u16() - CENTER

    if abs(x) < DEADZONE and abs(y) < DEADZONE:
        return "stop"
    if abs(y) >= abs(x):                # whichever axis is pushed further wins
        return "forward" if y > 0 else "back"
    else:
        return "right" if x < 0 else "left"


def callback(data):
    global buffer, event                # NEW: event
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        msg = json.loads(line.decode())
        print("Received:", msg)
        if "evt" in msg:                # NEW: remember what the robot told us
            event = msg["evt"]


p = None
try:
    set_lights((0, 0, 0))               # NEW: start with lights off
    p = Yell(NAME, interval_us=30000, verbose=False)
    p.callback = callback

    print("Waiting for a listener...")
    if p.connect_up():
        print("Connected")
        while p.is_connected:

            # NEW: react to the robot
            if event == "finish":
                set_lights((60, 0, 0))              # red
                play_melody(LA_CUCARACHA, 120)
                event = None
            elif event == "rearm":
                set_lights((0, 0, 0))               # off
                event = None

            cmd = get_command()
            payload = json.dumps({"cmd": cmd}) + "\n"
            print("Sending:", cmd)

            for start in range(0, len(payload), 20):
                p.send(payload[start:start + 20])
                time.sleep_ms(20)

            # NEW: wait 100 ms in 10 small steps so the song keeps playing
            for _ in range(10):
                update_melody(time.ticks_ms())
                time.sleep_ms(10)
    print("Lost connection")
finally:
    buzzer.duty_u16(0)                  # NEW
    set_lights((0, 0, 0))               # NEW
    if p:
        p.disconnect()
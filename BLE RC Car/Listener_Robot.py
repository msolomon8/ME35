# Listener (central) - robot driven by joystick, spins and sings at black finish line

from BLE_CEEO import Listen
from machine import PWM, Pin, I2C
import veml6040
import time
import json

NAME = "Justin"             # must match the yeller's name
buffer = b""
command = "stop"
last_msg = time.ticks_ms()


# ---- buzzer + melody player (from line follower) ----
buzzer = PWM(Pin(23), freq=1000, duty_u16=0)   # built-in buzzer
BEEP_DUTY = 2000            # buzzer volume
NOTE_GAP = 25               # ms of silence after each note so repeated notes sound separate

C4, D4, E4, F4, G4, A4, B4 = 262, 294, 330, 349, 392, 440, 494
REST = 0

melody = []                 # the steps being played: (freq, ms)
melody_i = 0
melody_next = 0             # when to move on to the next step


def play_melody(notes, beat_ms):
    # load a melody (does NOT play it - update_melody() must be called repeatedly)
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
    # call often: switches to the next note when the current one is done
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


# La Cucaracha - must come AFTER the note names are defined
LA_CUCARACHA = [
    (C4, 1), (C4, 1), (C4, 1), (F4, 3), (A4, 2), (REST, 1),
    (C4, 1), (C4, 1), (C4, 1), (F4, 3), (A4, 2), (REST, 1),
    (F4, 1), (F4, 1), (E4, 1), (E4, 1), (D4, 1), (D4, 1), (C4, 4),
]


# ---- motors ----
class Motor:
    def __init__(self, m1, m2):
        self.M1 = PWM(m1, freq=500, duty_u16=0)
        self.M2 = PWM(m2, freq=500, duty_u16=0)
        self.stop()

    def stop(self):
        self.M1.duty_u16(0)
        self.M2.duty_u16(0)

    def drive(self, speed, forward):
        # speed -100..100; forward = direction value that pushes this wheel forward
        if speed >= 0:
            self.start(forward, speed)
        else:
            self.start(1 - forward, -speed)

    def start(self, direction=0, speed=50):
        if direction:
            self.M1.duty_u16(int(speed * 65535 / 100))
            self.M2.duty_u16(0)
        else:
            self.M1.duty_u16(0)
            self.M2.duty_u16(int(speed * 65535 / 100))


Motor1 = Motor(12, 13)
Motor2 = Motor(14, 27)
LeftMotor = Motor2          # Motor1 is on the right, Motor2 on the left
RightMotor = Motor1

DRIVE_SPEED = 50            # forward/back speed (0-100)
TURN_SPEED = 40             # turning speed (0-100)
SPIN_MS = 3000              # how long the victory spin lasts


def set_wheels(left, right):
    LeftMotor.drive(left, 0)
    RightMotor.drive(right, 1)


def stop_all():
    LeftMotor.stop()
    RightMotor.stop()


# ---- finish-line sensor (VEML6040 on SDA = D33, SCL = D32) ----
i2c = I2C(0, sda=Pin(33), scl=Pin(32), freq=400000)   # if scan prints [], swap 33 and 32
print("I2C devices:", i2c.scan())    # should print [16]
color_sensor = veml6040.VEML6040(i2c)
color_sensor.trigger_measurement()

FINISH_LEVEL = 6000         # white-channel reading below this = on the red tape
                            # (latest calibration: tape ~5800, floor ~6200)
FINISH_READS = 3            # tape this many checks in a row = finish line
black_count = 0             # counts tape readings in a row
armed = True                # True = ready to detect the finish line
                            # (turns off after a dance; back on by holding reverse for REARM_MS)
REARM_MS = 1000             # how long you must hold "back" after a dance to re-arm (1 s)
back_since = None           # when the current "back" press started (None = not reversing)


def on_finish_tape():
    # the red tape is darker overall than the floor; its color ratio matches the
    # warm floor, so brightness (W) is what tells them apart
    red, green, blue, white = color_sensor.read_rgbw()
    return white < FINISH_LEVEL


# ---- BLE ----
def callback(data):
    global buffer, command, last_msg
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        try:
            msg = json.loads(line.decode())
            command = msg.get("cmd", "stop")
            last_msg = time.ticks_ms()
        except ValueError:
            pass            # bad message: ignore it, the next one arrives in ~120 ms


def send_event(name):
    # tell the remote something happened, e.g. {"evt": "finish"} (fits in one 20-byte packet)
    if p and p.is_connected:
        p.send(json.dumps({"evt": name}) + "\n")


p = None
try:
    p = Listen(NAME, verbose=False)
    p.callback = callback

    print("Looking for", NAME, "...")
    if p.connect_up():
        print("Connected")
        while p.is_connected:

            # --- keep any song going while you drive ---
            update_melody(time.ticks_ms())

            # --- finish line check ---
            on_tape = on_finish_tape()

            if armed:
                if on_tape:
                    black_count += 1
                else:
                    black_count = 0

                if black_count >= FINISH_READS:
                    armed = False                       # don't re-trigger while still on the tape
                    black_count = 0
                    print("Finish line!")
                    send_event("finish")                # remote plays the song + turns red
                    play_melody(LA_CUCARACHA, 120)      # start the song first

                    start = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), start) < SPIN_MS:
                        set_wheels(-TURN_SPEED, TURN_SPEED)   # spin in place
                        update_melody(time.ticks_ms())        # keep the song going
                        time.sleep_ms(10)
                    stop_all()
                    # no 'continue' here: we fall through to the joystick code below

            elif command == "back":
                # holding reverse also re-arms
                if back_since is None:
                    back_since = time.ticks_ms()        # just started reversing
                elif time.ticks_diff(time.ticks_ms(), back_since) >= REARM_MS:
                    armed = True
                    back_since = None
                    print("Reversed off the line - finish line re-armed")
                    send_event("rearm")                 # remote turns its lights off
            else:
                back_since = None                       # let go of "back": restart the timer

            # --- safety: stop if the remote goes quiet ---
            if time.ticks_diff(time.ticks_ms(), last_msg) > 500:
                command = "stop"

            # --- drive ---
            if command == "forward":
                set_wheels(DRIVE_SPEED, DRIVE_SPEED)
            elif command == "back":
                set_wheels(-DRIVE_SPEED, -DRIVE_SPEED)
            elif command == "left":
                set_wheels(-TURN_SPEED, TURN_SPEED)
            elif command == "right":
                set_wheels(TURN_SPEED, -TURN_SPEED)
            else:
                stop_all()

            time.sleep_ms(50)       # ~sensor update rate; still fast enough for driving
    print("Lost connection")
finally:
    stop_all()
    buzzer.duty_u16(0)
    if p:
        p.disconnect()

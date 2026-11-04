# Listener (central)
from BLE_CEEO import Listen
import time
import json
from machine import Pin
import neopixel

NAME = "Kevin"
NEO_PIN = 15
NUM_PIXELS = 1

np = neopixel.NeoPixel(Pin(NEO_PIN), NUM_PIXELS)

buffer = b""
light_on = False
changed = False

def set_light(on):
    color = (0, 255, 0) if on else (0, 0, 0)
    for i in range(NUM_PIXELS):
        np[i] = color
    np.write()

def callback(data):
    # Only save the state here; the main loop does the NeoPixel write
    global buffer, light_on, changed
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        try:
            msg = json.loads(line.decode())
        except ValueError:
            continue
        print("Received:", msg)

        if "button" in msg:
            light_on = (msg["button"] == 1)
            changed = True
        elif "count" in msg:
            light_on = not light_on      # toggle on each count
            changed = True

# --- Startup test: should flash RED for 1 second ---
print("NeoPixel test on pin", NEO_PIN)
for i in range(NUM_PIXELS):
    np[i] = (255, 0, 0)
np.write()
time.sleep(1)
set_light(False)

p = None
try:
    p = Listen(NAME, verbose=False)
    p.callback = callback

    print("Looking for", NAME, "...")
    if p.connect_up():
        print("Connected")
        while p.is_connected:
            if changed:
                changed = False
                set_light(light_on)
                print("Light ->", "ON" if light_on else "OFF")
            time.sleep_ms(50)
    print("Lost connection")
finally:
    set_light(False)
    if p:
        p.disconnect()
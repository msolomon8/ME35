# station.py - STATION ESP32 (Cytron Robo ESP32, MicroPython)
# Save this as main.py on the station board so it starts on power-up.
# It waits for the car, replies "ACK,<id>", then shows the color on the NeoPixels + beeps.
# You do NOT need the car's MAC address - the station learns it from the car's first message.
import network, espnow, neopixel, time
from machine import Pin, PWM
 
# ---- Wi-Fi radio on, but NOT connected to any network (keeps both boards on the same channel) ----
w = network.WLAN(network.STA_IF)
w.active(True)
w.disconnect()
 
en = espnow.ESPNow()
en.active(True)
 
np   = neopixel.NeoPixel(Pin(15), 2)          # Robo ESP32 on-board NeoPixels
buzz = PWM(Pin(23), freq=1000, duty_u16=0)    # Robo ESP32 buzzer
 
COLORS = {'RED': (80, 0, 0), 'GREEN': (0, 80, 0), 'BLUE': (0, 0, 80)}
NOTES  = {'RED': 440, 'GREEN': 660, 'BLUE': 880}   # different beep for each color
 
def show(color):
    np[0] = np[1] = COLORS.get(color, (40, 40, 40)); np.write()
    buzz.freq(NOTES.get(color, 1000)); buzz.duty_u16(20000)
    time.sleep_ms(300)
    buzz.duty_u16(0)
    time.sleep_ms(700)
    np[0] = np[1] = (0, 0, 0); np.write()
 
# startup blink so you know it's running
np[0] = np[1] = (0, 20, 20); np.write(); time.sleep_ms(300)
np[0] = np[1] = (0, 0, 0); np.write()
print("Station ready - waiting for the car...")
 
known = set()
while True:
    host, msg = en.recv()                      # waits until a message arrives
    if not msg:
        continue
    try:
        color, mid = msg.decode().split(",")
    except (ValueError, UnicodeError):
        print("ignored message:", msg)
        continue
    if host not in known:                      # first message from the car -> remember it
        try: en.add_peer(host)
        except OSError: pass                   # already added
        known.add(host)
    en.send(host, "ACK," + mid)                # acknowledge FIRST so the car isn't kept waiting
    print("got", color, "#", mid, "-> ACK sent")
    show(color)                                # visible acknowledgement
 

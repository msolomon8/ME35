import network
import urequests
import time
 
#setting up SSID and password 
SSID = "tufts_eecs" #wifi name
PASSWORD = "foundedin1883" #wifi password

#function definition 
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
 
#function call
connect_wifi()

## connect using import connect_wifi

#if eecs doesn't work

#import network
#wlan = network.WLAN()
#mac = wlan.config("mac")
#print(mac)

#import ubinascii
#mac_readable = ubinascii.hexlify(mac,":").decode()
#print(mac_readable)

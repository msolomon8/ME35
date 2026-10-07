from machine import Pin, SoftI2C
import time
import math

button_Play = Pin(25, Pin.IN, Pin.PULL_UP)
button_Train = Pin(26, Pin.IN, Pin.PULL_UP)

i2c = SoftI2C(scl = Pin(22), sda = Pin(21))

print(i2c.scan())
import time


DEBOUNCE_MS = 200
last_press = 0

pressed_flag = False
STATE_PLAY = False
STATE_TRAIN = True

last_play = 0
last_train = 0

def playButton(p):
    global STATE_PLAY, STATE_TRAIN, last_play
    now = time.ticks_ms()
    if time.ticks_diff(now, last_play) < DEBOUNCE_MS or p.value() != 0:
        return
    last_play = now
    STATE_PLAY = True
    STATE_TRAIN = False

def trainButton(p):
    global STATE_TRAIN, pressed_flag, last_train
    now = time.ticks_ms()
    if time.ticks_diff(now, last_train) < DEBOUNCE_MS or p.value() != 0:
        return
    last_train = now
    STATE_TRAIN = True
    pressed_flag = True

button_Train.irq(trigger=Pin.IRQ_FALLING, handler=trainButton)
button_Play.irq(trigger=Pin.IRQ_FALLING, handler=playButton)



import veml6040
sensor = veml6040.VEML6040(i2c)

sensor.trigger_measurement()
   
def k_nearest_neighbor(x,y,z, k =1):
    distances = []
    for index, d in enumerate(data):
        dist = math.sqrt((x-d[0])**2+(y-d[1])**2+(z-d[2])**2)
        distances.append([dist,d[3]])
    
    distances.sort()
    distances = distances[:k] #get k distances
    classes = []
    for dist in distances:
        classes.append(dist[1])
    print("k classes", classes)
    most_number_of_closest_classes = max(set(classes), key = classes.count)
    print("max classes ", most_number_of_closest_classes)
    
    return most_number_of_closest_classes


       
data = []
color = ""
index = 0

while True:
    red, green, blue, white = sensor.read_rgbw()
    if(STATE_TRAIN and pressed_flag):
        print(red, green, blue, white)
        index = index+1
        if index <= 5:
            print("red train")
            color = "red"
        elif index >5 and index <= 10:
            print("green train")
            color = "green"
        elif index >10 and index <=15:
            print("blue train")
            color = "blue"
        else:
            print("no clue train")
            color = "no clue"

        data.append((red, green, blue, color))
        pressed_flag = False
           
    if(STATE_PLAY):
        what_class = k_nearest_neighbor(red, green, blue, 3)
        print(what_class)
        time.sleep(0.1)
        STATE_PLAY = False
    time.sleep(0.1)

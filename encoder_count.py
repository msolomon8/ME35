#IF you want to set up just the encoder use this
import encoder
import time
# or from encoder import Count
count = encoder.Count(32,39) 
# or count = encoder.Count(32,39)
while True:
    print(count.value())
    time.sleep(0.1)

# what do you get for one full rotation?

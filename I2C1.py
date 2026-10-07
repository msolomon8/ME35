from machine import Pin, I2C
i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
print(i2c.scan())
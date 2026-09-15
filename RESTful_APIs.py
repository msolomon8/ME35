#importing the libraries
import network
import urequests
import time

import connect_wifi

#ISS Position
ISS_URL = "http://api.open-notify.org/iss-now.json"

response = urequests.get(ISS_URL)
data = response.json()
response.close()

print(data)


#ON REPL you can type wlan.isconnected() hit ENTER. it will return True

METEO_URL = "api.meteomatics.com/validdatetime/parameters/locations/format?optionals"

weather = urequests.get(METEO_URL)
data_1= weather.json()
weather.close()

print(data_1)
#Examples of dictionaries
data = {"key":"value"} 
print(data["key"])

data1 = {"key1" : "value1", "key2" : "value2"}
print(data1["key1"])

data2 = [{"key1" : "A", "key2" : "B"}, {"key1" : "C", "key2" : "D"}]
print(data2[0]["key1"])

## values
student = {
    "name": "Alex",
    "score": 92,
    "passed": True
}

print(student["name"])
print(student["score"])
print(student["passed"])

## nested
robot = {
    "name": "Rover",
    "position": {
        "x": 12,
        "y": 7
    }
}

print(robot["name"])
print(robot["position"]["x"])
print(robot["position"]["y"])

## list

robot = {
    "name": "Rover",
    "sensors": ["distance", "temperature", "light"]
}

print(robot["sensors"][0])  # distance
print(robot["sensors"][2])  # light

## looping
motors = [
    {"name": "left", "speed": 50},
    {"name": "right", "speed": 60}
]

for motor in motors:
    print(motor["name"])
    print(motor["speed"])
    
## key
    sensor = {
    "type": "temperature",
    "value": 24.5
}

if "value" in sensor:
    print(sensor["value"])

if "unit" in sensor:
    print(sensor["unit"])
else:
    print("No unit was provided")
    
## get
sensor = {
    "type": "distance",
    "value": 35
}

print(sensor.get("value"))
print(sensor.get("unit", "cm"))

print("############")

## json
import json

json_text = """
{
    "robot": "ESP32 Rover",
    "speed": 45,
    "active": true
}
"""

data = json.loads(json_text)

print(data["robot"])
print(data["speed"])
print(data["active"])

print("############")

## parsing API
import json

json_text = """
{
    "location": {
        "latitude": 42.36,
        "longitude": -71.06
    },
    "timestamp": 1789500000
}
"""

data = json.loads(json_text)

latitude = data["location"]["latitude"]
longitude = data["location"]["longitude"]

print("Latitude:", latitude)
print("Longitude:", longitude)

print("############")

## API response with list
import json

json_text = """
{
    "readings": [
        {"sensor": "temperature", "value": 23.5},
        {"sensor": "distance", "value": 42},
        {"sensor": "light", "value": 680}
    ]
}
"""

data = json.loads(json_text)

for reading in data["readings"]:
    print(reading["sensor"], reading["value"])
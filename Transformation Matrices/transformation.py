# 2D rotation matrix
from math import cos, sin, pi
import math
# remember that the default angles will be in radians
θ =  math.pi/4 # try changing this value
R = [
    [cos(θ), -sin(θ)],
    [sin(θ),  cos(θ)]
]
print(R)

#####

x = 2
y = 3
p = [x, y]


theta_degrees = 90 #change this value
theta_radian = theta_degrees * pi / 180

p_rotated = [
    x*cos(theta_radian) - y*sin(theta_radian),
    x*sin(theta_radian) + y*cos(theta_radian)
]

print(p_rotated)

translation_x = 4
translation_y = 10

p_translated = [
    x + translation_x, y + translation_y
]

print(p_translated)
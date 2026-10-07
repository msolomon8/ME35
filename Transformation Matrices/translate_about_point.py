import numpy as np
import matplotlib.pyplot as plt

x = 10
y = 11
cx = 3
cy = 4
theta = np.radians(60)

point = np.array([x, y, 0])

def rotate_around_point(x, y, cx, cy, theta):
    # Translate to origin
    translation_matrix = np.array([
    [1,0,-cx],
    [0,1,-cy],
    [0,0,1]])
    
    translate_to_origin = translation_matrix @ point
    
    # Rotate
    rotation_matrix = np.array([
    [np.cos(theta), -np.sin(theta),0],
    [np.sin(theta), np.cos(theta),0],
    [0,0,1]])
    
    rotated_point = rotation_matrix @ translate_to_origin
    x_r = rotated_point[0]
    y_r = rotated_point[1]
    
    # Translate back
    x_final = x_r + cx
    y_final = y_r + cy
    
    return x_final, y_final

x_final, y_final = rotate_around_point(x, y, cx, cy, theta)
print(x_final, y_final)

### x=0.43, y=13.56 ###
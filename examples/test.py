# Creating a gear wheel
from jupytercad import CadDocument
import math

doc = CadDocument()

radius = 5
num_teeth = 15
tooth_width = 0.5

# Create the gear wheel body
body_radius = radius - tooth_width / 2
body_height = tooth_width
doc.add_cylinder(radius=body_radius, height=body_height)

# Create the teeth
tooth_angle = 2 * math.pi / num_teeth
for i in range(num_teeth):
    angle = i * tooth_angle
    doc.add_box(
        length=tooth_width,
        width=tooth_width,
        height=body_height,
        position=[(radius - tooth_width) * math.cos(angle), (radius - tooth_width) * math.sin(angle), 0],
        rotation_axis=[0, 0, 1],
        rotation_angle=angle * 180/math.pi
    ).cut()

# Create the central hole
hole_radius = radius * 0.3
hole_height = body_height
doc.add_cylinder(radius=hole_radius, height=hole_height).cut()
doc.export("test.glb")
doc
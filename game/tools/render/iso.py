"""The isometric camera shared by the Blender renders and the collision tool. Pure Python, no Blender.

World units are Kenney units: x along the back wall, y from the open front edge to the back wall, z up.
Image pixels are GBA pixels of the camera's rendered image (cam["size"]): x right, y down.
"""
import math

ELEV = 26.565        # degrees above the floor: 2:1 pixel dimetric
AZIM = 45.0          # the camera looks from +x, -y toward the back corner
SCREEN_W, SCREEN_H = 240, 160
SCALE = 4            # renders are made at 4x and shrunk by the converter


def axes():
    """World directions of screen-right and screen-up (unit vectors)."""
    a = math.radians(90 - ELEV)
    z = math.radians(AZIM)
    right = (math.cos(z), math.sin(z), 0.0)
    up = (-math.sin(z) * math.cos(a), math.cos(z) * math.cos(a), math.sin(a))
    return right, up


def project(cam, p):
    """World point -> image pixel (continuous: 0.0 is the left or top edge of the camera's image)."""
    right, up = axes()
    w, h = cam["size"]
    k = w / cam["ortho"]
    d = [p[i] - cam["target"][i] for i in range(3)]
    return (w / 2 + k * sum(d[i] * right[i] for i in range(3)),
            h / 2 - k * sum(d[i] * up[i] for i in range(3)))


def unproject_floor(cam, sx, sy, z=0.0):
    """Image pixel -> the world point at height z that projects there."""
    right, up = axes()
    w, h = cam["size"]
    k = w / cam["ortho"]
    t = cam["target"]
    a = (sx - w / 2) / k
    b = (h / 2 - sy) / k - up[2] * (z - t[2])
    det = right[0] * up[1] - right[1] * up[0]
    dx = (a * up[1] - right[1] * b) / det
    dy = (right[0] * b - up[0] * a) / det
    return (t[0] + dx, t[1] + dy, z)

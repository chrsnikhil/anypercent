"""The launcher's buttons, whatever device they come from."""
from enum import Enum


class Action(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    A = "a"
    B = "b"
    X = "x"                      # Square
    Y = "y"                      # Triangle
    L = "l"
    R = "r"
    START = "start"
    SELECT = "select"
    THEMES = "themes"            # the DualSense trick, Create + Options together: the theme picker

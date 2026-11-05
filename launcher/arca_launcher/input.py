"""Keyboard and gamepad events to launcher actions.

Pads SDL recognises (DualSense, DualShock, Xbox, 8BitDo and most others) use SDL's game controller mapping,
whatever their raw button numbers: bottom face button A, right face button B, shoulders L and R, Back /
Create / Share Select, Start / Options Start, the D-pad and the left stick to move.

Any other pad, or every pad when --joy-map is given, uses raw SDL joystick buttons: by default 0 A, 1 B, 4 L,
5 R, 6 Select, 7 Start, and the first hat or axes 0 and 1 for the D-pad. A held D-pad repeats; the keyboard
repeats by itself (pygame.key.set_repeat, set up by the app)."""
import pygame
import pygame._sdl2.controller as sdl_controller

from .actions import Action

KEYS = {
    pygame.K_UP: Action.UP, pygame.K_DOWN: Action.DOWN, pygame.K_LEFT: Action.LEFT, pygame.K_RIGHT: Action.RIGHT,
    pygame.K_x: Action.A, pygame.K_z: Action.B, pygame.K_c: Action.X, pygame.K_d: Action.Y,
    pygame.K_a: Action.L, pygame.K_s: Action.R, pygame.K_RETURN: Action.START, pygame.K_BACKSPACE: Action.SELECT,
}
JOY_BUTTONS = {0: Action.A, 1: Action.B, 4: Action.L, 5: Action.R, 6: Action.SELECT, 7: Action.START}
CONTROLLER_BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: Action.A, pygame.CONTROLLER_BUTTON_B: Action.B,
    pygame.CONTROLLER_BUTTON_X: Action.X, pygame.CONTROLLER_BUTTON_Y: Action.Y,
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: Action.L, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: Action.R,
}
# Back / Create / Share and Start / Options act when let go, so that both pressed together can be the theme
# trick (Action.THEMES) without either acting on its own first.
CONTROLLER_RELEASE = {pygame.CONTROLLER_BUTTON_BACK: Action.SELECT, pygame.CONTROLLER_BUTTON_START: Action.START}
CONTROLLER_DPAD = {
    pygame.CONTROLLER_BUTTON_DPAD_UP: Action.UP, pygame.CONTROLLER_BUTTON_DPAD_DOWN: Action.DOWN,
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: Action.LEFT, pygame.CONTROLLER_BUTTON_DPAD_RIGHT: Action.RIGHT,
}
CONTROLLER_STICK = {pygame.CONTROLLER_AXIS_LEFTX: 0, pygame.CONTROLLER_AXIS_LEFTY: 1}   # -> axes 0 and 1
AXIS_DEAD = 0.5
NAMES = {"a": Action.A, "b": Action.B, "l": Action.L, "r": Action.R, "start": Action.START, "select": Action.SELECT}
REPEAT_DELAY, REPEAT_EVERY = 300, 80


def parse_joy_map(text):
    """'a=0,b=1,l=4,r=5,select=6,start=7' -> {button number: Action}, for gamepads with another layout."""
    out = {}
    for part in text.split(","):
        name, sep, number = part.strip().partition("=")
        name = name.strip().lower()
        if not sep or name not in NAMES or not number.strip().isdigit():
            raise ValueError(f"bad joystick mapping {part.strip()!r}; use e.g. a=0,b=1,l=4,r=5,select=6,start=7")
        button = int(number)
        if button in out:
            raise ValueError(f"joystick button {button} is mapped twice")
        out[button] = NAMES[name]
    return out


class Inputs:
    def __init__(self, joy_buttons=None):
        self.joy_buttons = dict(JOY_BUTTONS if joy_buttons is None else joy_buttons)
        self.use_controllers = joy_buttons is None             # an explicit map means raw buttons for every pad
        self.sticks = {}
        self.controllers = {}                                  # joystick instance id -> open SDL game controller
        self.pad_held = set()                                  # Create / Options held down
        self.trick = False                                     # both were down together: neither acts on release
        if self.use_controllers:
            try:
                sdl_controller.init()
            except Exception:                                  # noqa: BLE001  no controller support: raw pads only
                self.use_controllers = False
        self.axes = {}
        self.held = None
        self.held_axis = None
        self.held_ms = 0
        self.next_repeat = REPEAT_DELAY

    def translate(self, ev):
        t = ev.type
        if t == pygame.KEYDOWN:
            return KEYS.get(ev.key)
        if t == pygame.JOYDEVICEADDED:
            self._open(ev.device_index)
            return None
        if t == pygame.JOYDEVICEREMOVED:
            self.sticks.pop(ev.instance_id, None)
            self.controllers.pop(ev.instance_id, None)
            self._release()
            return None
        if t == pygame.CONTROLLERBUTTONDOWN:
            if ev.button in CONTROLLER_RELEASE:
                self.pad_held.add(ev.button)
                if len(self.pad_held) == len(CONTROLLER_RELEASE):
                    self.trick = True
                    return Action.THEMES
                return None
            if ev.button in CONTROLLER_DPAD:
                self.held_axis = None
                return self._press(CONTROLLER_DPAD[ev.button])
            return CONTROLLER_BUTTONS.get(ev.button)
        if t == pygame.CONTROLLERBUTTONUP:
            if ev.button in CONTROLLER_RELEASE:
                was_held = ev.button in self.pad_held
                self.pad_held.discard(ev.button)
                if self.trick:
                    self.trick = bool(self.pad_held)
                    return None
                return CONTROLLER_RELEASE[ev.button] if was_held else None
            if CONTROLLER_DPAD.get(ev.button) is not None and self.held is CONTROLLER_DPAD[ev.button]:
                self._release()
            return None
        if t == pygame.CONTROLLERAXISMOTION:
            if ev.axis in CONTROLLER_STICK:
                return self._axis(CONTROLLER_STICK[ev.axis], ev.value / 32767)
            return None
        if getattr(ev, "instance_id", None) in self.controllers:
            return None                                        # its controller events above already cover it
        if t == pygame.JOYBUTTONDOWN:
            return self.joy_buttons.get(ev.button)
        if t == pygame.JOYHATMOTION:
            x, y = ev.value
            action = (Action.LEFT if x < 0 else Action.RIGHT if x > 0 else
                      Action.UP if y > 0 else Action.DOWN if y < 0 else None)
            if action is None:
                self._release()
                return None
            self.held_axis = None
            return self._press(action)
        if t == pygame.JOYAXISMOTION and ev.axis in (0, 1):
            return self._axis(ev.axis, ev.value)
        return None

    def rumble(self, low, high, ms):
        """Rumble every open controller (strengths 0..1); a pad that cannot is skipped."""
        for pad in self.controllers.values():
            try:
                pad.rumble(low, high, ms)
            except Exception:                                  # noqa: BLE001
                pass

    @property
    def pad_connected(self):
        """A gamepad or controller is open: games need no on-screen controls."""
        return bool(self.controllers or self.sticks)

    def scan(self):
        """Open every pad already connected. SDL's device-added event is lost when the joystick system starts
        before the display (as in the app), and one sent while a game runs is cleared: so the app scans at
        start and after every game."""
        for index in range(pygame.joystick.get_count()):
            self._open(index)

    def _open(self, index):
        """Open the pad at SDL device index `index` once, as a game controller if SDL knows its layout."""
        if self.use_controllers and sdl_controller.is_controller(index):
            pad = sdl_controller.Controller(index)
            self.controllers.setdefault(pad.as_joystick().get_instance_id(), pad)
            return
        stick = pygame.joystick.Joystick(index)
        self.sticks.setdefault(stick.get_instance_id(), stick)

    def _axis(self, axis, value):
        """Axis 0 (left / right) or 1 (up / down) at value -1..1: one move per push past the dead zone."""
        state = -1 if value < -AXIS_DEAD else 1 if value > AXIS_DEAD else 0
        if state == self.axes.get(axis, 0):
            return None
        self.axes[axis] = state
        if state == 0:
            if self.held_axis == axis:
                self._release()
            return None
        if axis == 0:
            action = Action.LEFT if state < 0 else Action.RIGHT
        else:
            action = Action.UP if state < 0 else Action.DOWN
        self.held_axis = axis
        return self._press(action)

    def _press(self, action):
        self.held, self.held_ms, self.next_repeat = action, 0, REPEAT_DELAY
        return action

    def _release(self):
        self.held = None
        self.held_axis = None

    def reset(self):
        """Forget any held direction: after a game its release may have been lost."""
        self._release()
        self.axes = {}
        self.pad_held, self.trick = set(), False

    def tick(self, dt_ms):
        """Repeats for a held gamepad direction, at most one per call so a stalled frame never bursts."""
        if self.held is None:
            return []
        self.held_ms += dt_ms
        if self.held_ms < self.next_repeat:
            return []
        self.held_ms = self.next_repeat
        self.next_repeat += REPEAT_EVERY
        return [self.held]

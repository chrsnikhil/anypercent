import pygame

from arca_launcher.actions import Action
from arca_launcher.input import REPEAT_DELAY, REPEAT_EVERY, Inputs


def ev(kind, **kw):
    return pygame.event.Event(kind, **kw)


def test_keyboard_uses_mgbas_layout():
    i = Inputs()
    keys = {pygame.K_UP: Action.UP, pygame.K_x: Action.A, pygame.K_z: Action.B, pygame.K_a: Action.L,
            pygame.K_s: Action.R, pygame.K_RETURN: Action.START, pygame.K_BACKSPACE: Action.SELECT}
    for key, action in keys.items():
        assert i.translate(ev(pygame.KEYDOWN, key=key)) is action
    assert i.translate(ev(pygame.KEYDOWN, key=pygame.K_q)) is None


def test_gamepad_buttons_follow_the_contract():
    i = Inputs()
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=0, instance_id=0)) is Action.A
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=7, instance_id=0)) is Action.START
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=9, instance_id=0)) is None


def test_button_map_can_be_replaced():
    i = Inputs(joy_buttons={2: Action.A})
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=2, instance_id=0)) is Action.A
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=0, instance_id=0)) is None


def test_held_hat_repeats_then_stops():
    i = Inputs()
    assert i.translate(ev(pygame.JOYHATMOTION, hat=0, value=(0, 1), instance_id=0)) is Action.UP
    assert i.tick(REPEAT_DELAY - 1) == []
    assert i.tick(1) == [Action.UP]
    assert i.tick(REPEAT_EVERY) == [Action.UP]
    assert i.tick(REPEAT_EVERY) == [Action.UP]
    assert i.translate(ev(pygame.JOYHATMOTION, hat=0, value=(0, 0), instance_id=0)) is None
    assert i.tick(1000) == []


def test_axis_fires_once_per_push_and_releases():
    i = Inputs()
    assert i.translate(ev(pygame.JOYAXISMOTION, axis=0, value=-0.9, instance_id=0)) is Action.LEFT
    assert i.translate(ev(pygame.JOYAXISMOTION, axis=0, value=-0.95, instance_id=0)) is None
    assert i.translate(ev(pygame.JOYAXISMOTION, axis=0, value=0.1, instance_id=0)) is None
    assert i.tick(1000) == []
    assert i.translate(ev(pygame.JOYAXISMOTION, axis=1, value=0.8, instance_id=0)) is Action.DOWN


def test_a_stalled_frame_repeats_only_once():
    i = Inputs()
    i.translate(ev(pygame.JOYHATMOTION, hat=0, value=(1, 0), instance_id=0))
    assert i.tick(5000) == [Action.RIGHT]              # never a burst of queued repeats
    assert i.tick(REPEAT_EVERY - 1) == []
    assert i.tick(1) == [Action.RIGHT]


def test_reset_forgets_a_held_direction():
    i = Inputs()
    i.translate(ev(pygame.JOYHATMOTION, hat=0, value=(1, 0), instance_id=0))
    i.translate(ev(pygame.JOYAXISMOTION, axis=1, value=0.9, instance_id=0))
    i.reset()
    assert i.tick(5000) == []
    assert i.translate(ev(pygame.JOYAXISMOTION, axis=1, value=0.9, instance_id=0)) is Action.DOWN   # axis state cleared too


def test_joy_map_from_the_command_line():
    import pytest
    from arca_launcher.input import parse_joy_map
    assert parse_joy_map("a=2, b=3,start=9") == {2: Action.A, 3: Action.B, 9: Action.START}
    for bad in ("a=x", "jump=1", "a2", "a=1,b=1"):
        with pytest.raises(ValueError):
            parse_joy_map(bad)


# --- recognised game controllers (DualSense, DualShock, Xbox, 8BitDo...) through SDL's controller mapping ------

class FakeStick:
    def __init__(self, iid):
        self.iid = iid

    def get_instance_id(self):
        return self.iid


class FakeController:
    def __init__(self, index):
        self.index = index

    def as_joystick(self):
        return FakeStick(100 + self.index)


def with_controller(monkeypatch, index=0):
    import arca_launcher.input as inp
    monkeypatch.setattr(inp.sdl_controller, "is_controller", lambda i: True)
    monkeypatch.setattr(inp.sdl_controller, "Controller", FakeController)
    i = Inputs()
    i.translate(ev(pygame.JOYDEVICEADDED, device_index=index))
    return i, 100 + index


def test_a_dualsense_uses_the_standard_layout(monkeypatch):
    i, iid = with_controller(monkeypatch)
    expect = {pygame.CONTROLLER_BUTTON_A: Action.A, pygame.CONTROLLER_BUTTON_B: Action.B,
              pygame.CONTROLLER_BUTTON_LEFTSHOULDER: Action.L, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: Action.R}
    for button, action in expect.items():
        assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=button, instance_id=iid)) is action
    for button, action in ((pygame.CONTROLLER_BUTTON_BACK, Action.SELECT), (pygame.CONTROLLER_BUTTON_START, Action.START)):
        assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=button, instance_id=iid)) is None     # on release
        assert i.translate(ev(pygame.CONTROLLERBUTTONUP, button=button, instance_id=iid)) is action
    assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=pygame.CONTROLLER_BUTTON_GUIDE, instance_id=iid)) is None


def test_square_and_triangle_have_actions(monkeypatch):
    i, iid = with_controller(monkeypatch)
    assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=pygame.CONTROLLER_BUTTON_X, instance_id=iid)) is Action.X
    assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=pygame.CONTROLLER_BUTTON_Y, instance_id=iid)) is Action.Y
    assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=pygame.CONTROLLER_BUTTON_GUIDE, instance_id=iid)) is None


def test_keyboard_square_and_triangle():
    i = Inputs()
    assert i.translate(ev(pygame.KEYDOWN, key=pygame.K_c)) is Action.X
    assert i.translate(ev(pygame.KEYDOWN, key=pygame.K_d)) is Action.Y


def test_a_controllers_raw_joystick_events_are_ignored(monkeypatch):
    """SDL sends both: acting on the raw ones too would press twice, and with the wrong numbers."""
    i, iid = with_controller(monkeypatch)
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=0, instance_id=iid)) is None
    assert i.translate(ev(pygame.JOYHATMOTION, hat=0, value=(0, 1), instance_id=iid)) is None
    assert i.translate(ev(pygame.JOYAXISMOTION, axis=0, value=-1.0, instance_id=iid)) is None
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=0, instance_id=7)) is Action.A      # another, plain pad


def test_controller_dpad_repeats_while_held_and_stops_on_release(monkeypatch):
    i, iid = with_controller(monkeypatch)
    up = pygame.CONTROLLER_BUTTON_DPAD_UP
    assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=up, instance_id=iid)) is Action.UP
    assert i.tick(REPEAT_DELAY) == [Action.UP]
    assert i.translate(ev(pygame.CONTROLLERBUTTONUP, button=up, instance_id=iid)) is None
    assert i.tick(1000) == []


def test_controller_left_stick_moves_once_per_push(monkeypatch):
    i, iid = with_controller(monkeypatch)
    x = pygame.CONTROLLER_AXIS_LEFTX
    assert i.translate(ev(pygame.CONTROLLERAXISMOTION, axis=x, value=-30000, instance_id=iid)) is Action.LEFT
    assert i.translate(ev(pygame.CONTROLLERAXISMOTION, axis=x, value=-32000, instance_id=iid)) is None
    assert i.translate(ev(pygame.CONTROLLERAXISMOTION, axis=x, value=500, instance_id=iid)) is None
    assert i.translate(ev(pygame.CONTROLLERAXISMOTION, axis=pygame.CONTROLLER_AXIS_LEFTY, value=31000,
                          instance_id=iid)) is Action.DOWN


def test_an_explicit_joy_map_keeps_raw_buttons_for_every_pad(monkeypatch):
    import arca_launcher.input as inp
    monkeypatch.setattr(inp.sdl_controller, "is_controller", lambda i: True)
    monkeypatch.setattr(inp.sdl_controller, "Controller", FakeController)
    monkeypatch.setattr(inp.pygame.joystick, "Joystick", FakeStick)      # raw path: a plain joystick, id = index
    i = Inputs(joy_buttons={3: Action.A})
    i.translate(ev(pygame.JOYDEVICEADDED, device_index=0))
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=3, instance_id=0)) is Action.A


def test_unplugging_a_controller_forgets_it(monkeypatch):
    i, iid = with_controller(monkeypatch)
    i.translate(ev(pygame.JOYDEVICEREMOVED, instance_id=iid))
    assert i.translate(ev(pygame.JOYBUTTONDOWN, button=0, instance_id=iid)) is Action.A


def test_scan_opens_pads_already_connected_without_waiting_for_an_event(monkeypatch):
    """SDL's device-added event is lost when the joystick system starts before the display, as in the app: so the
    app scans for pads itself at start and after every game."""
    import arca_launcher.input as inp
    monkeypatch.setattr(inp.sdl_controller, "is_controller", lambda i: True)
    monkeypatch.setattr(inp.sdl_controller, "Controller", FakeController)
    monkeypatch.setattr(inp.pygame.joystick, "get_count", lambda: 1)
    i = Inputs()
    i.scan()
    assert 100 in i.controllers
    assert i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=pygame.CONTROLLER_BUTTON_A, instance_id=100)) is Action.A


def test_a_pad_is_opened_once_whether_found_by_scan_or_by_event(monkeypatch):
    import arca_launcher.input as inp
    opened = []
    monkeypatch.setattr(inp.sdl_controller, "is_controller", lambda i: True)
    monkeypatch.setattr(inp.sdl_controller, "Controller", lambda idx: opened.append(idx) or FakeController(idx))
    monkeypatch.setattr(inp.pygame.joystick, "get_count", lambda: 1)
    i = Inputs()
    i.scan()
    i.scan()
    i.translate(ev(pygame.JOYDEVICEADDED, device_index=0))
    assert len(i.controllers) == 1


# --- the theme trick: Create + Options together, launcher only ---------------------------------------------------

def press(i, iid, button):
    return i.translate(ev(pygame.CONTROLLERBUTTONDOWN, button=button, instance_id=iid))


def release(i, iid, button):
    return i.translate(ev(pygame.CONTROLLERBUTTONUP, button=button, instance_id=iid))


def test_create_and_options_together_open_the_theme_menu(monkeypatch):
    i, iid = with_controller(monkeypatch)
    back, start = pygame.CONTROLLER_BUTTON_BACK, pygame.CONTROLLER_BUTTON_START
    assert press(i, iid, back) is None                     # held: it might be the start of the trick
    assert press(i, iid, start) is Action.THEMES
    assert release(i, iid, start) is None and release(i, iid, back) is None   # neither acts on its own after it


def test_options_alone_still_acts_on_release(monkeypatch):
    i, iid = with_controller(monkeypatch)
    start = pygame.CONTROLLER_BUTTON_START
    assert press(i, iid, start) is None
    assert release(i, iid, start) is Action.START
    back = pygame.CONTROLLER_BUTTON_BACK
    assert press(i, iid, back) is None
    assert release(i, iid, back) is Action.SELECT


def test_rumble_reaches_every_open_controller(monkeypatch):
    i, iid = with_controller(monkeypatch)
    got = []
    i.controllers[iid].rumble = lambda lo, hi, ms: got.append((lo, hi, ms)) or True
    i.rumble(0.5, 0.7, 120)
    assert got == [(0.5, 0.7, 120)]

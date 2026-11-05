"""The touch-to-gamepad service (arca_launcher/touchpad.py): multitouch on the panel -> keys RetroArch maps."""
import os

import pytest

from conftest import LAUNCHER_DIR
from arca_launcher import touchpad as tp

REPO = os.path.dirname(LAUNCHER_DIR)
OVERLAY = os.path.join(REPO, "device", "overlay", "gamepad.cfg")
RA_CFG = os.path.join(REPO, "device", "retroarch.cfg")

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, SYN_DROPPED = 0, 3
SLOT, TID, MX, MY = 0x2F, 0x39, 0x35, 0x36
K = {"up": 103, "down": 108, "left": 105, "right": 106, "a": 45, "b": 44, "l": 30, "r": 31,
     "start": 28, "select": 14}

# panel pixels of the committed overlay's controls
DPAD = {(-1, -1): (32, 324), (0, -1): (80, 324), (1, -1): (128, 324),
        (-1, 0): (32, 372), (0, 0): (80, 372), (1, 0): (128, 372),
        (-1, 1): (32, 420), (0, 1): (80, 420), (1, 1): (128, 420)}
A, B, START, SELECT, L, R = (738, 318), (660, 382), (448, 460), (352, 460), (66, 29), (734, 29)
NOWHERE = (400, 200)


@pytest.fixture(scope="module")
def pad():
    return tp.Pad(tp.load_overlay(OVERLAY))


class Keys:
    """Records what the service sends to the virtual keyboard: one list of (key, value) per SYN."""

    def __init__(self):
        self.frames = []
        self.down = set()

    def send(self, changes):
        self.frames.append(list(changes))
        for code, value in changes:
            (self.down.add if value else self.down.discard)(code)


class Panel:
    """Writes type B multitouch frames the way the ft5x06 driver (through the input core) reports them."""

    def __init__(self, service):
        self.s = service
        self.slot = 0
        self.last = {}                                 # slot -> (x, y) as last sent: the core drops repeats
        self.next_id = 100

    def _slot(self, slot):
        if slot != self.slot:
            self.s.event(EV_ABS, SLOT, slot)
            self.slot = slot

    def _pos(self, slot, x, y):
        lx, ly = self.last.get(slot, (None, None))
        if x != lx:
            self.s.event(EV_ABS, MX, x)
        if y != ly:
            self.s.event(EV_ABS, MY, y)
        self.last[slot] = (x, y)

    def frame(self, **fingers):
        """fingers: s0=(x, y) puts or moves finger in slot 0, s1=None lifts slot 1."""
        for name, where in fingers.items():
            slot = int(name[1:])
            self._slot(slot)
            if where is None:
                self.s.event(EV_ABS, TID, -1)
            else:
                if not getattr(self, f"_down{slot}", False):
                    self.s.event(EV_ABS, TID, self.next_id)
                    self.next_id += 1
                self._pos(slot, *where)
            setattr(self, f"_down{slot}", where is not None)
        self.s.event(EV_SYN, SYN_REPORT, 0)


@pytest.fixture
def rig(pad):
    keys = Keys()
    service = tp.Touchpad(pad, keys.send)
    return service, Panel(service), keys


def names(codes):
    inv = {v: k for k, v in K.items()}
    return {inv[c] for c in codes}


# --- the overlay's hitboxes are the geometry -------------------------------------------------------------------

def test_every_overlay_button_has_a_key():
    boxes = tp.load_overlay(OVERLAY)
    assert len(boxes) == 14
    for box in boxes:
        for b in box.buttons:
            assert b in tp.KEYS, b


def test_keys_are_the_ones_retroarch_maps_for_player_one():
    """device/retroarch.cfg maps the keyboard to player 1; the service presses exactly those keys."""
    ra = {}
    for line in open(RA_CFG):
        if line.startswith("input_player1_") and "=" in line:
            k, v = line.split("=", 1)
            ra[k.strip()[len("input_player1_"):]] = v.strip().strip('"')
    linux = {"up": 103, "down": 108, "left": 105, "right": 106, "x": 45, "z": 44, "a": 30, "s": 31,
             "enter": 28, "backspace": 14}
    for button, code in tp.KEYS.items():
        assert linux[ra[button]] == code, button


def test_parse_reads_names_centres_shapes_and_ranges():
    boxes = tp.parse_overlay('overlay0_descs = 2\n'
                             'overlay0_desc0 = "up|left,0.1,0.5,rect,0.05,0.1"\n'
                             'overlay0_desc1 = "a,0.9,0.5,radial,0.05,0.1"\n'
                             'overlay0_desc1_overlay = "x.png"\n')
    assert [b.buttons for b in boxes] == [("up", "left"), ("a",)]
    assert boxes[1].shape == "radial" and boxes[0].x == pytest.approx(0.1) and boxes[1].ry == pytest.approx(0.1)


def test_rect_and_radial_hit_tests():
    rect = tp.Hitbox(("up",), 0.5, 0.5, "rect", 0.1, 0.1)
    assert rect.contains(0.59, 0.41) and not rect.contains(0.61, 0.5)
    disc = tp.Hitbox(("a",), 0.5, 0.5, "radial", 0.1, 0.1)
    assert disc.contains(0.55, 0.55) and not disc.contains(0.59, 0.59)       # inside the square, outside the disc


def test_dpad_grid_with_diagonals_and_a_dead_centre(pad):
    for (dx, dy), (x, y) in DPAD.items():
        want = set()
        if dx:
            want.add("left" if dx < 0 else "right")
        if dy:
            want.add("up" if dy < 0 else "down")
        assert set(pad.buttons_at(x, y)) == want, (dx, dy)


def test_buttons_and_nowhere(pad):
    for where, name in ((A, "a"), (B, "b"), (START, "start"), (SELECT, "select"), (L, "l"), (R, "r")):
        assert set(pad.buttons_at(*where)) == {name}
    assert not pad.buttons_at(*NOWHERE)
    assert not pad.buttons_at(A[0] - 60, A[1])                                # A's disc is 44 px


def test_missing_overlay_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        tp.parse_overlay("overlays = 1\n")


# --- fingers ---------------------------------------------------------------------------------------------------

def test_single_touch_press_and_lift(rig):
    s, panel, keys = rig
    panel.frame(s0=A)
    assert names(keys.down) == {"a"} and keys.frames[-1] == [(K["a"], 1)]
    panel.frame(s0=None)
    assert not keys.down and keys.frames[-1] == [(K["a"], 0)]


def test_hold_dpad_and_mash_a_with_a_second_finger(rig):
    s, panel, keys = rig
    panel.frame(s0=DPAD[(1, 0)])
    for _ in range(3):
        panel.frame(s1=A)
        assert names(keys.down) == {"right", "a"}
        panel.frame(s1=None)
        assert names(keys.down) == {"right"}
    releases = [c for f in keys.frames for c, v in f if v == 0]
    assert K["right"] not in releases                                          # held throughout
    panel.frame(s0=None)
    assert not keys.down


def test_both_fingers_down_in_one_report(rig):
    s, panel, keys = rig
    panel.frame(s0=DPAD[(-1, 0)], s1=B)
    assert names(keys.down) == {"left", "b"} and len(keys.frames) == 1


def test_sliding_across_the_dpad_changes_direction(rig):
    s, panel, keys = rig
    panel.frame(s0=DPAD[(0, 0)])
    assert not keys.down and not keys.frames                                   # the centre presses nothing
    panel.frame(s0=DPAD[(1, 0)])
    assert names(keys.down) == {"right"}
    panel.frame(s0=DPAD[(1, 1)])
    assert names(keys.down) == {"right", "down"} and keys.frames[-1] == [(K["down"], 1)]
    panel.frame(s0=DPAD[(0, 1)])
    assert names(keys.down) == {"down"} and keys.frames[-1] == [(K["right"], 0)]
    panel.frame(s0=DPAD[(-1, 1)])
    assert names(keys.down) == {"down", "left"}


def test_sliding_off_a_button_releases_it(rig):
    s, panel, keys = rig
    panel.frame(s0=A)
    panel.frame(s0=NOWHERE)
    assert not keys.down
    panel.frame(s0=A)                                                          # and back on presses it again
    assert names(keys.down) == {"a"}


def test_two_fingers_on_one_button_hold_it_until_both_lift(rig):
    s, panel, keys = rig
    panel.frame(s0=START)
    panel.frame(s1=(START[0] + 10, START[1]))
    panel.frame(s0=None)
    assert names(keys.down) == {"start"}
    panel.frame(s1=None)
    assert not keys.down
    assert sum(1 for f in keys.frames for c, v in f if c == K["start"] and v == 1) == 1


def test_select_and_start_together(rig):
    """Two thumbs on Select + Start: RetroArch's quit combo."""
    s, panel, keys = rig
    panel.frame(s0=SELECT, s1=START)
    assert names(keys.down) == {"select", "start"}


ESC = 1


def test_l_and_r_together_hold_escape_to_quit_to_the_launcher(rig):
    """L + R on the overlay quits the game: Esc (input_exit_emulator) is held while both are down, so RetroArch
    sees it on its next poll, and let go as soon as either lifts."""
    s, panel, keys = rig
    panel.frame(s0=L)
    assert ESC not in keys.down
    panel.frame(s1=R)
    assert ESC in keys.down and {K["l"], K["r"]} <= keys.down
    panel.frame(s1=None)
    assert ESC not in keys.down and K["l"] in keys.down


def test_l_or_r_alone_never_sends_escape(rig):
    s, panel, keys = rig
    panel.frame(s0=R)
    panel.frame(s0=None)
    panel.frame(s0=L)
    assert all(c != ESC for f in keys.frames for c, v in f)


def test_a_new_contact_where_the_last_one_lifted_is_still_placed(rig):
    """The input core drops a position equal to the slot's last one, so a new finger at the old spot sends none."""
    s, panel, keys = rig
    panel.frame(s0=A)
    panel.frame(s0=None)
    panel.frame(s0=A)                                                          # TID only, no X/Y events
    assert names(keys.down) == {"a"}


def test_nothing_is_sent_when_nothing_changes(rig):
    s, panel, keys = rig
    panel.frame(s0=A)
    panel.frame(s0=(A[0] + 3, A[1] + 2))
    panel.frame(s0=(A[0] + 5, A[1] - 2))
    assert len(keys.frames) == 1


def test_ten_slots(rig):
    s, panel, keys = rig
    panel.frame(**{f"s{i}": NOWHERE for i in range(10)})
    panel.frame(s9=A)
    assert names(keys.down) == {"a"}


def test_release_all_lets_go_of_everything(rig):
    s, panel, keys = rig
    panel.frame(s0=DPAD[(1, -1)], s1=A)
    s.release_all()
    assert not keys.down
    s.release_all()                                                            # twice sends nothing more
    assert keys.frames[-1] and len([f for f in keys.frames if not f]) == 0


def test_starts_on_the_slot_the_panel_is_on(pad):
    keys = Keys()
    s = tp.Touchpad(pad, keys.send, slot=3)
    s.event(EV_ABS, TID, 7)
    s.event(EV_ABS, MX, A[0])
    s.event(EV_ABS, MY, A[1])
    s.event(EV_SYN, SYN_REPORT, 0)
    assert s.fingers() == {3: A}


def test_dropped_events_resync_from_the_panel(pad):
    keys = Keys()
    state = {"slot": 1, "slots": {0: (5, DPAD[(1, 0)]), 1: (6, A)}}          # slot -> (tracking id, (x, y))
    s = tp.Touchpad(pad, keys.send, resync=lambda: (state["slot"], state["slots"]))
    s.event(EV_ABS, TID, 9)
    s.event(EV_ABS, MX, B[0])
    s.event(EV_SYN, SYN_DROPPED, 0)
    s.event(EV_ABS, MX, 1)                                                     # ignored until the next report
    s.event(EV_SYN, SYN_REPORT, 0)
    assert names(keys.down) == {"right", "a"}
    s.event(EV_ABS, TID, -1)                                                   # the resync put us on slot 1
    s.event(EV_SYN, SYN_REPORT, 0)
    assert names(keys.down) == {"right"}


def test_other_events_are_ignored(rig):
    s, panel, keys = rig
    s.event(EV_KEY, 0x14A, 1)                                                  # BTN_TOUCH
    s.event(EV_ABS, 0, 738)                                                    # ABS_X (single-touch emulation)
    s.event(EV_SYN, SYN_REPORT, 0)
    assert not keys.frames


def test_decode_events_from_bytes():
    raw = b"".join(tp.EVENT.pack(1, 2, EV_ABS, MX, 5) for _ in range(3))
    assert list(tp.decode(raw)) == [(1.000002, EV_ABS, MX, 5)] * 3
    assert list(tp.decode(raw[:-3])) == [(1.000002, EV_ABS, MX, 5)] * 2       # a torn tail is dropped


# --- the process the launcher starts around a game -------------------------------------------------------------

def fake_service(body):
    import sys
    return [sys.executable, "-c", body]


def test_start_waits_for_ready_and_stop_ends_the_process():
    import time
    t = time.monotonic()
    svc = tp.start("/o/gamepad.cfg", cmd=fake_service("import time; time.sleep(0.2); print('ready', flush=True); "
                                                       "time.sleep(60)"))
    assert svc.ready and time.monotonic() - t < 5
    svc.stop()
    assert svc.proc.poll() is not None


def test_start_gives_up_waiting_but_still_returns():
    import time
    t = time.monotonic()
    svc = tp.start("/o/gamepad.cfg", cmd=fake_service("import time; time.sleep(60)"), timeout=0.5)
    assert not svc.ready and time.monotonic() - t < 3
    svc.stop()
    assert svc.proc.poll() is not None


def test_a_service_that_exits_at_once_is_not_ready():
    svc = tp.start("/o/gamepad.cfg", cmd=fake_service("raise SystemExit(2)"))
    assert not svc.ready
    svc.stop()                                                                 # harmless


def test_stop_kills_a_service_that_ignores_sigterm():
    svc = tp.start("/o/gamepad.cfg", cmd=fake_service(
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); "
        "time.sleep(60)"))
    svc.stop(grace=0.5)
    assert svc.proc.poll() is not None


def test_default_command_runs_this_module():
    import sys
    cmd = tp.command("/o/gamepad.cfg")
    assert cmd == [sys.executable, "-m", "arca_launcher.touchpad", "/o/gamepad.cfg"]

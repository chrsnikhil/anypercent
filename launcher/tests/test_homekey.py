"""device/homekey.py: hold the controller's PS button for 2 s to get back to the launcher from anything."""
import importlib.util
import os

from conftest import LAUNCHER_DIR

spec = importlib.util.spec_from_file_location("homekey", os.path.join(os.path.dirname(LAUNCHER_DIR), "device", "homekey.py"))
hk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hk)


def test_a_two_second_hold_fires_once():
    h = hk.Hold(2.0)
    h.key(True, 10.0)
    assert not h.due(11.9)
    assert h.due(12.0)
    assert not h.due(13.0)                      # once per hold, however long it is held


def test_letting_go_early_does_nothing():
    h = hk.Hold(2.0)
    h.key(True, 10.0)
    h.key(False, 11.0)
    assert not h.due(13.0)


def test_a_new_press_starts_a_new_hold():
    h = hk.Hold(2.0)
    h.key(True, 0.0)
    assert h.due(2.0)
    h.key(False, 2.5)
    h.key(True, 3.0)
    assert not h.due(4.9)
    assert h.due(5.0)


def test_the_wait_until_due_bounds_the_select_timeout():
    h = hk.Hold(2.0)
    assert h.wait(5.0) is None                  # nothing held: wait for input
    h.key(True, 5.0)
    assert h.wait(5.5) == 1.5


def test_an_app_comes_before_a_game():
    assert hk.choose({"anypercent-gta3.service"}, [123]) == ("stop", "anypercent-gta3.service")
    assert hk.choose({"anypercent-browser.service"}, []) == ("stop", "anypercent-browser.service")
    assert hk.choose(set(), [123]) == ("term", 123)
    # already in the launcher: restart it, the way out of a frozen or black launcher
    assert hk.choose(set(), []) == ("restart", "anypercent-launcher.service")


def test_emulators_are_found_by_process_name(tmp_path):
    for pid, comm in ((101, "python3"), (202, "retroarch"), (303, "bash"), (404, "mgba-qt")):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "comm").write_text(comm + "\n")
    (tmp_path / "self").mkdir()
    assert sorted(hk.emulator_pids(str(tmp_path))) == [202, 404]


def test_a_device_with_a_ps_button_is_recognised():
    # capabilities/key: 64-bit words, most significant first; BTN_MODE is 316 (bit 60 of word 4 from the right)
    words = ["0"] * 5
    words[0] = format(1 << (316 - 256), "x")
    assert hk.has_key(" ".join(words), 316)
    assert not hk.has_key("0 0 0 0 0", 316)
    assert not hk.has_key("ffff", 316)          # too short to hold that bit


def test_going_home_leaves_a_mark_so_the_launcher_knows_it_was_on_purpose(tmp_path):
    calls = []
    action = hk.go_home(str(tmp_path), active=lambda: {"anypercent-browser.service"}, pids=lambda: [],
                        stop=calls.append, term=lambda pid: None, now=lambda: 1234.5)
    assert action == ("stop", "anypercent-browser.service")
    assert calls == ["anypercent-browser.service"]
    assert (tmp_path / "home-quit").read_text().strip() == "1234.5"


def test_holding_it_in_the_launcher_restarts_the_launcher(tmp_path):
    calls = []
    action = hk.go_home(str(tmp_path), active=set, pids=list, stop=None, term=None, now=lambda: 0,
                        restart=calls.append)
    assert action == ("restart", "anypercent-launcher.service")
    assert calls == ["anypercent-launcher.service"]


def test_an_emulator_is_asked_to_quit_so_it_saves_its_place():
    sent, killed = [], []
    alive = iter([True, False])                        # gone after the first check
    hk.quit_emulator(42, send=sent.append, alive=lambda pid: next(alive), kill=killed.append, wait=1.0, step=0)
    assert sent == [b"QUIT"] and killed == []


def test_an_emulator_that_ignores_quit_is_ended_anyway():
    sent, killed = [], []
    hk.quit_emulator(42, send=sent.append, alive=lambda pid: True, kill=killed.append, wait=0.0, step=0)
    assert sent == [b"QUIT"] and killed == [42]


def test_ps_plus_dpad_steps_volume_and_brightness():
    h = hk.Hold(2.0)
    h.key(True, 0.0)
    assert h.hat(17, -1) == ("volume", +1)       # up
    assert h.hat(17, 0) is None                   # the release of the press
    assert h.hat(17, 1) == ("volume", -1)         # down
    assert h.hat(16, 1) == ("brightness", +1)     # right
    assert h.hat(16, -1) == ("brightness", -1)    # left
    assert not h.due(5.0)                          # used for a combo: no trip home when it is let go


def test_the_dpad_alone_is_left_to_the_game():
    h = hk.Hold(2.0)
    assert h.hat(17, -1) is None


def test_levels_step_and_clamp(tmp_path):
    lv = {"volume": 95, "brightness": 15}
    assert hk.step(lv, "volume", +1) == {"volume": 100, "brightness": 15}
    assert hk.step(lv, "brightness", -1) == {"volume": 95, "brightness": 10}   # never dark: 10% floor
    assert hk.step({"volume": 3, "brightness": 50}, "volume", -1)["volume"] == 0


def test_levels_start_from_the_launchers_settings_and_are_shared(tmp_path):
    state = tmp_path / "state.json"
    state.write_text('{"volume": 40, "brightness": 70}')
    run = tmp_path / "run"
    lv = hk.load_levels(str(run), str(state))
    assert lv == {"volume": 40, "brightness": 70}
    hk.save_levels(str(run), {"volume": 50, "brightness": 70}, now=12.5)
    import json
    assert json.loads((run / "levels").read_text()) == {"volume": 50, "brightness": 70, "changed": 12.5}
    assert hk.load_levels(str(run), str(state)) == {"volume": 50, "brightness": 70}   # the newest wins


def test_volume_keeps_the_0db_ceiling_and_brightness_writes_the_backlight(tmp_path):
    calls = []
    hk.apply_volume(100, run=lambda cmd: calls.append(cmd))
    assert calls[0][-1] == "96%"                  # the launcher's ceiling: 100% is 0 dB
    bl = tmp_path / "bl"
    bl.mkdir()
    (bl / "max_brightness").write_text("255\n")
    (bl / "brightness").write_text("0\n")
    hk.apply_brightness(50, str(bl))
    assert (bl / "brightness").read_text().strip() == "128"


def test_a_quick_tap_of_ps_is_a_tap():
    h = hk.Hold(2.0)
    h.key(True, 10.0)
    assert h.key(False, 10.3) == "tap"


def test_a_long_press_or_a_combo_is_not_a_tap():
    h = hk.Hold(2.0)
    h.key(True, 0.0)
    assert h.key(False, 1.0) is None                   # held too long for a tap, too short to go home
    h.key(True, 5.0)
    h.hat(17, -1)
    assert h.key(False, 5.2) is None                   # a level step, not a tap


class Box:
    def __init__(self):
        self.calls = []


def make_sleeper(box, brightness=70, playing=True):
    return hk.Sleeper(set_brightness=lambda v: box.calls.append(("bright", v)),
                      pause=lambda: box.calls.append(("pause",)),
                      cpu=lambda mode: box.calls.append(("cpu", mode)),
                      brightness=lambda: brightness, playing=lambda: playing)


def test_sleep_turns_the_screen_off_pauses_and_slows_down():
    box = Box()
    s = make_sleeper(box)
    s.toggle()
    assert s.asleep
    assert box.calls == [("pause",), ("bright", 0), ("cpu", "powersave")]


def test_waking_puts_everything_back():
    box = Box()
    s = make_sleeper(box, brightness=70)
    s.toggle()
    box.calls.clear()
    s.wake()
    assert not s.asleep
    assert box.calls == [("cpu", "ondemand"), ("bright", 70), ("pause",)]   # the pause toggles back off


def test_sleep_in_the_launcher_does_not_pause_anything():
    box = Box()
    s = make_sleeper(box, playing=False)
    s.toggle()
    s.wake()
    assert ("pause",) not in box.calls

"""dev/record.py: the shot script's parser, the recorder's step loop (on a fake app and a fake clock), the copy of the
console's state it runs on, and the guard on real sponsor writes."""
import importlib.util
import json
import os
import stat

import pytest

from conftest import LAUNCHER_DIR
from arca_launcher.actions import Action
from arca_launcher.library import Game
from arca_launcher.model import Nav, Screen

spec = importlib.util.spec_from_file_location("record", os.path.join(LAUNCHER_DIR, "dev", "record.py"))
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)


# ---- the parser ------------------------------------------------------------------------------------------------------

def test_a_bare_list_is_a_script_with_every_default():
    s = rec.parse_script([{"press": "triangle"}, {"wait_ms": 1500}, {"mark": "scout_card"}])
    assert [st.kind for st in s.steps] == ["press", "wait", "mark"]
    assert s.steps[0].value is Action.Y and s.steps[0].times == 1
    assert s.steps[1].value == 1500 and s.steps[2].value == "scout_card"
    assert (s.name, s.splash, s.greet, s.warm_up, s.real_writes, s.launch_hold_ms) == (
        None, False, False, None, False, rec.LAUNCH_HOLD_MS)


def test_an_object_carries_its_options():
    s = rec.parse_script({"name": "scout-1", "splash": True, "greet": True, "warm_up": False, "real_writes": True,
                          "launch_hold_ms": 500, "steps": [{"until_state": "scout_pick", "timeout_ms": 60000}]})
    assert (s.name, s.splash, s.greet, s.warm_up, s.real_writes, s.launch_hold_ms) == (
        "scout-1", True, True, False, True, 500)
    assert s.steps[0].kind == "until_state" and s.steps[0].value == "scout_pick" and s.steps[0].timeout_ms == 60000


@pytest.mark.parametrize("name, action", [
    ("up", Action.UP), ("down", Action.DOWN), ("left", Action.LEFT), ("right", Action.RIGHT),
    ("cross", Action.A), ("circle", Action.B), ("square", Action.X), ("triangle", Action.Y),
    ("l1", Action.L), ("r1", Action.R), ("options", Action.START), ("create", Action.SELECT),
    (" Triangle ", Action.Y)])
def test_every_button_by_its_pad_name(name, action):
    assert rec.parse_step({"press": name}, 1).value is action


def test_presses_repeat_every_ms_apart():
    st = rec.parse_step({"press": "down", "times": 4, "every_ms": 1800}, 1)
    assert (st.times, st.every_ms) == (4, 1800)
    assert rec.parse_step({"press": "down", "times": 2}, 1).every_ms == rec.PRESS_EVERY_MS


def test_waits_default_their_timeout_and_screens_match_any_case():
    assert rec.parse_step({"until_state": "board"}, 1).timeout_ms == rec.UNTIL_MS
    assert rec.parse_step({"until_screen": "handler"}, 1).value is Screen.HANDLER
    assert rec.parse_step({"until_screen": "HANDLER"}, 1).value is Screen.HANDLER
    assert rec.parse_step({"until_ready": True}, 1).kind == "until_ready"
    assert rec.parse_step({"select": "marine-drive-gp"}, 1).every_ms == rec.SELECT_EVERY_MS
    assert rec.parse_step({"pick": "BOT-A2"}, 1).value == "BOT-A2"


@pytest.mark.parametrize("steps, said", [
    ([{"press": "jump"}], "step 1: press 'jump' is not a button"),
    ([{"wait_ms": 10}, {"until_state": "scout_pik"}], "step 2: 'scout_pik' is not one of PB's states"),
    ([{"until_screen": "STORE"}], "step 1: 'STORE' is not a screen"),
    ([{"wait_ms": -5}], "step 1: wait_ms must be a number"),
    ([{"wait_ms": True}], "step 1: wait_ms must be a number"),
    ([{"press": "cross", "wait_ms": 100}], "step 1: needs exactly one of"),
    ([{"hold": "cross"}], "step 1: needs exactly one of"),
    ([{"press": "cross", "timeout_ms": 100}], "step 1: press does not take timeout_ms"),
    ([{"press": "cross", "times": 0}], "step 1: times must be"),
    ([{"until_state": "board", "timeout_ms": 0}], "step 1: timeout_ms must be"),
    ([{"until_ready": "yes"}], "step 1: until_ready takes true"),
    ([{"mark": ""}], "step 1: a mark needs a name"),
    (["cross"], "step 1: a step is an object"),
])
def test_a_bad_step_is_named_with_its_number(steps, said):
    with pytest.raises(rec.ScriptError, match=said.replace("(", r"\(")):
        rec.parse_script(steps)


@pytest.mark.parametrize("script, said", [
    ([], "no steps"), ({"steps": []}, "no steps"), ("press cross", "a list of steps"),
    ({"steps": [{"wait_ms": 1}], "fps": 60}, "unknown option fps"),
    ({"steps": [{"wait_ms": 1}], "splash": "no"}, "splash is true or false"),
    ({"steps": [{"wait_ms": 1}], "name": "../x"}, "name is a file name")])
def test_a_bad_script_says_why(script, said):
    with pytest.raises(rec.ScriptError, match=said):
        rec.parse_script(script)


def test_frames_cover_the_wait():
    assert [rec.frames_for(ms) for ms in (0, 1, 33, 1000, 1500)] == [0, 1, 1, 30, 45]


# ---- the step loop ---------------------------------------------------------------------------------------------------

class FakeClock:
    """The wall clock, moved only by sleep: the recorder's pacing costs nothing."""

    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


class FakeApp:
    """A real Nav over a few games, a frame that applies its buttons (Triangle on a game opens a fake PB flow) and a
    screen that is the frame's number."""

    def __init__(self, launch_on=None):
        self.nav = Nav([Game(id=g, title=g.upper()) for g in ("zip", "rush", "mdgp")])
        self.frames, self.pressed, self.dts = 0, [], []
        self.launched = self.launch_card = None
        self.launch_on = launch_on
        self.waiting = []

    def frame(self, dt, actions=(), touches=()):
        self.dts.append(dt)
        for a in actions:
            self.pressed.append((self.frames, a))
            if a is self.launch_on:
                self.launched, self.launch_card = {"game": "mdgp"}, b"card"
            else:
                self.nav.apply(a)
        self.frames += 1

    def capture(self):
        return b"frame %d" % self.frames

    def waiting_for(self):
        return list(self.waiting)


class Sink:
    def __init__(self):
        self.frames = []

    def put(self, rgb):
        self.frames.append(rgb)


def play(steps, app=None, **options):
    app = app or FakeApp()
    clock, sink = FakeClock(), Sink()
    r = rec.Recorder(app, rec.parse_script(dict(options, steps=steps)), sink, clock=clock, sleep=clock.sleep)
    return r, app, sink, clock


def test_a_press_lands_on_the_next_frame_and_waits_fill_their_time():
    r, app, sink, clock = play([{"wait_ms": 1000}, {"press": "right"}, {"mark": "after"}, {"wait_ms": 500}])
    r.run()
    assert app.pressed == [(30, Action.RIGHT)]
    assert len(sink.frames) == r.k == 30 + 1 + 15
    assert r.marks == [{"mark": "after", "frame": 31, "t": round(31 / 30, 3)}]
    assert sum(app.dts) == 1533                    # 46 frames of 1/30 s, whole ms that add up
    assert clock.now == pytest.approx(100.0 + 45 / 30)   # frame k is never drawn before its time
    assert [s["frames"] for s in r.log] == [[0, 30], [30, 31], [31, 31], [31, 46]]


def test_repeated_presses_are_every_ms_apart():
    r, app, sink, _ = play([{"press": "right", "times": 3, "every_ms": 100}])
    r.run()
    assert [f for f, _ in app.pressed] == [0, 4, 8]


def test_an_until_that_never_comes_fails_with_the_frames_kept():
    r, app, sink, _ = play([{"wait_ms": 100}, {"until_state": "scout_pick", "timeout_ms": 2000}])
    with pytest.raises(rec.ShotFailed, match="'scout_pick' screen did not come in 2.0 s .on HOME"):
        r.run()
    assert len(sink.frames) == 3 + 60
    assert r.log[-1]["frames"] == [3, 63]


def test_until_screen_and_until_ready_stop_as_soon_as_they_hold():
    app = FakeApp()
    app.waiting = ["the MDGP board"]
    r, app, sink, _ = play([{"until_ready": True, "timeout_ms": 1000}], app=app)
    with pytest.raises(rec.ShotFailed, match="still waiting for the MDGP board"):
        r.run()
    r, app, sink, _ = play([{"until_screen": "home"}, {"until_ready": True}])
    r.run()
    assert sink.frames == []                       # both held at once: nothing to wait for


def test_select_moves_along_home_until_the_game():
    r, app, sink, _ = play([{"select": "ZIP", "every_ms": 100}, {"select": "mdgp"}])   # Home: MDGP RUSH ZIP
    r.run()
    assert app.nav.selected.id == "mdgp"
    assert [a for _, a in app.pressed] == [Action.RIGHT, Action.RIGHT, Action.LEFT, Action.LEFT]
    assert app.pressed[1][0] - app.pressed[0][0] == 1 + 3      # the press, then 100 ms


def test_select_of_a_game_not_on_home_fails():
    r, *_ = play([{"select": "tetris"}])
    with pytest.raises(rec.ShotFailed, match="no game 'tetris' on Home"):
        r.run()


def test_a_launch_holds_its_card_and_ends_the_shot():
    r, app, sink, _ = play([{"press": "cross"}, {"wait_ms": 1000}, {"mark": "never"}],
                           app=FakeApp(launch_on=Action.A), launch_hold_ms=500)
    r.run()
    assert sink.frames == [b"card"] * 15
    assert r.skipped == ['{"wait_ms": 1000}', '{"mark": "never"}'] and r.marks == []


def test_a_launch_while_waiting_ends_the_wait():
    app = FakeApp(launch_on=Action.A)
    r, app, sink, _ = play([{"press": "cross", "times": 3, "every_ms": 100}], app=app, launch_hold_ms=0)
    r.run()
    assert len(app.pressed) == 1 and sink.frames == [b"card"]


def test_warm_up_runs_unrecorded_until_ready():
    app = FakeApp()
    app.waiting = ["World's console binding"]
    r, app, sink, clock = play([{"wait_ms": 100}], app=app)
    with pytest.raises(rec.ShotFailed, match="warming up: after 1 s still waiting for World's console binding"):
        r.warm_up(timeout_ms=1000)
    app.waiting = []
    r.warm_up()
    assert sink.frames == [] and app.frames >= rec.PRE_ROLL and r.k == 0


# ---- the copy of the console -----------------------------------------------------------------------------------------

def console(tmp_path):
    src = tmp_path / "sandbox"
    (src / "runs" / "best").mkdir(parents=True)
    (src / "runs" / "best" / "MDGP.acl").write_bytes(b"ACL1")
    (src / "laptop-state.json").write_text(json.dumps({"coach_greeted": "2026-11-01", "handler_offered": "",
                                                       "volume": 70}))
    (src / "console-id").write_text("8136575778911b0f5e7eba25d6e31821")
    (src / "handler.json").write_text('{"book": "ANY-6PS"}')
    (src / "arkiv-key").write_text("ab" * 32 + "\n")
    os.chmod(src / "arkiv-key", 0o600)
    (src / "arkiv-address").write_text("0x" + "1a2b" * 10 + " 0123456789abcdef\n")
    (src / "coach-voice.key").write_text("secret")
    (src / "handler-resume.json").write_text("{}")
    return src


def test_the_copy_is_that_console_and_never_writes_it(tmp_path):
    src = console(tmp_path)
    before = {p: p.read_bytes() for p in src.rglob("*") if p.is_file()}
    dest = tmp_path / "recorder"
    dest.mkdir()
    (dest / "handler-resume.json").write_text("{}")          # an old run's leftovers go
    (dest / "runs").mkdir()
    (dest / "runs" / "stale.acl").write_text("x")
    state, runs, run = rec.prepare_state(str(src / "laptop-state.json"), str(src / "runs"), str(dest), "2026-11-06")
    assert state == str(dest / "laptop-state.json") and os.path.isdir(run)
    assert json.loads((dest / "laptop-state.json").read_text()) == {
        "coach_greeted": "2026-11-06", "handler_offered": "2026-11-06", "volume": 70}
    assert (dest / "console-id").read_text() == "8136575778911b0f5e7eba25d6e31821"
    assert (dest / "handler.json").read_text() == '{"book": "ANY-6PS"}'
    assert (dest / "arkiv-key").read_text() == "ab" * 32 + "\n"                  # the laptop console's own wallet
    assert (dest / "arkiv-address").read_text() == (src / "arkiv-address").read_text()
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(dest / "arkiv-key").st_mode) == 0o600
    assert not (dest / "coach-voice.key").exists() and not (dest / "handler-resume.json").exists()
    assert sorted(os.listdir(runs)) == ["best"] and (dest / "runs" / "best" / "MDGP.acl").read_bytes() == b"ACL1"
    assert {p: p.read_bytes() for p in src.rglob("*") if p.is_file()} == before


def test_the_greeting_is_kept_when_asked_and_the_source_dir_is_refused(tmp_path):
    src = console(tmp_path)
    rec.prepare_state(str(src / "laptop-state.json"), str(src / "runs"), str(tmp_path / "r"), "2026-11-06", greet=True)
    assert json.loads((tmp_path / "r" / "laptop-state.json").read_text())["coach_greeted"] == "2026-11-01"
    with pytest.raises(ValueError):
        rec.prepare_state(str(src / "laptop-state.json"), str(src / "runs"), str(src), "2026-11-06")


# ---- the guard on real writes ----------------------------------------------------------------------------------------

class Sponsors:
    def __init__(self, real=()):
        self.real_ones, self.begun = real, []
        self.names = "names"

    def mocked(self, service):
        return service not in self.real_ones

    def begin(self, step, payload):
        self.begun.append(step)
        return step


def test_real_writes_are_refused_unless_allowed():
    guard = rec.GuardedSponsors(Sponsors(real=("world", "board")), allow=False)
    assert guard.begin("status", {}) == "status" and guard.begin("load_ghost", {}) == "load_ghost"
    assert guard.names == "names" and not guard.mocked("world")
    for step in rec.WRITE_STEPS:
        with pytest.raises(rec.ShotFailed, match=f"'{step}', a real sponsor write"):
            guard.begin(step, {})
    assert guard.begun == ["status", "load_ghost"]
    assert rec.GuardedSponsors(Sponsors(real=("third",)), allow=True).begin("pay", {}) == "pay"
    assert rec.GuardedSponsors(Sponsors(), allow=False).begin("pay", {}) == "pay"      # every sponsor mocked

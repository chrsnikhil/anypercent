"""PB the handler inside the real App (app.py + handler_glue.py): Triangle opens a game's hub, the flow buys and races
the target's ghost through the arcade bridge, the race's result comes back to the flow, and the flows nobody asked for
(the daily record book offer, a new best's listing offer, a mock sale) wait for PB to be quiet on Home.

Driven headless with app.frame(), FakeRunner, a fake bridge and the mock sponsors on a clock the test moves by hand.
The board: the test log (RIA) at 6070 frames, the player's best at 6290, so YOU are 5th and RIA, 3rd, is 3.7 s ahead."""
import concurrent.futures
import dataclasses
import json
import os
import threading
import time

import pytest

from arca_launcher import coach, settings
from arca_launcher.actions import Action as A
from arca_launcher.app import HANDLER_IDLE_MS, MAX_DT, App, Config
from arca_launcher.coach import Line, fmt_time
from arca_launcher.handler import ledger as L
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler_glue import MOCK_WALLET, NO_RUMBLE, OK_RUMBLE, SALE_RUMBLE, ordinal
from arca_launcher.model import Screen
from arca_launcher.runner import RunResult
from arca_launcher.touch import Press, Tap
from conftest import distinct_colours, snapshot
from test_app import FakeHw, FakeRunner

LOG = 6070                              # the shipped test log's time: RIA
BEST = 6290                             # the player's best
GAME = "marine-drive-gp"


def ghost(*room_frames):
    """An ACG1-like ghost: one in-play sample a frame, room k for room_frames[k - 1] frames."""
    return {"period": 1, "points": [(0, 0, 0, 0x80 | room) for room, n in enumerate(room_frames, start=1)
                                    for _ in range(n)]}


class Bridge:
    """The arcade bridge's surface, without a replay tool. results: what after() returns, one per run."""

    def __init__(self, log_frames=LOG, ghosts=None):
        self.log_frames, self.ghosts = log_frames, ghosts or {}
        self.calls, self.results = [], []
        self.gate = None                # a threading.Event the comparison waits on
        self.runs_dir = None            # set by make(): a new best is written there, as the real bridge does

    def log_time(self, arcade, path):
        self.calls.append(("log_time", path))
        if isinstance(self.log_frames, Exception):
            raise self.log_frames
        return self.log_frames

    def ghost_bytes(self, arcade, path):
        self.calls.append(("ghost_bytes", path))
        return b"G"

    def ghost(self, arcade, path):
        if self.gate is not None:
            self.gate.wait(5)
        mine = os.path.basename(os.path.dirname(path)) == "best"
        self.calls.append(("ghost", "best" if mine else "log"))
        return self.ghosts.get("best" if mine else "log")

    def before(self, rom, arcade, ghost=None):
        self.calls.append(("before", rom, ghost))

    def after(self, rom, arcade):
        res = self.results.pop(0) if self.results else None
        if res and res.get("new_best"):
            write_best(self.runs_dir, res["time_frames"], final_hash=res["time_frames"])
        return res

    def history(self, gid, n=5):
        return [BEST] * 3


def write_best(runs_dir, frames, final_hash=7):
    best = os.path.join(runs_dir, "best")
    os.makedirs(best, exist_ok=True)
    with open(os.path.join(best, "MDGP.json"), "w", encoding="utf-8") as f:
        json.dump({"time_frames": frames, "final_hash": final_hash, "finished": True}, f)


def library(tmp_path, browser=False, zip_game=False):
    """Marine Drive GP (an arcade game, first A to Z) and Plain Game (not one); browser: and the Browser app (then
    first A to Z); zip_game: and ZIP, a second arcade game (last A to Z)."""
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    games = [{"id": "browser", "title": "Browser", "app": "browser"}] if browser else []
    rows = [(GAME, "Marine Drive GP", {"id": "MDGP", "replay": "/x"}), ("plain", "Plain Game", None)]
    if zip_game:
        rows.append(("zip", "ZIP", {"id": "ZIPG", "replay": "/x"}))
    for gid, title, arcade in rows:
        rom = tmp_path / f"{gid}.gba"
        rom.write_bytes(b"rom")
        games.append({"id": gid, "title": title, "rom": str(rom), **({"arcade": arcade} if arcade else {})})
    (lib / "library.json").write_text(json.dumps({"version": 1, "games": games}))
    return str(lib)


def make(tmp_path, bridge=None, book="ANY-7QZ", best=BEST, listings=(), coach=False, handler=True, runner=None,
         hw=None, browser=False, warm=False, zip_game=False):
    if book or listings:
        L.save(str(tmp_path / "handler.json"), L.Ledger(book=book, listings=list(listings)))
    runs = str(tmp_path / "runs")
    if best is not None:
        write_best(runs, best)
    bridge = bridge or Bridge()
    bridge.runs_dir = runs
    clock = [0]
    testlogs = tmp_path / "testlogs"
    if warm:                                                     # the warm-up reads only the logs that are there
        testlogs.mkdir(exist_ok=True)
        for gid in ("MDGP", "ZIPG"):
            (testlogs / f"{gid}.acl").write_bytes(b"log")
    cfg = Config(library_dir=library(tmp_path, browser, zip_game), state_path=str(tmp_path / "state.json"),
                 splash=False, run_dir=str(tmp_path / "run"), runs_dir=runs, testlogs_dir=str(testlogs),
                 coach=coach, handler=handler, handler_warm=warm)
    app = App(cfg, runner=runner or FakeRunner(), hw=hw or FakeHw(), bridge=bridge,
              sponsors=MockSponsors(lambda: clock[0]))
    app.clock = clock
    _MADE.append(app)
    return app


_MADE = []                                  # every App make() built: closed after its test, even a failed one


@pytest.fixture(autouse=True)
def _close_every_app():
    """A failed test never leaves its App (window, textures, worker threads) to corrupt the next test."""
    yield
    while _MADE:
        try:
            _MADE.pop().close()             # safe twice: most tests close their own
        except Exception:
            pass


def rom(tmp_path):
    return str(tmp_path / f"{GAME}.gba")


def warmed(app):
    """Wait for the start-up warm-up to finish (a read a PB press took over is cancelled: nothing to wait for)."""
    for job in list(app.handler._warm_jobs.values()):
        if not job.cancelled():
            job.result(5)


def test_boards_are_read_in_the_background_after_start(tmp_path):
    """The first PB press on a game never waits for a replay: every arcade game's test log time and her ghost are
    read once after start, off the main thread."""
    bridge = Bridge()
    app = make(tmp_path, bridge=bridge, warm=True, zip_game=True)
    warmed(app)
    reads = [c for c in bridge.calls if c[0] in ("log_time", "ghost_bytes")]
    assert sorted(os.path.basename(c[1]) for c in reads) == ["MDGP.acl", "MDGP.acl", "ZIPG.acl", "ZIPG.acl"]
    assert app.nav.board_times == {GAME: ("RIA", fmt_time(LOG)), "zip": ("RIA", fmt_time(LOG))}   # attract mode's
    app.frame(16, [A.Y])                                         # PB's hub on Marine Drive GP
    assert app.nav.screen is Screen.HANDLER
    assert [c for c in bridge.calls if c[0] in ("log_time", "ghost_bytes")] == reads      # nothing read again
    app.close()


def test_a_launch_stops_the_warm_up_between_replays(tmp_path):
    """A game started while the warm-up runs waits for the one replay running, never for the rest."""
    gate, order = threading.Event(), []

    class Slow(Bridge):
        def log_time(self, arcade, path):
            order.append("read " + arcade["id"])
            gate.wait(5)
            return super().log_time(arcade, path)

        def ghost_bytes(self, arcade, path):
            order.append("ghost " + arcade["id"])
            gate.wait(5)
            return super().ghost_bytes(arcade, path)

    class Runner(FakeRunner):
        def run(self, rom, **kw):
            order.append("run")
            return super().run(rom, **kw)

    app = make(tmp_path, bridge=Slow(), warm=True, zip_game=True, runner=Runner())
    started_warm(order)                                          # the warm-up has started its first read
    real_settle = app.handler.settle

    def settle():                                                # the launch has begun: only then does the read end
        threading.Timer(0.2, gate.set).start()
        real_settle()
    app.handler.settle = settle
    app.frame(16, [A.A])                                         # Play Marine Drive GP
    assert order[:2] == ["read MDGP", "run"], order              # one replay waited for, not the ghost after it
    warmed(app)                                                  # and once the game is over, the rest run after all
    assert order == ["read MDGP", "run", "read ZIPG", "ghost MDGP", "ghost ZIPG"], order
    app.close()


def started_warm(order, within=5):
    """Wait (at most `within` s) for the warm-up's first read to begin."""
    deadline = time.monotonic() + within
    while not order:
        assert time.monotonic() < deadline, "the warm-up never started"
        time.sleep(0.01)


def test_a_pb_press_on_a_game_being_read_waits_for_that_read_and_never_repeats_it(tmp_path):
    gate, order = threading.Event(), []

    class Slow(Bridge):
        def log_time(self, arcade, path):
            order.append("read " + arcade["id"])
            gate.wait(5)
            return super().log_time(arcade, path)

    app = make(tmp_path, bridge=Slow(), warm=True, zip_game=True)
    started_warm(order)                                          # Marine Drive GP's read is running
    real_await = app.handler._await_warm

    def await_warm(key):                                         # the press waits: only then does the read end
        threading.Timer(0.3, gate.set).start()
        real_await(key)
    app.handler._await_warm = await_warm
    started = time.monotonic()
    app.frame(16, [A.Y])                                         # PB on Marine Drive GP
    assert time.monotonic() - started >= 0.25 and app.nav.screen is Screen.HANDLER
    warmed(app)
    assert order.count("read MDGP") == 1, order
    app.close()


def test_the_warm_up_never_replays_a_log_the_main_thread_is_reading(tmp_path):
    """PB on ZIP reads ZIP's log itself; the worker, reaching ZIP's ghost job meanwhile, waits for that read."""
    gate, order = threading.Event(), []

    class Slow(Bridge):
        def log_time(self, arcade, path):
            order.append("read " + arcade["id"])
            if arcade["id"] == "MDGP":
                gate.wait(5)
            else:
                time.sleep(0.5)                                  # long enough for the worker to catch up
            return super().log_time(arcade, path)

    app = make(tmp_path, bridge=Slow(), warm=True, zip_game=True)
    started_warm(order)
    threading.Timer(0.1, gate.set).start()                      # the worker moves on to the ghosts mid-read
    app.nav.row_index = next(i for i, g in enumerate(app.nav.row) if g is not None and g.id == "zip")
    app.frame(16, [A.Y])
    warmed(app)
    assert order.count("read ZIPG") == 1, order
    app.close()


def test_a_launcher_that_fails_to_open_its_window_queues_no_replays(tmp_path, monkeypatch):
    """The warm-up starts last: a crash before it (no display at boot) exits at once, with no replay to wait for."""
    import pytest
    from arca_launcher import app as app_module
    bridge = Bridge()

    def no_display(cfg):
        raise RuntimeError("no DRM device yet")
    monkeypatch.setattr(app_module, "Display", no_display)
    with pytest.raises(RuntimeError):
        make(tmp_path, bridge=bridge, warm=True, zip_game=True)
    time.sleep(0.2)
    assert bridge.calls == []


def test_closing_after_a_launch_that_broke_midway_is_safe(tmp_path):
    """A crash between closing the window for a game and opening the next one: close() still runs to the end."""
    app = make(tmp_path)
    app.display.close()                                          # what launch() does before the game
    app.close()
    app.close()                                                  # and again (main's finally after run's own close)


def test_a_sale_that_cannot_open_is_dropped_not_a_boot_loop(tmp_path, monkeypatch):
    """Anything wrong with a flow nobody asked for is logged and dropped: the launcher never crashes on it at every
    start."""
    path = str(tmp_path / "handler.json")
    L.save(path, L.Ledger(book="ANY-7QZ", pending_sale={"game": GAME, "buyer": "ARJUN", "frames": 6100}))
    app = make(tmp_path, book=None)

    def broken(game):
        raise ValueError("a context that cannot be built")
    monkeypatch.setattr(app.handler, "_context", broken)
    app.frame(16)                                                # no exception
    assert app.nav.screen is Screen.HOME and app.handler.pending is None
    assert L.load(path).pending_sale is None
    app.close()


def test_an_arcade_entry_without_an_id_is_skipped_by_the_warm_up(tmp_path):
    """A library entry whose arcade field has no id cannot stop the launcher from starting."""
    app = make(tmp_path, warm=True, zip_game=True)
    warmed(app)
    i = next(k for k, g in enumerate(app.nav.row) if g is not None and g.id == "zip")
    app.nav.row[i] = dataclasses.replace(app.nav.row[i], arcade={"replay": "/x"})
    app.handler.warm_up()                                        # no KeyError
    app.close()


def test_a_pb_press_during_the_warm_up_never_waits_for_another_games_read(tmp_path):
    """Marine Drive GP's read is running (slow); PB on ZIP reads ZIP's board at once instead of queueing behind it."""
    gate, order = threading.Event(), []

    class Slow(Bridge):
        def log_time(self, arcade, path):
            order.append("read " + arcade["id"])
            if arcade["id"] == "MDGP":
                gate.wait(5)
            return super().log_time(arcade, path)

    app = make(tmp_path, bridge=Slow(), warm=True, zip_game=True)
    started_warm(order)
    app.nav.row_index = next(i for i, g in enumerate(app.nav.row) if g is not None and g.id == "zip")
    started = time.monotonic()
    app.frame(16, [A.Y])                                         # PB on ZIP while MDGP's replay still runs
    assert time.monotonic() - started < 2, "PB waited for Marine Drive GP's replay"
    assert app.nav.screen is Screen.HANDLER and not gate.is_set()
    assert order == ["read MDGP", "read ZIPG"], order
    assert app.handler._warm_jobs[("ZIPG", "time")].cancelled()  # the press took ZIP's queued read over
    gate.set()
    warmed(app)
    assert order.count("read ZIPG") == 1                        # the warm-up never reads it again
    app.close()


def test_attract_mode_waits_for_a_queued_offer(tmp_path):
    """A flow queued to open once PB is quiet (the listing offer after a best, the day's record-book offer) opens
    before attract mode can cover Home."""
    from arca_launcher.app import ATTRACT_MS
    from arca_launcher.coach import Line
    app = make(tmp_path, book=None)
    app.nav.say([Line("happy", "A new best! 1:42.95 on Marine Drive.")])
    app.handler.pending = (None, "book", {})
    idle(app, ATTRACT_MS + 15000, frame=1000)
    assert app.nav.screen is Screen.HANDLER, app.nav.stack     # PB finished, then the offer opened; no booth display
    app.close()


def wait(app, ms):
    """Let the mock sponsors' clock run on, then one frame (the flow polls its call)."""
    app.clock[0] += ms
    app.frame(16)


def idle(app, ms, frame=MAX_DT):
    """ms of frames of `frame` ms with no input. They are not drawn: only the idle timers matter here, and a few
    thousand drawn frames would make a slow test."""
    draw = app._draw_screen
    app._draw_screen = lambda dt: None
    try:
        for _ in range(ms // frame):
            app.frame(frame)
    finally:
        app._draw_screen = draw


def to_buy_done(app):
    """Triangle, then Cross through the hub, the board and her run; PB buys her ghost (check, pay, load)."""
    app.frame(16, [A.Y])
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "hub"
    app.frame(16, [A.A])                                         # the board
    app.frame(16, [A.A])                                         # her run, the next to beat
    app.frame(16, [A.A])                                         # buy it
    for ms in (1400, 2000, 1200):
        wait(app, ms)
    assert app.nav.handler.state.name == "buy_done"
    return app.nav.handler


class QuitRunner(FakeRunner):
    """The PS button ended the game: the home key marks it, then the emulator ends badly."""

    def __init__(self, run_dir):
        super().__init__()
        self.run_dir = run_dir

    def run(self, rom, **kw):
        super().run(rom, **kw)
        os.makedirs(self.run_dir, exist_ok=True)
        with open(os.path.join(self.run_dir, "home-quit"), "w") as f:
            f.write(f"{time.time()}\n")
        return RunResult(False, 143, "retroarch exited with code 143")


# --- racing the target ----------------------------------------------------------------------------------------------
def test_triangle_then_cross_races_the_target_with_her_ghost(tmp_path):
    bridge = Bridge()
    app = make(tmp_path, bridge)
    to_buy_done(app)
    app.frame(16, [A.A])                                         # race her
    assert ("before", rom(tmp_path), b"G") in bridge.calls
    assert ("ghost_bytes", str(tmp_path / "testlogs" / "MDGP.acl")) in bridge.calls
    assert app.runner.roms == [rom(tmp_path)]
    assert app.nav.screen is Screen.HANDLER                      # back on the handler after the race
    app.close()


def test_beating_the_target_shows_result_then_offers_listing(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6000, "new_best": True}]
    app = make(tmp_path, bridge, coach=True)
    app.nav.advance_mascot()                                     # past the hello
    flow = to_buy_done(app)
    app.frame(16, [A.A])
    assert app.nav.screen is Screen.HANDLER and flow.state.name == "result"
    assert (flow.ctx["rank"], flow.ctx["new_rank"], flow.ctx["gap"], flow.ctx["run_time"]) == \
        ("5th", "3rd", "1.2 s", "1:40.00")
    assert app.nav.mascot is None                                # PB's ordinary after-run lines are not queued
    app.frame(16, [A.A])
    assert flow.state.name == "ls_offer"
    app.close()


def test_losing_keeps_the_ghost_and_racing_again_is_free(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6300, "new_best": False},
                      {"finished": True, "time_frames": 6350, "new_best": False}]
    app = make(tmp_path, bridge)
    flow = to_buy_done(app)
    assert app.handler.ledger.spent == 10
    app.frame(16, [A.A])
    assert flow.state.name == "race_lost"
    app.frame(16, [A.A])                                         # Cross races her again, no charge
    assert flow.state.name == "race_lost" and len(app.runner.roms) == 2
    assert [c[2] for c in bridge.calls if c[0] == "before"] == [b"G", b"G"]
    assert app.handler.ledger.spent == 10 and L.load(str(tmp_path / "handler.json")).spent == 10
    assert L.owns(app.handler.ledger, GAME, "RIA")
    app.close()


def test_a_lost_race_shows_how_far_behind_and_no_rank_gain(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6300, "new_best": False}]
    app = make(tmp_path, bridge)
    flow = to_buy_done(app)
    assert (flow.ctx["rank"], flow.ctx["new_rank"]) == ("5th", "3rd")      # what beating her would give
    app.frame(16, [A.A])
    assert flow.state.name == "race_lost"
    assert (flow.ctx["rank"], flow.ctx["new_rank"], flow.ctx["gap"]) == ("5th", "5th", "3.8 s")
    assert "RIA is still *3.8 s* ahead" in flow.line
    app.close()


def test_back_at_the_hub_the_board_is_the_board_again(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6300, "new_best": False}]
    app = make(tmp_path, bridge)
    flow = to_buy_done(app)
    app.frame(16, [A.A])
    assert flow.state.name == "race_lost"
    app.frame(16, [A.B])                                         # Circle: the hub
    assert flow.state.name == "hub"
    assert (flow.ctx["rank"], flow.ctx["new_rank"], flow.ctx["gap"]) == ("5th", "3rd", "3.7 s")
    assert flow.ctx["run_frames"] is None and flow.ctx["run_time"] == fmt_time(BEST)   # "List my best run" lists it
    app.close()


def test_a_quit_race_keeps_the_ghost_and_charges_nothing(tmp_path):
    app = make(tmp_path, runner=QuitRunner(str(tmp_path / "run")))
    flow = to_buy_done(app)
    app.frame(16, [A.A])
    assert flow.state.name == "race_unfinished" and app.nav.screen is Screen.HANDLER
    assert flow.ctx["ghost_kept"] == "RIA's ghost is still yours. "
    assert app.nav.notice is None                                # a quit is not a crash
    app.frame(16, [A.A])                                         # race again
    assert len(app.runner.roms) == 2 and app.handler.ledger.spent == 10
    app.close()


def test_her_ghost_is_drawn_from_the_test_log_once(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6300, "new_best": False}] * 2
    app = make(tmp_path, bridge)
    flow = to_buy_done(app)
    app.frame(16, [A.A])
    app.frame(16, [A.A])                                         # race her again: no second replay of her log
    assert len(app.runner.roms) == 2 and flow.state.name == "race_lost"
    log = str(tmp_path / "testlogs" / "MDGP.acl")
    assert [c for c in bridge.calls if c[0] == "ghost_bytes"] == [("ghost_bytes", log)]
    assert [c[2] for c in bridge.calls if c[0] == "before"] == [b"G", b"G"]
    app.close()


def test_a_race_that_cannot_start_is_not_left_racing(tmp_path):
    app = make(tmp_path)
    app.nav.games[0] = dataclasses.replace(app.nav.games[0], rom_exists=False)   # its ROM went missing
    flow = to_buy_done(app)
    app.frame(16, [A.A])
    assert flow.state.name == "race_unfinished" and app.nav.screen is Screen.HANDLER
    assert app.nav.notice == "Marine Drive GP: ROM file missing" and app.runner.roms == []
    flow.game = "gone"                                           # a game no longer in the library
    app.frame(16, [A.A])                                         # Cross races again
    assert flow.state.name == "race_unfinished" and app.runner.roms == []
    app.close()


def test_her_ghost_failing_to_load_never_races_your_own_best_instead(tmp_path):
    class Flaky(Bridge):
        """ghost_bytes raises, then finds nothing, then works."""
        answers = [RuntimeError("replay tool crashed"), None, b"G"]

        def ghost_bytes(self, arcade, path):
            self.calls.append(("ghost_bytes", path))
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
    bridge = Flaky()
    app = make(tmp_path, bridge)
    flow = to_buy_done(app)
    for _ in range(2):
        app.frame(16, [A.A])                                     # race her: her ghost does not load, no launch
        assert app.runner.roms == [] and not any(c[0] == "before" for c in bridge.calls)
        assert flow.state.name == "race_unfinished" and app.nav.screen is Screen.HANDLER
        assert app.nav.notice == "RIA's ghost could not be loaded"
    app.frame(16, [A.A])                                         # the failures were not kept: this time it loads
    assert app.runner.roms == [rom(tmp_path)]
    assert [c[2] for c in bridge.calls if c[0] == "before"] == [b"G"]
    assert len([c for c in bridge.calls if c[0] == "ghost_bytes"]) == 3
    app.close()


def test_unverified_run_is_not_counted(tmp_path):
    app = make(tmp_path)                                         # the bridge's after() verifies nothing: None
    flow = to_buy_done(app)
    app.frame(16, [A.A])
    assert flow.state.name == "race_unverified"
    assert flow.ctx["best_frames"] == BEST and flow.ctx["rank"] == flow.ctx["new_rank"] == "5th"
    assert app.handler.ledger.spent == 10
    app.close()


def test_racing_your_own_best_when_nobody_ahead_sells(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 5900, "new_best": True}]
    app = make(tmp_path, bridge, best=6000)                      # already ahead of RIA
    app.frame(16, [A.Y, A.A])
    flow = app.nav.handler
    assert flow.state.name == "nobody_ahead"
    app.frame(16, [A.A])
    assert [c[2] for c in bridge.calls if c[0] == "before"] == [None]      # the bridge's own best ghost
    assert flow.state.name == "own_result" and app.handler.ledger.spent == 0
    app.close()


# --- the hub --------------------------------------------------------------------------------------------------------
def test_the_hub_context_for_an_arcade_game(tmp_path):
    bridge = Bridge()
    app = make(tmp_path, bridge)
    app.frame(16, [A.Y])
    ctx = app.nav.handler.ctx
    assert (ctx["game"], ctx["target"], ctx["target_time"], ctx["gap"], ctx["rank"], ctx["new_rank"]) == \
        ("Marine Drive GP", "RIA", fmt_time(LOG), "3.7 s", "5th", "3rd")
    assert (ctx["board_case"], len(ctx["board_rows"]), ctx["best_frames"], ctx["runs"], ctx["sold"]) == \
        ("ok", 8, BEST, "3", 0)
    assert (ctx["buyer"], ctx["ghost_look"], ctx["wallet"]) == ("", "the *cyan kart*", MOCK_WALLET)
    assert ctx["other_book"].startswith("ANY-") and ctx["other_book"] != "ANY-7QZ"
    assert ctx["arcade"] is True and app.nav.handler.hub_count == 5
    assert ctx["game_titles"] == {GAME: "Marine Drive GP", "plain": "Plain Game"}   # My listings names the games
    assert app.nav.handler.game == GAME
    app.frame(16, [A.B])                                         # Circle closes the hub
    assert app.nav.screen is Screen.HOME
    app.frame(16, [A.Y])                                         # and it opens fresh, the test log timed once
    assert [c for c in bridge.calls if c[0] == "log_time"] == [("log_time", str(tmp_path / "testlogs" / "MDGP.acl"))]
    app.close()


def test_board_survives_a_failing_replay_tool(tmp_path):
    app = make(tmp_path, Bridge(log_frames=RuntimeError("replay tool missing")))
    app.frame(16, [A.Y, A.A])
    assert app.nav.handler.state.name == "no_board"
    app.close()


def test_a_game_without_a_board_opens_a_hub_of_book_rows_only(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.RIGHT, A.Y])                                # Plain Game
    flow = app.nav.handler
    assert (flow.ctx["game"], flow.ctx["board_case"], flow.ctx.get("best_frames")) == ("Plain Game", "no_board", None)
    assert flow.ctx["ghost_look"] == "the ghost" and flow.ctx["arcade"] is False
    assert flow.hub_rows == ("My record book", "My listings", "Start over (mock)")
    app.frame(16)                                                # drawn: three rows to tap
    assert len([h for h in app.display.views.hits if h.target[:2] == ("handler", "row")]) == 3
    app.frame(16, [A.A])                                         # row 0: My record book
    assert flow.state.name == "book_view"
    app.frame(16, [A.B, A.DOWN, A.A])
    assert flow.state.name == "listings_view"
    app.frame(16, [A.B, A.B])                                    # the hub, then Home
    app.frame(16, [A.RIGHT, A.Y])                                # the Game Library tile: no game at all
    library = app.nav.handler
    assert library is not flow and library.ctx["game"] == "this game" and library.ctx["board_case"] == "no_board"
    assert library.hub_count == 3
    app.frame(16, [A.B])
    app.close()

    (tmp_path / "nobook").mkdir()
    app = make(tmp_path / "nobook", book=None)
    app.frame(16)                                                # the day's record book offer
    app.frame(16, [A.B])                                         # "later"
    app.frame(16, [A.RIGHT, A.Y, A.A])                           # Plain Game's row 0 needs a book first
    assert app.nav.handler.state.name == "need_book"
    app.close()


def test_handler_off_means_no_hub(tmp_path):
    app = make(tmp_path, handler=False)
    app.frame(16, [A.Y])
    assert app.nav.screen is Screen.HOME and app.nav.handler is None
    app.close()


def test_start_over_forgets_the_record_book(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y] + [A.DOWN] * 4 + [A.A])
    assert app.nav.handler.state.name == "start_over"
    app.frame(16, [A.A])
    assert app.nav.handler.state.name == "hub"
    assert app.handler.ledger.book is None and not os.path.exists(tmp_path / "handler.json")
    app.close()


def test_ordinals():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th"]


# --- where she is faster (the background comparison) ---------------------------------------------------------------
def test_where_she_is_faster_is_worked_out_in_the_background(tmp_path):
    bridge = Bridge(ghosts={"best": ghost(60, 90, 60, 60), "log": ghost(60, 60, 60, 60)})
    bridge.gate = threading.Event()
    app = make(tmp_path, bridge)
    app.frame(16, [A.Y])
    flow = app.nav.handler
    assert flow.ctx["split"] == "comparing..."
    bridge.gate.set()
    app.handler.settle()
    app.frame(16)
    assert flow.ctx["split"] == "0:01 to 0:02, -0.50 s"          # room 2: 30 frames lost
    assert sorted(c[1] for c in bridge.calls if c[0] == "ghost") == ["best", "log"]
    app.frame(16, [A.B, A.Y])                                    # the same best: the answer is kept
    assert app.nav.handler.ctx["split"] == "0:01 to 0:02, -0.50 s"
    assert len([c for c in bridge.calls if c[0] == "ghost"]) == 2
    app.close()


def test_the_comparison_is_of_two_finished_runs(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(coach, "compare", lambda run, best, finished=False: seen.append(finished))
    app = make(tmp_path)
    app.frame(16, [A.Y])
    app.handler.settle()
    assert seen == [True]                                        # the best run and the shipped test log both finish
    app.close()


def test_no_best_means_no_comparison(tmp_path):
    bridge = Bridge(ghosts={"best": ghost(60, 90, 60, 60), "log": ghost(60, 60, 60, 60)})
    app = make(tmp_path, bridge, best=None)
    app.frame(16, [A.Y])
    assert app.nav.handler.ctx["split"] == "" and app.nav.handler.ctx["board_case"] == "no_best"
    assert not any(c[0] == "ghost" for c in bridge.calls)
    app.close()


def test_a_failing_comparison_leaves_the_split_out(tmp_path):
    class Broken(Bridge):
        def ghost(self, arcade, path):
            raise RuntimeError("replay tool crashed")
    app = make(tmp_path, Broken())
    app.frame(16, [A.Y])
    app.handler.settle()
    app.frame(16)
    assert app.nav.handler.ctx["split"] == ""
    app.close()


def test_launch_waits_for_the_comparison(tmp_path):
    order = []

    class Slow(Bridge):
        def ghost(self, arcade, path):
            self.gate.wait(5)
            order.append("compared")
            return None

    class Runner(FakeRunner):
        def run(self, rom, **kw):
            order.append("run")
            return super().run(rom, **kw)
    bridge = Slow()
    bridge.gate = threading.Event()
    app = make(tmp_path, bridge, runner=Runner())
    app.frame(16, [A.Y])                                         # the hub starts the comparison
    app.frame(16, [A.B])                                         # back Home, the job still running
    assert order == []
    threading.Timer(0.3, bridge.gate.set).start()
    app.frame(16, [A.A])                                         # play: the launch waits for it first
    assert order == ["compared", "compared", "run"]
    app.close()


class SlowReplays(Bridge):
    """Each of the comparison's two replays takes 0.3 s; `order` records them and what started after."""

    def __init__(self):
        super().__init__()
        self.order = []

    def ghost(self, arcade, path):
        self.order.append("replay")
        time.sleep(0.3)
        self.order.append("replayed")
        return None


def test_a_launch_waits_out_both_replays_however_long(tmp_path, monkeypatch):
    """One comparison is two replays, each bounded by the bridge, so the launch's wait has no limit of its own. Time is
    scaled down here: every timeout given to a wait shrinks 1000-fold (a 60 s limit would become 0.06 s), and each
    replay takes 0.3 s, longer than any such limit."""
    real = concurrent.futures.Future.result
    monkeypatch.setattr(concurrent.futures.Future, "result",
                        lambda self, timeout=None: real(self, None if timeout is None else timeout / 1000))
    bridge = SlowReplays()

    class Runner(FakeRunner):
        def run(self, rom, **kw):
            bridge.order.append("run")
            return super().run(rom, **kw)
    app = make(tmp_path, bridge, runner=Runner())
    app.frame(16, [A.Y])                                         # the hub starts the comparison
    app.frame(16, [A.B, A.A])                                    # back Home and play at once
    assert bridge.order == ["replay", "replayed", "replay", "replayed", "run"]
    app.close()


def test_an_app_launch_waits_for_the_comparison_too(tmp_path):
    bridge = SlowReplays()

    class Hw(FakeHw):
        def start_app(self, name):
            bridge.order.append("app")
            return True
    app = make(tmp_path, bridge, hw=Hw(), browser=True)
    app.frame(16, [A.RIGHT, A.Y])                                # Marine Drive GP's hub starts the comparison
    app.frame(16, [A.B, A.LEFT, A.A])                            # back Home, the Browser
    assert bridge.order == ["replay", "replayed", "replay", "replayed", "app"]
    app.close()


# --- flows nobody asked for -----------------------------------------------------------------------------------------
def test_first_launch_offers_a_record_book_once_a_day(tmp_path):
    app = make(tmp_path, book=None, coach=True)
    app.frame(16)
    assert app.nav.screen is Screen.HOME and app.nav.mascot.kind == "greeting"   # PB says hello first
    assert settings.load(str(tmp_path / "state.json")).handler_offered == time.strftime("%Y-%m-%d")
    app.frame(16, [A.A])                                         # the hello read
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "s_boot"
    app.frame(16, [A.B])                                         # Circle: later
    assert app.nav.screen is Screen.HOME
    app.close()
    again = make(tmp_path, book=None, coach=True)
    again.frame(16)
    assert again.nav.mascot is None and again.nav.screen is Screen.HOME           # once a day
    again.close()


def test_no_offer_over_a_missing_library(tmp_path):
    cfg = Config(library_dir=str(tmp_path / "nowhere"), state_path=str(tmp_path / "state.json"), splash=False,
                 run_dir=str(tmp_path / "run"), handler=True)
    app = App(cfg, runner=FakeRunner(), hw=FakeHw(), bridge=Bridge(), sponsors=MockSponsors(lambda: 0))
    app.frame(16)
    assert app.error and app.nav.screen is Screen.HOME
    app.close()


def test_no_offer_with_a_record_book(tmp_path):
    app = make(tmp_path)
    app.frame(16)
    assert app.nav.screen is Screen.HOME
    assert settings.load(str(tmp_path / "state.json")).handler_offered == ""
    app.close()


def test_a_new_best_offers_its_listing_once_pb_is_quiet(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6200, "new_best": True,
                       "vs_best": {"best_frames": BEST, "splits": None}}]
    app = make(tmp_path, bridge, coach=True)
    app.nav.advance_mascot()                                     # past the hello
    app.frame(16, [A.A])                                         # an ordinary run: a new best
    assert app.nav.screen is Screen.HOME and app.nav.mascot.kind == "new_best"   # PB's debrief first
    app.frame(16)
    assert app.nav.screen is Screen.HOME
    app.frame(16, [A.A])                                         # read: PB is quiet
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "ls_offer"
    assert app.nav.handler.ctx["run_time"] == fmt_time(6200)
    app.close()


def test_a_new_best_without_a_record_book_offers_no_listing(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6200, "new_best": True}]
    app = make(tmp_path, bridge, book=None)
    app.frame(16)                                                # the day's record book offer: that is the ask
    app.frame(16, [A.B])                                         # "later"
    assert app.nav.stack == [Screen.HOME]
    app.frame(16, [A.A])                                         # an ordinary run: a new best
    for _ in range(3):
        app.frame(16)
    assert app.nav.stack == [Screen.HOME] and app.handler.pending is None
    assert app.nav.handler.state.name == "home"                  # still the offer's flow, never ls_offer
    app.close()


def test_cross_on_listed_shows_the_hub_and_sells_nothing(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y, A.DOWN, A.A])                            # the hub, "List my best run"
    flow = app.nav.handler
    assert flow.state.name == "ls_offer"
    app.frame(16, [A.A])                                         # the QR
    app.frame(16, [A.A])                                         # scanned on the phone
    assert flow.state.name == "ls_approve" and flow.ctx.get("code") and flow.ctx["code"] in flow.line
    app.frame(16, [A.A])                                         # approved on the phone
    assert flow.state.name == "ls_record" and flow.ctx.get("jti")
    wait(app, 2000)
    wait(app, 1400)
    assert flow.state.name == "ls_done"
    app.frame(16, [A.A])
    assert app.nav.screen is Screen.HANDLER and flow.state.name == "hub"
    assert [x["sold"] for x in L.load(str(tmp_path / "handler.json")).listings] == [0]
    app.close()


def test_the_first_launch_record_book_ends_back_home(tmp_path):
    app = make(tmp_path, book=None)
    app.frame(16)                                                # PB offers a record book
    flow = app.nav.handler
    assert flow.state.name == "s_boot"
    app.frame(16, [A.A, A.A])                                    # the QR, scanned on the phone
    app.frame(16, [A.A])                                         # confirmed on the phone
    assert flow.state.name == "id_verifying"
    wait(app, 1700)
    assert flow.state.name == "id_done" and app.handler.ledger.book
    app.frame(16, [A.A])                                         # Cross: Home, not "no board for this game"
    assert app.nav.stack == [Screen.HOME]
    app.close()


def test_a_listing_sells_on_the_next_return_home(tmp_path):
    fresh = {"game": GAME, "frames": 6150, "price": 10, "at": time.time(), "sold": 0}
    old = {"game": GAME, "frames": 6100, "price": 10, "at": time.time() - 120, "sold": 0}
    app = make(tmp_path, listings=[fresh, old])
    app.frame(16, [A.RIGHT, A.A])                                # play Plain Game and come back
    flow = app.nav.handler
    assert app.nav.screen is Screen.HANDLER and flow.state.name == "sale"
    assert (flow.ctx["buyer"], flow.ctx["game"], flow.ctx["run_time"]) == ("ARJUN", "Marine Drive GP", fmt_time(6100))
    assert [x["sold"] for x in L.load(str(tmp_path / "handler.json")).listings] == [0, 1]
    app.frame(16, [A.A])                                         # Cross: Home
    assert app.nav.screen is Screen.HOME
    app.frame(16, [A.A])                                         # another game: that listing has sold
    assert app.nav.screen is Screen.HOME
    assert [x["sold"] for x in L.load(str(tmp_path / "handler.json")).listings] == [0, 1]
    app.close()


def test_a_sale_pb_has_not_told_yet_survives_a_restart(tmp_path):
    """The sale is counted when it happens; a launcher restart before PB tells it still tells it, once."""
    old = {"game": GAME, "frames": 6100, "price": 10, "at": time.time() - 120, "sold": 0}
    app = make(tmp_path, listings=[old])
    app.handler.game_over(None, None, True, False)               # back Home from a game: the listing sells
    assert app.handler.pending is not None
    app.close()                                                  # and the launcher stops before PB says so
    path = str(tmp_path / "handler.json")
    assert [x["sold"] for x in L.load(path).listings] == [1]
    app = make(tmp_path, book=None)                              # the same console, started again
    app.frame(16)
    flow = app.nav.handler
    assert app.nav.screen is Screen.HANDLER and flow.state.name == "sale"
    assert (flow.ctx["buyer"], flow.ctx["game"], flow.ctx["run_time"]) == ("ARJUN", "Marine Drive GP", fmt_time(6100))
    assert L.load(path).pending_sale is None and [x["sold"] for x in L.load(path).listings] == [1]
    app.frame(16, [A.A])                                         # Cross: Home
    app.close()
    app = make(tmp_path, book=None)                              # told: another restart says nothing
    app.frame(16)
    assert app.nav.screen is Screen.HOME
    app.close()


def test_a_sale_for_a_game_no_longer_in_the_library_is_still_told(tmp_path):
    """A library update dropped the listed game: PB names the sale by its id, never crashes, and tells it once."""
    path = str(tmp_path / "handler.json")
    led = L.Ledger(book="ANY-7QZ", listings=[{"game": "gone", "frames": 6100, "price": 10, "at": 1.0, "sold": 1}],
                   pending_sale={"game": "gone", "buyer": "ARJUN", "frames": 6100})
    L.save(path, led)
    app = make(tmp_path, book=None)
    app.frame(16)
    flow = app.nav.handler
    assert app.nav.screen is Screen.HANDLER and flow.state.name == "sale"
    assert (flow.ctx["buyer"], flow.ctx["game"]) == ("ARJUN", "gone")
    assert L.load(path).pending_sale is None
    app.close()


def test_the_pad_rumbles_when_a_step_lands_or_is_refused(tmp_path):
    """The player feels it: a short pulse when a sponsor step lands, a low buzz when it is refused or backed out of,
    a bigger one for a sale. Nothing on the steps in between."""
    app = make(tmp_path, book=None)
    felt = []
    app.inputs.rumble = lambda low, high, ms: felt.append((low, high, ms))
    app.frame(16)                                                # the record book offer
    app.frame(16, [A.A, A.A])                                    # the QR, scanned on the phone
    app.frame(16, [A.A])                                         # confirmed on the phone
    assert felt == []
    wait(app, 1700)
    app.frame(16)
    assert app.nav.handler.state.name == "id_done" and felt == [OK_RUMBLE]
    app.frame(16, [A.A])                                         # Home
    app.frame(16, [A.Y, A.DOWN, A.A])                            # the hub, "List my best run"
    app.frame(16, [A.A])                                         # the QR
    app.frame(16, [A.B])                                         # backed out
    app.frame(16)
    assert app.nav.handler.state.name == "ls_cancel" and felt == [OK_RUMBLE, NO_RUMBLE]
    app.close()
    old = {"game": GAME, "frames": 6100, "price": 10, "at": time.time() - 120, "sold": 0}
    app = make(tmp_path, listings=[old])
    felt = []
    app.inputs.rumble = lambda low, high, ms: felt.append((low, high, ms))
    app.handler.game_over(None, None, True, False)               # back Home from a game: the listing sells
    app.frame(16)
    app.frame(16)
    assert app.nav.handler.state.name == "sale" and felt == [SALE_RUMBLE]
    app.close()


def test_a_visitor_waking_attract_mode_hears_pb_once(tmp_path):
    """Someone new picks up the controller at the booth: PB says who he is and where to start, once a wake."""
    from arca_launcher.app import ATTRACT_MS
    app = make(tmp_path, coach=True)
    app.nav.advance_mascot()                                     # past the day's hello
    for visit in range(2):
        for _ in range(ATTRACT_MS // 1000 + 1):
            app.frame(1000)
        assert app.nav.screen is Screen.ATTRACT
        app.frame(16, [A.A])                                     # the press only wakes it
        line = app.nav.mascot
        assert app.nav.screen is Screen.HOME and line is not None and line.kind == "visitor", visit
        assert "Play" in line.text and "PB" in line.text and "OPTIONS" in line.text      # Start, on a DualSense
        app.frame(16, [A.A])                                     # moves PB on
        assert app.nav.mascot is None
    app.close()
    touch = make(tmp_path / "touch", coach=True)                 # a finger wakes it: its lift keeps PB talking
    touch.nav.advance_mascot()
    touch.nav.attract()
    touch.frame(16, touches=[Press(400, 240), Tap(400, 240)])
    assert touch.nav.mascot is not None and touch.nav.mascot.kind == "visitor"
    touch.frame(16, touches=[Press(400, 240), Tap(400, 240)])    # the next tap moves PB on
    assert touch.nav.mascot is None
    touch.close()
    quiet = make(tmp_path / "quiet", coach=False)
    quiet.nav.attract()
    quiet.frame(16, [A.A])
    assert quiet.nav.mascot is None                              # no coach, no hello
    quiet.close()


def test_pb_names_each_games_ghost_as_it_looks(tmp_path):
    """Never "RIA's ghost is the ghost": PB says what to look for in each game."""
    from arca_launcher.handler_glue import GHOST_LOOKS
    app = make(tmp_path, zip_game=True)
    zip_game = next(g for g in app.nav.games if g.id == "zip")
    assert app.handler._context(zip_game)["ghost_look"] == "the *pale Zip*"
    assert set(GHOST_LOOKS) == {"SHIP", "RUSH", "ZIPG", "MDGP", "SEGF"}
    assert all(look != "the ghost" for look in GHOST_LOOKS.values())
    app.close()


def test_a_judges_whole_visit_with_everything_on(tmp_path):
    """The device's set-up (coach, handler, warm-up all on), one judge from the booth display to a sale: attract mode,
    PB's hello, the board, buying and racing her ghost, beating her, listing the run, and the sale after a game."""
    from arca_launcher.app import ATTRACT_MS
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6000, "new_best": True}]
    app = make(tmp_path, bridge=bridge, coach=True, warm=True, zip_game=True)
    warmed(app)
    app.nav.advance_mascot()                                     # the day's hello, said at start
    for _ in range(ATTRACT_MS // 1000 + 1):
        app.frame(1000)
    assert app.nav.screen is Screen.ATTRACT and app.nav.board_times[GAME][0] == "RIA"
    app.frame(16, [A.A])                                         # a judge picks the controller up
    assert app.nav.screen is Screen.HOME and app.nav.mascot.kind == "visitor"
    app.frame(16, [A.A])                                         # PB moves on
    app.nav.row_index = next(i for i, g in enumerate(app.nav.row) if g is not None and g.id == GAME)
    flow = to_buy_done(app)                                      # PB, the board, her run, bought
    app.frame(16, [A.A])                                         # race her, and beat her
    assert flow.state.name == "result" and app.runner.roms == [rom(tmp_path)]
    for _ in range(4):                                           # list it: the offer, the QR, scanned, approved
        app.frame(16, [A.A])
    wait(app, 2000)
    wait(app, 1400)
    assert flow.state.name == "ls_done"
    app.frame(16, [A.A])                                         # the hub
    app.frame(16, [A.B])                                         # Home
    assert app.nav.screen is Screen.HOME and app.nav.mascot is None
    app.handler.ledger.listings[-1]["at"] -= 120                 # a couple of minutes later
    app.nav.row_index = next(i for i, g in enumerate(app.nav.row) if g is not None and g.id == "plain")
    app.frame(16, [A.A])                                         # another game, and back Home
    app.frame(16)
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "sale"
    assert [x["sold"] for x in L.load(str(tmp_path / "handler.json")).listings] == [1]
    app.close()


def test_reaching_nobody_ahead_sells_does_not_rumble(tmp_path):
    """A board reading, not a sponsor step: the player's best beats RIA's, so there is no one to buy from."""
    app = make(tmp_path, best=6000)
    felt = []
    app.inputs.rumble = lambda low, high, ms: felt.append((low, high, ms))
    app.frame(16, [A.Y])
    app.frame(16, [A.A])                                         # the board row: nobody ahead sells
    app.frame(16)
    assert app.nav.handler.state.name == "nobody_ahead" and felt == []
    app.close()


# --- PB, touch and frame rate on the handler ------------------------------------------------------------------------
def test_pb_does_not_auto_advance_on_handler_screens(tmp_path):
    app = make(tmp_path, book=None)
    app.frame(16)                                                # the record book offer
    app.frame(16, [A.A])
    flow = app.nav.handler
    assert flow.state.name == "id_scan"
    app.nav.say([Line("happy", "A line for Home.")])
    for _ in range(100):                                         # 10 s of frames
        app.frame(100)
    assert flow.state.name == "id_scan" and app.nav.mascot is not None
    app.close()


def test_a_tap_on_the_handler_reaches_the_flow_while_pb_has_a_line(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y])
    app.nav.say([Line("happy", "Later.")])
    app.frame(16)                                                # drawn: its touch targets exist
    row = next(h for h in app.display.views.hits if h.target == ("handler", "row", 2))
    x, y = row.rect.center
    app.frame(16, touches=[Press(x, y), Tap(x, y)])
    assert app.nav.handler.state.name == "book_view" and app.nav.mascot is not None
    app.close()


def test_a_touch_only_player_opens_pb_from_the_pb_button_on_home(tmp_path):
    app = make(tmp_path)
    app.frame(16)                                                # Home drawn: its touch targets exist
    pb = next(h for h in app.display.views.hits if h.target == ("button", 1))
    assert app.nav.home_buttons()[1] == "PB"
    x, y = pb.rect.center
    app.frame(16, touches=[Press(x, y), Tap(x, y)])
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "hub"
    app.close()


def test_the_handler_runs_at_sixty_frames_a_second(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y])
    app.idle_ms = 10 ** 6
    assert app.target_fps() == 60
    app.frame(16, [A.B])
    app.idle_ms = 10 ** 6
    assert app.target_fps() == 30
    app.close()


def test_three_idle_minutes_on_a_handler_screen_go_home_unless_a_call_is_live(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y])                                         # the hub
    idle(app, HANDLER_IDLE_MS - MAX_DT)
    assert app.nav.screen is Screen.HANDLER
    app.frame(MAX_DT)                                            # three minutes with no input: Home
    assert app.nav.stack == [Screen.HOME]
    app.frame(16)
    assert app.nav.screen is Screen.ATTRACT                      # and attract mode takes over, as on Home
    app.frame(16, [A.A])                                         # wake

    app.frame(16, [A.Y, A.A, A.A, A.A])                          # buy her ghost: the listing check runs
    assert app.nav.handler.state.name == "buy_check"             # (the mock clock stands still: it never answers)
    idle(app, 200000)
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "buy_check"

    app.nav.handler.start("ls_approve")
    app.frame(16, [A.B])                                         # backed out: the approval is kept for a late answer
    assert app.nav.handler.state.name == "ls_cancel"
    idle(app, 200000)
    assert app.nav.screen is Screen.HANDLER
    app.close()


def test_idle_on_a_phone_step_keeps_the_handler_open_but_not_on_the_hub(tmp_path):
    app = make(tmp_path, book=None)
    app.frame(16)                                                # the day's record book offer
    app.frame(16, [A.A])                                         # the QR: a visitor may be in World App
    assert app.nav.handler.state.name == "id_scan"
    idle(app, 200000)                                            # 200 s with no input
    assert app.nav.screen is Screen.HANDLER and app.nav.handler.state.name == "id_scan"
    app.frame(16, [A.B, A.B])                                    # backed out, then Home
    assert app.nav.stack == [Screen.HOME]
    app.frame(16, [A.Y])                                         # the hub: no call
    assert app.nav.handler.state.name == "hub"
    idle(app, 200000)
    assert Screen.HANDLER not in app.nav.stack
    app.close()


def test_a_long_race_is_not_idle_time_on_its_result(tmp_path):
    bridge = Bridge()
    bridge.results = [{"finished": True, "time_frames": 6000, "new_best": True}]
    app = make(tmp_path, bridge)
    flow = to_buy_done(app)
    app.frame(16, [A.A])                                         # race her, and beat her
    assert flow.state.name == "result"
    app.frame(200000)                                            # the first frame back carries the race's wall time
    assert app.nav.stack == [Screen.HOME, Screen.HANDLER] and flow.state.name == "result"
    idle(app, 200000, frame=16)                                  # 200 s of ordinary idle frames do close it
    assert Screen.HANDLER not in app.nav.stack
    app.close()


def test_the_real_app_draws_the_handler(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y])
    for _ in range(30):
        app.frame(16)
    out = snapshot(app.display.renderer, "handler_app_hub")
    assert distinct_colours(out) > 3
    app.close()


# ---- one console, one person: the ledger follows the console's binding --------------------------------------------

class BoundSponsors(MockSponsors):
    """The mock, with World's bridge saying what this console is bound to (binding: set by the test)."""

    def __init__(self, clock_ms):
        super().__init__(clock_ms)
        self.binding = None

    def console_state(self):
        return dict(self.binding) if self.binding is not None else None


def bound_app(tmp_path, book=None, **kw):
    app = make(tmp_path, book=book, **kw)
    app.sponsors = BoundSponsors(lambda: app.clock[0])
    return app


def test_the_ledger_follows_the_consoles_binding(tmp_path):
    app = bound_app(tmp_path, book=None)
    app.frame(16)
    assert app.handler.ledger.book is None                           # no answer yet: nothing changes
    app.sponsors.binding = {"tag": "C-7QZP", "book": "ANY-6PS", "state": "bound", "credential": "Orb"}
    app.frame(16)
    led = L.load(str(tmp_path / "handler.json"))
    assert (led.book, led.world_verified, led.credential) == ("ANY-6PS", True, "Orb")   # a lost ledger recovered
    app.handler.ledger.purchases["MDGP:BOT-A2"] = {"price": 10, "receipt": "0.0.1@2", "at": 0}
    L.save(str(tmp_path / "handler.json"), app.handler.ledger)
    app.sponsors.binding = {"tag": "C-7QZP", "book": None, "state": "released", "credential": None}
    app.frame(16)
    led = L.load(str(tmp_path / "handler.json"))
    assert (led.book, led.world_verified) == (None, False) and "MDGP:BOT-A2" in led.purchases   # purchases stay
    app.sponsors.binding = {"tag": "C-7QZP", "book": "ANY-6PS", "state": "bound", "credential": "Orb"}
    app.frame(16)
    assert L.load(str(tmp_path / "handler.json")).book == "ANY-6PS"   # linked again


def test_an_unlinked_console_keeps_a_book_from_before(tmp_path):
    app = bound_app(tmp_path, book="ANY-6PS")
    app.sponsors.binding = {"tag": "C-7QZP", "book": None, "state": "unbound", "credential": None}
    app.frame(16, [A.Y])
    flow = app.nav.handler
    assert app.handler.ledger.book == "ANY-6PS"
    assert (flow.ctx["console_tag"], flow.ctx["console_line"]) == ("C-7QZP", "not linked yet")


def test_my_record_book_names_the_console_and_follows_a_release(tmp_path, monkeypatch):
    app = bound_app(tmp_path, book="ANY-6PS")
    app.sponsors.binding = {"tag": "C-7QZP", "book": "ANY-6PS", "state": "bound", "credential": "Orb"}
    app.frame(16, [A.Y])
    flow = app.nav.handler
    flow.pick(2)
    assert flow.state.name == "book_view"
    drawn, real = [], app.display.gfx.text
    monkeypatch.setattr(app.display.gfx, "text", lambda s, *a, **k: (drawn.append(s), real(s, *a, **k))[1])
    app.frame(16)
    assert flow.ctx["console_line"] == "linked to ANY-6PS" and flow.ctx["book"] == "ANY-6PS"
    assert any("C-7QZP" in s for s in drawn) and any("linked to ANY-6PS" in s for s in drawn)
    app.sponsors.binding = {"tag": "C-7QZP", "book": None, "state": "released", "credential": None}
    drawn.clear()
    app.frame(16)
    assert flow.ctx["book"] == "" and flow.ctx["console_line"] == "released"
    assert "No record book on this console" in drawn


def test_with_world_mocked_there_is_no_console_line(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y])
    assert "console_tag" not in app.nav.handler.ctx and app.handler.ledger.book == "ANY-7QZ"


# --- a chain link: Triangle (or a tap on the QR) opens it; on the handheld the card comes back after the browser ------
LINK = "https://hashscan.io/testnet/transaction/0.0.9185802-1762412349-000000123"
ROWS = [{"label": "Hedera INTENT #7", "value": "tx 0.0.9185802@1762412340",
         "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1762412340-000000001"},
        {"label": "Paid 0.10 USDC", "value": "tx 0.0.9185802@1762412349", "url": LINK},
        {"label": "Hedera RECEIPT", "value": "waiting for the mirror", "url": None}]
OPENING = ("Opening the explorer", "Hold PS for 2 seconds to come back to this screen.")


class PiHw(FakeHw):
    """The handheld: open_url answers `how` ("handoff": the browser has the screen; None: it did not start), noting
    whether the chain card was saved before it was called; on_open runs inside it (a SIGTERM landing mid-call).
    cancel_handoff counts the links taken back."""

    def __init__(self, how="handoff", resume=None, on_open=None):
        super().__init__()
        self.how, self.resume, self.on_open = how, resume, on_open
        self.opened, self.saved_first, self.cancelled = [], [], 0

    def is_pi(self):
        return True

    def open_url(self, url):
        self.opened.append(url)
        self.saved_first.append(os.path.exists(self.resume))
        if self.on_open is not None:
            self.on_open()
        return self.how

    def cancel_handoff(self):
        self.cancelled += 1


class LaptopHw(FakeHw):
    def __init__(self, how="window"):
        super().__init__()
        self.how, self.opened = how, []

    def is_pi(self):
        return False

    def open_url(self, url):
        self.opened.append(url)
        return self.how


def resume_path(tmp_path):
    return str(tmp_path / "handler-resume.json")


def on_chain_card(app, state="buy_done", chain_i=1):
    """PB's hub on Marine Drive GP, then the chain card `state` showing ROWS, row chain_i chosen, drawn once."""
    app.frame(16, [A.Y])
    flow = app.nav.handler
    flow.start(state)
    flow.ctx.update(chain=[dict(row) for row in ROWS], chain_i=chain_i)
    app.frame(16)
    return flow


def said(monkeypatch):
    """Every (title, body) the message screen shows from now on. Patched on the class: a spy on the instance would
    keep the window's renderer alive past the window (conftest.py's screen fixture says why that breaks later tests)."""
    from arca_launcher.render.views import Views
    shown, real = [], Views.message
    monkeypatch.setattr(Views, "message", lambda self, t, b, s: (shown.append((t, b)), real(self, t, b, s))[1])
    return shown


def hand_off(app, actions=(A.Y,)):
    """Triangle (or actions) on the card, then the frames until the browser is asked (HANDOFF_DELAY_MS on)."""
    from arca_launcher.app import HANDOFF_DELAY_MS
    app.frame(16, list(actions))
    for _ in range(HANDOFF_DELAY_MS // 100 + 1):
        app.frame(100)


def test_a_link_on_the_handheld_says_how_to_come_back_then_saves_the_card_and_asks_for_the_browser(tmp_path,
                                                                                                  monkeypatch):
    from arca_launcher.app import HANDOFF_DELAY_MS
    hw = PiHw(resume=resume_path(tmp_path))
    app = make(tmp_path, hw=hw)
    flow = on_chain_card(app)
    shown = said(monkeypatch)
    app.frame(16, [A.Y])                                         # Triangle: the words first, read for a moment
    assert shown == [OPENING] and hw.opened == [] and not os.path.exists(resume_path(tmp_path))
    for _ in range(HANDOFF_DELAY_MS // 100 - 1):
        app.frame(100, [A.B, A.DOWN])                            # nothing pressed while the words are up
    assert hw.opened == [] and shown[-1] == OPENING
    app.frame(100)
    app.frame(100)
    assert hw.opened == [LINK] and hw.saved_first == [True]      # saved right before the browser was asked
    with open(resume_path(tmp_path), encoding="utf-8") as f:
        saved = json.load(f)
    assert (saved["v"], saved["game"], saved["state"], saved["chain_pay"]) == (1, GAME, "buy_done", None)
    assert abs(saved["at"] - time.time()) < 60
    assert saved["ctx"]["chain"] == ROWS and saved["ctx"]["chain_i"] == 1 and saved["ctx"]["target"] == "RIA"
    assert "board_rows" not in saved["ctx"] and saved["ctx"]["game_titles"][GAME] == "Marine Drive GP"
    app.frame(16, [A.B, A.DOWN])                                 # until systemd stops it: the message, nothing pressed
    assert shown[-1] == OPENING and flow.ctx["chain_i"] == 1 and app.nav.screen is Screen.HANDLER
    assert hw.opened == [LINK] and hw.cancelled == 0
    app.close()


def test_the_frame_that_starts_the_hand_off_does_nothing_more(tmp_path, monkeypatch):
    """A second Triangle, a tap or a D-pad press in the same frame does nothing, and the card is not drawn over the
    words."""
    from arca_launcher.render.handler_view import HandlerView
    hw = PiHw(resume=resume_path(tmp_path))
    app = make(tmp_path, hw=hw)
    flow = on_chain_card(app)
    qr = next(h for h in app.display.views.hits if h.target == ("handler", "triangle"))
    drawn, real = [], HandlerView.draw
    monkeypatch.setattr(HandlerView, "draw", lambda self, *a: (drawn.append(1), real(self, *a))[1])
    x, y = qr.shape.center
    app.frame(16, [A.Y, A.Y, A.DOWN], touches=[Press(x, y), Tap(x, y)])
    assert drawn == [] and flow.ctx["chain_i"] == 1
    hand_off(app, actions=[A.Y])
    assert hw.opened == [LINK] and drawn == []
    app.close()


def test_a_stop_landing_while_the_browser_is_asked_keeps_the_card_and_its_link(tmp_path):
    """systemd's stop of the launcher can land before systemctl answers: the launcher is going, the browser is coming.
    Nothing is taken back."""
    app = make(tmp_path)
    hw = PiHw(how=None, resume=resume_path(tmp_path), on_open=lambda: setattr(app, "quitting", True))
    app.hw = hw
    on_chain_card(app)
    hand_off(app)
    assert hw.opened == [LINK] and os.path.exists(resume_path(tmp_path))
    assert hw.cancelled == 0 and app.nav.notice is None
    app.close()


def test_the_launcher_started_after_the_browser_reopens_the_same_chain_card(tmp_path):
    app = make(tmp_path, hw=PiHw(resume=resume_path(tmp_path)))
    flow = on_chain_card(app)
    before = (list(flow.ctx["chain"]), flow.ctx["chain_i"], flow.line)
    hand_off(app)
    app.close()                                                  # systemd stops it; the browser closes; it starts again
    again = make(tmp_path, book=None)                            # the same console
    again.frame(16)
    back = again.nav.handler
    assert again.nav.screen is Screen.HANDLER and back.state.name == "buy_done"
    assert (back.ctx["chain"], back.ctx["chain_i"], back.line) == before
    assert not os.path.exists(resume_path(tmp_path))             # one shot
    again.frame(16, [A.A])                                       # Cross still races the ghost
    assert ("before", str(tmp_path / f"{GAME}.gba"), b"G") in again.bridge.calls
    again.close()


def test_a_listing_card_brought_back_is_never_listed_twice(tmp_path):
    path = str(tmp_path / "handler.json")
    app = make(tmp_path, hw=PiHw(resume=resume_path(tmp_path)))
    on_chain_card(app, "ls_done", chain_i=0)
    assert len(L.load(path).listings) == 1
    hand_off(app)
    app.close()
    again = make(tmp_path, book=None)
    again.frame(16)
    assert again.nav.handler.state.name == "ls_done" and again.nav.handler.ctx["chain"] == ROWS
    assert len(L.load(path).listings) == 1
    again.close()


def _resume_file(tmp_path, **change):
    data = {"v": 1, "at": time.time(), "game": GAME, "state": "buy_done",
            "ctx": {"chain": ROWS, "chain_i": 1, "target": "RIA"}, "chain_pay": None}
    data.update(change)
    with open(resume_path(tmp_path), "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.mark.parametrize("change", [{"at": -601.0}, {"at": 30.0}, {"at": "now"}, {"v": 2},
                                    {"v": True}, {"state": "hub"}, {"state": "racing"}, {"game": "gone"},
                                    {"game": 7}, {"ctx": None}, {"ctx": {"chain": "rows"}},
                                    {"ctx": {"chain": [{"label": 1}]}}, {"ctx": {"chain": ROWS, "chain_i": "1"}},
                                    "not json", "a list"])
def test_a_resume_file_that_does_not_fit_is_dropped_and_never_crashes(tmp_path, change):
    if change == "not json":
        with open(resume_path(tmp_path), "w", encoding="utf-8") as f:
            f.write("{not json")
    elif change == "a list":
        with open(resume_path(tmp_path), "w", encoding="utf-8") as f:
            json.dump([1, 2], f)
    elif type(change.get("at")) is float:                        # seconds from now: saved too long ago, or later
        _resume_file(tmp_path, at=time.time() + change["at"])
    else:
        _resume_file(tmp_path, **change)
    app = make(tmp_path)
    assert not os.path.exists(resume_path(tmp_path))             # read once and gone, stale and broken ones too
    app.frame(16)
    assert app.nav.screen is Screen.HOME and app.handler.pending is None
    app.close()


def test_a_resume_with_no_game_or_payment_opens_as_saved(tmp_path):
    pay = {"receipt": "0.0.9185802@1762412349.000000123", "late": False, "receipt_msg": None}
    _resume_file(tmp_path, game=None, chain_pay=pay)
    app = make(tmp_path)
    app.frame(16)
    flow = app.nav.handler
    assert app.nav.screen is Screen.HANDLER and flow.state.name == "buy_done" and flow.game is None
    assert flow.ctx["chain"] == ROWS and flow.chain_pay == pay
    app.close()


def test_a_resume_wins_over_a_sale_pb_has_not_told_yet(tmp_path):
    path = str(tmp_path / "handler.json")
    L.save(path, L.Ledger(book="ANY-7QZ", pending_sale={"game": GAME, "buyer": "ARJUN", "frames": 6100}))
    _resume_file(tmp_path)
    app = make(tmp_path, book=None)
    app.frame(16)
    assert app.nav.handler.state.name == "buy_done"
    assert L.load(path).pending_sale is not None                 # the sale stays in the ledger
    app.close()


def test_the_days_record_book_offer_waits_behind_a_resume(tmp_path):
    _resume_file(tmp_path)
    app = make(tmp_path, book=None)                              # no record book: the day's offer would open
    app.frame(16)
    assert app.nav.handler.state.name == "buy_done"
    assert settings.load(str(tmp_path / "state.json")).handler_offered == ""   # offered on a later start
    app.close()


def test_a_browser_that_does_not_start_leaves_pb_on_the_card(tmp_path):
    hw = PiHw(how=None, resume=resume_path(tmp_path))
    app = make(tmp_path, hw=hw)
    flow = on_chain_card(app)
    hand_off(app)
    assert hw.saved_first == [True] and not os.path.exists(resume_path(tmp_path)) and hw.cancelled == 1
    assert app.nav.notice == "The browser could not start" and app.nav.screen is Screen.HANDLER
    app.frame(16, [A.DOWN])                                      # the card answers again
    assert flow.ctx["chain_i"] == 2
    app.close()


def test_a_hand_off_that_never_stops_the_launcher_gives_the_card_and_the_link_back(tmp_path, monkeypatch):
    from arca_launcher.app import HANDOFF_MS
    hw = PiHw(resume=resume_path(tmp_path))
    app = make(tmp_path, hw=hw)
    flow = on_chain_card(app)
    shown = said(monkeypatch)
    hand_off(app)
    assert hw.opened == [LINK]
    for _ in range(HANDOFF_MS // 100 - 2):                       # counted from the browser's start, not the press
        app.frame(100)
    assert shown[-1] == OPENING and app.nav.notice is None and hw.cancelled == 0
    app.frame(100)
    app.frame(100)
    app.frame(100)
    assert app.nav.notice == "The browser could not start" and not os.path.exists(resume_path(tmp_path))
    assert hw.cancelled == 1                                     # the link file goes too: no stale page later
    app.frame(16, [A.DOWN])
    assert flow.ctx["chain_i"] == 2
    app.close()


def test_a_resumed_payment_is_followed_again_by_the_sponsors(tmp_path):
    pay = {"receipt": "0.0.9185802@1762412349.000000123", "late": False, "receipt_msg": None, "job": "p-1a2b3c4d"}
    _resume_file(tmp_path, chain_pay=pay)
    app = make(tmp_path)
    followed = []
    app.sponsors.follow = followed.append
    app.frame(16)
    assert app.nav.handler.state.name == "buy_done" and followed == [pay]
    app.close()
    _resume_file(tmp_path)                                       # no payment kept: nothing to follow
    app = make(tmp_path)
    app.sponsors.follow = followed.append
    app.frame(16)
    assert app.nav.handler.state.name == "buy_done" and followed == [pay]
    app.close()

    def broken(pay):
        raise ValueError("a follow that fails")
    _resume_file(tmp_path, chain_pay=pay)
    app = make(tmp_path)
    app.sponsors.follow = broken
    app.frame(16)                                                # never a crash: the card still comes back
    assert app.nav.handler.state.name == "buy_done"
    app.close()


class PayToSponsors(MockSponsors):
    """Hedera real as far as the glue can tell: the book's account is `account` (None: not read yet)."""
    account = None

    def mocked(self, service):
        return service != "third" and super().mocked(service)

    def pay_to(self, book):
        return self.account


def test_a_resumed_listing_keeps_its_wallet_until_the_account_is_read(tmp_path):
    _resume_file(tmp_path, state="ls_done", ctx={"chain": ROWS, "chain_i": 0, "wallet": "0.0.9473064"})
    app = make(tmp_path)
    app.sponsors = PayToSponsors(lambda: app.clock[0])
    app.frame(16)
    flow = app.nav.handler
    assert flow.state.name == "ls_done" and flow.ctx["wallet"] == "0.0.9473064"
    app.frame(16)
    assert flow.ctx["wallet"] == "0.0.9473064"                   # not "no Hedera account yet" while it is read
    app.sponsors.account = "0.0.5550001"
    app.frame(16)
    assert flow.ctx["wallet"] == "0.0.5550001"                   # the account as read now
    app.sponsors.account = None
    app.frame(16)
    assert flow.ctx["wallet"] == "no Hedera account yet"         # from then on as before
    app.close()


@pytest.mark.parametrize("hw, notice", [(LaptopHw("window"), "Opened in a window"),
                                        (LaptopHw(None), "Links open on the handheld or the laptop"),
                                        (FakeHw(), "Links open on the handheld or the laptop")])
def test_a_link_off_the_handheld_opens_a_window_or_says_where_links_open(tmp_path, hw, notice):
    app = make(tmp_path, hw=hw)
    flow = on_chain_card(app)
    app.frame(16, [A.Y])
    assert getattr(hw, "opened", [LINK]) == [LINK] and app.nav.notice == notice
    assert app.nav.screen is Screen.HANDLER and not os.path.exists(resume_path(tmp_path))
    app.frame(16, [A.DOWN])                                      # the launcher carries on
    assert flow.ctx["chain_i"] == 2
    app.close()


def test_a_tap_on_the_qr_opens_its_link_as_triangle_does(tmp_path):
    hw = LaptopHw()
    app = make(tmp_path, hw=hw)
    on_chain_card(app)
    qr = next(h for h in app.display.views.hits if h.target == ("handler", "triangle"))
    x, y = qr.shape.center
    app.frame(16, touches=[Press(x, y), Tap(x, y)])
    assert hw.opened == [LINK] and app.nav.notice == "Opened in a window"
    app.close()


def test_only_a_chain_card_is_saved_for_the_browser(tmp_path):
    app = make(tmp_path)
    app.frame(16, [A.Y])                                         # the hub
    assert app.handler.save_resume() is False and not os.path.exists(resume_path(tmp_path))
    app.close()

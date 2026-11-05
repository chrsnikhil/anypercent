"""PB the handler, wired into the launcher. The App owns one of these while the handler is on (nav.handler is the open
flow, handler/flow.py; this is what feeds it).

It builds a game's hub context (the board, the player's best, a made-up wallet), works out where the target is faster
in the background, turns the flow's RaceTarget into a launch with her ghost and reports the race back to the flow, and
opens the flows nobody asked for (the day's record book offer, a new best's listing offer, a mock sale) once PB is
quiet on Home.

The board is Arkiv's when the sponsors say it is real (sponsors.board(): its run rows, read in the background) and the
mock one around the game's shipped test log otherwise. On a real board the target is a real run: her ghost is the log
load_ghost checked and kept (never the test log), a race is judged against her row's time, and attract mode's run to
beat and the record book's run count come from the rows too."""
import json
import logging
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import coach, settings
from .handler import board, ledger
from .handler.flow import CloseHandler, Flow
from .model import Screen

MOCK_WALLET = "0xDE40...0000"        # made up: the owner's real wallet is never shown
SALE_AFTER_S = 60                    # a listing sells on the first return Home at least this long after listing
# The pad as (low, high, ms) rumble: a sponsor step landed, was refused or backed out of, a ghost sold. A race's own
# result screens are left out (a new best already rumbles as the game ends, app.py), and so is "nobody ahead sells",
# a board reading, not a sponsor step.
OK_RUMBLE, NO_RUMBLE, SALE_RUMBLE = (0.5, 0.5, 140), (0.4, 0.0, 180), (0.8, 0.8, 300)
_UNFELT = ("result", "own_result", "nobody_ahead")
# A real board read that lands while one of these is on screen redraws it; any later screen keeps the target it had.
BOARD_STATES = ("hub", "board", "board_new", "no_board", "nobody_ahead")
BOARD_TIMES_MS = 1000                # attract mode's runs to beat are taken from the real boards this often
_LOG_H = re.compile(r"[0-9a-f]{64}")
# What each arcade game draws her ghost as (games/*/src/view.cpp), so PB can say what to look for.
GHOST_LOOKS = {"MDGP": "the *cyan kart*", "ZIPG": "the *pale Zip*", "RUSH": "the *see-through runner*",
               "SEGF": "the *teal phantom*", "SHIP": "the *see-through runner*"}
log = logging.getLogger(__name__)


def ordinal(n):
    """1 -> "1st", 12 -> "12th", 23 -> "23rd"; None -> ""."""
    if n is None:
        return ""
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _today():
    return time.strftime("%Y-%m-%d")


def _you(b):
    """YOU's place on board b ("6th"), or "" with no board."""
    return ordinal(next((r.rank for r in b.rows if r.you), None))


def _split_text(job):
    """The comparison's answer as "0:42 to 0:51, -0.40 s": "comparing..." while it runs, "" when there is none."""
    if job is None:
        return ""
    if not job.done():
        return "comparing..."
    try:
        worst = (job.result() or {}).get("worst")
    except Exception:
        return ""
    if not worst:
        return ""
    return f"{coach.fmt_clock(worst['start'])} to {coach.fmt_clock(worst['end'])}, -{coach.fmt_secs(worst['loss'])}"


class HandlerGlue:
    def __init__(self, app):
        self.app = app
        self.path = os.path.join(app.state_dir, "handler.json")
        self._ledger = ledger.load(self.path)
        self.race = None                   # (flow, seller, log_frames) while a RaceTarget's game runs
        self.pending = None                # (game, entry, extra ctx): a flow that opens once PB is quiet on Home
        self._game = None                  # the open flow's Game (None: no game)
        self._raced = False                # a race left its numbers in ctx: the hub puts the board's back
        self._pool = ThreadPoolExecutor(max_workers=1)   # the comparison: never behind the warm-up
        self._warm_pool = ThreadPoolExecutor(max_workers=1)
        self._jobs = {}                    # (arcade id, best final_hash) -> the comparison's Future
        self._job = None                   # the open flow's comparison
        self._log_frames = {}              # arcade id -> its test log's time (None: no board); the logs never change
        self._ghosts = {}                  # arcade id -> her ghost, drawn from the same log (None: it did not load)
        self._warm_jobs = {}               # (arcade id, "time" or "ghost") -> its warm_up read
        self._locks = {}                   # (arcade id, "time" or "ghost") -> its read's Lock
        self._felt = None                  # (flow, state name) the pad last rumbled for, or saw without a rumble
        self._read = None                  # the real board read the open flow's board was built from
        self._real_ghosts = {}             # a real target's checked log -> her ghost bytes, drawn once
        self._times_ms = BOARD_TIMES_MS    # since attract mode's runs to beat were last taken from the real boards
        # A sale counted before a restart, never told: PB tells it now. Only the mock counts sales, so a real board
        # never tells one (it stays in the ledger for a mocked run again).
        if self._ledger.pending_sale is not None and not self._real():
            self.pending = self._sale_offer(self._ledger.pending_sale)

    def _real(self):
        """The board is real (Arkiv): its rows, never the mock runners."""
        return not self.app.sponsors.mocked("board")

    @property
    def ledger(self):
        """The console's one ledger. A flow may replace it (Start over), so the newest flow's is the current one."""
        flow = self.app.nav.handler
        return flow.ledger if flow is not None else self._ledger

    # ---- opening a flow ---------------------------------------------------------------------------------------------
    def open(self, game, entry="hub", extra=None):
        """A new flow for game (None: no game) on screen at entry, extra laid over its context (a sale for a game no
        longer in the library brings its own "game"). Returns the command its start produced."""
        ctx = self._context(game)
        ctx.update(extra or {})
        self._game, self._raced = game, False
        flow = Flow(self.app.sponsors, self.ledger, self.path, game.id if game is not None else None, ctx, _today)
        return self.app.nav.open_handler(flow, entry)

    def offer_book(self, today):
        """The day's first start with no record book: PB offers one, once PB is quiet."""
        prefs = self.app.prefs
        if self.ledger.book is None and prefs.handler_offered != today:
            self.pending = (None, "book", {})
            prefs.handler_offered = today
            settings.save(self.app.cfg.state_path, prefs)

    def frame(self, dt):
        """Once a frame: tick the open flow, or open a waiting one when PB is quiet on Home. Returns a command for the
        app (a RaceTarget), or None."""
        nav = self.app.nav
        real = self._real()
        if real:
            self._board_times(dt)
        if nav.screen is Screen.HANDLER:
            flow = nav.handler
            if self._raced and flow.state.name == "hub":
                self._raced = False
                flow.ctx.update(self._context(self._game), run_frames=None)
            elif real and flow.state.name in BOARD_STATES:
                self._fresh_board(flow)
            if self._job is not None:
                flow.ctx["split"] = _split_text(self._job)
            cmd = flow.tick(dt)
            if isinstance(cmd, CloseHandler):      # the flow's own clock can lead Home too (apply's are Nav's)
                nav.close_handler()
                return None
            self._feel(flow)
            return cmd
        if self.pending is not None and nav.mascot is None and nav.stack == [Screen.HOME] and not self.app.error:
            game, entry, extra = self.pending
            self.pending = None
            try:
                cmd = self.open(game, entry, extra)
            except Exception:                      # nobody asked for it: never a crash, let alone one at every start
                log.exception("could not open the %s flow", entry)
                if nav.screen is Screen.HANDLER:
                    nav.close_handler()
                cmd = None
            if entry == "sale" and self.ledger.pending_sale is not None:
                self.ledger.pending_sale = None    # told now: a restart never tells it twice
                ledger.save(self.path, self.ledger)
            return cmd
        return None

    def _feel(self, flow):
        """Rumble once as the flow arrives in a state that landed, failed or sold (states.py's kind)."""
        seen = (flow, flow.state.name)
        if seen == self._felt:
            return
        self._felt = seen
        kind, name = flow.state.kind, flow.state.name
        pattern = (SALE_RUMBLE if name == "sale" else OK_RUMBLE if kind == "ok" and name not in _UNFELT
                   else NO_RUMBLE if kind == "no" else None)
        if pattern is not None:
            self.app.inputs.rumble(*pattern)

    # ---- the context ------------------------------------------------------------------------------------------------
    def _context(self, game):
        """Every placeholder the app fills for game, built fresh (board, best, runs, split). Starts the comparison."""
        arcade = game.arcade if game is not None else None
        arcades = [arcade] if arcade else [g.arcade for g in self.app.nav.games if g.arcade]
        ctx = {"game": game.title if game is not None else "this game", "buyer": "", "wallet": MOCK_WALLET,
               "arcade": bool(arcade), "arcade_id": arcade.get("id") if arcade else None,
               "game_titles": {g.id: g.title for g in self.app.nav.games},
               "other_book": ledger.make_book(random.Random()),
               "sold": sum(x.get("sold", 0) for x in self.ledger.listings),
               "runs": str(sum(self._runs(a) for a in arcades)),
               "ghost_look": GHOST_LOOKS.get(arcade.get("id"), "the *see-through runner*") if arcade else "the ghost"}
        if arcade is None:
            self._job = None
            ctx.update(self._board_ctx(None, None, None), log_frames=None, best_frames=None, run_time="", split="")
            return ctx
        best = self._best(arcade)
        best_frames = best["time_frames"] if best else None
        log_frames = None if self._real() else self._log_time(arcade)   # a real board never needs the test log
        board_ctx = self._board_ctx(arcade, log_frames, best_frames)
        ctx.update(board_ctx, log_frames=log_frames, best_frames=best_frames,
                   run_time=coach.fmt_time(best_frames) if best_frames is not None else "",
                   split=self._split(arcade, best, log_frames, board_ctx["target_log_h"]))
        return ctx

    def _board(self, log_frames, best_frames):
        """The mock board, its mock runners HUMAN only while World is mocked (a real World vouches for none of them).
        YOU's own mark is the flow's: it follows the record book."""
        return board.build(log_frames, best_frames, mock_humans=self.app.sponsors.mocked("world"))

    def _real_board(self, arcade, best_frames):
        """(the real board for arcade from its last Arkiv read, that read). No read yet: no board, never made up."""
        read = self.app.sponsors.board(arcade["id"]) if arcade else None
        led = self.ledger
        you = led.credential if led.book and led.world_verified else None
        return board.build_real(read.rows if read else (), best_frames, led.book, you), read

    def _board_for(self, arcade, log_frames, best_frames):
        return self._real_board(arcade, best_frames)[0] if self._real() else self._board(log_frames, best_frames)

    def _board_ctx(self, arcade, log_frames, best_frames):
        """Where YOU stand on the board, what beating the target gives, and the target itself: her name, time and
        frames, and on a real board her run, its listing and its log."""
        if self._real():
            b, read = self._real_board(arcade, best_frames)
            self._read = read
            t = b.target
            run = next((r for r in read.rows if r.key == t.key), None) if t is not None and read else None
            mine = next((r.frames for r in b.rows if r.you), None)
            return {"board_rows": b.rows, "board_case": b.case, "target": t.name if t else "",
                    "target_time": coach.fmt_time(t.frames) if t else "", "target_frames": t.frames if t else None,
                    "target_run": t.key if t else None, "target_listing": t.listing if t else None,
                    "target_log_h": run.log_h if run else None,
                    "gap": "%.1f s" % ((mine - t.frames) / 60) if t and mine is not None and mine > t.frames else "",
                    "rank": _you(b), "new_rank": ordinal(t.rank) if t else ""}
        b = self._board(log_frames, best_frames)
        behind = log_frames is not None and best_frames is not None and best_frames > log_frames
        return {"board_rows": b.rows, "board_case": b.case, "target": board.SELLER if b.target else "",
                "target_time": coach.fmt_time(log_frames) if log_frames is not None else "",
                "target_frames": log_frames if b.target else None, "target_run": None, "target_listing": None,
                "target_log_h": None, "gap": "%.1f s" % ((best_frames - log_frames) / 60) if behind else "",
                "rank": _you(b), "new_rank": ordinal(b.target.rank) if b.target else ""}

    def _fresh_board(self, flow):
        """A newer real board read for the open game: its board screens show it (the first press after start may
        come before the first read)."""
        arcade = self._game.arcade if self._game is not None else None
        if not arcade or self.app.sponsors.board(arcade["id"]) is self._read:
            return
        flow.ctx.update(self._board_ctx(arcade, None, flow.ctx.get("best_frames")))

    def _board_times(self, dt):
        """Attract mode's run to beat for each arcade game from its real board: the fastest run whose ghost is listed
        (none listed: no card)."""
        self._times_ms += dt
        if self._times_ms < BOARD_TIMES_MS:
            return
        self._times_ms = 0
        for game in self.app.nav.games:
            gid = game.arcade.get("id") if game.arcade else None
            read = self.app.sponsors.board(gid, look=False) if isinstance(gid, str) else None
            run = next((r for r in read.rows if r.listing), None) if read else None
            if run is not None:
                self.app.nav.board_times[game.id] = (run.book or run.label, coach.fmt_time(run.frames))
            else:
                self.app.nav.board_times.pop(game.id, None)

    def _test_log(self, arcade):
        return os.path.join(self.app.cfg.testlogs_dir, arcade["id"] + ".acl")

    def _log_time(self, arcade):
        """The game's shipped test log's time: None when it does not finish or the replay tool fails. Asked once."""
        self._await_warm((arcade["id"], "time"))
        return self._read_log_time(arcade)

    def _read_log_time(self, arcade):
        gid = arcade["id"]
        if gid not in self._log_frames:
            with self._lock((gid, "time")):                         # the main thread or the warm-up: one replay
                if gid not in self._log_frames:
                    self._read_log_time_now(arcade, gid)
        return self._log_frames[gid]

    def _read_log_time_now(self, arcade, gid):
        try:
            frames = self.app.bridge.log_time(arcade, self._test_log(arcade))
        except Exception:
            log.exception("no board for %s", gid)
            frames = None
        if frames is not None:                                      # attract mode shows whose time to beat
            for game in self.app.nav.games:
                if game.arcade and game.arcade.get("id") == gid:
                    self.app.nav.board_times[game.id] = (board.SELLER, coach.fmt_time(frames))
        self._log_frames[gid] = frames

    def _lock(self, key):
        """The lock for one log's (arcade id, "time" or "ghost") read: a PB press and the warm-up never replay the
        same log at once (setdefault is atomic, so both threads get the same lock)."""
        return self._locks.setdefault(key, threading.Lock())

    # ---- the start-up warm-up ---------------------------------------------------------------------------------------
    def warm_up(self):
        """Read every arcade game's test log time (its board), then her ghost from each, in the background on a worker
        of their own, in Home's order: the first PB press on a game never waits for a replay. One replay a job, keyed
        (arcade id, "time" or "ghost"): a launch (settle) or a PB press waits for at most the one already running, and
        cancels the rest; a cancelled one is queued again after the next game."""
        if self._real():                           # the boards are Arkiv's, read by the sponsors' own worker
            return
        arcades = [g.arcade for g in self.app.nav.row if g is not None and g.arcade]
        arcades = [a for a in arcades if isinstance(a.get("id"), str) and os.path.isfile(self._test_log(a))]
        for kind, read in (("time", self._read_log_time), ("ghost", self._warm_ghost)):
            for arcade in arcades:
                key = (arcade["id"], kind)
                job = self._warm_jobs.get(key)
                if job is not None and not job.cancelled():       # queued, running or read: once is enough
                    continue
                self._warm_jobs[key] = self._warm_pool.submit(read, arcade)

    def _warm_ghost(self, arcade):
        if self._read_log_time(arcade) is not None:             # read already, unless a launch cut the time job
            self._load_ghost(arcade)

    def _await_warm(self, key):
        """A background read of key not started yet is cancelled (the caller reads it now, never behind the queue);
        one running is let finish rather than replayed twice."""
        job = self._warm_jobs.get(key)
        if job is None or job.cancel() or job.done():
            return
        try:
            job.result()
        except Exception:                          # failed: the caller reads it again
            pass

    def _best(self, arcade):
        """The player's best run (the bridge's runs_dir/best/<ID>.json), or None."""
        try:
            with open(os.path.join(self.app.cfg.runs_dir, "best", arcade["id"] + ".json"), encoding="utf-8") as f:
                best = json.load(f)
        except (OSError, ValueError):
            return None
        return best if isinstance(best, dict) and isinstance(best.get("time_frames"), int) else None

    def _runs(self, arcade):
        """The record book's runs: its rows on a real board, else this console's finished runs."""
        if self._real():
            read, book = self.app.sponsors.board(arcade["id"], look=False), self.ledger.book
            return sum(1 for r in read.rows if r.book == book) if read and book else 0
        try:
            return len(self.app.bridge.history(arcade["id"], n=1000))
        except Exception:
            log.exception("run history unavailable")
            return 0

    # ---- where the target is faster: the one background job ---------------------------------------------------------
    def _split(self, arcade, best, log_frames, target_log_h=None):
        """Start (or find) the comparison of the player's best ghost with the target's; its text so far. Only with
        the target's log on this console: the test log on the mock board, a real target's once her ghost is loaded."""
        self._job = None
        if best is None:
            return ""
        if self._real():
            target_log = self._ghost_log(target_log_h)
        else:
            target_log = self._test_log(arcade) if log_frames is not None else None
        if target_log is None:
            return ""
        key = (arcade["id"], best.get("final_hash"), target_log)
        if key not in self._jobs:
            try:
                bridge = self.app.bridge
            except Exception:
                log.exception("no comparison for %s", arcade["id"])
                return ""
            best_log = os.path.join(self.app.cfg.runs_dir, "best", arcade["id"] + ".acl")
            self._jobs[key] = self._pool.submit(                    # the best run and the target's both finish
                lambda: coach.compare(bridge.ghost(arcade, best_log), bridge.ghost(arcade, target_log), finished=True))
        self._job = self._jobs[key]
        return _split_text(self._job)

    def _ghost_log(self, log_h):
        """A real target's checked log on this console (runs_dir/ghosts/<log_h>.acl), or None."""
        if not (isinstance(log_h, str) and _LOG_H.fullmatch(log_h)):
            return None
        path = os.path.join(self.app.cfg.runs_dir, "ghosts", log_h + ".acl")
        return path if os.path.isfile(path) else None

    def settle(self):
        """Let a comparison still running finish first: a game never shares the CPU with it. No time limit of its
        own: the job is two replays and the bridge bounds each one (a limit here let the second run during the game).
        Warm-up reads not yet started are cancelled (a PB press reads its game itself); a running one finishes."""
        for job in self._warm_jobs.values():
            job.cancel()
        for job in list(self._jobs.values()) + list(self._warm_jobs.values()):
            if not job.done():
                try:
                    job.result()
                except Exception:
                    pass

    # ---- racing -----------------------------------------------------------------------------------------------------
    @property
    def racing(self):
        return self.race is not None

    def race_target(self, cmd):
        """Start the game, racing the seller's ghost (her shipped test log's) or, with no seller, the player's best. A
        game that cannot start leaves the flow on its "no time this run" screen, never on "racing"."""
        nav = self.app.nav
        flow = nav.handler
        if flow is None:
            return
        game = next((g for g in nav.games if g.id == cmd.game_id), None)
        if game is None or not game.arcade or not game.rom_exists:
            if game is not None and not game.rom_exists:
                nav.notice = f"{game.title}: ROM file missing"
            log.warning("cannot race %s", cmd.game_id)
            flow.finish_race("unfinished", None)
            return
        if cmd.seller and flow.ctx.get("target_run"):              # a real target: the log load_ghost checked
            ghost = self._real_ghost(game.arcade, flow.ctx)
        else:
            ghost = self._her_ghost(game.arcade) if cmd.seller else None
        if cmd.seller and ghost is None:           # never her race with the player's own best in its place
            nav.notice = f"{cmd.seller}'s ghost could not be loaded"
            flow.finish_race("unfinished", None)
            return
        self.race = (flow, cmd.seller, flow.ctx.get("target_frames"), flow.ctx.get("log_frames"), game.arcade)
        try:
            self.app.launch(game, ghost=ghost)
        finally:
            self.race = None

    def _real_ghost(self, arcade, ctx):
        """A real target's ghost bytes, drawn once from the log load_ghost checked against her row (ghost_log, which
        must be her log_h's file). None when it is not here or does not draw; that is not kept."""
        path, expected = ctx.get("ghost_log"), self._ghost_log(ctx.get("target_log_h"))
        if not path or expected is None or os.path.abspath(path) != os.path.abspath(expected):
            return None
        if expected not in self._real_ghosts:
            try:
                ghost = self.app.bridge.ghost_bytes(arcade, expected)
            except Exception:
                log.exception("the target's ghost did not draw for %s", arcade.get("id"))
                return None
            if not ghost:
                return None
            self._real_ghosts[expected] = ghost
        return self._real_ghosts[expected]

    def _her_ghost(self, arcade):
        """The target's ghost bytes from the game's test log, drawn once (a replay): racing her again never waits.
        None when it did not load; that is not kept, so the next race tries again."""
        self._await_warm((arcade["id"], "ghost"))
        return self._load_ghost(arcade)

    def _load_ghost(self, arcade):
        gid = arcade["id"]
        with self._lock((gid, "ghost")):
            if gid not in self._ghosts:
                try:
                    ghost = self.app.bridge.ghost_bytes(arcade, self._test_log(arcade))
                except Exception:
                    log.exception("the target's ghost did not load for %s", gid)
                    return None
                if not ghost:
                    log.warning("the target's ghost is empty for %s", gid)
                    return None
                self._ghosts[gid] = ghost
            return self._ghosts[gid]

    def game_over(self, game, res, ok, asked):
        """A game ended (res: the bridge's verified run, or None). A handler race goes back to its flow; any other new
        best offers its listing once PB has said his piece, if there is a record book to list it in; otherwise a
        listing may sell."""
        if self.race is not None:
            self._race_over(res, ok, asked)
        elif res and res.get("new_best") and self.ledger.book:   # no book: the day's first start offers one
            self.pending = (game, "list", {})
        elif self.pending is None and self.app.nav.stack == [Screen.HOME]:
            self._sell()
        if self.app.cfg.handler_warm:
            self.warm_up()                         # the reads the launch cancelled, now the game is over

    def _race_over(self, res, ok, asked):
        flow, seller, target_frames, log_frames, arcade = self.race
        finished = bool(res) and bool(res.get("finished"))
        run = res.get("time_frames") if finished else None
        if not res:
            result = "unfinished" if not ok or asked else "unverified"
        elif not finished:
            result = "unfinished"
        elif seller:                               # judged against her time: her row's on a real board
            result = "beat" if run is not None and target_frames is not None and run < target_frames else "lost"
        else:
            result = "beat" if res.get("new_best") else "lost"
        # The result screens' numbers: the old and new place of YOU (a loss shows no gain), and the gap to her.
        old = flow.ctx.get("best_frames")
        best = run if finished and res.get("new_best") else old
        after = self._board_for(arcade, log_frames, best)
        ref = target_frames if target_frames is not None else log_frames
        flow.ctx.update(board_rows=after.rows, board_case=after.case, best_frames=best,
                        rank=_you(self._board_for(arcade, log_frames, old)), new_rank=_you(after),
                        gap="%.1f s" % (abs(run - ref) / 60) if None not in (run, ref) else "")
        self._raced = True
        flow.finish_race(result, run)
        if self.app.nav.handler is not None:
            self.app.nav.resume_handler()

    # ---- a mock sale ------------------------------------------------------------------------------------------------
    def _sell(self):
        """A mock buyer for the first listing that has waited a minute: at most one sale each return Home."""
        led, now = self.ledger, time.time()
        listing = next((x for x in led.listings if x.get("sold", 0) == 0 and isinstance(x.get("at"), (int, float))
                        and now - x["at"] >= SALE_AFTER_S), None)
        if listing is None:
            return
        r = self.app.sponsors.begin("sales", {"game": listing.get("game")}).poll()
        if not (r and r.ok):
            return
        listing["sold"] = listing.get("sold", 0) + 1
        led.pending_sale = {"game": listing.get("game"), "buyer": r.data.get("buyer", ""),
                            "frames": listing.get("frames")}
        ledger.save(self.path, led)
        self.pending = self._sale_offer(led.pending_sale)

    def _sale_offer(self, sale):
        """The sale flow PB opens for a sale the ledger keeps: (game, "sale", extra ctx)."""
        game = next((g for g in self.app.nav.games if g.id == sale.get("game")), None)
        extra = {"buyer": str(sale.get("buyer") or "")}
        if game is None:
            extra["game"] = str(sale.get("game") or "your game")
        if isinstance(sale.get("frames"), int):
            extra["run_time"] = coach.fmt_time(sale["frames"])
        return game, "sale", extra

    def close(self):
        for pool in (self._pool, self._warm_pool):
            pool.shutdown(wait=False, cancel_futures=True)

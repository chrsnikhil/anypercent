"""SHIP IT! through the arcade kit: the ROM records every frame's buttons from boot and, when the run ends, writes
the last-run log (and a new BEST) into the kit's save sections; out/arcade_replay replays a log through the PC
rules and must reach the hash the ROM claimed. Leaving the results resets the ROM, so every run starts at boot."""
import ctypes
import json
import os
import struct
import subprocess
import sys

import pytest

from conftest import A, GAME_DIR, SC_CLEAR, SC_MISSED, SC_PLAY, START, Game, sh
from test_rom import SPRITE_TILES, TEXT_MARGIN, first_frame, symbols

sys.path.insert(0, os.path.join(GAME_DIR, "..", "arcade", "py"))
import arcade_save as S  # noqa: E402

ROM = os.path.join(GAME_DIR, "shipit.gba")
ELF = os.path.join(GAME_DIR, "shipit.elf")
ROUTES = os.path.join(GAME_DIR, "tests", "routes")


def load_keys(name):
    with open(os.path.join(ROUTES, name)) as f:
        return [int(line, 16) for line in f if line.strip()]


SETTLE = [0] * 30                    # the ROM saves 1 KB a frame after the run ends (src/runlog.cpp)
FULL = load_keys("full_run.keys") + SETTLE
MISSED = load_keys("first_chai.keys") + [0] * (36 * 450) + SETTLE


def session(runner, keys, tmp_path, save_in=None):
    """Runs the ROM on one key mask per frame (gba_run reads "keys frames" pairs, so the keys are converted).
    Returns (save image after the last frame, [g_dbg_steps, g_dbg_run_written] for every frame)."""
    script = tmp_path / "script.txt"
    script.write_text("".join("%x 1\n" % k for k in keys))
    out = tmp_path / "after.sav"
    watch = ",".join("%x" % a for a in symbols(ELF, "g_dbg_steps", "g_dbg_run_written"))
    cmd = [runner, ROM, str(script), "--watch", watch, "--save-out", str(out)]
    if save_in:
        cmd += ["--save-in", str(save_in)]
    rows = [[int(v, 16) for v in line.split()[1:]] for line in sh(*cmd).splitlines()]
    return bytearray(out.read_bytes()), rows


def boots(rows):
    """The frame of the first rules step after each boot (power-on, then every reset)."""
    return [i for i, (steps, _) in enumerate(rows) if steps == 1]


def play(runner, keys, tmp_path, save_in=None):
    """(save image, the frame of the first rules step, g_dbg_run_written at the end) for a single-boot session."""
    save, rows = session(runner, keys, tmp_path, save_in)
    return save, boots(rows)[0], rows[-1][1]


def blank(tmp_path):
    p = tmp_path / "blank.sav"
    p.write_bytes(bytes(S.blank()))
    return p


def replay(tmp_path, log):
    sh("make", "-f", "tools.mk", "replay")
    p = tmp_path / "run.acl"
    p.write_bytes(log)
    r = subprocess.run([os.path.join(GAME_DIR, "out", "arcade_replay"), str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def decode(log):
    """The frames of a run log body (arcade/src/ac_log.h): one varint token per run; even = toggle one bit of the
    previous run's buttons (bit (V >> 1) & 15, count V >> 5), odd = set (count V >> 1, then buttons u16)."""
    keys, pos, buttons = [], 32, 0
    while pos < len(log):
        v = shift = 0
        while True:
            b = log[pos]
            pos += 1
            v |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        if v & 1:
            count, buttons = v >> 1, log[pos] | log[pos + 1] << 8
            pos += 2
        else:
            count, buttons = v >> 5, buttons ^ (1 << ((v >> 1) & 15))
        keys += [buttons] * count
    return keys


def run_end(lib, keys):
    """The keys the PC rules consume up to and including the frame the run ends (SC_CLEAR or SC_MISSED)."""
    g = Game(lib)
    for i, k in enumerate(keys):
        g.step(k)
        if g.scene() in (SC_CLEAR, SC_MISSED):
            return keys[:i + 1]
    raise AssertionError("the run never ended")


def test_a_missed_run_writes_a_last_run_that_replays_to_its_hash(runner, lib, tmp_path):
    save, first, written = play(runner, MISSED, tmp_path, blank(tmp_path))
    assert written == 1
    log, flags = S.get(save, b"SHIP", S.RUN)
    assert flags == 0 and len(log) < 4096                    # present, not truncated, small
    head = S.parse_log_header(log)
    assert head["game"] == b"SHIP" and head["rules_version"] == 2 and head["seed"] == 0 and head["trophies"] == 0
    assert decode(log) == run_end(lib, MISSED[first:])       # every frame the rules stepped, from rules_init()
    res = replay(tmp_path, log)
    assert res["hash_matches"] and res["complete"] and not res["finished"]
    assert S.get(save, b"SHIP", S.BEST) is None              # a missed run is no best
    assert save[0:8] == b"\xff" * 8                          # nor does it touch the legacy record


def test_a_shipped_run_writes_a_last_run_that_replays_to_its_hash(runner, lib, tmp_path):
    save, first, written = play(runner, FULL, tmp_path, blank(tmp_path))
    assert written == 1
    got = S.get(save, b"SHIP", S.RUN)
    assert got is not None and got[1] == 0                   # present, not truncated
    log = got[0]
    head = S.parse_log_header(log)
    assert head["game"] == b"SHIP" and head["trophies"] & 1  # shipped
    assert decode(log) == run_end(lib, FULL[first:]) and head["frames"] == len(decode(log))
    res = replay(tmp_path, log)
    assert res["hash_matches"] and res["complete"] and res["finished"] and res["trophies"] == head["trophies"]
    best = S.get(save, b"SHIP", S.BEST)
    assert best and S.parse_best(best[0])["frames"] == res["time_frames"]
    assert S.parse_best(best[0])["final_hash"] == head["final_hash"]
    assert save[0:2] == b"SI"                                # the legacy best record is still written


def test_the_shipped_log_fits_with_room_to_spare(runner, tmp_path):
    # The bot's route changes buttons ~3.5k times in ~12k frames; most changes are one bit (toggle tokens, 1 byte).
    save, _, _ = play(runner, FULL, tmp_path)
    log, _ = S.get(save, b"SHIP", S.RUN)
    assert len(log) < 12000 and len(log) < S.CAP[S.RUN]


def test_a_slower_run_keeps_the_best(runner, tmp_path):
    old = S.blank()
    S.fmt(old, b"SHIP")
    S.put(old, S.BEST, struct.pack("<4I16x", 100, 0, 1, 1234))
    p = tmp_path / "old.sav"
    p.write_bytes(bytes(old))
    save, _, _ = play(runner, FULL, tmp_path, p)
    assert S.parse_best(S.get(save, b"SHIP", S.BEST)[0])["frames"] == 100
    assert S.get(save, b"SHIP", S.RUN) is not None           # the last run is written all the same


def test_leaving_the_results_saves_then_resets_so_the_next_run_is_saved_too(runner, lib, tmp_path):
    # Run 1 is missed and Start is pressed on the very next frame, while its save is still flushing: the ROM
    # finishes the save, then resets. Run 2 (the shipped route) starts from the fresh boot and replaces it.
    _, rows = session(runner, [0] * 60, tmp_path)
    boot = boots(rows)[0]                                     # power-on frames before the first rules step
    end = boot + len(run_end(lib, MISSED[boot:]))             # the frame after run 1's last
    first_part = MISSED[:end] + [START] + [0] * 60

    save, rows = session(runner, first_part, tmp_path, blank(tmp_path))
    starts = boots(rows)
    assert starts[0] == boot and len(starts) == 2, "no reset after the results"
    log, flags = S.get(save, b"SHIP", S.RUN)                  # run 1, saved whole before the reset
    assert flags == 0 and decode(log) == MISSED[boot:end]
    res = replay(tmp_path, log)
    assert res["hash_matches"] and res["complete"] and not res["finished"]

    keys = first_part + [0] * 150 + FULL
    save, rows = session(runner, keys, tmp_path, blank(tmp_path))
    starts = boots(rows)
    assert len(starts) == 2 and rows[-1][1] == 1              # one save since the reset
    log, flags = S.get(save, b"SHIP", S.RUN)                  # run 2 replaced it
    assert flags == 0 and decode(log) == run_end(lib, keys[starts[1]:])
    res = replay(tmp_path, log)
    assert res["hash_matches"] and res["complete"] and res["finished"]
    assert S.parse_best(S.get(save, b"SHIP", S.BEST)[0])["frames"] == res["time_frames"]


def test_an_old_version_save_is_reformatted(runner, lib, tmp_path):
    old = S.blank()
    S.fmt(old, b"SHIP")
    S.put(old, S.BEST, struct.pack("<4I16x", 100, 0, 1, 1234))
    old[S.BASE + 4] = 1                                       # a version 1 table: the old layout
    p = tmp_path / "v1.sav"
    p.write_bytes(bytes(old))
    save, first, _ = play(runner, MISSED, tmp_path, p)
    assert save[S.BASE + 4] == S.VERSION and S.get(save, b"SHIP", S.BEST) is None
    log, flags = S.get(save, b"SHIP", S.RUN)
    assert flags == 0 and decode(log) == run_end(lib, MISSED[first:])


# The ghost: the ROM draws a translucent second player from the GHOST section, sampled by out/arcade_replay --ghost
# from a run log. g_dbg_ghost is 1 while the ghost sprite is visible, g_dbg_ghost_xy its (x << 16) | y.

def watch(runner, keys, tmp_path, names, save_in=None, save_out=None):
    """Runs the ROM on one key mask per frame; returns the watched symbols' values for every frame."""
    script = tmp_path / "watch.txt"
    script.write_text("".join("%x 1\n" % k for k in keys))
    cmd = [runner, ROM, str(script), "--watch", ",".join("%x" % a for a in symbols(ELF, *names))]
    if save_in:
        cmd += ["--save-in", str(save_in)]
    if save_out:
        cmd += ["--save-out", str(save_out)]
    return [[int(v, 16) for v in line.split()[1:]] for line in sh(*cmd).splitlines()]


def ghost_bytes_of(runner, tmp_path, keys, save_in=None):
    """Records keys (on a blank cartridge unless save_in); returns the ghost the host tool extracts from the saved
    run log, and the log."""
    out = tmp_path / "rec.sav"
    watch(runner, keys, tmp_path, ["g_dbg_steps"], save_in or blank(tmp_path), out)
    log, _ = S.get(bytearray(out.read_bytes()), b"SHIP", S.RUN)
    sh("make", "-f", "tools.mk", "replay")
    (tmp_path / "rec.acl").write_bytes(log)
    sh(os.path.join(GAME_DIR, "out", "arcade_replay"), str(tmp_path / "rec.acl"), "--ghost", str(tmp_path / "g.bin"))
    return (tmp_path / "g.bin").read_bytes(), log


def ghost_save(tmp_path, ghost, name="ghost.sav"):
    save = S.blank()
    S.fmt(save, b"SHIP")
    assert S.put(save, S.GHOST, ghost)
    path = tmp_path / name
    path.write_bytes(bytes(save))
    return path


START_X, START_Y = 141, 160              # gen/scene_office.h: the player's start
GHOST_WATCH = ["g_dbg_steps", "g_dbg_ghost", "g_dbg_ghost_xy"]


def test_the_ghost_follows_the_recorded_route(runner, lib, tmp_path):
    ghost, log = ghost_bytes_of(runner, tmp_path, FULL)
    parsed = S.parse_ghost(ghost)
    period, points = parsed["period"], parsed["points"]
    recorded = {}                                             # the recorded run's player after each rules step
    g = Game(lib)
    for steps, k in enumerate(decode(log), 1):
        g.step(k)
        recorded[steps] = (g.px(), g.py())
    rows = watch(runner, FULL, tmp_path, GHOST_WATCH, ghost_save(tmp_path, ghost))
    # Playing the route again with its ghost (a save that differs can boot a frame earlier or later, so this run need
    # not be the recorded one frame for frame). The ghost is aligned on play start: its first in-play sample (flags
    # AC_GHOST_PLAY) is shown on this run's first in-play step, so this run's step s shows the ghost's step
    # anchor + (s - live). The ghost is shown exactly while this run is in play in the ghost's room; it sits on the
    # recorded player on every sampled step (sample k is taken after rules step k * period + 1) and between samples
    # it lies between the recorded positions at the two samples around it.
    anchor = next(k for k, p in enumerate(points) if p[3] & AC_GHOST_PLAY) * period + 1
    g, live, shown_at = None, None, {}
    for i, (steps, shown, xy) in enumerate(rows):
        if steps == 0:
            continue
        if g is None:
            assert steps == 1
            g = Game(lib)
        g.step(FULL[i])
        if live is None and g.scene() == SC_PLAY:
            live = steps
        if live is None:
            assert shown == 0, "frame %d (step %d): ghost shown before play" % (i, steps)
            continue
        gs = anchor + (steps - live)
        room = points[min((gs - 1) // period, len(points) - 1)][3] & ~AC_GHOST_PLAY
        want = 1 if g.scene() == SC_PLAY and g.room() == room else 0
        assert shown == want, "frame %d (step %d): ghost shown %d" % (i, steps, shown)
        if shown:
            shown_at[gs] = (xy >> 16, xy & 0xFFFF)
    assert len(shown_at) > 1000
    sampled = 0
    last = (len(points) - 1) * period + 1
    for steps, (x, y) in shown_at.items():                    # keyed by the ghost's own step
        if steps >= last:
            assert (x, y) == recorded[last], "step %d: the ghost left its last sample" % steps
            continue
        k = (steps - 1) // period
        a, b = recorded[k * period + 1], recorded[(k + 1) * period + 1]
        if (steps - 1) % period == 0:
            sampled += 1
            assert abs(x - a[0]) <= 1 and abs(y - a[1]) <= 1, "step %d: ghost (%d, %d), recorded %s" % (
                steps, x, y, a)
        else:
            assert min(a[0], b[0]) <= x <= max(a[0], b[0]), "step %d: ghost x %d, samples %s %s" % (steps, x, a, b)
            assert min(a[1], b[1]) <= y <= max(a[1], b[1]), "step %d: ghost y %d, samples %s %s" % (steps, y, a, b)
    assert sampled > 100


def test_the_player_stays_solid_over_its_ghost(runner, lib, tmp_path):
    # The GBA blends a half-transparent sprite with the backgrounds only, never with another sprite, so a ghost drawn
    # in front of the player would wash the live player out wherever they overlap. It must be drawn behind: with
    # the ghost exactly on the player (same place, facing and animation step), the screen is the same as with the
    # ghost hidden.
    g1, _ = ghost_bytes_of(runner, tmp_path, FULL)
    # Recorded again on a cartridge that holds a ghost, so the replay below boots on the same frame as the recording
    # (a ghost's checksum can cost the boot a frame) and the ghost sits exactly on the player at its samples.
    ghost, log = ghost_bytes_of(runner, tmp_path, FULL, ghost_save(tmp_path, g1, "first.sav"))
    parsed = S.parse_ghost(ghost)
    period = parsed["period"]
    elsewhere = S.ghost_bytes(b"SHIP", parsed["source_hash"], period,
                              [(x, y, a, 7) for x, y, a, _ in parsed["points"]])    # room 7: never shown
    shown_sav, hidden_sav = ghost_save(tmp_path, ghost, "shown.sav"), ghost_save(tmp_path, elsewhere, "hidden.sav")
    shown = watch(runner, FULL, tmp_path, GHOST_WATCH, shown_sav)
    hidden = watch(runner, FULL, tmp_path, GHOST_WATCH, hidden_sav)
    assert [r[0] for r in shown] == [r[0] for r in hidden]                  # the same boot, the same steps
    # A frame where the ghost has been exactly on the player (place and facing) for four frames running, since a
    # shot can show sprites from a frame or two before it (OAM and tiles are committed at the end of a frame).
    recorded, g = {}, Game(lib)
    for steps, k in enumerate(decode(log), 1):
        g.step(k)
        recorded[steps] = (g.px(), g.py(), g.facing())

    def on_player(i):
        steps, visible, xy = shown[i]
        if not visible or steps not in recorded:
            return False
        facing = parsed["points"][min((steps - 1) // period, len(parsed["points"]) - 1)][2]
        return (xy >> 16, xy & 0xFFFF, facing) == recorded[steps]

    frame = next(i for i in range(3000, len(FULL))
                 if all(on_player(i - d) for d in range(4))                # the ghost on the player for 4 frames
                 and recorded[shown[i][0]] != recorded[shown[i][0] - period])   # somewhere the player walked to
    assert hidden[frame][1] == 0
    script = tmp_path / "shot.txt"
    script.write_text("".join("%x 1\n" % k for k in FULL[:frame + 2]))
    shots = []
    for sav in (shown_sav, hidden_sav):
        path = tmp_path / (sav.stem + ".rgba")
        sh(runner, ROM, str(script), "--save-in", str(sav), "--shot", str(frame), str(path))
        shots.append(path.read_bytes())
    differ = sum(1 for i in range(0, len(shots[0]), 4) if shots[0][i:i + 3] != shots[1][i:i + 3])
    assert differ == 0, "the ghost shows through the player at frame %d (%d pixels differ)" % (frame, differ)


def test_no_ghost_is_drawn_without_a_ghost_section(runner, tmp_path):
    rows = watch(runner, FULL, tmp_path, GHOST_WATCH, blank(tmp_path))
    assert all(shown == 0 for _, shown, _ in rows)


def test_another_games_ghost_is_not_drawn(runner, tmp_path):
    ghost = S.ghost_bytes(b"XXXX", 0, 4, [(300, 300, 0, 0)] * 800)
    rows = watch(runner, FULL, tmp_path, GHOST_WATCH, ghost_save(tmp_path, ghost))
    assert all(shown == 0 for _, shown, _ in rows)

def hall_deadline_keys(lib):
    """test_rom's owner's-crash sequence: the full route into the hall, then idle until the deadline passes."""
    keys = load_keys("full_run.keys")
    hall = first_frame(lib, keys, lambda g: g.room() == 1 and g.scene() == SC_PLAY)
    keys = keys[:hall + 1]
    g = Game(lib)
    for k in keys:
        g.step(k)
    while g.scene() != SC_MISSED:
        keys.append(0)
        g.step(0)
    return keys + [0] * 30 + [START] + [0] * 90


@pytest.mark.parametrize("run", ["shipped", "missed", "hall_deadline"])
def test_sprite_memory_has_room_with_a_ghost_that_faces_elsewhere(runner, lib, tmp_path, run):
    # The worst case for sprite tiles: a ghost that never faces the player's way needs frames of its own. This one
    # turns through every facing and hops between the office and the hall, over test_rom's sprite-memory runs.
    keys = {"shipped": lambda: load_keys("full_run.keys") + [0] * 130 + [START] + [0] * 90 + [START, 0, 0, 0, A, 0] +
                               [0] * 60,
            "missed": lambda: load_keys("first_chai.keys") + [0] * (36 * 450) + [0] * 30 + [START] + [0] * 90,
            "hall_deadline": lambda: hall_deadline_keys(lib)}[run]()
    pts = [(START_X, START_Y, (k // 2) % 8, k % 2) for k in range(min(len(keys) // 8 + 1, 2700))]
    rows = watch(runner, keys, tmp_path, ["g_dbg_sprite_tiles", "g_dbg_ghost"],
                 ghost_save(tmp_path, S.ghost_bytes(b"SHIP", 0, 8, pts)))
    assert sum(shown for _, shown in rows) > 1000
    peak = max(tiles for tiles, _ in rows)
    assert peak <= SPRITE_TILES - TEXT_MARGIN, "peak %d sprite tiles" % peak


# Final review fixes.

AC_GHOST_PLAY = 0x80                     # ac_game.h: game_ghost() flags bit set on every in-play step


class GhostPt(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int16), ("y", ctypes.c_int16), ("angle", ctypes.c_uint8), ("flags", ctypes.c_uint8)]


def test_game_ghost_marks_the_steps_in_play(lib):
    g = Game(lib)
    pt = GhostPt()
    seen = set()
    for k in FULL[:4000]:
        g.step(k)
        lib.game_ghost(ctypes.byref(pt))
        assert bool(pt.flags & AC_GHOST_PLAY) == (g.scene() == SC_PLAY), g.scene()
        assert pt.flags & ~AC_GHOST_PLAY == g.room()
        seen.add(g.scene())
    assert SC_PLAY in seen and len(seen) > 2


def test_the_rom_counts_its_steps_through_game_step(runner, tmp_path):
    rows = watch(runner, MISSED, tmp_path, ["g_dbg_run_frames"], blank(tmp_path), tmp_path / "out.sav")
    log, _ = S.get(bytearray((tmp_path / "out.sav").read_bytes()), b"SHIP", S.RUN)
    assert rows[-1][0] == S.parse_log_header(log)["frames"] > 16000     # game_result().frames at the run's end


def test_the_ghost_aligns_on_play_start(runner, lib, tmp_path):
    # The ghost's run and this one spend different times on the title (37 frames more here): the ghost's first
    # in-play sample is shown on this run's first in-play step, and it runs on from there.
    ghost, log = ghost_bytes_of(runner, tmp_path, FULL)
    parsed = S.parse_ghost(ghost)
    period, points = parsed["period"], parsed["points"]
    k0 = next(k for k, p in enumerate(points) if p[3] & AC_GHOST_PLAY)
    anchor, last = k0 * period + 1, (len(points) - 1) * period + 1
    recorded, g = {}, Game(lib)
    for steps, k in enumerate(decode(log), 1):
        g.step(k)
        recorded[steps] = (g.px(), g.py())
    keys = [0] * 37 + FULL
    rows = watch(runner, keys, tmp_path, GHOST_WATCH + ["g_dbg_scene"], ghost_save(tmp_path, ghost))
    live = next(steps for steps, _, _, scene in rows if scene == SC_PLAY)
    checked = 0
    for steps, shown, xy, scene in rows:
        if not shown:
            continue
        assert steps >= live
        gs = anchor + (steps - live)
        if gs < last and (gs - 1) % period == 0:
            checked += 1
            x, y = recorded[gs]
            assert abs((xy >> 16) - x) <= 1 and abs((xy & 0xFFFF) - y) <= 1, "step %d: ghost %x, recorded %s" % (
                steps, xy, recorded[gs])
    assert checked > 100


def test_install_builds_the_replay_tool_first(tmp_path):
    tool = os.path.join(GAME_DIR, "out", "arcade_replay")
    if os.path.exists(tool):
        os.remove(tool)
    env = dict(os.environ, ARCA_GAMES=str(tmp_path / "games"))
    r = subprocess.run(["bash", os.path.join(GAME_DIR, "..", "sandbox", "install_arcade.sh"), GAME_DIR, "SHIP",
                        "ship-it.gba"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.access(tmp_path / "games" / "arcade" / "SHIP" / "arcade_replay", os.X_OK)
    assert (tmp_path / "games" / "built" / "ship-it.gba").exists()


def test_the_builds_take_the_kit_flags():
    kit = open(os.path.join(GAME_DIR, "..", "arcade", "mk", "arcade.mk")).read()
    flags = kit.split("ARCADE_FLAGS :=")[1].split("\n")[0].split()
    assert flags == ["-fwrapv", "-funsigned-char", "-fno-short-enums"]
    for name in ("Makefile", "tools.mk"):
        text = open(os.path.join(GAME_DIR, name)).read()
        includes = [l for l in text.splitlines() if l.startswith("include ") and l.endswith("../arcade/mk/arcade.mk")]
        assert len(includes) == 1 and "-fwrapv" not in text, name
    cmds = sh("make", "-f", "tools.mk", "-n", "-B", "out/librules.so", "out/arcade_replay")
    gcc = [line for line in cmds.splitlines() if line.startswith("gcc")]
    assert len(gcc) == 2 and all(all(f in line.split() for f in flags) for line in gcc)

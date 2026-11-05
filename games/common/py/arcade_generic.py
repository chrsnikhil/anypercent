"""The arcade contract, shared by every game stamped from games/template. A game's tests/test_generic.py is one line:

    from arcade_generic import *  # noqa: F401,F403

(its conftest puts games/common/py on sys.path), so a fix here reaches every game. Never copy these tests into a
game; change the game's conftest fixtures instead.

Checked: the ROM steps the rules once a frame with the PC library's hash; it records the run from boot and saves it
when game_ended() rises; it resets when the player leaves the results; the RUN section keeps the cartridge's best
run (absent, truncated or unfinished RUNs are replaced; a finished RUN only by a finished faster run; a RUN from
other rules, and its BEST, by any run); BEST follows the best finished time; the launcher's ghost is drawn exactly where its samples say, aligned on play start (flags
bit 0x80), and another game's ghost is ignored; the sprite-tile budget holds; the ROM's determinism flags are the
kit's.

Fixtures (conftest.py): rom, elf, lib, replay_tool, game_id, route_frames, route_finished, short_run, leave_results."""
import os
import re
import struct

import pytest

import arcade_test as T
from arcade_test import S

SETTLE = [0] * 60                      # a saved run reaches SRAM within ~35 frames (arcade_runtime.cpp)
SPRITE_TILES, TEXT_MARGIN = 1024, 128  # SHIP IT!'s rule: keep 4 KB of sprite tiles spare
TITLE_IDLE = 45                        # extra title frames for the ghost alignment test
PLAY = 0x80                            # game_ghost() flags bit: in play (arcade_runtime.h)
WATCH = ("g_dbg_steps", "g_dbg_run_written", "g_dbg_phase", "g_dbg_ghost", "g_dbg_best")
STEPS, WRITTEN, PHASE, GHOST, BEST = range(5)


# ---- helpers -----------------------------------------------------------------------------------------------------

def session(rom, frames, save_in=None, watch=WATCH):
    """(watched rows, save after the last frame) for one emulator session (a blank cartridge by default)."""
    got = T.run_rom(rom, frames, watch=watch, save_in=T.blank_save() if save_in is None else save_in, save_out=True)
    assert got["save"] is not None, "the game never wrote save memory"
    return got["watch"], bytearray(got["save"])


def saved_run(save, game_id):
    got = S.get(save, game_id, S.RUN)
    assert got is not None, "no valid RUN section"
    return got


def assert_replays(replay_tool, log, game_id, want_keys, finished, seed=0):
    head = S.parse_log_header(log)
    keys = T.decode_log(log)
    assert head["game"] == game_id and head["seed"] == seed
    assert keys == want_keys, "the log is not the frames the rules stepped from boot"
    assert head["frames"] == len(keys)
    res = T.replay(replay_tool, log)
    assert res["hash_matches"] and res["complete"], res
    assert res["finished"] == finished, res
    assert res["trophies"] == head["trophies"]
    return res


def end_row(rows):
    """The index of the frame whose step ended the run (the first frame the ROM is saving)."""
    return next(i for i, r in enumerate(rows) if r[PHASE] != 0)


def best_bytes(frames, final_hash, score=0, trophies=0):
    return struct.pack("<4I16x", frames, score, trophies, final_hash)


def with_best_time(save, game_id, frames):
    """The save with its BEST time replaced (its final hash kept, so a RUN that matched it still counts as finished
    with that time)."""
    b = S.parse_best(S.get(save, game_id, S.BEST)[0])
    out = bytearray(save)
    assert S.put(out, S.BEST, best_bytes(frames, b["final_hash"], b["score"], b["trophies"]))
    return bytes(out)


def need_finished_route(route_finished):
    if not route_finished:
        pytest.skip("the route does not finish: the best-run rules need a finished run")


def recorded_ghost(rom, replay_tool, game_id, route_frames):
    """(ghost payload, parsed ghost) extracted by the replayer from the route's saved log, as the launcher does."""
    _, save = session(rom, route_frames + SETTLE)
    log, _ = saved_run(save, game_id)
    ghost = T.ghost_of(replay_tool, log)
    return ghost, S.parse_ghost(ghost)


def ghost_rows(rom, lib, game_id, ghost, frames):
    """Runs frames with the ghost in the save. Returns (rows of (steps, phase, shown, (x, y)), live step): live is the
    first step (from boot) whose game_ghost() has the PLAY bit, from the PC rules (None if never)."""
    rows = T.run_rom(rom, frames, watch=("g_dbg_steps", "g_dbg_phase", "g_dbg_ghost", "g_dbg_ghost_xy"),
                     save_in=T.save_with(game_id, ghost=ghost))["watch"]
    boot = T.boots([r[0] for r in rows])[0]
    flags = [g[3] for g in T.pc_ghosts(lib, frames[boot:])]
    live = next((i + 1 for i, f in enumerate(flags) if f & PLAY), None)
    out = []
    for steps, phase, on, xy in rows:
        out.append((steps, phase, on, struct.unpack("<hh", struct.pack("<HH", xy >> 16, xy & 0xFFFF))))
    return out, live


def assert_ghost_exact(rows, live, parsed):
    """Every shown ghost is exactly T.ghost_expected at the ghost step its anchors give; returns {play-relative step
    (or boot step when unaligned): (x, y)} and the number of run frames it could have been shown on."""
    period, points = parsed["period"], parsed["points"]
    anchor = T.ghost_anchor(points, period)
    shown, run_frames = {}, 0
    for steps, phase, on, xy in rows:
        if steps == 0 or phase != 0:
            continue
        g = T.ghost_step(steps, live, anchor)
        if g is not None:
            run_frames += 1
        if not on:
            continue
        assert g is not None, "step %d: the ghost is drawn before play started (live step %s)" % (steps, live)
        want = T.ghost_expected(points, period, g)
        assert xy == want, "step %d (ghost step %d): ghost %s, samples say %s" % (steps, g, xy, want)
        shown[steps - live if anchor else steps] = xy
    return shown, run_frames


# ---- the contract ------------------------------------------------------------------------------------------------

def test_rom_matches_pc_every_frame(rom, elf, lib, route_frames, leave_results):
    frames = route_frames + SETTLE + [leave_results] + [0] * 90 + route_frames[:300]
    assert T.assert_rom_matches_pc(rom, elf, lib, frames) > len(route_frames) // 2


def test_the_run_is_saved_and_replays(rom, lib, replay_tool, game_id, route_frames, route_finished, leave_results):
    frames = route_frames + SETTLE + [leave_results] + SETTLE
    rows, save = session(rom, frames)
    starts = T.boots([r[STEPS] for r in rows])
    assert len(starts) == 2, "leaving the results did not reset the ROM (boots at %s)" % starts
    assert max(r[WRITTEN] for r in rows[:starts[1]]) == 1, "the run was not written exactly once"
    assert all(r[GHOST] == 0 for r in rows), "a ghost was drawn from a blank cartridge"
    assert rows[end_row(rows)][BEST] == (1 if route_finished else 0), "g_dbg_best on a blank cartridge"
    log, flags = saved_run(save, game_id)
    assert flags == 0, "truncated"
    res = assert_replays(replay_tool, log, game_id, T.pc_run_end(lib, frames[starts[0]:]), route_finished)
    best = S.get(save, game_id, S.BEST)
    if route_finished:
        assert best is not None, "a finished run on a blank cartridge must set the best"
        b = S.parse_best(best[0])
        assert b["frames"] == res["time_frames"] and b["final_hash"] == S.parse_log_header(log)["final_hash"]
    else:
        assert best is None
    assert save[:0x100] == b"\xff" * 0x100, "the legacy area 0..0xFF was written"


def test_template_short_run_replays(rom, lib, replay_tool, game_id, short_run):
    frames = short_run + SETTLE
    rows, save = session(rom, frames)
    start = T.boots([r[STEPS] for r in rows])[0]
    want = T.pc_run_end(lib, frames[start:])
    assert len(want) <= len(short_run), "the short run did not end within its frames"
    log, flags = saved_run(save, game_id)
    assert flags == 0
    assert_replays(replay_tool, log, game_id, want, T.pc_result(lib, want)["finished"])


def test_leaving_results_mid_flush_keeps_the_run(rom, lib, replay_tool, game_id, route_frames, route_finished,
                                                 leave_results):
    rows, _ = session(rom, route_frames + SETTLE)
    end = end_row(rows)
    frames = (route_frames + SETTLE)[:end + 1] + [leave_results] * 60 + SETTLE    # pressed as the results appear, held
    rows, save = session(rom, frames)
    assert rows[end][PHASE] == 1, "the save was not in progress when the results were left"
    starts = T.boots([r[STEPS] for r in rows])
    assert len(starts) == 2, "leaving the results did not reset the ROM"
    log, flags = saved_run(save, game_id)
    assert flags == 0
    assert_replays(replay_tool, log, game_id, T.pc_run_end(lib, frames[starts[0]:]), route_finished)


def test_a_second_run_after_reset_is_saved(rom, lib, replay_tool, game_id, route_frames, route_finished, short_run,
                                           leave_results):
    # An unfinished (short) first run, then the route after the reset: the second run replaces the first.
    if T.pc_result(lib, T.pc_run_end(lib, short_run))["finished"]:
        pytest.skip("this game's short run finishes")
    frames = short_run + SETTLE + [leave_results] + [0] * 120 + route_frames + SETTLE
    rows, save = session(rom, frames)
    starts = T.boots([r[STEPS] for r in rows])
    assert len(starts) == 2, "expected one reset (boots at %s)" % starts
    assert rows[-1][WRITTEN] == 1, "the second run was not written once after the reset"
    log, flags = saved_run(save, game_id)
    assert flags == 0
    assert_replays(replay_tool, log, game_id, T.pc_run_end(lib, frames[starts[1]:]), route_finished)


def test_an_equal_or_slower_second_run_keeps_the_stored_run(rom, lib, replay_tool, game_id, route_frames,
                                                            route_finished, leave_results):
    # The route twice in one session (the second after a longer wait on the title: another log, the same time):
    # a tie (or a slower run, if the game's time counts the title) keeps the stored run.
    need_finished_route(route_finished)
    frames = route_frames + SETTLE + [leave_results] + [0] * 120 + route_frames + SETTLE
    rows, save = session(rom, frames)
    starts = T.boots([r[STEPS] for r in rows])
    assert len(starts) == 2
    first, second = T.pc_run_end(lib, frames[starts[0]:]), T.pc_run_end(lib, frames[starts[1]:])
    assert first != second, "both runs have the same frames from boot: the test cannot tell them apart"
    assert T.pc_result(lib, second)["time_frames"] >= T.pc_result(lib, first)["time_frames"]
    assert rows[-1][WRITTEN] == 0, "the tying second run was written"
    assert rows[-1][BEST] == 0b10
    log, _ = saved_run(save, game_id)
    assert_replays(replay_tool, log, game_id, first, True)


def test_a_faster_run_replaces_the_stored_run(rom, lib, replay_tool, game_id, route_frames, route_finished):
    need_finished_route(route_finished)
    _, save = session(rom, route_frames + SETTLE)
    slow = with_best_time(save, game_id, 0xFFFFFF00)          # the stored run now counts as a very slow finish
    frames = [0] * 30 + route_frames + SETTLE
    rows, after = session(rom, frames, slow)
    run = T.pc_run_end(lib, frames[T.boots([r[STEPS] for r in rows])[0]:])
    assert rows[-1][BEST] == 0b11 and rows[-1][WRITTEN] == 1
    log, _ = saved_run(after, game_id)
    res = assert_replays(replay_tool, log, game_id, run, True)
    b = S.parse_best(S.get(after, game_id, S.BEST)[0])
    assert b["frames"] == res["time_frames"] and b["final_hash"] == res["final_hash"]


def test_a_slower_run_keeps_the_stored_run(rom, game_id, route_frames, route_finished):
    need_finished_route(route_finished)
    _, save = session(rom, route_frames + SETTLE)
    fast = with_best_time(save, game_id, 1)                   # the stored run now counts as a 1-frame finish
    rows, after = session(rom, [0] * 30 + route_frames + SETTLE, fast)
    assert rows[-1][BEST] == 0b10 and rows[-1][WRITTEN] == 0
    assert S.get(after, game_id, S.RUN) == S.get(fast, game_id, S.RUN), "a slower run replaced the stored run"
    assert S.get(after, game_id, S.BEST) == S.get(fast, game_id, S.BEST), "a slower run replaced the best"


def test_a_run_from_older_rules_gives_way_to_the_next_run(rom, lib, replay_tool, game_id, route_frames,
                                                          route_finished):
    # A stored run and its best recorded by an older ROM (another rules version): the replay tools open only logs of
    # their own rules, so it can no longer be verified or give a ghost. It must not keep this ROM's runs out, however
    # fast it was: the next finished run is saved, and sets the best, whatever its time.
    need_finished_route(route_finished)
    _, save = session(rom, route_frames + SETTLE)
    old = bytearray(with_best_time(save, game_id, 1))         # the stored run now counts as a 1-frame finish ...
    log, flags = saved_run(old, game_id)
    rules = S.parse_log_header(log)["rules_version"]
    log = bytearray(log)
    struct.pack_into("<I", log, 8, rules - 1)                 # ... under the previous rules
    assert S.put(old, S.RUN, bytes(log), flags)
    frames = [0] * 30 + route_frames + SETTLE
    rows, after = session(rom, frames, bytes(old))
    run = T.pc_run_end(lib, frames[T.boots([r[STEPS] for r in rows])[0]:])
    assert rows[-1][WRITTEN] == 1, "the run under these rules was kept out by the older rules' run"
    assert rows[-1][BEST] == 0b01, "g_dbg_best: the older rules' best still counted at boot"
    log, _ = saved_run(after, game_id)
    assert S.parse_log_header(log)["rules_version"] == rules
    res = assert_replays(replay_tool, log, game_id, run, True)
    b = S.parse_best(S.get(after, game_id, S.BEST)[0])
    assert b["frames"] == res["time_frames"] and b["final_hash"] == res["final_hash"]


def test_a_faster_stored_best_is_kept(rom, game_id, route_frames, route_finished):
    need_finished_route(route_finished)
    seeded = T.save_with(game_id, best=best_bytes(1, 1234))
    rows, save = session(rom, route_frames + SETTLE, seeded)
    assert rows[end_row(rows)][BEST] == 0b10, "g_dbg_best: had a best, not new"
    assert S.get(save, game_id, S.BEST)[0] == best_bytes(1, 1234)
    assert S.get(save, game_id, S.RUN) is not None, "no stored run: the new run must still be saved"


def test_a_slower_stored_best_is_replaced(rom, lib, game_id, route_frames, route_finished):
    need_finished_route(route_finished)
    seeded = T.save_with(game_id, best=best_bytes(0xFFFFFFF0, 1234))
    rows, save = session(rom, route_frames + SETTLE, seeded)
    assert rows[end_row(rows)][BEST] == 0b11, "g_dbg_best: had a best, new"
    run = T.pc_run_end(lib, route_frames[T.boots([r[STEPS] for r in rows])[0]:])
    assert S.parse_best(S.get(save, game_id, S.BEST)[0])["frames"] == T.pc_result(lib, run)["time_frames"]


def test_ghost_is_drawn_from_save(rom, lib, replay_tool, game_id, route_frames):
    ghost, parsed = recorded_ghost(rom, replay_tool, game_id, route_frames)
    rows, live = ghost_rows(rom, lib, game_id, ghost, route_frames + SETTLE)
    shown, run_frames = assert_ghost_exact(rows, live, parsed)
    assert len(shown) > run_frames // 2, "the ghost was drawn on %d of %d frames of the run" % (len(shown), run_frames)


def test_the_ghost_is_aligned_on_play_start(rom, lib, replay_tool, game_id, route_frames):
    ghost, parsed = recorded_ghost(rom, replay_tool, game_id, route_frames)
    assert T.ghost_anchor(parsed["points"], parsed["period"]), \
        "game_ghost() never sets flags 0x80: set flags |= 0x80 while in play (games/README.md)"
    rows, live = ghost_rows(rom, lib, game_id, ghost, route_frames + SETTLE)
    base, _ = assert_ghost_exact(rows, live, parsed)
    rows, live = ghost_rows(rom, lib, game_id, ghost, [0] * TITLE_IDLE + route_frames + SETTLE)
    late, _ = assert_ghost_exact(rows, live, parsed)
    common = set(base) & set(late)
    assert len(common) > len(base) // 2, "the late start showed the ghost on too few of the same play steps"
    assert all(base[d] == late[d] for d in common), "the ghost moved with the time spent on the title"


def test_foreign_ghost_is_ignored(rom, lib, game_id, route_frames):
    other = b"XXXX" if game_id != b"XXXX" else b"YYYY"
    start = T.pc_player(lib, route_frames[:1])[0]
    pts = [(start[0], start[1], 0, PLAY)] * 400
    watch = ("g_dbg_steps", "g_dbg_ghost")
    ours = T.run_rom(rom, route_frames, watch=watch, save_in=T.save_with(game_id, ghost=S.ghost_bytes(
        game_id, 0, 4, pts)))["watch"]
    assert any(on for _, on in ours), "control: the game's own ghost track was never drawn"
    theirs = T.run_rom(rom, route_frames, watch=watch, save_in=T.save_with(game_id, ghost=S.ghost_bytes(
        other, 0, 4, pts)))["watch"]
    assert all(on == 0 for _, on in theirs), "a ghost track from game %r was drawn" % other


def test_sprite_budget(rom, lib, game_id, route_frames, leave_results):
    frames = route_frames + SETTLE + [leave_results] + [0] * 90
    start = T.pc_player(lib, route_frames[:1])[0]
    ghost = S.ghost_bytes(game_id, 0, 8, [(start[0] + (k % 64), start[1], k % 8, PLAY) for k in range(2000)])
    rows = T.run_rom(rom, frames, watch=("g_dbg_sprite_tiles", "g_dbg_ghost"),
                     save_in=T.save_with(game_id, ghost=ghost))["watch"]
    assert any(on for _, on in rows), "the ghost was never drawn: the budget would not include it"
    peak = max(t for t, _ in rows)
    assert peak <= SPRITE_TILES - TEXT_MARGIN, "peak %d sprite tiles" % peak


SEED_NONCE = 0x5EED1234


def seeded_save(game_id, boots=0):
    """A cartridge whose profile carries a seed nonce, as the launcher writes it before a launch."""
    prof = bytearray(S.profile_bytes("SEED", b"\0" * 8, 0, seed_nonce=SEED_NONCE))
    struct.pack_into("<I", prof, 28, boots)
    return T.save_with(game_id, profile=bytes(prof))


def test_a_blank_cartridge_plays_the_classic_seed_0(rom, game_id, short_run):
    rows = T.run_rom(rom, short_run, watch=("g_dbg_steps", "g_dbg_seed"), save_in=T.blank_save())["watch"]
    assert all(r[1] == 0 for r in rows if r[0]), "a blank cartridge must keep the classic seed 0"


def test_a_seeded_profile_gives_every_boot_its_own_seed(rom, lib, replay_tool, game_id, short_run, leave_results):
    frames = short_run + SETTLE + [leave_results] + SETTLE
    got = T.run_rom(rom, frames, watch=("g_dbg_steps", "g_dbg_seed"), save_in=seeded_save(game_id), save_out=True)
    rows, save = got["watch"], bytearray(got["save"])
    starts = T.boots([r[0] for r in rows])
    assert len(starts) == 2, "leaving the results did not reset the ROM (boots at %s)" % starts
    so = T.load_lib(lib)
    first, second = rows[starts[0]][1], rows[starts[1]][1]
    assert first == so.ac_seed_mix(SEED_NONCE, 1) and second == so.ac_seed_mix(SEED_NONCE, 2)
    assert first and second and first != second, "each boot must get its own non-zero seed"
    prof, _ = S.get(save, game_id, S.PROFILE)
    assert S.parse_profile_seed(prof) == (SEED_NONCE, 2), "the boot count was not written back each boot"
    assert prof[:24] == S.profile_bytes("SEED", b"\0" * 8, 0)[:24], "the boot write changed name, tag or trophies"
    log, _ = saved_run(save, game_id)
    want = T.pc_run_end(lib, frames[starts[0]:], seed=first)
    assert_replays(replay_tool, log, game_id, want, T.pc_result(lib, want, seed=first)["finished"], seed=first)
    assert save[:0x100] == b"\xff" * 0x100, "the legacy area 0..0xFF was written"


def test_rom_matches_pc_under_a_seed(rom, elf, lib, game_id, route_frames, short_run, leave_results):
    frames = route_frames[:1200] + short_run + SETTLE + [leave_results] + [0] * 90 + route_frames[:300]
    assert T.assert_rom_matches_pc(rom, elf, lib, frames, save_in=seeded_save(game_id, boots=41)) > 600


SEED_TRIALS = 100            # seeds tried by the recording test
SEED_SURVIVAL_MAX = 0.10     # the share of seeds a classic recording may still reproduce its result on


def test_a_recording_does_not_survive_other_seeds(lib, route_frames):
    """The anti-precomputation property: the route recorded for seed 0, replayed under other seeds, must not
    reproduce its result (finished, time, score, trophies) except on a small share of them. The same seed must
    replay the same game."""
    so = T.load_lib(lib)
    seeds = [so.ac_seed_mix(SEED_NONCE, b) for b in range(1, SEED_TRIALS + 1)]
    assert T.pc_hashes(lib, route_frames[:600], seed=seeds[0]) == T.pc_hashes(lib, route_frames[:600], seed=seeds[0])
    classic = T.pc_result(lib, route_frames)
    survived = sum(1 for sd in seeds if T.pc_result(lib, route_frames, seed=sd) == classic)
    print("recording survives %d of %d seeds" % (survived, SEED_TRIALS))
    assert survived <= SEED_SURVIVAL_MAX * SEED_TRIALS, \
        "the recording reproduces its result on %d of %d seeds: the seed barely changes play" % (survived, SEED_TRIALS)


def test_the_rom_uses_the_kits_determinism_flags(rom):
    """The Makefile's USERFLAGS are arcade/mk/arcade.mk's ARCADE_FLAGS (included, or the same flags spelled out)."""
    game_dir = os.path.dirname(os.path.abspath(rom))
    with open(os.path.join(T.REPO, "arcade", "mk", "arcade.mk")) as f:
        kit = set(re.search(r"^ARCADE_FLAGS\s*:=\s*(.*)$", f.read(), re.M).group(1).split())
    with open(os.path.join(game_dir, "Makefile")) as f:
        make = f.read()
    flags = re.search(r"^USERFLAGS\s*:=\s*(.*)$", make, re.M).group(1).split()
    if "$(ARCADE_FLAGS)" in flags:
        assert re.search(r"^include .*arcade/mk/arcade\.mk", make, re.M), "USERFLAGS uses $(ARCADE_FLAGS) unincluded"
    else:
        assert kit <= set(flags), "USERFLAGS %s lack the kit's %s" % (flags, sorted(kit))

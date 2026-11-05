"""ZIP's core rules (Task 3) on small test levels through out/librules.so: momentum on slopes, the slip, rolling,
jumps along the surface normal, springs, boosters, the loop, packets and hits, bugs, trophies."""
import pytest

from conftest import tuning
from zipsim import A, DOWN, LEFT, RIGHT, MODE_AIR, MODE_GROUND, MODE_LOOP, Sim, flat

T = tuning
BODY_H = T("BODY_H")


def hill(kind="45", width=48, height=16, floor=12, up_at=10, rise=6, plateau=6, down=True):
    """Flat floor, a rise of `rise` tiles (45: one tile per step; 22: two tiles per step), a plateau, then (down) the
    mirror fall and flat floor again. P at column 2."""
    rows = [["."] * width for _ in range(height)]
    top = [floor] * width                      # surface row per column: tiles at rows >= top are solid
    c, r = up_at, floor
    glyph = {}
    for _ in range(rise):
        if kind == "45":
            r -= 1
            glyph[(c, r)] = "/"
            top[c] = r + 1
            c += 1
        else:
            r -= 1
            glyph[(c, r)] = "a"
            glyph[(c + 1, r)] = "b"
            top[c] = top[c + 1] = r + 1
            c += 2
    for k in range(c, min(width, c + plateau)):
        top[k] = r
    c = min(width, c + plateau)
    if down:
        for _ in range(rise):
            if c >= width:
                break
            if kind == "45":
                glyph[(c, r)] = "\\"
                top[c] = r + 1
                r += 1
                c += 1
            else:
                glyph[(c, r)] = "c"
                glyph[(c + 1, r)] = "d"
                top[c] = top[c + 1] = r + 1
                r += 1
                c += 2
        for k in range(c, width):
            top[k] = floor
    else:
        for k in range(c, width):
            top[k] = r
    for col in range(width):
        for row in range(top[col], height):
            rows[row][col] = "#"
    for (col, row), g in glyph.items():
        rows[row][col] = g
    rows[floor - 1][2] = "P"
    return ["".join(x) for x in rows]


def surface_y(sim, x):
    for y in range(0, 16 * 64):
        if sim.lib.world_solid(int(x), y):
            return y
    raise AssertionError("no ground at x=%d" % x)


def stand_on(sim, x, gsp=0, angle=0):
    sim.put(x, surface_y(sim, x) - BODY_H, gsp, MODE_GROUND, angle)


def sign(v):
    return (v > 0) - (v < 0)


# ---- flat ground ----------------------------------------------------------------------------------------------------

def test_flat_run_reaches_top_speed_and_friction_stops(lib):
    s = Sim(lib, flat(width=120))
    s.step(RIGHT, 200)
    assert s.w.gsp == T("TOP_SPEED") and s.w.mode == MODE_GROUND
    s.step(0, 200)
    assert s.w.gsp == 0


def test_braking_turns_around(lib):
    s = Sim(lib, flat(width=120))
    s.step(RIGHT, 100)
    g0 = s.w.gsp
    s.step(LEFT)
    assert s.w.gsp == g0 - T("DECEL")


# ---- slopes -------------------------------------------------------------------------------------------------------

def test_slow_on_steep_slope_slides_back(lib):
    """Review focus 1: running up a 45-degree slope slowly slides back down: no sticking, no jitter."""
    s = Sim(lib, hill("45"))
    x0 = 13 * 16 + 8
    stand_on(s, x0, gsp=0x0100, angle=32)
    signs, xs = [], []
    for _ in range(150):
        w = s.step(RIGHT)
        signs.append(sign(w.gsp))
        xs.append(w.x)
        assert w.mode == MODE_GROUND
    flips = sum(1 for a, b in zip(signs, signs[1:]) if a and b and a != b)
    assert flips <= 4, "gsp changed direction %d times (jitter)" % flips
    assert min(xs) < 10 * 16 * 256, "the player did not slide down to the flat (min x=%d)" % (min(xs) // 256)


def test_standing_still_on_45_slips_down(lib):
    s = Sim(lib, hill("45"))
    stand_on(s, 13 * 16 + 8, angle=32)
    s.step(0, 90)
    assert s.px() < 13 * 16 and s.w.mode == MODE_GROUND


def test_standing_on_22_slope_holds(lib):
    s = Sim(lib, hill("22", width=64))
    x0 = 13 * 16 + 8
    stand_on(s, x0, angle=16)
    s.step(0, 60)
    assert abs(s.px() - x0) <= 1


def test_running_down_a_slope_gains_speed_past_top_and_up_loses_it(lib):
    s = Sim(lib, hill("45", width=64, plateau=4))
    down_x = (10 + 6 + 4) * 16 + 8                 # the top of the fall
    stand_on(s, down_x - 16, gsp=T("TOP_SPEED"), angle=0)
    peak = 0
    for _ in range(40):
        w = s.step(RIGHT)
        peak = max(peak, w.gsp)
    assert peak > T("TOP_SPEED") + 0x80, hex(peak)
    s2 = Sim(lib, hill("45", width=64))
    stand_on(s2, 9 * 16, gsp=T("TOP_SPEED"))
    s2.step(RIGHT, 14)
    assert s2.w.angle == 32 and s2.w.gsp < T("TOP_SPEED")


def test_the_player_follows_slopes_and_sets_the_angle(lib):
    s = Sim(lib, hill("45", width=64))
    stand_on(s, 5 * 16, gsp=0x0300)
    angles = set()
    for _ in range(120):
        w = s.step(RIGHT)
        assert w.mode == MODE_GROUND or w.xv != 0
        angles.add(w.angle)
    assert {0, 32, 224} <= angles, angles


# ---- no tunnelling ------------------------------------------------------------------------------------------------

def test_no_tunnelling_at_max_speed(lib):
    """Review focus 3: top speed into a wall never goes through it (ground and air)."""
    rows = flat(width=40, extra={(20, 7): "#", (20, 8): "#", (20, 6): "#", (20, 5): "#", (20, 4): "#"})
    s = Sim(lib, rows)
    stand_on(s, 12 * 16, gsp=T("MAX_SPEED"))
    for _ in range(30):
        w = s.step(RIGHT)
        assert w.x // 256 + T("WALL_W") < 20 * 16 + 1, w.x / 256
    assert s.w.gsp < 0x40
    s = Sim(lib, rows)
    s.put(12 * 16, 7 * 16)
    s.lib.world_test_air(T("MAX_SPEED"), 0)
    for _ in range(30):
        w = s.step(RIGHT)
        assert w.x // 256 + T("WALL_W") < 20 * 16 + 1
    s = Sim(lib, flat(width=40, floor=9))
    s.put(10 * 16, 2 * 16)
    s.lib.world_test_air(0, T("MAX_FALL"))
    for _ in range(40):
        w = s.step()
        assert w.y // 256 + BODY_H <= 9 * 16
    assert s.w.mode == MODE_GROUND


# ---- rolling ------------------------------------------------------------------------------------------------------

def test_roll_physics(lib):
    """Review focus 5: Down at speed rolls; rolling up a slope slows by the roll slope factor (plus roll friction)."""
    s = Sim(lib, hill("45", width=64))
    stand_on(s, 5 * 16, gsp=0x0080)
    s.step(DOWN)
    assert not s.w.rolling, "rolled below ROLL_MIN"
    stand_on(s, 5 * 16, gsp=0x0500)
    s.step(DOWN)
    assert s.w.rolling
    stand_on(s, 13 * 16 + 8, gsp=0x0500, angle=32)
    s.lib.world_test_set(s.w.x, s.w.y, 0x0500, MODE_GROUND, 32)
    before = s.w.gsp
    s.step(DOWN)
    assert s.w.rolling
    sin45 = 11585
    want = before - ((T("SLOPE_ROLL_UP") * sin45) >> 14) - T("ROLL_FRICTION")
    assert s.w.gsp == want, (hex(s.w.gsp), hex(want))


def test_rolling_down_is_faster_than_running_down(lib):
    def run(keys):
        s = Sim(lib, hill("45", width=64, plateau=4))
        stand_on(s, (10 + 6 + 4) * 16 - 8, gsp=T("TOP_SPEED"))
        s.step(keys)
        s.step(keys, 7)
        return s.w.gsp
    assert run(DOWN) > run(RIGHT) + 0x60


def test_a_slow_roll_stands_up(lib):
    s = Sim(lib, flat(width=120))
    stand_on(s, 5 * 16, gsp=0x0200)
    s.step(DOWN)
    assert s.w.rolling
    s.step(0, 150)
    assert not s.w.rolling and s.w.gsp == 0


# ---- jumping ------------------------------------------------------------------------------------------------------

def jump_apex(s, keys_held):
    y0 = s.w.y
    s.step(A)
    top = y0
    for _ in range(200):
        w = s.step(keys_held)
        top = min(top, w.y)
        if w.mode == MODE_GROUND:
            break
    return (y0 - top) / 256.0


def test_jump_heights_hold_and_tap(lib):
    s = Sim(lib, flat(width=60, height=20, floor=16))
    s.step(0, 5)
    full = jump_apex(s, A)
    tap = jump_apex(s, 0)
    v, g = T("JUMP_SPEED") / 256.0, T("GRAVITY") / 256.0
    assert abs(full - v * v / (2 * g)) < 8, full
    assert tap < full * 0.6, (tap, full)


def test_jump_off_a_slope_uses_the_surface_normal(lib):
    s = Sim(lib, hill("45"))
    stand_on(s, 13 * 16 + 8, angle=32)
    s.step(A)
    w = s.w
    assert w.mode == MODE_AIR
    j = T("JUMP_SPEED")
    assert w.xv < -j // 2, "the jump leans back, away from the rising slope"
    assert w.yv < -j // 2


# ---- springs and boosters ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("glyph,speed", [("S", "SPRING_YELLOW"), ("R", "SPRING_RED")])
def test_spring_heights(lib, glyph, speed):
    s = Sim(lib, flat(width=40, height=48, floor=44, extra={(8, 43): glyph}))
    s.step(RIGHT, 1)
    y0 = s.w.y
    fired = False
    top = y0
    for _ in range(300):
        w = s.step(RIGHT if not fired else 0)
        if w.mode == MODE_AIR and w.yv < 0:
            fired = True
        top = min(top, w.y)
        if fired and w.mode == MODE_GROUND:
            break
    assert fired
    v, g = T(speed) / 256.0, T("GRAVITY") / 256.0
    rise = (y0 - top) / 256.0
    assert abs(rise - (v * v / (2 * g) + 10)) < 16, (rise, v * v / (2 * g))


def test_booster_sets_ground_speed(lib):
    s = Sim(lib, flat(width=60, extra={(8, 8): ">"}))
    for _ in range(200):
        w = s.step(RIGHT)
        if w.gsp == T("BOOST_SPEED"):
            break
    assert s.w.gsp == T("BOOST_SPEED")
    s.step(RIGHT)
    assert s.w.gsp > T("TOP_SPEED")


# ---- the loop -----------------------------------------------------------------------------------------------------

def loop_level():
    return flat(width=80, height=24, floor=20, extra={(30, 19): "L"})


def run_into_loop(lib, gsp, frames=240):
    s = Sim(lib, loop_level())
    stand_on(s, 26 * 16, gsp=gsp)
    track = []
    for _ in range(frames):
        w = s.step(RIGHT if gsp >= 0x0600 else 0)
        track.append((w.x, w.y, w.mode, w.gsp))
    return s, track


def test_fast_loop_entry_goes_round(lib):
    s, track = run_into_loop(lib, 0x0800)
    modes = [m for _, _, m, _ in track]
    assert MODE_LOOP in modes
    first = modes.index(MODE_LOOP)
    last = len(modes) - 1 - modes[::-1].index(MODE_LOOP)
    assert all(m == MODE_LOOP for m in modes[first:last + 1])
    ys = [y for _, y, m, _ in track if m == MODE_LOOP]
    assert (min(ys) >> 8) < (20 * 16 - BODY_H) - 90, "never reached the top"
    assert track[-1][2] == MODE_GROUND and track[-1][0] > (30 * 16 + 60) * 256
    assert s.w.fell_off_loop == 0 and not s.w.loop_full
    for (x0, y0, _, _), (x1, y1, _, _) in zip(track, track[1:]):
        assert abs(x1 - x0) < 20 * 256 and abs(y1 - y0) < 20 * 256, "teleport"


def test_full_speed_loop_latches_the_trophy_flag(lib):
    s, _ = run_into_loop(lib, T("LOOP_FULL_SPEED"))
    assert s.w.loop_full


def test_slow_loop_entry_falls_back(lib):
    """Review focus 2: below the threshold the player falls off at the quarter point, cleanly."""
    s, track = run_into_loop(lib, 0x0500, 300)
    modes = [m for _, _, m, _ in track]
    assert MODE_LOOP in modes, "the slow player never ran up the loop"
    assert s.w.fell_off_loop == 1
    assert modes.count(MODE_LOOP) < 40, "stuck in the loop"
    assert track[-1][2] == MODE_GROUND
    lx = 30 * 16 + 8
    assert track[-1][0] < lx * 256, "fell back before the loop entry"
    for (x0, y0, _, _), (x1, y1, _, _) in zip(track, track[1:]):
        assert abs(x1 - x0) < 20 * 256 and abs(y1 - y0) < 20 * 256, "teleport"
    assert not s.w.loop_full


# ---- packets and hits ---------------------------------------------------------------------------------------------

def test_packets_are_collected_once(lib):
    s = Sim(lib, flat(width=60, extra={(6, 8): "o", (7, 8): "o", (8, 8): "o"}))
    s.step(RIGHT, 80)
    assert s.w.packets == 3
    s.step(LEFT, 80)
    assert s.w.packets == 3


def test_packet_scatter_rules(lib):
    """Review focus 4: a hit scatters (up to 32); they are recollectable only after 64 frames and gone after 240;
    a hit with none respawns at the checkpoint."""
    s = Sim(lib, flat(width=80, height=14, floor=11, extra={(12, 10): "C", (20, 10): "x"}))
    s.lib.world_test_packets(40)
    s.step(RIGHT, 1)
    for _ in range(300):
        w = s.step(RIGHT)
        if w.hits:
            break
    assert s.w.hits == 1 and s.w.packets == 0 and s.w.hurt and s.w.invuln
    assert s.lib.world_test_scatter_count() == 32
    # park a scattered packet on the player: not before 64 frames
    s.step(0, 1)
    age = s.lib.world_test_scatter_age(0)
    assert 0 < age <= tuning("SCATTER_WAIT")
    for _ in range(200):
        if not s.w.hurt:
            break
        s.step(0)
    s.lib.world_test_scatter_place(0, s.w.x, s.w.y, 10)
    s.step(0)
    assert s.w.packets == 0
    s.lib.world_test_scatter_place(0, s.w.x, s.w.y, tuning("SCATTER_WAIT") + 1)
    s.step(0)
    assert s.w.packets == 1
    s.step(0, tuning("SCATTER_LIFE"))
    assert s.lib.world_test_scatter_count() == 0
    # a hit with no packets: back to the checkpoint (lit on the way)
    s.lib.world_test_packets(0)
    s.step(0, tuning("INVULN_FRAMES") + 1)
    stand_on(s, 20 * 16 - 20, gsp=0x0200)
    for _ in range(30):
        if s.step(RIGHT).respawns:
            break
    assert s.w.respawns == 1 and s.w.hits == 2
    assert s.w.x // 256 == 12 * 16 + 8 and s.w.mode == MODE_GROUND and s.w.packets == 0


def test_scatter_is_deterministic_and_fanned(lib):
    def fan():
        s = Sim(lib, flat(width=80, height=14, floor=11, extra={(20, 10): "x"}))
        s.lib.world_test_packets(8)
        s.step(RIGHT, 150)
        return [(s.lib.world_test_scatter_x(i), s.lib.world_test_scatter_y(i)) for i in range(8)]
    a, b = fan(), fan()
    assert a == b
    xs = sorted(x for x, _ in a)
    assert xs[0] < xs[-1] - 32 * 256


def test_a_pit_respawns(lib):
    rows = flat(width=40, height=12, floor=9)
    rows = [r[:15] + "." * 4 + r[19:] for r in rows]
    s = Sim(lib, rows)
    s.step(RIGHT, 200)
    assert s.w.respawns >= 1


# ---- bugs ---------------------------------------------------------------------------------------------------------

def test_rolling_squashes_a_bug_and_walking_into_one_hurts(lib):
    s = Sim(lib, flat(width=80, extra={(20, 8): "e"}))
    stand_on(s, 10 * 16, gsp=0x0400)
    s.step(DOWN)
    s.step(0, 60)
    assert s.w.hits == 0 and s.lib.world_ent_state(0) == 1
    s = Sim(lib, flat(width=80, extra={(20, 8): "e"}))
    s.lib.world_test_packets(5)
    s.step(RIGHT, 120)
    assert s.w.hits == 1


# ---- trophies ------------------------------------------------------------------------------------------------------

def test_trophies_latch(lib):
    s = Sim(lib, flat(width=60, extra={(30, 8): "F", (20, 8): "x"}))
    s.lib.world_test_packets(100)
    s.step(0)
    assert s.lib.rules_trophies() & 4
    s.step(RIGHT, 150)
    assert s.w.hits == 1 and s.lib.rules_trophies() & 4, "100 packets stays after losing them"
    s.step(RIGHT, 300)
    assert s.lib.rules_finished()
    assert s.lib.rules_trophies() & 1 and not s.lib.rules_trophies() & 2


def test_a_clean_fast_finish_gets_under_and_no_loss(lib):
    s = Sim(lib, flat(width=60, extra={(30, 8): "F"}))
    s.step(RIGHT, 200)
    assert s.lib.rules_finished() and s.lib.rules_trophies() & 3 == 3
    s.step(0, tuning("GOAL_FRAMES"))
    assert s.lib.game_ended()


def test_same_inputs_same_hashes(lib):
    import arcade_test as T2
    lib.zip_level_reset()
    keys = [0] * 5 + [8, 0, 8] + [RIGHT] * 200 + [RIGHT | A] * 20 + [RIGHT | DOWN] * 50
    assert T2.pc_hashes(lib, keys) == T2.pc_hashes(lib, keys)


def test_the_score_is_the_packets_held_at_the_finish(lib):
    import arcade_test as T2
    s = Sim(lib, flat(width=80, extra={(10, 8): "o", (20, 8): "F", (22, 8): "o", (23, 8): "o"}))
    s.step(RIGHT, 150)
    s.step(0, tuning("GOAL_FRAMES"))
    assert s.lib.game_ended()
    r = T2.Result()
    s.lib.game_result(T2.ctypes.byref(r))
    assert r.finished and r.score == 1, (r.finished, r.score)


@pytest.mark.parametrize("age,taken", [(63, False), (64, True)])
def test_scatter_pickup_edge(lib, age, taken):
    """A packet scattered `age` frames ago: the step that makes it SCATTER_WAIT + 1 frames old may collect it."""
    assert tuning("SCATTER_WAIT") == 64
    s = Sim(lib, flat(width=40))
    s.step(0, 5)
    s.lib.world_test_scatter_place(0, s.w.x, s.w.y, age)
    s.step(0)
    assert (s.w.packets == 1) == taken


@pytest.mark.parametrize("age,alive", [(239, True), (240, False)])
def test_scatter_lifetime_edge(lib, age, alive):
    assert tuning("SCATTER_LIFE") == 240
    s = Sim(lib, flat(width=40))
    s.step(0, 5)
    s.lib.world_test_scatter_place(0, (s.w.x + 64 * 256), s.w.y - 40 * 256, age)
    s.step(0)
    assert (s.lib.world_test_scatter_count() == 1) == alive

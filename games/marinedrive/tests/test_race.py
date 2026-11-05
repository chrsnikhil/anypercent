"""MARINE DRIVE GP's race rules (plan Task 3) through out/librules.so: surfaces and top speeds, walls, reversing,
drifting and boosts, checkpoints and laps, kart contacts, placement, and every trophy latching. The rules_debug_*
calls exist only for these tests (the ROM never calls them)."""
import math
import os
import sys

import pytest

from conftest import (A, B, GAME_DIR, LEFT, R, RIGHT, SC_FINISH, SC_RACE, SC_RESULTS, centre_points, to_race,
                      tuning)

sys.path.insert(0, os.path.join(GAME_DIR, "tools", "art"))
import track_data as D  # noqa: E402

ONE = 65536
SURF_ROAD, SURF_CURB, SURF_SLOW, SURF_WALL, SURF_BOOST = range(5)
NORTH, EAST, WEST = 768, 0, 512


@pytest.fixture
def race(g):
    to_race(g)
    for i in range(1, 4):                      # rivals parked in the south-east corner, frozen
        g.rules_debug_place(i, 1000, 1000 - 16 * i, NORTH)
    g.rules_debug_freeze(0xE)
    return g


def px(k):
    return k.x / ONE, k.y / ONE


def hold(g, keys, n):
    for _ in range(n):
        g.game_step(keys)


def wall_clearance(g, x, y):
    """Distance from (x, y) to the nearest wall cell (0 if inside one)."""
    best = 99.0
    cx, cy = int(x // 8), int(y // 8)
    for yy in range(cy - 2, cy + 3):
        for xx in range(cx - 2, cx + 3):
            if g.rules_surface_at(xx * 8, yy * 8) == SURF_WALL:
                qx = min(max(x, xx * 8), xx * 8 + 8)
                qy = min(max(y, yy * 8), yy * 8 + 8)
                best = min(best, math.hypot(x - qx, y - qy))
    return best


# ---- surfaces and speeds ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("x,surface,top", [(100, SURF_ROAD, "TOP_ROAD"), (131, SURF_CURB, "TOP_CURB"),
                                           (146, SURF_SLOW, "TOP_SLOW")])
def test_top_speed_per_surface(race, x, surface, top):
    race.rules_debug_place(0, x, 680, NORTH)
    assert race.rules_surface_at(x, 680) == surface
    hold(race, A, 110)
    k = race.kart(0)
    assert k.surface == surface and k.speed == tuning(top)
    assert abs(k.x / ONE - x) < 1, "drove straight"


def test_coasting_slows_to_a_stop_and_brake_stops_sooner(race):
    race.rules_debug_place(0, 100, 680, NORTH)
    hold(race, A, 60)
    v = race.kart(0).speed
    hold(race, 0, 10)
    assert race.kart(0).speed == v - 10 * tuning("COAST_DRAG")
    hold(race, B, 25)
    assert race.kart(0).speed <= 0


def turns(g, keys, n):
    """Heading change per frame (signed, steps) over n frames of keys."""
    out = []
    for _ in range(n):
        h = g.kart(0).heading
        g.game_step(keys)
        d = (g.kart(0).heading - h) % 1024
        out.append(d - 1024 if d >= 512 else d)
    return out


def test_launch_is_punchy_and_eases_off_near_top_speed(race):
    race.rules_debug_place(0, 100, 680, NORTH)
    race.game_step(A)
    assert race.kart(0).speed == tuning("ACCEL_LAUNCH"), "full pull from rest"
    while race.kart(0).speed < tuning("TOP_ROAD") * 9 // 10:
        race.game_step(A)
    v = race.kart(0).speed
    race.game_step(A)
    assert 0 < race.kart(0).speed - v < tuning("ACCEL_LAUNCH") // 2, "gentler near the top"


def test_the_wheel_ramps_in_needs_speed_and_turns_the_heading(race):
    race.rules_debug_place(0, 100, 680, NORTH)
    hold(race, RIGHT, 30)
    assert race.kart(0).heading == NORTH, "no steering at rest"
    hold(race, A, 25)                                # past STEER_FULL_SPEED, under the taper
    ramp, full = tuning("STEER_RAMP"), tuning("STEER")
    seen = turns(race, A | RIGHT, 6)
    assert seen[0] == ramp and seen[-1] == full and seen == sorted(seen), seen
    assert race.kart(0).steer == full
    back = turns(race, A, 4)                         # let go: the wheel comes back, the kart still turns a little
    assert back[0] == full - ramp and back[-1] == 0 and race.kart(0).steer == 0, back


def test_steering_is_gentler_at_top_speed(race):
    race.rules_debug_place(0, 100, 680, NORTH)
    hold(race, A, 100)
    assert race.kart(0).speed == tuning("TOP_ROAD")
    assert turns(race, A | RIGHT, 8)[-1] == tuning("STEER_AT_TOP") < tuning("STEER")


def test_braking_turns_in_sharper(race):
    def heading_change(keys):
        race.rules_debug_place(0, 100, 680, NORTH)
        hold(race, A, 100)
        return sum(turns(race, keys, 8))
    assert heading_change(B | RIGHT) > heading_change(A | RIGHT)


def lateral(k):
    """The kart's sideways speed (Q16 px/frame) relative to its heading."""
    a = k.heading * 2 * math.pi / 1024
    return -k.vx * math.sin(a) + k.vy * math.cos(a)


def test_full_lock_at_top_speed_runs_wider_than_below_the_taper(race):
    def slide(speed_frames):
        race.rules_debug_place(0, 100, 680, NORTH)
        hold(race, A, speed_frames)
        hold(race, A | RIGHT, 12)
        return abs(lateral(race.kart(0)))
    assert slide(100) > 1.4 * slide(12)


# ---- walls --------------------------------------------------------------------------------------------------------

def wall_run(g, x, y, heading, frames=240, keys=A):
    """Drive at a wall; returns the clearances and speeds seen."""
    g.rules_debug_place(0, x, y, heading)
    out = []
    for _ in range(frames):
        g.game_step(keys)
        k = g.kart(0)
        out.append((wall_clearance(g, *px(k)), k.speed, k.wall_hits))
    return out


def test_wall_bounce_never_embeds(race):
    r = tuning("KART_RADIUS")
    runs = [(500, 92, EAST), (100, 640, WEST), (100, 600, (WEST + 64) % 1024), (560, 92, (EAST + 900) % 1024),
            (700, 250, 256 + 40), (300, 950, 256), (920, 560, 0)]
    for x, y, h in runs:
        seen = wall_run(race, x, y, h)
        assert max(w for _, _, w in seen) >= 1, "never reached the wall from %s" % ((x, y, h),)
        assert min(c for c, _, _ in seen) >= r - 0.02, "embedded %.2f px from %s" % (
            min(c for c, _, _ in seen), (x, y, h))


def test_wall_bounce_at_boost_speed_never_embeds(race):
    r = tuning("KART_RADIUS")
    for h in range(0, 1024, 64):
        race.rules_debug_place(0, 560, 92, h)
        race.rules_debug_set(0, tuning("PAD_BOOST_SPEED"), 1, 0)
        for _ in range(60):
            race.game_step(A)
            assert wall_clearance(race, *px(race.kart(0))) >= r - 0.02, "heading %d" % h


def hit_wall(g, x, y, heading, speed=2 * ONE):
    """Drive at a wall at a set speed; returns (speed before, the kart right after the first hit)."""
    g.rules_debug_place(0, x, y, heading)
    g.rules_debug_set(0, speed, 1, 0)
    hits = 0
    while hits == 0:
        v = math.hypot(g.kart(0).vx, g.kart(0).vy)
        g.game_step(A)
        hits = g.kart(0).wall_hits
    return v, g.kart(0)


def test_a_head_on_wall_hit_bounces_back_and_costs_most_of_the_speed(race):
    v, k = hit_wall(race, 100, 640, WEST)
    assert k.vx > 0, "bounced back off the sea wall"
    assert math.hypot(k.vx, k.vy) <= v * 0.45 + ONE * 0.05


def test_a_glancing_wall_hit_keeps_most_of_the_speed(race):
    v, k = hit_wall(race, 110, 700, (NORTH - 64) % 1024)    # 22.5 degrees off the line of the sea wall
    assert math.hypot(k.vx, k.vy) >= v * 0.6, "scraped along"
    assert k.vy < 0, "still going north"


def test_reverse_out_of_a_wall(race):
    race.rules_debug_place(0, 100, 640, WEST)
    hold(race, A, 90)                                # nose in the sea wall, pushing
    k = race.kart(0)
    x_wall = k.x / ONE
    assert k.wall_hits >= 1 and abs(k.speed) < ONE // 2
    hold(race, B, 90)
    k = race.kart(0)
    assert -tuning("REVERSE_MAX") <= k.speed < 0, "B at rest reverses"
    assert k.speed == -tuning("REVERSE_MAX")
    assert k.x / ONE > x_wall + 10, "backed away from the wall"
    hold(race, B | LEFT, 60)                         # reversing with the wheel turned swings the nose north
    hold(race, A, 60)
    k = race.kart(0)
    assert k.y / ONE < 620 and k.speed > ONE, "drove off along the straight"


# ---- drift and boosts ---------------------------------------------------------------------------------------------

def drift(g, frames, x=128, y=720):
    """Accelerate north up the straight, then drift left (R + LEFT pressed together) countersteering, release."""
    g.rules_debug_place(0, x, y, NORTH)
    hold(g, A, 45)
    g.game_step(A | R | LEFT)
    hold(g, A | R | RIGHT, frames - 1)
    k = g.kart(0)
    assert k.drift == 1 and k.drift_charge == frames
    g.game_step(A)


def test_a_long_drift_releases_a_boost(race):
    drift(race, tuning("DRIFT_CHARGE"))
    k = race.kart(0)
    assert k.drift == 0 and k.boost == tuning("DRIFT_BOOST_FRAMES") - 0 and k.lap_boosts == 1
    assert race.rules_events() & 8
    assert abs(k.speed - tuning("DRIFT_BOOST_SPEED")) < 0x200


def test_a_short_drift_gives_nothing(race):
    drift(race, tuning("DRIFT_CHARGE") - 1)
    k = race.kart(0)
    assert k.drift == 0 and k.boost == 0 and k.lap_boosts == 0


def test_no_drift_below_half_speed(race):
    race.rules_debug_place(0, 128, 720, NORTH)
    hold(race, A, 10)
    race.game_step(A | R | LEFT)
    assert race.kart(0).drift == 0


def test_boost_pads(race):
    pts = centre_points(race)
    for arc, lat in D.PADS:
        x, y, h = D.at_arc(__import__("numpy").array(pts, float), arc - 60, lat)
        race.rules_debug_place(0, round(x), round(y), h)
        race.rules_debug_set(0, 2 * ONE, 1, 0)
        got = False
        for _ in range(40):
            race.game_step(A)
            k = race.kart(0)
            if k.boost:
                got = True
                assert k.boost == tuning("PAD_BOOST_FRAMES") and k.speed == tuning("PAD_BOOST_SPEED")
                break
        assert got, "pad at arc %d missed" % arc
        hold(race, A, tuning("PAD_BOOST_FRAMES"))
        assert race.kart(0).boost == 0


# ---- checkpoints, laps, placement ---------------------------------------------------------------------------------

def test_the_start_crossing_is_lap_1(race):
    race.rules_debug_place(0, 100, 720, NORTH)
    hold(race, A, 45)
    k = race.kart(0)
    assert k.lap == 1 and k.cp == 0 and k.progress >= 0


def test_laps_need_checkpoints_in_order(race):
    race.rules_debug_place(0, 100, 720, NORTH)
    hold(race, A, 45)
    assert race.kart(0).lap == 1
    # backwards over the line and forward again: still lap 1
    hold(race, B, 160)
    k = race.kart(0)
    assert k.y / ONE > 700 and k.lap == 1 and k.progress < 0
    hold(race, A, 60)
    assert race.kart(0).lap == 1
    # teleported to the end of the lap (every checkpoint skipped), across the line: no lap
    race.rules_debug_place(0, 100, 740, NORTH)
    hold(race, A, 70)
    assert race.kart(0).y / ONE < 680 and race.kart(0).lap == 1
    # a kart that leaves its corridor keeps its tracked point: moved across the infield it gains nothing
    before = race.kart(0).progress
    race.rules_debug_move(0, 330, 110)             # the Necklace, 1500 px of track ahead
    hold(race, A, 20)
    assert race.kart(0).progress < before + 200


def test_a_full_lap_in_order_counts(race):
    """Drives the centre line (debug moves along it, checkpoint by checkpoint) and crosses the line: lap 2."""
    pts = centre_points(race)
    race.rules_debug_place(0, 100, 700, NORTH)
    race.game_step(0)
    for i in range(0, len(pts), 3):
        race.rules_debug_move(0, pts[i][0], pts[i][1])
        race.game_step(0)
    race.rules_debug_move(0, pts[-1][0], pts[-1][1])
    race.game_step(0)
    race.rules_debug_move(0, pts[1][0], pts[1][1])
    race.game_step(0)
    k = race.kart(0)
    assert k.lap == 2 and race.rules_lap_frames(1) > 0


def test_kart_contacts_push_apart(race):
    race.rules_debug_place(0, 100, 700, NORTH)
    race.rules_debug_place(1, 104, 650, NORTH)
    hold(race, A, 60)
    a, b = race.kart(0), race.kart(1)
    d = math.hypot(a.x - b.x, a.y - b.y) / ONE
    assert d >= 2 * tuning("KART_RADIUS") - 0.05


def test_a_kart_pushed_into_a_wall_by_another_never_embeds(race):
    """A rival parked against the sea wall, the player driving into it from the side: the contact push must not leave
    either kart in the wall (the push falls back to the pre-push position, not the pushed one)."""
    r = tuning("KART_RADIUS")
    # two karts on the same spot a radius from the wall: the contact pushes kart 0 a full radius into it
    race.rules_debug_freeze(0xF)
    race.rules_debug_place(0, 46, 620, NORTH)        # the wall cells end at x = 40
    race.rules_debug_place(1, 46, 620, NORTH)
    race.game_step(0)
    for i in (0, 1):
        k = race.kart(i)
        assert race.rules_surface_at(k.x // ONE, k.y // ONE) != SURF_WALL, "kart %d left inside the wall" % i
    race.rules_debug_freeze(0xE)
    for y0 in (640, 600, 560):
        race.rules_debug_place(1, 51, y0, WEST)            # its circle touching the wall cells at x < 44
        race.rules_debug_place(0, 75, y0 + 3, WEST)
        race.rules_debug_set(0, 2 * ONE, 1, 0)
        for _ in range(60):
            race.game_step(A)
            for i in (0, 1):
                k = race.kart(i)
                assert wall_clearance(race, *px(k)) >= r - 0.02, "kart %d embedded at y %d" % (i, y0)
                assert race.rules_surface_at(k.x // ONE, k.y // ONE) != SURF_WALL


def finish_setup(g, kart, x, y, speed, lap=3):
    g.rules_debug_place(kart, x, y, NORTH)
    g.rules_debug_set(kart, speed, lap, 31)


def test_finishing_lap_3_ends_the_race_with_a_win(race):
    finish_setup(race, 0, 100, 696, 2 * ONE)
    race.game_step(A)
    race.game_step(A)
    race.game_step(A)
    k = race.kart(0)
    assert k.finished and k.place == 1 and race.rules_finished()
    assert race.rules_scene() == SC_FINISH
    t = race.rules_trophies()
    assert t & 1 and t & 2, "Win and Under 2:15"
    hold(race, 0, tuning("FINISH_FRAMES"))
    assert race.rules_scene() == SC_RESULTS and race.game_ended()


def test_placement_ties_on_the_same_frame(race):
    race.rules_debug_freeze(0xF)                   # everyone coasts: the same speed, the same frame
    # rival 1 a pixel further past the line on the same frame: it is ahead
    finish_setup(race, 0, 90, 693, 2 * ONE)
    finish_setup(race, 1, 110, 692, 2 * ONE)
    race.game_step(0)
    race.game_step(0)
    a, b = race.kart(0), race.kart(1)
    assert a.finished and b.finished and a.finish_frame == b.finish_frame
    assert b.progress > a.progress and (b.place, a.place) == (1, 2)


def test_placement_exact_tie_goes_to_the_lower_index(race):
    race.rules_debug_freeze(0xF)
    finish_setup(race, 2, 110, 692, 2 * ONE)
    finish_setup(race, 1, 90, 692, 2 * ONE)
    race.game_step(0)
    race.game_step(0)
    a, b = race.kart(1), race.kart(2)
    assert a.finished and b.finished and a.progress == b.progress
    assert (a.place, b.place) == (1, 2)


def test_standings_by_progress(race):
    race.rules_debug_place(0, 100, 600, NORTH)     # player ahead of the grid
    race.game_step(0)
    assert race.kart(0).place == 1 and race.rules_order(1) == 0
    assert sorted(race.rules_order(p) for p in range(1, 5)) == [0, 1, 2, 3]


def test_the_clean_lap_trophy(race):
    race.rules_debug_place(0, 100, 700, NORTH)
    race.rules_debug_set(0, 2 * ONE, 1, 31)        # on lap 1, no wall hit yet
    race.rules_debug_move(0, 100, 697)
    race.game_step(A)
    race.game_step(A)
    assert race.kart(0).lap == 2 and race.rules_trophies() & 4


def test_a_wall_hit_spoils_the_clean_lap(race):
    wall_run(race, 100, 640, WEST, frames=60)
    assert race.kart(0).wall_hits >= 1 and race.kart(0).lap_clean == 0
    race.rules_debug_place(0, 100, 697, NORTH)
    race.rules_debug_set(0, 2 * ONE, 1, 31)
    race.game_step(A)
    race.game_step(A)
    assert race.kart(0).lap == 2 and not race.rules_trophies() & 4
    assert race.kart(0).lap_clean == 1, "a new lap starts clean"


def test_three_drift_boosts_in_one_lap(race):
    for n in range(3):
        drift(race, tuning("DRIFT_CHARGE") + 5)
        assert race.kart(0).lap_boosts == n + 1
        assert bool(race.rules_trophies() & 8) == (n == 2)


def test_the_race_is_deterministic(g):
    import arcade_test as T
    keys = [8, 0, 8] + [0] * 180 + [A] * 200 + [A | RIGHT] * 50 + [A | R | LEFT] * 60 + [A] * 100
    assert T.pc_hashes(g, keys) == T.pc_hashes(g, keys)
    k0 = None
    g.game_init(0)
    for k in keys:
        g.game_step(k)
    k0 = g.kart(1)
    assert k0.speed > 0 and g.rules_scene() == SC_RACE, "the rivals drive"

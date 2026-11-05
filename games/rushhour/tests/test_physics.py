"""RUSH HOUR's physics and entities on small test maps (conftest.Arena): collision, one-way platforms, jumps,
coyote time and the jump buffer, bugs, pickups, checkpoints, hits, respawns and the trophies."""
import pytest

from conftest import (A, B, DOWN, LEFT, RIGHT, E_BUG, E_CHAI, E_CHECK, E_DOOR, E_ORB, ES_GONE, ES_LIVE, ES_ON,
                      ES_SQUASHED, SC_PLAY, SC_RESULTS, Arena, to_play, tuning)

TILE = 16
PH = 14            # player hitbox height
PW = 12


def arena(rh, rows, start, ents=()):
    """game_init, into play, then this map with these entities; the player stands on start (tx, ty)."""
    rh.game_init(0)
    to_play(rh)
    a = Arena(rh, rows)
    for kind, tx, ty in ents:
        rh.rules_debug_add_ent(kind, tx, ty)
    rh.rules_debug_set_start(*start)
    rh._arena = a                      # keep the buffer alive while the test runs
    return a


def run(rh, keys, n=1):
    out = []
    for _ in range(n):
        rh.game_step(keys)
        out.append((rh.rules_px(), rh.rules_py()))
    return out


def settle(rh, n=5):
    run(rh, 0, n)


FLAT = ["." * 24] * 11 + ["#" * 24]


def feet(rh):
    return rh.rules_py() + PH


# ---- collision ---------------------------------------------------------------------------------------------------

def test_standing_on_the_floor(rh):
    arena(rh, FLAT, (3, 10))
    settle(rh, 30)
    assert rh.rules_on_ground() and feet(rh) == 11 * TILE and rh.rules_vy() == 0


def test_no_tunnelling_at_top_speed(rh):
    rows = ["." * 24] * 9 + ["." * 12 + "#" + "." * 11] * 2 + ["#" * 24]
    arena(rh, rows, (2, 10))
    for x, _ in run(rh, RIGHT | B, 200):
        assert x + PW <= 12 * TILE
    assert rh.rules_px() + PW == 12 * TILE
    for speed in (tuning("RUN_MAX"), 0x0C00, 0x1800):          # far faster than the game ever goes
        arena(rh, rows, (8, 10))
        rh.rules_debug_velocity(speed, 0)
        for x, _ in run(rh, RIGHT | B, 20):
            assert x + PW <= 12 * TILE, speed
    # falling onto a one-tile floor and a one-way platform, and jumping into a one-tile ceiling
    for tile in "#=":
        rows = ["." * 24] * 6 + ["." * 4 + tile * 4 + "." * 16] + ["." * 24] * 5
        arena(rh, rows, (5, 1))
        rh.rules_debug_velocity(0, 0x1800)
        for _, y in run(rh, 0, 20):
            assert y + PH <= 6 * TILE, tile
        assert feet(rh) == 6 * TILE and rh.rules_on_ground()
    rows = ["." * 24] * 4 + ["." * 4 + "#" * 4 + "." * 16] + ["." * 24] * 6 + ["#" * 24]
    arena(rh, rows, (5, 10))
    rh.rules_debug_velocity(0, -0x1800)
    for _, y in run(rh, 0, 20):
        assert y >= 5 * TILE


def test_walls_stop_the_player_and_the_level_edges_hold(rh):
    arena(rh, FLAT, (1, 10))
    run(rh, LEFT | B, 60)
    assert rh.rules_px() == 0 and rh.rules_vx() == 0
    run(rh, RIGHT | B, 400)
    assert rh.rules_px() == 24 * TILE - PW


def test_one_way_platforms_hold_from_above_only(rh):
    rows = ["." * 24] * 7 + ["." * 4 + "=" * 6 + "." * 14] + ["." * 24] * 3 + ["#" * 24]
    arena(rh, rows, (6, 10))                           # under the platform
    settle(rh, 5)
    rh.game_step(A)
    top = min(y for _, y in run(rh, A, 40))
    assert top < 7 * TILE - PH, "the jump did not pass up through the one-way platform"
    run(rh, 0, 80)
    assert feet(rh) == 7 * TILE and rh.rules_on_ground(), "did not land on the one-way platform"


def test_drop_through_one_way_only(rh):
    rows = ["." * 24] * 6 + ["." * 4 + "=" * 6 + "." * 14] + ["." * 24] * 4 + ["#" * 24]
    arena(rh, rows, (6, 5))
    settle(rh)
    assert feet(rh) == 6 * TILE
    rh.game_step(DOWN | A)
    assert rh.rules_vy() >= 0, "Down + A on a one-way platform jumped"
    run(rh, DOWN | A, 60)
    assert feet(rh) == 11 * TILE and rh.rules_on_ground()
    # the same on solid ground: never below its top
    rows = ["." * 24] * 6 + ["." * 4 + "#" * 6 + "." * 14] + ["." * 24] * 4 + ["#" * 24]
    arena(rh, rows, (6, 5))
    settle(rh)
    for _, y in run(rh, DOWN | A, 1) + run(rh, 0, 3) + run(rh, DOWN | A, 120):
        assert y + PH <= 6 * TILE
    # straddling one-way and solid: the solid holds
    rows = ["." * 24] * 6 + ["." * 4 + "===##" + "." * 15] + ["." * 24] * 4 + ["#" * 24]
    arena(rh, rows, (7, 5))
    rh.rules_debug_place(7 * TILE + 8, 6 * TILE - PH)
    settle(rh)
    for _, y in run(rh, DOWN | A, 60):
        assert y + PH <= 6 * TILE


# ---- jumps -------------------------------------------------------------------------------------------------------

def jump_height(rh, hold):
    arena(rh, FLAT, (3, 10))
    settle(rh)
    y0 = rh.rules_py()
    ys = [y for _, y in run(rh, A, hold)] + [y for _, y in run(rh, 0, 120)]
    assert feet(rh) == 11 * TILE
    return y0 - min(ys)


def test_jump_height_with_and_without_a_held(rh):
    tap, full = jump_height(rh, 1), jump_height(rh, 60)
    assert 40 <= tap <= 64, tap                 # about three tiles
    assert 90 <= full <= 116, full              # about six and a half
    mid = jump_height(rh, 12)
    assert tap < mid < full


def frames_to_leave_ledge(rh, rows, start):
    arena(rh, rows, start)
    settle(rh)
    n = 0
    while rh.rules_on_ground():
        rh.game_step(RIGHT)
        n += 1
        assert n < 200
    return n


LEDGE = ["." * 24] * 7 + ["#" * 8 + "." * 16] + ["." * 24] * 3 + ["#" * 24]


def test_coyote_time(rh):
    for late, jumps in ((1, True), (tuning("COYOTE_FRAMES") - 1, True), (tuning("COYOTE_FRAMES") + 2, False)):
        frames_to_leave_ledge(rh, LEDGE, (6, 6))
        run(rh, RIGHT, late - 1)
        rh.game_step(RIGHT | A)
        assert (rh.rules_vy() < 0) == jumps, late


def test_jump_buffer(rh):
    rows = FLAT
    arena(rh, rows, (3, 10))
    rh.rules_debug_place(3 * TILE, 4 * TILE)
    n = 0
    while not rh.rules_on_ground():
        rh.game_step(0)
        n += 1
    for early, jumps in ((2, True), (tuning("BUFFER_FRAMES"), True), (tuning("BUFFER_FRAMES") + 4, False)):
        arena(rh, rows, (3, 10))
        rh.rules_debug_place(3 * TILE, 4 * TILE)
        run(rh, 0, n - early)
        run(rh, A, 1)
        jumped = False
        for _ in range(early + 3):
            rh.game_step(A)
            jumped = jumped or rh.rules_vy() < 0
        assert jumped == jumps, early


def test_running_is_faster_than_walking(rh):
    arena(rh, ["." * 200] * 11 + ["#" * 200], (1, 10))
    run(rh, RIGHT, 120)
    assert rh.rules_vx() == tuning("WALK_MAX")
    run(rh, RIGHT | B, 120)
    assert rh.rules_vx() == tuning("RUN_MAX")
    run(rh, 0, 120)
    assert rh.rules_vx() == 0


# ---- bugs, hits and respawns -------------------------------------------------------------------------------------

def test_bugs_walk_and_turn_at_walls_and_ledges(rh):
    rows = ["." * 24] * 7 + ["." * 4 + "#" * 8 + "." * 12] + ["." * 24] * 3 + ["#" + "." * 20 + "###"]
    arena(rh, rows, (22, 10), [(E_BUG, 8, 6)])
    xs = []
    for _ in range(600):
        rh.game_step(0)
        xs.append(rh.rules_ent_x(0))
    assert min(xs) >= 4 * TILE and max(xs) + tuning("BUG_W") <= 12 * TILE
    assert min(xs) <= 4 * TILE + 2 and max(xs) + tuning("BUG_W") >= 12 * TILE - 2, "the bug never reached a ledge"
    rows = ["." * 24] * 10 + ["." * 3 + "#" + "." * 6 + "#" + "." * 13] + ["#" * 24]
    arena(rh, rows, (20, 10), [(E_BUG, 6, 10)])
    xs = []
    for _ in range(600):
        rh.game_step(0)
        xs.append(rh.rules_ent_x(0))
    assert min(xs) >= 4 * TILE and max(xs) + tuning("BUG_W") <= 10 * TILE


def test_stomping_a_bug(rh):
    for held, bounce in ((0, tuning("STOMP_LO")), (A, tuning("STOMP_HI"))):
        arena(rh, FLAT, (1, 10), [(E_BUG, 10, 10)])
        bx, by = rh.rules_ent_x(0), rh.rules_ent_y(0)
        rh.rules_debug_place(bx - 8, by - 48)          # the bug walks left while the player falls onto it
        vys = []
        for _ in range(60):
            rh.game_step(held)
            vys.append(rh.rules_vy())
            if rh.rules_ent_state(0) != ES_LIVE:
                break
        assert rh.rules_ent_state(0) == ES_SQUASHED
        assert vys[-1] == bounce and rh.rules_hp() == 3 and not rh.rules_damaged()
        run(rh, 0, tuning("SQUASH_FRAMES") + 1)
        assert rh.rules_ent_state(0) == ES_GONE


def hit_by_bug(rh):
    """Walk right into a bug until hurt; returns the frames it took."""
    for n in range(300):
        before = rh.rules_hp(), rh.rules_shield()
        rh.game_step(RIGHT)
        if (rh.rules_hp(), rh.rules_shield()) != before:
            return n
    raise AssertionError("never hit")


def test_side_contact_hurts_with_knockback_and_invulnerability(rh):
    arena(rh, FLAT, (4, 10), [(E_BUG, 14, 10)])
    hit_by_bug(rh)
    assert rh.rules_hp() == 2 and rh.rules_damaged()
    assert rh.rules_vx() < 0 and rh.rules_vy() < 0, "no knockback away from the bug"
    assert rh.rules_invuln() > 0
    hp = rh.rules_hp()
    for _ in range(tuning("INVULN_FRAMES") - 5):
        rh.game_step(RIGHT)
        assert rh.rules_hp() == hp or rh.rules_invuln() == 0


def test_spikes_hurt(rh):
    rows = ["." * 24] * 11 + ["#" * 24]
    rows[10] = "." * 8 + "^" + "." * 15
    arena(rh, rows, (4, 10))
    for _ in range(120):
        rh.game_step(RIGHT)
        if rh.rules_damaged():
            break
    assert rh.rules_hp() == 2


def test_shield_absorbs_one_hit(rh):
    arena(rh, FLAT, (3, 10), [(E_ORB, 6, 10), (E_BUG, 16, 10)])
    for _ in range(80):
        rh.game_step(RIGHT)
        if rh.rules_shield():
            break
    assert rh.rules_shield() == 1 and rh.rules_ent_state(0) == ES_GONE
    hit_by_bug(rh)
    assert rh.rules_shield() == 0 and rh.rules_hp() == 3 and not rh.rules_damaged()
    run(rh, 0, tuning("INVULN_FRAMES") + 2)
    hit_by_bug(rh)
    assert rh.rules_hp() == 2 and rh.rules_damaged()


def lose_all_hearts(rh):
    for _ in range(3):
        hit_by_bug(rh)
        if rh.rules_dead():
            break
        run(rh, 0, tuning("INVULN_FRAMES") + 2)


def test_respawn_without_checkpoint(rh):
    rows = ["." * 24] * 11 + ["#" * 10 + "." * 4 + "#" * 10]
    arena(rh, rows, (2, 10))
    sx, sy = rh.rules_px(), rh.rules_py()
    clock = rh.rules_run_frames()
    n = 0
    while not rh.rules_dead():
        rh.game_step(RIGHT)
        n += 1
        assert n < 300, "never fell into the pit"
    assert rh.rules_lives_lost() == 1 and rh.rules_damaged()
    run(rh, RIGHT, tuning("DEATH_FRAMES") + 1)
    assert not rh.rules_dead()
    assert rh.rules_run_frames() == clock + n + tuning("DEATH_FRAMES") + 1, "the clock stopped while dead"
    run(rh, 0, 1)
    assert abs(rh.rules_px() - sx) <= 1 and rh.rules_py() == sy
    assert rh.rules_hp() == tuning("MAX_HP") and rh.rules_scene() == SC_PLAY


def test_three_hits_respawn_at_the_last_checkpoint(rh):
    arena(rh, ["." * 40] * 11 + ["#" * 40], (2, 10), [(E_CHECK, 6, 10), (E_BUG, 20, 10)])
    run(rh, RIGHT, 60)
    assert rh.rules_touched_checkpoint() and rh.rules_ent_state(0) == ES_ON
    cx = rh.rules_ent_x(0)
    lose_all_hearts(rh)
    assert rh.rules_dead()
    run(rh, 0, tuning("DEATH_FRAMES") + 2)
    assert not rh.rules_dead() and rh.rules_hp() == 3
    assert abs(rh.rules_px() - cx) <= 4 and feet(rh) == 11 * TILE


# ---- pickups, the door and the trophies -------------------------------------------------------------------------

def walk_to_door(rh, keys=RIGHT, limit=900):
    for _ in range(limit):
        rh.game_step(keys)
        if rh.rules_scene() == SC_RESULTS:
            return
    raise AssertionError("never reached the door")


def test_chai_counts_and_all_chai_trophy(rh):
    arena(rh, ["." * 30] * 11 + ["#" * 30], (1, 10), [(E_CHAI, 5, 10), (E_CHAI, 9, 10), (E_DOOR, 20, 10)])
    assert rh.rules_chai_total() == 2
    walk_to_door(rh)
    assert rh.rules_chai() == 2 and rh.rules_trophies() & 2
    arena(rh, ["." * 30] * 11 + ["#" * 30], (1, 10), [(E_CHAI, 5, 7), (E_CHAI, 9, 10), (E_DOOR, 20, 10)])
    walk_to_door(rh)
    assert rh.rules_chai() == 1 and not rh.rules_trophies() & 2


def test_no_damage_and_checkpoint_free_trophies(rh):
    arena(rh, ["." * 30] * 11 + ["#" * 30], (1, 10), [(E_DOOR, 20, 10)])
    walk_to_door(rh)
    assert rh.rules_trophies() & 4 and rh.rules_trophies() & 8
    arena(rh, ["." * 30] * 11 + ["#" * 30], (1, 10), [(E_CHECK, 6, 10), (E_DOOR, 20, 10)])
    walk_to_door(rh)
    assert rh.rules_trophies() & 4 and not rh.rules_trophies() & 8
    rows = ["." * 30] * 11 + ["#" * 30]
    rows[10] = "." * 8 + "^" + "." * 21
    arena(rh, rows, (1, 10), [(E_DOOR, 20, 10)])
    for _ in range(200):                                # into the spike
        rh.game_step(RIGHT)
        if rh.rules_damaged():
            break
    assert rh.rules_damaged()
    for i in range(600):                                # then hop over it
        rh.game_step(RIGHT | (A if i % 2 else 0))
        if rh.rules_scene() == SC_RESULTS:
            break
    assert rh.rules_scene() == SC_RESULTS
    assert not rh.rules_trophies() & 4 and rh.rules_trophies() & 8


def test_trophies_are_latched_in_the_hashed_state(rh):
    arena(rh, ["." * 30] * 11 + ["#" * 30], (1, 10), [(E_DOOR, 20, 10)])
    walk_to_door(rh)
    t, h = rh.rules_trophies(), rh.game_hash()
    for _ in range(50):
        rh.game_step(0)
    assert rh.rules_trophies() == t and rh.game_hash() != h


def test_checkpoints_can_be_jumped_over(rh):
    arena(rh, ["." * 30] * 11 + ["#" * 30], (1, 10), [(E_CHECK, 8, 10), (E_DOOR, 20, 10)])
    keys = [RIGHT | B] * 20 + [RIGHT | B | A] * 30 + [RIGHT | B] * 200
    for k in keys:
        rh.game_step(k)
        if rh.rules_scene() == SC_RESULTS:
            break
    assert rh.rules_scene() == SC_RESULTS and not rh.rules_touched_checkpoint() and rh.rules_trophies() & 8

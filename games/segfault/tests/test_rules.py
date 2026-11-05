"""SEGFAULT's rules through the PC library (out/librules.so): the scenes, movement and collision, hitscan, doors,
the panels (Arkiv shelves, the World orb reader, the Chainlink terminal), the bugs, death and the trophies. Most
tests play a small arena loaded with rules_test_setup (the level/map.txt legend, padded with rack walls)."""
import ctypes
import random

import pytest

import arcade_test as T
from conftest import A, B, START, RIGHT, LEFT, UP, DOWN, L, R, tuning

ONE = 0x10000
HALF = 0x8000
SC_TITLE, SC_HOWTO, SC_PLAY, SC_RESULTS = range(4)
BUG_IDLE, BUG_CHASE, BUG_HURT, BUG_DEAD = range(4)
(MSG_NONE, MSG_NEED_KEY, MSG_GOT_KEY, MSG_HEALTH, MSG_HEALTH_FULL, MSG_SHELF_EMPTY, MSG_READER_DONE, MSG_SECRET,
 MSG_ALL_BUGS, MSG_REBOOT, MSG_LOCKED) = range(11)
CELL_FLOOR, CELL_DOOR, CELL_SHELF_EMPTY, CELL_READER_DONE, CELL_SECRET = 0, 5, 7, 9, 12
EAST, SOUTH, WEST, NORTH = 0, 256, 512, 768

READS = {
    "rules_scene": ctypes.c_uint8, "rules_paused": ctypes.c_uint8, "rules_pause_sel": ctypes.c_uint8,
    "rules_run_frames": ctypes.c_uint32, "rules_finished": ctypes.c_uint8, "rules_trophies": ctypes.c_uint32,
    "rules_px": ctypes.c_int32, "rules_py": ctypes.c_int32, "rules_angle": ctypes.c_uint16,
    "rules_health": ctypes.c_uint8, "rules_has_key": ctypes.c_uint8, "rules_took_damage": ctypes.c_uint8,
    "rules_deaths": ctypes.c_uint8, "rules_dead_timer": ctypes.c_uint16, "rules_fire_cooldown": ctypes.c_uint16,
    "rules_shot_age": ctypes.c_uint16, "rules_last_hit": ctypes.c_int8, "rules_hurt_age": ctypes.c_uint16,
    "rules_walk": ctypes.c_uint16, "rules_msg": ctypes.c_uint8, "rules_msg_timer": ctypes.c_uint16,
    "rules_secret_found": ctypes.c_uint8, "rules_cell": ctypes.c_uint8, "rules_door_amount": ctypes.c_uint8,
    "rules_bug_count": ctypes.c_uint8, "rules_bugs_left": ctypes.c_uint8, "rules_squashed": ctypes.c_uint8,
    "rules_bug_x": ctypes.c_int32, "rules_bug_y": ctypes.c_int32, "rules_bug_state": ctypes.c_uint8,
    "rules_bug_hp": ctypes.c_uint8, "rules_bug_sees": ctypes.c_uint8, "rules_bug_anim": ctypes.c_uint16,
    "rules_bug_biting": ctypes.c_uint8, "rules_los": ctypes.c_uint8,
}


class Info(ctypes.Structure):
    _fields_ = [("id", ctypes.c_char * 4), ("rules_version", ctypes.c_uint32), ("n_trophies", ctypes.c_uint8),
                ("trophy_names", ctypes.POINTER(ctypes.c_char_p)), ("ghost_period", ctypes.c_uint16)]


@pytest.fixture
def g(lib):
    for name, rt in READS.items():
        getattr(lib, name).restype = rt
    lib.rules_los.argtypes = [ctypes.c_int32] * 4
    lib.rules_test_setup.argtypes = [ctypes.c_char_p, ctypes.c_uint16]
    lib.game_init(0)
    return lib


def arena(g, lines, angle=EAST):
    """Loads a small map (top-left of a 48 x 48 grid of rack walls) and starts playing it."""
    rows = [(ln + "#" * 48)[:48] for ln in lines] + ["#" * 48] * (48 - len(lines))
    g.rules_test_setup("".join(rows).encode(), angle)
    assert g.rules_scene() == SC_PLAY


def cell_centre(x, y):
    return (x * ONE + HALF, y * ONE + HALF)


def steps(g, keys, n=1):
    for _ in range(n):
        g.game_step(keys)


def press(g, keys):
    g.game_step(keys)
    g.game_step(0)


def face(g, target):
    """Turns (the short way) until the view is within half a turn step of target."""
    for _ in range(200):
        d = (target - g.rules_angle()) % 1024
        if min(d, 1024 - d) <= tuning("TURN_SPEED") // 2:
            return
        g.game_step(RIGHT if d < 512 else LEFT)
    raise AssertionError("could not face %d" % target)


def bugs(g):
    return [(g.rules_bug_x(i), g.rules_bug_y(i), g.rules_bug_state(i), g.rules_bug_hp(i))
            for i in range(g.rules_bug_count())]


def result(g):
    r = T.Result()
    g.game_result(ctypes.byref(r))
    return {f: getattr(r, f) for f, _ in T.Result._fields_}


# ---- Task 1: scenes -----------------------------------------------------------------------------------------------

def test_game_info(g):
    info = Info.in_dll(g, "GAME_INFO")
    assert info.id == b"SEGF" and info.n_trophies == 4 and info.rules_version == 4      # 4: seeded bug spawns
    names = [info.trophy_names[i] for i in range(4)]
    assert names == [b"All bugs", b"No damage", b"Under 3:00", b"Secret room"]


def _spawns(g):
    return [(g.rules_bug_x(i) >> 16, g.rules_bug_y(i) >> 16) for i in range(g.rules_bug_count())]


def test_the_seed_nudges_where_the_bugs_spawn(g):
    """Seed 0 spawns every bug on its map cell; any other seed nudges each bug up to two cells onto open floor next
    to it, never near the player's start and never onto another bug, the same way every time for that seed (and
    again when play starts)."""
    g.game_init(0)
    classic = _spawns(g)
    start = (g.rules_px() >> 16, g.rules_py() >> 16)
    layouts = set()
    for seed in (0x01234567, 0xDEADBEEF, 0x5EED0001, 77):
        g.game_init(seed)
        spawns = _spawns(g)
        assert len(spawns) == len(classic) and len(set(spawns)) == len(spawns), "bugs stacked on one cell"
        assert spawns != classic, "seed %#x moved no bug" % seed
        for (x, y), (cx, cy) in zip(spawns, classic):
            assert max(abs(x - cx), abs(y - cy)) <= 2, "a bug moved more than two cells"
            assert g.rules_cell(x, y) == CELL_FLOOR, "a bug spawned inside something"
            if (x, y) != (cx, cy):
                assert max(abs(x - start[0]), abs(y - start[1])) > 3, "a bug was nudged next to the start"
        press(g, START)
        press(g, START)
        assert g.rules_scene() == SC_PLAY and _spawns(g) == spawns, "play must start the same seeded bugs"
        g.game_init(seed)
        assert _spawns(g) == spawns
        layouts.add(tuple(spawns))
    assert len(layouts) == 4, "different seeds gave the same spawns"


def test_title_then_howto_then_play(g):
    for _ in range(100):
        g.game_step(RIGHT | A)
    assert g.rules_scene() == SC_TITLE and not g.game_ended()
    g.game_step(START)
    assert g.rules_scene() == SC_HOWTO
    g.game_step(START)                          # held: not a new press
    assert g.rules_scene() == SC_HOWTO
    g.game_step(0)
    press(g, A)
    assert g.rules_scene() == SC_PLAY and g.rules_health() == tuning("HEALTH_START")
    assert (g.rules_px(), g.rules_py()) == cell_centre(5, 42) and g.rules_angle() == NORTH
    assert g.rules_bug_count() == 25 and g.rules_bugs_left() == 25 and g.rules_run_frames() == 1


def test_pause_freezes_and_resumes(g):
    press(g, START)
    press(g, START)
    steps(g, UP, 10)
    frames, y = g.rules_run_frames(), g.rules_py()
    press(g, START)
    assert g.rules_paused() and g.rules_pause_sel() == 0
    steps(g, UP, 30)
    assert g.rules_paused() and g.rules_pause_sel() == 0
    g.game_step(A)                              # A on Resume
    assert not g.rules_paused()
    assert g.rules_run_frames() == frames and g.rules_py() == y
    press(g, START)
    assert g.rules_paused()
    press(g, START)
    assert not g.rules_paused()


def test_quit_from_pause_ends_the_run_unfinished(g):
    press(g, START)
    press(g, START)
    press(g, START)
    press(g, DOWN)
    assert g.rules_pause_sel() == 1
    press(g, UP)
    assert g.rules_pause_sel() == 0
    press(g, DOWN)
    g.game_step(A)
    assert g.game_ended() and g.rules_scene() == SC_RESULTS and not g.rules_finished()
    res = T.pc_result(g, [START, 0, START, 0, START, 0, DOWN, 0, A])
    assert not res["finished"] and res["score"] == 0
    g.game_step(0)
    press(g, START)
    assert not g.game_ended() and g.rules_scene() == SC_TITLE


# ---- Task 3: movement and collision -------------------------------------------------------------------------------

def test_move_and_turn_speeds(g):
    arena(g, ["#######", "#.....#", "#.@...#", "#.....#", "#######"], EAST)
    x, y = g.rules_px(), g.rules_py()
    g.game_step(UP)
    assert (g.rules_px(), g.rules_py()) == (x + tuning("MOVE_SPEED"), y)
    g.game_step(DOWN)
    assert (g.rules_px(), g.rules_py()) == (x, y)
    g.game_step(R)                              # strafe right: facing east, right is south (+y)
    assert (g.rules_px(), g.rules_py()) == (x, y + tuning("STRAFE_SPEED"))
    g.game_step(L)
    assert (g.rules_px(), g.rules_py()) == (x, y)
    g.game_step(RIGHT)
    assert g.rules_angle() == tuning("TURN_SPEED")
    steps(g, LEFT, 2)
    assert g.rules_angle() == 1024 - tuning("TURN_SPEED")
    assert g.rules_walk() > 0


def test_corner_collision(g):
    r = tuning("PLAYER_RADIUS")
    arena(g, ["#####", "#...#", "#.@.#", "#...#", "#####"], 896)       # facing north-east, into the corner
    for _ in range(200):
        g.game_step(UP)
        assert g.rules_px() <= 4 * ONE - r and g.rules_py() >= ONE + r
    assert g.rules_px() == 4 * ONE - r and g.rules_py() == ONE + r, "slides into the corner and stops at the radius"
    for turn in (RIGHT, LEFT):
        for _ in range(64):
            g.game_step(turn | UP | R)
            x, y = g.rules_px(), g.rules_py()
            assert ONE + r <= x <= 4 * ONE - r and ONE + r <= y <= 4 * ONE - r


def test_a_corner_to_corner_gap_is_not_passable(g):
    # (3,1) and (4,2) are open cells touching only at the corner point (4,2): nothing with a radius gets through.
    arena(g, ["#######", "#...#.#", "#.@#..#", "#######"], 128)
    rnd = random.Random(7)
    keys = [UP, UP | RIGHT, UP | LEFT, UP | R, UP | L, DOWN, UP]
    for _ in range(3000):
        g.game_step(rnd.choice(keys))
        assert g.rules_px() >> 16 < 4, "went through the corner gap to (%x, %x)" % (g.rules_px(), g.rules_py())


# ---- Task 3: hitscan ------------------------------------------------------------------------------------------------

def test_hitscan_hits_a_bug_in_the_crosshair_twice_to_squash(g):
    arena(g, ["##########", "#@.....b.#", "##########"], EAST)
    g.game_step(A)
    assert g.rules_bug_hp(0) == tuning("BUG_HP") - 1 and g.rules_last_hit() == 0
    assert g.rules_bug_state(0) == BUG_HURT and g.rules_shot_age() == 0
    steps(g, A, tuning("FIRE_COOLDOWN") - 1)
    assert g.rules_bug_hp(0) == 1, "the cooldown holds the next shot"
    g.game_step(A)
    assert g.rules_bug_state(0) == BUG_DEAD and g.rules_squashed() == 1 and g.rules_bugs_left() == 0


def test_hitscan_misses_off_the_aim_line_and_out_of_range(g):
    arena(g, ["##########", "#@.......#", "#......b.#", "##########"], EAST)
    g.game_step(A)
    assert g.rules_bug_hp(0) == tuning("BUG_HP") and g.rules_last_hit() == -1
    arena(g, ["#" * 24, "#@" + "." * 20 + "b#", "#" * 24], EAST)          # 21 tiles away: beyond the range
    g.game_step(A)
    assert g.rules_bug_hp(0) == tuning("BUG_HP")


def test_hitscan_blocked_by_walls_and_doors(g):
    arena(g, ["##########", "#@.D...b.#", "##########"], EAST)
    g.game_step(A)
    assert g.rules_bug_hp(0) == tuning("BUG_HP"), "a shot went through a closed door"
    steps(g, 0, tuning("FIRE_COOLDOWN"))
    press(g, B)                                                  # open the door (its face is 1.5 tiles ahead)
    steps(g, 0, tuning("DOOR_FRAMES") - 6)
    g.game_step(A)
    assert g.rules_door_amount(3, 1) < tuning("DOOR_FRAMES")
    assert g.rules_bug_hp(0) == tuning("BUG_HP"), "a shot went through a door that is still opening"
    steps(g, 0, tuning("FIRE_COOLDOWN"))
    assert g.rules_door_amount(3, 1) == tuning("DOOR_FRAMES")
    face(g, EAST)
    g.game_step(A)
    assert g.rules_bug_hp(0) == tuning("BUG_HP") - 1
    arena(g, ["##########", "#@.......#", "###.######", "####b#####", "##########"], 96)
    g.game_step(A)                                               # aimed right at the bug, through the wall corner
    assert g.rules_bug_hp(0) == tuning("BUG_HP") and g.rules_last_hit() == -1


def test_line_of_sight(g):
    arena(g, ["#######", "#@....#", "#.##..#", "#.....#", "#######"], EAST)
    a, b = cell_centre(1, 1), cell_centre(5, 3)
    assert g.rules_los(*a, *cell_centre(5, 1))
    assert g.rules_los(*a, *cell_centre(1, 3))
    assert not g.rules_los(*a, *cell_centre(4, 3)), "through the 2-cell block"
    assert g.rules_los(*a, *b) == g.rules_los(*b, *a)


# ---- Task 3: doors, panels, keycard, exit ------------------------------------------------------------------------

def test_door_timing(g):
    arena(g, ["#######", "#@.D..#", "#######"], EAST)
    press(g, B)
    assert g.rules_door_amount(3, 1) == 2
    steps(g, 0, tuning("DOOR_FRAMES") - 3)
    assert g.rules_door_amount(3, 1) == tuning("DOOR_FRAMES") - 1
    steps(g, UP, 3)                                              # not through yet: a door is passable only when open
    steps(g, 0, 5)
    assert g.rules_door_amount(3, 1) == tuning("DOOR_FRAMES")
    hold = tuning("DOOR_OPEN_HOLD")
    steps(g, 0, hold - 10)
    assert g.rules_door_amount(3, 1) == tuning("DOOR_FRAMES")
    steps(g, 0, 10 + tuning("DOOR_FRAMES") + 2)
    assert g.rules_door_amount(3, 1) == 0, "the door closes after its hold"
    # It never closes on the player standing in it.
    press(g, B)
    steps(g, 0, tuning("DOOR_FRAMES"))
    steps(g, UP, 16)                                             # into the doorway
    assert g.rules_px() >> 16 == 3
    steps(g, 0, hold + tuning("DOOR_FRAMES") * 2)
    assert g.rules_door_amount(3, 1) == tuning("DOOR_FRAMES")
    steps(g, UP, 16)                                             # out of it: now it closes
    steps(g, 0, tuning("DOOR_FRAMES") + 2)
    assert g.rules_door_amount(3, 1) == 0


def test_b_shuts_an_open_door(g):
    arena(g, ["#######", "#@.D..#", "#######"], EAST)
    press(g, B)
    steps(g, 0, tuning("DOOR_FRAMES"))
    press(g, B)
    steps(g, 0, tuning("DOOR_FRAMES"))
    assert g.rules_door_amount(3, 1) == 0


def test_the_locked_door_needs_the_keycard(g):
    arena(g, ["######", "#.@.K#", "#....#", "##L###", "#.X..#", "######"], SOUTH)
    steps(g, UP, 8)                              # to the middle of row 2, the locked door below
    press(g, B)
    steps(g, 0, tuning("DOOR_FRAMES") + 2)
    assert g.rules_msg() == MSG_LOCKED and g.rules_door_amount(2, 3) == 0
    steps(g, DOWN, 8)
    face(g, EAST)
    press(g, B)
    assert g.rules_has_key()
    face(g, SOUTH)
    steps(g, UP, 8)
    press(g, B)
    steps(g, 0, tuning("DOOR_FRAMES") + 2)
    assert g.rules_door_amount(2, 3) == tuning("DOOR_FRAMES")


def test_closed_door_blocks_the_player(g):
    arena(g, ["#######", "#@.D..#", "#######"], EAST)
    steps(g, UP, 60)
    assert g.rules_px() == 3 * ONE - tuning("PLAYER_RADIUS")


def test_exit_needs_keycard(g):
    arena(g, ["####X####", "#...@...K", "#########"], NORTH)
    press(g, B)
    assert g.rules_msg() == MSG_NEED_KEY and not g.rules_finished() and not g.game_ended()
    assert g.rules_scene() == SC_PLAY
    face(g, EAST)
    steps(g, UP, 40)
    press(g, B)
    assert g.rules_has_key() and g.rules_msg() == MSG_GOT_KEY and g.rules_cell(8, 1) == CELL_READER_DONE
    press(g, B)
    assert g.rules_msg() == MSG_READER_DONE and g.rules_has_key()
    face(g, WEST)
    while g.rules_px() > 4 * ONE + HALF:
        g.game_step(UP)
    face(g, NORTH)
    press(g, B)
    assert g.game_ended() and g.rules_finished() and g.rules_scene() == SC_RESULTS
    assert g.rules_msg() == MSG_REBOOT


def test_shelves_heal_once_and_never_past_100(g):
    arena(g, ["#####", "#@.A#", "#b###", "#####"], EAST)
    press(g, B)
    assert g.rules_msg() == MSG_HEALTH_FULL and g.rules_cell(3, 1) != CELL_SHELF_EMPTY
    for _ in range(600):                                         # the bug below bites while we stand still
        g.game_step(0)
        if g.rules_health() <= 60:
            break
    h = g.rules_health()
    assert h == 60
    press(g, B)
    assert g.rules_health() == h + tuning("HEALTH_PICKUP") and g.rules_msg() == MSG_HEALTH
    assert g.rules_cell(3, 1) == CELL_SHELF_EMPTY
    press(g, B)
    assert g.rules_msg() == MSG_SHELF_EMPTY


def test_a_shelf_never_heals_past_100(g):
    arena(g, ["#####", "#@.A#", "#b###", "#####"], EAST)
    while g.rules_health() > 90:
        g.game_step(0)
    press(g, B)
    assert g.rules_health() == 100


def test_health_and_death(g):
    arena(g, ["#####", "#@.A#", "#b###", "#####"], EAST)
    bitten = []
    for k in range(3000):
        g.game_step(0)
        if g.rules_hurt_age() == 0:
            bitten.append(k)
        if g.rules_dead_timer():
            break
    assert g.rules_health() == 0 and g.rules_took_damage()
    assert len(bitten) == 10 and all(b - a == tuning("BUG_ATTACK_EVERY") for a, b in zip(bitten, bitten[1:]))
    frames = g.rules_run_frames()
    steps(g, UP | A, tuning("DEATH_FRAMES") - 1)
    assert g.rules_dead_timer() == 1 and g.rules_px() == cell_centre(1, 1)[0], "no input while dead"
    g.game_step(0)
    assert g.rules_dead_timer() == 0 and g.rules_deaths() == 1 and g.rules_health() == 100
    assert (g.rules_px(), g.rules_py()) == cell_centre(1, 1) and g.rules_angle() == EAST
    assert g.rules_run_frames() == frames + tuning("DEATH_FRAMES"), "the clock keeps running"
    assert g.rules_scene() == SC_PLAY and not g.game_ended() and g.rules_took_damage()


def test_death_restarts_the_level(g):
    arena(g, ["########", "#@.D...#", "#b######", "########"], EAST)
    press(g, B)
    steps(g, 0, 40)
    assert g.rules_door_amount(3, 1) == tuning("DOOR_FRAMES")
    while not g.rules_dead_timer():
        g.game_step(0)
    steps(g, 0, tuning("DEATH_FRAMES"))
    assert g.rules_door_amount(3, 1) == 0 and g.rules_bug_state(0) == BUG_IDLE
    assert (g.rules_bug_x(0), g.rules_bug_y(0)) == cell_centre(1, 2) and g.rules_bug_hp(0) == tuning("BUG_HP")


# ---- Task 3: bugs -----------------------------------------------------------------------------------------------

def overlapping(a, b, r):
    return abs(a[0] - b[0]) < 2 * r and abs(a[1] - b[1]) < 2 * r


def inside_a_wall(g, x, y, r):
    for cx in {(x - r) >> 16, (x + r - 1) >> 16}:
        for cy in {(y - r) >> 16, (y + r - 1) >> 16}:
            c = g.rules_cell(cx, cy)
            walkable = c in (CELL_FLOOR, CELL_SECRET) or (
                c == CELL_DOOR and g.rules_door_amount(cx, cy) == tuning("DOOR_FRAMES"))
            if not walkable:
                return True
    return False


def test_bug_pathing(g):
    """A pack in an open room: they chase, never enter walls, never overlap each other or the player."""
    br, pr = tuning("BUG_RADIUS"), tuning("PLAYER_RADIUS")
    arena(g, ["##########",
              "#b.b.b...#",
              "#........#",
              "#.b...b..#",
              "#........#",
              "#......@.#",
              "##########"], NORTH)
    chased, reached = set(), False
    for _ in range(300):
        g.game_step(0)
        if g.rules_dead_timer():
            break
        bs = bugs(g)
        for i, b in enumerate(bs):
            assert not inside_a_wall(g, b[0], b[1], br), "bug %d is inside a wall at %s" % (i, b[:2])
            assert not overlapping(b, (g.rules_px(), g.rules_py()), (br + pr) // 2), "bug %d is on the player" % i
            if b[2] == BUG_CHASE:
                chased.add(i)
            for j in range(i):
                assert not overlapping(b, bs[j], br), "bugs %d and %d overlap" % (i, j)
            if max(abs(b[0] - g.rules_px()), abs(b[1] - g.rules_py())) <= tuning("BUG_REACH"):
                reached = True
    assert len(chased) >= 4 and reached


def test_bug_follows_round_a_corner(g):
    arena(g, ["#########",
              "#b......#",
              "#######.#",
              "#######.#",
              "#######@#",
              "#########"], NORTH)
    steps(g, 0, 20)
    assert g.rules_bug_state(0) == BUG_IDLE
    steps(g, UP, 24)                                             # up to row 1: in sight along the corridor
    steps(g, 0, 8)
    assert g.rules_bug_state(0) == BUG_CHASE
    steps(g, DOWN, 24)                                           # back round the corner, out of sight
    for k in range(400):
        g.game_step(0)
        x, y = g.rules_bug_x(0), g.rules_bug_y(0)
        assert not inside_a_wall(g, x, y, tuning("BUG_RADIUS"))
        if max(abs(x - g.rules_px()), abs(y - g.rules_py())) <= tuning("BUG_REACH"):
            break
    else:
        raise AssertionError("the bug never found its way round the corner")


def test_bugs_give_up_after_losing_sight(g):
    arena(g, ["################",
              "#....@D.....b..#",
              "################"], EAST)
    steps(g, 0, 10)
    assert g.rules_bug_state(0) == BUG_IDLE, "a closed door hides the player"
    press(g, B)
    steps(g, 0, tuning("DOOR_FRAMES") + 4)
    assert g.rules_bug_state(0) == BUG_CHASE
    press(g, B)                                                  # shut it in the bug's face
    steps(g, 0, tuning("DOOR_FRAMES"))
    assert g.rules_door_amount(6, 1) == 0
    steps(g, 0, tuning("BUG_GIVE_UP") - 20 - tuning("DOOR_FRAMES") - 2)
    assert g.rules_bug_state(0) == BUG_CHASE and not g.rules_bug_sees(0)
    steps(g, 0, 30)
    assert g.rules_bug_state(0) == BUG_IDLE, "a bug that lost sight must give up"


def test_bug_does_not_walk_through_the_player(g):
    arena(g, ["########", "#@....b#", "########"], EAST)
    for _ in range(300):
        g.game_step(0)
        assert g.rules_bug_x(0) - g.rules_px() >= tuning("PLAYER_RADIUS") + tuning("BUG_RADIUS")
    assert g.rules_bug_x(0) - g.rules_px() <= tuning("BUG_REACH")


def test_the_player_does_not_walk_through_a_bug(g):
    arena(g, ["########", "#@....b#", "########"], EAST)
    for _ in range(200):
        g.game_step(UP)
        assert g.rules_bug_x(0) - g.rules_px() >= tuning("PLAYER_RADIUS") + tuning("BUG_RADIUS")


# ---- Task 3: secret room and trophies ----------------------------------------------------------------------------

def test_secret_wall_slides_and_latches_the_trophy(g):
    arena(g, ["######", "#@.P.#", "####s#", "######"], EAST)
    press(g, B)
    assert g.rules_door_amount(3, 1) == 2
    steps(g, 0, tuning("PUSH_FRAMES"))
    assert g.rules_cell(3, 1) == CELL_FLOOR
    steps(g, UP, 24)
    face(g, SOUTH)
    assert not g.rules_secret_found() and not g.rules_trophies() & 8
    steps(g, UP, 20)
    assert g.rules_secret_found() and g.rules_trophies() & 8 and g.rules_msg() == MSG_SECRET


def test_all_bugs_trophy_latches_on_the_last_squash(g):
    arena(g, ["##########", "#@.....b.#", "##########"], EAST)
    steps(g, A, tuning("FIRE_COOLDOWN") + 1)
    assert g.rules_trophies() == 1 and g.rules_msg() == MSG_ALL_BUGS


def test_finish_trophies_no_damage_and_under_time(g):
    arena(g, ["##X##", "#.@K#", "#####"], NORTH)
    face(g, EAST)
    press(g, B)
    assert g.rules_has_key()
    face(g, NORTH)
    press(g, B)
    assert g.rules_finished() and g.rules_trophies() == 1 | 2 | 4, "no bugs in the arena: all squashed"


def test_finish_without_the_time_and_damage_trophies(g):
    arena(g, ["##X###", "#.@K.#", "##b###", "######"], NORTH)
    while not g.rules_took_damage():
        g.game_step(0)
    face(g, EAST)
    press(g, B)                                  # the keycard; the bug keeps biting: shoot it
    face(g, SOUTH)
    while g.rules_bugs_left():
        g.game_step(A)
        g.game_step(0)
    while g.rules_run_frames() <= tuning("UNDER_FRAMES"):
        g.game_step(0)
    face(g, NORTH)
    press(g, B)
    assert g.rules_finished() and g.rules_run_frames() > tuning("UNDER_FRAMES")
    assert g.rules_trophies() == 1, "all bugs only: damage taken, over 3:00"


def test_a_held_a_from_the_how_to_card_does_not_fire(g):
    g.game_step(START)
    g.game_step(0)
    g.game_step(A)                               # leaves the how-to card
    steps(g, A, 30)                              # still held
    assert g.rules_shot_age() == 255 and g.rules_fire_cooldown() == 0
    g.game_step(0)
    g.game_step(A)
    assert g.rules_shot_age() == 0


def test_score_is_bugs_squashed_and_time_is_play_frames(g):
    arena(g, ["##X####", "#.@..b#", "#######"], EAST)
    steps(g, A, tuning("FIRE_COOLDOWN") + 1)
    assert g.rules_squashed() == 1
    res = result(g)
    assert res["score"] == 1 and res["time_frames"] == g.rules_run_frames()


def test_ghost_flags_play_and_units(g):
    gh = T.Ghost()
    g.game_ghost(ctypes.byref(gh))
    assert gh.flags & 0x80 == 0
    press(g, START)
    press(g, START)
    g.game_ghost(ctypes.byref(gh))
    assert gh.flags & 0x80 and (gh.x, gh.y) == (g.rules_px() >> 12, g.rules_py() >> 12)
    assert gh.angle == g.rules_angle() >> 2


def test_game_init_resets_everything(g, lib):
    """arcade_replay calls game_init twice in one process: a second init must equal a fresh process's first."""
    import subprocess
    import sys
    code = ("import ctypes; so = ctypes.CDLL(%r); so.game_init(0); so.game_hash.restype = ctypes.c_uint32; "
            "print(so.game_hash())" % lib._name)
    fresh = int(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout)
    arena(g, ["#####", "#@.A#", "#b###", "#####"], EAST)
    steps(g, A | UP, 300)
    for k in [START, 0, START, 0] + [UP | A | B] * 400:
        g.game_step(k)
    g.game_init(0)
    assert g.game_hash() == fresh
    assert T.pc_hashes(g, [START, 0, START, 0] + [UP] * 50) == T.pc_hashes(g, [START, 0, START, 0] + [UP] * 50)


def test_the_hash_follows_the_state(g):
    keys = [START, 0, START, 0] + [UP] * 10
    assert T.pc_hashes(g, keys) == T.pc_hashes(g, keys)
    assert T.pc_hashes(g, keys)[-1] != T.pc_hashes(g, keys[:-1] + [DOWN])[-1]
    assert T.pc_hashes(g, keys + [0])[-1] != T.pc_hashes(g, keys + [A])[-1]

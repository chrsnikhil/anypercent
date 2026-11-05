import random

from conftest import (tuning, A, B, DOWN, LEFT, RIGHT, SC_CLEAR, SC_DEMODAY, SC_HOWTO, SC_MISSED, SC_NIGHTFALL, SC_PLAY,
                      SC_TITLE, SC_WALKOUT, START, UP, Game)

HINT_NONE, HINT_TAKE, HINT_GIVE = 0, 1, 2
TARGET_COUNTER, TARGET_DEV = 0, 1


def start_at(game, scene, name="START"):
    game.start()
    game.place(scene["spots"][name + "_X"], scene["spots"][name + "_Y"])


def deliver(game, scene, k):
    game.place(scene["spots"]["COUNTER_X"], scene["spots"]["COUNTER_Y"])
    game.step(A)
    game.step(0)
    game.place(scene["spots"]["HAND%d_X" % k], scene["spots"]["HAND%d_Y" % k])
    game.step(A)
    game.step(0)


def test_start_opens_the_how_to_card_and_a_begins_the_run(game):
    assert game.scene() == SC_TITLE
    game.step(START)
    assert game.scene() == SC_HOWTO
    game.step(0)
    game.step(A)
    assert game.scene() == SC_PLAY
    game.step(0)
    assert game.run_frames() == 1 and game.progress() == 0


def test_start_held_from_the_title_stops_on_the_how_to_card(game):
    game.step(START, 10)
    assert game.scene() == SC_HOWTO
    game.step(0)
    game.step(START)
    assert game.scene() == SC_PLAY and not game.paused()


def test_walking_is_one_and_a_half_pixels_across_and_three_quarters_up(game, scene):
    start_at(game, scene)
    qx, qy = game.qx(), game.qy()
    game.step(LEFT, 10)
    assert game.qx() == qx - 60 and game.moving() and game.facing() == 6
    game.step(UP, 10)
    assert game.qy() == qy - 30 and game.facing() == 4


def test_diagonals_move_both_ways_and_face_between(game, scene):
    start_at(game, scene)
    qx, qy = game.qx(), game.qy()
    game.step(RIGHT | UP)
    assert (game.qx(), game.qy(), game.facing()) == (qx + 6, qy - 3, 3)


def test_walls_stop_you(game, scene):
    start_at(game, scene)
    game.step(LEFT, 400)
    x = game.px()
    game.step(LEFT, 10)
    assert game.px() == x and game.walkable(x - 3, game.py()) and game.walkable(x + 3, game.py())


def test_dash_then_cooldown(game, scene):
    start_at(game, scene)
    qx = game.qx()
    game.step(LEFT | B)
    game.step(LEFT, 9)
    assert game.qx() == qx - 140 and game.dash_cool() == 60
    qx = game.qx()
    game.step(LEFT)
    game.step(LEFT | B)
    assert game.qx() == qx - 12


def test_a_dash_without_a_direction_goes_the_way_you_face(game, scene):
    start_at(game, scene)
    game.step(RIGHT)
    qx = game.qx()
    game.step(B)
    assert game.qx() == qx + 14


def test_chai_from_the_counter_to_a_dev(game, scene):
    start_at(game, scene, "HAND2")
    game.so.rules_debug_energy(2, 0)
    game.step(A)
    assert game.carrying() == 0 and game.energy(2) == 0
    game.step(0)
    game.place(scene["spots"]["COUNTER_X"], scene["spots"]["COUNTER_Y"])
    game.step(A)
    assert game.carrying() == 1
    game.step(0)
    game.step(A)
    assert game.carrying() == 1
    game.step(0)
    game.place(scene["spots"]["HAND2_X"], scene["spots"]["HAND2_Y"])
    game.step(A)
    assert game.carrying() == 0 and game.energy(2) == 255


def test_the_clock_waits_for_the_first_chai(game, scene):
    game.start()
    game.step(0, 900)
    assert game.hour() == 0 and game.hour_frames() == 0 and not game.clock_running()
    assert game.run_frames() == 901                                   # the speedrun timer still runs
    deliver(game, scene, 0)
    assert game.clock_running()
    game.step(0, 450)
    assert game.hour() == 1


def test_the_hint_says_what_a_does(game, scene):
    start_at(game, scene)
    assert game.hint() == HINT_NONE
    game.place(scene["spots"]["COUNTER_X"], scene["spots"]["COUNTER_Y"])
    assert game.hint() == HINT_TAKE
    game.step(A)
    game.step(0)
    assert game.hint() == HINT_NONE                                   # holding a cup at the counter
    game.place(scene["spots"]["HAND1_X"], scene["spots"]["HAND1_Y"])
    assert game.hint() == HINT_GIVE and game.hint_dev() == 1


def test_the_hint_matches_what_a_does(game, scene):
    """Wherever the hint promises something, pressing A does exactly that; where it promises nothing, A does
    nothing."""
    game.start()
    rnd = random.Random(11)
    for _ in range(400):
        x = rnd.randint(0, scene["walk_w"] - 1) * 4 + 2
        y = rnd.randint(0, scene["walk_h"] - 1) * 4 + 2
        if not (game.walkable(x - 3, y) and game.walkable(x + 3, y)):
            continue
        game.place(x, y)
        game.step(0)
        hint, dev, carrying = game.hint(), game.hint_dev(), game.carrying()
        game.step(A)
        if hint == HINT_TAKE:
            assert game.carrying() == 1
        elif hint == HINT_GIVE:
            assert game.carrying() == 0 and game.energy(dev) == 255
        else:
            assert game.carrying() == carrying
        game.step(0)


def test_the_target_is_the_counter_then_the_most_tired_dev(game, scene):
    game.start()
    for i, e in enumerate((90, 30, 30)):
        game.so.rules_debug_energy(i, e)
    assert game.target() == TARGET_COUNTER
    game.place(scene["spots"]["COUNTER_X"], scene["spots"]["COUNTER_Y"])
    game.step(A)
    game.step(0)
    assert game.target() == TARGET_DEV + 1                            # ties go to the lower index


def test_energy_drains_and_a_tired_dev_stops_typing(game):
    game.start()
    for i in range(3):
        game.so.rules_debug_energy(i, 1)
    game.step(0, 8)
    assert [game.energy(i) for i in range(3)] == [0, 0, 0]
    p = game.progress()
    game.step(0, 200)
    assert game.progress() == p


def test_working_devs_fill_the_bar(game):
    game.start()
    for i in range(3):
        game.so.rules_debug_energy(i, 255)
    p = game.progress()
    game.step(0, tuning("TYPE_FRAMES"))
    assert game.progress() == p + 3


def test_act_one_ends_in_nightfall_then_act_two(game):
    game.start()
    game.so.rules_debug_progress(399)
    for i in range(3):
        game.so.rules_debug_energy(i, 255)
    while game.scene() == SC_PLAY:
        game.step(0)
    assert game.scene() == SC_NIGHTFALL and game.split(1) == game.run_frames()
    hour, frames = game.hour_frames(), game.run_frames()
    game.step(A | START | LEFT, 119)                                  # buttons do nothing; the clock pauses
    assert game.scene() == SC_NIGHTFALL and game.hour_frames() == hour and game.run_frames() == frames + 119
    game.step(0)
    assert game.scene() == SC_PLAY and game.act() == 2 and game.last_commit() == game.progress()


def test_missing_the_deadline(game):
    game.start()
    game.so.rules_debug_clock(35, 449)
    game.step(0)
    assert game.scene() == SC_MISSED and game.hour() == 36


def test_clear_beats_the_deadline_on_the_same_frame(game):
    game.start()
    game.so.rules_debug_progress(400)
    game.so.rules_debug_clock(35, 449)
    game.step(0)
    assert game.scene() == SC_NIGHTFALL                               # reaching 400 leads into nightfall


def test_pause_freezes_everything(game, scene):
    start_at(game, scene)
    game.step(START)
    assert game.paused()
    frozen = (game.run_frames(), game.hour_frames(), game.qx(), game.progress(), game.energy(0))
    game.step(LEFT, 60)
    assert (game.run_frames(), game.hour_frames(), game.qx(), game.progress(), game.energy(0)) == frozen
    game.step(0)
    game.step(START)
    assert not game.paused()
    qx = game.qx()
    game.step(LEFT)
    assert game.qx() == qx - 6


def test_random_play_never_leaves_the_floor(game):
    rnd = random.Random(7)
    game.start()
    dirs = [LEFT, RIGHT, UP, DOWN, LEFT | UP, RIGHT | DOWN, LEFT | DOWN, RIGHT | UP]
    for _ in range(6000):
        game.step(rnd.choice(dirs) | rnd.choice([0, 0, 0, B, A]))
        if game.scene() != SC_PLAY:
            break
        x, y = game.px(), game.py()
        assert game.walkable(x - 3, y) and game.walkable(x, y) and game.walkable(x + 3, y), (x, y)


def test_same_inputs_same_result_and_hidden_state_changes_the_hash(lib):
    rnd = random.Random(1)
    script = [rnd.choice([0, LEFT, RIGHT, UP, DOWN, A, B, LEFT | B, RIGHT | UP]) for _ in range(3000)]

    def run(inputs):
        g = Game(lib)
        g.start()
        for b in inputs:
            g.step(b)
        return g.hash(), g.run_frames(), g.progress()
    first = run(script)
    assert run(script) == first
    changed = list(script)
    changed[100] = RIGHT if script[100] != RIGHT else LEFT
    assert run(changed)[0] != first[0]

    def last_hash(final):                                             # Game objects share one C state: run in turn
        g = Game(lib)
        g.start()
        g.step(0, 3)
        g.step(final)
        return g.hash(), g.carrying(), g.qx(), g.qy()
    pressed, idle = last_hash(A), last_hash(0)                        # A away from everything: only prev differs
    assert pressed[1:] == idle[1:] and pressed[0] != idle[0]          # held buttons (prev) are hashed


HINT_STOMP, HINT_RESET, HINT_PAY, HINT_COMMIT = 3, 4, 5, 6
TARGET_ROUTER, TARGET_DOOR, TARGET_SHELF, TARGET_BUG = 4, 5, 6, 8


def act2(game, progress=500):
    game.start()
    game.so.rules_debug_act2(progress)


def spot(scene, name):
    return scene["spots"][name + "_X"], scene["spots"][name + "_Y"]


def test_a_bug_spawns_on_schedule_reaches_its_desk_and_freezes_typing(game, scene):
    act2(game)
    game.step(0, 239)
    assert not any(game.bug_on(i) for i in range(6))
    game.step(0)
    assert game.bug_on(0) and game.bug_desk(0) == 1 and (game.bug_x(0), game.bug_y(0)) == spot(scene, "BUGSPAWN0")
    for _ in range(2000):
        game.so.rules_debug_energy(1, 255)
        game.step(0)
        if game.bug_sitting(0):
            break
    assert game.bug_sitting(0) and (game.bug_x(0), game.bug_y(0)) == spot(scene, "BUGDESK1")
    p = game.progress()
    for i in range(3):
        game.so.rules_debug_energy(i, 0 if i != 1 else 255)
    game.step(0, 44)
    assert game.progress() == p                                       # Priya is frozen, the others are out of energy


def test_stomping_a_sitting_bug_from_the_desk(game, scene):
    act2(game)
    game.so.rules_debug_act_frames(239)
    game.step(0)
    while not game.bug_sitting(0):
        game.step(0)
    game.place(*spot(scene, "HAND1"))
    assert game.hint() == HINT_STOMP and game.hint_arg() == 0
    game.step(A)
    assert not game.bug_on(0)


def test_stomp_beats_giving_chai_at_the_same_desk(game, scene):
    act2(game)
    game.so.rules_debug_act_frames(239)
    game.step(0)
    while not game.bug_sitting(0):
        game.step(0)
    game.place(*spot(scene, "COUNTER"))
    game.step(A)
    game.step(0)
    assert game.carrying() == 1
    game.place(*spot(scene, "HAND1"))
    game.step(A)
    assert not game.bug_on(0) and game.carrying() == 1                # stomped first, chai still in hand


def test_router_rolls_back_to_the_last_commit(game, scene):
    act2(game, 520)
    game.so.rules_debug_progress(610)
    game.so.rules_debug_act_frames(tuning("ROUTER_FRIES")[0] - 1)
    game.step(0)
    assert game.router_fried() and game.progress() == 520 and game.message() == 3
    p = game.progress()
    for i in range(3):
        game.so.rules_debug_energy(i, 255)
    game.step(0, 44)
    assert game.progress() == p                                       # nobody types while it is down
    game.place(*spot(scene, "ROUTER"))
    assert game.hint() == HINT_RESET and game.target() == TARGET_ROUTER
    game.step(A)
    assert not game.router_fried()


def test_commit_needs_thirty_held_frames_and_fires_once(game, scene):
    act2(game, 500)
    game.so.rules_debug_progress(580)
    game.place(*spot(scene, "SHELF"))
    assert game.hint() == HINT_COMMIT
    game.step(A, 29)
    assert game.last_commit() == 500
    game.step(0)
    game.step(A, 29)
    assert game.last_commit() == 500                                  # a release restarts the count
    game.step(A)
    assert game.last_commit() >= 580 and game.message() == 1
    first = game.last_commit()
    game.so.rules_debug_progress(700)
    game.step(A, 60)
    assert game.last_commit() == first                                # still held: no second commit
    game.step(0)
    game.step(A, 30)
    assert game.last_commit() >= 700                                  # the devs keep typing while A is held


def test_the_shelf_offers_a_commit_only_after_five_percent_of_new_progress(game, scene):
    act2(game, 500)
    game.place(*spot(scene, "SHELF"))
    game.so.rules_debug_progress(549)
    assert game.hint() != HINT_COMMIT                                 # 49 points since the last commit: nothing
    game.step(A, 30)
    assert game.last_commit() == 500
    game.so.rules_debug_progress(550)
    assert game.hint() == HINT_COMMIT


def test_pizza_arrives_once_and_paying_fills_everyone(game, scene):
    act2(game)
    game.so.rules_debug_act_frames(tuning("PIZZA_FRAME") - 1)
    game.step(0)
    assert game.pizza() == 1 and game.target() == TARGET_DOOR
    for i in range(3):
        game.so.rules_debug_energy(i, 10)
    game.place(*spot(scene, "DOOR"))
    assert game.hint() == HINT_PAY
    game.step(A)
    assert game.pizza() == 2 and [game.energy(i) for i in range(3)] == [255] * 3 and game.message() == 2


def test_a_bug_beyond_six_is_skipped(game):
    act2(game)
    so = game.so
    sched = tuning("BUG_SCHEDULE")
    sched = [sched[k:k + 3] for k in range(0, len(sched), 3)]
    assert sched[6][2] != sched[7][2]                                 # the 7th and 8th bugs go to different desks
    for frame, _, _ in sched[:6]:
        so.rules_debug_act_frames(frame - 1)
        game.step(0)
    assert sum(1 for i in range(6) if game.bug_on(i)) == 6
    before = (so.rules_last_commit(), so.rules_router_fried(), so.rules_pizza(), so.rules_message())
    so.rules_debug_act_frames(sched[6][0] - 1)                        # the 7th is due with no free slot
    game.step(0)
    assert (so.rules_last_commit(), so.rules_router_fried(), so.rules_pizza(), so.rules_message()) == before
    so.rules_debug_place(so.rules_bug_x(0), so.rules_bug_y(0))        # free slot 0: stomp that bug
    game.step(A)
    game.step(0)
    assert not game.bug_on(0)
    while so.rules_act_frames() < sched[7][0]:                        # walk there: the debug setter would re-sync the queue
        game.step(0)
    assert game.bug_on(0) and so.rules_bug_desk(0) == sched[7][2]     # the 8th took the slot, not the skipped 7th


def test_target_order_in_act_two(game, scene):
    act2(game, 500)
    assert game.target() == 0                                         # nothing to do: the counter
    game.so.rules_debug_progress(560)
    assert game.target() == TARGET_SHELF
    game.so.rules_debug_act_frames(239)
    game.step(0)
    assert game.target() == TARGET_BUG + 0
    game.so.rules_debug_act_frames(tuning("ROUTER_FRIES")[0] - 1)
    game.step(0)
    assert game.target() == TARGET_ROUTER


def test_act_two_ends_at_eighty_percent_with_its_split(game):
    act2(game, 790)
    for i in range(3):
        game.so.rules_debug_energy(i, 255)
    for _ in range(300):
        game.step(0)
        if game.scene() != SC_PLAY:
            break
    assert game.scene() == SC_DEMODAY and game.split(2) == game.run_frames() - game.split(1)


def test_the_hint_matches_what_a_does_in_act_two(game, scene):
    rnd = random.Random(12)
    act2(game, 600)
    game.so.rules_debug_act_frames(tuning("ROUTER_FRIES")[0] - 1)
    game.step(0)                                                      # the router is down
    game.so.rules_debug_act_frames(tuning("PIZZA_FRAME") - 1)
    game.step(0)                                                      # the pizza is waiting
    names = ["COUNTER", "HAND0", "HAND1", "HAND2", "SHELF", "DOOR", "ROUTER"]
    for _ in range(300):
        x, y = spot(scene, rnd.choice(names))
        x, y = x + rnd.randint(-20, 20), y + rnd.randint(-10, 10)
        if not (game.walkable(x - 3, y) and game.walkable(x, y) and game.walkable(x + 3, y)):
            continue
        game.place(x, y)
        game.step(0)
        hint, arg = game.hint(), game.hint_arg()
        before = (game.router_fried(), game.pizza(), game.carrying(), game.last_commit())
        game.step(A)
        after = (game.router_fried(), game.pizza(), game.carrying(), game.last_commit())
        if hint == HINT_RESET:
            assert after[0] == 0
        elif hint == HINT_PAY:
            assert after[1] == 2
        elif hint == 1:
            assert after[2] == 1
        elif hint == 2:
            assert after[2] == 0 and game.energy(arg) == 255
        elif hint == HINT_STOMP:
            assert not game.bug_on(arg)
        else:                                                         # nothing, or COMMIT: one press does nothing
            assert after == before or hint == HINT_COMMIT and after[:3] == before[:3]
        game.step(0)


HINT_LAPTOP, HINT_SCAN, HINT_PITCH = 7, 8, 9
TARGET_LAPTOP, TARGET_ORB, TARGET_STAGE = 14, 15, 16
ROOM_OFFICE, ROOM_HALL = 0, 1


def act3(game, room=ROOM_OFFICE):
    game.start()
    game.so.rules_debug_act3(room)


def test_act_two_clear_goes_to_demo_day_then_act_three(game):
    act2(game, 790)
    for i in range(3):
        game.so.rules_debug_energy(i, 255)
    for _ in range(400):
        game.step(0)
        if game.scene() == SC_DEMODAY:
            break
    assert game.scene() == SC_DEMODAY and game.split(2) > 0
    hour_frames, run = game.hour_frames(), game.run_frames()
    game.step(A, 60)                                                  # buttons are ignored, the clock pauses
    assert game.hour_frames() == hour_frames and game.run_frames() == run + 60
    game.step(0, 60)
    assert game.scene() == SC_PLAY and game.act() == 3 and game.room() == ROOM_OFFICE
    assert game.carrying() == 0 and not any(game.bug_on(i) for i in range(6)) and not game.router_fried()


def test_take_the_laptop_at_arjuns_desk(game, scene):
    act3(game)
    assert game.target() == TARGET_LAPTOP
    game.place(*spot(scene, "HAND0"))
    assert game.hint() == HINT_LAPTOP
    game.step(A)
    assert game.carrying() == 2 and game.target() == TARGET_DOOR


def test_the_laptop_is_slow_and_stops_the_dash(game, scene):
    act3(game)
    game.place(*spot(scene, "HAND0"))
    game.step(A)
    game.step(0)
    game.place(*spot(scene, "START"))
    x, y = game.qx(), game.qy()
    game.step(RIGHT, 4)
    game.step(DOWN, 4)
    assert (game.qx() - x, game.qy() - y) == (16, 8)
    game.step(B)
    assert game.dash_cool() == 0
    x = game.qx()
    game.step(RIGHT)
    assert game.qx() - x == 4


def test_act_three_turns_off_chai_typing_and_act_two(game, scene):
    act3(game)
    for i in range(3):
        game.so.rules_debug_energy(i, 255)
    p = game.progress()
    game.step(0, 300)
    assert game.progress() == p
    for name in ("COUNTER", "SHELF", "ROUTER", "HAND1"):
        game.place(*spot(scene, name))
        assert game.hint() == 0, name


def test_walking_out_the_door_moves_to_the_hall(game, scene, hall):
    act3(game)
    game.place(*spot(scene, "HAND0"))
    game.step(A)
    game.place(*spot(scene, "DOOR"))
    game.step(0)
    assert game.scene() == SC_WALKOUT and game.room() == ROOM_OFFICE
    game.step(0, 30)
    assert game.room() == ROOM_HALL and (game.px(), game.py()) == spot(hall, "START")
    game.step(0, 30)
    assert game.scene() == SC_PLAY and game.room() == ROOM_HALL and game.carrying() == 2


def test_the_door_does_nothing_without_the_laptop(game, scene):
    act3(game)
    game.place(*spot(scene, "DOOR"))
    game.step(0, 5)
    assert game.scene() == SC_PLAY and game.room() == ROOM_OFFICE


def test_the_gate_blocks_until_the_scan(game, hall):
    act3(game, ROOM_HALL)
    gx, gy = spot(hall, "GATE")
    assert game.walkable(gx, gy) == 0
    game.so.rules_debug_verified(1)
    assert game.walkable(gx, gy) == 1


def test_walking_into_the_closed_gate_stops_you(game, hall):
    act3(game, ROOM_HALL)
    gx, gy = spot(hall, "GATE")
    game.place(gx - 20, gy)
    game.step(RIGHT, 40)
    assert game.px() < gx - 12


def test_scanning_at_the_orb_verifies(game, hall):
    act3(game, ROOM_HALL)
    assert game.target() == TARGET_ORB
    game.place(*spot(hall, "ORB"))
    assert game.hint() == HINT_SCAN
    game.step(A)
    assert game.verified() == 1 and game.message() == 4 and game.target() == TARGET_STAGE
    game.step(0)
    assert game.hint() == 0                                           # verified once is enough


def test_the_crowd_walks_its_paths(game, hall):
    act3(game, ROOM_HALL)
    assert game.crowd_count() == 6
    path = hall["crowd"][0]
    assert (game.crowd_x(0), game.crowd_y(0)) == tuple(path[0])
    game.step(0, 8)                                                   # 0.5 px per frame on each axis
    x, y = game.crowd_x(0), game.crowd_y(0)
    assert abs(x - path[0][0]) <= 4 and abs(y - path[0][1]) <= 4 and (x, y) != tuple(path[0])
    for _ in range(4000):
        game.step(0)
        if (game.crowd_x(0), game.crowd_y(0)) == tuple(path[1]):
            break
    assert (game.crowd_x(0), game.crowd_y(0)) == tuple(path[1])
    while game.crowd_paused(0):                                       # a pause at the waypoint
        game.step(0)
    game.step(0, 8)
    assert (game.crowd_x(0), game.crowd_y(0)) != tuple(path[1])       # and on toward the next waypoint


def test_a_bump_stuns_then_protects(game):
    act3(game, ROOM_HALL)
    game.place(game.crowd_x(3), game.crowd_y(3))
    game.step(0)
    assert game.stun() > 0
    x = game.qx()
    game.step(RIGHT, 29)
    assert game.qx() == x                                             # stunned: no moving
    game.step(0, 5)
    assert game.stun() == 0 and game.immune() > 0
    game.place(game.crowd_x(3), game.crowd_y(3))
    game.step(0)
    assert game.stun() == 0                                           # immune: no second stun


def test_an_attendee_walking_into_you_stuns_you(game, hall):
    act3(game, ROOM_HALL)
    path = hall["crowd"][0]
    ax = path[0][0] + (path[1][0] - path[0][0]) // 2                  # halfway along attendee 0's first leg
    ay = path[0][1] + (path[1][1] - path[0][1]) // 2
    game.place(ax, ay)
    for _ in range(3000):
        game.step(0)
        if game.stun():
            break
    assert game.stun() > 0


PITCH = [A, RIGHT, B, UP, A]


def at_stage(game, hall):
    act3(game, ROOM_HALL)
    game.so.rules_debug_verified(1)
    game.place(*spot(hall, "STAGE"))
    assert game.hint() == HINT_PITCH
    game.step(A)
    game.step(0)
    assert game.slide() == 1


def test_the_pitch_flips_slides_on_the_right_buttons(game, hall):
    at_stage(game, hall)
    p = game.progress()
    for k, key in enumerate(PITCH[:4]):
        assert game.pitch_key() == key
        game.step(key)
        game.step(0)
        assert game.slide() == k + 2 and game.progress() == p + 40 * (k + 1)
    run = game.run_frames()
    game.step(A)
    assert game.scene() == SC_CLEAR and game.progress() == 1000 and game.clear_frames() == 0
    assert game.run_frames() == run + 1
    game.step(0, 50)
    assert game.run_frames() == run + 1                               # the timer stopped on the last press


def test_a_wrong_press_stumbles(game, hall):
    at_stage(game, hall)
    game.step(B)
    assert game.stumble() == 30 and game.message() == 5 and game.slide() == 1
    game.step(0)
    game.step(A)                                                      # ignored while stumbling
    assert game.slide() == 1
    game.step(0, 30)
    game.step(A)
    assert game.slide() == 2


def test_holding_a_button_counts_once(game, hall):
    at_stage(game, hall)
    game.step(A, 20)                                                  # slide 1 passes on the first frame only
    assert game.slide() == 2 and game.stumble() == 0


def test_two_buttons_at_once_is_a_stumble(game, hall):
    at_stage(game, hall)
    game.step(A)
    game.step(0)
    game.step(A | RIGHT)                                              # slide 2 wants Right alone
    assert game.slide() == 2 and game.stumble() > 0


def test_pause_freezes_the_pitch_and_the_stun(game, hall):
    at_stage(game, hall)
    game.step(B)
    s = game.stumble()
    game.step(START)
    game.step(0, 40)
    assert game.paused() and game.stumble() == s
    game.step(START)
    game.step(0)
    assert not game.paused() and game.stumble() == s - 1


def test_the_results_wait_before_start(game, hall):
    at_stage(game, hall)
    for key in PITCH:
        game.step(key)
        game.step(0)
    assert game.scene() == SC_CLEAR
    game.step(START)
    game.step(0)
    assert game.scene() == SC_CLEAR                                   # SHIPPED! holds for 120 frames
    game.step(0, 120)
    game.step(START)
    assert game.scene() == SC_TITLE


def test_the_deadline_still_ends_act_three(game):
    act3(game, ROOM_HALL)
    game.so.rules_debug_clock(35, 449)
    game.step(0)
    assert game.scene() == SC_MISSED


def test_a_new_run_after_shipping_starts_clean(game, hall):
    at_stage(game, hall)
    for key in PITCH:
        game.step(key)
        game.step(0)
    game.step(0, 125)
    game.step(START)
    game.step(0)
    game.start()
    assert (game.scene(), game.act(), game.room(), game.verified(), game.slide(), game.carrying()) == (SC_PLAY, 1, 0, 0, 0, 0)
    assert game.split(1) == game.split(2) == game.split(3) == 0 and game.crowd_count() == 0


def walk_to_waypoint(game, k, n=1):
    """Step until attendee k has reached n more waypoints (it pauses on arriving)."""
    reached = 0
    was = game.crowd_paused(k)
    for _ in range(6000):
        game.step(0)
        now = game.crowd_paused(k)
        if now and not was:
            reached += 1
            if reached == n:
                return
        was = now
    raise AssertionError("attendee %d never paused" % k)


def test_attendees_pause_at_waypoints(game, hall):
    act3(game, ROOM_HALL)
    game.so.rules_debug_verified(1)
    game.place(20, 20)                                                # out of everyone's way
    walk_to_waypoint(game, 0)
    x, y, frames = game.crowd_x(0), game.crowd_y(0), 0
    while game.crowd_paused(0):
        assert (game.crowd_x(0), game.crowd_y(0)) == (x, y) and game.crowd_facing(0) == 0
        game.step(0)
        frames += 1
    assert frames == tuning("CROWD_PAUSE_MIN") + (0 * 37 + 1 * 53) % tuning("CROWD_PAUSE_SPAN")
    assert (x, y) == tuple(hall["crowd"][0][1])


def at_stage_now(game, hall):
    game.so.rules_debug_verified(1)
    game.place(*spot(hall, "STAGE"))
    game.step(A)
    game.step(0)
    assert game.slide() == 1


def test_the_crowd_gathers_for_the_pitch(game, hall):
    act3(game, ROOM_HALL)
    at_stage_now(game, hall)
    game.step(0, 1500)
    for k in range(6):
        assert game.crowd_gathered(k), k
        assert (game.crowd_x(k), game.crowd_y(k)) == spot(hall, "FAN%d" % k) and game.crowd_facing(k) == 3


def test_a_paused_attendee_still_gathers(game, hall):
    act3(game, ROOM_HALL)
    game.place(20, 20)
    walk_to_waypoint(game, 2)
    assert game.crowd_paused(2)
    at_stage_now(game, hall)
    game.step(0)
    assert not game.crowd_paused(2)                                   # the pause is dropped


def test_gathering_never_stuns_the_pitcher(game, hall):
    act3(game, ROOM_HALL)
    at_stage_now(game, hall)
    game.place(*spot(hall, "FAN3"))                                   # stand where attendee 3 comes to watch
    for _ in range(1500):
        game.step(0)
        assert game.stun() == 0
    assert game.crowd_gathered(3)                                     # it walked right into the player's spot


def test_gathered_and_paused_attendees_stand_still(game, hall):
    act3(game, ROOM_HALL)
    game.place(20, 20)
    walk_to_waypoint(game, 0)
    assert game.crowd_standing(0)
    while game.crowd_paused(0):
        game.step(0)
    game.step(0)
    assert not game.crowd_standing(0)                                 # walking again
    at_stage_now(game, hall)
    game.step(0, 1500)
    assert all(game.crowd_standing(k) for k in range(6))              # gathered: standing, not walking in place


def test_grades(game, hall):
    for hour, grade in ((24, "S"), (25, "A"), (28, "A"), (29, "B"), (32, "B"), (33, "C")):
        game.so.rules_init()                                          # a fresh run each time
        act3(game, ROOM_HALL)
        at_stage_now(game, hall)
        game.so.rules_debug_clock(hour, 0)
        for key in PITCH:
            game.step(key)
            game.step(0)
        assert game.scene() == SC_CLEAR and chr(game.grade()) == grade, hour
    game.so.rules_init()
    act3(game, ROOM_HALL)
    assert game.grade() == 0
    game.so.rules_debug_clock(35, 449)
    game.step(0)
    assert game.scene() == SC_MISSED and chr(game.grade()) == "F"


def test_the_record_codec(lib):
    import ctypes
    buf = (ctypes.c_uint8 * 8)()
    lib.record_encode(ctypes.c_uint32(10890), buf)
    assert bytes(buf)[:2] == b"SI" and lib.record_decode(buf) == 10890
    for blank in (bytes([255]) * 8, bytes([0]) * 8):
        assert lib.record_decode((ctypes.c_uint8 * 8)(*blank)) == 0
    bad = bytearray(bytes(buf))
    bad[3] ^= 1
    assert lib.record_decode((ctypes.c_uint8 * 8)(*bad)) == 0

"""PB, the coach: what it says after a run, from the verified result, the ghost splits and the run history."""
from arca_launcher import coach
from arca_launcher.coach import Line, after_run, compare, fmt_clock, fmt_secs, fmt_time, greeting

PLAY = 0x80


def ghost(points, period=4):
    return {"period": period, "points": points}


def run_x(xs, period=4, title_samples=2):
    """A side-scroller ghost: a couple of title-screen samples, then in-play samples at these x positions."""
    return ghost([(0, 0, 0, 0)] * title_samples + [(x, 50, 0, PLAY) for x in xs], period)


def test_times_read_like_the_games_clock():
    assert fmt_time(4892) == "1:21.53"
    assert fmt_time(59) == "0:00.98"
    assert fmt_secs(94) == "1.57 s"
    assert fmt_secs(6) == "0.10 s"
    assert fmt_clock(2460) == "0:41"


def test_a_new_best_is_celebrated_with_the_margin_and_the_replay():
    res = {"finished": True, "time_frames": 4892, "new_best": True, "vs_best": {"best_frames": 4986, "splits": None}}
    [line] = after_run("Rush Hour", res)
    assert line.mood == "excited" and line.kind == "new_best"
    assert "1:21.53" in line.text and "1.57 s faster" in line.text and "replayed" in line.text


def test_a_first_finish_has_no_margin():
    res = {"finished": True, "time_frames": 4892, "new_best": True, "vs_best": {"best_frames": None, "splits": None}}
    [line] = after_run("Rush Hour", res)
    assert line.kind == "first_finish" and line.mood == "happy"
    assert "Rush Hour" in line.text and "faster" not in line.text


def test_a_slower_run_says_how_far_off_and_where_the_time_went():
    res = {"finished": True, "time_frames": 5000, "new_best": False,
           "vs_best": {"best_frames": 4892, "splits": {"mode": "distance", "progress": 1.0,
                                                        "worst": {"start": 2460, "end": 3120, "loss": 108}}}}
    [line] = after_run("Rush Hour", res)
    assert line.mood == "thinking" and line.kind == "slower"
    assert "1:23.33" in line.text and "1.80 s off your best" in line.text
    assert "between 0:41 and 0:52" in line.text and "1.80 s there" in line.text


def test_a_small_loss_somewhere_is_not_worth_pointing_at():
    res = {"finished": True, "time_frames": 4900, "new_best": False,
           "vs_best": {"best_frames": 4892, "splits": {"mode": "distance", "progress": 1.0,
                                                        "worst": {"start": 600, "end": 900, "loss": 8}}}}
    [line] = after_run("Rush Hour", res)
    assert "between" not in line.text


def test_a_tie_is_called_a_tie():
    res = {"finished": True, "time_frames": 4892, "new_best": False, "vs_best": {"best_frames": 4892, "splits": None}}
    [line] = after_run("Rush Hour", res)
    assert "ties your best" in line.text


def test_an_unfinished_run_says_how_far_it_got():
    res = {"finished": False, "time_frames": 0, "new_best": False,
           "vs_best": {"best_frames": 4892, "splits": {"mode": "distance", "progress": 0.62, "worst": None}}}
    [line] = after_run("Rush Hour", res)
    assert line.kind == "unfinished" and line.mood == "worried"
    assert "62%" in line.text and "logged" in line.text


def test_an_unfinished_run_with_no_best_to_measure_against():
    [line] = after_run("Zip", {"finished": False, "time_frames": 0, "new_best": False})
    assert line.kind == "unfinished" and "%" not in line.text


def test_five_close_finishes_add_a_readiness_page():
    res = {"finished": True, "time_frames": 4900, "new_best": False, "vs_best": {"best_frames": 4892, "splits": None}}
    lines = after_run("Rush Hour", res, history=[4920, 4910, 4925, 4930, 4900])     # all within 30 frames
    assert [x.kind for x in lines] == ["slower", "consistent"]
    assert lines[1].mood == "serious" and "half a second" in lines[1].text


def test_spread_finishes_add_nothing():
    res = {"finished": True, "time_frames": 4900, "new_best": False, "vs_best": {"best_frames": 4892, "splits": None}}
    assert len(after_run("Rush Hour", res, history=[5200, 4910, 4925, 4930, 4900])) == 1
    assert len(after_run("Rush Hour", res, history=[4910, 4900])) == 1


def test_no_result_means_nothing_to_say():
    assert after_run("Rush Hour", None) == []


def test_the_greeting_says_what_pb_will_and_will_not_do():
    g = greeting()
    assert isinstance(g, Line) and g.mood == "happy" and coach.NAME in g.text and "can't press buttons" in g.text


def test_compare_by_distance_finds_the_segment_that_lost_the_most():
    best = run_x(range(0, 800, 10))                       # 80 samples, steady
    slow = list(range(0, 400, 10)) + [400] * 15 + list(range(410, 800, 10))   # x=400 held for 15 samples, not 1
    out = compare(run_x(slow), best)
    assert out["mode"] == "distance" and out["progress"] == 1.0
    w = out["worst"]
    assert w["loss"] == 14 * 4                            # 14 extra samples of period 4
    assert w["start"] <= 400 // 10 * 4 <= w["end"]        # the stall sits inside the reported window


def test_a_finished_run_that_crosses_the_line_short_of_the_best_keeps_its_last_stretch():
    """The finish triggers within a few px, so a finished run can end short of the best's farthest x (Rush Hour: 6304
    against 6307). Its last stretch, from the last mark to its own finish, still counts."""
    best = run_x(range(0, 1001, 10))                                              # ends at x=1000, t=400
    slow = list(range(0, 900, 10)) + [900] * 12 + list(range(910, 1000, 10)) + [997]   # hesitates near the line
    w = compare(run_x(slow), best, finished=True)["worst"]
    assert w == {"start": 88 * 4, "end": 111 * 4, "loss": 11 * 4}                  # mark 7 (x 875) .. its finish


def test_an_unfinished_run_short_of_the_line_has_no_last_stretch():
    best = run_x(range(0, 1001, 10))
    short = list(range(0, 900, 10)) + [900] * 12 + list(range(910, 1000, 10)) + [997]
    assert compare(run_x(short), best)["worst"] is None


def test_compare_measures_progress_of_an_unfinished_run():
    out = compare(run_x(range(0, 500, 10)), run_x(range(0, 1000, 10)))
    assert 0.48 <= out["progress"] <= 0.52


def test_compare_by_room_for_games_that_change_rooms_or_laps():
    def rooms(durations, period=4):
        pts = []
        for room, n in enumerate(durations):
            pts += [(0, 0, 0, PLAY | room)] * n
        return ghost(pts, period)
    out = compare(rooms([20, 20, 30, 20]), rooms([20, 20, 20, 20]))
    assert out["mode"] == "rooms"
    assert out["worst"]["loss"] == 10 * 4
    assert out["worst"]["start"] == 40 * 4 and out["worst"]["end"] == 70 * 4


def test_compare_gives_up_on_a_course_it_cannot_measure():
    wobble = ghost([((i * 37) % 200, 0, 0, PLAY) for i in range(60)])    # x jumps around, one room
    assert compare(wobble, wobble) is None
    assert compare(None, run_x(range(0, 100, 10))) is None

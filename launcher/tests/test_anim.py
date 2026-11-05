from arca_launcher.render.anim import CrossFade, Smooth


def test_smooth_gets_most_of_the_way_in_its_time_and_settles():
    s = Smooth(0, ms=120)
    s.set(100)
    s.update(120)
    assert 90 < s.value < 100
    for _ in range(20):
        s.update(16)
    assert s.value == 100 and s.done


def test_smooth_snap():
    s = Smooth(0, 120)
    s.set(50, snap=True)
    assert s.value == 50 and s.done


def test_crossfade_first_key_shows_at_once_then_fades():
    f = CrossFade(150)
    f.show("a")
    assert f.cur == "a" and f.t == 1.0 and f.prev is None
    f.show("b")
    assert (f.prev, f.cur, f.t) == ("a", "b", 0.0)
    f.update(75)
    assert f.t == 0.5
    f.update(100)
    assert f.t == 1.0 and f.prev is None
    f.show("b")
    assert f.t == 1.0

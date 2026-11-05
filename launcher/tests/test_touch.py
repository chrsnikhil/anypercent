import pygame

from arca_launcher.render import theme
from arca_launcher.touch import TAP_SLOP, Drag, Press, Swipe, Tap, Touch, flick

W1, H1 = theme.W - 1, theme.H - 1


def finger(kind, x, y, finger_id=0, touch_id=7):
    """x, y in logical pixels, sent as SDL sends them: normalised to the renderer's logical size."""
    return pygame.event.Event(kind, touch_id=touch_id, finger_id=finger_id, x=x / W1, y=y / H1, dx=0.0, dy=0.0,
                              pressure=1.0)


def mouse(kind, pos, button=1, touch=False):
    if kind == pygame.MOUSEMOTION:
        return pygame.event.Event(kind, pos=pos, rel=(0, 0), buttons=(1, 0, 0), touch=touch)
    return pygame.event.Event(kind, pos=pos, button=button, touch=touch)


DOWN, MOVE, UP = pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP


def run(t, steps):
    """steps: (ms, event) pairs; returns every gesture produced."""
    out = []
    for ms, e in steps:
        g = t.translate(e, ms)
        if g is not None:
            out.append(g)
    return out


def test_a_finger_landing_is_a_press_at_once_and_lifting_in_place_a_tap():
    t = Touch()
    assert t.translate(finger(DOWN, 300, 200), 0) == Press(300, 200)
    assert t.translate(finger(UP, 303, 198), 90) == Tap(303, 198)


def test_a_finger_that_drifts_within_the_slop_is_still_a_tap():
    t = Touch()
    gs = run(t, [(0, finger(DOWN, 300, 200)), (24, finger(MOVE, 300 + TAP_SLOP, 200)),
                 (48, finger(UP, 300 + TAP_SLOP, 200))])
    assert gs == [Press(300, 200), Tap(300 + TAP_SLOP, 200)]


def test_the_slop_is_small():
    assert 8 <= TAP_SLOP <= 16             # about 1-2 mm on the 5" panel (7.4 px per mm)


def test_moving_past_the_slop_drags_live_along_one_axis_then_swipes_on_release():
    t = Touch()
    gs = run(t, [(0, finger(DOWN, 600, 200)), (24, finger(MOVE, 580, 203)), (48, finger(MOVE, 450, 190)),
                 (72, finger(MOVE, 300, 230)), (300, finger(UP, 300, 230))])
    assert gs[0] == Press(600, 200)
    assert gs[1:4] == [Drag(-20, 0, 600, 200), Drag(-150, 0, 600, 200), Drag(-300, 0, 600, 200)]
    assert isinstance(gs[4], Swipe) and (gs[4].dx, gs[4].dy, gs[4].x0, gs[4].y0) == (-300, 0, 600, 200)


def test_a_vertical_drag_locks_to_y():
    t = Touch()
    gs = run(t, [(0, finger(DOWN, 400, 400)), (24, finger(MOVE, 405, 370)), (48, finger(MOVE, 470, 250)),
                 (400, finger(UP, 470, 250))])
    assert gs[1:3] == [Drag(0, -30, 400, 400), Drag(0, -150, 400, 400)]
    assert (gs[3].dx, gs[3].dy) == (0, -150)


def test_out_and_back_is_not_a_tap():
    t = Touch()
    gs = run(t, [(0, finger(DOWN, 300, 200)), (24, finger(MOVE, 380, 200)), (48, finger(MOVE, 301, 200)),
                 (72, finger(UP, 301, 200))])
    assert not any(isinstance(g, Tap) for g in gs) and isinstance(gs[-1], Swipe) and gs[-1].dx == 1


def test_release_velocity_is_the_recent_motion_and_zero_after_a_pause():
    t = Touch()
    gs = run(t, [(0, finger(DOWN, 600, 200)), (24, finger(MOVE, 570, 200)), (48, finger(MOVE, 530, 200)),
                 (72, finger(MOVE, 480, 200)), (96, finger(UP, 480, 200))])
    assert abs(gs[-1].vx - (-120 / 72)) < 0.01 and gs[-1].vy == 0      # px per ms, over the last 100 ms of motion
    gs = run(t, [(1000, finger(DOWN, 600, 200)), (1024, finger(MOVE, 500, 200)), (1400, finger(UP, 500, 200))])
    assert gs[-1].vx == 0                                                 # held still, then lifted: no flick


def test_flick_turns_release_speed_into_extra_tiles_against_the_finger():
    assert flick(0.0) == 0 and flick(0.3) == 0 and flick(-0.3) == 0
    assert flick(-0.8) == 1 and flick(0.8) == -1                          # finger left: the selection goes right
    assert flick(-2.0) == 2 and flick(2.0) == -2


def test_only_the_first_finger_counts():
    t = Touch()
    gs = run(t, [(0, finger(DOWN, 100, 100, 1)), (10, finger(DOWN, 700, 400, 2)), (20, finger(UP, 700, 400, 2)),
                 (30, finger(UP, 100, 100, 1))])
    assert gs == [Press(100, 100), Tap(100, 100)]


def test_the_mouse_presses_drags_and_taps_too():
    t = Touch()
    assert run(t, [(0, mouse(pygame.MOUSEBUTTONDOWN, (50, 60))), (50, mouse(pygame.MOUSEBUTTONUP, (52, 61)))]) \
        == [Press(50, 60), Tap(52, 61)]
    gs = run(t, [(100, mouse(pygame.MOUSEBUTTONDOWN, (50, 300))), (120, mouse(pygame.MOUSEMOTION, (200, 300))),
                 (140, mouse(pygame.MOUSEBUTTONUP, (400, 300)))])
    assert gs[1] == Drag(150, 0, 50, 300) and (gs[2].dx, gs[2].dy) == (350, 0)
    assert run(t, [(200, mouse(pygame.MOUSEMOTION, (90, 90)))]) == []                 # hovering is nothing
    assert run(t, [(300, mouse(pygame.MOUSEBUTTONDOWN, (50, 60), button=3)),
                   (310, mouse(pygame.MOUSEBUTTONUP, (50, 60), button=3))]) == []


def test_one_touch_is_handled_once_when_sdl_also_sends_it_as_a_mouse():
    t = Touch()
    events = [finger(DOWN, 300, 200), mouse(pygame.MOUSEBUTTONDOWN, (300, 200), touch=True),
              mouse(pygame.MOUSEMOTION, (300, 200), touch=True), finger(UP, 300, 200),
              mouse(pygame.MOUSEBUTTONUP, (300, 200), touch=True)]
    assert run(t, [(i * 10, e) for i, e in enumerate(events)]) == [Press(300, 200), Tap(300, 200)]
    mouse_only = events[1:3] + events[4:]
    assert run(t, [(100 + i * 10, e) for i, e in enumerate(mouse_only)]) == []


def test_touch_events_made_up_from_the_mouse_are_ignored():
    t = Touch()
    assert run(t, [(0, finger(DOWN, 300, 200, touch_id=-1)), (10, finger(UP, 300, 200, touch_id=-1))]) == []


def test_reset_drops_a_touch_in_progress():
    t = Touch()
    t.translate(finger(DOWN, 300, 200), 0)
    t.reset()                                           # a game ran; its finger-up went to the emulator
    assert t.translate(finger(MOVE, 100, 200), 10) is None
    assert t.translate(finger(UP, 300, 200), 20) is None


def test_the_clock_defaults_to_pygames():
    t = Touch()
    assert t.translate(finger(DOWN, 10, 10)) == Press(10, 10)
    assert t.translate(finger(UP, 10, 10)) == Tap(10, 10)

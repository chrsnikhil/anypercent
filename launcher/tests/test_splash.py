from arca_launcher.render import theme
from arca_launcher.render.splash import (DROP_MS, FADE_START, SHINE_MS, SHINE_START, TAG_MS, TAG_START, TOTAL_MS,
                                         SplashTimeline, SplashView)
from conftest import snapshot


def test_the_wordmark_drops_in_and_settles():
    t = SplashTimeline()
    assert t.drop == 0.0                        # starts above the screen
    t.update(DROP_MS / 2)
    assert 0.5 < t.drop < 1.0                   # ease-out: past halfway at half time
    t.update(DROP_MS)
    assert t.drop == 1.0


def test_shine_then_tagline_then_fade_then_done():
    t = SplashTimeline()
    t.update(SHINE_START - 1)
    assert t.shine is None and t.tagline_alpha == 0
    t.update(1 + SHINE_MS / 2)
    assert 0 < t.shine < 1
    t.update(SHINE_MS)
    assert t.shine is None
    t.update(TAG_START + TAG_MS - t.t)
    assert t.tagline_alpha == 255 and t.alpha == 255 and not t.fading
    t.update(FADE_START - t.t + (TOTAL_MS - FADE_START) / 2)
    assert t.fading and 0 < t.alpha < 255 and not t.done
    t.update(TOTAL_MS)
    assert t.done and t.alpha == 0


def test_any_button_jumps_straight_to_the_fade():
    t = SplashTimeline()
    t.update(100)
    t.skip()
    assert t.fading and not t.done and t.drop == 1.0
    t.update(TOTAL_MS - FADE_START)
    assert t.done


def test_a_second_skip_does_not_restart_the_fade():
    t = SplashTimeline()
    t.skip()
    t.update(200)
    before = t.t
    t.skip()
    assert t.t == before


def draw_at(screen, ms):
    t = SplashTimeline()
    t.update(ms)
    view = SplashView(screen.gfx)
    screen.gfx.fill(theme.BG)
    view.draw(t)
    return snapshot(screen.ren, f"splash-{ms}")


def bright_pixels(surf, rect):
    x0, y0, w, h = rect
    return sum(1 for x in range(x0, x0 + w, 3) for y in range(y0, y0 + h, 3) if sum(tuple(surf.get_at((x, y)))[:3]) > 600)


def test_the_wordmark_is_off_screen_at_first_and_centred_once_dropped(screen):
    middle = (theme.W // 2 - 200, theme.H // 2 - 80, 400, 110)
    assert bright_pixels(draw_at(screen, 0), middle) == 0
    assert bright_pixels(draw_at(screen, DROP_MS + 50), middle) > 50
    draw_at(screen, SHINE_START + SHINE_MS // 2)                   # shine mid-sweep, for the snapshot
    draw_at(screen, TAG_START + TAG_MS + 100)                      # settled, with the tagline


def test_art_warms_a_few_textures_at_a_time(screen):
    loaded, rounds = [], 0
    while True:
        n = screen.art.warm(screen.games, budget=2)
        if n == 0:
            break
        loaded.append(n)
        rounds += 1
        assert rounds < 50
    assert max(loaded) <= 2 and sum(loaded) >= len(screen.games) * 2

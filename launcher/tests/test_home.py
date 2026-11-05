from arca_launcher.actions import Action
from arca_launcher.model import Nav
from arca_launcher.render import theme
from arca_launcher.render.chrome import Status
from arca_launcher.render.home import HomeView
from conftest import distinct_colours, snapshot

STATUS = Status("9:41 PM", 72)


def settle(view, nav, frames=40):
    for _ in range(frames):
        view.draw(nav, 16, STATUS)


def test_home_first_game(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    settle(view, nav)
    out = snapshot(screen.ren, "home")
    assert out.get_size() == (800, 480)
    assert distinct_colours(out) > 8
    x = theme.MARGIN + theme.TILE_BIG // 2
    assert tuple(out.get_at((x, theme.ROW_Y - 4)))[:3] == theme.WHITE      # the selection outline


def test_home_long_title_and_buttons_focus(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    for _ in range(3):
        nav.apply(Action.RIGHT)                    # the long-titled game, fourth A to Z
    nav.apply(Action.DOWN)
    settle(view, nav)
    snapshot(screen.ren, "home-long-title-buttons")
    assert view.scroll.done


def test_home_game_without_rom_or_art(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    nav.apply(Action.RIGHT)
    nav.apply(Action.RIGHT)                        # "Gamma": no ROM, no art
    settle(view, nav)
    snapshot(screen.ren, "home-gamma")


def test_home_many_moves_settle_on_the_library_tile(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    for _ in range(30):
        nav.apply(Action.RIGHT)
        view.draw(nav, 5, STATUS)                  # input faster than the animation
    settle(view, nav, 60)
    assert nav.selected is None
    assert view.scroll.value == view.scroll.target
    snapshot(screen.ren, "home-library-tile")


def test_row_reorder_snaps_instead_of_sliding(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    nav.apply(Action.RIGHT)
    settle(view, nav)
    nav.played(nav.selected.id, 99.0)
    view.draw(nav, 16, STATUS)
    assert view.scroll.value == 0


def test_tiles_scrolled_off_the_left_are_not_drawn(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    nav.apply(Action.RIGHT)
    settle(view, nav)
    assert 0 not in view.visible and 1 in view.visible     # no sliver of the previous tile at the left edge


def test_the_more_button_shows_three_clear_dots(screen):
    nav = Nav(screen.games)
    view = HomeView(screen.gfx, screen.art)
    settle(view, nav)
    out = snapshot(screen.ren, "home-more-dots")
    r = view.more_rect
    bright = sum(1 for x in range(r.x + 6, r.right - 6) for y in range(r.y + 6, r.bottom - 6)
                 if min(tuple(out.get_at((x, y)))[:3]) > 230)
    assert bright >= 45                          # three dots you can see, not a dash-sized smudge

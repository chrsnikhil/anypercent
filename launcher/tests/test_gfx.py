import pygame

from arca_launcher.render import theme
from conftest import snapshot


def test_text_and_shapes_draw(screen):
    g = screen.gfx
    g.fill(theme.BG)
    g.round_rect((10, 10, 40, 20), theme.WHITE, 6)
    r = g.text("Play", 16, 100, 100, weight="bold", anchor="center")
    assert r.w > 20 and r.center == (100, 100)
    assert g.measure("Play", 16, "bold")[0] == r.w
    out = snapshot(screen.ren, "gfx")
    assert tuple(out.get_at((30, 20)))[:3] == (255, 255, 255)
    assert tuple(out.get_at((700, 400)))[:3] == theme.BG


def test_empty_text_and_empty_shapes_are_safe(screen):
    assert screen.gfx.text("", 14, 5, 5).w == 0
    assert screen.gfx.round_rect((0, 0, 0, 10), theme.WHITE, 3).w == 0


def test_moved_shifts_and_fades_what_is_drawn_inside(screen):
    g = screen.gfx
    g.fill(theme.BG)
    with g.moved(dx=40, dy=10):
        g.round_rect((10, 10, 20, 20), theme.WHITE, 0)
        with g.moved(dx=100, alpha=0):                       # nested: 140 px over, and faded out
            g.round_rect((10, 10, 20, 20), theme.WHITE, 0)
    g.round_rect((10, 100, 20, 20), theme.WHITE, 0)           # outside: as given
    out = screen.ren.to_surface()
    assert tuple(out.get_at((55, 25)))[:3] == theme.WHITE and tuple(out.get_at((15, 15)))[:3] == theme.BG
    assert tuple(out.get_at((155, 25)))[:3] == theme.BG
    assert tuple(out.get_at((15, 105)))[:3] == theme.WHITE


def test_shapes_turn_about_their_centre(screen):
    g = screen.gfx
    g.fill(theme.BG)
    g.round_rect((300, 10, 20, 20), theme.WHITE, 0, angle=45)  # a diamond: its top corner pokes above the square
    out = screen.ren.to_surface()
    assert tuple(out.get_at((310, 8)))[:3] == theme.WHITE
    assert tuple(out.get_at((301, 11)))[:3] == theme.BG

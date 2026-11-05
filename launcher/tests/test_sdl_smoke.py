"""The exact pygame-ce GPU-renderer calls the launcher relies on, run headless."""
import os

import pygame
from pygame._sdl2.video import Renderer, Texture, Window


def test_renderer_draws_and_reads_back_headless():
    pygame.display.init()
    win = Window("smoke", size=(80, 48))
    ren = Renderer(win)
    ren.logical_size = (80, 48)
    surf = pygame.Surface((10, 10), pygame.SRCALPHA)
    surf.fill((255, 0, 0, 255))
    tex = Texture.from_surface(ren, surf)
    assert tex.get_rect().size == (10, 10)
    ren.draw_color = (0, 0, 0, 255)
    ren.clear()
    tex.alpha = 128
    tex.draw(dstrect=pygame.Rect(5, 5, 20, 20))
    out = ren.to_surface()
    assert out.get_size() == (80, 48)
    r, g, b, _ = out.get_at((10, 10))
    assert 100 < r < 160 and g == 0 and b == 0
    win.destroy()
    pygame.display.quit()


def test_the_launcher_font_is_outfit_and_every_weight_is_there():
    """Outfit for the launcher, plus Jersey 10 for PB's dialogue; every file is there with its licence."""
    from arca_launcher.render import gfx
    pygame.font.init()
    assert set(gfx.FONT_FILES.values()) == {"Outfit-Regular.ttf", "Outfit-SemiBold.ttf", "Outfit-Bold.ttf",
                                            "Jersey10-Regular.ttf"}
    for name in gfx.FONT_FILES.values():
        assert os.path.exists(os.path.join(gfx.FONT_DIR, name)), name
    assert os.path.exists(os.path.join(gfx.FONT_DIR, "LICENSE-Outfit.txt"))
    assert os.path.exists(os.path.join(gfx.FONT_DIR, "LICENSE-Jersey10.txt"))
    w, h = pygame.font.Font(os.path.join(gfx.FONT_DIR, "Outfit-Bold.ttf"), 20).size("Tobu Tobu Girl")
    assert w > 100 and h > 15

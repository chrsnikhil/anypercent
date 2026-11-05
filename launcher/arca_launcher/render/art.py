"""Per-game textures: rounded tiles at their exact on-screen sizes, blurred backgrounds, 2x screenshots.

Pixel art is scaled once in software to the size it is drawn at, then drawn 1:1, so it stays sharp."""
import os

import pygame

from . import theme


def square_crop(surf):
    w, h = surf.get_size()
    s = min(w, h)
    return surf.subsurface(((w - s) // 2, (h - s) // 2, s, s)).copy()


def rounded(surf, size, radius):
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    out.blit(pygame.transform.scale(surf, (size, size)), (0, 0))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def placeholder():
    s = pygame.Surface((160, 144))
    s.fill((38, 42, 52))
    return s


class Art:
    def __init__(self, gfx, library_dir):
        self.gfx = gfx
        self.dir = library_dir
        self._cache = {}

    def _surface(self, rel):
        if not rel:
            return None
        try:
            return pygame.image.load(os.path.join(self.dir, rel))
        except (pygame.error, OSError):
            return None

    def _get(self, key, make):
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def tile(self, game, size):
        def make():
            surf = self._surface(game.tile) or placeholder()
            return self.gfx.texture(rounded(square_crop(surf), size, theme.TILE_RADIUS), pixel_art=True)
        return self._get(("tile", game.id, size), make)

    def library_tile(self, size):
        def make():
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(s, (44, 48, 60, 255), s.get_rect(), border_radius=theme.TILE_RADIUS)
            cell = size // 7
            x0 = (size - 5 * cell) // 2
            for r in range(3):
                for c in range(3):
                    pygame.draw.rect(s, (230, 232, 240, 255), (x0 + 2 * c * cell, x0 + 2 * r * cell, cell, cell),
                                     border_radius=max(1, cell // 4))
            return self.gfx.texture(s)
        return self._get(("library", size), make)

    def warm(self, games, budget=4):
        """Load up to `budget` textures that are not loaded yet (tiles at both sizes, backgrounds);
        returns how many it loaded, so the splash can spread the work over its frames."""
        done = 0
        for game in games:
            for key, make in ((("tile", game.id, theme.TILE), lambda g=game: self.tile(g, theme.TILE)),
                              (("tile", game.id, theme.TILE_BIG), lambda g=game: self.tile(g, theme.TILE_BIG)),
                              (("bg", game.id), lambda g=game: self.bg(g))):
                if key in self._cache or (key[0] == "bg" and not game.bg):
                    continue
                make()
                done += 1
                if done >= budget:
                    return done
        return done

    def bg(self, game):
        if game is None or not game.bg:
            return None

        def make():
            s = self._surface(game.bg)
            return self.gfx.texture(s) if s else None
        return self._get(("bg", game.id), make)

    def clip_frame(self, game, index):
        """Frame `index` of the game's attract-mode clip, at its native size (drawn scaled up, nearest). Only one
        game's frames are kept: the Pi's GPU memory is small and a clip is 30 frames."""
        if not game.clip:
            return None
        for key in [k for k in self._cache if k[0] == "clip" and k[1] != game.id]:
            del self._cache[key]
        rel = game.clip[index % len(game.clip)]

        def make():
            s = self._surface(rel)
            return self.gfx.texture(s, pixel_art=True) if s else None
        return self._get(("clip", game.id, rel), make)

    def shot(self, game, index):
        if not game.shots:
            return None
        rel = game.shots[index % len(game.shots)]

        def make():
            s = self._surface(rel)
            return self.gfx.texture(pygame.transform.scale(s, (s.get_width() * 2, s.get_height() * 2)),
                                    pixel_art=True) if s else None
        return self._get(("shot", rel), make)

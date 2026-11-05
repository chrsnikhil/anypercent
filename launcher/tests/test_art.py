import pygame

from arca_launcher.render.art import placeholder, rounded, square_crop


def test_square_crop_is_centred():
    s = pygame.Surface((160, 144))
    assert square_crop(s).get_size() == (144, 144)


def test_rounded_corners_are_transparent():
    s = pygame.Surface((144, 144))
    s.fill((255, 0, 0))
    out = rounded(s, 120, 10)
    assert out.get_size() == (120, 120)
    assert out.get_at((0, 0)).a == 0 and out.get_at((60, 60)).a == 255


def test_art_for_every_fixture_game(screen):
    for game in screen.games:
        assert screen.art.tile(game, 150).get_rect().size == (150, 150)
    by = {x.id: x for x in screen.games}
    assert screen.art.bg(by["gamma"]) is None                    # no art at all: no background
    assert screen.art.shot(by["gamma"], 0) is None
    assert screen.art.shot(by["alpha-quest"], 4).get_rect().size == (320, 288)   # index wraps
    assert screen.art.bg(None) is None
    assert screen.art.library_tile(120).get_rect().size == (120, 120)
    assert placeholder().get_size() == (160, 144)

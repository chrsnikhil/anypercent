"""MARINE DRIVE GP's seed: seed 0 is the classic race; any other seed gives each rival its own launch delay, line
and pace (never faster than classic), so a run recorded for one seed races different rivals on another."""
import ctypes

from conftest import SC_RACE, to_race


def rivals_after(g, seed, frames):
    """[(x, y)] of the three rivals `frames` race frames after the start, the player idle."""
    g.game_init(seed)
    to_race(g)
    for _ in range(frames):
        g.game_step(0)
    return [(g.kart(i).x, g.kart(i).y) for i in (1, 2, 3)]


def test_game_info_rules_version_is_4(g):
    info = ctypes.cast(ctypes.addressof(ctypes.c_char.in_dll(g, "GAME_INFO")), ctypes.POINTER(ctypes.c_uint8))
    assert int.from_bytes(bytes(info[4:8]), "little") == 4          # 4: the handling (wheel, torque, grip, walls)


def test_the_seed_varies_the_rivals(g):
    classic = rivals_after(g, 0, 240)
    races = set()
    for seed in (0x01234567, 0xDEADBEEF, 0x5EED0001, 77):
        rivals = rivals_after(g, seed, 240)
        assert rivals != classic, "seed %#x raced the classic rivals" % seed
        assert rivals_after(g, seed, 240) == rivals, "the same seed must race the same way"
        races.add(tuple(rivals))
    assert len(races) == 4, "different seeds raced the same rivals"


def test_a_seeded_rival_waits_its_launch_then_drives(g):
    """At least one rival of some seed is still on the grid a few frames after the green light, and every rival is
    on its way well after."""
    g.game_init(0)
    to_race(g)
    grid = [(g.kart(i).x, g.kart(i).y) for i in (1, 2, 3)]
    waited = False
    for seed in (0x01234567, 0xDEADBEEF, 0x5EED0001, 77):
        early = rivals_after(g, seed, 3)
        waited |= any(e == s for e, s in zip(early, grid))
        late = rivals_after(g, seed, 120)
        assert all(l != s for l, s in zip(late, grid)), "a rival never left the grid"
    assert waited, "no seeded rival held at the start"
    assert g.rules_scene() == SC_RACE

"""ZIP's seed: seed 0 is the classic level; any other seed shifts each bug along its patrol (its own phase of the
triangle wave), so a run recorded for one seed meets the bugs elsewhere on another."""
import ctypes

ENT_BUG = 4


class ZipEnt(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int16), ("y", ctypes.c_int16), ("kind", ctypes.c_uint8), ("arg", ctypes.c_uint8)]


class ZipLevel(ctypes.Structure):
    _fields_ = [("w", ctypes.c_uint16), ("h", ctypes.c_uint16), ("tiles", ctypes.c_void_p),
                ("n_ents", ctypes.c_uint16), ("ents", ctypes.POINTER(ZipEnt)),
                ("start_x", ctypes.c_int16), ("start_y", ctypes.c_int16)]


def bugs(lib):
    lib.zip_level_current.restype = ctypes.POINTER(ZipLevel)
    lvl = lib.zip_level_current().contents
    return [(i, lvl.ents[i]) for i in range(lvl.n_ents) if lvl.ents[i].kind == ENT_BUG]


def bug_xs(lib, found):
    lib.world_bug_x.restype = ctypes.c_int32
    return [lib.world_bug_x(i) for i, _ in found]


def test_a_bug_faces_the_way_it_walks_under_any_seed(g):
    """The view flips a bug's sprite by world_bug_left: it must agree with the seeded patrol's direction."""
    found = bugs(g)
    g.world_bug_left.restype = ctypes.c_int
    for seed in (0, 0xDEADBEEF):
        g.game_init(seed)
        for k in (8, 0, 8, 0):                           # START, release: title -> how-to -> play
            g.game_step(k)
        before = bug_xs(g, found)
        left = [g.world_bug_left(i) for i, _ in found]
        for _ in range(300):
            g.game_step(0)
            after = bug_xs(g, found)
            left_after = [g.world_bug_left(i) for i, _ in found]
            for l, l2, a, b in zip(left, left_after, before, after):
                if l != l2:
                    continue                              # it turned this step: the wave crossed an end
                assert not (l and b > a) and not (not l and b < a), "a bug faces away from where it walks"
            before, left = after, left_after


def test_game_info_rules_version_is_2(g):
    info = ctypes.cast(ctypes.addressof(ctypes.c_char.in_dll(g, "GAME_INFO")), ctypes.POINTER(ctypes.c_uint8))
    assert int.from_bytes(bytes(info[4:8]), "little") == 2          # 2: the seed shifts the bugs


def test_the_seed_shifts_every_bugs_patrol(g):
    found = bugs(g)
    assert found, "the level has no bugs"
    g.game_init(0)
    classic = bug_xs(g, found)
    assert classic == [(e.x << 8) - e.arg * 16 * 256 for _, e in found], "seed 0 must be the classic patrol"
    layouts = set()
    for seed in (0x01234567, 0xDEADBEEF, 0x5EED0001, 77):
        g.game_init(seed)
        xs = bug_xs(g, found)
        for x, (_, e) in zip(xs, found):
            rng = e.arg * 16 * 256
            assert (e.x << 8) - rng <= x <= (e.x << 8) + rng, "a bug left its patrol"
        assert xs != classic, "seed %#x moved no bug" % seed
        g.game_init(seed)
        assert bug_xs(g, found) == xs, "the same seed must place the bugs the same way"
        layouts.add(tuple(xs))
    assert len(layouts) == 4, "different seeds gave the same bugs"

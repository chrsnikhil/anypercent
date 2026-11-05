"""The RUSH HOUR bot: plays the PC rules (out/librules.so) from power-on to the venue door, collecting every chai
cup and the World orb on the way, without taking a hit.

It is a greedy planner with look-ahead: targets are taken in level order (each pickup, then the door); for each
target a weighted A* search over short macro-actions (6 frames of one button mask) simulates the real rules from
snapshots of their state (rules_debug_state_size + the exported rh_s) and keeps the first plan that touches the
target. It walks (no B) unless a target cannot be reached walking, which keeps its pace near a first-time human's.

    from bot import play; keys = play(lib)       (lib: arcade_test.load_lib of out/librules.so)"""
import ctypes
import heapq
import os
import sys

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME, "..", "common", "py"))
sys.path.insert(0, os.path.join(GAME, "tests"))
import arcade_test as T  # noqa: E402
from conftest import (A, B, DOWN, LEFT, RIGHT, START, E_BUG, E_CHAI, E_DOOR, E_ORB, ES_GONE, SC_RESULTS,  # noqa: E402
                      typed)

MACRO = 6
WALK = [RIGHT, RIGHT | A, LEFT, LEFT | A, 0, A, DOWN | A]
RUN = [RIGHT | B, RIGHT | B | A, LEFT | B, LEFT | B | A]
PREFIX = [0] * 60 + [START, 0, START]


class Sim:
    def __init__(self, lib):
        self.lib = typed(T.load_lib(lib))
        self.size = self.lib.rules_debug_state_size()
        self.addr = ctypes.addressof(ctypes.c_char.in_dll(self.lib, "rh_s"))

    def save(self):
        return ctypes.string_at(self.addr, self.size)

    def load(self, snap):
        ctypes.memmove(self.addr, snap, self.size)

    def step(self, keys):
        for k in keys:
            self.lib.game_step(k)


PROGRESS = -1          # a target that only asks the player to get past an x (y is ignored)
STRIDE = 64


def targets(lib):
    """Pickups in level order, then the door, with progress targets every STRIDE px where pickups are far apart."""
    picks = []
    for i in range(lib.rules_ent_count()):
        t = lib.rules_ent_type(i)
        if t in (E_CHAI, E_ORB, E_DOOR):
            picks.append((lib.rules_ent_x(i) + (16 if t == E_DOOR else 5), lib.rules_ent_y(i) + 5, i, t))
    picks.sort(key=lambda p: (p[3] == E_DOOR, p[0], p[1]))
    out, x = [], lib.rules_px()
    for p in picks:
        while p[0] - x > STRIDE + 16:
            x += STRIDE
            out.append((x, 0, -1, PROGRESS))
        out.append(p)
        x = max(x, p[0])
    return out


def reached(lib, index, kind, tx=0):
    if kind == PROGRESS:
        return lib.rules_px() >= tx and lib.rules_on_ground()
    if kind == E_DOOR:
        return lib.rules_scene() == SC_RESULTS
    return lib.rules_ent_state(index) == ES_GONE


def safe(sim, damaged, lives, frames=24):
    """Whether some plain action keeps the player unhurt for the next frames (so a plan never ends in a trap)."""
    lib = sim.lib
    here = sim.save()
    try:
        for a in (0, LEFT, RIGHT, LEFT | A, RIGHT | A, A, RIGHT | B | A, LEFT | B | A):
            sim.load(here)
            for _ in range(frames):
                lib.game_step(a)
                if lib.rules_damaged() != damaged or lib.rules_lives_lost() != lives or lib.rules_invuln():
                    break
            else:
                return True
        return False
    finally:
        sim.load(here)


def search(sim, target, actions, budget=40000, weight=2.0):
    """Macro-action keys from the current state to the target (or None). No damage and no death allowed.
    A macro holding A continues a held A (a higher jump); its "fresh" twin releases A for one frame first."""
    lib = sim.lib
    tx, ty, index, kind = target
    root = sim.save()
    damaged, lives = lib.rules_damaged(), lib.rules_lives_lost()
    bugs = [i for i in range(lib.rules_ent_count()) if lib.rules_ent_type(i) == E_BUG]

    def h():
        dx = abs(lib.rules_px() + 6 - tx)
        dy = 0 if kind == PROGRESS else abs(lib.rules_py() + 7 - ty)
        return (dx + dy) / 1.5

    def key():
        px = lib.rules_px()
        near = tuple((lib.rules_ent_x(i) // 4, lib.rules_ent_state(i)) for i in bugs
                     if abs(lib.rules_ent_x(i) - px) < 160)
        return (px // 3, lib.rules_py() // 3, lib.rules_vx() // 64, lib.rules_vy() // 128, lib.rules_on_ground(),
                near)

    moves = []
    for a in actions:
        moves.append((a, False))
        if a & A:
            moves.append((a, True))
    frontier = [(weight * h(), 0, 0, root, [])]
    seen = set()
    n = 0
    tie = 1
    while frontier and n < budget:
        _, g, _, snap, keys = heapq.heappop(frontier)
        n += 1
        for a, fresh in moves:
            if fresh and not (keys and keys[-1] & A):
                continue                                  # the same as holding
            sim.load(snap)
            seq = [a & ~A] + [a] * (MACRO - 1) if fresh else [a] * MACRO
            ok = True
            for j, k in enumerate(seq):
                lib.game_step(k)
                if lib.rules_damaged() != damaged or lib.rules_lives_lost() != lives or lib.rules_invuln():
                    ok = False
                    break
                if reached(lib, index, kind, tx) and (kind == E_DOOR or safe(sim, damaged, lives)):
                    sim.load(root)
                    return keys + seq[:j + 1]
            if not ok:
                continue
            k = key()
            if k in seen:
                continue
            seen.add(k)
            tie += 1
            heapq.heappush(frontier, (g + MACRO + weight * h(), g + MACRO, tie, sim.save(), keys + seq))
    sim.load(root)
    return None


def play(lib, verbose=False):
    """The full route from power-on: keys, one per frame, ending on the frame that reaches the door."""
    sim = Sim(lib)
    lib = sim.lib
    lib.game_init(0)
    keys = list(PREFIX)
    sim.step(keys)
    plan = targets(lib)
    skipped = []
    for target in plan:
        if reached(lib, target[2], target[3], target[0]):
            continue
        seq = search(sim, target, WALK, budget=6000)
        if seq is None:
            seq = search(sim, target, WALK + RUN, budget=60000)
        if seq is None:
            if target[3] == E_DOOR:
                raise RuntimeError("the door is unreachable from x=%d" % lib.rules_px())
            skipped.append(target)
            if verbose:
                print("skipped %s at (%d, %d) from (%d, %d)" % (target[3], target[0], target[1], lib.rules_px(), lib.rules_py()), flush=True)
            continue
        sim.step(seq)
        keys += seq
        if verbose:
            print("target %s at (%d, %d): frame %d" % (target[3], target[0], target[1], len(keys)), flush=True)
    # trim the frames after the door was reached
    lib.game_init(0)
    for i, k in enumerate(keys):
        lib.game_step(k)
        if lib.game_ended():
            keys = keys[:i + 1]
            break
    return keys, skipped

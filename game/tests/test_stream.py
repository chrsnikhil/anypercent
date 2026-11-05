import ctypes
import os
import random

import pytest

from conftest import GAME_DIR, sh

COLS, SLOT_ROWS, MAP_ROWS, SLOTS, MAX = 32, 24, 32, 768, 651


class State(ctypes.Structure):
    _fields_ = [("held", ctypes.c_uint16 * SLOTS), ("room_w_cells", ctypes.c_uint16), ("room_h_cells", ctypes.c_uint16)]


class Writes(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint16), ("slot", ctypes.c_uint16 * MAX), ("map_index", ctypes.c_uint16 * MAX),
                ("cell", ctypes.c_uint16 * MAX)]


@pytest.fixture(scope="module")
def so():
    sh("make", "-f", "tools.mk", "stream")
    lib = ctypes.CDLL(os.path.join(GAME_DIR, "out", "libstream.so"))
    lib.stream_init.argtypes = [ctypes.POINTER(State), ctypes.c_uint16, ctypes.c_uint16]
    lib.stream_update.argtypes = [ctypes.POINTER(State), ctypes.c_int16, ctypes.c_int16, ctypes.POINTER(Writes),
                                  ctypes.c_uint16]
    lib.stream_slot.restype = lib.stream_map_index.restype = ctypes.c_uint16
    lib.stream_slot.argtypes = lib.stream_map_index.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
    return lib


class Vram:
    """A model of the hardware: 768 tile slots holding room cells, and a 32 x 32 map of slot numbers."""

    def __init__(self, so, w_cells, h_cells):
        self.so, self.w, self.h = so, w_cells, h_cells
        self.state, self.writes = State(), Writes()
        so.stream_init(ctypes.byref(self.state), w_cells, h_cells)
        self.slot_cell = [None] * SLOTS
        self.map = [None] * (COLS * MAP_ROWS)

    def update(self, x, y, budget=MAX):
        self.so.stream_update(ctypes.byref(self.state), x, y, ctypes.byref(self.writes), budget)
        for i in range(self.writes.count):
            self.slot_cell[self.writes.slot[i]] = self.writes.cell[i]
            self.map[self.writes.map_index[i]] = self.writes.slot[i]
        return self.writes.count

    def visible_ok(self, x, y):
        """Every visible cell: the hardware map at its wrapped position points at a slot holding that cell."""
        for cy in range(y // 8, min(self.h, (y + 159) // 8 + 1)):
            for cx in range(x // 8, min(self.w, (x + 239) // 8 + 1)):
                slot = self.map[(cx % COLS) + COLS * (cy % MAP_ROWS)]
                if slot is None or self.slot_cell[slot] != cy * self.w + cx:
                    return False
        return True


def test_slot_and_map_layout(so):
    assert so.stream_slot(33, 25) == 1 + 32 * 1 and so.stream_map_index(33, 25) == 1 + 32 * 25
    assert so.stream_slot(5, 24) == 5 and so.stream_map_index(5, 32) == 5


def test_the_first_update_fills_the_window_and_the_same_camera_writes_nothing(so):
    v = Vram(so, 70, 48)
    assert v.update(0, 0) == 30 * 20 and v.visible_ok(0, 0)
    assert v.update(0, 0) == 0
    assert v.update(3, 5) == 31 + 21 - 1 and v.visible_ok(3, 5)       # unaligned: one more column and row


def test_random_camera_walks_keep_video_memory_equal_to_the_room(so):
    rnd = random.Random(5)
    v = Vram(so, 70, 48)
    x, y = 0, 0
    v.update(x, y)
    for _ in range(3000):
        x = max(0, min(560 - 240, x + rnd.randint(-8, 8)))
        y = max(0, min(380 - 160, y + rnd.randint(-8, 8)))
        n = v.update(x, y)
        assert n <= 31 + 21, n                                          # at most one column and one row
        assert v.visible_ok(x, y), (x, y)


def test_no_two_visible_cells_share_a_slot(so):
    for x, y in ((0, 0), (7, 7), (320, 220), (163, 95)):
        slots = [so.stream_slot(cx, cy) for cy in range(y // 8, (y + 159) // 8 + 1) for cx in range(x // 8, (x + 239) // 8 + 1)]
        assert len(slots) == len(set(slots))


def test_a_budgeted_refill_converges_and_never_exceeds_the_budget(so):
    v = Vram(so, 44, 30)
    for n in range(20):
        assert v.update(40, 30, 64) <= 64
    assert v.visible_ok(40, 30)
    so.stream_init(ctypes.byref(v.state), 44, 30)                       # a new room: everything is stale again
    counts = [v.update(40, 30, 64) for _ in range(12)]
    assert counts[:9] == [64] * 9 and sum(counts) == 30 * 21 and v.visible_ok(40, 30)   # x aligned: 30 x 21 cells

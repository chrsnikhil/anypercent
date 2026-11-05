import os
import random
import subprocess

from PIL import Image

from conftest import (A, B, DOWN, GAME_DIR, LEFT, OUT_DIR, RIGHT, SC_CLEAR, SC_DEMODAY, SC_HOWTO, SC_MISSED,
                      SC_NIGHTFALL, SC_PLAY, SC_TITLE, SC_WALKOUT, START, UP, Game)

NM = "/opt/wonderful/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-nm"
ROUTES = os.path.join(GAME_DIR, "tests", "routes")                     # re-record with dev/record_route.py
ROOM = os.path.join(GAME_DIR, "out", "room_office_day.png")
NIGHT_ROOM = os.path.join(GAME_DIR, "out", "room_office_night.png")
DAWN_ROOM = os.path.join(GAME_DIR, "out", "room_office_dawn.png")
HALL_ROOM = os.path.join(GAME_DIR, "out", "room_hall.png")
BEGIN = [0] * 90 + [START, 0, A, 0]


def symbols(elf, *names):
    out = subprocess.run([NM, elf], capture_output=True, text=True, check=True).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            table[parts[2]] = int(parts[0], 16)
    return [table[n] for n in names]


def run_rom(runner, rom, keys, shots=(), save_in=None, save_out=None):
    """keys: one GBA key mask per frame. Returns (steps, hash, scene, cam) for every frame. save_in / save_out:
    cartridge save memory loaded before the run / written after it."""
    path = os.path.join(OUT_DIR, "rom_script.txt")
    with open(path, "w") as f:
        f.write("".join("%x 1\n" % k for k in keys))
    watch = symbols(rom[1], "g_dbg_steps", "g_dbg_hash", "g_dbg_scene", "g_dbg_cam")
    cmd = [runner, rom[0], path, "--watch", ",".join("%x" % a for a in watch)]
    for frame, out in shots:
        cmd += ["--shot", str(frame), out]
    if save_in:
        cmd += ["--save-in", save_in]
    if save_out:
        cmd += ["--save-out", save_out]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return [tuple(int(v, 16) for v in line.split()[1:]) for line in r.stdout.splitlines()]


def load_keys(name):
    with open(os.path.join(ROUTES, name)) as f:
        return [int(line, 16) for line in f if line.strip()]


def screen(path):
    with open(path, "rb") as f:
        return Image.frombytes("RGBA", (240, 160), f.read()).convert("RGB")


def replay_without_lag(rom, runner, lib, keys):
    """Plays keys on the ROM and on the PC rules side by side: one rules step every frame, the same hash every step.
    Leaving the results resets the ROM (src/runlog.cpp): its step count drops to 0, it boots again, and the PC rules
    restart from rules_init() at the ROM's first step after the boot."""
    rows = run_rom(runner, rom, keys)
    g, last, scenes = None, 0, []
    for i, (steps, h, scene, _) in enumerate(rows):
        if steps and steps == last and i + 1 < len(rows) and rows[i + 1][0] < last:
            continue                                       # the frame the ROM reset in: its step was discarded
        if steps < last:                                   # the ROM reset
            g, last = None, 0
        if steps == 0:
            continue
        if g is None:
            assert steps == 1, "frame %d: the boot ran %d rules steps at once" % (i, steps)
            g = Game(lib)
        else:
            assert steps == last + 1, "frame %d ran %d rules steps" % (i, steps - last)
        g.step(keys[i])
        assert g.hash() == h, "hash differs at rules step %d" % steps
        last = steps
        if not scenes or scene != scenes[-1]:
            scenes.append(scene)
    return scenes


def test_boots_to_the_title_then_the_how_to_card_then_play(rom, runner):
    rows = run_rom(runner, rom, [0] * 120 + [START, 0] + [0] * 30 + [A, 0] + [0] * 20)
    assert rows[119][0] > 0 and rows[119][2] == SC_TITLE
    assert rows[140][2] == SC_HOWTO and rows[-1][2] == SC_PLAY


def test_rom_matches_the_pc_rules_every_frame(rom, runner, lib):
    rnd = random.Random(3)
    moves = [0, A, B, LEFT, RIGHT, UP, DOWN, LEFT | UP, RIGHT | DOWN, LEFT | B, RIGHT | A, UP | B]
    keys = list(BEGIN)
    for _ in range(150):
        keys += [rnd.choice(moves)] * rnd.randint(1, 20)
    keys += [START, 0, 0, 0, START, 0] + [LEFT] * 30
    replay_without_lag(rom, runner, lib, keys)


def test_replay_is_identical(rom, runner):
    keys = BEGIN + [RIGHT] * 40 + [UP | B] * 20 + [A, 0] * 10
    assert run_rom(runner, rom, keys) == run_rom(runner, rom, keys)


def test_the_full_run_ships_without_lag(rom, runner, lib):
    keys = load_keys("full_run.keys") + [0] * 130 + [START] + [0] * 90
    assert replay_without_lag(rom, runner, lib, keys) == [SC_TITLE, SC_HOWTO, SC_PLAY, SC_NIGHTFALL, SC_PLAY, SC_DEMODAY,
                                                          SC_PLAY, SC_WALKOUT, SC_PLAY, SC_CLEAR, SC_TITLE]


def test_the_deadline_ends_the_run_and_returns_to_the_title_without_lag(rom, runner, lib):
    keys = load_keys("first_chai.keys") + [0] * (36 * 450) + [0] * 30 + [START] + [0] * 90
    assert replay_without_lag(rom, runner, lib, keys) == [SC_TITLE, SC_HOWTO, SC_PLAY, SC_MISSED, SC_TITLE]


def test_the_streamed_room_matches_the_room_image_as_the_camera_moves(rom, runner):
    keys = load_keys("full_run.keys")[:6000]
    rows = run_rom(runner, rom, keys)
    day_end = next((i for i, r in enumerate(rows) if r[2] == SC_NIGHTFALL), len(rows))    # the day room only
    frames = [200]                     # then the first frames whose camera is 16 px (two tiles) from every one so far
    for f in range(300, day_end - 2, 10):
        cam = rows[f - 2][3]
        if len(frames) < 3 and all(abs((cam >> 16) - (rows[o - 2][3] >> 16)) + abs((cam & 0xFFFF) - (rows[o - 2][3] & 0xFFFF))
                                   >= 16 for o in frames):
            frames.append(f)
    assert len(frames) == 3, "the route never moves the camera 16 px"
    shots = [(f, os.path.join(OUT_DIR, "cam_%d.rgba" % f)) for f in frames]
    keys = keys[:frames[-1] + 1]
    rows = run_rom(runner, rom, keys, shots=shots)
    room = Image.open(ROOM).convert("RGB")
    cams = set()
    for f, path in shots:
        cam = rows[f - 2][3]           # the scroll set in a frame is shown from the next vblank on
        cx, cy = cam >> 16, cam & 0xFFFF
        cams.add((cx, cy))
        got = screen(path).crop((0, 0, 240, 128))
        want = room.crop((cx, cy, cx + 240, cy + 128))
        got.save(os.path.join(OUT_DIR, "cam_%d.png" % f))
        g, w = got.tobytes(), want.tobytes()
        # mGBA expands 5-bit colour as (c << 3) | (c >> 2) and rounds differently from the converter's
        # reference image, so compare within one or two 5-bit steps; a misplaced tile is far off
        same = sum(1 for i in range(0, len(g), 3) if max(abs(g[i + k] - w[i + k]) for k in range(3)) <= 12)
        assert same > 0.7 * 240 * 128, "frame %d: only %d pixels match the room crop at %s" % (f, same, (cx, cy))
    assert len(cams) == 3                                               # the camera really moved


def test_the_title_shows_the_logo(rom, runner):
    shot = os.path.join(OUT_DIR, "rom_title.rgba")
    run_rom(runner, rom, [0] * 100, shots=[(100, shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "rom_title.png"))
    maroon = sum(1 for (r, g, b) in img.crop((31, 8, 209, 72)).getdata()
                 if abs(r - 112) < 40 and g < 60 and abs(b - 48) < 40)
    assert maroon > 250, maroon


def test_the_how_to_card_is_shown(rom, runner):
    shot = os.path.join(OUT_DIR, "rom_howto.rgba")
    rows = run_rom(runner, rom, [0] * 90 + [START, 0] + [0] * 20, shots=[(112, shot)])
    assert rows[-1][2] == SC_HOWTO
    screen(shot).save(os.path.join(OUT_DIR, "rom_howto.png"))


def test_the_take_chai_prompt_is_on_screen_at_the_counter(rom, runner, lib):
    """The route's first A press is at the counter: the frame before it, the rules say TAKE and the red A
    button of the prompt pill must be visible."""
    keys = load_keys("full_run.keys")
    press = next(i for i in range(70, len(keys)) if keys[i] & A)
    g = Game(lib)
    for k in keys[:press]:
        g.step(k)
    assert g.hint() == 1                                                # HINT_TAKE
    shot = os.path.join(OUT_DIR, "rom_take_prompt.rgba")
    # emulator frame n (1-based) runs keys[n - 1]; the screen at the end of frame press + 1 shows the sprites
    # set in frame press, i.e. just before the A press is handled
    run_rom(runner, rom, keys[:press + 2], shots=[(press + 1, shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "rom_take_prompt.png"))
    button = sum(1 for (r, g_, b) in img.crop((0, 0, 240, 136)).getdata() if r > 200 and g_ < 80 and b < 100)
    assert button >= 20, "the prompt's A button is not on screen (%d red pixels)" % button


def test_the_opening_objective_fits_on_screen(rom, runner):
    shot = os.path.join(OUT_DIR, "rom_objective.rgba")
    run_rom(runner, rom, BEGIN + [0] * 30, shots=[(len(BEGIN) + 30, shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "rom_objective.png"))
    edge = img.crop((226, 137, 240, 148))                               # the last 14 px of the objective row
    lit = sum(1 for (r, g, b) in edge.getdata() if min(r, g, b) > 200)
    assert lit == 0, "the objective text runs off the right edge (%d lit pixels)" % lit


def test_the_night_room_streams_after_nightfall(rom, runner, lib):
    keys = load_keys("full_run.keys")
    g = Game(lib)
    night = None
    for i, k in enumerate(keys):
        g.step(k)
        if night is None and g.act() == 2:
            night = i
    shot_frame = night + 3 + 200                                        # 200 frames into Act 2 (+3 boot frames)
    shot = os.path.join(OUT_DIR, "night.rgba")
    rows = run_rom(runner, rom, keys[:shot_frame + 1], shots=[(shot_frame, shot)])
    cam = rows[shot_frame - 2][3]
    cx, cy = cam >> 16, cam & 0xFFFF
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "night.png"))
    want = Image.open(NIGHT_ROOM).convert("RGB").crop((cx, cy, cx + 240, cy + 128))
    g_, w_ = img.crop((0, 0, 240, 128)).tobytes(), want.tobytes()
    same = sum(1 for i in range(0, len(g_), 3) if max(abs(g_[i + k] - w_[i + k]) for k in range(3)) <= 12)
    assert same > 0.7 * 240 * 128, "only %d pixels match the night room" % same


def first_frame(lib, keys, test):
    g = Game(lib)
    for i, k in enumerate(keys):
        g.step(k)
        if test(g):
            return i
    raise AssertionError("never happened")


def room_matches(runner, rom, keys, frame, image, name, dim=0.0, share=0.7):
    """The ROM's screen at `frame` shows `image` under the camera (faded toward black by `dim`, as the title
    and results screens are), on at least `share` of the 240 x 128 play area."""
    shot = os.path.join(OUT_DIR, name + ".rgba")
    rows = run_rom(runner, rom, keys[:frame + 1], shots=[(frame, shot)])
    cam = rows[frame - 2][3]
    cx, cy = cam >> 16, cam & 0xFFFF
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, name + ".png"))
    want = Image.open(image).convert("RGB").crop((cx, cy, cx + 240, cy + 128))
    want = want.point(lambda v: int(v * (1 - dim)))
    g_, w_ = img.crop((0, 0, 240, 128)).tobytes(), want.tobytes()
    same = sum(1 for i in range(0, len(g_), 3) if max(abs(g_[i + k] - w_[i + k]) for k in range(3)) <= 12)
    assert same > share * 240 * 128, "%s: only %d pixels match" % (name, same)


def test_the_dawn_office_streams_on_demo_day(rom, runner, lib):
    keys = load_keys("full_run.keys")
    act3 = first_frame(lib, keys, lambda g: g.act() == 3)
    room_matches(runner, rom, keys, act3 + 3 + 100, DAWN_ROOM, "dawn")


def test_the_hall_streams_after_the_walk_out(rom, runner, lib):
    keys = load_keys("full_run.keys")
    hall = first_frame(lib, keys, lambda g: g.room() == 1 and g.scene() == SC_PLAY)
    room_matches(runner, rom, keys, hall + 3 + 120, HALL_ROOM, "hall")


def test_missing_the_deadline_in_the_hall_returns_to_the_day_office(rom, runner, lib):
    keys = load_keys("full_run.keys")
    hall = first_frame(lib, keys, lambda g: g.room() == 1 and g.scene() == SC_PLAY)
    keys = keys[:hall + 1]
    g = Game(lib)
    for k in keys:
        g.step(k)
    while g.scene() != SC_MISSED:
        keys.append(0)
        g.step(0)
    keys += [0] * 30 + [START] + [0] * 60
    room_matches(runner, rom, keys, len(keys) - 1, ROOM, "title_after_hall", dim=0.5, share=0.5)   # logo and text on top


def saved_best(lib, path):
    import ctypes
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        data = f.read(8)
    return lib.record_decode((ctypes.c_uint8 * 8)(*data)) if len(data) == 8 else 0


def best_flags(runner, rom, keys, save_in):
    """g_dbg_best on the last frame: bit 0 = this run set a new best, bit 1 = there was a best before it."""
    path = os.path.join(OUT_DIR, "best_script.txt")
    with open(path, "w") as f:
        f.write("".join("%x 1" % k + chr(10) for k in keys))
    flags, = symbols(rom[1], "g_dbg_best")
    out = subprocess.run([runner, rom[0], path, "--watch", "%x" % flags, "--save-in", save_in], capture_output=True,
                         text=True, check=True).stdout
    return int(out.splitlines()[-1].split()[1], 16)


def blank_cartridge():
    path = os.path.join(OUT_DIR, "save_blank.sav")
    with open(path, "wb") as f:
        f.write(bytes([255]) * 32768)
    return path


def test_a_shipped_run_saves_the_best_time(rom, runner, lib):
    keys = load_keys("full_run.keys") + [0] * 10
    out = os.path.join(OUT_DIR, "save_shipped.sav")
    if os.path.exists(out):
        os.remove(out)
    run_rom(runner, rom, keys, save_in=blank_cartridge(), save_out=out)
    g = Game(lib)
    for k in keys:
        g.step(k)
    assert g.scene() == SC_CLEAR and saved_best(lib, out) == g.run_frames()
    assert best_flags(runner, rom, keys, blank_cartridge()) == 0b01               # "First run!"


def test_the_card_says_new_best_or_keeps_the_best(rom, runner, lib):
    import ctypes
    keys = load_keys("full_run.keys") + [0] * 10
    for best, flags in ((100, 0b10), (10 ** 6, 0b11)):                           # "Best ..." / "NEW BEST!"
        buf = (ctypes.c_uint8 * 8)()
        lib.record_encode(ctypes.c_uint32(best), buf)
        path = os.path.join(OUT_DIR, "save_%d.sav" % best)
        with open(path, "wb") as f:
            f.write(bytes(buf) + bytes([255]) * (32768 - 8))
        assert best_flags(runner, rom, keys, path) == flags, best


def test_a_slower_run_keeps_the_best(rom, runner, lib):
    import ctypes
    buf = (ctypes.c_uint8 * 8)()
    lib.record_encode(ctypes.c_uint32(100), buf)
    old = os.path.join(OUT_DIR, "save_old.sav")
    with open(old, "wb") as f:
        f.write(bytes(buf) + bytes([255]) * (32768 - 8))
    out = os.path.join(OUT_DIR, "save_kept.sav")
    run_rom(runner, rom, load_keys("full_run.keys") + [0] * 10, save_in=old, save_out=out)
    assert saved_best(lib, out) == 100


def test_a_missed_run_saves_nothing(rom, runner, lib):
    keys = load_keys("first_chai.keys") + [0] * (36 * 450) + [0] * 10
    out = os.path.join(OUT_DIR, "save_missed.sav")
    if os.path.exists(out):
        os.remove(out)
    run_rom(runner, rom, keys, save_out=out)
    assert saved_best(lib, out) == 0


def test_the_results_card_is_drawn(rom, runner, lib):
    keys = load_keys("full_run.keys") + [0] * 125
    shot = os.path.join(OUT_DIR, "results_card.rgba")
    run_rom(runner, rom, keys, shots=[(len(keys), shot)])
    img = screen(shot)
    img.save(os.path.join(OUT_DIR, "results_card.png"))
    panel = img.crop((24, 12, 216, 124))
    fill = sum(1 for (r, g, b) in panel.getdata() if abs(r - 16) <= 8 and abs(g - 16) <= 8 and abs(b - 32) <= 8)
    assert fill > 0.5 * 192 * 112, fill                               # the card's own fill colour, not the dim hall


def peak_sprite_tiles(runner, rom, keys):
    """The most sprite tiles (of 1024) the ROM has allocated on any frame of the run."""
    path = os.path.join(OUT_DIR, "vram_script.txt")
    with open(path, "w") as f:
        f.write("".join("%x 1\n" % k for k in keys))
    tiles, = symbols(rom[1], "g_dbg_sprite_tiles")
    out = subprocess.run([runner, rom[0], path, "--watch", "%x" % tiles], capture_output=True, text=True,
                         check=True).stdout
    return max(int(line.split()[1], 16) for line in out.splitlines())


SPRITE_TILES, TEXT_MARGIN = 1024, 128    # 4 KB spare for what a human run adds (a message, a prompt, an objective)


def test_sprite_memory_has_room_through_a_full_run(rom, runner):
    keys = load_keys("full_run.keys") + [0] * 130 + [START] + [0] * 90 + [START, 0, 0, 0, A, 0] + [0] * 60
    peak = peak_sprite_tiles(runner, rom, keys)
    assert peak <= SPRITE_TILES - TEXT_MARGIN, "peak %d sprite tiles" % peak


def test_sprite_memory_has_room_after_a_missed_run(rom, runner):
    keys = load_keys("first_chai.keys") + [0] * (36 * 450) + [0] * 30 + [START] + [0] * 90
    peak = peak_sprite_tiles(runner, rom, keys)
    assert peak <= SPRITE_TILES - TEXT_MARGIN, "peak %d sprite tiles" % peak


def test_sprite_memory_has_room_when_the_deadline_passes_in_the_hall(rom, runner, lib):
    """The crowd, the missed card and the swap back to the day office in one sequence (the owner's crash)."""
    keys = load_keys("full_run.keys")
    hall = first_frame(lib, keys, lambda g: g.room() == 1 and g.scene() == SC_PLAY)
    keys = keys[:hall + 1]
    g = Game(lib)
    for k in keys:
        g.step(k)
    while g.scene() != SC_MISSED:
        keys.append(0)
        g.step(0)
    keys += [0] * 30 + [START] + [0] * 90
    peak = peak_sprite_tiles(runner, rom, keys)
    assert peak <= SPRITE_TILES - TEXT_MARGIN, "peak %d sprite tiles" % peak

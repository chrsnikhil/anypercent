"""The World sponsor demo (SPONSOR_DEMOS.md): its sound cues, its cut, and (run in WSL) its launcher screens.

Sound: python scripts/heavy.py python prep/make_mw3_audio.py out/mw3ref sponsor world  -> out/sponsor_world_orig.wav
  make_mw3_audio.py runs this file with card, ramp, rnd and np handed in, and reads LEN_S, BED_AT, BED_DB and build().
  Every cue comes from src/sponsors/world/timing.json, the same numbers Act.tsx draws from, so a retimed shot moves its
  sound with it. When built.json gets WORLD ID field-report clips, the act grows at the field slot; so does this.

Cut: python prep/sponsors/world.py cut  -> src/sponsors/world/cut.json
  The skeleton (title, the flash, the act, the end title) with the act at its real length (timing.json plus any WORLD ID
  clips), refusing a cut of 120 s or more. Re-run it whenever built.json's World clips change.

Screens: (WSL) /opt/arca-sandbox/venv/bin/python video/briefing/prep/sponsors/world.py screens
  -> public/sponsors/world/<state>/NNN.jpg + screens.json
  The console's screens for the World steps, drawn by the real launcher (launcher/arca_launcher: its handler flow, its
  MockSponsors, its views; headless SDL), exactly as prep/make_handler_frames.py draws the film's, only longer (so PB's
  whole line types out) and for the states the film never showed: id_dup (a second record book refused), buy_suspended
  (a coach on another console refusing to pay a voided runner), ls_approve and ls_done (the Agent Pass approval). The
  launcher's MOCK pill is on every one; every code, book name and wallet on them is the launcher's own mock value."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BRIEF = os.path.abspath(os.path.join(HERE, "..", ".."))


def render():
    import io
    import shutil
    import sys

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    repo = os.path.abspath(os.path.join(BRIEF, "..", ".."))
    sys.path.insert(0, os.path.join(repo, "launcher"))
    import pygame
    from PIL import Image

    from arca_launcher import coach
    from arca_launcher.app import Config, Display
    from arca_launcher.handler.flow import Flow
    from arca_launcher.handler.ledger import Ledger
    from arca_launcher.handler.mock import MockSponsors
    from arca_launcher.handler_glue import GHOST_LOOKS, MOCK_WALLET, HandlerGlue
    from arca_launcher.library import load_library
    from arca_launcher.model import Nav, Screen
    from arca_launcher.render.chrome import Status

    out = os.path.join(BRIEF, "public", "sponsors", "world")
    lib = "/opt/arca-sandbox/launcher"
    book = "ANY-7QZ"                                   # the film's mock record book (make_handler_frames.py's Ledger)
    every = 2                                          # one image every 2 film frames (30 fps), as the film's
    # state -> (film frames to draw, how to reach it, ctx overrides). PB types at 40 characters a second, so each runs
    # long enough for the whole line.
    plan = {
        "id_scan": (240, None, {}),
        "id_dup": (240, None, {"other_book": book}),
        "buy_suspended": (240, None, {"target": "ZOYA"}),  # a mock runner, not RIA: RIA's ghost is the film's honest log
        "ls_scan": (240, None, {}),
        "ls_approve": (240, "ls_scan", {}),             # reached for real, so the code on it is the one ls_scan drew
        "ls_done": (180, None, {}),
    }
    with open(os.path.join(BRIEF, "public", "handler", "run.json")) as f:
        run = json.load(f)
    you, ria = run["run"]["time_frames"], run["ria"]["time_frames"]
    display = Display(Config(library_dir=lib, state_path="/tmp/world-film-state.json"))
    games = load_library(lib)
    nav = Nav(games)
    status = Status("9:41 PM", 72)
    index = {}
    for state, (frames, via, extra) in plan.items():
        d = os.path.join(out, state)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        ctx = {"game": "Marine Drive GP", "arcade": True, "buyer": "", "wallet": MOCK_WALLET, "split": "",
               "ghost_look": GHOST_LOOKS["MDGP"], "runs": "1", "sold": 0, "log_frames": ria, "best_frames": you,
               "run_frames": you, "run_time": coach.fmt_time(you)}
        ctx.update(HandlerGlue._board_ctx(ria, you))
        ctx.update(extra)
        ctx["game_titles"] = {g.id: g.title for g in games}
        flow = Flow(MockSponsors(lambda: 0), Ledger(book=book), "/tmp/world-film.json", "marine-drive-gp", ctx,
                    lambda: "2026-11-07")
        nav.stack = [Screen.HOME]
        nav.open_handler(flow, via or state)
        if via:                                        # Cross on the phone step: the mock phone answers on the next tick
            flow.press("cross")
            flow.tick(1)
            assert flow.state.name == state, flow.state.name
        n = 0
        for i in range(0, frames, every):
            flow.ms_in_state = round(i * 1000 / 60)
            display.views.draw(nav, 1000 / 60 * every, status)
            raw = pygame.image.tobytes(display.renderer.to_surface(), "RGB")
            img = Image.frombytes("RGB", (800, 480), raw)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            with open(os.path.join(d, "%03d.jpg" % n), "wb") as f:
                f.write(buf.getvalue())
            n += 1
        index[state] = n
        print(state, n, "images:", flow.line)
    display.close()
    with open(os.path.join(out, "screens.json"), "w") as f:
        json.dump({"images": index, "every": every, "you": you, "ria": ria}, f)
    print(index, "->", out)



# ---- the act's length and sound (make_mw3_audio.py reads LEN_S, BED_AT, BED_DB, build) ------------------------------

TIMING = json.load(open(os.path.join(BRIEF, "src", "sponsors", "world", "timing.json"), encoding="utf-8"))
BUILT = json.load(open(os.path.join(BRIEF, "src", "acts", "built.json"), encoding="utf-8"))
CLIPS = [c for c in BUILT.get("clips", []) if str(c.get("sponsor", "")).upper() == "WORLD ID"]
CLIP_FR = [round(c["seconds"] * 60) for c in CLIPS]
SHOTS = []
_a = 0
for _s in TIMING["shots"]:
    _n = sum(CLIP_FR) if _s["id"] == "field" else _s["len"]
    SHOTS.append(dict(_s, len=_n, at=_a))
    _a += _n
AT = {s["id"]: s["at"] for s in SHOTS}
LEN = _a
LEN_S = LEN / 60
BED_AT = 40.0                       # C add9, the Mumbai bed: what gets built at the event
BED_DB = -25
BIG = ("line", "close")             # the act's two big statements land on a deep hit


def build(m, sec):
    line, close = AT["line"], AT["close"]
    ramp(m, 0, LEN_S, [(0, -4), (1.0, 0), (sec(line) - 0.3, 0), (sec(line) + 0.4, 3), (sec(line + 200), 0),
                       (sec(close) - 0.3, 0), (sec(close) + 0.6, 3), (LEN_S - 2.0, 2), (LEN_S, -8)])
    m.fx("whoosh", 0.05, -9)                                  # the slate
    m.fx("tick", sec(5), -12)
    m.fx("tick", sec(12), -15)
    for s in SHOTS:
        if s["id"] == "slate" or s["len"] == 0:
            continue
        a = s["at"]
        S = lambda f, a=a: sec(a + f)
        if s["id"] == "field":                                # the field report: in on a glitch, a chirp as it settles
            f0 = a
            for n in CLIP_FR:
                m.fx("glitch", sec(f0), -9)
                m.fx("chirp", sec(f0 + 30), -11)
                card(m, sec, f0 + 30, -13)
                f0 += n
            continue
        if s["id"] in BIG:                                    # a hard cut to the plate: a deep hit under it
            m.fx("whoosh", S(0) - 0.14, -12)
            m.fx("hit", S(0), -8)
        else:                                                 # every hard cut: a short glitch, a breath of air before it
            m.fx("whoosh", S(0) - 0.12, -13)
            m.fx("glitch", S(0), -11)
        for c in s.get("cuts", []):                           # a hard cut inside the shot (the loop going round)
            m.fx("whoosh", S(c) - 0.1, -12)
            m.fx("glitch", S(c), -9)
        for c in s.get("cards", []):                          # each card spawning: the box, then its content
            card(m, sec, a + c, -13)
        for c in s.get("hits", []):                           # stamps and the big lines landing
            m.fx("big" if s["id"] in BIG else "hit", S(c), -6 if s["id"] in BIG else -4)
            m.fx("chirp", S(c + 2), -9)
        for c in s.get("chirps", []):
            m.fx("chirp", S(c), -11)
        for c in s.get("glitch", []):                         # a screen coming up, or cutting to the next screen
            m.fx("glitch", S(c), -15 if c < 10 else -11)
        for f0, f1, step in s.get("typing", []):              # letters typing: the hook louder, PB's words under
            for k in range(f0, f1, step):
                m.fx("tick", S(k), -17 if s["id"] == "hook" else -23)
    for ln in TIMING["lines"]:                                # a soft comms tick as each subtitle comes in
        m.fx("tick", sec(AT[ln["shot"]] + ln["at"]) - 0.03, -19)
    for i, n in enumerate(CLIP_FR):
        m.fx("tick", sec(AT["field"] + sum(CLIP_FR[:i]) + 16) - 0.03, -19)
    m.fx("whoosh", sec(LEN - 30), -11)                        # out, into the end title


def write_cut():
    """src/sponsors/world/cut.json: the skeleton, with the act at its real length."""
    cut = [
        {"video": "out/title_open_raw.mov", "grade": "warm", "trim": None, "seconds": 2.5, "sound": "title_open_orig", "gain": 0,
         "overlay": None, "chapter": "Title"},
        {"video": "out/flash_raw.mov", "grade": "cool", "trim": None, "seconds": round(400 / 60, 6), "sound": "flash_orig", "gain": 0,
         "overlay": None, "chapter": "What Any% is"},
        {"video": "out/sponsor_world_raw.mov", "grade": "cool", "trim": None, "seconds": round(LEN / 60, 6), "sound": "sponsor_world_orig",
         "gain": 0, "overlay": None, "chapter": "Any% x World: why World"},
        {"video": "out/title_end_raw.mov", "grade": "warm", "trim": None, "seconds": 4.0, "sound": "title_end_orig", "gain": 0,
         "overlay": None, "chapter": "End title"},
    ]
    total = sum(c["seconds"] for c in cut)
    if total >= 120:
        raise SystemExit(f"the cut would run {total:.2f} s; trim the World clips (built.json) or drop the flash")
    path = os.path.join(BRIEF, "src", "sponsors", "world", "cut.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(" " + json.dumps(c) for c in cut) + "\n]\n")
    print(f"{path}: act {LEN} frames ({LEN / 60:.2f} s), cut {total:.2f} s")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "cut":
        write_cut()
    elif len(sys.argv) > 1 and sys.argv[1] == "screens":
        render()
    else:
        raise SystemExit(__doc__)

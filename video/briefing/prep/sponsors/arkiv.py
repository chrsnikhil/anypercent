"""Sound cues for the Arkiv sponsor demo's act (src/sponsors/arkiv/Act.tsx), synthesised only (the demo is public).
Run by prep/make_mw3_audio.py:  python scripts/heavy.py python prep/make_mw3_audio.py out/mw3ref sponsor arkiv
The shot clock is src/sponsors/arkiv/timing.json, the same file the act reads; the field-report clips (built.json clips
with sponsor ARKIV) are fitted the same way the act fits them, so the length always matches ARKIV_LEN. Every cut, card
and stamp in the act has a cue here; card, ramp, rnd and np are handed in by make_mw3_audio.py."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "..", "src")
T = json.load(open(os.path.join(_SRC, "sponsors", "arkiv", "timing.json"), encoding="utf-8"))
_B = json.load(open(os.path.join(_SRC, "acts", "built.json"), encoding="utf-8"))

_base = T["pre"]["clips"] + T["post"]["len"]
CLIPS, _acc = [], 0
for _c in (c for c in _B["clips"] if c.get("sponsor") == "ARKIV"):      # as Act.tsx: only clips that fit maxAct
    _n = round(_c["seconds"] * 60)
    if _base + _acc + _n > T["maxAct"]:
        break
    CLIPS.append((T["pre"]["clips"] + _acc, _n))
    _acc += _n
POST = T["pre"]["clips"] + _acc
AT = dict(T["pre"], stat1=POST + T["post"]["stat1"], stat2=POST + T["post"]["stat2"])
LEN = POST + T["post"]["len"]

LEN_S = LEN / 60
BED_AT = 40.0                     # C add9, "Mumbai": the build at the event
BED_DB = -25


def build(m, sec):
    ramp(m, 0, LEN_S, [(0, -5), (2.5, 0), (sec(AT["fake2"]) + 1.0, 0), (sec(AT["fake2"]) + 1.4, 2), (sec(AT["fake3"]), 0),
                       (sec(AT["stat2"]), 0), (sec(AT["stat2"]) + 0.6, 3), (LEN_S, 3)])
    for _s, o, _n, _a, *_ in T["lines"]:                   # a soft comms tick as each subtitle line comes in
        m.fx("tick", sec(AT[_s] + o) - 0.03, -19)

    def cut(f, kind="glitch", db=-12):                     # a hard cut: a glitch, a whoosh under the big ones
        m.fx(kind, sec(f), db)

    # the slate: in on a whoosh, the title lands
    m.fx("whoosh", 0.05, -9)
    m.fx("glitch", sec(4), -13)
    m.fx("hit", sec(10), -7)
    m.fx("chirp", sec(12), -9)

    # the rear plate in 3D, then in on the logo
    a = AT["plate"]
    m.fx("whoosh", sec(a) - 0.12, -8)
    cut(a, "glitch", -10)
    m.fx("hit", sec(a + 2), -8)
    card(m, sec, a + 24, -12)
    cut(AT["plateIn"], "glitch", -12)
    m.fx("chirp", sec(AT["plateIn"] + 6), -11)

    # 01 the record: the entity, its nine attributes typing in; then the four that matter
    a = AT["rec1"]
    cut(a, "hit", -9)
    card(m, sec, a + 8, -11)
    card(m, sec, a + 20, -13)
    card(m, sec, a + 34, -13)
    for i in range(9):
        m.fx("tick", sec(a + 24 + i * 8), -21)
    a = AT["rec2"]
    cut(a)
    card(m, sec, a + 6, -12)
    for i in range(4):
        m.fx("tick", sec(a + 22 + i * 34), -14)
    m.fx("chirp", sec(a + 22 + 3 * 34 + 2), -10)              # CHECKED BY: the checker's wallet

    # 02 the board reads: the console's screen opening, its rows; the cut-in; the query; one query, any reader
    a = AT["board1"]
    cut(a, "hit", -9)
    m.fx("glitch", sec(a + 4), -12)
    m.fx("chirp", sec(a + 8), -11)
    card(m, sec, a + 16, -12)
    for f in range(a + 6, a + 44, 6):                         # the launcher's rows sliding in
        m.fx("tick", sec(f), -24)
    cut(AT["board1In"])
    a = AT["board2"]
    cut(a)
    card(m, sec, a + 6, -12)
    for i in range(4):                                        # each line of the query typing on
        for k in range(0, 16, 4):
            m.fx("tick", sec(a + 22 + i * 26 + k), -20)
    res = a + 22 + 4 * 26 + 18
    card(m, sec, res, -11)
    m.fx("chirp", sec(res + 12), -9)                          # the ghost just ahead
    # the ghost just ahead: two real races on the console's screen, each a wide shot with its card, then a cut-in
    for g in ("ghost1", "ghost2"):
        a = AT[g]
        cut(a, "hit", -9)
        m.fx("glitch", sec(a + 2), -12)                       # the screen opening
        card(m, sec, a + 14, -12)
        m.fx("chirp", sec(a + 30), -12)                       # the badges
        cut(AT[g + "In"])
        card(m, sec, AT[g + "In"] + 10, -13)
        m.fx("tick", sec(AT[g + "In"] + 24), -14)             # the gap lands
    a = AT["board3"]
    cut(a)
    m.fx("tick", sec(a + 10), -15)
    m.fx("whoosh", sec(a + 28), -18)                          # the query fanning out to its readers
    for i in range(3):
        card(m, sec, a + 44 + i * 12, -12)

    # 03 nobody can fake a row: the forged row lands; pinned, struck, sunk, IGNORED; who wrote what
    a = AT["fake1"]
    cut(a, "hit", -9)
    card(m, sec, a + 8, -11)
    m.fx("glitch", sec(a + 96), -6)
    m.fx("hit", sec(a + 96), -6)
    a = AT["fake2"]
    cut(a)
    m.fx("chirp", sec(a + 18), -10)                           # the creator pin typing on
    m.fx("tick", sec(a + 46), -12)                            # struck
    m.fx("whoosh", sec(a + 56), -17)                          # and sunk
    m.fx("big", sec(a + 84), -4)                              # IGNORED
    a = AT["fake3"]
    cut(a)
    for i in range(2):
        at = a + 8 + i * 40
        card(m, sec, at, -12)
        card(m, sec, at + 22, -13)
        m.fx("whoosh", sec(at + 16), -21)
    m.fx("chirp", sec(a + 52), -8)                            # COUNTED
    m.fx("hit", sec(a + 92), -6)                              # IGNORED
    card(m, sec, a + 120, -11)

    # 04 the clock: the timeline drawing, its nodes, the extension; then the two flags
    a = AT["exp1"]
    cut(a, "hit", -9)
    card(m, sec, a + 6, -11)
    m.fx("whoosh", sec(a + 10), -16)
    for at in (14, 34, 50):
        m.fx("tick", sec(a + at), -13)
    m.fx("tick", sec(a + 40), -17)
    card(m, sec, a + 70, -13)
    m.fx("whoosh", sec(a + 120), -19)
    m.fx("chirp", sec(a + 150), -12)
    m.fx("tick", sec(a + 170), -18)
    a = AT["exp2"]
    cut(a)
    card(m, sec, a + 8, -11)
    m.fx("hit", sec(a + 146), -10)
    card(m, sec, a + 146, -12)

    # the field report: each live capture opens on a monitor, its evidence card spawns
    for at, n in CLIPS:
        m.fx("whoosh", sec(at) - 0.12, -9)
        cut(at, "glitch", -10)
        m.fx("tick", sec(at + 6), -15)
        card(m, sec, at + 30, -11)

    # status, then the close on the plate
    a = AT["stat1"]
    cut(a, "hit", -9)
    m.fx("tick", sec(a + 6), -15)
    for i in range(4):
        card(m, sec, a + 12 + i * 9, -12)
    a = AT["stat2"]
    m.fx("whoosh", sec(a) - 0.12, -8)
    cut(a, "glitch", -10)
    m.fx("hit", sec(a + 14), -6)
    m.fx("big", sec(a + 24), -7)
    m.fx("chirp", sec(a + 34), -10)
    m.fx("tick", sec(a + 48), -15)

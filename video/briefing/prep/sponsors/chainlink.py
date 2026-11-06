"""Sound cues for the Chainlink CRE demo's act (src/sponsors/chainlink/Act.tsx), synthesised only (the demo is public):

  python scripts/heavy.py python prep/make_mw3_audio.py out/mw3ref sponsor chainlink   -> out/sponsor_chainlink_orig.wav

Shot starts and narration lines come from src/sponsors/chainlink/config.json, the same file the act reads, so the cues
follow any re-timing. The frame offsets inside each shot below mirror the act's (cards, wipes, the stamp). The bed is the
fix's F add9 (220.0); the problem shots before CHAINLINK CRE lands sit on the film's D minor (145.0) instead, crossfaded
into the F as the fix arrives. card, ramp, rnd and np are handed in by make_mw3_audio.py."""
import json
import math
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")
CFG = json.load(open(os.path.join(_ROOT, "src", "sponsors", "chainlink", "config.json"), encoding="utf-8"))
BUILT = json.load(open(os.path.join(_ROOT, "src", "acts", "built.json"), encoding="utf-8"))
CLIPS = [c for c in BUILT["clips"] if c.get("sponsor") == "CHAINLINK"]
SR = 48000


def _clip_len(c):
    return int(math.floor(c["seconds"] * 60 + 0.5))          # Math.round, as the act does


AT, LENS = {}, {}
_a = 0
for _s in CFG["shots"]:
    _l = sum(_clip_len(c) for c in CLIPS) if (_s["id"] == "field" and CLIPS) else _s["len"]
    AT[_s["id"]], LENS[_s["id"]] = _a, _l
    _a += _l
LEN = _a
LEN_S = LEN / 60
BED_AT = 220.0                                                 # F add9, the fix
BED_DB = -25

STEPS = ["trigger", "hedera", "arkiv", "checks", "checker", "verdict"]
CHECK = json.load(open(os.path.join(_ROOT, "src", "acts", "check.json"), encoding="utf-8"))
RUSH_CMD = next(c for c in CHECK if c["game"] == "RUSH")["cmd"]
SIM_CMD = "cre workflow simulate"
CROSS = (15 - 1.5) / (1.42 - 1.03)                             # Act.tsx: SLOW_A, SLOW_B, SLOW_P, CROSS_AT
CROSS_AT = int(math.floor(120 + (196 - 120) * CROSS / 62 + 0.5))
VOID_AT = 108
OUT_AT = (18, 60, 102)


if __name__ == "__main__":
    # python prep/sponsors/chainlink.py: after built.json gains CHAINLINK clips the act grows; this sets the act's length
    # in src/sponsors/chainlink/cut.json to match (post_sponsor.py reads only the cut) and prints the demo's total
    _p = os.path.join(_ROOT, "src", "sponsors", "chainlink", "cut.json")
    _cut = json.load(open(_p, encoding="utf-8"))
    for _c in _cut:
        if _c["video"] == "out/sponsor_chainlink_raw.mov":
            _c["seconds"] = round(LEN_S, 6)
    open(_p, "w", encoding="utf-8", newline="\n").write("[\n" + ",\n".join(" " + json.dumps(_c) for _c in _cut) + "\n]\n")
    _tot = sum(_c["seconds"] for _c in _cut)
    print(f"act {LEN} frames = {LEN_S:.3f} s; the demo runs {_tot:.2f} s" + ("  ** OVER 2:00: shorten the clips **" if _tot >= 120 else ""))


def cut(m, sec, f, kind="glitch", db=-9):                      # a hard cut: the air moves, then the picture lands
    m.fx("whoosh", sec(f) - 0.15, db - 1)
    m.fx(kind, sec(f), db)


def build(m, sec):
    fix_s = sec(AT["fix"])
    # the bed: silent F under the problem, up as CHAINLINK CRE lands; a dip for the tamper beat, full again for the close
    ramp(m, 0, LEN_S, [(0, -40), (fix_s - 0.6, -40), (fix_s + 0.4, 0), (sec(AT["tamper"]), 0), (sec(AT["tamper"]) + 0.6, -5),
                       (sec(AT["outcomes"]), -5), (sec(AT["outcomes"]) + 0.8, 0), (LEN_S, 0)])
    tmp = type(m)(fix_s + 1.0)                                 # the problem's D minor, out as the F comes in
    tmp.bed(145.0, fix_s + 0.8, -26)
    n = min(len(tmp.x), len(m.x))
    m.x[:n] += tmp.x[:n]

    for l in CFG["lines"]:                                     # a soft comms tick as each line comes in
        if l["shot"] == "field" and CLIPS:
            continue
        m.fx("tick", sec(AT[l["shot"]] + l["at"]) - 0.03, -19)

    # the slate
    m.fx("glitch", 0, -10)
    m.fx("tick", sec(6), -12)
    m.fx("chirp", sec(10), -8)
    m.fx("hit", sec(10), -7)

    # the problem, then the close-up on our server
    a = AT["problem"]
    cut(m, sec, a, "hit", -8)
    m.fx("tick", sec(a + 6), -13)
    m.fx("chirp", sec(a + 12), -9)
    for f in (40, 52, 64, 72):
        card(m, sec, a + f, -11)
    for f in (54, 66, 72):
        m.fx("tick", sec(a + f), -17)
    a = AT["trust"]
    cut(m, sec, a, "glitch", -8)
    card(m, sec, a + 14, -9)
    m.fx("hit", sec(a + 14), -9)
    for k in range(4):                                         # the fake record running to the board and the payouts
        m.fx("tick", sec(a + 22 + k * 44), -18)

    # the fix: CHAINLINK CRE
    a = AT["fix"]
    cut(m, sec, a, "hit", -8)
    m.fx("tick", sec(a + 6), -12)
    m.fx("big", sec(a + 12), -4)
    m.fx("chirp", sec(a + 14), -7)
    m.fx("tick", sec(a + 40), -13)
    m.fx("tick", sec(a + 66), -15)
    card(m, sec, a + 118, -10)
    card(m, sec, a + 134, -12)

    # the workflow, one step a shot
    for k, sid in enumerate(STEPS):
        a = AT[sid]
        cut(m, sec, a, "hit" if k == 0 else "glitch", -9 if k == 0 else -11)
        card(m, sec, a + 8, -12)                               # the new node
        m.fx("chirp", sec(a + 8), -10)                         # the step's title
        m.fx("tick", sec(a + 16), -15)
        card(m, sec, a + 18, -12)                              # the right-hand card
        m.fx("tick", sec(a + 34), -16)                         # the status pills
    a = AT["trigger"]
    for f in (28, 42, 50):
        m.fx("tick", sec(a + f), -14)
    a = AT["hedera"]
    m.fx("chirp", sec(a + 30), -12)                            # START
    for i in range(1, 9):                                      # the checkpoints landing
        m.fx("tick", sec(a + 30 + i * 5), -16)
    m.fx("chirp", sec(a + 75), -11)                            # FINISH
    a = AT["arkiv"]
    for f in (26, 34, 42):
        m.fx("tick", sec(a + f), -14)
    a = AT["checks"]
    for i in range(3):
        card(m, sec, a + 18 + i * 14, -12)
        m.fx("tick", sec(a + 40 + i * 14), -18)
    a = AT["checker"]
    m.fx("chirp", sec(a + 16), -11)                            # the terminal opens
    for i in range(0, len(RUSH_CMD), 2):                       # keys, a character a frame
        m.fx("tick", sec(a + 26 + i), -19)
    out = a + 26 + len(RUSH_CMD) + 6
    m.fx("chirp", sec(out), -9)                                # the real output prints
    m.fx("tick", sec(out + 10), -12)
    a = AT["verdict"]
    for f in (28, 40, 56, 60):
        m.fx("tick", sec(a + f), -14)
    m.fx("chirp", sec(a + 70), -11)

    # all six, a pulse through them, the limits
    a = AT["pipeline"]
    cut(m, sec, a, "hit", -8)
    m.fx("chirp", sec(a + 10), -9)
    for i in range(6):
        cx = 70 + i * 302 + 134
        m.fx("tick", sec(a + 16 + 84 * (cx - 50) / 1808), -13)
    for i in range(3):
        card(m, sec, a + 40 + i * 10, -11)

    # the tamper beat
    a = AT["tamper"]
    cut(m, sec, a, "glitch", -7)
    card(m, sec, a + 10, -11)
    m.fx("tick", sec(a + 10), -15)                             # the axes
    m.fx("tick", sec(a + 30), -14)                             # the limit
    m.fx("chirp", sec(a + 60), -12)                            # the honest run
    card(m, sec, a + 64, -12)                                  # WHY THE CLOCK
    m.fx("rewind", sec(a + 120), -12)                          # the slowed run
    m.fx("glitch", sec(a + CROSS_AT), -6)                      # it leaves the envelope
    m.fx("hit", sec(a + CROSS_AT), -5)
    a = AT["void"]
    cut(m, sec, a, "hit", -8)
    card(m, sec, a + 8, -11)
    m.fx("tick", sec(a + 22), -12)
    m.fx("tick", sec(a + 40), -12)
    m.fx("glitch", sec(a + 58), -8)                            # NO
    m.fx("chirp", sec(a + 84), -8)
    m.fx("hit", sec(a + 84), -7)
    m.fx("big", sec(a + VOID_AT), -1)                          # VOID

    # the three outcomes
    a = AT["outcomes"]
    cut(m, sec, a, "glitch", -9)
    m.fx("tick", sec(a + 6), -13)
    for f in OUT_AT:
        m.fx("hit", sec(a + f), -6)
        card(m, sec, a + f, -11)

    # the field report: the empty slot, or the real clips once built.json has them
    a = AT["field"]
    if CLIPS:
        t = a
        for c in CLIPS:
            m.fx("whoosh", sec(t) - 0.15, -7)
            m.fx("glitch", sec(t), -9)                         # the monitor comes up
            m.fx("chirp", sec(t + 8), -9)
            card(m, sec, t + 30)                               # ON SCREEN
            t += _clip_len(c)
    else:
        cut(m, sec, a, "glitch", -9)
        m.fx("chirp", sec(a + 4), -11)
        for i in range(0, len(SIM_CMD), 2):
            m.fx("tick", sec(a + 22 + i * 2), -19)
        m.fx("chirp", sec(a + 22 + len(SIM_CMD) * 2 + 6), -10)
        card(m, sec, a + 30, -11)

    # the close
    a = AT["close"]
    cut(m, sec, a, "hit", -7)
    m.fx("tick", sec(a + 6), -12)
    m.fx("chirp", sec(a + 12), -7)
    for f in (44, 56, 68):
        card(m, sec, a + f, -11)
    m.fx("tick", sec(a + 100), -14)

"""Original music for the arcade games, written as code: each song (songs.py) becomes a VGM for the Game Boy sound
chip that Butano plays through its DMG backend (advgm), and a WAV preview from a small model of that chip.

Why the Game Boy chip and not sampled GBA sound: it costs the CPU almost nothing (the player writes a few registers
once a frame), so the Mode 7 racer and the raycaster keep their frame budget, and it sounds like the console looks.
Music never touches the rules: replays and run logs are unaffected.

Three voices: the lead on pulse 1, the bass on pulse 2, drums on the noise channel (one drum per step). The wave
channel is left off: its RAM banks behave differently on the GBA, and two pulses and noise need no such care.

Butano's converter (butano/tools/advgm/advgm_converter.py) decides the shape of the file:
  - version 1.61, no SN76489, the Game Boy clock (4194304) at 0x80;
  - every wait command counts as exactly one frame, whatever its length, so each frame ends with one 0x62;
  - only 0xB3 register writes, and the loop offset must land on a command;
  - Butano cannot change the volume of a VGM, so the song sets the chip's master volume (NR50) itself.

  python compose.py                 write every song into its game's dmg_audio/theme.vgm and previews/<id>.wav
  python compose.py --preview-only  previews only"""
import argparse
import math
import os
import struct
import wave
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 60
VGM_RATE = 44100
SAMPLES_PER_FRAME = VGM_RATE // FPS          # 735: what one 0x62 wait means
GB_CLOCK = 4194304
STEPS = 16                                    # sixteenth notes in a bar

# VGM 0xB3 register offsets (0xFF10 + offset on the Game Boy)
NR10, NR11, NR12, NR13, NR14 = 0x00, 0x01, 0x02, 0x03, 0x04
NR21, NR22, NR23, NR24 = 0x06, 0x07, 0x08, 0x09
NR30 = 0x0A
NR41, NR42, NR43, NR44 = 0x10, 0x11, 0x12, 0x13
NR50, NR51, NR52 = 0x14, 0x15, 0x16

NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# noise drums: (NR42 envelope, NR43 polynomial counter)
DRUMS = {
    "k": (0xF2, 0x51),    # kick: loud, fast decay, low 15-bit noise
    "s": (0xC2, 0x34),    # snare: mid noise
    "h": (0x51, 0x00),    # closed hat: quiet, very short, high
    "o": (0x63, 0x08),    # open hat: a little longer, metallic 7-bit noise
    "t": (0xA2, 0x46),    # low tom / thump
}


@dataclass(frozen=True)
class Instrument:
    duty: int          # 0 = 12.5 %, 1 = 25 %, 2 = 50 %, 3 = 75 %
    volume: int        # 0..15 starting volume
    decay: int = 0     # 0 = hold the volume; 1..7 = fade out, one step every decay/64 s


@dataclass(frozen=True)
class Section:
    name: str
    chords: tuple      # one chord root per bar ("Am", "F#", "Bb" ...), for the bass
    melody: tuple      # one bar string per bar: "C5:2 E5:2 .:4 ..." (note:steps, "." is a rest)


@dataclass(frozen=True)
class Song:
    id: str
    game_dir: str          # relative to the repo: where dmg_audio/theme.vgm goes
    title: str
    frames_per_step: int   # tempo: 6 frames a sixteenth = 150 BPM
    lead: Instrument
    bass: Instrument
    bass_octave: int
    bass_pattern: str      # one bar: "R:2 O:2 F:2 ..." (R root, O root an octave up, F fifth, "." rest)
    drums: str             # one bar, 16 chars of k s h o t .
    fill: str              # the last 4 steps of every 4th bar
    sections: tuple        # played in order, then looped from the top
    master: int = 5        # NR50 master volume, 0..7, both sides
    intro: tuple = field(default_factory=tuple)   # sections played once before the loop


def midi(name):
    """'C#5' -> 73. Sharps (#) and flats (b) after the letter, then the octave (C4 is middle C)."""
    i, acc = 1, 0
    while i < len(name) and name[i] in "#b":
        acc += 1 if name[i] == "#" else -1
        i += 1
    return 12 * (int(name[i:]) + 1) + NOTE[name[0]] + acc


def hz(name):
    return 440.0 * 2 ** ((midi(name) - 69) / 12)


def freq_reg(name):
    """The pulse channels' 11-bit period register for a note: f = 131072 / (2048 - x)."""
    return round(2048 - 131072 / hz(name))


def parse_bar(text):
    """'C5:2 .:2 E5:4 ...' -> [(note or None, steps)], refusing a bar that is not 16 steps."""
    out = []
    for tok in text.split():
        note, steps = tok.rsplit(":", 1)
        out.append((None if note == "." else note, int(steps)))
    total = sum(s for _, s in out)
    if total != STEPS:
        raise ValueError(f"bar has {total} steps, not {STEPS}: {text}")
    return out


def bar_steps(text):
    return sum(int(tok.rsplit(":", 1)[1]) for tok in text.split())


def chord_root(chord, octave):
    """'F#m' at octave 2 -> 'F#2'."""
    root = chord[0] + "".join(c for c in chord[1:3] if c in "#b")
    return root + str(octave)


def transpose(note, semis):
    m = midi(note) + semis
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return names[m % 12] + str(m // 12 - 1)


def bass_bar(song, chord):
    root = chord_root(chord, song.bass_octave)
    out = []
    for tok in song.bass_pattern.split():
        kind, steps = tok.rsplit(":", 1)
        note = {"R": root, "O": transpose(root, 12), "F": transpose(root, 7), ".": None}[kind]
        out.append((note, int(steps)))
    return out


def all_sections(song):
    return list(song.intro) + list(song.sections)


def all_notes(song):
    notes = []
    for sec in all_sections(song):
        for bar in sec.melody:
            notes += [n for n, _ in parse_bar(bar) if n]
        for chord in sec.chords:
            notes += [n for n, _ in bass_bar(song, chord) if n]
    return notes


def _steps(sections):
    return sum(len(s.melody) for s in sections) * STEPS


def intro_frames(song):
    return _steps(song.intro) * song.frames_per_step


def loop_frames(song):
    return _steps(song.sections) * song.frames_per_step


def song_frames(song):
    return intro_frames(song) + loop_frames(song)


def _note_on(pulse, note, inst):
    """Register writes that start a note on pulse 1 or 2 (with a trigger)."""
    x = freq_reg(note)
    duty_reg, env_reg, lo_reg, hi_reg = (NR11, NR12, NR13, NR14) if pulse == 1 else (NR21, NR22, NR23, NR24)
    return [(duty_reg, inst.duty << 6), (env_reg, (inst.volume << 4) | (inst.decay & 7)),
            (lo_reg, x & 0xFF), (hi_reg, 0x80 | (x >> 8))]


def _note_off(pulse):
    return [((NR12 if pulse == 1 else NR22), 0x00)]   # DAC off: silence until the next trigger


def events(song):
    """{frame: [(register, value), ...]} for the whole song (intro, then one pass of the loop)."""
    ev = {}

    def add(frame, writes):
        ev.setdefault(frame, []).extend(writes)

    step = 0
    bar_no = 0
    for sec in all_sections(song):
        for bar_text, chord in zip(sec.melody, sec.chords):
            bar_no += 1
            s = step
            for note, steps in parse_bar(bar_text):
                add(s * song.frames_per_step, _note_on(1, note, song.lead) if note else _note_off(1))
                s += steps
            s = step
            for note, steps in bass_bar(song, chord):
                add(s * song.frames_per_step, _note_on(2, note, song.bass) if note else _note_off(2))
                s += steps
            pattern = song.drums[:12] + song.fill if bar_no % 4 == 0 else song.drums
            for i, d in enumerate(pattern):
                if d in DRUMS:
                    env, poly = DRUMS[d]
                    add((step + i) * song.frames_per_step, [(NR42, env), (NR43, poly), (NR44, 0x80)])
            step += STEPS
    return ev


def init_writes(song):
    master = (song.master << 4) | song.master
    return [(NR52, 0x80), (NR50, master), (NR51, 0xBB), (NR10, 0x00), (NR30, 0x00), (NR41, 0x00)]


def vgm(song):
    """The song as a VGM file (bytes) that Butano's DMG backend plays, looping from the end of the intro."""
    ev = events(song)
    data = bytearray()
    loop_pos = None
    for w in init_writes(song):
        data += bytes([0xB3, w[0], w[1]])
    total = song_frames(song)
    first_loop_frame = intro_frames(song)
    for f in range(total):
        if f == first_loop_frame:
            loop_pos = len(data)
        for reg, val in ev.get(f, []):
            data += bytes([0xB3, reg, val])
        data += b"\x62"
    data += b"\x66"
    header = bytearray(0x100)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x161)
    struct.pack_into("<I", header, 0x18, total * SAMPLES_PER_FRAME)
    struct.pack_into("<I", header, 0x1C, 0x100 + loop_pos - 0x1C)
    struct.pack_into("<I", header, 0x20, loop_frames(song) * SAMPLES_PER_FRAME)
    struct.pack_into("<I", header, 0x24, FPS)
    struct.pack_into("<I", header, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", header, 0x80, GB_CLOCK)
    out = header + data
    struct.pack_into("<I", out, 0x04, len(out) - 4)
    return bytes(out)


# ---- a small model of the chip, for previews (the ROM capture in tools/ is the real thing) ----------------------
class _Chip:
    DUTY = (0.125, 0.25, 0.5, 0.75)

    def __init__(self, rate):
        self.rate = rate
        self.reg = [0] * 0x30
        self.ch = [dict(on=False, vol=0, env_dir=0, env_per=0, env_t=0.0, phase=0.0) for _ in range(3)]
        self.lfsr = 0x7FFF
        self.noise_t = 0.0

    def write(self, r, v):
        self.reg[r] = v
        for idx, (env_r, trig_r) in enumerate(((NR12, NR14), (NR22, NR24), (NR42, NR44))):
            c = self.ch[idx]
            if r == env_r and v & 0xF8 == 0:
                c["on"] = False
            if r == trig_r and v & 0x80:
                e = self.reg[env_r]
                c.update(on=e & 0xF8 != 0, vol=e >> 4, env_dir=1 if e & 8 else -1, env_per=e & 7, env_t=0.0)
                if idx == 2:
                    self.lfsr = 0x7FFF

    def _env(self, c, dt):
        if c["env_per"]:
            c["env_t"] += dt
            step = c["env_per"] / 64.0
            while c["env_t"] >= step:
                c["env_t"] -= step
                c["vol"] = max(0, min(15, c["vol"] + c["env_dir"]))

    def render(self, n):
        out = []
        dt = 1.0 / self.rate
        master = (self.reg[NR50] & 7) / 7.0
        for _ in range(n):
            s = 0.0
            for idx, (duty_r, lo_r, hi_r) in enumerate(((NR11, NR13, NR14), (NR21, NR23, NR24))):
                c = self.ch[idx]
                if c["on"] and c["vol"]:
                    x = self.reg[lo_r] | ((self.reg[hi_r] & 7) << 8)
                    f = 131072.0 / (2048 - x)
                    c["phase"] = (c["phase"] + f * dt) % 1.0
                    high = c["phase"] < self.DUTY[self.reg[duty_r] >> 6]
                    s += (c["vol"] / 15.0) * (1 if high else -1)
                self._env(c, dt)
            c = self.ch[2]
            if c["on"] and c["vol"]:
                poly = self.reg[NR43]
                r = (poly & 7) or 0.5
                freq = 524288.0 / r / (2 ** ((poly >> 4) + 1))
                self.noise_t += freq * dt
                while self.noise_t >= 1.0:
                    self.noise_t -= 1.0
                    bit = (self.lfsr ^ (self.lfsr >> 1)) & 1
                    self.lfsr = (self.lfsr >> 1) | (bit << 14)
                    if poly & 8:
                        self.lfsr = (self.lfsr & ~0x40) | (bit << 6)
                s += (c["vol"] / 15.0) * (1 if not self.lfsr & 1 else -1)
            self._env(c, dt)
            out.append(s * master / 3.0)
        return out


def preview(song, path, loops=2, rate=32768):
    """A WAV of the intro and `loops` passes of the loop, from the model above (mono, 16-bit)."""
    ev = events(song)
    chip = _Chip(rate)
    for r, v in init_writes(song):
        chip.write(r, v)
    per_frame = rate // FPS
    frames = []
    total = song_frames(song)
    intro = intro_frames(song)
    seq = list(range(total)) + [intro + (i % loop_frames(song)) for i in range(loop_frames(song) * (loops - 1))]
    for f in seq:
        for r, v in ev.get(f, []):
            chip.write(r, v)
        frames.extend(chip.render(per_frame))
    peak = max(1e-9, max(abs(x) for x in frames))
    scale = 0.8 / peak if peak > 0.8 else 1.0                      # never clip; never boost past full scale
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x * scale)) * 32767)) for x in frames))
    return len(frames) / rate


def main():
    import songs
    p = argparse.ArgumentParser()
    p.add_argument("--preview-only", action="store_true")
    a = p.parse_args()
    repo = os.path.dirname(os.path.dirname(HERE))
    os.makedirs(os.path.join(HERE, "previews"), exist_ok=True)
    for sid, song in sorted(songs.SONGS.items()):
        if not a.preview_only:
            out_dir = os.path.join(repo, song.game_dir, "dmg_audio")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "theme.vgm"), "wb") as f:
                f.write(vgm(song))
        secs = preview(song, os.path.join(HERE, "previews", f"{sid}.wav"))
        print(f"{sid:6s} {song.title:18s} loop {loop_frames(song) / FPS:5.1f} s   preview {secs:5.1f} s")


if __name__ == "__main__":
    main()

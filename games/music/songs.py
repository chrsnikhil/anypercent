"""The five arcade games' theme songs (original, 2026-10-24). Each bar is 16 sixteenth notes: "note:steps", with
"." for a rest; the bass follows each bar's chord with the song's pattern, and the drums repeat one bar with a fill
every fourth. compose.py turns them into the VGMs the ROMs play. A song loops from the top (no intro yet).

  SHIP  SHIP IT!         C major, ~128 BPM   a bouncy hackathon-office groove (I-vi-IV-V)
  RUSH  RUSH HOUR        D Mixolydian, 150   bright Mumbai street platformer, dhol-style kick pattern
  ZIPG  ZIP              E minor, 180        fast and driving, for momentum
  MDGP  MARINE DRIVE GP  A minor, 150        anthemic racer along the Queen's Necklace
  SEGF  SEGFAULT         D minor, ~112       the night before demo day: dark, sparse, chromatic"""
from compose import Instrument, Section, Song

SHIP = Song(
    id="SHIP", game_dir="game", title="SHIP IT!", frames_per_step=7,
    lead=Instrument(duty=1, volume=11, decay=7), bass=Instrument(duty=2, volume=9, decay=3),
    bass_octave=3, bass_pattern="R:2 O:2 F:2 O:2 R:2 O:2 F:2 O:2",
    drums="k.h.s.h.k.hks.h.", fill="s.ss",
    sections=(
        Section("A", ("C", "Am", "F", "G", "C", "Am", "F", "G"), (
            "E5:2 G5:2 C6:2 G5:2 A5:2 G5:2 E5:4",
            "C5:2 E5:2 A5:4 G5:2 E5:2 C5:4",
            "F5:2 A5:2 C6:4 A5:2 F5:2 A5:2 C6:2",
            "D6:4 B5:2 G5:2 D5:4 .:4",
            "E5:2 G5:2 C6:2 E6:2 D6:2 C6:2 G5:4",
            "A5:2 C6:2 E6:4 D6:2 C6:2 A5:4",
            "F5:2 A5:2 C6:2 F6:2 E6:2 C6:2 A5:4",
            "B5:2 D6:2 G6:4 F6:2 D6:2 B5:4",
        )),
        Section("B", ("F", "G", "Em", "Am", "F", "G", "C", "C"), (
            "C6:3 A5:1 F5:4 A5:4 C6:4",
            "D6:3 B5:1 G5:4 B5:4 D6:4",
            "E6:6 D6:2 B5:4 G5:4",
            "A5:6 G5:2 E5:4 C5:4",
            "F5:2 A5:2 C6:2 F6:2 E6:4 C6:4",
            "D6:2 G5:2 B5:2 D6:2 F6:4 D6:4",
            "E6:4 C6:4 G5:4 E5:4",
            "C6:8 .:8",
        )),
    ),
)

RUSH = Song(
    id="RUSH", game_dir="games/rushhour", title="RUSH HOUR", frames_per_step=6,
    lead=Instrument(duty=2, volume=11, decay=7), bass=Instrument(duty=2, volume=10, decay=2),
    bass_octave=3, bass_pattern="R:3 R:1 F:2 R:2 O:2 R:2 F:2 R:2",
    drums="k.hks.h.k.hks.h.", fill="stss",
    sections=(
        Section("A", ("D", "C", "G", "D", "D", "C", "G", "A"), (
            "D5:2 F#5:2 A5:2 F#5:1 G5:1 A5:4 B5:2 A5:2",
            "G5:2 E5:2 C6:4 B5:2 A5:2 G5:4",
            "B5:2 D6:2 G5:4 A5:2 B5:2 C6:2 B5:2",
            "A5:4 F#5:2 E5:2 D5:8",
            "A5:2 A5:2 D6:2 C6:1 B5:1 A5:2 G5:2 F#5:2 G5:2",
            "E5:2 G5:2 C6:2 B5:1 A5:1 G5:4 E5:4",
            "D5:2 G5:2 B5:2 D6:2 C6:2 B5:2 A5:2 G5:2",
            "A5:8 C#6:4 E6:4",
        )),
        Section("B", ("G", "A", "D", "Bm", "G", "A", "D", "D"), (
            "D6:3 C6:1 B5:4 G5:4 B5:4",
            "C#6:3 B5:1 A5:4 E5:4 A5:4",
            "F#6:4 E6:2 D6:2 A5:4 F#5:4",
            "B5:4 A5:2 F#5:2 D5:4 F#5:4",
            "G5:2 B5:2 D6:2 G6:2 F#6:2 E6:2 D6:4",
            "E6:2 C#6:2 A5:2 E6:2 G6:4 E6:4",
            "F#6:4 D6:4 A5:4 F#5:4",
            "D6:8 .:8",
        )),
    ),
)

ZIPG = Song(
    id="ZIPG", game_dir="games/zip", title="ZIP", frames_per_step=5,
    lead=Instrument(duty=1, volume=12, decay=7), bass=Instrument(duty=2, volume=10, decay=2),
    bass_octave=2, bass_pattern="R:2 O:2 R:2 O:2 R:2 O:2 R:2 O:2",
    drums="k.h.s.hkk.h.s.ho", fill="ssss",
    sections=(
        Section("A", ("Em", "C", "D", "B", "Em", "C", "Am", "B"), (
            "E5:2 G5:2 B5:2 E6:2 D#6:1 E6:1 B5:2 G5:4",
            "C6:2 B5:2 G5:2 E5:2 G5:4 C6:4",
            "D6:2 A5:2 F#5:2 A5:2 D6:2 E6:2 F#6:4",
            "F#6:4 D#6:4 B5:4 .:4",
            "G6:2 F#6:2 E6:2 B5:2 G5:2 B5:2 E6:4",
            "E6:2 D6:2 C6:2 G5:2 E5:2 G5:2 C6:4",
            "A5:2 C6:2 E6:2 A6:2 G6:2 E6:2 C6:4",
            "B5:2 D#6:2 F#6:2 B6:2 A6:4 F#6:4",
        )),
        Section("B", ("C", "D", "Em", "Em", "C", "D", "B", "B"), (
            "E6:6 D6:2 C6:4 G5:4",
            "F#6:6 E6:2 D6:4 A5:4",
            "G6:4 F#6:2 E6:2 B5:4 E6:4",
            "E6:12 .:4",
            "C6:2 E6:2 G6:2 E6:2 C6:2 E6:2 G6:4",
            "D6:2 F#6:2 A6:2 F#6:2 D6:2 F#6:2 A6:4",
            "B6:4 A6:4 F#6:4 D#6:4",
            "B5:8 .:8",
        )),
    ),
)

MDGP = Song(
    id="MDGP", game_dir="games/marinedrive", title="MARINE DRIVE GP", frames_per_step=6,
    lead=Instrument(duty=2, volume=12, decay=7), bass=Instrument(duty=2, volume=10, decay=2),
    bass_octave=2, bass_pattern="R:2 R:2 O:2 R:2 R:2 O:2 R:2 O:2",
    drums="k.hhs.hhk.hhs.hk", fill="s.so",
    sections=(
        Section("A", ("Am", "F", "C", "G", "Am", "F", "G", "E"), (
            "A5:3 A5:1 C6:2 E6:2 D6:2 C6:2 A5:4",
            "F5:2 A5:2 C6:2 F6:2 E6:4 C6:4",
            "G5:2 C6:2 E6:2 G6:2 F6:2 E6:2 C6:4",
            "D6:4 B5:4 G5:4 B5:4",
            "E6:3 E6:1 D6:2 C6:2 B5:2 C6:2 A5:4",
            "A5:2 C6:2 F6:4 E6:2 D6:2 C6:4",
            "B5:2 D6:2 G6:4 F6:2 E6:2 D6:4",
            "E6:4 G#5:4 B5:4 E6:4",
        )),
        Section("B", ("F", "G", "Am", "Am", "F", "G", "E", "E"), (
            "A6:6 G6:2 F6:4 C6:4",
            "B6:6 A6:2 G6:4 D6:4",
            "C7:4 B6:2 A6:2 E6:4 A6:4",
            "A6:12 .:4",
            "F6:2 E6:2 F6:2 A6:2 G6:2 F6:2 E6:2 C6:2",
            "D6:2 C6:2 D6:2 G6:2 F6:2 E6:2 D6:2 B5:2",
            "G#6:4 E6:4 B5:4 G#5:4",
            "E6:8 .:8",
        )),
    ),
)

SEGF = Song(
    id="SEGF", game_dir="games/segfault", title="SEGFAULT", frames_per_step=8,
    lead=Instrument(duty=0, volume=10, decay=5), bass=Instrument(duty=1, volume=11, decay=3),
    bass_octave=2, bass_pattern="R:2 .:2 R:2 R:2 O:2 .:2 R:2 R:2",
    drums="k.h.h.k.s.k.h.h.", fill="t.tt",
    sections=(
        Section("A", ("Dm", "Dm", "Bb", "A", "Dm", "Gm", "Bb", "A"), (
            "D5:4 .:2 F5:2 E5:4 D5:4",
            "A5:6 G#5:2 A5:4 .:4",
            "Bb5:4 A5:2 G5:2 F5:4 D5:4",
            "E5:4 C#5:4 A4:8",
            "D6:4 .:2 C6:2 Bb5:4 A5:4",
            "G5:4 Bb5:2 D6:2 C#6:4 D6:4",
            "F6:4 E6:2 D6:2 Bb5:4 G5:4",
            "A5:4 E5:4 C#5:4 A4:4",
        )),
        Section("B", ("Gm", "A", "Dm", "Dm", "Bb", "Gm", "A", "A"), (
            "G5:2 .:2 G5:2 Bb5:2 A5:4 G5:4",
            "A5:2 .:2 A5:2 C#6:2 E6:4 .:4",
            "F6:4 E6:2 D6:2 A5:8",
            "D6:4 C#6:4 D6:8",
            "D6:2 F6:2 Bb6:4 A6:2 F6:2 D6:4",
            "Bb5:2 D6:2 G6:4 F6:2 D6:2 Bb5:4",
            "C#6:4 E6:4 A6:4 G6:4",
            "A5:8 .:8",
        )),
    ),
)

SONGS = {s.id: s for s in (SHIP, RUSH, ZIPG, MDGP, SEGF)}

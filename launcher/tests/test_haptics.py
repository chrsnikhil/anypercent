import ctypes
import math
import struct

from arca_launcher import haptics

RATE = 48000
BLOCK = RATE // haptics.BLOCKS_PER_SECOND


def tone(freq, amp, n=BLOCK):
    return [round(amp * math.sin(2 * math.pi * freq * i / RATE)) for i in range(n)]


def run(r, samples):
    out = (0.0, 0.0)
    for i in range(0, len(samples), BLOCK):
        out = r.feed(samples[i:i + BLOCK])
    return out


def test_wav_header_gives_rate_channels_and_bits():
    head = b"RIFF" + struct.pack("<I", 0) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 2, 44100, 44100 * 4, 4, 16) \
        + b"data" + struct.pack("<I", 0)
    assert haptics.parse_wav_header(head) == (44100, 2, 16)
    assert haptics.parse_wav_header(b"not a wav header at all, forty-four bytes!!") is None


def test_silence_does_not_rumble():
    assert run(haptics.Rumbler(RATE), [0] * BLOCK * 10) == (0.0, 0.0)


def test_a_sudden_bass_hit_rumbles_the_strong_motor():
    r = haptics.Rumbler(RATE)
    run(r, [0] * BLOCK * 20)
    strong, weak = r.feed(tone(60, 20000))
    assert strong > 0.5


def test_a_steady_sound_fades_out_instead_of_buzzing_forever():
    r = haptics.Rumbler(RATE)
    run(r, [0] * BLOCK * 20)
    strong, weak = run(r, tone(60, 20000, BLOCK * haptics.BLOCKS_PER_SECOND * 3))
    assert strong < 0.1 and weak < 0.1


def test_a_high_pitched_hit_is_mostly_the_weak_motor():
    r = haptics.Rumbler(RATE)
    run(r, [0] * BLOCK * 20)
    strong, weak = r.feed(tone(3000, 20000))
    assert weak > 0.3 and strong < weak


def test_the_rumble_effect_matches_the_kernel_struct():
    size = ctypes.sizeof(haptics.FFEffect)
    assert size == (48 if ctypes.sizeof(ctypes.c_void_p) == 8 else 44)
    raw = haptics.rumble_effect(3, 0.5, 1.0, 80)
    assert len(raw) == size
    e = haptics.FFEffect.from_buffer_copy(raw)
    assert (e.type, e.id, e.replay_length, e.strong, e.weak) == (haptics.FF_RUMBLE, 3, 80, 32768, 65535)


def test_finds_the_dualsense_and_not_its_touchpad(tmp_path):
    for n, name in ((3, "vc4-hdmi"), (5, "DualSense Wireless Controller Touchpad"),
                    (6, "DualSense Wireless Controller"), (7, "DualSense Wireless Controller Motion Sensors")):
        d = tmp_path / "class" / "input" / f"event{n}" / "device"
        d.mkdir(parents=True)
        (d / "name").write_text(name + "\n")
    assert haptics.find_pad(str(tmp_path)) == "/dev/input/event6"
    assert haptics.find_pad(str(tmp_path / "nothing")) is None

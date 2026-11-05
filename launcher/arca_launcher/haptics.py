"""Rumble for every game, from its sound. No GBA homebrew in the library drives a rumble motor, so this listens to
what the game plays instead: a sudden bass hit (an explosion, a landing, a crash) kicks the DualSense's strong
motor, a sudden sharp sound (a shot, a coin, a hit) the weak one, and a steady sound (music, an engine) fades out
rather than buzzing for ever.

RetroArch plays through the ALSA pcm "anypercent_haptics" (device/asoundrc): a file plugin that sends the game's
audio on to the speaker and copies it, as WAV, into this script's stdin. Standalone on purpose (ALSA starts it by
path, outside the launcher), and it never stops reading: if it did, RetroArch would die of a broken pipe.

  python haptics.py < game-audio.wav"""
import array
import ctypes
import fcntl
import glob
import math
import os
import re
import struct
import sys
import time

BLOCKS_PER_SECOND = 50                  # 20 ms of sound per decision
PAD_NAME = "DualSense Wireless Controller"
FF_RUMBLE = 0x50
EV_FF = 0x15
PLAY_MS = 70                            # each kick outlasts its 20 ms block a little: no gaps in a long rumble
THRESHOLD = 0.08                        # below this, leave the motors alone
RESCAN_S = 2.0                          # how often to look for a pad when none is open

# how sudden: a block counts as a hit by how far it rises over its recent average (about a quarter second)
SLOW = 0.08
RISE = 1.2
FLOOR = 0.02
GAIN_STRONG = 3.0
GAIN_WEAK = 2.0
DECIMATE = 8
BASS_HZ = 150


class _Rumble(ctypes.Structure):
    _fields_ = [("strong", ctypes.c_uint16), ("weak", ctypes.c_uint16)]


class _Periodic(ctypes.Structure):      # the union's largest member: it sets the struct's size and alignment
    _fields_ = [("waveform", ctypes.c_uint16), ("period", ctypes.c_uint16), ("magnitude", ctypes.c_int16),
                ("offset", ctypes.c_int16), ("phase", ctypes.c_uint16), ("envelope", ctypes.c_uint16 * 4),
                ("custom_len", ctypes.c_uint32), ("custom_data", ctypes.c_void_p)]


class _Union(ctypes.Union):
    _anonymous_ = ("r",)
    _fields_ = [("r", _Rumble), ("periodic", _Periodic)]


class FFEffect(ctypes.Structure):
    """struct ff_effect from linux/input.h."""
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint16), ("id", ctypes.c_int16), ("direction", ctypes.c_uint16),
                ("trigger_button", ctypes.c_uint16), ("trigger_interval", ctypes.c_uint16),
                ("replay_length", ctypes.c_uint16), ("replay_delay", ctypes.c_uint16), ("u", _Union)]


EVIOCSFF = 0x40000000 | (ctypes.sizeof(FFEffect) << 16) | (ord("E") << 8) | 0x80


def rumble_effect(effect_id, strong, weak, ms):
    e = FFEffect(type=FF_RUMBLE, id=effect_id, replay_length=ms)
    e.strong, e.weak = round(max(0.0, min(1.0, strong)) * 65535), round(max(0.0, min(1.0, weak)) * 65535)
    return bytes(e)


def parse_wav_header(head):
    """(rate, channels, bits) from a 44-byte WAV header, or None."""
    if len(head) < 44 or head[:4] != b"RIFF" or head[8:16] != b"WAVEfmt ":
        return None
    _, _, channels, rate, _, _, bits = struct.unpack("<IHHIIHH", head[16:36])
    return rate, channels, bits


def find_pad(sys_root="/sys"):
    """The DualSense's own event node (the one with the motors, not its touchpad or motion sensors), or None."""
    def number(path):
        return int(re.search(r"event(\d+)", path).group(1))
    for name_file in sorted(glob.glob(os.path.join(sys_root, "class", "input", "event*", "device", "name")),
                            key=number):
        try:
            with open(name_file) as f:
                if f.read().strip() == PAD_NAME:
                    return f"/dev/input/event{number(name_file)}"
        except OSError:
            pass
    return None


def _rms(xs):
    return math.sqrt(sum(x * x for x in xs) / len(xs)) / 32768 if xs else 0.0


class Rumbler:
    """Mono blocks of samples in, (strong, weak) motor levels 0..1 out."""

    def __init__(self, rate):
        self.a = 1 - math.exp(-2 * math.pi * BASS_HZ / (rate / DECIMATE))
        self.lp = 0.0
        self.slow_bass = self.slow_full = 0.0

    def feed(self, samples):
        full = _rms(samples)
        bass_xs = []
        for i in range(0, len(samples) - DECIMATE + 1, DECIMATE):
            self.lp += self.a * (sum(samples[i:i + DECIMATE]) / DECIMATE - self.lp)
            bass_xs.append(self.lp)
        bass = _rms(bass_xs)
        hit_bass = max(0.0, bass - RISE * self.slow_bass - FLOOR)
        hit_full = max(0.0, full - RISE * self.slow_full - FLOOR)
        self.slow_bass += SLOW * (bass - self.slow_bass)
        self.slow_full += SLOW * (full - self.slow_full)
        strong = min(1.0, hit_bass * GAIN_STRONG)
        weak = min(1.0, max(0.0, hit_full - hit_bass) * GAIN_WEAK)
        return strong, weak


class Pad:
    """The DualSense's motors through evdev force feedback; quietly absent when no pad is connected."""

    def __init__(self):
        self.fd, self.effect, self.looked = None, -1, 0.0

    def kick(self, strong, weak):
        now = time.monotonic()
        if self.fd is None and now - self.looked >= RESCAN_S:
            self.looked = now
            path = find_pad()
            if path:
                try:
                    self.fd, self.effect = os.open(path, os.O_RDWR), -1
                except OSError:
                    self.fd = None
        if self.fd is None:
            return
        try:
            buf = bytearray(rumble_effect(self.effect, strong, weak, PLAY_MS))
            fcntl.ioctl(self.fd, EVIOCSFF, buf)                 # upload (or update) the effect; the kernel sets its id
            self.effect = FFEffect.from_buffer(buf).id
            os.write(self.fd, struct.pack("llHHi", 0, 0, EV_FF, self.effect, 1))
        except OSError:                                         # the pad went away
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


def _log(line):
    """One line per game when ANYPERCENT_HAPTICS_LOG names a file (debugging on the device)."""
    path = os.environ.get("ANYPERCENT_HAPTICS_LOG")
    if path:
        try:
            with open(path, "a") as f:
                f.write(time.strftime("%H:%M:%S ") + line + "\n")
        except OSError:
            pass


DUMP_SECONDS = 90


def _dump_open(rate, channels):
    """When ANYPERCENT_HAPTICS_DUMP names a folder, the first 90 s of each game's sound go to a WAV there, to tune
    the hit detection against real game audio. The header's lengths are left at 0 (most tools read on to the end)."""
    folder = os.environ.get("ANYPERCENT_HAPTICS_DUMP")
    if not folder:
        return None
    try:
        f = open(os.path.join(folder, time.strftime("haptics-%H%M%S.wav")), "wb")
        f.write(b"RIFF" + struct.pack("<I", 0) + b"WAVEfmt " +
                struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * 2, channels * 2, 16) +
                b"data" + struct.pack("<I", 0))
        return f
    except OSError:
        return None


def main():
    src = sys.stdin.buffer
    try:
        gain = float(os.environ.get("ANYPERCENT_RUMBLE", "1"))
        fmt = parse_wav_header(src.read(44)) or (48000, 2, 16)
        rate, channels, bits = fmt
        if bits != 16 or channels < 1 or gain <= 0:
            raise ValueError("nothing to do")
        rumbler, pad = Rumbler(rate), Pad()
        frames = max(1, rate // BLOCKS_PER_SECOND)
        blocks = kicks = 0
        dump = _dump_open(rate, channels)
        while True:
            data = src.read(frames * channels * 2)
            if not data:
                _log(f"{rate} Hz x{channels}: {blocks} blocks, {kicks} kicks, pad {'open' if pad.fd else 'none'}")
                return
            blocks += 1
            if dump is not None and blocks <= DUMP_SECONDS * BLOCKS_PER_SECOND:
                dump.write(data)
                dump.flush()
            s = array.array("h")
            s.frombytes(data[:len(data) // 2 * 2])
            mono = s[0::channels] if channels == 1 else [(a + b) >> 1 for a, b in zip(s[0::channels], s[1::channels])]
            strong, weak = rumbler.feed(mono)
            strong, weak = strong * gain, weak * gain
            if max(strong, weak) > THRESHOLD:
                pad.kick(strong, weak)
                kicks += 1
    except Exception as e:                                      # noqa: BLE001 - keep the pipe drained, whatever happens
        _log(f"stopped: {e!r}")
        while src.read(65536):
            pass


if __name__ == "__main__":
    main()

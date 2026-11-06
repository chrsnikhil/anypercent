"""A race at full length for the demo film: a run's log replayed on the ROM headless, every frame (60 a second) and its
sound, with a ghost in the cartridge save as the console races one (the arcade bridge's before(): her log's ghost
from the game's replay tool), so the ghost rides where it really went and Marine Drive GP's HUD shows the live gap.

  /opt/arca-sandbox/venv/bin/python games/clips/render_race.py RUN.acl [--ghost GHOST.acl] [--best BEST.acl]
      [--name NAME] [--run-label L] [--ghost-label L] [--scale 4] [--tail-s 4] [--no-audio] [--keep]
  (in the WSL sandbox; the Windows ffmpeg encodes) -> video/final/race/<name>.mp4 and <name>.json

The log is the run: its buttons, step by step from power-on (gba_film.c, beside this), on the cartridge the console
would have had: a profile whose seed nonce boots into the log's own seed (worked back from the header's seed,
arcade/src/ac_rng.h), the ghost, and with --best the best run the cartridge held before (its title and results
screens show it). Like make_clips.py's clips it runs headless on the static libmgba; unlike gba_run it writes every
frame, and the sound (mGBA's own mix, resampled so that each frame is 800 samples at 48 kHz: 60 frames a second, a
0.45% faster pitch than the GBA's 59.73).

Every render is checked before it is encoded: the run verifies with the game's replay tool, and the ROM, fed the
log, ends the run on the log's own final hash and seed; anything else stops here with no video.

Names say whose driving it is. Each log is looked up by its sha256 (the board's log_h) on the Arkiv board the
laptop console last read (arkiv-boards.json) and in the BOT ghost generator's manifests: a person's run is named by
its record book (ANY-6PS), a house run by its BOT label (BOT-A2). A log found nowhere needs --run-label or
--ghost-label, and a BOT's log is always named BOT-... whatever the label says."""
import argparse
import datetime
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "games", "common", "py"))
import arcade_test as T  # noqa: E402
from make_clips import ARCADE, BUILT, TOOLS  # noqa: E402

S = T.S
FILM_SRC = os.path.join(HERE, "gba_film.c")
FILM = os.path.join(HERE, "out", "gba_film")
OUT = os.path.join(REPO, "video", "final", "race")
WORK = "/opt/arca-sandbox/race-work"
BOARD_CACHE = "/opt/arca-sandbox/arkiv-boards.json"     # what the laptop console last read from Arkiv
FFMPEG = os.environ.get("ARCA_FFMPEG", "/mnt/c/ProgramData/chocolatey/bin/ffmpeg.exe")
ELF = {"MDGP": "games/marinedrive/marinedrive.elf", "RUSH": "games/rushhour/rushhour.elf",
       "ZIPG": "games/zip/zip.elf", "SEGF": "games/segfault/segfault.elf", "SHIP": "game/shipit.elf"}
GBA_HZ, GBA_FRAME = 16777216, 280896                    # cycles a second, cycles a frame (228 lines x 1232)
FPS, RATE = 60, 48000
SAMPLES = RATE // FPS                                     # 800 samples each frame
PROFILE_NAME = "PLAYER"                                   # the arcade bridge's default profile
M = 0xFFFFFFFF
FNV_OFFSET, FNV_PRIME = 2166136261, 16777619
FNV_UNPRIME = pow(FNV_PRIME, -1, 1 << 32)


class RenderError(Exception):
    """The render cannot be made honestly: nothing is written."""


# ---- the seed -------------------------------------------------------------------------------------------------------

def rng32(x):
    """ac_rng32: xorshift32 (13, 17, 5)."""
    x ^= (x << 13) & M
    x ^= x >> 17
    x ^= (x << 5) & M
    return x


def _unshift_left(y, k):
    x = y
    for _ in range(32 // k + 1):
        x = y ^ ((x << k) & M)
    return x


def _unshift_right(y, k):
    x = y
    for _ in range(32 // k + 1):
        x = y ^ (x >> k)
    return x


def unrng32(y):
    return _unshift_left(_unshift_right(_unshift_left(y, 5), 17), 13)


def fnv_bytes(h, data):
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & M
    return h


def seed_mix(nonce, boots):
    """ac_seed_mix: the seed a ROM boots into from its profile's nonce and boot count (after its own bump)."""
    if nonce == 0:
        return 0
    h = fnv_bytes(FNV_OFFSET, nonce.to_bytes(4, "little") + boots.to_bytes(4, "little"))
    return rng32(h or 0x9E3779B9)


_FORWARD = None


def profile_seed(seed):
    """(nonce, boot count to write) for a profile whose next boot seeds the game with seed: the ROM bumps the count
    and mixes it with the nonce. Worked back through xorshift32 and FNV-1a, meeting in the middle of the nonce's four
    bytes; the first boot count that has a nonce wins. (0, 0) for seed 0, the classic game."""
    global _FORWARD
    if seed == 0:
        return 0, 0
    if _FORWARD is None:
        _FORWARD = {}
        for b0 in range(256):
            h0 = ((FNV_OFFSET ^ b0) * FNV_PRIME) & M
            for b1 in range(256):
                _FORWARD.setdefault(((h0 ^ b1) * FNV_PRIME) & M, []).append(b0 | b1 << 8)
    mixed = unrng32(seed)
    for written in range(0, 4096):
        h = mixed
        for b in reversed((written + 1).to_bytes(4, "little")):
            h = ((h * FNV_UNPRIME) & M) ^ b
        for b3 in range(256):
            h3 = ((h * FNV_UNPRIME) & M) ^ b3
            for b2 in range(256):
                low = _FORWARD.get(((h3 * FNV_UNPRIME) & M) ^ b2)
                if low is None:
                    continue
                for lo in low:
                    nonce = lo | b2 << 16 | b3 << 24
                    if nonce and seed_mix(nonce, written + 1) == seed:
                        return nonce, written
    raise RenderError(f"no profile boots into seed {seed:#010x}")


def profile_bytes(nonce, boots, trophies=0):
    """arcade_save.profile_bytes with the boot count set: name, tag, trophies, seed nonce, boot count, 32 reserved."""
    return S.profile_bytes(PROFILE_NAME, b"\0" * 8, trophies, seed_nonce=nonce)[:28] + boots.to_bytes(4, "little") \
        + bytes(32)


# ---- who drove it ---------------------------------------------------------------------------------------------------

def sha(data):
    return hashlib.sha256(data).hexdigest()


def known_logs(board_cache=BOARD_CACHE):
    """log_h -> what is known of it: the board's rows (a person's book or a BOT label, human, credential, its listing)
    and the BOT ghost generator's manifests (games/*/out/ghostgen/*/manifest.json)."""
    out = {}
    for path in glob.glob(os.path.join(REPO, "games", "*", "out", "ghostgen", "*", "manifest.json")):
        try:
            with open(path, encoding="utf-8") as f:
                for e in json.load(f):
                    out.setdefault(e["log_h"], {})["bot"] = f"ghostgen {e.get('name')} ({os.path.relpath(path, REPO)})"
        except (OSError, ValueError, KeyError, TypeError):
            continue
    try:
        with open(board_cache, encoding="utf-8") as f:
            boards = json.load(f).get("boards", {})
    except (OSError, ValueError, AttributeError):
        boards = {}
    for game, b in boards.items():
        for row in b.get("rows", ()):
            if isinstance(row, dict) and isinstance(row.get("log_h"), str):
                out.setdefault(row["log_h"], {}).update(
                    board=game, book=row.get("book"), label=row.get("label"), human=bool(row.get("human")),
                    credential=row.get("credential"), listing=row.get("listing"), run=row.get("key"),
                    frames=row.get("frames"), runner=row.get("runner"))
    return out


def who(log_h, known, given=None):
    """(the name a render may use for a log's driver, is it a BOT, what it is known as). A BOT's run is always
    BOT-...; a log found nowhere needs a given label."""
    k = known.get(log_h, {})
    bot = "bot" in k or (k.get("label") or "").startswith("BOT-") or (k and not k.get("human") and not k.get("book"))
    name = k.get("book") or k.get("label")
    if given:
        name = given
    if not name:
        raise RenderError(f"log {log_h[:16]} is on no board and in no BOT manifest: name its driver with a label")
    if bot and not name.upper().startswith("BOT"):
        name = "BOT-" + name
    return name, bot, k


def clock(frames):
    """6414 -> 1m46.90 (a file name's run time)."""
    cs = round(frames * 100 / 60)
    return "%dm%02d.%02d" % (cs // 6000, cs // 100 % 60, cs % 100)


# ---- the runner -----------------------------------------------------------------------------------------------------

def build_film():
    """gba_film.c on the static libmgba, as arcade_test.build_runner builds gba_run: once, and again when either is
    newer."""
    deps = [FILM_SRC, os.path.join(T.MGBA, "build", "libmgba.a")]
    if os.path.exists(FILM) and all(os.path.getmtime(FILM) >= os.path.getmtime(d) for d in deps if os.path.exists(d)):
        return FILM
    os.makedirs(os.path.dirname(FILM), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="gba_film.", dir=os.path.dirname(FILM))
    os.close(fd)
    try:
        cmd = ["gcc", "-O2", "-o", tmp, FILM_SRC, "-I%s/include" % T.MGBA, "-I%s/build/include" % T.MGBA,
               "%s/build/libmgba.a" % T.MGBA, "-lm", "-lpthread"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RenderError(" ".join(cmd) + "\n" + r.stderr[-3000:])
        os.chmod(tmp, 0o755)
        os.replace(tmp, FILM)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return FILM


def replay(tool, path, ghost_out=None):
    cmd = [tool, path] + (["--ghost", ghost_out] if ghost_out else [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RenderError(f"{os.path.basename(tool)} refused {path}: {r.stderr.strip()[-300:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def verified(res, gid, path):
    if not (res.get("game") == gid and res.get("hash_matches") and res.get("complete") and res.get("claims_match")):
        raise RenderError(f"{path} does not verify with {gid}'s replay tool: {res}")
    return res


def windows_path(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, check=True).stdout.strip()


def encode(video, audio_wav, out_mp4, size, scale, ffmpeg=FFMPEG):
    """Raw RGB24 frames (through stdin) and the WAV into an H.264 mp4 at 60 fps, scaled up scale times with nearest
    neighbour (crisp pixels; 4 x 4 blocks keep yuv420p's chroma inside one GBA pixel)."""
    win = ffmpeg.lower().endswith(".exe")
    w, h = size
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-framerate", str(FPS), "-i", "-"]
    if audio_wav:
        cmd += ["-i", windows_path(audio_wav) if win else audio_wav]
    cmd += ["-vf", f"scale={w * scale}:{h * scale}:flags=neighbor,"
                   "scale=out_color_matrix=bt709:out_range=tv:flags=neighbor+accurate_rnd,format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-color_range", "tv", "-r", str(FPS)]
    if audio_wav:
        cmd += ["-c:a", "aac", "-b:a", "256k"]
    cmd += ["-movflags", "+faststart", windows_path(out_mp4) if win else out_mp4]
    with open(video, "rb") as src:
        r = subprocess.run(cmd, stdin=src)
    if r.returncode != 0:
        raise RenderError(f"ffmpeg failed ({r.returncode}) on {out_mp4}")


# ---- the render -----------------------------------------------------------------------------------------------------

def read_log(path):
    with open(path, "rb") as f:
        data = f.read()
    try:
        return data, S.parse_log_header(data[:32])
    except Exception as e:                 # a short file, another magic
        raise RenderError(f"{path} is not a run log ({e})") from None


def render(run_path, ghost_path=None, best_path=None, name=None, run_label=None, ghost_label=None, scale=4,
           tail_s=4.0, audio=True, out_dir=OUT, keep=False, board_cache=BOARD_CACHE):
    log, head = read_log(run_path)
    gid = head["game"].decode("ascii")
    game = next((g for g, a in ARCADE.items() if a[3] == gid), None)
    if game is None or gid not in ELF:
        raise RenderError(f"{gid} is not an arcade game here")
    rom, elf = os.path.join(BUILT, ARCADE[game][0]), os.path.join(REPO, ELF[gid])
    with open(rom, "rb") as f:
        rom_h = sha(f.read())
    with open(os.path.splitext(elf)[0] + ".gba", "rb") as f:
        if sha(f.read()) != rom_h:
            raise RenderError(f"{elf} was not built with {rom}: its symbols may be elsewhere (rebuild, or redeploy)")
    tool = os.path.join(TOOLS, gid, "arcade_replay")
    run = verified(replay(tool, run_path), gid, run_path)
    known = known_logs(board_cache)
    run_h = sha(log)
    driver, run_bot, run_known = who(run_h, known, run_label)
    ghost = ghost_res = ghost_known = None
    ghost_name, ghost_bot = None, False
    with tempfile.TemporaryDirectory() as tmp:
        if ghost_path:
            glog, ghead = read_log(ghost_path)
            if ghead["game"] != head["game"]:
                raise RenderError(f"the ghost is a {ghead['game'].decode()} run, not {gid}")
            ghost_res = verified(replay(tool, ghost_path, os.path.join(tmp, "ghost.acg")), gid, ghost_path)
            with open(os.path.join(tmp, "ghost.acg"), "rb") as f:
                ghost = f.read()
            ghost_name, ghost_bot, ghost_known = who(sha(glog), known, ghost_label)
        best_res = verified(replay(tool, best_path), gid, best_path) if best_path else None
    if name is None:
        name = f"{gid}_{driver}_{clock(run['time_frames']) if run.get('finished') else 'unfinished'}"
        if ghost_name:
            name += f"_vs_{ghost_name}_ghost"
    if run_bot and "BOT" not in name.upper():
        raise RenderError(f"{name}: a BOT's run must say BOT in its name")

    nonce, boots = profile_seed(head["seed"])
    save = S.blank()
    S.fmt(save, head["game"])
    S.put(save, S.PROFILE, profile_bytes(nonce, boots, best_res["trophies"] if best_res else 0))
    if ghost:
        S.put(save, S.GHOST, ghost)
    if best_path:                          # the cartridge's best before this run: BEST and the RUN it came from
        with open(best_path, "rb") as f:
            S.put(save, S.RUN, f.read())
        S.put(save, S.BEST, (best_res["time_frames"].to_bytes(4, "little") + best_res["score"].to_bytes(4, "little")
                             + best_res["trophies"].to_bytes(4, "little")
                             + best_res["final_hash"].to_bytes(4, "little") + bytes(16)))
    keys = T.decode_log(log)
    if len(keys) != head["frames"]:
        raise RenderError(f"{run_path}: {len(keys)} steps in the body, {head['frames']} in the header")

    work = os.path.join(WORK, name)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    with open(os.path.join(work, "steps.bin"), "wb") as f:
        f.write(b"".join(k.to_bytes(2, "little") for k in keys))
    with open(os.path.join(work, "cart.sav"), "wb") as f:
        f.write(bytes(save))
    addrs = T.symbols(elf, "g_dbg_steps", "g_dbg_hash", "g_dbg_seed")
    video, pcm = os.path.join(work, "video.rgb"), os.path.join(work, "audio.pcm")
    cmd = [build_film(), rom, os.path.join(work, "steps.bin"), "--steps-addr", "%x" % addrs["g_dbg_steps"],
           "--hash-addr", "%x" % addrs["g_dbg_hash"], "--seed-addr", "%x" % addrs["g_dbg_seed"],
           "--save-in", os.path.join(work, "cart.sav"), "--tail", str(round(tail_s * FPS)),
           "--max-frames", str(len(keys) + 3600), "--video", video]
    if audio:
        cmd += ["--audio", pcm, "--rate", repr(SAMPLES * GBA_HZ / GBA_FRAME)]
    print("render: playing %s (%d steps) on %s" % (os.path.basename(run_path), len(keys), os.path.basename(rom)),
          flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RenderError(f"gba_film failed ({r.returncode}): {r.stderr.strip()[-500:]} {r.stdout.strip()[-300:]}")
    film = json.loads(r.stdout.strip().splitlines()[-1])
    if (film["hash_at_end"], film["seed"]) != (head["final_hash"], head["seed"]):
        raise RenderError("the ROM did not replay the run: final hash %08x (the log's %08x), seed %08x (%08x); "
                          "no video. Files in %s" % (film["hash_at_end"], head["final_hash"], film["seed"],
                                                     head["seed"], work))
    wav = None
    if audio:
        wav = os.path.join(work, "audio.wav")
        with open(pcm, "rb") as f, wave.open(wav, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            sound = f.read()[:film["frames"] * SAMPLES * 4]
            # mGBA's resampler holds back a few samples: silence at the end makes the sound exactly the video's length
            w.writeframes(sound + bytes(film["frames"] * SAMPLES * 4 - len(sound)))
    os.makedirs(out_dir, exist_ok=True)
    mp4, side = os.path.join(out_dir, name + ".mp4"), os.path.join(out_dir, name + ".json")
    print(f"render: encoding {film['frames']} frames to {mp4}", flush=True)
    encode(video, wav, mp4, (film["width"], film["height"]), scale)

    def person(k, label, bot):
        return {"label": label, "bot": bot, "board": k.get("board"), "book": k.get("book"), "human": k.get("human"),
                "credential": k.get("credential"), "run_key": k.get("run"), "listing": k.get("listing"),
                "ghostgen": k.get("bot")}
    data = {
        "name": name, "video": os.path.basename(mp4), "rendered_at": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "fps": FPS, "size": [film["width"] * scale, film["height"] * scale], "scale": scale, "frames": film["frames"],
        "duration_s": round(film["frames"] / FPS, 3),
        "audio": {"rate": RATE, "samples": film["audio_samples"], "note": "mGBA's mix, 800 samples a frame: 60 fps, "
                  "0.45% above the GBA's own 59.73 fps and pitch"} if audio else None,
        "game": gid, "rom": rom, "rom_sha256": rom_h,
        "run": {"log": os.path.abspath(run_path), "log_h": run_h, "time_frames": run.get("time_frames"),
                "finished": run.get("finished"), "seed": head["seed"], "final_hash": "%08x" % head["final_hash"],
                "steps": head["frames"], **person(run_known, driver, run_bot)},
        "ghost": None if not ghost else {
            "log": os.path.abspath(ghost_path), "log_h": sha(glog), "time_frames": ghost_res.get("time_frames"),
            **person(ghost_known, ghost_name, ghost_bot)},
        "best_in_cart": None if not best_res else {"log": os.path.abspath(best_path), "time_frames":
                                                    best_res["time_frames"]},
        "verified": {"replay_tool": True, "rom_final_hash": "%08x" % film["hash_at_end"],
                     "rom_seed": "%08x" % film["seed"], "profile": {"nonce": nonce, "boots_written": boots}},
        "finish_frame": film["end_frame"], "finish_s": round(film["end_frame"] / FPS, 3),
    }
    with open(side, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    if not keep:
        shutil.rmtree(work)
    return data


def main(argv=None):
    p = argparse.ArgumentParser(prog="render_race.py", description=__doc__.split("\n\n")[0])
    p.add_argument("run", help="the run's log (.acl)")
    p.add_argument("--ghost", help="the ghost's log (.acl): her run, raced as the console races a ghost")
    p.add_argument("--best", help="a log the cartridge held as its best before this run (title and results show it)")
    p.add_argument("--name", help="the output's name (default: game_driver_time_vs_ghost_ghost)")
    p.add_argument("--run-label", help="the run's driver, for a log on no board (a BOT's is BOT-... regardless)")
    p.add_argument("--ghost-label", help="the ghost's driver, likewise")
    p.add_argument("--scale", type=int, default=4, choices=(1, 2, 3, 4, 5, 6), help="nearest-neighbour scale (4)")
    p.add_argument("--tail-s", type=float, default=4.0, help="seconds after the run's end (4)")
    p.add_argument("--no-audio", dest="audio", action="store_false")
    p.add_argument("--board", default=BOARD_CACHE, help=f"the board the logs are looked up on ({BOARD_CACHE})")
    p.add_argument("--out", default=OUT, help=f"where the video and sidecar go ({OUT})")
    p.add_argument("--keep", action="store_true", help=f"keep the raw frames and sound ({WORK}/<name>)")
    a = p.parse_args(argv)
    try:
        d = render(a.run, a.ghost, a.best, a.name, a.run_label, a.ghost_label, a.scale, a.tail_s, a.audio, a.out,
                   a.keep, a.board)
    except RenderError as e:
        print(f"render: {e}", file=sys.stderr)
        return 1
    print("render: %s: %d frames (%.1f s), run %s by %s%s, final hash %s matches" % (
        d["name"], d["frames"], d["duration_s"], d["run"]["time_frames"], d["run"]["label"],
        f" vs {d['ghost']['label']}'s ghost" if d["ghost"] else "", d["verified"]["rom_final_hash"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

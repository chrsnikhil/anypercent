"""The arcade bridge: before an arcade game runs, write the player's profile and the best run's ghost into the
cartridge save the emulator keeps next to the ROM (mGBA: <rom>.sav; RetroArch, configured by the runner to keep
saves in the content directory: <rom>.srm); after it, take the last run's log out of the save, verify it with the
game's replay tool and queue it (and keep it as the new best when it is faster).

A run is verified when the replay tool reports the arcade id's game, hash_matches (the replayed final hash is the
claimed one), complete (every claimed frame replayed) and claims_match (the claimed score and trophies are the
replayed ones). The tool runs with a timeout; a replay that times out verifies nothing.

runs_dir/queue/<ID>-<final_hash:08x>.acl + .json   verified runs waiting to be submitted
runs_dir/seen/<ID>-<final_hash:08x>                every run ever verified (its result JSON): never queued twice
runs_dir/best/<ID>.acl + .json                      the fastest finished run (the ghost's source); a best from older
                                                    rules (the replay tool no longer opens it) is replaced by the next
                                                    finished run

The profile's trophies are the OR of the trophies of every verified run of that game (seen/). Every launch also
writes a fresh random seed nonce (and boot count 0) into the profile: the ROM seeds each boot's run from it and the
boot count (arcade/src/ac_rng.h ac_seed_mix), so every run, including one started again from the results, plays a
different game; the seed is in the run log's header, so the replay tool still verifies it.
A save of at least 32 KB is kept: its first 32 KB (the game's SRAM) is edited and anything after it (an emulator's
own data) is left as it is; a shorter or missing save is replaced by a blank 32 KB one.

For the coach (coach.py), after() also returns res["vs_best"] = {best_frames, splits}: the time of the best this run
is measured against (the one it replaced, for a new best; None when there is none under these rules) and where it
lost time against that best's ghost. It is worked out from the two logs with the replay tool, never stored, and a
comparison that fails leaves splits None and the run verified as before."""
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.environ.get("ARCADE_PY") or os.path.join(os.path.dirname(__file__), "..", "..", "arcade", "py"))
import arcade_save as S  # noqa: E402

from . import coach  # noqa: E402


REPLAY_TIMEOUT = 60        # seconds for one replay (a verify or a ghost); a log claims at most an hour of frames


def sav_path(rom_path, emulator="mgba"):
    return os.path.splitext(rom_path)[0] + (".srm" if emulator == "retroarch" else ".sav")


def _header_ok(save, game):
    return (bytes(save[S.BASE:S.BASE + 4]) == b"ACSV" and struct.unpack_from("<H", save, S.BASE + 4)[0] == S.VERSION
            and bytes(save[S.BASE + 6:S.BASE + 10]) == game)


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


class Bridge:
    def __init__(self, runs_dir, profile_name="PLAYER", profile_tag=b"\0" * 8, replay_runner=subprocess.run,
                 emulator="mgba"):
        self.runs_dir = runs_dir
        self.profile_name, self.profile_tag = profile_name, profile_tag
        self.replay_runner = replay_runner
        self.emulator = emulator

    def _dir(self, name):
        return os.path.join(self.runs_dir, name)

    def _best(self, gid):
        return os.path.join(self._dir("best"), gid + ".acl"), os.path.join(self._dir("best"), gid + ".json")

    def _replay(self, arcade, log_path, *extra):
        try:
            r = self.replay_runner([arcade["replay"], log_path, *extra], capture_output=True, text=True,
                                   timeout=REPLAY_TIMEOUT)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip().splitlines()[-1])

    def _rules_version(self, log_path):
        """The rules version in a stored log's header; None when it is missing or unreadable."""
        try:
            with open(log_path, "rb") as f:
                return S.parse_log_header(f.read(32))["rules_version"]
        except (OSError, AssertionError, struct.error):
            return None

    def _seen(self, gid, final_hash):
        return os.path.join(self._dir("seen"), "%s-%08x" % (gid, final_hash))

    def _trophies(self, gid):
        """The OR of the trophies of every verified run of the game."""
        seen, out = self._dir("seen"), 0
        if os.path.isdir(seen):
            for name in os.listdir(seen):
                if name.startswith(gid + "-"):
                    try:
                        with open(os.path.join(seen, name), encoding="utf-8") as f:
                            out |= int(json.load(f).get("trophies", 0))
                    except (OSError, ValueError):
                        continue
        return out

    def history(self, gid, n=5):
        """The times of the game's last n finished, verified runs, oldest first."""
        seen, out = self._dir("seen"), []
        if os.path.isdir(seen):
            for name in os.listdir(seen):
                if name.startswith(gid + "-"):
                    path = os.path.join(seen, name)
                    try:
                        with open(path, encoding="utf-8") as f:
                            d = json.load(f)
                        if d.get("finished"):
                            out.append((d.get("verified_at", 0), os.path.getmtime(path), int(d["time_frames"])))
                    except (OSError, ValueError, KeyError, TypeError):
                        continue
        return [t for _, _, t in sorted(out)][-n:]

    def ghost_bytes(self, arcade, log_path):
        """The raw ghost payload the replay tool draws from a log (its --ghost output), or None on any failure."""
        fd, path = tempfile.mkstemp(suffix=".acg")
        os.close(fd)
        try:
            if self._replay(arcade, log_path, "--ghost", path) is None:
                return None
            with open(path, "rb") as f:
                data = f.read()
            return data if data else None
        finally:
            os.unlink(path)

    def ghost(self, arcade, log_path):
        """The ghost the replay tool draws from a log (arcade_save.parse_ghost), or None."""
        data = self.ghost_bytes(arcade, log_path)
        return S.parse_ghost(data) if data else None

    def log_time(self, arcade, log_path):
        """A finished log's claimed time_frames from the replay tool's JSON; None when the run is unfinished, the
        tool fails, the JSON lacks the field, or the log is missing."""
        if not os.path.isfile(log_path):
            return None
        res = self._replay(arcade, log_path)
        if not res or not res.get("finished"):
            return None
        return res.get("time_frames")

    def _load_save(self, path):
        """(the first 32 KB as a bytearray, the bytes after it) of the save at path; a blank save if it is missing
        or shorter than 32 KB."""
        data = b""
        if os.path.isfile(path):
            with open(path, "rb") as f:
                data = f.read()
        if len(data) < S.SIZE:
            return S.blank(), b""
        return bytearray(data[:S.SIZE]), data[S.SIZE:]

    def before(self, rom_path, arcade, ghost=None):
        """Writes the profile and (unless ghost overrides it) the best run's ghost into the game's save. ghost, when
        given, is raced as-is and the best log is never replayed."""
        game = arcade["id"].encode("ascii")
        path = sav_path(rom_path, self.emulator)
        save, tail = self._load_save(path)
        if not _header_ok(save, game):
            S.fmt(save, game)                      # writes the table at 0x100 only; bytes 0..0xFF are the game's
        nonce = secrets.randbits(32) or 1                       # 0 would mean the classic, unseeded game
        S.put(save, S.PROFILE, S.profile_bytes(self.profile_name, self.profile_tag, self._trophies(arcade["id"]),
                                               seed_nonce=nonce))
        if ghost is not None:
            S.put(save, S.GHOST, ghost)
        else:
            best_log, _ = self._best(arcade["id"])
            if os.path.isfile(best_log):
                data = self.ghost_bytes(arcade, best_log)
                if data:
                    S.put(save, S.GHOST, data)
        _write(path, bytes(save) + tail)

    def after(self, rom_path, arcade):
        gid = arcade["id"]
        path = sav_path(rom_path, self.emulator)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            save = bytearray(f.read()[:S.SIZE])
        if len(save) < S.SIZE:
            return None
        run = S.get(save, gid.encode("ascii"), S.RUN)
        if run is None:
            return None
        log, flags = run
        if flags & S.TRUNCATED:
            return None
        claimed = S.parse_log_header(log)["final_hash"]
        queue = self._dir("queue")
        stem = os.path.join(queue, "%s-%08x" % (gid, claimed))
        seen = self._seen(gid, claimed)
        if os.path.exists(stem + ".acl") or os.path.exists(seen):
            return None                            # already verified (and queued, or queued and submitted)
        os.makedirs(queue, exist_ok=True)
        part = stem + ".acl.part"                  # the replay tool reads a file; it becomes .acl once verified
        _write(part, log)
        try:
            res = self._replay(arcade, part)
            if not res or not (res.get("game") == gid and res.get("hash_matches") and res.get("complete")
                               and res.get("claims_match")):
                return None
            res["rom"] = rom_path                  # hash_matches: final_hash == the claimed hash in the name
            _write(stem + ".json", json.dumps(res).encode("utf-8"))
            os.replace(part, stem + ".acl")
            os.makedirs(self._dir("seen"), exist_ok=True)
            _write(seen, json.dumps(dict(res, verified_at=time.time())).encode("utf-8"))
        finally:
            if os.path.exists(part):
                os.unlink(part)
        best_log, best_json = self._best(gid)
        best = None
        if os.path.isfile(best_json) and self._rules_version(best_log) == S.parse_log_header(log)["rules_version"]:
            with open(best_json, encoding="utf-8") as f:
                best = json.load(f)
        vs_best = {"best_frames": best["time_frames"] if best else None, "splits": None}
        if best is not None:                       # before a new best replaces it
            try:
                vs_best["splits"] = coach.compare(self.ghost(arcade, stem + ".acl"), self.ghost(arcade, best_log),
                                                  finished=bool(res.get("finished")))
            except Exception:                      # coaching is a nicety: it never costs a verified run
                vs_best["splits"] = None
        res["new_best"] = False
        if res.get("finished"):
            if best is None or res["time_frames"] < best["time_frames"]:
                os.makedirs(self._dir("best"), exist_ok=True)
                res["new_best"] = True
                shutil.copyfile(stem + ".acl", best_log)
                _write(best_json, json.dumps(res).encode("utf-8"))
        res["vs_best"] = vs_best
        return res

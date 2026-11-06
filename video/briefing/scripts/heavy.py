"""Run a heavy job (a Remotion render or still, an ffmpeg encode) only when no other one is running: the laptop takes one
heavy job at a time (it blue-screens otherwise). Several agents can call this at once; they queue on a lock directory.

  python scripts/heavy.py <command ...>        e.g.  python scripts/heavy.py npx remotion still src/index.ts SponsorArkiv out/x.png --frame=300

The lock is out/.heavy.lock (a directory: making one is atomic). A lock older than 45 min is taken as stale (a crashed
job) and broken. The command's exit code is passed through."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(HERE, "out", ".heavy.lock")
STALE = 45 * 60


def release():
    for p, rm in ((os.path.join(LOCK, "owner"), os.remove), (LOCK, os.rmdir)):
        try:
            rm(p)
        except FileNotFoundError:
            pass


def acquire(who):
    waited = 0
    while True:
        try:
            os.mkdir(LOCK)
            open(os.path.join(LOCK, "owner"), "w").write(f"{who}\n{time.time()}\n")
            return waited
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > STALE:
                    print("heavy: breaking a stale lock", file=sys.stderr)
                    release()
                    continue
            except FileNotFoundError:
                continue
            time.sleep(3)
            waited += 3
            if waited % 60 == 0:
                print(f"heavy: waiting for the lock ({waited} s)", file=sys.stderr, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if not cmd:
        sys.exit(__doc__)
    w = acquire(" ".join(cmd)[:200])
    if w:
        print(f"heavy: got the lock after {w} s", file=sys.stderr)
    try:
        code = subprocess.call(subprocess.list2cmdline(cmd) if os.name == "nt" else cmd, shell=os.name == "nt")
    finally:
        release()
    sys.exit(code)

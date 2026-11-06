"""Deploy the launcher and device files to the Any% handheld in one step.

  python device/deploy.py               test, sync, apply, restart, check
  python device/deploy.py --dry-run     test, then list what would change on the Pi; change nothing
  python device/deploy.py --rollback    put back the copy the last deploy replaced
  options: --no-tests (skip the test suite), --no-restart (leave the launcher running as it is)

What happens:
  1. the launcher's tests (launcher/dev/pytest.sh in the WSL sandbox); any failure stops the deploy
  2. SSH with the laptop's key (anypercent_ssh); a Pi in read-only mode is refused (readonly.sh off first)
  3. launcher/, device/ and arcade/py/ (the save-format module the launcher's arcade bridge imports) are packed,
     sent and swapped into /opt/anypercent/src in one move each; the copy they replace is kept in
     /opt/anypercent/src.prev for --rollback
  4. device/apply.sh puts units, tools, udev rules and settings in place, installs the console signer's Node packages
     (launcher/arkiv_signer) when its package-lock.json is new, and says which units changed
  5. changed services restart; the launcher restarts unless a game or app is running (then it picks the new code
     up when it next starts)
  6. a check: the launcher and the home key are running and the launcher logged no traceback
Game data, the library, saves and runs are never touched."""
import argparse
import io
import os
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = "/opt/anypercent/src"
PREV = "/opt/anypercent/src.prev"
DIRS = ("launcher", "device", "arcade/py")     # arcade/py: the bridge imports ../../arcade/py/arcade_save.py
# node_modules: the console signer's npm packages (launcher/arkiv_signer) are installed on the Pi by apply.sh, never
# sent from the laptop (WSL's tree is ~74 MB with an x86 esbuild in it)
SKIP_DIRS = {"__pycache__", ".pytest_cache", "out", "tests", "node_modules"}
SKIP_FILES = (".pyc", ".pulled")
# these drive the Pi from the laptop; the Pi has no use for them
LAPTOP_ONLY = {"deploy.py", "push.py", "remote_keys.py", "anypercent_ssh.py", "anypercent_host_key.pub",
               "booth_check.py"}
ALWAYS_RESTART = ("anypercent-homekey.service",)
# apply.sh's first run after the console signer arrived installs nodejs and npm with apt and the signer's packages with
# npm ci: minutes on a Pi 3B+. Its progress lines (": " after a tag) are printed as they come.
APPLY_TIMEOUT_S = 1800


def files(repo=REPO):
    """(local path, archive name) for everything sent: DIRS without caches, tests, test output."""
    out = []
    for d in DIRS:
        for root, dirs, names in os.walk(os.path.join(repo, d)):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            for n in sorted(names):
                if n.endswith(SKIP_FILES) or (d == "device" and n in LAPTOP_ONLY):
                    continue
                path = os.path.join(root, n)
                out.append((path, os.path.relpath(path, repo).replace(os.sep, "/")))
    return out


def mode_for(name):
    """Windows keeps no Unix modes, so they are set here: device/ scripts (.sh, .py, and the extensionless app
    wrappers like anypercent-gta3 and ssh-switch) are executable, everything else is not."""
    base = os.path.basename(name)
    if name.startswith("device/") and (base.endswith((".sh", ".py")) or "." not in base):
        return 0o755
    return 0o644


def pack(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, name in entries:
            info = tar.gettarinfo(path, name)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = mode_for(name)
            with open(path, "rb") as f:
                tar.addfile(info, f)
    return buf.getvalue()


def changed_units(apply_output):
    for line in apply_output.splitlines():
        if line.startswith("changed:"):
            return line.split(":", 1)[1].split()
    return []


def run_tests():
    print("== tests", flush=True)
    if os.name == "nt":
        launcher = "/mnt/" + REPO[0].lower() + REPO[2:].replace("\\", "/") + "/launcher"
        cmd = ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", f"cd '{launcher}' && bash dev/pytest.sh -q"]
    else:
        cmd = ["bash", "-c", f"cd '{os.path.join(REPO, 'launcher')}' && bash dev/pytest.sh -q"]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    print("   " + "\n   ".join(tail))
    if r.returncode != 0:
        sys.exit("tests failed: nothing was deployed")


class Pi:
    def __init__(self):
        sys.path.insert(0, HERE)
        import anypercent_ssh
        self.c, self.host = anypercent_ssh.connect()
        print("== connected to", self.host, flush=True)

    def stream(self, cmd, timeout):
        """Run cmd, printing each output line as it comes (a long first apply shows its progress, never a silent SSH
        timeout); exits on a failure like run(). Returns the output."""
        _, o, e = self.c.exec_command(cmd, timeout=timeout)
        lines = []
        for line in o:
            lines.append(line.rstrip("\n"))
            if not line.startswith("changed:"):
                print("   " + line.rstrip(), flush=True)
        err, code = e.read().decode(), o.channel.recv_exit_status()
        if code:
            sys.exit(f"on the Pi, failed ({code}): {cmd}\n" + "\n".join(lines) + err)
        return "\n".join(lines + [err]).strip()

    def run(self, cmd, check=True, timeout=300):
        _, o, e = self.c.exec_command(cmd, timeout=timeout)
        out, err, code = o.read().decode(), e.read().decode(), o.channel.recv_exit_status()
        if check and code:
            sys.exit(f"on the Pi, failed ({code}): {cmd}\n{out}{err}")
        return (out + err).strip()

    def busy(self):
        """A game or app is on screen (so the launcher is not restarted under it)."""
        apps = self.run("systemctl is-active anypercent-gta3 anypercent-browser", check=False).split()
        return "active" in apps or bool(self.run("pgrep -x retroarch || pgrep -x mgba-qt", check=False))


def swap_in(pi, tar_path):
    pi.run(f"sudo rm -rf /tmp/anypercent-deploy && sudo mkdir -p /tmp/anypercent-deploy && "
           f"sudo tar -xzf {tar_path} -C /tmp/anypercent-deploy")      # as root: the files stay root's
    summary = pi.run("cd /tmp/anypercent-deploy && for d in " + " ".join(DIRS) +
                     f"; do diff -rq --exclude=__pycache__ {SRC}/$d $d 2>/dev/null; done | wc -l", check=False)
    print(f"   {summary.strip() or 0} files differ", flush=True)
    for d in DIRS:                                  # a nested one (arcade/py) needs its parents on both sides
        pi.run(f"sudo mkdir -p $(dirname {PREV}/{d}) $(dirname {SRC}/{d}) && sudo rm -rf {PREV}/{d} && "
               f"(sudo mv {SRC}/{d} {PREV}/{d} 2>/dev/null || true) && sudo mv /tmp/anypercent-deploy/{d} {SRC}/{d}")


def apply(pi):
    """device/apply.sh on the Pi, its progress printed as it runs, with room for a first apt and npm install."""
    return pi.stream(f"sudo bash {SRC}/device/apply.sh", timeout=APPLY_TIMEOUT_S)


def restart(pi, units, restart_launcher):
    for u in sorted(set(units) | set(ALWAYS_RESTART)):
        if u in ("anypercent-launcher.service", "anypercent-browser.service", "anypercent-gta3.service"):
            continue                                                # the launcher below; apps start on demand
        pi.run(f"sudo systemctl restart {u}", check=False)
        print("   restarted", u)
    if not restart_launcher:
        print("   launcher left running (it loads the new code at its next start)")
        return False
    if pi.busy():
        print("   a game or app is running: the launcher picks up the new code when it next starts")
        return False
    pi.run("sudo systemctl restart anypercent-launcher")
    print("   restarted anypercent-launcher.service")
    return True


def check(pi, since):
    time.sleep(6)
    states = pi.run("systemctl is-active anypercent-launcher anypercent-homekey", check=False).split()
    tb = pi.run(f"journalctl -u anypercent-launcher --since '@{since}' --no-pager | grep -c Traceback", check=False)
    ok = states == ["active", "active"] and tb.strip() in ("", "0")
    print(f"== check: launcher {states[0] if states else '?'}, home key {states[1] if len(states) > 1 else '?'}, "
          f"tracebacks {tb.strip() or 0}: {'OK' if ok else 'PROBLEM (python device/deploy.py --rollback)'}")
    return ok


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--no-tests", action="store_true")
    p.add_argument("--no-restart", action="store_true")
    a = p.parse_args(argv)

    if not (a.no_tests or a.rollback):
        run_tests()
    pi = Pi()
    if pi.run("findmnt -n -o FSTYPE /", check=False).strip() == "overlay":
        sys.exit("the Pi is in read-only mode: sudo sh /opt/anypercent/src/device/readonly.sh off, reboot, deploy")
    since = int(pi.run("date +%s"))

    if a.rollback:
        print("== rollback", flush=True)
        for d in DIRS:                              # a folder with no previous copy (first deploy of it) is skipped
            pi.run(f"if [ -d {PREV}/{d} ]; then sudo rm -rf {SRC}/{d}.new && sudo mv {SRC}/{d} {SRC}/{d}.new && "
                   f"sudo mv {PREV}/{d} {SRC}/{d} && sudo mv {SRC}/{d}.new {PREV}/{d}; fi")
    else:
        entries = files()
        data = pack(entries)
        print(f"== sending {len(entries)} files ({len(data) // 1024} KB)", flush=True)
        if a.dry_run:
            s = pi.c.open_sftp()
            with s.open("/tmp/anypercent-deploy.tgz", "wb") as f:
                f.write(data)
            print(pi.run("rm -rf /tmp/anypercent-dry && mkdir /tmp/anypercent-dry && "
                         "tar -xzf /tmp/anypercent-deploy.tgz -C /tmp/anypercent-dry && cd /tmp/anypercent-dry && "
                         "for d in " + " ".join(DIRS) + f"; do diff -rq --exclude=__pycache__ {SRC}/$d $d; done",
                         check=False) or "   no changes")
            return 0
        s = pi.c.open_sftp()
        with s.open("/tmp/anypercent-deploy.tgz", "wb") as f:
            f.write(data)
        swap_in(pi, "/tmp/anypercent-deploy.tgz")

    print("== apply", flush=True)
    out = apply(pi)
    units = changed_units(out)
    print("   units changed:", " ".join(units) or "none")
    restart(pi, units, not a.no_restart)
    return 0 if check(pi, since) else 1


if __name__ == "__main__":
    sys.exit(main())

"""device/deploy.py: what it sends and how it reads apply.sh (the SSH side needs the Pi)."""
import importlib.util
import io
import os
import tarfile

from conftest import LAUNCHER_DIR

REPO = os.path.dirname(LAUNCHER_DIR)
spec = importlib.util.spec_from_file_location("deploy", os.path.join(REPO, "device", "deploy.py"))
dp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dp)


def test_it_sends_the_launcher_code_and_the_device_files_only():
    names = [n for _, n in dp.files(REPO)]
    assert "launcher/arca_launcher/app.py" in names and "device/apply.sh" in names and "device/homekey.py" in names
    assert not any("/tests/" in n or "__pycache__" in n or n.endswith(".pyc") for n in names)
    assert not any(n.split("/")[0] not in ("launcher", "device", "arcade") for n in names)


def test_it_sends_the_arcade_save_module_the_bridge_imports():
    """The launcher's arcade bridge imports arcade/py/arcade_save.py (../../arcade/py on the Pi): a profile format
    change (the seed nonce) must reach the Pi with the launcher, and only that folder of arcade/ is sent."""
    names = [n for _, n in dp.files(REPO)]
    assert "arcade/py/arcade_save.py" in names
    assert not any(n.startswith("arcade/") and not n.startswith("arcade/py/") for n in names)


def test_laptop_tools_and_pulled_configs_stay_behind():
    names = {n for _, n in dp.files(REPO)}
    assert "device/deploy.py" not in names and "device/remote_keys.py" not in names
    assert "device/booth_check.py" not in names                    # run from the laptop, against the Pi
    assert not any(n.endswith(".pulled") for n in names)


def test_scripts_are_executable_and_the_rest_is_not():
    assert dp.mode_for("device/apply.sh") == 0o755
    assert dp.mode_for("device/homekey.py") == 0o755
    assert dp.mode_for("device/anypercent-gta3") == 0o755
    assert dp.mode_for("device/ssh-switch") == 0o755
    assert dp.mode_for("device/anypercent-gta3.service") == 0o644
    assert dp.mode_for("launcher/arca_launcher/app.py") == 0o644


def test_the_archive_is_root_owned_with_those_modes(tmp_path):
    f = tmp_path / "apply.sh"
    f.write_text("#!/bin/sh\n")
    data = dp.pack([(str(f), "device/apply.sh")])
    info = tarfile.open(fileobj=io.BytesIO(data)).getmember("device/apply.sh")
    assert (info.uid, info.gid, info.mode) == (0, 0, 0o755)


def test_changed_units_come_from_apply_sh():
    out = "something\nchanged: anypercent-homekey.service anypercent-launcher.service \n"
    assert dp.changed_units(out) == ["anypercent-homekey.service", "anypercent-launcher.service"]
    assert dp.changed_units("changed: \n") == []
    assert dp.changed_units("") == []


def test_the_console_signer_is_sent_without_its_npm_packages():
    """launcher/arkiv_signer goes to the Pi as source and lockfile; apply.sh installs its packages there (npm ci), so
    the laptop's node_modules (an x86 tree of ~74 MB) is never sent."""
    names = {n for _, n in dp.files(REPO)}
    for name in ("signer.mjs", "schemas.mjs", "package.json", "package-lock.json"):
        assert "launcher/arkiv_signer/" + name in names
    assert not any("node_modules" in n.split("/") for n in names)
    assert "node_modules" in dp.SKIP_DIRS



class _Channel:
    def __init__(self, code):
        self.code = code

    def recv_exit_status(self):
        return self.code


class _Out:
    """paramiko's stdout as a file: its lines as they come, and its channel."""

    def __init__(self, lines, code=0):
        self.lines, self.channel = lines, _Channel(code)

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return "".join(self.lines).encode()


class _Err:
    def read(self):
        return b""


class _Client:
    def __init__(self, lines, code=0):
        self.lines, self.code, self.calls = lines, code, []

    def exec_command(self, cmd, timeout=None):
        self.calls.append((cmd, timeout))
        return None, _Out(self.lines, self.code), _Err()


def test_apply_gets_room_for_a_first_install_and_prints_its_progress_as_it_runs(capsys):
    """The first apply after the console signer arrived runs apt (nodejs, npm) and npm ci: minutes on a Pi 3B+. It
    must not hit the 300 s SSH timeout, and its progress lines show while it runs."""
    pi = dp.Pi.__new__(dp.Pi)
    pi.c = _Client(["signer: installing nodejs and npm with apt\n", "signer: packages installed\n",
                    "changed: anypercent-launcher.service \n"])
    out = dp.apply(pi)
    ((cmd, timeout),) = pi.c.calls
    assert cmd.endswith("/device/apply.sh") and timeout == dp.APPLY_TIMEOUT_S >= 1800
    shown = capsys.readouterr().out
    assert "signer: installing nodejs and npm with apt" in shown and "signer: packages installed" in shown
    assert dp.changed_units(out) == ["anypercent-launcher.service"]
    pi.c = _Client(["signer: npm ci\n"], code=1)
    import pytest
    with pytest.raises(SystemExit):
        dp.apply(pi)


def _signer_section(tmp_path, apt_fails):
    """device/apply.sh's signer section, run in bash over a fake /opt/anypercent with stub apt-get, dpkg and npm (no
    network). apt_fails: how many apt-get calls fail first, as on a held dpkg lock."""
    import shutil
    import subprocess
    import textwrap
    if shutil.which("bash") is None or shutil.which("flock") is None or os.name == "nt":
        import pytest
        pytest.skip("needs bash and flock")
    root, stubs, tools = tmp_path / "root", tmp_path / "stubs", tmp_path / "tools"
    signer = root / "src" / "launcher" / "arkiv_signer"
    signer.mkdir(parents=True)
    stubs.mkdir()
    tools.mkdir()
    for name in ("package.json", "package-lock.json"):
        (signer / name).write_text(open(os.path.join(LAUNCHER_DIR, "arkiv_signer", name)).read())
    (stubs / "apt-get").write_text(textwrap.dedent(f"""\
        #!/bin/bash
        echo "apt-get $*" >> {tmp_path}/calls
        n=$(cat {tmp_path}/apt-n 2>/dev/null || echo 0); echo $((n + 1)) > {tmp_path}/apt-n
        [ "$n" -lt {apt_fails} ] && exit 100
        if [[ " $* " == *" install "* ]]; then
            printf '#!/bin/bash\necho v20.19.2\n' > {tools}/node
            printf '#!/bin/bash\n[ "$1" = -v ] && echo 9.2.0 && exit 0\necho "npm $*" >> {tmp_path}/calls\n'\
'mkdir -p node_modules/@arkiv-network/sdk\n' > {tools}/npm
            chmod +x {tools}/node {tools}/npm
        fi
        """))
    (stubs / "dpkg").write_text(f"#!/bin/bash\necho \"dpkg $*\" >> {tmp_path}/calls\n")
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    text = open(os.path.join(REPO, "device", "apply.sh")).read()
    section = text[text.index("SIGNER=$ROOT"):text.index("\n# units\n")]
    script = tmp_path / "section.sh"
    script.write_text(f"ROOT={root}\n" + section)
    system = tmp_path / "system"                         # what the section needs, and no node or npm of the host's
    system.mkdir()
    for name in ("bash", "flock", "sha256sum", "cut", "cat", "cp", "mkdir", "rm", "mv", "ln", "sleep", "chmod"):
        os.symlink(shutil.which(name), system / name)
    env = dict(os.environ, PATH=f"{stubs}:{tools}:{system}", APT_RETRY_S="0",
               SIGNER_LOCK=str(tmp_path / "signer.lock"))
    done = subprocess.run([shutil.which("bash"), "-euo", "pipefail", str(script)], env=env, capture_output=True,
                          text=True)
    calls = (tmp_path / "calls").read_text().splitlines() if (tmp_path / "calls").exists() else []
    return done, calls, signer


def test_the_signer_install_waits_for_dpkg_tries_again_and_says_what_it_does(tmp_path):
    done, calls, signer = _signer_section(tmp_path, apt_fails=1)
    assert done.returncode == 0, done.stderr
    assert "signer: installing nodejs and npm with apt" in done.stdout
    assert "try 1 of 3" in done.stdout and "signer: packages installed" in done.stdout
    apt = [c for c in calls if c.startswith("apt-get")]
    assert len(apt) == 2 and all("DPkg::Lock::Timeout=" in c for c in apt)          # waits on dpkg's lock, then again
    assert any(c.startswith("dpkg --configure -a") for c in calls)                  # a cut-off install is finished
    assert [c for c in calls if c.startswith("npm ci")] == ["npm ci --omit=dev --no-audit --no-fund --loglevel=error"]
    assert (signer / "node_modules").is_symlink()


def test_the_signer_install_gives_up_with_a_warning_never_a_failed_apply(tmp_path):
    done, calls, signer = _signer_section(tmp_path, apt_fails=99)
    assert done.returncode == 0 and "nodejs and npm not installed" in done.stderr
    assert not (signer / "node_modules").exists()

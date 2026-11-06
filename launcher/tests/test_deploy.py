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

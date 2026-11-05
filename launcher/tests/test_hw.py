import os
import stat

from arca_launcher.hw import Hardware


def sysfs(tmp_path, battery=None, backlight_max=None):
    root = tmp_path / "sys"
    (root / "class" / "power_supply" / "AC").mkdir(parents=True)
    (root / "class" / "power_supply" / "AC" / "type").write_text("Mains\n")
    if battery is not None:
        bat = root / "class" / "power_supply" / "BAT0"
        bat.mkdir()
        (bat / "type").write_text("Battery\n")
        (bat / "capacity").write_text(f"{battery}\n")
    (root / "class" / "backlight").mkdir(parents=True)
    if backlight_max is not None:
        bl = root / "class" / "backlight" / "panel"
        bl.mkdir()
        (bl / "max_brightness").write_text(f"{backlight_max}\n")
        (bl / "brightness").write_text("0\n")
    return str(root)


def test_battery(tmp_path):
    assert Hardware(sysfs(tmp_path, battery=67)).battery_percent() == 67
    assert Hardware(sysfs(tmp_path / "x")).battery_percent() is None


def test_backlight(tmp_path):
    root = sysfs(tmp_path, backlight_max=255)
    hw = Hardware(root)
    assert hw.brightness_available()
    assert hw.set_brightness(50)
    assert open(os.path.join(root, "class", "backlight", "panel", "brightness")).read() == "128"


def test_no_backlight(tmp_path):
    hw = Hardware(sysfs(tmp_path))
    assert not hw.brightness_available()
    assert hw.set_brightness(50) is False


def test_volume_tries_master_then_pcm(tmp_path):
    log = tmp_path / "calls.txt"
    fake = tmp_path / "amixer"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {log}\n[ "$3" = "PCM" ]\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert Hardware(str(tmp_path), amixer=str(fake)).set_volume(50)
    assert log.read_text().splitlines() == ["-q sset Master 48%", "-q sset PCM 48%"]   # 50% of the 0 dB ceiling


def test_full_volume_stops_at_0db(tmp_path):
    # 100% on the slider is the mixer's 96%: 0 dB on the Pi's PCM; above that it adds digital gain and clips
    log = tmp_path / "calls.txt"
    fake = tmp_path / "amixer"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {log}\n[ "$3" = "PCM" ]\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert Hardware(str(tmp_path), amixer=str(fake)).set_volume(100)
    assert log.read_text().splitlines()[-1] == "-q sset PCM 96%"


def test_no_amixer_is_a_no_op(tmp_path):
    assert Hardware(str(tmp_path), amixer="").set_volume(40) is False


def test_volume_reaches_the_pis_headphone_control(tmp_path):
    log = tmp_path / "calls.txt"
    fake = tmp_path / "amixer"
    fake.write_text(f'#!/bin/sh\necho "$3" >> {log}\n[ "$3" = "Headphone" ]\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert Hardware(str(tmp_path), amixer=str(fake)).set_volume(40)
    assert log.read_text().splitlines() == ["Master", "PCM", "Headphone"]


def test_a_backlight_the_launcher_cannot_write_is_not_offered(tmp_path, monkeypatch):
    root = sysfs(tmp_path, backlight_max=255)
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda p, mode: False if p.endswith("brightness") else real_access(p, mode))
    assert not Hardware(root).brightness_available()     # tests run as root, so simulate a normal user's permissions


# --- the DualSense: its battery is not the console's, and its light bar -------------------------------------------

def pad_battery(root, pct=80):
    d = os.path.join(root, "class", "power_supply", "ps-controller-battery-50:ee:32:44:93:ba")
    os.makedirs(d)
    open(os.path.join(d, "type"), "w").write("Battery\n")
    open(os.path.join(d, "scope"), "w").write("Device\n")
    open(os.path.join(d, "capacity"), "w").write(f"{pct}\n")


def test_a_controllers_battery_is_not_the_consoles(tmp_path):
    root = sysfs(tmp_path)
    pad_battery(root, 95)
    hw = Hardware(root)
    assert hw.battery_percent() is None
    assert hw.controller_battery() == 95


def test_no_controller_battery_without_a_pad(tmp_path):
    assert Hardware(sysfs(tmp_path, battery=50)).controller_battery() is None


def test_light_bar_colour_is_written_to_every_pad(tmp_path):
    root = sysfs(tmp_path)
    led = os.path.join(root, "class", "leds", "input7:rgb:indicator")
    os.makedirs(led)
    for f, v in (("multi_intensity", "0 0 0"), ("brightness", "0"), ("max_brightness", "255")):
        open(os.path.join(led, f), "w").write(v + "\n")
    assert Hardware(root).set_lightbar((255, 133, 0)) is True
    assert open(os.path.join(led, "multi_intensity")).read().strip() == "255 133 0"
    assert open(os.path.join(led, "brightness")).read().strip() == "255"


def test_no_light_bar_is_a_no_op(tmp_path):
    assert Hardware(sysfs(tmp_path)).set_lightbar((1, 2, 3)) is False


# --- Wi-Fi and the Pi's power / heat warnings -------------------------------------------------------------------

WIRELESS = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   {link}.  -45.  -256        0      0      0     32      0        0
"""


def wifi_sys(tmp_path, state="up", link=65):
    root = sysfs(tmp_path)
    net = os.path.join(root, "class", "net", "wlan0")
    os.makedirs(os.path.join(net, "wireless"))
    open(os.path.join(net, "operstate"), "w").write(state + "\n")
    proc = str(tmp_path / "wireless")
    open(proc, "w").write(WIRELESS.format(link=link) if link is not None else WIRELESS.split("wlan0")[0])
    return Hardware(root, proc_wireless=proc)


def test_wifi_signal_as_a_percent(tmp_path):
    assert wifi_sys(tmp_path, link=70).wifi() == 100
    assert wifi_sys(tmp_path / "b", link=35).wifi() == 50


def test_wifi_down_is_zero(tmp_path):
    assert wifi_sys(tmp_path, state="down").wifi() == 0
    assert wifi_sys(tmp_path / "b", link=None).wifi() == 0             # up but not associated


def test_no_wifi_hardware_is_none(tmp_path):
    assert Hardware(sysfs(tmp_path), proc_wireless=str(tmp_path / "none")).wifi() is None


def fake_vcgencmd(tmp_path, value):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "vcgencmd"
    p.write_text(f"#!/bin/sh\necho throttled={value}\n")
    p.chmod(0o755)
    return Hardware(sysfs(tmp_path), vcgencmd=str(p))


def test_power_warning_from_the_firmware(tmp_path):
    assert fake_vcgencmd(tmp_path, "0x0").power_warning() is None
    assert fake_vcgencmd(tmp_path / "a", "0x50005").power_warning() == "Low power"       # under-voltage now
    assert fake_vcgencmd(tmp_path / "b", "0x80008").power_warning() == "Hot"             # soft temperature limit
    assert fake_vcgencmd(tmp_path / "c", "0x50000").power_warning() is None              # happened earlier, fine now


def test_hard_throttling_is_too_hot_and_low_power_still_comes_first(tmp_path):
    assert fake_vcgencmd(tmp_path / "a", "0x4").power_warning() == "Too hot"             # throttled now
    assert fake_vcgencmd(tmp_path / "b", "0xc").power_warning() == "Too hot"             # above the soft limit too
    assert fake_vcgencmd(tmp_path / "c", "0x5").power_warning() == "Low power"           # starved: the cause


def test_temperature_from_the_thermal_zone(tmp_path):
    root = sysfs(tmp_path)
    zone = tmp_path / "sys" / "class" / "thermal" / "thermal_zone0"
    zone.mkdir(parents=True)
    (zone / "temp").write_text("63412\n")
    assert Hardware(root).temperature() == 63
    assert Hardware(sysfs(tmp_path / "none")).temperature() is None


def test_no_vcgencmd_no_warning(tmp_path):
    assert Hardware(sysfs(tmp_path), vcgencmd="").power_warning() is None


def pi_hw(tmp_path):
    model = tmp_path / "model"
    model.write_text("Raspberry Pi 3 Model B Plus Rev 1.4\x00")
    return Hardware(sysfs(tmp_path), model_path=str(model))


def test_start_app_asks_systemd_for_its_service(tmp_path, monkeypatch):
    import subprocess
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **k: calls.append(args) or type("R", (), {"returncode": 0})())
    hw = pi_hw(tmp_path)
    assert hw.start_app("browser") is True
    assert calls == [["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "anypercent-browser.service"]]
    assert hw.start_app("not-an-app") is False and len(calls) == 1


def test_start_app_does_nothing_off_the_pi(tmp_path):
    assert Hardware(sysfs(tmp_path), model_path=str(tmp_path / "none")).start_app("browser") is False


def test_gta3_is_an_app_with_its_own_service(tmp_path, monkeypatch):
    import subprocess
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **k: calls.append(args) or type("R", (), {"returncode": 0})())
    assert pi_hw(tmp_path).start_app("gta3") is True
    assert calls[-1][-1] == "anypercent-gta3.service"


def test_health_reads_cpu_speed_uptime_and_free_space(tmp_path):
    root = sysfs(tmp_path)
    cpu = tmp_path / "sys" / "devices" / "system" / "cpu" / "cpu0" / "cpufreq"
    cpu.mkdir(parents=True)
    (cpu / "scaling_cur_freq").write_text("1200000\n")
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("3725.42 1000.00\n")
    h = Hardware(root, vcgencmd="").health(proc_root=str(proc), disks=(("Card", str(tmp_path)),))
    assert h["cpu_mhz"] == 1200 and h["uptime_s"] == 3725
    assert h["disks"][0][0] == "Card" and h["disks"][0][1] > 0          # free MB


def test_health_lists_what_happened_since_boot(tmp_path):
    hw = fake_vcgencmd(tmp_path, "0x50000")                             # under-voltage earlier, throttled earlier
    assert hw.health(proc_root=str(tmp_path), disks=())["since_boot"] == ["Low power", "Slowed down"]
    assert fake_vcgencmd(tmp_path / "x", "0x80000").health(proc_root=str(tmp_path), disks=())["since_boot"] == ["Hot"]

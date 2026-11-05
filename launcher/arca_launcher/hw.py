"""Battery, backlight, volume, Wi-Fi, power warnings and power off. Real on the Pi; in the sandbox they are absent and do nothing."""
import glob
import os
import shutil
import subprocess


# apps a library entry can start in place of a game: its systemd service (device/anypercent-browser.service)
APP_SERVICES = {"browser": "anypercent-browser.service", "gta3": "anypercent-gta3.service"}

# Master (a sound server), PCM (older Pi kernels), Headphone (the Pi's own audio today), Digital (I2S DACs)
MIXER_CONTROLS = ("Master", "PCM", "Headphone", "Digital")
# The slider's 100% is the mixer's 96%: 0 dB on the Pi's PCM. Its top 4% is +4 dB of digital gain, which clipped
# loud passages into a harsh buzz on the handheld's speaker.
VOLUME_CEILING = 96


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


class Hardware:
    def __init__(self, sys_root="/sys", amixer=None, model_path="/proc/device-tree/model",
                 proc_wireless="/proc/net/wireless", vcgencmd=None):
        self.sys = sys_root
        self.amixer = shutil.which("amixer") if amixer is None else amixer
        self.model_path = model_path
        self.proc_wireless = proc_wireless
        self.vcgencmd = shutil.which("vcgencmd") if vcgencmd is None else vcgencmd

    def is_pi(self):
        return (_read(self.model_path) or "").startswith("Raspberry Pi")

    def power_off(self):
        """Shut the device down. Only on a Raspberry Pi: anywhere else (the sandbox) it does nothing."""
        if not self.is_pi():
            return False
        return subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"], capture_output=True).returncode == 0

    def start_app(self, name):
        """Start an app (the browser) through systemd. Its service takes the screen from the launcher, which systemd
        stops, and hands it back when the app closes. Only on a Raspberry Pi; False for an unknown app."""
        service = APP_SERVICES.get(name)
        if service is None or not self.is_pi():
            return False
        cmd = ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", service]
        return subprocess.run(cmd, capture_output=True).returncode == 0

    def battery_percent(self):
        """The console's own battery. A controller's (scope Device, e.g. the DualSense) is not it."""
        for d in sorted(glob.glob(os.path.join(self.sys, "class", "power_supply", "*"))):
            if _read(os.path.join(d, "type")) == "Battery" and _read(os.path.join(d, "scope")) != "Device":
                v = _read(os.path.join(d, "capacity"))
                if v and v.isdigit():
                    return max(0, min(100, int(v)))
        return None

    def controller_battery(self):
        """A connected controller's battery percent (the DualSense reports one), or None."""
        for d in sorted(glob.glob(os.path.join(self.sys, "class", "power_supply", "*"))):
            if _read(os.path.join(d, "type")) == "Battery" and _read(os.path.join(d, "scope")) == "Device":
                v = _read(os.path.join(d, "capacity"))
                if v and v.isdigit():
                    return max(0, min(100, int(v)))
        return None

    def set_lightbar(self, rgb):
        """Colour every controller light bar (a DualSense's rgb:indicator LED). True if one was set."""
        done = False
        for d in sorted(glob.glob(os.path.join(self.sys, "class", "leds", "*:rgb:indicator"))):
            top = _read(os.path.join(d, "max_brightness")) or "255"
            try:
                with open(os.path.join(d, "multi_intensity"), "w") as f:
                    f.write(" ".join(str(int(c)) for c in rgb))
                with open(os.path.join(d, "brightness"), "w") as f:
                    f.write(top)
                done = True
            except OSError:
                pass
        return done

    def wifi(self):
        """Wi-Fi signal 1..100, 0 when not connected, None when there is no Wi-Fi at all."""
        ifaces = [os.path.dirname(d) for d in glob.glob(os.path.join(self.sys, "class", "net", "*", "wireless"))]
        if not ifaces:
            return None
        for d in sorted(ifaces):
            if _read(os.path.join(d, "operstate")) != "up":
                continue
            name = os.path.basename(d)
            for line in (_read(self.proc_wireless) or "").splitlines():
                head, _, rest = line.partition(":")
                if head.strip() == name and rest.split():
                    link = float(rest.split()[1].rstrip("."))         # link quality, out of 70
                    return max(1, min(100, round(link * 100 / 70)))
        return 0

    def power_warning(self):
        """"Low power" while the Pi is under-voltage (a weak power bank or cable), "Hot" while it is held back for
        heat, else None. From the firmware's throttled flags: bit 0 under-voltage now, bit 3 soft temperature limit."""
        bits = self._throttled()
        if bits is None:
            return None
        if bits & 0x1:
            return "Low power"
        if bits & 0x4:                                            # throttled now (the hard limit, 80 C)
            return "Too hot"
        if bits & 0x8:
            return "Hot"
        return None

    def _throttled(self):
        """The firmware's throttled flags (vcgencmd get_throttled), or None."""
        if not self.vcgencmd:
            return None
        try:
            out = subprocess.run([self.vcgencmd, "get_throttled"], capture_output=True, text=True, timeout=2).stdout
            return int(out.strip().split("=")[1], 16)
        except (OSError, subprocess.SubprocessError, IndexError, ValueError):
            return None

    def health(self, proc_root="/proc", disks=(("Card", "/"), ("Saves", "/data"))):
        """The Device health screen's readings: temperature, CPU speed, uptime, free space, and what the firmware
        saw since boot (bits 16 under-voltage, 18 throttled, 19 soft temperature limit)."""
        mhz = _read(os.path.join(self.sys, "devices", "system", "cpu", "cpu0", "cpufreq", "scaling_cur_freq"))
        up = _read(os.path.join(proc_root, "uptime"))
        free = []
        for name, path in disks:
            try:
                free.append((name, shutil.disk_usage(path).free // (1024 * 1024)))
            except OSError:
                pass
        bits = self._throttled() or 0
        since = [label for bit, label in ((16, "Low power"), (18, "Slowed down"), (19, "Hot")) if bits >> bit & 1]
        return {"temp_c": self.temperature(), "cpu_mhz": int(mhz) // 1000 if mhz and mhz.isdigit() else None,
                "uptime_s": int(float(up.split()[0])) if up else None, "disks": free, "since_boot": since}

    def temperature(self):
        """The SoC temperature in whole degrees C, or None."""
        v = _read(os.path.join(self.sys, "class", "thermal", "thermal_zone0", "temp"))
        return round(int(v) / 1000) if v and v.lstrip("-").isdigit() else None

    def _backlight(self):
        hits = sorted(glob.glob(os.path.join(self.sys, "class", "backlight", "*")))
        return hits[0] if hits else None

    def brightness_available(self):
        d = self._backlight()
        return d is not None and os.access(os.path.join(d, "brightness"), os.W_OK)

    def set_brightness(self, pct):
        d = self._backlight()
        top = _read(os.path.join(d, "max_brightness")) if d else None
        if not top or not top.isdigit():
            return False
        try:
            with open(os.path.join(d, "brightness"), "w") as f:
                f.write(str(round(int(top) * pct / 100)))
            return True
        except OSError:
            return False

    def set_volume(self, pct):
        if not self.amixer:
            return False
        level = round(pct * VOLUME_CEILING / 100)
        for control in MIXER_CONTROLS:
            if subprocess.run([self.amixer, "-q", "sset", control, f"{level}%"], capture_output=True).returncode == 0:
                return True
        return False

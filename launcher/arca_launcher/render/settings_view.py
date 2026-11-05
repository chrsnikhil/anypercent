"""Settings tab (volume, brightness, controller, on-screen controls, About, Sleep, Power off), the About screen and
the controller button map."""
import json
import os

import pygame

from .. import NAME, __version__, model
from ..model import Screen
from . import chrome, theme
from .text import wrap

LABELS = {"volume": "Volume", "brightness": "Brightness", "gamepad": "Controller", "controls": "On-screen controls",
          "health": "Device health", "about": "About", "sleep": "Sleep", "power": "Power off"}
ROW_Y, ROW_PITCH, ROW_H = 70, 46, 40       # eight rows above the button hints
HIT_GAP = (ROW_PITCH - ROW_H) // 2         # each row's touch strip fills the gap to its neighbours, never past it
# The DualSense, in the launcher and in games (input.py for the launcher, the RetroArch profile and the launcher's
# quit combo for games), as callouts round the line drawing (tools/make_dualsense_art.py).
# (side, label top, button in dualsense.json, name, launcher, in games)
CALLOUTS = [
    ("l", 60, "l1", "L1", "Games tab", "L"),
    ("l", 124, "create", "Create", "-", "Select"),
    ("l", 188, "dpad", "D-pad", "Move", "D-pad"),
    ("l", 252, "lstick", "Left stick", "Move", "D-pad"),
    ("r", 60, "r1", "R1", "Settings tab", "R"),
    ("r", 124, "options", "Options", "Game info", "Start"),
    ("r", 188, "triangle", "Triangle, Square", "PB hub, mock pick", "-"),
    ("r", 252, "circle", "Circle", "Back", "B"),
    ("r", 316, "cross", "Cross", "Select, Play", "A"),
]
PAD_ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "dualsense")
PAD_RECT = pygame.Rect(213, 78, 375, 240)
GUIDE = (96, 102, 112)
SWITCH_W, SWITCH_H = 52, 28


class SettingsView:
    def __init__(self, gfx):
        self.gfx = gfx
        self.rows = []                    # each row's rect, as drawn
        self.bars = []                    # each row's slider bar, or None
        self.switches = []                # each row's on/off switch, or None
        self.hits = []                    # touch targets: [chrome.Hit]

    def draw(self, nav, dt, status):
        if nav.screen is Screen.ABOUT:
            return self._about(nav, status)
        if nav.screen is Screen.GAMEPAD:
            return self._gamepad(nav, status)
        if nav.screen is Screen.HEALTH:
            return self._health(nav, status)
        g = self.gfx
        g.fill(theme.BG)
        self.hits = chrome.top_bar(g, status, tab="settings")
        self.rows, self.bars, self.switches = [], [], []
        for i, key in enumerate(model.SETTINGS_ROWS):
            row = pygame.Rect(60, ROW_Y + i * ROW_PITCH, theme.W - 120, ROW_H)
            self.rows.append(row)
            self.bars.append(None)
            self.switches.append(None)
            self.hits.append(chrome.Hit(row.inflate(0, 2 * HIT_GAP), ("setting", i), row, 12))
            enabled = key != "brightness" or nav.brightness_available
            if i == nav.settings_index:
                g.round_rect(row, theme.WHITE, 12, alpha=26)
                g.round_rect(row.inflate(6, 6), theme.WHITE, 15, alpha=200, width=2)
            g.text(LABELS[key], 18, row.x + 20, row.centery, weight="semibold", alpha=255 if enabled else 110,
                   anchor="midleft")
            if key in ("about", "gamepad", "health"):
                if key == "gamepad":
                    g.text("Button map", 14, row.right - 44, row.centery, anchor="midright", alpha=150)
                if key == "health":
                    g.text("Heat, power, storage, crashes", 14, row.right - 44, row.centery, anchor="midright",
                           alpha=150)
                g.text("›", 24, row.right - 20, row.centery - 2, anchor="midright", alpha=200)
                continue
            if key == "sleep":
                g.text("Dim to a clock", 14, row.right - 20, row.centery, anchor="midright", alpha=150)
                continue
            if key == "power":
                if nav.power_armed:
                    g.text("Press again to power off", 15, row.right - 20, row.centery, weight="semibold",
                           anchor="midright")
                else:
                    g.text("Safe to unplug after", 14, row.right - 20, row.centery, anchor="midright", alpha=150)
                continue
            if key == "controls":
                self.switches[i] = self._switch(row, i, nav.touch_controls, self.label(nav, key))
                continue
            if not enabled:
                g.text("Not available here", 14, row.right - 20, row.centery, anchor="midright", alpha=130)
                continue
            value = nav.volume if key == "volume" else nav.brightness
            bar = pygame.Rect(row.x + 240, row.centery - 4, 300, 8)
            self.bars[i] = bar
            self.hits.append(chrome.Hit(pygame.Rect(bar.x - 16, row.y - HIT_GAP, bar.w + 32, row.h + 2 * HIT_GAP), ("slider", i),
                                        bar=bar))
            g.round_rect(bar, theme.WHITE, 4, alpha=60)
            if value:
                g.round_rect((bar.x, bar.y, max(8, round(bar.w * value / 100)), bar.h), theme.WHITE, 4)
            g.text(self.label(nav, key), 16, row.right - 20, row.centery, anchor="midright")
        row = model.SETTINGS_ROWS[nav.settings_index]
        chrome.hints(g, [("A", "Confirm"), ("B", "Cancel")] if row == "power" and nav.power_armed else
                     [("A", "Power off"), ("B", "Games")] if row == "power" else
                     [("A", "Sleep"), ("B", "Games")] if row == "sleep" else
                     [("A", "Open"), ("B", "Games")] if row in ("about", "gamepad", "health") else
                     [("A", "On / Off"), ("B", "Games")] if row == "controls" else
                     [("←→", "Adjust"), ("B", "Games")])

    @staticmethod
    def label(nav, key):
        """The value a row shows as text: a slider's number, "On" or "Off" for the on-screen controls."""
        if key == "controls":
            return "On" if nav.touch_controls else "Off"
        return str(nav.volume if key == "volume" else nav.brightness)

    def _switch(self, row, i, on, label):
        """An on/off switch at the row's right end with its value to its left; a tap on either flips it."""
        g = self.gfx
        sw = pygame.Rect(row.right - 20 - SWITCH_W, row.centery - SWITCH_H // 2, SWITCH_W, SWITCH_H)
        g.round_rect(sw, theme.WHITE, SWITCH_H // 2, alpha=255 if on else 60)
        knob = pygame.Rect(0, 0, SWITCH_H - 8, SWITCH_H - 8)
        knob.center = (sw.right - SWITCH_H // 2, sw.centery) if on else (sw.x + SWITCH_H // 2, sw.centery)
        g.round_rect(knob, theme.BG if on else theme.WHITE, knob.h // 2)
        text = g.text(label, 16, sw.x - 14, row.centery, anchor="midright", alpha=255 if on else 170)
        hit = pygame.Rect(text.x - 12, row.y - HIT_GAP, row.right - text.x + 12, row.h + 2 * HIT_GAP)
        self.hits.append(chrome.Hit(hit, ("switch", i), sw, SWITCH_H // 2))
        return sw

    def _pad(self):
        """The line drawing as a texture and its button positions, loaded once; None if the asset is missing."""
        if not hasattr(self, "_pad_art"):
            try:
                with open(PAD_ART + ".json", encoding="utf-8") as fh:
                    spots = json.load(fh)
                self._pad_art = (self.gfx.texture(pygame.image.load(PAD_ART + ".png")), spots)
            except (OSError, ValueError, pygame.error):
                self._pad_art = None
        return self._pad_art

    def _gamepad(self, nav, status):
        g = self.gfx
        g.fill(theme.BG)
        self.hits = chrome.top_bar(g, status, title="Controller", back=True)
        art = self._pad()
        spots = {}
        if art is not None:
            tex, rel = art
            g.image(tex, PAD_RECT)
            spots = {k: (PAD_RECT.x + x * PAD_RECT.w, PAD_RECT.y + y * PAD_RECT.h) for k, (x, y) in rel.items()}
        for side, top, key, name, launcher, game in CALLOUTS:
            if key == "triangle" and not getattr(nav, "handler_enabled", False):
                launcher = "-"                     # --no-handler: no PB hub, no mock pick
            x = 205 if side == "l" else 596
            anchor = "topright" if side == "l" else "topleft"
            g.text(name, 15, x, top, weight="semibold", anchor=anchor)
            g.text(f"Launcher: {launcher}", 12, x, top + 19, alpha=200, anchor=anchor)
            g.text(f"In games: {game}", 12, x, top + 34, alpha=150, anchor=anchor)
            if key in spots:
                sx, sy = spots[key]
                g.line((x + (4 if side == "l" else -4), top + 9), (sx, sy), GUIDE)
                g.round_rect((round(sx) - 3, round(sy) - 3, 6, 6), theme.WHITE, 3)
        if "ps" in spots:
            sx, sy = spots["ps"]
            g.line((sx, sy), (sx, 336), GUIDE)
            g.round_rect((round(sx) - 3, round(sy) - 3, 6, 6), theme.WHITE, 3)
        g.text("PS   Launcher: reconnects the pad   ·   In games: RetroArch menu", 13, theme.W // 2, 340, anchor="midtop")
        g.text("L1 + R1   In games: quit to the launcher", 13, theme.W // 2, 364, weight="semibold", anchor="midtop")
        g.text("Create + Options together   Launcher: change the theme", 13, theme.W // 2, 388, anchor="midtop")
        pad = getattr(nav, "pad_battery", None)
        g.text(("Controller battery %d%%.  " % pad if pad is not None else "") +
               "Touchpad is ignored. On-screen controls hide while a controller is connected.", 12, theme.W // 2, 414,
               alpha=140, anchor="midtop")
        chrome.hints(g, [("B", "Back")])

    def _about(self, nav, status):
        g = self.gfx
        g.fill(theme.BG)
        self.hits = chrome.top_bar(g, status, title="About", back=True)
        lines = [
            (f"{NAME} launcher", f"Version {__version__}"),
            ("Games", f"{len(nav.az)} open-source homebrew games. Each game's authors and licences are on its info page."),
            ("Emulator", "mGBA (Mozilla Public License 2.0) in the sandbox; RetroArch (GPL-3.0) with the mGBA core "
                         "on the handheld."),
            ("Font", "Outfit by The Outfit Project Authors, SIL Open Font License 1.1."),
        ]
        y = 64
        for label, value in lines:
            y = g.text(label.upper(), 11, 60, y, weight="semibold", alpha=150).bottom + 2
            for line in wrap(value, theme.W - 120, lambda s: g.measure(s, 15)[0], max_lines=2):
                y = g.text(line, 15, 60, y).bottom
            y += 14
        chrome.hints(g, [("B", "Back")])

    def _health(self, nav, status):
        """Device health: live readings on the left, the firmware's since-boot record and recent crashes on the right."""
        import time
        g = self.gfx
        g.fill(theme.BG)
        self.hits = chrome.top_bar(g, status, title="Device health", back=True)
        h = nav.health or {}
        temp = h.get("temp_c") if h.get("temp_c") is not None else status.temp
        up = h.get("uptime_s")
        disks = "  ·  ".join(f"{n} {mb / 1024:.1f} GB free" if mb >= 1024 else f"{n} {mb} MB free"
                             for n, mb in h.get("disks") or [])
        pad = getattr(nav, "pad_battery", None)
        wifi = status.wifi
        hot = status.warning in ("Hot", "Too hot")
        left = [("Temperature", (f"{temp}°C" if temp is not None else "Unknown") +
                 (f", {status.warning.lower()}: slowed down" if hot else "")),
                ("Power", "Low power" if status.warning == "Low power" else "OK"),
                ("CPU", f"{h['cpu_mhz']} MHz" if h.get("cpu_mhz") else "Unknown"),
                ("Running for", f"{up // 3600} h {up % 3600 // 60} min" if up is not None else "Unknown"),
                ("Storage", disks or "Unknown"),
                ("Wi-Fi", "Not connected" if wifi == 0 else f"Signal {wifi}%" if wifi else "None"),
                ("Controller", f"Battery {pad}%" if pad is not None else "Not connected")]
        y = 66
        for label, value in left:
            y = g.text(label.upper(), 11, 60, y, weight="semibold", alpha=150).bottom + 1
            warn = value == "Low power" or (label == "Temperature" and hot)
            y = g.text(value, 15, 60, y, color=chrome.WARN if warn else theme.WHITE).bottom + 9
        x, y = 430, 66
        y = g.text("SINCE THE LAST BOOT", 11, x, y, weight="semibold", alpha=150).bottom + 1
        since = h.get("since_boot") or []
        y = g.text(", ".join(since) if since else "No power or heat trouble", 15, x, y,
                   color=chrome.WARN if since else theme.WHITE).bottom + 18
        y = g.text("RECENT CRASHES", 11, x, y, weight="semibold", alpha=150).bottom + 3
        if not nav.crashes:
            g.text("None. Everything ran clean.", 15, x, y)
        for when, title, detail in nav.crashes[:5]:
            stamp = time.strftime("%d %b %H:%M", time.localtime(when))
            y = g.text(f"{stamp}  {title}", 14, x, y, weight="semibold").bottom
            for line in wrap(detail, theme.W - x - 60, lambda t: g.measure(t, 12)[0], max_lines=1):
                y = g.text(line, 12, x, y, alpha=150).bottom
            y += 8
        chrome.hints(g, [("B", "Back")])

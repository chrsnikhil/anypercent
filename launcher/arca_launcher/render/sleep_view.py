"""The sleep screen: a dim clock with the battery level. Any button or touch wakes the launcher."""
from . import chrome, theme

DIM = 90                                  # text alpha: readable in a dark room, quiet on a dimmed backlight


class SleepView:
    def __init__(self, gfx):
        self.gfx = gfx
        self.hits = []                    # no targets: any touch wakes (the app handles it before the views)

    def draw(self, nav, dt, status):
        g = self.gfx
        g.fill(theme.BLACK)
        cx, cy = theme.W // 2, theme.H // 2
        g.text(status.clock, 112, cx, cy - 20, weight="bold", alpha=DIM, anchor="center")
        if status.battery is not None:
            g.text(f"Battery {status.battery}%", 18, cx, cy + 58, alpha=DIM, anchor="midtop")
        chrome.sponsor_logo(g, cx, cy + 100, 22, anchor="midtop", alpha=DIM)
        g.text("Tap or press any button to wake", 13, cx, theme.H - 28, alpha=60, anchor="midbottom")

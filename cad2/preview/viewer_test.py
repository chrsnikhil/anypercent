"""Headless smoke test of stl_viewer.html: no JS errors, the step mode and the
explode work, and screenshots for a visual check. Run from anywhere."""
import os
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE = os.path.join(ROOT, "stl_viewer.html")
OUT = os.path.join(ROOT, "cad2", "preview", "viewer2")
os.makedirs(OUT, exist_ok=True)
url = "file:///" + PAGE.replace("\\", "/")

errors = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    pg = b.new_page(viewport={"width": 1100, "height": 1500})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))

    def shot(name, hash_=None, wait=2.5):
        if hash_ is not None:
            pg.goto("about:blank")
            pg.goto(url + "#" + hash_)
            pg.wait_for_selector("#msg.gone", timeout=120000)
        time.sleep(wait)
        pg.locator("#stage").screenshot(path=os.path.join(OUT, name + ".png"))

    # front view (yaw pi): D-pad must be on the LEFT of the picture
    shot("front", "part=Assembly&yaw=3.1416&pitch=0.0&spin=0&zoom=1.1")
    shot("front_34", "part=Assembly&yaw=2.6&pitch=0.35&spin=0")
    shot("rear_34", "part=Assembly&yaw=0.6&pitch=0.5&spin=0")
    shot("exploded", "part=Assembly&yaw=0.9&pitch=0.35&spin=0&explode=100&zoom=0.55")
    shot("exploded_side", "part=Assembly&yaw=1.5708&pitch=0.1&spin=0&explode=100&zoom=0.55")
    # step mode
    pg.goto("about:blank")
    pg.goto(url + "#part=Assembly&spin=0")
    pg.wait_for_selector("#msg.gone", timeout=120000)
    pg.click("#stepStart")
    n = pg.locator("#stepList li").count()
    for i in range(n):
        time.sleep(3.2)                     # let the step's parts slide in
        pg.locator("#stage").screenshot(path=os.path.join(OUT, f"step_{i+1:02d}.png"))
        card = pg.locator("#stepCard").inner_text()
        print(f"step {i+1}: {card.splitlines()[0] if card else '?'} | {card.splitlines()[-1][:100] if card else ''}")
        if i < n - 1:
            pg.click("#stepNext")
    pg.screenshot(path=os.path.join(OUT, "page_stepmode.png"), full_page=True)
    b.close()

print("JS errors:", errors if errors else "none")
sys.exit(1 if errors else 0)

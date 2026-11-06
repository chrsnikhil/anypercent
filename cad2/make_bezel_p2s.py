"""The display bezel (display_bezel.scad -> stl_extra/anypercent_display_bezel.stl) as a sliced Bambu Studio
project for the P2S: black PLA, same printer, plate and process as the panels (make_panel_p2s.py).

  BAMBU_STUDIO=<folder with bambu-studio.exe> python make_bezel_p2s.py"""
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

from make_panel_p2s import BED, CAD2, FILAMENT, OUT, PLATE, PRINT, PRINTER, PROCESS, cli, flatten

STL = os.path.join(CAD2, "stl_extra", "anypercent_display_bezel.stl")
W, H = 131.5, 91.25


def main():
    exe_dir = os.environ.get("BAMBU_STUDIO")
    if not exe_dir or not os.path.exists(os.path.join(exe_dir, "bambu-studio.exe")):
        sys.exit("Set BAMBU_STUDIO to the folder holding bambu-studio.exe.")
    exe, res = os.path.join(exe_dir, "bambu-studio.exe"), os.path.join(exe_dir, "resources", "profiles", "BBL")
    work = tempfile.mkdtemp(prefix="bezel_")
    try:
        def dump(name, d):
            p = os.path.join(work, name)
            json.dump(d, open(p, "w", encoding="utf-8"), indent=1)
            return p
        settings = dump("m.json", flatten(res, PRINTER)) + ";" + dump("p.json", flatten(res, PROCESS, **PRINT))
        fil = dump("f.json", flatten(res, FILAMENT, filament_colour=["#000000"]))
        plates = dump("a.json", {"plates": [{"plate_name": "display bezel", "need_arrange": False, "objects": [
            {"path": STL, "count": 1, "filaments": [1], "assemble_index": [1],
             "pos_x": [(PLATE - W) / 2 + W / 2], "pos_y": [(PLATE - H) / 2 + H / 2], "pos_z": [0]}]}]})
        out = cli(exe, work, "--load-settings", settings, "--load-filaments", fil, "--curr-bed-type", BED,
                  "--load-assemble-list", plates, "--slice", "0", "--export-3mf", "b.3mf")
        dst = os.path.join(OUT, "display_bezel__P2S.3mf")
        shutil.copy(os.path.join(out, "b.3mf"), dst)
        with zipfile.ZipFile(dst) as z:
            g = z.read("Metadata/plate_1.gcode").decode("utf-8", "replace")
            pj = json.loads(z.read("Metadata/plate_1.json"))
        t = re.search(r"; total estimated time: ([^\n]+)", g).group(1)
        grams = re.search(r"; total filament weight \[g\] : ([\d.]+)", g).group(1)
        print(f"  ok  {os.path.basename(dst)}  black: {t}, {grams} g, plate bbox {[round(v, 1) for v in pj['bbox_all']]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

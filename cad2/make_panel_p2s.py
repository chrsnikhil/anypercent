"""
Two-colour rear panels as ready-to-print Bambu Studio projects for the Bambu Lab P2S.

  printer   Bambu Lab P2S, 0.4 mm nozzle (hardened steel, the P2S stock nozzle)
  plate     Textured PEI Plate
  process   0.20mm Standard @BBL P2S, with the overrides in PRINT below
  filament  Bambu PLA Basic, AMS slot 1 = body colour, slot 2 = logo colour

Each project holds ONE object with two parts, body and logo, so the logo prints fused
to the panel face (the body's top layer is at z 4.0, the logo's four layers sit on it).
Bambu Studio's own CLI builds the object from the body/logo STLs (--load-assemble-list),
applies the system presets, slices plate 1 and saves the project, so the file is what
Bambu Studio itself would save, with the plate already sliced.

  BAMBU_STUDIO=<folder with bambu-studio.exe> python make_panel_p2s.py

Needs the body/logo STLs from build_extra.sh. Output: stl_extra/p2s/panel_<kind>__P2S.3mf
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

CAD2 = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(CAD2, "stl_extra", "p2s")

PRINTER = "Bambu Lab P2S 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL P2S"
FILAMENT = "Bambu PLA Basic @BBL P2S"
BED = "Textured PEI Plate"
PRINT = {                                  # overrides on 0.20mm Standard, per PRINTING_GUIDE.md
    "wall_loops": "4",                     # the guide's 4 walls
    "top_shell_layers": "5",
    "bottom_shell_layers": "5",
    "sparse_infill_density": "25%",
    "sparse_infill_pattern": "gyroid",
    "brim_type": "outer_only",             # the guide's 5 mm brim on the large flat parts
    "brim_width": "5",
    "enable_support": "0",
    "enable_prime_tower": "0",             # colour changes only in the top 0.8 mm: the purge goes to the chute
}
PLATE, W, H = 256.0, 202.0, 124.0          # P2S plate; panel footprint

# kind: [(part, colour name, hex), ...]: AMS slot 1 is the body, then one slot per logo part.
# Part names match the STLs: stl_extra/arca_panel_<kind>_<part>.stl
# Colours are the spools on the owner's printer, as Bambu PLA Basic codes, so previews and AMS matching line up.
WHITE, BLACK, RED, BLUE = ("white", "#FFFFFF"), ("black", "#000000"), ("red", "#C12E1F"), ("blue", "#0A2989")
GREEN, YELLOW, ORANGE = ("green", "#00AE42"), ("yellow", "#F4EE2A"), ("orange", "#FF6A13")
PANELS = {
    "world":     [("body", *WHITE), ("logo", *BLACK)],
    "arkiv":     [("body", *BLUE),  ("logo", *WHITE)],
    "arc":       [("body", *BLACK), ("logo", *WHITE)],
    "chainlink": [("body", *BLUE),  ("logo", *WHITE)],
    "hedera":    [("body", *BLACK), ("logo", *WHITE)],
    # ETHGlobal Mumbai diya (logos/make_ethglobal_mumbai.py): its pink and deep-red lamp print red
    "ethglobal": [("body", *BLACK), ("orange", *ORANGE), ("pink", *RED), ("green", *GREEN)],
    # the full lockup (logos/make_ethglobal_mumbai_lockup.py) on white in 4 slots: lamp and wordmark red, rays orange
    "ethglobal_lockup": [("body", *WHITE), ("spool_orange", *ORANGE), ("spool_red", *RED), ("spool_green", *GREEN)],
}


def flatten(res, name, **over):
    """A system preset with its inherits chain and G-code includes resolved: the CLI wants it whole."""
    idx = {}
    for sub in ("machine", "process", "filament"):
        for dp, _, fs in os.walk(os.path.join(res, sub)):
            for f in fs:
                if f.endswith(".json"):
                    idx.setdefault(f[:-5], os.path.join(dp, f))

    def load(n):
        with open(idx[n], encoding="utf-8") as fh:
            return json.load(fh)

    def resolve(n):
        d = load(n)
        base = dict(resolve(d["inherits"])) if d.get("inherits") else {}
        base.update(d)
        for inc in d.get("include", []):
            base.update({k: v for k, v in load(inc).items()
                         if k not in ("name", "instantiation", "type", "from", "setting_id")})
        return base

    d = resolve(name)
    d.pop("inherits", None)
    d.pop("include", None)
    d.update({"from": "system", "instantiation": "true"}, **over)
    return d


def cli(exe, work, *args):
    out = os.path.join(work, "out")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    subprocess.run([exe, "--outputdir", out, *args], cwd=work, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with open(os.path.join(out, "result.json"), encoding="utf-8") as fh:
            r = json.load(fh)
    except FileNotFoundError:
        sys.exit(f"Bambu Studio CLI crashed on: {' '.join(args)}")
    if r.get("return_code") != 0:
        sys.exit(f"Bambu Studio CLI failed: {r.get('error_string')}")
    return out


def rename(path, kind):
    """The CLI names the object assemble_1 and the parts after the STL paths: give them readable names."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == "Metadata/model_settings.config":
                s = data.decode("utf-8")
                s = s.replace('value="assemble_1"', f'value="anypercent_panel_{kind}"')
                for part, name, _ in PANELS[kind]:
                    label = "body" if part == "body" else "logo"
                    s = re.sub(rf'value="[^"]*arca_panel_{kind}_{part}_1"', f'value="{label} ({name})"', s)
                data = s.encode("utf-8")
            dst.writestr(info, data)
    os.replace(tmp, path)


def check(path, kind):
    """Every colour prints, each part is on its own filament, and the settings are what we asked for."""
    with zipfile.ZipFile(path) as z:
        g = z.read("Metadata/plate_1.gcode").decode("utf-8", "replace")
        ps = json.loads(z.read("Metadata/project_settings.config"))
        ms = z.read("Metadata/model_settings.config").decode("utf-8")
    layers = int(re.search(r"; total layer number: (\d+)", g).group(1))
    m = re.search(r"; total filament weight \[g\] : ([\d.,]+)", g)
    grams = [float(v) for v in m.group(1).split(",")] if m else []
    time = re.search(r"; total estimated time: ([^\n]+)", g).group(1)
    parts = PANELS[kind]
    problems = []
    if layers != 24:
        problems.append(f"{layers} layers, want 24 (4.0 mm body + 0.8 mm logo)")
    if len(grams) != len(parts) or min(grams, default=0) <= 0:
        problems.append(f"filament use {grams}: every colour must print")
    for i in range(1, len(parts)):
        if not re.search(rf"^M620 S{i}A", g, re.M):
            problems.append(f"never changes to filament {i + 1}")
    if [c.upper() for c in ps["filament_colour"]] != [hx.upper() for _, _, hx in parts]:
        problems.append(f"colours {ps['filament_colour']}")
    want = {"printer_settings_id": PRINTER, "print_settings_id": PROCESS, "curr_bed_type": BED, **PRINT}
    problems += [f"{k} = {ps.get(k)!r}" for k, v in want.items() if ps.get(k) != v]
    if ps["nozzle_type"][0] != "hardened_steel" or ps["nozzle_diameter"] != ["0.4"]:
        problems.append(f"nozzle {ps['nozzle_type']} {ps['nozzle_diameter']}")
    if ms.count("<object id=") != 1 or ms.count("<part id=") != len(parts):
        problems.append(f"not one object made of {len(parts)} parts")
    for i, (part, name, _) in enumerate(parts[1:], start=2):
        if not re.search(rf'logo \({re.escape(name)}\)".*?<metadata key="extruder" value="{i}"/>', ms, re.S):
            problems.append(f"{part} is not on filament {i}")
    if problems:
        sys.exit(f"{kind}: " + "; ".join(problems))
    return f"{time}, " + " + ".join(f"{v:g} g" for v in grams)


def main():
    exe_dir = os.environ.get("BAMBU_STUDIO")
    if not exe_dir or not os.path.exists(os.path.join(exe_dir, "bambu-studio.exe")):
        sys.exit("Set BAMBU_STUDIO to the folder holding bambu-studio.exe (the portable zip from "
                 "github.com/bambulab/BambuStudio/releases works).")
    exe = os.path.join(exe_dir, "bambu-studio.exe")
    res = os.path.join(exe_dir, "resources", "profiles", "BBL")
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="p2s_")
    try:
        def dump(name, d):
            p = os.path.join(work, name)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=1)
            return p

        settings = (dump("machine.json", flatten(res, PRINTER)) + ";" +
                    dump("process.json", flatten(res, PROCESS, **PRINT)))
        x, y = (PLATE - W) / 2, (PLATE - H) / 2          # the STLs start at the origin: centre on the plate
        kinds = sys.argv[1:] or list(PANELS)                # e.g. python make_panel_p2s.py ethglobal
        for kind in kinds:
            parts = PANELS[kind]
            plates = dump(f"{kind}_assemble.json", {"plates": [{
                "plate_name": f"{kind} panel", "need_arrange": False,
                "objects": [{"path": os.path.join(CAD2, "stl_extra", f"arca_panel_{kind}_{part}.stl"),
                             "count": 1, "filaments": [i], "assemble_index": [1],
                             "pos_x": [x], "pos_y": [y], "pos_z": [0]}
                            for i, (part, _, _) in enumerate(parts, start=1)]}]})
            fils = ";".join(dump(f"{kind}_{part}.json", flatten(res, FILAMENT, filament_colour=[hx]))
                            for part, _, hx in parts)
            out = cli(exe, work, "--load-settings", settings, "--load-filaments", fils,
                      "--curr-bed-type", BED, "--load-assemble-list", plates,
                      "--slice", "0", "--export-3mf", "p.3mf")
            dst = os.path.join(OUT, f"panel_{kind}__P2S.3mf")
            shutil.copy(os.path.join(out, "p.3mf"), dst)
            rename(dst, kind)
            slots = ", ".join(f"AMS {i} {name} {hx}" for i, (_, name, hx) in enumerate(parts, start=1))
            print(f"  ok  {os.path.basename(dst):28s} {slots}: {check(dst, kind)}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

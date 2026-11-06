"""Console meshes for the briefing film: every assembled part of the Any% handheld, with smooth-shading normals and
CAD feature edges, packed into one binary the film's Three.js scene loads.

  python video/briefing/prep/make_meshes.py      -> video/briefing/public/console.bin + console.json

Sources (read only), the same ones the product viewer uses (cad2/make_product_viewer.py):
  build_stl_viewer.ps1 $AssemblyManifest      colours and labels
  cad2/viewer_cache/asm/asm_*.stl             decimated assembly meshes, device coordinates in mm
  cad2/stl_extra/arca_panel_<kind>_*.stl      the printed sponsor panels (print position, shifted by the measured dz)
  cad2/assembly_steps.json                    the build order: which parts go in at each step, from which direction

Layout of console.bin, per part in console.json order: positions f32 xyz, normals f32 xyz, indices u32,
edges f32 (pairs of xyz points). console.json gives each block's byte offset and count."""
import importlib.util
import json
import math
import os
import sys

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CAD2 = os.path.join(ROOT, "cad2")
OUT = os.path.join(HERE, "..", "public")
CREASE_DEG = 28          # normals are smoothed across folds flatter than this; sharper folds are drawn as edges
PANELS = ("ethglobal", "ethglobal_lockup")          # the two printed ETHGlobal Mumbai plates (build step, then the swap)
# meshes holding several separate solids that animate one by one (screws spin in, inserts press in, ...)
SPLIT = {"asm_inserts", "asm_screws_plates", "asm_screws_frame", "asm_spacers", "asm_shoulders", "asm_pins",
         "asm_switches_shoulder"}

spec = importlib.util.spec_from_file_location("pv", os.path.join(CAD2, "make_product_viewer.py"))
pv = importlib.util.module_from_spec(spec)
sys.path.insert(0, CAD2)
spec.loader.exec_module(pv)


def feature_edges(m):
    """Segments where the surface folds sharper than CREASE_DEG, plus open boundaries."""
    keep = m.face_adjacency_edges[m.face_adjacency_angles > math.radians(CREASE_DEG)]
    bound = m.edges_sorted[trimesh.grouping.group_rows(m.edges_sorted, require_count=1)]
    e = np.vstack([keep, bound]) if len(bound) else keep
    return m.vertices[e].reshape(-1, 3)


def shaded(m):
    s = trimesh.graph.smooth_shade(m, angle=math.radians(CREASE_DEG))
    return np.asarray(s.vertices, np.float32), np.asarray(s.vertex_normals, np.float32), np.asarray(s.faces, np.uint32)


def main():
    rows = {n: (c, a, g, lab) for n, c, a, g, lab in pv.manifest()}
    steps = json.load(open(os.path.join(CAD2, "assembly_steps.json")))
    dz, _, _ = pv.panel_offset()
    table = pv.panels_table()

    # step of each file: the shell is step 0, then assembly_steps.json in order
    where = {"asm_front_shell": (0, [0, 0, -1], 0, "shell")}
    titles = ["Front shell"]
    for i, s in enumerate(steps["steps"], 1):
        titles.append(s["title"])
        for p in s["parts"]:
            files = p.get("files") or [p["file"]]
            files = sum((["asm_pi_board", "asm_pi_parts"] if f == "asm_pi" else [f] for f in files), [])
            rigid = files[0] if p.get("rigid") else None
            for f in files:
                where[f] = (i, p["dir"], p["dist"], rigid or f)

    blob = bytearray()
    parts = []

    def add(name, mesh, colour, label, step, direction, dist, body, panel=None, file=None, inst=0):
        v, n, f = shaded(mesh)
        e = feature_edges(mesh).astype(np.float32)
        rec = {"name": name, "file": file or name, "inst": inst, "label": label, "colour": colour, "step": step,
               "dir": direction, "dist": dist, "body": body, "panel": panel, "bounds": np.asarray(mesh.bounds).round(3).tolist(),
               "nVerts": len(v), "nIdx": int(f.size), "nEdge": len(e)}
        for key, arr in (("pos", v), ("nrm", n), ("idx", f), ("edge", e)):
            rec[key] = len(blob)
            blob.extend(np.ascontiguousarray(arr).tobytes())
        parts.append(rec)
        return rec

    for name, (step, d, dist, body) in sorted(where.items(), key=lambda kv: kv[1][0]):
        if name.startswith("asm_panel_") or name == "asm_magnets_panel" or name == "asm_pico":
            continue                                    # the sponsor panels are added below; the Pico was dropped
        path = os.path.join(CAD2, "viewer_cache", "asm", name + ".stl")
        colour, _, _, label = rows[name]
        mesh = trimesh.load(path)
        if name in SPLIT:
            comps = mesh.split(only_watertight=False)
            comps = sorted(comps, key=lambda c: (round(float(c.bounds.mean(0)[0]) / 4), float(c.bounds.mean(0)[1])))
            for k, c in enumerate(comps):
                add(f"{name}#{k}", c, colour, label, step, d, dist, body if body != name else f"{name}#{k}", file=name, inst=k)
            print(f"  step {step:2d} {name:24s} split into {len(comps)}  {label}")
            continue
        r = add(name, mesh, colour, label, step, d, dist, body)
        print(f"  step {step:2d} {name:24s} {r['nIdx'] // 3:6d} tris {r['nEdge'] // 2:6d} edges  {label}")

    panel_step = where["asm_panel_world_body"]
    mag = trimesh.load(os.path.join(CAD2, "viewer_cache", "asm", "asm_magnets_panel.stl"))
    for kind in PANELS:
        for part, cname, hx in table[kind]:
            m = trimesh.load(os.path.join(CAD2, "stl_extra", f"arca_panel_{kind}_{part}.stl"))
            if part == "body" and len(m.faces) > pv.MAX_BODY_FACES:
                m = m.simplify_quadric_decimation(face_count=pv.MAX_BODY_FACES)
            m.apply_translation([0, 0, dz])
            r = add(f"panel_{kind}_{part}", m, hx.upper(), f"{kind} panel {part} ({cname})", panel_step[0],
                    panel_step[1], panel_step[2], f"panel_{kind}", panel=kind)
            print(f"  panel {kind:7s} {part:5s} {r['nIdx'] // 3:6d} tris {r['nEdge'] // 2:6d} edges  {cname}")
        add(f"panel_{kind}_magnets", mag.copy(), "#A9AEB5", "panel magnets", panel_step[0], panel_step[1],
            panel_step[2], f"panel_{kind}", panel=kind)

    win, glass = pv.screen_rect()
    cx, cy = (win[0] + win[1]) / 2, (win[2] + win[3]) / 2
    lo = np.min([p["bounds"][0] for p in parts], axis=0)
    hi = np.max([p["bounds"][1] for p in parts], axis=0)
    meta = {"parts": parts, "steps": titles, "panelDz": dz,
            "screen": {"rect": [cx - 54, cx + 54, cy - 32.4, cy + 32.4], "glassZ": glass},
            "bounds": [lo.round(3).tolist(), hi.round(3).tolist()], "bytes": len(blob)}
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "console.bin"), "wb").write(bytes(blob))
    json.dump(meta, open(os.path.join(OUT, "console.json"), "w"), indent=1)
    print(f"{len(parts)} parts, {len(blob) / 1e6:.1f} MB, bounds {lo.round(1).tolist()} .. {hi.round(1).tolist()}, "
          f"screen {meta['screen']}")


if __name__ == "__main__":
    main()

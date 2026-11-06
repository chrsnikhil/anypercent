"""Manifold / bed-fit check for every ARCA handheld STL.

Run:  python cad2/check_stl.py
Needs: pip install trimesh numpy
"""
import glob
import os
import sys

import trimesh

BED = (220.0, 220.0, 250.0)
ORDER = [
    "front_shell", "bay_tray", "rear_frame",
    "panel_world", "panel_arkiv", "panel_arc",
    "buttons", "switch_plates", "display_spacers", "sd_hatch", "fit_check_jig",
]


def locate(mesh, name):
    """Print where the bad edges are, in model mm. Far more useful than
    'may need repair': it points straight at the offending feature."""
    import numpy as np
    uniq, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    bad = uniq[counts != 2]
    if not len(bad):
        return
    pts = mesh.vertices[bad.reshape(-1)]
    print(f"    {name}: {len(bad)} bad edges, "
          f"bbox {np.round(pts.min(0), 2)} .. {np.round(pts.max(0), 2)}")
    buckets = {}
    for q in (np.floor(pts / 5.0) * 5).astype(int):
        buckets[tuple(q)] = buckets.get(tuple(q), 0) + 1
    for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])[:8]:
        print(f"      near x{k[0]} y{k[1]} z{k[2]}  ({v} vertices)")


def fits(ext):
    """True if the part fits the bed in either the as-exported or the 90deg
    rotated footprint."""
    w, d, h = ext
    if h > BED[2]:
        return False
    return (w <= BED[0] and d <= BED[1]) or (d <= BED[0] and w <= BED[1])


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    files = {}
    for f in glob.glob(os.path.join(here, "stl", "*.stl")):
        files[os.path.basename(f)[len("arca_"):-len(".stl")]] = f

    hdr = f"{'part':<16}{'tris':>9}{'watertight':>12}{'open edges':>12}{'bodies':>8}{'volume cm3':>12}   bounding box (mm)      bed"
    print(hdr)
    print("-" * len(hdr))
    bad = 0
    for name in ORDER + sorted(set(files) - set(ORDER)):
        if name not in files:
            print(f"{name:<16}  MISSING")
            bad += 1
            continue
        # process=True merges the duplicated vertices an STL always has;
        # without it every triangle reads as its own body with 3 open edges.
        m = trimesh.load(files[name], process=True)
        m.merge_vertices()
        ext = m.extents
        bodies = m.body_count
        wt = m.is_watertight
        oe = len(trimesh.grouping.group_rows(m.edges_sorted, require_count=1))
        ok = fits(ext)
        vol = m.volume / 1000.0 if wt else float("nan")
        print(
            f"{name:<16}{len(m.faces):>9}{str(wt):>12}{oe:>12}{bodies:>8}"
            f"{vol:>12.1f}   {ext[0]:6.1f} x{ext[1]:6.1f} x{ext[2]:6.1f}   "
            f"{'OK' if ok else 'TOO BIG'}"
        )
        if not wt or oe or not ok:
            bad += 1
            locate(m, name)
    print()
    print("bed:", f"{BED[0]:.0f} x {BED[1]:.0f} x {BED[2]:.0f} mm")
    print("FAIL" if bad else "ALL PARTS MANIFOLD AND ON THE BED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""
Prepare meshes for the STL viewer page.

OpenSCAD writes ASCII STL, which is ~5x bigger than binary, and the viewer
embeds every mesh in one HTML file. This writes binary copies (never touching
the originals the fit checks use) and, for the few very dense vendor meshes,
a decimated copy so the page stays quick to open.

  cad2/stl_assembly/*.stl -> cad2/viewer_cache/asm/*.stl
  cad2/stl/*.stl          -> cad2/viewer_cache/stl/*.stl

Run before build_stl_viewer.ps1 (build_viewer_all.sh does both).
"""
import gzip
import os
import sys

import trimesh

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_FACES = 40000          # decimate above this (viewer only)


def prep(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    for f in os.listdir(dst_dir):
        if f.endswith(".stl"):
            os.remove(os.path.join(dst_dir, f))
    tot_raw = tot_gz = 0
    for f in sorted(os.listdir(src_dir)):
        if not f.endswith(".stl"):
            continue
        m = trimesh.load(os.path.join(src_dir, f), process=False)
        n0 = len(m.faces)
        if n0 > MAX_FACES:
            try:
                m = m.simplify_quadric_decimation(face_count=MAX_FACES)
            except Exception as e:                      # noqa: BLE001
                print(f"  (no decimation for {f}: {e})")
        out = os.path.join(dst_dir, f)
        m.export(out, file_type="stl")                   # binary
        raw = os.path.getsize(out)
        gz = len(gzip.compress(open(out, "rb").read(), 6))
        tot_raw += raw; tot_gz += gz
        note = f"  (decimated from {n0})" if len(m.faces) < n0 else ""
        print(f"  {f:34s} {len(m.faces):7d} tris  {raw/1024:7.0f} kB -> gz {gz/1024:6.0f} kB{note}")
    print(f"  total {tot_raw/1048576:.1f} MB binary, {tot_gz/1048576:.1f} MB gzipped")


if __name__ == "__main__":
    prep(os.path.join(ROOT, "stl_assembly"), os.path.join(ROOT, "viewer_cache", "asm"))
    prep(os.path.join(ROOT, "stl"), os.path.join(ROOT, "viewer_cache", "stl"))

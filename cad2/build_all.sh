#!/bin/sh
# Everything, in order. About 15 minutes (the OpenSCAD CGAL exports dominate).
set -e
cd "$(dirname "$0")"
python components/build_components.py
sh build.sh
sh build_assembly.sh
sh build_extra.sh
python check_stl.py
python check_assembly.py || echo "!! check_assembly.py reported FAILs -- see preview/assembly_report.txt"
python prep_viewer_meshes.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ../build_stl_viewer.ps1

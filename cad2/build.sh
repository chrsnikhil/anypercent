#!/bin/sh
# Build every ARCA handheld part to STL and a preview PNG.
OS="C:/Program Files/OpenSCAD/openscad.exe"
cd "$(dirname "$0")" || exit 1
mkdir -p stl preview
for p in front_shell bay_tray rear_frame panel_world panel_arkiv panel_arc buttons switch_plates display_spacers sd_hatch fit_check_jig; do
  echo "=== $p"
  "$OS" -o "stl/arca_${p}.stl" "make_${p}.scad" 2>&1 | grep -Ei "error|warning|WARNING" | head -6
  ls -l "stl/arca_${p}.stl" 2>/dev/null | awk '{print "    stl bytes:",$5}'
done
echo "=== done"

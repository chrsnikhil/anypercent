#!/bin/sh
# Print-shop extras: one button file per colour, panels split body/logo.
OS="C:/Program Files/OpenSCAD/openscad.exe"
cd "$(dirname "$0")" || exit 1
mkdir -p stl_extra
export OS
echo "buttons_orange buttons_slate buttons_pale buttons_charcoal panel_world_body panel_world_logo panel_arkiv_body panel_arkiv_logo panel_arc_body panel_arc_logo panel_chainlink_body panel_chainlink_logo panel_hedera_body panel_hedera_logo" | tr ' ' '\n' | xargs -P 6 -I{} sh -c '
  printf "part = \"%s\";\ninclude <enclosure.scad>\n" "{}" > "_x_{}.scad"
  "$OS" -o "stl_extra/arca_{}.stl" "_x_{}.scad" > "stl_extra/{}.log" 2>&1; rc=$?
  rm -f "_x_{}.scad"
  if [ $rc -ne 0 ] || grep -qiE "^(ERROR|WARNING)" "stl_extra/{}.log"; then echo "!! {}"; else rm -f "stl_extra/{}.log"; echo "   {}"; fi'

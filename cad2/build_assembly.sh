#!/bin/sh
# Export every ASSEMBLED-POSITION component to stl_assembly/ for the web
# viewer. These are in true device coordinates, NOT print orientation -- never
# slice them. Print from stl/ (build.sh).
#
# Each export goes through a throwaway one-line wrapper next to enclosure.scad,
# for the reason in README section 1: -D cannot set `part`, and fails silently.
#
# The viewer's colour for each file is set in ../build_stl_viewer.ps1
# ($AssemblyManifest). A new file here that is not in that manifest still shows
# up, but with a guessed colour and a build warning.
OS="C:/Program Files/OpenSCAD/openscad.exe"
cd "$(dirname "$0")" || exit 1
mkdir -p stl_assembly

PARTS="
asm_front_shell asm_bay_tray asm_rear_frame asm_spacers
asm_panel_world_body asm_panel_world_logo
asm_panel_arkiv_body asm_panel_arkiv_logo
asm_panel_arc_body   asm_panel_arc_logo
asm_cap_dpad asm_cap_a asm_cap_b asm_cap_x asm_cap_y asm_cap_pills asm_shoulders asm_pins
asm_plate_face asm_plate_dpad asm_plate_pills
asm_display asm_pi asm_pi_board asm_pi_parts asm_heatsinks asm_bank asm_speaker asm_pico asm_pam
asm_switches_plates asm_switches_shoulder asm_screws_frame asm_screws_plates asm_screw_pivot
asm_inserts asm_magnets_frame asm_magnets_panel
"
# Real bought parts come from components/*.stl (build_components.py); the
# asm_ targets only place them. Stale files from older part lists are removed
# first so nothing in stl_assembly/ can be out of date.
# With arguments, rebuild only those parts and leave the rest alone.
if [ $# -gt 0 ]; then PARTS="$*"; else rm -f stl_assembly/*.stl stl_assembly/*.log; fi

export OS
echo $PARTS | tr ' ' '\n' | xargs -P 8 -I{} sh -c '
  p="{}"
  w="_asm_${p}.scad"
  printf "part = \"%s\";\ninclude <enclosure.scad>\n" "$p" > "$w"
  "$OS" -o "stl_assembly/${p}.stl" "$w" > "stl_assembly/${p}.log" 2>&1
  rc=$?
  rm -f "$w"
  if [ $rc -ne 0 ] || grep -qiE "^(ERROR|WARNING)" "stl_assembly/${p}.log"; then
    echo "!! $p (exit $rc)"; grep -iE "error|warning" "stl_assembly/${p}.log" | head -4
  else
    rm -f "stl_assembly/${p}.log"
    echo "   $p  $(wc -c < "stl_assembly/${p}.stl") bytes"
  fi
'
echo "=== done"

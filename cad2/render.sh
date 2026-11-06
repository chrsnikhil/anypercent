#!/bin/sh
OS="C:/Program Files/OpenSCAD/openscad.exe"
cd "$(dirname "$0")" || exit 1
mkdir -p preview
# z = depth with the FRONT face at z = 0, so rot [0,0,0] looks at the REAR and
# rot [180,0,0] looks at the FRONT. Parts exported in print orientation are
# viewed with a normal 3/4 [55,0,25].
shot() {
  "$OS" -o "preview/$1.png" --imgsize=1500,1050 --projection=p \
    --camera=0,0,0,"$3","$4","$5",0 --viewall --autocenter \
    --colorscheme=Tomorrow "make_$2.scad" >/dev/null 2>&1
  # OpenSCAD's gimbal camera always looks down -z, so a FRONT view needs
  # rot_x = 180, which also turns the object upside down in the image. Flip
  # the PNG back for those shots so previews read the right way up. Nothing
  # on the front face carries text, so a vertical flip is lossless.
  if [ "$3" = "180" ] && [ "$5" = "0" ]; then
    python -c "from PIL import Image; import sys; p=sys.argv[1]; Image.open(p).transpose(Image.FLIP_TOP_BOTTOM).save(p)" "preview/$1.png"
  fi
  echo "  preview/$1.png"
}
shot assembly_front     assembly          180   0   0
shot assembly_rear      assembly            0   0   0
shot assembly_iso       assembly          235   0  25
shot assembly_exploded  assembly_exploded 240   0  30
shot shell_face         front_shell       180   0   0
shot shell_inside       front_shell         0   0   0
shot shell_iso          front_shell       235   0  25
shot bay_tray           bay_tray           55   0  25
shot rear_frame_in      rear_frame          0   0   0
shot rear_frame_out     rear_frame        180   0   0
shot panel_world        panel_world        55   0  25
shot panel_arkiv        panel_arkiv        55   0  25
shot panel_arc          panel_arc          55   0  25
shot buttons            buttons            55   0  25
shot display_spacers    display_spacers    55   0  25
shot fit_check_jig      fit_check_jig       0   0   0
echo done

"""
Build the print-shop package: ONE flat folder (select all, send) plus a zip.

  ../ARCA_print_files/        numbered in print order, colour in every name
  ../ARCA_print_files.zip

Binary STL (every slicer reads it, a fifth of the size), each file re-checked
watertight after conversion. The guide is rendered to PDF with the
pdf-documents skill if it is installed.
"""
import os
import shutil
import subprocess
import sys

import numpy as np
import trimesh

CAD2 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CAD2)
OUT = os.path.join(ROOT, "ARCA_print_files")

FILES = [
    ("stl/arca_fit_check_jig.stl",   "01_PRINT_FIRST_fit_check_jig__any_colour.stl"),
    ("stl/arca_front_shell.stl",     "02_front_shell__SMOKE.stl"),
    ("stl/arca_sd_hatch.stl",        "03_sd_hatch__SMOKE.stl"),
    ("stl/arca_rear_frame.stl",      "04_rear_frame__any_colour.stl"),
    ("stl/arca_bay_tray.stl",        "05_bay_tray__any_colour.stl"),
    ("stl/arca_switch_plates.stl",   "06_switch_plates__any_colour__3pcs.stl"),
    ("stl/arca_display_spacers.stl", "07_display_spacers__any_colour__4pcs.stl"),
    ("stl_extra/arca_buttons_orange.stl",   "08_buttons_A_B__ORANGE__2pcs.stl"),
    ("stl_extra/arca_buttons_slate.stl",    "09_buttons_X_Y__GREY__2pcs.stl"),
    ("stl_extra/arca_buttons_pale.stl",     "10_buttons_START_SELECT__LIGHT_GREY__2pcs.stl"),
    ("stl_extra/arca_buttons_charcoal.stl", "11_dpad_and_shoulders__BLACK__3pcs.stl"),
    ("stl/arca_panel_world.stl",     "12_panel_world__WHITE_with_BLACK_logo.stl"),
    ("stl/arca_panel_arkiv.stl",     "13_panel_arkiv__BLUE_with_WHITE_logo.stl"),
    ("stl/arca_panel_arc.stl",       "14_panel_arc__BLACK_with_WHITE_logo.stl"),
    ("stl/arca_panel_chainlink.stl", "15_panel_chainlink__BLUE_with_WHITE_logo.stl"),
    ("stl_extra/p2s/panel_world__P2S.3mf",     "16_AMS_Bambu_P2S_panel_world__WHITE_body_BLACK_logo.3mf"),
    ("stl_extra/p2s/panel_arkiv__P2S.3mf",     "17_AMS_Bambu_P2S_panel_arkiv__BLUE_body_WHITE_logo.3mf"),
    ("stl_extra/p2s/panel_arc__P2S.3mf",       "18_AMS_Bambu_P2S_panel_arc__BLACK_body_WHITE_logo.3mf"),
    ("stl_extra/p2s/panel_chainlink__P2S.3mf", "19_AMS_Bambu_P2S_panel_chainlink__BLUE_body_WHITE_logo.3mf"),
    ("stl/arca_panel_ethglobal.stl", "20_panel_ethglobal_mumbai__BLACK_with_ORANGE_logo.stl"),
    ("stl_extra/p2s/panel_ethglobal__P2S.3mf", "21_AMS_Bambu_P2S_panel_ethglobal_mumbai__BLACK_body_ORANGE_RED_GREEN_logo.3mf"),
    ("stl/arca_panel_ethglobal_lockup.stl", "22_panel_ethglobal_mumbai_lockup__WHITE_with_RED_logo.stl"),
    ("stl_extra/p2s/panel_ethglobal_lockup__P2S.3mf", "23_AMS_Bambu_P2S_panel_ethglobal_mumbai_lockup__WHITE_body_ORANGE_RED_GREEN_logo.3mf"),
    ("stl/arca_panel_hedera.stl",    "24_panel_hedera__BLACK_with_WHITE_logo.stl"),
    ("stl_extra/p2s/panel_hedera__P2S.3mf",    "25_AMS_Bambu_P2S_panel_hedera__BLACK_body_WHITE_logo.3mf"),
]


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    for src, dst in FILES:
        if src.endswith(".3mf"):                   # Bambu projects from make_panel_p2s.py: checked there
            shutil.copy(os.path.join(CAD2, src), os.path.join(OUT, dst))
            print(f"  ok   {dst}")
            continue
        a = trimesh.load(os.path.join(CAD2, src))
        out = os.path.join(OUT, dst)
        a.export(out, file_type="stl")
        b = trimesh.load(out)
        ok = b.is_watertight and np.allclose(a.bounds, b.bounds, atol=1e-3) and b.bounds[0][2] > -1e-3
        print(f"  {'ok  ' if ok else 'FAIL'} {dst:52s} {b.extents[0]:6.1f} x {b.extents[1]:6.1f} x {b.extents[2]:5.1f}")
        if not ok:
            sys.exit(f"{dst} failed the post-conversion check")

    # guide + pictures (the PDF references the pictures relative to the .md)
    g = os.path.join(CAD2, "preview", "guide")
    for f in ("assembled_front.png", "exploded.png"):
        shutil.copy(os.path.join(g, f), OUT)
    shutil.copy(os.path.join(g, "PRINTING_GUIDE.md"), OUT)
    md2pdf = os.path.join(os.path.expanduser("~"), ".claude", "skills", "pdf-documents", "scripts", "md2pdf.py")
    if os.path.exists(md2pdf):
        subprocess.run([sys.executable, md2pdf, os.path.join(OUT, "PRINTING_GUIDE.md"),
                        "-o", os.path.join(OUT, "00_PRINTING_GUIDE.pdf"),
                        "--css", os.path.join(g, "extra.css")], check=True)
    os.remove(os.path.join(OUT, "PRINTING_GUIDE.md"))
    for f in ("assembled_front.png", "exploded.png"):
        os.remove(os.path.join(OUT, f))
    shutil.copy(os.path.join(ROOT, "stl_viewer.html"), os.path.join(OUT, "view_all_parts_in_3d.html"))

    z = shutil.make_archive(OUT, "zip", ROOT, "ARCA_print_files")
    print("folder:", OUT, f"({len(os.listdir(OUT))} files)")
    print("zip:   ", z, f"{os.path.getsize(z)/1048576:.1f} MB")


if __name__ == "__main__":
    main()

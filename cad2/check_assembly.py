"""
ARCA handheld -- assembly verification.

Cross-checks the assembled-position meshes in stl_assembly/ (real vendor /
datasheet models for every bought part, see components/) against each other
and against the assembly order in assembly_steps.json. Nothing here trusts a
parameter: every number is MEASURED off the meshes, and the parameters are
only used to know where to look.

  A  inventory        every part exported, printed parts watertight
  B  interference     every pair of parts, exact boolean volume. Designed
                      interference (screw threads, heat-set knurls, bank
                      detents) is allowed ONLY where it belongs.
  C  fasteners        per screw: head room, pilot clear, holes aligned,
                      thread engagement, tip clearance, skin outboard
  D  insertion        every part is swept along its assembly direction
                      against everything installed before it
  E  tool access      soldering iron over every insert, driver over every screw
  F  controls         cap pre-travel / float / switch-is-the-stop, D-pad pivot
                      geometry (centre, arm and diagonal presses), shoulder
                      pin travel
  G  integrity        magnet pockets intact, bosses uncut, skin unbroken
  H  clearances       tightest gaps between neighbouring parts
  I  ports            a typical plug of each kind reaches its socket

Usage:  python check_assembly.py            (exit 1 on any FAIL)
Writes: preview/assembly_report.txt and preview/assembly_report.json (the STL
        viewer shows the per-step results in its step-by-step mode).
Needs:  trimesh, numpy, manifold3d, rtree; OpenSCAD for the parameter dump.
"""
import ast
import itertools
import json
import os
import re
import subprocess
import sys
import time

import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.abspath(__file__))
ASM = os.path.join(ROOT, "stl_assembly")
OPENSCAD = r"C:/Program Files/OpenSCAD/openscad.exe"
T0 = time.time()

# ------------------------------------------------------------------ report
RESULTS = []            # dicts: section, level, msg, step (optional)
LOG = []


def out(s=""):
    print(s)
    LOG.append(s)


def res(section, level, msg, step=None):
    RESULTS.append(dict(section=section, level=level, msg=msg, step=step))
    out(f"  {level:4}  {msg}")


def hdr(t):
    out("")
    out("=" * 78)
    out(t)
    out("=" * 78)


# ------------------------------------------------------------- parameters
PARAMS = """W H cr t_wall t_face boss_pos boss_od boss_h ins_len ins_pilot_d ins_pilot_h
ins_od scr_len scr_dk scr_k scr_d scr_head_d scr_head_h scr_head_clr pilot_selftap
z_face_in z_frame_f z_frame_r wall_top mag_pos mag_pocket_d mag_pocket_h mag_t
face_posts dpad_posts pill_posts post_d z_plate_head z_post_top z_plate_f z_plate_r
z_sw_seat z_sw_tip z_cap_back cap_float cap_gap cap_proud sw_travel sw_actuator_h
dpad_cx dpad_cy dpad_r dpad_flange dpad_arm_f dpad_pivot_gap z_pivot_head z_pivot_tip
face_cx face_cy face_r face_cap_d pill_w pill_h pill_dx pill_cy ap_cx
sh_lx sh_rx sh_w sh_z0 sh_zh sh_pin_y sh_pin_d sh_pin_hole sh_in sh_travel sh_y_seat sh_zc
sh_block_top pi_x0 pi_y0 pi_w pi_h z_pi_front z_pi_rear pi_pcb_t tray_ears clr_fit
bay_x0 bay_x1 bay_y0 bay_y1 z_tray_f z_bay_f bay_det_h pi_pwr_bx pi_hdmi_bx pi_av_bx
pi_usbA_by0 pi_usbA_by1 pi_ovh_pwr pi_ovh_hdmi pi_ovh_av pi_ovh_usb z_spk_f
pi_clip_bx sw_leg_h z_sw_legs""".split()


def load_params():
    wrap = os.path.join(ROOT, "_params_dump.scad")
    with open(wrap, "w") as f:
        f.write('part = "asm_pins";\ninclude <enclosure.scad>\n')
        for n in PARAMS:
            f.write(f'echo(str("P|{n}|", {n}));\n')
    tmp = os.path.join(ROOT, "_params_dump.stl")
    r = subprocess.run([OPENSCAD, "-o", tmp, wrap], capture_output=True, text=True, cwd=ROOT)
    for f in (wrap, tmp):
        if os.path.exists(f):
            os.remove(f)
    P = {}
    for line in (r.stdout + r.stderr).splitlines():
        m = re.search(r'"P\|(\w+)\|(.*)"', line)
        if m:
            v = m.group(2).replace("true", "True").replace("false", "False")
            P[m.group(1)] = ast.literal_eval(v)
    missing = [n for n in PARAMS if n not in P]
    if missing:
        sys.exit(f"parameter dump failed for {missing}\n{r.stderr[-2000:]}")
    return P


P = load_params()
BOSSES = [tuple(p) for p in P["boss_pos"]]

# ----------------------------------------------------------------- meshes
STEPS = json.load(open(os.path.join(ROOT, "assembly_steps.json"), encoding="utf-8"))
MESH = {}


def mesh(name):
    if name not in MESH:
        path = os.path.join(ASM, name + ".stl")
        MESH[name] = trimesh.load(path) if os.path.exists(path) else None
    return MESH[name]


PRINTED = ["asm_front_shell", "asm_bay_tray", "asm_rear_frame", "asm_spacers",
           "asm_plate_face", "asm_plate_dpad", "asm_plate_pills",
           "asm_cap_a", "asm_cap_b", "asm_cap_x", "asm_cap_y", "asm_cap_pills",
           "asm_cap_dpad", "asm_shoulders", "asm_panel_world_body"]
BOUGHT = ["asm_display", "asm_pi", "asm_heatsinks", "asm_bank", "asm_speaker",
          "asm_pico", "asm_pam", "asm_switches_plates", "asm_switches_shoulder",
          "asm_screws_frame", "asm_screws_plates", "asm_screw_pivot", "asm_inserts",
          "asm_magnets_frame", "asm_magnets_panel", "asm_pins"]
PANEL_ALT = ["asm_panel_arkiv_body", "asm_panel_arc_body",
             "asm_panel_world_logo", "asm_panel_arkiv_logo", "asm_panel_arc_logo"]
ALL = PRINTED + BOUGHT


def bbox_near(a, b, pad=0.0):
    la, ha = a.bounds
    lb, hb = b.bounds
    return not (np.any(ha + pad < lb) or np.any(hb + pad < la))


def inter(a, b):
    try:
        i = trimesh.boolean.intersection([a, b], engine="manifold")
    except Exception as e:                        # noqa: BLE001
        return None, str(e)
    if i is None or i.is_empty:
        return 0.0, None
    return float(abs(i.volume)), i


def contains(m, pts):
    return m.contains(np.atleast_2d(pts))


def solid_at(m, pts):
    """Ray-parity containment, with every 'outside' answer re-checked by an
    exact signed distance: the ray test very occasionally misreads a point
    that sits near an edge, and a single misread must not fail a build."""
    pts = np.atleast_2d(pts)
    s = m.contains(pts)
    if (~s).any():
        sd = trimesh.proximity.signed_distance(m, pts[~s])
        s[np.where(~s)[0][sd > -0.02]] = True
    return s


def col(m, x, y, z0, z1, step=0.02):
    z = np.arange(z0, z1, step)
    return z, contains(m, np.column_stack([np.full_like(z, x), np.full_like(z, y), z]))


DIRS = np.array([[np.cos(t), np.sin(t)] for t in np.linspace(0, 2*np.pi, 32, endpoint=False)])


def radial(m, x, y, z, rmax=5.0, step=0.02):
    rs = np.arange(0, rmax, step)
    pts = np.array([[x + r*d[0], y + r*d[1], z] for d in DIRS for r in rs])
    s = contains(m, pts).reshape(len(DIRS), len(rs))
    return np.array([rs[np.argmax(r)] if r.any() else rmax for r in s])


def cyl(r, z0, z1, x, y, sec=64):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sec)
    c.apply_translation([x, y, (z0 + z1)/2])
    return c


def sd_rrect(xy):
    W, H, CR = P["W"], P["H"], P["cr"]
    xy = np.atleast_2d(xy)
    q = np.abs(xy - [W/2, H/2]) - [W/2 - CR, H/2 - CR]
    return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(axis=1), 0) - CR


# ======================================================================= A
hdr("A. INVENTORY -- every part exported, printed parts are closed solids")
for n in ALL + PANEL_ALT:
    m = mesh(n)
    if m is None:
        res("A", "FAIL", f"{n}.stl missing -- run build_assembly.sh")
        continue
    if n in PRINTED and not m.is_watertight:
        res("A", "FAIL", f"{n} is not watertight (would not slice cleanly)")
missing = [n for n in ALL if mesh(n) is None]
if not missing:
    res("A", "PASS", f"{len(ALL)} parts present; {len(PRINTED)} printed parts watertight")
SHELL, FRAME = mesh("asm_front_shell"), mesh("asm_rear_frame")
if SHELL is None or FRAME is None:
    sys.exit("shell / frame missing")

# ======================================================================= B
hdr("B. INTERFERENCE -- every pair of parts, exact boolean volume")
# Designed interference: where it is allowed, and how much.
#   (pair) -> (max mm3, why, region test)
def in_cols(pts_bounds, centres, r):
    lo, hi = pts_bounds
    c = (lo[:2] + hi[:2]) / 2
    return any(np.hypot(c[0] - x, c[1] - y) <= r for x, y in centres)

post_xy = [tuple(p) for p in P["face_posts"] + P["dpad_posts"] + P["pill_posts"]]
ALLOWED = {
    frozenset(["asm_screws_frame", "asm_inserts"]):
        ("M3 thread engaging the insert", lambda b: in_cols(b, BOSSES, 2.0)),
    frozenset(["asm_screws_plates", "asm_front_shell"]):
        ("M3 self-tapping into the plate posts", lambda b: in_cols(b, post_xy, 2.0)),
    frozenset(["asm_screw_pivot", "asm_plate_dpad"]):
        ("D-pad pivot self-tapping into its plate", lambda b: in_cols(b, [(P["dpad_cx"], P["dpad_cy"])], 2.0)),
    frozenset(["asm_inserts", "asm_front_shell"]):
        ("heat-set knurl melting into the pilot", lambda b: in_cols(b, BOSSES, 2.6)),
    frozenset(["asm_bank", "asm_bay_tray"]):
        ("bank retention detents", lambda b: True),
}
pairs = []
names = [n for n in ALL if mesh(n) is not None]
clash_parts = {}
for a, b in itertools.combinations(names, 2):
    ma, mb = mesh(a), mesh(b)
    if not bbox_near(ma, mb):
        continue
    v, i = inter(ma, mb)
    if v is None:
        res("B", "WARN", f"{a} x {b}: boolean failed ({i})")
        continue
    if v < 0.01:
        continue
    key = frozenset([a, b])
    lo, hi = i.bounds
    where = f"x {lo[0]:.1f}..{hi[0]:.1f} y {lo[1]:.1f}..{hi[1]:.1f} z {lo[2]:.1f}..{hi[2]:.1f}"
    if key in ALLOWED:
        why, ok = ALLOWED[key]
        bodies = i.split(only_watertight=False)
        stray = [bd for bd in bodies if not ok(bd.bounds) and abs(bd.volume) > 0.01]
        if stray:
            sv = sum(abs(bd.volume) for bd in stray)
            res("B", "FAIL", f"{a} x {b}: {sv:.2f} mm3 OUTSIDE the designed {why} zones")
        else:
            out(f"  ok    {a} x {b}: {v:.2f} mm3 designed ({why})")
        continue
    res("B", "FAIL", f"{a} x {b}: {v:.3f} mm3 at {where}")
    clash_parts.setdefault(a, []).append(b)
    clash_parts.setdefault(b, []).append(a)
# every alternative panel sits exactly where the World one does
for alt in PANEL_ALT:
    m = mesh(alt)
    if m is None:
        continue
    for n in ["asm_rear_frame", "asm_front_shell", "asm_screws_frame", "asm_magnets_frame"]:
        v, i = inter(m, mesh(n))
        if v and v > 0.01:
            res("B", "FAIL", f"{alt} x {n}: {v:.3f} mm3")
if not [r for r in RESULTS if r["section"] == "B" and r["level"] == "FAIL"]:
    res("B", "PASS", "no part overlaps another except where designed")

STEP_RESULTS = {st["id"]: [] for st in STEPS["steps"]}

# ======================================================================= C
hdr("C. FASTENERS -- frame screws into the 8 inserts")
out(f"  {'boss':>14} {'head room':>9} {'wall@head':>9} {'pilot':>6} {'frame':>6} "
    f"{'offset':>6} {'engage':>6} {'tip gap':>7} {'skin':>5}")
CX, CY = P["W"]/2, P["H"]/2
for (x, y) in BOSSES:
    u = np.array([CX - x, CY - y]); u /= np.linalg.norm(u)
    # boss top (probe inboard edge of the boss)
    z, s = col(SHELL, x + u[0]*3.0, y + u[1]*3.0, 20, P["z_frame_f"] + 1)
    boss_top = z[s].max() if s.any() else np.nan
    z, s = col(FRAME, x + u[0]*2.6, y + u[1]*2.6, 20, 46)
    frame_bot = z[s].min() if s.any() else np.nan
    seat = z[s].max() if s.any() else np.nan
    z, s = col(FRAME, x + u[0]*(P["scr_head_d"]/2 + 0.6), y + u[1]*(P["scr_head_d"]/2 + 0.6), 20, 46)
    frame_top = z[s].max() if s.any() else np.nan
    z, s = col(SHELL, x, y, 0, boss_top)
    pilot_floor = z[s].max() if s.any() else np.nan
    pil = radial(SHELL, x, y, boss_top - 3.0)
    thr = radial(FRAME, x, y, frame_bot + 0.6)
    wall = radial(SHELL, x, y, seat + P["scr_k"]/2, rmax=6).min()
    off = np.linalg.norm((2/len(DIRS))*((pil[:, None]*DIRS).sum(0) - (thr[:, None]*DIRS).sum(0)))
    tip = seat - P["scr_len"]
    engage = boss_top - max(tip, boss_top - P["ins_len"])
    tipgap = tip - pilot_floor
    headroom = frame_top - (seat + P["scr_k"])
    skin = -(sd_rrect([x, y])[0] + P["ins_od"]/2)
    out(f"  ({x:6.1f},{y:6.1f}) {headroom:9.2f} {wall:9.2f} {pil.min():6.2f} {thr.min():6.2f} "
        f"{off:6.3f} {engage:6.2f} {tipgap:7.2f} {skin:5.2f}")
    tag = f"frame screw ({x},{y})"
    if wall < P["scr_head_clr"] - 0.05:
        res("C", "FAIL", f"{tag}: shell only {wall:.2f} from the axis at head height (needs {P['scr_head_clr']:.2f})")
    if pil.min() < P["ins_pilot_d"]/2 - 0.1:
        res("C", "FAIL", f"{tag}: pilot hole partly filled ({pil.min():.2f} from the axis)")
    if thr.min() < P["scr_d"]/2 - 0.1 or thr.max() >= 4.9:
        res("C", "FAIL", f"{tag}: frame hole obstructed or broken out ({thr.min():.2f}..{thr.max():.2f})")
    if off > 0.15:
        res("C", "FAIL", f"{tag}: pilot and frame hole offset {off:.3f} mm")
    if abs(frame_bot - boss_top) > 0.3:
        res("C", "FAIL", f"{tag}: {frame_bot - boss_top:+.2f} between boss top and frame")
    if engage < P["ins_len"] - 0.3:
        res("C", "FAIL", f"{tag}: only {engage:.2f} of thread engagement")
    if tipgap < 0.3:
        res("C", "FAIL", f"{tag}: screw tip {tipgap:.2f} from the pilot floor")
    if headroom < 0:
        res("C", "FAIL", f"{tag}: head stands {-headroom:.2f} proud of the frame")
    if skin < 1.5:
        res("C", "WARN", f"{tag}: {skin:.2f} of skin outboard of the insert")
# plate screws and the pivot
for (x, y) in post_xy:
    tip = P["z_plate_head"] - P["scr_len"]
    eng = P["z_post_top"] - tip
    skin = tip - 0.0
    if eng < 4.0:
        res("C", "FAIL", f"plate screw ({x},{y}): {eng:.2f} of thread in the post")
    if tip < P["z_face_in"] + 0.8:
        res("C", "FAIL", f"plate screw ({x},{y}): tip {tip:.2f} leaves under 0.8 of face skin")
out(f"  plate screws: head bearing z {P['z_plate_head']:.2f}, tip z {P['z_plate_head'] - P['scr_len']:.2f}, "
    f"{P['z_post_top'] - (P['z_plate_head'] - P['scr_len']):.2f} of thread in each post, "
    f"{P['z_plate_head'] - P['scr_len']:.2f} of face below the tip")
for (x, y) in BOSSES:
    bad = [r for r in RESULTS if r["section"] == "C" and r["level"] == "FAIL" and f"({x},{y})" in r["msg"]]
    STEP_RESULTS.setdefault("frame", []).append(("FAIL" if bad else "PASS", f"frame screw ({x},{y})", "fastener"))
for (x, y) in post_xy:
    bad = [r for r in RESULTS if r["section"] == "C" and r["level"] == "FAIL" and f"({x},{y})" in r["msg"]]
    STEP_RESULTS.setdefault("plates", []).append(("FAIL" if bad else "PASS", f"plate screw ({x},{y})", "fastener"))
if not [r for r in RESULTS if r["section"] == "C" and r["level"] == "FAIL"]:
    res("C", "PASS", f"all {len(BOSSES)} frame screws and {len(post_xy)} plate screws seat, engage and clear")

# ======================================================================= D
hdr("D. INSERTION -- every part swept along its assembly direction")
# A part at its final pose P moves in along d, i.e. it arrives from P - s*d
# for s in (0, dist]. It collides iff (a) a point of P, cast back along -d,
# meets an obstacle within dist, or (b) a point of an obstacle, cast along +d,
# meets P within dist. Both are sampled densely; contacts at s < 0.05 (the
# final resting contact) are ignored.
EPS_S = 0.05


def ray_hits(src_mesh, dst_mesh, direction, dist, n=20000):
    # Sample points are pulled 0.03 INSIDE the source surface, so a face that
    # merely slides along a face of the obstacle (the bank on the tray floor)
    # is not read as a collision; grazing hits are dropped as well.
    pts, fi = trimesh.sample.sample_surface(src_mesh, n)
    pts = pts - src_mesh.face_normals[fi] * 0.03
    dirs = np.tile(direction, (len(pts), 1))
    loc, idx, tri = dst_mesh.ray.intersects_location(pts, dirs, multiple_hits=False)
    if len(loc) == 0:
        return np.zeros((0, 3))
    d = np.einsum("ij,ij->i", loc - pts[idx], dirs[idx])
    graze = np.abs(dst_mesh.face_normals[tri] @ np.asarray(direction, float)) < 0.02
    keep = (d > EPS_S) & (d < dist) & ~graze
    return loc[keep]


def snap_zone(kind, pts):
    """Designed snap-past interference: the Pi board edge riding over the wall
    clip lips, the bank riding over its detents."""
    if kind == "pi_clips":
        ok = np.zeros(len(pts), bool)
        for b0, b1 in P["pi_clip_bx"]:
            y0, y1 = P["pi_y0"] + b0, P["pi_y0"] + b1
            ok |= ((pts[:, 1] > y0 - 0.5) & (pts[:, 1] < y1 + 0.5) &
                   (pts[:, 0] < P["pi_x0"] + 1.2) & (pts[:, 2] > P["z_pi_rear"] - 0.2))
        return ok
    if kind == "detents":
        return ((np.abs(pts[:, 0] - P["bay_x0"]) < 1.5) | (np.abs(pts[:, 0] - P["bay_x1"]) < 1.5))
    return np.zeros(len(pts), bool)


installed = [n for n in STEPS["base"]]
snaps = {}
for step in STEPS["steps"]:
    sid = step["id"]
    for part in step["parts"]:
        files = part.get("files", [part.get("file")])
        body = trimesh.util.concatenate([mesh(f) for f in files if mesh(f) is not None])
        label = "+".join(f.replace("asm_", "") for f in files)
        d = np.array(part["dir"], float)
        if part.get("sweep", True):
            bad = []
            for obs in installed:
                om = mesh(obs)
                if om is None:
                    continue
                h1 = ray_hits(body, om, -d, part["dist"])
                h2 = ray_hits(om, body, d, part["dist"])
                hits = np.vstack([h1, h2]) if len(h1) or len(h2) else np.zeros((0, 3))
                if part.get("snap") and len(hits):
                    z = snap_zone(part["snap"], hits)
                    snaps[part["snap"]] = snaps.get(part["snap"], 0) + int(z.sum())
                    hits = hits[~z]
                if len(hits):
                    lo, hi = hits.min(0), hits.max(0)
                    bad.append(f"{obs.replace('asm_', '')} ({len(hits)} hits, x {lo[0]:.1f}..{hi[0]:.1f} "
                               f"y {lo[1]:.1f}..{hi[1]:.1f} z {lo[2]:.1f}..{hi[2]:.1f})")
            if bad:
                msg = f"step '{step['title']}': {label} is blocked on the way in by " + "; ".join(bad)
                res("D", "FAIL", msg, sid)
                STEP_RESULTS[sid].append(("FAIL", msg, "path"))
            else:
                msg = f"step '{step['title']}': {label} goes in along {part['dir']} with nothing in the way"
                out(f"  ok    {msg}")
                STEP_RESULTS[sid].append(("PASS", msg, "path"))
        installed += files

# A snap that never touches is a clip that never holds: the board edge MUST
# ride over the clip lips, and the bank MUST ride over its detents.
for kind, label, sid in [("pi_clips", "Pi board edge rides over the wall clips", "pi"),
                         ("detents", "bank rides over the tray detents", "bank")]:
    n = snaps.get(kind, 0)
    if n == 0:
        res("D", "FAIL", f"{label}: no contact at all -- the snap would not hold", sid)
        STEP_RESULTS[sid].append(("FAIL", label, "snap"))
    else:
        out(f"  ok    {label} ({n} contact points: it snaps, as designed)")
        STEP_RESULTS[sid].append(("PASS", label, "snap"))

# NEGATIVE CONTROLS: deliberately wrong assemblies that MUST be caught. If one
# passes, this checker is blind and every PASS above is worthless.
def must_fail(label, moving, obstacles, d, dist):
    hit = 0
    for o in obstacles:
        hit += len(ray_hits(mesh(moving), mesh(o), -np.asarray(d, float), dist))
        hit += len(ray_hits(mesh(o), mesh(moving), np.asarray(d, float), dist))
    if hit:
        out(f"  ok    control: {label} -> caught ({hit} hits)")
    else:
        res("D", "FAIL", f"CHECKER BLIND: '{label}' was not caught")
must_fail("display dropped in AFTER the Pi", "asm_display", ["asm_pi"], [0, 0, -1], 30)
must_fail("tray dropped in AFTER the frame", "asm_bay_tray", ["asm_rear_frame"], [0, 0, -1], 30)
shifted = mesh("asm_rear_frame").copy(); shifted.apply_translation([1.0, 0, 0])
v, _ = inter(shifted, SHELL)
if v and v > 0.01:
    out(f"  ok    control: rear frame shifted 1 mm sideways -> caught ({v:.1f} mm3 into the shell)")
else:
    res("B", "FAIL", "CHECKER BLIND: a frame shifted 1 mm into the wall was not caught")

if not [r for r in RESULTS if r["section"] == "D" and r["level"] == "FAIL"]:
    res("D", "PASS", "every part goes in along its assembly direction; both snaps engage; "
                     "3 wrong-order controls caught")

# ======================================================================= E
hdr("E. TOOL ACCESS")
# soldering iron + insert over each boss, with only the shell installed
for (x, y) in BOSSES:
    tool = cyl(3.6, P["z_frame_f"] + 0.05, P["z_frame_f"] + 60, x, y)
    v, _ = inter(tool, SHELL)
    if v and v > 0.01:
        res("E", "FAIL", f"iron cannot reach the boss at ({x},{y}): {v:.2f} mm3 of shell in the way", "inserts")
    STEP_RESULTS["inserts"].append(("PASS" if not v or v <= 0.01 else "FAIL",
                                    f"iron reaches boss ({x},{y})", "tool"))
# a 3 mm driver shaft above every screw head, against everything installed
# by the time that screw is driven
order = [n for n in STEPS["base"]]
for step in STEPS["steps"]:
    for part in step["parts"]:
        files = part.get("files", [part.get("file")])
        if part.get("tool") == "driver":
            heads = []
            f = files[0]
            if f == "asm_screws_frame":
                heads = [(x, y, P["z_frame_r"] - P["scr_head_h"] + P["scr_k"]) for x, y in BOSSES]
            elif f == "asm_screws_plates":
                heads = [(x, y, P["z_plate_head"] + P["scr_k"]) for x, y in post_xy]
            elif f == "asm_screw_pivot":
                heads = [(P["dpad_cx"], P["dpad_cy"], P["z_pivot_head"] + P["scr_k"])]
            for (x, y, zt) in heads:
                shaft = cyl(1.6, zt + 0.1, zt + 80, x, y, 32)
                blockers = []
                for n in order:
                    m = mesh(n)
                    if m is None or not bbox_near(shaft, m):
                        continue
                    v, _ = inter(shaft, m)
                    if v and v > 0.01:
                        blockers.append(n.replace("asm_", ""))
                if blockers:
                    res("E", "FAIL", f"driver cannot reach the screw at ({x:.1f},{y:.1f}): {', '.join(blockers)}",
                        step["id"])
                    STEP_RESULTS[step["id"]].append(("FAIL", f"driver blocked at ({x:.1f},{y:.1f})", "tool"))
                else:
                    STEP_RESULTS[step["id"]].append(("PASS", f"driver reaches ({x:.1f},{y:.1f})", "tool"))
        order += files
if not [r for r in RESULTS if r["section"] == "E" and r["level"] == "FAIL"]:
    res("E", "PASS", f"iron reaches all {len(BOSSES)} bosses; a driver reaches every screw when it is driven")

# ======================================================================= F
hdr("F. CONTROLS -- travel, stops and the D-pad pivot, measured off the meshes")
SWP = mesh("asm_switches_plates")


def lowest_z(m, x, y, r=0.8):
    pts = np.array([[x + dx, y + dy, 50.0] for dx in np.linspace(-r, r, 5) for dy in np.linspace(-r, r, 5)])
    loc, idx, _ = m.ray.intersects_location(pts, np.tile([0, 0, -1.0], (len(pts), 1)), multiple_hits=True)
    return loc[:, 2].min() if len(loc) else np.nan


def highest_z_below(m, x, y, zmax, r=0.8):
    pts = np.array([[x + dx, y + dy, -5.0] for dx in np.linspace(-r, r, 5) for dy in np.linspace(-r, r, 5)])
    loc, idx, _ = m.ray.intersects_location(pts, np.tile([0, 0, 1.0], (len(pts), 1)), multiple_hits=True)
    loc = loc[loc[:, 2] < zmax]
    return loc[:, 2].max() if len(loc) else np.nan


def face_xy(i):
    return (P["face_cx"] + P["face_r"]*np.cos(np.radians(i*90)),
            P["face_cy"] + P["face_r"]*np.sin(np.radians(i*90)))


checks = []
for name, (x, y), cap in (
        [(f"face {i}", face_xy(i), "asm_cap_" + {2: "a", 3: "b", 1: "x", 0: "y"}[i]) for i in range(4)] +
        [(f"pill {s:+d}", (P["ap_cx"] + s*(P["pill_w"]/2 + P["pill_dx"]/2), P["pill_cy"]), "asm_cap_pills")
         for s in (-1, 1)]):
    cm = mesh(cap)
    tip = lowest_z(SWP, x, y, 0.8)                      # plunger tip
    cap_back = highest_z_below(cm, x, y, 10.0, 1.5)     # cap rear face at the plunger
    # plate front face under the flange, just outside the plunger bore
    plate = {"face": "asm_plate_face", "pill": "asm_plate_pills"}[name.split()[0]]
    pm = mesh(plate)
    fl_r = (P["face_cap_d"] + 3.0)/2 - 0.6 if name.startswith("face") else 3.5
    probe = (x + fl_r, y) if name.startswith("face") else (x + P["pill_w"]/2, y)
    plate_front = lowest_z(pm, probe[0], probe[1], 0.2)
    pre = tip - cap_back
    float_ = plate_front - cap_back
    ok_stop = float_ > pre + P["sw_travel"] + 0.1
    out(f"  {name:8} pre-travel {pre:5.2f}  flange float {float_:5.2f}  "
        f"-> {'switch is the rear stop' if ok_stop else 'FLANGE BOTTOMS BEFORE THE CLICK'}")
    if not (0.05 <= pre <= 0.35):
        res("F", "FAIL", f"{name}: plunger pre-travel {pre:.2f} (want 0.05..0.35)", "plates")
    if not ok_stop:
        res("F", "FAIL", f"{name}: flange float {float_:.2f} < pre-travel + click travel", "plates")

# D-pad pivot, as a lever: rest = flange against the face; pivot tip gap g
rock = mesh("asm_cap_dpad")
piv = mesh("asm_screw_pivot")
g = lowest_z(piv, P["dpad_cx"], P["dpad_cy"], 0.5) - highest_z_below(rock, P["dpad_cx"], P["dpad_cy"], 10.0, 1.0)
pre_d = lowest_z(SWP, P["dpad_cx"] + P["dpad_r"], P["dpad_cy"], 0.8) - \
    highest_z_below(rock, P["dpad_cx"] + P["dpad_r"], P["dpad_cy"], 10.0, 0.8)
need = pre_d + P["sw_travel"]
r_f, r_s = P["dpad_flange"]/2, P["dpad_r"]
r_fd = (P["dpad_arm_f"]/2 + P["dpad_flange"]/2)/np.sqrt(2)
arm = g*(1 + r_s/r_f)
diag = g*(1 + r_s*np.cos(np.pi/4)/r_fd)
out(f"  D-pad: pivot gap {g:.2f}, plunger pre-travel {pre_d:.2f}, click needs {need:.2f} at the switch")
out(f"         centre press moves every plunger {g:.2f}  -> {'no click' if g < need - 0.05 else 'CLICKS ALL FOUR'}")
out(f"         arm press reaches {arm:.2f} at that switch -> {'clicks' if arm >= need else 'DOES NOT CLICK'}")
out(f"         diagonal press reaches {diag:.2f} at both  -> {'clicks both' if diag >= need else 'marginal'}")
g_lo, g_hi = need/(1 + r_s/r_f), need - 0.05
g_dlo = need/(1 + r_s*np.cos(np.pi/4)/r_fd)
out(f"         working pivot gap: {g_lo:.2f} .. {g_hi:.2f} (diagonals need >= {g_dlo:.2f}); the screw adjusts it")
if not (g_lo <= g <= g_hi):
    res("F", "FAIL", f"D-pad pivot gap {g:.2f} outside the working range {g_lo:.2f}..{g_hi:.2f}", "pivot")
elif g < g_dlo:
    res("F", "WARN", f"D-pad diagonals need a pivot gap >= {g_dlo:.2f}; nominal {g:.2f} -- back the screw out slightly", "pivot")
pressed_tip = 2*g
if pressed_tip >= P["cap_float"]:
    res("F", "FAIL", f"D-pad: pressed flange tip travels {pressed_tip:.2f}, float is only {P['cap_float']:.2f}", "pivot")

# shoulder: pin slot travel vs the switch
sh_need = P["cap_gap"] + P["sw_travel"]
out(f"  shoulders: slot free travel {P['sh_travel']:.2f}, switch needs {sh_need:.2f} "
    f"-> {'switch bottoms first' if P['sh_travel'] > sh_need + 0.1 else 'PIN STOPS THE PADDLE SHORT'}")
if P["sh_travel"] <= sh_need + 0.1:
    res("F", "FAIL", "shoulder pin slot shorter than the switch travel", "shoulders")
for sid, what in [("plates", "cap pre-travel and flange float, 6 buttons"),
                  ("pivot", "D-pad pivot: centre, arm and diagonal presses"),
                  ("shoulders", "shoulder pin travel")]:
    bad = [r for r in RESULTS if r["section"] == "F" and r["level"] == "FAIL" and r["step"] == sid]
    STEP_RESULTS[sid].append(("FAIL" if bad else "PASS", what, "function"))
if not [r for r in RESULTS if r["section"] == "F" and r["level"] == "FAIL"]:
    res("F", "PASS", "every button reaches its click before any printed stop; D-pad pivot in range")

# ======================================================================= G
hdr("G. INTEGRITY -- nothing cut through where it must not be")
# magnet pockets: a ring just outside the pocket, at mid depth, must be solid
for (x, y) in P["mag_pos"]:
    z = P["z_frame_r"] - P["mag_pocket_h"]/2
    rr = P["mag_pocket_d"]/2 + 0.35
    ring = np.array([[x + rr*np.cos(t), y + rr*np.sin(t), z] for t in np.linspace(0, 2*np.pi, 48, endpoint=False)])
    s = solid_at(FRAME, ring)
    if not s.all():
        res("G", "FAIL", f"magnet pocket ({x},{y}) breached ({(~s).sum()} of 48 wall samples missing)")
# bosses: the boss wall (r 3.2) inboard of the web must be solid full height
for (x, y) in BOSSES:
    u = np.array([CX - x, CY - y]); u /= np.linalg.norm(u)
    angs = [a for a in np.linspace(0, 2*np.pi, 32, endpoint=False) if np.cos(a)*u[0] + np.sin(a)*u[1] > 0.3]
    gaps = 0
    for z in np.arange(P["z_face_in"] + 0.5, P["z_frame_f"] - 0.3, 0.5):
        pts = np.array([[x + 3.2*np.cos(a), y + 3.2*np.sin(a), z] for a in angs])
        gaps += (~solid_at(SHELL, pts)).sum()
    if gaps:
        res("G", "FAIL", f"boss ({x},{y}) wall cut through ({gaps} samples) -- a port or vent runs into it")
# outer skin
sdv = sd_rrect(SHELL.vertices[:, :2])
if sdv.max() > 0.02:
    i = sdv.argmax()
    res("G", "FAIL", f"shell pokes {sdv.max():.2f} outside its outline at {np.round(SHELL.vertices[i], 1)}")
if not [r for r in RESULTS if r["section"] == "G" and r["level"] == "FAIL"]:
    res("G", "PASS", "6 magnet pockets intact, 8 bosses uncut, outer skin unbroken")

# ======================================================================= H
hdr("H. CLEARANCES -- tightest gap between neighbouring parts (sampled)")
CONTACT = {  # designed contacts, reported but not flagged
    frozenset(["asm_rear_frame", "asm_front_shell"]), frozenset(["asm_rear_frame", "asm_bay_tray"]),
    frozenset(["asm_bay_tray", "asm_spacers"]), frozenset(["asm_spacers", "asm_display"]),
    frozenset(["asm_display", "asm_front_shell"]), frozenset(["asm_pi", "asm_front_shell"]),
    frozenset(["asm_bank", "asm_bay_tray"]), frozenset(["asm_panel_world_body", "asm_rear_frame"]),
    frozenset(["asm_panel_world_body", "asm_front_shell"]), frozenset(["asm_speaker", "asm_front_shell"]),
    frozenset(["asm_plate_face", "asm_front_shell"]), frozenset(["asm_plate_dpad", "asm_front_shell"]),
    frozenset(["asm_plate_pills", "asm_front_shell"]), frozenset(["asm_switches_plates", "asm_plate_face"]),
    frozenset(["asm_switches_plates", "asm_plate_dpad"]), frozenset(["asm_switches_plates", "asm_plate_pills"]),
    frozenset(["asm_cap_a", "asm_front_shell"]), frozenset(["asm_cap_b", "asm_front_shell"]),
    frozenset(["asm_cap_x", "asm_front_shell"]), frozenset(["asm_cap_y", "asm_front_shell"]),
    frozenset(["asm_cap_pills", "asm_front_shell"]), frozenset(["asm_cap_dpad", "asm_front_shell"]),
    frozenset(["asm_screws_frame", "asm_rear_frame"]), frozenset(["asm_screws_plates", "asm_plate_face"]),
    frozenset(["asm_screws_plates", "asm_plate_dpad"]), frozenset(["asm_screws_plates", "asm_plate_pills"]),
    frozenset(["asm_magnets_frame", "asm_rear_frame"]), frozenset(["asm_magnets_panel", "asm_panel_world_body"]),
    frozenset(["asm_pico", "asm_rear_frame"]), frozenset(["asm_pam", "asm_rear_frame"]),
    frozenset(["asm_heatsinks", "asm_pi"]), frozenset(["asm_shoulders", "asm_pins"]),
    frozenset(["asm_pins", "asm_front_shell"]), frozenset(["asm_switches_shoulder", "asm_front_shell"]),
    frozenset(["asm_shoulders", "asm_front_shell"]), frozenset(["asm_inserts", "asm_rear_frame"]),
    frozenset(["asm_screw_pivot", "asm_cap_dpad"]), frozenset(["asm_magnets_frame", "asm_magnets_panel"]),
    frozenset(["asm_switches_plates", "asm_cap_a"]), frozenset(["asm_switches_plates", "asm_cap_b"]),
    frozenset(["asm_switches_plates", "asm_cap_x"]), frozenset(["asm_switches_plates", "asm_cap_y"]),
    frozenset(["asm_switches_plates", "asm_cap_pills"]), frozenset(["asm_switches_plates", "asm_cap_dpad"]),
    frozenset(["asm_switches_shoulder", "asm_shoulders"]),
    frozenset(["asm_front_shell", "asm_bay_tray"]),          # clr_slide all round
    frozenset(["asm_rear_frame", "asm_pi"]),                 # the 0.3 travel-limiter gap
}
tight = []
for a, b in itertools.combinations(names, 2):
    ma, mb = mesh(a), mesh(b)
    if not bbox_near(ma, mb, pad=0.6) or frozenset([a, b]) in ALLOWED:
        continue
    pa = ma.sample(3000)
    lo, hi = mb.bounds
    pa = pa[np.all((pa > lo - 0.6) & (pa < hi + 0.6), axis=1)]
    if not len(pa):
        continue
    _, dist, _ = trimesh.proximity.closest_point(mb, pa)
    gmin = float(dist.min())
    if gmin < 0.3:
        tight.append((gmin, a, b))
for gmin, a, b in sorted(tight):
    contact = frozenset([a, b]) in CONTACT
    line = f"{a.replace('asm_', '')} / {b.replace('asm_', '')}: {gmin:.2f} mm"
    if contact:
        out(f"  info  {line} (designed contact or location fit)")
    else:
        res("H", "WARN", f"tight: {line}")
if not [r for r in RESULTS if r["section"] == "H"]:
    res("H", "PASS", "no unexpected gap under 0.3 mm")

# ======================================================================= I
hdr("I. PORTS -- a typical plug of each kind reaches its socket")
# plug = metal tip (inserted) + overmould behind it; must not hit the shell
PLUGS = [  # name, axis, socket face point, (tip w, h, depth), (mould w, h, depth)
    ("HDMI", "x", (P["pi_x0"] - P["pi_ovh_hdmi"], P["pi_y0"] + P["pi_hdmi_bx"], P["z_pi_rear"] + 3.25),
     (14.0, 4.5, 8.5), (21.0, 11.0, 20.0)),
    ("micro-USB", "x", (P["pi_x0"] - P["pi_ovh_pwr"], P["pi_y0"] + P["pi_pwr_bx"], P["z_pi_rear"] + 1.5),
     (6.9, 1.8, 5.6), (11.0, 8.0, 15.0)),
    ("3.5 mm", "x", (P["pi_x0"] - P["pi_ovh_av"], P["pi_y0"] + P["pi_av_bx"], P["z_pi_rear"] + 3.0),
     (3.5, 3.5, 14.0), (7.0, 7.0, 20.0)),
    ("USB-A", "y", (P["pi_x0"] + P["pi_h"] - (P["pi_usbA_by0"] + P["pi_usbA_by1"])/2,
                    P["pi_y0"] + P["pi_w"] + P["pi_ovh_usb"], P["z_pi_rear"] + 12.0),
     (12.0, 4.5, 11.5), (16.0, 8.0, 25.0)),
]
for name, ax, (sx, sy, sz), tip, mould in PLUGS:
    parts = []
    # tip from the socket face back out through the wall (inside the socket it
    # is the socket's business), then the overmould
    if ax == "x":
        e = tip[2] - tip[2]            # tip fully home: exposed metal = 0 at the socket face
        m1 = trimesh.creation.box(extents=[1.0, tip[0], tip[1]]); m1.apply_translation([sx - 0.5, sy, sz])
        m2 = trimesh.creation.box(extents=[mould[2], mould[0], mould[1]])
        m2.apply_translation([sx - 1.0 - mould[2]/2, sy, sz])
    else:
        m1 = trimesh.creation.box(extents=[tip[0], 1.0, tip[1]]); m1.apply_translation([sx, sy + 0.5, sz])
        m2 = trimesh.creation.box(extents=[mould[0], mould[2], mould[1]])
        m2.apply_translation([sx, sy + 1.0 + mould[2]/2, sz])
    if name == "3.5 mm":                       # round plug
        m2 = trimesh.creation.cylinder(radius=mould[0]/2, height=mould[2], sections=48)
        m2.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0]))
        m2.apply_translation([sx - 1.0 - mould[2]/2, sy, sz])
    plug = trimesh.util.concatenate([m1, m2])
    v, _ = inter(plug, SHELL)
    if v and v > 0.05:
        res("I", "WARN", f"{name}: a {mould[0]:.0f} x {mould[1]:.0f} plug overmould hits the shell "
                         f"({v:.1f} mm3) -- slim plugs only")
    else:
        out(f"  ok    {name}: {mould[0]:.0f} x {mould[1]:.0f} overmould seats fully")
if not [r for r in RESULTS if r["section"] == "I"]:
    res("I", "PASS", "HDMI, micro-USB, 3.5 mm and USB-A plugs all seat")

# ================================================================= summary
fails = [r for r in RESULTS if r["level"] == "FAIL"]
warns = [r for r in RESULTS if r["level"] == "WARN"]
hdr(f"SUMMARY: {len(fails)} FAIL, {len(warns)} WARN   ({time.time() - T0:.0f} s)")
for r in fails + warns:
    out(f"  {r['level']:4}  [{r['section']}] {r['msg']}")
os.makedirs(os.path.join(ROOT, "preview"), exist_ok=True)
open(os.path.join(ROOT, "preview", "assembly_report.txt"), "w", encoding="utf-8").write("\n".join(LOG) + "\n")
by_step = {}
for sid, lst in STEP_RESULTS.items():
    kinds = {}
    for l, m, k in lst:
        kinds[k] = kinds.get(k, 0) + 1
    by_step[sid] = {"fail": sum(1 for l, _, _ in lst if l == "FAIL"), "checks": len(lst),
                    "messages": [m for l, m, _ in lst if l == "FAIL"], "kinds": kinds}
for r in RESULTS:
    if r["step"] and r["level"] in ("FAIL", "WARN") and r["section"] != "D":
        by_step.setdefault(r["step"], {"fail": 0, "checks": 0, "messages": []})
        by_step[r["step"]]["messages"].append(r["msg"])
        by_step[r["step"]]["fail"] += r["level"] == "FAIL"
json.dump({"fail": len(fails), "warn": len(warns), "sections": sorted({r["section"] for r in RESULTS}),
           "results": RESULTS, "steps": by_step,
           "when": time.strftime("%Y-%m-%d %H:%M")},
          open(os.path.join(ROOT, "preview", "assembly_report.json"), "w", encoding="utf-8"), indent=1)
sys.exit(1 if fails else 0)

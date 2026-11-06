// ===========================================================================
// GamePi43 + Raspberry Pi 4B printed enclosure
// ETHGlobal Mumbai handheld -- replaces the Waveshare acrylic sandwich case.
//
// Parts (select with -D 'part="..."'):
//   "front_shell"  one-piece front tray: face, walls, all port cutouts,
//                  button holes, screen aperture, heat-set insert bosses
//   "rear_frame"   structural back frame, screws to the shell, carries
//                  magnets, battery access window, vents, speaker opening
//   "panel_world" / "panel_0g" / "panel_arkiv"
//                  swappable magnetic cosmetic rear panels (identical
//                  geometry, inner-face ID engraving differs)
//   "button_caps"  8 round caps + D-pad rocker + 2 rear R/L plungers
//   "fit_check_jig" 2 mm test plate: PRINT THIS FIRST and lay the real
//                  GamePi43 board/acrylic on it to verify hole positions
//                  before committing to the big prints
//   "assembly"     visual check model (not for printing)
//
// COORDINATES: x = device width (0 = left edge, front view),
//              y = device height in OpenSCAD +y up; feature positions are
//              given as distance FROM THE TOP EDGE and converted via fy(),
//              z = depth (0 = front face outer surface, +z rearward).
// All exports re-orient each part into its support-free print orientation.
//
// DIMENSION PROVENANCE -- every parameter is tagged:
//   [OFFICIAL]  from a published vendor drawing (see cad/README.md for URLs)
//   [PHOTO]     measured by homography-calibrated analysis of Waveshare's
//               own assembly-manual photographs; expect +/-1 mm, verify
//               with fit_check_jig before printing large parts
//   [ASSUMED]   not published anywhere we could find; a stated guess that
//               MUST be measured against the real kit
//   [DESIGN]    our free choice, no external constraint
// ===========================================================================

// NOTE: `part` is deliberately NOT assigned here. A top-level assignment in
// the file takes precedence over -D on the command line, so defining it would
// silently make every -D export produce the full assembly instead of the part
// asked for. Supply it as -D 'part="front_shell"'; with no -D the dispatch at
// the bottom falls back to the assembly view, so opening this in the GUI still
// shows something sensible.

$fa = 6;
$fs = 0.4;
EPS = 0.01;

// ---------------------------------------------------------------------------
// 1. DEVICE ENVELOPE  [OFFICIAL: Waveshare GamePi43-size.jpg dimension photo]
// ---------------------------------------------------------------------------
W   = 111.21;   // [OFFICIAL] device width
HGT = 170.7;    // [OFFICIAL] device height (portrait, screen at top)
// kit acrylic stack is 33.65 thick [OFFICIAL]; this printed design closes at
// ~38.0 because the swappable magnet panel + structural frame replace 3 mm
// of rear acrylic. Stated, deliberate.
cr  = 5.0;      // [DESIGN] body corner radius (kit acrylic approx 4)

function fy(y) = HGT - y;   // feature y given from top edge -> scad y

// ---------------------------------------------------------------------------
// 2. WALLS, TOLERANCES, FASTENERS
// ---------------------------------------------------------------------------
t_face   = 2.4;   // [DESIGN] front face thickness (task nominal)
t_wall   = 2.4;   // [DESIGN] perimeter wall thickness
clr_slide = 0.20; // [DESIGN] sliding-fit clearance (panel outline, pins)
clr_press = 0.15; // [DESIGN] press-fit clearance (magnet pockets)

// M2.5 heat-set inserts -- sized for common 4.6 mm-OD short brass inserts
// (Ruthex RX-M2.5 class). [ASSUMED] verify against the inserts you buy.
ins_hole_d  = 4.0;   // [ASSUMED] pilot bore for the insert
ins_depth   = 6.2;   // [ASSUMED] bore depth (insert ~5.7 long)
ins_lead_d  = 5.0;   // [DESIGN] lead-in chamfer top diameter
ins_lead_h  = 1.0;   // [DESIGN] lead-in chamfer height
boss_od     = 9.0;   // [DESIGN] insert boss outer diameter

// ---------------------------------------------------------------------------
// 3. Z STACK (front face outer = 0, +z rearward)
// ---------------------------------------------------------------------------
gap_front    = 6.5;  // [ASSUMED] front-face inner surface to GamePi43 PCB
                     // front face. Sets button/display clearance. Kit uses
                     // ~6 mm standoffs; MEASURE on the real kit.
t_pcb        = 1.6;  // [ASSUMED] standard PCB thickness
h_header     = 8.5;  // [ASSUMED] 2x20 female header stack height (standard)
t_pi_pcb     = 1.6;  // [ASSUMED] Pi 4 PCB thickness
bat_holder_h = 20.0; // [PHOTO]   18650 holder height above GamePi43 rear
                     //           face (18.65 cell + holder floor), +/-1
bat_clear    = 0.5;  // [DESIGN] clearance above battery holders

z_board_f = t_face + gap_front;            //  8.9  GamePi43 PCB front face
z_board_r = z_board_f + t_pcb;             // 10.5  GamePi43 PCB rear face
z_pi_f    = z_board_r + h_header;          // 19.0  Pi PCB front face
z_pi_r    = z_pi_f + t_pi_pcb;             // 20.6  Pi PCB rear face
z_wall_top = z_board_r + bat_holder_h + bat_clear;  // 31.0 frame seat plane
skirt_h   = 2.95;  // [DESIGN] shell alignment skirt above the seat plane;
                   // tops 0.05 under the panel underside -> closed seam
                   // with a fine shadow line, frame fully captured inside
skirt_w   = 1.2;   // [DESIGN] skirt (lip) width, outer half of the wall
t_frame   = 3.0;   // [DESIGN] rear frame plate thickness
t_panel   = 4.0;   // [DESIGN] cosmetic panel thickness (>= magnet 3.05+0.8)
z_frame_f = z_wall_top;            // 31.0
z_frame_r = z_frame_f + t_frame;   // 34.0
z_panel_r = z_frame_r + t_panel;   // 38.0 = overall device thickness

// ---------------------------------------------------------------------------
// 4. DISPLAY  (aperture is a parameter -- see the alternates below)
// ---------------------------------------------------------------------------
// Default = the kit's real 4.3 inch 800x480 panel. [OFFICIAL] window
// 96.30 x 56.15 from the Waveshare dimension drawing.
disp_ap_w  = 96.30 + 0.6;   // aperture = official window + clearance
disp_ap_h  = 56.15 + 0.6;
disp_cx    = W / 2;         // [PHOTO] window is centred on the width
disp_cy    = 42.6;          // [PHOTO] window centre from top edge, +/-1.5
//
// ALTERNATE APERTURES (only if the client later fits a different panel):
//   4.55 inch class, 99.0 x 59.4 active (the render model's rev-4 screen):
//       disp_ap_w = 99.6; disp_ap_h = 60.0;
//       NOTE: at 99.6 wide the aperture corners graze the top corner
//       screw bosses; move disp_cy to >= 43.6 and check the preview.
//   TRUE 5 inch, 108.0 x 64.8 active: DOES NOT FIT this 111.21 body.
//       The aperture would cut through the board mounting columns at
//       x = 6.3 / 104.9 and both side walls. The render model showing a
//       5-inch-look screen was a visual design choice, not hardware.
disp_mod_t = 4.5;  // [ASSUMED] display module thickness incl. FPC + foam;
                   // must be < gap_front. MEASURE.

// ---------------------------------------------------------------------------
// 5. GAMEPI43 BOARD + FRONT CONTROLS  [PHOTO unless noted]
// (homography-calibrated from Waveshare's flat front-acrylic photograph,
//  cross-checked against the assembled-device photos; +/-0.7 mm class)
// ---------------------------------------------------------------------------
// board outline (clearance only, not load-bearing)
board_x0 = 6.15;  board_x1 = 106.1;   // [PHOTO +/-1.5]
board_y0 = 5.5;   board_y1 = 156.1;   // [PHOTO +/-1.5] from top

// six mounting columns (the kit's screw/standoff columns through the board)
col_xy = [ [  6.3,   9.1], [104.9,   9.1],
           [  6.3,  83.3], [104.9,  83.3],
           [  6.3, 159.9], [104.9, 159.9] ];   // [PHOTO +/-0.6]
board_screw_d = 3.2;  // kit board holes take M3; we run M2.5 screws through

// D-pad cross cutout
dpad_c    = [28.9, 111.4];  // [PHOTO]
dpad_span = 24.65;          // [PHOTO] kit acrylic cross span
dpad_arm  = 10.4;           // [PHOTO -derived] arm width
// action buttons: kit cap ~10 dia through 10.4 holes [PHOTO]
btn_hole_d = 11.0;          // [DESIGN] our hole = cap 9.6 + generous slop
hk_c      = [54.0, 116.0];  // [PHOTO] HK (hotkey)
dia_c     = [79.9, 111.4];  // [PHOTO] ABXY diamond centre
dia_r     = 10.4;           // [PHOTO] diamond pitch radius
sel_c     = [44.3, 129.3];  // [PHOTO] SELECT
sta_c     = [63.8, 129.3];  // [PHOTO] START
led_x     = 103.4;          // [PHOTO +/-1] battery LED column
led_ys    = [108.6, 118.2, 127.7, 137.3];
led_d     = 2.6;
aux_hole  = [79.5, 9.5];    // [PHOTO] small hole above screen (kit has it)
aux_d     = 2.6;

// tact switches under the caps  [ASSUMED: 6x6x5 with 3.5 sq plunger]
sw_h        = 5.0;   // switch body+plunger height above PCB. MEASURE.
sw_plunger  = 3.5;   // square plunger side. MEASURE.

// ---------------------------------------------------------------------------
// 6. REAR FEATURES  [PHOTO]
// ---------------------------------------------------------------------------
rl_L = [24.8, 82.0];   // [PHOTO] rear L dome button centre (front-view x)
rl_R = [84.7, 82.0];   // [PHOTO] rear R dome button centre
rl_hole_kit = 9.6;     // [PHOTO] kit rear-panel hole dia
dome_top_z  = 30.6;    // [ASSUMED] top of the metal dome plunger. MEASURE.

spk_c   = [53.0, 148.0];  // [PHOTO +/-3] speaker cone centre
spk_dia = 36.0;           // [PHOTO +/-2] cone outer dia. Waveshare publishes
                          // no speaker spec sheet -- measured from photos.

// battery bay (two single 18650 holders side by side, cells across width)
// [OFFICIAL] kit constraint: cell length < 67 mm, no protection plate.
// [ASSUMED]  cell 18.65 dia x 65.2 (standard unprotected 18650)
bat_x0 = 15.0;  bat_x1 = 87.0;   // [PHOTO +/-2] bay incl. contact clips
bat_y0 = 90.0;  bat_y1 = 136.0;  // [PHOTO +/-2] from top

// ---------------------------------------------------------------------------
// 7. RASPBERRY PI 4B PLACEMENT + PORTS
// Pi outline/holes/port geometry [OFFICIAL: rpi 4 b mechanical drawing].
// Pi position inside the device [PHOTO +/-2]: the Pi plugs face-down into
// the GamePi43 GPIO header; GPIO edge toward device bottom, USB/ETH edge
// toward the device LEFT side (front view), ports overhanging the board.
// ---------------------------------------------------------------------------
pi_w = 85.0;  pi_h = 56.0;        // [OFFICIAL]
pi_left_x     = 2.5;   // [PHOTO +/-1.5] Pi USB-edge x in device coords
pi_gpio_edge_y = 80.0; // [PHOTO +/-2]   Pi GPIO-side edge from device top
// Pi 4 connector centres, distance from the Pi GPIO edge [OFFICIAL]:
//   ETH 10.25 / USB3 29.0 / USB2 47.0 (i.e. drawing 45.75/27/9 from the
//   far edge of the 56 board). Front view: measured UP from pi_gpio_edge_y.
eth_off  = 10.25;  usb3_off = 29.0;  usb2_off = 47.0;
eth_w    = 16.2;   eth_hz   = 13.5;  // [OFFICIAL z] width [ASSUMED 16 typ]
usb_w    = 13.3;   usb_hz   = 16.0;  // [OFFICIAL z] width [ASSUMED 13.1 typ]
// left-wall window: one opening over ETH+USB3+USB2 with optional bars.
lw_margin = 3.0;              // [DESIGN] position-error margin each side
lw_y0 = pi_gpio_edge_y - usb2_off - usb_w/2 - lw_margin;   // 23.35
lw_y1 = pi_gpio_edge_y - eth_off  + eth_w/2 + lw_margin;   // 80.85
lw_z0 = z_pi_f - usb_hz - 0.5;   //  2.5  (USB stacks reach the front)
lw_z1 = z_pi_f + 1.0;            // 20.0
lw_bars = true;   // [DESIGN] 2 printed bars between the port windows; they
                  // need Pi position within ~1 mm -- if the fit-check shows
                  // drift, set false and print that wall face with supports
                  // or accept the long top bridge.
bar_w = 2.4;
// bars sit at the centre of the physical gap between connector BODIES
bar_y_a = pi_gpio_edge_y
        - ((usb2_off - usb_w/2) + (usb3_off + usb_w/2))/2;   // 42.0
bar_y_b = pi_gpio_edge_y
        - ((usb3_off - usb_w/2) + (eth_off + eth_w/2))/2;    // 59.65

// ---------------------------------------------------------------------------
// 8. GAMEPI43 EDGE CONNECTORS (top / bottom / right walls)  [PHOTO +/-1.5]
// all mounted on the GamePi43 rear face -> z band just behind z_board_r
// ---------------------------------------------------------------------------
chg_x  = 27.1;   // charge micro-USB centre        (top edge, from left)
aud_x  = 37.2;   // 3.5 mm earphone jack centre    (top edge)
pwr_x  = 96.3;   // power slide switch centre      (top edge)
key_xs = [32.6, 40.8, 90.4, 98.5];  // backlight-/+, sound-/+ (bottom edge)
sd_y0 = 39.0; sd_y1 = 53.0;   // GamePi43's own SD slot, right wall, from top
tf_y0 = 28.0; tf_y1 = 46.0;   // [ASSUMED +/-4] Pi TF-adapter slot, right wall

// ---------------------------------------------------------------------------
// 9. REAR FRAME / PANEL FEATURES
// ---------------------------------------------------------------------------
frame_inset  = skirt_w + 0.25;         // frame outline inset from body
frame_scr_xy = [ [16.0,  6.2], [60.0,  6.2],
                 [ 6.2,120.0], [105.0,120.0],
                 [18.0,164.5], [65.0,164.5] ];  // [DESIGN] frame screws
// magnets: six 6 x 3 N52 discs per panel (task requirement) + six mates in
// the frame. Attracting pair across the z=34 interface.
mag_d = 6.0;  mag_t = 3.0;
mag_xy = [ [14.5, 15.0], [96.7, 15.0],
           [14.5, 86.0], [96.7, 86.0],
           [14.5,158.0], [96.7,158.0] ];        // [DESIGN]
pin_xy = [ [10.0, 45.0], [101.0, 45.0],
           [10.0,152.0], [101.0,152.0] ];       // [DESIGN] panel align pins
pin_d = 4.0;  pin_len = 2.6;

grille_hole_d = 2.4;   // [DESIGN] panel speaker grille
grille_rings  = [[0,1],[4.2,6],[8.4,12],[12.6,18]];  // [radius, holes]

vent_x0 = 22; vent_x1 = 86;   // [DESIGN] frame vent field over the Pi
vent_y0 = 30; vent_y1 = 75.5;
vent_w  = 4;  vent_pitch = 8;

// ---------------------------------------------------------------------------
// 10. BUTTON CAPS  (all [ASSUMED] against the kit switches -- tune & reprint)
// ---------------------------------------------------------------------------
cap_head_d   = 9.6;
cap_flange_d = 12.6;
cap_flange_t = 1.2;
cap_socket   = sw_plunger + clr_slide;        // square socket for the plunger
cap_socket_z = 2.0;
// cap body height: from switch shoulder (z_board_f - sw_h) out to 1.8 proud
cap_body_h   = (z_board_f - sw_h) + 1.8;      // 5.7 total incl. flange
dp_plate_t   = 3.0;
dp_flange_d  = 28.0;
dp_nub_r     = 9.0;    // [ASSUMED] radius of the 4 D-pad switch plungers
plg_head_d   = 9.2;    // R/L plunger head (through 9.8 panel hole)
plg_head_h   = t_panel + 1.0;
plg_flange_d = 12.0;
plg_stem_d   = 6.0;
plg_stem_h   = (z_frame_r - 1.4) - dome_top_z;  // flange seat to dome top

// ===========================================================================
// helpers
// ===========================================================================
module rrect(w, h, r) {
    hull() for (p = [[r, r], [w - r, r], [r, h - r], [w - r, h - r]])
        translate(p) circle(r);
}
module body2d(inset = 0)
    translate([inset, inset])
        rrect(W - 2*inset, HGT - 2*inset, max(cr - inset, 0.6));

module at(p) translate([p[0], fy(p[1]), 0]) children();

// gable profile: rectangle w x h with a 45 deg roof -> prints supportless
module gable2d(w, h) polygon([[-w/2,0],[w/2,0],[w/2,h],[0,h+w/2],[-w/2,h]]);

// wall cutouts (gable roof toward +z). len covers wall + overshoot.
module cut_xwall(x0, yc, z0, w, h)          // window in a wall along x=const
    translate([x0, fy(yc), z0]) rotate([90,0,90])
        linear_extrude(t_wall + 2) gable2d(w, h);
module cut_ywall(xc, y0, z0, w, h)          // window in a wall along y=const
    translate([xc, y0 + t_wall + 1, z0]) rotate([90,0,0])
        linear_extrude(t_wall + 2) gable2d(w, h);

module insert_bore(ztop) {                  // bore + lead-in chamfer, tip up
    translate([0,0,ztop - ins_depth]) cylinder(d = ins_hole_d, h = ins_depth + EPS);
    translate([0,0,ztop - ins_lead_h])
        cylinder(d1 = ins_hole_d, d2 = ins_lead_d, h = ins_lead_h + EPS);
}
module dpad2d(span, arm) {
    square([span, arm], center = true);
    square([arm, span], center = true);
}

// ===========================================================================
// PART: front shell
// ===========================================================================
module front_shell() {
    union() {
        difference() {
            union() {
                linear_extrude(z_wall_top) body2d(0);
                // alignment skirt (outer lip the rear frame drops into)
                translate([0,0,z_wall_top]) linear_extrude(skirt_h)
                    difference() { body2d(0); body2d(skirt_w); }
            }
            // main cavity
            translate([0,0,t_face]) linear_extrude(z_wall_top) body2d(t_wall);

            // ---- front face ----
            translate([disp_cx, fy(disp_cy), -1]) linear_extrude(t_face + 2)
                square([disp_ap_w, disp_ap_h], center = true);
            at(dpad_c) translate([0,0,-1]) linear_extrude(t_face + 2)
                dpad2d(dpad_span + 0.75, dpad_arm + 1.0);
            for (c = [hk_c, sel_c, sta_c]) at(c)
                translate([0,0,-1]) cylinder(d = btn_hole_d, h = t_face + 2);
            for (a = [0, 90, 180, 270]) at(dia_c)
                rotate([0,0,a]) translate([dia_r, 0, -1])
                    cylinder(d = btn_hole_d, h = t_face + 2);
            for (y = led_ys) at([led_x, y])
                translate([0,0,-1]) cylinder(d = led_d, h = t_face + 2);
            at(aux_hole) translate([0,0,-1]) cylinder(d = aux_d, h = t_face + 2);

            // ---- left wall: Pi 4 ETH + USB2 + USB3 window ----
            // with bars: three per-cluster gable windows (each roof stays
            // below the frame seat, fully supportless). without bars: one
            // big window -- needs supports or a long bridge, see README.
            if (lw_bars) {
                for (seg = [ [lw_y0,               bar_y_a - bar_w/2],
                             [bar_y_a + bar_w/2,   bar_y_b - bar_w/2],
                             [bar_y_b + bar_w/2,   lw_y1] ])
                    cut_xwall(-1, (seg[0] + seg[1])/2, lw_z0,
                              seg[1] - seg[0], lw_z1 - lw_z0);
            } else {
                cut_xwall(-1, (lw_y0 + lw_y1)/2, lw_z0, lw_y1 - lw_y0,
                          lw_z1 - lw_z0);
            }

            // ---- right wall: GamePi43 SD slot + Pi TF-adapter slot ----
            cut_xwall(W - t_wall - 1, (sd_y0 + sd_y1)/2, z_board_r - 1.2,
                      sd_y1 - sd_y0, 5.2);
            cut_xwall(W - t_wall - 1, (tf_y0 + tf_y1)/2, z_pi_f - 0.5,
                      tf_y1 - tf_y0, 6.0);

            // ---- top wall: charge micro-USB + earphone jack (merged),
            //      power slide switch ----
            cut_ywall((chg_x + aud_x)/2, fy(0) - t_wall,
                      z_board_r - 1.7, (aud_x - chg_x) + 10.3, 9.8);
            cut_ywall(pwr_x, fy(0) - t_wall, z_board_r - 1.0, 12.0, 6.5);

            // ---- bottom wall: backlight / volume key windows (merged
            //      into two pair-windows) ----
            cut_ywall((key_xs[0]+key_xs[1])/2, 0,
                      z_board_r - 0.5, key_xs[1]-key_xs[0] + 8.0, 6.0);
            cut_ywall((key_xs[2]+key_xs[3])/2, 0,
                      z_board_r - 0.5, key_xs[3]-key_xs[2] + 8.0, 6.0);
        }
        // ---- board mounting bosses (M2.5 heat-set inserts) ----
        for (c = col_xy) at(c) difference() {
            translate([0,0,t_face - EPS])
                cylinder(d = boss_od, h = gap_front + EPS);
            insert_bore(z_board_f);
        }
        // ---- frame screw bosses (M2.5 heat-set inserts, full height) ----
        for (c = frame_scr_xy) at(c) difference() {
            translate([0,0,t_face - EPS])
                cylinder(d = boss_od, h = z_wall_top - t_face + EPS);
            insert_bore(z_wall_top);
        }
    }
}

// ===========================================================================
// PART: rear structural frame
// ===========================================================================
module rear_frame() {
    difference() {
        translate([0,0,z_frame_f]) linear_extrude(t_frame) body2d(frame_inset);

        // battery access window
        translate([bat_x0, fy(bat_y1), z_frame_f - 1])
            cube([bat_x1 - bat_x0, bat_y1 - bat_y0, t_frame + 2]);

        // vent slots over the Pi
        for (x = [vent_x0 : vent_pitch : vent_x1 - vent_w])
            translate([x, fy(vent_y1), z_frame_f - 1])
                cube([vent_w, vent_y1 - vent_y0, t_frame + 2]);

        // R/L dome pass-through + plunger flange spot-face
        for (c = [rl_L, rl_R]) at(c) {
            translate([0,0,z_frame_f - 1]) cylinder(d = 10.4, h = t_frame + 2);
            translate([0,0,z_frame_r - 1.4])
                cylinder(d = plg_flange_d + 1.4, h = 1.5);
        }

        // speaker opening (panel carries the fine grille)
        at(spk_c) translate([0,0,z_frame_f - 1])
            cylinder(d = 30, h = t_frame + 2);

        // frame screws: through hole + counterbore for M2.5 pan head
        for (c = frame_scr_xy) at(c) {
            translate([0,0,z_frame_f - 1]) cylinder(d = 2.9, h = t_frame + 2);
            translate([0,0,z_frame_r - 1.6]) cylinder(d = 5.8, h = 1.7);
        }

        // magnet pockets (through; magnet glued flush with outer face)
        for (c = mag_xy) at(c)
            translate([0,0,z_frame_f - 1])
                cylinder(d = mag_d + clr_press, h = t_frame + 2);

        // panel locating pin holes
        for (c = pin_xy) at(c)
            translate([0,0,z_frame_f - 1])
                cylinder(d = pin_d + 2*clr_slide, h = t_frame + 2);
    }
    // speaker opening cross ribs (keep panel supported)
    at(spk_c) intersection() {
        translate([0,0,z_frame_f]) cylinder(d = 30 + 2, h = t_frame);
        union() {
            translate([-1.5, -16, z_frame_f]) cube([3, 32, t_frame]);
            translate([-16, -1.5, z_frame_f]) cube([32, 3, t_frame]);
        }
    }
}

// ===========================================================================
// PART: cosmetic rear panel (label engraved on the INNER face only)
// ===========================================================================
module rear_panel(label) {
    difference() {
        translate([0,0,z_frame_r]) linear_extrude(t_panel) body2d(clr_slide);

        // R/L plunger holes
        for (c = [rl_L, rl_R]) at(c)
            translate([0,0,z_frame_r - 1]) cylinder(d = 9.8, h = t_panel + 2);

        // speaker grille -- real acoustic holes over the cone
        for (ring = grille_rings)
            for (i = [0 : ring[1] - 1]) at(spk_c)
                rotate([0,0,i * 360 / ring[1]])
                    translate([ring[0], 0, z_frame_r - 1])
                        cylinder(d = grille_hole_d, h = t_panel + 2);

        // magnet pockets from the INNER face; 0.95 cover skin outside
        for (c = mag_xy) at(c)
            translate([0,0,z_frame_r - EPS])
                cylinder(d = mag_d + clr_press, h = mag_t + 0.05 + EPS);

        // inner-face ID engraving
        // reads correctly with the panel lying outer-face-down (as printed)
        translate([W/2, fy(62), z_frame_r - EPS]) linear_extrude(0.6 + EPS)
            text(label, size = 8, halign = "center", valign = "center",
                 font = "Liberation Sans:style=Bold");
    }
    // locating pins into the frame
    for (c = pin_xy) at(c)
        translate([0,0,z_frame_r - pin_len]) cylinder(d = pin_d, h = pin_len + EPS);
}

// ===========================================================================
// PART: button caps (printed flat on the plate, supportless)
// ===========================================================================
module round_cap() {
    difference() {
        union() {
            cylinder(d = cap_flange_d, h = cap_flange_t);
            cylinder(d = cap_head_d, h = cap_body_h - 0.6);
            translate([0,0,cap_body_h - 0.6 - EPS])
                cylinder(d1 = cap_head_d, d2 = cap_head_d - 1.6, h = 0.6 + EPS);
        }
        translate([-cap_socket/2, -cap_socket/2, -EPS])
            cube([cap_socket, cap_socket, cap_socket_z]);
    }
}
module dpad_cap() {   // modeled TOP-DOWN: flat cross face on the bed
    // cross plate
    linear_extrude(dp_plate_t) dpad2d(dpad_span - 0.45, dpad_arm - 0.5);
    // retaining flange
    translate([0,0,dp_plate_t - EPS]) cylinder(d = dp_flange_d, h = cap_flange_t);
    // centre pivot + 4 actuator nubs (all point up = toward the switches)
    translate([0,0,dp_plate_t + cap_flange_t - 0.3]) {
        cylinder(d = 5, h = 0.8 + 0.3);
        for (a = [0, 90, 180, 270]) rotate([0,0,a])
            translate([dp_nub_r, 0, 0]) cylinder(d = 4, h = 0.5 + 0.3);
    }
}
module rl_plunger() {  // head down on the bed
    cylinder(d = plg_head_d, h = plg_head_h);
    translate([0,0,plg_head_h - EPS])
        cylinder(d1 = plg_head_d, d2 = plg_flange_d, h = 1.4);
    translate([0,0,plg_head_h + 1.4 - 2*EPS]) {
        cylinder(d = plg_flange_d, h = cap_flange_t);
        translate([0,0,cap_flange_t - EPS])
            cylinder(d = plg_stem_d, h = plg_stem_h + EPS);
    }
}
module button_caps() {
    for (i = [0:7]) translate([12 + (i%4)*16, 12 + floor(i/4)*16, 0]) round_cap();
    translate([90, 22, 0]) dpad_cap();
    for (i = [0:1]) translate([12 + i*18, 46, 0]) rl_plunger();
}

// ===========================================================================
// PART: fit-check jig -- print first, lay the real board/acrylic on it
// ===========================================================================
module fit_check_jig() {
    difference() {
        linear_extrude(2.0) body2d(0);
        // screen window
        translate([disp_cx, fy(disp_cy), -1]) linear_extrude(4)
            square([disp_ap_w, disp_ap_h], center = true);
        // controls
        at(dpad_c) translate([0,0,-1]) linear_extrude(4)
            dpad2d(dpad_span + 0.75, dpad_arm + 1.0);
        for (c = [hk_c, sel_c, sta_c]) at(c)
            translate([0,0,-1]) cylinder(d = btn_hole_d, h = 4);
        for (a = [0,90,180,270]) at(dia_c) rotate([0,0,a])
            translate([dia_r,0,-1]) cylinder(d = btn_hole_d, h = 4);
        // the six mounting columns -- MUST line up with the board holes
        for (c = col_xy) at(c) translate([0,0,-1]) cylinder(d = 2.9, h = 4);
        // R/L + speaker centre marks
        for (c = [rl_L, rl_R, spk_c]) at(c)
            translate([0,0,-1]) cylinder(d = 3.0, h = 4);
        // engraved references: board outline, Pi outline, battery bay
        for (r = [ [board_x0, board_y0, board_x1, board_y1],
                   [pi_left_x, pi_gpio_edge_y - pi_h,
                    pi_left_x + pi_w, pi_gpio_edge_y],
                   [bat_x0, bat_y0, bat_x1, bat_y1] ])
            translate([0,0,1.4]) linear_extrude(1)
                difference() {
                    translate([r[0], fy(r[3])]) square([r[2]-r[0], r[3]-r[1]]);
                    translate([r[0]+0.5, fy(r[3])+0.5])
                        square([r[2]-r[0]-1, r[3]-r[1]-1]);
                }
        // notches on the left edge at the port-window extents
        for (y = [lw_y0, lw_y1])
            translate([-1, fy(y) - 1.5, -1]) cube([4, 3, 4]);
    }
}

// ===========================================================================
// assembly preview (visual verification only)
// ===========================================================================
module mock_hardware() {
    color("green", 0.5) {   // GamePi43 board
        translate([board_x0, fy(board_y1), z_board_f])
            cube([board_x1-board_x0, board_y1-board_y0, t_pcb]);
    }
    color("red", 0.5) {     // Pi 4 + port stacks
        translate([pi_left_x, fy(pi_gpio_edge_y), z_pi_f])
            cube([pi_w, pi_h, t_pi_pcb]);
        for (p = [[eth_off, eth_w, eth_hz], [usb3_off, usb_w, usb_hz],
                  [usb2_off, usb_w, usb_hz]])
            translate([pi_left_x - 2.5, fy(pi_gpio_edge_y - p[0]) - p[1]/2,
                       z_pi_f - p[2]])
                cube([20, p[1], p[2]]);
    }
    color("orange", 0.5)    // 18650s
        for (yc = [102.5, 123.5]) translate([18.5, fy(yc), z_board_r + 10.6])
            rotate([0,90,0]) cylinder(d = 18.65, h = 65.2);
    color("purple", 0.5) at(spk_c)   // speaker
        translate([0,0,z_board_r]) cylinder(d = spk_dia, h = 5);
}
module assembly() {
    front_shell();
    color("steelblue", 0.85) rear_frame();
    color("white", 0.6) rear_panel("WORLD");
    mock_hardware();
}

// ===========================================================================
// export dispatch (each part re-oriented for support-free printing)
// ===========================================================================
if (is_undef(part))         assembly();                       // GUI default
else if (part == "front_shell")  front_shell();               // face on bed
else if (part == "rear_frame")
    translate([0,0,-z_frame_f]) rear_frame();                 // inner face down
else if (part == "panel_world")
    translate([0, HGT, z_panel_r]) rotate([180,0,0]) rear_panel("WORLD");
else if (part == "panel_0g")
    translate([0, HGT, z_panel_r]) rotate([180,0,0]) rear_panel("0G");
else if (part == "panel_arkiv")
    translate([0, HGT, z_panel_r]) rotate([180,0,0]) rear_panel("ARKIV");
else if (part == "button_caps") button_caps();
else if (part == "fit_check_jig") fit_check_jig();

// Assembled-position exports for the web viewer. These deliberately skip the
// print re-orientation above, so every component lands in its true in-device
// coordinates and the viewer can stack them without knowing any transforms.
// Not for slicing -- use the print-oriented exports for that.
else if (part == "asm_front_shell") front_shell();
else if (part == "asm_rear_frame")  rear_frame();
else if (part == "asm_panel_world") rear_panel("WORLD");
else if (part == "asm_panel_0g")    rear_panel("0G");
else if (part == "asm_panel_arkiv") rear_panel("ARKIV");
else if (part == "asm_hardware")    mock_hardware();

else assembly();

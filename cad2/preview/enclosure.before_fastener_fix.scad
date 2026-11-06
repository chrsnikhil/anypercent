// ===========================================================================
// ARCA HANDHELD -- printed enclosure for a Raspberry Pi 3B+ / Waveshare 5in
// DSI landscape retro console.
//
// THIS SUPERSEDES cad/enclosure.scad (that file models a Waveshare GamePi43
// kit around a Pi 4B with a 4.3in screen and 18650 cells -- a DIFFERENT
// DEVICE). Nothing is shared but the house style.
//
// PARTS -- select with a wrapper file, NOT with -D. See wrappers/.
//   "front_shell"       face, walls, display pocket, all button towers,
//                       speaker posts + grille, Pi posts, port cutouts,
//                       M3 heat-set insert bosses
//   "bay_tray"          power-bank bay floor + side walls + retention
//                       detents; also clamps the display down
//   "rear_frame"        structural back plate: Pi clamp towers, fan mount,
//                       vents, 6 body magnet pockets, screw counterbores
//   "panel_world" / "panel_arkiv" / "panel_arc"
//                       swappable magnetic cosmetic rear panels
//                       (0G was DROPPED -- there is deliberately no 0G panel)
//   "buttons"           D-pad rocker, 4 face caps, 2 pills, 2 shoulders
//   "sd_hatch"          removable bottom-wall plug for microSD access
//   "fit_check_jig"     2.5 mm plate carrying EVERY hole / boss / pin
//                       position. PRINT THIS FIRST (about 40 min) and lay
//                       the real parts on it before the 10 h shell print.
//   "assembly"          visual check model, not for printing
//
// WHY A WRAPPER AND NOT -D:
//   A top-level `part = "..."` assignment in this file would silently beat
//   any -D on the command line, and PowerShell strips the quotes out of
//   -Dpart="x" before openscad.exe ever sees them, leaving a bare
//   identifier. Both failures are SILENT. So `part` is NOT assigned here;
//   each wrapper sets it and then includes this file. With no wrapper the
//   dispatch at the bottom falls back to the assembly view, so opening this
//   file in the GUI still shows something sensible.
//
// COORDINATES
//   x = device width,  0 = left edge   (front view)
//   y = device height, 0 = bottom edge, +y up
//   z = depth,         0 = front face OUTER surface, +z rearward
//   Exports re-orient each part into its support-free print orientation.
//
// DIMENSION PROVENANCE -- every parameter is tagged:
//   [OFFICIAL] taken from a published vendor drawing. The exact file and
//              the extraction method are recorded in cad2/README.md.
//   [ASSUMED]  not published anywhere we could find. A stated, conservative
//              guess. MUST be checked against the real part.
//   [MEASURE]  the client owns the part and will caliper it. Default is a
//              deliberately generous placeholder.
//   [DESIGN]   our free choice, no external constraint.
// ===========================================================================

$fa = 4;
$fs = 0.5;
EPS  = 0.01;
E2   = 0.02;

// ---------------------------------------------------------------------------
// 1. DEVICE ENVELOPE                                              [DESIGN]
// ---------------------------------------------------------------------------
// Width is set from the bottom up: display glass 121.00 + two grips wide
// enough for a 30 mm D-pad rocker and a 36 mm face-button diamond.
// Height is set by the 76.00 glass + a 42 mm bottom band. The band has to
// clear BOTH the 30 mm-tall FIT0502 speaker behind the grille AND the
// START/SELECT switch towers, which stand in front of the face and must not
// land on the speaker box. 6 mm top margin.
W   = 202.0;    // device width
H   = 124.0;    // device height
cr  = 7.0;      // body corner radius

// ---------------------------------------------------------------------------
// 2. WALLS, TOLERANCES, FASTENERS                                 [DESIGN]
// ---------------------------------------------------------------------------
t_face   = 2.4;   // front face thickness (task nominal)
t_wall   = 2.4;   // perimeter wall thickness
t_rib    = 2.0;   // internal rib / bay wall thickness

clr_slide = 0.20; // sliding fit  (panel rims, power bank, button stems)
clr_press = 0.15; // press fit    (magnets, tactile switch pockets)

// M3 heat-set inserts, 4.4 mm OD x 5 mm long                     [verified]
ins_od       = 4.4;
ins_len      = 5.0;
ins_pilot_d  = 4.1;   // 0.3 under the knurl OD so the knurl bites
ins_pilot_h  = 6.4;   // bore depth: insert 5.0 + 1.4 swarf relief
ins_lead_d   = 5.1;   // lead-in chamfer top diameter
ins_lead_h   = 0.9;
boss_od      = 7.0;   // insert boss outer diameter
// boss_h is DERIVED further down: the bosses are the standoffs between the
// face and the rear frame, so they have to reach z_frame_f. A fixed value
// here would leave the frame screws biting into thin air.

// M3 x 8 button head, hex socket                                 [verified]
scr_d        = 3.3;   // clearance hole
scr_head_d   = 6.2;   // button head clearance
scr_head_h   = 2.1;   // counterbore depth

// N52 disc magnets 6 dia x 3 thick, 60 off                       [verified]
mag_d        = 6.0;
mag_t        = 3.0;
mag_pocket_d = mag_d + 2*clr_press;   // 6.30
mag_pocket_h = mag_t + clr_press;     // 3.15

// ---------------------------------------------------------------------------
// 3. WAVESHARE 5 inch DSI LCD
//    [OFFICIAL] every number below is read out of Waveshare's own 2D
//    drawing 5inch-dsi-lcd.dxf (wiki "5inch DSI LCD" -> 2D Drawing).
//    See cad2/README.md for how each was extracted.
// ---------------------------------------------------------------------------
disp_glass_w = 121.00;  // [OFFICIAL] touch glass outline
disp_glass_h = 76.00;
disp_pcb_w   = 120.70;  // [OFFICIAL] PCB outline (matches the spec sheet)
disp_pcb_h   = 75.80;
disp_act_w   = 108.00;  // [OFFICIAL] active pixel area
disp_act_h   =  64.80;
// The active area is centred on the glass in X but sits 1.89 mm off-centre
// in Y. Measured from the drawing: glass mid y 38.00, VA mid y 39.89.
disp_act_dy  = 1.89;    // [OFFICIAL] active centre above glass centre
// 8 x M2.50 mounting holes. Outer four (case mounting, what we use) on a
// 113.00 x 68.00 grid, 4.00 in from each glass edge. Inner four are a
// 58 x 49 Raspberry Pi pattern, which this design deliberately does NOT use
// (bolting the Pi to the display would make the stack 16 mm deeper).
disp_hole_dx = 113.00;  // [OFFICIAL]
disp_hole_dy =  68.00;  // [OFFICIAL]
disp_hole_d  =   2.50;  // [OFFICIAL]
// NOTE: those holes are drilled in the PCB and the touch glass covers them.
// Waveshare's front view is a plain 121.00 x 76.00 outline with no holes, so
// NOTHING can engage them from the front. The display is located by the
// pocket rib and clamped on its PCB rear by four printed spacer pucks.
// Side view of the same drawing: front glass surface -> PCB rear face 9.01,
// rear components/DSI connector a further 5.67. Total module depth 14.68.
// NOTE: Waveshare's web spec says "5 mm thick"; that is the panel sandwich
// only and does NOT include the PCB or its rear connectors. Believe 14.7.
disp_t_stack    = 9.0;  // [OFFICIAL] glass front -> PCB rear
disp_rear_proj  = 5.7;  // [OFFICIAL] rear components behind the PCB

// Display position. The aperture is the design datum; the board hangs off it.
ap_cx   = W/2;                  // 101.00  [DESIGN] horizontally centred
ap_cy   = 82.00;                // [DESIGN] leaves a 42.1 bottom band
ap_clr  = 0.6;                  // [DESIGN] aperture oversize on the active area
disp_cx = ap_cx;                // glass centre x
disp_cy = ap_cy - disp_act_dy;  // 72.11  glass centre y

// ---------------------------------------------------------------------------
// 4. RASPBERRY PI 3 MODEL B+
//    [OFFICIAL] Raspberry Pi mechanical drawing RP-008337-DS-2. Board-local
//    coordinates: bx runs 0..85 from the microSD edge, by runs 0..56 from
//    the GPIO edge. Every value was recovered from the drawing's own vector
//    geometry and cross-checked against its printed callouts (85, 56, 58,
//    49, 3.5, R3.0, 10.6, 32, 53.5, 28, 47, 29, 10.25).
// ---------------------------------------------------------------------------
pi_w = 85.0; pi_h = 56.0; pi_cr = 3.0; pi_pcb_t = 1.6;
pi_hole_inset = 3.5;  pi_hole_dx = 58.0;  pi_hole_dy = 49.0;  pi_hole_d = 2.75;

pi_pwr_bx  = 10.62; pi_pwr_w  =  7.5; pi_pwr_z  = 3.0; // micro-USB power
pi_hdmi_bx = 32.03; pi_hdmi_w = 15.0; pi_hdmi_z = 6.5; // full-size HDMI
pi_av_bx   = 53.53; pi_av_w   =  7.0; pi_av_z   = 6.0; // 3.5 mm AV jack
pi_usbA_by0 =  2.45; pi_usbA_by1 = 15.59;  // USB-A stack nearest GPIO edge
pi_usbB_by0 = 20.44; pi_usbB_by1 = 33.61;  // second USB-A stack
pi_eth_by0  = 38.04; pi_eth_by1  = 53.54;  // RJ45 (deliberately NOT opened)
pi_usb_z    = 16.0;  // [OFFICIAL] USB-A stack height above the PCB
pi_eth_z    = 13.5;  // [OFFICIAL]
pi_gpio_z   =  8.5;  // [OFFICIAL] 40-pin header height
pi_gpio_bx0 =  7.11; pi_gpio_bx1 = 57.94; pi_gpio_by1 = 6.04;
pi_soc_bx = 27.0; pi_soc_by = 24.5; pi_soc_sz = 14.0; // BCM2837B0, 14 x 14
pi_dsi_by0 = 16.81; pi_dsi_by1 = 39.22; pi_dsi_bx1 = 5.47; // DSI FPC socket

// The microSD socket is on the UNDERSIDE and is not drawn on the official
// top-view drawing, so its position along the edge is the one Pi number we
// could not source.
pi_sd_by   = 28.0;  // [MEASURE] microSD socket centre, board y. Caliper it.
pi_sd_w    = 13.0;  // [ASSUMED] socket width
pi_sd_card = 1.2;   // [ASSUMED] card + socket lip height below the PCB

// Pi placement. The board is rotated 90 deg: its 85 mm axis runs up the
// device. by = 56 (the micro-USB / HDMI / AV edge) faces the LEFT wall,
// bx = 85 (the USB-A / Ethernet edge) faces the TOP wall.
pi_x0 = 3.0;        // [DESIGN] device x of the by = 56 edge
pi_y0 = 35.6;       // [DESIGN] device y of the bx = 0 edge
                    // set so the USB-A stack face lands flush in the top wall
function pdx(by) = pi_x0 + (pi_h - by);   // board y -> device x
function pdy(bx) = pi_y0 + bx;            // board x -> device y

// ---------------------------------------------------------------------------
// 5. Z STACK  (front face outer = 0, +z rearward)
// ---------------------------------------------------------------------------
z_face_in   = t_face;                        //  2.40 face inner surface
z_disp_pcb  = z_face_in + disp_t_stack;      // 11.40 display PCB rear face
z_disp_rear = z_disp_pcb + disp_rear_proj;   // 17.10 rearmost display feature

// The Pi sits BESIDE most of the display, not behind it: it overlaps the
// glass only over x 40.5..59. Over that strip the display's rear carries
// only ~2 mm of small parts, so the Pi can come forward of z_disp_rear.
z_pi_front  = 14.40;   // [DESIGN] Pi PCB front face
z_pi_rear   = z_pi_front + pi_pcb_t;         // 16.00
z_pi_max    = z_pi_rear + pi_usb_z;          // 32.00 tallest Pi feature

z_tray_f    = 17.60;   // [DESIGN] bay tray front face. 0.5 clear of the
                       // display's rearmost feature at 17.10.
t_tray      = 2.00;
z_bay_f     = z_tray_f + t_tray;             // 19.30 bank rests here

// The rear frame plane is DERIVED, not fixed: it sits on the bay walls so
// the frame presses the bay tray home, and it must also clear the Pi's USB
// stacks. Measure a thicker power bank and the whole device grows correctly.

// ---------------------------------------------------------------------------
// 6. POWER BANK BAY -- Noise MagSafe 10000 mAh
//    Noise publishes ONLY the weight (192 g). No dimension is available from
//    the vendor, so all three are [MEASURE]. Defaults are the middle of the
//    10000 mAh Qi2/MagSafe class. The bay is a removable drawer, not a
//    sealed cavity: the client also uses this bank as a phone charger.
//    The bank is Type-C output only, so a short C-to-microUSB lead lives in
//    the bay and feeds the Pi's micro-USB power inlet.
// ---------------------------------------------------------------------------
bank_w = 106.0;   // [MEASURE] long axis, across the device
bank_h =  69.0;   // [MEASURE] short axis, into the device from the top edge
bank_t =  14.5;   // [MEASURE] thickness
bank_port_x = 53.0; // [MEASURE] Type-C port centre, from the bank's left edge
                    //           (looking at the bay opening). Sets the notch.

bay_w  = bank_w + 2*clr_slide;
bay_d  = bank_h + clr_slide;
bay_t  = bank_t + 2*clr_slide;
bay_x0 = 67.5;                    // [DESIGN]
bay_x1 = bay_x0 + bay_w;          // 173.90
bay_y1 = H - t_wall;              // 113.60 open at the top edge
bay_y0 = bay_y1 - bay_d;          //  44.40
bay_z1 = z_bay_f + bay_t;         //  34.50 -- the rear frame closes the bay
bay_det_h = 0.9;                  // [DESIGN] retention detent proud height

// --- rest of the z stack, derived -----------------------------------------
// The rear frame plane sits ON the bay walls, so the frame presses the tray
// home, and it must also clear the Pi's 16 mm USB stacks. Measuring a thicker
// power bank therefore grows the whole device correctly.
z_frame_f   = max(bay_z1, z_pi_max + 2.5);   // 34.50 at the defaults
t_frame     =  4.20;   // thick enough for a full-depth magnet pocket
z_frame_r   = z_frame_f + t_frame;           // 38.70
t_panel     =  4.00;
z_panel_r   = z_frame_r + t_panel;           // 42.70 = device thickness

wall_top    = z_frame_r;   // shell walls run to here; the frame is captured
                           // inside them and only the panel shows at the rear

boss_h      = z_frame_f - z_face_in;         // 32.10 face inner -> frame

// ---------------------------------------------------------------------------
// 7. DFRobot FIT0502 enclosed stereo speaker                      [verified]
//    70 x 30 x 16, screw pitch 24 x 63, JST PH2.0, 42 cm lead.
//    Already enclosed, so no printed chamber -- just posts and a grille.
// ---------------------------------------------------------------------------
spk_w = 70.0; spk_h = 30.0; spk_t = 16.0;
spk_pitch_x = 63.0; spk_pitch_y = 24.0;
spk_screw_pilot = 2.8;  // [DESIGN] M3 self-tap into a printed post
spk_cx = W/2; spk_cy = 17.4;   // [DESIGN]
// spk_post_h is DERIVED, down in section 9 -- it depends on z_sw_seat, and
// OpenSCAD evaluates top-level assignments in file order, so it cannot be
// written here.

// ---------------------------------------------------------------------------
// 8. PARTS WITH NO PUBLISHED DIMENSIONS
// ---------------------------------------------------------------------------
// Raspberry Pi Pico                                              [OFFICIAL]
pico_w = 51.0; pico_h = 21.0; pico_t = 1.0;
pico_x = 140.0; pico_y = 16.0;   // [DESIGN] lower-right pocket
// USB-wired to a Pi USB-A port: the lead runs up the right-hand wall channel
// to the top-edge USB window. See cable_route() in the assembly view.

// PAM8403 amplifier. Variants run 21 x 18 x 3.4 (mini, no pot) up to
// 30 x 30. Robu's 19-rupee part is almost certainly the mini.
pam_w = 22.0;   // [MEASURE] generous default for the mini variant
pam_h = 22.0;   // [MEASURE]
pam_t =  8.0;   // [MEASURE] includes the tallest electrolytic
pam_x = 176.8; pam_y = 92.0;   // [DESIGN] right-hand strip (23.7 mm wide)
// If the client's board turns out to be a 30 x 30 variant it will NOT fit
// the 23.3 mm right-hand strip -- move it to the bottom-left trough and
// re-run. See README.

// Waveshare Colorful Heat Sink Set (2 x aluminium + 1 x copper, adhesive).
// "Low profile" is the only published figure.
heatsink_h = 6.0;   // [MEASURE] tallest fin height above the chip
heatsink_pad = 16.0;// [DESIGN]  keep-out square around each chip

// ---------------------------------------------------------------------------
// 9. CONTROLS
// ---------------------------------------------------------------------------
// Tactile switches: 6 x 6 footprint, ten actuator heights in the kit from
// 4.3 to 13 mm. THE ACTUATOR HEIGHT IS A PARAMETER ON PURPOSE -- the client
// picks after a test print. Everything downstream (pocket floor, tower
// height, cap stem length) is derived from it; nothing is hard-coded.
sw_size      = 6.0;
sw_pocket    = sw_size + 2*clr_press;   // 6.30 press fit
sw_body_h    = 3.5;    // [ASSUMED] body height above the seating plane
sw_actuator_h = 5.0;   // [MEASURE] TOTAL height, seating plane -> plunger tip
                       // Kit options: 4.3 5 6 7 8 9 10 12 13
sw_plunger_d = 3.5;    // [ASSUMED]
sw_lead_clr  = 4.2;    // [DESIGN] plunger clearance bore
t_tower      = 1.6;    // [DESIGN] wall of a printed switch tower

cap_t        = 1.6;    // [DESIGN] cap flange thickness
cap_proud    = 0.6;    // [DESIGN] how far a cap stands off the face
cap_gap      = 0.15;   // [DESIGN] lost motion between plunger and cap

// Derived: with the cap front at -cap_proud and the cap rear (flange back)
// at t_face + cap_t, the plunger tip must land at t_face + cap_t + cap_gap.
z_cap_back   = t_face + cap_t;                       // 4.00 cap flange rear
z_flange_cb  = z_cap_back + 0.4;                     // 4.40 top of the flange
                                                     //      counterbore
z_sw_tip     = z_cap_back + cap_gap;                 // 4.15 plunger tip
z_sw_seat    = z_sw_tip + sw_actuator_h;             // 9.15 at the default
z_sw_floor   = z_sw_seat - sw_body_h;                // 5.65 pocket shoulder

// DERIVED: the START/SELECT switch towers stand in front of the speaker, so
// the speaker has to sit behind them. Tracking sw_actuator_h means raising
// the switch height can never silently make the speaker foul a tower. The
// cost is a short duct between the grille and the speaker face -- 7.25 mm at
// the default actuator height, 15.35 mm at the 13 mm one.
spk_post_h   = z_sw_seat - z_face_in + 0.5;          // 7.25 at the default

// D-pad: four 6 x 6 tactiles under ONE printed rocker.
// The rocker and its flange are CROSSES, not squares. That leaves the four
// diagonal corners of the tower block solid, which is what carries the
// counterbore ceiling on a face-down print, and it keeps the face hole
// narrower than the switch towers so the towers are not floating islands.
dpad_cx = 20.5; dpad_cy = ap_cy;   // [DESIGN]
dpad_r  = 9.0;                     // [DESIGN] switch centre radius
dpad_size  = 26.0; dpad_arm   =  9.0;  // [DESIGN] front cross, across / arm
dpad_flange = 30.0; dpad_arm_f = 11.0; // [DESIGN] rear flange cross
dpad_block  = dpad_flange + 2*clr_slide + 2*t_tower;  // 33.6 tower block
// No central pivot: the rocker see-saws on the un-pressed plungers, which is
// how a cheap membrane D-pad works and removes an unprintable post.

// NO ANALOG THUMBSTICK WAS PURCHASED. Nothing below is built; these are the
// documented hooks for adding one later. Set stick_enable = true and a
// 24 mm clearance bore + a 4-hole 20 x 20 module pad appear in the right
// grip, and the face-button diamond shifts up by stick_shift.
stick_enable = false;   // [DESIGN]
stick_cx = 181.5; stick_cy = 54.0;
stick_bore_d = 24.0; stick_pad_pitch = 20.0; stick_shift = 0.0;

// Face buttons: four caps in a diamond.
// The diamond has to live between the display pocket rib (outer edge 163.3)
// and the right wall inner face (199.6). That is 36.3 mm, and a tower is
// (cap_d + 3 + 2*t_tower) across, so face_r + tower_r <= 18.15.
// Adjacent flange counterbores are face_r*sqrt(2) apart and (cap_d + 3 +
// 2*clr_slide) across. At cap_d = 10 and face_r = 9.5 that leaves a 0.035 mm
// wall between them, which CGAL cannot resolve and which exported as a
// non-manifold solid. cap_d = 9.0 opens the gap to 1.03 mm.
// A DIAMOND: one button at each of 0/90/180/270 degrees, the SNES/Xbox
// layout. Putting them at 45/135/225/315 gives a 2 x 2 square instead, which
// is what the first render showed and is not what was asked for.
face_cx = 181.5; face_cy = ap_cy + stick_shift;  // [DESIGN]
face_r  =  9.5;                                  // [DESIGN] diamond radius
face_cap_d =  9.0;                               // [DESIGN]

// START / SELECT pills, centred below the screen.
pill_w = 14.0; pill_h = 6.0; pill_dx = 9.0; pill_cy = 33.0;  // [DESIGN]
// The pill towers reach y 39.3, just under the display pocket rib at 40.3.
// They overlap the speaker in plan, so the speaker is stood off far enough
// to pass behind them -- see spk_post_h, which is derived.

// Shoulder buttons on the top edge.
sh_lx = 14.0; sh_rx = 185.0;   // [DESIGN] centres
sh_w  = 15.0; sh_z0 = 4.0; sh_zh = 8.0;   // paddle: 15 wide, z 4..12

// Speaker grille, two fields flanking the pills.
// Two fields, over the speaker's two halves, clear of its four corner posts
// (x 69.5 / 132.5) and below the pill towers (which start at y 26.7).
gr_y0 = 4.0; gr_y1 = 24.0;      // [DESIGN]
gr_lx0 = 74.0; gr_lx1 = 97.0;
gr_rx0 = 105.0; gr_rx1 = 128.0;
gr_slot_w = 1.6; gr_slot_pitch = 3.4;   // [DESIGN] printable at 0.4 nozzle

// ---------------------------------------------------------------------------
// 10. FAN -- not fitted now, provision only
// ---------------------------------------------------------------------------
fan_enable   = true;    // build the bosses and the grille
fan_size     = 30.0;    // [ASSUMED] 25 or 30 mm both work; pitch follows
fan_pitch    = 24.0;    // [ASSUMED] 30 mm fan = 24, 25 mm fan = 20
fan_thk      = 10.0;    // [ASSUMED]
fan_pilot    = 2.8;     // [DESIGN] M3 self-tap into a printed boss
fan_cx = pdx(pi_soc_by);   // 34.50 -- directly over the SoC
fan_cy = pdy(pi_soc_bx);   // 54.60

// ---------------------------------------------------------------------------
// 11. FASTENER AND MAGNET POSITIONS
// ---------------------------------------------------------------------------
// 9 M3 insert bosses. Every position dodges the Pi (x 3..59, y 27.6..112.6),
// the bay (x 65.1..176.3, y 42..113.6), the speaker (x 66..136, y 2.4..32.4),
// the display (x 40.5..161.5, y 34.1..110.1) and the shoulder paddles.
// Insets of 4.4 put a 7 mm boss 1.5 mm into the 2.4 mm wall, so every boss
// is welded to a wall instead of standing as a lone 32 mm tower.
boss_pos = [
  [  4.4,   4.4], [ 45.0,   4.4], [150.0,   4.4], [197.6,   4.4],
  [  4.4,  20.0], [197.6,  45.0], [197.6,  85.0],
  [ 62.0, 119.6], [197.6, 119.6]
];
// The bay tray is not screwed down. It drops over these three bosses, which
// locate it, and the rear frame lands on the bay walls and presses it home.
tray_ears = [[62.0, 119.6], [197.6, 45.0], [197.6, 85.0]];

// Display clamp points: four spots on the display PCB that are (a) under the
// bay tray floor and (b) on the clear perimeter of the board, away from the
// rear DSI connector whichever way round the board is fitted.
disp_clamp = [[75, 59], [152, 59], [75, 111], [152, 111]];
disp_spacer_d = 12.0;
disp_spacer_h = z_tray_f - z_disp_pcb;   // 6.20

// 6 magnet stations, body and panel share the list.
mag_pos = [[20,10],[101,10],[182,10],[20,114],[101,114],[182,114]];

// microSD hatch in the bottom wall, under the Pi's card edge.
sd_x  = pdx(pi_sd_by);   // 31.00 at the default pi_sd_by
sd_hatch_w = 30.0; sd_hatch_h = 11.0; sd_hatch_t = t_wall;

// ---------------------------------------------------------------------------
// 12. LOGOS
// ---------------------------------------------------------------------------
logo_dir = "logos/";
logo_h   = 0.8;     // [DESIGN] raised emblem, proud of the panel face
logo_w   = 92.0;    // [DESIGN] emblem width on the panel
// Sources, all genuine vector geometry (no traced approximations):
//   world.svg  world.org official orb+wordmark, flattened for import
//   arkiv.svg  Arkiv official lockup
//   arc.svg    arc.network official site logo (Circle's Arc L1)

// ===========================================================================
//                              PRIMITIVES
// ===========================================================================

module rrect(w, h, r) {
  offset(r=r) offset(delta=-r) square([w, h]);
}

// Outer body outline, in device xy.
module body2d() { rrect(W, H, cr); }
module inner2d(inset = t_wall) {
  translate([inset, inset]) rrect(W - 2*inset, H - 2*inset, max(0.8, cr - inset));
}

// Rounded slot / stadium, centred on the origin, w x h overall.
// It has to work in BOTH aspect ratios: the START/SELECT caps are wide and
// short, every grille slot and wall vent is narrow and tall.
module pill2d(w, h) {
  if (w >= h)
    hull() { translate([-(w-h)/2, 0]) circle(d=h); translate([(w-h)/2, 0]) circle(d=h); }
  else
    hull() { translate([0, -(h-w)/2]) circle(d=w); translate([0, (h-w)/2]) circle(d=w); }
}

// M3 heat-set boss standing on the face inner surface.
module insert_boss(h = boss_h) {
  difference() {
    cylinder(d = boss_od, h = h);
    translate([0,0,h - ins_pilot_h]) cylinder(d = ins_pilot_d, h = ins_pilot_h + EPS);
    translate([0,0,h - ins_lead_h])  cylinder(d1 = ins_pilot_d, d2 = ins_lead_d, h = ins_lead_h + EPS);
  }
}

// Countersunk-free M3 clearance + button-head counterbore, drilled +z.
module screw_thru(plate_t) {
  translate([0,0,-EPS]) cylinder(d = scr_d, h = plate_t + E2);
  translate([0,0,plate_t - scr_head_h]) cylinder(d = scr_head_d, h = scr_head_h + EPS);
}

module magnet_pocket() {
  translate([0,0,-EPS]) cylinder(d = mag_pocket_d, h = mag_pocket_h + EPS);
}

// A cross outline, used for the D-pad rocker, its flange and its face hole.
module cross2d(across, arm) {
  offset(r=1.2) offset(delta=-1.2)
    union() { square([across, arm], center=true); square([arm, across], center=true); }
}

// The switch pocket, the plunger bore above it and the wire reliefs. Cut out
// of whichever tower block encloses it. Everything derives from
// sw_actuator_h; nothing in the stack is hard-coded.
module switch_void() {
  translate([0,0,z_flange_cb - EPS])
    cylinder(d = sw_lead_clr, h = z_sw_floor - z_flange_cb + E2);
  translate([0,0,z_sw_floor])
    linear_extrude(z_sw_seat - z_sw_floor + EPS) square([sw_pocket, sw_pocket], center=true);
  for (s = [-1,1]) translate([s*(sw_pocket/2 + 1.0), 0, z_sw_floor])
    linear_extrude(z_sw_seat - z_sw_floor + EPS) square([2.4, 4.2], center=true);
}

// Round tower for one face button. The bore from the face inner surface up to
// z_flange_cb is the counterbore the cap's flange is trapped in, so the tower
// wraps the cap instead of fighting it.
module tower_round(cap_d) {
  difference() {
    translate([0,0,z_face_in])
      cylinder(d = cap_d + 3.0 + 2*t_tower, h = z_sw_seat - z_face_in);
    translate([0,0,z_face_in - EPS])
      cylinder(d = cap_d + 3.0 + 2*clr_slide, h = z_flange_cb - z_face_in + EPS);
    switch_void();
  }
}

// Stadium tower for one START/SELECT pill.
module tower_pill() {
  difference() {
    translate([0,0,z_face_in]) linear_extrude(z_sw_seat - z_face_in)
      pill2d(pill_w + 3.0 + 2*t_tower, pill_h + 3.0 + 2*t_tower);
    translate([0,0,z_face_in - EPS]) linear_extrude(z_flange_cb - z_face_in + EPS)
      pill2d(pill_w + 3.0 + 2*clr_slide, pill_h + 3.0 + 2*clr_slide);
    switch_void();
  }
}

// One block carrying all four D-pad switches. The flange counterbore is a
// CROSS, so the block's four diagonal corners stay solid all the way up and
// support the counterbore ceiling on a face-down print.
module tower_dpad() {
  difference() {
    translate([0,0,z_face_in]) linear_extrude(z_sw_seat - z_face_in)
      offset(r=2.5) offset(delta=-2.5) square([dpad_block, dpad_block], center=true);
    translate([0,0,z_face_in - EPS]) linear_extrude(z_flange_cb - z_face_in + EPS)
      cross2d(dpad_flange + 2*clr_slide, dpad_arm_f + 2*clr_slide);
    for (i = [0:3])
      translate([dpad_r*cos(i*90), dpad_r*sin(i*90), 0]) switch_void();
  }
}

// Round cap hole through the face + the open interior behind it.
module cap_hole(d) {
  translate([0,0,-EPS]) cylinder(d = d + 2*clr_slide, h = t_face + E2);
}

// t defaults to the face, but the fit-check jig is 2.5 thick and has to cut
// all the way through, or the slots come out as a 0.08 mm membrane.
module grille_field(x0, x1, y0, y1, t = t_face) {
  n = floor((x1 - x0) / gr_slot_pitch);
  for (i = [0 : n-1])
    translate([x0 + gr_slot_pitch/2 + i*gr_slot_pitch, (y0+y1)/2, -EPS])
      linear_extrude(t + E2) pill2d(gr_slot_w, y1 - y0);
}

module vent_field(x0, x1, y0, y1, t, pitch = 5.0, slot = 2.2) {
  n = floor((x1 - x0) / pitch);
  for (i = [0 : n-1])
    translate([x0 + pitch/2 + i*pitch, (y0+y1)/2, -EPS])
      linear_extrude(t + E2) pill2d(slot, y1 - y0);
}

// ===========================================================================
//                         COMPONENT PROXIES (assembly view)
// ===========================================================================

module proxy_display() {
  color("#20242c") translate([disp_cx - disp_glass_w/2, disp_cy - disp_glass_h/2, z_face_in])
    cube([disp_glass_w, disp_glass_h, disp_t_stack]);
  color("#2f6f3f") translate([disp_cx - disp_pcb_w/2, disp_cy - disp_pcb_h/2, z_disp_pcb])
    cube([disp_pcb_w, disp_pcb_h, 2.0]);
  color("#111") translate([disp_cx - 8, disp_cy + 6, z_disp_pcb])
    cube([32, 22, disp_rear_proj]);
  color("#0a1a2a") translate([ap_cx - disp_act_w/2, ap_cy - disp_act_h/2, -0.2])
    cube([disp_act_w, disp_act_h, 0.4]);
}

// The Pi proxy is split into its bare board and everything mounted on it, so
// the assembled-view exports can colour the PCB green and the connectors metal
// (asm_pi_board / asm_pi_parts). proxy_pi() is still the whole thing.
module pi_place() {
  // board-local: bx along +x, by along +y, rotated into place
  translate([pi_x0, pi_y0, z_pi_front]) rotate([0,0,90]) translate([0,-pi_h,0]) children();
}

module proxy_pi() { pi_place() { proxy_pi_board(); proxy_pi_parts(); } }

module proxy_pi_board() {
  color("#2f6f3f") linear_extrude(pi_pcb_t)
    translate([0,0]) offset(r=pi_cr) offset(delta=-pi_cr) square([pi_w, pi_h]);
}

module proxy_pi_parts() {
  // USB-A stacks and Ethernet
  color("#9aa0a6") {
    translate([pi_w - 15.7, pi_usbA_by0, pi_pcb_t]) cube([17.3, pi_usbA_by1-pi_usbA_by0, pi_usb_z]);
    translate([pi_w - 15.7, pi_usbB_by0, pi_pcb_t]) cube([17.3, pi_usbB_by1-pi_usbB_by0, pi_usb_z]);
    translate([pi_w - 19.3, pi_eth_by0,  pi_pcb_t]) cube([21.3, pi_eth_by1-pi_eth_by0,  pi_eth_z]);
  }
  color("#222") translate([pi_gpio_bx0, 1.04, pi_pcb_t]) cube([pi_gpio_bx1-pi_gpio_bx0, 5.0, pi_gpio_z]);
  color("#b05a2a") translate([pi_soc_bx - pi_soc_sz/2, pi_soc_by - pi_soc_sz/2, pi_pcb_t])
    cube([pi_soc_sz, pi_soc_sz, heatsink_h]);
  color("#444") {
    translate([pi_pwr_bx  - pi_pwr_w/2,  pi_h - 0.8, pi_pcb_t]) cube([pi_pwr_w,  6.0, pi_pwr_z]);
    translate([pi_hdmi_bx - pi_hdmi_w/2, pi_h - 1.4, pi_pcb_t]) cube([pi_hdmi_w, 12.0, pi_hdmi_z]);
    translate([pi_av_bx   - pi_av_w/2,   pi_h - 0.6, pi_pcb_t]) cube([pi_av_w,   12.5, pi_av_z]);
    translate([0.35, pi_dsi_by0, pi_pcb_t]) cube([pi_dsi_bx1, pi_dsi_by1-pi_dsi_by0, 5.5]);
  }
  color("#888") translate([-1.0, pi_sd_by - pi_sd_w/2, -pi_sd_card]) cube([12.0, pi_sd_w, pi_sd_card]);
}

module proxy_bank() {
  color("#d8dade") translate([bay_x0 + clr_slide, bay_y0, z_bay_f]) cube([bank_w, bank_h, bank_t]);
}

module proxy_speaker() {
  color("#1b1b1b") translate([spk_cx - spk_w/2, spk_cy - spk_h/2, z_face_in + spk_post_h])
    cube([spk_w, spk_h, spk_t]);
}

module proxy_pico() {
  color("#1f5f2f") translate([pico_x, pico_y, z_pi_front]) cube([pico_w, pico_h, pico_t + 3.0]);
}

module proxy_pam() {
  color("#1e4faa") translate([pam_x, pam_y, z_pi_front]) cube([pam_w, pam_h, pam_t]);
}

module proxy_fan() {
  if (fan_enable)
    color("#333") translate([fan_cx - fan_size/2, fan_cy - fan_size/2, z_frame_f - fan_thk])
      cube([fan_size, fan_size, fan_thk]);
}

// ===========================================================================
//                                CUTOUTS
// ===========================================================================

// Every wall port, cut through the shell walls.
module port_cuts() {
  // --- LEFT WALL: Pi micro-USB power, HDMI, 3.5 mm AV jack -----------------
  translate([-1, pdy(pi_pwr_bx),  z_pi_rear + pi_pwr_z/2])
    rotate([0,90,0]) linear_extrude(t_wall + 3) pill2d(pi_pwr_z + 3.0, pi_pwr_w + 3.0);
  translate([-1, pdy(pi_hdmi_bx), z_pi_rear + pi_hdmi_z/2])
    rotate([0,90,0]) linear_extrude(t_wall + 3) pill2d(pi_hdmi_z + 1.6, pi_hdmi_w + 1.6);
  translate([-1, pdy(pi_av_bx),   z_pi_rear + pi_av_z/2])
    rotate([0,90,0]) linear_extrude(t_wall + 3) circle(d = max(pi_av_w, pi_av_z) + 2.6);

  // --- TOP WALL: one USB-A stack opened, the other two left blind ----------
  // Stack A (board by 2.45..15.59) is the external port. Stack B feeds the
  // Pico internally; Ethernet is deliberately sealed.
  translate([pdx(pi_usbA_by1), H - t_wall - 1, z_pi_rear + pi_usb_z/2])
    rotate([-90,0,0]) linear_extrude(t_wall + 3)
      translate([(pi_usbA_by1 - pi_usbA_by0)/2, 0]) square([pi_usbA_by1-pi_usbA_by0 + 1.6, pi_usb_z + 1.6], center=true);

  // --- TOP WALL: power bank bay mouth --------------------------------------
  // cut deep enough in y to pass through the reinforcement collar as well
  translate([bay_x0 - t_rib, H - t_wall - 9, z_bay_f - 0.6])
    cube([bay_w + 2*t_rib, t_wall + 11, bay_t + 1.2]);

  // --- TOP WALL: shoulder paddle slideways ---------------------------------
  for (sx = [sh_lx, sh_rx])
    translate([sx - (sh_w + 2*clr_slide)/2, H - t_wall - 6, sh_z0])
      cube([sh_w + 2*clr_slide, t_wall + 8, sh_zh]);

  // --- BOTTOM WALL: microSD hatch aperture + flange rebate -----------------
  translate([sd_x - sd_hatch_w/2, -1, z_pi_front - 2.0])
    cube([sd_hatch_w, t_wall + 3, sd_hatch_h]);
  translate([sd_x - sd_hatch_w/2 - 1.5, -EPS, z_pi_front - 3.5])
    cube([sd_hatch_w + 3.0, 1.0 + EPS, sd_hatch_h + 3.0]);
}

// Side and bottom breathing vents in the shell walls.
// Keep-outs, all checked: the AV jack cutout reaches y 93.9 on the left wall;
// insert bosses sit at y 81.5..88.5 and 116.1..123.1 on the right wall and at
// x 146.5..153.5 and 194.1..201.1 on the bottom wall. A vent through a boss
// would put a hole straight into a screw column.
module wall_vents() {
  for (i = [0:5]) {
    // left wall, above the AV jack, below the top wall
    translate([-1, 98 + i*3.6, z_pi_rear + 3]) rotate([0,90,0])
      linear_extrude(t_wall + 3) pill2d(2.0, 12.0);
    // right wall, between the bosses at y 85 and y 119.6
    translate([W - t_wall - 1, 92 + i*3.6, z_pi_rear + 3]) rotate([0,90,0])
      linear_extrude(t_wall + 3) pill2d(2.0, 12.0);
  }
  // bottom wall, between the bosses at x 150 and x 197.6
  for (i = [0:6])
    translate([158 + i*4.2, -1, z_pi_front + 2]) rotate([-90,0,0])
      linear_extrude(t_wall + 3) pill2d(2.2, 9.0);
}

// ===========================================================================
//                              FRONT SHELL
// ===========================================================================

module front_shell() {
  difference() {
    union() {
      // face + perimeter wall
      linear_extrude(t_face) body2d();
      linear_extrude(wall_top) difference() { body2d(); inner2d(t_wall); }

      // display pocket walls: a 1.6 mm rib around the glass that locates it
      translate([0,0,z_face_in]) linear_extrude(z_disp_pcb - z_face_in)
        difference() {
          translate([disp_cx - disp_glass_w/2 - 1.6 - clr_slide, disp_cy - disp_glass_h/2 - 1.6 - clr_slide])
            square([disp_glass_w + 3.2 + 2*clr_slide, disp_glass_h + 3.2 + 2*clr_slide]);
          translate([disp_cx - disp_glass_w/2 - clr_slide, disp_cy - disp_glass_h/2 - clr_slide])
            square([disp_glass_w + 2*clr_slide, disp_glass_h + 2*clr_slide]);
        }
      // M3 insert bosses
      for (p = boss_pos) translate([p[0], p[1], z_face_in - EPS]) insert_boss();

      // Pi posts. ONLY the two mounting holes at device x 6.5 get a post:
      // the other two are at x 55.5, inside the screen aperture, where a post
      // would stand in the middle of the display.
      for (sy = [-1,1]) {
        px = pdx(pi_hole_inset + pi_hole_dy);
        py = pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0));
        translate([px, py, z_face_in - EPS]) {
          cylinder(d = 6.4, h = z_pi_front - z_face_in + EPS);
          translate([0,0,z_pi_front - z_face_in])
            cylinder(d = pi_hole_d - 0.4, h = pi_pcb_t + 1.0);
        }
      }
      // Support rib carrying the Pi's other side, in the 1.7 mm gap between
      // the D-pad tower block (ends x 37.3) and the display pocket rib
      // (starts x 38.7). Starts at y 50 so it clears the microSD socket on
      // the board's underside (device y 35.6..47.6).
      translate([35.0, 50.0, z_face_in - EPS])
        cube([3.0, pi_y0 + pi_w - 2.0 - 50.0, z_pi_front - z_face_in + EPS]);

      // speaker posts
      for (sx = [-1,1], sy = [-1,1])
        translate([spk_cx + sx*spk_pitch_x/2, spk_cy + sy*spk_pitch_y/2, z_face_in - EPS])
          difference() {
            cylinder(d = 6.0, h = spk_post_h + EPS);
            translate([0,0,-EPS]) cylinder(d = spk_screw_pilot, h = spk_post_h + 4);
          }

      // button switch towers
      translate([dpad_cx, dpad_cy, 0]) tower_dpad();
      for (i = [0:3])
        translate([face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90), 0])
          tower_round(face_cap_d);
      for (s = [-1,1]) translate([ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy, 0]) tower_pill();

      // shoulder switch blocks: solid columns with a rear-loading pocket
      for (sx = [sh_lx, sh_rx]) translate([sx, H - t_wall, 0]) shoulder_block();

      // Bay mouth reinforcement: a FULL HEIGHT rib on the inside of the top
      // wall, not a shelf. A shelf starting partway up would have had its
      // whole underside as an unsupported overhang on a face-down print.
      // It MUST also be wider than the mouth cut in port_cuts: matching the
      // cut exactly put two coincident faces at x 65.5 / 175.9 and exported
      // non-manifold. 3 mm is all the depth there is -- the display glass
      // reaches y 118.11 and the wall inner face is at 121.6.
      translate([bay_x0 - t_rib - 3, H - t_wall - 3, z_face_in])
        cube([bay_w + 2*t_rib + 6, 3, wall_top - z_face_in]);

      // PANEL REGISTER RIDGE on the wall top. It lives here and not on the
      // panel because the shell prints face-down, so this points up and is
      // free, whereas a lip on the panel's inner face would lift the whole
      // plate off the bed and leave its entire underside unsupported.
      // Inner half of the wall; the outer 1.2 mm stays a flat land for the
      // panel to sit on.
      translate([0,0,wall_top - EPS]) linear_extrude(1.2 + EPS)
        difference() { inner2d(1.2); inner2d(t_wall); }

    }

    // ---- subtractions ----
    // screen aperture
    translate([ap_cx - (disp_act_w + 2*ap_clr)/2, ap_cy - (disp_act_h + 2*ap_clr)/2, -EPS])
      cube([disp_act_w + 2*ap_clr, disp_act_h + 2*ap_clr, t_face + E2]);

    // button holes through the face
    for (i = [0:3]) translate([face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90), 0])
      cap_hole(face_cap_d);
    translate([dpad_cx, dpad_cy, -EPS]) linear_extrude(t_face + E2)
      cross2d(dpad_size + 2*clr_slide, dpad_arm + 2*clr_slide);
    for (s = [-1,1]) translate([ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy, -EPS])
      linear_extrude(t_face + E2) pill2d(pill_w + 2*clr_slide, pill_h + 2*clr_slide);

    // optional analog stick provision
    if (stick_enable) {
      translate([stick_cx, stick_cy, -EPS]) cylinder(d = stick_bore_d + 2*clr_slide, h = t_face + E2);
      for (sx = [-1,1], sy = [-1,1])
        translate([stick_cx + sx*stick_pad_pitch/2, stick_cy + sy*stick_pad_pitch/2, -EPS])
          cylinder(d = 2.6, h = 12);
    }

    // speaker grille
    grille_field(gr_lx0, gr_lx1, gr_y0, gr_y1);
    grille_field(gr_rx0, gr_rx1, gr_y0, gr_y1);

    port_cuts();
    wall_vents();

  }
}

// Local origin: x at the paddle centre, y = 0 at the top wall INNER face
// (device y = H - t_wall), z = device z. Everything here derives from
// sw_actuator_h, exactly like the face buttons.
//
//   y -sh_stem   .. +t_wall+1   narrow slideway, the paddle stem rides here
//   y -sh_flange .. -sh_stem    wide counterbore, the paddle flange is trapped
//   y  sh_seat   .. +sw_body_h  switch pocket, plunger facing +y
sh_stem   = 4.0;
sh_flange = 7.0;
sh_seat   = -sh_flange - sw_actuator_h;      // switch seating plane
sh_depth  = -sh_seat + 1.5;                  // block depth into the device
sh_zc     = sh_z0 + sh_zh/2;                 // plunger axis height

module shoulder_block() {
  difference() {
    // Width leaves a full t_tower wall outside the flange counterbore; at
    // sh_w + 7 it was 0.3 mm. Height is clipped just short of the Pi PCB
    // plane on purpose.
    translate([-(sh_w + 6 + 2*clr_slide + 2*t_tower)/2, -sh_depth, z_face_in - EPS])
      cube([sh_w + 6 + 2*clr_slide + 2*t_tower, sh_depth, z_pi_front - 0.6 - z_face_in]);

    // The narrow slideway is cut at SHELL level, in port_cuts, so it goes
    // through the top wall as well. Cutting it here too would put coincident
    // faces on both sides of the same prism.
    // wide flange counterbore -- its outer end is the return stop
    translate([-(sh_w + 6 + 2*clr_slide)/2, -sh_flange, sh_z0 - 0.2])
      cube([sh_w + 6 + 2*clr_slide, sh_flange - sh_stem, sh_zh + 0.4]);
    // plunger clearance, flange rear face back to the switch body
    translate([0, sh_seat + sw_body_h, sh_zc]) rotate([-90,0,0])
      cylinder(d = sw_lead_clr, h = -sh_seat - sw_body_h - sh_flange + EPS);
    // switch pocket, loaded from the rear (+z)
    translate([-sw_pocket/2, sh_seat, sh_zc - sw_pocket/2])
      cube([sw_pocket, sw_body_h, sw_pocket + 12]);
    // wire relief either side of the pocket
    translate([-sw_pocket/2 - 2.4, sh_seat, sh_zc + 1])
      cube([sw_pocket + 4.8, sw_body_h, 14]);
  }
}

// ===========================================================================
//                               BAY TRAY
// ===========================================================================
// Floor + side walls of the power bank drawer. Also carries four legs that
// reach down onto the display PCB and clamp it into the shell pocket -- the
// bay sits directly behind the screen so there is nowhere else for a display
// retainer to live.

module bay_tray() {
  difference() {
    // Clip the whole tray to the shell interior. Without this the locating
    // ears - discs of diameter boss_od+5 centred on bosses at x 197.6 and
    // y 119.6 - reach 1.6 mm PAST the 202 x 124 outer envelope and foul the
    // side wall, so the drawer cannot seat. Verified by a vertex-overhang
    // check against the envelope. The clip is the guard, not a fudge: any
    // future feature placed near a wall is now trimmed automatically.
    intersection() {
    linear_extrude(200) inner2d(t_wall + clr_slide);
    union() {
      // floor
      translate([bay_x0 - t_rib, bay_y0 - t_rib, z_tray_f])
        cube([bay_w + 2*t_rib, bay_d + t_rib, t_tray]);
      // side + bottom walls of the drawer
      translate([bay_x0 - t_rib, bay_y0 - t_rib, z_tray_f])
        linear_extrude(t_tray + bay_t)
          difference() {
            square([bay_w + 2*t_rib, bay_d + t_rib]);
            translate([t_rib, t_rib]) square([bay_w, bay_d + t_rib]);
          }
      // Locating ears. These are NOT screwed: each is a clearance hole that
      // drops over one of the 32 mm shell bosses, which locates the tray in
      // x and y. The rear frame lands on the bay walls and pushes it home.
      for (p = tray_ears)
        hull() {
          translate([p[0], p[1], z_tray_f]) cylinder(d = boss_od + 5, h = t_tray);
          translate([max(bay_x0 - t_rib, min(bay_x1 + t_rib, p[0])),
                     max(bay_y0 - t_rib, min(bay_y1, p[1])), z_tray_f])
            cylinder(d = 6, h = t_tray);
        }
      // Retention detents: vertical half-cylinders on the drawer walls, so
      // they print in the build direction and need no support.
      for (dx = [bay_x0, bay_x1])
        translate([dx, bay_y1 - 16, z_bay_f + 2])
          cylinder(d = bay_det_h*2, h = bay_t - 4, $fn = 24);
    }
    }   // end intersection: tray clipped to shell interior

    // register dimples that stop the four display spacer pucks wandering
    for (c = disp_clamp)
      translate([c[0], c[1], z_tray_f - EPS])
        cylinder(d = disp_spacer_d + 2*clr_slide, h = 0.6 + EPS);

    // clearance holes that drop over the shell bosses
    for (p = tray_ears)
      translate([p[0], p[1], -EPS]) cylinder(d = boss_od + 2*clr_slide, h = 60);

    // cable pass-through at the bay's inner end for the bank's Type-C lead
    translate([bay_x0 + bank_port_x - 11, bay_y0 - t_rib - EPS, z_bay_f + 1.0])
      cube([22, t_rib + E2, bay_t - 2.0]);
    // finger notch at the mouth so the bank can be pulled out
    translate([bay_x0 + bay_w/2 - 13, bay_y1 - 16, z_tray_f - EPS])
      cube([26, 20, t_tray + E2]);
    // Weight-saving / airflow slots in the floor. Banded y 70..96 on
    // purpose: clear of the drawer's bottom wall root (y 50.4..52.4) and of
    // both rows of spacer register dimples (y 52.8..65.2 and 104.8..117.2).
    for (i = [0:5])
      translate([bay_x0 + 10 + i*16, 83, z_tray_f - EPS])
        linear_extrude(t_tray + E2) pill2d(6.0, 26.0);
  }
}

// ===========================================================================
//                              REAR FRAME
// ===========================================================================

module rear_frame() {
  difference() {
    union() {
      translate([0,0,z_frame_f]) linear_extrude(t_frame) inner2d(t_wall + clr_slide);
      // Pi clamp towers. The pair at x 6.5 land ON the PCB rear face and
      // trap the board against the front posts. The pair at x 55.5 stop
      // 1.4 mm short and act as travel limiters only: at z 16.0 they could
      // clash with the display's rear DSI connector, whose x position is
      // only known from a rear view whose mirroring we cannot confirm.
      for (sx = [-1,1], sy = [-1,1]) {
        px = pdx(pi_hole_inset + (sx>0 ? pi_hole_dy : 0));
        py = pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0));
        z0 = (px < 38.0) ? z_pi_rear : z_pi_rear + 1.4;
        // d2 was 9.0, which put the towers at x 6.5 across x 2.0..11.0 --
        // 0.4 mm into the shell's inner wall face at x 2.4. 7.6 clears it.
        translate([px, py, z0])
          cylinder(d1 = 6.4, d2 = 7.6, h = z_frame_f - z0 + EPS);
      }
      // fan bosses
      if (fan_enable)
        for (sx = [-1,1], sy = [-1,1])
          translate([fan_cx + sx*fan_pitch/2, fan_cy + sy*fan_pitch/2, z_frame_f - fan_thk])
            cylinder(d = 6.4, h = fan_thk + EPS);
      // magnet bosses are not needed: t_frame 4.2 already takes a 3.15 pocket
    }

    // Spigot relief, only in the two towers that actually meet the board
    for (sy = [-1,1]) {
      px = pdx(pi_hole_inset + pi_hole_dy);
      py = pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0));
      translate([px, py, z_pi_rear - EPS]) cylinder(d = pi_hole_d + 1.0, h = 3.0);
    }

    // screw counterbores, drilled from the rear face
    for (p = boss_pos) translate([p[0], p[1], z_frame_f - EPS]) {
      cylinder(d = scr_d, h = t_frame + E2);
      translate([0,0,t_frame - scr_head_h]) cylinder(d = scr_head_d, h = scr_head_h + E2);
    }

    // magnet pockets, open to the REAR (mating) face -> magnet-to-magnet
    for (p = mag_pos) translate([p[0], p[1], z_frame_r - mag_pocket_h])
      cylinder(d = mag_pocket_d, h = mag_pocket_h + EPS);

    // fan pilot holes and the fan grille
    if (fan_enable) {
      for (sx = [-1,1], sy = [-1,1])
        translate([fan_cx + sx*fan_pitch/2, fan_cy + sy*fan_pitch/2, z_frame_f - fan_thk - EPS])
          cylinder(d = fan_pilot, h = fan_thk + t_frame + E2);
      // Concentric ring grille. The rings MUST be broken by spokes, or every
      // ring of material between them is a floating island.
      translate([fan_cx, fan_cy, z_frame_f - EPS]) difference() {
        union() {
          cylinder(r = 3.5, h = t_frame + E2);
          for (r = [4:4:fan_size/2 - 2]) difference() {
            cylinder(r = r + 1.3, h = t_frame + E2);
            cylinder(r = r,       h = t_frame + E2);
          }
        }
        for (a = [0:3]) rotate([0,0,45 + a*90])
          translate([-1.1, 0, -EPS]) cube([2.2, fan_size/2 + 2, t_frame + 1]);
      }
    }

    // exhaust vents over the Pi's USB / Ethernet end and the right strip
    translate([0,0,z_frame_f]) {
      // keep-outs: Pi clamp towers at x 2..11 and 51..60, screw bosses at
      // [196.5,45] and [196.5,85], the bay wall ring, the fan grille
      vent_field(14, 48, 100, 114, t_frame);
      vent_field(180, 195, 54, 76,  t_frame);
      vent_field(14, 48,  18,  28, t_frame);
    }

    // No relief over the bay walls: z_frame_f IS bay_z1, so the frame lands
    // flat on the wall tops and that contact is what holds the tray down.

  }
}

// ===========================================================================
//                            REAR PANELS
// ===========================================================================

module logo_emblem(kind) {
  if (kind == "world")
    resize([logo_w, 0, logo_h], auto=[true,true,false]) linear_extrude(1) import(str(logo_dir, "world.svg"), center=true);
  else if (kind == "arkiv")
    resize([logo_w, 0, logo_h], auto=[true,true,false]) linear_extrude(1) import(str(logo_dir, "arkiv.svg"), center=true);
  else if (kind == "arc")
    resize([logo_w*0.72, 0, logo_h], auto=[true,true,false]) linear_extrude(1) import(str(logo_dir, "arc.svg"), center=true);
}

module panel(kind) {
  difference() {
    union() {
      translate([0,0,z_frame_r]) linear_extrude(t_panel) body2d();

      // raised emblem on the outer face
      translate([W/2, H/2, z_panel_r - EPS]) logo_emblem(kind);
    }
    // Register groove for the shell's wall-top ridge. A groove, not a lip:
    // open to the inner face, it is a void in the first layers with a 1.6 mm
    // bridged ceiling, so the panel still prints flat on its inner face.
    translate([0,0,z_frame_r - EPS]) linear_extrude(1.2 + EPS)
      difference() { inner2d(1.2 - clr_slide); inner2d(t_wall + clr_slide); }
    // magnet pockets from the INNER face, 0.85 mm cover skin stays outside
    for (p = mag_pos) translate([p[0], p[1], z_frame_r - EPS])
      cylinder(d = mag_pocket_d, h = mag_pocket_h + EPS);
    // inner-face identification, so a stack of three panels is sortable
    translate([W/2, 18, z_frame_r - EPS]) linear_extrude(0.6 + EPS)
      mirror([1,0,0])
        text(kind, size = 7, halign = "center", font = "Liberation Sans:style=Bold");
  }
}

// Assembled-view split of ONE panel into two colourable meshes. Both are cut
// out of panel(kind) itself at the panel's outer face plane z_panel_r, so the
// emblem geometry and position stay defined in exactly one place and
// body + logo is precisely the printed one-piece panel. Every subtraction in
// panel() (register groove, magnet pockets, inner label) lives in
// z 38.69..41.85 and the emblem in z 42.69..43.49, so the cut plane touches
// neither. Both cuts are difference()s, not intersection()s: intersecting at a
// face the two solids only TOUCH on would leave CGAL a zero-thickness sheet.
// These are for the viewer only. PRINT the one-piece panel_<kind> targets.
module panel_body(kind) {
  difference() {
    panel(kind);
    translate([-1, -1, z_panel_r]) cube([W + 2, H + 2, logo_h + 1]);
  }
}

module panel_logo(kind) {
  difference() {
    panel(kind);
    translate([-1, -1, z_frame_r - 1]) cube([W + 2, H + 2, t_panel + 1]);
  }
}

// ===========================================================================
//                               BUTTONS
// ===========================================================================

module round_cap(d) {
  difference() {
    union() {
      translate([0,0,-cap_proud]) cylinder(d = d, h = cap_proud + t_face);
      translate([0,0,t_face])     cylinder(d = d + 3.0, h = cap_t);
    }
    // 0.5 x 45 deg break on the front edge so it does not feel sharp
    translate([0,0,-cap_proud - EPS])
      difference() {
        cylinder(d = d + 2, h = 0.5 + E2);
        cylinder(d1 = d - 1.0, d2 = d + 0.01, h = 0.5 + E2);
      }
  }
}

module pill_cap() {
  translate([0,0,-cap_proud]) linear_extrude(cap_proud + t_face) pill2d(pill_w, pill_h);
  translate([0,0,t_face])     linear_extrude(cap_t)              pill2d(pill_w + 3.0, pill_h + 3.0);
}

// Cross front plate through the cross face hole, cross flange behind it.
// The flange arms are wider than the face-hole arms, so the rocker cannot
// fall out forwards, and the plungers bear on the flange at dpad_r.
module dpad_rocker() {
  difference() {
    union() {
      translate([0,0,-cap_proud]) linear_extrude(cap_proud + t_face)
        cross2d(dpad_size, dpad_arm);
      translate([0,0,t_face]) linear_extrude(cap_t)
        cross2d(dpad_flange, dpad_arm_f);
    }
    // shallow dished thumb pads on the four arms, no printed lettering
    for (i = [0:3])
      translate([(dpad_size/2 - 3.2)*cos(i*90), (dpad_size/2 - 3.2)*sin(i*90), -cap_proud - 2.7])
        sphere(d = 7.5);
  }
}

// Printed lying on the bed: stem + flange, both sh_zh tall.
module shoulder_paddle() {
  linear_extrude(sh_zh - 2*clr_slide) {
    // stem: from the flange out through the wall, 1.0 proud of the top edge
    translate([0, (t_wall + 1.0 - sh_stem)/2])
      square([sh_w - 2*clr_slide, sh_stem + t_wall + 1.0], center=true);
    // flange: trapped in the counterbore. Gives the return stop and the face
    // the switch plunger pushes on.
    translate([0, -(sh_stem + (sh_flange - sh_stem - cap_gap)/2)])
      offset(r=1.0) offset(delta=-1.0)
        square([sh_w + 6 - 2*clr_slide, sh_flange - sh_stem - cap_gap], center=true);
  }
}

// A print tray. The caps are flipped so every visible surface is against the
// bed; the z offset is t_face + cap_t so the flange backs land on z = 0.
module buttons() {
  translate([0, 0, t_face + cap_t]) rotate([180,0,0]) {
    for (i = [0:3]) translate([i*20, 0, 0]) round_cap(face_cap_d);
    for (i = [0:1]) translate([i*26, 26, 0]) pill_cap();
    translate([18, 62, 0]) dpad_rocker();
  }
  for (i = [0:1]) translate([78 + i*30, 62, 0]) shoulder_paddle();
}

// ===========================================================================
//                          DISPLAY SPACER PUCKS
// ===========================================================================
// Four pucks sit on the display PCB's clear perimeter and are pressed down by
// the bay tray floor, holding the display against the front face. A relief
// pocket in the contact face clears anything up to 2 mm tall on the board.
// They cannot be part of the tray: they hang 6.2 mm below its floor, which
// would make the tray unprintable without support.

module display_spacer() {
  difference() {
    cylinder(d = disp_spacer_d, h = disp_spacer_h);
    translate([0,0,-EPS]) cylinder(d = disp_spacer_d - 4.0, h = 2.0 + EPS);
  }
}

module display_spacers() {
  for (i = [0:3]) translate([i * (disp_spacer_d + 4), 0, 0]) display_spacer();
}

// ===========================================================================
//                              microSD HATCH
// ===========================================================================

module sd_hatch() {
  difference() {
    union() {
      translate([-(sd_hatch_w - 2*clr_slide)/2, 0, 0])
        cube([sd_hatch_w - 2*clr_slide, sd_hatch_t, sd_hatch_h - 2*clr_slide]);
      // flush outer flange, seats in a rebate in the wall's outer face, so
      // the plug cannot be pushed into the case
      translate([-sd_hatch_w/2 - 1.5, 0, -1.5])
        cube([sd_hatch_w + 3.0 - 2*clr_slide, 1.0, sd_hatch_h + 3.0 - 2*clr_slide]);
      // barbs
      for (s = [-1,1]) translate([s*(sd_hatch_w/2 - clr_slide), 0.6, sd_hatch_h/2 - 1])
        rotate([0,0,45]) cube([1.0,1.0,4.0], center=true);
    }
    // card slot straight through
    translate([-16/2, -EPS, sd_hatch_h/2 - 3.0]) cube([16, sd_hatch_t + 2, 2.4]);
    // finger scallop
    translate([0, sd_hatch_t, sd_hatch_h/2]) rotate([90,0,0]) cylinder(d = 9, h = 1.2);
  }
}

// ===========================================================================
//                            FIT CHECK JIG
// ===========================================================================
// One thin plate carrying EVERY hole, boss, pin and outline in the design.
// Print this first: about 40 minutes, and it validates positions before the
// ten-hour shell.

t_jig = 2.5;

module jig_label(s, x, y, sz = 4) {
  translate([x, y, t_jig - 0.6]) linear_extrude(0.61)
    text(s, size = sz, halign = "center", valign = "center", font = "Liberation Sans");
}

module fit_check_jig() {
  difference() {
    union() {
      linear_extrude(t_jig) body2d();
      // real M3 bosses so the client can test an actual insert + screw
      for (p = boss_pos) translate([p[0], p[1], t_jig - EPS]) insert_boss(6.0);
      // The two real Pi posts, short, with the spigot. The other two hole
      // positions are drilled through below, not posted -- they sit inside
      // the screen aperture in the real shell.
      for (sy = [-1,1]) {
        px = pdx(pi_hole_inset + pi_hole_dy);
        py = pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0));
        translate([px, py, t_jig - EPS]) {
          cylinder(d = 6.4, h = 3.0);
          translate([0,0,3.0]) cylinder(d = pi_hole_d - 0.4, h = pi_pcb_t + 1.0);
        }
      }
      // Two real switch towers so the chosen actuator height can be tried for
      // feel with a real cap. Placed on blank plate, NOT inside a through
      // hole, or they print as floating islands.
      for (jx = [30.0, 175.0])
        translate([jx, 46.0, -z_face_in + t_jig]) tower_round(face_cap_d);
    }

    // scribed outlines, 0.6 deep
    for (o = [
      [disp_cx - disp_glass_w/2, disp_cy - disp_glass_h/2, disp_glass_w, disp_glass_h],
      [pi_x0, pi_y0, pi_h, pi_w],
      [bay_x0, bay_y0, bay_w, bay_d],
      [spk_cx - spk_w/2, spk_cy - spk_h/2, spk_w, spk_h],
      [pico_x, pico_y, pico_w, pico_h],
      [pam_x, pam_y, pam_w, pam_h],
      [fan_cx - fan_size/2, fan_cy - fan_size/2, fan_size, fan_size]
    ]) translate([0,0,t_jig - 0.6]) linear_extrude(0.61)
        difference() {
          translate([o[0], o[1]]) square([o[2], o[3]]);
          translate([o[0] + 0.7, o[1] + 0.7]) square([o[2] - 1.4, o[3] - 1.4]);
        }

    // every through feature
    translate([ap_cx - (disp_act_w + 2*ap_clr)/2, ap_cy - (disp_act_h + 2*ap_clr)/2, -EPS])
      cube([disp_act_w + 2*ap_clr, disp_act_h + 2*ap_clr, t_jig + E2]);
    for (i = [0:3]) translate([face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90), -EPS])
      cylinder(d = face_cap_d + 2*clr_slide, h = t_jig + E2);
    translate([dpad_cx, dpad_cy, -EPS]) linear_extrude(t_jig + E2)
      cross2d(dpad_size + 2*clr_slide, dpad_arm + 2*clr_slide);
    for (s = [-1,1]) translate([ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy, -EPS])
      linear_extrude(t_jig + E2) pill2d(pill_w + 2*clr_slide, pill_h + 2*clr_slide);
    grille_field(gr_lx0, gr_lx1, gr_y0, gr_y1, t_jig);
    grille_field(gr_rx0, gr_rx1, gr_y0, gr_y1, t_jig);
    for (p = mag_pos) translate([p[0], p[1], -EPS]) cylinder(d = mag_pocket_d, h = mag_pocket_h);
    for (sx = [-1,1], sy = [-1,1])
      translate([spk_cx + sx*spk_pitch_x/2, spk_cy + sy*spk_pitch_y/2, -EPS])
        cylinder(d = spk_screw_pilot, h = t_jig + E2);
    if (fan_enable) for (sx = [-1,1], sy = [-1,1])
      translate([fan_cx + sx*fan_pitch/2, fan_cy + sy*fan_pitch/2, -EPS])
        cylinder(d = fan_pilot, h = t_jig + E2);
    translate([sd_x - sd_hatch_w/2, 3, -EPS]) cube([sd_hatch_w, sd_hatch_h, t_jig + E2]);
    // the two un-posted Pi hole positions, drilled so they can still be checked
    for (sy = [-1,1])
      translate([pdx(pi_hole_inset), pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0)), -EPS])
        cylinder(d = pi_hole_d, h = t_jig + E2);

    jig_label("FIT CHECK -- do not print the shell until this passes", W/2, H - 4, 4.5);
    jig_label("Pi 3B+", pi_x0 + 28, pi_y0 + 70);
    // NOT inside the bay outline: that whole area is the open screen
    // aperture on the jig, so an engraved label there would not exist.
    jig_label("BANK BAY -- MEASURE THE BANK", bay_x0 + bay_w/2, 44, 4);
    jig_label("SPK 70x30", 101, 28, 3.5);
    jig_label("PICO", pico_x + pico_w/2, pico_y + pico_h/2);
    jig_label("PAM", pam_x + pam_w/2, pam_y + pam_h/2);
    // The fan sits behind the screen, so its marks fall inside the aperture
    // cut on a flat jig. Only its left-hand half survives; check the fan
    // position against the rear frame instead.
    jig_label("FAN", fan_cx - 6, fan_cy - 18, 3.5);
    for (c = disp_clamp) translate([c[0], c[1], t_jig - 0.6])
      linear_extrude(0.61) difference() {
        circle(d = disp_spacer_d); circle(d = disp_spacer_d - 1.4);
      }
    for (sx = [-1,1], sy = [-1,1])
      translate([disp_cx + sx*disp_hole_dx/2, disp_cy + sy*disp_hole_dy/2, -EPS])
        cylinder(d = disp_hole_d, h = t_jig + E2);
    jig_label("SD", sd_x, 20);
    jig_label("switch tower, both sides: try your actuator height", W/2, 36, 3.2);
  }
}

// ===========================================================================
//                               ASSEMBLY
// ===========================================================================

module assembly(explode = 0) {
  color("#3a4250") front_shell();
  translate([0,0,explode*0.6]) color("#5a6374") bay_tray();
  translate([0,0,explode*1.4]) color("#48505f") rear_frame();
  translate([0,0,explode*2.2]) color("#181EA9") panel("arkiv");
  translate([0,0,-explode*0.5]) color("#c8ccd4") {
    for (i = [0:3]) translate([face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90), 0]) round_cap(face_cap_d);
    for (s = [-1,1]) translate([ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy, 0]) pill_cap();
    translate([dpad_cx, dpad_cy, 0]) dpad_rocker();
  }
  color("#6b7486") for (c = disp_clamp) translate([c[0], c[1], z_disp_pcb]) display_spacer();
  proxy_display(); proxy_pi(); proxy_bank(); proxy_speaker();
  proxy_pico(); proxy_pam(); proxy_fan();
}

// Assembled positions of the controls, used by the per-colour asm_* exports.
// Face buttons are indexed as everywhere else in this file: i = 0 outer
// (toward the nearest side edge), 1 top, 2 inner, 3 bottom. In SNES terms
// that is A, X, Y, B.
module at_face_button(i) {
  translate([face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90), 0]) children();
}

// Shoulder paddles at rest. shoulder_paddle() is drawn in the shoulder_block
// frame (x at the paddle centre, y = 0 at the top wall inner face), so it only
// needs lifting to its slideway: z sh_z0 .. sh_z0 + sh_zh, with clr_slide
// either side. At rest the flange's outer face bears on the counterbore end at
// y = -sh_stem and the stem stands 1.0 proud of the top edge.
module asm_shoulder_paddles() {
  for (sx = [sh_lx, sh_rx]) translate([sx, H - t_wall, sh_z0 + clr_slide]) shoulder_paddle();
}

// ===========================================================================
//                         PRINT-ORIENTED EXPORTS
// ===========================================================================

module export_part(p) {
  if      (p == "front_shell")   front_shell();                       // face down
  else if (p == "bay_tray")      translate([0,0,-z_tray_f]) bay_tray();
  else if (p == "rear_frame")    rotate([180,0,0]) translate([0,0,-z_frame_r]) rear_frame();
  // Panels print EMBLEM UP, inner face on the bed: a raised emblem cannot be
  // printed face down, and the inner face is deliberately flat so it can be.
  else if (p == "panel_world")   translate([0,0,-z_frame_r]) panel("world");
  else if (p == "panel_arkiv")   translate([0,0,-z_frame_r]) panel("arkiv");
  else if (p == "panel_arc")     translate([0,0,-z_frame_r]) panel("arc");
  else if (p == "buttons")       buttons();
  else if (p == "display_spacers") display_spacers();
  else if (p == "sd_hatch")      sd_hatch();
  else if (p == "fit_check_jig") fit_check_jig();
  // Assembled-position exports, one component per target. These deliberately
  // skip the print re-orientation above, so every part lands in true device
  // coordinates and the web viewer can stack and colour them without knowing
  // any transforms. NOT for slicing - use the print-oriented targets for that.
  else if (p == "asm_front_shell") front_shell();
  else if (p == "asm_bay_tray")    bay_tray();
  else if (p == "asm_rear_frame")  rear_frame();
  else if (p == "asm_panel_world") panel("world");
  else if (p == "asm_panel_arkiv") panel("arkiv");
  else if (p == "asm_panel_arc")   panel("arc");
  else if (p == "asm_caps") {
    for (i = [0:3]) translate([face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90), 0]) round_cap(face_cap_d);
    for (s = [-1,1]) translate([ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy, 0]) pill_cap();
    translate([dpad_cx, dpad_cy, 0]) dpad_rocker();
  }
  else if (p == "asm_spacers") {
    for (c = disp_clamp) translate([c[0], c[1], z_disp_pcb]) display_spacer();
  }
  else if (p == "asm_display")   proxy_display();
  else if (p == "asm_internals") { proxy_pi(); proxy_bank(); proxy_speaker(); proxy_pico(); proxy_pam(); }
  // Per-colour splits of the above, for the viewer's colour manifest. The
  // monolithic asm_caps / asm_panel_<kind> / asm_internals targets stay as
  // they were; the viewer build excludes them so nothing is drawn twice.
  // Rear panel, body and emblem separately (see panel_body / panel_logo).
  else if (p == "asm_panel_world_body") panel_body("world");
  else if (p == "asm_panel_world_logo") panel_logo("world");
  else if (p == "asm_panel_arkiv_body") panel_body("arkiv");
  else if (p == "asm_panel_arkiv_logo") panel_logo("arkiv");
  else if (p == "asm_panel_arc_body")   panel_body("arc");
  else if (p == "asm_panel_arc_logo")   panel_logo("arc");
  // Controls: D-pad, each face button, both pills, both shoulder paddles.
  else if (p == "asm_cap_dpad")  translate([dpad_cx, dpad_cy, 0]) dpad_rocker();
  else if (p == "asm_cap_a")     at_face_button(0) round_cap(face_cap_d);
  else if (p == "asm_cap_x")     at_face_button(1) round_cap(face_cap_d);
  else if (p == "asm_cap_y")     at_face_button(2) round_cap(face_cap_d);
  else if (p == "asm_cap_b")     at_face_button(3) round_cap(face_cap_d);
  else if (p == "asm_cap_pills") {
    for (s = [-1,1]) translate([ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy, 0]) pill_cap();
  }
  else if (p == "asm_shoulders") asm_shoulder_paddles();
  // Internals, one proxy per colour.
  else if (p == "asm_pi_board")  pi_place() proxy_pi_board();
  else if (p == "asm_pi_parts")  pi_place() proxy_pi_parts();
  else if (p == "asm_bank")      proxy_bank();
  else if (p == "asm_speaker")   proxy_speaker();
  else if (p == "asm_pico")      proxy_pico();
  else if (p == "asm_pam")       proxy_pam();

  else if (p == "assembly")      assembly();
  else if (p == "assembly_exploded") assembly(6);
  else                           assembly();
}

export_part(is_undef(part) ? "assembly" : part);

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
//   "panel_world" / "panel_arkiv" / "panel_arc" / "panel_chainlink" / "panel_hedera" / "panel_ethglobal"
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
//   x = device width,  0 = the PLAYER'S RIGHT-hand edge
//   y = device height, 0 = bottom edge, +y up
//   z = depth,         0 = front face OUTER surface, +z rearward
//   Because +z points AWAY from the player, +x runs to the player's LEFT when
//   the device is held and looked at. (Earlier revisions said "x = 0 is the
//   left edge", which is only true looking at the BACK. That mistake put the
//   D-pad under the right thumb.) So: D-pad at high x, face buttons at low x.
//   Exports re-orient each part into its support-free print orientation.
//
// ASSEMBLY ORDER -- the whole design is checked against it by
// check_assembly.py. Shell face-down on the bench, everything drops in from
// the open back (-z) unless noted:
//    1  heat-set the 8 M3 inserts into the shell bosses
//    2  drop the 4 face caps, 2 pills and the D-pad rocker into their rings
//    3  press the switches into the 3 switch plates, lay each plate over its
//       caps and screw it down (6 x M3x8 self-tapping), then the D-pad pivot
//    4  push the 2 shoulder paddles in from OUTSIDE through the top wall,
//       drop a 1.75 mm filament pin into each, drop the 2 shoulder switches in
//    5  display glass-down into its pocket, then the 4 spacer pucks on its PCB
//    6  speaker onto its posts
//    7  Pi onto its posts -- the two wall clips snap over its left edge
//    8  bay tray over the two right-hand bosses
//    9  Pico and PAM8403 taped inside their fences on the rear frame, then the
//       rear frame in, 8 x M3x8 into the inserts
//   10  magnets into frame and panel, panel on
//   11  microSD hatch in from outside, power bank in through the top edge
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
clr_fit   = 0.40; // drop-in fit  (parts located by hand over posts/bosses:
                  //               tray ears, switch-plate sleeves)

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
// ISO 7380: head 5.7 dia x 1.65. EVERY screw in the device is this one screw.
scr_len      = 8.0;
scr_dk       = 5.7;   // head diameter
scr_k        = 1.65;  // head height
scr_d        = 3.3;   // clearance hole
scr_head_d   = 6.4;   // button head clearance, 0.35 all round
scr_head_h   = 2.1;   // counterbore depth
// Shell material has to stay this far from every screw axis above the boss
// top, or the head cannot seat. Checked, not assumed: check_assembly.py.
scr_head_clr = scr_dk/2 + 0.5;          // 3.35
// The same M3 x 8 screws self-tap into printed posts (switch plates, D-pad
// pivot, speaker).
pilot_selftap = 2.8;

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
// Outline for the POCKET, from Waveshare's own 3D model (vendor/), measured
// from the active-area centre. The 2D drawing's "121 x 76" is the PCB; the
// touch glass is 120.7 x 77.8 and its flex tail folds round the bottom edge
// to 42.35 below the active-area centre. The pocket has to take all of it.
disp_ol_x   = 60.50;   // [OFFICIAL 3D] half-width (PCB)
disp_ol_top = 36.11;   // [OFFICIAL 3D] above the active-area centre (PCB)
disp_ol_bot = 42.35;   // [OFFICIAL 3D] below it (glass + flex tail)

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

// How far each edge connector sticks out past the board outline, read off
// the drawing's outlines (USB/ETH) and its side view (the three on the long
// edge). The Pi must DROP straight in onto its posts, so nothing may reach
// into a wall: the board is set in from the walls by the worst overhang plus
// pi_wall_clr, and the wall holes are sized for the cable PLUGS instead.
// All five measured off the vector geometry of RP-008337-DS-2 (vendor/),
// scaled by its own 85 x 56 board outline (3.144 pt/mm).
pi_ovh_usb  = 1.98;  // [OFFICIAL] USB-A stacks (body face; the flange tabs too)
pi_ovh_eth  = 1.98;  // [OFFICIAL] RJ45
pi_ovh_pwr  = 1.21;  // [OFFICIAL] micro-USB
pi_ovh_hdmi = 1.48;  // [OFFICIAL] HDMI
pi_ovh_av   = 2.51;  // [OFFICIAL] 3.5 mm jack barrel
pi_wall_clr_x = 1.0; // [DESIGN] AV barrel to the x = 0 wall (keeps the board
                     //          where rev 3 verified it, x 5.91)
pi_wall_clr_y = 0.5; // [DESIGN] USB / RJ45 faces to the top wall
// Through-hole pins and pegs of the big connectors stand this far below the
// board. The RJ45 pegs are the deepest.
pi_tht_below = 1.8;  // [ASSUMED]
pi_tht_bx0   = 65.65; // [OFFICIAL] where the USB / RJ45 bodies (and their pins) start
// LPDDR2 RAM on the UNDERSIDE, under the SoC. Nothing may bear on it.
pi_ram = [21.0, 18.5, 33.0, 30.5];   // [ASSUMED] bx0, by0, bx1, by1

// Pi placement. The board is rotated 90 deg: its 85 mm axis runs up the
// device. by = 56 (the micro-USB / HDMI / AV edge) faces the x = 0 wall (the
// player's RIGHT), bx = 85 (the USB-A / Ethernet edge) faces the TOP wall.
pi_x0 = t_wall + max(pi_ovh_pwr, pi_ovh_hdmi, pi_ovh_av) + pi_wall_clr_x;   //  5.91
pi_y0 = H - t_wall - pi_wall_clr_y - max(pi_ovh_usb, pi_ovh_eth) - pi_w;    // 34.12
function pdx(by) = pi_x0 + (pi_h - by);   // board y -> device x
function pdy(bx) = pi_y0 + bx;            // board x -> device y

// ---------------------------------------------------------------------------
// 5. Z STACK  (front face outer = 0, +z rearward)
// ---------------------------------------------------------------------------
z_face_in   = t_face;                        //  2.40 face inner surface
z_disp_pcb  = z_face_in + disp_t_stack;      // 11.40 display PCB rear face
z_disp_rear = z_disp_pcb + disp_rear_proj;   // 17.10 rearmost display feature

// The Pi sits BESIDE most of the display, not behind it: it overlaps the
// glass only over x 40.5..61.9. Over that strip the REAL display model
// (Waveshare's own STEP) carries a 6.5 x 6.8 IC standing 2.0 proud of its
// PCB, i.e. to z 13.4, right under the Pi's GPIO through-hole pins
// (pi_tht_below). 15.6 keeps 0.4 between them.
z_pi_front  = 15.60;   // [DESIGN] Pi PCB front face
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
// 6. POWER BANK BAY -- Noise MagSafe Wireless 10000 mAh, Built-in Stand
//    Amazon.in ASIN B0GVN4NHKB, the listing it was bought from: "Item
//    Dimensions 10 x 6.8 x 1.9 cm", 192 g. Noise's own pages publish no size.
//    The listing photos put the Type-C port on a SHORT end, so the bank lies
//    long axis across the device with the port toward the Pi side, and its
//    lead leaves through the drawer's side wall. The bay is a removable
//    drawer, not a sealed cavity: the client also uses this bank as a phone
//    charger.
//    The bank is Type-C output only. Its lead leaves the drawer through the
//    pass-through at the drawer's inner end and feeds the Pi's 5V/GND GPIO
//    pins (2 and 6). The Pi's own micro-USB faces the wall, so a plug can
//    only reach it from OUTSIDE -- that port stays free for bench power.
// ---------------------------------------------------------------------------
bank_w = 100.0;   // [LISTING] long axis, across the device
bank_h =  68.0;   // [LISTING] short axis, into the device from the top edge
bank_t =  19.0;   // [LISTING] thickness, folded kickstand included
// The port's position ALONG its short end is not published, so the drawer's
// cable slot spans most of that end rather than being cut for one spot.

bay_w  = bank_w + 2*clr_slide;
bay_d  = bank_h + clr_slide;
bay_t  = bank_t + 2*clr_slide;
bay_x0 = 67.5;                    // [DESIGN]
bay_x1 = bay_x0 + bay_w;          // 173.90
bay_y1 = H - t_wall;              // 121.60 open at the top edge
bay_y0 = bay_y1 - bay_d;          //  52.40
bay_z1 = z_bay_f + bay_t;         //  34.50 -- the rear frame closes the bay
bay_det_h = 0.9;                  // [DESIGN] retention detent proud height

// --- rest of the z stack, derived -----------------------------------------
// The rear frame plane sits ON the bay walls, so the frame presses the tray
// home, and it must also clear the Pi's 16 mm USB stacks. Measuring a thicker
// power bank therefore grows the whole device correctly.
z_frame_f   = max(bay_z1, z_pi_max + 1.2);   // 34.50 at the defaults
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
pico_x = 140.0; pico_y = 16.0;   // [DESIGN] lower-right, USB end at x = 140
// Taped to the INSIDE of the rear frame, flat back against it, inside a low
// locating fence. Nothing below it in the shell has to carry it, and it
// comes out with the frame for rewiring. USB-wired to a Pi USB-A port.

// PAM8403 amplifier. Variants run 21 x 18 x 3.4 (mini, no pot) up to
// 30 x 30. Robu's 19-rupee part is almost certainly the mini.
// Robu SKU 33457 "PAM8403 5V Two-channel Stereo Mini Class-D", no pot.
// 21 x 18 x 3 per a seller of the same part (techiesms); one other listing
// says 21 x 22, so the frame locates it with an open L-corner, not a fence.
pam_w = 21.0;   // [LISTING]
pam_h = 18.0;   // [LISTING]
pam_t =  3.4;   // [LISTING] incl. solder blobs
pam_x = 177.2; pam_y = 88.0;   // [DESIGN] right-hand strip, taped to the frame
// If the client's board turns out to be a 30 x 30 variant it will NOT fit
// the 23.3 mm right-hand strip -- move it to the bottom-left trough and
// re-run. See README.
fence_h = 0.8;    // [DESIGN] locating fence on the frame's inner face

// Waveshare Colorful Heat Sink Set (2 x aluminium + 1 x copper, adhesive).
// "Low profile" is the only published figure.
heatsink_h = 6.0;   // [ASSUMED] Waveshare publishes no height; the photos show
                    // a low-profile set. 6 is an upper bound, and the frame
                    // sits 4+ mm higher than the fan bosses need anyway
heatsink_pad = 16.0;// [DESIGN]  keep-out square around each chip

// ---------------------------------------------------------------------------
// 9. CONTROLS
// ---------------------------------------------------------------------------
// Tactile switches: 6 x 6 footprint, ten actuator heights in the kit from
// 4.3 to 13 mm. THE ACTUATOR HEIGHT IS A PARAMETER ON PURPOSE -- the client
// picks after a test print. Everything downstream (plate thickness, pocket
// floor, speaker stand-off) is derived from it. Use 5.0 or taller: below
// that the pocket shoulder in the switch plate gets too thin to print.
sw_size      = 6.0;
sw_pocket    = sw_size + 2*clr_press;   // 6.30 press fit
sw_rib       = 0.30;   // [MEASURE] crush rib height into the pocket. The plain 6.30 pocket printed
                       // loose and the switch backed out under a press. Pick from the
                       // switch_rib_test piece (0.20 / 0.30 / 0.40) and set it here.
sw_rib_w     = 1.2;    // [DESIGN] rib base width along the wall
sw_mouth     = 0.5;    // [DESIGN] lead-in chamfer depth at the pocket mouth
sw_body_h    = 3.5;    // [ASSUMED] body height above the seating plane
sw_actuator_h = 5.0;   // [DESIGN] TOTAL height, seating plane -> plunger tip.
                       // Use the kit's 6x6x5 switches. Not a free choice: the
                       // face-button plate sits under the Pi, and its legs +
                       // solder reach z_sw_legs = 13.65 against the board at
                       // 15.6. 6 mm leaves under 1 mm for the wires; 7 and up
                       // hit the Pi. Below 5 the plate's pocket shoulder is too
                       // thin to print.
sw_plunger_d = 3.5;    // [ASSUMED]
sw_lead_clr  = 4.2;    // [DESIGN] plunger clearance bore
sw_leg_h     = 3.5;    // [ASSUMED] leg length behind the seating plane
sw_travel    = 0.25;   // [ASSUMED] plunger travel to the click
sw_wire_clr  = 1.0;    // [DESIGN] solder blob + wire behind the leg tips
t_tower      = 1.6;    // [DESIGN] wall of a printed ring

cap_t        = 1.6;    // [DESIGN] cap flange thickness
cap_proud    = 2.0;    // [DESIGN] how far A/B/X/Y stand off the face (0.6 felt flush on the real print)
dpad_proud   = 2.0;    // [DESIGN] D-pad, same as the face buttons
pill_proud   = 1.2;    // [DESIGN] START/SELECT lower, so they are not hit by accident
cap_gap      = 0.15;   // [DESIGN] lost motion between plunger and cap

// HOW THE CONTROLS ASSEMBLE. Each cap drops into an OPEN ring on the inside of
// the face, front first, from the back. A separate SWITCH PLATE carrying the
// switches then goes over the caps and is screwed to two posts. The plate is
// what traps the caps -- there is no closed cavity anywhere, so nothing has to
// be fitted "inside" a printed part. (The first revision had closed towers:
// the caps could not physically be put in.)
//
// The flange floats cap_float between the face and the plate. That is more
// than the switch travel, so the SWITCH is the rear stop, never the plate:
// a flange that bottoms first would stop the button short of its click.
cap_float    = 0.8;                                  // [DESIGN]
z_cap_back   = t_face + cap_t;                       // 4.00 cap flange rear
z_sw_tip     = z_cap_back + cap_gap;                 // 4.15 plunger tip
z_sw_seat    = z_sw_tip + sw_actuator_h;             // 9.15 at the default
z_sw_floor   = z_sw_seat - sw_body_h;                // 5.65 pocket shoulder
z_plate_f    = z_cap_back + cap_float;               // 4.80 switch plate front
z_ring_top   = z_plate_f - 0.2;                      // 4.60 rings stop short
z_sw_legs    = z_sw_seat + sw_leg_h + sw_wire_clr;   // 13.65 keep-out behind

// Switch-plate posts: M3 x 8 self-tapping. The head height is set by the
// screw, not by taste: an 8 mm screw has to stop 1.0 short of the face skin,
// so the head bears 8 + 1.0 above the face inner surface. The plate reaches
// the post top with a SLEEVE that drops over the post (which also locates the
// plate) and a solid cap on top.
post_d       = 6.5;                                  // [DESIGN]
sleeve_id    = post_d + 2*clr_fit;                   // 7.30
sleeve_od    = sleeve_id + 2*1.4;                    // 10.10
t_sleeve_cap = 2.4;
z_plate_head = z_face_in + 1.0 + scr_len;            // 11.40 head bearing face
z_post_top   = z_plate_head - t_sleeve_cap;          //  9.00
z_plate_r    = z_sw_seat;                            //  9.15 plate rear face

// The speaker sits behind the START/SELECT plate, whose switch legs and
// screw heads are under it in plan. DERIVED so a taller switch can never
// silently put a leg into the speaker.
z_spk_f      = max(z_sw_legs, z_plate_head + scr_k) + 0.4;   // 14.05
spk_post_h   = z_spk_f - z_face_in;                  // 11.65

// D-pad: four 6 x 6 tactiles under ONE printed rocker, with a CENTRE PIVOT.
// Without a pivot a press in the middle pushes the rocker straight back onto
// all four switches (up+down+left+right at once). The pivot is an M3 x 8
// screw through the plate's centre, tip toward the rocker: turn it in until a
// centre press does nothing, back it off until every arm clicks. It
// self-taps into the plate, so it holds wherever it is set.
dpad_cx = W - 20.5; dpad_cy = ap_cy;   // [DESIGN] PLAYER'S LEFT (high x)
dpad_r  = 9.0;                         // [DESIGN] switch centre radius
dpad_size  = 26.0; dpad_arm   =  9.0;  // [DESIGN] front cross, across / arm
dpad_flange = 30.0; dpad_arm_f = 11.0; // [DESIGN] rear flange cross
dpad_pivot_gap = 0.30;                 // [DESIGN] nominal, adjustable
z_pivot_tip  = z_cap_back + dpad_pivot_gap;          // 4.30
z_pivot_head = z_pivot_tip + scr_len;                // 12.30
dpad_plate_across = 34.0; dpad_plate_arm = 15.0;     // [DESIGN]

// NO ANALOG THUMBSTICK WAS PURCHASED. Nothing below is built; these are the
// documented hooks for adding one later.
stick_enable = false;   // [DESIGN]
stick_cx = 20.5; stick_cy = 54.0;
stick_bore_d = 24.0; stick_pad_pitch = 20.0; stick_shift = 0.0;

// Face buttons: four caps in a diamond, PLAYER'S RIGHT (low x). Roles as the
// player sees them: A right, B bottom, X top, Y left. The player's right is
// -x, so on this side A is index 2 (180 deg) and Y is index 0.
// Adjacent flange counterbores are face_r*sqrt(2) apart; cap_d = 9.0 keeps
// 1.03 mm of ring wall between them.
face_cx = 20.5; face_cy = ap_cy + stick_shift;   // [DESIGN]
face_r  =  9.5;                                  // [DESIGN] diamond radius
face_cap_d =  9.0;                               // [DESIGN]
face_i_a = 2; face_i_x = 1; face_i_y = 0; face_i_b = 3;

// Plate screw posts, two per plate, on diagonals clear of every ring.
face_posts = [[face_cx + 10.5, face_cy + 10.5], [face_cx - 10.5, face_cy - 10.5]];
dpad_posts = [[dpad_cx + 11.0, dpad_cy + 11.0], [dpad_cx - 11.0, dpad_cy - 11.0]];

// START / SELECT pills, centred below the screen.
pill_w = 14.0; pill_h = 6.0; pill_dx = 9.0; pill_cy = 31.5;  // [DESIGN]
// 31.5, not 33: the display pocket reaches down to y 39.45 (see disp_ol_bot)
pill_posts = [[W/2 - 20.0, 22.0], [W/2 + 20.0, 22.0]];       // [DESIGN]

// Shoulder buttons on the top edge. A paddle is pushed in from OUTSIDE
// through its slot in the top wall; a 1.75 mm filament pin dropped in from
// the back through the block and a slot in the paddle's stem keeps it in and
// sets its travel. The switch drops into a pocket behind the stem.
sh_lx = 14.0; sh_rx = 182.5;   // [DESIGN] centres; right moved in 2.5 so the
                               // top-right corner screw clears the block
sh_w  = 15.0; sh_z0 = 4.0; sh_zh = 8.0;   // paddle: 15 wide, z 4..12
sh_pin_d     = 1.75;   // [DESIGN] a piece of 1.75 filament
sh_pin_hole  = 1.95;
sh_pin_y     = -3.0;   // pin axis, from the top wall inner face (+y out)
sh_in        = 6.0;    // stem length inside the wall at rest
sh_travel    = cap_gap + sw_travel + 0.3;             // 0.70 slot free travel
// Block top: just under the Pi's through-hole pins -- the RJ45 pegs are right
// over the left block.
sh_block_top = z_pi_front - pi_tht_below - 0.3;       // 13.50

// Speaker grille, two fields flanking the pills. Kept below y 17 so the pill
// plate's posts (y 22) stand on solid face, not on slots.
gr_y0 = 4.0; gr_y1 = 17.0;      // [DESIGN]
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
// 8 M3 insert bosses, full height from the face to the rear frame.
//
// Rules every position has to meet (all verified by check_assembly.py):
//  * the screw HEAD sits above the boss top, beside the shell wall, so the
//    screw axis must be >= scr_head_clr (3.35) from every wall face. On a
//    straight edge that means an inset of 6.5 (axis 4.1 off the wall face);
//    in a rounded corner it means sitting near the corner arc's centre.
//    The first revision used 4.4 and no M3 head could seat at all.
//  * nothing may overhang the display, the Pi or the power bank in plan:
//    those drop in from the back and a boss above them blocks the way. That
//    rules out the whole top edge between the corners -- there is no screw at
//    the top-left; the Pi is held there by two wall clips instead.
//  * clear of the caps, rings and switch plates at the face, and of the
//    shoulder blocks at the top corners.
// A boss inset 6.5 no longer touches the wall, so each gets a web to the wall
// (boss_web) -- the stiffness the old "welded" layout was after, without
// putting the wall in the screw's way.
boss_pos = [
  [  7.3,   7.3], [ 54.0,   6.5], [150.0,   6.5], [194.7,   7.3],
  [  6.5,  28.0], [195.5,  45.0], [195.5,  70.0], [194.7, 116.7]
];
boss_web_w = 3.0;   // [DESIGN]
// The bay tray is not screwed down. It drops over these two bosses, which
// locate it, and the rear frame lands on the bay walls and presses it home.
tray_ears = [[195.5, 45.0], [195.5, 70.0]];
tray_ear_d = boss_od + 5.0;

// Pi retention: two flexible clips rise from the face beside the wall and
// snap over the board's by = 56 edge (device x = pi_x0). Board-x positions
// chosen in the gaps between the micro-USB, HDMI and AV connectors.
pi_clip_bx = [[16.4, 21.4], [65.8, 70.1]];   // [DESIGN] bx ranges, clear of
                                             // the frame towers and the shoulder block
pi_clip_t  = 1.7;     // cantilever thickness (x)
pi_clip_lip = 0.6;    // how far the lip reaches over the board

// Display clamp points: four spots on the display PCB that are (a) under the
// bay tray floor and (b) on the clear perimeter of the board, away from the
// rear DSI connector whichever way round the board is fitted.
disp_clamp = [[75, 59], [152, 59], [72, 111], [152, 111]];   // (72,111): 3 mm off an IC
                                                              // on the display's back
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
//   hedera.svg Hedera official lockup (hedera.com/brand logo library), trademark sign dropped

// ===========================================================================
//                              PRIMITIVES
// ===========================================================================

module rrect(w, h, r) {
  offset(r=r) offset(delta=-r) square([w, h]);
}

// Outer body outline, in device xy.
module body2d() { rrect(W, H, cr); }
module rrect_c(w, h, r) { translate([-w/2, -h/2]) rrect(w, h, r); }   // centred
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

// M3 heat-set boss standing on the face inner surface. SOLID on purpose: the
// pilot, the lead-in and the head relief are cut from the WHOLE shell at the
// end of front_shell(), after every union. Cut inside the boss (as the first
// revision did) a neighbouring wall or rib unioned later simply re-fills the
// hole -- which is exactly what happened in all three corners.
module insert_boss(h = boss_h) {
  cylinder(d = boss_od, h = h);
}
module insert_pilot(h = boss_h) {
  translate([0,0,h - ins_pilot_h]) cylinder(d = ins_pilot_d, h = ins_pilot_h + 1.0);
  translate([0,0,h - ins_lead_h])  cylinder(d1 = ins_pilot_d, d2 = ins_lead_d, h = ins_lead_h + EPS);
}

// Unit vector from a boss toward its nearest wall(s): both walls in a corner.
function boss_dir(p) = let(
  dx = (p[0] < 12) ? -1 : ((p[0] > W - 12) ? 1 : 0),
  dy = (p[1] < 12) ? -1 : ((p[1] > H - 12) ? 1 : 0),
  n  = sqrt(dx*dx + dy*dy)) [dx/n, dy/n];

// Webs tying each boss to its wall, clipped to the body outline.
module boss_webs() {
  intersection() {
    linear_extrude(wall_top) body2d();
    for (p = boss_pos)
      translate([0,0,z_face_in - EPS]) linear_extrude(boss_h + EPS)
        hull() {
          translate(p) circle(d = boss_web_w);
          translate(p + 9*boss_dir(p)) circle(d = boss_web_w);
        }
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

// A cross outline, used for the D-pad rocker, its flange, its face hole, its
// ring and its switch plate.
module cross2d(across, arm) {
  offset(r=1.2) offset(delta=-1.2)
    union() { square([across, arm], center=true); square([arm, across], center=true); }
}

// ---------------------------------------------------------------- controls
function face_pos(i) = [face_cx + face_r*cos(i*90), face_cy + face_r*sin(i*90)];
function dpad_sw(i)  = [dpad_cx + dpad_r*cos(i*90), dpad_cy + dpad_r*sin(i*90)];
function pill_pos(s) = [ap_cx + s*(pill_w/2 + pill_dx/2), pill_cy];

// Counterbore outlines the cap flanges sit in (flange + clr_slide all round).
module cb2d_round() { circle(d = face_cap_d + 3.0 + 2*clr_slide); }
module cb2d_pill()  { pill2d(pill_w + 3.0 + 2*clr_slide, pill_h + 3.0 + 2*clr_slide); }
module cb2d_dpad()  { cross2d(dpad_flange + 2*clr_slide, dpad_arm_f + 2*clr_slide); }

// Every counterbore, in place. Cut from the WHOLE shell so no neighbouring
// ring wall can intrude on a flange (adjacent face rings overlap by design).
module control_counterbores() {
  translate([0,0,z_face_in - EPS]) linear_extrude(z_plate_f - z_face_in + 1.0) {
    for (i = [0:3]) translate(face_pos(i)) cb2d_round();
    for (s = [-1,1]) translate(pill_pos(s)) cb2d_pill();
    translate([dpad_cx, dpad_cy]) cb2d_dpad();
  }
}

// Open rings on the face inner surface: t_tower walls around each counterbore.
module control_rings() {
  translate([0,0,z_face_in - EPS]) linear_extrude(z_ring_top - z_face_in + EPS) {
    for (i = [0:3]) translate(face_pos(i)) offset(delta = t_tower) cb2d_round();
    for (s = [-1,1]) translate(pill_pos(s)) offset(delta = t_tower) cb2d_pill();
    translate([dpad_cx, dpad_cy]) offset(delta = t_tower) cb2d_dpad();
  }
}

// Plate posts in the shell (solid; pilots cut at shell level).
module plate_posts() {
  for (p = concat(face_posts, dpad_posts, pill_posts))
    translate([p[0], p[1], z_face_in - EPS]) cylinder(d = post_d, h = z_post_top - z_face_in + EPS);
}
module plate_post_pilots() {
  for (p = concat(face_posts, dpad_posts, pill_posts))
    translate([p[0], p[1], z_face_in + 1.0]) cylinder(d = pilot_selftap, h = z_post_top - z_face_in);
}

// The switch pocket in a switch plate, at the switch axis: plunger bore from
// the plate front, square pocket from the shoulder to the plate rear, leg
// reliefs either side. Legs run along x, so a switch goes in legs-along-x.
// Two crush ribs on each of the two solid (leg-free, +-y) walls grip the switch
// body: it pushes in with a thumb and cannot back out when the button is
// pressed. They stop short of the mouth, which is chamfered, so the switch
// starts straight. No glue: superglue wicks into a tactile switch and jams it.
module switch_void(rib = sw_rib) {
  pocket_h = z_plate_r - z_sw_floor;
  translate([0,0,z_plate_f - EPS]) cylinder(d = sw_lead_clr, h = z_sw_floor - z_plate_f + E2);
  translate([0,0,z_sw_floor]) difference() {
    linear_extrude(pocket_h + EPS) square([sw_pocket, sw_pocket], center=true);
    if (rib > 0)
      for (sy = [-1,1], sx = [-1,1])
        translate([sx*1.6, sy*sw_pocket/2, -EPS])
          linear_extrude(pocket_h - sw_mouth)
            polygon([[-sw_rib_w/2, 0], [sw_rib_w/2, 0], [0, -sy*rib]]);
  }
  translate([0,0,z_plate_r - sw_mouth])
    hull() {
      linear_extrude(EPS) square([sw_pocket, sw_pocket], center=true);
      translate([0,0,sw_mouth]) linear_extrude(EPS) square([sw_pocket + 2*sw_mouth, sw_pocket + 2*sw_mouth], center=true);
    }
  for (s = [-1,1]) translate([s*(sw_pocket/2 + 1.0), 0, z_sw_floor])
    linear_extrude(z_plate_r - z_sw_floor + EPS) square([2.4, 5.6], center=true);
}

// 5-minute test piece: three plate-thickness pockets with 0.20 / 0.30 / 0.40 ribs,
// front face on the bed like the plates. Push a real switch into each; the one
// that holds firmly without a fight sets sw_rib.
module switch_rib_test() {
  ribs = [0.20, 0.30, 0.40];
  translate([0,0,-z_plate_f]) difference() {
    translate([0, -6, z_plate_f]) cube([3*12 + 4, 18, z_plate_r - z_plate_f]);
    for (i = [0:2]) translate([8 + i*12, 0, 0]) switch_void(ribs[i]);
    for (i = [0:2]) translate([8 + i*12, 8, z_plate_r - 0.6])
      linear_extrude(1) text(str(ribs[i]*10), size = 3.2, halign = "center", valign = "center",
                             font = "Liberation Sans:style=Bold");
  }
}

// A plate sleeve: tube over a post, solid cap on top that the screw goes
// through. Positioned in device xy.
module plate_sleeve(p) {
  translate([p[0], p[1], z_plate_f]) cylinder(d = sleeve_od, h = z_plate_head - z_plate_f);
}
module plate_sleeve_void(p) {
  translate([p[0], p[1], z_plate_f - EPS]) cylinder(d = sleeve_id, h = z_post_top - z_plate_f + EPS);
  translate([p[0], p[1], z_plate_f - EPS]) cylinder(d = scr_d, h = z_plate_head - z_plate_f + E2);
}

// ---- the three switch plates, in device coordinates ----
module face_plate() {
  difference() {
    union() {
      translate([0,0,z_plate_f]) linear_extrude(z_plate_r - z_plate_f)
        hull() for (i = [0:3]) translate(face_pos(i)) offset(delta = 1.1) cb2d_round();
      for (p = face_posts) plate_sleeve(p);
    }
    for (i = [0:3]) translate(face_pos(i)) switch_void();
    for (p = face_posts) plate_sleeve_void(p);
  }
}

module dpad_plate() {
  difference() {
    union() {
      translate([dpad_cx, dpad_cy, z_plate_f]) linear_extrude(z_plate_r - z_plate_f)
        cross2d(dpad_plate_across, dpad_plate_arm);
      for (p = dpad_posts) plate_sleeve(p);
      // pivot boss: the M3 x 8 pivot self-taps through boss + plate
      translate([dpad_cx, dpad_cy, z_plate_r - EPS]) cylinder(d = 7.0, h = z_pivot_head - z_plate_r + EPS);
    }
    for (i = [0:3]) translate(dpad_sw(i)) switch_void();
    for (p = dpad_posts) plate_sleeve_void(p);
    translate([dpad_cx, dpad_cy, z_plate_f - 1]) cylinder(d = pilot_selftap, h = z_pivot_head - z_plate_f + 2);
  }
}

module pill_plate() {
  difference() {
    union() {
      translate([0,0,z_plate_f]) linear_extrude(z_plate_r - z_plate_f)
        hull() {
          for (s = [-1,1]) translate(pill_pos(s)) offset(delta = 1.1) cb2d_pill();
          for (p = pill_posts) translate(p) circle(d = sleeve_od);
        }
      for (p = pill_posts) plate_sleeve(p);
    }
    for (s = [-1,1]) translate(pill_pos(s)) switch_void();
    for (p = pill_posts) plate_sleeve_void(p);
  }
}

// ---- Pi wall clips: cantilevers from the face, lip over the board edge ----
module pi_clips() {
  x_in = pi_x0 - 0.3;
  for (r = pi_clip_bx) {
    y0 = pdy(r[0]); y1 = pdy(r[1]);
    translate([x_in - pi_clip_t, y0, z_face_in - EPS])
      cube([pi_clip_t, y1 - y0, z_pi_rear + 0.1 + 1.6 - z_face_in]);
    // lip: flat underside 0.1 above the board, 45 deg lead-in on top
    translate([0, y1, 0]) rotate([90,0,0]) linear_extrude(y1 - y0)
      polygon([[x_in - EPS, z_pi_rear + 0.1], [pi_x0 + pi_clip_lip, z_pi_rear + 0.1],
               [x_in - EPS, z_pi_rear + 0.1 + (pi_x0 + pi_clip_lip - x_in)]]);
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
//                     REAL COMPONENTS (assembly view + fit checks)
// ===========================================================================
// Meshes from components/build_components.py, each in its own local frame
// (documented there). Only the PLACEMENT lives here, so moving a part in
// this file moves its real model and its fit check together.
comp_dir = "components/";
module comp(name) { import(str(comp_dir, name, ".stl")); }

module real_display() { translate([ap_cx, ap_cy, z_face_in]) comp("display_waveshare_5in_dsi"); }

// board frame of the drawing -> device
module pi_place() {
  translate([pi_x0, pi_y0, z_pi_front]) rotate([0,0,90]) translate([0,-pi_h,0]) children();
}
module real_pi()        { pi_place() comp("pi3bplus"); }
module real_heatsinks() {
  pi_place() {
    translate([20.0, 17.5, pi_pcb_t + 1.4]) comp("heatsink_soc");
    translate([55.0, 24.5, pi_pcb_t + 1.0]) comp("heatsink_lan");
  }
}
module real_bank()    { translate([bay_x0 + clr_slide, bay_y0, z_bay_f]) comp("power_bank"); }
module real_speaker() { translate([spk_cx - spk_w/2, spk_cy - spk_h/2, z_spk_f]) comp("speaker_fit0502"); }
// Pico and PAM hang under the rear frame, flat side taped to it.
module real_pico() {
  translate([pico_x + pico_w, pico_y + pico_h, z_frame_f]) rotate([180,0,0]) rotate([0,0,90]) comp("pico");
}
module real_pam() { translate([pam_x, pam_y + 18.0, z_frame_f]) rotate([180,0,0]) comp("pam8403_mini"); }

// Switch seating: plunger toward the face for the plates, outward (+y) for
// the shoulder blocks. Legs always along x.
sh_y_seat = -sh_in - cap_gap - sw_actuator_h;     // -11.15 (block frame)
sh_zc     = sh_z0 + sh_zh/2;                      //   8.00 plunger axis
module real_switches() { real_plate_switches(); real_shoulder_switches(); }
module real_plate_switches() {
  for (i = [0:3]) translate([face_pos(i)[0], face_pos(i)[1], z_sw_seat]) rotate([180,0,0]) comp("tactile_6x6");
  for (i = [0:3]) translate([dpad_sw(i)[0], dpad_sw(i)[1], z_sw_seat]) rotate([180,0,0]) comp("tactile_6x6");
  for (s = [-1,1]) translate([pill_pos(s)[0], pill_pos(s)[1], z_sw_seat]) rotate([180,0,0]) comp("tactile_6x6");
}
module real_shoulder_switches() {
  for (sx = [sh_lx, sh_rx]) translate([sx, H - t_wall + sh_y_seat, sh_zc]) rotate([-90,0,0]) comp("tactile_6x6");
}
// Every screw in the device is the same M3 x 8 button head.
module real_frame_screws() {
  for (p = boss_pos) translate([p[0], p[1], z_frame_r - scr_head_h]) comp("screw_m3x8");
}
module real_plate_screws() { real_post_screws(); real_pivot_screw(); }
module real_post_screws() {
  for (p = concat(face_posts, dpad_posts, pill_posts)) translate([p[0], p[1], z_plate_head]) comp("screw_m3x8");
}
module real_pivot_screw() { translate([dpad_cx, dpad_cy, z_pivot_head]) comp("screw_m3x8"); }
module real_inserts() { for (p = boss_pos) translate([p[0], p[1], z_frame_f - ins_len]) comp("insert_m3"); }
module real_frame_magnets() { for (p = mag_pos) translate([p[0], p[1], z_frame_r - mag_pocket_h]) comp("magnet_6x3"); }
module real_panel_magnets() { for (p = mag_pos) translate([p[0], p[1], z_frame_r + mag_pocket_h - mag_t]) comp("magnet_6x3"); }
module shoulder_pins() {
  for (sx = [sh_lx, sh_rx])
    translate([sx, H - t_wall + sh_pin_y, z_face_in + 0.5]) cylinder(d = sh_pin_d, h = sh_pin_len, $fn = 16);
}
sh_pin_len = sh_block_top - 0.1 - (z_face_in + 0.5);   // 10.5 at the defaults

// Old box proxies, kept for the fan provision only.
module proxy_fan() {
  if (fan_enable)
    color("#333") translate([fan_cx - fan_size/2, fan_cy - fan_size/2, z_frame_f - fan_thk])
      cube([fan_size, fan_size, fan_thk]);
}

// ===========================================================================
//                                CUTOUTS
// ===========================================================================

// Every wall port, cut through the shell walls. Holes on the Pi's side are
// sized for the cable PLUG overmoulds (the receptacles sit 2.9..4.4 behind
// the outer face now), and none reaches more than 1 mm inside the wall, so
// they never touch the Pi clips.
port_depth = t_wall + 2.0;
module port_cuts() {
  // --- x = 0 WALL: Pi micro-USB (bench power), HDMI, 3.5 mm AV -------------
  translate([-1, pdy(pi_pwr_bx),  z_pi_rear + pi_pwr_z/2])
    rotate([0,90,0]) linear_extrude(port_depth) rrect_c(9.5, 12.5, 1.5);
  translate([-1, pdy(pi_hdmi_bx), z_pi_rear + pi_hdmi_z/2])
    rotate([0,90,0]) linear_extrude(port_depth) rrect_c(12.5, 22.0, 1.5);
  translate([-1, pdy(pi_av_bx),   z_pi_rear + pi_av_z/2 - 0.0])
    rotate([0,90,0]) linear_extrude(port_depth) circle(d = 9.6);

  // --- TOP WALL: one USB-A stack opened, the other two left blind ----------
  // Stack A (board by 2.45..15.59) is the external port. Stack B feeds the
  // Pico internally; Ethernet is deliberately sealed.
  translate([pdx((pi_usbA_by0 + pi_usbA_by1)/2), H - t_wall - 1, z_pi_rear + pi_usb_z/2])
    rotate([-90,0,0]) linear_extrude(port_depth)
      square([17.0, pi_usb_z + 1.6], center=true);

  // --- TOP WALL: power bank bay mouth --------------------------------------
  // Deep enough in y to pass through the reinforcement rib, and down to just
  // under the tray floor so the tray never lands on the rib.
  translate([bay_x0 - t_rib - clr_slide, H - t_wall - 9, z_tray_f - 0.3])
    cube([bay_w + 2*t_rib + 2*clr_slide, t_wall + 11, bay_z1 + 0.6 - (z_tray_f - 0.3)]);

  // --- TOP WALL: shoulder paddle slideways, through the wall and the block --
  for (sx = [sh_lx, sh_rx])
    translate([sx - (sh_w + 2*clr_slide)/2, H - t_wall - 7.0, sh_z0 - clr_slide])
      cube([sh_w + 2*clr_slide, t_wall + 9, sh_zh + 2*clr_slide]);

  // --- BOTTOM WALL: microSD hatch aperture + flange rebate -----------------
  translate([sd_x - sd_hatch_w/2, -1, z_pi_front - 2.0])
    cube([sd_hatch_w, t_wall + 3, sd_hatch_h]);
  translate([sd_x - sd_hatch_w/2 - 1.5, -EPS, z_pi_front - 3.5])
    cube([sd_hatch_w + 3.0, 1.0 + EPS, sd_hatch_h + 3.0]);
}

// Side and bottom breathing vents in the shell walls. Each slot is 12 long
// in z and 2 wide in y (the first revision had the pill2d arguments swapped,
// which merged six slots into one 30 mm gash). Cut only 0.5 mm past the wall.
module wall_vents() {
  for (i = [0:5]) {
    // x = 0 wall, above the AV jack
    translate([-1, 98 + i*3.6, z_pi_rear + 3]) rotate([0,90,0])
      linear_extrude(t_wall + 1.5) pill2d(12.0, 2.0);
    // x = W wall, between the bosses at y 70 and y 116.7
    translate([W - t_wall - 0.5, 92 + i*3.6, z_pi_rear + 3]) rotate([0,90,0])
      linear_extrude(t_wall + 1.5) pill2d(12.0, 2.0);
  }
  // bottom wall, between the bosses at x 150 and x 194.7
  for (i = [0:6])
    translate([158 + i*4.2, -1, z_pi_front + 2]) rotate([-90,0,0])
      linear_extrude(t_wall + 1.5) pill2d(2.2, 9.0);
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

      // display pocket walls: a 1.6 mm rib round the REAL display outline
      translate([0,0,z_face_in]) linear_extrude(z_disp_pcb - z_face_in)
        difference() {
          translate([ap_cx - disp_ol_x - clr_slide - 1.6, ap_cy - disp_ol_bot - clr_slide - 1.6])
            square([2*disp_ol_x + 2*clr_slide + 3.2, disp_ol_top + disp_ol_bot + 2*clr_slide + 3.2]);
          translate([ap_cx - disp_ol_x - clr_slide, ap_cy - disp_ol_bot - clr_slide])
            square([2*disp_ol_x + 2*clr_slide, disp_ol_top + disp_ol_bot + 2*clr_slide]);
        }

      // M3 insert bosses and their webs to the wall
      for (p = boss_pos) translate([p[0], p[1], z_face_in - EPS]) insert_boss();
      boss_webs();

      // Pi posts. ONLY the two mounting holes at the x = pi_x0 + 3.5 edge get
      // a post: the other two are over the display.
      for (sy = [-1,1]) {
        px = pdx(pi_hole_inset + pi_hole_dy);
        py = pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0));
        translate([px, py, z_face_in - EPS]) {
          cylinder(d = 6.4, h = z_pi_front - z_face_in + EPS);
          translate([0,0,z_pi_front - z_face_in])
            cylinder(d = pi_hole_d - 0.4, h = pi_pcb_t + 1.0);
        }
      }
      // Support rib under the Pi's middle, between the face-button plate and
      // the display pocket (merges into the pocket rib). It starts past the
      // RAM on the board's underside -- nothing may bear on that chip.
      // It also stops 1 mm short of the USB / RJ45 end: their through-hole
      // pins stand below the board from bx 65.65 on.
      translate([ap_cx - disp_ol_x - clr_slide - 2.1, pdy(pi_ram[2]) + 1.5, z_face_in - EPS])
        cube([2.1, pdy(pi_tht_bx0) - 1.0 - (pdy(pi_ram[2]) + 1.5), z_pi_front - z_face_in + EPS]);
      pi_clips();

      // speaker posts (pilots cut at shell level)
      for (sx = [-1,1], sy = [-1,1])
        translate([spk_cx + sx*spk_pitch_x/2, spk_cy + sy*spk_pitch_y/2, z_face_in - EPS])
          cylinder(d = 6.0, h = spk_post_h + EPS);

      // open rings the caps drop into, and the switch-plate posts
      control_rings();
      plate_posts();

      // shoulder switch blocks
      for (sx = [sh_lx, sh_rx]) translate([sx, H - t_wall, 0]) shoulder_block();

      // Bay mouth reinforcement: a rib on the inside of the top wall, from
      // the face up to the frame plane (the frame lands on it). The mouth cut
      // removes it under the tray.
      translate([bay_x0 - t_rib - 3, H - t_wall - 3, z_face_in - EPS])
        cube([bay_w + 2*t_rib + 6, 3, z_frame_f - z_face_in + EPS]);

      // PANEL REGISTER RIDGE on the wall top (outer 1.2 mm stays a flat land).
      translate([0,0,wall_top - EPS]) linear_extrude(1.2 + EPS)
        difference() { inner2d(1.2); inner2d(t_wall); }
    }

    // ---- subtractions, AFTER every union, so nothing can re-fill them ----
    // screen aperture
    translate([ap_cx - (disp_act_w + 2*ap_clr)/2, ap_cy - (disp_act_h + 2*ap_clr)/2, -EPS])
      cube([disp_act_w + 2*ap_clr, disp_act_h + 2*ap_clr, t_face + E2]);

    // button holes through the face, and the counterbores behind them
    for (i = [0:3]) translate(face_pos(i)) cap_hole(face_cap_d);
    translate([dpad_cx, dpad_cy, -EPS]) linear_extrude(t_face + E2)
      cross2d(dpad_size + 2*clr_slide, dpad_arm + 2*clr_slide);
    for (s = [-1,1]) translate([pill_pos(s)[0], pill_pos(s)[1], -EPS])
      linear_extrude(t_face + E2) pill2d(pill_w + 2*clr_slide, pill_h + 2*clr_slide);
    control_counterbores();

    // insert pilots, head reliefs, plate-post and speaker-post pilots
    for (p = boss_pos) translate([p[0], p[1], z_face_in - EPS]) insert_pilot();
    for (p = boss_pos) translate([p[0], p[1], z_frame_f]) cylinder(r = scr_head_clr, h = 10);
    plate_post_pilots();
    for (sx = [-1,1], sy = [-1,1])
      translate([spk_cx + sx*spk_pitch_x/2, spk_cy + sy*spk_pitch_y/2, z_face_in + 1.0])
        cylinder(d = spk_screw_pilot, h = spk_post_h + 1);

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

// Shoulder block. Local origin: x at the paddle centre, y = 0 at the top wall
// INNER face (device y = H - t_wall), +y outward, z = device z.
//
//   y -7.0 .. +4.4            slideway for the paddle stem (cut in port_cuts,
//                             through the wall as well)
//   y = sh_pin_y              vertical pin hole, open to the back
//   y sh_y_seat .. +3.5       switch pocket, plunger facing +y, open to the back
//   y sh_y_seat-4.5 .. seat   leg / wire relief, open to the back
sh_blk_half = (sh_w + 2*clr_slide)/2 + t_tower;       // 9.30
sh_blk_back = sh_y_seat - sw_leg_h - sw_wire_clr - 1.2;
module shoulder_block() {
  difference() {
    translate([-sh_blk_half, sh_blk_back, z_face_in - EPS])
      cube([2*sh_blk_half, -sh_blk_back, sh_block_top - z_face_in + EPS]);
    // pin hole, from 0.5 above the face up through the top
    translate([0, sh_pin_y, z_face_in + 0.5]) cylinder(d = sh_pin_hole, h = 20, $fn = 24);
    // plunger clearance from the switch body to the slideway
    translate([0, sh_y_seat + sw_body_h - EPS, sh_zc]) rotate([-90,0,0])
      cylinder(d = sw_lead_clr, h = -7.0 - (sh_y_seat + sw_body_h) + 0.5);
    // switch pocket, loaded from the back
    translate([-sw_pocket/2, sh_y_seat, sh_zc - sw_pocket/2]) cube([sw_pocket, sw_body_h, 20]);
    // the plunger stands 1.5 proud of the body, so it needs its own slot to
    // come down through the block roof as the switch drops in
    translate([-(sw_plunger_d + 0.5)/2, sh_y_seat + sw_body_h - EPS, sh_zc - sw_lead_clr/2])
      cube([sw_plunger_d + 0.5, sw_actuator_h - sw_body_h + 0.3, 20]);
    // legs + wires behind the switch, open to the back
    // (reaches 1.0 in front of the seat: the legs leave the body sides there)
    translate([-4.2, sh_y_seat - sw_leg_h - sw_wire_clr, sh_zc - 3.2]) cube([8.4, sw_leg_h + sw_wire_clr + 1.0, 20]);
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
    // ears reach past the outer envelope and foul the side wall, so the
    // drawer cannot seat. The clip is the guard, not a fudge: any future
    // feature placed near a wall is trimmed automatically.
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
          translate([p[0], p[1], z_tray_f]) cylinder(d = tray_ear_d, h = t_tray);
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

    // clearance holes that drop over the shell bosses -- clr_fit, so the tray
    // drops in by hand without having to be wiggled onto two posts at once
    for (p = tray_ears)
      translate([0,0,-EPS]) linear_extrude(60) hull() {
        translate(p) circle(d = boss_od + 2*clr_fit);
        translate(p + 9*boss_dir(p)) circle(d = boss_web_w + 2*clr_fit);   // the web
      }

    // Type-C lead exit: the bank's port is on its short end facing the Pi, so
    // the slot is in the drawer's Pi-side wall, spanning most of that end
    // (the port's position along it is not published). Stops short of the
    // retention detent near the mouth.
    translate([bay_x0 - t_rib - EPS, bay_y0 + 4, z_bay_f + 3.0])
      cube([t_rib + E2, (bay_y1 - 16 - 4) - (bay_y0 + 4), bay_t - 6.0]);
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
      // Pi towers over the four mounting holes. TRAVEL LIMITERS, 0.3 mm off
      // the board: the Pi is held down by the two wall clips, so the frame
      // never has to press on it (a frame pushed up by the Pi at the top-left,
      // where there is no screw, would bow).
      for (sx = [-1,1], sy = [-1,1]) {
        px = pdx(pi_hole_inset + (sx>0 ? pi_hole_dy : 0));
        py = pdy(pi_hole_inset + (sy>0 ? pi_hole_dx : 0));
        z0 = z_pi_rear + 0.3;
        translate([px, py, z0])
          cylinder(d = 6.4, h = z_frame_f - z0 + EPS);   // straight: a flared top
                                                         // passed 0.1 from the GPIO pins
      }
      // low fences locating the Pico and the PAM8403 for taping
      translate([0,0,z_frame_f - fence_h]) linear_extrude(fence_h + EPS) {
        difference() {
          translate([pico_x - 0.4 - 0.8, pico_y - 0.4 - 0.8]) square([pico_w + 2.4, pico_h + 2.4]);
          translate([pico_x - 0.4, pico_y - 0.4]) square([pico_w + 0.8, pico_h + 0.8]);
          translate([pico_x - 3, pico_y + pico_h/2 - 5]) square([5, 10]);   // USB end open
        }
        // PAM8403: an L-corner (two sides only), so a 21 x 18 or a 21 x 22
        // board both sit in it
        difference() {
          translate([pam_x - 0.3 - 0.8, pam_y - 0.3 - 0.8]) square([pam_w + 1.1, pam_h + 1.1]);
          translate([pam_x - 0.3, pam_y - 0.3]) square([pam_w + 5, pam_h + 5]);
        }
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
      // keep-outs, all checked in check_assembly.py: the magnet pocket at
      // (20,114) (the old field at x 14.. cut straight into it), the Pi
      // towers, the screw counterbores at (195.5, 70) and (6.5, 28)
      vent_field(26, 50, 98, 112, t_frame);
      vent_field(176, 191, 54, 76, t_frame);
      vent_field(14, 48, 18, 28, t_frame);
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
  else if (kind == "chainlink")     // hexagon mark only: sized by height, it is taller than wide
    resize([0, 64, logo_h], auto=[true,true,false]) linear_extrude(1) import(str(logo_dir, "chainlink.svg"), center=true);
  else if (kind == "hedera")
    resize([logo_w, 0, logo_h], auto=[true,true,false]) linear_extrude(1) import(str(logo_dir, "hedera.svg"), center=true);
  else if (kind == "ethglobal" || kind == "ethglobal_full")
    linear_extrude(logo_h) eth_mumbai2d();
  else if (kind == "ethglobal_lockup")
    linear_extrude(logo_h) eth_lockup2d();
}

// ETHGlobal Mumbai logomark (the diya), official SVG split into one file per path by
// logos/make_ethglobal_mumbai.py. Paths are painted in order, so each one is cut by every later
// path: the colour groups tile the emblem without overlapping, as a multi-colour print needs.
include <logos/ethglobal_mumbai/groups.scad>
module eth_mumbai_path2d(i) {
  translate([-eth_mumbai_w/2, -eth_mumbai_h/2])
    import(str(logo_dir, "ethglobal_mumbai/p", i < 10 ? "0" : "", i, ".svg"));
}
module eth_mumbai_visible2d(i) {
  n = len(eth_mumbai_groups);
  difference() {
    eth_mumbai_path2d(i);
    if (i < n - 1) for (j = [i + 1 : n - 1]) eth_mumbai_path2d(j);
  }
}
// group: "orange" / "pink" / "green", or undef for the whole emblem
module eth_mumbai2d(group = undef, groups = eth_mumbai_groups) {   // groups: eth_mumbai_groups (3, merged) or eth_mumbai_colours (all 6)
  // close then open by 0.01 mm: removes the slivers the path cuts leave, which make non-manifold solids
  offset(delta = 0.01) offset(delta = -0.02) offset(delta = 0.01)
    for (i = [0 : len(eth_mumbai_groups) - 1])
      if (is_undef(group) || groups[i] == group) eth_mumbai_visible2d(i);
}
// One colour of the emblem as its own solid, in the same place as panel()'s emblem, for multi-colour prints.
// The full ETHGlobal Mumbai lockup (diya + "ETHGlobal MUMBAI"), official SVG split per path by
// logos/make_ethglobal_mumbai_lockup.py, cut in painting order like the logomark above.
include <logos/ethglobal_mumbai_lockup/groups.scad>
module eth_lockup_path2d(i) {
  translate([-eth_lockup_w/2, -eth_lockup_h/2])
    import(str(logo_dir, "ethglobal_mumbai_lockup/p", i < 10 ? "0" : "", i, ".svg"));
}
module eth_lockup_visible2d(i) {
  n = len(eth_lockup_colours);
  difference() {
    eth_lockup_path2d(i);
    if (i < n - 1) for (j = [i + 1 : n - 1]) eth_lockup_path2d(j);
  }
}
module eth_lockup2d(colour = undef, colours = eth_lockup_colours) {
  offset(delta = 0.01) offset(delta = -0.02) offset(delta = 0.01)
    for (i = [0 : len(eth_lockup_colours) - 1])
      if (is_undef(colour) || colours[i] == colour) eth_lockup_visible2d(i);
}
module panel_lockup_colour(colour, colours = eth_lockup_colours) {
  translate([W/2, H/2, z_panel_r]) linear_extrude(logo_h - EPS) eth_lockup2d(colour, colours);
}
module panel_logo_group(group, groups = eth_mumbai_groups) {
  translate([W/2, H/2, z_panel_r]) linear_extrude(logo_h - EPS) eth_mumbai2d(group, groups);
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
  translate([0,0,-pill_proud]) linear_extrude(pill_proud + t_face) pill2d(pill_w, pill_h);
  translate([0,0,t_face])     linear_extrude(cap_t)              pill2d(pill_w + 3.0, pill_h + 3.0);
}

// Cross front plate through the cross face hole, cross flange behind it.
// The flange arms are wider than the face-hole arms, so the rocker cannot
// fall out forwards; the switches bear on the flange at dpad_r and the pivot
// screw tip on its centre.
module dpad_rocker() {
  difference() {
    union() {
      translate([0,0,-dpad_proud]) linear_extrude(dpad_proud + t_face)
        cross2d(dpad_size, dpad_arm);
      translate([0,0,t_face]) linear_extrude(cap_t)
        cross2d(dpad_flange, dpad_arm_f);
    }
    // shallow dished thumb pads on the four arms, no printed lettering
    for (i = [0:3])
      translate([(dpad_size/2 - 3.2)*cos(i*90), (dpad_size/2 - 3.2)*sin(i*90), -dpad_proud - 2.7])
        sphere(d = 7.5);
  }
}

// Shoulder paddle, in the shoulder_block frame (x at the paddle centre, y = 0
// at the top wall inner face, +y outward), z from 0 -- it prints flat. No
// flange: the stem is pushed in from outside and a filament pin through the
// slot keeps it. At rest the slot's inner end bears on the pin; pressed, the
// switch bottoms before the slot's outer end reaches the pin.
module shoulder_paddle() {
  linear_extrude(sh_zh - 2*clr_slide)
    difference() {
      translate([-(sh_w - 2*clr_slide)/2, -sh_in])
        offset(r = 0.8) offset(delta = -0.8)
          square([sh_w - 2*clr_slide, sh_in + t_wall + 1.0]);
      hull() {
        translate([0, sh_pin_y]) circle(d = sh_pin_d + 0.4, $fn = 24);
        translate([0, sh_pin_y + sh_travel]) circle(d = sh_pin_d + 0.4, $fn = 24);
      }
    }
}

// Print tray: caps flipped so every visible surface is against the bed.
module buttons() {
  translate([0, 0, t_face + cap_t]) rotate([180,0,0]) {
    for (i = [0:3]) translate([i*20, 0, 0]) round_cap(face_cap_d);
    for (i = [0:1]) translate([i*26, 26, 0]) pill_cap();
    translate([18, 62, 0]) dpad_rocker();
  }
  for (i = [0:1]) translate([70 + i*22, 50, 0]) shoulder_paddle();
}

// Print tray: the three switch plates, front face on the bed, pockets up.
module switch_plates() {
  translate([-face_cx + 20, -face_cy + 20, -z_plate_f]) face_plate();
  translate([-dpad_cx + 62, -dpad_cy + 20, -z_plate_f]) dpad_plate();
  translate([-W/2 + 45, -pill_cy + 58, -z_plate_f]) pill_plate();
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
      // y 0.75: the barb diamonds stay 0.04 behind the outer face (at 0.6
      // they poked 0.1 through it and kept the part off the bed)
      for (s = [-1,1]) translate([s*(sd_hatch_w/2 - clr_slide), 0.75, sd_hatch_h/2 - 1])
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
      // Two real cap rings so a printed cap can be tried for fit.
      for (jx = [30.0, 175.0])
        translate([jx, 46.0, t_jig - EPS]) linear_extrude(z_ring_top - z_face_in + EPS)
          difference() { offset(delta = t_tower) cb2d_round(); cb2d_round(); }
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
    for (i = [0:3]) translate([face_pos(i)[0], face_pos(i)[1], -EPS])
      cylinder(d = face_cap_d + 2*clr_slide, h = t_jig + E2);
    for (jx = [30.0, 175.0]) translate([jx, 46.0, -EPS]) cylinder(d = face_cap_d + 2*clr_slide, h = t_jig + E2);
    translate([dpad_cx, dpad_cy, -EPS]) linear_extrude(t_jig + E2)
      cross2d(dpad_size + 2*clr_slide, dpad_arm + 2*clr_slide);
    for (s = [-1,1]) translate([pill_pos(s)[0], pill_pos(s)[1], -EPS])
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
  translate([0,0,-explode*0.5]) color("#c8ccd4") asm_caps_all();
  translate([0,0, explode*0.3]) color("#7a8290") { face_plate(); dpad_plate(); pill_plate(); }
  translate([0,0, explode*0.3]) color("#b8bcc2") { real_switches(); real_plate_screws(); }
  color("#26282C") asm_shoulder_paddles();
  translate([0,0, explode*0.4]) { real_display(); color("#6b7486") for (c = disp_clamp) translate([c[0], c[1], z_disp_pcb]) display_spacer(); }
  translate([0,0, explode*0.5]) { real_speaker(); real_pi(); real_heatsinks(); }
  translate([0,0, explode*0.6]) color("#5a6374") bay_tray();
  translate([0,0, explode*0.7]) real_bank();
  translate([0,0, explode*1.4]) { color("#48505f") rear_frame(); real_pico(); real_pam(); real_frame_screws(); }
  translate([0,0, explode*2.2]) color("#181EA9") panel("arkiv");
}

module asm_caps_all() {
  for (i = [0:3]) translate(face_pos(i)) round_cap(face_cap_d);
  for (s = [-1,1]) translate(pill_pos(s)) pill_cap();
  translate([dpad_cx, dpad_cy, 0]) dpad_rocker();
}

// Assembled position of one face button by ROLE (face_i_* in section 9).
module at_face_button(i) { translate(face_pos(i)) children(); }

// Shoulder paddles at rest: pulled out until the slot's inner end meets the
// pin, stem 1.0 proud of the top edge, riding in the middle of the slideway.
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
  else if (p == "panel_chainlink") translate([0,0,-z_frame_r]) panel("chainlink");
  else if (p == "panel_hedera")  translate([0,0,-z_frame_r]) panel("hedera");
  else if (p == "panel_ethglobal") translate([0,0,-z_frame_r]) panel("ethglobal");
  else if (p == "buttons")       buttons();
  // One print tray per filament colour, for the print shop. Caps flipped so
  // every visible face is on the bed, exactly as in buttons().
  else if (p == "buttons_orange")   translate([0,0,t_face + cap_t]) rotate([180,0,0])
                                      for (i = [0:1]) translate([i*20, 0, 0]) round_cap(face_cap_d);     // A, B
  else if (p == "buttons_slate")    translate([0,0,t_face + cap_t]) rotate([180,0,0])
                                      for (i = [0:1]) translate([i*20, 0, 0]) round_cap(face_cap_d);     // X, Y
  else if (p == "buttons_pale")     translate([0,0,t_face + cap_t]) rotate([180,0,0])
                                      for (i = [0:1]) translate([i*26, 0, 0]) pill_cap();                // START, SELECT
  else if (p == "buttons_charcoal") {
    translate([0,0,t_face + cap_t]) rotate([180,0,0]) dpad_rocker();
    for (i = [0:1]) translate([24 + i*22, -20, 0]) shoulder_paddle();
  }
  // Panels split body / emblem in PRINT orientation, for multi-material
  // printers (load both as one object). Single-extruder: print the one-piece
  // panel and change filament at z = t_panel.
  else if (p == "panel_world_body")  translate([0,0,-z_frame_r]) panel_body("world");
  else if (p == "panel_world_logo")  translate([0,0,-z_frame_r]) panel_logo("world");
  else if (p == "panel_arkiv_body")  translate([0,0,-z_frame_r]) panel_body("arkiv");
  else if (p == "panel_arkiv_logo")  translate([0,0,-z_frame_r]) panel_logo("arkiv");
  else if (p == "panel_arc_body")    translate([0,0,-z_frame_r]) panel_body("arc");
  else if (p == "panel_arc_logo")    translate([0,0,-z_frame_r]) panel_logo("arc");
  else if (p == "panel_chainlink_body") translate([0,0,-z_frame_r]) panel_body("chainlink");
  else if (p == "panel_chainlink_logo") translate([0,0,-z_frame_r]) panel_logo("chainlink");
  else if (p == "panel_hedera_body") translate([0,0,-z_frame_r]) panel_body("hedera");
  else if (p == "panel_hedera_logo") translate([0,0,-z_frame_r]) panel_logo("hedera");
  else if (p == "panel_ethglobal_body") translate([0,0,-z_frame_r]) panel_body("ethglobal");
  else if (p == "panel_ethglobal_orange") translate([0,0,-z_frame_r]) panel_logo_group("orange");
  else if (p == "panel_ethglobal_pink")   translate([0,0,-z_frame_r]) panel_logo_group("pink");
  else if (p == "panel_ethglobal_green")  translate([0,0,-z_frame_r]) panel_logo_group("green");
  // the full ETHGlobal Mumbai lockup on the cream panel, every official colour
  else if (p == "panel_ethglobal_lockup") translate([0,0,-z_frame_r]) panel("ethglobal_lockup");
  else if (p == "panel_ethglobal_lockup_body") translate([0,0,-z_frame_r]) panel_body("ethglobal_lockup");
  else if (p == "panel_ethglobal_lockup_yellow") translate([0,0,-z_frame_r]) panel_lockup_colour("yellow");
  else if (p == "panel_ethglobal_lockup_orange") translate([0,0,-z_frame_r]) panel_lockup_colour("orange");
  else if (p == "panel_ethglobal_lockup_flame") translate([0,0,-z_frame_r]) panel_lockup_colour("flame");
  else if (p == "panel_ethglobal_lockup_pink") translate([0,0,-z_frame_r]) panel_lockup_colour("pink");
  else if (p == "panel_ethglobal_lockup_red") translate([0,0,-z_frame_r]) panel_lockup_colour("red");
  else if (p == "panel_ethglobal_lockup_green") translate([0,0,-z_frame_r]) panel_lockup_colour("green");
  else if (p == "panel_ethglobal_lockup_burgundy") translate([0,0,-z_frame_r]) panel_lockup_colour("burgundy");
  // the lockup on the owner's spools: yellow / orange / red / green (eth_lockup_spools)
  else if (p == "panel_ethglobal_lockup_spool_yellow") translate([0,0,-z_frame_r]) panel_lockup_colour("yellow", eth_lockup_spools);
  else if (p == "panel_ethglobal_lockup_spool_orange") translate([0,0,-z_frame_r]) panel_lockup_colour("orange", eth_lockup_spools);
  else if (p == "panel_ethglobal_lockup_spool_red") translate([0,0,-z_frame_r]) panel_lockup_colour("red", eth_lockup_spools);
  else if (p == "panel_ethglobal_lockup_spool_green") translate([0,0,-z_frame_r]) panel_lockup_colour("green", eth_lockup_spools);
  // the complete six-colour logo on the burgundy panel
  else if (p == "panel_ethglobal_full") translate([0,0,-z_frame_r]) panel("ethglobal_full");
  else if (p == "panel_ethglobal_full_body") translate([0,0,-z_frame_r]) panel_body("ethglobal_full");
  else if (p == "panel_ethglobal_full_yellow") translate([0,0,-z_frame_r]) panel_logo_group("yellow", eth_mumbai_colours);
  else if (p == "panel_ethglobal_full_orange") translate([0,0,-z_frame_r]) panel_logo_group("orange", eth_mumbai_colours);
  else if (p == "panel_ethglobal_full_flame") translate([0,0,-z_frame_r]) panel_logo_group("flame", eth_mumbai_colours);
  else if (p == "panel_ethglobal_full_pink") translate([0,0,-z_frame_r]) panel_logo_group("pink", eth_mumbai_colours);
  else if (p == "panel_ethglobal_full_red") translate([0,0,-z_frame_r]) panel_logo_group("red", eth_mumbai_colours);
  else if (p == "panel_ethglobal_full_green") translate([0,0,-z_frame_r]) panel_logo_group("green", eth_mumbai_colours);
  else if (p == "switch_plates") switch_plates();
  else if (p == "switch_rib_test") switch_rib_test();
  else if (p == "display_spacers") display_spacers();
  else if (p == "sd_hatch")      rotate([90,0,0]) sd_hatch();          // flat, outer face on the bed
  else if (p == "fit_check_jig") fit_check_jig();
  // Assembled-position exports, one component per target, in true device
  // coordinates, for the viewer and check_assembly.py. NOT for slicing.
  else if (p == "asm_front_shell") front_shell();
  else if (p == "asm_bay_tray")    bay_tray();
  else if (p == "asm_rear_frame")  rear_frame();
  else if (p == "asm_spacers")     for (c = disp_clamp) translate([c[0], c[1], z_disp_pcb]) display_spacer();
  else if (p == "asm_panel_world_body") panel_body("world");
  else if (p == "asm_panel_world_logo") panel_logo("world");
  else if (p == "asm_panel_arkiv_body") panel_body("arkiv");
  else if (p == "asm_panel_arkiv_logo") panel_logo("arkiv");
  else if (p == "asm_panel_arc_body")   panel_body("arc");
  else if (p == "asm_panel_arc_logo")   panel_logo("arc");
  else if (p == "asm_panel_chainlink_body") panel_body("chainlink");
  else if (p == "asm_panel_chainlink_logo") panel_logo("chainlink");
  else if (p == "asm_panel_hedera_body") panel_body("hedera");
  else if (p == "asm_panel_hedera_logo") panel_logo("hedera");
  // controls
  else if (p == "asm_cap_dpad")  translate([dpad_cx, dpad_cy, 0]) dpad_rocker();
  else if (p == "asm_cap_a")     at_face_button(face_i_a) round_cap(face_cap_d);
  else if (p == "asm_cap_b")     at_face_button(face_i_b) round_cap(face_cap_d);
  else if (p == "asm_cap_x")     at_face_button(face_i_x) round_cap(face_cap_d);
  else if (p == "asm_cap_y")     at_face_button(face_i_y) round_cap(face_cap_d);
  else if (p == "asm_cap_pills") for (s = [-1,1]) translate(pill_pos(s)) pill_cap();
  else if (p == "asm_shoulders") asm_shoulder_paddles();
  else if (p == "asm_pins")      shoulder_pins();
  else if (p == "asm_plate_face")  face_plate();
  else if (p == "asm_plate_dpad")  dpad_plate();
  else if (p == "asm_plate_pills") pill_plate();
  // real bought parts
  else if (p == "asm_display")   real_display();
  else if (p == "asm_pi")        real_pi();
  else if (p == "asm_pi_board")  pi_place() comp("pi3bplus_pcb");     // viewer only
  else if (p == "asm_pi_parts")  pi_place() comp("pi3bplus_parts");   // viewer only
  else if (p == "asm_heatsinks") real_heatsinks();
  else if (p == "asm_bank")      real_bank();
  else if (p == "asm_speaker")   real_speaker();
  else if (p == "asm_pico")      real_pico();
  else if (p == "asm_pam")       real_pam();
  else if (p == "asm_switches")  real_switches();
  else if (p == "asm_switches_plates")   real_plate_switches();
  else if (p == "asm_switches_shoulder") real_shoulder_switches();
  else if (p == "asm_screws_frame")  real_frame_screws();
  else if (p == "asm_screws_plates") real_post_screws();
  else if (p == "asm_screw_pivot")   real_pivot_screw();
  else if (p == "asm_inserts")   real_inserts();
  else if (p == "asm_magnets_frame") real_frame_magnets();
  else if (p == "asm_magnets_panel") real_panel_magnets();

  else if (p == "none")          ;                 // render nothing: for wrappers that add their own geometry
  else if (p == "assembly")      assembly();
  else if (p == "assembly_exploded") assembly(6);
  else                           assembly();
}

export_part(is_undef(part) ? "assembly" : part);

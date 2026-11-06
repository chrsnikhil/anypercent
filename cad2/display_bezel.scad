// ===========================================================================
// Display bezel for the screen actually fitted: Waveshare 50H-800480-IPS-CT
// ("5inch DSI Display, Thin & Light", touch glass 127.70 x 87.45 x 4.9). It is
// NOT the "5inch DSI LCD" the shell pocket was drawn for, so the screen is glued
// on the front face; this frame wraps the glass edge and laps over its black
// print so the screen looks built in.
//
// Glass outline, clear window and pixel area are read from Waveshare's own STEP
// (vendor/50h-800480-ips-ct/50h-800480-ips-ct.stp), origin at the window centre:
//   glass  x -63.85..63.85, y -45.20..42.25 (top face z 4.70)
//   window 109.0 x 65.8, pixels 108.0 x 64.8, both centred on the origin
//   black print: 9.35 on the sides and the top, 12.30 on the cable (bottom) edge
//
// part = "bezel" (default): print orientation, lip face down on the bed.
// part = "bezel_fitted": as it sits on the shell, z = 0 on the face.
// ===========================================================================
$fn = 48;

gl_x0 = -63.85; gl_x1 = 63.85;   // [OFFICIAL 3D] glass outline
gl_y0 = -45.20; gl_y1 = 42.25;   //   y0 is the cable edge (12.30 border), y1 the top (9.35 border)

glass_h = 6.45;  // [MEASURE] glass top above the shell face. 6.45 = glass top to the LCD
                 // back plate in the model, i.e. the LCD back resting on the face.
clr     = 0.30;  // [DESIGN] gap round the glass edge
wall    = 1.60;  // [DESIGN] side wall: clears the Y and D-pad holes beside the glass
lip_t   = 1.00;  // [DESIGN] lip thickness over the glass
lip     = 2.50;  // [DESIGN] lip over the black print on the sides and the top
lip_bot = lip + (12.30 - 9.35);  // wider on the cable edge: an even 6.85 of black shows all round
seat    = 0.15;  // [DESIGN] the lip clears the glass by this before the glue takes up
r_out   = 1.20;  // [DESIGN] outer corner radius

H = glass_h + seat + lip_t;      // face to the top of the lip

module rrect(x0, x1, y0, y1, r) {
  translate([x0 + r, y0 + r]) offset(r = r) square([x1 - x0 - 2*r, y1 - y0 - 2*r]);
}

module bezel_fitted() {
  difference() {
    linear_extrude(H)
      rrect(gl_x0 - clr - wall, gl_x1 + clr + wall, gl_y0 - clr - wall, gl_y1 + clr + wall, r_out);
    // the glass and everything under it
    translate([0, 0, -1]) linear_extrude(glass_h + seat + 1)
      rrect(gl_x0 - clr, gl_x1 + clr, gl_y0 - clr, gl_y1 + clr, 0.5);
    // the opening in the lip
    translate([0, 0, -1]) linear_extrude(H + 2)
      rrect(gl_x0 + lip, gl_x1 - lip, gl_y0 + lip_bot, gl_y1 - lip, 0.5);
  }
}

if (is_undef(part) || part == "bezel")
  translate([0, 0, H]) rotate([180, 0, 0]) bezel_fitted();      // lip face on the bed
else if (part == "bezel_fitted")
  bezel_fitted();

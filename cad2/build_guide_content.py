"""Text and page template for make_build_guide.py. Steps are plain data; the page renders them."""

BACK = {"pos": [101, -70, 290], "target": [101, 62, 18]}      # looking into the open back, shell face-down
FRONT = {"pos": [101, -60, -250], "target": [101, 62, 20]}
TOP = {"pos": [101, 250, 170], "target": [101, 100, 15]}

STEPS = [
    {
        "id": "start", "title": "Before you start", "time": "15 min", "view": FRONT, "showAll": True,
        "summary": "Check the parts, gather the tools, and read the three changes from the original plan. The 3D view shows the finished device; drag to turn it, scroll to zoom.",
        "hardware": ["Printed: front shell, rear frame, bay tray, 3 switch plates, 4 spacer pucks, SD hatch, button set, one panel",
                     "Raspberry Pi 3B+ with the Any% microSD card", "Waveshare 5in DSI display and its ribbon",
                     "12 tactile switches, 6 x 6 mm", "PAM8403 mini amp", "DFRobot FIT0502 speaker",
                     "Power bank and a USB-C cable you can cut", "Pi heatsinks",
                     "8 M3 heat-set inserts, 15 M3 x 8 button-head screws", "12 magnets, 6 x 3 mm (6 frame, 6 per panel)"],
        "tools": ["Soldering iron, fine tip", "Solder and flux", "Multimeter (beep and DC volts)", "2 mm hex key",
                  "Flush cutters, wire strippers", "About 3 m of 26 to 30 AWG wire", "Heatshrink, 1.5 to 2 mm",
                  "Double-sided foam tape", "Hot glue gun (switches)", "Superglue (magnets only)", "Marker and masking tape"],
        "do": [
            ["Power the Pi once as it is now and check the launcher comes up. Then shut it down and unplug everything from the Pi: power, the amp wires and the display ribbon at the Pi end. Leave the ribbon on the display."],
            ["Lay the parts out in step order. Cut two pieces of 1.75 mm filament, 10.5 mm long, for the shoulder buttons."],
            ["<b>Change 1: no Pico.</b> Its USB lead was meant to plug into the Pi's second USB port, but that port faces the top wall with about 0.5 mm to spare, so no plug fits. The 12 buttons go straight to the Pi's GPIO header instead, and a small service on the Pi turns them into the same keys your laptop remote sends.", "warn"],
            ["<b>Change 2: audio is soldered.</b> The Pi's 3.5 mm jack faces a hole in the side wall, so no plug fits from inside. Three short wires are soldered to the jack's legs under the Pi instead (step 8).", "warn"],
            ["<b>Power is as designed.</b> The power bank feeds the GPIO header (pin 2 is 5 V, pin 6 is GND) through a cut USB-C cable. The Pi's micro-USB stays free, reachable from outside for bench power.", "tip"],
        ],
        "checks": ["Launcher boots before you start", "Every part and tool above is on the bench", "Shoulder pins cut, 2 x 10.5 mm"],
        "diagrams": ["header"],
    },
    {
        "id": "inserts", "title": "Heat-set the inserts", "time": "15 min", "view": BACK,
        "summary": "Melt 8 threaded brass inserts into the shell's screw bosses. The rear frame screws into them at the end.",
        "hardware": ["8 x M3 heat-set insert"], "tools": ["Soldering iron", "M3 x 8 screw, for testing"],
        "do": [
            ["Lay the front shell face-down on a towel, open back up. From here on the shell stays face-down. Looking into it, the D-pad side is on your right and the ABXY side on your left: the mirror image of holding it."],
            ["Set the iron to 220 C for a PLA shell or 245 C for PETG."],
            ["Stand an insert on a boss, narrow end down. Rest the iron tip in it and let it sink under light pressure. Stop when the top is flush with the top of the boss."],
            ["Lift the iron straight up. If the insert tilted, reheat it and straighten it while it is soft."],
            ["Let each one cool for about 10 seconds before the next. Do all 8."],
            ["Do not push an insert below flush. The frame screws are only 8 mm long and would no longer reach.", "warn"],
        ],
        "checks": ["All 8 inserts flush with their boss tops", "An M3 x 8 screw threads into each one straight, by hand"],
    },
    {
        "id": "caps", "title": "Drop in the buttons", "time": "2 min", "view": BACK,
        "summary": "The caps rest loose in their rings. The switch plates in step 3 hold them in.",
        "hardware": ["A, B (orange)", "X, Y (grey)", "START, SELECT (light grey)", "D-pad (charcoal)"], "tools": [],
        "do": [
            ["ABXY diamond, on your left: <b>A</b> in the ring nearest the shell edge, <b>Y</b> in the ring nearest the screen, <b>X</b> in the top ring, <b>B</b> in the bottom ring. A and B are orange, X and Y grey."],
            ["START and SELECT are identical pills. They go in the two rings below the screen."],
            ["The cross-shaped D-pad goes in the cross ring on your right, arms lined up with the ring."],
            ["Drop each one in front first. It should sit flat and slide freely. Do not flip the shell from now on.", "tip"],
        ],
        "checks": ["All 7 caps sit flat and move freely"],
    },
    {
        "id": "plates", "title": "Switch plates and button wiring", "time": "60 to 90 min", "view": BACK,
        "summary": "Fit 10 switches into the three plates, solder a signal wire and the shared ground to each, then screw the plates down over the caps. This is the longest step.",
        "hardware": ["10 x tactile switch", "6 x M3 x 8", "10 signal wires (lengths in the table)", "1 ground wire"],
        "tools": ["Soldering iron", "Multimeter (beep)", "Masking tape for labels"],
        "do": [
            ["Cut the 10 signal wires to the lengths in the wire table below and label each end with tape: UP, DOWN, LEFT, RIGHT, A, B, X, Y, START, SELECT. The lengths come from the 3D routes plus 50 mm spare. Keep L and R for step 5."],
            ["Press a switch into each of the 10 pockets from the back with your thumb: plunger first toward the plate's flat face, legs up into the leg slots, until it bottoms out. The ribs in the pocket hold it. Bend long legs flat."],
            ["<b>No superglue on switches.</b> It wicks inside and jams the plunger for good. On the older rib-less plates, hold the switches in with a strip of electrical tape across their backs, or a bead of hot glue on the back corners.", "warn"],
            ["Each switch has 4 legs in two connected pairs. Solder the signal wire to one leg and the ground to the leg <b>diagonally opposite</b>. Diagonal legs are always on different pairs, so the switch always works."],
            ["Ground is one black wire, daisy-chained. Solder short jumpers from ground leg to ground leg within each plate, then one wire on to the next plate. Leave a long tail: it ends on pin 39 in step 8. Cut it about the length in the table."],
            ["Test each switch now: meter on beep, one probe on its signal wire, the other on the ground wire. Press: it beeps. Release: silent."],
            ["Lay each plate over its caps, plunger side down. Its two sleeves drop over two posts. ABXY plate on the left, D-pad plate on the right, pill plate at the bottom centre."],
            ["Drive 2 x M3 x 8 into each plate, 6 in all. Stop when snug; they cut their own thread in plastic."],
            ["Run the wires as the 3D view shows: from each plate down to the bottom edge, then along the bottom toward the Pi's corner. Tape the bundle every few centimetres. The ends stay loose until step 8.", "tip"],
            ["Keep wires away from the middle of the shell. The display lies there in step 6 and must sit flat.", "warn"],
        ],
        "checks": ["Every switch beeps when pressed", "Each cap clicks when pressed from the front", "All 10 wire ends labelled", "Ground tail runs to the Pi corner"],
        "diagrams": ["switch", "wiretable"],
        "labels": ["A", "B", "X", "Y", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT"],
        "focus": ["buttons"],
    },
    {
        "id": "pivot", "title": "Tune the D-pad pivot", "time": "5 min", "view": BACK,
        "summary": "One screw in the middle of the D-pad plate is the rocker's pivot. Its depth sets how the D-pad feels.",
        "hardware": ["1 x M3 x 8"], "tools": ["2 mm hex key"],
        "do": [
            ["Drive the screw into the centre hole of the D-pad plate until it just touches the rocker."],
            ["Press the middle of the D-pad from the front: nothing may click."],
            ["Press each arm: each must click once."],
            ["If the middle clicks, screw in a little. If an arm will not click, back out a quarter turn. Repeat until both are true.", "tip"],
        ],
        "checks": ["Centre press: no click", "Up, down, left and right each click"],
    },
    {
        "id": "shoulders", "title": "Shoulder buttons", "time": "20 min", "view": TOP,
        "summary": "Two paddles slide in through the top edge, pinned by a piece of filament, with a switch behind each.",
        "hardware": ["2 shoulder paddles", "2 x 10.5 mm of 1.75 mm filament", "2 x tactile switch", "L and R wires"],
        "tools": ["Soldering iron", "Hot glue gun"],
        "do": [
            ["Solder the L and R wires and extend the ground chain to both switches before fitting them (same diagonal-leg rule). Label L and R."],
            ["From outside, push each paddle into its slot in the top edge, slotted end first."],
            ["From the back, drop a filament pin down the hole in each block so it passes through the paddle's slot. The paddle now pivots on it."],
            ["Drop a switch into each block's pocket, plunger facing the paddle. Hold it with a bead of <b>hot glue</b> on its back corners, never superglue (it wicks inside and jams the switch)."],
            ["Looking into the back, <b>L is on your right</b> and R on your left. Holding the device, L is under your left finger.", "tip"],
            ["Run the L wire down the right-hand wall and the R wire down the left-hand wall to the bottom bundle."],
        ],
        "checks": ["Both paddles pivot freely and spring back", "L and R each beep on the meter when pressed"],
        "diagrams": ["wiretable"],
        "labels": ["L", "R"],
        "focus": ["buttons"],
    },
    {
        "id": "display", "title": "Display", "time": "10 min", "view": BACK,
        "summary": "The display lies glass-down in its pocket. Four printed pucks on its board carry the tray above it.",
        "hardware": ["Waveshare 5in DSI display, ribbon attached", "4 spacer pucks"], "tools": [],
        "do": [
            ["Do <b>not</b> fit the display's brass standoffs. They would hit the Pi.", "warn"],
            ["Check the ribbon is latched at the display end."],
            ["Lay the display glass-down into its pocket: flex tail toward START/SELECT, DSI connector toward the D-pad side."],
            ["Make sure no wire is trapped under it. It must sit flat, and the glass must not rock."],
            ["Put the 4 spacer pucks on its board at the 4 marked spots."],
        ],
        "checks": ["No standoffs fitted", "Display flat, nothing trapped", "4 pucks in place"],
    },
    {
        "id": "speaker", "title": "Speaker", "time": "5 min", "view": BACK,
        "summary": "The speaker sits in the bottom band over the grille.",
        "hardware": ["FIT0502 speaker", "4 screws to suit its holes, or foam tape"], "tools": ["Screwdriver"],
        "do": [
            ["Drivers face the grille (down into the shell), lead toward the top."],
            ["Lower it onto its 4 posts and fix it with 4 screws or foam tape on the post tops."],
            ["Leave its lead free: it goes to the amp in step 10."],
        ],
        "checks": ["Speaker firm on its posts", "Lead free and reaching toward the top"],
    },
    {
        "id": "pi", "title": "Raspberry Pi and GPIO wiring", "time": "45 min", "view": BACK,
        "summary": "Solder the audio wires under the Pi, plug in the display ribbon, lower the Pi onto its posts, then land every button wire on its header pin.",
        "hardware": ["Pi 3B+ with microSD", "Heatsinks", "3 audio wires, about 40 cm (lengths in the audio diagram)"],
        "tools": ["Soldering iron", "Multimeter", "An aux (3.5 mm) cable, for finding the jack legs", "Heatshrink"],
        "do": [
            ["Stick the heatsinks on the Pi's main chip and its USB/LAN chip."],
            ["<b>Find the jack's legs.</b> Plug an aux cable into the Pi's 3.5 mm jack. Meter on beep: the leg that beeps with the plug's <b>tip</b> is L, with the <b>ring</b> is R. The GND leg beeps with header pin 6. Mark them."],
            ["Unplug the aux cable. Solder a wire to each of the three legs on the underside: red to L, white to R, black to GND. Keep the joints low and cover them with tape; this side faces the display."],
            ["Plug the display ribbon into the Pi's DISPLAY connector, the same way round as when the screen worked on the bench. Close the latch."],
            ["Lower the Pi components-up onto its two posts: HDMI toward the wall with the HDMI hole, USB toward the top edge. The two wall clips snap over the board edge. Feed the audio wires out past the board edge."],
            ["<b>Land the button wires</b> on the header as the pin map shows. Pin 1 is the square pad at the microSD end, on the inner row. Odd pins are the inner row, even pins the outer row."],
            ["Solder each wire straight onto its pin, low down, with heatshrink over the joint. The frame sits about 13 mm above the pin tips, so standard 14 mm jumper housings will not fit upright.", "warn"],
            ["Buttons use pins 11, 13, 15, 16, 18, 22, 29, 31, 36, 37, 38, 40. Ground goes to pin 39. Pins 2, 4, 6 and 14 are kept for power and the amp in step 10.", "tip"],
        ],
        "checks": ["Audio L, R and GND soldered and marked", "Ribbon latched at both ends", "Pi clipped down, ports lined up with the wall holes",
                   "All 12 button wires and the ground on their pins, checked against the map"],
        "diagrams": ["header", "wiretable"],
        "labels": ["GPIO header", "Pin 1", "Audio jack legs"],
        "focus": ["buttons", "audio"],
    },
    {
        "id": "tray", "title": "Bay tray", "time": "3 min", "view": BACK,
        "summary": "The tray forms the power bank drawer and holds the display down. It is not screwed.",
        "hardware": ["Bay tray"], "tools": [],
        "do": [
            ["Lower the tray so its two ears drop over the two bosses on the D-pad side."],
            ["It rests on the spacer pucks. Check no wire is pinched under an ear or its edge."],
        ],
        "checks": ["Tray seated on both bosses", "No wire pinched"],
    },
    {
        "id": "frame", "title": "Rear frame, amp, power and bench test", "time": "60 min", "view": BACK,
        "summary": "Fit the frame magnets and the amp, finish the audio and power wiring, test everything with the back open, then screw the frame down.",
        "hardware": ["Rear frame", "PAM8403", "6 magnets", "8 x M3 x 8", "A USB-C cable to cut"],
        "tools": ["Soldering iron", "Multimeter (DC volts)", "Superglue", "Marker", "Foam tape"],
        "do": [
            ["<b>Magnets.</b> Stack all the magnets into one column and mark the top face of the column. Every magnet's marked face is now the same pole. Frame: press 6 in with the <b>marked face showing</b>, with a drop of superglue."],
            ["<b>Amp.</b> Stick the PAM8403 into its L-shaped corner on the frame's inner face with foam tape, pads facing you."],
            ["<b>Audio.</b> Jack L, GND and R wires to the amp's input L, G and R. Header pin 4 (5 V) to the amp's +, pin 14 (GND) to its -. Amp outputs L+ and L- to the speaker's left driver, R+ and R- to its right driver."],
            ["Never join an amp output minus to ground. The outputs are bridged, and that shorts the amp.", "warn"],
            ["<b>Power lead.</b> Cut a USB-C cable about 15 cm from the plug and strip the red and black wires. Plug it into the bank and switch the bank on. The meter must read <b>+5 V</b> from black to red. If it reads -5 V, the colours are swapped. Unplug it."],
            ["Solder red to <b>pin 2</b> (5 V) and black to <b>pin 6</b> (GND), with heatshrink. Run the lead through the pass-through at the drawer's inner end, plug end in the drawer."],
            ["5 V on any other pin can destroy the Pi. Pin 2 is on the outer row at the microSD end. Check it twice before powering on.", "warn"],
            ["<b>Bench test, back still open.</b> Plug bench power into the micro-USB on the side. The launcher starts and touch works."],
            ["Install the button service: tell Claude \"deploy the button service\" while the Pi is on the hotspot. Then run <code>sudo python3 /opt/anypercent/tools/gpio_buttons.py --test</code> and press all 12 buttons. Each prints down and up."],
            ["Check the sound with <code>speaker-test -D default -c 2 -t wav -l 1</code>. It says Front Left from the left driver and Front Right from the right."],
            ["Unplug bench power, plug the lead into the bank and switch it on: the Pi boots from the bank."],
            ["<b>Close.</b> Tuck every wire in, away from the screw bosses and the frame edge. Lower the frame, magnets facing out, and drive 8 x M3 x 8 into the inserts. Tighten in a cross pattern, snug only."],
        ],
        "checks": ["Frame magnets in, marked faces showing", "Amp wired: input, power, outputs", "Lead reads +5 V before soldering",
                   "Bench test: screen, touch, 12 buttons, sound", "Boots from the power bank", "Frame screwed down, no wire pinched"],
        "diagrams": ["audio", "power", "magnets", "header"],
        "labels": ["PAM8403", "Power lead", "Speaker lead"],
        "focus": ["audio", "power"],
    },
    {
        "id": "panel", "title": "Rear panel", "time": "10 min, plus glue", "view": BACK,
        "summary": "Each panel holds 6 magnets and snaps onto the frame.",
        "hardware": ["One printed panel", "6 magnets per panel"], "tools": ["Superglue", "The marked magnet column"],
        "do": [
            ["Press 6 magnets into the panel's inner pockets with the <b>marked face going into the pocket</b> (hidden), with a drop of superglue."],
            ["Before the glue sets, hold the panel near the back. It must pull on. If it pushes away, that magnet is flipped: pop it out and turn it over."],
            ["Let the glue set, then snap the panel on. Swap panels per sponsor."],
        ],
        "checks": ["Panel pulls on at all 6 points", "Glue set before handling"],
        "diagrams": ["magnets"],
    },
    {
        "id": "bank", "title": "Power bank", "time": "2 min", "view": TOP,
        "summary": "The bank slides in through the top edge like a cartridge.",
        "hardware": ["Power bank"], "tools": [],
        "do": [
            ["Pull the USB-C plug out of the drawer mouth and plug it into the bank."],
            ["Slide the bank in through the top edge, port end first, feeding the lead back in. Push until the detents click."],
            ["To remove it, pull on the finger notch."],
        ],
        "checks": ["Bank clicks in", "Lead not pinched"],
    },
    {
        "id": "test", "title": "Power on and final checks", "time": "10 min", "view": FRONT, "showAll": True,
        "summary": "Switch the bank on and run through the whole device once.",
        "hardware": [], "tools": [],
        "do": [
            ["Switch the power bank on. The Any% splash and launcher appear."],
            ["Walk the launcher with the D-pad, open a game with A, go back with B."],
            ["In a game: L, R, START and SELECT respond. X opens the RetroArch menu, Y returns to the launcher."],
            ["Game sound comes from both drivers. Set the volume in Settings."],
            ["Snap a different panel on and off."],
            ["Before Mumbai: the SSH lockdown checklist in docs/TODO-before-hackathon.md is still open.", "warn"],
        ],
        "checks": ["Boots from the bank", "All 12 buttons work", "Stereo sound", "Touch works", "Panels swap"],
    },
]

HTML = r"""<meta charset="utf-8">
<title>Any% Build Guide</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --bg:#E9ECEF; --surface:#FFFFFF; --sunk:#F3F5F7; --ink:#15171B; --muted:#59616A; --line:#D3D8DE;
  --accent:#D9481F; --accent-soft:#FBE3DA; --accent-ink:#FFFFFF; --stage:#D8DDE2;
  --warn:#8A5A00; --warn-bg:#FFF3D6; --tip:#1F5E8C; --tip-bg:#E3F0FA; --ok:#1E7A46;
  --display:"Chakra Petch", "Segoe UI", system-ui, sans-serif;
  --body:"IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, Consolas, monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0E1012; --surface:#171A1E; --sunk:#1D2126; --ink:#E8EBEE; --muted:#9BA3AC; --line:#2A3037;
  --accent:#F0663D; --accent-soft:#3A1F16; --accent-ink:#17120F; --stage:#121518;
  --warn:#F2C46B; --warn-bg:#2E2412; --tip:#8CC6F0; --tip-bg:#14263A; --ok:#5FD08F; color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0E1012; --surface:#171A1E; --sunk:#1D2126; --ink:#E8EBEE; --muted:#9BA3AC; --line:#2A3037;
  --accent:#F0663D; --accent-soft:#3A1F16; --accent-ink:#17120F; --stage:#121518;
  --warn:#F2C46B; --warn-bg:#2E2412; --tip:#8CC6F0; --tip-bg:#14263A; --ok:#5FD08F; color-scheme:dark;}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--body)}
*{box-sizing:border-box}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{display:grid;grid-template-columns:260px minmax(0,1fr) 440px;grid-template-rows:auto minmax(0,1fr);height:100%}
header.bar{grid-column:1/-1;display:flex;align-items:center;gap:16px;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--surface)}
.brand{font:700 20px/1 var(--display);letter-spacing:.02em}
.brand span{color:var(--accent)}
.prog{flex:1;display:flex;align-items:center;gap:10px;min-width:0}
.prog .track{flex:1;height:6px;border-radius:3px;background:var(--sunk);overflow:hidden;max-width:360px}
.prog .fill{height:100%;background:var(--accent);width:0;transition:width .3s}
.prog .txt{font:500 12px var(--mono);color:var(--muted);white-space:nowrap}
.nav{display:flex;gap:8px}
.btn{border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:6px 12px;cursor:pointer}
.btn:hover{border-color:var(--muted)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
.btn:disabled{opacity:.4;cursor:default}
nav.rail{overflow:auto;border-right:1px solid var(--line);background:var(--surface);padding-block:8px}
.rail ol{list-style:none;margin:0;padding:0}
.rail li button{display:grid;grid-template-columns:34px 1fr auto;align-items:center;gap:8px;width:100%;text-align:left;border:0;background:none;padding:9px 14px;cursor:pointer;border-left:3px solid transparent}
.rail li button:hover{background:var(--sunk)}
.rail li.cur button{background:var(--accent-soft);border-left-color:var(--accent)}
.rail .num{font:600 15px var(--display);color:var(--muted);font-variant-numeric:tabular-nums}
.rail li.cur .num{color:var(--accent)}
.rail .t{font-size:14px;line-height:1.3}
.rail .done{font:500 11px var(--mono);color:var(--muted)}
.rail li.complete .done{color:var(--ok)}
.stage{position:relative;background:var(--stage);min-height:0;overflow:hidden}
.stage canvas{display:block;width:100%;height:100%;touch-action:none}
.stagebar{position:absolute;left:12px;right:12px;top:12px;display:flex;flex-wrap:wrap;gap:6px;pointer-events:none}
.stagebar > *{pointer-events:auto}
.chip{border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 88%,transparent);border-radius:999px;padding:4px 11px;font-size:12.5px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.stagehint{position:absolute;left:12px;bottom:10px;font:500 11.5px var(--mono);color:var(--muted);pointer-events:none}
.tag{position:absolute;transform:translate(-50%,-120%);font:600 11px var(--mono);padding:2px 6px;border-radius:4px;background:var(--ink);color:var(--bg);white-space:nowrap;pointer-events:none}
.pick{position:absolute;right:12px;bottom:10px;max-width:60%;font-size:12.5px;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.loading{position:absolute;inset:0;display:grid;place-items:center;font:500 13px var(--mono);color:var(--muted)}
aside.panel{overflow:auto;background:var(--surface);border-left:1px solid var(--line);padding-block:20px 40px;padding-inline:22px}
.eyebrow{font:600 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:700 26px/1.15 var(--display);margin:4px 0 8px;text-wrap:balance}
h2{font:600 15px var(--display);letter-spacing:.04em;text-transform:uppercase;margin:24px 0 8px;color:var(--muted)}
.summary{color:var(--ink);margin:0 0 12px;max-width:62ch}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.pill{font-size:12.5px;padding:3px 9px;border-radius:6px;background:var(--sunk);border:1px solid var(--line)}
.pill.time{font-family:var(--mono)}
ol.do{margin:0;padding:0;list-style:none;counter-reset:d;display:grid;gap:10px}
ol.do li{position:relative;padding-left:34px;max-width:64ch}
ol.do li::before{counter-increment:d;content:counter(d);position:absolute;left:0;top:1px;width:24px;height:24px;border-radius:6px;background:var(--sunk);border:1px solid var(--line);display:grid;place-items:center;font:600 12px var(--mono);color:var(--muted)}
ol.do li.warn,ol.do li.tip{padding:9px 12px 9px 34px;border-radius:8px}
ol.do li.warn{background:var(--warn-bg);color:var(--ink)}
ol.do li.warn::before{content:"!";background:var(--warn);color:var(--warn-bg);border:0;counter-increment:none}
ol.do li.tip{background:var(--tip-bg)}
ol.do li.tip::before{content:"i";background:var(--tip);color:var(--tip-bg);border:0;counter-increment:none;font-style:italic}
code{font:13px var(--mono);background:var(--sunk);padding:1px 5px;border-radius:4px;word-break:break-all}
ul.checks{list-style:none;margin:0;padding:0;display:grid;gap:6px}
ul.checks label{display:flex;gap:10px;align-items:flex-start;cursor:pointer}
ul.checks input{width:18px;height:18px;margin-top:2px;accent-color:var(--accent);flex:none}
ul.plain{margin:0;padding-left:18px;display:grid;gap:3px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.diagram{margin-top:8px;border:1px solid var(--line);border-radius:10px;background:var(--sunk);padding:12px;overflow-x:auto}
.diagram svg{display:block;max-width:100%;height:auto}
.diagram .cap{font-size:12.5px;color:var(--muted);margin-top:8px;max-width:62ch}
table.wt{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
table.wt th{font:600 11px var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);text-align:left;padding:4px 6px;border-bottom:1px solid var(--line)}
table.wt td{padding:5px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
table.wt td.m{font-family:var(--mono)}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:6px;border:1px solid var(--line)}
.foot{display:flex;justify-content:space-between;gap:8px;margin-top:26px}
.mode{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.mode button{border:0;background:var(--surface);padding:6px 12px;cursor:pointer;font-weight:500}
.mode button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.rail .grp{font:600 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:14px 14px 4px}
.rail li.w .num{display:grid;place-items:center}
.rail li.w .sw{margin:0;width:14px;height:14px}
dl.ft{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:6px 0 4px;font-size:14px}
dl.ft dt{font:500 12px var(--mono);color:var(--muted);padding-top:2px;text-transform:uppercase;letter-spacing:.05em}
dl.ft dd{margin:0}
@media (max-width:1100px){.app{grid-template-columns:220px minmax(0,1fr) 380px}}
@media (max-width:860px){
  html,body{height:auto}
  .app{display:block;height:auto}
  header.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;flex-wrap:wrap}
  .prog{order:3;flex-basis:100%}
  nav.rail{border:0;border-bottom:1px solid var(--line);overflow-x:auto;padding:6px 16px}
  .rail ol{display:flex;gap:6px}
  .rail li button{grid-template-columns:auto;padding:6px 10px;border:1px solid var(--line);border-radius:8px;white-space:nowrap}
  .rail li.cur button{border-color:var(--accent)}
  .rail .t,.rail .done{display:none}
  .stage{height:56vh;min-height:320px}
  aside.panel{border:0;padding-inline:16px}
  .two{grid-template-columns:1fr}
}
@media (max-width:860px){.rail .grp{display:none}.rail li.w .t{display:inline}.mode{order:2}}
@media (prefers-reduced-motion:reduce){.prog .fill{transition:none}}
</style>

<div class="app">
  <header class="bar">
    <div class="brand">Any<span>%</span> build</div>
    <div class="mode" role="group" aria-label="Guide mode"><button id="mSteps" aria-pressed="true">Build steps</button><button id="mWiring" aria-pressed="false">Wiring</button></div>
    <div class="prog"><div class="track"><div class="fill" id="fill"></div></div><div class="txt" id="progtxt"></div></div>
    <div class="nav"><button class="btn" id="prev">Back</button><button class="btn primary" id="next">Next step</button></div>
  </header>
  <nav class="rail" aria-label="Steps"><ol id="rail"></ol></nav>
  <section class="stage" id="stage">
    <canvas id="cv" aria-label="3D view of the device at this step"></canvas>
    <div class="stagebar">
      <button class="chip" id="replay">Replay</button>
      <button class="chip" data-view="back" id="vback">Back view</button>
      <button class="chip" data-view="front" id="vfront">Front view</button>
      <button class="chip" id="vstep">Frame it</button>
      <button class="chip" id="shell" aria-pressed="false">Hide shell</button>
      <button class="chip" id="wires" aria-pressed="false">Only this step's wires</button>
    </div>
    <div id="tags"></div>
    <div class="stagehint" id="hint">Drag to turn, scroll or pinch to zoom, right-drag to pan. Tap a part or wire to name it.</div>
    <div class="pick" id="pick" hidden></div>
    <div class="loading" id="loading">Loading the 3D parts...</div>
  </section>
  <aside class="panel" id="panel" aria-live="polite"></aside>
</div>

<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/controls/OrbitControls.js"></script>
<script>
const DATA = __DATA__;
const STEPS = DATA.steps;
const $ = s => document.querySelector(s);
const store = {
  get(k){ try { return localStorage.getItem('anypct-build:' + k); } catch (e) { return null; } },
  set(k, v){ try { localStorage.setItem('anypct-build:' + k, v); } catch (e) {} }
};
let cur = Math.min(STEPS.length - 1, Math.max(0, parseInt(store.get('step') || '0', 10) || 0));
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* ---------------- diagrams ---------------- */
function headerSVG(sel) {
  const used = DATA.pintable.used, std = DATA.pintable.std, btn = DATA.buttons;
  const colOf = {};
  for (const [k, b] of Object.entries(btn)) colOf[b.pin] = b.colour;
  const rowH = 17, W = 460, top = 28, cx = [W/2 - 11, W/2 + 11];
  let s = `<svg viewBox="0 0 ${W} ${top + 20*rowH + 24}" role="img" aria-label="Raspberry Pi GPIO header pin map">`;
  s += `<text x="${W/2}" y="14" text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">microSD end (pin 1)</text>`;
  s += `<rect x="${W/2 - 24}" y="${top - 10}" width="48" height="${20*rowH + 4}" rx="4" fill="var(--surface)" stroke="var(--line)"/>`;
  for (let r = 0; r < 20; r++) {
    for (let c = 0; c < 2; c++) {
      const n = r*2 + c + 1, y = top + r*rowH, x = cx[c];
      const u = used[n], kind = u ? u[1] : null;
      let fill = 'var(--sunk)', stroke = 'var(--muted)';
      if (kind === 'btn') { fill = colOf[n]; stroke = 'var(--ink)'; }
      if (kind === 'pwr') { fill = '#EB5757'; stroke = 'var(--ink)'; }
      if (kind === 'gnd') { fill = '#1b1d20'; stroke = 'var(--ink)'; }
      if (n === sel) s += `<circle cx="${x}" cy="${y}" r="9.5" fill="none" stroke="var(--accent)" stroke-width="2.5"/>`;
      s += n === 1 ? `<rect x="${x-5.5}" y="${y-5.5}" width="11" height="11" fill="${fill}" stroke="${stroke}"/>`
                   : `<circle cx="${x}" cy="${y}" r="5.5" fill="${fill}" stroke="${stroke}"/>`;
      const tx = c === 0 ? x - 16 : x + 16, anchor = c === 0 ? 'end' : 'start';
      const label = u ? u[0] : (std[n] || '');
      const weight = u ? 600 : 400, col = u ? 'var(--ink)' : 'var(--muted)';
      s += `<text x="${tx}" y="${y + 4}" text-anchor="${anchor}" font-family="var(--mono)" font-size="10.5" font-weight="${weight}" fill="${col}">${n}  ${esc(label)}</text>`;
    }
  }
  s += `<text x="${W/2}" y="${top + 20*rowH + 14}" text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">USB end (pins 39, 40)</text></svg>`;
  return s + `<div class="cap">Seen from above, components side. Odd pins are the inner row (away from the board edge), even pins the outer row. Pin 1 has a square pad.</div>`;
}
function switchSVG() {
  return `<svg viewBox="0 0 420 170" role="img" aria-label="Tactile switch wiring: signal and ground on diagonal legs">
  <rect x="140" y="35" width="100" height="100" rx="6" fill="var(--surface)" stroke="var(--ink)"/>
  <circle cx="190" cy="85" r="22" fill="var(--sunk)" stroke="var(--muted)"/>
  <text x="190" y="89" text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">plunger</text>
  <g stroke="var(--ink)" stroke-width="3"><line x1="128" y1="50" x2="140" y2="50"/><line x1="128" y1="120" x2="140" y2="120"/><line x1="240" y1="50" x2="252" y2="50"/><line x1="240" y1="120" x2="252" y2="120"/></g>
  <path d="M128 50 C100 50 90 30 40 30" fill="none" stroke="#F2C94C" stroke-width="4"/>
  <text x="36" y="24" font-family="var(--mono)" font-size="12" fill="var(--ink)">signal wire</text>
  <path d="M252 120 C290 120 300 145 380 145" fill="none" stroke="#1b1d20" stroke-width="4"/>
  <text x="300" y="165" font-family="var(--mono)" font-size="12" fill="var(--ink)">ground (daisy chain)</text>
  <line x1="140" y1="50" x2="240" y2="50" stroke="var(--muted)" stroke-dasharray="3 3"/><line x1="140" y1="120" x2="240" y2="120" stroke="var(--muted)" stroke-dasharray="3 3"/>
  <text x="258" y="46" font-family="var(--mono)" font-size="10.5" fill="var(--muted)">joined pair</text>
  <text x="258" y="116" font-family="var(--mono)" font-size="10.5" fill="var(--muted)">joined pair</text></svg>
  <div class="cap">Legs on the same side are joined inside the switch. Diagonal legs are always on different pairs, so signal on one corner and ground on the opposite corner always switches.</div>`;
}
function wiretable() {
  let s = `<table class="wt"><thead><tr><th>Button</th><th>GPIO</th><th>Pin</th><th>Sends</th><th>Cut</th></tr></thead><tbody>`;
  for (const [k, b] of Object.entries(DATA.buttons))
    s += `<tr><td><span class="sw" style="background:${b.colour}"></span>${k}</td><td class="m">${b.gpio}</td><td class="m">${b.pin}</td><td>${esc(b.key)}</td><td class="m">${b.cut} mm</td></tr>`;
  s += `<tr><td><span class="sw" style="background:#1b1d20"></span>Ground</td><td class="m">GND</td><td class="m">39</td><td>daisy chain</td><td class="m">${DATA.gndcut} mm</td></tr></tbody></table>`;
  return s + `<div class="cap">Cut lengths are the 3D route plus 50 mm for stripping and slack. The wire colours are only for the 3D view; use any colour and label the ends.</div>`;
}
function box(x, y, w, h, title, rows, side) {
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="var(--surface)" stroke="var(--ink)"/>`;
  s += `<text x="${x + w/2}" y="${y + 16}" text-anchor="middle" font-family="var(--display)" font-weight="600" font-size="13" fill="var(--ink)">${title}</text>`;
  rows.forEach((r, i) => {
    const ty = y + 36 + i*20, tx = side === 'r' ? x + w - 10 : x + 10;
    s += `<text x="${tx}" y="${ty}" text-anchor="${side === 'r' ? 'end' : 'start'}" font-family="var(--mono)" font-size="11" fill="var(--ink)">${r}</text>`;
  });
  return s;
}
function wire(x1, y1, x2, y2, col) { const m = (x1 + x2)/2; return `<path d="M${x1} ${y1} C${m} ${y1} ${m} ${y2} ${x2} ${y2}" fill="none" stroke="${col}" stroke-width="3.5" stroke-linecap="round"/>`; }
function audioSVG() {
  let s = `<svg viewBox="0 0 560 300" role="img" aria-label="Audio wiring from the Pi jack and header to the PAM8403 and speaker">`;
  s += box(10, 20, 140, 100, 'Pi jack legs', ['L', 'GND', 'R'], 'r');
  s += box(10, 170, 140, 80, 'Pi header', ['pin 4  5V', 'pin 14 GND'], 'r');
  s += box(215, 40, 130, 220, 'PAM8403', ['IN  L', 'IN  G', 'IN  R', '', '', 'PWR +', 'PWR -'], 'l');
  s += `<text x="335" y="${40+36}" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink)">L+</text><text x="335" y="${40+56}" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink)">L-</text><text x="335" y="${40+116}" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink)">R+</text><text x="335" y="${40+136}" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink)">R-</text>`;
  s += box(420, 40, 130, 70, 'Speaker left', ['+  -'], 'l') + box(420, 145, 130, 70, 'Speaker right', ['+  -'], 'l');
  s += wire(150, 56, 215, 76, '#EB5757') + wire(150, 76, 215, 96, '#1b1d20') + wire(150, 96, 215, 116, '#DADADA');
  s += wire(150, 206, 215, 176, '#EB5757') + wire(150, 226, 215, 196, '#1b1d20');
  s += wire(345, 72, 425, 76, '#EB5757') + wire(345, 92, 455, 76, '#6b6f76') + wire(345, 152, 425, 181, '#EB5757') + wire(345, 172, 455, 181, '#6b6f76');
  s += `</svg><div class="cap">Input from the jack: L, G, R. Power from the header: pin 4 to +, pin 14 to -. Outputs are bridged: L+ and L- go only to the left driver, R+ and R- only to the right. Never join an output minus to ground. Cut lengths from the 3D routes: jack wires ${DATA.audiocut['aud-L']} to ${DATA.audiocut['aud-R']} mm, amp power ${DATA.audiocut['amp-5V']} mm.</div>`;
  return s;
}
function powerSVG() {
  let s = `<svg viewBox="0 0 560 190" role="img" aria-label="Power lead from the bank to GPIO pins 2 and 6">`;
  s += box(10, 30, 130, 90, 'Power bank', ['USB-C out', '5 V'], 'l');
  s += `<rect x="150" y="62" width="60" height="18" rx="4" fill="var(--sunk)" stroke="var(--ink)"/><text x="180" y="75" text-anchor="middle" font-family="var(--mono)" font-size="10" fill="var(--ink)">C plug</text>`;
  s += `<text x="265" y="44" text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">cut cable, 15 cm</text>`;
  s += box(380, 30, 170, 110, 'Pi header', ['pin 2  5V  (outer row)', 'pin 6  GND (outer row)'], 'l');
  s += wire(210, 66, 380, 66, '#EB5757') + wire(210, 76, 380, 86, '#1b1d20');
  s += `<text x="280" y="175" text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--ink)">meter, black probe on black, red on red: must read +5.0 V</text></svg>`;
  return s + `<div class="cap">Measure before you solder: with the bank on, the lead must read +5 V from black to red. Most cables use red for 5 V and black for ground, but some do not.</div>`;
}
function magnetsSVG() {
  return `<svg viewBox="0 0 520 170" role="img" aria-label="Magnet polarity: frame marked face out, panel marked face in">
  <rect x="20" y="30" width="200" height="30" fill="var(--surface)" stroke="var(--ink)"/><text x="120" y="22" text-anchor="middle" font-family="var(--display)" font-size="13" font-weight="600" fill="var(--ink)">Rear frame</text>
  <rect x="100" y="60" width="40" height="16" fill="#A9AEB5" stroke="var(--ink)"/><rect x="100" y="72" width="40" height="4" fill="var(--accent)"/>
  <text x="150" y="98" font-family="var(--mono)" font-size="11" fill="var(--ink)">marked face OUT (showing)</text>
  <rect x="300" y="100" width="200" height="30" fill="var(--surface)" stroke="var(--ink)"/><text x="400" y="152" text-anchor="middle" font-family="var(--display)" font-size="13" font-weight="600" fill="var(--ink)">Panel, inner face up</text>
  <rect x="380" y="84" width="40" height="16" fill="#A9AEB5" stroke="var(--ink)"/><rect x="380" y="96" width="40" height="4" fill="var(--accent)"/>
  <text x="300" y="72" font-family="var(--mono)" font-size="11" fill="var(--ink)">marked face IN (into the pocket)</text></svg>
  <div class="cap">Stack every magnet in one column and mark the column's top face: all marked faces are then the same pole. Frame: marked face showing. Panel: marked face into the pocket. The panel then always pulls on.</div>`;
}
const DIAGRAMS = {
  header: ['GPIO pin map', headerSVG], switch: ['Wiring one switch', switchSVG], wiretable: ['Button wires', wiretable],
  audio: ['Audio wiring', audioSVG], power: ['Power lead', powerSVG], magnets: ['Magnet polarity', magnetsSVG]
};

/* ---------------- panel + rail ---------------- */
function checksDone(i) {
  const st = STEPS[i]; let n = 0;
  st.checks.forEach((_, j) => { if (store.get(`${st.id}:${j}`) === '1') n++; });
  return n;
}
function renderStepRail() {
  $('#rail').innerHTML = STEPS.map((st, i) => {
    const n = checksDone(i), all = st.checks.length;
    return `<li class="${i === cur ? 'cur' : ''} ${n === all && all ? 'complete' : ''}"><button data-i="${i}" aria-current="${i === cur ? 'step' : 'false'}"><span class="num">${String(i).padStart(2, '0')}</span><span class="t">${esc(st.title)}</span><span class="done">${n}/${all}</span></button></li>`;
  }).join('');
  let tot = 0, done = 0;
  STEPS.forEach((st, i) => { tot += st.checks.length; done += checksDone(i); });
  $('#fill').style.width = (tot ? 100*done/tot : 0) + '%';
  $('#progtxt').textContent = `Step ${cur} of ${STEPS.length - 1}  ·  ${done}/${tot} checks`;
  const c = $('#rail .cur'); if (c) c.scrollIntoView({block: 'nearest', inline: 'nearest'});
}
function renderStepPanel() {
  const st = STEPS[cur];
  let h = `<div class="eyebrow">Step ${String(cur).padStart(2, '0')}</div><h1>${esc(st.title)}</h1><p class="summary">${st.summary}</p>`;
  h += `<div class="meta"><span class="pill time">${esc(st.time)}</span></div>`;
  if (st.hardware.length || st.tools.length) {
    h += `<div class="two">`;
    if (st.hardware.length) h += `<div><h2>Parts</h2><ul class="plain">${st.hardware.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
    if (st.tools.length) h += `<div><h2>Tools</h2><ul class="plain">${st.tools.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
    h += `</div>`;
  }
  h += `<h2>Do this</h2><ol class="do">${st.do.map(d => `<li class="${d[1] || ''}">${d[0]}</li>`).join('')}</ol>`;
  (st.diagrams || []).forEach(k => { const [t, f] = DIAGRAMS[k]; h += `<h2>${t}</h2><div class="diagram">${f()}</div>`; });
  h += `<h2>Check before moving on</h2><ul class="checks">${st.checks.map((c, j) =>
      `<li><label><input type="checkbox" id="ck-${st.id}-${j}" data-k="${st.id}:${j}" ${store.get(`${st.id}:${j}`) === '1' ? 'checked' : ''}>${esc(c)}</label></li>`).join('')}</ul>`;
  h += `<div class="foot"><button class="btn" id="pprev" ${cur === 0 ? 'disabled' : ''}>Back</button><button class="btn primary" id="pnext" ${cur === STEPS.length - 1 ? 'disabled' : ''}>Next: ${cur < STEPS.length - 1 ? esc(STEPS[cur + 1].title) : 'done'}</button></div>`;
  const p = $('#panel'); p.innerHTML = h; p.scrollTop = 0;
  p.querySelectorAll('input[type=checkbox]').forEach(el => el.addEventListener('change', () => { store.set(el.dataset.k, el.checked ? '1' : '0'); renderRail(); }));
  $('#pprev').onclick = () => go(cur - 1); $('#pnext').onclick = () => go(cur + 1);
  $('#prev').disabled = cur === 0; $('#next').disabled = cur === STEPS.length - 1;
}
const WIRES = DATA.wiring;
let mode = store.get('mode') === 'wiring' ? 'wiring' : 'steps';
let curW = Math.min(WIRES.length - 1, Math.max(0, parseInt(store.get('wire') || '0', 10) || 0));
const idx = () => mode === 'wiring' ? curW : cur;
function renderRail() { if (mode === 'wiring') renderWireRail(); else renderStepRail(); }
function renderPanel() { if (mode === 'wiring') renderWirePanel(); else renderStepPanel(); }
function wireColour(id) { const w = DATA.wires.find(x => x.id === id); return w ? w.colour : null; }
function renderWireRail() {
  let h = '', g = null;
  WIRES.forEach((w, i) => {
    if (w.group !== g) { g = w.group; h += `<li class="grp">${esc(g)}</li>`; }
    const c = w.wire ? wireColour(w.wire) : null;
    h += `<li class="w ${i === curW ? 'cur' : ''}"><button data-i="${i}" aria-current="${i === curW ? 'true' : 'false'}"><span class="num">${c ? `<span class="sw" style="background:${c}"></span>` : ''}</span><span class="t">${esc(w.title)}</span><span class="done">${w.pin ? 'pin ' + w.pin : ''}</span></button></li>`;
  });
  $('#rail').innerHTML = h;
  $('#fill').style.width = (100 * (curW + 1) / WIRES.length) + '%';
  $('#progtxt').textContent = `Connection ${curW + 1} of ${WIRES.length}`;
  const c = $('#rail .cur'); if (c) c.scrollIntoView({block: 'nearest', inline: 'nearest'});
}
function renderWirePanel() {
  const w = WIRES[curW];
  let h = `<div class="eyebrow">Wiring: ${esc(w.group)}</div><h1>${esc(w.title)}</h1>`;
  h += `<dl class="ft"><dt>From</dt><dd>${esc(w.from)}</dd><dt>To</dt><dd>${esc(w.to)}</dd><dt>Carries</dt><dd>${esc(w.sends)}</dd><dt>Wire</dt><dd>${esc(w.cut)}</dd><dt>When</dt><dd>${esc(w.when)}</dd></dl>`;
  h += `<h2>Do this</h2><ol class="do">${w.how.map(x => `<li>${esc(x)}</li>`).join('')}${w.warn ? `<li class="warn">${esc(w.warn)}</li>` : ''}</ol>`;
  h += `<h2>Test it</h2><p class="summary">${esc(w.test)}</p>`;
  (w.diagrams || []).forEach(k => { const [t, f] = DIAGRAMS[k]; h += `<h2>${t}</h2><div class="diagram">${f(w.pin)}</div>`; });
  h += `<div class="foot"><button class="btn" id="pprev" ${curW === 0 ? 'disabled' : ''}>Back</button><button class="btn primary" id="pnext" ${curW === WIRES.length - 1 ? 'disabled' : ''}>Next: ${curW < WIRES.length - 1 ? esc(WIRES[curW + 1].title) : 'done'}</button></div>`;
  const p = $('#panel'); p.innerHTML = h; p.scrollTop = 0;
  $('#pprev').onclick = () => go(curW - 1); $('#pnext').onclick = () => go(curW + 1);
  $('#prev').disabled = curW === 0; $('#next').disabled = curW === WIRES.length - 1;
}
function setMode(m) {
  mode = m; store.set('mode', m);
  $('#mSteps').setAttribute('aria-pressed', m === 'steps'); $('#mWiring').setAttribute('aria-pressed', m === 'wiring');
  $('#next').textContent = m === 'wiring' ? 'Next wire' : 'Next step';
  $('#wires').textContent = m === 'wiring' ? 'Only this wire' : "Only this step's wires";
  renderRail(); renderPanel();
  if (window.scene3d) { if (m === 'wiring') scene3d.setWire(curW, true); else scene3d.setStep(cur, true); }
}
$('#mSteps').onclick = () => setMode('steps'); $('#mWiring').onclick = () => setMode('wiring');
function go(i) {
  if (mode === 'wiring') {
    if (i < 0 || i >= WIRES.length) return;
    curW = i; store.set('wire', String(i));
    renderRail(); renderPanel(); if (window.scene3d) scene3d.setWire(i, true);
    return;
  }
  if (i < 0 || i >= STEPS.length) return;
  cur = i; store.set('step', String(i));
  renderRail(); renderPanel(); if (window.scene3d) scene3d.setStep(i, true);
}
$('#rail').addEventListener('click', e => { const b = e.target.closest('button[data-i]'); if (b) go(+b.dataset.i); });
$('#prev').onclick = () => go(idx() - 1); $('#next').onclick = () => go(idx() + 1);
document.addEventListener('keydown', e => {
  if (e.target.closest('input,textarea')) return;
  if (e.key === 'ArrowRight' && !e.altKey) go(idx() + 1);
  if (e.key === 'ArrowLeft' && !e.altKey) go(idx() - 1);
});
setMode(mode);

/* ---------------- 3D ---------------- */
async function gunzip(b64) {
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const ds = new DecompressionStream('gzip');
  const buf = await new Response(new Blob([bin]).stream().pipeThrough(ds)).arrayBuffer();
  return buf;
}
function parseSTL(buf) {
  const dv = new DataView(buf), n = dv.getUint32(80, true);
  const pos = new Float32Array(n*9), nor = new Float32Array(n*9);
  let o = 84;
  for (let i = 0; i < n; i++, o += 50) {
    const nx = dv.getFloat32(o, true), ny = dv.getFloat32(o + 4, true), nz = dv.getFloat32(o + 8, true);
    for (let v = 0; v < 3; v++) {
      const k = i*9 + v*3;
      pos[k] = dv.getFloat32(o + 12 + v*12, true); pos[k+1] = dv.getFloat32(o + 16 + v*12, true); pos[k+2] = dv.getFloat32(o + 20 + v*12, true);
      nor[k] = nx; nor[k+1] = ny; nor[k+2] = nz;
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  if (!(Math.abs(nor[0]) + Math.abs(nor[1]) + Math.abs(nor[2]))) g.computeVertexNormals();
  return g;
}
function labelPoint(name) {
  const L = DATA.labels, P = DATA.pins;
  if (L[name]) return L[name];
  if (name === 'GPIO header') { const p = P['21']; return [p[0], p[1], p[2] + 3]; }
  if (name === 'Pin 1') { const p = P['1']; return [p[0], p[1], p[2] + 2]; }
  if (name === 'Audio jack legs') return [11, 87.6, 26];
  if (name === 'PAM8403') return [187.7, 97, 38];
  if (name === 'Power lead') return [66, 64, 31];
  if (name === 'Speaker lead') return [100, 36, 31];
  return null;
}

(async function init3d() {
  if (typeof THREE === 'undefined') { $('#loading').textContent = 'The 3D view needs an internet connection to load three.js.'; return; }
  const cv = $('#cv'), stage = $('#stage');
  const renderer = new THREE.WebGLRenderer({canvas: cv, antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(34, 1, 1, 5000);
  const controls = new THREE.OrbitControls(cam, cv);
  controls.enableDamping = true; controls.dampingFactor = 0.12;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x6d737a, 1.05));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.85); d1.position.set(160, 120, 300); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.55); d2.position.set(-80, -60, -260); scene.add(d2);
  function setBg() { scene.background = new THREE.Color(css('--stage') || '#d8dde2'); }
  setBg();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', setBg);
  new MutationObserver(setBg).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});

  const parts = [];
  for (const p of DATA.parts) {
    const geo = parseSTL(await gunzip(p.blob));
    const translucent = p.alpha < 1;
    const mat = new THREE.MeshStandardMaterial({color: p.colour, roughness: 0.62, metalness: p.colour === '#B8BCC2' || p.colour === '#C9A24A' || p.colour === '#A9AEB5' ? 0.45 : 0.05,
      transparent: translucent, opacity: translucent ? p.alpha : 1, depthWrite: !translucent, side: translucent ? THREE.DoubleSide : THREE.FrontSide,
      emissive: new THREE.Color(css('--accent') || '#D9481F'), emissiveIntensity: 0});
    const mesh = new THREE.Mesh(geo, mat);
    mesh.renderOrder = translucent ? 2 : 0;
    mesh.userData = {name: p.name, label: p.label, step: p.step, dir: p.dir, dist: p.dist, shell: p.name === 'asm_front_shell'};
    scene.add(mesh); parts.push(mesh);
  }
  const wires = [], wireById = {};
  for (const w of DATA.wires) {
    const path = new THREE.CurvePath();
    for (let i = 0; i < w.pts.length - 1; i++) path.add(new THREE.LineCurve3(new THREE.Vector3(...w.pts[i]), new THREE.Vector3(...w.pts[i+1])));
    const seg = Math.max(8, w.pts.length * 6);
    const geo = new THREE.TubeGeometry(path, seg, 0.55, 6, false);
    const mat = new THREE.MeshStandardMaterial({color: w.colour, roughness: 0.5, transparent: true, opacity: 1, emissive: new THREE.Color(w.colour), emissiveIntensity: 0.12});
    const m = new THREE.Mesh(geo, mat);
    m.userData = {label: w.label, step: w.step, group: w.group, cut: w.cut, wire: true};
    scene.add(m); wires.push(m); wireById[w.id] = m;
  }
  $('#loading').remove();

  let hideShell = false, onlyStep = false, anim = null, camTween = null;
  const tags = $('#tags');
  function viewFor(st) { return st.view; }
  function fitPos(v) {
    // keep the view's direction, back off far enough that 230 x 150 mm fits at this aspect
    const t = new THREE.Vector3(...v.target), dir = new THREE.Vector3(...v.pos).sub(t).normalize();
    const k = 2*Math.tan(THREE.MathUtils.degToRad(cam.fov/2));
    const d = Math.max((v.h || 150)/k, (v.w || 230)/(k*Math.max(0.3, cam.aspect)));
    return t.clone().add(dir.multiplyScalar(d));
  }
  function tweenCam(v, instant) {
    const from = {p: cam.position.clone(), t: controls.target.clone()};
    const to = {p: fitPos(v), t: new THREE.Vector3(...v.target)};
    if (instant || matchMedia('(prefers-reduced-motion: reduce)').matches) { cam.position.copy(to.p); controls.target.copy(to.t); controls.update(); return; }
    camTween = {from, to, t0: performance.now(), dur: 700};
  }
  const HIDE_W = new Set(['asm_rear_frame', 'asm_magnets_frame', 'asm_screws_frame', 'asm_panel_world_body',
    'asm_panel_world_logo', 'asm_magnets_panel', 'asm_bank', 'asm_bay_tray']);
  const mk = [0, 1].map(() => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(1.7, 18, 12), new THREE.MeshBasicMaterial({color: css('--accent') || '#D9481F'}));
    m.visible = false; scene.add(m); return m;
  });
  function addTag(text, p) {
    const d = document.createElement('div'); d.className = 'tag'; d.textContent = text; d.dataset.p = JSON.stringify(p); tags.appendChild(d);
  }
  function fitBox(box) {
    const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
    return {pos: [c.x, c.y - 90, c.z + 220], target: [c.x, c.y, c.z], w: Math.max(70, s.x + 40), h: Math.max(50, s.y + 40)};
  }
  function setWire(i, move) {
    const it = DATA.wiring[i]; anim = null;
    for (const m of parts) {
      const u = m.userData;
      m.visible = !HIDE_W.has(u.name) && !(u.shell && hideShell);
      m.position.set(0, 0, 0); m.material.emissiveIntensity = 0;
    }
    const sel = it.wire ? wireById[it.wire] : null;
    for (const w of wires) {
      w.visible = !onlyStep || w === sel;
      w.material.opacity = w === sel ? 1 : 0.13;
      w.material.emissiveIntensity = w === sel ? 0.55 : 0.05;
    }
    tags.innerHTML = ''; $('#pick').hidden = true;
    mk.forEach(m => { m.visible = false; });
    let view = {pos: [101, -70, 290], target: [101, 62, 18]};
    if (sel) {
      const pts = DATA.wires.find(x => x.id === it.wire).pts;
      const ends = [pts[0], pts[pts.length - 1]], names = [it.fromTag, it.toTag];
      ends.forEach((p, k) => { mk[k].position.set(...p); mk[k].visible = true; if (names[k]) addTag(names[k], [p[0], p[1], p[2] + 3]); });
      const box = new THREE.Box3(); pts.forEach(p => box.expandByPoint(new THREE.Vector3(...p)));
      view = fitBox(box);
    } else {
      for (const m of parts) if (m.userData.name === 'asm_display' || m.userData.name === 'asm_pi_board') m.material.emissiveIntensity = 0.3;
    }
    if (move) tweenCam(view);
    return view;
  }
  function setStep(i, move) {
    const st = STEPS[i], all = !!st.showAll;
    mk.forEach(m => { m.visible = false; });
    for (const m of parts) {
      const u = m.userData;
      m.visible = (all || u.step <= i) && !(u.shell && hideShell);
      m.position.set(0, 0, 0);
      m.material.emissiveIntensity = 0;
    }
    for (const w of wires) {
      const u = w.userData;
      w.visible = (all || u.step <= i) && (!onlyStep || u.step === i || (st.focus || []).includes(u.group) && u.step <= i);
      const focus = all || (st.focus || []).includes(u.group) || u.step === i;
      w.material.opacity = focus ? 1 : 0.35;
      w.material.emissiveIntensity = 0.12;
    }
    anim = all ? null : {t0: performance.now(), i};
    tags.innerHTML = '';
    (st.labels || []).forEach(n => {
      const p = labelPoint(n); if (!p) return;
      const d = document.createElement('div'); d.className = 'tag'; d.textContent = n; d.dataset.p = JSON.stringify(p); tags.appendChild(d);
    });
    $('#pick').hidden = true;
    if (move) tweenCam(viewFor(st));
  }
  window.scene3d = {setStep, setWire};

  function resize() {
    const w = stage.clientWidth, h = stage.clientHeight;
    renderer.setSize(w, h, false); cam.aspect = w / Math.max(1, h); cam.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage); resize();

  const ease = t => t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3)/2;
  const v = new THREE.Vector3();
  function frame(now) {
    if (camTween) {
      const k = Math.min(1, (now - camTween.t0) / camTween.dur), e = ease(k);
      cam.position.lerpVectors(camTween.from.p, camTween.to.p, e); controls.target.lerpVectors(camTween.from.t, camTween.to.t, e);
      if (k >= 1) camTween = null;
    }
    if (anim) {
      const k = Math.min(1, (now - anim.t0) / 1400), e = ease(k), pulse = 0.18 + 0.12*Math.sin(now/260);
      for (const m of parts) {
        const u = m.userData;
        if (u.step !== anim.i || !u.dir) continue;
        const off = (1 - e) * u.dist * 1.6;
        m.position.set(-u.dir[0]*off, -u.dir[1]*off, -u.dir[2]*off);
        m.material.emissiveIntensity = k < 1 ? 0.28 : pulse;
      }
    }
    controls.update();
    renderer.render(scene, cam);
    const w = stage.clientWidth, h = stage.clientHeight;
    for (const t of tags.children) {
      v.set(...JSON.parse(t.dataset.p)).project(cam);
      t.style.left = ((v.x + 1)/2*w) + 'px'; t.style.top = ((1 - v.y)/2*h) + 'px'; t.hidden = v.z > 1;
    }
    requestAnimationFrame(frame);
  }
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  let down = null;
  cv.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  cv.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const r = cv.getBoundingClientRect();
    ptr.set((e.clientX - r.left)/r.width*2 - 1, -(e.clientY - r.top)/r.height*2 + 1);
    ray.setFromCamera(ptr, cam);
    const hits = ray.intersectObjects([...wires, ...parts].filter(m => m.visible && !m.userData.shell));
    const pk = $('#pick');
    if (hits.length) { const u = hits[0].object.userData; pk.textContent = u.label + (u.cut ? `  ·  cut ${u.cut} mm` : ''); pk.hidden = false; }
    else pk.hidden = true;
  });
  $('#replay').onclick = () => { if (mode === 'wiring') setWire(curW, true); else setStep(cur, false); };
  $('#vback').onclick = () => tweenCam({pos: [101, -70, 290], target: [101, 62, 18]});
  $('#vfront').onclick = () => tweenCam({pos: [101, -60, -250], target: [101, 62, 20]});
  $('#vstep').onclick = () => { if (mode === 'wiring') setWire(curW, true); else tweenCam(viewFor(STEPS[cur])); };
  $('#shell').onclick = e => { hideShell = !hideShell; e.currentTarget.setAttribute('aria-pressed', hideShell); if (mode === 'wiring') setWire(curW, false); else setStep(cur, false); };
  $('#wires').onclick = e => { onlyStep = !onlyStep; e.currentTarget.setAttribute('aria-pressed', onlyStep); if (mode === 'wiring') setWire(curW, false); else setStep(cur, false); };
  tweenCam(mode === 'wiring' ? setWire(curW, false) : (setStep(cur, false), viewFor(STEPS[cur])), true);
  requestAnimationFrame(frame);
})().catch(err => { const l = $('#loading'); if (l) l.textContent = '3D view failed to load: ' + err.message; });
</script>
"""

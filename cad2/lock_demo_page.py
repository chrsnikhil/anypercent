"""Page template for make_lock_demo.py."""

PAGE = r"""<meta charset="utf-8">
<title>Any% Switch Lock</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --bg:#E9ECEF; --surface:#FFFFFF; --sunk:#F3F5F7; --ink:#15171B; --muted:#59616A; --line:#D3D8DE;
  --accent:#D9481F; --accent-soft:#FBE3DA; --accent-ink:#FFFFFF; --stage:#D8DDE2;
  --rib:#1B9CC8; --hold:#2E9E62; --push:#C99A06; --fail:#D64545; --void:#F3F5F7;
  --plate:#EE8A4F; --capA:#E4572E; --face:#6F757C; --sw:#2E3035;
  --display:"Chakra Petch", "Segoe UI", system-ui, sans-serif;
  --body:"IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, Consolas, monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0E1012; --surface:#171A1E; --sunk:#1D2126; --ink:#E8EBEE; --muted:#9BA3AC; --line:#2A3037;
  --accent:#F0663D; --accent-soft:#3A1F16; --accent-ink:#17120F; --stage:#121518;
  --rib:#4CC3EE; --hold:#5FD08F; --push:#F2C94C; --fail:#FF6B6B; --void:#1D2126;
  --plate:#EE8A4F; --capA:#F0663D; --face:#8A9097; --sw:#A7ADB4; color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0E1012; --surface:#171A1E; --sunk:#1D2126; --ink:#E8EBEE; --muted:#9BA3AC; --line:#2A3037;
  --accent:#F0663D; --accent-soft:#3A1F16; --accent-ink:#17120F; --stage:#121518;
  --rib:#4CC3EE; --hold:#5FD08F; --push:#F2C94C; --fail:#FF6B6B; --void:#1D2126;
  --plate:#EE8A4F; --capA:#F0663D; --face:#8A9097; --sw:#A7ADB4; color-scheme:dark;}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--body)}
*{box-sizing:border-box}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{display:grid;grid-template-columns:minmax(0,1fr) 460px;grid-template-rows:auto minmax(0,1fr);height:100%}
header{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--surface)}
.brand{font:700 20px/1 var(--display)}
.brand span{color:var(--accent)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{border:0;background:var(--surface);padding:6px 12px;cursor:pointer;font-weight:500}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.hint{font:500 12px var(--mono);color:var(--muted)}
.stage{position:relative;background:var(--stage);min-height:0;overflow:hidden}
.stage canvas{display:block;width:100%;height:100%;touch-action:none}
.chips{position:absolute;left:12px;right:12px;top:12px;display:flex;flex-wrap:wrap;gap:6px;pointer-events:none}
.chips > *{pointer-events:auto}
.chip{border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 88%,transparent);border-radius:999px;padding:4px 11px;font-size:12.5px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.tag{position:absolute;transform:translate(-50%,-130%);font:600 11px var(--mono);padding:2px 6px;border-radius:4px;background:var(--ink);color:var(--bg);white-space:nowrap;pointer-events:none}
.tag.rib{background:var(--rib);color:#fff}.tag.hold{background:var(--hold);color:#fff}.tag.push{background:var(--push);color:#111}.tag.fail{background:var(--fail);color:#fff}
.click{position:absolute;right:16px;top:56px;font:700 22px var(--display);color:var(--hold);opacity:0;transition:opacity .08s}
.timeline{position:absolute;left:12px;right:12px;bottom:10px;background:color-mix(in srgb,var(--surface) 90%,transparent);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
.tl-row{display:flex;align-items:center;gap:10px}
.tl-row input[type=range]{flex:1;accent-color:var(--accent)}
.ticks{display:grid;grid-template-columns:repeat(7,1fr);font:500 10.5px var(--mono);color:var(--muted);margin-top:2px;margin-left:44px}
.ticks span{border-left:1px solid var(--line);padding-left:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.play{width:34px;height:30px;border-radius:8px;border:1px solid var(--line);background:var(--accent);color:var(--accent-ink);cursor:pointer;font-weight:700}
.loading{position:absolute;inset:0;display:grid;place-items:center;font:500 13px var(--mono);color:var(--muted)}
aside{overflow:auto;background:var(--surface);border-left:1px solid var(--line);padding-block:16px 32px;padding-inline:20px}
ol.chap{list-style:none;margin:0 0 14px;padding:0;display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
ol.chap button{width:100%;border:1px solid var(--line);background:var(--sunk);border-radius:6px;padding:5px 0;font:600 13px var(--display);cursor:pointer}
ol.chap li.cur button{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.eyebrow{font:600 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:700 24px/1.15 var(--display);margin:2px 0 8px;text-wrap:balance}
h2{font:600 13px var(--display);letter-spacing:.06em;text-transform:uppercase;margin:18px 0 6px;color:var(--muted)}
p.body{margin:0;max-width:62ch}
dl.read{display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;margin:0}
dl.read div{background:var(--sunk);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
dl.read dt{font:500 11px var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
dl.read dd{margin:0;font:600 16px var(--mono);font-variant-numeric:tabular-nums}
.fig{border:1px solid var(--line);border-radius:10px;background:var(--sunk);padding:10px;overflow-x:auto}
.fig svg{display:block;max-width:100%;height:auto}
.legend{display:flex;flex-wrap:wrap;gap:10px;font-size:12.5px;color:var(--muted);margin-top:6px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
@media (max-width:980px){
  html,body{height:auto}
  .app{display:block;height:auto}
  .stage{height:62vh;min-height:360px}
  aside{border:0;padding-inline:16px}
  .ticks{display:none}
}
</style>

<div class="app">
  <header>
    <div class="brand">Any<span>%</span> switch lock</div>
    <div class="seg" role="group" aria-label="Switch plate"><button id="mRib" aria-pressed="true">Ribbed plate (new)</button><button id="mOld" aria-pressed="false">Plain pocket (old)</button></div>
    <div class="hint">Real CAD parts, device millimetres</div>
  </header>
  <section class="stage" id="stage">
    <canvas id="cv" aria-label="3D view of the switch, plate and button"></canvas>
    <div class="chips">
      <button class="chip" id="cut" aria-pressed="true">Cutaway</button>
      <button class="chip" id="ex" aria-pressed="true">Travel x6</button>
      <button class="chip" id="shellBtn" aria-pressed="false">Hide shell</button>
      <button class="chip" id="reframe">Reframe</button>
    </div>
    <div id="tags"></div>
    <div class="click" id="click">click</div>
    <div class="timeline">
      <div class="tl-row"><button class="play" id="play" aria-label="Play">&#9654;</button><input type="range" id="tl" min="0" max="7" step="0.001" value="0" aria-label="Timeline"></div>
      <div class="ticks" id="ticks"></div>
    </div>
    <div class="loading" id="loading">Loading parts...</div>
  </section>
  <aside>
    <ol class="chap" id="chap"></ol>
    <div class="eyebrow" id="eyebrow"></div>
    <h1 id="title"></h1>
    <p class="body" id="text"></p>
    <h2>Live numbers (real size)</h2>
    <dl class="read" id="read"></dl>
    <h2>Section through the centre of A, to scale</h2>
    <div class="fig" id="sec"></div>
    <div class="legend"><span><i style="background:var(--face)"></i>face</span><span><i style="background:var(--capA)"></i>cap</span><span><i style="background:var(--plate)"></i>plate</span><span><i style="background:var(--sw)"></i>switch</span><span><i style="background:var(--rib)"></i>ribs</span></div>
    <h2>The pocket from the back, to scale</h2>
    <div class="fig" id="top"></div>
  </aside>
</div>

<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/controls/OrbitControls.js"></script>
<script>
const DATA = __DATA__, D = DATA.dim, A = DATA.caps.a;
const $ = s => document.querySelector(s);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const E = t => t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3)/2;
const RIB_TOP = D.z_plate_r - D.sw_mouth;           // 8.65
const TRAVEL = D.cap_gap + D.sw_travel;             // 0.40 cap travel to the click
const OLD_STOP = D.cap_float;                        // 0.80 flange meets the plate
const CH = [
  {t: 'The pocket', short: 'Pocket', cut: true,
   rib: 'Each switch sits in a 6.30 mm square pocket, 3.5 mm deep, open to the back of the plate. Four ribs (blue), 0.30 mm tall and 1.2 mm wide, stand on the two solid walls; the other two walls are slots for the legs. The ribs stop 0.5 mm below the mouth and the mouth is chamfered, so a switch starts straight.',
   old: 'The original pocket: a plain 6.30 mm square for a 6.00 mm switch, 0.15 mm clearance each side as drawn. Your printer made it a little bigger still, so nothing touches the switch.'},
  {t: 'Push the switch in', short: 'Insert', cut: true,
   rib: 'Plunger first, legs up into the slots, pushed with a thumb. The rib tips are 5.70 mm apart and the switch body is 6.00 mm, so each rib is crushed by 0.15 mm as the body slides past. It stops when the body bottoms on the shoulder at 5.65 mm; the plunger pokes through the 4.2 mm bore toward the cap.',
   old: 'It drops straight in and bottoms on the shoulder. Nothing touches the walls on the way, so nothing will hold it there.'},
  {t: 'Why it stays put', short: 'Hold', cut: true,
   rib: 'A press pushes the plunger toward the back of the device, and so the whole switch toward the open mouth of the pocket (yellow). The four crushed ribs squeeze the body, and their friction (green) holds it against that push: about 1.6 N for a typical 6 x 6 switch. No glue.',
   old: 'The same push meets nothing, so the switch slides out of the open mouth (red). That is why glue seemed necessary, and superglue then wicks into the switch and jams it.'},
  {t: 'Caps into their rings', short: 'Caps', cut: false,
   rib: 'Shell face-down on the bench. Each cap drops in front first. Its 9 mm stem passes through the 9.4 mm hole in the face; the 12 mm flange behind it cannot, so the cap cannot fall out of the front. The caps just rest in their rings.',
   old: null},
  {t: 'Plate over the caps', short: 'Plate', cut: false,
   rib: 'The plate goes on plunger side down with its switches already in. Its two sleeves slide over the two shell posts, which lines every plunger up with its cap. Between the cap flange (back face at 4.0 mm) and the plate (front at 4.8 mm) there is 0.8 mm of float: more than the switch travel, so the switch is always what stops the button, never the plate.',
   old: null},
  {t: 'Screw it down', short: 'Screws', cut: false,
   rib: 'Two M3 x 8 screws go through the sleeve tops into the posts and cut their own thread. Snug, not tight. The cap is now trapped between the face and the plate, with the plunger tip 0.15 mm behind the cap.',
   old: null},
  {t: 'Press it', short: 'Press', cut: true,
   rib: 'The cap moves 0.15 mm before it meets the plunger (designed lost motion), then 0.25 mm more to the click. The ribs keep the switch still, so the plunger does the moving, every time. With Travel x6 on, the movement is drawn six times bigger.',
   old: 'Press 1: the cap reaches the plunger, but the loose switch slides back instead of clicking, and stays there. Presses 2 and 3: the cap flange hits the plate after 0.8 mm, before it reaches the plunger again. The button is dead until you push the switch back in.'},
];
let mode = 'rib', t = 0, playing = false, cutOn = true, exOn = true, hideShell = false, lastK = -1;

/* ---------- panel ---------- */
$('#chap').innerHTML = CH.map((c, i) => `<li><button data-k="${i}" aria-label="${c.t}">${i + 1}</button></li>`).join('');
$('#ticks').innerHTML = CH.map((c, i) => `<span>${i + 1} ${c.short}</span>`).join('');
$('#chap').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { t = +b.dataset.k; playing = true; syncPlay(); } });
function panelText(k) {
  const c = CH[k];
  $('#eyebrow').textContent = `Step ${k + 1} of 7`;
  $('#title').textContent = c.t;
  $('#text').textContent = (mode === 'old' && c.old) ? c.old : c.rib;
  document.querySelectorAll('#chap li').forEach((li, i) => li.classList.toggle('cur', i === k));
}
function setMode(m) {
  mode = m;
  $('#mRib').setAttribute('aria-pressed', m === 'rib'); $('#mOld').setAttribute('aria-pressed', m === 'old');
  panelText(Math.min(6, Math.floor(t)));
}
$('#mRib').onclick = () => setMode('rib'); $('#mOld').onclick = () => setMode('old');

/* ---------- state for time t ---------- */
function state(t) {
  const k = Math.min(6, Math.floor(t)), u = t - k, ex = exOn ? 6 : 1, S = {k, u, ex};
  S.plateLift = t < 3 ? 0 : t < 4 ? 22*E(clamp((t - 3)/0.35)) : t < 5 ? 22*(1 - E(clamp((t - 4)/0.8))) : 0;
  S.shell = t >= 3 ? clamp((t - 3)/0.3) : 0;
  S.caps = {};
  ['a', 'x', 'y', 'b'].forEach((c, j) => { S.caps[c] = t < 3 ? null : t < 4 ? 18*(1 - E(clamp((t - 3 - 0.35 - j*0.1)/0.35))) : 0; });
  S.sw = {};
  S.sw.a = t < 1 ? 18 : t < 2 ? 18*(1 - E(clamp(u/0.7))) : 0;
  ['x', 'y', 'b'].forEach((c, j) => { S.sw[c] = t < 1.62 ? null : t < 2 ? 12*(1 - E(clamp((u - 0.62 - j*0.08)/0.14))) : 0; });
  S.screw = t < 5 ? null : t < 6 ? 14*(1 - E(clamp((t - 5)/0.8))) : 0;
  S.cap = 0; S.plunger = 0; S.click = false; S.presses = 0; S.pressing = 0;
  if (k === 6) {
    const c = Math.min(2, Math.floor(u*3)), f = u*3 - c;
    const p = f < 0.35 ? E(f/0.35) : f < 0.6 ? 1 : f < 0.9 ? 1 - E((f - 0.6)/0.3) : 0;
    S.presses = c + (f >= 0.35 ? 1 : 0); S.pressing = p;
    if (mode === 'rib') {
      S.cap = p*TRAVEL;
      S.plunger = Math.max(0, S.cap - D.cap_gap);
      S.click = p > 0.97;
    } else {
      S.cap = p*OLD_STOP;
      const walked = OLD_STOP - D.cap_gap;                    // 0.65: pushed back on press 1, stays
      S.swWalk = c === 0 ? Math.max(0, S.cap - D.cap_gap) : walked;
      S.plunger = 0;
    }
  }
  const crushOf = off => mode === 'rib' ? clamp((RIB_TOP - (D.z_sw_floor + off))/(RIB_TOP - D.z_sw_floor)) : 0;
  S.crushA = crushOf(S.sw.a + (S.swWalk || 0));
  S.crush = c => S.sw[c] == null ? 0 : crushOf(S.sw[c]);
  return S;
}

/* ---------- 2D figures ---------- */
function secSVG(S) {
  const sc = 11, W = 470, H = 250, ox = 150, base = 196;
  const X = y => ox + y*sc, Y = z => base - z*sc;
  const R = (y0, y1, z0, z1, fill, extra = '') => `<rect x="${X(Math.min(y0, y1))}" y="${Y(Math.max(z0, z1))}" width="${Math.abs(y1 - y0)*sc}" height="${Math.abs(z1 - z0)*sc}" fill="${fill}" ${extra}/>`;
  const cap = S.cap, pl = S.plunger, sw = (S.sw.a || 0) + (S.swWalk || 0), lift = S.plateLift;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Section through button A">`;
  // face with its hole, and the ring walls
  s += R(-13, -4.7, 0, D.t_face, 'var(--face)') + R(4.7, 13, 0, D.t_face, 'var(--face)');
  if (S.shell > 0 || S.k < 3) {
    s += R(-8.0, -6.4, D.t_face, 4.6, 'var(--face)', 'opacity=".75"') + R(6.4, 8.0, D.t_face, 4.6, 'var(--face)', 'opacity=".75"');
  }
  // cap
  if (S.k >= 3) {
    const cz = (S.caps.a || 0) + cap;
    s += R(-D.face_cap_d/2, D.face_cap_d/2, -D.cap_proud + cz, D.t_face + cz, 'var(--capA)');
    s += R(-D.flange_d/2, D.flange_d/2, D.t_face + cz, D.z_cap_back + cz, 'var(--capA)');
  }
  // plate with its pocket, mouth chamfer and plunger bore
  const pz = lift;
  s += R(-11.5, 11.5, D.z_plate_f + pz, D.z_plate_r + pz, 'var(--plate)');
  const p = D.sw_pocket/2, m = p + D.sw_mouth, b = D.sw_lead_clr/2;
  s += `<polygon fill="var(--void)" points="${[[-b, D.z_plate_f - .01], [b, D.z_plate_f - .01], [b, D.z_sw_floor], [p, D.z_sw_floor], [p, D.z_plate_r - D.sw_mouth], [m, D.z_plate_r + .01], [-m, D.z_plate_r + .01], [-p, D.z_plate_r - D.sw_mouth], [-p, D.z_sw_floor], [-b, D.z_sw_floor]].map(q => `${X(q[0])},${Y(q[1] + pz)}`).join(' ')}"/>`;
  // ribs, just behind this plane (at +-1.6 mm)
  if (mode === 'rib') {
    const w = D.sw_rib*(1 - 0.5*S.crushA);
    s += R(-p, -p + w, D.z_sw_floor + pz, RIB_TOP + pz, 'var(--rib)') + R(p - w, p, D.z_sw_floor + pz, RIB_TOP + pz, 'var(--rib)');
  }
  // switch: body, plunger, legs
  if (S.sw.a != null) {
    const z0 = D.z_sw_floor + sw + pz, z1 = D.z_plate_r + sw + pz;
    s += R(-3, 3, z0, z1, 'var(--sw)');
    s += R(-D.sw_plunger_d/2, D.sw_plunger_d/2, D.z_sw_tip + sw + pl + pz, z0, 'var(--sw)');
    s += `<g stroke="var(--sw)" stroke-width="2" opacity=".5"><line x1="${X(-2.2)}" y1="${Y(z1)}" x2="${X(-2.2)}" y2="${Y(z1 + 3.5)}"/><line x1="${X(2.2)}" y1="${Y(z1)}" x2="${X(2.2)}" y2="${Y(z1 + 3.5)}"/></g>`;
  }
  // depth scale on the right
  const lv = [[-D.cap_proud, 'cap front'], [0, 'face'], [D.t_face, 'face back'], [D.z_cap_back, 'flange back'], [D.z_sw_tip, 'plunger tip'],
              [D.z_plate_f, 'plate front'], [D.z_sw_floor, 'shoulder'], [D.z_plate_r, 'seat / plate back']];
  // labels spread so none overlap (at least 11 px apart), each with a leader to its true depth
  let prev = -1e9;
  lv.slice().sort((a, b) => b[0] - a[0]).forEach(([z, name]) => {
    const y = Y(z), ty = Math.max(y + 3.5, prev + 11); prev = ty;
    s += `<polyline points="${X(12.4)},${y} ${X(13.4)},${y} ${X(14.2)},${ty - 3.5}" fill="none" stroke="var(--muted)"/>`;
    s += `<text x="${X(14.5)}" y="${ty}" font-family="var(--mono)" font-size="9.5" fill="var(--ink)">${z.toFixed(2)} ${name}</text>`;
  });
  s += `<text x="8" y="16" font-family="var(--mono)" font-size="10" fill="var(--muted)">back of device</text><text x="8" y="${H - 8}" font-family="var(--mono)" font-size="10" fill="var(--muted)">front (player)</text>`;
  s += `<line x1="${X(-12)}" y1="${H - 26}" x2="${X(-7)}" y2="${H - 26}" stroke="var(--ink)" stroke-width="2"/><text x="${X(-12)}" y="${H - 30}" font-family="var(--mono)" font-size="9.5" fill="var(--ink)">5 mm</text>`;
  return s + '</svg>';
}
function topSVG(S) {
  const sc = 15, W = 470, H = 200, cx = 120, cy = 100;
  const X = x => cx + x*sc, Y = y => cy - y*sc, p = D.sw_pocket/2;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="The pocket seen from the back">`;
  s += `<rect x="${X(-p - 2)}" y="${Y(p + 2)}" width="${(2*p + 4)*sc}" height="${(2*p + 4)*sc}" fill="var(--plate)"/>`;
  s += `<rect x="${X(-p)}" y="${Y(p)}" width="${2*p*sc}" height="${2*p*sc}" fill="var(--void)"/>`;
  s += `<rect x="${X(-p - 2.4)}" y="${Y(2.8)}" width="${2.4*sc}" height="${5.6*sc}" fill="var(--void)"/><rect x="${X(p)}" y="${Y(2.8)}" width="${2.4*sc}" height="${5.6*sc}" fill="var(--void)"/>`;
  if (mode === 'rib') {
    const h = D.sw_rib*(1 - 0.5*S.crushA);
    for (const sy of [-1, 1]) for (const sx of [-1, 1]) {
      const bx = sx*D.rib_x, wy = sy*p;
      s += `<polygon fill="var(--rib)" points="${X(bx - D.sw_rib_w/2)},${Y(wy)} ${X(bx + D.sw_rib_w/2)},${Y(wy)} ${X(bx)},${Y(wy - sy*h)}"/>`;
    }
  }
  const inPocket = S.sw.a != null && (S.sw.a + (S.swWalk || 0)) < 3.5;
  if (S.sw.a != null) s += `<rect x="${X(-3)}" y="${Y(3)}" width="${6*sc}" height="${6*sc}" fill="var(--sw)" opacity="${inPocket ? 0.85 : 0.25}"/>`;
  s += `<text x="${X(p + 3.2)}" y="${Y(2.2)}" font-family="var(--mono)" font-size="11" fill="var(--ink)">pocket 6.30</text>`;
  s += `<text x="${X(p + 3.2)}" y="${Y(0.8)}" font-family="var(--mono)" font-size="11" fill="var(--ink)">switch 6.00</text>`;
  if (mode === 'rib') {
    s += `<text x="${X(p + 3.2)}" y="${Y(-0.6)}" font-family="var(--mono)" font-size="11" fill="var(--rib)">rib tips 5.70 apart</text>`;
    s += `<text x="${X(p + 3.2)}" y="${Y(-2.0)}" font-family="var(--mono)" font-size="11" fill="var(--rib)">each rib crushed ${(0.15*S.crushA).toFixed(2)}</text>`;
  } else {
    s += `<text x="${X(p + 3.2)}" y="${Y(-0.6)}" font-family="var(--mono)" font-size="11" fill="var(--fail)">0.15 clear each side</text>`;
    s += `<text x="${X(p + 3.2)}" y="${Y(-2.0)}" font-family="var(--mono)" font-size="11" fill="var(--fail)">nothing grips the switch</text>`;
  }
  s += `<text x="${X(-p - 2.3)}" y="${Y(-p - 1.2)}" font-family="var(--mono)" font-size="10" fill="var(--muted)">leg slot</text><text x="${X(p - 0.2)}" y="${Y(-p - 1.2)}" font-family="var(--mono)" font-size="10" fill="var(--muted)">leg slot</text>`;
  return s + '</svg>';
}
function readouts(S) {
  const sw = (S.sw.a == null ? null : S.sw.a + (S.swWalk || 0));
  const rows = [
    ['Rib crush, each', mode === 'rib' ? (0.15*S.crushA).toFixed(2) + ' mm' : 'no ribs'],
    ['Switch behind its seat', sw == null ? '-' : sw.toFixed(2) + ' mm'],
    ['Cap travel', (S.cap).toFixed(2) + ' mm'],
    ['Click', S.k < 6 ? '-' : (mode === 'rib' ? (S.click ? 'yes' : 'not yet') : 'never')],
  ];
  $('#read').innerHTML = rows.map(r => `<div><dt>${r[0]}</dt><dd>${r[1]}</dd></div>`).join('');
}

/* ---------- 3D ---------- */
async function gunzip(b64) {
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return new Response(new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
}
function parseSTL(buf) {
  const dv = new DataView(buf), n = dv.getUint32(80, true), pos = new Float32Array(n*9);
  for (let i = 0, o = 84; i < n; i++, o += 50)
    for (let v = 0; v < 9; v++) pos[i*9 + v] = dv.getFloat32(o + 12 + v*4, true);
  return pos;
}
function geo(pos) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.computeVertexNormals(); return g; }

(async function () {
  if (typeof THREE === 'undefined') { $('#loading').textContent = 'The 3D view needs an internet connection to load three.js.'; return; }
  const stage = $('#stage'), cv = $('#cv');
  const renderer = new THREE.WebGLRenderer({canvas: cv, antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.localClippingEnabled = true;
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(32, 1, 0.5, 2000); cam.up.set(0, 0, 1);
  const controls = new THREE.OrbitControls(cam, cv); controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x60666e, 1.0));
  const l1 = new THREE.DirectionalLight(0xffffff, 0.9); l1.position.set(80, -60, 120); scene.add(l1);
  const l2 = new THREE.DirectionalLight(0xffffff, 0.45); l2.position.set(-60, 90, -80); scene.add(l2);
  const setBg = () => { scene.background = new THREE.Color(css('--stage')); };
  setBg(); matchMedia('(prefers-color-scheme: dark)').addEventListener('change', setBg);
  new MutationObserver(setBg).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});

  const plane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), A[0] + D.rib_x);   // keep x <= 12.6: the cut passes through two ribs
  const clipMats = [];
  function solid(g, colour, opts = {}) {
    const front = new THREE.MeshStandardMaterial({color: colour, roughness: 0.6, metalness: opts.metal || 0.05,
      transparent: !!opts.alpha, opacity: opts.alpha || 1, depthWrite: !opts.alpha, polygonOffset: !!opts.offset, polygonOffsetFactor: -1, polygonOffsetUnits: -2});
    const back = new THREE.MeshBasicMaterial({color: new THREE.Color(colour).multiplyScalar(0.55), side: THREE.BackSide,
      transparent: !!opts.alpha, opacity: opts.alpha || 1, depthWrite: !opts.alpha});
    clipMats.push(front, back);
    const grp = new THREE.Group();
    grp.add(new THREE.Mesh(g, front), new THREE.Mesh(g, back));
    grp.userData.mats = [front, back];
    return grp;
  }
  const byId = {};
  for (const p of DATA.parts) byId[p.id] = {pos: parseSTL(await gunzip(p.blob)), axis: p.axis};

  const shell = solid(geo(byId.shell.pos), '#555b62', {alpha: 0.5}); scene.add(shell);
  const plateGrp = new THREE.Group(); scene.add(plateGrp);
  plateGrp.add(solid(geo(byId.plate.pos), css('--plate') || '#EE8A4F'));
  const capCol = {a: '#E4572E', b: '#E4572E', x: '#5F646B', y: '#5F646B'};
  const caps = {}, sws = {}, plungers = {};
  for (const c of ['a', 'x', 'y', 'b']) {
    caps[c] = solid(geo(byId['cap_' + c].pos), capCol[c]); scene.add(caps[c]);
    const all = byId['sw_' + c].pos, body = [], plg = [];
    for (let i = 0; i < all.length; i += 9) {
      const tri = all.slice(i, i + 9), front = tri[2] < 5.7 && tri[5] < 5.7 && tri[8] < 5.7;
      (front ? plg : body).push(...tri);
    }
    const g = new THREE.Group();
    g.add(solid(geo(new Float32Array(body)), '#2E3035'));
    plungers[c] = solid(geo(new Float32Array(plg)), '#3a3d42'); g.add(plungers[c]);
    sws[c] = g; plateGrp.add(g);
  }
  // ribs: the exact CAD rib prisms, drawn separately so they can be lit up and crushed
  const ribs = {};
  for (const c of ['a', 'x', 'y', 'b']) {
    const [px, py] = DATA.caps[c]; ribs[c] = [];
    for (const sy of [-1, 1]) for (const sx of [-1, 1]) {
      const sh = new THREE.Shape([new THREE.Vector2(-D.sw_rib_w/2, 0), new THREE.Vector2(D.sw_rib_w/2, 0), new THREE.Vector2(0, -sy*D.sw_rib)]);
      const g = new THREE.ExtrudeGeometry(sh, {depth: RIB_TOP - D.z_sw_floor, bevelEnabled: false});
      const m = solid(g, css('--rib') || '#1B9CC8', {offset: true});
      m.position.set(px + sx*D.rib_x, py + sy*D.sw_pocket/2, D.z_sw_floor);
      plateGrp.add(m); ribs[c].push(m);
    }
  }
  const screws = DATA.parts.filter(p => p.id.startsWith('screw_')).map(p => {
    const [ax, ay] = p.axis, piv = new THREE.Group(); piv.position.set(ax, ay, 0);
    const m = solid(geo(byId[p.id].pos), '#B8BCC2', {metal: 0.5}); m.position.set(-ax, -ay, 0); piv.add(m); scene.add(piv); return piv;
  });
  const finger = new THREE.Mesh(new THREE.CapsuleGeometry(6.5, 14, 8, 20), new THREE.MeshStandardMaterial({color: 0xd9a988, roughness: 0.8, transparent: true, opacity: 0.85}));
  finger.rotation.x = Math.PI/2; scene.add(finger);
  const arrow = (col) => { const a = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 4, new THREE.Color(col), 1.4, 0.9); scene.add(a); return a; };
  const push = arrow(css('--push') || '#C99A06');
  const holds = [0, 1, 2, 3].map(() => arrow(css('--hold') || '#2E9E62'));
  const fail = arrow(css('--fail') || '#D64545');
  $('#loading').remove();

  const tags = $('#tags');
  const tagEls = {};
  function tag(key, text, cls, p) {
    let d = tagEls[key];
    if (!d) { d = document.createElement('div'); tags.appendChild(d); tagEls[key] = d; }
    d.className = 'tag ' + (cls || ''); d.textContent = text; d.dataset.p = JSON.stringify(p); d.hidden = false;
  }
  function applyClip(on) { clipMats.forEach(m => { m.clippingPlanes = on ? [plane] : []; m.needsUpdate = true; }); }
  const VIEWS = [
    {p: [46, 50, 30], t: [11, 82, 7.5]}, {p: [46, 50, 34], t: [11, 82, 8]}, {p: [44, 52, 26], t: [11, 82, 7]},
    {p: [82, 26, 72], t: [20, 82, 6]}, {p: [82, 26, 66], t: [20, 82, 12]}, {p: [76, 32, 58], t: [20, 82, 10]}, {p: [52, 58, 6], t: [11, 82, 3]}];
  let tween = null;
  function goView(k, instant) {
    const v = VIEWS[k], tgt = new THREE.Vector3(...v.t), dir = new THREE.Vector3(...v.p).sub(tgt);
    dir.multiplyScalar(Math.max(1, 1.25/Math.max(0.4, cam.aspect)));
    const to = {p: tgt.clone().add(dir), t: tgt};
    if (instant) { cam.position.copy(to.p); controls.target.copy(to.t); controls.update(); return; }
    tween = {from: {p: cam.position.clone(), t: controls.target.clone()}, to, t0: performance.now()};
  }
  function resize() { const w = stage.clientWidth, h = stage.clientHeight; renderer.setSize(w, h, false); cam.aspect = w/Math.max(1, h); cam.updateProjectionMatrix(); }
  new ResizeObserver(resize).observe(stage); resize();

  function apply(S) {
    shell.visible = S.shell > 0 && !hideShell;
    shell.userData.mats.forEach(m => { m.opacity = 0.5*S.shell; });
    plateGrp.position.z = S.plateLift;
    for (const c of ['a', 'x', 'y', 'b']) {
      caps[c].visible = S.caps[c] != null;
      caps[c].position.z = (S.caps[c] || 0) + (c === 'a' ? S.cap : 0);
      sws[c].visible = S.sw[c] != null;
      sws[c].position.z = (S.sw[c] || 0) + (c === 'a' ? (S.swWalk || 0)*(S.k === 6 ? S.ex/1 : 1) : 0);
      plungers[c].position.z = c === 'a' ? S.plunger*(S.k === 6 ? S.ex : 1) : 0;
      const cr = c === 'a' ? S.crushA : S.crush(c);
      ribs[c].forEach(m => { m.visible = mode === 'rib'; m.scale.y = 1 - 0.5*cr; });
    }
    if (S.k === 6) caps.a.position.z = S.cap*S.ex;
    screws.forEach(s => { s.visible = S.screw != null; s.position.z = S.screw || 0; s.rotation.z = (S.screw || 0)/0.5*Math.PI*2; });
    // finger and forces
    const pressing = S.k === 6;
    finger.visible = pressing;
    const capFront = -D.cap_proud + S.cap*S.ex;
    finger.position.set(A[0], A[1], capFront - 13.5 - (pressing ? (1 - Math.min(1, S.u*6))*10 : 0));
    const showHold = (S.k === 2 || (pressing && S.pressing > 0.3)) && mode === 'rib';
    push.visible = S.k === 2 || (pressing && S.pressing > 0.1);
    push.position.set(A[0], A[1], pressing ? capFront - 6 : 1.2); push.setLength(pressing ? 5.5 : 3.8, 1.4, 0.9);
    holds.forEach((h, i) => {
      const sx = i % 2 ? 1 : -1, sy = i < 2 ? -1 : 1;
      h.visible = showHold;
      h.position.set(A[0] + sx*D.rib_x, A[1] + sy*(D.sw_pocket/2 - 0.2), RIB_TOP + 3.2 + S.plateLift);
      h.setDirection(new THREE.Vector3(0, 0, -1)); h.setLength(3.2, 1.1, 0.8);
    });
    fail.visible = mode === 'old' && (S.k === 2 || (pressing && S.presses <= 1 && S.pressing > 0.3));
    fail.position.set(A[0], A[1], D.z_plate_r + 4 + S.plateLift + (sws.a.position.z)); fail.setLength(5, 1.6, 1.0);
    // labels
    for (const k in tagEls) tagEls[k].hidden = true;
    if (S.k <= 2 && mode === 'rib') tag('rib', 'ribs 0.30', 'rib', [A[0] + D.rib_x, A[1] - D.sw_pocket/2, RIB_TOP + 1 + S.plateLift]);
    if (S.k <= 1) tag('pocket', mode === 'rib' ? 'pocket 6.30' : 'pocket 6.30, no ribs', mode === 'rib' ? '' : 'fail', [A[0] - 3, A[1] + 5, D.z_plate_r + 2]);
    if (S.k === 1 || S.k === 2) tag('shoulder', 'shoulder 5.65', '', [A[0] - 1, A[1] + 1.5, D.z_sw_floor - 0.4]);
    if (S.k === 2) tag('push', 'push from the button', 'push', [A[0], A[1], -0.5]);
    if (S.k === 2 && mode === 'rib') tag('hold', 'rib friction holds', 'hold', [A[0], A[1] + 4, RIB_TOP + 6]);
    if (fail.visible) tag('fail', 'switch slides out', 'fail', [A[0], A[1], D.z_plate_r + 9 + sws.a.position.z]);
    if (S.k === 3) tag('flange', 'flange 12 mm', '', [A[0] - 1, A[1] - 6, D.z_cap_back + (S.caps.a || 0)]);
    if (S.k === 4) tag('sleeve', 'sleeve over post', '', [30.9, 92.4, 11 + S.plateLift]);
    if (S.k === 5 && S.screw != null) tag('screw', 'M3 x 8', '', [30.9, 92.4, 14 + S.screw]);
    if (pressing) tag('finger', mode === 'rib' ? (S.click ? 'click' : 'press') : 'press', S.click ? 'hold' : 'push', [A[0], A[1], capFront - 20]);
    const ck = $('#click'); ck.style.opacity = S.click ? 1 : 0;
    $('#sec').innerHTML = secSVG(S); $('#top').innerHTML = topSVG(S); readouts(S);
  }

  function frame(now) {
    if (playing) {
      t = Math.min(7, t + (now - (frame.last || now))/1000*0.16);
      if (t >= 7) { t = 7; playing = false; syncPlay(); }
      $('#tl').value = t;
    }
    frame.last = now;
    const S = state(Math.min(6.9999, t));
    if (S.k !== lastK) {
      lastK = S.k; panelText(S.k);
      cutOn = CH[S.k].cut; $('#cut').setAttribute('aria-pressed', cutOn); applyClip(cutOn);
      goView(S.k);
    }
    apply(S);
    if (tween) {
      const k = Math.min(1, (now - tween.t0)/800), e = E(k);
      cam.position.lerpVectors(tween.from.p, tween.to.p, e); controls.target.lerpVectors(tween.from.t, tween.to.t, e);
      if (k >= 1) tween = null;
    }
    controls.update(); renderer.render(scene, cam);
    const w = stage.clientWidth, h = stage.clientHeight, v = new THREE.Vector3();
    for (const el of tags.children) {
      if (el.hidden) continue;
      v.set(...JSON.parse(el.dataset.p)).project(cam);
      el.style.left = ((v.x + 1)/2*w) + 'px'; el.style.top = ((1 - v.y)/2*h) + 'px';
      if (v.z > 1) el.hidden = true;
    }
    requestAnimationFrame(frame);
  }
  window.syncPlay = function () { $('#play').innerHTML = playing ? '&#10074;&#10074;' : '&#9654;'; $('#play').setAttribute('aria-label', playing ? 'Pause' : 'Play'); };
  $('#play').onclick = () => { if (t >= 6.99) t = 0; playing = !playing; syncPlay(); };
  $('#tl').addEventListener('input', e => { t = +e.target.value; playing = false; syncPlay(); });
  $('#cut').onclick = e => { cutOn = !cutOn; e.currentTarget.setAttribute('aria-pressed', cutOn); applyClip(cutOn); };
  $('#ex').onclick = e => { exOn = !exOn; e.currentTarget.setAttribute('aria-pressed', exOn); };
  $('#shellBtn').onclick = e => { hideShell = !hideShell; e.currentTarget.setAttribute('aria-pressed', hideShell); };
  $('#reframe').onclick = () => goView(Math.min(6, Math.floor(t)));
  document.addEventListener('keydown', e => {
    if (e.key === ' ') { e.preventDefault(); $('#play').click(); }
    if (e.key === 'ArrowRight') { t = Math.min(6, Math.floor(t) + 1); playing = true; syncPlay(); }
    if (e.key === 'ArrowLeft') { t = Math.max(0, Math.floor(t) - 1); playing = true; syncPlay(); }
  });
  goView(0, true); applyClip(true); playing = true; syncPlay();
  requestAnimationFrame(frame);
})().catch(err => { const l = $('#loading'); if (l) l.textContent = 'The 3D view failed to load: ' + err.message; });
function syncPlay() { window.syncPlay && window.syncPlay(); }
panelText(0);
</script>
"""

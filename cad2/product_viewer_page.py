"""Page template for make_product_viewer.py. __DATA__ is replaced with the mesh and panel JSON."""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Any% Product Viewer</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="The Any% retro handheld in 3D, with its six swappable magnetic rear panels.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --bg:#E9ECEF; --surface:#FFFFFF; --sunk:#F3F5F7; --ink:#15171B; --muted:#59616A; --line:#D3D8DE;
  --accent:#D9481F; --accent-soft:#FBE3DA; --accent-ink:#FFFFFF;
  --stage-hi:#FFFFFF; --stage-mid:#E6EAEE; --stage-lo:#CDD3D9; --glow:#2F8CFF;
  --display:"Chakra Petch", "Segoe UI", system-ui, sans-serif;
  --body:"IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, Consolas, monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0E1012; --surface:#171A1E; --sunk:#1D2126; --ink:#E8EBEE; --muted:#9BA3AC; --line:#2A3037;
  --accent:#F0663D; --accent-soft:#3A1F16; --accent-ink:#17120F;
  --stage-hi:#2A3038; --stage-mid:#15191D; --stage-lo:#0A0C0E; --glow:#58A8FF; color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0E1012; --surface:#171A1E; --sunk:#1D2126; --ink:#E8EBEE; --muted:#9BA3AC; --line:#2A3037;
  --accent:#F0663D; --accent-soft:#3A1F16; --accent-ink:#17120F;
  --stage-hi:#2A3038; --stage-mid:#15191D; --stage-lo:#0A0C0E; --glow:#58A8FF; color-scheme:dark;}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--body);-webkit-text-size-adjust:100%}
*{box-sizing:border-box}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{display:grid;grid-template-columns:minmax(0,1fr) 400px;grid-template-rows:auto minmax(0,1fr);height:100%}
header.bar{grid-column:1/-1;display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--surface)}
.brand{font:700 20px/1 var(--display);letter-spacing:.02em}
.brand span{color:var(--accent)}
.bar .sub{font:500 12px var(--mono);color:var(--muted);letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.bar .sp{flex:1}
.ib{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:13px;white-space:nowrap}
.ib:hover{border-color:var(--muted)}
.ib svg{width:16px;height:16px;flex:none}
.stage{position:relative;min-height:0;overflow:hidden;background:radial-gradient(120% 90% at 50% 38%,var(--stage-hi) 0%,var(--stage-mid) 52%,var(--stage-lo) 100%)}
.stage canvas{display:block;width:100%;height:100%;touch-action:none;outline:none}
.views{position:absolute;left:16px;top:14px;display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 82%,transparent);backdrop-filter:blur(6px);border-radius:999px;padding:5px 12px;font-size:13px;cursor:pointer}
.chip:hover{border-color:var(--muted)}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.status{position:absolute;left:16px;bottom:14px;display:flex;align-items:center;gap:8px;font:500 12px var(--mono);color:var(--muted);pointer-events:none}
.status .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);transition:background .2s}
.status.busy .dot{background:var(--glow);box-shadow:0 0 10px var(--glow)}
.hint{position:absolute;right:16px;bottom:14px;font:500 11.5px var(--mono);color:var(--muted);pointer-events:none;text-align:right;max-width:46%}
.loading{position:absolute;inset:0;display:grid;place-items:center;font:500 13px var(--mono);color:var(--muted)}
aside.side{overflow:auto;background:var(--surface);border-left:1px solid var(--line);padding:24px 22px 36px}
.eyebrow{font:600 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:700 44px/1 var(--display);margin:6px 0 10px;letter-spacing:.01em}
h1 span{color:var(--accent)}
.lead{margin:0 0 6px;max-width:44ch;text-wrap:pretty}
h2{font:600 13px var(--display);letter-spacing:.08em;text-transform:uppercase;margin:26px 0 10px;color:var(--muted)}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:10px;list-style:none;margin:0;padding:0}
.card{width:100%;display:grid;gap:8px;text-align:left;border:1px solid var(--line);background:var(--surface);border-radius:12px;padding:10px;cursor:pointer;transition:border-color .15s,box-shadow .15s,transform .15s}
.card:hover{border-color:var(--muted)}
.card[aria-pressed="true"]{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset,0 6px 18px -10px var(--accent)}
.card:active{transform:translateY(1px)}
.mini{position:relative;aspect-ratio:202/124;border-radius:7px;border:1px solid var(--line);overflow:hidden;display:grid;place-items:center}
.mini .marks{display:flex;gap:4px;align-items:center}
.mini .marks i{display:block;width:16px;height:16px;border-radius:4px;box-shadow:0 0 0 1px rgba(127,127,127,.35)}
.mini .mag{position:absolute;width:5px;height:5px;border-radius:50%;background:rgba(150,156,164,.75)}
.card .nm{font:600 14px/1.2 var(--display);letter-spacing:.01em}
.card .cl{font:500 11.5px/1.3 var(--mono);color:var(--muted)}
.keys{font:500 12px var(--mono);color:var(--muted);margin-top:10px}
kbd{font:500 11.5px var(--mono);border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 5px;background:var(--sunk)}
dl.specs{display:grid;grid-template-columns:auto 1fr;gap:7px 16px;margin:0;font-size:14px}
dl.specs dt{font:500 11.5px var(--mono);color:var(--muted);padding-top:2px;text-transform:uppercase;letter-spacing:.05em}
dl.specs dd{margin:0}
.note{font-size:12.5px;color:var(--muted);margin-top:18px;max-width:52ch}
@media (max-width:980px){.app{grid-template-columns:minmax(0,1fr) 340px}h1{font-size:38px}}
@media (max-width:760px){
  html,body{height:auto}
  .app{display:block;height:auto}
  header.bar{position:sticky;top:0;z-index:5;padding:10px 16px}
  .bar .sub{display:none}
  .ib .t{display:none}
  .stage{height:62vh;min-height:340px}
  .hint{display:none}
  aside.side{border:0;padding:20px 16px 32px}
  .cards{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
  .card{padding:8px;gap:6px}
  .card .cl{display:none}
  .card .nm{font-size:12.5px}
  .mini .marks i{width:11px;height:11px}
  h1{font-size:34px}
}
@media (prefers-reduced-motion:reduce){.card,.status .dot{transition:none}}
</style>
</head>
<body>
<div class="app">
  <header class="bar">
    <div class="brand">Any<span>%</span></div>
    <div class="sub">Retro handheld / ETHGlobal Mumbai</div>
    <div class="sp"></div>
    <button class="ib" id="mute" aria-pressed="false" title="Toggle sound">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path id="waves" d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/><path id="cross" d="M16 9l6 6M22 9l-6 6" hidden/></svg>
      <span class="t" id="muteT">Sound on</span>
    </button>
    <button class="ib" id="theme" title="Switch light or dark theme">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16z" fill="currentColor"/></svg>
      <span class="t">Theme</span>
    </button>
  </header>
  <section class="stage" id="stage">
    <canvas id="cv" aria-label="3D view of the Any% handheld. Drag to turn it."></canvas>
    <div class="views" role="group" aria-label="Camera views">
      <button class="chip" data-view="front">Front</button>
      <button class="chip" data-view="back">Back</button>
      <button class="chip" data-view="three">Three-quarter</button>
    </div>
    <div class="status" id="status" aria-live="polite"><span class="dot"></span><span id="statusT"></span></div>
    <div class="hint">Drag to turn, scroll or pinch to zoom</div>
    <div class="loading" id="loading">Loading the 3D model...</div>
  </section>
  <aside class="side">
    <div class="eyebrow">Built for ETHGlobal Mumbai</div>
    <h1>Any<span>%</span></h1>
    <p class="lead">A Raspberry Pi handheld in a smoke shell, with rear panels that come off and snap back on with six magnets. Pick a panel to swap it.</p>
    <h2>Rear panels</h2>
    <ul class="cards" id="cards" aria-label="Rear panels"></ul>
    <div class="keys"><kbd>Left</kbd> <kbd>Right</kbd> arrow keys cycle panels</div>
    <h2>Inside</h2>
    <dl class="specs">
      <dt>Compute</dt><dd>Raspberry Pi 3B+</dd>
      <dt>Display</dt><dd>Waveshare 5 in DSI touchscreen</dd>
      <dt>Control</dt><dd>DualSense controller and touch</dd>
      <dt>Power</dt><dd>10000 mAh bank in the rear bay</dd>
      <dt>Audio</dt><dd>PAM8403 amp, FIT0502 speaker</dd>
      <dt>Panels</dt><dd>4.0 mm plate, 0.8 mm raised logo, six 6 x 3 mm magnets</dd>
      <dt>Size</dt><dd id="size"></dd>
    </dl>
    <p class="note">Panel colours are the Bambu PLA Basic spools they print in. The front buttons are still fitted in the shell; the device is played with a DualSense and the touchscreen.</p>
  </aside>
</div>

<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/environments/RoomEnvironment.js"></script>
<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const store = {
  get(k){ try { return localStorage.getItem('anypct-viewer:' + k); } catch (e) { return null; } },
  set(k, v){ try { localStorage.setItem('anypct-viewer:' + k, v); } catch (e) {} }
};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
const reduced = () => reduceMQ.matches;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (a, b, x) => { const t = clamp((x - a)/(b - a), 0, 1); return t*t*(3 - 2*t); };
const easeInOut = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3)/2;
const easeIn3 = t => t*t*t;
const N = D.panels.length;

/* ---------------- theme ---------------- */
(function(){ const t = store.get('theme'); if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; })();
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
}
$('#theme').onclick = () => { const n = isDark() ? 'light' : 'dark'; document.documentElement.dataset.theme = n; store.set('theme', n); };

/* ---------------- sound + haptics ---------------- */
let actx = null, muted = store.get('muted') === '1';
function renderMute() {
  $('#mute').setAttribute('aria-pressed', String(muted));
  $('#muteT').textContent = muted ? 'Sound off' : 'Sound on';
  $('#waves').toggleAttribute('hidden', muted); $('#cross').toggleAttribute('hidden', !muted);
}
renderMute();
$('#mute').onclick = () => { muted = !muted; store.set('muted', muted ? '1' : '0'); renderMute(); };
function unlockAudio() {
  try {
    if (!actx) { const AC = window.AudioContext || window.webkitAudioContext; if (AC) actx = new AC(); }
    if (actx && actx.state === 'suspended') actx.resume();
  } catch (e) { actx = null; }
}
addEventListener('pointerdown', unlockAudio, {passive: true});
addEventListener('keydown', unlockAudio);
function clack(strength, pitch) {
  if (muted || !actx || actx.state !== 'running') return;
  try {
    const t = actx.currentTime, s = clamp(strength, 0.1, 1), p = pitch || 1;
    const out = actx.createGain(); out.gain.value = 0.55; out.connect(actx.destination);
    // plastic and steel: a band-passed noise burst with a very fast decay
    const len = Math.floor(actx.sampleRate*0.07), buf = actx.createBuffer(1, len, actx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random()*2 - 1)*Math.pow(1 - i/len, 6);
    const src = actx.createBufferSource(); src.buffer = buf;
    const bp = actx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 2900*p; bp.Q.value = 1.4;
    const ng = actx.createGain(); ng.gain.value = 1.1*s;
    src.connect(bp); bp.connect(ng); ng.connect(out); src.start(t);
    // the panel body: a short low thump that drops in pitch
    const o = actx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(210*p, t); o.frequency.exponentialRampToValueAtTime(75*p, t + 0.07);
    const og = actx.createGain(); og.gain.setValueAtTime(0.0001, t); og.gain.exponentialRampToValueAtTime(0.7*s, t + 0.003);
    og.gain.exponentialRampToValueAtTime(0.0001, t + 0.11);
    o.connect(og); og.connect(out); o.start(t); o.stop(t + 0.13);
    // the magnet tick: a few ms of bright square wave
    const c = actx.createOscillator(); c.type = 'square'; c.frequency.value = 4600*p;
    const cg = actx.createGain(); cg.gain.setValueAtTime(0.18*s, t); cg.gain.exponentialRampToValueAtTime(0.0001, t + 0.012);
    c.connect(cg); cg.connect(out); c.start(t); c.stop(t + 0.02);
  } catch (e) {}
}
function buzz(ms) { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) {} }

/* ---------------- panel switcher UI ---------------- */
let target = 0;            // the panel the user last picked
const cards = $('#cards');
const B = D.bounds;
$('#size').textContent = `${Math.round(B[1][0] - B[0][0])} x ${Math.round(B[1][1] - B[0][1])} x ${Math.round(B[1][2] - B[0][2])} mm`;
cards.innerHTML = D.panels.map((p, i) => {
  const body = p.parts[0].colour, marks = p.parts.slice(1).map(q => `<i style="background:${q.colour}"></i>`).join('');
  const mags = D.magnets.map(([x, y]) => `<span class="mag" style="left:calc(${x/202*100}% - 2.5px);top:calc(${(124 - y)/124*100}% - 2.5px)"></span>`).join('');
  return `<li><button class="card" data-i="${i}" aria-pressed="${i === target}"><span class="mini" style="background:${body}">${mags}<span class="marks">${marks}</span></span>` +
         `<span class="nm">${p.name}</span><span class="cl">${p.colours.join(' / ')}</span></button></li>`;
}).join('');
function renderCards() { cards.querySelectorAll('.card').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.i === target))); }
cards.addEventListener('click', e => { const b = e.target.closest('.card'); if (b) choose(+b.dataset.i); });
document.addEventListener('keydown', e => {
  if (e.altKey || e.ctrlKey || e.metaKey || e.target.closest('input,textarea,select')) return;
  if (e.key === 'ArrowRight') { e.preventDefault(); choose(target + 1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); choose(target - 1); }
});
function setStatus(t, busy) { $('#statusT').textContent = t; $('#status').classList.toggle('busy', !!busy); }
setStatus(`${D.panels[0].name} panel fitted`);

let api = null;            // the 3D side, once loaded
function choose(i) {
  target = ((i % N) + N) % N;
  renderCards();
  if (api) api.request(target);
}

/* ---------------- mesh loading ---------------- */
async function gunzip(b64) {
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const ds = new DecompressionStream('gzip');
  return new Response(new Blob([bin]).stream().pipeThrough(ds)).arrayBuffer();
}
function parseSTL(buf) {
  const dv = new DataView(buf), n = dv.getUint32(80, true);
  const pos = new Float32Array(n*9), nor = new Float32Array(n*9);
  let o = 84;
  for (let i = 0; i < n; i++, o += 50) {
    for (let v = 0; v < 3; v++) {
      const k = i*9 + v*3;
      pos[k] = dv.getFloat32(o + 12 + v*12, true); pos[k+1] = dv.getFloat32(o + 16 + v*12, true); pos[k+2] = dv.getFloat32(o + 20 + v*12, true);
    }
  }
  // face normals from the winding (STL normals are not always filled in)
  for (let i = 0; i < n; i++) {
    const k = i*9;
    const ax = pos[k+3] - pos[k], ay = pos[k+4] - pos[k+1], az = pos[k+5] - pos[k+2];
    const bx = pos[k+6] - pos[k], by = pos[k+7] - pos[k+1], bz = pos[k+8] - pos[k+2];
    let nx = ay*bz - az*by, ny = az*bx - ax*bz, nz = ax*by - ay*bx;
    const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
    for (let v = 0; v < 3; v++) { nor[k + v*3] = nx; nor[k + v*3 + 1] = ny; nor[k + v*3 + 2] = nz; }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  return g;
}
// Smooth shading on curved faces (caps, magnets, screws) while keeping hard CAD edges:
// average the normals of faces that meet at a vertex at less than the crease angle.
function creaseNormals(g, deg) {
  const pos = g.attributes.position.array, nor = g.attributes.normal.array, n = pos.length/3;
  const fn = nor.slice(), cosA = Math.cos(deg*Math.PI/180), groups = new Map();
  for (let i = 0; i < n; i++) {
    const key = Math.round(pos[3*i]*500) + ',' + Math.round(pos[3*i+1]*500) + ',' + Math.round(pos[3*i+2]*500);
    let a = groups.get(key); if (!a) groups.set(key, a = []); a.push(i);
  }
  for (const a of groups.values()) {
    if (a.length < 2) continue;
    for (const i of a) {
      let x = 0, y = 0, z = 0;
      const ix = fn[3*i], iy = fn[3*i+1], iz = fn[3*i+2];
      for (const j of a) {
        const jx = fn[3*j], jy = fn[3*j+1], jz = fn[3*j+2];
        if (ix*jx + iy*jy + iz*jz >= cosA) { x += jx; y += jy; z += jz; }
      }
      const l = Math.hypot(x, y, z) || 1;
      nor[3*i] = x/l; nor[3*i+1] = y/l; nor[3*i+2] = z/l;
    }
  }
}
function radialTexture(stops) {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const x = c.getContext('2d'), gr = x.createRadialGradient(64, 64, 0, 64, 64, 64);
  stops.forEach(([o, col]) => gr.addColorStop(o, col));
  x.fillStyle = gr; x.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); return t;
}

/* ---------------- 3D ---------------- */
(async function init3d() {
  if (typeof THREE === 'undefined') { $('#loading').textContent = 'The 3D view needs an internet connection to load three.js.'; return; }
  if (typeof DecompressionStream === 'undefined') { $('#loading').textContent = 'This browser cannot unpack the 3D model. Try a current Chrome, Edge, Firefox or Safari.'; return; }
  if (THREE.ColorManagement) THREE.ColorManagement.legacyMode = false;
  const cv = $('#cv'), stage = $('#stage');
  const renderer = new THREE.WebGLRenderer({canvas: cv, antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(30, 1, 5, 6000);
  const controls = new THREE.OrbitControls(cam, cv);
  controls.enableDamping = true; controls.dampingFactor = 0.08; controls.enablePan = false;
  controls.minDistance = 170; controls.maxDistance = 1100;
  controls.minPolarAngle = 0.12; controls.maxPolarAngle = Math.PI/2 - 0.03;
  controls.rotateSpeed = 0.7;

  // studio lighting: an environment for soft reflections, a warm key, a cool fill and two rims
  let hasEnv = false;
  if (THREE.RoomEnvironment) {
    try {
      const pm = new THREE.PMREMGenerator(renderer);
      scene.environment = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
      hasEnv = true;
    } catch (e) { hasEnv = false; }
  }
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a9099, hasEnv ? 0.35 : 0.9));
  const key = new THREE.DirectionalLight(0xfff3e6, hasEnv ? 1.5 : 1.2); key.position.set(-260, 340, -320); scene.add(key);
  const fill = new THREE.DirectionalLight(0xe6f0ff, hasEnv ? 0.55 : 0.6); fill.position.set(420, 120, -120); scene.add(fill);
  const rimB = new THREE.DirectionalLight(0xffffff, hasEnv ? 0.9 : 0.8); rimB.position.set(250, 260, 420); scene.add(rimB);
  const rimC = new THREE.DirectionalLight(0xdfe9ff, hasEnv ? 0.5 : 0.5); rimC.position.set(-300, 80, 300); scene.add(rimC);
  [key, fill, rimB, rimC].forEach(l => { l.target.position.set(101, 62, 22); scene.add(l.target); });

  const [lo, hi] = D.bounds;
  const C = new THREE.Vector3((lo[0] + hi[0])/2, (lo[1] + hi[1])/2, (lo[2] + hi[2])/2);
  const device = new THREE.Group(); scene.add(device);

  const METAL = new Set(['#B8BCC2', '#C9A24A', '#A9AEB5']);
  function material(colour, alpha, opts) {
    const tr = alpha < 1, a = tr ? 1 - Math.sqrt(1 - alpha) : 1;   // one wall's opacity -> per surface
    const metal = METAL.has(colour);
    return new THREE.MeshStandardMaterial(Object.assign({
      color: colour, roughness: metal ? 0.32 : 0.58, metalness: metal ? (hasEnv ? 0.85 : 0.45) : 0.0,
      transparent: tr, opacity: a, depthWrite: !tr, side: tr ? THREE.DoubleSide : THREE.FrontSide,
      envMapIntensity: 0.9}, opts || {}));
  }
  const loadMesh = async (b64, smoothIt) => { const g = parseSTL(await gunzip(b64)); if (smoothIt) creaseNormals(g, 32); return g; };

  let frameMagMat = null;
  for (const p of D.parts) {
    const g = await loadMesh(p.blob, p.smooth);
    const shell = p.name === 'asm_front_shell';
    const m = new THREE.Mesh(g, material(p.colour, p.alpha, shell ? {roughness: 0.22, envMapIntensity: 1.3} : null));
    if (shell) m.renderOrder = 3;
    if (p.name === 'asm_magnets_frame') { m.material.emissive = new THREE.Color(css('--glow') || '#2F8CFF'); m.material.emissiveIntensity = 0; frameMagMat = m.material; }
    device.add(m);
  }

  // the launcher on the screen, in the front shell's window
  if (D.screen.img) {
    const [x0, x1, y0, y1] = D.screen.rect;
    const tex = new THREE.TextureLoader().load(D.screen.img);
    tex.encoding = THREE.sRGBEncoding; tex.anisotropy = 4;
    const sm = new THREE.Mesh(new THREE.PlaneGeometry(x1 - x0, y1 - y0),
      new THREE.MeshBasicMaterial({map: tex, toneMapped: false, color: 0xe8e8e8}));
    sm.rotation.y = Math.PI;                       // face the front (-z); image left lands at +x, the viewer's left
    sm.position.set((x0 + x1)/2, (y0 + y1)/2, (D.screen.z || 2.4) - 0.08);
    device.add(sm);
  }

  // panels: pivot at the panel centre so tilts look natural; geometry in print position (inner face z = 0)
  const PX = 101, PY = 62;
  const pmGeo = await loadMesh(D.panelMagnets, true);
  const panels = [];
  for (const p of D.panels) {
    const pivot = new THREE.Group(), inner = new THREE.Group();
    inner.position.set(-PX, -PY, 0); pivot.add(inner);
    const mats = [];
    for (const q of p.parts) {
      const col = q.colour === '#000000' ? '#0D0E10' : q.colour;   // pure black reads as a hole on screen
      const mt = material(col, 1, {roughness: q.part === 'body' ? 0.62 : 0.5});
      const m = new THREE.Mesh(await loadMesh(q.blob, false), mt);
      inner.add(m); mats.push(mt);
    }
    const magMat = material('#A9AEB5', 1); magMat.emissive = new THREE.Color(css('--glow') || '#2F8CFF'); magMat.emissiveIntensity = 0;
    inner.add(new THREE.Mesh(pmGeo, magMat)); mats.push(magMat);
    pivot.visible = false; device.add(pivot);
    panels.push({pivot, mats, magMat, op: 1});
  }

  // contact shadow under the device, which stands on its bottom edge
  const shadowTex = radialTexture([[0, 'rgba(0,0,0,0.62)'], [0.45, 'rgba(0,0,0,0.30)'], [1, 'rgba(0,0,0,0)']]);
  const softTex = radialTexture([[0, 'rgba(0,0,0,0.30)'], [0.6, 'rgba(0,0,0,0.10)'], [1, 'rgba(0,0,0,0)']]);
  function blob(tex, w, d, y) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({map: tex, transparent: true, depthWrite: false, toneMapped: false}));
    m.rotation.x = -Math.PI/2; m.scale.set(w, d, 1); m.position.set(C.x, y, C.z); scene.add(m); return m;
  }
  const shadowSoft = blob(softTex, (hi[0] - lo[0])*1.55, (hi[2] - lo[2])*4.2, lo[1] - 0.6);
  const shadowCore = blob(shadowTex, (hi[0] - lo[0])*1.12, (hi[2] - lo[2])*1.5, lo[1] - 0.3);
  function shadowTone() { const k = isDark() ? 1.0 : 0.8; shadowCore.material.opacity = k; shadowSoft.material.opacity = k; }
  shadowTone();

  // magnet glow: soft spots and an expanding ring at each of the six magnet positions,
  // one set on the frame's outer face (seen while the panel is off) and one on the panel's outer face
  const glowTex = radialTexture([[0, 'rgba(255,255,255,1)'], [0.25, 'rgba(255,255,255,0.75)'], [1, 'rgba(255,255,255,0)']]);
  const ringTex = (function(){
    const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
    const gr = x.createRadialGradient(64, 64, 40, 64, 64, 62);
    gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(0.55, 'rgba(255,255,255,0.9)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    x.fillStyle = gr; x.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c);
  })();
  const glowCol = () => new THREE.Color(css('--glow') || '#2F8CFF');
  function spriteSet(tex, z) {
    return D.magnets.map(([x, y]) => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({map: tex, color: glowCol(), transparent: true, opacity: 0, depthWrite: false, toneMapped: false}));
      s.position.set(x, y, z); s.renderOrder = 4; device.add(s); return s;
    });
  }
  const panelTop = D.dz + 4.0 + 0.85;
  const frameGlow = spriteSet(glowTex, D.dz + 0.3);
  const panelGlow = spriteSet(glowTex, panelTop + 0.15);
  const panelRing = spriteSet(ringTex, panelTop + 0.2);
  function retint() { const c = glowCol(); [...frameGlow, ...panelGlow, ...panelRing].forEach(s => s.material.color.copy(c));
    if (frameMagMat) frameMagMat.emissive.copy(c); panels.forEach(p => p.magMat.emissive.copy(c)); shadowTone(); }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', retint);
  new MutationObserver(retint).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});

  /* ---------- camera ---------- */
  const VIEWS = {front: [0.0, 0.16, -1], back: [0.0, 0.16, 1], three: [-0.95, 0.42, -1], back3: [0.9, 0.36, 1]};
  function viewPos(name) {
    const dir = new THREE.Vector3(...VIEWS[name]).normalize();
    const k = 2*Math.tan(THREE.MathUtils.degToRad(cam.fov/2));
    const d = Math.max(225/k, 335/(k*Math.max(0.3, cam.aspect)));
    return C.clone().add(dir.multiplyScalar(d));
  }
  let camTween = null;
  function tweenCam(name, dur) {
    autoStop();
    const to = viewPos(name);
    if (reduced() || !dur) { cam.position.copy(to); controls.target.copy(C); controls.update(); camTween = null; return 0; }
    // orbit around the target rather than cutting through the device
    const r0 = cam.position.clone().sub(controls.target), r1 = to.clone().sub(C);
    const s0 = new THREE.Spherical().setFromVector3(r0), s1 = new THREE.Spherical().setFromVector3(r1);
    let dth = s1.theta - s0.theta; while (dth > Math.PI) dth -= 2*Math.PI; while (dth < -Math.PI) dth += 2*Math.PI;
    camTween = {s0, s1, dth, t0: performance.now(), dur, tgt0: controls.target.clone()};
    return dur;
  }
  function stepCam(now) {
    if (!camTween) return;
    const {s0, s1, dth, t0, dur, tgt0} = camTween, e = easeInOut(clamp((now - t0)/dur, 0, 1));
    const s = new THREE.Spherical(s0.radius + (s1.radius - s0.radius)*e, s0.phi + (s1.phi - s0.phi)*e, s0.theta + dth*e);
    controls.target.lerpVectors(tgt0, C, e);
    cam.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(s));
    if (e >= 1) camTween = null;
  }
  const backVisible = () => cam.position.clone().sub(controls.target).normalize().z > 0.3;
  let autoOn = !reduced();
  function autoStop() { autoOn = false; controls.autoRotate = false; }
  controls.autoRotate = autoOn; controls.autoRotateSpeed = 0.7;
  controls.addEventListener('start', () => { autoStop(); camTween = null; });
  document.querySelectorAll('.chip[data-view]').forEach(b => b.onclick = () => tweenCam(b.dataset.view, 900));

  function resize() {
    const w = stage.clientWidth, h = stage.clientHeight;
    renderer.setSize(w, h, false); cam.aspect = w/Math.max(1, h); cam.updateProjectionMatrix();
  }
  resize(); new ResizeObserver(resize).observe(stage);
  cam.position.copy(viewPos('three')); controls.target.copy(C); controls.update();

  /* ---------- panel poses ---------- */
  function pose(i, z, x, y, rx, ry, op) {
    const p = panels[i], pv = p.pivot;
    pv.position.set(PX + (x || 0), PY + (y || 0), D.dz + z);
    pv.rotation.set(rx || 0, ry || 0, 0);
    op = op === undefined ? 1 : op;
    if (Math.abs(op - p.op) > 1e-4) {
      for (const m of p.mats) {
        const tr = op < 0.999;
        if (m.transparent !== tr) { m.transparent = tr; m.needsUpdate = true; }
        m.opacity = op;
      }
      p.op = op;
    }
    pv.visible = op > 0.01;
  }
  function hideAll() { panels.forEach((p, i) => { pose(i, 0, 0, 0, 0, 0, 1); p.pivot.visible = false; }); }

  /* ---------- the swap ----------
     phases: cam (ease to the back if needed) -> strain (held by the magnets) -> pop (breaks free,
     lifts along +z, slides away and fades) -> gap -> approach (simulated pull, roughly 1/d^2,
     from 80 mm out) -> settle (crisp overshoot, two small settles) */
  let seated = 0, sw = null;
  const T_STRAIN = 0.30, T_POP = 0.95, T_GAP = 0.08, T_SETTLE = 0.34;
  const D0 = 80, V0 = -130, K = 70000, SOFT = 6, DRAG = 2.0;
  let shakeT = 9, shakeAmp = 0, shakePh = [0, 0, 0], glowT = 9, glowAmp = 0, preGlow = 0;

  function name(i) { return D.panels[i].name; }
  function request(i) {
    if (reduced()) {                            // no motion: swap in place
      sw = null; hideAll(); seated = i; pose(i, 0, 0, 0, 0, 0, 1);
      setStatus(`${name(i)} panel fitted`); clack(0.6); buzz(15); return;
    }
    if (sw) { sw.hurry = true; return; }        // the running swap picks up the newest target
    if (i !== seated) startSwap();
  }
  function startSwap() {
    const wait = backVisible() ? 0 : tweenCam('back3', 850)/1000*0.65;
    autoStop();
    sw = {phase: 'cam', t: 0, wait, from: seated, to: -1, hurry: false, z: 0};
    setStatus(`Releasing ${name(seated)}`, true);
  }
  function contact(v) {
    const s = clamp(Math.abs(v)/140, 0.35, 1);
    clack(s); buzz(15);
    shakeT = 0; shakeAmp = 0.35 + 0.35*s; shakePh = [Math.random()*6.28, Math.random()*6.28, Math.random()*6.28];
    glowT = 0; glowAmp = 1;
    sw.amp = 0.45 + 0.45*s;
  }
  function stepSwap(dt) {
    if (!sw) return;
    const ts = sw.hurry ? 1.9 : 1;
    sw.t += dt*ts;
    const t = sw.t;
    if (sw.phase === 'cam') {
      if (target === seated) { sw = null; setStatus(`${name(seated)} panel fitted`); return; }
      if (t >= sw.wait) { sw.phase = 'strain'; sw.t = 0; }
      return;
    }
    if (sw.phase === 'strain') {
      const e = clamp(t/T_STRAIN, 0, 1);
      // the magnets hold: a tiny creep outwards and a 0.3 mm shiver that builds as the pull grows
      const z = 0.12*e*e + 0.3*Math.sin(2*Math.PI*21*t)*(0.35 + 0.65*e);
      const rx = 0.0015*Math.sin(2*Math.PI*16*t)*e;
      pose(sw.from, Math.max(-0.05, z), 0, 0, rx, 0, 1);
      sw.z = z;
      if (e >= 1) {
        if (target === seated) { pose(sw.from, 0, 0, 0, 0, 0, 1); sw = null; setStatus(`${name(seated)} panel fitted`); return; }
        sw.phase = 'pop'; sw.t = 0; sw.z0 = Math.max(0, z); clack(0.22, 1.6);
      }
      return;
    }
    if (sw.phase === 'pop') {
      const e = clamp(t/T_POP, 0, 1);
      // breaks free: fast initial velocity that bleeds off (ease out), then slides away and fades
      const z = sw.z0 + 46*(1 - Math.exp(-t/0.13)) + 22*t;
      const slide = easeIn3(clamp((t - 0.2)/(T_POP - 0.2), 0, 1));
      const rx = -0.06*(1 - Math.exp(-t/0.09)) + 0.04*slide;
      pose(sw.from, z, 230*slide, 10*slide, rx, 0.22*slide, 1 - smooth(0.42, 0.95, e));
      if (e >= 1) {
        pose(sw.from, 0, 0, 0, 0, 0, 1); panels[sw.from].pivot.visible = false;
        sw.phase = 'gap'; sw.t = 0;
      }
      return;
    }
    if (sw.phase === 'gap') {
      if (t >= T_GAP) {
        sw.to = target; sw.phase = 'approach'; sw.t = 0; sw.d = D0; sw.v = V0;
        setStatus(`Snapping on ${name(sw.to)}`, true);
      }
      return;
    }
    if (sw.phase === 'approach') {
      // fixed 1 ms steps: drift and drag far away, attraction K/(d+SOFT)^2 that takes over near the frame
      let steps = Math.max(1, Math.round(dt*ts*1000));
      while (steps-- > 0 && sw.d > 0) {
        const a = -K/((sw.d + SOFT)*(sw.d + SOFT)) - DRAG*sw.v;
        sw.v += a*0.001; sw.d += sw.v*0.001;
      }
      const d = Math.max(0, sw.d), f = Math.pow(d/D0, 1.6);
      preGlow = 0.45*smooth(22, 0, d);
      pose(sw.to, d, -150*f, 14*f, 0.07*f, -0.3*f, smooth(0, 0.3, t));
      if (sw.d <= 0) { contact(sw.v); sw.phase = 'settle'; sw.t = 0; preGlow = 0; }
      return;
    }
    if (sw.phase === 'settle') {
      // overshoot into the frame, rebound, settle: a fast damped ring
      const A = sw.amp, env = Math.exp(-t/0.055);
      const z = -A*env*Math.sin(2*Math.PI*t/0.09);
      const rx = 0.0035*env*Math.sin(2*Math.PI*t/0.065 + 0.6);
      pose(sw.to, z, 0, 0, rx, 0, 1);
      if (t >= T_SETTLE) {
        pose(sw.to, 0, 0, 0, 0, 0, 1);
        seated = sw.to; sw = null;
        setStatus(`${name(seated)} panel fitted`);
        if (target !== seated) { startSwap(); sw.hurry = true; }
      }
    }
  }
  function stepFx(dt) {
    shakeT += dt; glowT += dt;
    if (shakeT < 0.25) {
      const a = shakeAmp*Math.exp(-shakeT/0.04);
      device.position.set(a*Math.sin(2*Math.PI*53*shakeT + shakePh[0]), 0.7*a*Math.sin(2*Math.PI*61*shakeT + shakePh[1]),
                          0.8*a*Math.sin(2*Math.PI*47*shakeT + shakePh[2]));
      device.rotation.z = 0.0012*Math.exp(-shakeT/0.04)*Math.sin(2*Math.PI*44*shakeT);
    } else { device.position.set(0, 0, 0); device.rotation.z = 0; }
    const g = glowT < 1.2 ? glowAmp*Math.exp(-glowT/0.22) : 0;
    const fg = Math.max(g, preGlow);
    frameGlow.forEach(s => { s.material.opacity = 0.85*fg; s.scale.setScalar(9 + 6*fg); s.visible = fg > 0.01; });
    panelGlow.forEach(s => { s.material.opacity = 0.9*g; s.scale.setScalar(8 + 10*(1 - g)); s.visible = g > 0.01; });
    panelRing.forEach(s => { s.material.opacity = 0.8*g; s.scale.setScalar(8 + 26*(1 - g)); s.visible = g > 0.01; });
    if (frameMagMat) frameMagMat.emissiveIntensity = 2.2*fg;
    panels.forEach(p => { p.magMat.emissiveIntensity = 2.2*g; });
  }

  hideAll();
  seated = target; pose(seated, 0, 0, 0, 0, 0, 1);
  setStatus(`${name(seated)} panel fitted`);
  api = {request};
  $('#loading').remove();

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, Math.max(0, (now - last)/1000)); last = now;
    stepCam(now); stepSwap(dt); stepFx(dt);
    controls.autoRotate = autoOn && !sw && !camTween;
    controls.update();
    renderer.render(scene, cam);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})().catch(e => { const l = $('#loading'); if (l) l.textContent = 'The 3D view could not load: ' + e.message; console.error(e); });
</script>
</body>
</html>
"""

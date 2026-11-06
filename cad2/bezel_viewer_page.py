PAGE = r"""<meta charset="utf-8">
<title>Any% Bezel Fit</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@600;700&family=IBM+Plex+Mono:wght@500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{--bg:#E9ECEF;--surface:#FFFFFF;--ink:#15171B;--muted:#59616A;--line:#D3D8DE;--accent:#D9481F;--stage:#D8DDE2;color-scheme:light;
  --display:"Chakra Petch","Segoe UI",system-ui,sans-serif;--body:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0E1012;--surface:#171A1E;--ink:#E8EBEE;--muted:#9BA3AC;--line:#2A3037;--accent:#F0663D;--stage:#121518;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0E1012;--surface:#171A1E;--ink:#E8EBEE;--muted:#9BA3AC;--line:#2A3037;--accent:#F0663D;--stage:#121518;color-scheme:dark}
html,body{height:100%}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--body)}*{box-sizing:border-box}button,input{font:inherit;color:inherit}
.app{display:grid;grid-template-columns:minmax(0,1fr) 340px;height:100%}
.stage{position:relative;background:var(--stage);min-height:0}.stage canvas{display:block;width:100%;height:100%;touch-action:none}
.bar{position:absolute;left:12px;top:12px;right:12px;display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 88%,transparent);border-radius:999px;padding:4px 11px;font-size:12.5px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
aside{background:var(--surface);border-left:1px solid var(--line);overflow:auto;padding-block:18px 28px;padding-inline:20px}
h1{font:700 22px/1.2 var(--display);margin:0 0 6px}.eyebrow{font:500 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
p{margin:0 0 10px;max-width:60ch}h2{font:600 13px var(--display);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:18px 0 6px}
table{border-collapse:collapse;width:100%;font-size:13.5px}td{padding:5px 0;border-bottom:1px solid var(--line);vertical-align:top}td.v{font:500 13px var(--mono);text-align:right;white-space:nowrap;padding-left:10px}
label{display:block;font-size:13px;color:var(--muted);margin-top:12px}input[type=range]{width:100%;accent-color:var(--accent)}
.loading{position:absolute;inset:0;display:grid;place-items:center;font:500 13px var(--mono);color:var(--muted)}
@media (max-width:820px){html,body{height:auto}.app{display:block}.stage{height:60vh;min-height:340px}aside{border:0;padding-inline:16px}}
</style>
<div class="app">
  <section class="stage" id="stage"><canvas id="cv" aria-label="The bezel over the screen"></canvas>
    <div class="bar"><button class="chip" id="vIso">Three-quarter</button><button class="chip" id="vFront">Front</button>
      <button class="chip" id="vEdge">Edge close-up</button><button class="chip" id="cut" aria-pressed="false">Cut through</button>
      <button class="chip" id="hideB" aria-pressed="false">Hide bezel</button></div>
    <div class="loading" id="loading">Loading...</div></section>
  <aside>
    <div class="eyebrow">Any% display bezel</div><h1>Bezel on the real screen</h1>
    <p>The screen is Waveshare's own 3D model of the 50H-800480-IPS-CT, straight from their STEP file. The black frame is the bezel exactly as it prints. The grey slab is the shell face it sits on.</p>
    <label for="lift">Lift the bezel off: <span id="liftv">0</span> mm</label><input type="range" id="lift" min="0" max="30" step="0.5" value="0">
    <h2>From the screen's model</h2>
    <table>
      <tr><td>Touch glass</td><td class="v">127.70 x 87.45</td></tr>
      <tr><td>Clear window</td><td class="v">109.0 x 65.8</td></tr>
      <tr><td>Pixels</td><td class="v">108.0 x 64.8</td></tr>
      <tr><td>Black print, sides and top</td><td class="v">9.35</td></tr>
      <tr><td>Black print, cable edge</td><td class="v">12.30</td></tr>
      <tr><td>Glass top above the LCD back</td><td class="v">6.45</td></tr>
    </table>
    <h2>The bezel</h2>
    <table>
      <tr><td>Outside</td><td class="v">131.5 x 91.25 x 7.6</td></tr>
      <tr><td>Gap round the glass</td><td class="v">0.30</td></tr>
      <tr><td>Wall</td><td class="v">1.60</td></tr>
      <tr><td>Lip over the black print</td><td class="v">2.50 / 5.45</td></tr>
      <tr><td>Black left showing, every side</td><td class="v">6.85</td></tr>
      <tr><td>Lip clears the glass by</td><td class="v">0.15</td></tr>
    </table>
    <p style="margin-top:12px;color:var(--muted);font-size:13px">Assumed: the LCD back rests on the shell face, so the glass top is 6.45 mm above it. Measure yours before printing.</p>
  </aside>
</div>
<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/controls/OrbitControls.js"></script>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
async function gunzip(b64) {
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return new Response(new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
}
function geo(buf) {
  const dv = new DataView(buf), n = dv.getUint32(80, true), pos = new Float32Array(n * 9);
  for (let i = 0, o = 84; i < n; i++, o += 50) for (let v = 0; v < 9; v++) pos[i * 9 + v] = dv.getFloat32(o + 12 + v * 4, true);
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.computeVertexNormals(); return g;
}
(async () => {
  if (typeof THREE === 'undefined') { $('#loading').textContent = 'Needs an internet connection for three.js.'; return; }
  const stage = $('#stage'), cv = $('#cv');
  const r = new THREE.WebGLRenderer({canvas: cv, antialias: true}); r.setPixelRatio(Math.min(devicePixelRatio, 2)); r.localClippingEnabled = true;
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(32, 1, 1, 3000); cam.up.set(0, 0, 1);
  const ctl = new THREE.OrbitControls(cam, cv); ctl.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x5a6068, 1.0));
  const l1 = new THREE.DirectionalLight(0xffffff, 0.9); l1.position.set(-120, -160, 220); scene.add(l1);
  const l2 = new THREE.DirectionalLight(0xffffff, 0.35); l2.position.set(160, 120, 90); scene.add(l2);
  const bg = () => { scene.background = new THREE.Color(css('--stage')); }; bg();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', bg);
  const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);          // cut through: keep y <= 0
  const mats = [];
  const meshes = {};
  for (const p of DATA.parts) {
    const m = new THREE.MeshStandardMaterial({color: p.colour, roughness: p.id === 'glass' ? 0.25 : 0.7, metalness: p.id === 'lcd' ? 0.4 : 0.05, side: THREE.DoubleSide});
    mats.push(m);
    const mesh = new THREE.Mesh(geo(await gunzip(p.blob)), m); scene.add(mesh); meshes[p.id] = mesh;
  }
  // the shell face under the screen (context only)
  const faceM = new THREE.MeshStandardMaterial({color: 0x8a8e93, roughness: 0.9}); mats.push(faceM);
  const face = new THREE.Mesh(new THREE.BoxGeometry(170, 120, 2.4), faceM); face.position.set(0, -2, DATA.face_z - 1.2); scene.add(face);
  if (DATA.shot) {
    const tex = new THREE.TextureLoader().load(DATA.shot); tex.encoding = THREE.sRGBEncoding;
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(108, 64.8), new THREE.MeshBasicMaterial({map: tex}));
    scr.position.set(0, 0, 4.72); scene.add(scr); mats.push(scr.material);
  }
  $('#loading').remove();
  const views = {iso: [[95, -170, 150], [0, 0, 2]], front: [[0, -10, 260], [0, 0, 2]], edge: [[62, -70, 22], [55, -40, 3]]};
  let tw = null;
  function go(k, now) { const [p, t] = views[k]; const to = {p: new THREE.Vector3(...p), t: new THREE.Vector3(...t)};
    if (now) { cam.position.copy(to.p); ctl.target.copy(to.t); return; } tw = {f: {p: cam.position.clone(), t: ctl.target.clone()}, to, t0: performance.now()}; }
  $('#vIso').onclick = () => go('iso'); $('#vFront').onclick = () => go('front'); $('#vEdge').onclick = () => go('edge');
  $('#cut').onclick = e => { const on = e.currentTarget.getAttribute('aria-pressed') !== 'true'; e.currentTarget.setAttribute('aria-pressed', on);
    mats.forEach(m => { m.clippingPlanes = on ? [plane] : []; m.needsUpdate = true; }); if (on) go('edge'); };
  $('#hideB').onclick = e => { const on = e.currentTarget.getAttribute('aria-pressed') !== 'true'; e.currentTarget.setAttribute('aria-pressed', on); meshes.bezel.visible = !on; };
  $('#lift').oninput = e => { meshes.bezel.position.z = +e.target.value; $('#liftv').textContent = e.target.value; };
  const size = () => { const w = stage.clientWidth, h = stage.clientHeight; r.setSize(w, h, false); cam.aspect = w / Math.max(1, h); cam.updateProjectionMatrix(); };
  new ResizeObserver(size).observe(stage); size(); go('iso', true);
  const E = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  (function loop(now) {
    if (tw) { const k = Math.min(1, (now - tw.t0) / 700), e = E(k); cam.position.lerpVectors(tw.f.p, tw.to.p, e); ctl.target.lerpVectors(tw.f.t, tw.to.t, e); if (k >= 1) tw = null; }
    ctl.update(); r.render(scene, cam); requestAnimationFrame(loop);
  })(performance.now());
})().catch(e => { const l = $('#loading'); if (l) l.textContent = 'Failed: ' + e.message; });
</script>
"""

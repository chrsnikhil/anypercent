import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import * as THREE from "three";
import { clamp, easeInOut, easeOutExpo, lerp, prog, rnd } from "../util";
import { BAR, Bars, CameraAt, Card, GLYPHS, H, kick, Line, Mono, MW, Post, Row, Subs, W, useGlyphAtlas } from "./common";
import { FONT } from "../theme";

/* Act 0. One world-record timer, ticking, in extreme close-up. The camera pulls back: it is one cell in a canyon of
   timers that runs into the fog and breathes. A red VOID wave rolls down the canyon toward us. PROVE IT. */

export const COLD_LEN = 1200;
const CELL_U = 150, CELL_V = 64, WALL_X = 500;
const HERO = { u: 900, v: 0 };                       // the cell we start on (right wall)
const VOID_A = 760, VOID_B = 1010;                   // the wave's run, frames
const LINES: Line[] = [
  { at: 70, len: 210, who: "Handler", text: "Every world record is a claim." },
  { at: 330, len: 300, who: "Handler", text: "Thousands of records, and you have to take each one on trust." },
  { at: 780, len: 220, who: "Handler", text: "And a claim is only as good as its proof." },
];

/** The canyon walls breathe: the same displacement on the GPU and here, so the camera can find the hero cell. */
const breathe = (z: number, y: number, t: number) => Math.sin(z * 0.0021 + t * 0.55) * 42 + Math.sin(y * 0.003 - t * 0.4) * 18;

const vert = /* glsl */ `
  uniform float uT; uniform float uSide;
  varying vec3 vW; varying float vDist;
  void main() {
    vec3 p = position;
    vec4 w = modelMatrix * vec4(p, 1.0);
    w.x += uSide * (sin(w.z * 0.0021 + uT * 0.55) * 42.0 + sin(w.y * 0.003 - uT * 0.4) * 18.0);
    float far = max(0.0, -w.z - 2600.0) / 1000.0;
    w.y += far * far * 70.0;                                              // far off, the canyon folds up into the sky
    vW = w.xyz;
    vec4 mv = viewMatrix * w;
    vDist = -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;
const frag = /* glsl */ `
  uniform sampler2D uAtlas; uniform float uT; uniform float uHeroT; uniform float uFront; uniform float uSide;
  uniform float uDark; uniform float uN; uniform float uRed; uniform vec3 uHeroCol; uniform float uHeroGlow;
  varying vec3 vW; varying float vDist;
  float hash(vec3 p) { return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); }
  float glyph(float idx, vec2 g) {
    if (g.x < 0.0 || g.x > 1.0 || g.y < 0.0 || g.y > 1.0) return 0.0;
    return texture2D(uAtlas, vec2((idx + g.x) / uN, g.y)).a;
  }
  void main() {
    float u = -vW.z, v = vW.y;
    vec2 cell = floor(vec2(u / ${CELL_U.toFixed(1)}, v / ${CELL_V.toFixed(1)}));
    vec2 l = fract(vec2(u / ${CELL_U.toFixed(1)}, v / ${CELL_V.toFixed(1)}));
    if (uSide > 0.0) l.x = 1.0 - l.x;                        // seen from inside, the right wall runs backwards
    float h1 = hash(vec3(cell, uSide)), h2 = hash(vec3(cell.yx, uSide + 3.0)), h3 = hash(vec3(cell + 7.0, uSide));
    bool hero = uSide > 0.0 && cell.x == ${(HERO.u / CELL_U).toFixed(1)} && cell.y == ${(HERO.v / CELL_V).toFixed(1)};
    float t = 41.0 + h1 * 520.0 + (h2 > 0.3 ? uT * (0.6 + h3) : 0.0);
    if (hero) t = uHeroT;
    bool isVoid = u > uFront && !hero;
    bool scramble = !isVoid && !hero && u > uFront - 420.0;            // digits churn just ahead of the wave
    // seven glyph slots: M : S S . c c
    float slot = floor((l.x - 0.07) / 0.86 * 7.0);
    vec2 g = vec2(fract((l.x - 0.07) / 0.86 * 7.0), (l.y - 0.2) / 0.62);
    float behind = u - uFront;
    if (behind > 0.0 && behind < 260.0) {                                  // the cell flips over like a split-flap
      float k = abs(cos(behind / 260.0 * 3.14159 * (1.0 + h1)));
      g.y = (g.y - 0.5) / max(k, 0.05) + 0.5;
    }
    float idx = 18.0;
    if (slot >= 0.0 && slot < 7.0) {
      if (isVoid) {
        idx = slot == 1.0 ? 12.0 : slot == 2.0 ? 13.0 : slot == 3.0 ? 14.0 : slot == 4.0 ? 15.0 : 18.0;
      } else {
        float m = mod(floor(t / 60.0), 10.0), s = mod(floor(t), 60.0), c = floor(fract(t) * 100.0);
        idx = slot == 0.0 ? m : slot == 1.0 ? 10.0 : slot == 2.0 ? floor(s / 10.0) : slot == 3.0 ? mod(s, 10.0)
            : slot == 4.0 ? 11.0 : slot == 5.0 ? floor(c / 10.0) : mod(c, 10.0);
        if (scramble && slot != 1.0 && slot != 4.0) idx = floor(hash(vec3(cell * 3.1 + slot, floor(uT * 30.0))) * 10.0);
      }
    }
    float a = glyph(idx, g);
    float edge = step(l.x, 0.02) + step(0.98, l.x) + step(l.y, 0.04) + step(0.96, l.y);
    float lit = 0.35 + 0.65 * h3;
    lit *= 0.85 + 0.15 * step(0.5, hash(vec3(cell, floor(uT * 9.0))));      // a faint flicker
    vec3 amber = vec3(1.0, 0.62, 0.2), red = vec3(1.0, 0.16, 0.08);
    vec3 bg = isVoid ? vec3(0.012, 0.002, 0.001) : vec3(0.0035, 0.0025, 0.0016);
    vec3 col = bg + (isVoid ? vec3(0.05, 0.008, 0.004) : vec3(0.014, 0.009, 0.005)) * min(edge, 1.0);
    float pulse = scramble ? 1.8 : 1.0;
    if (hero) col += vec3(0.0, 0.07, 0.025) * uHeroGlow;                // the proven record lights its own cell
    col += (isVoid ? red * 0.75 : hero ? uHeroCol * 0.75 : amber * 0.55 * lit * pulse) * a;
    float df = (u - uFront) / 45.0;
    float front = exp(-df * df);                                       // the wave front burns white
    col += vec3(1.0, 0.45, 0.25) * front * 1.6;
    col *= 1.0 - uDark;
    float fog = 1.0 - exp(-vDist * 0.00036);
    vec3 haze = mix(vec3(0.034, 0.017, 0.008), vec3(0.04, 0.008, 0.004), uRed) * exp(-abs(v - 300.0) * 0.00045);
    col = mix(col, haze, clamp(fog, 0.0, 0.985));
    gl_FragColor = vec4(col, 1.0);
  }`;

const AMBER = new THREE.Color(1.0, 0.62, 0.2), GREEN = new THREE.Color(0.35, 1.0, 0.45);
const Walls: React.FC<{ f: number; atlas: THREE.Texture; coda?: { heroT: number; green: number; dark: number } }> = ({ f, atlas, coda }) => {
  const mats = useMemo(() => [1, -1].map((side) => new THREE.ShaderMaterial({
    vertexShader: vert, fragmentShader: frag, side: THREE.DoubleSide,
    uniforms: { uAtlas: { value: atlas }, uT: { value: 0 }, uHeroT: { value: 0 }, uFront: { value: 1e6 }, uSide: { value: side },
      uDark: { value: 0 }, uN: { value: GLYPHS.length }, uRed: { value: 0 }, uHeroCol: { value: AMBER.clone() }, uHeroGlow: { value: 0 } },
  })), [atlas]);
  const geo = useMemo(() => new THREE.PlaneGeometry(9000, 3600, 220, 90), []);
  const t = f / 60;
  const front = lerp(9000, -700, Math.pow(prog(f, VOID_A, 1004), 1.7));     // it accelerates, and passes the lens at the flash
  for (const m of mats) {
    m.uniforms.uT.value = t;
    m.uniforms.uHeroT.value = Math.max(0, (f - 40) / 60);
    m.uniforms.uFront.value = f < VOID_A ? 1e6 : front;
    m.uniforms.uDark.value = clamp((f - 1150) / 40);
    m.uniforms.uRed.value = easeInOut(prog(f, VOID_A, VOID_B));
    m.uniforms.uHeroCol.value.copy(AMBER);
    m.uniforms.uHeroGlow.value = coda ? coda.green : 0;
    if (coda) {                                        // every record VOID but one
      m.uniforms.uHeroT.value = coda.heroT;
      m.uniforms.uFront.value = -1e9;
      m.uniforms.uRed.value = 1;
      m.uniforms.uDark.value = coda.dark;
      m.uniforms.uHeroCol.value.copy(AMBER).lerp(GREEN, coda.green).multiplyScalar(1 + 1.5 * Math.max(0, 1 - Math.abs(coda.green - 0.5) * 2));
    }
  }
  return (
    <>
      <mesh geometry={geo} material={mats[0]} position={[WALL_X, 0, -4300]} rotation={[0, -Math.PI / 2, 0]} />
      <mesh geometry={geo} material={mats[1]} position={[-WALL_X, 0, -4300]} rotation={[0, Math.PI / 2, 0]} />
    </>
  );
};

/** The sky at the end of the canyon: the same haze the walls fog into, with a soft light at the vanishing point. */
const Backdrop: React.FC<{ f: number; coda?: { dark: number } }> = ({ f, coda }) => {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    depthWrite: false,
    uniforms: { uK: { value: 1 }, uRed: { value: 0 }, uDark: { value: 0 } },
    vertexShader: "varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }",
    fragmentShader: `uniform float uK; uniform float uRed; uniform float uDark; varying vec3 vW;
      void main(){
        vec3 haze = mix(vec3(0.034, 0.017, 0.008), vec3(0.04, 0.008, 0.004), uRed) * exp(-abs(vW.y - 300.0) * 0.00045);
        vec2 d = (vW.xy - vec2(0.0, 900.0)) / vec2(2600.0, 1500.0); float r2 = dot(d, d);
        vec3 warm = mix(vec3(1.0, 0.6, 0.28), vec3(1.0, 0.16, 0.07), uRed);
        vec3 c = haze + warm * (0.5 * exp(-r2 * 14.0) + 0.06 * exp(-r2 * 1.5)) * uK;
        gl_FragColor = vec4(c * (1.0 - uDark), 1.0); }`,
  }), []);
  mat.uniforms.uK.value = lerp(0.5, 1.0, prog(f, 300, 720));
  mat.uniforms.uRed.value = easeInOut(prog(f, VOID_A, VOID_B));
  mat.uniforms.uDark.value = clamp((f - 1150) / 40);
  if (coda) { mat.uniforms.uRed.value = 1; mat.uniforms.uDark.value = coda.dark; }
  return <mesh material={mat} position={[0, 0, -9400]} renderOrder={-1}><planeGeometry args={[60000, 40000]} /></mesh>;
};

/** Dust in the canyon, drifting slowly through the light. */
const Dust: React.FC<{ f: number }> = ({ f }) => {
  const { geo, mat } = useMemo(() => {
    const n = 1400, p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { p[i * 3] = (rnd(i, 1) - 0.5) * 900; p[i * 3 + 1] = (rnd(i, 2) - 0.5) * 1400; p[i * 3 + 2] = 400 - rnd(i, 3) * 5000; }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    const c = document.createElement("canvas");                       // a soft round mote, not a square point
    c.width = c.height = 64;
    const g2 = c.getContext("2d")!;
    const grd = g2.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)");
    grd.addColorStop(0.35, "rgba(255,255,255,0.45)");
    grd.addColorStop(1, "rgba(255,255,255,0)");
    g2.fillStyle = grd;
    g2.fillRect(0, 0, 64, 64);
    const m = new THREE.PointsMaterial({ color: new THREE.Color("#ffb86b"), size: 5.5, map: new THREE.CanvasTexture(c), transparent: true, opacity: 0.6,
      depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
    return { geo: g, mat: m };
  }, []);
  return <points geometry={geo} material={mat} position={[Math.sin(f * 0.004) * 20, f * 0.12, 0]} />;
};

/** Where the light at the end of the canyon is (the backdrop's glow), and where the hero cell is at a moment. */
const GLOW = new THREE.Vector3(0, 900, -9400);
const heroAt = (f: number) => {
  const hz = -(HERO.u + CELL_U / 2), hy = HERO.v + CELL_V / 2;
  return new THREE.Vector3(WALL_X + breathe(hz, hy, f / 60), hy, hz);
};

/** The camera: extreme close-up on the hero timer, then a long pull-back that turns to look down the canyon. */
const camAt = (f: number) => {
  const t = f / 60;
  const hz = -(HERO.u + CELL_U / 2), hy = HERO.v + CELL_V / 2;
  const hx = WALL_X + breathe(hz, hy, t);
  const close = { pos: new THREE.Vector3(hx - lerp(175, 128, easeInOut(prog(f, 0, 300))), hy, hz), target: new THREE.Vector3(hx, hy, hz) };
  const far = { pos: new THREE.Vector3(-60, 140, 700 - 900 * prog(f, 720, 1200)), target: new THREE.Vector3(40, 60, -3200) };
  const k = easeInOut(prog(f, 300, 720));
  const pos = close.pos.clone().lerp(far.pos, k);
  // swing out from the wall on an arc so the reveal turns rather than slides
  pos.x -= Math.sin(k * Math.PI) * 260;
  pos.y += Math.sin(k * Math.PI) * 120;
  const target = close.target.clone().lerp(far.target, Math.pow(k, 0.7));
  return { pos, target, fov: lerp(30, 42, k), roll: -0.06 * Math.sin(k * Math.PI) - 0.03 * k };
};

/** The archive card, MW3 spawn grammar: the black box grows from its corner, the header flickers on, rows wipe down. */
const ArchiveCard: React.FC<{ f: number }> = ({ f }) => {
  const a = 330, out = 1 - prog(f, 990, 1000);
  if (f < a || out <= 0) return null;
  const grow = easeOutExpo(prog(f, a, a + 6));
  const head = f > a + 8 && !(f > a + 11 && f < a + 13) ? 1 : 0;
  const rows: [string, string, string][] = [
    ["SUBMITTED AS", "VIDEO", MW.text],
    ["PROOF", "NONE", MW.text],
    ["VERIFIED", f > VOID_A + 40 ? "0" : "UNKNOWN", f > VOID_A + 40 ? MW.red : MW.amber],
  ];
  return (
    <div style={{ position: "absolute", left: 64, top: BAR + 34, opacity: out }}>
      <div style={{ width: 360 * grow, height: 150 * grow, background: "rgba(4,4,4,0.82)", borderLeft: `3px solid ${MW.orange}` }} />
      <div style={{ position: "absolute", left: 20, top: 14, opacity: head }}>
        <Mono s={15} c={MW.orange} w={700} ls="0.18em">ARCHIVE // WORLD RECORDS</Mono>
      </div>
      {rows.map(([k, v, c], i) => (
        <div key={k} style={{ position: "absolute", left: 20, top: 48 + i * 30, width: 320, display: "flex", justifyContent: "space-between",
          clipPath: `inset(0 0 ${100 - 100 * prog(f, a + 12 + i * 5, a + 22 + i * 5)}% 0)` }}>
          <Mono s={17} c={MW.dim} ls="0.1em">{k}</Mono>
          <Mono s={17} c={c} w={700}>{v}</Mono>
        </div>
      ))}
    </div>
  );
};

/** The opening camera with the shake of the wave's arrival on it. */
const camShaken = (f: number) => {
  const c = camAt(f);
  const shake = Math.pow(prog(f, 900, 1000), 2) * (1 - prog(f, 1004, 1030));
  c.pos.x += Math.sin(f * 1.7) * 5 * shake;
  c.pos.y += Math.sin(f * 2.3 + 1) * 4 * shake;
  return c;
};

export const ColdOpen: React.FC = () => {
  const f = useCurrentFrame();
  const atlas = useGlyphAtlas();
  const c = camShaken(f);
  const cPrev = camShaken(f - 0.5);                                    // half a frame ago, for the motion blur
  const flash = clamp(1 - Math.abs(f - 1005) / 3);
  const slam = prog(f, 1010, 1030);
  const slamOut = 1 - prog(f, 1160, 1185);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {atlas ? (
        <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0, opacity: clamp(f / 30), transform: kick(f, [1010], 12) }}>
          <color attach="background" args={["#050403"]} />
          <CameraAt pos={c.pos} target={c.target} fov={c.fov} roll={c.roll} />
          <Walls f={f} atlas={atlas} />
          <Backdrop f={f} />
          <Dust f={f} />
          <Post strength={lerp(0.45, 0.85, prog(f, 260, 420))} radius={0.5} threshold={0.32} prev={f > 0 ? cPrev : null}
            rays={{ world: GLOW, amount: 4.2 * easeInOut(prog(f, 330, 640)) * (1 - prog(f, 1150, 1190)), threshold: 0.16, decay: 0.968,
              tint: "#" + new THREE.Color("#ffc98f").lerp(new THREE.Color("#ff5a3a"), easeInOut(prog(f, VOID_A, VOID_B))).getHexString() }}
            dof={{ focus: lerp(c.pos.distanceTo(c.target), 900, easeInOut(prog(f, 300, 720))), range: lerp(70, 1400, easeInOut(prog(f, 300, 720))), blur: lerp(9, 4, prog(f, 300, 720)) }} />
        </ThreeCanvas>
      ) : null}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.7) 100%)" }} />
      {f >= 1010 ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: H / 2 - 110, textAlign: "center", opacity: slamOut,
          transform: `scale(${lerp(1.35, 1, easeOutExpo(slam))})` }}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 190, letterSpacing: "0.04em", color: "#f2efe8",
            textShadow: "0 0 30px rgba(255,120,60,0.55), 0 0 90px rgba(255,60,30,0.35)" }}>PROVE IT.</div>
        </div>
      ) : null}
      <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      <Subs f={f} lines={LINES} />
      <ArchiveCard f={f} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, fontFamily: FONT.ui }} />
    </AbsoluteFill>
  );
};

/* The coda: the opening camera move replayed backwards, at speed, out of the canyon and back to the one cell. Every
   record is VOID now except that one: the RUSH HOUR run from Act IV, its real replayed time, turning green. */
export const CODA_LEN = 480;

/** The last image: the primer's leaderboard row again, but for our own run, and its proof column turns from a video into
    a log that replays to the same fingerprint. Held sharp to the cut. */
const Payoff: React.FC<{ f: number; time: string }> = ({ f, time }) => {
  if (f < 296) return null;
  const on = prog(f, 296, 310), flip = prog(f, 340, 348);
  const cols = "110px 1fr 230px 600px";
  return (
    <>
    <div style={{ position: "absolute", inset: 0, background: `rgba(0,0,0,${(0.68 * on).toFixed(3)})` }} />
    <div style={{ position: "absolute", left: (W - 1500) / 2, top: H / 2 - 150, width: 1500, transform: `${kick(f, [340], 6)} scale(${lerp(1.04, 1, easeOutExpo(on))})` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", opacity: on }}>
        <Mono s={22} c={MW.orange} w={700} ls="0.32em">LEADERBOARD // RUSH HOUR</Mono>
        <div style={{ border: `2px solid ${MW.green}`, padding: "3px 14px 4px" }}><Mono s={20} c={MW.green} w={700} ls="0.28em">OUR TEST ROUTE</Mono></div>
      </div>
      <div style={{ height: 2, background: MW.orange, marginTop: 12, width: `${100 * easeOutExpo(on)}%`, opacity: 0.8 }} />
      <div style={{ display: "grid", gridTemplateColumns: cols, alignItems: "center", height: 112, marginTop: 16, paddingLeft: 28,
        background: flip > 0 ? "rgba(10,26,15,0.96)" : "rgba(8,9,10,0.94)", borderLeft: `5px solid ${flip > 0 ? MW.green : MW.amber}`,
        clipPath: `inset(0 ${100 - 100 * on}% 0 0)`, boxShadow: flip > 0 ? `0 0 60px ${MW.green}33` : "none" }}>
        <Mono s={46} c={MW.amber} w={700}>01</Mono>
        <Mono s={34} c={MW.text} w={700} ls="0.06em">OUR RUN</Mono>
        <Mono s={46} c={MW.text} w={700}>{time}</Mono>
        {flip <= 0 ? (
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 46, height: 34, border: `3px solid ${MW.red}`, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ width: 0, height: 0, borderLeft: `14px solid ${MW.red}`, borderTop: "9px solid transparent", borderBottom: "9px solid transparent" }} />
            </div>
            <Mono s={34} c={MW.red} w={700} ls="0.12em">VIDEO</Mono>
          </div>
        ) : (
          <div style={{ transform: `scale(${lerp(1.3, 1, easeOutExpo(flip))})`, transformOrigin: "0% 50%" }}>
            <Mono s={30} c={MW.green} w={700} ls="0.06em">LOG 94853AFC = 94853AFC</Mono>
            <Mono s={20} c={MW.green} w={700} ls="0.4em" style={{ marginTop: 6 }}>VERIFIED BY REPLAY</Mono>
          </div>
        )}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: cols, marginTop: 10, paddingLeft: 28, opacity: on * 0.9 }}>
        {["RANK", "RUNNER", "TIME", "PROOF"].map((h) => <Mono key={h} s={16} c={MW.dim} ls="0.3em">{h}</Mono>)}
      </div>
    </div>
    </>
  );
};
const RUN_S = 4892 / 60;                                          // proof.json replay.time_frames
const CODA_LINES: Line[] = [{ at: 250, len: 200, who: "Handler", text: "Don't trust the video. Check the run." }];
export const Coda: React.FC = () => {
  const f = useCurrentFrame();
  const atlas = useGlyphAtlas();
  const foAt = (x: number) => lerp(1000, 60, prog(x, 8, 390));      // the opening's own frame, running backwards
  const fo = foAt(f);
  const c = camAt(fo);
  const cPrev = camAt(foAt(f - 0.5));
  const heroT = Math.min(RUN_S, RUN_S - 1.2 + Math.max(0, f - 98) / 60);
  const green = prog(f, 180, 188);
  const dark = clamp((f - 440) / 36);
  const fmt = `${Math.floor(RUN_S / 60)}:${(RUN_S % 60).toFixed(2).padStart(5, "0")}`;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {atlas ? (
        <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0, opacity: clamp(f / 10), transform: kick(f, [180], 6) }}>
          <color attach="background" args={["#050403"]} />
          <CameraAt pos={c.pos} target={c.target} fov={c.fov} roll={c.roll} />
          <Walls f={fo} atlas={atlas} coda={{ heroT, green, dark }} />
          <Backdrop f={fo} coda={{ dark }} />
          <Dust f={fo} />
          <Post strength={lerp(0.85, 0.5, prog(fo, 420, 260))} radius={0.5} threshold={0.32} prev={f > 0 ? cPrev : null}
            rays={green > 0 && fo < 420 ? { world: heroAt(fo), amount: green * lerp(1.2, 3.6, prog(fo, 300, 720)), tint: "#9dffb8", threshold: 0.2, decay: 0.962 }
              : { world: GLOW, amount: 3.4, tint: "#ff5a3a", threshold: 0.16, decay: 0.968 }}
            dof={{ focus: lerp(c.pos.distanceTo(c.target), 900, easeInOut(prog(fo, 300, 720))), range: lerp(70, 1400, easeInOut(prog(fo, 300, 720))), blur: lerp(9, 4, prog(fo, 300, 720)) }} />
        </ThreeCanvas>
      ) : null}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.7) 100%)" }} />
      <div style={{ position: "absolute", right: 70, top: BAR + 34, opacity: f < 380 && f % 30 < 20 ? 1 : 0 }}>
        <Mono s={18} c={MW.text} w={700} ls="0.3em">{"<< REPLAY"}</Mono>
      </div>
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: dark * 0.85 }} />
      <Payoff f={f} time={fmt} />
      <Subs f={f} lines={CODA_LINES} />
    </AbsoluteFill>
  );
};

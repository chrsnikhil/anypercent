import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { useTexture } from "../three/useAsset";
import { clamp, easeIn, easeInOut, easeOut, easeOutExpo, lerp, prog, rnd } from "../util";
import { BAR, Bars, CameraAt, Card, H, kick, Line, Mono, MW, Post, Row, Slate, Stamp, Subs, W } from "./common";

/* Act II, how records break. Three surreal vignettes, one per attack, each tied back to a case in the dossier:
   SPLICED (a filmstrip of a real run is cut and re-joined), MODDED (twelve dice in slow motion, all sixes),
   SLOWED (the game's clock melts over a ledge while the wall clock keeps time). */

export const BREAKS_SLOW = 1.25;                                       // the act's own clock runs at 1/1.25 of the film's
export const BREAKS_LEN = Math.round(1340 * BREAKS_SLOW);
const S = { lead: [0, 50], spliced: [50, 430], modded: [430, 810], slowed: [810, 1190], sum: [1190, 1340] } as const;
const shotOf = (f: number) => (Object.keys(S) as (keyof typeof S)[]).find((k) => f >= S[k][0] && f < S[k][1]) ?? "sum";
const LINES: Line[] = [
  { at: 70, len: 300, who: "Handler", text: "Splice two attempts together, and the video looks like one run." },
  { at: 450, len: 300, who: "Handler", text: "Mod the game to change the odds, and the video still looks fair." },
  { at: 830, len: 300, who: "Handler", text: "Or slow the game down, and play the video back at full speed." },
  { at: 1200, len: 135, who: "Handler", text: "Video can't tell which. So we stopped trusting video." },
];
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const vUvVert = "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";

/* ---------------- SPLICED ---------------- */
const FR = 34, FW = 52, FH = 40, CUT_A = 13, CUT_B = 22;            // frames CUT_A..CUT_B-1 are cut out
const filmFrag = /* glsl */ `
  uniform sampler2D uAtlas; uniform float uFrame; uniform float uAmt; uniform float uGrey; uniform float uT;
  varying vec2 vUv;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  void main(){
    vec2 p = vUv * vec2(${FW.toFixed(1)}, ${FH.toFixed(1)});
    vec3 c = vec3(0.012, 0.008, 0.006);                                 // the film base
    bool hole = (p.y < 3.4 || p.y > ${(FH - 3.4).toFixed(1)}) && fract(p.x / 6.5) > 0.3 && fract(p.x / 6.5) < 0.7
      && abs(p.y - (p.y < 20.0 ? 1.7 : ${(FH - 1.7).toFixed(1)})) < 1.1;
    if (hole) c = vec3(1.0, 0.72, 0.42) * 0.9;                           // the light table shows through the sprockets
    vec2 q = (p - vec2(2.0, 5.0)) / vec2(${(FW - 4).toFixed(1)}, ${(FH - 10).toFixed(1)});
    if (q.x > 0.0 && q.x < 1.0 && q.y > 0.0 && q.y < 1.0) {
      float fr = floor(uFrame), col = mod(fr, 20.0), row = floor(fr / 20.0);
      vec3 img = texture2D(uAtlas, vec2((col + q.x) / 20.0, 1.0 - (row + 1.0 - q.y) / 18.0)).rgb;
      img = mix(img, vec3(dot(img, vec3(0.3, 0.59, 0.11))), uGrey);
      img *= vec3(1.08, 0.96, 0.82);                                     // warm print
      img += (hash(p + uT) - 0.5) * 0.06;
      c = img * 1.25;
    }
    gl_FragColor = vec4(c * uAmt, 1.0);
  }`;
const Film: React.FC<{ f: number; atlas: THREE.Texture }> = ({ f, atlas }) => {
  const frames = useMemo(() => Array.from({ length: FR }, (_, i) => {
    const m = new THREE.ShaderMaterial({ vertexShader: vUvVert, fragmentShader: filmFrag, side: THREE.DoubleSide,
      uniforms: { uAtlas: { value: atlas }, uFrame: { value: (i * 10) % 360 }, uAmt: { value: 1 }, uGrey: { value: 0 }, uT: { value: 0 } } });
    return new THREE.Mesh(new THREE.PlaneGeometry(FW, FH), m);
  }), [atlas]);
  const t = f - S.spliced[0];
  const cut = prog(t, 150, 158);                                          // the laser cut
  const lift = easeInOut(prog(t, 160, 250));
  const close = easeInOut(prog(t, 215, 290));
  frames.forEach((m, i) => {
    const mid = i >= CUT_A && i < CUT_B;
    let x = (i - FR / 2) * FW;
    if (i >= CUT_B) x -= close * (CUT_B - CUT_A) * FW;
    const wave = (u: number) => Math.sin(u * 0.012 + t * 0.01) * 26;
    let y = 0, z = wave(x), rx = 0, rz = 0;
    if (mid) {
      const k = (i - CUT_A) / (CUT_B - CUT_A);
      z -= easeIn(lift) * (150 + 60 * Math.sin(k * Math.PI)) - lift * 20;   // the cut-out frames fall away into the dark
      y += lift * (60 + 40 * k);
      rx = lift * (0.35 + rnd(i, 1) * 0.5);
      rz = lift * (rnd(i, 2) - 0.5) * 0.8;
    }
    m.position.set(x, y, z);
    m.rotation.set(Math.PI / 2 + rx, 0, rz + Math.atan(Math.cos(x * 0.012 + t * 0.01) * 26 * 0.012));    // follow the strip's slope
    const u = (m.material as THREE.ShaderMaterial).uniforms;
    u.uAmt.value = mid ? 1 - 0.85 * lift : 1;
    u.uGrey.value = mid ? lift : 0;
    u.uT.value = f;
  });
  // the blade: a red light line at each cut, and a white seam flash where the ends meet
  const cutX = (i: number) => (i - FR / 2 - 0.5) * FW;
  const seam = prog(t, 286, 292) * (1 - prog(t, 292, 330));
  return (
    <>
      {frames.map((m, i) => <primitive key={i} object={m} />)}
      {[CUT_A, CUT_B].map((i) => (
        <mesh key={i} position={[cutX(i), 0, Math.sin(cutX(i) * 0.012 + t * 0.01) * 26]} visible={t > 140 && t < 175}>
          <boxGeometry args={[0.8, 2, 140 * cut]} />
          <meshBasicMaterial color={new THREE.Color(6, 0.5, 0.3)} />
        </mesh>
      ))}
      <mesh position={[cutX(CUT_A), 0, Math.sin(cutX(CUT_A) * 0.012 + t * 0.01) * 26]} visible={seam > 0}>
        <boxGeometry args={[2.5 * seam + 0.1, 1, FH + 10]} />
        <meshBasicMaterial color={new THREE.Color(5, 4, 3.2)} />
      </mesh>
    </>
  );
};

/* ---------------- MODDED ---------------- */
const DICE = 12;
const pipTex = (n: number) => {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  g.fillStyle = "#c01a28";                                             // casino dice: translucent red, painted white pips
  g.fillRect(0, 0, 256, 256);
  const P: Record<number, [number, number][]> = { 1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]], 4: [[-1, -1], [1, -1], [-1, 1], [1, 1]],
    5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]], 6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]] };
  g.fillStyle = "#f4f0e6";
  for (const [x, y] of P[n]) { g.beginPath(); g.arc(128 + x * 64, 128 + y * 64, n === 1 ? 34 : 24, 0, Math.PI * 2); g.fill(); }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
};
const dieDrop = (i: number) => ({ at: 40 + i * 16 + Math.floor(rnd(i, 7) * 10), x: (i % 4 - 1.5) * 54 + (rnd(i, 1) - 0.5) * 26,
  y: (Math.floor(i / 4) - 1) * 54 + (rnd(i, 2) - 0.5) * 26, yaw: (rnd(i, 3) - 0.5) * 1.2 });
const Dice: React.FC<{ f: number }> = ({ f }) => {
  const { geo, mats } = useMemo(() => {
    // BoxGeometry faces: +x, -x, +y, -y, +z, -z; with +z up, the six is on top and opposite faces add to seven
    const order = [3, 4, 2, 5, 6, 1];
    return { geo: new THREE.BoxGeometry(22, 22, 22), mats: order.map((n) => new THREE.MeshPhysicalMaterial({ map: pipTex(n), roughness: 0.1, metalness: 0,
      transmission: 0.5, thickness: 18, ior: 1.49, clearcoat: 1, clearcoatRoughness: 0.06,
      attenuationColor: new THREE.Color("#6e0410"), attenuationDistance: 14 })) };
  }, []);
  const t = f - S.modded[0];
  return (
    <>
      {Array.from({ length: DICE }, (_, i) => {
        const d = dieDrop(i);
        const fall = prog(t, d.at - 70, d.at);                            // slow motion: a long fall
        const after = t - d.at;
        const bounce = after > 0 ? 14 * Math.exp(-after / 9) * Math.abs(Math.sin(after * 0.22)) : 0;
        const z = 11 + lerp(420, 0, easeIn(fall)) + bounce;
        const final = new THREE.Quaternion().setFromAxisAngle(V(0, 0, 1), d.yaw);
        const start = new THREE.Quaternion().setFromEuler(new THREE.Euler(rnd(i, 4) * 6, rnd(i, 5) * 6, rnd(i, 6) * 6));
        const spinAx = V(rnd(i, 8) - 0.5, rnd(i, 9) - 0.5, 0.2).normalize();
        const settle = easeOut(clamp((t - (d.at - 70)) / 80));
        const q = start.clone().slerp(final, settle).multiply(new THREE.Quaternion().setFromAxisAngle(spinAx, (1 - settle) * 7));
        if (t < d.at - 70) return null;
        return <mesh key={i} geometry={geo} material={mats} position={[d.x, d.y, z]} quaternion={q} />;
      })}
    </>
  );
};

/* ---------------- SLOWED ---------------- */
const CLOCK_R = 150, LEDGE_Y = -10;
const clockVert = /* glsl */ `
  uniform float uMelt; uniform float uT; varying vec2 vUv; varying float vShade;
  void main(){
    vUv = uv;
    vec3 p = position;                                                  // the face lies flat on the ledge, z up
    float d = ${LEDGE_Y.toFixed(1)} - p.y;                               // how far past the ledge's edge
    vShade = 1.0;
    if (d > 0.0 && uMelt > 0.001) {
      float R = 70.0 / uMelt, a = d / R;
      float sag = 1.0 + 0.25 * sin(p.x * 0.03 + uT * 0.6) * uMelt;
      if (a < 1.5708) { p.y = ${LEDGE_Y.toFixed(1)} - R * sin(a); p.z = -R * (1.0 - cos(a)) * sag; }
      else { p.y = ${LEDGE_Y.toFixed(1)} - R; p.z = (-R - (d - R * 1.5708)) * sag; }
      p.x *= 1.0 - 0.12 * uMelt * clamp(d / 120.0, 0.0, 1.0);
      vShade = 1.0 - 0.45 * clamp(a / 1.5708, 0.0, 1.0);
    }
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }`;
const clockFrag = /* glsl */ `
  uniform float uHand; uniform float uRed; varying vec2 vUv; varying float vShade;
  void main(){
    vec2 p = (vUv - 0.5) * 2.0;
    float r = length(p);
    if (r > 1.0) discard;
    float ang = atan(p.x, p.y);                                         // 0 at twelve, clockwise
    vec3 face = vec3(0.86, 0.82, 0.74);
    vec3 c = face;
    c = mix(c, vec3(0.1, 0.09, 0.08), smoothstep(0.93, 0.94, r));     // the bezel
    float tick = abs(fract(ang / 6.28318 * 60.0 + 0.5) - 0.5);
    float major = abs(fract(ang / 6.28318 * 12.0 + 0.5) - 0.5);
    if (r > 0.78 && r < 0.9 && tick < 0.06) c = vec3(0.12);
    if (r > 0.7 && r < 0.9 && major < 0.035) c = vec3(0.05);
    // the second hand
    vec2 h = vec2(sin(uHand), cos(uHand));
    float along = dot(p, h), across = abs(p.x * h.y - p.y * h.x);
    vec3 hand = mix(vec3(0.94, 0.45, 0.12), vec3(0.85, 0.15, 0.1), uRed);
    if (along > -0.15 && along < 0.86 && across < 0.012 + 0.01 * (1.0 - along)) c = hand;
    if (r < 0.045) c = hand;
    gl_FragColor = vec4(c * vShade, 1.0);
  }`;
const Clock: React.FC<{ f: number }> = ({ f }) => {
  const mat = useMemo(() => new THREE.ShaderMaterial({ vertexShader: clockVert, fragmentShader: clockFrag, side: THREE.DoubleSide,
    uniforms: { uMelt: { value: 0 }, uT: { value: 0 }, uHand: { value: 0 }, uRed: { value: 0 } } }), []);
  const t = f - S.slowed[0];
  const { game } = slowClock(t);
  mat.uniforms.uMelt.value = easeInOut(prog(t, 60, 300)) * 1.6;
  mat.uniforms.uT.value = t / 60;
  mat.uniforms.uHand.value = game / 6 * Math.PI * 2;                   // one turn every six game seconds
  mat.uniforms.uRed.value = prog(t, 200, 280);
  return (
    <>
      <mesh material={mat} position={[0, 0, 0.6]}><planeGeometry args={[CLOCK_R * 2, CLOCK_R * 2, 90, 90]} /></mesh>
      <mesh position={[0, 300 + LEDGE_Y, -30]}><boxGeometry args={[900, 600, 60]} /><meshStandardMaterial color="#0c0907" roughness={0.6} /></mesh>
    </>
  );
};
/** Game time runs at the wall clock's pace, then slows to half; the video, sped back up, shows game time. */
const slowClock = (t: number) => {
  const wall = Math.max(0, t) / 60;
  const r = (x: number) => 1 - 0.5 * easeInOut(clamp((x - 1) / 3));     // the game's speed, against the wall
  let game = 0;
  for (let i = 0; i < Math.max(0, t); i++) game += r(i / 60) / 60;
  return { wall, game, rate: r(wall) };
};

/* ---------------- the scene ---------------- */
const camFor = (f: number) => {
  const sh = shotOf(f);
  if (sh === "spliced") {
    const t = prog(f, S.spliced[0], S.spliced[1]);
    const k = easeInOut(prog(f, S.spliced[0] + 120, S.spliced[0] + 300));
    return { pos: V(lerp(-40, -300, k) - 40, lerp(-300, -250, k), lerp(130, 95, k)), target: V(lerp(0, -234, k), 40 * k, lerp(10, 0, k)), fov: 34 };
  }
  if (sh === "modded") {
    const t = prog(f, S.modded[0], S.modded[1]);
    return { pos: V(lerp(170, 130, t), lerp(-300, -250, t), lerp(110, 95, t)), target: V(0, 0, 30), fov: 34 };
  }
  const t = prog(f, S.slowed[0], S.slowed[1]);
  return { pos: V(lerp(-90, -50, t), lerp(-480, -420, t), lerp(220, 170, t)), target: V(0, 10, -60), fov: 32 };
};
const Scene: React.FC<{ f: number; atlas: THREE.Texture; slow: number }> = ({ f, atlas, slow }) => {
  const { gl, scene } = useThree();
  useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
  }, [gl, scene]);
  scene.environmentIntensity = shotOf(f) === "modded" ? 0.3 : 1;
  const sh = shotOf(f);
  const c = camFor(f);
  return (
    <>
      <color attach="background" args={[sh === "slowed" ? "#0a0705" : "#030304"]} />
      <CameraAt pos={c.pos} target={c.target} fov={c.fov} up={V(0, 0, 1)} />
      <ambientLight intensity={0.15} />
      <directionalLight position={[-200, -400, 500]} intensity={1.8} color="#fff1df" />
      <directionalLight position={[300, 400, 200]} intensity={1.0} color="#7cc4ff" />
      {sh === "spliced" ? <Film f={f} atlas={atlas} /> : null}
      {sh === "modded" ? (
        <>
          <Dice f={f} />
          <mesh position={[0, 0, 0]}><planeGeometry args={[2000, 2000]} /><meshStandardMaterial color="#0b2a1b" roughness={0.95} metalness={0} envMapIntensity={0.1} /></mesh>
          <spotLight position={[0, -40, 520]} angle={0.42} penumbra={0.8} intensity={2.6} decay={0} color="#ffe2bf" />
        </>
      ) : null}
      {sh === "slowed" ? (
        <>
          <Clock f={f} />
          <spotLight position={[-60, -260, 420]} angle={0.5} penumbra={0.8} intensity={6} decay={0} color="#ffd2a0" />
        </>
      ) : null}
      <Post strength={0.7} radius={0.5} threshold={sh === "modded" ? 1.6 : 1.1}
        rays={sh === "spliced" ? { world: V((CUT_A - FR / 2 - 0.5) * FW, 0, 0), amount: 2.4 * prog(f - S.spliced[0], 284, 292) * (1 - prog(f - S.spliced[0], 292, 340)), tint: "#fff1dc", threshold: 0.5 } : null}
        dof={{ focus: c.pos.distanceTo(sh === "modded" ? V(0, 0, 25) : c.target), range: sh === "spliced" ? 110 : 130, blur: sh === "slowed" ? 8 : 10 }}
        prev={shotOf(f - 0.5 / slow) === sh ? { ...camFor(f - 0.5 / slow), up: V(0, 0, 1) } : null} />
    </>
  );
};

/** After the splice, name the two halves and the seam, so a newcomer sees two runs passed off as one. */
const SpliceTags: React.FC<{ f: number }> = ({ f }) => {
  const t = f - S.spliced[0];
  const k = prog(t, 296, 310);
  if (k <= 0) return null;
  const c = camFor(f);
  const cam = new THREE.PerspectiveCamera(c.fov, W / H, 1, 20000);
  cam.position.copy(c.pos);
  cam.up.set(0, 0, 1);
  cam.lookAt(c.target);
  cam.updateMatrixWorld();
  const close = easeInOut(prog(t, 215, 290));
  const at = (i: number) => {
    let x = (i - FR / 2) * FW;
    if (i >= CUT_B) x -= close * (CUT_B - CUT_A) * FW;
    const p = V(x, 0, Math.sin(x * 0.012 + t * 0.01) * 26 + 22).project(cam);   // just above the frame's top edge
    return { x: (p.x + 1) / 2 * W, y: (1 - p.y) / 2 * H };
  };
  const a = at(CUT_A - 3), b = at(CUT_B + 2), seam = at(CUT_A - 0.5);              // after closing, the seam is at cut A
  const tag = (p: { x: number; y: number }, text: string, col: string) => (
    <div style={{ position: "absolute", left: p.x - 120, top: p.y - 92, width: 240, textAlign: "center", opacity: k }}>
      <Mono s={20} c={col} w={700} ls="0.25em">{text}</Mono>
      <div style={{ width: 2, height: 62, background: col, margin: "6px auto 0" }} />
    </div>
  );
  return (
    <>
      {tag(a, "ATTEMPT 1", MW.amber)}
      {tag(b, "ATTEMPT 2", MW.blue)}
      <div style={{ position: "absolute", left: seam.x - 100, top: seam.y - 110, width: 200, textAlign: "center", opacity: k }}>
        <Mono s={16} c={MW.red} w={700} ls="0.3em">SPLICE</Mono>
      </div>
    </>
  );
};

const Overlay: React.FC<{ f: number; part: string }> = ({ f, part }) => {
  const sh = shotOf(f);
  const L = 70, T = BAR + 30;
  if (sh === "lead") return <Slate f={f} part={part} title="HOW RECORDS BREAK" len={S.lead[1]} />;
  if (sh === "spliced") {
    const t = f - S.spliced[0];
    return (
      <>
        <Card f={f} at={S.spliced[0] + 14} x={L} y={T} w={470} h={150} head="METHOD 01 // SPLICE">
          {part === "PART I" ? null : <Row k="SEEN IN" v="ID-03 // ID-05" />}
          <Row k="CUT AT" v={t > 158 ? `FRAME ${String(CUT_A * 10).padStart(4, "0")}` : "..."} c={MW.red} />
          <Row k="RESUMES AT" v={t > 290 ? `FRAME ${String(CUT_B * 10).padStart(4, "0")}` : "..."} c={MW.red} />
        </Card>
        <SpliceTags f={f} />
        <Stamp f={f} at={S.spliced[0] + 300} text="SPLICED" col={MW.red} y={H / 2 + 150} s={110} sub="TWO ATTEMPTS // ONE VIDEO" />
      </>
    );
  }
  if (sh === "modded") {
    const t = f - S.modded[0];
    const landed = Array.from({ length: DICE }, (_, i) => dieDrop(i).at).filter((a) => t > a + 8).length;
    return (
      <>
        <Card f={f} at={S.modded[0] + 14} x={L} y={T} w={470} h={150} head="METHOD 02 // MOD">
          {part === "PART I" ? null : <Row k="SEEN IN" v="ID-02" />}
          <Row k="ROLLS" v={String(landed).padStart(2, "0")} />
          <Row k="SIXES" v={String(landed).padStart(2, "0")} c={landed > 3 ? MW.red : MW.text} />
        </Card>
        <Card f={f} at={S.modded[0] + 255} x={W - 540} y={T} w={470} h={110} head="ODDS BY LUCK ALONE" accent={MW.red} headCol={MW.red}>
          <Mono s={30} c={MW.text} w={700}>1 IN {Math.pow(6, DICE).toLocaleString("en-US")}</Mono>
        </Card>
        <Stamp f={f} at={S.modded[0] + 300} text="MODDED" col={MW.red} y={H / 2 + 150} s={110} sub="THE GAME ITSELF WAS CHANGED" />
      </>
    );
  }
  if (sh === "slowed") {
    const t = f - S.slowed[0];
    const c = slowClock(t);
    const fmt = (s: number) => `0:${s.toFixed(2).padStart(5, "0")}`;
    return (
      <>
        <Card f={f} at={S.slowed[0] + 14} x={L} y={T} w={470} h={150} head="METHOD 03 // SLOWDOWN">
          {part === "PART I" ? null : <Row k="SEEN IN" v="ID-04" />}
          <Row k="GAME CLOCK" v={fmt(c.game)} c={MW.amber} />
          <Row k="WALL CLOCK" v={fmt(c.wall)} />
        </Card>
        <Card f={f} at={S.slowed[0] + 200} x={W - 540} y={T} w={470} h={110} head="GAME SPEED" accent={MW.red} headCol={MW.red}>
          <Mono s={30} c={c.rate < 0.75 ? MW.red : MW.text} w={700}>{(c.rate * 100).toFixed(0)}% OF REAL TIME</Mono>
        </Card>
        <Stamp f={f} at={S.slowed[0] + 300} text="SLOWED" col={MW.red} y={H / 2 + 150} s={110} sub="PLAYED SLOW // SHOWN AT FULL SPEED" />
      </>
    );
  }
  const t = f - S.sum[0];
  // the three methods side by side, each its own stamped frame (public/breaks_tri_N.jpg, cut from this act's render)
  const PW = 590, PH = Math.round(590 * 475 / 1080), GAP = 24, X0 = (W - (3 * PW + 2 * GAP)) / 2, Y0 = H / 2 - PH / 2 - 20;
  const seen = part === "PART I" ? ["", "", ""] : ["SEEN IN ID-03 // ID-05", "SEEN IN ID-02", "SEEN IN ID-04"];
  return (
    <>
      <Mono s={15} c={MW.orange} w={700} ls="0.3em" style={{ position: "absolute", left: X0, top: Y0 - 44, opacity: t > 4 && !(t > 6 && t < 8) ? 1 : 0 }}>
        METHODS // THREE WAYS A VIDEO LIES
      </Mono>
      {[0, 1, 2].map((k) => {
        const at = 6 + k * 8;
        const g = Math.min(1, Math.ceil(prog(t, at, at + 6) * 4) / 4);
        const wipe = prog(t, at + 7, at + 17);
        const x = X0 + k * (PW + GAP);
        return (
          <div key={k} style={{ position: "absolute", left: x, top: Y0, width: PW, height: PH + 40, opacity: t >= at ? 1 : 0 }}>
            <div style={{ position: "absolute", left: 0, top: 0, width: PW * g, height: PH * g, background: "#050505", borderLeft: `3px solid ${MW.red}` }} />
            <div style={{ position: "absolute", left: 3, top: 0, width: PW - 3, height: PH, overflow: "hidden", clipPath: `inset(0 0 ${100 - 100 * wipe}% 0)` }}>
              <Img src={staticFile(`breaks_tri_${k + 1}.jpg`)} style={{ width: "100%", height: "100%", objectFit: "cover",
                transform: `scale(${1 + 0.035 * prog(t, 0, 150)})` }} />
            </div>
            <Mono s={14} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: 3, top: PH + 14, opacity: wipe }}>{seen[k]}</Mono>
          </div>
        );
      })}
    </>
  );
};

/** part: the act card's label (PART I in the submission cut, which drops the dossier). slow: the act's clock (the
    submission cut plays it at 1, its v3 pace). */
export const Breaks: React.FC<{ part?: string; slow?: number }> = ({ part = "PART II", slow = BREAKS_SLOW }) => {
  const f = useCurrentFrame() / slow;
  const atlas = useTexture(staticFile("game/MDGP_atlas.png"));
  if (atlas) { atlas.magFilter = THREE.NearestFilter; atlas.minFilter = THREE.LinearFilter; atlas.generateMipmaps = false; }
  const sh = shotOf(f);
  const cut = [S.spliced[0], S.modded[0], S.slowed[0], S.sum[0]].find((c) => f >= c && f < c + 3);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {atlas && sh !== "lead" && sh !== "sum" ? (
        <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }}
          style={{ position: "absolute", inset: 0, transform: kick(f, [S.spliced[0] + 300, S.modded[0] + 300, S.slowed[0] + 300, S.spliced[0] + 290]) }}>
          <Scene f={f} atlas={atlas} slow={slow} />
        </ThreeCanvas>
      ) : null}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.7) 100%)" }} />
      <Overlay f={f} part={part} />
      <Subs f={f} lines={LINES} />
      {cut !== undefined ? <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: 0.08 * (3 - (f - cut)) }} /> : null}
      <Bars />
    </AbsoluteFill>
  );
};

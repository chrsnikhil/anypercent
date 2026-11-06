import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { AbsoluteFill, staticFile, useCurrentFrame } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import PLAYER from "../../public/game/RUSH_player.json";
import PROOF from "../../public/proof.json";
import TL from "../timeline.json";
import { applyPose, asmMatrix, buildParts, clip, FLIP, META_, partCentre, partPose, PartObj, section } from "../three/consoleModel";
import { useBuffer, useTexture } from "../three/useAsset";
import { clamp, easeInOut, easeOut, lerp, prog, rnd } from "../util";
import { BAR, Bars, CameraAt, Card, Dof, H, kick, Line, Mono, MW, Post, Row, Slate, Stamp, Subs, W } from "./common";

/* Act IV, the proof. The console plays a real run (real ROM frames). Its inputs stream out of it as a ribbon of light,
   one column per frame, into a log; an x-ray twin replays the log to the same hash: VERIFIED. One bit of the log is
   flipped: REJECTED. The seed is rolled on the device. Every number on screen comes from public/proof.json, which
   prep/make_proof.py takes from the real log and the real replay tool. */

export const PROOF_SLOW = 1.2;                                         // the act's clock runs at 1/1.2 of the film's
export const PROOF_LEN = Math.round(2160 * PROOF_SLOW);
const S = {
  lead: [0, 50], screen: [50, 260], wide: [260, 500], track: [500, 740], ghost: [740, 1000], verdict: [1000, 1200],
  tamper: [1200, 1420], reject: [1420, 1640], seed: [1640, 1880], gap: [1880, 2160],
} as const;
const CUTS = Object.values(S).map((s) => s[0]).filter((c) => c !== S.wide[0]);   // screen -> wide is one move, not a cut
const camShot = (f: number) => { const sh = shotOf(f); return sh === "screen" || sh === "wide" ? "oner" : sh; };
const shotOf = (f: number) => (Object.keys(S) as (keyof typeof S)[]).find((k) => f >= S[k][0] && f < S[k][1]) ?? "gap";

const LINES: Line[] = [
  { at: 70, len: 185, who: "Handler", text: "A full run of Rush Hour, logged by the game itself." },
  { at: 280, len: 215, who: "Handler", text: "Every button, every frame, written down as it is played." },
  { at: 515, len: 220, who: "Handler", text: `The whole run, every frame of it, fits in ${PROOF.log_bytes} bytes.` },
  { at: 760, len: 235, who: "Handler", text: "Hand that log to anyone. They replay it, with the same rules." },
  { at: 1020, len: 175, who: "Handler", text: "The fingerprints match: the run is exactly what those inputs produce." },
  { at: 1220, len: 195, who: "Handler", text: `Now change a single bit of the log. Byte ${PROOF.tampered_byte}.` },
  { at: 1440, len: 195, who: "Handler", text: "The fingerprint changes. A modded game fails too; a spliced log desyncs." },
  { at: 1660, len: 215, who: "Handler", text: "A fresh seed every launch, but a rigged console could pick its own." },
  { at: 1900, len: 250, who: "Handler", text: "Not proven yet: who claims it, when, and at what pace. That is Mumbai." },
];

const KEYS = ["A", "B", "SEL", "STA", "RIGHT", "LEFT", "UP", "DOWN", "R", "L"];
const keyName = (k: number) => KEYS.filter((_, i) => (k >> i) & 1).join(" + ") || "NONE";
const IN = PROOF.inputs_window as number[];

/** The run on screen: global frame g of the footage loop, which wraps at the cut into the wide shot. */
const gFrame = (f: number) => f - S.wide[0];
const footage = (g: number) => ((g % 360) + 360) % 360;
/** The footage frame as an index into per-frame data: the act's clock is slowed, so g is fractional. */
const fi = (g: number) => Math.floor(footage(g));

// layout, in the CAD's millimetres: console A face up at the origin, the ribbon to its right, the twin B beyond it
const COLS = 240, STEP = 5, RIB_X = 214, RIB_Y = 62.5, BX = RIB_X + COLS * STEP + 14;
const FACE_UP = asmMatrix(FLIP[1]);
const AT_B = new THREE.Matrix4().makeTranslation(BX, 0, 0).multiply(FACE_UP);
const MID_A = new THREE.Vector3(101, 62.5, 24), MID_B = new THREE.Vector3(BX + 101, 62.5, 24);
const SCREEN = (() => {
  const [x0, x1, y0, y1] = META_.screen.rect;
  return { w: x1 - x0, h: y1 - y0, c: new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, 48 - META_.screen.glassZ + 0.35) };
})();
const DONE = TL.shots.end[0];                                       // every part fitted

const screenFrag = /* glsl */ `
  uniform sampler2D uAtlas; uniform float uFrame; uniform vec3 uTint; uniform float uTintAmt; uniform float uOn; uniform float uTear;
  varying vec2 vUv;
  void main() {
    vec2 uv = vUv;
    uv.x += uTear * (step(0.5, fract(uv.y * 9.0 + uFrame * 0.37)) - 0.5) * 0.06;
    float lx = (uv.x - 0.05) / 0.9;                                    // the 3:2 game inside the 5:3 panel
    vec3 c = vec3(0.0);
    if (lx >= 0.0 && lx <= 1.0) {
      float fr = floor(uFrame), col = mod(fr, 20.0), row = floor(fr / 20.0);
      c = texture2D(uAtlas, vec2((col + lx) / 20.0, 1.0 - (row + 1.0 - uv.y) / 18.0)).rgb;
      vec2 px = vec2(lx * 240.0, uv.y * 160.0);
      c *= 0.8 + 0.2 * smoothstep(0.0, 0.2, fract(px.x)) * smoothstep(0.0, 0.2, fract(px.y));
      // in macro, the panel's own RGB stripes resolve: how many screen pixels one game pixel covers decides how much
      float big = smoothstep(5.0, 16.0, 1.0 / max(length(fwidth(px)), 1e-4));
      vec2 sp = fract(px * vec2(3.0, 1.0));
      float k = fract(px.x) * 3.0;
      vec3 stripe = vec3(1.0 - smoothstep(0.85, 1.0, k), smoothstep(0.85, 1.0, k) * (1.0 - smoothstep(1.85, 2.0, k)), smoothstep(1.85, 2.0, k));
      float cell = smoothstep(0.0, 0.12, sp.x) * smoothstep(1.0, 0.88, sp.x) * smoothstep(0.0, 0.08, sp.y) * smoothstep(1.0, 0.92, sp.y);
      c = mix(c, c * (0.35 + 1.4 * stripe) * cell, big);
    }
    float l = dot(c, vec3(0.3, 0.59, 0.11));
    c = mix(c, uTint * (0.15 + 1.2 * l), uTintAmt);
    gl_FragColor = vec4(c * uOn * 1.15, 1.0);
  }`;
const screenMat = (atlas: THREE.Texture) => new THREE.ShaderMaterial({
  uniforms: { uAtlas: { value: atlas }, uFrame: { value: 0 }, uTint: { value: new THREE.Color(MW.ice) }, uTintAmt: { value: 0 }, uOn: { value: 1 }, uTear: { value: 0 } },
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
  fragmentShader: screenFrag,
});

/** The cameras, one per shot, all motivated: a locked-off creep in the briefing shots, a track along the ribbon. */
type Cam = { pos: THREE.Vector3; target: THREE.Vector3; fov: number; up?: THREE.Vector3; t?: number };
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const creep = (f: number, a: number, b: number, pos: THREE.Vector3, target: THREE.Vector3, rate = 0.0066 / 60) => {
  const k = 1 - Math.max(0, f - a) * rate * 1.6;                      // a linear push-in, MW3's measured rate (a touch more), from a
  return pos.clone().sub(target).multiplyScalar(k).add(target);
};
const camFor = (f: number): Cam => {
  const sh = shotOf(f);
  const s = S[sh];
  const t = prog(f, s[0], s[1]);
  switch (sh) {
    case "screen":
    case "wide":
      return onerCam(f);
    case "track": {
      // along the ribbon at half its speed, so it flows past; then a crane up and back that shows the whole line:
      // the console, the log in flight, and the twin waiting at the far end
      const x = lerp(330, 930, Math.min(t, 0.62) / 0.62 * 0.8 + 0.2 * clamp((t - 0.62) / 0.38));
      const k = easeInOut(clamp((t - 0.58) / 0.42));
      const pos = V(x - 40, RIB_Y - 125, 78 - 18 * Math.min(t, 0.6)).lerp(V(640, -1380, 1220), k);
      const target = V(x + 70, RIB_Y, 24).lerp(V(815, 62, 10), k);
      return { pos, target, fov: lerp(36, 30, k), t };
    }
    case "ghost": {
      const a = lerp(-0.95, -0.55, t);
      const r = 330;
      const tg = MID_B.clone().add(V(-30, 0, 0));
      return { pos: V(tg.x + Math.cos(a) * r * 0.55 - 120, tg.y + Math.sin(a) * r, 230), target: tg, fov: 34 };
    }
    case "verdict": {
      const tg = MID_B.clone();
      return { pos: creep(f, s[0], s[1], V(BX + 101, 62.5 - 210, 330), tg), target: tg, fov: 30 };
    }
    case "tamper": {
      const tg = V(RIB_X + 92 * STEP, RIB_Y, 26);
      return { pos: creep(f, s[0], s[1], V(tg.x - 40, RIB_Y - 120, 70), tg, 0.02 / 60), target: tg, fov: 30 };
    }
    case "reject": {
      const tg = MID_B.clone();
      return { pos: creep(f, s[0], s[1], V(BX + 30, 62.5 - 260, 250), tg), target: tg, fov: 32 };
    }
    case "seed": {
      const tg = piCentre.clone();
      return { pos: creep(f, s[0], s[1], tg.clone().add(V(70, -110, 120)), tg, 0.02 / 60), target: tg, fov: 30 };
    }
    default: {
      const tg = MID_A.clone();
      return { pos: creep(f, S.gap[0], S.gap[1], V(-180, -300, 260), tg), target: tg, fov: 30 };
    }
  }
};
/** Part IV opens on one continuous move: a macro on the LCD's subpixels, an exponential pull back through the glass
    and off the console, then an arc out to the wide shot as the inputs stream away. */
/** Where the player is on the panel at frame f: the sprite tracked in the real footage (prep: public/game/RUSH_player.json,
    its shirt colour per frame, smoothed over half a second), as a point on the screen in the CAD's millimetres. */
const playerAt = (f: number) => {
  const g = footage(gFrame(f)), i = Math.floor(g), k = g - i, j = (i + 1) % 360;
  const x = lerp(PLAYER.x[i], PLAYER.x[j], k) / 240, y = lerp(PLAYER.y[i], PLAYER.y[j], k) / 160;
  return SCREEN.c.clone().add(V((0.05 + 0.9 * x - 0.5) * SCREEN.w, (0.5 - y) * SCREEN.h, 0));
};
const onerCam = (f: number): Cam => {
  const t = f - S.screen[0];
  const p1 = V(101, 82 - 120, 48 + 135), t1 = SCREEN.c.clone().add(V(0, -3, 0));
  const p2 = V(-60, -330, 210), t2 = V(330, 62, 18);
  if (t < 300) {
    // hold on the pixels (a slow drift), then pull out: distance grows exponentially, so it reads as one smooth rush
    const k = easeInOut(clamp((t - 70) / 230));
    const target = playerAt(f).lerp(t1, k);                           // the operator follows the runner, then lets go
    const dir0 = V(0, -0.12, 1).normalize(), dir1 = p1.clone().sub(t1).normalize();
    const dist = 24 * Math.pow(p1.distanceTo(t1) / 24, k);
    const pos = target.clone().add(dir0.lerp(dir1, k).normalize().multiplyScalar(dist));
    return { pos, target, fov: lerp(34, 30, k), t };
  }
  const k = easeInOut(clamp((t - 300) / 150));
  const pos = p1.clone().lerp(p2, k).add(V(-70, -40, 70).multiplyScalar(Math.sin(k * Math.PI)));
  return { pos: creep(f, S.screen[0] + 400, S.wide[1], pos, t1.clone().lerp(t2, k)), target: t1.clone().lerp(t2, k), fov: lerp(30, 34, k), t };
};

const piMeta = META_.parts.find((p) => p.name === "asm_pi_board")!;
const piCentre = partCentre(piMeta, DONE).applyMatrix4(FACE_UP);

const projector = (f: number) => {
  const c = camFor(f);
  const cam = new THREE.PerspectiveCamera(c.fov, W / H, 1, 20000);
  cam.position.copy(c.pos);
  cam.up.set(0, 0, 1);
  cam.lookAt(c.target);
  cam.updateMatrixWorld();
  return (v: THREE.Vector3) => {
    const p = v.clone().project(cam);
    return { x: (p.x + 1) / 2 * W, y: (1 - p.y) / 2 * H };
  };
};

/** The ribbon: one column per frame of play, a cell per button, lit when held. */
const Ribbon: React.FC<{ f: number }> = ({ f }) => {
  const mesh = useMemo(() => {
    const m = new THREE.InstancedMesh(new THREE.BoxGeometry(STEP * 0.78, 1.4, 3.9), new THREE.MeshBasicMaterial({ color: 0xffffff }), COLS * 10);
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(COLS * 10 * 3), 3);
    m.frustumCulled = false;
    return m;
  }, []);
  const sh = shotOf(f);
  const frozen = sh === "tamper" || sh === "reject";
  const G = frozen ? gFrame(S.tamper[0]) : gFrame(f);
  const flip = sh === "tamper" ? prog(f, S.tamper[0] + 70, S.tamper[0] + 80) : sh === "reject" ? 1 : 0;
  const o = new THREE.Object3D();
  const c = new THREE.Color();
  const hot = frozen ? 0.55 : 1;                                       // the close-ups need less light
  for (let j = 0; j < COLS; j++) {
    const g = G - j;
    const k = IN[fi(g)];
    const fade = Math.pow(1 - j / COLS, 0.6) * clamp(0.25 + 0.75 * (1 - Math.abs(j - COLS * 0.5) / (COLS * 0.6)));
    for (let r = 0; r < 10; r++) {
      const i = j * 10 + r;
      const on = (k >> r) & 1;
      const tampered = j === 92 && r === 2 && flip > 0;
      const wob = Math.sin(j * 0.09 - f * 0.05) * 3;
      o.position.set(RIB_X + j * STEP, RIB_Y + wob * 0.3, 3 + r * 4.9 + wob);
      o.scale.setScalar(tampered ? 1 + 0.6 * flip : 1);
      o.updateMatrix();
      mesh.setMatrixAt(i, o.matrix);
      if (tampered) c.setRGB(lerp(0.05, 5, flip), lerp(0.05, 0.35, flip), lerp(0.05, 0.2, flip));
      else if (on) c.setRGB(3.2 * fade * hot, 1.55 * fade * hot, 0.45 * fade * hot);
      else c.setRGB(0.022 * fade, 0.026 * fade, 0.034 * fade);
      mesh.setColorAt(i, c);
    }
  }
  mesh.instanceMatrix.needsUpdate = true;
  mesh.instanceColor!.needsUpdate = true;
  return <primitive object={mesh} />;
};

/** The x-ray look was tuned without bloom; under it, it needs to come down to stay a cold hologram. */
const dimXray = (p: PartObj, k: number) => {
  p.coreMat.opacity *= k;
  p.glowMat.opacity *= k * 0.7;
  p.ghostMat.opacity *= k;
  p.fillMat.uniforms.alpha.value *= k * 0.8;
};

/** A soft pool of light on an unlit ground, so the console sits on something without a glaring floor. */
const Pool: React.FC<{ x: number; k: number }> = ({ x, k }) => {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    uniforms: { uK: { value: 1 } }, transparent: true, depthWrite: false,
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `uniform float uK; varying vec2 vUv;
      void main(){ vec2 d = (vUv - 0.5) * 2.0; float r2 = dot(d, d);
        vec3 c = vec3(0.05, 0.045, 0.04) * exp(-r2 * 4.0) * uK; gl_FragColor = vec4(c, 1.0); }`,
  }), []);
  mat.uniforms.uK.value = k;
  return <mesh material={mat} position={[x, 62.5, -1]}><planeGeometry args={[900, 700]} /></mesh>;
};

/** Light shafts from whatever the shot is about: the twin's screen, the flipped bit, the Pi. */
const raysFor = (sh: keyof typeof S, f: number) => {
  if (sh === "ghost" || sh === "verdict") return { world: SCREEN.c.clone().add(V(BX, 0, 0)), amount: 0.9, tint: "#bfe6ff", threshold: 0.45 };
  if (sh === "tamper") return { world: V(RIB_X + 92 * STEP, RIB_Y, 3 + 2 * 4.9), amount: 2.2 * prog(f, S.tamper[0] + 70, S.tamper[0] + 84), tint: "#ff6a4a", threshold: 0.6 };
  if (sh === "reject") return { world: SCREEN.c.clone().add(V(BX, 0, 0)), amount: 0.9, tint: "#ff6a4a", threshold: 0.45 };
  if (sh === "seed") return { world: piCentre, amount: 0.7 * prog(f, S.seed[0] + 20, S.seed[0] + 60), tint: "#ffd9a6", threshold: 0.5 };
  return null;
};

/** Focus pulled to each shot's subject: the screen, the console, the cells, the twin, the flipped bit, the Pi. */
const dofFor = (sh: keyof typeof S, c: Cam): Dof => {
  const d = c.pos.distanceTo(c.target);
  const r: Record<string, [number, number]> = { screen: [45, 9], wide: [260, 7], track: [110, 9], ghost: [220, 4], verdict: [220, 3],
    tamper: [26, 13], reject: [260, 3], seed: [55, 10], gap: [300, 5] };
  let [range, blur] = r[sh] ?? [300, 0];
  if (sh === "screen" || sh === "wide") {
    const k = clamp(((c.t ?? 0) - 70) / 380);
    return { focus: lerp(d, c.pos.distanceTo(MID_A), clamp(((c.t ?? 0) - 300) / 150)), range: lerp(4, 260, Math.pow(k, 0.6)), blur: lerp(11, 6, k) };
  }
  if (sh === "track") { const k = easeInOut(clamp(((c.t ?? 0) - 0.58) / 0.42)); range = lerp(range, 1600, k); blur = lerp(blur, 3, k); }
  return { focus: d, range, blur };
};

const Scene: React.FC<{ f: number; buf: ArrayBuffer; atlas: THREE.Texture }> = ({ f, buf, atlas }) => {
  const { gl, scene } = useThree();
  useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 1.0;
  }, [gl, scene]);
  const A = useMemo(() => buildParts(buf), [buf]);
  const B = useMemo(() => buildParts(buf), [buf]);
  const poses = useMemo(() => A.map((p) => partPose(p.meta, DONE)), [A]);
  const rig = useMemo(() => {
    const mk = (parts: PartObj[], m: THREE.Matrix4, tint: boolean) => {
      const g = new THREE.Group();
      g.matrixAutoUpdate = false;
      g.matrix.copy(m);
      for (const p of parts) g.add(p.group);
      const sm = screenMat(atlas);
      sm.uniforms.uTintAmt.value = tint ? 1 : 0;
      const scr = new THREE.Mesh(new THREE.PlaneGeometry(SCREEN.w, SCREEN.h), sm);
      scr.position.copy(SCREEN.c);
      scr.renderOrder = 6;
      return { g, scr, sm };
    };
    const a = mk(A, FACE_UP, false), b = mk(B, AT_B, true);
    b.scr.position.x += BX;
    return { a, b };
  }, [A, B, atlas]);
  clip.constant = 1e5;
  section.constant = 1e5;
  const sh = shotOf(f);
  const noScan = { x: -1000, amt: 0 };
  // console A: coloured CAD; in the seed shot it turns x-ray and the Pi lights up
  const xA = sh === "seed" ? clamp((f - S.seed[0] - 10) / 20) : 0;
  A.forEach((p, i) => {
    const pose = { ...poses[i], hi: sh === "seed" && /pi_board|pi_parts/.test(p.meta.name) ? 0.6 + 0.4 * Math.sin(f * 0.2) : 0 };
    applyPose(p, pose, noScan, p.meta.name === "asm_pi_board" || p.meta.name === "asm_pi_parts" ? 0 : xA);
    p.group.visible = !(xA > 0 && /^panel_/.test(p.meta.name));
    if (xA > 0) dimXray(p, 0.45);
  });
  // twin B: always x-ray; in the reject shot it glitches apart and burns red
  const rej = sh === "reject" ? prog(f, S.reject[0] + 40, S.reject[0] + 60) : 0;
  const red = new THREE.Color(MW.red);
  B.forEach((p, i) => {
    const jit = rej > 0 && Math.floor(f / 3) % 2 === 0 ? rej : rej * 0.6;
    const off = new THREE.Vector3(rnd(i, Math.floor(f / 4), 1) - 0.5, rnd(i, Math.floor(f / 4), 2) - 0.5, rnd(i, 3) * 0.8).multiplyScalar(26 * jit);
    applyPose(p, { ...poses[i], m: new THREE.Matrix4().makeTranslation(off.x, off.y, off.z).multiply(poses[i].m), hi: 0 }, noScan, 1);
    p.group.visible = !/^panel_/.test(p.meta.name);         // in x-ray the rear plate's raised lettering reads through, mirrored
    dimXray(p, (sh === "ghost" || sh === "verdict" || sh === "reject" ? 0.42 : 0.22) + 0.3 * rej);
    if (rej > 0) {
      p.coreMat.color.lerp(red, rej);
      p.glowMat.color.lerp(red, rej);
      p.fillMat.uniforms.rim.value.set("#6cc4f2").lerp(red, rej);
    } else p.fillMat.uniforms.rim.value.set("#6cc4f2");
  });
  // the screens: A plays the run; B replays the log, faster, ice blue (red and torn when it disagrees)
  const g = gFrame(f);
  rig.a.sm.uniforms.uFrame.value = footage(sh === "seed" ? g : sh === "screen" ? g : g);
  rig.a.sm.uniforms.uOn.value = sh === "seed" ? 0.35 : 1;
  const rep = sh === "ghost" ? (f - S.ghost[0]) * 1.5 : sh === "verdict" ? 359 : sh === "reject" ? (f - S.reject[0]) * 1.5 : 0;
  rig.b.sm.uniforms.uFrame.value = footage(Math.min(359, rep));
  rig.b.sm.uniforms.uTint.value.set(rej > 0 ? MW.red : MW.ice);
  rig.b.sm.uniforms.uTear.value = rej;
  rig.b.sm.uniforms.uOn.value = sh === "ghost" || sh === "verdict" || sh === "reject" ? 0.9 : 0.25;
  const c = camFor(f);
  return (
    <>
      <color attach="background" args={["#020304"]} />
      <CameraAt pos={c.pos} target={c.target} fov={c.fov} up={V(0, 0, 1)} />
      <ambientLight intensity={0.18} />
      <directionalLight position={[-300, -500, 600]} intensity={1.7} color="#fff3e6" />
      <directionalLight position={[500, 600, 160]} intensity={1.1} color="#7cc4ff" />
      <directionalLight position={[101, 900, 420]} intensity={0.55} color="#ffb070" />
      <primitive object={rig.a.g} />
      <primitive object={rig.a.scr} />
      <primitive object={rig.b.g} />
      <primitive object={rig.b.scr} />
      <Pool x={101} k={1} />
      <Ribbon f={f} />
      <Post strength={0.65} radius={0.5} threshold={1.3} dof={dofFor(sh, c)} rays={raysFor(sh, f)}
        prev={camShot(f - 0.5 / PROOF_SLOW) === camShot(f) ? { ...camFor(f - 0.5 / PROOF_SLOW), up: V(0, 0, 1) } : null} />
    </>
  );
};

/** The two fingerprints, the console's and the replay's, as split-flap boxes: the replay's characters settle one by
    one, each marked equal or not against the console's, so the match (or the total mismatch) is seen, not just read. */
const Fingerprints: React.FC<{ f: number; at: number; top: string; bottom: string }> = ({ f, at, top, bottom }) => {
  if (f < at) return null;
  const BW = 62, BH = 78, GAP = 10, X = W / 2 - (8 * BW + 7 * GAP) / 2 + 60, Y = BAR + 40;
  const ok = top === bottom;
  const hex = "0123456789ABCDEF";
  const grow = Math.min(1, Math.ceil(prog(f, at, at + 6) * 4) / 4);
  const box = (key: string, ch: string, x: number, y: number, col: string, glow: boolean) => (
    <div key={key} style={{ position: "absolute", left: x, top: y, width: BW, height: BH, background: "#0b0c0d", border: `1px solid ${glow ? col : "#2a2d31"}`,
      boxShadow: glow ? `0 0 18px ${col}55, inset 0 0 14px ${col}22` : "none", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: BH / 2, height: 1, background: "rgba(0,0,0,0.6)" }} />
      <Mono s={44} c={col} w={700}>{ch}</Mono>
    </div>
  );
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H }}>
      <div style={{ position: "absolute", left: X - 190, top: Y - 16, width: (8 * BW + 7 * GAP + 230) * grow, height: (2 * BH + 120) * grow,
        background: "rgba(5,5,6,0.86)", borderLeft: `3px solid ${ok ? MW.green : MW.red}` }} />
      {f > at + 7 ? (
        <>
          <Mono s={15} c={ok ? MW.green : MW.red} w={700} ls="0.25em" style={{ position: "absolute", left: X - 170, top: Y - 4 }}>FINGERPRINT // THE FINAL GAME STATE, HASHED</Mono>
          <Mono s={15} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: X - 170, top: Y + 48 }}>CLAIMED</Mono>
          <Mono s={15} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: X - 170, top: Y + 48 + BH + 34 }}>REPLAY</Mono>
          {top.split("").map((ch, i) => box(`t${i}`, ch, X + i * (BW + GAP), Y + 28, MW.text, false))}
          {bottom.split("").map((ch, i) => {
            const done = f >= at + 16 + i * 4;
            const same = ch === top[i];
            const col = done ? (same ? MW.green : MW.red) : MW.dim;
            const show = done ? ch : hex[Math.floor(rnd(i, Math.floor(f / 2), 9) * 16)];
            return (
              <React.Fragment key={`b${i}`}>
                {box(`bb${i}`, show, X + i * (BW + GAP), Y + 28 + BH + 34, col, done)}
                {done ? <Mono s={24} c={col} w={700} style={{ position: "absolute", left: X + i * (BW + GAP), width: BW, textAlign: "center", top: Y + 28 + BH + 2 }}>{same ? "=" : "\u2260"}</Mono> : null}
              </React.Fragment>
            );
          })}
        </>
      ) : null}
    </div>
  );
};

/** The hex view of the log around the tampered byte, with that byte flipping. */
const Hex: React.FC<{ f: number; flip: number }> = ({ f, flip }) => {
  const b = PROOF.tampered_byte;
  const row0 = Math.floor(b / 16) - 3;
  const hex = PROOF.log_hex as string;
  return (
    <div>
      {Array.from({ length: 7 }, (_, r) => {
        const base = (row0 + r) * 16;
        return (
          <div key={r} style={{ display: "flex", gap: 10, marginBottom: 4 }}>
            <Mono s={17} c={MW.faint}>{base.toString(16).padStart(4, "0").toUpperCase()}</Mono>
            {Array.from({ length: 16 }, (_, i) => {
              const at = base + i;
              let v = parseInt(hex.slice(at * 2, at * 2 + 2), 16);
              const hit = at === b;
              if (hit && flip > 0.5) v ^= 0x01;
              const s = v.toString(16).padStart(2, "0").toUpperCase();
              return <Mono key={i} s={17} c={hit ? (flip > 0.5 ? MW.red : MW.amber) : MW.dim} w={hit ? 700 : 400}
                style={hit ? { outline: `2px solid ${flip > 0.5 ? MW.red : MW.amber}`, outlineOffset: 3, opacity: f % 10 < 5 || flip > 0.5 ? 1 : 0.6 } : undefined}>{s}</Mono>;
            })}
          </div>
        );
      })}
    </div>
  );
};

const Overlay: React.FC<{ f: number; part: string }> = ({ f, part }) => {
  const sh = shotOf(f);
  const P = projector(f);
  const g = gFrame(f);
  const L = 70, T = BAR + 30;
  const rep = PROOF.replay as { frames: number; time_frames: number; score: number; trophies: number };
  return (
    <>
      {sh === "lead" ? <Slate f={f} part={part} title="THE PROOF" len={S.lead[1]} /> : null}
      <Card f={f} at={S.screen[0] + 14} out={S.wide[0] + 110} x={L} y={T} w={430} h={150} head="EVIDENCE // RUN FOOTAGE">
        <Row k="CARTRIDGE" v="RUSH HOUR" />
        <Row k="RULES" v={`v${PROOF.rules_version}`} />
        <Row k="FRAME" v={String(fi(g) + 600).padStart(5, "0")} c={MW.amber} />
      </Card>
      {sh === "wide" || sh === "track" ? (() => {
        const k = IN[fi(g)];
        const at = sh === "wide" ? S.wide[0] + 120 : S.track[0] + 10;
        return (
          <>
            <Card f={f} at={at} x={L} y={T} w={430} h={sh === "track" ? 180 : 150} head="INPUT LOG // RECORDING" accent={MW.amber}>
              <Row k="FRAME" v={String(fi(g) + 600).padStart(5, "0")} c={MW.amber} />
              <Row k="HELD" v={keyName(k)} />
              <Row k="LOG" v={f % 40 < 26 ? "WRITING" : ""} c={MW.red} />
              {sh === "track" ? <Row k="RUN" v={`${PROOF.frames} FRAMES // ${PROOF.log_bytes} B`} c={MW.dim} /> : null}
            </Card>
            {(sh === "wide" && f > S.wide[0] + 150) || (sh === "track" && f < S.track[0] + 130) ? (   // how to read the ribbon
              <div style={{ position: "absolute", left: W - 790, top: H - BAR - 168, display: "flex", gap: 34, alignItems: "center",
                opacity: sh === "wide" ? prog(f, S.wide[0] + 150, S.wide[0] + 162) : 1 - prog(f, S.track[0] + 118, S.track[0] + 130) }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 10, height: 34, background: "rgba(40,46,56,0.9)", boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.15)" }} />
                  <Mono s={15} c={MW.text} ls="0.18em">1 COLUMN = 1 FRAME (1/60 S)</Mono>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 12, height: 12, background: "#ffcf7a", boxShadow: "0 0 12px #ffb23f" }} />
                  <Mono s={15} c={MW.text} ls="0.18em">LIT = BUTTON HELD</Mono>
                </div>
              </div>
            ) : null}
            {sh === "track" ? (() => {                                   // the size of the proof, against the same run as raw frames
              const raw = PROOF.frames * 240 * 160 * 3;                   // 240 x 160 game pixels, 24-bit, every frame: arithmetic
              return (
                <Card f={f} at={S.track[0] + 22} out={S.track[0] + 196} x={W - 70 - 620} y={T} w={620} h={196} head="THE WHOLE RUN" accent={MW.green} headCol={MW.green}>
                  <Row k="AS A LOG" v={`${PROOF.log_bytes} B`} c={MW.green} s={24} />
                  <Row k="AS RAW FRAMES, 240 x 160 x 24-BIT" v={`${(raw / 1e6).toFixed(1)} MB`} c={MW.dim} s={20} />
                  <Row k="SMALLER BY" v={`${Math.round(raw / PROOF.log_bytes).toLocaleString("en-US")} x`} c={MW.amber} s={24} />
                </Card>
              );
            })() : null}
            {sh === "track" ? (() => {                                   // the crane: name the three things in the frame
              const k = prog(f, S.track[0] + 200, S.track[0] + 212);
              const tags: [THREE.Vector3, string, string][] = [[V(101, 62.5, -20), "CONSOLE // PLAYING", MW.text],
                [V(RIB_X + 600, RIB_Y, -10), `INPUT LOG // ${PROOF.log_bytes} B`, MW.amber], [V(BX + 101, 62.5, -20), "REPLAY // WAITING", MW.blue]];
              return k > 0 ? tags.map(([v, t, col]) => { const p = P(v); return (
                <Mono key={t} s={15} c={col} w={700} ls="0.22em" style={{ position: "absolute", left: p.x - 160, top: p.y + 26, width: 320, textAlign: "center",
                  clipPath: `inset(0 ${100 - 100 * k}% 0 0)` }}>{t}</Mono>
              ); }) : null;
            })() : null}
            {sh === "wide" ? KEYS.map((name, r) => {
              const p = P(V(RIB_X - 6, RIB_Y, 3 + r * 4.9));
              return <Mono key={name} s={14} c={(k >> r) & 1 ? MW.amber : MW.dim} w={700} ls="0.1em"
                style={{ position: "absolute", left: p.x - 70, top: p.y - 7, width: 60, textAlign: "right", opacity: prog(f, S.wide[0] + 170, S.wide[0] + 182) }}>{name}</Mono>;
            }) : null}
          </>
        );
      })() : null}
      {sh === "ghost" ? (
        <>
          <Card f={f} at={S.ghost[0] + 10} x={L} y={T} w={560} h={250} head="REPLAY // SAME LOG, SAME RULES" accent={MW.blue} headCol={MW.blue}>
            <Mono s={17} c={MW.dim}>$ arcade_replay RUSH.acl</Mono>
            <div style={{ height: 10 }} />
            <Row k="FRAMES" v={Math.min(PROOF.frames, Math.round(PROOF.frames * easeOut(prog(f, S.ghost[0] + 30, S.ghost[1] - 30)))).toLocaleString("en-US")} c={MW.ice} />
            <Row k="FINISHED" v={f > S.ghost[1] - 30 ? `${(rep.time_frames / 60).toFixed(2)} S` : "..."} />
            <Row k="SCORE // TROPHIES" v={f > S.ghost[1] - 30 ? `${rep.score} // ${rep.trophies}` : "..."} />
          </Card>
          {(() => { const p = P(MID_B.clone().add(V(0, 0, 60))); return (
            <Mono s={14} c={MW.blue} ls="0.25em" style={{ position: "absolute", left: p.x - 200, top: p.y - 60, width: 400, textAlign: "center", opacity: prog(f, S.ghost[0] + 20, S.ghost[0] + 30) }}>ANYONE CAN REPLAY IT</Mono>
          ); })()}
        </>
      ) : null}
      {sh === "verdict" ? (
        <>
          <Fingerprints f={f} at={S.verdict[0] + 6} top={PROOF.claimed_hash} bottom={PROOF.replay_hash} />
          <Stamp f={f} at={S.verdict[0] + 52} text="VERIFIED" col={MW.green} y={H / 2 + 120} s={120} sub={`${PROOF.claimed_hash} = ${PROOF.replay_hash}`} />
        </>
      ) : null}
      {sh === "tamper" ? (
        <>
          <Card f={f} at={S.tamper[0] + 10} x={L} y={T} w={760} h={300} head={`TAMPER TEST // BYTE ${PROOF.tampered_byte} OF ${PROOF.log_bytes}`} accent={MW.red} headCol={MW.red}>
            <Hex f={f} flip={prog(f, S.tamper[0] + 70, S.tamper[0] + 80)} />
            <Mono s={16} c={f > S.tamper[0] + 80 ? MW.red : MW.dim} style={{ marginTop: 12 }}>{f > S.tamper[0] + 80 ? "XOR 0x01 // ONE BIT CHANGED" : "ORIGINAL LOG"}</Mono>
          </Card>
          {(() => { const p = P(V(RIB_X + 92 * STEP, RIB_Y, 3 + 2 * 4.9)); const k = prog(f, S.tamper[0] + 78, S.tamper[0] + 86); return k > 0 ? (
            <>
              <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
                <rect x={p.x - 46 - 20 * (1 - k)} y={p.y - 46 - 20 * (1 - k)} width={92 + 40 * (1 - k)} height={92 + 40 * (1 - k)} fill="none" stroke={MW.red} strokeWidth={3} opacity={k} />
              </svg>
              <Mono s={24} c={MW.red} w={700} ls="0.25em" style={{ position: "absolute", left: p.x - 150, top: p.y + 60, width: 300, textAlign: "center", opacity: k }}>ONE BIT</Mono>
            </>
          ) : null; })()}
        </>
      ) : null}
      {sh === "reject" ? (
        <>
          <Fingerprints f={f} at={S.reject[0] + 10} top={PROOF.claimed_hash} bottom={PROOF.tampered_hash as string} />
          <Stamp f={f} at={S.reject[0] + 60} text="REJECTED" col={MW.red} y={H / 2 + 120} s={120} sub={`${PROOF.tampered_hash} != ${PROOF.claimed_hash}`} />
        </>
      ) : null}
      {sh === "seed" ? (() => {
        const p = P(piCentre);
        const on = prog(f, S.seed[0] + 40, S.seed[0] + 52);
        return (
          <>
            <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
              <line x1={p.x} y1={p.y} x2={p.x + 260 * on} y2={p.y - 200 * on} stroke={MW.amber} strokeWidth={2} />
              <circle cx={p.x} cy={p.y} r={7} fill="none" stroke={MW.amber} strokeWidth={2} opacity={on} />
            </svg>
            <Card f={f} at={S.seed[0] + 52} x={p.x + 270} y={p.y - 290} w={540} h={170} head="SEED // ROLLED AT LAUNCH" accent={MW.amber} headCol={MW.amber}>
              <Mono s={46} c={MW.text} w={700} ls="0.12em">{PROOF.seeded_seed}</Mono>
              <Mono s={15} c={MW.dim} ls="0.15em" style={{ marginTop: 10 }}>NEW EVERY LAUNCH // IN THE LOG HEADER</Mono>
            </Card>
          </>
        );
      })() : null}
      {sh === "gap" ? (
        // the hinge of the film, centred and large: what the log proves, and which network answers each gap
        <Card f={f} at={S.gap[0] + 16} x={(W - 1300) / 2} y={BAR + 150} w={1300} h={340} head="WHAT THE LOG PROVES" accent={MW.text} headCol={MW.text}>
          {[
            ["WHAT HAPPENED, FRAME BY FRAME", "PROVEN", MW.green, 0, ""],
            ["WHO CLAIMS THE RUN", "NOT YET", MW.amber, 40, "WORLD ID"],
            ["WHEN, AND AT WHAT PACE", "NOT YET", MW.amber, 70, "HEDERA"],
            ["WHERE THE RECORD LIVES", "NOT YET", MW.amber, 100, "ARKIV"],
          ].map(([k, v, c, d, to]) => (
            <div key={k as string} style={{ display: "grid", gridTemplateColumns: "640px 210px 1fr", alignItems: "baseline", height: 62,
              opacity: f > S.gap[0] + 26 + (d as number) ? 1 : 0 }}>
              <Mono s={26} c={MW.text} ls="0.04em">{k as string}</Mono>
              <Mono s={26} c={c as string} w={700}>{v as string}</Mono>
              <Mono s={26} c={MW.orange} w={700} ls="0.08em" style={{ opacity: f > S.gap[0] + 40 + (d as number) ? 1 : 0 }}>{to ? `-> ${to}` : ""}</Mono>
            </div>
          ))}
        </Card>
      ) : null}
    </>
  );
};

/** part: the act card's label (the submission cut drops Part I, so there it is PART III). */
/** clean: no subtitles (for the cover image, src/acts/Poster.tsx). */
export const Proof: React.FC<{ part?: string; clean?: boolean }> = ({ part = "PART IV", clean = false }) => {
  const f = useCurrentFrame() / PROOF_SLOW;
  const buf = useBuffer(staticFile("console.bin"));
  const atlas = useTexture(staticFile("game/RUSH_atlas.png"));
  if (atlas) { atlas.magFilter = THREE.NearestFilter; atlas.minFilter = THREE.LinearFilter; atlas.generateMipmaps = false; }
  const cut = CUTS.find((c) => f >= c && f < c + 3 && c > 0);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {buf && atlas && f >= S.screen[0] ? (
        <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }}
          style={{ position: "absolute", inset: 0, transform: kick(f, [S.verdict[0] + 52, S.reject[0] + 60, S.tamper[0] + 78]) }}>
          <Scene f={f} buf={buf} atlas={atlas} />
        </ThreeCanvas>
      ) : null}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.65) 100%)" }} />
      <Overlay f={f} part={part} />
      {clean ? null : <Subs f={f} lines={LINES} />}
      {cut !== undefined ? <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: 0.08 * (3 - (f - cut)) }} /> : null}
      <Bars />
    </AbsoluteFill>
  );
};

/** A flash-forward for the cold open: the console playing, clean, for a moment, then gone. It pays off in Act IV. */
export const TEASER_LEN = 100;
export const ProofTeaser: React.FC = () => {
  const t = useCurrentFrame();
  const f = 300 + t;                                                   // the console, as the inputs start to stream
  const buf = useBuffer(staticFile("console.bin"));
  const atlas = useTexture(staticFile("game/RUSH_atlas.png"));
  if (atlas) { atlas.magFilter = THREE.NearestFilter; atlas.minFilter = THREE.LinearFilter; atlas.generateMipmaps = false; }
  const gl = t < 5 ? 5 - t : t > TEASER_LEN - 7 ? t - (TEASER_LEN - 7) : 0;   // glitch in, glitch out
  const jx = gl > 0 ? (rnd(t, 9) - 0.5) * 70 * gl / 5 : 0;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {buf && atlas ? (
        <AbsoluteFill style={{ transform: `translateX(${jx}px)`, filter: gl > 0 ? `saturate(${1 + gl * 0.4}) contrast(${1 + gl * 0.15})` : undefined }}>
          <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0 }}>
            <Scene f={f} buf={buf} atlas={atlas} />
          </ThreeCanvas>
        </AbsoluteFill>
      ) : null}
      {gl > 0 ? Array.from({ length: 7 }, (_, i) => (
        <div key={i} style={{ position: "absolute", left: 0, right: 0, top: rnd(i, t, 1) * H, height: 3 + rnd(i, t, 2) * 46,
          background: i % 2 ? "#fff" : "#000", opacity: 0.55 * gl / 5, mixBlendMode: i % 2 ? "screen" : "normal" }} />
      )) : null}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.7) 100%)" }} />
      <Mono s={15} c={MW.red} w={700} ls="0.3em" style={{ position: "absolute", left: 70, top: BAR + 34, opacity: t % 24 < 15 ? 1 : 0 }}>INTERCEPT // LIVE FEED</Mono>
      <Bars />
    </AbsoluteFill>
  );
};

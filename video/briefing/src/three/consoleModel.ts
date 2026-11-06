import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import META from "../../public/console.json";
import { C, H, TL, W } from "../theme";
import { clamp, easeIn, easeInOut, easeOut, easeOutExpo, lerp, prog, rnd, smooth } from "../util";

export const META_ = META;
export type PartMeta = (typeof META.parts)[number];
type Move = { files: string[]; kind: string; t0: number; dur: number; stagger?: number; fly?: number; rigid?: boolean };

const B = TL.build;
const SW = TL.swap;
const HERO = TL.hero;
export const EXPLODE = 3.0;
export const CENTRE = new THREE.Vector3(101, 62.5, 24);
const HOUSING = new Set(["asm_front_shell", "asm_rear_frame", "asm_bay_tray", "panel_ethglobal_body", "panel_ethglobal_lockup_body"]);

export const stepStart = (s: number) => B.start + (s - 1) * B.stepLen;
export const assembled = B.start + B.steps * B.stepLen;

const centreOf = (p: PartMeta) => {
  const [lo, hi] = p.bounds;
  return new THREE.Vector3((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2);
};

/** Each part's place in the build: its step, its move, when it starts and when it lands. */
export type Slot = { step: number; move: Move; k: number; n: number; start: number; land: number; pressAt: number; pivot: THREE.Vector3 };
export const SLOTS = new Map<string, Slot>();
TL.steps.forEach((st, s) => {
  for (const m of st.moves as Move[]) {
    const parts = m.files.flatMap((f) => META.parts.filter((p) => p.file === f || p.name === f).sort((a, b) => a.inst - b.inst));
    const box = new THREE.Box3();
    for (const p of parts) box.expandByPoint(new THREE.Vector3(...(p.bounds[0] as [number, number, number]))).expandByPoint(new THREE.Vector3(...(p.bounds[1] as [number, number, number])));
    parts.forEach((p, i) => {
      const k = m.rigid ? 0 : i;
      const begin = stepStart(s) + m.t0 + (m.kind === "press" ? k * 2 : k * (m.stagger ?? 0));
      const pressAt = stepStart(s) + m.t0 + (m.fly ?? 0) + k * (m.stagger ?? 0);
      const land = m.kind === "press" ? pressAt + m.dur : begin + m.dur;
      SLOTS.set(p.name, { step: s, move: m, k, n: m.rigid ? 1 : parts.length, start: begin, land, pressAt,
        pivot: m.rigid ? box.getCenter(new THREE.Vector3()) : centreOf(p) });
    });
  }
});

/** The frame the last part of step s lands. */
export const stepDone = (s: number) => {
  let f = s === 0 ? 0 : stepStart(s);
  for (const sl of SLOTS.values()) if (sl.step === s) f = Math.max(f, sl.land);
  return f;
};

const fillVert = /* glsl */ `
  #include <common>
  #include <clipping_planes_pars_vertex>
  varying vec3 vN; varying vec3 vV; varying vec3 vW;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vN = normalMatrix * normal;                     // normalised in the fragment, safely (a few CAD normals are zero)
    vV = normalize(-mvPosition.xyz);
    vW = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * mvPosition;
    #include <clipping_planes_vertex>
  }`;
const fillFrag = /* glsl */ `
  #include <common>
  #include <clipping_planes_pars_fragment>
  uniform vec3 base; uniform vec3 rim; uniform vec3 hi; uniform float hiAmt; uniform float alpha;
  uniform vec3 heat; uniform float heatAmt; uniform float scanX; uniform float scanAmt;
  varying vec3 vN; varying vec3 vV; varying vec3 vW;
  void main() {
    #include <clipping_planes_fragment>
    vec3 n = vN / max(length(vN), 1e-6);
    float fr = clamp(1.0 - abs(dot(n, normalize(vV))), 0.0, 1.0);   // pow() of a hair below zero is NaN
    vec3 c = base + rim * pow(fr, 2.4) * 0.55;
    c += rim * 0.03 * (0.5 + 0.5 * sin(vW.y * 1.6));
    c = mix(c, hi * (0.10 + pow(fr, 1.6) * 0.9), hiAmt * 0.38);
    c = mix(c, heat * (0.45 + pow(fr, 1.2)), heatAmt * 0.85);
    float band = exp(-pow((vW.x - scanX) * 0.09, 2.0));
    c += rim * band * scanAmt * 0.9;
    gl_FragColor = vec4(c, alpha + band * scanAmt * 0.25);
  }`;

export type PartObj = {
  meta: PartMeta;
  group: THREE.Group;
  fill: THREE.Mesh;
  fillMat: THREE.ShaderMaterial;
  core: LineSegments2; coreMat: LineMaterial;
  glow: LineSegments2; glowMat: LineMaterial;
  ghost: LineSegments2; ghostMat: LineMaterial;
  solid: THREE.Mesh; solidMat: THREE.MeshStandardMaterial;
  lineCol: THREE.Color;
  housing: boolean;
  smoke: boolean;
};

const METAL = /screw|insert|magnet|heatsink|pi_parts/;

/** How much of the x-ray look is on at frame f: the hero and the section cut; coloured CAD everywhere else. */
export const xrayAt = (f: number) => {
  const S = TL.shots, SC = TL.section;
  if (f < S.build[0]) return 1;
  if (f < S.section[0]) return 0;
  if (f < SC.out[1]) return clamp((f - S.section[0]) / 20);
  return clamp(1 - (f - SC.out[1]) / 6);
};

const ICE = new THREE.Color(C.ink);
const AMBER = new THREE.Color(C.accent);
const HEAT = new THREE.Color("#ff5a1f");
const DIMC = new THREE.Color(C.dim);
const BASE = new THREE.Color("#04101a");

export const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e5);     // the hero's scan reveal: keeps y < constant
export const section = new THREE.Plane(new THREE.Vector3(0, 1, 0), 1e5);  // the section cut: keeps y > -constant
const PLANES = [clip, section];

const lineMat = (width: number, opacity: number, depthTest: boolean, additive: boolean) => {
  const m = new LineMaterial({ color: 0xffffff, linewidth: width, transparent: true, opacity, depthTest, depthWrite: false, worldUnits: false });
  m.resolution.set(W, H);
  if (additive) m.blending = THREE.AdditiveBlending;
  m.clippingPlanes = PLANES;
  return m;
};

export const buildParts = (buf: ArrayBuffer): PartObj[] =>
  META.parts.map((p) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, p.pos, p.nVerts * 3), 3));
    g.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(buf, p.nrm, p.nVerts * 3), 3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, p.idx, p.nIdx), 1));
    const housing = HOUSING.has(p.name);
    const fillMat = new THREE.ShaderMaterial({
      vertexShader: fillVert, fragmentShader: fillFrag, clipping: true, transparent: true,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, depthWrite: !housing,
      blending: housing ? THREE.AdditiveBlending : THREE.NormalBlending,
      uniforms: { base: { value: BASE.clone().lerp(new THREE.Color(p.colour), 0.08) }, rim: { value: new THREE.Color("#6cc4f2") },
        hi: { value: AMBER.clone() }, hiAmt: { value: 0 }, alpha: { value: 1 }, heat: { value: HEAT.clone() }, heatAmt: { value: 0 },
        scanX: { value: -1000 }, scanAmt: { value: 0 } },
    });
    fillMat.clippingPlanes = PLANES;
    const fill = new THREE.Mesh(g, fillMat);
    fill.renderOrder = housing ? 1 : 0;
    const eg = new LineSegmentsGeometry();
    eg.setPositions(new Float32Array(buf, p.edge, p.nEdge * 3));
    const coreMat = lineMat(1.3, 0.95, true, false);
    const glowMat = lineMat(5.5, 0.1, true, true);
    const ghostMat = lineMat(1.0, 0.15, false, true);
    const core = new LineSegments2(eg, coreMat);
    const glow = new LineSegments2(eg, glowMat);
    const ghost = new LineSegments2(eg, ghostMat);
    core.renderOrder = 3; glow.renderOrder = 2; ghost.renderOrder = 4;
    // the coloured CAD: the part's own filament colour, satin PLA or metal; the front shell is smoke PLA
    const colour = new THREE.Color(p.colour);
    const smoke = p.name === "asm_front_shell";
    const metal = METAL.test(p.name);
    const solidMat = new THREE.MeshStandardMaterial({
      color: smoke ? new THREE.Color("#2a3038") : colour, roughness: metal ? 0.3 : 0.56, metalness: metal ? 0.85 : 0,
      transparent: smoke, opacity: smoke ? 0.4 : 1, depthWrite: !smoke, side: smoke ? THREE.DoubleSide : THREE.FrontSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, emissive: new THREE.Color(0x000000), envMapIntensity: metal ? 1.1 : 0.7,
    });
    solidMat.clippingPlanes = PLANES;
    const solid = new THREE.Mesh(g, solidMat);
    solid.renderOrder = smoke ? 1 : 0;
    const lum = colour.r * 0.3 + colour.g * 0.59 + colour.b * 0.11;
    const lineCol = smoke ? new THREE.Color("#9aa3ab") : lum > 0.3 ? colour.clone().lerp(new THREE.Color("#000000"), 0.62) : colour.clone().lerp(new THREE.Color("#ffffff"), 0.24);
    const group = new THREE.Group();
    group.matrixAutoUpdate = false;
    group.add(solid, fill, glow, core, ghost);
    return { meta: p, group, fill, fillMat, core, coreMat, glow, glowMat, ghost, ghostMat, solid, solidMat, lineCol, housing, smoke };
  });

export type Pose = { visible: boolean; m: THREE.Matrix4; offset: THREE.Vector3; mode: "ghost" | "live"; hi: number; heat: number; alpha: number };

const D2R = Math.PI / 180;
const poseM = (off: THREE.Vector3, pivot: THREE.Vector3, rot?: THREE.Quaternion) => {
  const m = new THREE.Matrix4().makeTranslation(off.x + pivot.x, off.y + pivot.y, off.z + pivot.z);
  if (rot) m.multiply(new THREE.Matrix4().makeRotationFromQuaternion(rot));
  return m.multiply(new THREE.Matrix4().makeTranslation(-pivot.x, -pivot.y, -pivot.z));
};

/** Where a sponsor panel is during the swaps: in place, lifting off, or snapping on. */
const panelSwap = (kind: string, f: number) => {
  const i = SW.order.indexOf(kind);
  const inAt = i === 0 ? -Infinity : SW.swaps[i - 1] + 16;
  const outAt = i < SW.order.length - 1 ? SW.swaps[i] : Infinity;
  if (f < inAt) return null;
  if (f >= outAt + 30) return { lift: 1.2, alpha: 0, hi: 0 };
  if (f >= outAt) { const t = prog(f, outAt, outAt + 30); return { lift: easeIn(t) * 1.2, alpha: 1 - t, hi: 0 }; }
  if (i > 0) {
    const t = prog(f, inAt, inAt + 50);
    const lift = t < 0.7 ? lerp(1.3, 0.12, easeOut(t / 0.7)) : 0.12 * (1 - easeIn((t - 0.7) / 0.3));
    return { lift, alpha: clamp(t * 4), hi: clamp(1 - (f - inAt - 50) / 30) };
  }
  return { lift: 0, alpha: 1, hi: 0 };
};

export const partPose = (p: PartMeta, f: number): Pose => {
  const dir = new THREE.Vector3(...(p.dir as [number, number, number]));
  const up = dir.clone().multiplyScalar(-1);
  const away = up.clone().multiplyScalar(p.dist * EXPLODE);
  const slot = SLOTS.get(p.name);
  const pivot = slot?.pivot ?? centreOf(p);
  const live = (off: THREE.Vector3, hi = 0, heat = 0, rot?: THREE.Quaternion, alpha = 1): Pose =>
    ({ visible: alpha > 0.001, m: poseM(off, pivot, rot), offset: off, mode: "live", hi, heat, alpha });

  // the second plate only exists in the swap shot; the first is fitted at its build step, then lifted off
  if (p.panel && SW.order.indexOf(p.panel) > 0) {
    const s = panelSwap(p.panel, f);
    if (!s) return { ...live(away), visible: false };
    return live(away.clone().multiplyScalar(s.lift / EXPLODE * 2), s.hi, 0, undefined, s.alpha);
  }
  if (p.panel === SW.order[0] && f >= SW.swaps[0]) {
    const s = panelSwap(SW.order[0], f)!;
    return live(away.clone().multiplyScalar(s.lift / EXPLODE * 2), 0, 0, undefined, s.alpha);
  }
  if (!slot) return live(new THREE.Vector3());                        // the shell: the base, never moves

  // hero: assembled, then it bursts apart into the exploded view
  const delay = Math.floor(rnd(slot.step, slot.k, 3) * 10);
  const ex = easeOutExpo(prog(f, HERO.explode + delay, HERO.explode + delay + HERO.explodeLen));
  if (f < slot.start) {
    if (ex <= 0) return live(new THREE.Vector3());
    const ghost = clamp((f - HERO.explode - 30) / 20);
    return { ...live(away.clone().multiplyScalar(ex)), mode: ghost > 0.5 ? "ghost" : "live" };
  }

  const m = slot.move;
  const after = f - slot.land;
  const hi = f < slot.land ? 1 : clamp(1 - after / 26);
  const bounce = (amp: number) => (after > 0 && after < 40 ? amp * Math.exp(-after / 4.5) * Math.abs(Math.sin(after * 0.75)) : 0);
  const t = prog(f, slot.start, slot.start + m.dur);
  switch (m.kind) {
    case "spin": {
      // fly in to just above the hole, then thread down one and a half turns
      const lift = up.clone().multiplyScalar(8);
      if (t < 0.45) {
        const e = easeOut(t / 0.45);
        return live(lift.clone().lerp(away, 1 - e), hi, 0, new THREE.Quaternion().setFromAxisAngle(dir, 3 * Math.PI));
      }
      const t2 = (t - 0.45) / 0.55;
      return live(lift.clone().multiplyScalar(1 - t2), hi, 0, new THREE.Quaternion().setFromAxisAngle(dir, (1 - t2) * 3 * Math.PI));
    }
    case "press": {
      // all eight fly to just above their bosses, then each is pressed in hot, one after another
      const above = up.clone().multiplyScalar(5);
      if (f < slot.pressAt) {
        const e = easeOut(prog(f, slot.start, slot.start + (m.fly ?? 20)));
        return live(above.clone().lerp(away, 1 - e), 0.7, 0);
      }
      const tb = prog(f, slot.pressAt, slot.land);
      const heat = f < slot.land ? tb : clamp(1 - after / 45);
      return live(above.clone().multiplyScalar(1 - easeInOut(tb)), hi * 0.5, heat);
    }
    case "tilt": {
      const e = easeInOut(t);
      const r = Math.pow(1 - e, 1.6);
      const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(14 * D2R * r, -9 * D2R * r, 4 * D2R * r));
      return live(away.clone().multiplyScalar(1 - e).add(up.clone().multiplyScalar(bounce(0.8))), hi, 0, q);
    }
    case "slide": {
      const e = easeInOut(t);
      return live(away.clone().multiplyScalar(1 - e), hi);
    }
    case "snap": {
      // drift in, hover over the magnets, then snap down and rebound
      const hover = up.clone().multiplyScalar(16);
      if (t < 0.62) return live(hover.clone().lerp(away, 1 - easeOut(t / 0.62)), hi);
      if (t < 0.76) return live(hover.clone().add(up.clone().multiplyScalar(Math.sin(f * 1.7) * 0.35)), hi);
      if (t < 0.84) return live(hover.clone().multiplyScalar(1 - easeIn((t - 0.76) / 0.08)), hi);
      return live(up.clone().multiplyScalar(bounce(1.4)), hi);
    }
    default: {                                                         // drop
      const e = easeOut(t);
      return live(away.clone().multiplyScalar(1 - e).add(up.clone().multiplyScalar(bounce(1.6))), hi);
    }
  }
};

export const applyPose = (o: PartObj, s: Pose, scan: { x: number; amt: number }, xr = 1) => {
  o.group.visible = s.visible;
  o.group.matrix.copy(s.m);
  o.group.matrixWorldNeedsUpdate = true;
  const ghost = s.mode === "ghost";
  const x = ghost ? 1 : xr;                     // waiting parts are x-ray ghosts until they move in
  const hot = Math.max(s.hi, s.heat);
  // x-ray layer
  o.fill.visible = !ghost && x > 0.01;
  o.ghost.visible = !ghost && x > 0.01;
  const u = o.fillMat.uniforms;
  u.hiAmt.value = s.hi;
  u.heatAmt.value = s.heat;
  u.alpha.value = (o.housing ? 0.22 : 1) * s.alpha * x;
  u.scanX.value = scan.x;
  u.scanAmt.value = scan.amt;
  o.fillMat.depthWrite = !o.housing && s.alpha > 0.99 && x > 0.99;
  o.ghostMat.color.copy(ICE);
  o.ghostMat.opacity = (o.housing ? 0.06 : 0.15) * s.alpha * x;
  // coloured CAD layer
  const c = 1 - x;
  o.solid.visible = c > 0.01;
  const m = o.solidMat;
  m.emissive.copy(AMBER).multiplyScalar(0.32 * s.hi).add(HEAT.clone().multiplyScalar(1.1 * s.heat));
  m.opacity = (o.smoke ? 0.4 : 1) * s.alpha * c;
  m.transparent = o.smoke || m.opacity < 0.99;
  m.depthWrite = !o.smoke && m.opacity > 0.99;
  // edges: ice in x-ray, the part's own darker tone on colour; amber or heat while it moves
  const xrayLine = ghost ? DIMC.clone() : ICE.clone().lerp(AMBER, s.hi).lerp(HEAT, s.heat * 0.8);
  const solidLine = o.lineCol.clone().lerp(AMBER, s.hi).lerp(HEAT, s.heat * 0.8);
  const col = solidLine.lerp(xrayLine, x);
  o.coreMat.color.copy(col);
  o.glowMat.color.copy(ghost ? DIMC : ICE.clone().lerp(AMBER, s.hi).lerp(HEAT, s.heat * 0.8));
  o.coreMat.opacity = lerp(0.5 + 0.45 * hot, ghost ? 0.42 : 0.95, x) * s.alpha;
  o.coreMat.linewidth = ghost ? 1.0 : lerp(1.0 + 0.9 * hot, 1.3 + hot * 0.7, x);
  o.glowMat.opacity = lerp(0.2 * hot, ghost ? 0.03 : 0.09 + hot * 0.24, x) * s.alpha;
};

/** The device lies face-down on the bench (+z up); for the reveal it is flipped over about its long axis. */
export const FLIP = [TL.shots.reveal[0], TL.shots.reveal[0] + 90] as const;
export const asmMatrix = (f: number) => {
  const t = smooth(prog(f, FLIP[0], FLIP[1]));
  const lift = Math.sin(Math.PI * t) * 115;
  return new THREE.Matrix4()
    .makeTranslation(CENTRE.x, CENTRE.y, CENTRE.z + lift)
    .multiply(new THREE.Matrix4().makeRotationY(Math.PI * t))
    .multiply(new THREE.Matrix4().makeTranslation(-CENTRE.x, -CENTRE.y, -CENTRE.z));
};

const orbit = (az: number, el: number, r: number, target: THREE.Vector3) => ({
  pos: target.clone().add(new THREE.Vector3(Math.sin(az * D2R) * Math.cos(el * D2R), -Math.cos(az * D2R) * Math.cos(el * D2R), Math.sin(el * D2R)).multiplyScalar(r)),
  target, fov: 30,
});

const stepTarget = (s: number) => {
  const c = new THREE.Vector3();
  let n = 0;
  for (const [name, sl] of SLOTS) if (sl.step === s) { const p = META.parts.find((q) => q.name === name)!; c.add(centreOf(p)); n++; }
  return n ? c.multiplyScalar(1 / n).lerp(CENTRE, 0.4) : CENTRE.clone();
};

/** The camera by frame: a slow orbit for the hero, a cut to a new angle for every build step. */
export const camAt = (f: number) => {
  const S = TL.shots;
  if (f < S.build[0]) {
    const t = smooth(prog(f, S.hero[0], HERO.explode));
    const e = easeOut(prog(f, HERO.explode, S.build[0]));
    return orbit(lerp(-52, 8, t) + 14 * e, lerp(32, 40, t) - 12 * e, lerp(540, 470, t) + 230 * e, CENTRE.clone().add(new THREE.Vector3(0, 0, 75 * e)));
  }
  if (f < assembled) {
    const s = Math.min(B.steps, Math.floor((f - B.start) / B.stepLen) + 1);
    const [az, el, r] = TL.steps[s].cam as number[];
    const t = smooth(prog(f, stepStart(s), stepStart(s) + B.stepLen));
    return orbit(az + 12 * t, el - 4 * t, r * (1 - 0.1 * t), stepTarget(s));
  }
  if (f < S.allies[0]) {
    const t = smooth(prog(f, assembled, S.allies[0]));
    return orbit(lerp(-24, -8, t), lerp(34, 40, t), lerp(470, 420, t), CENTRE.clone());
  }
  if (f < S.reveal[0]) {
    const t = smooth(prog(f, S.allies[0], S.reveal[0]));
    return orbit(lerp(8, 2, t), lerp(56, 62, t), lerp(440, 400, t), CENTRE.clone().add(new THREE.Vector3(0, 0, 24)));
  }
  const R0 = S.reveal[0];
  const k: [number, number, number, number, number][] = [
    [R0, 2, 62, 400, 24], [R0 + 60, -10, 44, 600, 80], [R0 + 100, -4, 40, 520, 18], [S.reveal[1], 0, 38, 480, 18]];
  let i = 0;
  while (i < k.length - 2 && f >= k[i + 1][0]) i++;
  const [f0, a0, e0, r0, z0] = k[i];
  const [f1, a1, e1, r1, z1] = k[i + 1];
  const t = smooth(prog(f, f0, f1));
  return orbit(lerp(a0, a1, t), lerp(e0, e1, t), lerp(r0, r1, t), CENTRE.clone().add(new THREE.Vector3(0, 0, lerp(z0, z1, t))));
};

export const cameraFor = (f: number) => {
  const c = camAt(f);
  const cam = new THREE.PerspectiveCamera(c.fov, W / H, 1, 5000);
  cam.position.copy(c.pos);
  cam.up.set(0, 0, 1);
  cam.lookAt(c.target);
  cam.updateMatrixWorld();
  cam.updateProjectionMatrix();
  return cam;
};

/** Screen position of a point given in device coordinates (before the flip). */
export const projectTo = (f: number, v: THREE.Vector3, cam: THREE.Camera = cameraFor(f)) => {
  const p = v.clone().applyMatrix4(asmMatrix(f)).project(cam);
  return { x: (p.x * 0.5 + 0.5) * W, y: (-p.y * 0.5 + 0.5) * H };
};

export const partCentre = (p: PartMeta, f: number) => centreOf(p).applyMatrix4(partPose(p, f).m);

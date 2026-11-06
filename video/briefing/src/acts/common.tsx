import { useFrame, useThree } from "@react-three/fiber";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { cancelRender, continueRender, delayRender } from "remotion";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { FullScreenQuad, Pass } from "three/examples/jsm/postprocessing/Pass.js";
import { RaysPass, raysAt } from "./rays";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { FONT } from "../theme";
import { clamp, easeOutExpo, lerp, prog } from "../util";

export const W = 1920, H = 1080, BAR = 118;
export const MW = { text: "#e6e6e3", dim: "#8f918f", faint: "#5b5d5c", orange: "#f08a24", red: "#d43a2b", blue: "#7cc4ff",
  green: "#7bd389", amber: "#ffb23f", ice: "#d6eefc" };

/** Bloom over the whole scene; it takes over rendering from R3F (priority 1). */
export const Bloom: React.FC<{ strength?: number; radius?: number; threshold?: number }> = ({ strength = 0.9, radius = 0.55, threshold = 0.18 }) => {
  const { gl, scene, camera } = useThree();
  const { composer, bloom } = useMemo(() => {
    const c = new EffectComposer(gl);
    c.setSize(W, H);
    c.addPass(new RenderPass(scene, camera));
    const b = new UnrealBloomPass(new THREE.Vector2(W, H), 1, 0.5, 0.3);
    c.addPass(b);
    c.addPass(new OutputPass());
    return { composer: c, bloom: b };
  }, [gl, scene, camera]);
  bloom.strength = strength;                         // these may change frame to frame
  bloom.radius = radius;
  bloom.threshold = threshold;
  useFrame(() => composer.render(), 1);
  return null;
};

/** A texture of glyphs drawn in the film's mono face, ready once the font is. Glyphs are 128 x 256 cells. */
export const GLYPHS = "0123456789:.VOIDX- ";
export const useGlyphAtlas = () => {
  const [tex, setTex] = useState<THREE.CanvasTexture | null>(null);
  const [handle] = useState(() => delayRender("glyph atlas"));
  useEffect(() => {
    (async () => {
      await document.fonts.load(`700 200px "${FONT.ui}"`);
      const c = document.createElement("canvas");
      c.width = 128 * GLYPHS.length;
      c.height = 256;
      const g = c.getContext("2d")!;
      g.fillStyle = "#fff";
      g.font = `700 200px "${FONT.ui}"`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      for (let i = 0; i < GLYPHS.length; i++) g.fillText(GLYPHS[i], i * 128 + 64, 140);
      const t = new THREE.CanvasTexture(c);
      t.anisotropy = 8;
      t.minFilter = THREE.LinearMipmapLinearFilter;
      t.generateMipmaps = true;
      setTex(t);
      continueRender(handle);
    })().catch((e) => cancelRender(e));
  }, [handle]);
  return tex;
};

export const Bars: React.FC<{ on?: number }> = ({ on = 1 }) => (
  <>
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: BAR * on, background: "#000" }} />
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: BAR * on, background: "#000" }} />
  </>
);

/** A subtitle line, MW3 style: blue speaker tag, white text, bottom of the frame. */
export const Sub: React.FC<{ who: string; text: string; op?: number }> = ({ who, text, op = 1 }) => (
  <div style={{ position: "absolute", left: 0, right: 0, bottom: BAR + 70, textAlign: "center", fontFamily: FONT.sub, fontWeight: 600, fontSize: 33,
    color: "#f2f2f0", textShadow: "0 2px 6px rgba(0,0,0,0.95), 0 0 2px rgba(0,0,0,0.9)", opacity: op }}>
    {/* a soft pool of shade behind the line, so it reads over bright geometry (a lit screen, a PCB) */}
    <span style={{ display: "inline-block", padding: "16px 110px 18px",
      background: "radial-gradient(ellipse at 50% 55%, rgba(0,0,0,0.74) 0%, rgba(0,0,0,0.55) 50%, rgba(0,0,0,0) 76%)" }}>
      <span style={{ color: MW.blue }}>{who}: </span>{text}
    </span>
  </div>
);

export type Line = { at: number; len: number; who: string; text: string };
export const Subs: React.FC<{ f: number; lines: Line[] }> = ({ f, lines }) => {
  const l = lines.find((q) => f >= q.at && f < q.at + q.len);
  return l ? <Sub who={l.who} text={l.text} /> : null;
};

export const Mono: React.FC<{ s: number; c?: string; w?: number; ls?: string; style?: React.CSSProperties; children: React.ReactNode }> = ({ s, c = MW.text, w = 400, ls = "0.02em", style, children }) => (
  <div style={{ fontFamily: FONT.ui, fontSize: s, color: c, fontWeight: w, letterSpacing: ls, whiteSpace: "pre", lineHeight: 1.15, ...style }}>{children}</div>
);

/** Sets the R3F camera from a plain description every frame. */
export const CameraAt: React.FC<{ pos: THREE.Vector3; target: THREE.Vector3; fov?: number; up?: THREE.Vector3; roll?: number }> = ({ pos, target, fov = 35, up, roll = 0 }) => {
  const { camera } = useThree();
  const cam = camera as THREE.PerspectiveCamera;
  cam.position.copy(pos);
  cam.up.copy(up ?? new THREE.Vector3(0, 1, 0));
  cam.fov = fov;
  cam.near = 1;
  cam.far = 20000;
  cam.lookAt(target);
  if (roll) cam.rotateZ(roll);
  cam.updateProjectionMatrix();
  return null;
};

/** An MW3 intel card: the black box grows from its top-left over 6 frames, the header flickers on, then the body
    wipes down from the top over 10 frames. `out` is the frame it cuts away. */
export const Card: React.FC<{ f: number; at: number; out?: number; x: number; y: number; w: number; h: number; head?: string;
  headCol?: string; accent?: string; children?: React.ReactNode; bg?: string }> = ({ f, at, out = 1e9, x, y, w, h, head, headCol = MW.orange,
  accent = MW.orange, children, bg = "rgba(5,5,5,0.84)" }) => {
  if (f < at || f >= out) return null;
  const g = Math.min(1, Math.floor(prog(f, at, at + 6) * 4) / 4 + (f >= at + 6 ? 1 : 0.25));
  const headOn = f >= at + 7 && !(f >= at + 9 && f < at + 11);
  const wipe = prog(f, at + 10, at + 20);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: w * g, height: h * g, background: bg, borderLeft: `3px solid ${accent}` }} />
      {head && headOn ? (
        <div style={{ position: "absolute", left: 22, top: 16 }}>
          <Mono s={15} c={headCol} w={700} ls="0.2em">{head}</Mono>
        </div>
      ) : null}
      <div style={{ position: "absolute", left: 22, right: 22, top: head ? 48 : 18, bottom: 14, clipPath: `inset(0 0 ${100 - 100 * wipe}% 0)` }}>
        {children}
      </div>
    </div>
  );
};

/** An act slate: a big outlined numeral on the dark board, PART N, the title wiping on, an orange rule. It replaced a
    small mono line on black, which read as a dropout at viewing size. f: the slate's own frame; len: how long it shows. */
export const Slate: React.FC<{ f: number; part: string; title: string; len?: number; num?: string }> = ({ f, part, title, len = 50, num: big }) => {
  const num = big ?? part.replace(/^PART\s+/, "");
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: "radial-gradient(ellipse at 50% 46%, #15181b 0%, #0a0c0e 55%, #030405 100%)" }}>
      <div style={{ position: "absolute", inset: 0, opacity: 0.12, backgroundSize: "64px 64px",
        backgroundImage: "linear-gradient(rgba(124,196,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.35) 1px, transparent 1px)" }} />
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${1 + 0.05 * (f / len)})` }}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 560, lineHeight: 1, color: "transparent", letterSpacing: "0.02em",
          WebkitTextStroke: `3px rgba(240,138,36,${(0.34 * prog(f, 0, 8)).toFixed(3)})` }}>{num}</div>
      </div>
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 18 }}>
        <Mono s={24} c={MW.orange} w={700} ls="0.6em" style={{ opacity: f > 4 ? 1 : 0 }}>{part}</Mono>
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 92, lineHeight: 1, letterSpacing: "0.2em", paddingLeft: "0.2em", color: MW.text,
          clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(f, 8, 20))}% 0 0)`, textShadow: "0 0 40px rgba(124,196,255,0.18)" }}>{title}</div>
        <div style={{ width: 620 * easeOutExpo(prog(f, 12, 28)), height: 3, background: MW.orange, opacity: 0.9 }} />
      </div>
    </div>
  );
};

/** A key / value row for cards. */
export const Row: React.FC<{ k: string; v: React.ReactNode; c?: string; s?: number }> = ({ k, v, c = MW.text, s = 18 }) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
    <Mono s={s - 1} c={MW.dim} ls="0.12em">{k}</Mono>
    <Mono s={s} c={c} w={700}>{v}</Mono>
  </div>
);

/** A big verdict stamp that slams in: scale from 1.6 with a white flash on its first frames. */
export const Stamp: React.FC<{ f: number; at: number; text: string; col: string; x?: number; y?: number; s?: number; sub?: string }> = ({ f, at, text, col, x = W / 2, y = H / 2, s = 150, sub }) => {
  if (f < at) return null;
  const t = prog(f, at, at + 9);
  const sc = lerp(1.6, 1, 1 - Math.pow(1 - t, 3));
  return (
    <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%, -50%) scale(${sc}) rotate(-2deg)`, textAlign: "center", opacity: clamp(t * 3) }}>
      <div style={{ fontFamily: "Archivo Black", fontSize: s, letterSpacing: "0.06em", color: col, padding: "6px 40px", border: `8px solid ${col}`,
        textShadow: `0 0 40px ${col}88`, boxShadow: `0 0 60px ${col}44, inset 0 0 40px ${col}33`, background: "rgba(0,0,0,0.62)", lineHeight: 1.05 }}>{text}</div>
      {sub ? <Mono s={22} c={MW.text} ls="0.3em" style={{ marginTop: 18, opacity: prog(f, at + 12, at + 20), display: "inline-block",
        background: "rgba(0,0,0,0.66)", padding: "5px 16px 6px" }}>{sub}</Mono> : null}
    </div>
  );
};

/** Depth of field from the frame's own depth buffer: a golden-angle disc gather whose radius follows each pixel's
    circle of confusion. Focus and range are in scene units from the camera; blur is the largest radius in pixels. */
class DofPass extends Pass {
  q: FullScreenQuad;
  m: THREE.ShaderMaterial;
  constructor() {
    super();
    this.m = new THREE.ShaderMaterial({
      uniforms: { tColor: { value: null }, tDepth: { value: null }, uFocus: { value: 200 }, uRange: { value: 100 }, uBlur: { value: 10 },
        uNear: { value: 1 }, uFar: { value: 20000 }, uRes: { value: new THREE.Vector2(W, H) } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: /* glsl */ `
        uniform sampler2D tColor; uniform sampler2D tDepth; uniform float uFocus, uRange, uBlur, uNear, uFar; uniform vec2 uRes;
        varying vec2 vUv;
        float lin(float d) { return uNear * uFar / (uFar - d * (uFar - uNear)); }
        float coc(vec2 uv) { float z = lin(texture2D(tDepth, uv).x); return clamp(abs(z - uFocus) / uRange, 0.0, 1.0); }
        void main() {                                                  // after D. Gustafsson's single-pass bokeh
          float zc = lin(texture2D(tDepth, vUv).x);
          float sc = coc(vUv) * uBlur;
          // one NaN pixel would become a black frame in bloom; ANGLE's D3D compiler deletes isnan(), but D3D's max() returns
          // the other operand for a NaN, so a clamp scrubs it
          vec3 col = min(max(texture2D(tColor, vUv).rgb, vec3(0.0)), vec3(65000.0));
          if (uBlur < 0.3) { gl_FragColor = vec4(col, 1.0); return; }
          float tot = 1.0, rad = 0.6, ang = 0.0, stp = max(0.6, uBlur * uBlur / 140.0);
          for (int i = 0; i < 160; i++) {
            if (rad >= uBlur) break;
            vec2 uv = vUv + vec2(cos(ang), sin(ang)) * rad / uRes;
            vec3 c = min(max(texture2D(tColor, uv).rgb, vec3(0.0)), vec3(65000.0));
            float z = lin(texture2D(tDepth, uv).x);
            float ss = coc(uv) * uBlur;
            if (z > zc) ss = clamp(ss, 0.0, sc * 2.0);                 // a sharp foreground does not take the blur behind it
            float m = smoothstep(rad - 0.5, rad + 0.5, ss);
            col += mix(col / tot, c, m);
            tot += 1.0;
            rad += stp / rad;
            ang += 2.39996;
          }
          gl_FragColor = vec4(col / tot, 1.0);
        }`,
    });
    this.q = new FullScreenQuad(this.m);
  }
  depth: THREE.DepthTexture | null = null;              // the depth the scene was drawn with this frame, for later passes
  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    this.m.uniforms.tColor.value = readBuffer.texture;
    this.m.uniforms.tDepth.value = readBuffer.depthTexture;
    this.depth = readBuffer.depthTexture;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.q.render(renderer);
  }
}

/** Camera motion blur by reprojection: each pixel's world point (from depth) is projected through the camera of half a
    frame earlier, and the image is smeared along that screen-space path, a 180 degree shutter for camera moves. */
class MotionPass extends Pass {
  q: FullScreenQuad;
  m: THREE.ShaderMaterial;
  out = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType });
  copy = new FullScreenQuad(new THREE.ShaderMaterial({ uniforms: { t: { value: null } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: "uniform sampler2D t; varying vec2 vUv; void main(){ gl_FragColor = texture2D(t, vUv); }" }));
  src: DofPass;
  constructor(src: DofPass) {
    super();
    this.src = src;
    this.m = new THREE.ShaderMaterial({
      uniforms: { tColor: { value: null }, tDepth: { value: null }, uInv: { value: new THREE.Matrix4() }, uPrev: { value: new THREE.Matrix4() },
        uRes: { value: new THREE.Vector2(W, H) }, uOn: { value: 0 }, uMax: { value: 30 } },   // longer smears stop reading as motion
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: /* glsl */ `
        uniform sampler2D tColor; uniform sampler2D tDepth; uniform mat4 uInv; uniform mat4 uPrev; uniform vec2 uRes;
        uniform float uOn; uniform float uMax;
        varying vec2 vUv;
        void main() {
          vec3 col = min(max(texture2D(tColor, vUv).rgb, vec3(0.0)), vec3(65000.0));
          if (uOn < 0.5) { gl_FragColor = vec4(col, 1.0); return; }
          float d = texture2D(tDepth, vUv).x;
          vec4 w = uInv * vec4(vUv * 2.0 - 1.0, d * 2.0 - 1.0, 1.0);
          w /= w.w;
          vec4 pc = uPrev * vec4(w.xyz, 1.0);
          if (pc.w <= 0.0) { gl_FragColor = vec4(col, 1.0); return; }
          vec2 vel = vUv - ((pc.xy / pc.w) * 0.5 + 0.5);
          float len = length(vel * uRes);
          if (len < 0.5) { gl_FragColor = vec4(col, 1.0); return; }
          if (len > uMax) vel *= uMax / len;
          float tot = 1.0;
          for (int i = 1; i < 14; i++) {
            col += min(max(texture2D(tColor, clamp(vUv - vel * (float(i) / 13.0), vec2(0.001), vec2(0.999))).rgb, vec3(0.0)), vec3(65000.0));
            tot += 1.0;
          }
          gl_FragColor = vec4(col / tot, 1.0);
        }`,
    });
    this.q = new FullScreenQuad(this.m);
  }
  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    // the scene's depth lives on the composer's first target, which may be this pass's write buffer: drawing into a
    // target while sampling its own depth is a WebGL feedback loop (the draw is dropped, the frame goes black), so the
    // blur goes to a private target and is copied over
    this.m.uniforms.tColor.value = readBuffer.texture;
    // the composer's ping-pong targets do not reset each frame (an odd number of passes swap), so the scene lands in
    // either target: take the depth it was actually drawn with, which the DOF pass saw
    this.m.uniforms.tDepth.value = this.src.depth;
    renderer.setRenderTarget(this.out);
    this.q.render(renderer);
    (this.copy.material as THREE.ShaderMaterial).uniforms.t.value = this.out.texture;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.copy.render(renderer);
  }
}

/** A camera as the acts describe it, for the motion blur's "half a frame ago". */
export type CamDesc = { pos: THREE.Vector3; target: THREE.Vector3; fov?: number; up?: THREE.Vector3; roll?: number };

export type Dof = { focus: number; range: number; blur: number };
/** Bloom, and depth of field when `dof` is given: the film's post stack inside three. Takes over rendering (priority 1). */
export type Rays = { world: THREE.Vector3; amount: number; tint?: string; threshold?: number; decay?: number };
export const Post: React.FC<{ strength?: number; radius?: number; threshold?: number; dof?: Dof | null; prev?: CamDesc | null; rays?: Rays | null }> = ({ strength = 0.7, radius = 0.5, threshold = 1.1, dof, prev, rays }) => {
  const { gl, scene, camera, advance } = useThree();
  // a still can be captured before the canvas has drawn at all; hold the frame until the composer has rendered once
  const drawn = useRef(false);
  const [first] = useState(() => delayRender("first composed frame"));
  useEffect(() => { if (!drawn.current) advance(performance.now()); }, [advance]);
  const { composer, bloom, dp, mp, rp } = useMemo(() => {
    const rt = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 0 });
    rt.depthTexture = new THREE.DepthTexture(W, H, THREE.FloatType);
    const c = new EffectComposer(gl, rt);
    c.setSize(W, H);
    c.addPass(new RenderPass(scene, camera));
    const d = new DofPass();
    c.addPass(d);
    const mb = new MotionPass(d);                         // reads the depth the DOF pass was handed this frame
    c.addPass(mb);
    const rp = new RaysPass();                            // light shafts, before bloom so they glow too
    c.addPass(rp);
    const b = new UnrealBloomPass(new THREE.Vector2(W, H), 1, 0.5, 1);
    c.addPass(b);
    c.addPass(new OutputPass());
    return { composer: c, bloom: b, dp: d, mp: mb, rp };
  }, [gl, scene, camera]);
  bloom.strength = strength;
  bloom.radius = radius;
  bloom.threshold = threshold;
  dp.m.uniforms.uBlur.value = 0;                     // always on: with no blur it still scrubs NaNs
  if (dof) {
    const cam = camera as THREE.PerspectiveCamera;
    Object.assign(dp.m.uniforms.uFocus, { value: dof.focus });
    dp.m.uniforms.uRange.value = dof.range;
    dp.m.uniforms.uBlur.value = dof.blur;
    dp.m.uniforms.uNear.value = cam.near;
    dp.m.uniforms.uFar.value = cam.far;
  }
  // set in the render pass, like the DOF above, never inside useFrame: R3F swaps in a new useFrame callback only after
  // the commit, and Remotion advances right after the props change, so a callback would see the previous frame's
  // `prev` (four frames back with four render tabs, or another shot entirely) and smear the image
  const prevCam = useMemo(() => new THREE.PerspectiveCamera(35, W / H, 1, 20000), []);
  rp.m.uniforms.uAmount.value = 0;
  if (rays && rays.amount > 0.001) {                    // the light's place on screen, from the camera CameraAt just set
    const cam = camera as THREE.PerspectiveCamera;
    cam.updateMatrixWorld();
    const r = raysAt(cam, rays.world);
    rp.m.uniforms.uCenter.value.copy(r.center);
    rp.m.uniforms.uAmount.value = rays.amount * r.visible;
    rp.m.uniforms.uTint.value.set(rays.tint ?? "#ffd9a6");
    rp.m.uniforms.uThreshold.value = rays.threshold ?? 0.35;
    rp.m.uniforms.uDecay.value = rays.decay ?? 0.955;
  }
  mp.m.uniforms.uOn.value = prev ? 1 : 0;
  if (prev) {
    const cam = camera as THREE.PerspectiveCamera;                   // CameraAt, earlier in this render, has set it
    cam.updateMatrixWorld();
    mp.m.uniforms.uInv.value.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse).invert();
    prevCam.fov = prev.fov ?? cam.fov;
    prevCam.near = cam.near;
    prevCam.far = cam.far;
    prevCam.position.copy(prev.pos);
    prevCam.up.copy(prev.up ?? cam.up);
    prevCam.lookAt(prev.target);
    if (prev.roll) prevCam.rotateZ(prev.roll);
    prevCam.updateProjectionMatrix();
    prevCam.updateMatrixWorld();
    mp.m.uniforms.uPrev.value.multiplyMatrices(prevCam.projectionMatrix, prevCam.matrixWorldInverse);
  }
  useFrame(() => {
    composer.render();
    if (!drawn.current) { drawn.current = true; continueRender(first); }
  }, 1);
  return null;
};

/** A camera kick for impacts: a few frames of decaying shake after each frame in `at`. Returns a CSS translate. */
export const kick = (f: number, at: number[], amp = 9) => {
  let x = 0, y = 0, sc = 1;
  for (const a of at) {
    const t = f - a;
    if (t < 0 || t > 16) continue;
    const e = Math.exp(-t / 3.2);
    x += amp * e * Math.sin(t * 2.7 + a);
    y += amp * e * 0.7 * Math.cos(t * 3.4 + a * 0.5);
    sc = Math.max(sc, 1 + 0.03 * e);                                   // a punch-in, which also keeps the edges covered
  }
  return `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) scale(${sc.toFixed(4)})`;
};

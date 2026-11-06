import { useThree } from "@react-three/fiber";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { staticFile } from "remotion";
import * as THREE from "three";
import { Brackets, DataFeed, Flash, Frame, Glitch, Head, Mono, TypeText, fade, jitter } from "../hud";
import { C, H, TL, W, glow } from "../theme";
import {
  CENTRE, META_, SLOTS, applyPose, asmMatrix, assembled, buildParts, camAt, cameraFor, clip, partCentre, partPose, xrayAt,
  projectTo, section, stepDone, stepStart,
} from "../three/consoleModel";
import { useBuffer, useTexture } from "../three/useAsset";
import { clamp, easeOut, easeOutExpo, lerp, pad, prog, typeEntry } from "../util";

const S = TL.shots;
const B = TL.build;
const SW = TL.swap;
const HERO = TL.hero;
const SEC = TL.section;
const POWER = S.reveal[0] + 100;

const Rig: React.FC<{ f: number }> = ({ f }) => {
  const { camera, gl } = useThree();
  gl.localClippingEnabled = true;
  const c = camAt(f);
  const cam = camera as THREE.PerspectiveCamera;
  cam.position.copy(c.pos);
  cam.up.set(0, 0, 1);
  cam.fov = c.fov;
  cam.near = 1;
  cam.far = 5000;
  cam.lookAt(c.target);
  cam.updateProjectionMatrix();
  return null;
};

/** How far through the section cut we are at frame f: the cut plane's y, or null when there is no cut. */
const sectionY = (f: number) => {
  if (f < SEC.in[0] || f > SEC.out[1]) return null;
  const t = f < SEC.out[0] ? easeOut(prog(f, SEC.in[0], SEC.in[1])) : 1 - easeOut(prog(f, SEC.out[0], SEC.out[1]));
  return lerp(-12, 64, t);
};

const Scene: React.FC<{ f: number; buf: ArrayBuffer; screenTex: THREE.Texture }> = ({ f, buf, screenTex }) => {
  const parts = useMemo(() => buildParts(buf), [buf]);
  const { gl, scene } = useThree();
  useMemo(() => {                                   // studio lighting for the coloured CAD: a soft room for reflections
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 1.05;
  }, [gl, scene]);
  const asm = useMemo(() => { const g = new THREE.Group(); g.matrixAutoUpdate = false; return g; }, []);
  const grid = useMemo(() => {
    const g = new THREE.GridHelper(900, 45, C.line, C.line);
    g.rotation.x = Math.PI / 2;
    g.position.set(CENTRE.x, CENTRE.y, -4);
    (g.material as THREE.Material).transparent = true;
    return g;
  }, []);
  const sweep = useMemo(() => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(260, 80), new THREE.MeshBasicMaterial({
      color: C.accent, transparent: true, opacity: 0.16, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
    m.rotation.x = -Math.PI / 2;
    return m;
  }, []);
  const screen = useMemo(() => {
    const [x0, x1, y0, y1] = META_.screen.rect;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(x1 - x0, y1 - y0), new THREE.MeshBasicMaterial({ transparent: true, toneMapped: false }));
    m.position.set((x0 + x1) / 2, (y0 + y1) / 2, META_.screen.glassZ - 0.35);
    m.rotation.y = Math.PI;
    m.renderOrder = 6;
    return m;
  }, []);
  // the hero scan reveal (y sweep) and the section cut (y plane)
  const rev = prog(f, S.hero[0], S.hero[0] + 76);
  clip.constant = rev < 1 ? lerp(-6, 132, easeOut(rev)) : 1e5;
  const sy = sectionY(f);
  section.constant = sy === null ? 1e5 : -sy;
  sweep.visible = (rev > 0 && rev < 1) || sy !== null;
  sweep.position.set(CENTRE.x, rev > 0 && rev < 1 ? clip.constant : sy ?? 0, 22);
  // an x-ray scan band that runs along the device during the hero
  const st = prog(f, S.hero[0] + 84, HERO.explode - 10);
  const scan = { x: lerp(-30, 232, st), amt: st > 0 && st < 1 ? 1 : 0 };
  const xr = xrayAt(f);
  for (const p of parts) applyPose(p, partPose(p.meta, f), scan, xr);
  if (asm.children.length === 0) { for (const p of parts) asm.add(p.group); asm.add(screen); }
  asm.matrix.copy(asmMatrix(f));
  asm.matrixWorldNeedsUpdate = true;
  (grid.material as THREE.Material).opacity = 0.09 * clamp(1 - prog(f, S.reveal[0], S.reveal[0] + 50)) * clamp((f - S.hero[0]) / 30);
  const mat = screen.material as THREE.MeshBasicMaterial;
  mat.map = screenTex;
  const flick = f >= POWER && f < POWER + 24 ? (Math.floor((f - POWER) / 3) % 2 ? 0.25 : 1) : 1;
  mat.opacity = prog(f, POWER, POWER + 24) * flick;
  screen.visible = f >= POWER;
  return (
    <>
      <Rig f={f} />
      <ambientLight intensity={0.25} />
      <directionalLight position={[-260, -420, 640]} intensity={2.2} />
      <directionalLight position={[460, 380, 260]} intensity={0.9} color="#a8ccff" />
      <primitive object={grid} />
      <primitive object={sweep} />
      <primitive object={asm} />
    </>
  );
};

const stepNow = (f: number) => (f < B.start ? 0 : Math.min(B.steps, Math.floor((f - B.start) / B.stepLen) + 1));
const partsOf = (s: number) => META_.parts.filter((p) => SLOTS.get(p.name)?.step === s);

/** CAD dimension lines on the assembled device. */
const Dims: React.FC<{ f: number; cam: THREE.Camera }> = ({ f, cam }) => {
  const [lo, hi] = META_.bounds;
  const off = 14;
  const dims: [THREE.Vector3, THREE.Vector3, THREE.Vector3, string][] = [
    [new THREE.Vector3(lo[0], lo[1] - off, lo[2]), new THREE.Vector3(hi[0], lo[1] - off, lo[2]), new THREE.Vector3(0, -1, 0), `${(hi[0] - lo[0]).toFixed(1)} MM`],
    [new THREE.Vector3(hi[0] + off, lo[1], lo[2]), new THREE.Vector3(hi[0] + off, hi[1], lo[2]), new THREE.Vector3(1, 0, 0), `${(hi[1] - lo[1]).toFixed(1)} MM`],
    [new THREE.Vector3(hi[0] + off, lo[1] - off, lo[2]), new THREE.Vector3(hi[0] + off, lo[1] - off, hi[2]), new THREE.Vector3(1, -1, 0), `${(hi[2] - lo[2]).toFixed(1)} MM`],
  ];
  const op = fade(f, HERO.dims, HERO.dims + 10, HERO.explode - 6, HERO.explode + 6);
  if (op <= 0) return null;
  return (
    <svg style={{ position: "absolute", inset: 0, opacity: op, overflow: "visible" }} width={W} height={H}>
      {dims.map(([a, b, n, label], i) => {
        const t = easeOut(prog(f, HERO.dims + i * 12, HERO.dims + i * 12 + 22));
        const pa = projectTo(f, a, cam), pb = projectTo(f, b, cam);
        const bx = lerp(pa.x, pb.x, t), by = lerp(pa.y, pb.y, t);
        const ea = projectTo(f, a.clone().add(n.clone().multiplyScalar(-off + 2)), cam);
        const eb = projectTo(f, b.clone().add(n.clone().multiplyScalar(-off + 2)), cam);
        const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;
        return (
          <g key={i} stroke={C.accent} fill="none" strokeWidth={1.4}>
            <line x1={ea.x} y1={ea.y} x2={pa.x} y2={pa.y} strokeOpacity={0.6} />
            <line x1={eb.x} y1={eb.y} x2={pb.x} y2={pb.y} strokeOpacity={0.6 * t} />
            <line x1={pa.x} y1={pa.y} x2={bx} y2={by} />
            <circle cx={pa.x} cy={pa.y} r={3} fill={C.accent} />
            {t > 0.98 ? <circle cx={pb.x} cy={pb.y} r={3} fill={C.accent} /> : null}
            <text x={mx + 10} y={my - 10} fill={C.accent} stroke="none" fontFamily="Share Tech Mono" fontSize={20} opacity={t}
              style={{ textShadow: glow(C.accent, 3) }}>{label}</text>
          </g>
        );
      })}
    </svg>
  );
};

const HeroHud: React.FC<{ f: number; cam: THREE.Camera }> = ({ f, cam }) => {
  if (f >= S.build[0] + 30) return null;
  const ids = ["spec1", "spec2", "spec3", "spec4", "spec5", "spec6"];
  const out = 1 - prog(f, HERO.explode - 8, HERO.explode + 8);
  const ex = prog(f, HERO.explode, HERO.explode + 6);
  const exOut = fade(f, HERO.explode, HERO.explode + 6, S.build[0] - 4, S.build[0] + 4);
  return (
    <>
      <Dims f={f} cam={cam} />
      <div style={{ position: "absolute", left: 110, top: 170, display: "flex", flexDirection: "column", gap: 10, opacity: out }}>
        <Head size={20} color={C.dim} spacing="0.35em">Asset file</Head>
        {ids.map((id) => {
          const e = typeEntry(id);
          return <TypeText key={id} f={f} text={e.text} start={e.frame} cps={e.cps} size={19} color={C.ink} cursor={f < e.frame + 30} />;
        })}
      </div>
      <div style={{ position: "absolute", left: 110, bottom: 112, opacity: out * clamp((f - S.hero[0]) / 14) }}>
        <Mono size={20} color={C.accent} style={{ textShadow: glow(C.accent, 3) }}>X-RAY // FULL ASSEMBLY</Mono>
        <Head size={80} weight={700} style={{ marginTop: 6, textShadow: glow(C.ink, 7) }}>Any% Handheld</Head>
      </div>
      {ex > 0 ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 128, display: "flex", justifyContent: "center", opacity: exOut }}>
          <div style={{ border: `2px solid ${C.accent}`, padding: "10px 34px", background: "rgba(255,178,63,0.08)",
            transform: `scale(${lerp(1.25, 1, easeOutExpo(ex))})` }}>
            <Head size={52} color={C.accent} spacing="0.4em" style={{ textShadow: glow(C.accent, 6) }}>Exploded view // 59 parts</Head>
          </div>
        </div>
      ) : null}
    </>
  );
};

const BOM: React.FC<{ f: number }> = ({ f }) => (
  <div style={{ position: "absolute", left: 110, top: 160, opacity: fade(f, S.build[0], S.build[0] + 20, assembled + 30, assembled + 60) }}>
    <Head size={18} color={C.dim} spacing="0.35em">Bill of materials</Head>
    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
      {TL.steps.map((s, i) => {
        const done = i === 0 || f >= stepDone(i);
        const active = i > 0 && f >= stepStart(i) && !done;
        const color = active ? C.accent : done ? C.ink : C.dim;
        return (
          <Mono key={i} size={16} color={color} style={{ textShadow: active ? glow(C.accent, 3) : undefined }}>
            {`${active ? "[>]" : done ? "[x]" : "[ ]"} ${pad(i)} ${s.label}`}
          </Mono>
        );
      })}
    </div>
  </div>
);

/** The step's name, slammed in at every cut, with a live count for screws and inserts. */
const StepBanner: React.FC<{ f: number }> = ({ f }) => {
  const s = stepNow(f);
  if (s === 0 || f >= assembled + 40) return null;
  const at = stepStart(s);
  const t = easeOutExpo(prog(f, at, at + 12));
  const st = TL.steps[s] as { label: string; sub: string; count?: string };
  const counted = partsOf(s).filter((p) => ["spin", "press"].includes(SLOTS.get(p.name)!.move.kind));
  const landed = counted.filter((p) => f >= SLOTS.get(p.name)!.land).length;
  return (
    <>
      <div style={{ position: "absolute", left: 110, top: 548 }}>{/* under the parts list, clear of the narration line */}
        <Mono size={20} color={C.accent} style={{ textShadow: glow(C.accent, 3) }}>{`STEP ${pad(s)} / ${pad(B.steps)}`}</Mono>
        <div style={{ overflow: "hidden", marginTop: 6 }}>
          <Head size={70} weight={700} style={{ transform: `translateX(${(1 - t) * -60}px)`, opacity: t, textShadow: glow(C.ink, 6) }}>{st.label}</Head>
        </div>
        <Mono size={20} color={C.line} style={{ marginTop: 8, opacity: t }}>{st.sub}</Mono>
        {st.count && counted.length ? (
          <Mono size={24} color={landed === counted.length ? C.ink : C.accent} style={{ marginTop: 12, textShadow: glow(C.accent, 3) }}>
            {`${st.count} ${landed}/${counted.length}`}
          </Mono>
        ) : null}
      </div>
      <div style={{ position: "absolute", right: 104, top: 168, opacity: 0.16 * t + 0.08 }}>
        <Head size={170} weight={700} spacing="0" style={{ transform: `scale(${lerp(1.3, 1, t)})`, transformOrigin: "right top" }}>{pad(s)}</Head>
      </div>
    </>
  );
};

/** A leader from the parts moving right now to a label in the right column. */
const Callout: React.FC<{ f: number; cam: THREE.Camera }> = ({ f, cam }) => {
  const s = stepNow(f);
  if (s === 0 || f >= assembled) return null;
  const moving = partsOf(s).filter((p) => { const sl = SLOTS.get(p.name)!; return f >= sl.start - 4 && f < sl.land + 18; });
  if (!moving.length) return null;
  const c = new THREE.Vector3();
  for (const p of moving) c.add(partCentre(p, f));
  c.multiplyScalar(1 / moving.length);
  const p = projectTo(f, c, cam);
  const st = TL.steps[s];
  const kind = SLOTS.get(moving[0].name)!.move.kind;
  const verb: Record<string, string> = { drop: "PLACE", spin: "SCREW IN", press: "HEAT-PRESS", tilt: "SEAT", slide: "SLIDE IN", snap: "MAGNET SNAP" };
  const lx = W - 600, ly = clamp(p.y - 150, 380, H - 380);
  const t = easeOut(prog(f, stepStart(s) + 2, stepStart(s) + 14));
  return (
    <div style={{ position: "absolute", inset: 0, opacity: t }}>
      <svg style={{ position: "absolute", inset: 0, overflow: "visible" }} width={W} height={H}>
        <circle cx={p.x} cy={p.y} r={8} fill="none" stroke={C.accent} strokeWidth={2} />
        <circle cx={p.x} cy={p.y} r={2.5} fill={C.accent} />
        <polyline points={`${p.x},${p.y} ${lx - 60},${ly + 26} ${lx - 14},${ly + 26}`} fill="none" stroke={C.accent} strokeWidth={1.5} />
      </svg>
      <div style={{ position: "absolute", left: lx, top: ly, padding: "10px 18px 12px", background: "rgba(2, 8, 14, 0.72)",
        borderLeft: `3px solid ${C.accent}`, width: 420 }}>
        <Mono size={15} color={C.dim}>{`OP ${pad(s)}.${moving.length > 1 ? "x" + moving.length : "1"} // ${verb[kind] ?? "PLACE"}`}</Mono>
        <Head size={30} color={C.accent} style={{ marginTop: 6, textShadow: glow(C.accent, 4) }}>{st.label}</Head>
      </div>
    </div>
  );
};

const Progress: React.FC<{ f: number }> = ({ f }) => {
  const total = SLOTS.size;
  let done = 0;
  for (const sl of SLOTS.values()) if (f >= sl.land) done++;
  const pct = clamp(done / total);
  return (
    <div style={{ position: "absolute", right: 110, top: 128, textAlign: "right", opacity: fade(f, S.build[0], S.build[0] + 20, S.allies[0], S.allies[0] + 20) }}>
      <Mono size={18} color={C.ink}>{`ASSEMBLY ${String(Math.round(pct * 100)).padStart(3, " ")}%  //  ${done + 1}/${total + 1} PARTS`}</Mono>
      <div style={{ width: 360, height: 6, border: `1px solid ${C.line}`, marginTop: 8, marginLeft: "auto" }}>
        <div style={{ width: `${pct * 100}%`, height: "100%", background: pct >= 1 ? C.accent : C.ink }} />
      </div>
    </div>
  );
};

const SectionHud: React.FC<{ f: number; cam: THREE.Camera }> = ({ f, cam }) => {
  const y = sectionY(f);
  const op = fade(f, assembled, assembled + 12, S.allies[0] - 10, S.allies[0]);
  if (op <= 0) return null;
  const corners = y === null ? [] : [[-14, -4], [216, -4], [216, 54], [-14, 54]].map(([x, z]) => projectTo(f, new THREE.Vector3(x, y, z), cam));
  return (
    <div style={{ position: "absolute", inset: 0, opacity: op }}>
      {corners.length ? (
        <svg style={{ position: "absolute", inset: 0 }} width={W} height={H}>
          <polygon points={corners.map((c) => `${c.x},${c.y}`).join(" ")} fill={C.accent} fillOpacity={0.05} stroke={C.accent} strokeWidth={1.5} strokeDasharray="14 8" />
        </svg>
      ) : null}
      <div style={{ position: "absolute", left: 0, right: 0, top: 150, display: "flex", justifyContent: "center", opacity: fade(f, assembled - 14, assembled, SEC.in[0] - 6, SEC.in[0] + 6) }}>
        <div style={{ border: `2px solid ${C.accent}`, padding: "8px 30px", background: "rgba(255,178,63,0.08)" }}>
          <Head size={36} color={C.accent} spacing="0.4em" style={{ textShadow: glow(C.accent, 5) }}>Assembly complete</Head>
        </div>
      </div>
      <div style={{ position: "absolute", left: 110, bottom: 112, opacity: fade(f, SEC.in[0], SEC.in[0] + 10, SEC.out[1] - 4, SEC.out[1] + 6) }}>
        <Mono size={20} color={C.accent} style={{ textShadow: glow(C.accent, 3) }}>X-RAY // CUT PLANE Y</Mono>
        <Head size={70} weight={700} style={{ marginTop: 6, textShadow: glow(C.ink, 6) }}>Section A-A</Head>
        <Mono size={20} color={C.line} style={{ marginTop: 8 }}>{`Y = ${(y ?? 0).toFixed(1)} MM`}</Mono>
      </div>
    </div>
  );
};

const PANEL_PARTS = (kind: string) => META_.parts.filter((p) => p.panel === kind).map((p) => p.name);

const PartBox: React.FC<{ f: number; parts: string[]; cam: THREE.Camera; opacity?: number }> = ({ f, parts, cam, opacity = 1 }) => {
  const metas = META_.parts.filter((p) => parts.includes(p.name));
  if (!metas.length) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const m of metas) {
    const mm = partPose(m, f).m;
    const [lo, hi] = m.bounds;
    for (const cx of [lo[0], hi[0]]) for (const cy of [lo[1], hi[1]]) for (const cz of [lo[2], hi[2]]) {
      const q = projectTo(f, new THREE.Vector3(cx, cy, cz).applyMatrix4(mm), cam);
      x0 = Math.min(x0, q.x); y0 = Math.min(y0, q.y); x1 = Math.max(x1, q.x); y1 = Math.max(y1, q.y);
    }
  }
  return <Brackets x={x0 - 16} y={y0 - 16} w={x1 - x0 + 32} h={y1 - y0 + 32} len={20} color={C.accent} width={2} opacity={opacity} />;
};

const Allies: React.FC<{ f: number; cam: THREE.Camera }> = ({ f, cam }) => {
  const [a0, a1] = S.allies;
  if (f < a0 - 10 || f > a1 + 20) return null;
  const idx = SW.swaps.filter((sw) => f >= sw + 16).length;
  const op = fade(f, a0, a0 + 16, a1 - 10, a1 + 10);
  const at = idx === 0 ? a0 + 10 : SW.swaps[idx - 1] + 60;
  return (
    <>
      <div style={{ position: "absolute", right: 110, top: 150, textAlign: "right", opacity: op }}>
        <Head size={22} color={C.dim} spacing="0.35em">Rear panels</Head>
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
          {TL.allies.map((a, i) => (
            <Mono key={a.kind} size={22} color={i === idx ? C.accent : i < idx ? C.ink : C.dim} style={{ textShadow: i === idx ? glow(C.accent, 3) : undefined }}>
              {`${(a.role.split("// ")[1] ?? a.name).padEnd(11, " ")} ${i < idx ? "STOWED" : i === idx ? "MOUNTED" : "STANDBY"}`}
            </Mono>
          ))}
        </div>
      </div>
      <PartBox f={f} cam={cam} parts={PANEL_PARTS(TL.allies[idx].kind)} opacity={op * easeOut(prog(f, at, at + 12))} />
      <div style={{ position: "absolute", left: 110, bottom: 112, opacity: op }}>
        <Mono size={20} color={C.accent}>MAGNETIC REAR PANEL // HOT-SWAP</Mono>
        <Head size={70} weight={700} style={{ marginTop: 6, textShadow: glow(C.ink, 6) }}>{TL.allies[idx].name}</Head>
        <Mono size={20} color={C.line} style={{ marginTop: 8 }}>{TL.allies[idx].role}</Mono>
      </div>
    </>
  );
};

const Ready: React.FC<{ f: number }> = ({ f }) => {
  const e = typeEntry("ready");
  if (f < e.frame) return null;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 70, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
      <TypeText f={f} text={e.text} start={e.frame} cps={e.cps} size={44} head color={C.accent} style={{ textShadow: glow(C.accent, 6), letterSpacing: "0.3em" }} />
      <Mono size={18} color={C.ink} style={{ opacity: prog(f, e.frame + 30, e.frame + 50) }}>ANY% HANDHELD // RASPBERRY PI 3B+ // 5 IN DSI // REV 3</Mono>
    </div>
  );
};

const cuts = Array.from({ length: B.steps }, (_, i) => stepStart(i + 1));

export const Build: React.FC<{ f: number }> = ({ f }) => {
  const buf = useBuffer(staticFile("console.bin"));
  const screenTex = useTexture(staticFile("screen.png"));
  const cam = cameraFor(f);
  const end = S.reveal[1];
  const cut = cuts.find((c) => f >= c && f < c + 6);
  const label = f < S.build[0] ? "X-RAY // ANY% HANDHELD // REV 3" : f < assembled ? "ASSEMBLY // ANY% HANDHELD // REV 3"
    : f < S.allies[0] ? "SECTION // ANY% HANDHELD" : f < S.reveal[0] ? "LOADOUT // REAR PANEL" : "ASSET // FRONT";
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", transform: `translateX(${jitter(f, end - 18, 10) + (cut !== undefined ? jitter(f, cut, 4) * 0.6 : 0)}px)`,
      background: "radial-gradient(ellipse at 50% 45%, #071624 0%, #03080e 55%, #010306 100%)" }}>
      {buf && screenTex ? (
        <ThreeCanvas width={W} height={H} gl={{ antialias: true }} style={{ position: "absolute", inset: 0 }}>
          <Scene f={f} buf={buf} screenTex={screenTex} />
        </ThreeCanvas>
      ) : null}
      <Frame f={f} tl={label} tr={`T+${pad(Math.floor(f / 3600))}:${pad(Math.floor(f / 60) % 60)}:${pad(f % 60)}`}
        bl="SOURCE: CAD // ENCLOSURE.SCAD" br={`FRAME ${String(f).padStart(5, "0")}`} />
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none",
        background: "linear-gradient(to right, rgba(1,4,8,0.82) 0%, rgba(1,4,8,0.55) 20%, rgba(1,4,8,0) 38%), linear-gradient(to top, rgba(1,4,8,0.7) 0%, rgba(1,4,8,0) 32%)" }} />
      <HeroHud f={f} cam={cam} />
      <BOM f={f} />
      <Progress f={f} />
      <StepBanner f={f} />
      <Callout f={f} cam={cam} />
      <SectionHud f={f} cam={cam} />
      <Allies f={f} cam={cam} />
      <Ready f={f} />
      <DataFeed f={f} x={W - 330} y={H - 380} rows={8} cols={4} opacity={0.22 * fade(f, S.hero[0], S.hero[0] + 30, end - 40, end)} seed={13} />
      {f >= S.reveal[0] ? <Brackets x={W / 2 - 520} y={H / 2 - 300} w={1040} h={560} len={30} color={C.line} width={1.5}
        opacity={0.5 * prog(f, S.reveal[0] + 100, S.reveal[0] + 130)} /> : null}
      {cut !== undefined ? <><Glitch f={f} at={cut} len={5} /><Flash f={f} at={cut} len={6} peak={0.18} /></> : null}
      <Flash f={f} at={HERO.explode} len={10} color={C.accent} peak={0.25} />
      <Flash f={f} at={S.hero[0]} len={14} peak={0.5} />
      <Flash f={f} at={POWER} len={20} color={C.ink} peak={0.35} />
      <Glitch f={f} at={end - 18} len={12} />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: clamp(1 - (f - S.hero[0]) / 8) }} />
    </div>
  );
};

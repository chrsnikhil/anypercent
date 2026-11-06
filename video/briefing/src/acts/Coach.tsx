import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import React, { useEffect, useMemo, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import COACH from "../../public/coach/coach.json";
import SCREEN_SEQ from "../../public/coach/screen.json";
import TL from "../timeline.json";
import { applyPose, asmMatrix, buildParts, clip, FLIP, META_, partPose, section } from "../three/consoleModel";
import { useBuffer } from "../three/useAsset";
import { clamp, easeInOut, lerp, prog } from "../util";
import { BAR, Bars, CameraAt, Card, H, kick, Line, Mono, MW, Post, Row, Subs, W } from "./common";
import { Board } from "./GameReel";

/* THE COACH, after the check: the same logs coach the player. The console's screen shows the real launcher, drawn by
   its own code (prep/make_coach_frames.py), with PB saying the line coach.after_run() made from a real second run of
   Rush Hour (prep/make_coach.py: the route with a 45-frame hesitation near the line, played on the ROM, both logs
   replayed by the PC tool, the two ghosts compared by coach.compare()). The plot is those two ghosts. */

export const COACH_LEN = 630;                                         // shot B holds 1 s on the answer
const A_END = 330;                                                    // the console shot, then the ghost compare
const LINES: Line[] = [
  { at: 24, len: 280, who: "Handler", text: "The same log also coaches you. Meet PB, the launcher's coach." },
  { at: 342, len: 214, who: "Handler", text: "It replays both runs, and finds where the time went." },
];

const C = COACH as unknown as {
  best: { time_frames: number }; run: { time_frames: number }; period: number;
  splits: { worst: { start: number; end: number; loss: number } };
  best_track: number[][]; run_track: number[][];
};
const SEQ = SCREEN_SEQ as { lead: number; frames: number[]; images: number };
const fmt = (fr: number) => {
  const cs = Math.round((fr * 100) / 60);
  return `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
};
const secs = (fr: number) => `${(fr / 60).toFixed(2)} S`;

/* ---------------- shot A: the console, PB on its screen ---------------- */
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const FACE_UP = asmMatrix(FLIP[1]);
const DONE = TL.shots.end[0];
const SCREEN = (() => {
  const [x0, x1, y0, y1] = META_.screen.rect;
  return { w: x1 - x0, h: y1 - y0, c: new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, 48 - META_.screen.glassZ + 0.35) };
})();

/** Every distinct launcher frame as a texture, loaded once before the first frame renders. */
const useScreens = () => {
  const [tex, setTex] = useState<THREE.Texture[] | null>(null);
  const [handle] = useState(() => delayRender("coach screens"));
  useEffect(() => {
    const loader = new THREE.TextureLoader();
    Promise.all(Array.from({ length: SEQ.images }, (_, i) => new Promise<THREE.Texture>((res, rej) =>
      loader.load(staticFile(`coach/screen/${String(i).padStart(3, "0")}.jpg`), res, undefined, rej))))
      .then((all) => {
        all.forEach((t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; });
        setTex(all);
        continueRender(handle);
      })
      .catch((e) => cancelRender(e));
  }, [handle]);
  return tex;
};

/** The camera: low and to the side, a slow arc in to the screen (the MW3 creep, a touch faster: it is a reveal). */
const camA = (f: number) => {
  const t = easeInOut(clamp(f / A_END));
  // ends framed on PB's box (the screen's lower third), so it sits mid-frame, clear of the subtitle band
  const tg = SCREEN.c.clone().add(V(0, lerp(1, -13, t), 0));
  const a = lerp(-2.2, -1.68, t), r = lerp(215, 100, t);
  return { pos: V(tg.x + Math.cos(a) * r, tg.y + Math.sin(a) * r, lerp(205, 176, t)), target: tg, fov: lerp(30, 27, t) };
};

const SceneA: React.FC<{ f: number; buf: ArrayBuffer; screens: THREE.Texture[] }> = ({ f, buf, screens }) => {
  const { gl, scene } = useThree();
  useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 1.0;
  }, [gl, scene]);
  const parts = useMemo(() => buildParts(buf), [buf]);
  const poses = useMemo(() => parts.map((p) => partPose(p.meta, DONE)), [parts]);
  const rig = useMemo(() => {
    const g = new THREE.Group();
    g.matrixAutoUpdate = false;
    g.matrix.copy(FACE_UP);
    parts.forEach((p) => g.add(p.group));
    const mat = new THREE.MeshBasicMaterial({ map: screens[0], toneMapped: false });
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(SCREEN.w, SCREEN.h), mat);
    scr.position.copy(SCREEN.c);
    scr.renderOrder = 6;
    return { g, scr, mat };
  }, [parts, screens]);
  clip.constant = 1e5;
  section.constant = 1e5;
  parts.forEach((p, i) => applyPose(p, { ...poses[i], hi: 0 }, { x: -1000, amt: 0 }, 0));
  rig.mat.map = screens[SEQ.frames[Math.min(SEQ.frames.length - 1, Math.floor(f))]];
  rig.mat.color.setScalar(lerp(0.0, 1.05, clamp(f / 10)));             // the panel wakes as the shot opens
  const c = camA(f), p = camA(f - 0.5);
  return (
    <>
      <color attach="background" args={["#020304"]} />
      <CameraAt pos={c.pos} target={c.target} fov={c.fov} up={V(0, 0, 1)} />
      <ambientLight intensity={0.18} />
      <directionalLight position={[-300, -500, 600]} intensity={1.15} color="#fff3e6" />
      <directionalLight position={[500, 600, 160]} intensity={1.1} color="#7cc4ff" />
      <directionalLight position={[101, 900, 420]} intensity={0.55} color="#ffb070" />
      <primitive object={rig.g} />
      <primitive object={rig.scr} />
      <mesh position={[101, 62.5, -1]}>
        <planeGeometry args={[900, 700]} />
        <meshStandardMaterial color="#0b0c0e" roughness={0.55} metalness={0.1} />
      </mesh>
      <Post strength={0.4} radius={0.5} threshold={1.6} dof={{ focus: c.pos.distanceTo(c.target), range: 70, blur: 7 }}
        rays={{ world: SCREEN.c.clone(), amount: 0.18, tint: "#9fd6ff", threshold: 0.6 }} prev={{ ...p, up: V(0, 0, 1) }} />
    </>
  );
};

/* ---------------- shot B: the two ghosts ---------------- */
type Pt = { t: number; x: number };
const track = (raw: number[][]): Pt[] => {
  const s = raw.findIndex((p) => p[2] & 0x80);
  return raw.slice(s).filter((p) => p[2] & 0x80).map((p, i) => ({ t: i * C.period, x: p[0] }));
};
const BEST = track(C.best_track), RUN = track(C.run_track);
const T_END = Math.max(RUN[RUN.length - 1].t, BEST[BEST.length - 1].t);
const X0 = BEST[0].x, X1 = Math.max(...BEST.map((p) => p.x));
/** The gap to the best, the way PB measures it: for each point of the course, when this run first got there minus when
    the best did (frames), against this run's clock. Level (0) while the two runs are the same inputs, then the cliff. */
/** When a track first reached x, interpolated between its samples (one every 4 frames). */
const firstAt = (pts: Pt[], x: number) => {
  const i = pts.findIndex((p) => p.x >= x);
  if (i < 0) return undefined;
  if (i === 0 || pts[i].x === pts[i - 1].x) return pts[i].t;
  const a = pts[i - 1], b = pts[i];
  return a.t + ((x - a.x) / (b.x - a.x)) * (b.t - a.t);
};
const GAP: { t: number; g: number }[] = (() => {
  const raw: { t: number; g: number }[] = [];
  const xMax = Math.max(...RUN.map((p) => p.x));
  for (let x = X0; x <= xMax; x += 16) {
    const tr = firstAt(RUN, x), tb = firstAt(BEST, x);
    if (tr !== undefined && tb !== undefined) raw.push({ t: tr, g: tr - tb });
  }
  // a 5-point median takes out the sample-boundary spikes (the gap after the hesitation is a steady 46 frames)
  const out = raw.map((p, i) => ({ t: p.t, g: raw.slice(Math.max(0, i - 2), i + 3).map((q) => q.g).sort((u, v) => u - v)[Math.min(2, Math.floor(raw.slice(Math.max(0, i - 2), i + 3).length / 2))] }));
  out.push({ t: RUN[RUN.length - 1].t, g: C.run.time_frames - C.best.time_frames });   // at the line: the whole difference
  return out;
})();
const LEVEL_BEFORE = GAP.filter((p) => p.t < C.splits.worst.start).every((p) => Math.abs(p.g) < 0.5);
const gapAt = (t: number) => { let g = 0; for (const p of GAP) { if (p.t > t) break; g = p.g; } return g; };

/** The race's clock (run frames) at shot frame t: quick while the two runs are the same, slow over the last stretch. */
const SLOWMO = 70;
const raceClock = (t: number) => t < SLOWMO ? lerp(0, C.splits.worst.start, prog(t, 16, SLOWMO)) : lerp(C.splits.worst.start, T_END, prog(t, SLOWMO, 150));

/** GAP TO YOUR BEST, drawn up to run frame `upto`, with a live readout at its head. */
const GapPlot: React.FC<{ w: number; h: number; upto: number; hi: number }> = ({ w, h, upto, hi }) => {
  const G1 = 60;                                                       // the y axis: one second
  const sx = (t: number) => (t / T_END) * w, sy = (g: number) => h - (Math.min(g, G1) / G1) * (h - 20);
  const pts = GAP.filter((p) => p.t <= upto);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.t).toFixed(1)},${sy(p.g).toFixed(1)}`).join("") + (pts.length ? `L${sx(upto).toFixed(1)},${sy(gapAt(upto)).toFixed(1)}` : "");
  const wk = C.splits.worst, g = gapAt(upto), cliff = g > 0;
  const ticks: number[] = [];
  for (let s = 0; s <= T_END; s += 600) ticks.push(s);
  return (
    <svg width={w} height={h} style={{ overflow: "visible", position: "absolute", left: 0, top: 0 }}>
      <rect x={sx(wk.start)} y={0} width={Math.max(0, (sx(wk.end) - sx(wk.start)) * hi)} height={h} fill="rgba(255,178,63,0.13)" />
      {hi > 0 ? <line x1={sx(wk.start)} x2={sx(wk.start)} y1={0} y2={h} stroke={MW.amber} strokeWidth={1.5} strokeDasharray="4 5" opacity={hi} /> : null}
      {[0, 30, 60].map((v) => (
        <g key={v}>
          <line x1={0} x2={w} y1={sy(v)} y2={sy(v)} stroke={MW.faint} strokeWidth={1} strokeDasharray={v ? "2 6" : undefined} opacity={v ? 0.6 : 1} />
          <text x={-14} y={sy(v) + 5} fill={MW.dim} fontFamily="Space Mono" fontSize={16} textAnchor="end">{`+${(v / 60).toFixed(2)} S`}</text>
        </g>
      ))}
      {ticks.map((s) => (
        <g key={s}>
          <line x1={sx(s)} x2={sx(s)} y1={h} y2={h + 8} stroke={MW.faint} strokeWidth={1} />
          <text x={sx(s)} y={h + 30} fill={MW.dim} fontFamily="Space Mono" fontSize={16} textAnchor="middle">{fmt(s).slice(0, 4)}</text>
        </g>
      ))}
      <path d={d} fill="none" stroke={cliff ? MW.amber : MW.ice} strokeWidth={4} strokeLinejoin="round" />
      {pts.length ? (
        <g>
          <circle cx={sx(upto)} cy={sy(g)} r={12} fill={cliff ? MW.amber : MW.ice} opacity={0.22} />
          <circle cx={sx(upto)} cy={sy(g)} r={6} fill={cliff ? MW.amber : MW.ice} />
          <text x={sx(upto) - 20} y={sy(g) - 20} fill={cliff ? MW.amber : MW.ice} fontFamily="Space Mono" fontSize={26} fontWeight={700}
            textAnchor="end">{`+${(g / 60).toFixed(2)} S`}</text>
        </g>
      ) : null}
    </svg>
  );
};

const Compare: React.FC<{ f: number }> = ({ f }) => {
  const t = f - A_END;
  const clock = raceClock(t);
  const hi = prog(t, SLOWMO - 2, SLOWMO + 10);
  const wk = C.splits.worst;
  const PX = 210, PY = BAR + 120, PW = 1000, PH = 440;
  return (
    <>
      <Card f={t} at={1} x={PX - 100} y={PY - 70} w={PW + 150} h={PH + 150} head="GHOST COMPARE // RUSH HOUR // GAP TO YOUR BEST" accent={MW.ice} headCol={MW.ice}>
        <div style={{ position: "absolute", left: 78, top: 22, width: PW, height: PH }}>
          <GapPlot w={PW} h={PH} upto={clock} hi={hi} />
        </div>
        <Mono s={17} c={MW.amber} w={700} ls="0.3em" style={{ position: "absolute", right: 24, top: -32,
          opacity: t >= SLOWMO && t < 150 && Math.floor(t / 14) % 2 === 0 ? 1 : 0 }}>SLOW MOTION</Mono>
      </Card>
      <Card f={t} at={20} x={PX + PW + 90} y={PY - 70} w={480} h={196} head="TWO RUNS // TWO LOGS" accent={MW.text} headCol={MW.text}>
        <Row k="BEST" v={fmt(C.best.time_frames)} c={MW.ice} s={22} />
        <Row k="THIS RUN" v={fmt(C.run.time_frames)} c={MW.amber} s={22} />
        <Row k="OFF YOUR BEST" v={secs(C.run.time_frames - C.best.time_frames)} s={22} />
      </Card>
      <Card f={t} at={158} x={PX + PW + 90} y={PY + 150} w={480} h={LEVEL_BEFORE ? 250 : 200} head="WHERE THE TIME WENT" accent={MW.amber} headCol={MW.amber}>
        <Mono s={54} c={MW.amber} w={700}>{`${fmt(wk.start).slice(0, 4)} - ${fmt(wk.end).slice(0, 4)}`}</Mono>
        <Mono s={20} c={MW.text} ls="0.16em" style={{ marginTop: 10 }}>{`PB'S SPLIT: ${(wk.loss / 60).toFixed(2)} OF ${secs(C.run.time_frames - C.best.time_frames)}`}</Mono>
        {LEVEL_BEFORE ? <Mono s={20} c={MW.dim} ls="0.16em" style={{ marginTop: 10 }}>{"EVERYWHERE ELSE:\nLEVEL WITH YOUR BEST"}</Mono> : null}
      </Card>
      <div style={{ position: "absolute", left: PX - 100, top: PY + PH + 96, opacity: prog(t, 30, 40), display: "flex", gap: 40 }}>
        <Mono s={19} c={MW.text} ls="0.18em">EVERY NUMBER: THE REPLAY TOOL, ON BOTH LOGS</Mono>
        <Mono s={19} c={MW.dim} ls="0.18em">THE WORDS: PB</Mono>
      </div>
    </>
  );
};

export const Coach: React.FC = () => {
  const f = useCurrentFrame();
  const buf = useBuffer(staticFile("console.bin"));
  const screens = useScreens();
  const inA = f < A_END;
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {inA ? (
        <>
          {buf && screens ? (
            <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0 }}>
              <SceneA f={f} buf={buf} screens={screens} />
            </ThreeCanvas>
          ) : null}
          <Card f={f} at={40} x={70} y={BAR + 30} w={440} h={196} head="THE COACH // PB">
            <Row k="PART OF" v="THE LAUNCHER" />
            <Row k="FACTS FROM" v="THE REPLAY TOOL" c={MW.green} />
            <Row k="SAYS" v="WHERE TIME WENT" c={MW.amber} />
          </Card>
        </>
      ) : (
        <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * ((f - A_END) / 60)}) ${kick(f, [A_END + SLOWMO], 5)}`, transformOrigin: "50% 48%" }}>
          <Board f={f} t={clamp((f - A_END) / (COACH_LEN - A_END))} dir={0.8}>
            <Compare f={f} />
          </Board>
        </AbsoluteFill>
      )}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.7) 100%)" }} />
      <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: f >= A_END ? clamp(1 - (f - A_END) / 5) * 0.22 : 0 }} />
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, COACH_LEN - 8, COACH_LEN)) }} />
    </AbsoluteFill>
  );
};

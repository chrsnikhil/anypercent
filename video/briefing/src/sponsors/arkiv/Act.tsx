import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import SCREENS from "../../../public/handler/screens.json";
import PJ from "../../../public/sponsors/arkiv/panel.json";
import BUILT from "../../acts/built.json";
import { BAR, Bars, CameraAt, Card, H, kick, Line, Mono, MW, Post, Row, Slate, Stamp, Subs, W } from "../../acts/common";
import { Board } from "../../acts/GameReel";
import TLJ from "../../timeline.json";
import { applyPose, buildParts, CENTRE, clip, partPose, section } from "../../three/consoleModel";
import { useBuffer } from "../../three/useAsset";
import { clamp, easeInOut, easeOutExpo, lerp, prog } from "../../util";
import GH from "../../../public/sponsors/arkiv/ghost/ghosts.json";
import DATA from "./data.json";
import T from "./timing.json";

/* ANY% x ARKIV: the sponsor demo's own act (SPONSOR_DEMOS.md). After the title and the flash-forward (what Any% is), it
   says what Arkiv is for in Any% and shows the design that was red-teamed on 27 Oct, minus everything that leaned on
   World (dropped 5 Nov): every verified run is an Arkiv entity; the console's board (and anyone else) reads those rows
   back with one query; a look-alike row from a stranger's wallet is ignored because the board pins $creator to the
   checker; rows stay until season end + 30 days, anyone can extend, nobody can edit. The Arkiv calls are built at the
   event (built.json arkiv: false), so every card about a call says CALL: AT THE EVENT and no entity key, tx hash or
   address is shown; the values on screen are real (data.json). When built.json gains ARKIV clips (the field report),
   they play before the status card and the act grows to fit, held under 2:00 for the whole cut. */

const DONE = (BUILT.built as Record<string, boolean>).arkiv === true;
type Clip = { file: string; sponsor: string; title: string; rows: [string, string][]; line: string; seconds: number; from?: number };
const ALL = (BUILT.clips as unknown as Clip[]).filter((c) => c.sponsor === "ARKIV");
const BASE = T.pre.clips + T.post.len;
const CLIPS: Clip[] = [];
let acc = 0;
for (const c of ALL) {                                       // as many clips as keep the act (and so the cut) in time
  const n = Math.round(c.seconds * 60);
  if (BASE + acc + n > T.maxAct) break;
  CLIPS.push(c);
  acc += n;
}
const CLIP_AT = CLIPS.map((_, i) => T.pre.clips + CLIPS.slice(0, i).reduce((a, c) => a + Math.round(c.seconds * 60), 0));
const POST = T.pre.clips + acc;
export const ARKIV_LEN = POST + T.post.len;
const AT: Record<string, number> = { ...T.pre, stat1: POST + T.post.stat1, stat2: POST + T.post.stat2 };
const ORDER: [string, number][] = [
  ...["slate", "plate", "rec1", "rec2", "board1", "board2", "ghost1", "ghost2", "board3", "fake1", "fake2", "fake3", "exp1", "exp2"].map((k) => [k, AT[k]] as [string, number]),
  ...CLIPS.map((_, i) => [`clip${i}`, CLIP_AT[i]] as [string, number]),
  ["stat1", AT.stat1], ["stat2", AT.stat2],
];
const shotAt = (f: number) => {
  let i = 0;
  while (i < ORDER.length - 1 && f >= ORDER[i + 1][1]) i++;
  return { name: ORDER[i][0], t: f - ORDER[i][1], len: (i < ORDER.length - 1 ? ORDER[i + 1][1] : ARKIV_LEN) - ORDER[i][1] };
};
const LINES: Line[] = [
  ...(T.lines as unknown as [string, number, number, string, string?][]).map(([s, o, len, a, b]) => ({ at: AT[s] + o, len, who: "Handler", text: DONE && b ? b : a })),
  ...CLIPS.map((c, i) => ({ at: CLIP_AT[i] + 16, len: Math.round(c.seconds * 60) - 28, who: "Handler", text: c.line })),
].sort((a, b) => a.at - b.at);

const R = DATA.ria, YOU = DATA.you, FAKE = DATA.forged;
const fmt = (fr: number) => {
  const cs = Math.round((fr * 100) / 60);
  return `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
};
const HASH = `0x${R.log_sha256.slice(0, 8)}...${R.log_sha256.slice(-8)}`;
const CALL = DONE ? "CALL: BUILT" : "CALL: AT THE EVENT";
const callCol = DONE ? MW.green : MW.amber;
const blink = (f: number) => (DONE || f % 40 < 26 ? 1 : 0.25);

/* ---------------------------------------------------------------- the console and its Arkiv plate, in 3D */

type PM = { name: string; colour: string; nVerts: number; nIdx: number; nEdge: number; pos: number; nrm: number; idx: number; edge: number };
const ASSEMBLED = TLJ.shots.end[0];                         // every part home (the film's end shot), face down, rear up

const plateMeshes = (buf: ArrayBuffer) => (PJ.parts as PM[]).map((p) => {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, p.pos, p.nVerts * 3), 3));
  g.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(buf, p.nrm, p.nVerts * 3), 3));
  g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, p.idx, p.nIdx), 1));
  const logo = /logo/.test(p.name);
  const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(p.colour), roughness: logo ? 0.72 : 0.86, metalness: 0, envMapIntensity: logo ? 0.45 : 0.3,
    polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  const eg = new LineSegmentsGeometry();
  eg.setPositions(new Float32Array(buf, p.edge, p.nEdge * 3));
  const lm = new LineMaterial({ color: logo ? 0xb8c0c8 : 0x04124a, linewidth: 1.0, transparent: true, opacity: logo ? 0.5 : 0.7, worldUnits: false });
  lm.resolution.set(W, H);
  const grp = new THREE.Group();
  grp.add(new THREE.Mesh(g, mat), new LineSegments2(eg, lm));
  return grp;
});

const Pool: React.FC = () => {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `varying vec2 vUv;
      void main(){ vec2 d = (vUv - 0.5) * 2.0; float r2 = dot(d, d);
        vec3 c = vec3(0.045, 0.05, 0.07) * exp(-r2 * 4.0); gl_FragColor = vec4(c, 1.0); }`,
  }), []);
  return <mesh material={mat} position={[101, 62.5, -1]}><planeGeometry args={[900, 700]} /></mesh>;
};

type Cam3 = { pos: THREE.Vector3; target: THREE.Vector3; fov: number };
const D2R = Math.PI / 180;
const orbit = (az: number, el: number, r: number, target: THREE.Vector3, fov = 30): Cam3 => ({
  pos: target.clone().add(new THREE.Vector3(Math.sin(az * D2R) * Math.cos(el * D2R), -Math.cos(az * D2R) * Math.cos(el * D2R), Math.sin(el * D2R)).multiplyScalar(r)),
  target, fov,
});
const LOGO = new THREE.Vector3(101, 62, 47.6);
/** Locked-off framings with the measured linear push-in (0.66 %/s): wide on the plate, in on the logo, and the closer. */
const camFor = (shot: string, t: number): Cam3 => {
  const push = 1 - 0.0066 * (t / 60);
  if (shot === "plate") return orbit(-34, 38, 470 * push, CENTRE.clone().add(new THREE.Vector3(0, 0, 18)));
  if (shot === "plateIn") return orbit(-10, 56, 290 * push, LOGO.clone());
  return orbit(28, 30, 560 * push, CENTRE.clone().add(new THREE.Vector3(-84, 10, 14)));
};

const PlateScene: React.FC<{ cbuf: ArrayBuffer; pbuf: ArrayBuffer; cam: Cam3 }> = ({ cbuf, pbuf, cam }) => {
  const { gl, scene } = useThree();
  useMemo(() => {                                            // the film's studio light for the coloured CAD
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 0.85;
  }, [gl, scene]);
  const parts = useMemo(() => buildParts(cbuf), [cbuf]);
  const poses = useMemo(() => parts.map((p) => partPose(p.meta, ASSEMBLED)), [parts]);
  const plate = useMemo(() => plateMeshes(pbuf), [pbuf]);
  const root = useMemo(() => {
    const g = new THREE.Group();
    parts.forEach((p) => g.add(p.group));
    plate.forEach((p) => g.add(p));
    return g;
  }, [parts, plate]);
  clip.constant = 1e5;
  section.constant = 1e5;
  parts.forEach((p, i) => {
    applyPose(p, { ...poses[i], hi: 0, heat: 0 }, { x: -1000, amt: 0 }, 0);
    p.group.visible = !/^panel_/.test(p.meta.name);          // the ETHGlobal plates off: the Arkiv plate is on
  });
  return (
    <>
      <color attach="background" args={["#030405"]} />
      <CameraAt pos={cam.pos} target={cam.target} fov={cam.fov} up={new THREE.Vector3(0, 0, 1)} />
      <ambientLight intensity={0.2} />
      <directionalLight position={[-300, -500, 600]} intensity={1.35} color="#fff3e6" />
      <directionalLight position={[500, 600, 160]} intensity={1.0} color="#7cc4ff" />
      <directionalLight position={[101, 900, 420]} intensity={0.6} color="#ffb070" />
      <primitive object={root} />
      <Pool />
      <Post strength={0.35} radius={0.45} threshold={1.7} dof={{ focus: cam.pos.distanceTo(cam.target), range: 150, blur: 4 }} />
    </>
  );
};

const Plate3D: React.FC<{ cbuf: ArrayBuffer; pbuf: ArrayBuffer; cam: Cam3 }> = (p) => (
  <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0 }}>
    <PlateScene {...p} />
  </ThreeCanvas>
);

/* ---------------------------------------------------------------- small pieces */

/** The dark intel board, locked off with the measured push-in, re-angled on every cut. */
const Shot: React.FC<{ f: number; t: number; len: number; dir: number; children: React.ReactNode }> = ({ f, t, len, dir, children }) => (
  <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (t / 60)})`, transformOrigin: "50% 48%" }}>
    <Board f={f} t={clamp(t / len)} dir={dir}>{children}</Board>
  </AbsoluteFill>
);

/** The section tag, top left, flickering on with each cut. */
const Tag: React.FC<{ t: number; text: string; col?: string }> = ({ t, text, col = MW.orange }) => (
  <Mono s={16} c={col} w={700} ls="0.4em" style={{ position: "absolute", left: 90, top: BAR + 28, opacity: t > 3 && !(t > 5 && t < 8) ? 1 : 0 }}>{text}</Mono>
);

/** A line that types on, left to right. */
const Wipe: React.FC<{ t: number; at: number; dur?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ t, at, dur = 12, children, style }) => (
  <div style={{ clipPath: `inset(0 ${100 - 100 * prog(t, at, at + dur)}% 0 0)`, ...style }}>{children}</div>
);

const Badge: React.FC<{ t: number; text: string; col: string; s?: number }> = ({ t, text, col, s = 15 }) => (
  <div style={{ display: "inline-flex", gap: 10, alignItems: "center", padding: "4px 12px 5px", border: `2px solid ${col}`, background: `${col}1f` }}>
    <div style={{ width: 10, height: 10, background: col, opacity: col === MW.amber ? blink(t) : 1 }} />
    <Mono s={s} c={col} w={700} ls="0.16em">{text}</Mono>
  </div>
);

/* ---------------------------------------------------------------- 01 the record */

const ATTRS: [string, string, string, string?][] = [
  ["kind", "str('run')", ""],
  ["game", `str('${R.game}')`, R.title],
  ["rules", `u64(${R.rules})`, "THE GAME'S RULES VERSION"],
  ["frames", `u64(${R.time_frames})`, fmt(R.time_frames)],
  ["log_h", `bytes32(${HASH})`, "SHA-256 OF HER LOG"],
  ["$creator", "THE CHECKER'S WALLET", "SET BY ARKIV", MW.amber],
  ["$expiresAt", "SEASON END + 30 DAYS", "IN ~2 S BLOCKS", MW.amber],
  ["flags", "READ-ONLY, ANYONE CAN EXTEND", "FIXED AT CREATION", MW.amber],
  ["payload", "THE LOG ITSELF", `${R.log_bytes.toLocaleString("en-US")} BYTES`],
];

const Record1: React.FC<{ t: number }> = ({ t }) => {
  const X = 130, Y = BAR + 70, CW = 1130, RH = 50;
  return (
    <>
      <Card f={t} at={8} x={X} y={Y} w={CW} h={612} head="ARKIV ENTITY // ONE VERIFIED RUN" accent={MW.blue} headCol={MW.blue}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 34, color: MW.text, lineHeight: 1 }}>RIA // MARINE DRIVE GP // {fmt(R.time_frames)}</div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 58 }}>
          {ATTRS.map(([k, v, note, col], i) => {
            const at = 24 + i * 8;
            return (
              <div key={k} style={{ position: "absolute", left: 0, right: 0, top: i * RH, height: RH - 6, opacity: t >= at ? 1 : 0,
                borderBottom: `1px solid rgba(143,145,143,0.18)`, display: "flex", alignItems: "center" }}>
                <Mono s={20} c={MW.blue} w={700} style={{ width: 190 }}>{k}</Mono>
                <Wipe t={t} at={at} dur={10} style={{ flex: 1 }}><Mono s={21} c={col ?? MW.text} w={700}>{v}</Mono></Wipe>
                <Mono s={16} c={MW.dim} ls="0.12em" style={{ textAlign: "right" }}>{note}</Mono>
              </div>
            );
          })}
        </div>
      </Card>
      <Card f={t} at={20} x={1300} y={Y} w={550} h={290} head="WHERE IT LIVES" accent={MW.orange}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 44, color: MW.text, lineHeight: 1.02 }}>PUBLIC DATA</div>
        <Mono s={19} c={MW.text} style={{ marginTop: 18, lineHeight: 1.4 }}>{"ON ARKIV, NOT IN OUR DATABASE.\nANYONE CAN READ THE ROW."}</Mono>
      </Card>
      <Card f={t} at={34} x={1300} y={Y + 318} w={550} h={294} head="ON SCREEN" accent={MW.green} headCol={MW.green}>
        <Row k="VALUES" v="REAL: RIA'S LOG" c={MW.green} s={18} />
        <Row k="REPLAYED" v={R.replay_hash} c={MW.green} s={18} />
        <Row k="ENTITY KEY" v="NONE YET" c={MW.amber} s={18} />
        <div style={{ marginTop: 14 }}><Badge t={t} text={DONE ? "WRITE: BUILT" : "WRITE: AT THE EVENT"} col={callCol} /></div>
      </Card>
    </>
  );
};

const RECORD: [string, string, string][] = [
  ["GAME", R.title, `str('${R.game}')`],
  ["TIME", `${fmt(R.time_frames)}  //  ${R.time_frames} FRAMES`, "u64"],
  ["LOG HASH", HASH.slice(2).toUpperCase(), "SHA-256"],
  ["CHECKED BY", "THE CHECKER'S WALLET", "$creator"],
];
const Record2: React.FC<{ t: number }> = ({ t }) => (
  <Card f={t} at={6} x={170} y={BAR + 78} w={1580} h={612} head="THE RECORD // ITS ATTRIBUTES" accent={MW.blue} headCol={MW.blue}>
    {RECORD.map(([k, v, ty], i) => {
      const at = 22 + i * 34;
      const last = i === RECORD.length - 1;
      return (
        <div key={k} style={{ position: "absolute", left: 0, right: 0, top: 12 + i * 132, opacity: t >= at ? 1 : 0 }}>
          <Mono s={17} c={MW.dim} w={700} ls="0.32em">{k}</Mono>
          <Wipe t={t} at={at + 2} dur={14}>
            <div style={{ fontFamily: "Archivo Black", fontSize: 58, lineHeight: 1.12, color: last ? MW.amber : MW.text, letterSpacing: "0.02em" }}>{v}</div>
          </Wipe>
          <Mono s={17} c={MW.blue} w={700} ls="0.12em" style={{ position: "absolute", right: 0, top: 4 }}>{ty}</Mono>
        </div>
      );
    })}
    {t >= 150 ? (
      <Mono s={16} c={MW.amber} w={700} ls="0.16em" style={{ position: "absolute", right: 0, top: 12 + 3 * 132 + 82, opacity: blink(t) }}>
        ADDRESS: PUBLISHED IN THE README AT THE EVENT
      </Mono>
    ) : null}
  </Card>
);

/* ---------------------------------------------------------------- 02 the board reads */

/** The console's screen, drawn by the real launcher (public/handler/board, MOCK pill on): cropped to the board, which
    also leaves out the status bar's World pill (World was dropped). */
const BoardScreen: React.FC<{ t: number; x: number; y: number; crop: { x: number; y: number; w: number; h: number }; s: number }> = ({ t, x, y, crop, s }) => {
  const img = clamp(Math.floor(t / SCREENS.every), 0, SCREENS.images.board - 1);
  const on = prog(t, 0, 10);
  const w = crop.w * s, h = crop.h * s;
  return (
    <>
      <div style={{ position: "absolute", left: x - 12, top: y - 12, width: w + 24, height: h + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: x, top: y, width: w, height: h, overflow: "hidden", background: "#000", transform: `scaleY(${lerp(0.02, 1, easeInOut(on))})` }}>
        <Img src={staticFile(`handler/board/${String(img).padStart(2, "0")}.jpg`)}
          style={{ position: "absolute", left: -crop.x * s, top: -crop.y * s, width: 800 * s, height: 480 * s }} />
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: clamp(1 - t / 4) * 0.35 }} />
      </div>
    </>
  );
};

const Board1: React.FC<{ t: number; tin: number }> = ({ t, tin }) => {
  if (tin >= 0) {                                            // the cut-in: closer on the rows
    return (
      <>
        <BoardScreen t={t} x={(W - 614 * 1.95) / 2} y={BAR + 70} crop={{ x: 186, y: 0, w: 614, h: 302 }} s={1.95} />
        <Mono s={15} c={MW.text} w={700} ls="0.24em" style={{ position: "absolute", right: (W - 614 * 1.95) / 2, top: BAR + 30, opacity: prog(tin, 4, 8) }}>
          {"\"VERIFIED RUNS, ARKIV\" // THE LAUNCHER'S OWN BOARD"}
        </Mono>
      </>
    );
  }
  const X = 90, Y = BAR + 112, S = 1.85, CX = X + Math.round(614 * S) + 50;
  return (
    <>
      <BoardScreen t={t} x={X} y={Y} crop={{ x: 186, y: 0, w: 614, h: 302 }} s={S} />
      <Mono s={15} c={MW.text} w={700} ls="0.24em" style={{ position: "absolute", left: X, top: Y - 44, opacity: prog(t, 6, 12) }}>
        {"THE CONSOLE'S SCREEN // DRAWN BY THE LAUNCHER // MOCK SPONSORS"}
      </Mono>
      <Card f={t} at={16} x={CX} y={Y - 12} w={W - CX - 70} h={584} head="THE CONSOLE // READS" accent={MW.blue} headCol={MW.blue}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 32, color: MW.text, lineHeight: 1.05, whiteSpace: "pre" }}>{"THE BOARD\nIS A QUERY"}</div>
        <Mono s={17} c={MW.text} style={{ marginTop: 18, lineHeight: 1.45 }}>{"ITS ROWS: RUNS OUR\nCHECKER WROTE"}</Mono>
        <div style={{ marginTop: 20, borderTop: `1px solid ${MW.faint}`, paddingTop: 14 }}>
          <Row k="RIA" v={fmt(R.time_frames)} c={MW.orange} s={19} />
          <Mono s={13} c={MW.dim} ls="0.12em" style={{ marginTop: -2, marginBottom: 12 }}>SHIPPED TEST LOG</Mono>
          <Row k="YOU" v={fmt(YOU.time_frames)} c={MW.blue} s={19} />
          <Mono s={13} c={MW.dim} ls="0.12em" style={{ marginTop: -2, marginBottom: 12 }}>A REAL SECOND RUN</Mono>
          <Mono s={13} c={MW.dim} ls="0.12em">OTHER NAMES: MOCK</Mono>
        </div>
        <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", flexDirection: "column", gap: 10 }}>
          <Badge t={t} text="UI: BUILT" col={MW.green} />
          <Badge t={t} text={DONE ? "READ: BUILT" : "READ: AT THE EVENT"} col={callCol} />
        </div>
      </Card>
    </>
  );
};

const Q: { k: string; v: string; hole?: string; tail?: string; note: string }[] = [
  { k: "", v: "kind = str('run')", note: "" },
  { k: "AND ", v: `game = str('${R.game}')`, note: R.title },
  { k: "AND ", v: `frames < u64(${YOU.time_frames})`, note: `YOUR BEST, ${fmt(YOU.time_frames)}` },
  { k: "AND ", v: "$creator = addr(", hole: "CHECKER", tail: ")", note: "OUR CHECKER ONLY" },
];
const Board2: React.FC<{ t: number }> = ({ t }) => {
  const Y = BAR + 76;
  const res = 22 + Q.length * 26 + 18;
  return (
    <>
      <Card f={t} at={6} x={110} y={Y} w={1100} h={430} head="THE BOARD'S QUERY // AS THE ARKIV SDK WRITES IT" accent={MW.blue} headCol={MW.blue}>
        {Q.map((q, i) => {
          const at = 22 + i * 26;
          return (
            <div key={i} style={{ position: "absolute", left: 0, right: 0, top: 14 + i * 74, opacity: t >= at ? 1 : 0 }}>
              <Wipe t={t} at={at} dur={16}>
                <Mono s={30} c={MW.text} w={700}>
                  <span style={{ color: MW.dim }}>{q.k}</span>{q.v}{q.hole ? <span style={{ color: MW.amber }}>{`<${q.hole}>`}</span> : null}{q.tail ?? ""}
                </Mono>
              </Wipe>
              {q.note ? <Mono s={14} c={MW.dim} ls="0.18em" style={{ position: "absolute", right: 0, top: 10, opacity: prog(t, at + 14, at + 20) }}>{q.note}</Mono> : null}
            </div>
          );
        })}
        <Mono s={14} c={MW.amber} w={700} ls="0.16em" style={{ position: "absolute", left: 0, bottom: 2, opacity: prog(t, 140, 146) }}>
          {"<CHECKER>: ITS ADDRESS GOES IN THE README AT THE EVENT"}
        </Mono>
      </Card>
      <Card f={t} at={res} x={1250} y={Y} w={600} h={430} head="RESULT // SORTED ON THE CONSOLE" accent={MW.orange}>
        <Mono s={15} c={MW.dim} ls="0.14em">THE CLOSEST ROW ABOVE YOU</Mono>
        <div style={{ marginTop: 16, padding: "14px 18px", border: `2px solid ${MW.orange}`, background: "rgba(240,138,36,0.10)", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 40, color: MW.orange, lineHeight: 1 }}>RIA</div>
          <Mono s={30} c={MW.text} w={700}>{fmt(R.time_frames)}</Mono>
        </div>
        <div style={{ marginTop: 18 }}>
          <Row k="FRAMES" v={`${R.time_frames}`} s={19} />
          <Row k="AHEAD OF YOU" v={`${YOU.time_frames - R.time_frames} FRAMES, ${((YOU.time_frames - R.time_frames) / 60).toFixed(2)} S`} c={MW.orange} s={19} />
        </div>
        <Mono s={13} c={MW.dim} ls="0.12em" style={{ position: "absolute", left: 0, bottom: 2, lineHeight: 1.4 }}>{"ARKIV HAS NO ORDER BY:\nONE PAGE, SORTED BY THE CONSOLE"}</Mono>
      </Card>
      <Mono s={16} c={MW.text} w={700} ls="0.3em" style={{ position: "absolute", left: 110, top: Y + 470, opacity: prog(t, res + 30, res + 36) }}>
        {"THE GHOST JUST AHEAD: ONE CALL, NO SERVER OF OURS IN THE PATH"}
      </Mono>
      <div style={{ position: "absolute", left: 110, top: Y + 510 }}><Badge t={t} text={DONE ? "READ: BUILT" : "READ: AT THE EVENT"} col={callCol} /></div>
    </>
  );
};

const READERS: { k: string; t: string; s: string; st: [string, string][] }[] = [
  { k: "01 // THE CONSOLE", t: "THE BOARD AND\nTHE GHOST AHEAD", s: "THE LAUNCHER'S OWN BOARD", st: [["UI: BUILT", MW.green], [CALL, callCol]] },
  { k: "02 // A WEB PAGE", t: "THE SAME BOARD\nON ANY PHONE", s: "ONE STATIC PAGE, NO BACKEND", st: [[CALL, callCol]] },
  { k: "03 // ANYONE", t: "RAW JSON-RPC,\nBY HAND", s: "ARKIV'S PUBLIC RPC: NO KEY", st: [[DONE ? "README QUERY: BUILT" : "README QUERY: AT THE EVENT", callCol]] },
];
const Board3: React.FC<{ t: number }> = ({ t }) => {
  const NW = 500, GAP = 40, X0 = (W - (3 * NW + 2 * GAP)) / 2, Y = BAR + 330, NH = 340, chipY = BAR + 96;
  return (
    <>
      <div style={{ position: "absolute", left: W / 2 - 560, top: chipY, width: 1120, opacity: prog(t, 4, 8) }}>
        <Mono s={16} c={MW.orange} w={700} ls="0.4em" style={{ textAlign: "center" }}>ONE QUERY, ANY READER</Mono>
        <div style={{ marginTop: 16, padding: "16px 22px", background: "rgba(5,5,5,0.84)", borderLeft: `3px solid ${MW.blue}`, textAlign: "center" }}>
          <Wipe t={t} at={10} dur={22}>
            <Mono s={21} c={MW.text} w={700}>
              {`kind = str('run') AND game = str('${R.game}') AND $creator = addr(`}<span style={{ color: MW.amber }}>{"<CHECKER>"}</span>{")"}
            </Mono>
          </Wipe>
        </div>
      </div>
      <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={10} height={10}>
        {READERS.map((_, i) => {
          const x = X0 + i * (NW + GAP) + NW / 2, y0 = chipY + 108, y1 = Y - 6;
          const d = prog(t, 30 + i * 8, 46 + i * 8);
          return <line key={i} x1={W / 2} y1={y0} x2={lerp(W / 2, x, d)} y2={lerp(y0, y1, d)} stroke={MW.blue} strokeWidth={2} strokeOpacity={0.7} />;
        })}
      </svg>
      {READERS.map((r, i) => (
        <Card key={r.k} f={t} at={44 + i * 12} x={X0 + i * (NW + GAP)} y={Y} w={NW} h={NH} head={r.k} accent={MW.blue} headCol={MW.blue}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 34, color: MW.text, lineHeight: 1.08, whiteSpace: "pre" }}>{r.t}</div>
          <Mono s={16} c={MW.dim} ls="0.1em" style={{ marginTop: 18 }}>{r.s}</Mono>
          <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", flexDirection: "column", gap: 8 }}>
            {r.st.map(([s, c]) => <Badge key={s} t={t} text={s} col={c} s={14} />)}
          </div>
        </Card>
      ))}
    </>
  );
};

/* ---------------------------------------------------------------- 02b the ghost just ahead: what the query is for */

/** Real ghost races (prep/sponsors/arkiv_ghosts.py): the shipped ROM played headless with RIA's shipped log's ghost in
    its cartridge, the way the launcher's bridge races one; the game draws the ghost. The player is the real slower run
    (the recorded route with a scripted pause), its log saved by the game and replayed by the PC tool: those replays
    give every time and gap on the cards. Fetching the ghost from Arkiv is the event's call. */
type GD = { title: string; ria_frames: number; you_frames: number; gap_frames: number; hold: { at: number; frames: number };
  window: { first: number; count: number; every: number }; images: number };
const GHOSTS = GH as unknown as Record<string, GD>;
const GHOST_SHOTS: Record<string, { gid: string; look: string; last: number }> = {
  ghost1: { gid: "MDGP", look: "THE TRANSLUCENT KART AHEAD", last: 125 },   // stops before the finish gantry's sponsor art
  ghost2: { gid: "RUSH", look: "THE SEE-THROUGH RUNNER", last: 149 },
};
const SUBCUT: Record<string, string> = { plate: "plateIn", ghost1: "ghost1In", ghost2: "ghost2In" };

const GameScreen: React.FC<{ gid: string; img: number; x: number; y: number; s: number; rows: number; t: number }> = ({ gid, img, x, y, s, rows, t }) => {
  const w = 240 * s, h = rows * s;
  return (
    <>
      <div style={{ position: "absolute", left: x - 14, top: y - 14, width: w + 28, height: h + 28, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: x, top: y, width: w, height: h, overflow: "hidden", background: "#000",
        transform: `scaleY(${lerp(0.02, 1, easeInOut(prog(t, 0, 8)))})` }}>
        <Img src={staticFile(`sponsors/arkiv/ghost/${gid}/${String(img).padStart(4, "0")}.png`)}
          style={{ position: "absolute", left: 0, top: 0, width: w, height: 160 * s, imageRendering: "pixelated" }} />
        <div style={{ position: "absolute", inset: 0, opacity: 0.5,
          backgroundImage: `repeating-linear-gradient(0deg, rgba(0,0,0,0.22) 0px, rgba(0,0,0,0.22) 1px, rgba(0,0,0,0) 1px, rgba(0,0,0,0) ${s}px)` }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.35) 100%)" }} />
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: clamp(1 - t / 4) * 0.3 }} />
      </div>
    </>
  );
};

const Ghost: React.FC<{ t: number; tt: number; shot: string; cutIn: boolean }> = ({ t, tt, shot, cutIn }) => {
  const g = GHOST_SHOTS[shot], d = GHOSTS[g.gid];
  const img = clamp(Math.floor(tt / d.window.every), 0, Math.min(g.last, d.images - 1));
  const gap = `${d.gap_frames} FRAMES, ${(d.gap_frames / 60).toFixed(2)} S`;
  const fetch = DONE ? "FROM ARKIV: BUILT" : "FROM ARKIV: AT THE EVENT";
  if (cutIn) {
    const X = 130, Y = BAR + 62, S = 4.5, CX = X + 240 * S + 50;
    return (
      <>
        <GameScreen gid={g.gid} img={img} x={X} y={Y} s={S} rows={140} t={t} />
        <Card f={t} at={10} x={CX} y={Y - 14} w={W - CX - 70} h={420} head="THE GAP AT THE LINE" accent={MW.orange}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 64, color: MW.orange, lineHeight: 1 }}>{`${d.gap_frames} FRAMES`}</div>
          <Mono s={22} c={MW.text} w={700} style={{ marginTop: 12 }}>{`${(d.gap_frames / 60).toFixed(2)} SECONDS`}</Mono>
          <div style={{ marginTop: 26, borderTop: `1px solid ${MW.faint}`, paddingTop: 16 }}>
            <Row k="RIA" v={fmt(d.ria_frames)} c={MW.orange} s={20} />
            <Row k="YOU" v={fmt(d.you_frames)} c={MW.blue} s={20} />
          </div>
          <Mono s={13} c={MW.dim} ls="0.12em" style={{ position: "absolute", left: 0, bottom: 2, lineHeight: 1.4 }}>{"BOTH TIMES: THE TWO LOGS,\nREPLAYED BY THE PC TOOL"}</Mono>
        </Card>
        <div style={{ position: "absolute", left: CX, top: Y + 430, display: "flex", flexDirection: "column", gap: 10 }}>
          <Badge t={t} text="GHOST: DRAWN BY THE GAME" col={MW.green} s={14} />
          <Badge t={t} text={fetch} col={callCol} s={14} />
        </div>
      </>
    );
  }
  const X = 90, Y = BAR + 70, S = 4, CX = X + 240 * S + 60;
  return (
    <>
      <GameScreen gid={g.gid} img={img} x={X} y={Y} s={S} rows={150} t={t} />
      <Card f={t} at={14} x={CX} y={Y - 14} w={W - CX - 70} h={628} head={`GHOST RACE // ${d.title}`} accent={MW.orange}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 50, lineHeight: 1 }}>
          <span style={{ color: MW.blue }}>YOU</span><span style={{ color: MW.dim, fontSize: 32 }}>{"  vs  "}</span><span style={{ color: MW.orange }}>RIA</span>
        </div>
        <Mono s={15} c={MW.dim} ls="0.12em" style={{ marginTop: 14 }}>{`HER GHOST: ${g.look}`}</Mono>
        <div style={{ marginTop: 22, borderTop: `1px solid ${MW.faint}`, paddingTop: 16 }}>
          <Row k="YOU" v={`${fmt(d.you_frames)}  //  ${d.you_frames}`} c={MW.blue} s={20} />
          <Row k="RIA'S GHOST" v={`${fmt(d.ria_frames)}  //  ${d.ria_frames}`} c={MW.orange} s={20} />
          <Row k="GAP AT THE LINE" v={gap} c={MW.text} s={20} />
        </div>
        <Mono s={13} c={MW.dim} ls="0.1em" style={{ marginTop: 12, lineHeight: 1.45 }}>
          {`THE SHIPPED ROM, PLAYED HEADLESS. RIA = ITS SHIPPED LOG.\nYOU = THE RECORDED ROUTE WITH A SCRIPTED ${d.hold.frames}-FRAME PAUSE.`}
        </Mono>
        <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", flexDirection: "column", gap: 10 }}>
          <Badge t={t} text="GHOST: REAL, THE GAME REPLAYS HER LOG" col={MW.green} s={14} />
          <Badge t={t} text={fetch} col={callCol} s={14} />
        </div>
      </Card>
    </>
  );
};

/* ---------------------------------------------------------------- 03 nobody can fake a row */

type RowD = { who: string; fr: number; by: string; fake?: boolean };
const ROWS: RowD[] = [
  { who: "FORGED", fr: FAKE.time_frames, by: "A STRANGER'S WALLET", fake: true },
  { who: "RIA", fr: R.time_frames, by: "THE CHECKER" },
  { who: "YOU", fr: YOU.time_frames, by: "THE CHECKER" },
];
const FAKE_AT = 96;                                          // the forged row lands, in fake1
const STAMP_AT = 84;                                         // IGNORED lands on it, in fake2
/** The rows a query returns: first without the creator pin (the forged row lands on top), then with it (ignored). */
const Rows: React.FC<{ t: number; pinned: boolean }> = ({ t, pinned }) => {
  const X = 230, Y = BAR + 84, CW = 1460, RH = 96;
  const fakeIn = pinned ? 1 : prog(t, FAKE_AT, FAKE_AT + 8);
  const strike = pinned ? prog(t, 46, 58) : 0;
  const drop = pinned ? easeInOut(prog(t, 58, 78)) : 0;
  const cols = [{ k: "RUNNER", x: 0 }, { k: "TIME", x: 300 }, { k: "FRAMES", x: 560 }, { k: "$creator", x: 820 }];
  const gl = !pinned && t >= FAKE_AT && t < FAKE_AT + 10;
  return (
    <>
      <Card f={t} at={pinned ? 2 : 8} x={X} y={Y} w={CW} h={560} head={pinned ? "THE BOARD'S QUERY // PINNED TO THE CHECKER" : "ANY QUERY // NO CREATOR PIN"}
        accent={pinned ? MW.green : MW.blue} headCol={pinned ? MW.green : MW.blue}>
        <Mono s={22} c={MW.text} w={700}>
          {`kind = str('run') AND game = str('${R.game}')`}
          {pinned ? <span style={{ color: MW.green, clipPath: `inset(0 ${100 - 100 * prog(t, 14, 34)}% 0 0)`, display: "inline-block" }}>
            {" AND $creator = addr("}<span style={{ color: MW.amber }}>{"<CHECKER>"}</span>{")"}</span> : null}
        </Mono>
        <div style={{ position: "absolute", left: 0, right: 0, top: 58, height: 30, borderBottom: `1px solid ${MW.faint}` }}>
          {cols.map((c) => <Mono key={c.k} s={14} c={MW.dim} w={700} ls="0.24em" style={{ position: "absolute", left: c.x + 24 }}>{c.k}</Mono>)}
        </div>
        {ROWS.map((r, i) => {
          if (r.fake && fakeIn <= 0) return null;
          // the real rows slide down as the forged one lands; once pinned, it is struck and sinks under them
          const slot = r.fake ? 2 * drop : i - 1 + fakeIn - drop;
          const y = 100 + slot * RH + (r.fake && !pinned ? (1 - easeOutExpo(fakeIn)) * -30 : 0);
          const op = r.fake ? (pinned ? lerp(1, 0.4, strike) : fakeIn) : 1;
          const jx = r.fake && gl ? (((t * 7) % 5) - 2) * 6 : 0;
          return (
            <div key={r.who} style={{ position: "absolute", left: 0, right: 0, top: y, height: RH - 12, opacity: op, transform: `translateX(${jx}px)`,
              background: r.fake ? "rgba(212,58,43,0.10)" : "rgba(124,196,255,0.05)", border: `1px solid ${r.fake ? "rgba(212,58,43,0.55)" : "rgba(124,196,255,0.18)"}` }}>
              <div style={{ position: "absolute", left: 24, top: 22, fontFamily: "Archivo Black", fontSize: 34, lineHeight: 1, color: r.fake ? MW.red : r.who === "RIA" ? MW.orange : MW.blue }}>{r.who}</div>
              <Mono s={30} c={MW.text} w={700} style={{ position: "absolute", left: 324, top: 22 }}>{fmt(r.fr)}</Mono>
              <Mono s={24} c={MW.dim} w={700} style={{ position: "absolute", left: 584, top: 26 }}>{`${r.fr}`}</Mono>
              <Mono s={22} c={r.fake ? MW.red : MW.green} w={700} ls="0.08em" style={{ position: "absolute", left: 844, top: 28 }}>{r.by}</Mono>
              {r.fake && strike > 0 ? <div style={{ position: "absolute", left: 14, top: (RH - 12) / 2 - 1, height: 3, width: (CW - 72) * strike, background: MW.red }} /> : null}
            </div>
          );
        })}
        {!pinned && t >= FAKE_AT + 14 ? (
          <Mono s={15} c={MW.red} w={700} ls="0.18em" style={{ position: "absolute", left: 0, bottom: 4, opacity: prog(t, FAKE_AT + 14, FAKE_AT + 18) }}>
            {"FORGED: SAME ATTRIBUTES, A BETTER TIME, FROM ANY WALLET. STAGED LIVE AT THE EVENT."}
          </Mono>
        ) : null}
        {pinned && t >= 140 ? (
          <Mono s={15} c={MW.green} w={700} ls="0.18em" style={{ position: "absolute", left: 0, bottom: 4, opacity: prog(t, 140, 146) }}>
            {`THE BOARD: RIA ${fmt(R.time_frames)}, YOU ${fmt(YOU.time_frames)}. THE FORGED ROW NEVER COUNTS.`}
          </Mono>
        ) : null}
      </Card>
      {pinned ? <Stamp f={t} at={STAMP_AT} text="IGNORED" col={MW.red} x={X + 760} y={Y + 48 + 100 + 2 * RH + (RH - 12) / 2 + 30} s={58} sub="NOT THE CHECKER" /> : null}
    </>
  );
};

const LANES = [
  { src: "OUR CHECKER", srcS: "ITS KEY ON OUR BACKEND", row: `RIA  ${fmt(R.time_frames)}`, by: "$creator = THE CHECKER", v: "COUNTED", col: MW.green },
  { src: "A STRANGER", srcS: "ANY WALLET, ANY ROW", row: `FORGED  ${fmt(FAKE.time_frames)}`, by: "$creator = THE STRANGER", v: "IGNORED", col: MW.red },
];
const Fake3: React.FC<{ t: number }> = ({ t }) => {
  const Y0 = BAR + 84, LH = 176, SX = 120, SW = 400, RX = 640, RW = 640, VX = 1400, VW = 400;
  return (
    <>
      {LANES.map((l, i) => {
        const y = Y0 + i * (LH + 18), at = 8 + i * 40;
        const a1 = prog(t, at + 16, at + 30), a2 = prog(t, at + 30, at + 44);
        return (
          <React.Fragment key={l.src}>
            <Card f={t} at={at} x={SX} y={y} w={SW} h={LH} head="WRITER" accent={l.col} headCol={l.col}>
              <div style={{ fontFamily: "Archivo Black", fontSize: 34, color: MW.text, lineHeight: 1 }}>{l.src}</div>
              <Mono s={15} c={MW.dim} ls="0.12em" style={{ marginTop: 14 }}>{l.srcS}</Mono>
            </Card>
            <div style={{ position: "absolute", left: SX + SW + 14, top: y + LH / 2, width: (RX - SX - SW - 28) * a1, height: 2, background: MW.text, opacity: 0.8 }} />
            <Card f={t} at={at + 22} x={RX} y={y} w={RW} h={LH} head="ROW ON ARKIV" accent={MW.blue} headCol={MW.blue}>
              <Mono s={30} c={MW.text} w={700}>{l.row}</Mono>
              <Mono s={20} c={l.col} w={700} style={{ marginTop: 16 }}>{l.by}</Mono>
            </Card>
            <div style={{ position: "absolute", left: RX + RW + 14, top: y + LH / 2, width: (VX - RX - RW - 28) * a2, height: 2, background: MW.text, opacity: 0.8 }} />
            {t >= at + 44 ? (
              <div style={{ position: "absolute", left: VX, top: y + LH / 2 - 44, width: VW, height: 88, border: `4px solid ${l.col}`, background: `${l.col}22`,
                display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${lerp(1.4, 1, easeOutExpo(prog(t, at + 44, at + 52)))})` }}>
                <div style={{ fontFamily: "Archivo Black", fontSize: 44, color: l.col, letterSpacing: "0.06em" }}>{l.v}</div>
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
      <Card f={t} at={120} x={SX} y={Y0 + 2 * (LH + 18) + 4} w={VX + VW - SX} h={130} head="$creator" accent={MW.amber} headCol={MW.amber}>
        <Mono s={20} c={MW.text} w={700}>{"ARKIV SETS IT TO THE WALLET THAT SIGNED THE WRITE. NO WRITER CAN CHOOSE IT."}</Mono>
        <div style={{ position: "absolute", right: 0, bottom: 0 }}><Badge t={t} text={DONE ? "LOOK-ALIKE ROW: BUILT" : "LOOK-ALIKE ROW: AT THE EVENT"} col={callCol} s={14} /></div>
      </Card>
    </>
  );
};

/* ---------------------------------------------------------------- 04 the clock */

const Exp1: React.FC<{ t: number }> = ({ t }) => {
  const X0 = 200, X1 = 1720, Y = BAR + 420, xs = 1060, xe = 1500;
  const draw = prog(t, 10, 60);
  const nodes = [
    { x: X0, k: "WRITTEN", s: "THE CHECKER\nWRITES THE ROW", at: 14, col: MW.blue },
    { x: xs, k: "SEASON END", s: "", at: 34, col: MW.text },
    { x: xe, k: "+ 30 DAYS", s: "$expiresAt", at: 50, col: MW.amber },
  ];
  const ext = prog(t, 120, 160);
  return (
    <>
      <Card f={t} at={6} x={X0} y={BAR + 70} w={760} h={176} head="EXPIRY // THE BOARD'S CLOCK" accent={MW.amber} headCol={MW.amber}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 32, color: MW.text, lineHeight: 1.1 }}>{"SEASON END + 30 DAYS"}</div>
        <Mono s={17} c={MW.dim} ls="0.1em" style={{ marginTop: 14 }}>NOTHING DROPS OFF THE BOARD EARLY</Mono>
      </Card>
      <div style={{ position: "absolute", left: X0 + 860, top: BAR + 92, opacity: prog(t, 70, 78), padding: "12px 18px", background: "rgba(5,5,5,0.84)", borderLeft: `3px solid ${MW.orange}` }}>
        <Mono s={14} c={MW.dim} ls="0.24em">THE BOARD SHOWS IT ON EVERY ROW</Mono>
        <Mono s={24} c={MW.text} w={700} style={{ marginTop: 8 }}>
          <span style={{ color: MW.orange }}>RIA</span>{`  ${fmt(R.time_frames)}   ON BOARD UNTIL `}<span style={{ color: MW.amber }}>$expiresAt</span>
        </Mono>
      </div>
      <div style={{ position: "absolute", left: X0, top: Y - 74, width: (xe - X0) * prog(t, 40, 70), height: 30, borderTop: `2px solid ${MW.green}`, borderLeft: `2px solid ${MW.green}`,
        borderRight: t > 70 ? `2px solid ${MW.green}` : "none", opacity: 0.9 }} />
      <Mono s={15} c={MW.green} w={700} ls="0.3em" style={{ position: "absolute", left: X0 + 16, top: Y - 104, opacity: prog(t, 62, 70) }}>ON THE BOARD</Mono>
      <div style={{ position: "absolute", left: X0, top: Y, width: (xe - X0) * draw, height: 3, background: MW.text }} />
      <div style={{ position: "absolute", left: xe, top: Y, width: (X1 - xe) * ext, height: 0, borderTop: `3px dashed ${MW.amber}` }} />
      {ext > 0 ? (
        <Mono s={15} c={MW.amber} w={700} ls="0.22em" style={{ position: "absolute", left: xe + 40, top: Y - 66, opacity: prog(t, 150, 158), lineHeight: 1.4 }}>{"ANYONE CAN\nEXTEND IT"}</Mono>
      ) : null}
      {nodes.map((n) => (
        <React.Fragment key={n.k}>
          <div style={{ position: "absolute", left: n.x - 9, top: Y - 8, width: 18, height: 18, background: n.col, transform: `rotate(45deg) scale(${easeOutExpo(prog(t, n.at, n.at + 8))})` }} />
          <Mono s={17} c={n.col} w={700} ls="0.22em" style={{ position: "absolute", left: n.x - 6, top: Y + 28, opacity: prog(t, n.at + 4, n.at + 10) }}>{n.k}</Mono>
          {n.s ? <Mono s={15} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: n.x - 6, top: Y + 56, opacity: prog(t, n.at + 8, n.at + 14), lineHeight: 1.4 }}>{n.s}</Mono> : null}
        </React.Fragment>
      ))}
      <Mono s={15} c={MW.dim} ls="0.16em" style={{ position: "absolute", left: X0, top: Y + 150, opacity: prog(t, 170, 178) }}>
        {"BOARD ROWS END. THE HEDERA RECORD BOOK DOES NOT."}
      </Mono>
    </>
  );
};

const Exp2: React.FC<{ t: number }> = ({ t }) => {
  const Y = BAR + 120, CW = 790, CH = 470, X0 = (W - (2 * CW + 60)) / 2;
  const cards = [
    { at: 8, head: "permissionlessExtension // ON", t: "ANYONE CAN\nEXTEND", s: "A RACER OR A FAN CAN KEEP\nA GHOST ON THE BOARD PAST\nITS SEASON. NO PERMISSION\nFROM US.", col: MW.blue },
    { at: 146, head: "readonly // ON", t: "A RUN ROW CAN'T\nBE EDITED", s: "NOT BY THE RUNNER, NOT BY US.\nOUR CHECKER DELETES ONLY TO\nVOID, AND EVERY VOID LEAVES\nA PUBLIC VOID ROW.", col: MW.green },
  ];
  return (
    <>
      {cards.map((c, i) => (
        <Card key={c.head} f={t} at={c.at} x={X0 + i * (CW + 60)} y={Y} w={CW} h={CH} head={c.head} accent={c.col} headCol={c.col}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 54, color: MW.text, lineHeight: 1.04, whiteSpace: "pre" }}>{c.t}</div>
          <Mono s={20} c={MW.text} style={{ marginTop: 26, lineHeight: 1.45 }}>{c.s}</Mono>
          <Mono s={14} c={MW.dim} w={700} ls="0.22em" style={{ position: "absolute", left: 0, bottom: 4 }}>SET WHEN THE ROW IS WRITTEN, FOR GOOD</Mono>
        </Card>
      ))}
    </>
  );
};

/* ---------------------------------------------------------------- the field report (built.json clips) */

const FieldClip: React.FC<{ t: number; c: Clip }> = ({ t, c }) => {
  const MX = 90, MY = BAR + 74, MW_ = 1136, MH = 639, CX = MX + MW_ + 60;
  const on = prog(t, 0, 8);
  return (
    <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (t / 60)})`, transformOrigin: "50% 48%" }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 40% 45%, #15181b 0%, #0a0c0e 60%, #040506 100%)" }} />
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MW_ + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MW_, height: MH, overflow: "hidden", transform: `scaleY(${lerp(0.02, 1, easeInOut(on))})` }}>
        <OffthreadVideo src={staticFile(`built/${c.file}`)} muted startFrom={Math.round((c.from ?? 0) * 60)} style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }} />
      </div>
      <div style={{ position: "absolute", left: MX, top: MY - 46, display: "flex", alignItems: "center", gap: 12, opacity: prog(t, 6, 12) }}>
        <div style={{ width: 12, height: 12, borderRadius: "50%", background: MW.red, boxShadow: `0 0 10px ${MW.red}`, opacity: Math.floor(t / 30) % 2 === 0 ? 1 : 0.3 }} />
        <Mono s={15} c={MW.text} w={700} ls="0.28em">LIVE CAPTURE // UNEDITED // ETHGLOBAL MUMBAI</Mono>
      </div>
      <div style={{ position: "absolute", left: CX, top: MY - 6, width: W - CX - 70 }}>
        <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: t > 8 ? 1 : 0 }}>FIELD REPORT // ARKIV</Mono>
        <div style={{ fontFamily: "Archivo Black", fontSize: 40, lineHeight: 1.05, color: MW.text, marginTop: 14, whiteSpace: "pre-wrap",
          clipPath: `inset(0 ${100 - 100 * prog(t, 12, 26)}% 0 0)` }}>{c.title}</div>
      </div>
      <Card f={t} at={30} x={CX} y={MY + 230} w={W - CX - 70} h={60 + 34 * c.rows.length} head="ON SCREEN" accent={MW.green} headCol={MW.green}>
        {c.rows.map(([k, v]) => <Row key={k} k={k} v={v} c={MW.green} s={17} />)}
      </Card>
    </AbsoluteFill>
  );
};

/* ---------------------------------------------------------------- status, and the close */

const STEPS = [
  { k: "01 // WRITE", t: "RUN ROWS, FROM OUR CHECKER", ui: false },
  { k: "02 // READ", t: "THE CONSOLE'S BOARD AND THE GHOST AHEAD", ui: true },
  { k: "03 // READ", t: "THE WEB BOARD, THE README QUERY", ui: false },
  { k: "04 // PROOF", t: "THE LOOK-ALIKE ROW, IGNORED", ui: false },
];
const Stat1: React.FC<{ t: number }> = ({ t }) => {
  const X = 230, CW = 1460, CH = 104, G = 14, Y = BAR + 110;
  return (
    <>
      <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ position: "absolute", left: X, top: BAR + 62, opacity: t > 6 ? 1 : 0 }}>ANY% x ARKIV // WHAT IS BUILT</Mono>
      {STEPS.map((s, i) => (
        <Card key={s.k} f={t} at={12 + i * 9} x={X} y={Y + i * (CH + G)} w={CW} h={CH} head={s.k} accent={MW.blue} headCol={MW.blue}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 30, color: MW.text, lineHeight: 1 }}>{s.t}</div>
          <div style={{ position: "absolute", right: 0, top: 0, display: "flex", gap: 12 }}>
            {s.ui ? <Badge t={t} text="UI: BUILT" col={MW.green} s={14} /> : null}
            <Badge t={t} text={CALL} col={callCol} s={14} />
          </div>
        </Card>
      ))}
      <Mono s={15} c={MW.dim} ls="0.14em" style={{ position: "absolute", left: X, top: Y + 4 * (CH + G) + 8, lineHeight: 1.5, opacity: prog(t, 60, 70) }}>
        {"ON SCREEN: RIA'S SHIPPED LOG AND A REAL SECOND RUN. THE OTHER NAMES AND EVERY CALL: MOCK.\nNO ENTITY KEY, TX OR ADDRESS IS SHOWN: NONE EXISTS UNTIL THE EVENT."}
      </Mono>
    </>
  );
};

const Stat2: React.FC<{ t: number }> = ({ t }) => (
  <>
    <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, rgba(3,4,5,0.92) 0%, rgba(3,4,5,0.75) 34%, rgba(3,4,5,0) 58%)" }} />
    <div style={{ position: "absolute", left: 120, top: BAR + 170 }}>
      <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: t > 10 ? 1 : 0 }}>BUILD ON ARKIV // ETHGLOBAL MUMBAI '26</Mono>
      <div style={{ fontFamily: "Archivo Black", fontSize: 120, lineHeight: 1, color: MW.text, marginTop: 18, letterSpacing: "0.02em",
        clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, 14, 30))}% 0 0)` }}>ANY%</div>
      <div style={{ fontFamily: "Archivo Black", fontSize: 120, lineHeight: 1, color: "#ffffff", marginTop: 6, letterSpacing: "0.02em",
        clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, 24, 40))}% 0 0)` }}>
        <span style={{ color: MW.dim, fontSize: 70 }}>x </span>[ ARKIV ]
      </div>
      <div style={{ width: 620 * easeOutExpo(prog(t, 32, 50)), height: 3, background: MW.orange, marginTop: 26 }} />
      <Mono s={20} c={MW.text} w={700} ls="0.2em" style={{ marginTop: 22, opacity: prog(t, 48, 56) }}>THE BOARD IS A PUBLIC QUERY</Mono>
    </div>
  </>
);

/* ---------------------------------------------------------------- the act */

const TAGS: Record<string, string> = {
  plate: "ANY% x ARKIV // THE REAR PLATE",
  rec1: "01 // THE RECORD", rec2: "01 // THE RECORD",
  board1: "02 // THE BOARD READS ARKIV", board2: "02 // THE BOARD READS ARKIV", board3: "02 // THE BOARD READS ARKIV",
  ghost1: "02 // THE GHOST JUST AHEAD", ghost1In: "02 // THE GHOST JUST AHEAD", ghost2: "02 // THE GHOST JUST AHEAD", ghost2In: "02 // THE GHOST JUST AHEAD",
  fake1: "03 // NOBODY CAN FAKE A ROW", fake2: "03 // NOBODY CAN FAKE A ROW", fake3: "03 // NOBODY CAN FAKE A ROW",
  exp1: "04 // THE CLOCK", exp2: "04 // THE CLOCK", stat1: "STATUS",
};
const DIRS: Record<string, number> = { ghost1: -0.7, ghost1In: 0.6, ghost2: 0.8, ghost2In: -0.6, rec1: -0.8, rec2: 0.7, board1: -0.6, board2: 0.8, board3: -0.8, fake1: 0.7, fake2: -0.7, fake3: 0.8, exp1: -0.7, exp2: 0.7, stat1: -0.6 };
const CUTS = [...ORDER.map(([, a]) => a).filter((a) => a > 0), AT.plateIn, AT.board1In, AT.ghost1In, AT.ghost2In].sort((a, b) => a - b);

export const ArkivAct: React.FC = () => {
  const f = useCurrentFrame();
  const cbuf = useBuffer(staticFile("console.bin"));
  const pbuf = useBuffer(staticFile("sponsors/arkiv/panel.bin"));
  const s = shotAt(f);
  const sub = SUBCUT[s.name];                                // a cut-in inside the shot
  const name = sub && f >= AT[sub] ? sub : s.name;
  const t = name !== s.name ? f - AT[name] : s.t;
  const cutAt = CUTS.filter((a) => a <= f).pop() ?? -100;
  const ci = /^clip(\d+)$/.exec(name);
  let body: React.ReactNode = null;
  if (name === "slate") body = <Slate f={f} part="ANY% x ARKIV" title="THE BOARD" num="[ ]" len={50} />;
  else if (name === "plate" || name === "plateIn" || name === "stat2") body = cbuf && pbuf ? <Plate3D cbuf={cbuf} pbuf={pbuf} cam={camFor(name, t)} /> : null;
  else if (ci) body = <FieldClip t={t} c={CLIPS[Number(ci[1])]} />;
  else {
    const inner = name === "rec1" ? <Record1 t={t} /> : name === "rec2" ? <Record2 t={t} /> : name === "board1" ? <Board1 t={t} tin={f - AT.board1In} />
      : name === "board2" ? <Board2 t={t} /> : GHOST_SHOTS[name.replace("In", "")] ? <Ghost t={t} tt={f - AT[name.replace("In", "")]} shot={name.replace("In", "")} cutIn={name.endsWith("In")} />
      : name === "board3" ? <Board3 t={t} /> : name === "fake1" ? <Rows t={t} pinned={false} />
      : name === "fake2" ? <Rows t={t} pinned /> : name === "fake3" ? <Fake3 t={t} /> : name === "exp1" ? <Exp1 t={t} /> : name === "exp2" ? <Exp2 t={t} />
      : name === "stat1" ? <Stat1 t={t} /> : null;
    body = <Shot f={f} t={t} len={s.len} dir={DIRS[name] ?? 0.7}>{inner}</Shot>;
  }
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: kick(f, [AT.fake2 + STAMP_AT, AT.fake1 + FAKE_AT], 7) }}>{body}</AbsoluteFill>
      {name !== "slate" ? <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.7) 100%)" }} /> : null}
      {name === "plate" ? (
        <Card f={t} at={24} x={1330} y={BAR + 96} w={500} h={170} head="SWAP PLATE // REAR" accent={MW.blue} headCol={MW.blue}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 40, color: MW.text, lineHeight: 1 }}>ANY% x ARKIV</div>
          <Mono s={16} c={MW.dim} ls="0.12em" style={{ marginTop: 14 }}>BLUE BODY, WHITE LOGO, ON MAGNETS</Mono>
        </Card>
      ) : null}
      {name === "stat2" ? <Stat2 t={t} /> : null}
      {TAGS[name] ? <Tag t={t} text={TAGS[name]} /> : null}
      {name === "plateIn" ? <Tag t={t} text="THE CONSOLE // ITS CAD" col={MW.blue} /> : null}
      {f - cutAt >= 0 && f - cutAt < 3 ? <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: (0.1 * (3 - (f - cutAt))) / 3 }} /> : null}
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, ARKIV_LEN - 14, ARKIV_LEN)) }} />
    </AbsoluteFill>
  );
};

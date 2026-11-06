import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import * as THREE from "three";
import TL from "../timeline.json";
import { applyPose, asmMatrix, buildParts, clip, FLIP, partPose, section } from "../three/consoleModel";
import { useBuffer } from "../three/useAsset";
import { clamp, easeInOut, lerp, prog, rnd } from "../util";
import BUILT from "./built.json";
import { BAR, Bars, CameraAt, Card, H, Line, Mono, MW, Post, Row, Slate, Subs, W } from "./common";

/* Act V, the Mumbai objectives. Each answers one "NOT YET" from the end of Act IV, in the wording the designs were
   red-teamed to (memory: hedera-live-run-design, world-agent-pass-angles). They are targets for the event, never shown
   as done. World ID never attests who played (an Orb holder can approve a bot's run): it answers for whose record book
   a run goes in, and nothing is published without that person's approval. */

/* FIELD REPORT (src/acts/built.json): what was built at the event. Before it, nothing is flagged and there are no clips,
   so every status reads TO BUILD. At the event, a sponsor is flagged only when it works end to end on camera, and each
   proof is a real screen recording (public/built/) shown between the cards and the loop, with the values on screen
   copied into its evidence card. The act grows by the clips' length; post_film.py, the sound and the VO read it too. */
type Clip = { file: string; sponsor: string; title: string; rows: [string, string][]; line: string; seconds: number; from?: number };
const CLIPS = BUILT.clips as unknown as Clip[];
const DONE = BUILT.built as { world: boolean; hedera: boolean; arkiv: boolean };
const ALL_DONE = DONE.world && DONE.hedera && DONE.arkiv;
const CLIP0 = 856;                                                    // the cards give way here (to the clips, then the loop)
const CLIP_AT = CLIPS.map((_, i) => CLIP0 + CLIPS.slice(0, i).reduce((a, c) => a + Math.round(c.seconds * 60), 0));
const CLIPS_LEN = CLIPS.reduce((a, c) => a + Math.round(c.seconds * 60), 0);
const LOOP = CLIP0 + CLIPS_LEN;                                       // the loop that joins the three networks
const SUM = LOOP + 344;                                               // the one-sentence summary across all three
export const OBJ_LEN = SUM + 310;
const LINES: Line[] = [
  { at: 60, len: 140, who: "Handler", text: ALL_DONE ? "At ETHGlobal Mumbai, we added three networks." : "At ETHGlobal Mumbai, we'll add three networks." },
  { at: 210, len: 195, who: "Handler", text: "World ID: your agent asks, only you approve." },
  { at: 420, len: 205, who: "Handler", text: "Hedera: HCS seeds and checkpoints, and x402 payments." },
  { at: 640, len: 190, who: "Handler", text: "And Arkiv: every log, on a board anyone can query." },
  ...CLIPS.map((c, i) => ({ at: CLIP_AT[i] + 16, len: Math.round(c.seconds * 60) - 28, who: "Handler", text: c.line })),
  { at: LOOP, len: 330, who: "Handler", text: ALL_DONE ? "Your coach agent pays the runner just ahead of you, for their ghost." : "The goal: your coach agent pays the runner just ahead of you, for their ghost." },
  { at: SUM, len: 300, who: "Handler", text: ALL_DONE ? "Checked on the console, published with World ID, listed on Arkiv, paid over Hedera."
    : "The plan: checked on the console, published with World ID, listed on Arkiv, paid over Hedera." },
];
// each card names the sponsor feature it uses (Agent Pass; HCS + x402; Arkiv entities), still marked TO BUILD
const OBJ = [
  { n: "01", who: "WORLD ID", what: "AGENT PASS: YOUR COACH AGENT\nASKS, YOU APPROVE IN WORLD APP,\nTHEN IT GOES IN YOUR RECORD BOOK", answers: "WHO CLAIMS THE RUN", at: 200, done: DONE.world },
  { n: "02", who: "HEDERA", what: "HCS: SEED FROM THE RUNNING HASH\nHCS: A CHECKPOINT EVERY 2 S\nx402: COACH AGENTS PAY RUNNERS", answers: "WHEN, AND AT WHAT PACE", at: 410, done: DONE.hedera },
  { n: "03", who: "ARKIV", what: "EVERY VERIFIED LOG AND GHOST\nSTORED AS AN ENTITY\nTHE BOARD IS A PUBLIC QUERY", answers: "WHERE THE RECORD LIVES", at: 630, done: DONE.arkiv },
];

/** One field-report clip: the real screen recording on a monitor, what it proves, and the values seen on it. */
const FieldClip: React.FC<{ f: number; i: number }> = ({ f, i }) => {
  const c = CLIPS[i], t = f - CLIP_AT[i];
  const MX = 90, MY = BAR + 74, MW_ = 1136, MH = 639, CX = MX + MW_ + 60;          // ends above the subtitle band
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
        <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: t > 8 ? 1 : 0 }}>{`FIELD REPORT // ${c.sponsor}`}</Mono>
        <div style={{ fontFamily: "Archivo Black", fontSize: 40, lineHeight: 1.05, color: MW.text, marginTop: 14, whiteSpace: "pre-wrap",
          clipPath: `inset(0 ${100 - 100 * prog(t, 12, 26)}% 0 0)` }}>{c.title}</div>
      </div>
      <Card f={t} at={30} x={CX} y={MY + 230} w={W - CX - 70} h={60 + 34 * c.rows.length} head="ON SCREEN" accent={MW.green} headCol={MW.green}>
        {c.rows.map(([k, v]) => <Row key={k} k={k} v={v} c={MW.green} s={17} />)}
      </Card>
    </AbsoluteFill>
  );
};

/** THE LOOP: one run through all three networks, each step marked built (now) or to build at the event. */
const NODES = [
  { k: "01 // RUN", t: "YOU PLAY", s: "EVERY INPUT\nLOGGED", built: true },
  { k: "02 // CHECK", t: "VERIFIED", s: "REPLAYED TO\nTHE SAME HASH", built: true },
  { k: "03 // WORLD ID", t: "PUBLISHED", s: "YOUR APPROVAL,\nYOUR RECORD BOOK", built: DONE.world },
  { k: "04 // ARKIV", t: "LISTED", s: "YOUR GHOST,\nON THE BOARD", built: DONE.arkiv },
  { k: "05 // HEDERA x402", t: "PAID", s: "A COACH AGENT PAYS,\nNO HUMAN TAPS", built: DONE.hedera },
];
const Loop: React.FC<{ f: number }> = ({ f }) => {
  if (f < LOOP) return null;
  const t = f - LOOP;
  const NW = 290, NH = 214, GAP = 56, X0 = 330, Y = BAR + 448;
  const xs = NODES.map((_, i) => X0 + i * (NW + GAP));
  const arc = prog(t, 128, 168), cx0 = xs[0] + NW / 2, cx4 = xs[4] + NW / 2, yb = Y + NH + 8, dip = 112;
  const len = 2 * dip + (cx4 - cx0);
  return (
    <>
      <Mono s={16} c={MW.orange} w={700} ls="0.4em" style={{ position: "absolute", left: X0, top: Y - 40, opacity: prog(t, 0, 6) }}>THE LOOP // ONE RUN, THREE NETWORKS</Mono>
      {NODES.map((n, i) => {
        const at = 10 + i * 22, col = n.built ? MW.green : MW.amber;
        const draw = prog(t, at + 12, at + 24);
        return (
          <React.Fragment key={n.k}>
            <Card f={t} at={at} x={xs[i]} y={Y} w={NW} h={NH} head={n.k} accent={col} headCol={col}>
              <div style={{ fontFamily: "Archivo Black", fontSize: 38, color: MW.text, letterSpacing: "0.02em", lineHeight: 1 }}>{n.t}</div>
              <Mono s={16} c={MW.text} style={{ marginTop: 14, lineHeight: 1.35 }}>{n.s}</Mono>
              <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", gap: 10, alignItems: "center" }}>
                <div style={{ width: 10, height: 10, background: col, opacity: n.built || f % 40 < 26 ? 1 : 0.25 }} />
                <Mono s={16} c={col} w={700} ls="0.18em">{n.built ? "BUILT" : "AT THE EVENT"}</Mono>
              </div>
            </Card>
            {i < 4 && draw > 0 ? (
              <div style={{ position: "absolute", left: xs[i] + NW + 6, top: Y + NH / 2 - 1, width: (GAP - 12) * draw, height: 2, background: MW.text, opacity: 0.85 }}>
                {draw >= 1 ? <div style={{ position: "absolute", right: -2, top: -6, width: 0, height: 0, borderLeft: `10px solid ${MW.text}`,
                  borderTop: "7px solid transparent", borderBottom: "7px solid transparent" }} /> : null}
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
      {arc > 0 ? (
        <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={10} height={10}>
          <path d={`M ${cx4} ${yb} L ${cx4} ${yb + dip} L ${cx0} ${yb + dip} L ${cx0} ${yb + 10}`} fill="none" stroke={MW.amber} strokeWidth={2}
            strokeDasharray={`${len * arc} ${len}`} />
          {arc >= 1 ? <path d={`M ${cx0 - 8} ${yb + 18} L ${cx0} ${yb + 4} L ${cx0 + 8} ${yb + 18} Z`} fill={MW.amber} /> : null}
        </svg>
      ) : null}
      <Mono s={15} c={MW.amber} w={700} ls="0.26em" style={{ position: "absolute", left: (cx0 + cx4) / 2 - 330, width: 660, textAlign: "center", top: yb + dip - 30,
        opacity: prog(t, 160, 172) }}>THE NEXT RUNNER TRAINS ON YOUR GHOST</Mono>
    </>
  );
};

/** The console behind the board: an x-ray hologram turning slowly, out of focus, the thing these objectives are for. */
const Holo: React.FC<{ f: number; buf: ArrayBuffer }> = ({ f, buf }) => {
  const parts = useMemo(() => buildParts(buf), [buf]);
  const poses = useMemo(() => parts.map((p) => partPose(p.meta, TL.shots.end[0])), [parts]);
  const g = useMemo(() => { const g = new THREE.Group(); g.matrixAutoUpdate = false; parts.forEach((p) => g.add(p.group)); return g; }, [parts]);
  clip.constant = 1e5;
  section.constant = 1e5;
  parts.forEach((p, i) => {
    applyPose(p, { ...poses[i], hi: 0 }, { x: -1000, amt: 0 }, 1);
    p.group.visible = !/^panel_/.test(p.meta.name);           // the rear plate's MUMBAI lettering read through the cards
    const dim = 1 - 0.5 * prog(f, LOOP - 10, LOOP + 20);      // and the hologram steps back behind the loop
    p.coreMat.opacity *= 0.32 * dim;
    p.glowMat.opacity *= 0.2 * dim;
    p.ghostMat.opacity *= 0.3 * dim;
    p.fillMat.uniforms.alpha.value *= 0.22 * dim;
  });
  const c = new THREE.Vector3(101, 62.5, 24);
  g.matrix.copy(new THREE.Matrix4().makeTranslation(c.x, c.y, c.z).multiply(new THREE.Matrix4().makeRotationZ(lerp(-0.55, 0.2, f / OBJ_LEN)))
    .multiply(new THREE.Matrix4().makeTranslation(-c.x, -c.y, -c.z)).multiply(asmMatrix(FLIP[1])));
  g.matrixWorldNeedsUpdate = true;
  const pos = new THREE.Vector3(101, -250, 175).lerp(new THREE.Vector3(101, -215, 150), f / OBJ_LEN);
  return (
    <>
      <color attach="background" args={["#040506"]} />
      <CameraAt pos={pos} target={new THREE.Vector3(101, 70, 10)} fov={34} up={new THREE.Vector3(0, 0, 1)} />
      <primitive object={g} />
      <Post strength={0.5} radius={0.5} threshold={1.3} dof={{ focus: 120, range: 70, blur: 7 }} />
    </>
  );
};

/** part: the act card's label (PART IV in the submission cut). */
export const Objectives: React.FC<{ part?: string }> = ({ part = "PART V" }) => {
  const f = useCurrentFrame();
  const buf = useBuffer(staticFile("console.bin"));
  const t = prog(f, 40, OBJ_LEN);
  const sweep = (at: number) => prog(f, at + 4, at + 34);
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {f < 40 ? (
        <Slate f={f} part={part} title="MUMBAI" len={40} />
      ) : (
        <>
          {buf && !(f >= CLIP0 && f < LOOP) ? (
            <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0 }}>
              <Holo f={f} buf={buf} />
            </ThreeCanvas>
          ) : null}
          {/* the tactical display: a dark plate with a fine grid, seen in a slow lateral dolly */}
          <div style={{ position: "absolute", inset: 0, perspective: 1600, perspectiveOrigin: "50% 45%" }}>
            <div style={{ position: "absolute", left: -200, top: -120, width: W + 400, height: H + 240, transformStyle: "preserve-3d",
              transform: `rotateY(${lerp(9, 3, t)}deg) rotateX(${lerp(3, 1.5, t)}deg) translateZ(${lerp(-60, 30, t)}px) translateX(${lerp(40, -40, t)}px)` }}>
              <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 45% 40%, rgba(21,24,27,0.35) 0%, rgba(10,12,14,0.6) 55%, rgba(4,5,6,0.92) 100%)" }} />
              <div style={{ position: "absolute", inset: 0, opacity: 0.16,
                backgroundImage: "linear-gradient(rgba(124,196,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.35) 1px, transparent 1px)",
                backgroundSize: "64px 64px" }} />
              {Array.from({ length: 26 }, (_, i) => (
                <Mono key={i} s={12} c={MW.faint} style={{ position: "absolute", left: 120 + (i % 2) * 1880, top: 200 + Math.floor(i / 2) * 26, opacity: 0.5 }}>
                  {`${(0x1000 + Math.floor(rnd(i, 3) * 60000)).toString(16).toUpperCase()}  ${(rnd(i, 4) * 90).toFixed(2)}  ${rnd(i, 5) > 0.5 ? "OK" : "--"}`}
                </Mono>
              ))}
              <div style={{ position: "absolute", left: 340, top: BAR + 270 }}>
                <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: f > 52 && !(f > 55 && f < 58) ? 1 : 0 }}>MISSION OBJECTIVES</Mono>
                <Mono s={56} c={MW.text} w={700} ls="0.12em" style={{ marginTop: 10, clipPath: `inset(0 ${100 - 100 * prog(f, 58, 76)}% 0 0)` }}>ETHGLOBAL MUMBAI '26</Mono>
              </div>
              {f < CLIP0 + 12 ? OBJ.map((o, i) => {
                const x = 340 + i * 560, y = BAR + 450;
                const s = sweep(o.at);
                return (
                  <div key={o.n} style={{ opacity: 1 - prog(f, CLIP0 - 6, CLIP0 + 8) }}>
                    <Card f={f} at={o.at} x={x} y={y} w={520} h={330} head={`OBJECTIVE ${o.n}`} accent={MW.amber} headCol={MW.amber}>
                      <div style={{ fontFamily: "Archivo Black", fontSize: 54, color: MW.text, letterSpacing: "0.03em", lineHeight: 1 }}>{o.who}</div>
                      <Mono s={19} c={MW.text} style={{ marginTop: 18, lineHeight: 1.35 }}>{o.what}</Mono>
                      <div style={{ position: "absolute", left: 0, right: 0, bottom: 52, borderTop: `1px solid ${MW.faint}`, paddingTop: 12 }}>
                        <Mono s={16} c={MW.dim} ls="0.16em">ANSWERS // {o.answers}</Mono>
                      </div>
                      <div style={{ position: "absolute", left: 0, bottom: 6, display: "flex", gap: 12, alignItems: "center", padding: "5px 14px 6px",
                        border: `2px solid ${o.done ? MW.green : MW.amber}`, background: o.done ? "rgba(123,211,137,0.12)" : "rgba(255,178,63,0.12)" }}>
                        <div style={{ width: 12, height: 12, background: o.done ? MW.green : MW.amber, opacity: o.done || f % 40 < 26 ? 1 : 0.25 }} />
                        <Mono s={19} c={o.done ? MW.green : MW.amber} w={700} ls="0.18em">{o.done ? "BUILT AT THE EVENT" : "TO BUILD AT THE EVENT"}</Mono>
                      </div>
                    </Card>
                    {s > 0 && s < 1 ? (
                      <div style={{ position: "absolute", left: x, top: y, width: 520, height: 330, pointerEvents: "none", mixBlendMode: "screen",
                        background: `linear-gradient(100deg, rgba(255,178,63,0) ${s * 140 - 30}%, rgba(255,178,63,0.22) ${s * 140 - 10}%, rgba(255,178,63,0) ${s * 140}%)` }} />
                    ) : null}
                  </div>
                );
              }) : null}
              <Loop f={f} />
            </div>
          </div>
          {CLIPS.map((c, i) => (f >= CLIP_AT[i] && f < CLIP_AT[i] + Math.round(c.seconds * 60) ? <FieldClip key={i} f={f} i={i} /> : null))}
          <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 50%, rgba(0,0,0,0.75) 100%)" }} />
          <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: clamp(1 - (f - 40) / 4) * 0.25 }} />
          <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, OBJ_LEN - 14, OBJ_LEN)) }} />
        </>
      )}
      <Subs f={f} lines={LINES} />
      <Bars />
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { FONT } from "../theme";
import { clamp, easeInOut, easeOut, easeOutExpo, lerp, prog, rnd } from "../util";
import D from "./dossier.json";

/* A briefing in the manner of Modern Warfare III (2023): intel screens floating over a dark board, filmed close
   with a near-static camera that creeps forward, shallow depth of field, a comms card for whoever is talking, subtitles, letterbox,
   and pixel-block cuts. All type, layout and art here are original. */

const W = 1920, H = 1080, BAR = 118;
const P = 1400;                                  // CSS perspective, px
const UI = FONT.ui, SUB = FONT.sub;
const COL = { panel: "#0c0d0f", edge: "rgba(255,255,255,0.09)", text: "#e6e6e3", dim: "#8f918f", faint: "#5b5d5c",
  orange: "#f08a24", red: "#d43a2b", blue: "#7cc4ff", green: "#7bd389", amber: "#ffb23f" };

type Case = (typeof D.cases)[number];
const SLOT_X = [-1700, -850, 0, 850, 1700];
const SLOT_Y = -240;
const CARD = { w: 520, h: 660 };
const caseAt = (k: number) => D.caseStart + k * D.caseLen;

/* ---------------------------------------------------------------- world: what sits where on the board */

/** Each case is three shots, A (the profile), B (the evidence), C (the countermeasure), of uneven length. */
export const caseShots = (k: number) => {
  const s0 = caseAt(k), [la, lb] = D.splits[k];
  return { A: s0, B: s0 + la, C: s0 + la + lb, end: s0 + D.caseLen };
};
const PROFILE_SPAWN = (k: number) => 214 + k * 12;              // they cascade in, left to right, across the board

type Item = { id: string; x: number; y: number; z: number; w: number; h: number; from: number; to: number; rz?: number };
const ITEMS: Item[] = [
  { id: "comms", x: -260, y: -1080, z: 170, w: 980, h: 380, from: 0, to: 330 },
  ...D.cases.map((_, k) => ({ id: `profile${k}`, x: SLOT_X[k], y: SLOT_Y, z: 90, w: CARD.w, h: CARD.h, from: PROFILE_SPAWN(k), to: 1e9, rz: (rnd(k, 1) - 0.5) * 3 })),
  ...D.cases.map((_, k) => ({ id: `tag${k}`, x: SLOT_X[k] + 440, y: SLOT_Y - 210, z: 150, w: 340, h: 190, from: caseShots(k).A + 12, to: caseShots(k).B - 1, rz: (rnd(k, 4) - 0.5) * 2 })),
  ...D.cases.map((_, k) => ({ id: `evidence${k}`, x: SLOT_X[k] + 470, y: SLOT_Y + 70, z: 200, w: 780, h: 480, from: caseShots(k).B + 8, to: caseShots(k).C - 1, rz: (rnd(k, 2) - 0.5) * 2 })),
  ...D.cases.map((_, k) => ({ id: `counter${k}`, x: SLOT_X[k] + 120, y: SLOT_Y + 500, z: 150, w: 720, h: 230, from: caseShots(k).C + 10, to: caseShots(k).end - 2 })),
  { id: "node", x: 0, y: 820, z: 110, w: 560, h: 230, from: D.outro[0] + 20, to: 1e9 },
];

/* ---------------------------------------------------------------- camera: what the reference measures
   164 shots: the camera is locked off and creeps forward at a constant ~0.66 %/s (p10 0.35, p90 0.83), no easing
   (the midpoint holds half the push), pan ~2 px/s, roll ~0. Cuts are hard; a few open with a short whip while the
   board under the cards resolves out of big pixel blocks. */

type Shot = { a: number; b: number; fx: number; fy: number; fz: number; Z: number; rx: number; ry: number; rate: number; whip: boolean };
const SHOTS: Shot[] = [];
const shot = (a: number, b: number, fx: number, fy: number, fz: number, Z: number, rx = 12, ry = 0, whip = false) =>
  SHOTS.push({ a, b, fx, fy, fz, Z, rx, ry, rate: 0.0042 + rnd(a, 7) * 0.0041, whip });
shot(0, 190, -260, -1080, 170, 120, 10, -9);                                  // the comms card
shot(190, 330, -900, -200, 90, -1500, 16, 6, true);                            // the board
D.cases.forEach((_, k) => {
  const c = caseShots(k), x = SLOT_X[k];
  shot(c.A, c.B, x, SLOT_Y, 90, 80, 10, k % 2 ? 9 : -9, k === 2);
  shot(c.B, c.C, x + 470, SLOT_Y + 70, 200, 150, 9, k % 2 ? -7 : 7, k === 4);
  shot(c.C, c.end, x + 90, SLOT_Y + 300, 120, -190, 12, k % 2 ? 6 : -6);
});
shot(D.outro[0], 2900, 0, 120, 60, -2300, 18, -4, true);                       // the whole board
shot(2900, D.duration, 0, 820, 110, -200, 12, 0);                               // the Any% node
export const DOSSIER_CUTS = SHOTS.map((q) => ({ at: q.a, whip: q.whip })).filter((q) => q.at > 0);
const MOSAIC = [160, 160, 96, 96, 56, 56, 32, 32, 18, 18];                      // board resolution, frame by frame

const camAt = (f: number) => {
  const s = SHOTS.find((q) => f >= q.a && f < q.b) ?? SHOTS[SHOTS.length - 1];
  const sec = (f - s.a) / 60;
  const s0 = P / (P - s.Z);
  const scale = s0 * (1 + s.rate * sec);                                          // linear push, like the reference
  const k = f - s.a;
  const whip = s.whip && k < 8 ? 1 - easeOut(k / 8) : 0;
  const Z = P - P / scale + 260 * whip;
  return { fx: s.fx + (2.5 * sec) / s0, fy: s.fy, fz: s.fz, Z, rx: s.rx, ry: s.ry, rz: 0, shot: s,
    worldBlur: 7 * whip, mosaic: s.whip && k < MOSAIC.length ? MOSAIC[k] : 0 };
};

/** Depth-of-field blur for an item: by depth from the focus plane and distance across it, stronger when close. */
const blurFor = (it: { x: number; y: number; z: number }, cam: ReturnType<typeof camAt>) => {
  const scale = P / (P - cam.Z);
  const lateral = Math.hypot(it.x - cam.fx, it.y - cam.fy);
  return Math.min(10, (0.035 * Math.abs(it.z - cam.fz) + 0.0024 * lateral) * Math.max(0.35, scale));
};

/* ---------------------------------------------------------------- pieces */

const Mono: React.FC<{ s: number; c?: string; w?: number; ls?: string; style?: React.CSSProperties; children: React.ReactNode }> = ({ s, c = COL.text, w = 400, ls = "0.02em", style, children }) => (
  <div style={{ fontFamily: UI, fontSize: s, color: c, fontWeight: w, letterSpacing: ls, whiteSpace: "pre", lineHeight: 1.15, ...style }}>{children}</div>
);

const lcd: React.CSSProperties = {
  backgroundImage: "repeating-linear-gradient(0deg, rgba(0,0,0,0.16) 0 1px, transparent 1px 3px), repeating-linear-gradient(90deg, rgba(0,0,0,0.10) 0 1px, transparent 1px 3px)",
};

/** A card that spawns like the reference: a black box grows from its top-left corner in steps (6 frames), the
    header flickers on, then the content wipes in from the top (frames 10-20). */
const Loaded: React.FC<{ f: number; at: number; w: number; h: number; children: React.ReactNode }> = ({ f, at, w, h, children }) => {
  const k = f - at;
  if (k < 0) return null;
  const steps = [[0.16, 0.12], [0.16, 0.12], [0.45, 0.3], [0.45, 0.3], [0.8, 0.7], [0.8, 0.7], [1, 1]];
  const [sw, sh] = k < steps.length ? steps[k] : [1, 1];
  const header = 0.17;                                                       // the header strip shows first
  const wipe = k < 6 ? 0 : k < 11 ? header : Math.min(1, header + ((k - 11) / 9) * (1 - header));
  const flick = k >= 6 && k < 10 && k % 2 === 1 ? 0.35 : 1;
  return (
    <div style={{ position: "relative", width: w, height: h }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: w * sw, height: h * sh, background: "#030303", border: `1px solid ${COL.edge}` }} />
      {k >= 6 ? (
        <div style={{ position: "absolute", inset: 0, opacity: flick, clipPath: `inset(0 0 ${((1 - wipe) * 100).toFixed(2)}% 0)` }}>{children}</div>
      ) : null}
    </div>
  );
};

/** A small file tab beside the profile: game, platform, record, year. */
const Tag: React.FC<{ f: number; c: Case; at: number }> = ({ f, c, at }) => {
  return (
    <Loaded f={f} at={at} w={340} h={190}>
      <div style={{ position: "absolute", inset: 0, background: COL.panel, border: `1px solid ${COL.edge}`, padding: "14px 18px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 8, height: 8, background: COL.orange }} />
          <Mono s={13} c={COL.dim}>{`File ${c.id} // Claim`}</Mono>
        </div>
        <Mono s={22} w={700} style={{ marginTop: 12 }}>{c.game}</Mono>
        <Mono s={15} c={COL.dim} style={{ marginTop: 6 }}>{`${c.platform}${c.year ? " // " + c.year : ""}`}</Mono>
        <Mono s={15} c={COL.orange} style={{ marginTop: 10, whiteSpace: "normal" }}>{c.claim.toUpperCase()}</Mono>
      </div>
    </Loaded>
  );
};

const Silhouette: React.FC<{ seed: number; tone?: string; bar?: boolean }> = ({ seed, tone = "#26323a", bar = true }) => {
  const r = (i: number) => rnd(seed, i, 7);
  const hx = 235 + (r(1) - 0.5) * 16, hy = 212 + (r(2) - 0.5) * 12, hw = 86 + r(3) * 14, hh = 112 + r(4) * 12;
  return (
    <svg width={470} height={520} viewBox="0 0 470 520" style={{ position: "absolute", inset: 0 }}>
      <defs>
        <linearGradient id={`bg${seed}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#d6dedf" /><stop offset="1" stopColor="#aebbbe" /></linearGradient>
        <radialGradient id={`sh${seed}`} cx="0.42" cy="0.32" r="0.75"><stop offset="0" stopColor="#4a5a63" /><stop offset="0.45" stopColor={tone} /><stop offset="1" stopColor="#0d1215" /></radialGradient>
        <filter id={`soft${seed}`}><feGaussianBlur stdDeviation="2.2" /></filter>
        <filter id={`gr${seed}`}><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={seed} /><feColorMatrix type="saturate" values="0" /></filter>
        <radialGradient id={`lt${seed}`} cx="0.3" cy="0.2" r="0.9"><stop offset="0" stopColor="#ffffff" stopOpacity="0.28" /><stop offset="1" stopColor="#000000" stopOpacity="0.25" /></radialGradient>
      </defs>
      <rect width={470} height={520} fill={`url(#bg${seed})`} />
      {Array.from({ length: 12 }, (_, i) => (
        <g key={i} opacity={0.35}>
          <line x1={0} x2={470} y1={40 + i * 40} y2={40 + i * 40} stroke="#6f7c80" strokeWidth={1} />
          <text x={8} y={36 + i * 40} fontFamily={UI} fontSize={12} fill="#5d696d">{`${6 - Math.floor(i / 2)}'${i % 2 ? "6" : "0"}`}</text>
        </g>
      ))}
      <g filter={`url(#soft${seed})`}>
        <path d={`M 20 520 C 40 420, 120 390, ${hx - 70} 372 L ${hx - 34} ${hy + hh - 10} L ${hx + 34} ${hy + hh - 10} L ${hx + 70} 372 C 350 390, 430 420, 450 520 Z`} fill={`url(#sh${seed})`} />
        <ellipse cx={hx} cy={hy} rx={hw} ry={hh} fill={`url(#sh${seed})`} />
      </g>
      <rect width={470} height={520} fill={`url(#lt${seed})`} />
      <rect width={470} height={520} filter={`url(#gr${seed})`} opacity={0.16} />
      {bar ? <>
        <rect x={hx - 150} y={hy - 30} width={300} height={56} fill="#050505" />
        <text x={hx} y={hy + 7} textAnchor="middle" fontFamily={UI} fontWeight={700} fontSize={22} letterSpacing="6" fill="#e9e9e6">REDACTED</text>
      </> : null}
    </svg>
  );
};

const Profile: React.FC<{ f: number; k: number; c: Case; at: number }> = ({ f, k, c, at }) => {
  const stampAt = caseShots(k).C + 24;
  const st = f - stampAt;
  return (
    <Loaded f={f} at={at} w={CARD.w} h={CARD.h}>
      <div style={{ position: "absolute", inset: 0, background: `linear-gradient(180deg, #121316, ${COL.panel})`, border: `1px solid ${COL.edge}`, padding: "22px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 10, height: 10, borderRadius: 5, background: COL.orange }} />
          <Mono s={16} c={COL.dim}>Profile View</Mono>
          <div style={{ marginLeft: "auto", width: 26, height: 26, border: `2px solid ${COL.dim}`, opacity: 0.6 }} />
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 10 }}>
          <Mono s={44} w={700}>{c.name}</Mono>
          <Mono s={26} c={COL.dim}>{`> ${c.id}`}</Mono>
        </div>
        <div style={{ position: "relative", width: 470, height: 470, marginTop: 14, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, top: -30 }}><Silhouette seed={k + 3} /></div>
          <div style={{ position: "absolute", inset: 0, ...lcd }} />
          <div style={{ position: "absolute", inset: 0, boxShadow: "inset 0 0 60px rgba(0,0,0,0.45)" }} />
          {st >= 0 ? (
            <div style={{ position: "absolute", left: 40, top: 300, transform: `rotate(-9deg) scale(${lerp(1.6, 1, easeOutExpo(clamp(st / 8)))})`, opacity: clamp(st / 4) * 0.92,
              border: `4px solid ${COL.red}`, padding: "8px 16px", background: "rgba(212,58,43,0.08)" }}>
              <Mono s={26} w={700} c={COL.red} ls="0.12em">{c.verdict.toUpperCase()}</Mono>
            </div>
          ) : null}
        </div>
      </div>
    </Loaded>
  );
};

const EvidenceArt: React.FC<{ f: number; c: Case; at: number }> = ({ f, c, at }) => {
  const e = c.evidence as Record<string, unknown>;
  const t = easeOut(prog(f, at + 14, at + 70));
  switch (e.kind) {
    case "timing": {
      const x = (v: number) => 40 + ((v - 5.4) / 0.4) * 640;
      return (
        <svg width={700} height={300}>
          <text x={40} y={70} fontFamily={UI} fontSize={20} fill={COL.dim}>CLAIMED</text>
          <text x={40} y={140} fontFamily={UI} fontWeight={700} fontSize={66} fill={COL.red}>{`${e.claimed} S`}</text>
          <line x1={36} x2={36 + 270 * t} y1={118} y2={118} stroke={COL.red} strokeWidth={5} />
          <text x={380} y={70} fontFamily={UI} fontSize={20} fill={COL.dim}>FASTEST POSSIBLE</text>
          <text x={380} y={140} fontFamily={UI} fontWeight={700} fontSize={66} fill={COL.text}>{`${e.floor} S`}</text>
          <rect x={x(5.4)} y={200} width={(x(5.57) - x(5.4)) * t} height={36} fill={COL.red} opacity={0.18} />
          <line x1={x(5.4)} x2={x(5.8)} y1={236} y2={236} stroke={COL.dim} strokeWidth={2} />
          {[5.4, 5.5, 5.6, 5.7, 5.8].map((v) => (
            <g key={v}><line x1={x(v)} x2={x(v)} y1={236} y2={246} stroke={COL.dim} /><text x={x(v) - 18} y={268} fontFamily={UI} fontSize={14} fill={COL.dim}>{v.toFixed(2)}</text></g>
          ))}
          <line x1={x(5.57)} x2={x(5.57)} y1={190} y2={240} stroke={COL.text} strokeWidth={2} />
          <circle cx={x(5.51)} cy={218} r={8} fill={COL.red} opacity={t} />
          <text x={x(5.4) + 8} y={194} fontFamily={UI} fontSize={14} fill={COL.red} opacity={t}>IMPOSSIBLE</text>
        </svg>
      );
    }
    case "odds": {
      const rows = e.rows as [string, number, number, number][];
      return (
        <svg width={700} height={300}>
          {rows.map(([label, got, of, exp], i) => {
            const y = 40 + i * 110;
            const obs = got / of;
            return (
              <g key={label}>
                <text x={20} y={y} fontFamily={UI} fontSize={20} fill={COL.dim}>{label.toUpperCase()}</text>
                <text x={680} y={y} textAnchor="end" fontFamily={UI} fontSize={20} fill={COL.text}>{`${got} / ${of} = ${(obs * 100).toFixed(1)}%`}</text>
                <rect x={20} y={y + 16} width={660} height={30} fill="none" stroke={COL.faint} />
                <rect x={20} y={y + 16} width={660 * obs * t} height={30} fill={COL.orange} opacity={0.85} />
                <line x1={20 + 660 * exp} x2={20 + 660 * exp} y1={y + 8} y2={y + 54} stroke={COL.text} strokeWidth={3} />
                <text x={26 + 660 * exp} y={y + 74} fontFamily={UI} fontSize={14} fill={COL.text}>{`EXPECTED ${(exp * 100).toFixed(1)}%`}</text>
              </g>
            );
          })}
          <text x={20} y={282} fontFamily={UI} fontWeight={700} fontSize={36} fill={COL.red} opacity={clamp(t * 1.5 - 0.4)}>{`P = ${String(e.odds).toUpperCase()}`}</text>
        </svg>
      );
    }
    case "seeds": {
      const n = Math.floor(Number(e.seeds) * t);
      return (
        <svg width={700} height={300}>
          <text x={20} y={46} fontFamily={UI} fontSize={20} fill={COL.dim}>SEEDS GENERATED</text>
          <text x={20} y={112} fontFamily={UI} fontWeight={700} fontSize={60} fill={COL.text}>{n.toLocaleString("en-US")}</text>
          <text x={20} y={160} fontFamily={UI} fontSize={20} fill={COL.dim}>MATCHING THE RUN</text>
          <text x={340} y={160} fontFamily={UI} fontWeight={700} fontSize={30} fill={COL.red}>0</text>
          {Array.from({ length: 8 * 34 }, (_, i) => {
            const on = i / (8 * 34) < t;
            return <rect key={i} x={20 + (i % 34) * 19.5} y={186 + Math.floor(i / 34) * 10} width={16} height={7} fill={on ? "#3a3d3f" : "#17191a"} />;
          })}
          <text x={20} y={290} fontFamily={UI} fontSize={16} fill={COL.orange}>VERSION 1.00 + 1.09 IN ONE VIDEO // SPLICED</text>
        </svg>
      );
    }
    case "inputs": {
      const pts: string[] = [];
      for (let i = 0; i <= 140; i++) {
        const x = 20 + i * 4.7;
        const burst = (i > 46 && i < 58) || (i > 96 && i < 110);
        const v = burst ? (i % 2 ? -1 : 1) * (0.7 + rnd(i, 3) * 0.3) : Math.sin(i * 0.12) * 0.35 + (rnd(i, 4) - 0.5) * 0.08;
        if (i / 140 <= t) pts.push(`${x},${150 - v * 90}`);
      }
      return (
        <svg width={700} height={300}>
          <text x={20} y={40} fontFamily={UI} fontSize={20} fill={COL.dim}>STEERING INPUT // PER FRAME</text>
          <line x1={20} x2={680} y1={150} y2={150} stroke={COL.faint} strokeDasharray="4 6" />
          <rect x={20 + 46 * 4.7} y={50} width={12 * 4.7} height={200} fill={COL.red} opacity={0.14 * t} />
          <rect x={20 + 96 * 4.7} y={50} width={14 * 4.7} height={200} fill={COL.red} opacity={0.14 * t} />
          <polyline points={pts.join(" ")} fill="none" stroke={COL.text} strokeWidth={2} />
          <text x={20} y={286} fontFamily={UI} fontWeight={700} fontSize={22} fill={COL.red}>INPUT RATE ABOVE HUMAN LIMIT // GAME SLOWED</text>
        </svg>
      );
    }
    default: {
      const cut = 1;
      return (
        <svg width={700} height={300}>
          <text x={20} y={40} fontFamily={UI} fontSize={20} fill={COL.dim}>FRAME STRIP // SPELUNKY CLASSIC</text>
          {Array.from({ length: 6 }, (_, i) => (
            <g key={i} opacity={clamp(t * 6 - i)}>
              <rect x={20 + i * 112} y={70} width={100} height={130} fill="#16181a" stroke={COL.faint} />
              <text x={70 + i * 112} y={142} textAnchor="middle" fontFamily={UI} fontSize={16} fill={COL.dim}>{`LVL ${i < cut ? 1 : i + 1}`}</text>
            </g>
          ))}
          <line x1={20 + cut * 112 - 6} x2={20 + cut * 112 - 6} y1={56} y2={214} stroke={COL.red} strokeWidth={4} opacity={clamp(t * 2 - 0.6)} />
          <text x={20 + cut * 112 + 4} y={240} fontFamily={UI} fontWeight={700} fontSize={22} fill={COL.red} opacity={clamp(t * 2 - 0.6)}>CUT // SAVED RUN SPLICED IN</text>
          <text x={20} y={286} fontFamily={UI} fontSize={16} fill={COL.orange}>RECORD 2:30 // UNNOTICED FOR 8 YEARS</text>
        </svg>
      );
    }
  }
};

const Evidence: React.FC<{ f: number; k: number; c: Case; at: number }> = ({ f, k, c, at }) => (
  <Loaded f={f} at={at} w={780} h={480}>
    <div style={{ position: "absolute", inset: 0, background: COL.panel, border: `1px solid ${COL.edge}`, padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 10, height: 10, background: COL.orange }} />
        <Mono s={16} c={COL.dim}>{`File ${String(k + 1).padStart(2, "0")}.A // ${(c.evidence as { title: string }).title}`}</Mono>
        <Mono s={16} c={COL.dim} style={{ marginLeft: "auto" }}>{`${c.game} // ${c.platform}`}</Mono>
      </div>
      <div style={{ height: 1, background: COL.edge, margin: "14px 0 6px" }} />
      <EvidenceArt f={f} c={c} at={at} />
      <Mono s={14} c={COL.faint} style={{ position: "absolute", left: 24, bottom: 16 }}>{`SOURCE: ${(c.evidence as { source: string }).source.toUpperCase()}`}</Mono>
    </div>
  </Loaded>
);

const Counter: React.FC<{ f: number; k: number; c: Case; at: number }> = ({ f, k, c, at }) => {
  const planned = c.lines[2].startsWith("Planned");
  return (
    <Loaded f={f} at={at} w={720} h={230}>
      <div style={{ position: "absolute", inset: 0, background: "rgba(14,12,8,0.96)", border: `1px solid rgba(255,178,63,0.35)`, borderLeft: `5px solid ${COL.amber}`, padding: "18px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Mono s={18} w={700} c={COL.amber} ls="0.18em">ANY% // COUNTERMEASURE</Mono>
          <div style={{ marginLeft: "auto", border: `1px solid ${planned ? COL.dim : COL.green}`, padding: "2px 10px" }}>
            <Mono s={14} c={planned ? COL.dim : COL.green}>{planned ? "PLANNED" : "BUILT"}</Mono>
          </div>
        </div>
        <Mono s={25} c={COL.text} style={{ whiteSpace: "normal", marginTop: 18, lineHeight: 1.35 }}>{c.lines[2].replace(/^Planned: /, "")}</Mono>
        <Mono s={13} c={COL.faint} style={{ position: "absolute", left: 24, bottom: 14 }}>{`REF ${c.id} // REPLAY // RULES ${k < 3 ? "v2" : "v2"}`}</Mono>
      </div>
    </Loaded>
  );
};

const Node: React.FC<{ f: number; at: number }> = ({ f, at }) => (
  <Loaded f={f} at={at} w={560} h={230}>
    <div style={{ position: "absolute", inset: 0, background: "rgba(14,12,8,0.96)", border: `2px solid ${COL.amber}`, padding: "22px 26px", textAlign: "center" }}>
      <Mono s={16} c={COL.dim} ls="0.3em">COUNTERMEASURE</Mono>
      <Mono s={74} w={700} c={COL.amber} style={{ marginTop: 6 }}>ANY%</Mono>
      <Mono s={16} c={COL.text} style={{ marginTop: 10 }}>EVERY RUN REPLAYED // EVERY INPUT LOGGED</Mono>
    </div>
  </Loaded>
);

/* ---------------------------------------------------------------- the board itself */

export const Board: React.FC<{ f: number; plate?: boolean }> = ({ f, plate }) => {
  const rows = Array.from({ length: 22 }, (_, i) => i);
  return (
    <div style={{ position: "absolute", left: plate ? 0 : -2400, top: plate ? 0 : -1400, width: 4800, height: 2800,
      background: "radial-gradient(ellipse at 50% 40%, #24201b 0%, #15130f 55%, #0a0908 100%)" }}>
      <svg width={4800} height={2800} style={{ position: "absolute", inset: 0 }}>
        {Array.from({ length: 49 }, (_, i) => <line key={"v" + i} x1={i * 100} x2={i * 100} y1={0} y2={2800} stroke="#ffffff" strokeOpacity={0.035} />)}
        {Array.from({ length: 29 }, (_, i) => <line key={"h" + i} x1={0} x2={4800} y1={i * 100} y2={i * 100} stroke="#ffffff" strokeOpacity={0.035} />)}
        {/* red dashed lines from every case file down to the countermeasure */}
        {SLOT_X.map((x, k) => (
          <path key={k} d={`M ${2400 + x} ${1400 + SLOT_Y + 340} C ${2400 + x} ${1400 + 560}, ${2400} ${1400 + 520}, ${2400} ${1400 + 700}`}
            fill="none" stroke={COL.red} strokeWidth={4} strokeDasharray="16 12" opacity={0.75} />
        ))}
        <path d="M 300 2250 L 4500 2250" stroke={COL.orange} strokeWidth={3} opacity={0.5} />
      </svg>
      <div style={{ position: "absolute", left: 2400 - 1300, top: 1400 - 880, width: 2600, textAlign: "center" }}>
        <Mono s={92} w={700} c="#cfcac0" ls="0.32em" style={{ opacity: 0.85 }}>CASE FILES</Mono>
        <Mono s={30} c={COL.dim} ls="0.4em" style={{ marginTop: 10 }}>LEADERBOARD FRAUD // 1982 - 2024</Mono>
      </div>
      {/* faint printed leaderboards on the board, for texture */}
      {[[260, 300], [3900, 260], [300, 1900], [3850, 1950]].map(([x, y], j) => (
        <div key={j} style={{ position: "absolute", left: x, top: y, opacity: 0.22, background: "#1d1a16", padding: 18, border: "1px solid #2c2822" }}>
          {rows.map((i) => (
            <Mono key={i} s={18} c="#b9b2a5">{`${String(i + 1).padStart(2, "0")}  ${"RUNNER_" + Math.floor(rnd(i, j, 5) * 9000 + 1000)}  ${Math.floor(rnd(i, j, 6) * 9)}:${String(Math.floor(rnd(i, j, 7) * 60)).padStart(2, "0")}.${Math.floor(rnd(i, j, 8) * 99)}  ${rnd(i, j, 9) > 0.86 ? "VOID" : "OK  "}`}</Mono>
          ))}
        </div>
      ))}
    </div>
  );
};

/* ---------------------------------------------------------------- screen-space: comms, subtitles, cuts */

type Line = { at: number; len: number; who: string; text: string };
const LINES: Line[] = [
  ...(D.intro_lines as Line[]),
  ...D.cases.flatMap((c, k) => {
    const q = caseShots(k), starts = [q.A, q.B, q.C, q.end];
    return c.lines.map((text, i) => ({ at: starts[i] + 8, len: starts[i + 1] - starts[i] - 10, who: i === 2 ? "Any%" : "Handler", text }));
  }),
  ...(D.outro_lines as Line[]),
];
export const DOSSIER_LINES = LINES;
const lineAt = (f: number) => LINES.find((l) => f >= l.at && f < l.at + l.len);

const Avatar: React.FC<{ seed: number; on?: boolean; size?: number }> = ({ seed, on, size = 64 }) => (
  <div style={{ width: size, height: size, border: `2px solid ${on ? COL.green : "rgba(255,255,255,0.18)"}`, background: "#c9d2d3", position: "relative", overflow: "hidden" }}>
    <div style={{ position: "absolute", left: 0, top: -size * 0.04, transform: `scale(${size / 470})`, transformOrigin: "0 0" }}>
      <Silhouette seed={seed} bar={false} />
    </div>
    <div style={{ position: "absolute", inset: 0, ...lcd }} />
  </div>
);

const Wave: React.FC<{ f: number; w: number; h: number; active: boolean }> = ({ f, w, h, active }) => {
  const pts: string[] = [];
  for (let i = 0; i <= 120; i++) {
    const x = (i / 120) * w;
    const a = active ? 0.25 + 0.75 * Math.abs(Math.sin(i * 0.31 + f * 0.37) * Math.sin(i * 0.07 - f * 0.11)) : 0.05;
    pts.push(`${x},${h / 2 - Math.sin(i * 0.9 + f * 0.8) * a * h * 0.42}`);
  }
  return (
    <svg width={w} height={h}>
      <polyline points={pts.join(" ")} fill="none" stroke="#dfe8ea" strokeWidth={2} opacity={0.9} />
      <line x1={0} x2={w} y1={h / 2} y2={h / 2} stroke="#ffffff" strokeOpacity={0.12} />
    </svg>
  );
};

const CommsBody: React.FC<{ f: number; who: string; big?: boolean }> = ({ f, who, big }) => {
  const l = lineAt(f);
  const handler = who === "Handler";
  const s = big ? 1 : 0.42;
  return (
    <div style={{ width: 980 * s, padding: 22 * s, background: "rgba(10,11,13,0.94)", border: `1px solid ${COL.edge}` }}>
      <div style={{ display: "flex", gap: 10 * s, alignItems: "center" }}>
        {[1, 2, 3, 4, 5].map((i) => <Avatar key={i} seed={i * 11} size={92 * s} on={(handler && i === 1) || (!handler && i === 2)} />)}
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <Mono s={15 * s} c={COL.dim}>{D.speaker.channel}</Mono>
          <Mono s={15 * s} c={COL.dim}>{D.speaker.people}</Mono>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 * s, marginTop: 16 * s }}>
        <div style={{ width: 11 * s, height: 11 * s, borderRadius: 6 * s, background: COL.blue }} />
        <Mono s={22 * s} c={COL.text}>Online</Mono>
      </div>
      <div style={{ display: "flex", gap: 22 * s, marginTop: 12 * s }}>
        <Avatar seed={handler ? 11 : 22} size={160 * s} />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14 * s }}>
            <Mono s={54 * s} w={700}>{handler ? D.speaker.name : "Any%, Ops."}</Mono>
            <Mono s={22 * s} c={COL.dim}>{handler ? D.speaker.freq : "Freq 99.9"}</Mono>
          </div>
          <Mono s={20 * s} c="#9fd7e8" ls="0.06em" style={{ marginTop: 8 * s }}>RECEIVING COMMUNICATIONS...</Mono>
          <div style={{ marginTop: 10 * s }}><Wave f={f} w={640 * s} h={80 * s} active={!!l} /></div>
        </div>
      </div>
    </div>
  );
};

const Subtitle: React.FC<{ f: number }> = ({ f }) => {
  const l = lineAt(f);
  if (!l) return null;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: BAR + 70, textAlign: "center", fontFamily: SUB, fontWeight: 600, fontSize: 33,
      color: "#f2f2f0", textShadow: "0 2px 6px rgba(0,0,0,0.95), 0 0 2px rgba(0,0,0,0.9)" }}>
      <span style={{ color: COL.blue }}>{l.who}: </span>{l.text}
    </div>
  );
};


/* ---------------------------------------------------------------- the shot */

const ItemView: React.FC<{ f: number; it: Item; cam: ReturnType<typeof camAt> }> = ({ f, it, cam }) => {
  if (f < it.from || f > it.to) return null;
  const blur = blurFor(it, cam);
  let body: React.ReactNode = null;
  const k = Number(it.id.slice(-1));
  if (it.id === "comms") body = <CommsBody f={f} who={lineAt(f)?.who ?? "Handler"} big />;
  else if (it.id.startsWith("profile")) body = <Profile f={f} k={k} c={D.cases[k]} at={it.from} />;
  else if (it.id.startsWith("tag")) body = <Tag f={f} c={D.cases[k]} at={it.from} />;
  else if (it.id.startsWith("evidence")) body = <Evidence f={f} k={k} c={D.cases[k]} at={it.from} />;
  else if (it.id.startsWith("counter")) body = <Counter f={f} k={k} c={D.cases[k]} at={it.from} />;
  else if (it.id === "node") body = <Node f={f} at={it.from + 100} />;
  return (
    <div style={{ position: "absolute", left: it.x - it.w / 2, top: it.y - it.h / 2, width: it.w, height: it.h,
      transform: `translateZ(${it.z}px) rotateZ(${it.rz ?? 0}deg)`, filter: blur > 0.3 ? `blur(${blur.toFixed(2)}px)` : undefined,
      boxShadow: "0 30px 60px rgba(0,0,0,0.55)" }}>
      {body}
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "linear-gradient(115deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0) 32%, rgba(255,255,255,0) 70%, rgba(255,255,255,0.04) 100%)" }} />
    </div>
  );
};

export const Dossier: React.FC<{ offset?: number }> = ({ offset = 0 }) => {
  const f = useCurrentFrame() + offset;
  const cam = camAt(f);
  const boardBlur = Math.min(7, (0.035 * cam.fz + 1.2) * Math.max(0.35, P / (P - cam.Z)));
  const who = lineAt(f)?.who ?? "Handler";
  const fadeIn = clamp((f - 8) / 14);
  const fadeOut = 1 - prog(f, D.duration - 24, D.duration);
  const showHud = f > 330 && f < D.outro[0] + 300;
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, perspective: `${P}px`, perspectiveOrigin: "50% 50%", opacity: fadeIn * fadeOut,
        filter: cam.worldBlur > 0.2 ? `blur(${cam.worldBlur.toFixed(2)}px)` : undefined }}>
        <div style={{ position: "absolute", left: W / 2, top: H / 2, width: 0, height: 0, transformStyle: "preserve-3d",
          transform: `translateZ(${cam.Z}px) rotateX(${cam.rx}deg) rotateY(${cam.ry}deg) rotateZ(${cam.rz}deg) translate3d(${-cam.fx}px, ${-cam.fy}px, ${-cam.fz}px)` }}>
          <Img src={staticFile(cam.mosaic ? `board_m${cam.mosaic}.jpg` : "board.jpg")}
            style={{ position: "absolute", left: -2400, top: -1400, width: 4800, height: 2800, filter: `blur(${(cam.mosaic ? 0 : boardBlur).toFixed(2)}px)` }} />
          {ITEMS.map((it) => <ItemView key={it.id} f={f} it={it} cam={cam} />)}
        </div>
      </div>
      {/* lens: warm grade, vignette, a little bloom on highlights */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.6) 100%)" }} />
      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(255,170,90,0.05), rgba(40,90,120,0.05))", mixBlendMode: "overlay" }} />
      {showHud ? (
        <div style={{ position: "absolute", left: 60, bottom: BAR + 30, opacity: 0.92, filter: "blur(0.4px)" }}>
          <CommsBody f={f} who={who} />
        </div>
      ) : null}
      <Subtitle f={f} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: BAR, background: "#000" }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: BAR, background: "#000" }} />
    </AbsoluteFill>
  );
};

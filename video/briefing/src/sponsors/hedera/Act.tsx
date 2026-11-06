import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import SCREENS from "../../../public/handler/screens.json";
import PROOF from "../../../public/proof.json";
import BUILT from "../../acts/built.json";
import { BAR, Bars, Card, Line, Mono, MW, Row, Slate, Subs, W } from "../../acts/common";
import { Board } from "../../acts/GameReel";
import { clamp, easeInOut, easeOutExpo, lerp, prog } from "../../util";
import { Plate, usePlateAssets } from "./Plate";
import T from "./timing.json";

/* ANY% x HEDERA, the sponsor demo's own act (SPONSOR_DEMOS.md). Hedera does two jobs in Any%, in the wording the designs
   were red-teamed to (memory: hedera-live-run-design, hire-the-champ-design):
   - the clock: a Live run's seed comes from the running hash of its own START message on HCS, a checkpoint goes to the
     console's HCS topic every 2 s of play, and every input must be committed within 15 s + 3% of real time (the
     envelope), so a run slowed past about 18 s on 90 s of play is not a Live run. Real-time bots are not ruled out.
   - the pay: PB, the coach agent, buys the ghost of the runner just ahead over x402, USDC (HTS) on Hedera testnet,
     payTo = that runner, under caps the player set, with no human approving the payment.
   Both with the Hedera SDK only: HCS + HTS, no Solidity. World was dropped on 5 Nov: no World ID anywhere.
   Honesty: the calls are built at the event. Until built.json says hedera: true every call card says CALL: AT THE
   EVENT; the launcher screens keep their MOCK pill (its World chip is masked: World is out). No topic, tx or account
   id is invented: the only values on screen are real (the device seed, the board's two replayed times, Hedera's public
   testnet USDC token) or the design's own arithmetic (15 s + 1.03 x play). The HashScan beat is a field-report slot;
   when built.json gains HEDERA clips they play there, like Objectives.tsx, and the act grows by the difference
   (timing.json + prep/sponsors/hedera.py). */

type Shot = { id: string; at: number; len: number; cards?: number[]; chirps?: number[]; hits?: number[]; glitch?: number[] };
type Clip = { file: string; sponsor: string; title: string; rows: [string, string][]; line: string; seconds: number; from?: number };
type TLine = { at: number; len: number; todo: string; done?: string; slot?: boolean };

const DONE = (BUILT.built as Record<string, boolean>).hedera === true;
const CLIPS = (BUILT.clips as unknown as Clip[]).filter((c) => String(c.sponsor).toUpperCase() === "HEDERA");
const BASE = T.shots as Shot[];
const SLOT = BASE.find((s) => s.id === "hashscan")!;
const CLIP_FR = CLIPS.map((c) => Math.round(c.seconds * 60));
const CLIPS_LEN = CLIP_FR.reduce((a, b) => a + b, 0);
const GROW = CLIPS.length ? CLIPS_LEN - SLOT.len : 0;
const shift = (f: number) => (f >= SLOT.at + SLOT.len ? f + GROW : f);
const SHOTS: Shot[] = BASE.map((s) => (s.id === "hashscan" && CLIPS.length ? { ...s, len: CLIPS_LEN } : { ...s, at: shift(s.at) }));
const CLIP_AT = CLIP_FR.map((_, i) => SLOT.at + CLIP_FR.slice(0, i).reduce((a, b) => a + b, 0));
export const HEDERA_LEN = T.len + GROW;

const LINES: Line[] = [
  ...(T.lines as TLine[]).filter((l) => !(CLIPS.length && l.slot))
    .map((l) => ({ at: shift(l.at), len: l.len, who: "Handler", text: DONE && l.done ? l.done : l.todo })),
  ...CLIPS.map((c, i) => ({ at: CLIP_AT[i] + 16, len: CLIP_FR[i] - 28, who: "Handler", text: c.line })),
];
const sh = (id: string) => SHOTS.find((s) => s.id === id)!;
const shotAt = (f: number) => SHOTS.reduce((k, s) => (f >= s.at ? s : k), SHOTS[0]);

const S = SCREENS as { steps: string[]; images: Record<string, number>; every: number; you: number; ria: number };
const fmt = (fr: number) => {
  const cs = Math.round((fr * 100) / 60);
  return `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
};
const secs = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, "0")}`;
const RIA = fmt(S.ria), YOU = fmt(S.you);                      // the board's two real, replayed times
const SEED = (PROOF as { seeded_seed: string }).seeded_seed;     // the seeded RUSH HOUR log's header: the device's own seed
const CALL = DONE ? "CALL: BUILT" : "CALL: AT THE EVENT";

/* ------------------------------------------------------------------ small pieces */

const Kicker: React.FC<{ t: number; at?: number; c?: string; children: React.ReactNode; style?: React.CSSProperties }> = ({ t, at = 2, c = MW.orange, children, style }) => (
  <Mono s={17} c={c} w={700} ls="0.4em" style={{ opacity: t > at && !(t > at + 3 && t < at + 6) ? 1 : 0, ...style }}>{children}</Mono>
);

const Title: React.FC<{ t: number; at?: number; s?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ t, at = 6, s = 56, children, style }) => (
  <div style={{ fontFamily: "Archivo Black", fontSize: s, lineHeight: 1.05, color: MW.text, letterSpacing: "0.02em", whiteSpace: "pre",
    clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, at, at + 16))}% 0 0)`, ...style }}>{children}</div>
);

/** The status pill: green once built.json says so, amber and blinking until then. */
const Pill: React.FC<{ t: number; at: number; text?: string; ok?: boolean; s?: number; style?: React.CSSProperties }> = ({ t, at, text = CALL, ok = DONE, s = 18, style }) => {
  if (t < at) return null;
  const col = ok ? MW.green : MW.amber;
  return (
    <div style={{ display: "inline-flex", gap: 12, alignItems: "center", padding: "5px 14px 6px", border: `2px solid ${col}`,
      background: ok ? "rgba(123,211,137,0.12)" : "rgba(255,178,63,0.12)", opacity: prog(t, at, at + 4), ...style }}>
      <div style={{ width: 11, height: 11, background: col, opacity: ok || t % 40 < 26 ? 1 : 0.25 }} />
      <Mono s={s} c={col} w={700} ls="0.18em">{text}</Mono>
    </div>
  );
};

/** The call status, right-aligned in a card's corner (Handler.tsx's convention). */
const Status: React.FC = () => (
  <div style={{ position: "absolute", right: 0, top: 0, textAlign: "right" }}>
    <Mono s={14} c={DONE ? MW.green : MW.amber} w={700} ls="0.16em">{CALL}</Mono>
  </div>
);

/** An arrow that draws itself from x0 to x1 at height y. */
const Arrow: React.FC<{ t: number; at: number; x0: number; x1: number; y: number; col?: string; dur?: number }> = ({ t, at, x0, x1, y, col = MW.text, dur = 12 }) => {
  const d = prog(t, at, at + dur);
  if (d <= 0) return null;
  const right = x1 > x0;
  const len = Math.abs(x1 - x0) * d;
  const head: React.CSSProperties = right
    ? { right: -2, borderLeft: `10px solid ${col}` }
    : { left: -2, borderRight: `10px solid ${col}` };
  return (
    <div style={{ position: "absolute", left: right ? x0 : x0 - len, top: y - 1, width: len, height: 2, background: col, opacity: 0.85 }}>
      {d >= 1 ? <div style={{ position: "absolute", top: -6, width: 0, height: 0, borderTop: "7px solid transparent", borderBottom: "7px solid transparent", ...head }} /> : null}
    </div>
  );
};

/** A packet (or a coin) riding from x0 to x1 between frames a and b. */
const Packet: React.FC<{ t: number; a: number; b: number; x0: number; x1: number; y: number; col?: string; coin?: boolean }> = ({ t, a, b, x0, x1, y, col = MW.amber, coin }) => {
  if (t < a || t > b + 2) return null;
  const x = lerp(x0, x1, easeInOut(prog(t, a, b)));
  return coin ? (
    <div style={{ position: "absolute", left: x - 17, top: y - 17, width: 34, height: 34, borderRadius: "50%", background: "radial-gradient(circle at 40% 35%, #ffe08a, #e0a52c 70%)",
      border: "2px solid #8a5a10", boxShadow: "0 0 18px rgba(255,190,80,0.6)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Mono s={17} c="#5a3a08" w={700}>$</Mono>
    </div>
  ) : <div style={{ position: "absolute", left: x - 9, top: y - 9, width: 18, height: 18, borderRadius: "50%", background: col, boxShadow: `0 0 16px ${col}` }} />;
};

/** A glowing ring around a box for a moment after `at` (an arrival). */
const Ring: React.FC<{ t: number; at: number; x: number; y: number; w: number; h: number }> = ({ t, at, x, y, w, h }) => {
  const g = t >= at ? clamp(1 - (t - at) / 28) : 0;
  if (g <= 0) return null;
  return <div style={{ position: "absolute", left: x - 6, top: y - 6, width: w + 12, height: h + 12, pointerEvents: "none",
    boxShadow: `0 0 0 2px rgba(255,178,63,${0.9 * g}), 0 0 46px rgba(255,178,63,${0.38 * g})` }} />;
};

/** One board shot: the intel plate at its own angle, the measured linear push-in; an optional inner hard cut closer. */
const OnBoard: React.FC<{ f: number; t: number; len: number; dir: number; zoom?: { at: number; s: number; ox: string; oy: string }; children: React.ReactNode }> = ({ f, t, len, dir, zoom, children }) => {
  const z = zoom && t >= zoom.at ? zoom : null;
  return (
    <AbsoluteFill style={{ transform: `scale(${(z ? z.s : 1) * (1 + 0.0066 * (t / 60))})`, transformOrigin: z ? `${z.ox} ${z.oy}` : "50% 48%" }}>
      <Board f={f} t={clamp(t / len)} dir={dir}>{children}</Board>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------ the shots */

/** Over the 3D plate: the asset tag; at the close, the limits and the title. */
const PlateHud: React.FC<{ t: number; end: boolean }> = ({ t, end }) => {
  const c = sh(end ? "end" : "plate").cards!;
  const corner = (l: boolean, tp: boolean): React.CSSProperties => ({ position: "absolute", width: 42, height: 42, opacity: prog(t, 4, 10),
    [l ? "left" : "right"]: 70, [tp ? "top" : "bottom"]: BAR + 30,
    borderLeft: l ? `2px solid ${MW.dim}` : undefined, borderRight: l ? undefined : `2px solid ${MW.dim}`,
    borderTop: tp ? `2px solid ${MW.dim}` : undefined, borderBottom: tp ? undefined : `2px solid ${MW.dim}` });
  return (
    <>
      <div style={corner(true, true)} /><div style={corner(false, true)} /><div style={corner(true, false)} /><div style={corner(false, false)} />
      {!end ? (
        <>
          <Card f={t} at={c[0]} x={110} y={BAR + 56} w={520} h={180} head="ASSET // REAR PLATE" accent={MW.orange}>
            <div style={{ fontFamily: "Archivo Black", fontSize: 44, color: MW.text, lineHeight: 1 }}>HEDERA</div>
            <Mono s={16} c={MW.text} style={{ marginTop: 12, lineHeight: 1.4 }}>{"BLACK BODY, WHITE LOGO\nA MAGNETIC SPONSOR SWAP PLATE"}</Mono>
          </Card>
          <Card f={t} at={c[1]} x={W - 110 - 430} y={BAR + 56} w={430} h={150} head="ANY% x HEDERA" accent={MW.blue} headCol={MW.blue}>
            <Mono s={17} c={MW.text} style={{ lineHeight: 1.5 }}>{"HCS: THE CLOCK\nx402 + HTS: THE PAY"}</Mono>
          </Card>
          <Mono s={14} c={MW.dim} ls="0.24em" style={{ position: "absolute", right: 120, top: BAR + 226, opacity: prog(t, 30, 40) }}>CAD RENDER // THE PRINT FILE'S OWN MESH</Mono>
        </>
      ) : (
        <>
          <Card f={t} at={c[0]} x={110} y={BAR + 56} w={640} h={196} head="LIMITS // SAID OUT LOUD" accent={MW.dim} headCol={MW.dim}>
            <Mono s={15} c={MW.text} style={{ lineHeight: 1.55 }}>
              {"TESTNET USDC ONLY. NOT AN ENTRY FEE, NOT A PRIZE.\nSOFTWARE PLAYING IN REAL TIME IS NOT RULED OUT.\nWHOEVER HOLDS A CONSOLE HOLDS ITS KEY."}
            </Mono>
          </Card>
          <div style={{ position: "absolute", right: 116, top: BAR + 64, textAlign: "right" }}>
            <Kicker t={t} at={40}>ETHGLOBAL MUMBAI '26</Kicker>
            <Title t={t} at={46} s={84} style={{ marginTop: 8, textShadow: "0 0 30px rgba(0,0,0,0.9)" }}>ANY% x HEDERA</Title>
          </div>
        </>
      )}
    </>
  );
};

/** What Hedera does in Any%: the three jobs, and the two tracks. */
const Brief: React.FC<{ t: number }> = ({ t }) => {
  const c = sh("brief").cards!;
  const items = [
    { k: "01 // THE CLOCK", h: "LIVE RUNS", s: "HCS: THE SEED COMES FROM\nTHE RUNNING HASH AT START\nHCS: A CHECKPOINT EVERY 2 S", ui: false },
    { k: "02 // THE PAY", h: "PAID COACHING", s: "x402: PB, THE COACH AGENT,\nPAYS THE RUNNER JUST AHEAD\nIN USDC. NO HUMAN APPROVES", ui: true },
    { k: "03 // NO SOLIDITY", h: "SDK ONLY", s: "TWO NATIVE SERVICES:\nHCS + HTS\nNO CONTRACTS AT ALL", ui: false },
  ];
  return (
    <>
      <div style={{ position: "absolute", left: 150, top: BAR + 66 }}>
        <Kicker t={t}>ANY% x HEDERA // ETHGLOBAL MUMBAI '26</Kicker>
        <Title t={t} style={{ marginTop: 12 }}>WHAT HEDERA DOES IN ANY%</Title>
      </div>
      {items.map((it, i) => (
        <Card key={it.k} f={t} at={c[i]} x={150 + i * 560} y={BAR + 236} w={520} h={340} head={it.k} accent={MW.amber} headCol={MW.amber}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 44, color: MW.text, lineHeight: 1 }}>{it.h}</div>
          <Mono s={19} c={MW.text} style={{ marginTop: 18, lineHeight: 1.4 }}>{it.s}</Mono>
          <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", gap: 14, alignItems: "center" }}>
            {it.ui ? <Mono s={15} c={MW.green} w={700} ls="0.16em">UI: BUILT</Mono> : null}
            <Pill t={t} at={c[i] + 14} s={15} />
          </div>
        </Card>
      ))}
      <Mono s={15} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: 150, top: BAR + 600, opacity: prog(t, 50, 60) }}>
        {"TRACKS // AI AGENTS THAT PAY: x402 ON HEDERA // NO SOLIDITY ALLOWED"}
      </Mono>
    </>
  );
};

/** START goes to HCS, consensus orders it, and its running hash becomes the seed. */
const Start: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("start"), c = s.cards!, [hit, seed] = s.chirps!;
  const Y = BAR + 236, CH = 300, CW = 480, X = [150, 720, 1290];
  return (
    <>
      <div style={{ position: "absolute", left: 150, top: BAR + 66 }}>
        <Kicker t={t}>01 // THE CLOCK // HEDERA CONSENSUS SERVICE</Kicker>
        <Title t={t} style={{ marginTop: 12 }}>THE SEED ARRIVES WITH START</Title>
      </div>
      <Card f={t} at={c[0]} x={X[0]} y={Y} w={CW} h={CH} head="THE CONSOLE" accent={MW.blue} headCol={MW.blue}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 46, color: MW.text, lineHeight: 1 }}>START</div>
        <Mono s={18} c={MW.text} style={{ marginTop: 18, lineHeight: 1.45 }}>{"THE RUN'S FIRST MESSAGE\nSIGNED WITH THE CONSOLE'S KEY\nIT CARRIES THE RUN_ID"}</Mono>
      </Card>
      <Card f={t} at={c[1]} x={X[1]} y={Y} w={CW} h={CH} head="HCS // CONSENSUS" accent={MW.amber} headCol={MW.amber}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 46, color: MW.text, lineHeight: 1 }}>ORDERED</div>
        <Mono s={18} c={MW.text} style={{ marginTop: 18, lineHeight: 1.45 }}>{"TIMESTAMPED BY THE NETWORK\nAND FOLDED INTO THE TOPIC'S\nRUNNING HASH"}</Mono>
      </Card>
      <Card f={t} at={c[2]} x={X[2]} y={Y} w={CW} h={CH} head="THE RUN'S SEED" accent={MW.amber} headCol={MW.amber}>
        <Mono s={22} c={MW.text} w={700} style={{ lineHeight: 1.4 }}>{"SHA-256(\n  START'S RUNNING HASH\n  || RUN_ID )"}</Mono>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 6, borderTop: `1px solid ${MW.faint}`, paddingTop: 12 }}>
          {t < seed ? <Mono s={17} c={MW.dim} w={700} ls="0.14em" style={{ opacity: t % 30 < 20 ? 1 : 0.4 }}>UNKNOWN UNTIL CONSENSUS</Mono>
            : <Mono s={17} c={DONE ? MW.green : MW.amber} w={700} ls="0.14em">{DONE ? "SET AT CONSENSUS" : "SET AT CONSENSUS // AT THE EVENT"}</Mono>}
        </div>
      </Card>
      <Ring t={t} at={hit} x={X[1]} y={Y} w={CW} h={CH} />
      <Ring t={t} at={seed} x={X[2]} y={Y} w={CW} h={CH} />
      <Arrow t={t} at={44} x0={X[0] + CW + 8} x1={X[1] - 10} y={Y + CH / 2} />
      <Packet t={t} a={60} b={hit} x0={X[0] + CW + 8} x1={X[1] - 12} y={Y + CH / 2} col={MW.blue} />
      <Arrow t={t} at={110} x0={X[1] + CW + 8} x1={X[2] - 10} y={Y + CH / 2} />
      <Packet t={t} a={122} b={seed} x0={X[1] + CW + 8} x1={X[2] - 12} y={Y + CH / 2} />
      <div style={{ position: "absolute", left: 150, top: BAR + 566 }}><Pill t={t} at={40} /></div>
    </>
  );
};

/** Who can know the seed, and when: today the console makes it (real), at Mumbai Hedera does. */
const Seed: React.FC<{ t: number }> = ({ t }) => {
  const c = sh("seed").cards!, [arrow] = sh("seed").chirps!;
  const Y = BAR + 236, CH = 310;
  return (
    <>
      <div style={{ position: "absolute", left: 150, top: BAR + 66 }}>
        <Kicker t={t}>01 // THE CLOCK // THE SEED</Kicker>
        <Title t={t} style={{ marginTop: 12 }}>WHO CAN KNOW IT, AND WHEN</Title>
      </div>
      <Card f={t} at={c[0]} x={150} y={Y} w={740} h={CH} head="TODAY // MADE ON THE CONSOLE" accent={MW.green} headCol={MW.green}>
        <Mono s={17} c={MW.dim} ls="0.14em">THE SEEDED RUSH HOUR LOG'S HEADER</Mono>
        <Mono s={86} c={MW.green} w={700} ls="0.08em" style={{ marginTop: 10 }}>{SEED}</Mono>
        <Mono s={19} c={MW.text} style={{ marginTop: 16, lineHeight: 1.4 }}>{"THE CONSOLE KNOWS ITS SEED\nBEFORE THE RUN STARTS"}</Mono>
        <div style={{ position: "absolute", right: 0, top: 0 }}><Mono s={14} c={MW.green} w={700} ls="0.16em">BUILT</Mono></div>
      </Card>
      <Arrow t={t} at={arrow - 12} x0={904} x1={1016} y={Y + CH / 2} col={MW.amber} />
      <Card f={t} at={c[1]} x={1030} y={Y} w={740} h={CH} head="AT MUMBAI // FROM HEDERA" accent={MW.amber} headCol={MW.amber}>
        <Mono s={17} c={MW.dim} ls="0.14em">THE RUNNING HASH OF ITS OWN START</Mono>
        <div style={{ fontFamily: "Archivo Black", fontSize: 40, color: MW.text, lineHeight: 1.1, marginTop: 12, whiteSpace: "pre" }}>{"NOBODY, INCLUDING\nTHE CONSOLE, KNOWS IT"}</div>
        <Mono s={19} c={MW.text} style={{ marginTop: 14, lineHeight: 1.4 }}>{"BEFORE START REACHES CONSENSUS.\nEVERY REROLL IS PUBLIC, AND COUNTED."}</Mono>
        <Status />
      </Card>
    </>
  );
};

/** The run on the console in real time, its checkpoints landing on the console's HCS topic every 2 s of play. */
const PLAY0 = 600;                                                // public/game/RUSH: route frames 600-959 of the RUSH run
const Topic: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("topic"), c = s.cards!, land = s.chirps!;
  const play = (PLAY0 + t) / 60;
  const MX = 110, MY = BAR + 86, MWd = 780, MH = 520;
  const rows = [
    { k: "START", mid: "RUN_ID // SIGNED // THE SEED IS SET HERE", due: "T = 0", at: c[1], fresh: -1 },
    ...[1, 2, 3, 4, 5, 6].map((n, i) => ({
      k: `CP ${String(n).padStart(2, "0")}`, mid: `${secs(2 * n - 2)}-${secs(2 * n)} // SALTED INPUT HASH`,
      due: `+${(15 + 1.03 * 2 * n).toFixed(2)} S`, at: i < 4 ? c[2 + i] : land[i - 4], fresh: i < 4 ? -1 : land[i - 4],
    })),
  ];
  const RX = 960, RW = 850, RH = 62, RG = 8;
  return (
    <>
      <Kicker t={t} style={{ position: "absolute", left: MX, top: BAR + 40 }}>THE RUN // RUSH HOUR // REAL FOOTAGE, REAL TIME</Kicker>
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MWd + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8)", opacity: prog(t, c[0], c[0] + 4) }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MWd, height: MH, overflow: "hidden", background: "#000",
        transform: `scaleY(${lerp(0.02, 1, easeInOut(prog(t, c[0], c[0] + 10)))})` }}>
        <Img src={staticFile(`game/RUSH/${String(clamp(t, 0, 359)).padStart(4, "0")}.png`)} style={{ width: "100%", height: "100%", imageRendering: "pixelated" }} />
      </div>
      <div style={{ position: "absolute", left: MX, top: MY + MH + 22, display: "flex", gap: 26, alignItems: "baseline", opacity: prog(t, 14, 20) }}>
        <Mono s={15} c={MW.dim} ls="0.2em">LOG TIME</Mono>
        <Mono s={34} c={MW.amber} w={700}>{secs(play)}</Mono>
        <Mono s={15} c={MW.dim} ls="0.14em">A CHECKPOINT EVERY 2 S OF THE LOG</Mono>
      </div>
      <Kicker t={t} at={6} style={{ position: "absolute", left: RX, top: BAR + 40 }}>HCS TOPIC // THIS CONSOLE'S RUN</Kicker>
      <Mono s={13} c={MW.dim} ls="0.16em" style={{ position: "absolute", left: RX + 22, top: MY - 6, opacity: prog(t, 10, 16) }}>{"MESSAGE   COVERS (LOG TIME) // CONTENT"}</Mono>
      <Mono s={13} c={MW.dim} ls="0.16em" style={{ position: "absolute", left: RX, width: RW - 22, textAlign: "right", top: MY - 6, opacity: prog(t, 10, 16) }}>LANDS BY (AFTER THE SEED)</Mono>
      {rows.map((r, i) => {
        const hot = r.fresh >= 0 && t >= r.fresh && t < r.fresh + 40;
        return (
          <Card key={r.k} f={t} at={r.at} x={RX} y={MY + 20 + i * (RH + RG)} w={RW} h={RH} accent={hot ? MW.amber : r.k === "START" ? MW.blue : MW.faint}>
            <div style={{ position: "absolute", left: 0, top: -6, display: "flex", gap: 22, alignItems: "baseline" }}>
              <div style={{ fontFamily: "Archivo Black", fontSize: 22, color: hot ? MW.amber : MW.text, width: 92 }}>{r.k}</div>
              <Mono s={15} c={MW.text}>{r.mid}</Mono>
            </div>
            <Mono s={15} c={MW.amber} w={700} style={{ position: "absolute", right: 0, top: -4 }}>{r.due}</Mono>
          </Card>
        );
      })}
      <Mono s={14} c={MW.dim} ls="0.12em" style={{ position: "absolute", left: RX, top: MY + 20 + 7 * (RH + RG) + 4, lineHeight: 1.5, opacity: prog(t, 60, 70) }}>
        {"RAW INPUTS NEVER GO ON HCS. THE CONSOLE SIGNS EVERY MESSAGE.\nLANDS BY = 15 S + 1.03 x LOG TIME: THE ENVELOPE."}
      </Mono>
      <div style={{ position: "absolute", right: 110, top: BAR + 30 }}><Pill t={t} at={50} s={15} /></div>
    </>
  );
};

/** The envelope: commits must land by 15 s + 1.03 x play time after the seed. Live play stays inside; half speed leaves
    it after 15.5 s of play (15 + 1.03 x = 2 x). The design's own arithmetic, no measured data. */
const Envelope: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("envelope"), c = s.cards!, [env] = s.chirps!, [out] = s.hits!;
  const CX = 110, CY = BAR + 52, CWd = 1130, CHt = 640;
  const PW = CWd - 44, PH = CHt - 70;                              // the svg, inside the card's body
  const L = 96, R = PW - 40, TOP = 24, BOT = PH - 66;
  const px = (x: number) => L + (x / 90) * (R - L), py = (y: number) => BOT - (y / 120) * (BOT - TOP);
  const pe = prog(t, env - 40, env), pl = prog(t, 50, 150), ph = prog(t, out - 56, out);
  const xo = 15 / (2 - 1.03);                                      // half speed meets the envelope: 15.46 s of play
  const live = Array.from({ length: 46 }, (_, i) => i * 2).filter((x) => x <= 90 * pl);
  const tx = (x: number, y: number, txt: string, o: { col?: string; size?: number; anchor?: "start" | "middle" | "end"; bold?: boolean; rot?: number } = {}) => (
    <text x={x} y={y} fill={o.col ?? MW.dim} fontFamily="Space Mono" fontWeight={o.bold ? 700 : 400} fontSize={o.size ?? 14} textAnchor={o.anchor ?? "middle"}
      letterSpacing="0.06em" transform={o.rot ? `rotate(${o.rot} ${x} ${y})` : undefined}>{txt}</text>
  );
  const slope = (Math.atan2(py(1.03) - py(0), px(1) - px(0)) * 180) / Math.PI;
  const dash = 18 * prog(t, out, out + 30);
  return (
    <>
      <Card f={t} at={c[0]} x={CX} y={CY} w={CWd} h={CHt} head="HCS // THE ENVELOPE, ON A 90 S RUN" accent={MW.amber} headCol={MW.amber}>
        <svg width={PW} height={PH} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
          {[0, 30, 60, 90, 120].map((y) => <line key={`h${y}`} x1={L} x2={R} y1={py(y)} y2={py(y)} stroke="rgba(124,196,255,0.12)" />)}
          {[0, 15, 30, 45, 60, 75, 90].map((x) => <line key={`v${x}`} x1={px(x)} x2={px(x)} y1={TOP} y2={BOT} stroke="rgba(124,196,255,0.08)" />)}
          <line x1={L} x2={R} y1={BOT} y2={BOT} stroke={MW.dim} />
          <line x1={L} x2={L} y1={TOP} y2={BOT} stroke={MW.dim} />
          {[0, 15, 30, 45, 60, 75, 90].map((x) => <React.Fragment key={`x${x}`}>{tx(px(x), BOT + 24, `${x}`)}</React.Fragment>)}
          {[0, 30, 60, 90, 120].map((y) => <React.Fragment key={`y${y}`}>{tx(L - 14, py(y) + 5, `${y}`, { anchor: "end" })}</React.Fragment>)}
          {tx((L + R) / 2, BOT + 54, "PLAY TIME (S)")}
          {tx(L - 66, (TOP + BOT) / 2, "WALL CLOCK SINCE THE SEED (S)", { rot: -90 })}
          <polygon points={`${px(0)},${py(15)} ${px(90)},${py(107.7)} ${px(90)},${py(120)} ${px(0)},${py(120)}`} fill={MW.red}
            opacity={0.1 * pe + (t >= out ? 0.06 * (0.5 + 0.5 * Math.sin(t * 0.25)) : 0)} />
          <line x1={px(0)} y1={py(15)} x2={px(90 * pe)} y2={py(15 + 1.03 * 90 * pe)} stroke={MW.amber} strokeWidth={3} />
          {pe >= 1 ? tx(px(52), py(15 + 1.03 * 52) - 14, "ENVELOPE: 15 S + 1.03 x PLAY", { col: MW.amber, size: 17, bold: true, rot: slope }) : null}
          {pe >= 1 ? tx(px(10), py(110), "OUTSIDE: NOT A LIVE RUN", { col: MW.red, size: 17, bold: true, anchor: "start" }) : null}
          {pl > 0 ? <line x1={px(0)} y1={py(0)} x2={px(90 * pl)} y2={py(90 * pl)} stroke={MW.green} strokeWidth={2.5} /> : null}
          {live.map((x) => <circle key={`c${x}`} cx={px(x)} cy={py(x)} r={3.6} fill={MW.green} />)}
          {pl >= 1 ? tx(px(60), py(60) + 30, "LIVE: REAL TIME, INSIDE", { col: MW.green, size: 17, bold: true, anchor: "start", rot: (Math.atan2(py(1) - py(0), px(1) - px(0)) * 180) / Math.PI }) : null}
          {ph > 0 ? <line x1={px(0)} y1={py(0)} x2={px(xo * ph)} y2={py(2 * xo * ph)} stroke={MW.red} strokeWidth={3} /> : null}
          {t >= out ? <line x1={px(xo)} y1={py(2 * xo)} x2={px(xo + dash * 0.6)} y2={py(2 * (xo + dash * 0.6))} stroke={MW.red} strokeWidth={2} strokeDasharray="6 7" opacity={0.6} /> : null}
          {t >= out ? (
            <g transform={`translate(${px(xo)} ${py(2 * xo)}) scale(${lerp(1.8, 1, easeOutExpo(prog(t, out, out + 8)))})`}>
              <line x1={-13} y1={-13} x2={13} y2={13} stroke={MW.red} strokeWidth={4} />
              <line x1={-13} y1={13} x2={13} y2={-13} stroke={MW.red} strokeWidth={4} />
            </g>
          ) : null}
          {t >= out + 6 ? (
            <g opacity={prog(t, out + 6, out + 12)}>
              <line x1={px(xo) + 10} y1={py(2 * xo) + 14} x2={px(27)} y2={py(9) - 6} stroke={MW.red} strokeWidth={1.5} opacity={0.7} />
              {tx(px(27) + 6, py(9) + 12, "HALF SPEED: OUT AFTER 15.5 S OF PLAY", { col: MW.red, size: 17, bold: true, anchor: "start" })}
            </g>
          ) : null}
          {t >= 150 ? (
            <g opacity={prog(t, 150, 160)}>
              <line x1={px(90) + 14} x2={px(90) + 14} y1={py(90)} y2={py(107.7)} stroke={MW.amber} strokeWidth={2} />
              <line x1={px(90) + 8} x2={px(90) + 20} y1={py(90)} y2={py(90)} stroke={MW.amber} strokeWidth={2} />
              <line x1={px(90) + 8} x2={px(90) + 20} y1={py(107.7)} y2={py(107.7)} stroke={MW.amber} strokeWidth={2} />
              {tx(px(90) - 4, py(107.7) - 18, "ABOUT 18 S OF SLACK AT 90 S", { col: MW.amber, size: 16, bold: true, anchor: "end" })}
            </g>
          ) : null}
        </svg>
      </Card>
      <Card f={t} at={c[1]} x={1280} y={CY} w={530} h={440} head="THE RULE // CHECKED FROM HCS" accent={MW.amber} headCol={MW.amber}>
        <Mono s={18} c={MW.text} style={{ lineHeight: 1.45 }}>
          {"THE CLOCK STARTS WHEN\nTHE SEED BECOMES KNOWABLE\n\nEVERY FRAME'S CHECKPOINT\nLANDS BY 15 S + 1.03 x ITS TIME\n\nMISS IT: NOT A LIVE RUN"}
        </Mono>
        <div style={{ position: "absolute", left: 0, bottom: 4 }}><Pill t={t} at={c[1] + 16} s={15} /></div>
      </Card>
      <Mono s={15} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: 1282, top: CY + 464, lineHeight: 1.5, opacity: prog(t, 90, 100) }}>
        {"NOT RULED OUT: SOFTWARE THAT\nPLAYS IN REAL TIME, OR FASTER."}
      </Mono>
    </>
  );
};

/** common.tsx's Stamp on one line (the shared one wraps past half the frame's width). */
const LineStamp: React.FC<{ t: number; at: number; text: string; col: string; s: number; y: number }> = ({ t, at, text, col, s, y }) => {
  if (t < at) return null;
  const k = prog(t, at, at + 9);
  const sc = lerp(1.6, 1, 1 - Math.pow(1 - k, 3));
  return (
    <div style={{ position: "absolute", left: W / 2, top: y, transform: `translate(-50%, -50%) scale(${sc}) rotate(-2deg)`, opacity: clamp(k * 3), whiteSpace: "nowrap" }}>
      <div style={{ fontFamily: "Archivo Black", fontSize: s, letterSpacing: "0.06em", color: col, padding: "6px 40px", border: `8px solid ${col}`,
        textShadow: `0 0 40px ${col}88`, boxShadow: `0 0 60px ${col}44, inset 0 0 40px ${col}33`, background: "rgba(0,0,0,0.7)", lineHeight: 1.05 }}>{text}</div>
    </div>
  );
};

/** The film's SLOWED art, and what the envelope does to it. */
const Slowed: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("slowed"), c = s.cards!, [hit] = s.hits!;
  const AW = 1458, AH = 640, AX = (W - AW) / 2, AY = BAR + 56;
  return (
    <>
      <Kicker t={t} style={{ position: "absolute", left: AX, top: BAR + 14 }}>FROM THE FILM // HOW RECORDS BREAK // SLOWED</Kicker>
      <div style={{ position: "absolute", left: AX - 10, top: AY - 10, width: AW + 20, height: AH + 20, background: "#0d0f11", border: "1px solid #2a2d31", opacity: prog(t, c[0], c[0] + 4) }} />
      <div style={{ position: "absolute", left: AX, top: AY, width: AW, height: AH, overflow: "hidden", transform: `scaleY(${lerp(0.02, 1, easeInOut(prog(t, c[0], c[0] + 10)))})` }}>
        <Img src={staticFile("breaks_tri_3.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover", filter: t >= hit ? "saturate(0.6) brightness(0.7)" : undefined }} />
      </div>
      <LineStamp t={t} at={hit} text="OUTSIDE THE ENVELOPE" col={MW.red} s={66} y={AY + 262} />
    </>
  );
};

/** The console's screen, the real launcher paying the runner ahead (MOCK pill on), and what PB does. */
const MASK = { x: 94, y: 5, w: 88, h: 31 };                       // the launcher's World chip (800 x 480): World is out
const Pay: React.FC<{ t: number }> = ({ t }) => {
  const c = sh("pay").cards!;
  const MX = 90, MY = BAR + 74, MWd = 1065, MH = 639, CX = MX + MWd + 50, CW = W - CX - 70;
  const k = MWd / 800;
  const img = clamp(Math.floor((t - 10) / 4), 0, S.images.buy_pay - 1);  // real time: the launcher's 30 fps, one image per 4 frames
  return (
    <>
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MWd + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MWd, height: MH, overflow: "hidden", background: "#000",
        transform: `scaleY(${lerp(0.02, 1, easeInOut(prog(t, 0, 10)))})` }}>
        <Img src={staticFile(`handler/buy_pay/${String(img).padStart(2, "0")}.jpg`)} style={{ width: "100%", height: "100%" }} />
        <div style={{ position: "absolute", left: MASK.x * k, top: MASK.y * k, width: MASK.w * k, height: MASK.h * k, background: "rgb(12,13,18)" }} />
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: t >= 10 ? clamp(1 - (t - 10) / 4) * 0.35 : 0 }} />
      </div>
      <Mono s={15} c={MW.text} w={700} ls="0.28em" style={{ position: "absolute", left: MX, top: MY - 46, opacity: prog(t, 6, 12) }}>
        {"THE CONSOLE'S SCREEN // DRAWN BY THE LAUNCHER // MOCK SPONSORS"}
      </Mono>
      <Kicker t={t} at={8} style={{ position: "absolute", left: CX, top: MY - 6 }}>02 // THE PAY // x402</Kicker>
      <Card f={t} at={c[0]} x={CX} y={MY + 36} w={CW} h={190} head="THE RUNNER JUST AHEAD" accent={MW.blue} headCol={MW.blue}>
        <Row k="RIA" v={RIA} s={22} c={MW.text} />
        <Row k="YOU" v={YOU} s={22} c={MW.dim} />
        <Mono s={13} c={MW.dim} ls="0.1em" style={{ marginTop: 4 }}>MARINE DRIVE GP // BOTH LOGS REPLAYED</Mono>
      </Card>
      <Card f={t} at={c[1]} x={CX} y={MY + 240} w={CW} h={250} head="PB // THE COACH AGENT" accent={MW.amber} headCol={MW.amber}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 30, color: MW.text, lineHeight: 1 }}>BUYS HER GHOST</div>
        <Mono s={16} c={MW.text} style={{ marginTop: 14, lineHeight: 1.5 }}>{"PAYS OVER x402, USDC ON HEDERA\nSTRAIGHT TO HER ACCOUNT\nNO HUMAN APPROVES: UNDER YOUR CAPS"}</Mono>
        <div style={{ position: "absolute", left: 0, bottom: 2, display: "flex", gap: 18 }}>
          <Mono s={14} c={MW.green} w={700} ls="0.16em">UI: BUILT</Mono>
          <Mono s={14} c={DONE ? MW.green : MW.amber} w={700} ls="0.16em">{CALL}</Mono>
        </div>
      </Card>
      <Mono s={14} c={MW.dim} ls="0.12em" style={{ position: "absolute", left: CX, top: MY + 510, lineHeight: 1.5, opacity: prog(t, 60, 70) }}>
        {"ON SCREEN: THE REAL LAUNCHER OVER MOCK\nSPONSORS. RIA'S LOG AND YOURS ARE REAL;\nHER NAME, THE PRICE AND THE CALL: MOCK."}
      </Mono>
    </>
  );
};

/** Where the money goes: from PB, over x402, settled on Hedera, to the runner's own account. */
const Route: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("pay2"), c = s.cards!, [arrive] = s.chirps!;
  const Y = BAR + 236, NW = 370, NH = 270, GAP = 80, X0 = (W - (4 * NW + 3 * GAP)) / 2;
  const xs = [0, 1, 2, 3].map((i) => X0 + i * (NW + GAP));
  const nodes = [
    { k: "01 // YOUR COACH AGENT", h: "PB", s: "ON YOUR CONSOLE\nPICKS THE RUNNER\nJUST AHEAD", col: MW.blue },
    { k: "02 // THE GHOST'S PRICE", h: "x402", s: "HER GHOST SITS\nBEHIND x402\nPAYTO = HER ACCOUNT", col: MW.amber },
    { k: "03 // SETTLED", h: "HEDERA", s: "USDC, AN HTS TOKEN\nON HEDERA TESTNET\nPAID BY PB", col: MW.amber },
    { k: "04 // THE RUNNER AHEAD", h: "RIA", s: `HER OWN ACCOUNT\n${RIA} ON THE BOARD\nPAID DIRECTLY`, col: MW.amber },
  ];
  return (
    <>
      <div style={{ position: "absolute", left: X0, top: BAR + 66 }}>
        <Kicker t={t}>02 // THE PAY // x402 ON HEDERA</Kicker>
        <Title t={t} style={{ marginTop: 12 }}>STRAIGHT TO THE RUNNER AHEAD</Title>
      </div>
      {nodes.map((n, i) => (
        <Card key={n.k} f={t} at={c[i]} x={xs[i]} y={Y} w={NW} h={NH} head={n.k} accent={n.col} headCol={n.col}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 50, color: MW.text, lineHeight: 1 }}>{n.h}</div>
          <Mono s={17} c={MW.text} style={{ marginTop: 18, lineHeight: 1.45 }}>{n.s}</Mono>
        </Card>
      ))}
      {[0, 1, 2].map((i) => <Arrow key={i} t={t} at={56 + i * 24} x0={xs[i] + NW + 8} x1={xs[i + 1] - 10} y={Y + NH / 2} />)}
      <Packet t={t} coin a={110} b={arrive} x0={xs[0] + NW / 2} x1={xs[3] + NW / 2} y={Y + NH + 34} />
      <Ring t={t} at={arrive} x={xs[3]} y={Y} w={NW} h={NH} />
      <Mono s={16} c={MW.text} ls="0.08em" style={{ position: "absolute", left: X0, top: Y + NH + 74, lineHeight: 1.5, opacity: prog(t, 70, 80) }}>
        {"NO ESCROW, NO SPLIT: ONE PAYMENT, ONE PERSON.\nPAYTO COMES FROM HER VERIFIED LISTING, NEVER FROM THE 402 RESPONSE."}
      </Mono>
      <div style={{ position: "absolute", right: X0, top: Y + NH + 74 }}><Pill t={t} at={60} /></div>
    </>
  );
};

/** x402 as a ladder between PB, the ghost's server and Hedera: no human anywhere in it. */
const Ladder: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("x402"), c = s.cards!;
  const LX = [330, 960, 1590], top = BAR + 74;
  const heads = [
    { k: "PB // COACH AGENT", h: "YOUR CONSOLE", col: MW.blue },
    { k: "THE GHOST // x402", h: "HER GHOST'S SERVER", col: MW.amber },
    { k: "HEDERA // TESTNET", h: "SETTLEMENT", col: MW.amber },
  ];
  const GY = 470, GH = 100;                                         // the guards, on PB's side, between the 402 and the payment
  const steps = [
    { from: 0, to: 1, y: 360, txt: "GET HER GHOST" },
    { from: 1, to: 0, y: 436, txt: "402: PAYMENT REQUIRED (USDC, PAYTO, PRICE)" },
    { from: 0, to: 1, y: 616, txt: "PAYMENT, SIGNED BY PB" },
    { from: 1, to: 2, y: 692, txt: "SETTLE: USDC TO HER ACCOUNT" },
    { from: 1, to: 0, y: 768, txt: "200 + THE GHOST" },
  ];
  const at = (i: number) => (i < 2 ? 50 + i * 30 : 80 + i * 30);  // 50, 80, then the guards (110), then 140, 170, 200
  const lifeTop = top + 112, lifeBot = 792;
  return (
    <>
      <Kicker t={t} style={{ position: "absolute", left: 110, top: BAR + 26 }}>02 // THE PAY // HOW PB PAYS, OVER x402</Kicker>
      {heads.map((h, i) => (
        <React.Fragment key={h.k}>
          <Card f={t} at={c[i]} x={LX[i] - 210} y={top} w={420} h={104} head={h.k} accent={h.col} headCol={h.col}>
            <div style={{ fontFamily: "Archivo Black", fontSize: 28, color: MW.text, lineHeight: 1 }}>{h.h}</div>
          </Card>
          <div style={{ position: "absolute", left: LX[i] - 1, top: lifeTop, width: 0, height: (lifeBot - lifeTop) * prog(t, c[i] + 6, c[i] + 26),
            borderLeft: `2px dashed ${MW.faint}` }} />
        </React.Fragment>
      ))}
      {steps.map((st, i) => {
        const fwd = st.to > st.from;
        const x0 = LX[st.from] + (fwd ? 8 : -8), x1 = LX[st.to] + (fwd ? -10 : 10);
        const col = i === 4 ? MW.green : MW.text;
        return (
          <React.Fragment key={i}>
            <Arrow t={t} at={at(i)} x0={x0} x1={x1} y={st.y} col={col} dur={10} />
            {t >= at(i) ? <Mono s={15} c={col} w={700} ls="0.1em" style={{ position: "absolute", left: Math.min(x0, x1), width: Math.abs(x1 - x0),
              textAlign: "center", top: st.y - 30, opacity: prog(t, at(i) + 4, at(i) + 10) }}>{st.txt}</Mono> : null}
          </React.Fragment>
        );
      })}
      <Card f={t} at={c[3]} x={LX[0] - 220} y={GY} w={560} h={GH} head="GUARDS // OUTSIDE THE MODEL" accent={MW.amber} headCol={MW.amber}>
        <Mono s={15} c={MW.text} style={{ lineHeight: 1.45 }}>{"DAILY CAP, PER-RUNNER CAP. PAYTO AND PRICE\nMUST MATCH HER LISTING."}</Mono>
      </Card>
      <Mono s={15} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: 1010, top: GY + 6, lineHeight: 1.5, opacity: prog(t, c[3] + 10, c[3] + 20) }}>
        {"THE MODEL SEES NUMBERS ONLY. PB POSTS ITS\nINTENT TO HCS BEFORE IT PAYS, ITS RECEIPT AFTER."}
      </Mono>
      <div style={{ position: "absolute", left: 1010, top: GY + 64 }}><Pill t={t} at={30} s={15} /></div>
    </>
  );
};

/** No Solidity: the two native services, and what each one carries. */
const Native: React.FC<{ t: number }> = ({ t }) => {
  const c = sh("native").cards!, zoomed = t >= sh("native").glitch![0];
  const Y = BAR + 196, CHt = 410, CWd = 790;
  const cards = [
    { k: "HEDERA CONSENSUS SERVICE", h: "HCS", job: "THE CLOCK AND THE RECEIPTS",
      rows: [["START", "THE SEED'S SOURCE"], ["CHECKPOINTS", "EVERY 2 S, AND END"], ["PB", "INTENT, THEN RECEIPT"], ["REGISTRY", "EACH CONSOLE'S KEY"]] },
    { k: "HEDERA TOKEN SERVICE", h: "HTS", job: "THE MONEY",
      rows: [["USDC", "TESTNET TOKEN 0.0.429274"], ["PAID TO", "THE RUNNER'S OWN ACCOUNT"], ["BEFORE", "EVERY RUNNER ASSOCIATED"], ["NO", "CONTRACT, ESCROW OR SPLIT"]] },
  ];
  return (
    <>
      <div style={{ position: "absolute", left: 150, top: BAR + 52 }}>
        <Kicker t={t} style={{ visibility: zoomed ? "hidden" : "visible" }}>03 // NO SOLIDITY ALLOWED</Kicker>
        <Title t={t} style={{ marginTop: 12 }}>HEDERA SDK ONLY. NO CONTRACTS.</Title>
      </div>
      {cards.map((cd, i) => (
        <Card key={cd.h} f={t} at={c[i]} x={150 + i * 830} y={Y} w={CWd} h={CHt} head={cd.k} accent={MW.amber} headCol={MW.amber}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
            <div style={{ fontFamily: "Archivo Black", fontSize: 96, color: MW.text, lineHeight: 1 }}>{cd.h}</div>
            <Mono s={18} c={MW.amber} w={700} ls="0.16em">{cd.job}</Mono>
          </div>
          <div style={{ marginTop: 26 }}>{cd.rows.map(([a, b]) => <Row key={a} k={a} v={b} s={20} />)}</div>
          <div style={{ position: "absolute", left: 0, bottom: 4 }}><Pill t={t} at={c[i] + 20} s={15} /></div>
        </Card>
      ))}
      <Mono s={15} c={MW.dim} ls="0.14em" style={{ position: "absolute", left: 150, top: Y + CHt + 18, opacity: zoomed ? 0 : prog(t, 60, 70) }}>
        {"THE CONSOLE'S SIDE: A NODE SIDECAR ON THE OFFICIAL HEDERA SDK (@hiero-ledger/sdk)"}
      </Mono>
    </>
  );
};

/** The HashScan beat: a field-report slot until the event. */
const HashSlot: React.FC<{ t: number }> = ({ t }) => {
  const c = sh("hashscan").cards!;
  const MX = 90, MY = BAR + 74, MWd = 1136, MH = 639, CX = MX + MWd + 60, CW = W - CX - 70;
  return (
    <>
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MWd + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8)" }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MWd, height: MH, overflow: "hidden", transform: `scaleY(${lerp(0.02, 1, easeInOut(prog(t, 0, 8)))})`,
        background: "repeating-linear-gradient(135deg, #0a0b0d 0px, #0a0b0d 22px, #0e1013 22px, #0e1013 44px)" }}>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 22 }}>
          <Mono s={17} c={MW.dim} w={700} ls="0.4em">FIELD REPORT SLOT</Mono>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div style={{ width: 22, height: 22, background: MW.amber, opacity: t % 40 < 26 ? 1 : 0.25 }} />
            <div style={{ fontFamily: "Archivo Black", fontSize: 92, color: MW.amber, letterSpacing: "0.04em", lineHeight: 1 }}>AT THE EVENT</div>
          </div>
          <Mono s={19} c={MW.text} ls="0.12em" style={{ textAlign: "center", lineHeight: 1.5 }}>{"THE PAYMENT ON HASHSCAN, HEDERA TESTNET\nA REAL SCREEN CAPTURE, FILMED AT ETHGLOBAL MUMBAI"}</Mono>
        </div>
      </div>
      <div style={{ position: "absolute", left: MX, top: MY - 46, display: "flex", alignItems: "center", gap: 12, opacity: prog(t, 6, 12) }}>
        <div style={{ width: 12, height: 12, borderRadius: "50%", background: MW.dim }} />
        <Mono s={15} c={MW.text} w={700} ls="0.28em">HASHSCAN // NOT YET FILMED</Mono>
      </div>
      <Kicker t={t} at={20} style={{ position: "absolute", left: CX, top: MY - 6 }}>04 // THE RECEIPT</Kicker>
      <Card f={t} at={c[0]} x={CX} y={MY + 36} w={CW} h={330} head="IT WILL SHOW" accent={MW.amber} headCol={MW.amber}>
        <Mono s={16} c={MW.text} style={{ lineHeight: 1.5 }}>
          {"THE TOKEN TRANSFER:\nUSDC, PB TO THE RUNNER\n\nTHE PAYER ROW:\nTHE x402 FACILITATOR\n\nON HCS: PB'S INTENT AND\nRECEIPT; START, CHECKPOINTS,\nEND"}
        </Mono>
      </Card>
      <Mono s={14} c={MW.dim} ls="0.12em" style={{ position: "absolute", left: CX, top: MY + 390, lineHeight: 1.5, opacity: prog(t, c[1], c[1] + 10) }}>
        {"NO ID IN THIS FILM IS MADE UP:\nTHE REAL ONES ARRIVE WITH\nTHE CAPTURE."}
      </Mono>
    </>
  );
};

/** One field-report clip (Objectives.tsx's FieldClip, for Hedera): the real screen recording, what it shows, its values. */
const FieldClip: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const c = CLIPS[i];
  const MX = 90, MY = BAR + 74, MWd = 1136, MH = 639, CX = MX + MWd + 60;
  return (
    <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (t / 60)})`, transformOrigin: "50% 48%" }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 40% 45%, #15181b 0%, #0a0c0e 60%, #040506 100%)" }} />
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MWd + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MWd, height: MH, overflow: "hidden", transform: `scaleY(${lerp(0.02, 1, easeInOut(prog(t, 0, 8)))})` }}>
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

/** One Live run through Hedera, each step marked built (now) or at the event. */
const LoopShot: React.FC<{ t: number }> = ({ t }) => {
  const s = sh("loop"), c = s.cards!, [arcAt] = s.chirps!;
  const nodes = [
    { k: "01 // HCS", h: "START", s: "THE SEED, FROM\nTHE RUNNING HASH", st: DONE ? "BUILT" : "AT THE EVENT", ok: DONE },
    { k: "02 // HCS", h: "PLAY", s: "A CHECKPOINT\nEVERY 2 S", st: DONE ? "BUILT" : "AT THE EVENT", ok: DONE },
    { k: "03 // CONSOLE", h: "VERIFIED", s: "REPLAYED TO\nTHE SAME HASH", st: "BUILT", ok: true },
    { k: "04 // PB", h: "COACHED", s: "BUYS THE GHOST\nJUST AHEAD", st: DONE ? "BUILT" : "UI BUILT", ok: DONE },
    { k: "05 // x402 + HTS", h: "PAID", s: "USDC, TO\nA PERSON", st: DONE ? "BUILT" : "AT THE EVENT", ok: DONE },
  ];
  const NW = 300, NH = 220, GAP = 50, X0 = (W - (5 * NW + 4 * GAP)) / 2, Y = BAR + 236;
  const xs = nodes.map((_, i) => X0 + i * (NW + GAP));
  const arc = prog(t, arcAt - 40, arcAt), cx0 = xs[0] + NW / 2, cx4 = xs[4] + NW / 2, yb = Y + NH + 8, dip = 96;
  const len = 2 * dip + (cx4 - cx0);
  return (
    <>
      <div style={{ position: "absolute", left: X0, top: BAR + 66 }}>
        <Kicker t={t}>THE LOOP // ONE LIVE RUN ON HEDERA</Kicker>
        <Title t={t} style={{ marginTop: 12 }}>PLAYED LIVE. CHECKED. PAID.</Title>
      </div>
      {nodes.map((n, i) => {
        const col = n.ok ? MW.green : MW.amber;
        return (
          <React.Fragment key={n.k}>
            <Card f={t} at={c[i]} x={xs[i]} y={Y} w={NW} h={NH} head={n.k} accent={col} headCol={col}>
              <div style={{ fontFamily: "Archivo Black", fontSize: 38, color: MW.text, letterSpacing: "0.02em", lineHeight: 1 }}>{n.h}</div>
              <Mono s={16} c={MW.text} style={{ marginTop: 14, lineHeight: 1.35 }}>{n.s}</Mono>
              <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", gap: 10, alignItems: "center" }}>
                <div style={{ width: 10, height: 10, background: col, opacity: n.ok || t % 40 < 26 ? 1 : 0.25 }} />
                <Mono s={15} c={col} w={700} ls="0.18em">{n.st}</Mono>
              </div>
            </Card>
            {i < 4 ? <Arrow t={t} at={c[i] + 12} x0={xs[i] + NW + 6} x1={xs[i + 1] - 8} y={Y + NH / 2} /> : null}
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
      <Mono s={15} c={MW.amber} w={700} ls="0.26em" style={{ position: "absolute", left: (cx0 + cx4) / 2 - 360, width: 720, textAlign: "center", top: yb + dip - 30,
        opacity: prog(t, arcAt - 8, arcAt + 4) }}>THE NEXT RUNNER TRAINS ON YOUR GHOST</Mono>
    </>
  );
};

/* ------------------------------------------------------------------ the act */

export const HederaAct: React.FC = () => {
  const f = useCurrentFrame();
  const assets = usePlateAssets();                                // loaded before any canvas mounts
  const s = shotAt(f), t = f - s.at;
  const board = (dir: number, body: React.ReactNode, zoom?: { at: number; s: number; ox: string; oy: string }) => (
    <OnBoard f={f} t={t} len={s.len} dir={dir} zoom={zoom}>{body}</OnBoard>
  );
  let body: React.ReactNode = null;
  switch (s.id) {
    case "slate": body = <Slate f={t} part="ANY% x HEDERA" title="LIVE AND PAID" len={s.len} num="H" />; break;
    case "plate": case "end":
      body = (
        <>
          {assets ? <Plate a={assets} t={t} len={s.len} view={s.id === "plate" ? 0 : 1} /> : null}
          <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 50%, rgba(0,0,0,0.65) 100%)" }} />
          <PlateHud t={t} end={s.id === "end"} />
        </>
      );
      break;
    case "brief": body = board(-0.8, <Brief t={t} />); break;
    case "start": body = board(0.8, <Start t={t} />); break;
    case "seed": body = board(-0.8, <Seed t={t} />); break;
    case "topic": body = board(0.7, <Topic t={t} />); break;
    case "envelope": body = board(-0.6, <Envelope t={t} />); break;
    case "slowed": body = board(0.6, <Slowed t={t} />); break;
    case "pay": body = board(-0.8, <Pay t={t} />); break;
    case "pay2": body = board(0.8, <Route t={t} />); break;
    case "x402": body = board(-0.7, <Ladder t={t} />); break;
    case "native": body = board(0.7, <Native t={t} />, { at: s.glitch![0], s: 1.1, ox: "50%", oy: "47%" }); break;
    case "hashscan":
      if (CLIPS.length) {
        const i = CLIP_AT.reduce((k, a, j) => (f >= a ? j : k), 0);
        body = <FieldClip t={f - CLIP_AT[i]} i={i} />;
      } else body = board(-0.8, <HashSlot t={t} />);
      break;
    case "loop": body = board(0.8, <LoopShot t={t} />); break;
  }
  const cut = s.id !== "slate" ? clamp(1 - t / 4) * 0.25 : 0;      // every hard cut lands on a short white flash
  const inner = s.glitch?.find((g) => t >= g && t < g + 4);
  const clipCut = s.id === "hashscan" && CLIPS.length ? CLIP_AT.find((a) => f >= a && f < a + 4) : undefined;
  const flash = cut + (inner !== undefined ? 0.2 * (1 - (t - inner) / 4) : 0) + (clipCut !== undefined ? 0.25 * (1 - (f - clipCut) / 4) : 0);
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {body}
      {s.id !== "slate" && s.id !== "plate" && s.id !== "end" ? (
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.7) 100%)" }} />
      ) : null}
      {flash > 0 ? <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} /> : null}
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, HEDERA_LEN - 14, HEDERA_LEN)) }} />
    </AbsoluteFill>
  );
};

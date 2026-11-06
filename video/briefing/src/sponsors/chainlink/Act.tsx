import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import BUILT from "../../acts/built.json";
import CHECK from "../../acts/check.json";
import { BAR, Bars, Card, kick, Line, Mono, MW, Row, Slate, Stamp, Subs, W } from "../../acts/common";
import { Board } from "../../acts/GameReel";
import { clamp, easeInOut, easeOutExpo, lerp, prog } from "../../util";
import CFG from "./config.json";

/* ANY% x CHAINLINK CRE (SPONSOR_DEMOS.md): the referee is a CRE workflow. Today the replay check runs on our server with
   our key; one finished run in, one verdict out, onchain, is the design (decided 5 Nov):
     TRIGGER  a run id, anyone can ask
     HEDERA   the run's HCS messages (START with the seed, a checkpoint every 2 s, FINISH) from the mirror node's REST API,
              with Hedera's consensus timestamps (CRE has no Hedera network: the mirror node is the external API)
     ARKIV    the run's record (game, time, log hash)
     CHECKS   inside the workflow: record = Hedera (Hedera wins), time inside the 15 s + 3% envelope, seed = START
     CHECKER  do the inputs replay to that time (ideally two independent operators)
     VERDICT  onchain (config.json verdict_destination), which the board and the payouts act on
   Honesty (docs/sponsors/chainlink-redteam-verdict.md): the workflow is built at the event, so until built.json has
   chainlink: true every call reads AT THE EVENT. A simulation runs on one machine (its write comes from a mock forwarder
   and our key), so the film never says a network agreed: "SIMULATED WITH THE CRE CLI" and "DEPLOYED: EVERY NODE RUNS IT,
   AND THEY MUST AGREE" are separate lines, and the second says NOT YET. VOID only on proof; anything missing is PENDING.
   The tamper beat shows the rule and a schematic, never made-up logs. The only values on screen are real: the checker's
   output is check.json (arcade_replay on the RUSH run log), 4892 frames / 60 = 1:21.53. When built.json gains CHAINLINK
   clips (the field report), they replace the empty slot and the act grows by their length, as in Objectives.tsx. */

type Clip = { file: string; sponsor: string; title: string; rows: [string, string][]; line: string; seconds: number; from?: number };
type Shot = { id: string; at: number; len: number };
type CLine = { shot: string; at: number; len: number; text: string; built?: string };
const CLIPS = (BUILT.clips as unknown as Clip[]).filter((c) => c.sponsor === "CHAINLINK");
const DONE = (BUILT.built as Record<string, boolean>).chainlink === true;
const DEST = String(CFG.verdict_destination).toUpperCase();
const clipLen = (c: Clip) => Math.round(c.seconds * 60);
const SHOTS: Shot[] = (() => {
  let a = 0;
  return (CFG.shots as { id: string; len: number }[]).map((s) => {
    const len = s.id === "field" && CLIPS.length ? CLIPS.reduce((n, c) => n + clipLen(c), 0) : s.len;
    const o = { id: s.id, at: a, len };
    a += len;
    return o;
  });
})();
const AT = Object.fromEntries(SHOTS.map((s) => [s.id, s.at])) as Record<string, number>;
export const CHAINLINK_LEN = SHOTS[SHOTS.length - 1].at + SHOTS[SHOTS.length - 1].len;
const CLIP_AT = CLIPS.map((_, i) => AT.field + CLIPS.slice(0, i).reduce((n, c) => n + clipLen(c), 0));
const LINES: Line[] = [
  ...(CFG.lines as CLine[]).filter((l) => !(l.shot === "field" && CLIPS.length))
    .map((l) => ({ at: AT[l.shot] + l.at, len: l.len, who: "Handler", text: DONE && l.built ? l.built : l.text })),
  ...CLIPS.map((c, i) => ({ at: CLIP_AT[i] + 16, len: clipLen(c) - 28, who: "Handler", text: c.line })),
].sort((a, b) => a.at - b.at);
const shotAt = (f: number) => SHOTS.reduce((k, s) => (f >= s.at ? s : k), SHOTS[0]);

// a call's status: amber AT THE EVENT until built.json says the workflow ran (simulated) on camera
const ST = DONE ? { text: "SIMULATED AT THE EVENT", call: "CALL: SIMULATED", col: MW.green } : { text: "AT THE EVENT", call: "CALL: AT THE EVENT", col: MW.amber };
const VOID_AT = 108;                                                  // the VOID stamp, in the void shot

/* ---------- small parts ---------- */

const Kicker: React.FC<{ t: number; text: string; x: number; y: number; at?: number; col?: string; s?: number; center?: boolean }> = ({ t, text, x, y, at = 6, col = MW.orange, s = 17, center }) => (
  <Mono s={s} c={col} w={700} ls="0.4em" style={{ position: "absolute", left: center ? 0 : x, width: center ? W : undefined, textAlign: center ? "center" : undefined,
    top: y, opacity: t > at && !(t > at + 3 && t < at + 6) ? 1 : 0 }}>{text}</Mono>
);

/** An Archivo heading that wipes on from the left. */
const Head: React.FC<{ t: number; at: number; text: string; s: number; x?: number; y: number; col?: string; dur?: number; center?: boolean; style?: React.CSSProperties }> = ({ t, at, text, s, x = 0, y, col = MW.text, dur = 18, center, style }) => (
  <div style={{ position: "absolute", left: center ? 0 : x, width: center ? W : undefined, textAlign: center ? "center" : undefined, top: y,
    fontFamily: "Archivo Black", fontSize: s, lineHeight: 1.05, color: col, whiteSpace: "pre", letterSpacing: "0.02em",
    clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, at, at + dur))}% 0 0)`, ...style }}>{text}</div>
);

/** Body text that wipes down, the card grammar. */
const Body: React.FC<{ t: number; at: number; text: string; s?: number; x?: number; y: number; col?: string; lh?: number }> = ({ t, at, text, s = 21, x = 0, y, col = MW.text, lh = 1.45 }) => (
  <Mono s={s} c={col} ls="0.04em" style={{ position: "absolute", left: x, top: y, lineHeight: lh, clipPath: `inset(0 0 ${100 - 100 * prog(t, at, at + 10)}% 0)` }}>{text}</Mono>
);

const Pill: React.FC<{ t: number; text: string; col: string; blink?: boolean; s?: number }> = ({ t, text, col, blink, s = 17 }) => (
  <div style={{ display: "inline-flex", gap: 12, alignItems: "center", padding: "5px 14px 6px", border: `2px solid ${col}`, background: `${col}1c` }}>
    <div style={{ width: 11, height: 11, background: col, opacity: !blink || t % 40 < 26 ? 1 : 0.25 }} />
    <Mono s={s} c={col} w={700} ls="0.18em">{text}</Mono>
  </div>
);

/** A labelled box for the little flow diagrams. */
const Box: React.FC<{ x: number; y: number; w: number; h: number; text: string; col: string; s?: number; on?: number }> = ({ x, y, w, h, text, col, s = 22, on = 1 }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, border: `2px solid ${col}`, background: `${col}14`, display: "flex",
    alignItems: "center", justifyContent: "center", opacity: on > 0 ? 1 : 0, clipPath: `inset(0 ${100 - 100 * on}% 0 0)` }}>
    <Mono s={Math.min(s, (w - 24) / (text.length * 0.74))} c={col} w={700} ls="0.14em">{text}</Mono>
  </div>
);

const along = (pts: [number, number][], u: number): [number, number] => {
  const seg = pts.slice(1).map((q, i) => Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]));
  let d = clamp(u) * seg.reduce((a, b) => a + b, 0);
  for (let i = 0; i < seg.length; i++) {
    if (d <= seg[i] || i === seg.length - 1) {
      const k = seg[i] ? clamp(d / seg[i]) : 0;
      return [lerp(pts[i][0], pts[i + 1][0], k), lerp(pts[i][1], pts[i + 1][1], k)];
    }
    d -= seg[i];
  }
  return pts[pts.length - 1];
};

/** A line drawn on along its points (p: 0..1), with an arrowhead once it lands. */
const Path: React.FC<{ pts: [number, number][]; p: number; col?: string; sw?: number; head?: boolean; dash?: string; op?: number }> = ({ pts, p, col = MW.text, sw = 2, head = true, dash, op = 0.9 }) => {
  if (p <= 0) return null;
  const len = pts.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]), 0);
  const d = pts.map((q, i) => `${i ? "L" : "M"} ${q[0].toFixed(1)} ${q[1].toFixed(1)}`).join(" ");
  const [a, b] = [pts[pts.length - 2], pts[pts.length - 1]];
  const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const hp = (r: number, s: number) => `${(b[0] + Math.cos(ang + s) * r).toFixed(1)} ${(b[1] + Math.sin(ang + s) * r).toFixed(1)}`;
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity: op }} width={1} height={1}>
      {dash ? <path d={d} fill="none" stroke={col} strokeWidth={sw} strokeDasharray={dash} opacity={p} />
        : <path d={d} fill="none" stroke={col} strokeWidth={sw} strokeDasharray={`${(len * p).toFixed(1)} ${(len + 2).toFixed(1)}`} />}
      {head && p >= 1 ? <path d={`M ${b[0]} ${b[1]} L ${hp(13, Math.PI - 0.42)} L ${hp(13, Math.PI + 0.42)} Z`} fill={col} /> : null}
    </svg>
  );
};

const Dot: React.FC<{ at: [number, number]; col: string; r?: number }> = ({ at, col, r = 7 }) => (
  <div style={{ position: "absolute", left: at[0] - r, top: at[1] - r, width: 2 * r, height: 2 * r, borderRadius: "50%", background: col,
    boxShadow: `0 0 14px ${col}, 0 0 30px ${col}88` }} />
);

/** A light sweeping across a card once it has landed (Objectives' sweep). */
const Sweep: React.FC<{ t: number; at: number; x: number; y: number; w: number; h: number; col?: string }> = ({ t, at, x, y, w, h, col = "255,178,63" }) => {
  const s = prog(t, at, at + 30);
  if (s <= 0 || s >= 1) return null;
  return <div style={{ position: "absolute", left: x, top: y, width: w, height: h, pointerEvents: "none", mixBlendMode: "screen",
    background: `linear-gradient(100deg, rgba(${col},0) ${s * 140 - 30}%, rgba(${col},0.2) ${s * 140 - 10}%, rgba(${col},0) ${s * 140}%)` }} />;
};

/* ---------- 1. the problem: today the referee is our server ---------- */

const DG = { A: { x: 140, y: 440, w: 320, h: 170 }, B: { x: 560, y: 440, w: 440, h: 170 }, C: { x: 1110, y: 380, w: 380, h: 140 }, D: { x: 1110, y: 560, w: 380, h: 140 } };
const P_AB: [number, number][] = [[468, 525], [550, 525]];
const P_BC: [number, number][] = [[1008, 525], [1055, 525], [1055, 450], [1100, 450]];
const P_BD: [number, number][] = [[1008, 525], [1055, 525], [1055, 630], [1100, 630]];

const Today: React.FC<{ t: number; trust?: boolean }> = ({ t, trust }) => {
  const q = trust ? 999 : t;                                          // the close-up: the same board, already built
  const big = (s: string, c = MW.text, n = 34) => <div style={{ fontFamily: "Archivo Black", fontSize: n, color: c, lineHeight: 1, letterSpacing: "0.02em" }}>{s}</div>;
  const red = trust ? 0.55 + 0.45 * Math.abs(Math.sin(t / 9)) : 0;
  return (
    <>
      <Card f={q} at={40} {...DG.A} head="01 // A RUN" accent={MW.blue} headCol={MW.blue}>
        {big("A RECORD")}
        <Mono s={16} c={MW.text} style={{ marginTop: 14, lineHeight: 1.35 }}>{"ITS LOG: ANYONE\nCAN REPLAY IT"}</Mono>
      </Card>
      <Card f={q} at={52} {...DG.B} head="02 // THE REFEREE, TODAY" accent={MW.red} headCol={MW.red}>
        {big("OUR SERVER")}
        <Mono s={16} c={MW.text} style={{ marginTop: 14, lineHeight: 1.35 }}>{"REPLAYS THE LOG, THEN WRITES\nTHE VERDICT WITH OUR KEY"}</Mono>
      </Card>
      <Card f={q} at={64} {...DG.C} head="03 // THE BOARD">
        {big("LISTED", MW.text, 30)}
        <Mono s={16} c={MW.dim} style={{ marginTop: 10 }}>WHAT EVERYONE SEES</Mono>
      </Card>
      <Card f={q} at={72} {...DG.D} head="04 // COACH PAYOUTS" accent={MW.amber} headCol={MW.amber}>
        {big("PAID", MW.amber, 30)}
        <Mono s={16} c={MW.dim} style={{ marginTop: 10 }}>MONEY MOVES ON IT</Mono>
      </Card>
      <Path pts={P_AB} p={prog(q, 54, 62)} />
      <Path pts={P_BC} p={prog(q, 66, 78)} />
      <Path pts={P_BD} p={prog(q, 72, 84)} />
      {trust ? (
        <>
          <div style={{ position: "absolute", left: DG.B.x - 6, top: DG.B.y - 6, width: DG.B.w + 12, height: DG.B.h + 12, border: `2px solid ${MW.red}`, opacity: red,
            boxShadow: `0 0 30px ${MW.red}66` }} />
          {[P_BC, P_BD].map((p, k) => (t > 22 ? <Dot key={k} at={along(p, ((t - 22 + k * 12) % 44) / 44)} col={MW.red} /> : null))}
          <Card f={t} at={14} x={480} y={236} w={600} h={150} head="SINGLE POINT OF TRUST" accent={MW.red} headCol={MW.red}>
            <Mono s={20} c={MW.text} style={{ lineHeight: 1.35 }}>{"IF WE LIE, OR WE ARE HACKED,\nA FAKE RECORD REACHES THE BOARD\nAND THE PAYOUTS."}</Mono>
          </Card>
        </>
      ) : null}
    </>
  );
};

const Problem: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Kicker t={t} text="THE PROBLEM" x={140} y={160} />
    <Head t={t} at={12} text={"WHO REFEREES A RECORD\nWHEN MONEY IS ON IT?"} s={66} x={140} y={200} dur={22} />
    <Today t={t} />
  </>
);

/* ---------- 2. the fix ---------- */

const StatusRow: React.FC<{ t: number; at: number; y: number; label: string; status: string; col: string; blink?: boolean }> = ({ t, at, y, label, status, col, blink }) => (
  <Card f={t} at={at} x={360} y={y} w={1200} h={60} accent={col}>
    <Mono s={20} c={MW.text} w={700} ls="0.08em" style={{ position: "absolute", left: 0, top: -2 }}>{label}</Mono>
    <div style={{ position: "absolute", right: 0, top: -1, display: "flex", gap: 10, alignItems: "center" }}>
      <div style={{ width: 11, height: 11, background: col, opacity: !blink || t % 40 < 26 ? 1 : 0.25 }} />
      <Mono s={18} c={col} w={700} ls="0.18em">{status}</Mono>
    </div>
  </Card>
);

const Fix: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Kicker t={t} text="THE FIX" x={0} y={196} center />
    <Head t={t} at={12} text="CHAINLINK CRE" s={132} y={226} center dur={20} style={{ textShadow: "0 0 50px rgba(124,196,255,0.16)" }} />
    <div style={{ position: "absolute", left: W / 2 - 310 * easeOutExpo(prog(t, 18, 34)), top: 390, width: 620 * easeOutExpo(prog(t, 18, 34)), height: 3, background: MW.orange }} />
    <Mono s={30} c={MW.text} w={700} ls="0.12em" style={{ position: "absolute", left: 0, width: W, textAlign: "center", top: 418,
      clipPath: `inset(0 ${100 - 100 * prog(t, 40, 58)}% 0 0)` }}>THE REFEREE BECOMES A WORKFLOW</Mono>
    <Mono s={20} c={MW.dim} ls="0.16em" style={{ position: "absolute", left: 0, width: W, textAlign: "center", top: 470, opacity: prog(t, 66, 74) }}>
      ONE FINISHED RUN IN. ONE VERDICT OUT, ONCHAIN.
    </Mono>
    <StatusRow t={t} at={118} y={560} label="SIMULATED WITH THE CRE CLI" status={ST.text} col={ST.col} blink={!DONE} />
    <StatusRow t={t} at={134} y={634} label="DEPLOYED: EVERY NODE RUNS IT, AND THEY MUST AGREE" status="NOT YET" col={MW.dim} />
  </>
);

/* ---------- 3. the workflow, built up step by step ---------- */

const STEPS = ["trigger", "hedera", "arkiv", "checks", "checker", "verdict"];
const NODES = [
  { k: "01 // TRIGGER", t: "A RUN ID", via: "ANYONE CAN CALL IT" },
  { k: "02 // HEDERA", t: "THE CLOCK", via: "HTTP // MIRROR NODE" },
  { k: "03 // ARKIV", t: "THE RECORD", via: "HTTP // ARKIV RPC" },
  { k: "04 // CHECKS", t: "THE RULES", via: "INSIDE THE WORKFLOW" },
  { k: "05 // CHECKER", t: "THE REPLAY", via: "HTTP x2 // CHECKERS" },
  { k: "06 // VERDICT", t: "ONCHAIN", via: `WRITE // ${DEST}` },
];
const NX = (i: number) => 70 + i * 302, NY = 176, NW = 268, NH = 124;
const PX = 70, PY = 340, PW = 1780, PH = 452;

/** The six nodes across the top: the ones already built stay, the new one spawns, the current one is lit. */
const Pipeline: React.FC<{ t: number; k: number }> = ({ t, k }) => {
  const all = k >= NODES.length;
  const px = all ? lerp(NX(0) - 20, NX(5) + NW + 20, prog(t, 16, 100)) : -1e4;   // the pulse, in the wide shot
  return (
    <>
      <Kicker t={k === 0 ? t : 99} text="CHAINLINK CRE // THE WORKFLOW: ONE FINISHED RUN, ONE VERDICT" x={70} y={140} s={15} />
      {NODES.map((n, i) => {
        if (i > k) return null;
        const cur = i === k || all;
        const fresh = i === k && !all;
        const d = Math.abs(px - (NX(i) + NW / 2));
        const hot = d < 70 ? 1 - d / 70 : 0;
        return (
          <React.Fragment key={n.k}>
            {i > 0 ? <Path pts={[[NX(i) - 30, NY + NH / 2], [NX(i) - 6, NY + NH / 2]]} p={fresh ? prog(t, 2, 8) : 1} col={cur ? MW.blue : MW.faint} /> : null}
            <Card f={fresh ? t : 999} at={8} x={NX(i)} y={NY} w={NW} h={NH} head={n.k} accent={cur ? MW.blue : MW.faint} headCol={cur ? MW.blue : MW.dim}>
              <div style={{ fontFamily: "Archivo Black", fontSize: 26, color: cur ? MW.text : MW.dim, lineHeight: 1 }}>{n.t}</div>
              <div style={{ position: "absolute", left: 0, bottom: 0, display: "flex", gap: 8, alignItems: "center" }}>
                <div style={{ width: 9, height: 9, background: ST.col, opacity: DONE || t % 40 < 26 ? 1 : 0.25 }} />
                <Mono s={12} c={ST.col} w={700} ls="0.16em">{ST.text}</Mono>
              </div>
            </Card>
            {hot > 0 ? <div style={{ position: "absolute", left: NX(i) - 4, top: NY - 4, width: NW + 8, height: NH + 8, border: `2px solid ${MW.ice}`, opacity: hot,
              boxShadow: `0 0 40px rgba(124,196,255,${(0.5 * hot).toFixed(3)})` }} /> : null}
            <Mono s={12} c={cur ? MW.blue : MW.faint} ls="0.14em" style={{ position: "absolute", left: NX(i) + 4, top: NY + NH + 10, opacity: fresh ? prog(t, 20, 26) : 1 }}>{n.via}</Mono>
          </React.Fragment>
        );
      })}
      {all && px > NX(0) && px < NX(5) + NW ? <Dot at={[px, NY + NH / 2]} col={MW.ice} r={8} /> : null}
    </>
  );
};

type PillT = { text: string; col: string; blink?: boolean };
/** The left half of the detail panel: what this step is, and what is built. */
const Left: React.FC<{ t: number; kicker: string; title: string; desc: string; note?: string; pills: PillT[]; ts?: number }> = ({ t, kicker, title, desc, note, pills, ts = 62 }) => {
  const rows = title.split("\n").length;
  const dy = 30 + rows * ts * 1.05 + 22;
  const dl = desc.split("\n").length;
  return (
    <div style={{ position: "absolute", left: 44, top: 34, width: 800 }}>
      <Kicker t={t} text={kicker} x={0} y={0} s={16} />
      <Head t={t} at={8} text={title} s={ts} y={30} />
      <Body t={t} at={16} text={desc} y={dy} />
      {note ? <Body t={t} at={26} text={note} s={15} col={MW.dim} y={dy + dl * 21 * 1.45 + 14} lh={1.45} /> : null}
      <div style={{ position: "absolute", left: 0, top: 336, display: "flex", gap: 14, opacity: prog(t, 34, 40) }}>
        {pills.map((p) => <Pill key={p.text} t={t} text={p.text} col={p.col} blink={p.blink} />)}
      </div>
    </div>
  );
};
const CALL: PillT = { text: ST.call, col: ST.col, blink: !DONE };

const RX = 880, RY = 34, RW = 856;                                     // the right half, inside the panel

const TriggerR: React.FC<{ t: number }> = ({ t }) => (
  <Card f={t} at={18} x={RX} y={RY} w={RW} h={330} head="THE INPUT" accent={MW.blue} headCol={MW.blue}>
    <Box x={0} y={14} w={240} h={70} text="RUN ID" col={MW.amber} on={prog(t, 28, 36)} />
    <Path pts={[[250, 49], [366, 49]]} p={prog(t, 36, 44)} />
    <Box x={378} y={14} w={434} h={70} text="CHAINLINK CRE WORKFLOW" col={MW.blue} on={prog(t, 42, 50)} />
    <div style={{ position: "absolute", left: 0, right: 0, top: 124, opacity: prog(t, 50, 58) }}>
      <Row k="WHO CAN TRIGGER IT" v="ANYONE" s={20} c={MW.green} />
      <Row k="WHAT IT CARRIES" v="ONE FINISHED RUN'S ID" s={20} />
      <Row k="WHAT COMES BACK" v="ONE VERDICT" s={20} />
    </div>
  </Card>
);

const HederaR: React.FC<{ t: number }> = ({ t }) => {
  const x0 = 24, x1 = 788, y = 120, n = 8, dx = (x1 - x0) / (n + 1);
  const at = (i: number) => 30 + i * 5;                               // START, the checkpoints, FINISH, one after another
  return (
    <Card f={t} at={18} x={RX} y={RY} w={RW} h={330} head="HCS // ONE RUN'S MESSAGES" accent={MW.blue} headCol={MW.blue}>
      <div style={{ position: "absolute", left: x0, top: y - 1, width: (x1 - x0) * prog(t, 28, at(n + 1)), height: 2, background: MW.dim }} />
      {t >= at(0) ? <Dot at={[x0, y]} col={MW.green} r={10} /> : null}
      {Array.from({ length: n }, (_, i) => (t >= at(i + 1) ? (
        <div key={i} style={{ position: "absolute", left: x0 + (i + 1) * dx - 2, top: y - 16, width: 4, height: 32, background: MW.blue, boxShadow: `0 0 10px ${MW.blue}` }} />
      ) : null))}
      {t >= at(n + 1) ? <Dot at={[x1, y]} col={MW.amber} r={10} /> : null}
      <Mono s={16} c={MW.green} w={700} ls="0.16em" style={{ position: "absolute", left: x0 - 10, top: y - 52, opacity: prog(t, at(0), at(0) + 4) }}>START</Mono>
      <Mono s={14} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: x0 - 10, top: y + 26, lineHeight: 1.35, opacity: prog(t, at(0) + 4, at(0) + 10) }}>{"SEED: HEDERA'S\nRUNNING HASH"}</Mono>
      <Mono s={16} c={MW.blue} w={700} ls="0.16em" style={{ position: "absolute", left: 0, width: x1 + x0, textAlign: "center", top: y - 52, opacity: prog(t, at(4), at(4) + 4) }}>A CHECKPOINT EVERY 2 S</Mono>
      <Mono s={16} c={MW.amber} w={700} ls="0.16em" style={{ position: "absolute", right: 812 - x1 - 10, top: y - 52, opacity: prog(t, at(n + 1), at(n + 1) + 4) }}>FINISH</Mono>
      <Mono s={14} c={MW.dim} ls="0.1em" style={{ position: "absolute", right: 812 - x1 - 10, top: y + 26, textAlign: "right", lineHeight: 1.35, opacity: prog(t, at(n + 1) + 4, at(n + 1) + 10) }}>{"THE CLAIMED\nTIME"}</Mono>
      <div style={{ position: "absolute", left: 0, right: 0, top: 206, borderTop: `1px solid ${MW.faint}`, paddingTop: 14, opacity: prog(t, 84, 92) }}>
        <Mono s={17} c={MW.text} ls="0.08em">EACH ONE STAMPED WITH HEDERA'S CONSENSUS TIME</Mono>
      </div>
    </Card>
  );
};

const ArkivR: React.FC<{ t: number }> = ({ t }) => {
  const rows = [["GAME", "WHICH GAME, WHICH RULES"], ["TIME", "THE TIME IT CLAIMS"], ["LOG HASH", "THE LOG IT CAME FROM"]];
  return (
    <Card f={t} at={18} x={RX} y={RY} w={RW} h={330} head="ARKIV // THE RUN'S RECORD" accent={MW.blue} headCol={MW.blue}>
      {rows.map(([k, v], i) => (
        <div key={k} style={{ position: "absolute", left: 0, right: 0, top: 8 + i * 64, height: 54, borderBottom: `1px solid ${MW.faint}`,
          clipPath: `inset(0 ${100 - 100 * prog(t, 26 + i * 8, 36 + i * 8)}% 0 0)` }}>
          <div style={{ position: "absolute", left: 0, top: 6, fontFamily: "Archivo Black", fontSize: 30, color: MW.text, letterSpacing: "0.03em" }}>{k}</div>
          <Mono s={17} c={MW.dim} ls="0.12em" style={{ position: "absolute", left: 300, top: 16 }}>{v}</Mono>
        </div>
      ))}
      <Mono s={16} c={MW.blue} w={700} ls="0.16em" style={{ position: "absolute", left: 0, top: 222, opacity: prog(t, 60, 66) }}>NEXT: CHECKED AGAINST HEDERA. HEDERA WINS.</Mono>
    </Card>
  );
};

const RULES = [
  { r: "THE RECORD MATCHES HEDERA", n: "IF THEY DIFFER, HEDERA WINS" },
  { r: "THE TIME FITS HEDERA'S CLOCK", n: "15 S + 3% ENVELOPE" },
  { r: "THE SEED MATCHES START", n: "HEDERA'S RUNNING HASH" },
];
const ChecksR: React.FC<{ t: number }> = ({ t }) => (
  <>
    {RULES.map((r, i) => {
      const at = 18 + i * 14, y = RY + i * 128;
      return (
        <React.Fragment key={r.r}>
          <Card f={t} at={at} x={RX} y={y} w={RW} h={112} head={`RULE 0${i + 1} // ${r.n}`} accent={MW.blue} headCol={MW.blue}>
            <div style={{ position: "absolute", left: 0, top: 2, fontFamily: "Archivo Black", fontSize: 28, color: MW.text, letterSpacing: "0.02em" }}>{r.r}</div>
          </Card>
          <Sweep t={t} at={at + 22} x={RX} y={y} w={RW} h={112} col="124,196,255" />
        </React.Fragment>
      );
    })}
  </>
);

/** The real checker on the RUSH run log: the command and its exact stdout (check.json), nothing added inside. */
const RUSH = CHECK.find((c) => c.game === "RUSH")!;
const RUSH_TIME = (() => {
  const tf = Number(/"time_frames":(\d+)/.exec(RUSH.stdout)![1]);
  const cs = Math.round((tf * 100) / 60);
  return { tf, txt: `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}` };
})();
const CheckerR: React.FC<{ t: number }> = ({ t }) => {
  const grow = easeOutExpo(prog(t, 16, 26));
  const cmd = RUSH.cmd, n = Math.min(cmd.length, Math.max(0, t - 26));
  const out = 26 + cmd.length + 6;
  const parts = RUSH.stdout.split(/("hash_matches":true|"time_frames":\d+)/);
  return (
    <>
      <div style={{ position: "absolute", left: RX, top: RY, width: RW, height: 214 * grow, overflow: "hidden", background: "rgba(7,8,9,0.97)",
        border: "1px solid #2a2d31", boxShadow: "0 30px 90px rgba(0,0,0,0.7)" }}>
        <div style={{ height: 36, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px", background: "#111315", borderBottom: `2px solid ${MW.green}` }}>
          <Mono s={14} c={MW.green} w={700} ls="0.26em">THE CHECKER TODAY // REAL OUTPUT</Mono>
          <Mono s={12} c={MW.dim} ls="0.2em">RUSH HOUR'S RUN LOG</Mono>
        </div>
        <div style={{ position: "absolute", left: 18, right: 18, top: 50 }}>
          <div style={{ fontFamily: "Space Mono", fontSize: 17, lineHeight: "27px", color: MW.text, whiteSpace: "pre" }}>
            <span style={{ color: MW.green }}>$ </span>{cmd.slice(0, n)}{t < out && Math.floor(t / 8) % 2 === 0 ? <span style={{ background: MW.text }}> </span> : null}
          </div>
          {t >= out ? (
            <div style={{ fontFamily: "Space Mono", fontSize: 16, lineHeight: "26px", color: MW.dim, wordBreak: "break-all", whiteSpace: "pre-wrap", marginTop: 6 }}>
              {parts.map((p, i) => <span key={i} style={{ color: /hash_matches/.test(p) ? MW.green : /time_frames/.test(p) ? MW.amber : undefined, fontWeight: /hash_matches|time_frames/.test(p) ? 700 : 400 }}>{p}</span>)}
            </div>
          ) : null}
        </div>
      </div>
      <div style={{ position: "absolute", left: RX, top: RY + 232, opacity: prog(t, out + 10, out + 18), borderLeft: `3px solid ${MW.amber}`, padding: "2px 0 2px 14px" }}>
        <Mono s={20} c={MW.amber} w={700} ls="0.1em">{`${RUSH_TIME.tf} FRAMES / 60 = ${RUSH_TIME.txt}`}</Mono>
        <Mono s={14} c={MW.dim} ls="0.16em" style={{ marginTop: 6 }}>THE TIME THE INPUTS GIVE. MEASURED, NOT CLAIMED.</Mono>
      </div>
    </>
  );
};

const VerdictR: React.FC<{ t: number }> = ({ t }) => (
  <Card f={t} at={18} x={RX} y={RY} w={RW} h={330} head="WHERE IT GOES" accent={MW.blue} headCol={MW.blue}>
    <Box x={0} y={70} w={200} h={64} text="VERDICT" col={MW.green} on={prog(t, 28, 36)} />
    <Path pts={[[208, 102], [270, 102]]} p={prog(t, 36, 42)} />
    <Box x={282} y={70} w={250} h={64} text={DEST} col={MW.blue} on={prog(t, 40, 48)} />
    <Path pts={[[540, 102], [572, 102], [572, 40], [600, 40]]} p={prog(t, 48, 56)} />
    <Path pts={[[540, 102], [572, 102], [572, 164], [600, 164]]} p={prog(t, 52, 60)} />
    <Box x={612} y={8} w={200} h={64} text="THE BOARD" col={MW.text} on={prog(t, 56, 62)} />
    <Box x={612} y={132} w={200} h={64} text="PAYOUTS" col={MW.amber} on={prog(t, 60, 66)} />
    <Mono s={13} c={MW.dim} ls="0.16em" style={{ position: "absolute", left: 612, top: 86, opacity: prog(t, 62, 68) }}>BOTH ACT ON IT</Mono>
    <div style={{ position: "absolute", left: 0, right: 0, top: 222, borderTop: `1px solid ${MW.faint}`, paddingTop: 14, opacity: prog(t, 70, 78) }}>
      <Mono s={17} c={MW.text} ls="0.08em">ONE VALUE A RUN: VERIFIED, VOID OR PENDING</Mono>
    </div>
  </Card>
);

const DETAIL: Record<string, { kicker: string; title: string; desc: string; note?: string; pills: PillT[]; R: React.FC<{ t: number }>; ts?: number }> = {
  trigger: { kicker: "01 // TRIGGER", title: "ONE RUN ID", desc: "ONE FINISHED RUN, ONE VERDICT.\nANYONE CAN ASK FOR IT:\nNO KEY OF OURS IN THE WAY.", pills: [CALL], R: TriggerR },
  hedera: { kicker: "02 // HEDERA // HTTP: MIRROR NODE", title: "THE CLOCK", desc: "THE RUN'S HCS MESSAGES,\nWITH HEDERA'S CONSENSUS\nTIMESTAMPS.",
    note: "CRE HAS NO HEDERA NETWORK, SO THE WORKFLOW\nREADS THE MIRROR NODE'S REST API OVER HTTP.", pills: [CALL], R: HederaR },
  arkiv: { kicker: "03 // ARKIV // HTTP: ARKIV RPC", title: "THE RECORD", desc: "WHAT THE BOARD CLAIMS\nFOR THIS RUN.", pills: [CALL], R: ArkivR },
  checks: { kicker: "04 // CHECKS // INSIDE THE WORKFLOW", title: "DOES IT ADD UP?", desc: "THREE RULES, RUN BY THE\nWORKFLOW ITSELF. WHEN ARKIV\nAND HEDERA DISAGREE,\nHEDERA WINS.", pills: [CALL], R: ChecksR, ts: 58 },
  checker: { kicker: "05 // REPLAY CHECKER // HTTP x2", title: "THE REPLAY", desc: "DO THE INPUTS REPLAY TO\nTHAT TIME? THE CHECKER ANSWERS.\nIDEALLY TWO, RUN BY\nINDEPENDENT OPERATORS.",
    note: "DEPLOYED, THE NODES AGREE ON WHAT\nTHE CHECKER ANSWERED.", pills: [{ text: "REPLAY TOOL: BUILT", col: MW.green }, CALL], R: CheckerR },
  verdict: { kicker: `06 // VERDICT // ${DEST}`, title: "THE VERDICT,\nONCHAIN", desc: "THE BOARD AND THE COACH\nPAYOUTS ACT ON IT.", pills: [CALL], R: VerdictR, ts: 58 },
};

const Panel: React.FC<{ t: number; grow: boolean; children: React.ReactNode }> = ({ t, grow, children }) => (
  <div style={{ position: "absolute", left: PX, top: PY, width: PW, height: PH * (grow ? easeOutExpo(prog(t, 4, 14)) : 1), overflow: "hidden",
    background: "rgba(6,7,8,0.9)", border: "1px solid #2a2d31", borderLeft: `3px solid ${MW.blue}`,
    boxShadow: "0 40px 120px rgba(0,0,0,0.75), 0 0 80px rgba(124,196,255,0.06)" }}>{children}</div>
);

const Step: React.FC<{ t: number; id: string }> = ({ t, id }) => {
  const k = STEPS.indexOf(id), d = DETAIL[id];
  return (
    <>
      <Pipeline t={t} k={k} />
      <Panel t={t} grow={k === 0}>
        <Left t={t} kicker={d.kicker} title={d.title} desc={d.desc} note={d.note} pills={d.pills} ts={d.ts} />
        <d.R t={t} />
      </Panel>
    </>
  );
};

/** All six lit, a pulse through them, and CRE's limits. */
const LIMITS = [
  { big: "5 HTTP CALLS", small: "A RUN. THIS WORKFLOW USES 4" },
  { big: "100 KB", small: "A RESPONSE, AT MOST" },
  { big: "5 MIN", small: "A RUN, AT MOST" },
];
const Wide: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Pipeline t={t} k={NODES.length} />
    <div style={{ position: "absolute", left: 0, width: W, top: 380, display: "flex", justifyContent: "center", alignItems: "center", gap: 34,
      clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, 10, 30))}% 0 0)` }}>
      <div style={{ fontFamily: "Archivo Black", fontSize: 56, color: MW.text, letterSpacing: "0.02em" }}>ONE FINISHED RUN</div>
      <svg width={110} height={40}><path d="M 0 20 L 92 20" stroke={MW.blue} strokeWidth={4} /><path d="M 108 20 L 88 8 L 88 32 Z" fill={MW.blue} /></svg>
      <div style={{ fontFamily: "Archivo Black", fontSize: 56, color: MW.blue, letterSpacing: "0.02em" }}>ONE VERDICT</div>
    </div>
    {LIMITS.map((l, i) => (
      <Card key={l.big} f={t} at={40 + i * 10} x={140 + i * 560} y={520} w={520} h={150} head="CRE LIMIT" accent={MW.orange}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 40, color: MW.text, lineHeight: 1 }}>{l.big}</div>
        <Mono s={17} c={MW.dim} ls="0.12em" style={{ marginTop: 12 }}>{l.small}</Mono>
      </Card>
    ))}
  </>
);

/* ---------- 4. the tamper beat: a slowed run, and the rule that voids it ---------- */

const PL = { x: 990, y: 210, w: 780, h: 500, pMax: 90, cMax: 130 };
const map = (p: number, c: number): [number, number] => [PL.x + (p / PL.pMax) * PL.w, PL.y + PL.h - (c / PL.cMax) * PL.h];
const ENV = (p: number) => 15 + 1.03 * p;                             // the rule: START + 15 s + 1.03 x play time
const SLOW = (p: number) => 1.5 + 1.42 * p;                           // schematic: a run played at about 70 % speed
const HONEST = (p: number) => 1.5 + p;                                // schematic: real time, plus posting latency
const CROSS = (15 - 1.5) / (1.42 - 1.03);                             // where the slowed run leaves the envelope
const SLOW_A = 120, SLOW_B = 196, SLOW_P = 62;                        // the slowed line draws over these frames, to this play time
export const CROSS_AT = Math.round(SLOW_A + ((SLOW_B - SLOW_A) * CROSS) / SLOW_P);

const Plot: React.FC<{ t: number }> = ({ t }) => {
  const env: [number, number][] = [map(0, ENV(0)), map(PL.pMax, ENV(PL.pMax))];
  const area = [map(0, 0), map(0, ENV(0)), map(PL.pMax, ENV(PL.pMax)), map(PL.pMax, PL.pMax)].map((q) => q.join(",")).join(" ");
  const pS = lerp(0, SLOW_P, prog(t, SLOW_A, SLOW_B));
  const out = pS >= CROSS;
  const xp = map(CROSS, SLOW(CROSS));
  return (
    <>
      <Path pts={[[PL.x, PL.y + PL.h], [PL.x + PL.w + 10, PL.y + PL.h]]} p={prog(t, 10, 22)} col={MW.dim} sw={2} />
      <Path pts={[[PL.x, PL.y + PL.h], [PL.x, PL.y - 10]]} p={prog(t, 10, 22)} col={MW.dim} sw={2} />
      <Mono s={14} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: PL.x + PL.w - 160, top: PL.y + PL.h + 14, opacity: prog(t, 20, 26) }}>PLAY TIME</Mono>
      <Mono s={14} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: PL.x + 14, top: PL.y - 22, opacity: prog(t, 20, 26) }}>HEDERA'S CLOCK</Mono>
      <Mono s={15} c={MW.text} w={700} ls="0.2em" style={{ position: "absolute", left: PL.x + PL.w - 400, top: PL.y - 24, width: 400, textAlign: "right", opacity: prog(t, 20, 26) }}>SCHEMATIC // NOT A REAL RUN</Mono>
      <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={1} height={1}>
        <polygon points={area} fill={MW.amber} opacity={0.09 * prog(t, 36, 50)} />
      </svg>
      <Path pts={[map(0, 0), map(PL.pMax, PL.pMax)]} p={prog(t, 22, 34)} col={MW.dim} sw={1.5} head={false} dash="6 8" />
      <Mono s={13} c={MW.dim} ls="0.16em" style={{ position: "absolute", left: map(80, 80)[0] - 40, top: map(80, 80)[1] + 16, opacity: prog(t, 30, 36) }}>REAL TIME</Mono>
      <Path pts={env} p={prog(t, 30, 48)} col={MW.amber} sw={3} head={false} />
      <div style={{ position: "absolute", left: PL.x - 52, top: map(0, 15)[1] - 9, opacity: prog(t, 40, 46) }}><Mono s={14} c={MW.amber} w={700}>15 S</Mono></div>
      <Mono s={15} c={MW.amber} w={700} ls="0.16em" style={{ position: "absolute", left: map(84, ENV(84))[0] - 150, top: map(84, ENV(84))[1] - 44, opacity: prog(t, 46, 52) }}>THE LIMIT</Mono>
      <Path pts={[map(0, HONEST(0)), map(88, HONEST(88))]} p={prog(t, 60, 100)} col={MW.green} sw={3} head={false} />
      <Mono s={15} c={MW.green} w={700} ls="0.16em" style={{ position: "absolute", left: map(62, HONEST(62))[0] + 20, top: map(62, HONEST(62))[1] + 6, opacity: prog(t, 96, 102) }}>HONEST RUN</Mono>
      {pS > 0 ? <Path pts={[map(0, SLOW(0)), map(pS, SLOW(pS))]} p={1} col={MW.red} sw={3.5} head={false} /> : null}
      {pS > 0 ? <Dot at={map(pS, SLOW(pS))} col={MW.red} r={6} /> : null}
      <Mono s={15} c={MW.red} w={700} ls="0.16em" style={{ position: "absolute", left: map(SLOW_P, SLOW(SLOW_P))[0] - 150, top: map(SLOW_P, SLOW(SLOW_P))[1] - 46, opacity: prog(t, SLOW_B - 6, SLOW_B) }}>SLOWED RUN</Mono>
      {out ? (
        <>
          <div style={{ position: "absolute", left: xp[0] - 22, top: xp[1] - 22, width: 44, height: 44, borderRadius: "50%", border: `3px solid ${MW.red}`,
            boxShadow: `0 0 24px ${MW.red}`, transform: `scale(${lerp(2.2, 1, easeOutExpo(prog(t, CROSS_AT, CROSS_AT + 9)))})` }} />
          <Path pts={[[xp[0] - 24, xp[1] - 18], [xp[0] - 60, xp[1] - 46]]} p={prog(t, CROSS_AT + 2, CROSS_AT + 8)} col={MW.red} sw={2} head={false} />
          <div style={{ position: "absolute", right: W - (xp[0] - 60), top: xp[1] - 64, padding: "4px 12px", background: "rgba(5,5,6,0.9)", borderRight: `3px solid ${MW.red}`,
            opacity: prog(t, CROSS_AT + 6, CROSS_AT + 10) }}>
            <Mono s={16} c={MW.red} w={700} ls="0.14em">OUTSIDE THE LIMIT</Mono>
          </div>
        </>
      ) : null}
    </>
  );
};

const Tamper: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Kicker t={t} text="TAMPER // A SLOWED RUN" x={140} y={150} col={MW.red} />
    <Card f={t} at={10} x={140} y={200} w={760} h={340} head="THE RULE // TIME" accent={MW.orange}>
      <Mono s={22} c={MW.text} ls="0.06em" style={{ lineHeight: 1.4 }}>{"EVERY CHECKPOINT MUST BE\nON HEDERA BY:"}</Mono>
      <div style={{ fontFamily: "Archivo Black", fontSize: 44, color: MW.amber, lineHeight: 1.08, marginTop: 14, whiteSpace: "pre" }}>{"START + 15 S\n+ 1.03 x PLAY TIME"}</div>
      <div style={{ borderTop: `1px solid ${MW.faint}`, marginTop: 22, paddingTop: 16 }}>
        <Mono s={18} c={MW.dim} ls="0.06em" style={{ lineHeight: 1.45 }}>{"A 90 S RUN: AT MOST ABOUT 18 S OF\nPAUSE OR SLOW MOTION, IN TOTAL."}</Mono>
      </div>
    </Card>
    <Card f={t} at={64} x={140} y={562} w={760} h={150} head="WHY THE CLOCK" accent={MW.blue} headCol={MW.blue}>
      <Mono s={19} c={MW.text} ls="0.05em" style={{ lineHeight: 1.45 }}>{"THE LOG PROVES WHAT HAPPENED, NOT AT\nWHAT PACE. HEDERA'S TIMESTAMPS BOUND IT."}</Mono>
    </Card>
    <Plot t={t} />
  </>
);

const VROWS = [
  { k: "THE INPUTS REPLAY TO THE CLAIMED TIME", v: "YES", c: MW.green },
  { k: "THE SEED MATCHES START", v: "YES", c: MW.green },
  { k: "THE TIME FITS HEDERA'S CLOCK", v: "NO", c: MW.red },
];
const Void: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Card f={t} at={8} x={420} y={190} w={1080} h={250} head="THE WORKFLOW'S CHECKS // A SLOWED RUN, SCHEMATIC" accent={MW.orange}>
      {VROWS.map((r, i) => (
        <div key={r.k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: 58, borderBottom: `1px solid ${MW.faint}`,
          clipPath: `inset(0 ${100 - 100 * prog(t, 22 + i * 18, 32 + i * 18)}% 0 0)` }}>
          <Mono s={22} c={MW.text} w={700} ls="0.06em">{r.k}</Mono>
          <Mono s={26} c={r.c} w={700} ls="0.16em">{r.v}</Mono>
        </div>
      ))}
    </Card>
    <Head t={t} at={84} text="TIME OUTSIDE HEDERA'S CLOCK" s={50} y={486} col={MW.red} center dur={16} style={{ textShadow: `0 0 30px ${MW.red}66` }} />
    <Stamp f={t} at={VOID_AT} text="VOID" col={MW.red} x={W / 2} y={680} s={110} />
  </>
);

/* ---------- 5. the three outcomes ---------- */

const OUT = [
  { n: "01", w: "VERIFIED", c: MW.green, body: "EVERY CHECK PASSES.\nTHE BOARD LISTS IT.\nPAYOUTS CAN FLOW.", foot: "THE BOARD AND PAYOUTS ACT" },
  { n: "02", w: "VOID", c: MW.red, body: "ONLY WHEN THE EVIDENCE\nPROVES IT: THE REPLAY\nDISAGREES, THE SEED IS\nWRONG, OR THE TIME IS\nOUTSIDE HEDERA'S CLOCK.", foot: "ONLY ON PROOF" },
  { n: "03", w: "PENDING", c: MW.amber, body: "ANYTHING MISSING OR\nEXPIRED: NO RECORD, A\nMIRROR GAP, NO ANSWER.\nASK AGAIN LATER.", foot: "NEVER A BAN" },
];
const OUT_AT = [18, 60, 102];
const Outcomes: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Kicker t={t} text="THREE OUTCOMES // ONE VERDICT A RUN" x={140} y={150} />
    {OUT.map((o, i) => {
      const x = 140 + i * 560, y = 206, at = OUT_AT[i];
      return (
        <React.Fragment key={o.w}>
          <Card f={t} at={at} x={x} y={y} w={520} h={430} head={`OUTCOME ${o.n}`} accent={o.c} headCol={o.c}>
            <div style={{ fontFamily: "Archivo Black", fontSize: 62, color: o.c, letterSpacing: "0.03em", lineHeight: 1, textShadow: `0 0 30px ${o.c}44` }}>{o.w}</div>
            <Mono s={22} c={MW.text} ls="0.03em" style={{ marginTop: 26, lineHeight: 1.45 }}>{o.body}</Mono>
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 4, borderTop: `1px solid ${MW.faint}`, paddingTop: 12 }}>
              <Mono s={16} c={o.c} w={700} ls="0.18em">{o.foot}</Mono>
            </div>
          </Card>
          <Sweep t={t} at={at + 20} x={x} y={y} w={520} h={430} />
        </React.Fragment>
      );
    })}
  </>
);

/* ---------- 6. the field report: the real `cre workflow simulate` output goes here ---------- */

const SIM_CMD = "cre workflow simulate";
const Field: React.FC<{ t: number }> = ({ t }) => {
  const grow = easeOutExpo(prog(t, 4, 14));
  const n = Math.min(SIM_CMD.length, Math.max(0, Math.floor((t - 22) / 2)));
  const typed = 22 + SIM_CMD.length * 2;
  return (
    <>
      <Kicker t={t} text="FIELD REPORT // CRE CLI" x={140} y={150} />
      <div style={{ position: "absolute", left: 140, top: 200, width: 1060, height: 510 * grow, overflow: "hidden", background: "rgba(7,8,9,0.96)",
        border: "1px solid #2a2d31", boxShadow: "0 40px 120px rgba(0,0,0,0.8)" }}>
        <div style={{ height: 40, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 18px", background: "#111315", borderBottom: `2px solid ${MW.orange}` }}>
          <Mono s={15} c={MW.orange} w={700} ls="0.3em">TERMINAL // ETHGLOBAL MUMBAI</Mono>
          <Mono s={13} c={MW.dim} ls="0.24em">ONE MACHINE</Mono>
        </div>
        <div style={{ position: "absolute", left: 30, top: 66, fontFamily: "Space Mono", fontSize: 22, color: MW.text, whiteSpace: "pre" }}>
          <span style={{ color: MW.green }}>$ </span>{SIM_CMD.slice(0, n)}{t < typed + 30 && Math.floor(t / 8) % 2 === 0 ? <span style={{ background: MW.text }}> </span> : null}
        </div>
        <div style={{ position: "absolute", left: 30, right: 30, top: 128, bottom: 30, border: `2px dashed ${ST.col}`, background: `${ST.col}0d`,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 18, opacity: prog(t, typed + 6, typed + 14) }}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 40, color: ST.col, letterSpacing: "0.04em" }}>THE REAL OUTPUT GOES HERE</div>
          <Pill t={t} text="RECORDED AT THE EVENT" col={ST.col} blink />
          <Mono s={16} c={MW.dim} ls="0.14em">NOTHING IS SHOWN HERE UNTIL IT IS REAL</Mono>
        </div>
      </div>
      <Card f={t} at={30} x={1260} y={200} w={520} h={216} head="A SIMULATION, HONESTLY" accent={MW.blue} headCol={MW.blue}>
        <Row k="RUNS ON" v="ONE MACHINE" s={19} />
        <Row k="ITS WRITE" v="A MOCK FORWARDER" s={19} />
        <Row k="SIGNED WITH" v="OUR KEY" s={19} />
        <Row k="IT SHOWS" v="THE WORKFLOW RUNS" s={19} c={MW.green} />
        <Row k="IT IS NOT" v="A NETWORK AGREEING" s={19} c={MW.amber} />
      </Card>
      <Mono s={15} c={MW.dim} ls="0.14em" style={{ position: "absolute", left: 1262, top: 436, lineHeight: 1.5, opacity: prog(t, 70, 80) }}>
        {"DEPLOYED, EVERY NODE RUNS IT,\nAND THEY MUST AGREE: NOT YET."}
      </Mono>
    </>
  );
};

/** A field-report clip from built.json: the real screen recording, what it shows, the values seen on it (Objectives). */
const FieldClip: React.FC<{ f: number; i: number }> = ({ f, i }) => {
  const c = CLIPS[i], t = f - CLIP_AT[i];
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
        <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: t > 8 ? 1 : 0 }}>FIELD REPORT // CHAINLINK CRE</Mono>
        <div style={{ fontFamily: "Archivo Black", fontSize: 40, lineHeight: 1.05, color: MW.text, marginTop: 14, whiteSpace: "pre-wrap",
          clipPath: `inset(0 ${100 - 100 * prog(t, 12, 26)}% 0 0)` }}>{c.title}</div>
      </div>
      <Card f={t} at={30} x={CX} y={MY + 230} w={W - CX - 70} h={60 + 34 * c.rows.length} head="ON SCREEN" accent={MW.green} headCol={MW.green}>
        {c.rows.map(([k, v]) => <Row key={k} k={k} v={v} c={MW.green} s={17} />)}
      </Card>
    </AbsoluteFill>
  );
};

/* ---------- 7. the close ---------- */

const Close: React.FC<{ t: number }> = ({ t }) => (
  <>
    <Kicker t={t} text="ANY% x CHAINLINK CRE" x={0} y={186} center />
    <Head t={t} at={12} text="ONE RUN IN. ONE VERDICT OUT." s={66} y={222} center dur={20} />
    <StatusRow t={t} at={44} y={360} label="THE WORKFLOW: 6 STEPS, 4 HTTP CALLS" status={ST.text} col={ST.col} blink={!DONE} />
    <StatusRow t={t} at={56} y={434} label="SIMULATED WITH THE CRE CLI" status={ST.text} col={ST.col} blink={!DONE} />
    <StatusRow t={t} at={68} y={508} label="DEPLOYED: EVERY NODE RUNS IT, AND THEY MUST AGREE" status="NOT YET" col={MW.dim} />
    <Mono s={19} c={MW.text} ls="0.2em" style={{ position: "absolute", left: 0, width: W, textAlign: "center", top: 630, opacity: prog(t, 100, 116) }}>
      <span style={{ color: MW.dim }}>HEDERA:</span>{" THE CLOCK   "}<span style={{ color: MW.faint }}>//</span>{"   "}<span style={{ color: MW.dim }}>ARKIV:</span>
      {" THE RECORD   "}<span style={{ color: MW.faint }}>//</span>{"   "}<span style={{ color: MW.dim }}>CRE:</span>{" THE REFEREE"}
    </Mono>
  </>
);

/* ---------- the act ---------- */

// the camera of each shot: a scale and the point it pushes in on (the close-up on our server is the same board, nearer)
const CAM: Record<string, { s: number; ox: number; oy: number }> = { trust: { s: 1.3, ox: 780, oy: 525 } };

export const ChainlinkAct: React.FC = () => {
  const f = useCurrentFrame();
  const s = shotAt(f), t = f - s.at, idx = SHOTS.indexOf(s);
  const clip = s.id === "field" ? CLIPS.findIndex((c, i) => f >= CLIP_AT[i] && f < CLIP_AT[i] + clipLen(c)) : -1;
  const cam = CAM[s.id] ?? { s: 1, ox: 960, oy: 518 };
  const push = cam.s * (1 + 0.0066 * (t / 60));
  const shake = s.id === "void" ? kick(t, [VOID_AT], 7) : s.id === "outcomes" ? kick(t, OUT_AT, 3) : "";
  let body: React.ReactNode = null;
  if (s.id === "problem") body = <Problem t={t} />;
  else if (s.id === "trust") body = <Today t={t} trust />;
  else if (s.id === "fix") body = <Fix t={t} />;
  else if (STEPS.includes(s.id)) body = <Step t={t} id={s.id} />;
  else if (s.id === "pipeline") body = <Wide t={t} />;
  else if (s.id === "tamper") body = <Tamper t={t} />;
  else if (s.id === "void") body = <Void t={t} />;
  else if (s.id === "outcomes") body = <Outcomes t={t} />;
  else if (s.id === "field") body = <Field t={t} />;
  else if (s.id === "close") body = <Close t={t} />;
  const cutFlash = idx > 1 && t < 4 && clip < 0 ? 0.22 * (1 - t / 4) : 0;
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {s.id === "slate" ? (
        <Slate f={t} part="ANY% x CHAINLINK" title="THE REFEREE" num="CRE" len={s.len} />
      ) : clip >= 0 ? (
        <FieldClip f={f} i={clip} />
      ) : (
        <AbsoluteFill style={{ transform: `scale(${push.toFixed(5)}) ${shake}`, transformOrigin: `${cam.ox}px ${cam.oy}px` }}>
          <Board f={f} t={0.3 + 0.4 * prog(t, 0, s.len)} dir={idx % 2 ? 0.8 : -0.8}>
            {body}
          </Board>
        </AbsoluteFill>
      )}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.42) 100%)" }} />
      {cutFlash > 0 ? <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: cutFlash }} /> : null}
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, CHAINLINK_LEN - 14, CHAINLINK_LEN)) }} />
    </AbsoluteFill>
  );
};

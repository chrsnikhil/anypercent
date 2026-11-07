import React from "react";
import { Freeze, OffthreadVideo, staticFile } from "remotion";
import { BAR, Line, Mono, MW } from "../acts/common";
import { FONT } from "../theme";
import { easeOutExpo, lerp, prog } from "../util";
import { FPS, sec } from "./kit";
import { LIVE, SAFE } from "./takes";

/* Round 2: phone-legible type, punch-ins on console recordings, the Arkiv and x402 diagrams, real HCS panels. */

/** The intel card at phone size: header 22 px, body set by its rows (Row2, 26-28 px). */
export const Card2: React.FC<{ f: number; at: number; out?: number; x: number; y: number; w: number; h: number; head?: string;
  headCol?: string; accent?: string; children?: React.ReactNode; bg?: string }> = ({ f, at, out = 1e9, x, y, w, h, head, headCol = MW.orange,
  accent = MW.orange, children, bg = "rgba(5,5,5,0.88)" }) => {
  if (f < at || f >= out) return null;
  const g = Math.min(1, Math.floor(prog(f, at, at + 6) * 4) / 4 + (f >= at + 6 ? 1 : 0.25));
  const headOn = f >= at + 7 && !(f >= at + 9 && f < at + 11);
  const wipe = prog(f, at + 10, at + 20);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: w * g, height: h * g, background: bg, borderLeft: `4px solid ${accent}` }} />
      {head && headOn ? <Mono s={22} c={headCol} w={700} ls="0.16em" style={{ position: "absolute", left: 26, top: 18 }}>{head}</Mono> : null}
      <div style={{ position: "absolute", left: 26, right: 24, top: head ? 62 : 22, bottom: 14, clipPath: `inset(0 0 ${100 - 100 * wipe}% 0)` }}>{children}</div>
    </div>
  );
};

export const Row2: React.FC<{ k: string; v: React.ReactNode; c?: string; s?: number }> = ({ k, v, c = MW.text, s = 27 }) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12, gap: 18 }}>
    <Mono s={s - 4} c={MW.dim} ls="0.06em">{k}</Mono>
    <Mono s={s} c={c} w={700}>{v}</Mono>
  </div>
);

/** Subtitles at phone size: 44 px, the speaker tag in blue, a pool of shade behind. */
export const Subs2: React.FC<{ f: number; lines: Line[] }> = ({ f, lines }) => {
  const l = lines.find((q) => f >= q.at && f < q.at + q.len);
  if (!l) return null;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: BAR + 36, textAlign: "center", fontFamily: FONT.sub, fontWeight: 600, fontSize: 44,
      color: "#f4f4f2", textShadow: "0 2px 8px rgba(0,0,0,0.95), 0 0 3px rgba(0,0,0,0.9)" }}>
      <span style={{ display: "inline-block", padding: "14px 120px 16px",
        background: "radial-gradient(ellipse at 50% 55%, rgba(0,0,0,0.82) 0%, rgba(0,0,0,0.62) 52%, rgba(0,0,0,0) 78%)" }}>
        <span style={{ color: MW.blue }}>{l.who}: </span>{l.text}
      </span>
    </div>
  );
};

/** A punch-in on the part of a console recording (800 x 480 px) that matters: crop [x, y, w, h] fills a box w wide. */
export const RecCrop: React.FC<{ file: string; from: number; crop: [number, number, number, number]; x: number; y: number; w: number; f?: number;
  hold?: boolean; glow?: string }> = ({ file, from, crop, x, y, w, f = 0, hold, glow = "124,196,255" }) => {
  const s = w / crop[2], h = crop[3] * s;
  const v = <OffthreadVideo src={staticFile(file)} trimBefore={sec(from)} muted
    style={{ width: 800 * s, height: 480 * s, position: "absolute", left: -crop[0] * s, top: -crop[1] * s, maxWidth: "none" }} />;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, overflow: "hidden", borderRadius: 8, background: "#0b0d10",
      boxShadow: `0 0 0 3px #2a2d31, 0 30px 90px rgba(0,0,0,0.75), 0 0 80px rgba(${glow},0.12)`,
      transform: `scale(${1 + 0.0066 * (f / FPS)})`, transformOrigin: "50% 50%" }}>
      {hold ? <Freeze frame={0}>{v}</Freeze> : v}
    </div>
  );
};

/** A diagram node: a small intel card with a heading and lines, lit when it is the beat's subject. */
const Node: React.FC<{ f: number; at: number; x: number; y: number; w: number; h: number; head: string; lines: string[]; col: string; lit: boolean }> = ({ f, at, x, y, w, h, head, lines: ls, col, lit }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, opacity: f < at ? 0 : lit ? 1 : 0.42,
    clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(f, at, at + 12))}% 0 0)` }}>
    <div style={{ position: "absolute", inset: 0, background: lit ? "rgba(8,10,12,0.94)" : "rgba(8,10,12,0.8)", border: `2px solid ${lit ? col : "#33363a"}`,
      boxShadow: lit ? `0 0 34px ${col}33` : "none" }} />
    <Mono s={22} c={col} w={700} ls="0.12em" style={{ position: "absolute", left: 20, top: 14 }}>{head}</Mono>
    {ls.map((t, i) => (
      <Mono key={i} s={25} c={t.includes("<take") ? MW.amber : MW.text} w={i === 0 ? 700 : 400}
        style={{ position: "absolute", left: 20, top: 54 + i * 34, whiteSpace: "nowrap" }}>{t}</Mono>
    ))}
  </div>
);

/** An arrow between two points with a label; dashed for "points at", a red cross for "cannot". */
const Arrow: React.FC<{ f: number; at: number; a: [number, number]; b: [number, number]; label?: string; col: string; dash?: boolean; no?: boolean;
  lit?: boolean; ly?: number }> = ({ f, at, a, b, label, col, dash, no, lit = true, ly = -16 }) => {
  const k = easeOutExpo(prog(f, at, at + 14));
  if (k <= 0) return null;
  const ex = lerp(a[0], b[0], k), ey = lerp(a[1], b[1], k);
  const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity: lit ? 1 : 0.4 }} width={10} height={10}>
      <line x1={a[0]} y1={a[1]} x2={ex} y2={ey} stroke={col} strokeWidth={4} strokeDasharray={dash ? "12 10" : undefined} />
      {k > 0.95 ? <polygon points={`${b[0]},${b[1]} ${b[0] - 18 * Math.cos(ang - 0.42)},${b[1] - 18 * Math.sin(ang - 0.42)} ${b[0] - 18 * Math.cos(ang + 0.42)},${b[1] - 18 * Math.sin(ang + 0.42)}`} fill={col} /> : null}
      {no && k > 0.95 ? (
        <g stroke={MW.red} strokeWidth={7}>
          <line x1={mx - 20} y1={my - 20} x2={mx + 20} y2={my + 20} />
          <line x1={mx + 20} y1={my - 20} x2={mx - 20} y2={my + 20} />
        </g>
      ) : null}
      {label && k > 0.6 ? <text x={mx} y={my + ly} fill={no ? MW.red : col} fontFamily={FONT.ui} fontWeight={700} fontSize={22} textAnchor="middle"
        style={{ paintOrder: "stroke", stroke: "#050607", strokeWidth: 7 }}>{label}</text> : null}
    </svg>
  );
};

/** Arkiv after the switch-over, as a diagram: the console signs its record, the checker stamps it, the board reads.
    `beat` lights the part the scene is about. Laid out in a 1240 x 520 box at (x, y). */
export type ArkivBeat = "sign" | "stamp" | "own" | "query" | "lookalike";
export const ArkivFlow: React.FC<{ f: number; x: number; y: number; beat: ArkivBeat }> = ({ f, x, y, beat }) => {
  if (SAFE && !LIVE) return <SafeFlow f={f} x={340} y={y} beat={beat} />;
  const lit = (...b: ArkivBeat[]) => b.includes(beat);
  const BL = MW.blue, OR = MW.orange, GR = MW.green;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: 1240, height: 520 }}>
      <Node f={f} at={4} x={0} y={0} w={350} h={150} head="THE CONSOLE" lines={["its own wallet", LIVE ? "0xda28...2f89" : "<take: 0x...>"]} col={OR} lit={lit("sign", "own")} />
      <Node f={f} at={12} x={450} y={0} w={440} h={150} head="ARKIV // RUN + LISTING" lines={["owner: the console", "read-only rows"]} col={BL} lit={lit("sign", "own", "query")} />
      <Node f={f} at={20} x={0} y={320} w={350} h={150} head="OUR CHECKER" lines={["replays the log", "0x3d32...3f63"]} col={GR} lit={lit("stamp", "own")} />
      <Node f={f} at={28} x={450} y={320} w={440} h={150} head="ARKIV // STAMP" lines={["creator: the checker", "run, console, frames"]} col={BL} lit={lit("stamp", "query")} />
      <Node f={f} at={36} x={990} y={160} w={250} h={150} head="THE BOARD" lines={["ranks", "stamped runs"]} col={OR} lit={lit("stamp", "query", "lookalike")} />
      <Arrow f={f} at={10} a={[350, 75]} b={[446, 75]} label="signs" col={OR} lit={lit("sign", "own")} />
      <Arrow f={f} at={26} a={[350, 395]} b={[446, 395]} label="stamps" col={GR} lit={lit("stamp")} />
      <Arrow f={f} at={32} a={[760, 320]} b={[760, 156]} label="points at" col={BL} dash lit={lit("stamp")} ly={6} />
      <Arrow f={f} at={40} a={[890, 75]} b={[986, 200]} col={BL} lit={lit("query", "stamp")} />
      <Arrow f={f} at={40} a={[890, 395]} b={[986, 270]} col={BL} lit={lit("query", "stamp")} />
      {lit("own") ? <Arrow f={f} at={46} a={[250, 320]} b={[520, 156]} label="can't change, delete, own" col={MW.red} no lit ly={-26} /> : null}
      {lit("query") ? <Node f={f} at={46} x={990} y={340} w={250} h={150} head="ANYONE" lines={["same query", "no key"]} col={GR} lit /> : null}
      {lit("lookalike") ? <Node f={f} at={44} x={990} y={340} w={250} h={150} head="LOOK-ALIKE" lines={["no stamp:", "ignored"]} col={MW.red} lit /> : null}
    </div>
  );
};

/** The x402 payment as a diagram; values from the earlier real purchase (HCS INTENT #12, RECEIPT #13). */
export const PayFlow: React.FC<{ f: number; x: number; y: number }> = ({ f, x, y }) => (
  <div style={{ position: "absolute", left: x, top: y, width: 1780, height: 470 }}>
    <Node f={f} at={4} x={0} y={0} w={340} h={150} head="PB'S SCOUT" lines={["picked BOT-A3", "lap 1, -1.29 s"]} col={MW.blue} lit />
    <Node f={f} at={14} x={420} y={0} w={420} h={150} head="THE GHOST'S PAYWALL" lines={["402: pay 0.10 USDC", "to 0.0.11333910"]} col={MW.orange} lit />
    <Node f={f} at={24} x={920} y={0} w={420} h={186} head="PB'S GUARDS, IN CODE" lines={["<= 0.10 a ghost", "<= 1.00 a book a day", "payTo = the listing"]} col={MW.green} lit />
    <Node f={f} at={34} x={1420} y={0} w={360} h={150} head="HEDERA TESTNET" lines={["0.10 USDC settled", "via x402.org"]} col={MW.blue} lit />
    <Arrow f={f} at={10} a={[340, 75]} b={[416, 75]} col={MW.blue} />
    <Arrow f={f} at={20} a={[840, 75]} b={[916, 75]} col={MW.orange} />
    <Arrow f={f} at={30} a={[1340, 75]} b={[1416, 75]} col={MW.green} />
    <Node f={f} at={44} x={420} y={270} w={560} h={150} head="HCS #12 INTENT, BEFORE SIGNING" lines={["openai/gpt-oss-120b", "left today: 0.80 USDC"]} col={MW.amber} lit />
    <Node f={f} at={54} x={1060} y={270} w={600} h={150} head="HCS #13 RECEIPT, AFTER" lines={["0.0.11332435 > 0.0.11333910", "mirror: SUCCESS"]} col={MW.amber} lit />
  </div>
);

/** A decoded HCS message (mirror node), real values only. */
export const HcsPanel: React.FC<{ f: number; x: number; y: number; w: number; h: number; head: string; sub: string; rows: [string, string, string?][] }> = ({ f, x, y, w, h, head, sub, rows }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, background: "#0d0f12", border: "1px solid #2b2e33", borderRadius: 8,
    boxShadow: "0 30px 90px rgba(0,0,0,0.7)", overflow: "hidden" }}>
    <div style={{ height: 58, background: "#171a1e", display: "flex", alignItems: "center", padding: "0 26px", gap: 22 }}>
      <Mono s={25} c={MW.amber} w={700} ls="0.08em">{head}</Mono>
      <Mono s={21} c="#8b949e">{sub}</Mono>
    </div>
    <div style={{ padding: "22px 32px" }}>
      {rows.map(([k, v, c], i) => (
        <div key={i} style={{ display: "flex", gap: 26, marginBottom: 12, opacity: prog(f, 6 + i * 5, 12 + i * 5) }}>
          <Mono s={25} c="#8b949e" style={{ width: 200, flexShrink: 0 }}>{k}</Mono>
          <Mono s={27} c={c ?? "#e6edf3"} w={700} style={{ whiteSpace: "pre-wrap" }}>{v}</Mono>
        </div>
      ))}
    </div>
  </div>
);

/** A real line of text, quoted large (an approved action, as recorded on HCS). */
export const Quote: React.FC<{ f: number; at: number; x: number; y: number; w: number; head: string; text: string; foot?: string }> = ({ f, at, x, y, w, head, text, foot }) => {
  if (f < at) return null;
  const k = easeOutExpo(prog(f, at, at + 16));
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, background: "rgba(6,7,8,0.93)", borderLeft: `5px solid ${MW.amber}`, padding: "22px 34px 26px",
      clipPath: `inset(0 ${100 - 100 * k}% 0 0)` }}>
      <Mono s={22} c={MW.amber} w={700} ls="0.14em">{head}</Mono>
      <div style={{ fontFamily: FONT.sub, fontWeight: 600, fontSize: 40, lineHeight: 1.25, color: "#f4f4f2", marginTop: 14 }}>{`"${text}"`}</div>
      {foot ? <Mono s={21} c={MW.dim} style={{ marginTop: 14 }}>{foot}</Mono> : null}
    </div>
  );
};

/** A label with an arrow pointing at something on screen (the ghost kart in the race). */
export const Pointer: React.FC<{ f: number; at: number; x: number; y: number; label: string; col?: string; dx?: number; dy?: number }> = ({ f, at, x, y, label, col = MW.blue, dx = 150, dy = -110 }) => {
  if (f < at) return null;
  const k = easeOutExpo(prog(f, at, at + 12));
  return (
    <>
      <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={10} height={10}>
        <circle cx={x} cy={y} r={34 + 6 * Math.sin(f / 6)} fill="none" stroke={col} strokeWidth={4} opacity={k} />
        <line x1={x + dx * k} y1={y + dy * k} x2={x + 26} y2={y - 22} stroke={col} strokeWidth={4} opacity={k} />
      </svg>
      <div style={{ position: "absolute", left: x + dx, top: y + dy - 44, opacity: k, background: "rgba(5,6,8,0.9)", border: `3px solid ${col}`, padding: "6px 16px 8px" }}>
        <Mono s={30} c={col} w={700} ls="0.08em">{label}</Mono>
      </div>
    </>
  );
};

/** What the model decides and what code decides (scene 14's close): the real pick on the left, PB's guards right. */
export const ModelCode: React.FC<{ f: number; x: number; y: number }> = ({ f, x, y }) => (
  <div style={{ position: "absolute", left: x, top: y, width: 1780, height: 300 }}>
    <Node f={f} at={4} x={0} y={0} w={820} h={226} head="THE MODEL // gpt-oss-120b ON GROQ" lines={["picks which ghost: BOT-A2 1:43.93", "\"You lose 2.85 s on lap 2,", "this ghost is fastest there.\""]} col={MW.blue} lit />
    <Node f={f} at={30} x={960} y={0} w={820} h={226} head="CODE // PB'S GUARDS" lines={["whether: only under the caps", "how much: 0.10 USDC at most", "to whom: the listing's payTo"]} col={MW.green} lit />
    <Arrow f={f} at={22} a={[820, 113]} b={[956, 113]} label="then" col={MW.dim} />
  </div>
);

/** SAFE mode's Arkiv diagram: only what is true of the build before and after the switch-over (no console-signed
    record, no stamp): the console sends its run, our checker replays it, Arkiv keeps read-only rows with their writer,
    the board and anyone read them. */
const SafeFlow: React.FC<{ f: number; x: number; y: number; beat: ArkivBeat }> = ({ f, x, y, beat }) => {
  const lit = (...b: ArkivBeat[]) => b.includes(beat);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: 1240, height: 520 }}>
      <Node f={f} at={4} x={0} y={0} w={270} h={150} head="THE CONSOLE" lines={["sends its run", "and its log"]} col={MW.orange} lit={lit("sign")} />
      <Node f={f} at={12} x={310} y={0} w={290} h={150} head="OUR CHECKER" lines={["replays the log", "0x3d32...3f63"]} col={MW.green} lit={lit("stamp")} />
      <Node f={f} at={20} x={640} y={0} w={320} h={150} head="ARKIV" lines={["read-only rows,", "with their writer"]} col={MW.blue} lit={lit("sign", "stamp", "own", "query")} />
      <Node f={f} at={28} x={1000} y={0} w={240} h={150} head="THE BOARD" lines={["reads Arkiv,", "ranks runs"]} col={MW.orange} lit={lit("stamp", "query", "lookalike")} />
      <Arrow f={f} at={10} a={[270, 75]} b={[306, 75]} col={MW.orange} lit={lit("sign")} />
      <Arrow f={f} at={18} a={[600, 75]} b={[636, 75]} col={MW.green} lit={lit("stamp")} />
      <Arrow f={f} at={26} a={[960, 75]} b={[996, 75]} col={MW.blue} lit={lit("stamp", "query")} />
      {lit("query") ? <Node f={f} at={36} x={640} y={300} w={320} h={150} head="ANYONE" lines={["the same query,", "no key"]} col={MW.green} lit /> : null}
      {lit("query") ? <Arrow f={f} at={44} a={[800, 300]} b={[800, 156]} label="reads" col={MW.green} ly={6} /> : null}
      {lit("lookalike") ? <Node f={f} at={36} x={1000} y={300} w={240} h={150} head="LOOK-ALIKE" lines={["a stranger's", "row: ignored"]} col={MW.red} lit /> : null}
      {lit("lookalike") ? <Arrow f={f} at={44} a={[1120, 300]} b={[1120, 156]} col={MW.red} no /> : null}
    </div>
  );
};

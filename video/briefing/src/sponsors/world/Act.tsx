import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import RUN from "../../../public/handler/run.json";
import PROOF from "../../../public/proof.json";
import SCREENS from "../../../public/sponsors/world/screens.json";
import BUILT from "../../acts/built.json";
import { BAR, Bars, Card, kick, Line, Mono, MW, Row, Slate, Stamp, Subs, W } from "../../acts/common";
import { Board } from "../../acts/GameReel";
import { clamp, easeInOut, easeOutExpo, lerp, prog } from "../../util";
import T from "./timing.json";

/* ANY% x WORLD (SPONSOR_DEMOS.md): an argument that World is what makes Any%'s verdicts land, built on the World judges'
   own booth question ("you already have anti-cheat, why World?", "just ban the run"):
     HOOK       their question, typed out; the answer in one line: a ban that lands on a person, not a wallet.
     THE LOOP   without World: the cheater's run is VOID, a new wallet, the same cheat, back on the board; three times,
                with a counter (accounts 1, 2, 3, cost free).
     WITH WORLD IDKit at sign-up (the real launcher's id_scan); the same cheat fails the check (VOID) and, because the run
                carried its owner's approval, the finding goes on that record book; another console's coach refuses to
                pay (the launcher's buy_suspended); the same person signs up again: same nullifier, REFUSED (id_dup).
                "BANNING THE RUN STOPS A RUN. WORLD STOPS THE CHEATER."
     PRECEDENT  hardware bans and phone numbers are stand-ins for "same person"; World ID is the real one.
     THE BOT    a bot's run is legal and replays perfectly (run.json: the board's 1:41.58, played by a script on the ROM,
                fingerprint B872DDD7 both ways); World's answer is two tiers: an open tier for machines, a human tier
                where every record book has one World ID behind it. World doesn't detect the bot; it bounds the books.
     THE MONEY  coaches pay runners; one person with 20 wallets is 20 rows and 20 payment streams; with World, one.
     CONSENT    Agent Pass: the coach agent drafts a listing; nothing happens until you approve in World App (ls_scan,
                ls_approve, ls_done). An approval allows one future action by that account, once.
     SCOPE      "World doesn't watch the controller. It makes sure every record book has one human behind it." Mock
                identities at the event, Orb-class in production.
     CLOSE      "The anti-cheat judges runs. World makes the verdict land on a person." "One human. One record book."
   The console's screens are the real launcher, drawn by its own code over its MockSponsors (prep/sponsors/world.py; the
   MOCK pill stays on screen). Wording follows the red-teamed World design (memory: world-agent-pass-angles): never who
   held the controller; uniqueness is World's guarantee; no earn/win/cash out/payout/staked/human ghost.
   Honesty: the World calls are built at the event, so until built.json has world: true every call card reads
   CALL: AT THE EVENT (UI: BUILT where the launcher screen exists). No value on a card is invented: the replay values
   are proof.json and run.json; codes, book names and wallets appear only on the launcher's own mock screens.
   FIELD REPORT: when built.json gains WORLD ID clips (real screen recordings in public/built/), they play in the field
   slot (before the scope), as in Objectives.tsx, and the act grows by their length. */

type Clip = { file: string; sponsor: string; title: string; rows: [string, string][]; line: string; seconds: number; from?: number };
type ShotDef = { id: string; len: number; cards?: number[]; hits?: number[]; cuts?: number[]; chirps?: number[]; glitch?: number[]; typing?: number[][] };
type Shot = ShotDef & { at: number; i: number };
type TLine = { shot: string; at: number; len: number; text: string; built?: string };

const CLIPS = (BUILT.clips as unknown as Clip[]).filter((c) => String(c.sponsor).toUpperCase() === "WORLD ID");
const DONE = (BUILT.built as Record<string, boolean>).world === true;
const clipLen = (c: Clip) => Math.round(c.seconds * 60);
const FIELD = CLIPS.reduce((n, c) => n + clipLen(c), 0);
const SHOTS: Shot[] = (() => {
  let a = 0;
  return (T.shots as ShotDef[]).map((s, i) => {
    const len = s.id === "field" ? FIELD : s.len;
    const o = { ...s, len, at: a, i };
    a += len;
    return o;
  });
})();
const SH = Object.fromEntries(SHOTS.map((s) => [s.id, s])) as Record<string, Shot>;
export const WORLD_LEN = SHOTS[SHOTS.length - 1].at + SHOTS[SHOTS.length - 1].len;
const CLIP_AT = CLIPS.map((_, i) => SH.field.at + CLIPS.slice(0, i).reduce((n, c) => n + clipLen(c), 0));
const LINES: Line[] = [
  ...(T.lines as TLine[]).map((l) => ({ at: SH[l.shot].at + l.at, len: l.len, who: "Handler", text: DONE && l.built ? l.built : l.text })),
  ...CLIPS.map((c, i) => ({ at: CLIP_AT[i] + 16, len: clipLen(c) - 28, who: "Handler", text: c.line })),
].sort((a, b) => a.at - b.at);
const shotAt = (f: number) => SHOTS.reduce((k, s) => (f >= s.at && s.len > 0 ? s : k), SHOTS[0]);
const lastCut = (t: number, s: Shot) => (s.cuts ?? []).reduce((a, c) => (t >= c ? c : a), 0);

const S = SCREENS as { images: Record<string, number>; every: number };
const R = RUN as { run: { time_frames: number; final_hash: number; claimed_hash: number; hash_matches: boolean } };
const P = PROOF as { log_bytes: number; claimed_hash: string; tampered_byte: number; tampered_hash: string };
const hex = (n: number) => (n >>> 0).toString(16).toUpperCase().padStart(8, "0");
const fmt = (fr: number) => {
  const cs = Math.round((fr * 100) / 60);
  return `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
};
const pad2 = (n: number) => String(n).padStart(2, "0");
const CALL = DONE ? { text: "CALL: BUILT", col: MW.green, blink: false } : { text: "CALL: AT THE EVENT", col: MW.amber, blink: true };
const L = 150;                                                         // the left margin of the board's text
const ARCHIVO = "Archivo Black";

/* ---------- small parts ---------- */

const Kick: React.FC<{ t: number; text: string; x?: number; y?: number; at?: number; col?: string; center?: boolean }> = ({ t, text, x = L, y = 192, at = 6, col = MW.orange, center }) => (
  <Mono s={17} c={col} w={700} ls="0.4em" style={{ position: "absolute", left: center ? 0 : x, top: y, width: center ? W : undefined, textAlign: center ? "center" : undefined,
    opacity: t > at && !(t > at + 3 && t < at + 6) ? 1 : 0 }}>{text}</Mono>
);

const Head: React.FC<{ t: number; at: number; x?: number; y: number; s: number; text: string; col?: string; center?: boolean; glow?: string }> = ({ t, at, x = L, y, s, text, col = MW.text, center, glow }) => (
  <div style={{ position: "absolute", left: center ? 0 : x, width: center ? W : undefined, textAlign: center ? "center" : undefined, top: y, fontFamily: ARCHIVO, fontSize: s,
    lineHeight: 1.05, color: col, whiteSpace: "pre", letterSpacing: "0.02em", textShadow: glow ? `0 0 40px ${glow}` : undefined,
    clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, at, at + 16))}% 0 0)` }}>{text}</div>
);

const Tag: React.FC<{ t: number; text: string; col: string; blink?: boolean }> = ({ t, text, col, blink }) => (
  <div style={{ display: "inline-flex", gap: 10, alignItems: "center", padding: "4px 12px 5px", border: `2px solid ${col}`, background: `${col}1f` }}>
    <div style={{ width: 10, height: 10, background: col, opacity: blink && t % 40 >= 26 ? 0.25 : 1 }} />
    <Mono s={16} c={col} w={700} ls="0.16em">{text}</Mono>
  </div>
);

const Title: React.FC<{ s?: number; c?: string; children: React.ReactNode; style?: React.CSSProperties }> = ({ s = 36, c = MW.text, children, style }) => (
  <div style={{ fontFamily: ARCHIVO, fontSize: s, color: c, lineHeight: 1.05, letterSpacing: "0.02em", whiteSpace: "pre", ...style }}>{children}</div>
);

/** The dark intel board behind a shot: its angle alternates cut to cut, the measured creep restarts at each cut, and
    stamps kick the camera. */
const OnBoard: React.FC<{ t: number; s: Shot; children: React.ReactNode }> = ({ t, s, children }) => {
  const c0 = lastCut(t, s), k = (s.cuts ?? []).filter((c) => t >= c).length;
  const end = (s.cuts ?? []).find((c) => c > t) ?? s.len;
  const lt = t - c0;
  return (
    <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (lt / 60)})`, transformOrigin: "50% 48%" }}>
      <Board f={s.at + t} t={0.3 + 0.4 * clamp(lt / Math.max(1, end - c0))} dir={(s.i + k) % 2 ? 0.8 : -0.8}>
        <div style={{ position: "absolute", inset: 0, transform: kick(t, s.hits ?? [], 7) }}>{children}</div>
      </Board>
    </AbsoluteFill>
  );
};

/** A plain dark plate for the big lines, the act's own slate look. */
const Plate: React.FC<{ t: number; s: Shot; children: React.ReactNode }> = ({ t, s, children }) => (
  <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 46%, #15181b 0%, #0a0c0e 55%, #030405 100%)" }}>
    <div style={{ position: "absolute", inset: 0, opacity: 0.12, backgroundSize: "64px 64px",
      backgroundImage: "linear-gradient(rgba(124,196,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.35) 1px, transparent 1px)" }} />
    <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (t / 60)}) ${kick(t, s.hits ?? [], 6)}`, transformOrigin: "50% 48%" }}>{children}</AbsoluteFill>
  </AbsoluteFill>
);

/** A plain person: the thing World ID counts. */
const Person: React.FC<{ x: number; y: number; s?: number; col?: string; op?: number }> = ({ x, y, s = 1, col = MW.text, op = 1 }) => (
  <div style={{ position: "absolute", left: x - 90 * s, top: y, width: 180 * s, height: 210 * s, opacity: op, filter: `drop-shadow(0 0 18px ${col}66)` }}>
    <div style={{ position: "absolute", left: 50 * s, top: 0, width: 80 * s, height: 80 * s, borderRadius: "50%", background: col }} />
    <div style={{ position: "absolute", left: 0, top: 94 * s, width: 180 * s, height: 116 * s, borderRadius: `${90 * s}px ${90 * s}px ${10 * s}px ${10 * s}px`, background: col }} />
  </div>
);

/* ---------- the console's screen, as Handler.tsx draws it ---------- */

const MX = 90, MY = BAR + 74, MW_ = 1065, MH = 639, CX = MX + MW_ + 50, CW = W - CX - 70, CY = MY + 36;

/** The real launcher on the monitor: seq is [state, from frame] pairs, cut hard from one to the next. */
const Monitor: React.FC<{ t: number; seq: [string, number][]; caption: string }> = ({ t, seq, caption }) => {
  const k = seq.reduce((i, [, a], j) => (t >= a ? j : i), 0);
  const [state, a] = seq[k];
  const img = clamp(Math.floor((t - a) / S.every), 0, S.images[state] - 1);
  const on = prog(t, 0, 10);
  const flash = clamp(1 - (t - a) / 4) * 0.35;
  return (
    <>
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MW_ + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MW_, height: MH, overflow: "hidden", background: "#000", transform: `scaleY(${lerp(0.02, 1, easeInOut(on))})` }}>
        <Img src={staticFile(`sponsors/world/${state}/${String(img).padStart(3, "0")}.jpg`)} style={{ width: "100%", height: "100%" }} />
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      </div>
      <div style={{ position: "absolute", left: MX, top: MY - 46, opacity: prog(t, 6, 12) }}>
        <Mono s={15} c={MW.text} w={700} ls="0.28em">{caption}</Mono>
      </div>
    </>
  );
};

/** The card beside the monitor: what this screen is, in the design's words, and its build status. */
const Side: React.FC<{ t: number; at: number; head: string; title: string; rows: [string, string, string?][]; h?: number; ts?: number; note?: string; noteCol?: string }> = ({ t, at, head, title, rows, h = 380, ts = 36, note, noteCol = MW.dim }) => (
  <>
    <Card f={t} at={at} x={CX} y={CY} w={CW} h={h} head={head} accent={MW.blue} headCol={MW.blue}>
      <Title s={ts}>{title}</Title>
      <div style={{ marginTop: 20 }}>{rows.map(([k, v, c]) => <Row key={k} k={k} v={v} c={c ?? MW.text} s={19} />)}</div>
      <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", gap: 12 }}>
        <Tag t={t} text="UI: BUILT" col={MW.green} />
        <Tag t={t} {...CALL} />
      </div>
    </Card>
    {note ? <Mono s={18} c={noteCol} ls="0.1em" style={{ position: "absolute", left: CX + 4, top: CY + h + 22, lineHeight: 1.45, opacity: prog(t, at + 40, at + 52) }}>{note}</Mono> : null}
  </>
);

/* ---------- the shots ---------- */

/** Their question, typed; then the answer in one line, and the road map. */
const Hook: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const [[a1, , st1], [a2, , st2]] = s.typing!;
  const l1 = "YOU ALREADY HAVE ANTI-CHEAT.", l2 = "WHY WORLD?";
  const n1 = clamp(Math.floor((t - a1) / (st1 / 2)), 0, l1.length), n2 = clamp(Math.floor((t - a2) / (st2 / 2)), 0, l2.length);
  const on2 = t >= a2, cur = Math.floor(t / 15) % 2 === 0;
  const Cursor: React.FC<{ h: number }> = ({ h }) => <span style={{ display: "inline-block", width: h * 0.42, height: h * 0.78, marginLeft: h * 0.08, background: MW.orange, opacity: cur ? 0.9 : 0, verticalAlign: "-0.06em" }} />;
  return (
    <>
      <Kick t={t} text="THE QUESTION // ASKED AT THE WORLD BOOTH" />
      <div style={{ position: "absolute", left: L, top: 246, fontFamily: ARCHIVO, fontSize: 72, lineHeight: 1.05, color: MW.text, whiteSpace: "pre", letterSpacing: "0.02em" }}>
        {l1.slice(0, n1)}{!on2 && t >= a1 ? <Cursor h={72} /> : null}
      </div>
      <div style={{ position: "absolute", left: L, top: 334, fontFamily: ARCHIVO, fontSize: 132, lineHeight: 1.05, color: MW.blue, whiteSpace: "pre", letterSpacing: "0.02em",
        textShadow: "0 0 50px rgba(124,196,255,0.3)" }}>
        {l2.slice(0, n2)}{on2 && t < s.chirps![0] ? <Cursor h={132} /> : null}
      </div>
      <Head t={t} at={s.chirps![0]} y={520} s={46} text="A BAN THAT LANDS ON A PERSON, NOT A WALLET." col={MW.amber} />
      <Mono s={20} c={MW.dim} ls="0.2em" style={{ position: "absolute", left: L + 4, top: 604, opacity: prog(t, s.chirps![1], s.chirps![1] + 10) }}>
        THE LOOP  //  THE BOT  //  THE MONEY  //  CONSENT
      </Mono>
    </>
  );
};

/** Without World: VOID, a new wallet, the same cheat, back on the board, cut hard each time round, counted. */
const Loop: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const starts = [0, ...s.cuts!];
  const k = starts.reduce((i, a, j) => (t >= a ? j : i), 0);
  const ct = t - starts[k];
  const voidAt = k < s.hits!.length ? s.hits![k] - starts[k] : 1e9;
  const voided = s.hits!.filter((h) => t >= h).length;
  const state = ct < 34 ? { text: "SUBMITTING", col: MW.dim } : ct < voidAt ? { text: "ON THE BOARD", col: MW.green } : null;
  const RX = L, RY = 290, RW = 1100, RH = 176;
  const arc = prog(ct, voidAt + 18, voidAt + 46), yb = RY + RH + 24, xl = RX - 34, xr = RX + RW + 34;
  const len = (xr - xl) + 2 * (yb + 120 - (RY + RH / 2));
  return (
    <>
      <Kick t={t} text="WITHOUT WORLD // THE LOOP" col={MW.red} />
      <Card f={ct} at={6} x={RX} y={RY} w={RW} h={RH} head={`ACCOUNT ${pad2(k + 1)} // A NEW WALLET`} accent={ct >= voidAt ? MW.red : MW.orange}>
        <Title s={58}>{`ACCOUNT ${pad2(k + 1)}`}</Title>
        <Mono s={20} c={MW.text} ls="0.12em" style={{ marginTop: 14 }}>SAME PERSON. SAME CHEAT. NEW RUN.</Mono>
        {state ? <Title s={40} c={state.col} style={{ position: "absolute", right: 0, top: 10 }}>{state.text}</Title> : null}
      </Card>
      <Stamp f={ct} at={voidAt} text="VOID" col={MW.red} x={RX + 880} y={RY + 92} s={104} />
      {arc > 0 ? (
        <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={10} height={10}>
          <path d={`M ${xr - 30} ${RY + RH / 2} L ${xr} ${RY + RH / 2} L ${xr} ${yb + 120} L ${xl} ${yb + 120} L ${xl} ${RY + RH / 2} L ${RX - 8} ${RY + RH / 2}`}
            fill="none" stroke={MW.amber} strokeWidth={3} strokeDasharray={`${len * arc} ${len * 2}`} />
          {arc >= 1 ? <path d={`M ${RX - 22} ${RY + RH / 2 - 9} L ${RX - 6} ${RY + RH / 2} L ${RX - 22} ${RY + RH / 2 + 9} Z`} fill={MW.amber} /> : null}
        </svg>
      ) : null}
      <Mono s={22} c={MW.amber} w={700} ls="0.24em" style={{ position: "absolute", left: RX + 30, top: yb + 50, opacity: arc > 0.3 && ct % 20 < 14 ? 1 : 0 }}>
        MAKING A NEW WALLET... FREE
      </Mono>
      <Card f={t} at={s.cards![0]} x={1330} y={RY} w={440} h={250} head="THE TALLY" accent={MW.red} headCol={MW.red}>
        <Row k="ACCOUNTS" v={String(k + 1)} s={26} />
        <Row k="RUNS VOIDED" v={String(voided)} s={26} />
        <Row k="COST" v="FREE" c={MW.green} s={26} />
        <Row k="CHEATER STOPPED" v="NO" c={MW.red} s={26} />
      </Card>
    </>
  );
};

const Signup: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Monitor t={t} seq={[["id_scan", 0]]} caption="WITH WORLD // THE CONSOLE'S SCREEN, DRAWN BY THE LAUNCHER // MOCK SPONSORS" />
    <Side t={t} at={s.cards![0]} head="WITH WORLD // IDKIT" title="SIGN-UP, ONCE" h={330}
      rows={[["ASKS", "A UNIQUE HUMAN?"], ["KEEPS", "ONE CODE PER PERSON"], ["NEVER KEPT", "NAME OR FACE"]]}
      note={"SAME HUMAN, SAME ACTION:\nTHE SAME NULLIFIER, EVERY TIME."} noteCol={MW.blue} />
  </>
);

const VoidChain: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const N = [
    { k: "01 // THE CHECK", t: "VOID", s: "THE SAME CHEAT\nFAILS THE REPLAY", built: true },
    { k: "02 // ITS RECORD BOOK", t: "A FINDING", s: "THE RUN CARRIED ITS\nOWNER'S APPROVAL", built: DONE },
    { k: "03 // EVERY CONSOLE", t: "SALES STOP", s: "COACHES READ THE\nBOOK BEFORE PAYING", built: DONE },
    { k: "04 // A NEW SIGN-UP", t: "REFUSED", s: "SAME PERSON,\nSAME NULLIFIER", built: DONE },
  ];
  const NW = 380, GAP = 33, Y = 300, NH = 250;
  return (
    <>
      <Kick t={t} text="WITH WORLD // THE VERDICT LANDS ON A PERSON" col={MW.blue} />
      {N.map((n, i) => {
        const at = s.cards![i], col = n.built ? MW.green : MW.amber, x = L + i * (NW + GAP);
        const draw = prog(t, at + 12, at + 22);
        return (
          <React.Fragment key={n.k}>
            <Card f={t} at={at} x={x} y={Y} w={NW} h={NH} head={n.k} accent={i === 0 ? MW.red : MW.blue} headCol={i === 0 ? MW.red : MW.blue}>
              <Title s={44} c={i === 0 ? MW.red : MW.text}>{n.t}</Title>
              <Mono s={18} style={{ marginTop: 16, lineHeight: 1.4 }}>{n.s}</Mono>
              <div style={{ position: "absolute", left: 0, bottom: 4, display: "flex", gap: 10, alignItems: "center" }}>
                <div style={{ width: 10, height: 10, background: col, opacity: n.built || t % 40 < 26 ? 1 : 0.25 }} />
                <Mono s={16} c={col} w={700} ls="0.18em">{n.built ? (i === 0 ? "CHECK: BUILT" : "CALL: BUILT") : "CALL: AT THE EVENT"}</Mono>
              </div>
            </Card>
            {i < 3 && draw > 0 ? (
              <div style={{ position: "absolute", left: x + NW + 4, top: Y + NH / 2 - 1, width: (GAP - 8) * draw, height: 2, background: MW.text, opacity: 0.85 }} />
            ) : null}
          </React.Fragment>
        );
      })}
      <Mono s={18} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: L + 4, top: Y + NH + 34, lineHeight: 1.45, opacity: prog(t, 130, 142) }}>
        {"THE REPLAY CHECK VOIDS THE RUN. WORLD IS WHAT LETS THE FINDING FOLLOW THE PERSON."}
      </Mono>
    </>
  );
};

const Suspended: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Monitor t={t} seq={[["buy_suspended", 0]]} caption="ANOTHER CONSOLE // ITS COACH, ABOUT TO BUY // MOCK SPONSORS" />
    <Side t={t} at={s.cards![0]} head="ANOTHER CONSOLE // ITS COACH" title="PAYS NOTHING" h={370}
      rows={[["CHECKS", "THE SELLER'S BOOK"], ["FINDS", "A FRAUD FINDING"], ["THE SALE", "SUSPENDED", MW.red], ["ALREADY PAID", "STAYS PAID"]]}
      note={"EVERY CONSOLE'S COACH READS\nTHE SAME RECORD BOOK."} />
  </>
);

const Dup: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Monitor t={t} seq={[["id_dup", 0]]} caption="SAME PERSON, NEW WALLET, NEW SIGN-UP // MOCK SPONSORS" />
    <Side t={t} at={s.cards![0]} head="SAME PERSON // NEW WALLET" title="SIGNS UP AGAIN" h={330}
      rows={[["IDKIT PROOF", "SAME NULLIFIER"], ["SECOND BOOK", "REFUSED", MW.red], ["ACCOUNTS", "STILL ONE", MW.blue]]} />
    <Stamp f={t} at={s.hits![0]} text="REFUSED" col={MW.red} x={CX + CW / 2} y={CY + 330 + 110} s={72} sub="THE LOOP ENDS" />
  </>
);

const LineShot: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <Plate t={t} s={s}>
    <Head t={t} at={s.chirps![0]} center y={388} s={80} text="BANNING THE RUN STOPS A RUN." />
    <Head t={t} at={s.hits![0] - 8} center y={500} s={80} text="WORLD STOPS THE CHEATER." col={MW.blue} glow="rgba(124,196,255,0.3)" />
  </Plate>
);

const Precedent: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const C = [
    { head: "HARDWARE BANS", title: "BAN A MACHINE", body: "A NEW MACHINE\nGETS BACK IN.", tag: "A STAND-IN FOR \"SAME PERSON\"", tagCol: MW.amber },
    { head: "PHONE NUMBERS", title: "BAN A SIM", body: "A NEW SIM\nGETS BACK IN.", tag: "A STAND-IN FOR \"SAME PERSON\"", tagCol: MW.amber },
    { head: "WORLD ID", title: "THE REAL ONE", body: "SAME HUMAN?\nASKED DIRECTLY,\nANONYMOUSLY.", tag: "NOT A STAND-IN", tagCol: MW.blue },
  ];
  return (
    <>
      <Kick t={t} text="THIS IS NOT NEW // HOW GAMES ALREADY TRY" />
      {C.map((c, i) => (
        <React.Fragment key={c.head}>
          <Card f={t} at={s.cards![i]} x={L + i * 550} y={260} w={520} h={236} head={c.head} accent={i === 2 ? MW.blue : MW.faint} headCol={i === 2 ? MW.blue : MW.dim}>
            <Title s={42} c={i === 2 ? MW.text : MW.dim}>{c.title}</Title>
            <Mono s={20} c={i === 2 ? MW.text : MW.dim} style={{ marginTop: 18, lineHeight: 1.4 }}>{c.body}</Mono>
          </Card>
          <Mono s={17} c={c.tagCol} w={700} ls="0.16em" style={{ position: "absolute", left: L + i * 550 + 4, top: 524, opacity: prog(t, s.chirps![0] + i * 8, s.chirps![0] + i * 8 + 6) }}>{c.tag}</Mono>
        </React.Fragment>
      ))}
    </>
  );
};

const Bot: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Kick t={t} text="THE BOT // A LEGAL RUN" />
    <Card f={t} at={s.cards![0]} x={L} y={250} w={940} h={400} head="A RUN ON THE BOARD // MARINE DRIVE GP" accent={MW.green} headCol={MW.green}>
      <Title s={72}>{fmt(R.run.time_frames)}</Title>
      <div style={{ marginTop: 22 }}>
        <Row k="PLAYED BY" v="A SCRIPT, ON THE ROM" s={21} />
        <Row k="CLAIMED FINGERPRINT" v={hex(R.run.claimed_hash)} s={21} />
        <Row k="REPLAYED FINGERPRINT" v={hex(R.run.final_hash)} c={MW.green} s={21} />
        <Row k="RULES BROKEN" v="NONE" s={21} />
      </div>
      <div style={{ position: "absolute", left: 0, bottom: 4 }}><Tag t={t} text="CHECK: BUILT" col={MW.green} /></div>
    </Card>
    <Stamp f={t} at={s.hits![0]} text="VERIFIED" col={MW.green} x={1450} y={400} s={94} sub="THE RUN CHECK CAN'T CATCH THIS" />
    <Mono s={18} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: L + 4, top: 676, lineHeight: 1.45, opacity: prog(t, 130, 142) }}>
      {"REAL: THE FILM'S OWN RUN, ITS INPUTS FED BY A PROGRAM,\nITS LOG REPLAYED BY THE PC TOOL. NO RULE WAS BROKEN, SO NONE CAN FLAG IT."}
    </Mono>
  </>
);

const Tiers: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Kick t={t} text="WORLD'S ANSWER // TWO TIERS" col={MW.blue} />
    <Card f={t} at={s.cards![0]} x={L} y={250} w={790} h={400} head="OPEN TIER" accent={MW.faint} headCol={MW.dim}>
      <Title s={50}>MACHINES WELCOME</Title>
      <Mono s={21} style={{ marginTop: 22, lineHeight: 1.5 }}>{"BOTS, SCRIPTS, TOOL-ASSISTED RUNS.\nEVERY RUN STILL REPLAY-CHECKED.\nNO WORLD ID NEEDED."}</Mono>
      <div style={{ position: "absolute", left: 0, bottom: 4 }}><Tag t={t} text="CHECK: BUILT" col={MW.green} /></div>
    </Card>
    <Card f={t} at={s.cards![1]} x={L + 830} y={250} w={790} h={400} head="HUMAN TIER" accent={MW.blue} headCol={MW.blue}>
      <Title s={50}>{"ONE WORLD ID\nBEHIND EVERY BOOK"}</Title>
      <Mono s={21} style={{ marginTop: 22, lineHeight: 1.5 }}>{"ONE HUMAN, ONE RECORD BOOK.\nRUNS CHECKED THE SAME WAY."}</Mono>
      <div style={{ position: "absolute", left: 0, bottom: 4 }}><Tag t={t} {...CALL} /></div>
    </Card>
    <Person x={L + 830 + 700} y={300} s={0.42} col={MW.blue} op={prog(t, s.cards![1] + 20, s.cards![1] + 28)} />
    <Mono s={18} c={MW.dim} ls="0.1em" style={{ position: "absolute", left: L + 4, top: 676, opacity: prog(t, s.chirps![0], s.chirps![0] + 10) }}>
      THE CHECK STILL JUDGES EVERY RUN, IN BOTH TIERS.
    </Mono>
  </>
);

const Bound: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const land = prog(t, s.hits![0], s.hits![0] + 9);
  return (
    <>
      <Kick t={t} text="WHAT WORLD DOES ABOUT THE BOT" col={MW.blue} />
      <Head t={t} at={s.chirps![0]} y={232} s={42} text="IT DOESN'T DETECT THE BOT." col={MW.dim} />
      <div style={{ position: "absolute", left: L - 10, top: 290, fontFamily: ARCHIVO, fontSize: 440, lineHeight: 1, color: `rgba(124,196,255,${(0.14 * land).toFixed(3)})`,
        WebkitTextStroke: `4px rgba(124,196,255,${(0.9 * land).toFixed(3)})`, transform: `scale(${lerp(1.35, 1, 1 - Math.pow(1 - land, 3))})`, transformOrigin: "30% 50%",
        textShadow: `0 0 60px rgba(124,196,255,${(0.35 * land).toFixed(3)})` }}>1</div>
      <Head t={t} at={s.chirps![1] - 24} x={540} y={350} s={84} text="RECORD BOOK" />
      <Head t={t} at={s.chirps![1] - 14} x={540} y={444} s={84} text="PER HUMAN." col={MW.blue} />
      <Mono s={22} c={MW.text} ls="0.1em" style={{ position: "absolute", left: 546, top: 568, lineHeight: 1.5, opacity: prog(t, s.chirps![1] + 20, s.chirps![1] + 32) }}>
        {"IT BOUNDS HOW MANY RECORD BOOKS\nONE HUMAN CAN HOLD."}
      </Mono>
    </>
  );
};

const Pay: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const draw = prog(t, s.chirps![0] - 20, s.chirps![0]);
  return (
    <>
      <Kick t={t} text="THE MONEY // IT GOES TO PEOPLE" />
      <Card f={t} at={s.cards![0]} x={L} y={300} w={600} h={230} head="WHO PAYS" accent={MW.orange}>
        <Title s={44}>A COACH AGENT</Title>
        <Mono s={20} style={{ marginTop: 18, lineHeight: 1.4 }}>{"BUYS A GHOST TO TRAIN ON.\nNO HUMAN TAPS."}</Mono>
      </Card>
      <div style={{ position: "absolute", left: L + 620, top: 414, width: 360 * draw, height: 3, background: MW.text, opacity: 0.9 }}>
        {draw >= 1 ? <div style={{ position: "absolute", right: -2, top: -7, width: 0, height: 0, borderLeft: `14px solid ${MW.text}`, borderTop: "8px solid transparent", borderBottom: "8px solid transparent" }} /> : null}
      </div>
      <Mono s={17} c={MW.amber} w={700} ls="0.24em" style={{ position: "absolute", left: L + 620, width: 360, textAlign: "center", top: 372, opacity: prog(t, s.chirps![0], s.chirps![0] + 6) }}>PAYS, DIRECTLY</Mono>
      <Card f={t} at={s.cards![1]} x={L + 1020} y={300} w={600} h={230} head="WHO IS PAID" accent={MW.blue} headCol={MW.blue}>
        <Title s={44}>A PERSON</Title>
        <Mono s={20} style={{ marginTop: 18, lineHeight: 1.4 }}>{"THE RUNNER JUST AHEAD\nOF YOU ON THE BOARD."}</Mono>
      </Card>
    </>
  );
};

/** One person, twenty wallets: twenty rows, twenty payment streams; with World they collapse into one record book. */
const Twenty: React.FC<{ t: number; s: Shot }> = ({ t, s }) => {
  const [a0, , st] = s.typing![0];
  const cw = 250, ch = 56, g = 14, x0 = L, y0 = 262, px = 1500, py = 290;
  const turn = s.chirps![0], colAt = s.hits![0];
  const lines = prog(t, turn - 26, turn);
  const c = easeInOut(prog(t, colAt, colAt + 30));
  const tw = 4 * cw + 3 * g, ty = y0 + 2 * (ch + g);
  const after = t >= colAt;
  const pcol = after ? MW.blue : t >= turn ? MW.red : MW.text;
  const cell = (i: number) => ({ gx: x0 + (i % 4) * (cw + g), gy: y0 + Math.floor(i / 4) * (ch + g) });
  return (
    <>
      {after ? <Kick t={t} at={colAt + 2} text="WITH WORLD // ONE PERSON, ONE RECORD BOOK" col={MW.blue} />
        : <Kick t={t} text="WITHOUT WORLD // ONE PERSON, TWENTY WALLETS" col={MW.red} />}
      <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={10} height={10}>
        {Array.from({ length: 20 }, (_, i) => {
          const { gx, gy } = cell(i);
          const x = lerp(gx, x0, c) + (i === 0 ? lerp(cw, tw, c) : cw), y = lerp(gy, ty, c) + ch / 2;
          const ex = lerp(x, px - 70, lines), ey = lerp(y, py + 150, lines);
          const op = i === 0 ? 0.55 : 0.55 * (1 - c);
          return lines > 0 && op > 0.01 ? <line key={i} x1={x} y1={y} x2={ex} y2={ey} stroke={after ? MW.blue : MW.red} strokeWidth={i === 0 && after ? 3 : 1.5} opacity={after && i === 0 ? 0.9 : op} /> : null;
        })}
      </svg>
      {Array.from({ length: 20 }, (_, i) => {
        if (t < a0 + i * st) return null;
        const { gx, gy } = cell(i);
        const one = i === 0 && c > 0.5;
        const op = i === 0 ? 1 : 1 - c;
        if (op <= 0.01) return null;
        return (
          <div key={i} style={{ position: "absolute", left: lerp(gx, x0, c), top: lerp(gy, ty, c), width: i === 0 ? lerp(cw, tw, c) : cw, height: ch, opacity: op,
            background: "rgba(5,5,5,0.88)", borderLeft: `3px solid ${after ? MW.blue : t >= turn ? MW.red : MW.orange}`, display: "flex", alignItems: "center",
            justifyContent: "space-between", padding: "0 14px 0 16px", boxSizing: "border-box" }}>
            <Mono s={17} w={700} ls="0.08em">{one ? "ONE RECORD BOOK  //  ONE WORLD ID" : `WALLET ${pad2(i + 1)}`}</Mono>
            <Mono s={14} c={one ? MW.blue : MW.amber} w={700} ls="0.14em">{one ? "ONE ROW  //  ONE PAYEE" : "LISTED"}</Mono>
          </div>
        );
      })}
      <Person x={px} y={py} col={pcol} op={prog(t, turn - 30, turn - 20)} />
      <Mono s={20} c={MW.text} w={700} ls="0.12em" style={{ position: "absolute", left: px - 260, width: 520, textAlign: "center", top: py + 236, lineHeight: 1.45,
        opacity: prog(t, turn, turn + 8) }}>{after ? "ONE PERSON\nONE ROW ON THE BOARD\nONE PAYEE" : "ONE PERSON\n20 ROWS ON THE BOARD\n20 PAYMENT STREAMS"}</Mono>
      <Head t={t} at={s.chirps![1]} y={640} s={40} text={"PAYMENTS GO TO PEOPLE, SO THEY MUST\nTELL ONE PERSON FROM TWENTY."} col={MW.amber} />
    </>
  );
};

const Consent1: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Monitor t={t} seq={[["ls_scan", 0]]} caption="THE CONSOLE'S SCREEN // LIST YOUR GHOST // MOCK SPONSORS" />
    <Side t={t} at={s.cards![0]} head="WORLD ID // AGENT PASS" title="LIST MY GHOST?" h={366}
      rows={[["DRAFTED BY", "YOUR COACH AGENT"], ["APPROVED IN", "WORLD APP, BY YOU"], ["THE CONSOLE", "SHOWS THE CODE"], ["NO TAP", "NOTHING LISTED"]]} />
  </>
);

const Consent2: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Monitor t={t} seq={[["ls_approve", 0], ["ls_done", s.glitch![1]]]} caption="THE CONSOLE'S SCREEN // APPROVE, THEN LISTED // MOCK SPONSORS" />
    <Side t={t} at={s.cards![0]} head="THE RULE" title={"AN APPROVAL ALLOWS\nONE FUTURE ACTION\nBY THAT ACCOUNT."} ts={31} h={400}
      rows={[["USED", "ONCE"], ["A NEW PAYEE", "A NEW APPROVAL"], ["CIRCLE ON THE CONSOLE", "ALWAYS DECIDES"]]} />
    <Head t={t} at={s.chirps![1]} x={CX + 4} y={CY + 400 + 28} s={40} text={"THE AGENT DRAFTS.\nYOU DECIDE."} col={MW.amber} />
  </>
);

const Scope: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <>
    <Kick t={t} text="WHAT WORLD DOES, EXACTLY" />
    <Head t={t} at={s.chirps![0]} y={236} s={58} text="WORLD DOESN'T WATCH THE CONTROLLER." col={MW.dim} />
    <Head t={t} at={s.chirps![0] + 22} y={318} s={58} text="IT MAKES SURE EVERY RECORD BOOK" />
    <Head t={t} at={s.chirps![0] + 32} y={386} s={58} text="HAS ONE HUMAN BEHIND IT." col={MW.blue} glow="rgba(124,196,255,0.25)" />
    <Card f={t} at={s.cards![0]} x={L} y={500} w={1620} h={214} head="AT ETHGLOBAL MUMBAI" accent={MW.amber} headCol={MW.amber}>
      <Row k="PROOFS AT THIS EVENT" v="MOCK, WITH FAKE IDENTITIES" c={MW.amber} s={20} />
      <Row k="IN PRODUCTION" v="ORB-CLASS WORLD ID" s={20} />
      <Row k="A SECOND MOCK IDENTITY" v="GETS IN HERE; IN PRODUCTION THAT TAKES A SECOND ORB ENROLMENT" s={20} />
      <Row k="THE WORLD CALLS" v={DONE ? "BUILT AT THE EVENT" : "TO BUILD AT THE EVENT"} c={DONE ? MW.green : MW.amber} s={20} />
    </Card>
  </>
);

const Close: React.FC<{ t: number; s: Shot }> = ({ t, s }) => (
  <Plate t={t} s={s}>
    <Kick t={t} at={s.chirps![0] - 6} center y={262} text="ANY% x WORLD ID" />
    <Head t={t} at={s.chirps![0]} center y={312} s={74} text="THE ANTI-CHEAT JUDGES RUNS." />
    <Head t={t} at={s.hits![0] - 10} center y={414} s={74} text="WORLD MAKES THE VERDICT" col={MW.blue} glow="rgba(124,196,255,0.3)" />
    <Head t={t} at={s.hits![0] - 2} center y={498} s={74} text="LAND ON A PERSON." col={MW.blue} glow="rgba(124,196,255,0.3)" />
    <div style={{ position: "absolute", left: W / 2 - 310, top: 612, width: 620 * easeOutExpo(prog(t, s.hits![0] + 10, s.hits![0] + 26)), height: 3, background: MW.orange, opacity: 0.9 }} />
    <Head t={t} at={s.hits![1] - 6} center y={652} s={54} text="ONE HUMAN. ONE RECORD BOOK." col={MW.orange} />
  </Plate>
);

/** One field-report clip (Objectives.tsx's FieldClip): the real screen recording on a monitor, and the values seen on it. */
const FieldClip: React.FC<{ f: number; i: number }> = ({ f, i }) => {
  const c = CLIPS[i], t = f - CLIP_AT[i];
  const FX = 90, FY = BAR + 74, FW = 1136, FH = 639, FC = FX + FW + 60;
  const on = prog(t, 0, 8);
  return (
    <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (t / 60)})`, transformOrigin: "50% 48%" }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 40% 45%, #15181b 0%, #0a0c0e 60%, #040506 100%)" }} />
      <div style={{ position: "absolute", left: FX - 12, top: FY - 12, width: FW + 24, height: FH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: FX, top: FY, width: FW, height: FH, overflow: "hidden", transform: `scaleY(${lerp(0.02, 1, easeInOut(on))})` }}>
        <OffthreadVideo src={staticFile(`built/${c.file}`)} muted startFrom={Math.round((c.from ?? 0) * 60)} style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }} />
      </div>
      <div style={{ position: "absolute", left: FX, top: FY - 46, display: "flex", alignItems: "center", gap: 12, opacity: prog(t, 6, 12) }}>
        <div style={{ width: 12, height: 12, borderRadius: "50%", background: MW.red, boxShadow: `0 0 10px ${MW.red}`, opacity: Math.floor(t / 30) % 2 === 0 ? 1 : 0.3 }} />
        <Mono s={15} c={MW.text} w={700} ls="0.28em">LIVE CAPTURE // UNEDITED // ETHGLOBAL MUMBAI</Mono>
      </div>
      <div style={{ position: "absolute", left: FC, top: FY - 6, width: W - FC - 70 }}>
        <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: t > 8 ? 1 : 0 }}>FIELD REPORT // WORLD ID</Mono>
        <div style={{ fontFamily: ARCHIVO, fontSize: 40, lineHeight: 1.05, color: MW.text, marginTop: 14, whiteSpace: "pre-wrap",
          clipPath: `inset(0 ${100 - 100 * prog(t, 12, 26)}% 0 0)` }}>{c.title}</div>
      </div>
      <Card f={t} at={30} x={FC} y={FY + 230} w={W - FC - 70} h={60 + 34 * c.rows.length} head="ON SCREEN" accent={MW.green} headCol={MW.green}>
        {c.rows.map(([k, v]) => <Row key={k} k={k} v={v} c={MW.green} s={17} />)}
      </Card>
    </AbsoluteFill>
  );
};

const BOARD_SHOTS: Record<string, React.FC<{ t: number; s: Shot }>> = {
  hook: Hook, loop: Loop, signup: Signup, void: VoidChain, suspended: Suspended, dup: Dup, precedent: Precedent, bot: Bot, tiers: Tiers,
  bound: Bound, pay: Pay, twenty: Twenty, consent1: Consent1, consent2: Consent2, scope: Scope,
};

export const WorldAct: React.FC = () => {
  const f = useCurrentFrame();
  const s = shotAt(f);
  const t = f - s.at;
  let body: React.ReactNode = null;
  if (s.id === "slate") body = <Slate f={t} part="ANY% x WORLD" title="WHY WORLD" num="?" len={s.len} />;
  else if (s.id === "line") body = <LineShot t={t} s={s} />;
  else if (s.id === "close") body = <Close t={t} s={s} />;
  else if (s.id === "field") {
    const i = CLIPS.findIndex((c, k) => f >= CLIP_AT[k] && f < CLIP_AT[k] + clipLen(c));
    body = i >= 0 ? <FieldClip f={f} i={i} /> : null;
  } else {
    const B = BOARD_SHOTS[s.id];
    body = B ? <OnBoard t={t} s={s}><B t={t} s={s} /></OnBoard> : null;
  }
  const ct = t - lastCut(t, s);
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {body}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 50%, rgba(0,0,0,0.72) 100%)" }} />
      {s.id !== "slate" ? <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: clamp(1 - ct / 4) * 0.2 }} /> : null}
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, WORLD_LEN - 14, WORLD_LEN)) }} />
    </AbsoluteFill>
  );
};

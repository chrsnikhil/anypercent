import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { clamp, easeInOut, easeOutExpo, lerp, prog } from "../util";
import { BAR, Bars, H, kick, Line, Mono, MW, Subs, W } from "./common";
import CHECK from "./check.json";
import { Board } from "./GameReel";

/* THE CHECK, inside Part IV after REJECTED: the real PC replay tool (arcade_replay, x86, on this laptop) run on each
   game's device-check log. The terminal shows only the commands and their exact stdout (prep/make_check.py); the size
   and time beside each are measured annotations, drawn outside the terminal so they never pass as tool output.
   The logs were made in the sandbox from the recorded routes, so the lines say "run logs", not "from the console". */

export const CHECK_LEN = 570;
const LINES: Line[] = [
  { at: 26, len: 270, who: "Handler", text: "The real checker, run on a laptop, with its actual output." },
  { at: 318, len: 240, who: "Handler", text: "Five games, five run logs. Each one checked in milliseconds." },
];
const TX = 150, TY = BAR + 74, TW = 1370, TH = 600, PAD = 30, LH = 29, FS = 19;
const CPL = Math.floor((TW - 2 * PAD) / (FS * 0.6));                   // Space Mono: 0.6 em a character

type Row = (typeof CHECK)[number];
/** When game k's command starts typing, how fast, and when its output lands. */
const timing = (k: number) => {
  const per = k === 0 ? 2 : 0.8;
  const s = 12 + (k === 0 ? 0 : 76 + 46 - 24 + (k - 1) * 49);
  const typed = s + CHECK[k].cmd.length * per;
  return { s, per, out: typed + 4 };
};

/** The tool's JSON, wrapped at the terminal's width, with the verdict fields lit. */
const Json: React.FC<{ text: string }> = ({ text }) => {
  const parts = text.split(/("hash_matches":true|"claims_match":true|"complete":true|"final_hash":\d+|"claimed_hash":\d+)/);
  return (
    <div style={{ fontFamily: "Space Mono", fontSize: FS, lineHeight: `${LH}px`, color: MW.dim, wordBreak: "break-all", whiteSpace: "pre-wrap" }}>
      {parts.map((p, i) => <span key={i} style={{ color: /true/.test(p) ? MW.green : /hash/.test(p) ? MW.amber : undefined }}>{p}</span>)}
    </div>
  );
};

const Terminal: React.FC<{ f: number; dim: number }> = ({ f, dim }) => {
  const grow = easeOutExpo(prog(f, 2, 10));
  let y = 0;
  return (
    <div style={{ position: "absolute", left: TX, top: TY, width: TW, height: TH * grow, overflow: "hidden", background: "rgba(7,8,9,0.95)",
      border: "1px solid #2a2d31", boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(123,211,137,0.06)" }}>
      <div style={{ height: 40, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 18px", background: "#111315",
        borderBottom: `2px solid ${MW.orange}` }}>
        <Mono s={15} c={MW.orange} w={700} ls="0.3em">PC // REPLAY CHECK</Mono>
        <Mono s={13} c={MW.dim} ls="0.24em">ANY PC // NO NETWORK NEEDED</Mono>
      </div>
      <div style={{ position: "absolute", left: PAD, top: 40 + 22, right: PAD, opacity: 1 - 0.65 * dim }}>
        {CHECK.map((r: Row, k) => {
          const tm = timing(k);
          if (f < tm.s) return null;
          const n = Math.min(r.cmd.length, Math.floor((f - tm.s) / tm.per));
          const rows = Math.ceil(r.stdout.length / CPL);
          const top = y;
          y += LH * (1 + (f >= tm.out ? rows : 0)) + 12;
          const caret = f < tm.out && Math.floor(f / 8) % 2 === 0;
          return (
            <div key={r.game} style={{ position: "absolute", left: 0, right: 0, top }}>
              <div style={{ fontFamily: "Space Mono", fontSize: FS, lineHeight: `${LH}px`, color: MW.text, whiteSpace: "pre" }}>
                <span style={{ color: MW.green }}>$ </span>{r.cmd.slice(0, n)}{caret ? <span style={{ background: MW.text }}> </span> : null}
              </div>
              {f >= tm.out ? <Json text={r.stdout} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** The measured size and time of each check, as HUD tags beside its command (not inside the terminal). */
const Tags: React.FC<{ f: number; dim: number }> = ({ f, dim }) => {
  let y = 0;
  return (
    <>
      {CHECK.map((r: Row, k) => {
        const tm = timing(k);
        const rows = Math.ceil(r.stdout.length / CPL);
        const top = y;
        y += LH * (1 + (f >= tm.out ? rows : 0)) + 12;
        if (f < tm.out) return null;
        const k1 = prog(f, tm.out, tm.out + 6);
        return (
          <div key={r.game} style={{ position: "absolute", left: TX + TW + 26, top: TY + 40 + 22 + top - 2, opacity: k1 * (1 - 0.6 * dim),
            borderLeft: `3px solid ${MW.green}`, padding: "2px 0 2px 12px" }}>
            <Mono s={16} c={MW.green} w={700} ls="0.2em">{`${r.game} // MATCH`}</Mono>
            <Mono s={13} c={MW.dim} ls="0.14em" style={{ marginTop: 4 }}>{`${r.bytes.toLocaleString("en-US")} B LOG  ${r.ms} MS`}</Mono>
            {r.game === "SHIP" ? <Mono s={13} c={MW.amber} ls="0.14em" style={{ marginTop: 4 }}>LOST RUN: CHECKS OUT</Mono> : null}
          </div>
        );
      })}
    </>
  );
};

/** The tally: one row a game, then the stamp. */
const Tally: React.FC<{ f: number; at: number }> = ({ f, at }) => {
  if (f < at) return null;
  const t = f - at, w = 1080, x = (W - w) / 2, y = TY + 40;
  const grow = Math.min(1, Math.ceil(prog(t, 0, 6) * 4) / 4);
  const cols = "130px 170px 150px 170px 1fr";
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w }}>
      <div style={{ position: "absolute", inset: 0, height: 452 * grow, background: "rgba(5,5,6,0.93)", borderLeft: `3px solid ${MW.green}`,
        boxShadow: "0 30px 90px rgba(0,0,0,0.75)" }} />
      {t > 7 ? (
        <div style={{ position: "relative", padding: "26px 34px" }}>
          <Mono s={17} c={MW.green} w={700} ls="0.3em">REPLAY CHECK // ALL FIVE GAMES</Mono>
          <div style={{ display: "grid", gridTemplateColumns: cols, marginTop: 22, opacity: prog(t, 9, 14) }}>
            {["GAME", "FRAMES", "LOG", "CHECKED IN", "FINGERPRINT"].map((h) => <Mono key={h} s={13} c={MW.dim} ls="0.24em">{h}</Mono>)}
          </div>
          {CHECK.map((r: Row, k) => {
            const on = prog(t, 12 + k * 6, 20 + k * 6);
            return (
              <div key={r.game} style={{ display: "grid", gridTemplateColumns: cols, alignItems: "center", height: 52, marginTop: 6,
                background: "rgba(123,211,137,0.05)", clipPath: `inset(0 ${100 - 100 * on}% 0 0)`, paddingLeft: 4 }}>
                <Mono s={22} c={MW.text} w={700}>{r.game}</Mono>
                <Mono s={20} c={MW.text}>{r.frames.toLocaleString("en-US")}</Mono>
                <Mono s={20} c={MW.text}>{`${r.bytes.toLocaleString("en-US")} B`}</Mono>
                <Mono s={20} c={MW.amber} w={700}>{`${r.ms} MS`}</Mono>
                <Mono s={20} c={MW.green} w={700}>{`${r.hash} = ${r.hash}`}</Mono>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};

export const Check: React.FC = () => {
  const f = useCurrentFrame();
  const TALLY = 330, STAMP = 386;
  const dim = prog(f, TALLY - 4, TALLY + 6);
  const push = 1 + 0.0066 * (f / 60);
  const st = prog(f, STAMP, STAMP + 9);
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${push}) ${kick(f, [STAMP], 6)}`, transformOrigin: "50% 48%" }}>
        <Board f={f + 400} t={clamp(f / CHECK_LEN)} dir={-0.6}>
          <Terminal f={f} dim={dim} />
          <Tags f={f} dim={dim} />
        </Board>
      </AbsoluteFill>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.72) 100%)" }} />
      <Tally f={f} at={TALLY} />
      {f >= STAMP ? (
        <div style={{ position: "absolute", left: W / 2 + 160, top: TY + 556, transform: `translate(-50%, -50%) scale(${lerp(1.6, 1, 1 - Math.pow(1 - st, 3))}) rotate(-2deg)`,
          opacity: clamp(st * 3) }}>
          <div style={{ fontFamily: "Archivo Black", fontSize: 64, letterSpacing: "0.06em", color: MW.green, padding: "4px 30px", border: `6px solid ${MW.green}`,
            background: "rgba(5,5,6,0.88)", boxShadow: `0 0 40px ${MW.green}55` }}>5 / 5 MATCH</div>
        </div>
      ) : null}
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, CHECK_LEN - 8, CHECK_LEN)) }} />
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { clamp, easeInOut, easeOutExpo, lerp, prog, rnd } from "../util";
import { BAR, Bars, Card, H, kick, Line, Mono, MW, Row, Subs, W } from "./common";

/* The primer, right after the title: what a speedrun record is, for anyone who has never seen one. The run on screen is
   real footage; the leaderboard is an example and says so (no real names, no claim about any real board). */

export const PRIMER_LEN = 720;
const S = { run: [0, 260], board: [260, 720] } as const;
const LINES: Line[] = [
  { at: 24, len: 226, who: "Handler", text: "A speedrun: finish a game as fast as you possibly can." },
  { at: 280, len: 210, who: "Handler", text: "The fastest time on the board is the world record." },
  { at: 500, len: 215, who: "Handler", text: "And the only thing standing behind it is a video." },
];
const ROWS = [
  ["01", "RUNNER A", "1:21.53"], ["02", "RUNNER B", "1:22.10"], ["03", "RUNNER C", "1:24.87"], ["04", "RUNNER D", "1:26.02"], ["05", "RUNNER E", "1:29.44"],
];

/** The real run, on a monitor: the RUSH atlas as a CSS sprite, pixels kept square, a CRT's scanlines and glass. */
const Monitor: React.FC<{ f: number; w: number; h: number }> = ({ f, w, h }) => {
  const fr = Math.floor(100 + f) % 360, col = fr % 20, row = Math.floor(fr / 20);
  const gw = w * 0.9;                                                  // the 3:2 game inside the 5:3 panel
  return (
    <div style={{ position: "relative", width: w, height: h, borderRadius: 18, background: "#08090a", padding: 0,
      boxShadow: "0 0 0 14px #15171a, 0 0 0 16px #2a2d31, 0 40px 120px rgba(0,0,0,0.8), 0 0 90px rgba(124,196,255,0.12)" }}>
      <div style={{ position: "absolute", left: (w - gw) / 2, top: 0, width: gw, height: h, overflow: "hidden" }}>
        <Img src={staticFile("game/RUSH_atlas.png")} style={{ position: "absolute", left: -col * gw, top: -row * h, width: gw * 20, height: h * 18,
          maxWidth: "none", imageRendering: "pixelated", filter: "saturate(1.08) contrast(1.05)" }} />
      </div>
      <div style={{ position: "absolute", inset: 0, borderRadius: 18, pointerEvents: "none", opacity: 0.22,
        backgroundImage: "repeating-linear-gradient(0deg, rgba(0,0,0,0.9) 0px, rgba(0,0,0,0.9) 1px, transparent 1px, transparent 3px)" }} />
      <div style={{ position: "absolute", inset: 0, borderRadius: 18, pointerEvents: "none",
        background: "radial-gradient(ellipse at 30% 20%, rgba(255,255,255,0.10), rgba(255,255,255,0) 45%), radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.45) 100%)" }} />
    </div>
  );
};

/** The tactical board behind everything: dark plate, fine grid, slow drift. */
const Board: React.FC<{ f: number; children: React.ReactNode }> = ({ f, children }) => {
  const t = f / PRIMER_LEN;
  return (
    <div style={{ position: "absolute", inset: 0, perspective: 1700, perspectiveOrigin: "50% 45%" }}>
      <div style={{ position: "absolute", left: -160, top: -100, width: W + 320, height: H + 200, transformStyle: "preserve-3d",
        transform: `rotateY(${lerp(-5, 4, t)}deg) rotateX(${lerp(2.5, 1, t)}deg) translateZ(${lerp(-40, 40, t)}px)` }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 42%, #171a1d 0%, #0b0d0f 55%, #040506 100%)" }} />
        <div style={{ position: "absolute", inset: 0, opacity: 0.13,
          backgroundImage: "linear-gradient(rgba(124,196,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.35) 1px, transparent 1px)",
          backgroundSize: "64px 64px" }} />
        {Array.from({ length: 30 }, (_, i) => (
          <Mono key={i} s={12} c={MW.faint} style={{ position: "absolute", left: 90 + (i % 2) * 2020, top: 170 + Math.floor(i / 2) * 26, opacity: 0.45 }}>
            {`${(0x2000 + Math.floor(rnd(i, 7) * 50000)).toString(16).toUpperCase()}  ${(rnd(i, 8) * 99).toFixed(2)}  ${rnd(i, 9) > 0.5 ? "RUN" : "---"}`}
          </Mono>
        ))}
        {/* a slow light scan down the board, and dust in the air */}
        <div style={{ position: "absolute", left: 0, right: 0, top: ((f * 3.2) % (H + 600)) - 300, height: 220, opacity: 0.5,
          background: "linear-gradient(180deg, rgba(124,196,255,0) 0%, rgba(124,196,255,0.06) 50%, rgba(124,196,255,0) 100%)" }} />
        {Array.from({ length: 46 }, (_, i) => {
          const x = rnd(i, 21) * (W + 300), y = (rnd(i, 22) * (H + 200) - f * (0.15 + rnd(i, 23) * 0.35)) % (H + 200);
          return <div key={i} style={{ position: "absolute", left: x, top: y < 0 ? y + H + 200 : y, width: 3 + rnd(i, 24) * 4, height: 3 + rnd(i, 24) * 4,
            borderRadius: "50%", background: "rgba(255,214,170,0.5)", filter: `blur(${1 + rnd(i, 25) * 2}px)`, opacity: 0.25 + rnd(i, 26) * 0.4 }} />;
        })}
        <div style={{ position: "absolute", left: 160, top: 100, width: W, height: H }}>{children}</div>
      </div>
    </div>
  );
};

export const Primer: React.FC = () => {
  const f = useCurrentFrame();
  const L = 70, T = BAR + 30;
  const run = f < S.board[0];
  const push = 1 + 0.0066 * (f / 60);                           // MW3's locked-off creep
  const flash = f >= S.board[0] && f < S.board[0] + 3 ? 0.24 - 0.08 * (f - S.board[0]) : 0;
  const tb = f - S.board[0];
  const proofAt = (i: number) => 520 + i * 9;                         // the proof column turns, row by row
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${push}) ${kick(f, [proofAt(4) + 4], 5)}`, transformOrigin: "50% 48%" }}>
        <Board f={f}>
          {run ? (
            <>
              <div style={{ position: "absolute", left: 500 - 300, top: 250 - 200, width: 1500, height: 940, opacity: 0.55 * clamp(f / 10),
                background: "radial-gradient(ellipse at 50% 50%, rgba(140,190,255,0.16) 0%, rgba(140,190,255,0.05) 40%, rgba(0,0,0,0) 70%)" }} />
              <div style={{ position: "absolute", left: 500, top: 250, opacity: clamp(f / 10) }}>
                <Monitor f={f} w={900} h={540} />
              </div>
              {/* the run's own clock, called out */}
              {(() => {
                const k = prog(f, 70, 82);
                const bx = 500 + 450 - 80, by = 250 + 10;
                return k > 0 ? (
                  <>
                    <div style={{ position: "absolute", left: bx, top: by, width: 160, height: 44, border: `2px solid ${MW.amber}`, opacity: k,
                      boxShadow: `0 0 18px ${MW.amber}55` }} />
                    <svg width={W + 400} height={H} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
                      <polyline points={`${bx + 80},${by} ${bx + 80},${by - 46 * k} ${bx + 80 + (1500 - bx - 80) * k},${by - 46 * k}`} fill="none" stroke={MW.amber} strokeWidth={2} />
                    </svg>
                    <div style={{ position: "absolute", left: 1520, top: by - 70, opacity: k }}>
                      <Mono s={22} c={MW.amber} w={700} ls="0.25em">THE CLOCK</Mono>
                      <Mono s={15} c={MW.dim} ls="0.2em" style={{ marginTop: 8, opacity: prog(f, 90, 100) }}>EVERY RUN IS TIMED</Mono>
                    </div>
                  </>
                ) : null;
              })()}
            </>
          ) : (
            <>
              {/* the leaderboard: an example, labelled as one */}
              <div style={{ position: "absolute", left: 330, top: 230, width: 1180 }}>
                <div style={{ opacity: tb > 4 && !(tb > 6 && tb < 8) ? 1 : 0, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <Mono s={20} c={MW.orange} w={700} ls="0.32em">LEADERBOARD // ANY GAME</Mono>
                  <div style={{ border: `2px solid ${MW.amber}`, padding: "3px 14px 4px", background: "rgba(5,5,6,0.72)" }}>{/* findable: a claims check starts here */}
                    <Mono s={22} c={MW.amber} w={700} ls="0.3em">EXAMPLE DATA</Mono>
                  </div>
                </div>
                <div style={{ height: 2, background: MW.orange, marginTop: 12, width: `${100 * easeOutExpo(prog(tb, 6, 20))}%`, opacity: 0.8 }} />
                <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 260px 260px", marginTop: 18, opacity: prog(tb, 12, 18) }}>
                  {["RANK", "RUNNER", "TIME", "PROOF"].map((h) => <Mono key={h} s={15} c={MW.dim} ls="0.3em">{h}</Mono>)}
                </div>
                {ROWS.map(([rk, who, time], i) => {
                  const at = 18 + i * 8;
                  const on = prog(tb, at, at + 10);
                  const red = prog(f, proofAt(i), proofAt(i) + 6);
                  const wr = i === 0;
                  return (
                    <div key={rk} style={{ position: "relative", display: "grid", gridTemplateColumns: "120px 1fr 260px 260px", alignItems: "center", height: 76,
                      marginTop: 8, background: wr ? "rgba(255,178,63,0.08)" : "rgba(8,9,10,0.72)", borderLeft: `4px solid ${wr ? MW.amber : MW.faint}`,
                      clipPath: `inset(0 ${100 - 100 * on}% 0 0)`, paddingLeft: 26 }}>
                      <Mono s={34} c={wr ? MW.amber : MW.text} w={700}>{rk}</Mono>
                      <div>
                        <Mono s={26} c={MW.text} w={700} ls="0.08em">{who}</Mono>
                        {wr ? <Mono s={14} c={MW.amber} w={700} ls="0.3em" style={{ marginTop: 6, opacity: prog(tb, 60, 66) }}>WORLD RECORD</Mono> : null}
                      </div>
                      <Mono s={34} c={MW.text} w={700} ls="0.04em">{time}</Mono>
                      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                        <div style={{ width: 46, height: 32, borderRadius: 5, border: `2px solid ${red > 0.5 ? MW.red : MW.dim}`, position: "relative",
                          boxShadow: red > 0.5 ? `0 0 16px ${MW.red}88` : "none" }}>
                          <div style={{ position: "absolute", left: 16, top: 7, width: 0, height: 0, borderTop: "8px solid transparent", borderBottom: "8px solid transparent",
                            borderLeft: `13px solid ${red > 0.5 ? MW.red : MW.dim}` }} />
                        </div>
                        <Mono s={26} c={red > 0.5 ? MW.red : MW.dim} w={700} ls="0.12em">VIDEO</Mono>
                      </div>
                    </div>
                  );
                })}
              </div>
              {f > proofAt(4) + 8 ? (
                <div style={{ position: "absolute", left: 330 + 1180 - 620, top: 230 - 66, width: 620, textAlign: "right",
                  transform: `scale(${lerp(1.25, 1, easeOutExpo(prog(f, proofAt(4) + 8, proofAt(4) + 18)))})`, transformOrigin: "100% 50%" }}>
                  <Mono s={22} c={MW.red} w={700} ls="0.3em">EVERY PROOF: A VIDEO FILE</Mono>
                </div>
              ) : null}
            </>
          )}
        </Board>
      </AbsoluteFill>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.72) 100%)" }} />
      <Card f={f} at={14} out={S.board[0]} x={L} y={T} w={470} h={150} head="BRIEFING // SPEEDRUNNING">
        <Row k="GOAL" v="FINISH THE GAME" />
        <Row k="HOW" v="AS FAST AS POSSIBLE" />
        <Row k="TIMED TO" v="1/100 S" c={MW.amber} />
      </Card>
      <Subs f={f} lines={LINES} />
      <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, PRIMER_LEN - 10, PRIMER_LEN)) }} />
    </AbsoluteFill>
  );
};

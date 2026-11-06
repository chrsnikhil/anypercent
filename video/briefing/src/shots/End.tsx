import React from "react";
import { Flash, Head, Mono } from "../hud";
import { C, H, TL, W, glow } from "../theme";
import { clamp, easeOutExpo, prog, rnd } from "../util";

const [S0] = TL.shots.end;

/** The title card the film ends on, held to the last frame. */
export const End: React.FC<{ f: number }> = ({ f }) => {
  const t = easeOutExpo(prog(f, S0 + 4, S0 + 40));
  const flicker = f < S0 + 16 && rnd(f, 5) > 0.45 ? 0.3 : 1;
  const sub = prog(f, S0 + 40, S0 + 60);
  const bar = easeOutExpo(prog(f, S0 + 24, S0 + 64));
  return (
    <div style={{ position: "absolute", inset: 0, background: C.bg, overflow: "hidden" }}>
      <svg style={{ position: "absolute", inset: 0, opacity: 0.08 }} width={W} height={H}>
        {Array.from({ length: 33 }, (_, i) => <line key={"v" + i} x1={i * 60} y1={0} x2={i * 60} y2={H} stroke={C.line} />)}
        {Array.from({ length: 19 }, (_, i) => <line key={"h" + i} x1={0} y1={i * 60} x2={W} y2={i * 60} stroke={C.line} />)}
      </svg>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at center, rgba(40,110,160,0.18) 0%, transparent 60%)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: H / 2 - 150, display: "flex", flexDirection: "column", alignItems: "center", opacity: flicker }}>
        <Head size={26} color={C.accent} spacing="0.6em" style={{ opacity: clamp(t * 2), textShadow: glow(C.accent, 4) }}>Any%</Head>
        <Head size={150} weight={700} spacing={`${0.5 - 0.36 * t}em`} style={{ marginTop: 26, opacity: clamp(t * 1.5), textShadow: glow(C.ink, 16) }}>
          ETHGlobal Mumbai '26
        </Head>
        <div style={{ width: 1100 * bar, height: 3, background: C.accent, marginTop: 34, boxShadow: glow(C.accent, 8) }} />
        <Mono size={24} color={C.ink} style={{ marginTop: 30, opacity: sub, letterSpacing: "0.3em" }}>
          05 - 07 NOV 2026
        </Mono>
      </div>
      <Flash f={f} at={S0} len={18} peak={0.8} />
    </div>
  );
};

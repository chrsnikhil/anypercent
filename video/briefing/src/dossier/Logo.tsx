import { loadFont } from "@remotion/fonts";
import React from "react";
import { staticFile } from "remotion";
import { FONT } from "../theme";
import { clamp, easeOutExpo, prog, rnd } from "../util";

loadFont({ family: "Archivo Black", url: staticFile("fonts/ArchivoBlack-Regular.ttf"), weight: "400" });

/** The Any% title lockup: original letterforms in the language of a modern military-shooter title, brushed metal
    with grain, a light sweep, an RGB-split flicker on the way in. `t` is frames since the lockup starts. */
export const Logo: React.FC<{ t: number; scale?: number; sub?: string; out?: number }> = ({ t, scale = 1, sub = "ETHGLOBAL MUMBAI '26", out = 1e9 }) => {
  if (t < 0) return null;
  const on = t < 14 ? (rnd(Math.floor(t), 3) > 0.45 ? 1 : 0.15) : 1;
  const split = Math.max(0, 1 - t / 18) * 10;
  const sweep = prog(t, 22, 70);
  const gone = 1 - prog(t, out, out + 10);
  const subT = easeOutExpo(prog(t, 30, 54));
  const W = 1500, H = 520;
  const word = (dx: number, fill: string, op = 1) => (
    <text x={W / 2 + dx} y={330} textAnchor="middle" fontFamily="Archivo Black" fontSize={292} letterSpacing="10" fill={fill} opacity={op}>ANY%</text>
  );
  return (
    <svg width={W * scale} height={H * scale} viewBox={`0 45 ${W} ${H}`} style={{ opacity: on * gone, overflow: "visible" }}>
      <defs>
        <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f4f3ef" />
          <stop offset="0.46" stopColor="#c9c8c3" />
          <stop offset="0.5" stopColor="#8d8c88" />
          <stop offset="0.62" stopColor="#b3b2ad" />
          <stop offset="1" stopColor="#6f6e6a" />
        </linearGradient>
        <linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0.25">
          <stop offset={Math.max(0, sweep - 0.12)} stopColor="#fff" stopOpacity="0" />
          <stop offset={sweep} stopColor="#fff" stopOpacity="0.85" />
          <stop offset={Math.min(1, sweep + 0.12)} stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <filter id="brush" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.6 0.012" numOctaves="2" seed="4" />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <clipPath id="letters"><text x={W / 2} y={330} textAnchor="middle" fontFamily="Archivo Black" fontSize={292} letterSpacing="10">ANY%</text></clipPath>
      </defs>
      {split > 0.3 ? <>{word(-split, "#ff3b2f", 0.55)}{word(split, "#2fb8ff", 0.55)}</> : null}
      {word(0, "url(#metal)")}
      <rect x={0} y={60} width={W} height={330} filter="url(#brush)" clipPath="url(#letters)" opacity={0.28} style={{ mixBlendMode: "multiply" }} />
      <text x={W / 2} y={330} textAnchor="middle" fontFamily="Archivo Black" fontSize={292} letterSpacing="10" fill="none" stroke="#ffffff" strokeOpacity={0.3} strokeWidth={1.6}>ANY%</text>
      <rect x={0} y={60} width={W} height={330} fill="url(#sweep)" clipPath="url(#letters)" style={{ mixBlendMode: "screen" }} />
      <rect x={W / 2 - 560 * subT} y={384} width={1120 * subT} height={5} fill="#f08a24" />
      <text x={W / 2} y={448} textAnchor="middle" fontFamily={FONT.ui} fontWeight={700} fontSize={34} letterSpacing="14" fill="#d9d6ce" opacity={subT}>{sub}</text>
    </svg>
  );
};

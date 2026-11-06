import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame } from "remotion";
import { prog } from "../util";
import { BAR, Bars, Line, Mono, MW, Subs } from "./common";

/* FIELD TAPE: real footage of the physical console, filmed by a person (a camera or webcam, not a phone: ETHGlobal's
   rule), dropped in as public/field/device.mp4. The film's only shot that is not code: it is framed as a tape, with
   nothing added to the picture but the HUD, so it reads as evidence. Optional: post_film.py uses it only if it was
   rendered (out/field_raw.mov). FIELD_LEN caps it at 10 s; the clip should open on the device already on. */

export const FIELD_LEN = 600;
const LINES: Line[] = [{ at: 24, len: 260, who: "Handler", text: "And this is the real console, running." }];

export const FieldTape: React.FC = () => {
  const f = useCurrentFrame();
  const rec = Math.floor(f / 30) % 2 === 0;
  const tc = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}:${String(Math.floor((s * 60) % 60)).padStart(2, "0")}`;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <OffthreadVideo src={staticFile("field/device.mp4")} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.6) 100%)" }} />
      <div style={{ position: "absolute", left: 70, top: BAR + 30, display: "flex", alignItems: "center", gap: 14, opacity: prog(f, 4, 10) }}>
        <div style={{ width: 14, height: 14, borderRadius: "50%", background: MW.red, boxShadow: `0 0 12px ${MW.red}`, opacity: rec ? 1 : 0.25 }} />
        <Mono s={20} c={MW.text} w={700} ls="0.3em">FIELD TAPE // THE REAL CONSOLE</Mono>
      </div>
      <Mono s={16} c={MW.dim} ls="0.24em" style={{ position: "absolute", left: 98, top: BAR + 62, opacity: prog(f, 8, 14) }}>UNEDITED // FILMED, NOT RENDERED</Mono>
      <Mono s={20} c={MW.text} w={700} style={{ position: "absolute", right: 70, top: BAR + 30 }}>{tc(f / 60)}</Mono>
      {[[60, BAR + 20, 1, 1], [1860, BAR + 20, -1, 1], [60, 1080 - BAR - 20, 1, -1], [1860, 1080 - BAR - 20, -1, -1]].map(([x, y, sx, sy], i) => (
        <div key={i} style={{ position: "absolute", left: x - (sx < 0 ? 40 : 0), top: y - (sy < 0 ? 40 : 0), width: 40, height: 40,
          borderLeft: sx > 0 ? `3px solid ${MW.text}` : undefined, borderRight: sx < 0 ? `3px solid ${MW.text}` : undefined,
          borderTop: sy > 0 ? `3px solid ${MW.text}` : undefined, borderBottom: sy < 0 ? `3px solid ${MW.text}` : undefined, opacity: 0.7 }} />
      ))}
      <Subs f={f} lines={LINES} />
      <Bars />
    </AbsoluteFill>
  );
};

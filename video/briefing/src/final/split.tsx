import React from "react";
import { OffthreadVideo, Sequence, staticFile } from "remotion";
import { MW, Mono } from "../acts/common";
import { prog } from "../util";

/* The owner's split screen (7 Nov): left, the film's version of a beat (scaled whole frame); right, the owner's real
   recording of the same beat, from public/final/live_clips/<clip>.mp4 (proxies of video/final CLIPS_A/B.md). */

export type LiveWin = {
  a: number; b: number;                 // scene frames the window covers
  clip: string; at: number;             // proxy name, and the second in it shown at frame a
  label?: string;                       // default: LIVE ON THE HANDHELD, 7 NOV
  note?: string;                        // an honest line under the clip
  crop?: [number, number, number, number]; // the region of the clip to show, as fractions [x, y, w, h]
  ar?: number;                          // the proxy's aspect (w / h); 16/9 by default, phones about 0.46
};

export const HANDHELD = "LIVE ON THE HANDHELD, 7 NOV";
export const LAPTOP = "LIVE, LAPTOP, 7 NOV";
export const PHONE = "LIVE, WORLD APP ON THE OWNER'S PHONE, 7 NOV";

const RX = 970, RY = 172, RW = 930, RH = 523;           // the live panel
const LS = 930 / 1920, LX = 20, LW = 930, LH = Math.round(844 * LS);
const LY = Math.round(RY + RH / 2 - LH / 2);

/** The film's frame (bars excluded), scaled into the left panel. */
export const LeftPanel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ position: "absolute", left: LX, top: LY, width: LW, height: LH, overflow: "hidden", borderRadius: 6,
    boxShadow: "0 0 0 2px #2a2d31, 0 24px 70px rgba(0,0,0,0.7)" }}>
    <div style={{ position: "absolute", left: 0, top: -118 * LS, width: 1920, height: 1080, transform: `scale(${LS})`, transformOrigin: "0 0" }}>
      {children}
    </div>
  </div>
);

/** The live clip, contained in the right panel, with its label above and its note below. */
export const LivePanel: React.FC<{ w: LiveWin; f: number }> = ({ w, f }) => {
  const [cx, cy, cw, ch] = w.crop ?? [0, 0, 1, 1];
  const ar = w.ar ?? 16 / 9;
  const regionAr = (cw * ar) / ch;
  const dw = regionAr > RW / RH ? RW : RH * regionAr;
  const dh = dw / regionAr;
  const vw = dw / cw, vh = vw / ar;
  const t = f - w.a;
  const on = prog(t, 0, 8);
  return (
    <>
      <div style={{ position: "absolute", left: RX, top: RY, width: RW, height: RH, background: "#050607", borderRadius: 6,
        boxShadow: "0 0 0 2px rgba(212,58,43,0.55), 0 24px 70px rgba(0,0,0,0.7)", overflow: "hidden" }}>
        <div style={{ position: "absolute", left: (RW - dw) / 2, top: (RH - dh) / 2, width: dw, height: dh, overflow: "hidden", opacity: on }}>
          <Sequence from={w.a} layout="none">
            <OffthreadVideo src={staticFile(`final/live_clips/${w.clip}.mp4`)} trimBefore={Math.round(w.at * 60)} muted
              style={{ position: "absolute", left: -cx * vw, top: -cy * vh, width: vw, height: vh, maxWidth: "none" }} />
          </Sequence>
        </div>
      </div>
      <div style={{ position: "absolute", left: RX, top: RY - 40, display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 14, height: 14, borderRadius: 7, background: MW.red, opacity: Math.floor(t / 30) % 2 === 0 ? 1 : 0.45 }} />
        <Mono s={24} c={MW.text} w={700} ls="0.08em">{w.label ?? HANDHELD}</Mono>
      </div>
      <div style={{ position: "absolute", left: LX, top: RY - 40 }}>
        <Mono s={20} c={MW.dim} w={700} ls="0.08em">THE FILM'S VERSION</Mono>
      </div>
      {w.note ? (
        <div style={{ position: "absolute", left: RX, top: RY + RH + 14, width: RW, background: "rgba(5,5,6,0.9)", borderLeft: `4px solid ${MW.amber}`,
          padding: "8px 16px 10px", opacity: prog(t, 10, 20) }}>
          <Mono s={24} c={MW.amber} w={700} ls="0.04em" style={{ whiteSpace: "normal" }}>{w.note}</Mono>
        </div>
      ) : null}
    </>
  );
};

import React, { useMemo } from "react";
import { AbsoluteFill, Audio, Sequence, Series, staticFile, useCurrentFrame } from "remotion";
import { Breaks } from "../src/acts/Breaks";
import { Chapter } from "../src/acts/Chapter";
import { Check } from "../src/acts/Check";
import { Coach } from "../src/acts/Coach";
import { Coda, ColdOpen } from "../src/acts/ColdOpen";
import { GameReel } from "../src/acts/GameReel";
import { Handler } from "../src/acts/Handler";
import { MachineSubs } from "../src/acts/MachineSubs";
import { Objectives } from "../src/acts/Objectives";
import { Primer } from "../src/acts/Primer";
import { Proof, ProofTeaser } from "../src/acts/Proof";
import { ProofFlash } from "../src/acts/ProofFlash";
import { Briefing } from "../src/Briefing";
import { Dossier } from "../src/dossier/Dossier";
import { TitleEnd, TitleOpen } from "../src/dossier/TitleCard";
import SEGS from "./segments.json";

/* The film, live: the same compositions that render the MP4, in the order and at the cuts post_film.py stitches them
   (web/segments.json is exported from its tables), with the original soundtrack. The ffmpeg finish (warm and cool
   grades, the assembly film's scanlines, grain, vignette) is approximated in CSS. */

export type Cut = "full" | "sub";
type Seg = { comp: string; props: Record<string, string | number>; from: number; frames: number; grade: string; overlay: string | null; chapter: string | null };
const TABLE = SEGS as Record<Cut, Seg[]>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const COMPS: Record<string, React.FC<any>> = {
  ColdOpen, ProofTeaser, ProofFlash, TitleOpen, Primer, Chapter, Dossier, Breaks, Briefing, GameReel, Proof, Check, Coach, Objectives, Handler, Coda, TitleEnd,
  MachineSubs,
};

export const filmFrames = (cut: Cut) => TABLE[cut].reduce((a, r) => a + r.frames, 0);
/** Chapter marks: (frame, name), a PART card belonging to the act it opens, as in the MP4's chapters. */
export const chapters = (cut: Cut) => {
  let t = 0;
  const out: { frame: number; name: string }[] = [];
  for (const r of TABLE[cut]) {
    if (r.chapter) out.push({ frame: t, name: r.chapter });
    t += r.frames;
  }
  return out;
};

/** A tile of film grain, made once. */
const useGrain = () => useMemo(() => {
  if (typeof document === "undefined") return "";
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const img = g.createImageData(256, 256);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.random() * 255;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  return c.toDataURL();
}, []);

const LOOK: Record<string, React.CSSProperties> = {
  warm: { filter: "saturate(0.88) contrast(1.06) brightness(1.03) sepia(0.05)" },     // post_film's grades, gamma lift included
  cool: { filter: "saturate(0.96) contrast(1.05) brightness(1.03)" },
  asm: {},
};

/** The finish over a segment: tint, vignette, grain; the assembly film keeps its scanlines. */
const Finish: React.FC<{ kind: string }> = ({ kind }) => {
  const f = useCurrentFrame();
  const grain = useGrain();
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {kind === "warm" ? <AbsoluteFill style={{ background: "rgba(255,170,90,0.05)", mixBlendMode: "soft-light" }} /> : null}
      {kind === "cool" ? <AbsoluteFill style={{ background: "rgba(110,170,255,0.07)", mixBlendMode: "soft-light" }} /> : null}
      {kind === "asm" ? <AbsoluteFill style={{ backgroundImage: `url(${staticFile("scanlines.png")})`, mixBlendMode: "multiply", opacity: 0.9 }} /> : null}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.42) 100%)" }} />
      <AbsoluteFill style={{ backgroundImage: `url(${grain})`, backgroundPosition: `${(f * 97) % 256}px ${(f * 61) % 256}px`, opacity: 0.045,
        mixBlendMode: "overlay" }} />
    </AbsoluteFill>
  );
};

export const Film: React.FC<{ cut: Cut }> = ({ cut }) => (
  <AbsoluteFill style={{ background: "#000" }}>
    <Series>
      {TABLE[cut].map((r, i) => {
        const C = COMPS[r.comp];
        const O = r.overlay ? COMPS[r.overlay] : null;
        return (
          <Series.Sequence key={i} durationInFrames={r.frames} premountFor={45}>
            <AbsoluteFill style={LOOK[r.grade]}>
              <Sequence from={-r.from}>
                <C {...r.props} />
              </Sequence>
            </AbsoluteFill>
            {O ? <O /> : null}
            <Finish kind={r.grade} />
          </Series.Sequence>
        );
      })}
    </Series>
    <Audio src={staticFile(`audio/${cut}.m4a`)} />
  </AbsoluteFill>
);

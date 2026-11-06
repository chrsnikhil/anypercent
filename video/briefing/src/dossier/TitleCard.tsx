import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { clamp, rnd } from "../util";
import { Logo } from "./Logo";

const BG = "radial-gradient(ellipse at center, #1a1714 0%, #050505 70%)";
const Bars: React.FC = () => (
  <>
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 118, background: "#000" }} />
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 118, background: "#000" }} />
  </>
);

/** Preview of the lockup on its own. */
export const TitleCard: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center" }}>
      <Logo t={f} />
    </AbsoluteFill>
  );
};

/** 150 frames: the lockup flickers in, the light sweeps it, then it breaks up into the dossier. */
export const TitleOpen: React.FC = () => {
  const f = useCurrentFrame();
  const out = f >= 132;
  const jx = out ? (rnd(f, 3) - 0.5) * 60 : 0;
  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center", opacity: f >= 146 ? 0 : 1 }}>
      <div style={{ transform: `translateX(${jx}px)`, opacity: out ? (rnd(f, 5) > 0.4 ? 1 : 0.2) : 1 }}>
        <Logo t={f - 10} sub="LEADERBOARD INTEGRITY BRIEFING" />
      </div>
      <Bars />
    </AbsoluteFill>
  );
};

/** 240 frames: the closing card, held to the last frame. */
export const TitleEnd: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center" }}>
      <div style={{ opacity: clamp(f / 4) }}><Logo t={f - 4} sub="ETHGLOBAL MUMBAI '26" /></div>
      <Bars />
    </AbsoluteFill>
  );
};

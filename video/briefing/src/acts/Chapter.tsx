import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Bars, Slate } from "./common";

/** The act card that opens each part: the slate (common.Slate). */
export const CHAPTER_LEN = 50;
export const Chapter: React.FC<{ part: string; title: string }> = ({ part, title }) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Slate f={f} part={part} title={title} len={CHAPTER_LEN} />
      <Bars />
    </AbsoluteFill>
  );
};

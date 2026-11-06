import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Boot } from "./shots/Boot";
import { Build } from "./shots/Build";
import { End } from "./shots/End";
import { C, TL } from "./theme";

type ShotProps = { f: number };
const S = TL.shots;
const SHOTS: [number, number, React.FC<ShotProps>][] = [
  [S.boot[0], S.boot[1], Boot],
  [S.hero[0], S.reveal[1], Build],
  [S.end[0], S.end[1], End],
];

const Abs: React.FC<{ from: number; Shot: React.FC<ShotProps> }> = ({ from, Shot }) => {
  const rel = useCurrentFrame();
  return <Shot f={rel + from} />;
};

/** The whole film: each shot mounts only for its own frames and reads the absolute frame. */
export const Briefing: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg }}>
    {SHOTS.map(([a, b, Shot], i) => (
      <Sequence key={i} from={a} durationInFrames={b - a} layout="none">
        <AbsoluteFill><Abs from={a} Shot={Shot} /></AbsoluteFill>
      </Sequence>
    ))}
  </AbsoluteFill>
);

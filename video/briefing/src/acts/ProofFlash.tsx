import React from "react";
import { AbsoluteFill, Sequence, Series, useCurrentFrame } from "remotion";
import { prog } from "../util";
import { Bars, Line, Mono, MW, Subs } from "./common";
import { Proof, ProofTeaser, TEASER_LEN } from "./Proof";

/* The flash-forward of the submission cut: by 0:27 a judge has seen the mechanism, not just the mood. The console
   (ProofTeaser), then three beats of Part III cut straight from it with no subtitles of their own: the fingerprints
   matching (VERIFIED), one byte of the log flipping, the fingerprint failing (REJECTED). Frames are the Proof act's. */
const SHOTS = [{ from: 1250, len: 100 }, { from: 1500, len: 80 }, { from: 1765, len: 120 }];
export const FLASH_LEN = TEASER_LEN + SHOTS.reduce((a, s) => a + s.len, 0);
const LINES: Line[] = [
  { at: 8, len: 220, who: "Handler", text: "Any%: every run is a tiny log anyone can replay." },
  { at: 236, len: 158, who: "Handler", text: "Change one byte, and the fingerprint breaks." },
];
const CUTS = [TEASER_LEN, TEASER_LEN + 100, TEASER_LEN + 180];

export const ProofFlash: React.FC = () => {
  const f = useCurrentFrame();
  const cut = CUTS.find((c) => f >= c && f < c + 3);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Series>
        <Series.Sequence durationInFrames={TEASER_LEN}>
          <ProofTeaser />
        </Series.Sequence>
        {SHOTS.map((s) => (
          <Series.Sequence key={s.from} durationInFrames={s.len}>
            <Sequence from={-s.from}>
              <Proof clean />
            </Sequence>
          </Series.Sequence>
        ))}
      </Series>
      <Mono s={16} c={MW.orange} w={700} ls="0.4em" style={{ position: "absolute", right: 70, top: 152, opacity: f > 4 && Math.floor(f / 20) % 2 === 0 ? 1 : 0.4 }}>
        FLASH-FORWARD // PART III
      </Mono>
      {cut !== undefined ? <AbsoluteFill style={{ background: "#fff", opacity: 0.3 - 0.1 * (f - cut) }} /> : null}
      <Subs f={f} lines={LINES} />
      <Bars />
      <AbsoluteFill style={{ background: "#000", opacity: prog(f, FLASH_LEN - 6, FLASH_LEN) }} />
    </AbsoluteFill>
  );
};

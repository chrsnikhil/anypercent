import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { BAR, Line, MW } from "./common";
import { FONT } from "../theme";

/* Part III's narration: the assembly film (its master, frames 120-2010) carries no subtitles of its own, so these are
   rendered on a transparent background and laid over it in post_film.py. Local frame 0 = assembly frame 120.
   Only what is true: the face buttons are cosmetic, so it is "pair a controller"; the games are Chris's own. */

export const MACHINE_LEN = 1890;
const LINES: Line[] = [
  { at: 20, len: 200, who: "Handler", text: "This is Any%: a handheld console, built for speedrunning." },
  { at: 240, len: 190, who: "Handler", text: "Fifty-nine parts, from the shell to the screws." },
  { at: 900, len: 230, who: "Handler", text: "A five-inch touchscreen, and a Raspberry Pi to run the games." },
  { at: 1150, len: 250, who: "Handler", text: "Our own games, with fixed rules: same inputs in, same run out." },
  { at: 1420, len: 240, who: "Handler", text: "The buttons are cosmetic for now: pair a controller, and play." },
  { at: 1690, len: 195, who: "Handler", text: "And every input, every frame, is written to a log." },
];

/** Same type and baseline as every other subtitle, but centred in the right two-thirds: the assembly film's step titles
    own the bottom-left corner, and a long line would run into them. */
export const MachineSubs: React.FC = () => {
  const f = useCurrentFrame();
  const l = LINES.find((q) => f >= q.at && f < q.at + q.len);
  return (
    <AbsoluteFill style={{ background: "transparent" }}>
      {l ? (
        <div style={{ position: "absolute", left: 680, right: 40, bottom: BAR + 70, textAlign: "center", fontFamily: FONT.sub, fontWeight: 600, fontSize: 33,
          color: "#f2f2f0", textShadow: "0 2px 6px rgba(0,0,0,0.95), 0 0 2px rgba(0,0,0,0.9)" }}>
          <span style={{ color: MW.blue }}>{l.who}: </span>{l.text}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

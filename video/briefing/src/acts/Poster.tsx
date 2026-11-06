import React from "react";
import { AbsoluteFill } from "remotion";
import { FONT } from "../theme";
import { BAR, Mono, MW } from "./common";
import { Proof } from "./Proof";

/* The cover image (ETHGlobal showcase, YouTube): Part IV with no subtitles, and the title over a shade at the lower
   left. Render one still at the Proof act's frame: npx remotion still src/index.ts Poster out.png --frame=1380
   (1380 = VERIFIED landed, 1872 = REJECTED). */
export const Poster: React.FC<{ title?: boolean }> = ({ title = true }) => (
  <AbsoluteFill style={{ background: "#000" }}>
    <Proof clean />
    {title ? (
      <>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 520,
          background: "linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.6) 45%, rgba(0,0,0,0) 100%)" }} />
        <div style={{ position: "absolute", left: 96, bottom: BAR + 18 }}>
          <Mono s={22} c={MW.orange} w={700} ls="0.5em">ETHGLOBAL MUMBAI '26</Mono>
          <div style={{ fontFamily: "Archivo Black", fontSize: 128, lineHeight: 1, color: MW.text, marginTop: 12, letterSpacing: "0.01em",
            textShadow: "0 8px 40px rgba(0,0,0,0.8)" }}>ANY%</div>
          <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: 38, letterSpacing: "0.16em", color: MW.text, marginTop: 12 }}>
            SPEEDRUN RECORDS ANYONE CAN CHECK
          </div>
        </div>
      </>
    ) : null}
  </AbsoluteFill>
);

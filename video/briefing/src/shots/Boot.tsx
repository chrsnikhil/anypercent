import React from "react";
import { C, H, TL, W, glow } from "../theme";
import { DataFeed, Flash, Frame, Glitch, Head, Mono, TypeText, jitter } from "../hud";
import { clamp, easeOutExpo, prog, rnd, typeEntry } from "../util";

const [, END] = TL.shots.boot;
const SLAM = 62;

/** 0-120: three lines of terminal, then the title slams in and glitches out. */
export const Boot: React.FC<{ f: number }> = ({ f }) => {
  const lines = ["boot1", "boot2", "boot3"].map(typeEntry);
  const t = easeOutExpo(prog(f, SLAM, SLAM + 14));
  const flicker = f >= SLAM && f < SLAM + 10 && rnd(f, 9) > 0.5 ? 0.35 : 1;
  return (
    <div style={{ position: "absolute", inset: 0, background: C.bg, transform: `translateX(${jitter(f, END - 8, 8)}px)` }}>
      <Frame f={f} opacity={clamp(f / 6)} tl="SECURE TERMINAL // ANY%-01" tr="ASSET FILE 4F-0711" bl="CLASSIFIED // EYES ONLY" br="DO NOT DISTRIBUTE" />
      <div style={{ position: "absolute", left: 0, right: 0, top: 96, display: "flex", justifyContent: "center", opacity: clamp(f / 4) }}>
        <div style={{ border: `2px solid ${C.alert}`, padding: "6px 22px" }}>
          <Head size={24} color={C.alert} spacing="0.4em" style={{ textShadow: glow(C.alert, 4) }}>Classified // Eyes only</Head>
        </div>
      </div>
      <div style={{ position: "absolute", left: 260, top: 300, display: "flex", flexDirection: "column", gap: 16, opacity: 1 - prog(f, SLAM - 4, SLAM + 6) * 0.8 }}>
        {lines.map((l) => <TypeText key={l.id} f={f} text={l.text} start={l.frame} cps={l.cps} size={30} color={C.ink} cursor={f < l.frame + 20} />)}
      </div>
      <DataFeed f={f} x={W - 380} y={300} rows={22} cols={5} opacity={0.4 * clamp(f / 12)} />
      {f >= SLAM ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: H / 2 - 40, display: "flex", flexDirection: "column", alignItems: "center", gap: 16, opacity: flicker }}>
          <Head size={170} weight={700} spacing={`${0.5 - 0.36 * t}em`} style={{ transform: `scale(${1.25 - 0.25 * t})`, textShadow: glow(C.ink, 14) }}>
            Any%
          </Head>
          <Head size={30} color={C.accent} spacing="0.5em" style={{ opacity: t }}>Asset briefing</Head>
        </div>
      ) : null}
      <Flash f={f} at={SLAM} len={12} peak={0.55} />
      <Glitch f={f} at={END - 8} len={8} />
      {f >= END - 2 ? <div style={{ position: "absolute", inset: 0, background: "#000" }} /> : null}
      <Mono size={1} color="transparent">{""}</Mono>
    </div>
  );
};

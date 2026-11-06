import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { FONT } from "../theme";
import { clamp, prog } from "../util";
import { Mono, MW } from "./common";
import VO from "./vo.json";

/* The read-along panel for recording the narration (prep/vo.py prompter stacks it under the submission picture).
   Its clock: VO.pre seconds of countdown (three beeps in the audio), then the film. The line to say now is big and
   turns amber on its cue; the next one waits below with a bar that fills to its cue. */

export const PROMPTER_W = 1920, PROMPTER_H = 360;
export const PROMPTER_LEN = Math.round((VO.pre + VO.total) * 60) + 30;
type L = (typeof VO.lines)[number];

export const Prompter: React.FC = () => {
  const f = useCurrentFrame();
  const t = f / 60 - VO.pre;                                           // seconds on the film's clock
  const lines = VO.lines as L[];
  const i = lines.reduce((k, l, j) => (l.t <= t ? j : k), -1);
  const cur = i >= 0 ? lines[i] : null, next = lines[i + 1];
  const live = cur ? t - cur.t : 99;
  const mm = Math.max(0, Math.floor(t / 60)), ss = Math.max(0, t - mm * 60);
  const count = t < 0 ? (t < -2 ? "3" : t < -1 ? "2" : "1") : null;
  const lead = next ? next.t - t : 99;
  return (
    <AbsoluteFill style={{ background: "#0b0c0d", fontFamily: FONT.sub }}>
      <div style={{ position: "absolute", left: 40, top: 26, display: "flex", gap: 40, alignItems: "baseline" }}>
        <Mono s={22} c={MW.dim} w={700}>{`${String(mm).padStart(2, "0")}:${ss.toFixed(1).padStart(4, "0")}`}</Mono>
        <Mono s={18} c={MW.faint} ls="0.2em">{`LINE ${String(Math.max(0, i + 1)).padStart(2, "0")} / ${lines.length}`}</Mono>
        <Mono s={16} c={MW.faint} ls="0.2em">READ WHEN AMBER // KEEP GOING IF YOU STUMBLE</Mono>
      </div>
      {count ? (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 150, fontWeight: 800, color: MW.amber, fontFamily: FONT.head }}>{count}</div>
        </div>
      ) : (
        <>
          {cur ? (
            <div style={{ position: "absolute", left: 40, right: 40, top: 80, fontSize: 50, fontWeight: 700, lineHeight: 1.2,
              color: live < 0.6 ? MW.amber : live < 6 ? "#f2f2f0" : MW.faint }}>
              {cur.caption ? null : <span style={{ color: MW.blue, fontSize: 28, marginRight: 14 }}>(over the title)</span>}{cur.text}
            </div>
          ) : null}
          {next ? (
            <div style={{ position: "absolute", left: 40, right: 40, top: 236 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 20 }}>
                <Mono s={18} c={lead < 1.5 ? MW.amber : MW.faint} w={700} ls="0.2em">{lead < 1.5 ? `NEXT IN ${lead.toFixed(1)}` : "NEXT"}</Mono>
                <div style={{ fontSize: 30, color: lead < 1.5 ? "#cfcfcc" : MW.dim, fontWeight: 600 }}>{next.text}</div>
              </div>
              <div style={{ marginTop: 14, height: 6, background: "#1c1e21" }}>
                <div style={{ height: 6, width: `${100 * clamp(1 - lead / Math.max(1, next.t - (cur ? cur.t : -VO.pre)))}%`,
                  background: lead < 1.5 ? MW.amber : MW.dim }} />
              </div>
            </div>
          ) : null}
        </>
      )}
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 8, background: MW.amber, opacity: prog(-live, -0.6, 0) > 0 && live < 0.6 ? 1 : 0 }} />
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import SCREENS from "../../public/handler/screens.json";
import BUILT from "./built.json";
import { clamp, easeInOut, lerp, prog } from "../util";
import { BAR, Bars, Card, Line, Mono, MW, Subs, W } from "./common";
import { Board } from "./GameReel";

/* THE HANDLER, after the Mumbai objectives: the same PB also walks a player through each sponsor step, on the console.
   The monitor is the real launcher, drawn by its own code (prep/make_handler_frames.py): its handler flow over its mock
   sponsors (the MOCK pill is on screen), each step from the moment it opens. The numbers are real: RIA is the game's
   shipped test log, "you" a real slower run (prep/make_handler_run.py), both replayed by the PC tool; the other names on
   the board are the launcher's mock runners. The sponsor calls are built at the event, and every card says so: each
   card turns BUILT with its sponsor's flag in built.json, and once any is built the second line points back to the
   field report (the screens here stay mock-drawn until they are re-made against the real calls). */

export const HANDLER_LEN = 540;
export const STEP_AT = [30, 156, 282, 408];                         // the monitor cuts to each step
const DONE = BUILT.built as { world: boolean; hedera: boolean; arkiv: boolean };
const ANY_DONE = DONE.world || DONE.hedera || DONE.arkiv;
const LINES: Line[] = [
  { at: 54, len: 226, who: "Handler", text: "PB also walks you through every sponsor step." },
  { at: 300, len: 220, who: "Handler", text: ANY_DONE ? "These screens run on mocks. The real calls came just before." : "Real screens. The calls stay mock until Mumbai." },
];
const S = SCREENS as { steps: string[]; images: Record<string, number>; every: number; you: number; ria: number };
const fmt = (fr: number) => {
  const cs = Math.round((fr * 100) / 60);
  return `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
};
const STEPS = [
  { k: "01 // WORLD ID", t: "RECORD BOOK", s: "IDKIT: ONE PERSON, ONE BOOK", built: DONE.world },
  { k: "02 // ARKIV", t: "THE BOARD", s: `RIA ${fmt(S.ria)}   YOU ${fmt(S.you)}`, built: DONE.arkiv },
  { k: "03 // HEDERA x402", t: "PAY HER GHOST", s: "STRAIGHT TO THE RUNNER AHEAD", built: DONE.hedera },
  { k: "04 // WORLD ID", t: "LIST YOURS", s: "AGENT PASS: YOU APPROVE", built: DONE.world },
];
const MX = 90, MY = BAR + 74, MW_ = 1065, MH = 639, CX = MX + MW_ + 50;  // the monitor (5:3, the console's own shape)
const CW = W - CX - 70, CH = 120, CG = 12, CY = MY + 36;

const stepAt = (f: number) => STEP_AT.reduce((k, a, i) => (f >= a ? i : k), -1);

/** The console's screen, full size: the real launcher on each step, cut hard from one to the next. */
const Monitor: React.FC<{ f: number }> = ({ f }) => {
  const k = stepAt(f), on = prog(f, 0, 10);
  const step = S.steps[Math.max(0, k)];
  const img = k < 0 ? 0 : clamp(Math.floor((f - STEP_AT[k]) / S.every), 0, S.images[step] - 1);
  const flash = k >= 0 ? clamp(1 - (f - STEP_AT[k]) / 4) * 0.35 : 0;
  return (
    <>
      <div style={{ position: "absolute", left: MX - 12, top: MY - 12, width: MW_ + 24, height: MH + 24, background: "#0d0f11", border: "1px solid #2a2d31",
        boxShadow: "0 40px 120px rgba(0,0,0,0.8), 0 0 80px rgba(124,196,255,0.08)" }} />
      <div style={{ position: "absolute", left: MX, top: MY, width: MW_, height: MH, overflow: "hidden", background: "#000",
        transform: `scaleY(${lerp(0.02, 1, easeInOut(on))})` }}>
        {k >= 0 ? <Img src={staticFile(`handler/${step}/${String(img).padStart(2, "0")}.jpg`)} style={{ width: "100%", height: "100%" }} /> : null}
        <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      </div>
      <div style={{ position: "absolute", left: MX, top: MY - 46, opacity: prog(f, 6, 12) }}>
        <Mono s={15} c={MW.text} w={700} ls="0.28em">{"THE CONSOLE'S SCREEN // DRAWN BY THE LAUNCHER // MOCK SPONSORS"}</Mono>
      </div>
    </>
  );
};

/** The four steps, one card each, the one on the monitor lit; every one built on the console, its call at the event. */
const Steps: React.FC<{ f: number }> = ({ f }) => {
  const k = stepAt(f);
  return (
    <>
      <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ position: "absolute", left: CX, top: MY - 6, opacity: f > 8 ? 1 : 0 }}>PB // THE SPONSOR STEPS</Mono>
      {STEPS.map((s, i) => {
        const now = i === k;
        const col = now ? MW.blue : MW.faint;
        return (
          <Card key={s.k} f={f} at={14 + i * 9} x={CX} y={CY + i * (CH + CG)} w={CW} h={CH} head={s.k} accent={col} headCol={now ? MW.blue : MW.dim}>
            <div style={{ position: "absolute", left: 0, top: -2, fontFamily: "Archivo Black", fontSize: 28, color: now ? MW.text : MW.dim, lineHeight: 1 }}>{s.t}</div>
            <Mono s={14} c={now ? MW.text : MW.dim} style={{ position: "absolute", left: 0, top: 34, lineHeight: 1.3 }}>{s.s}</Mono>
            <div style={{ position: "absolute", right: 0, top: 0, textAlign: "right" }}>
              <Mono s={14} c={MW.green} w={700} ls="0.16em">UI: BUILT</Mono>
              <Mono s={14} c={s.built ? MW.green : MW.amber} w={700} ls="0.16em" style={{ marginTop: 8 }}>{s.built ? "CALL: BUILT" : "CALL: AT THE EVENT"}</Mono>
            </div>
          </Card>
        );
      })}
      <Mono s={14} c={MW.dim} ls="0.14em" style={{ position: "absolute", left: CX, top: CY + 4 * (CH + CG) + 6, lineHeight: 1.4, opacity: prog(f, 60, 70) }}>
        {"ON SCREEN: RIA'S SHIPPED LOG, A REAL SECOND RUN.\nTHE OTHER NAMES AND EVERY CALL: MOCK."}
      </Mono>
    </>
  );
};

export const Handler: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${1 + 0.0066 * (f / 60)})`, transformOrigin: "50% 48%" }}>
        <Board f={f} t={clamp(f / HANDLER_LEN)} dir={-0.8}>
          <Monitor f={f} />
          <Steps f={f} />
        </Board>
      </AbsoluteFill>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.7) 100%)" }} />
      <Subs f={f} lines={LINES} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, HANDLER_LEN - 8, HANDLER_LEN)) }} />
    </AbsoluteFill>
  );
};

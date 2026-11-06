import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { FONT } from "../theme";
import { clamp, easeInOut, easeOutExpo, lerp, prog, rnd } from "../util";
import { BAR, Bars, Card, H, kick, Line, Mono, MW, Row, Slate, Subs, W } from "./common";
import REEL from "./reel.json";

/* The games, after Part III: the five games built for the console, eight seconds of each, in the primer's look (a CRT on
   the tactical board). All footage is the shipped ROMs played headless on their recorded routes
   (prep/capture_gameplay.py window <ID> <FIRST> 480 reel), one game frame per film frame; the input log beside each is
   the same route's real key bits (prep/reel_keys.py). Sponsor art inside the games is art only: no claim rides on it. */

export const INTRO = 70, SHOT = 480, OUTRO = 240;
export const REEL_LEN = INTRO + 5 * SHOT + OUTRO;
export const SHORT_SHOT = 240;                                       // the submission cut: four seconds a game
export const REEL_SHORT_LEN = INTRO + 5 * SHORT_SHOT + OUTRO;
const FOOT = 480;                                                    // frames of footage captured per game
type Gid = keyof typeof REEL;
type Clock = { x0: number; y0: number; x1: number; y1: number; tag: string; above: boolean; lift?: number };
const GAMES: { id: Gid; name: string; genre: string; rows: [string, string][]; clock: Clock }[] = [
  { id: "SHIP", name: "SHIP IT!", genre: "HACKATHON OFFICE SIM", rows: [["SETTING", "ETHGLOBAL MUMBAI"], ["GOAL", "SHIP BEFORE THE DEADLINE"]],
    clock: { x0: 103, y0: 147, x1: 136, y1: 159, tag: "HACKATHON CLOCK // 36 H", above: true, lift: 34 } },
  { id: "RUSH", name: "RUSH HOUR", genre: "PLATFORMER", rows: [["SETTING", "MUMBAI, ON THE LOCAL TRAINS"], ["GOAL", "MAKE REGISTRATION"]],
    clock: { x0: 101, y0: 1, x1: 143, y1: 14, tag: "THE CLOCK", above: false } },
  { id: "ZIPG", name: "ZIP", genre: "MOMENTUM PLATFORMER", rows: [["SETTING", "THE VENUE NETWORK"], ["GOAL", "LAPTOP TO DEMO SCREEN"]],
    clock: { x0: 1, y0: 20, x1: 40, y1: 34, tag: "THE CLOCK", above: false } },
  { id: "MDGP", name: "MARINE DRIVE GP", genre: "MODE 7 KART RACER", rows: [["SETTING", "MARINE DRIVE, MUMBAI"], ["GOAL", "3 LAPS, 3 RIVALS"]],
    clock: { x0: 94, y0: 1, x1: 146, y1: 15, tag: "THE CLOCK", above: false } },
  { id: "SEGF", name: "SEGFAULT", genre: "FIRST-PERSON SHOOTER", rows: [["SETTING", "THE BUILD SERVER ROOM"], ["GOAL", "REBOOT THE SERVER"]],
    clock: { x0: 127, y0: 145, x1: 157, y1: 159, tag: "THE CLOCK", above: true } },
];
const timing = (shot: number) => {
  const at = (i: number) => INTRO + i * shot;
  return { at, out0: at(5), len: at(5) + OUTRO };
};
const linesFor = (shot: number): Line[] => {
  const { at, out0 } = timing(shot);
  const last = { at: out0 + 22, len: 214, who: "Handler", text: "Five games. Any run in any of them can be checked, by anyone." };
  if (shot < SHOT) return [                                          // four seconds a game: a name and a hook
    { at: at(0) + 16, len: 200, who: "Handler", text: "Ship It: run the hackathon office." },
    { at: at(1) + 16, len: 200, who: "Handler", text: "Rush Hour: Mumbai's trains, against the clock." },
    { at: at(2) + 16, len: 200, who: "Handler", text: "Zip: a packet racing through the venue." },
    { at: at(3) + 16, len: 200, who: "Handler", text: "Marine Drive GP: three laps, three rivals." },
    { at: at(4) + 16, len: 200, who: "Handler", text: "Segfault: bugs in the server room." },
    last,
  ];
  return [
    { at: at(0) + 24, len: 300, who: "Handler", text: "Ship It: run the hackathon office, and ship before the deadline." },
    { at: at(1) + 24, len: 300, who: "Handler", text: "Rush Hour: late for registration, across Mumbai's streets and train roofs." },
    { at: at(2) + 24, len: 290, who: "Handler", text: "Zip: a data packet, racing through the venue's network." },
    { at: at(3) + 24, len: 300, who: "Handler", text: "Marine Drive GP: three laps of the seafront, against three rivals." },
    { at: at(4) + 24, len: 310, who: "Handler", text: "Segfault: the night before demo day, and the server room is full of bugs." },
    last,
  ];
};
const KEYS = ["A", "B", "SEL", "STA", "RIGHT", "LEFT", "UP", "DOWN", "R", "L"];
const keyName = (k: number) => KEYS.filter((_, i) => (k >> i) & 1).join(" + ") || "NONE";
const num = (n: number, w = 5) => String(n).padStart(w, "0").replace(/\B(?=(\d{3})+(?!\d))/g, ",");

/** One game on a CRT: its frame idx (0..479) of the reel footage, pixels kept square, scanlines and glass. `on` (0..1)
    is the power-on: a bright line opening to the full picture. */
const Screen: React.FC<{ id: Gid; idx: number; w: number; h: number; on?: number }> = ({ id, idx, w, h, on = 1 }) => {
  const gw = w * 0.9;                                                  // the 3:2 game inside the 5:3 panel
  const open = easeOutExpo(prog(on, 0.25, 1));
  return (
    <div style={{ position: "relative", width: w, height: h, borderRadius: 18, background: "#08090a",
      boxShadow: "0 0 0 14px #15171a, 0 0 0 16px #2a2d31, 0 40px 120px rgba(0,0,0,0.8), 0 0 90px rgba(124,196,255,0.12)" }}>
      <div style={{ position: "absolute", left: (w - gw) / 2, top: 0, width: gw, height: h, overflow: "hidden",
        transform: `scaleY(${lerp(0.012, 1, open)})`, opacity: on > 0 ? 1 : 0 }}>
        <Img src={staticFile(`game/reel/${id}/${String(Math.max(0, Math.min(FOOT - 1, Math.floor(idx)))).padStart(4, "0")}.png`)}
          style={{ width: gw, height: h, imageRendering: "pixelated", filter: `saturate(1.08) contrast(1.05) brightness(${lerp(3.5, 1, open)})` }} />
      </div>
      <div style={{ position: "absolute", inset: 0, borderRadius: 18, pointerEvents: "none", opacity: 0.22,
        backgroundImage: "repeating-linear-gradient(0deg, rgba(0,0,0,0.9) 0px, rgba(0,0,0,0.9) 1px, transparent 1px, transparent 3px)" }} />
      <div style={{ position: "absolute", inset: 0, borderRadius: 18, pointerEvents: "none",
        background: "radial-gradient(ellipse at 30% 20%, rgba(255,255,255,0.10), rgba(255,255,255,0) 45%), radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.45) 100%)" }} />
    </div>
  );
};

/** The primer's tactical board, its drift per shot: t (0..1) through the shot, dir which way it swings. */
export const Board: React.FC<{ f: number; t: number; dir: number; children: React.ReactNode }> = ({ f, t, dir, children }) => (
  <div style={{ position: "absolute", inset: 0, perspective: 1700, perspectiveOrigin: "50% 45%" }}>
    <div style={{ position: "absolute", left: -160, top: -100, width: W + 320, height: H + 200, transformStyle: "preserve-3d",
      transform: `rotateY(${dir * lerp(-4.5, 3.5, t)}deg) rotateX(${lerp(2.5, 1, t)}deg) translateZ(${lerp(-40, 40, t)}px)` }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 42%, #171a1d 0%, #0b0d0f 55%, #040506 100%)" }} />
      <div style={{ position: "absolute", inset: 0, opacity: 0.13,
        backgroundImage: "linear-gradient(rgba(124,196,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.35) 1px, transparent 1px)",
        backgroundSize: "64px 64px" }} />
      {Array.from({ length: 30 }, (_, i) => (
        <Mono key={i} s={12} c={MW.faint} style={{ position: "absolute", left: 60 + (i % 2) * 2080, top: 170 + Math.floor(i / 2) * 26, opacity: 0.4 }}>
          {`${(0x2000 + Math.floor(rnd(i, 7) * 50000)).toString(16).toUpperCase()}  ${(rnd(i, 8) * 99).toFixed(2)}  ${rnd(i, 9) > 0.5 ? "RUN" : "---"}`}
        </Mono>
      ))}
      <div style={{ position: "absolute", left: 0, right: 0, top: ((f * 3.2) % (H + 600)) - 300, height: 220, opacity: 0.5,
        background: "linear-gradient(180deg, rgba(124,196,255,0) 0%, rgba(124,196,255,0.06) 50%, rgba(124,196,255,0) 100%)" }} />
      {Array.from({ length: 46 }, (_, i) => {
        const x = rnd(i, 21) * (W + 300), y = (rnd(i, 22) * (H + 200) - f * (0.15 + rnd(i, 23) * 0.35)) % (H + 200);
        return <div key={i} style={{ position: "absolute", left: x, top: y < 0 ? y + H + 200 : y, width: 3 + rnd(i, 24) * 4, height: 3 + rnd(i, 24) * 4,
          borderRadius: "50%", background: "rgba(255,214,170,0.5)", filter: `blur(${1 + rnd(i, 25) * 2}px)`, opacity: 0.25 + rnd(i, 26) * 0.4 }} />;
      })}
      <div style={{ position: "absolute", left: 160, top: 100, width: W, height: H }}>{children}</div>
    </div>
  </div>
);

/** The live input log: the route's real key bits, one column per frame, the newest on the right; lit = held. */
const InputLog: React.FC<{ id: Gid; t: number; x: number; y: number; w: number; appear: number }> = ({ id, t, x, y, w, appear }) => {
  const R = REEL[id];
  const N = 96, cw = (w - 64) / N, rh = 11, gap = 2;
  const now = R.lead + Math.floor(t);
  const cur = R.keys[now] ?? 0;
  const cols = Array.from({ length: N }, (_, c) => R.keys[now - (N - 1) + c] ?? 0);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, opacity: appear }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: MW.red, boxShadow: `0 0 10px ${MW.red}`, opacity: Math.floor(t / 24) % 2 ? 0.35 : 1 }} />
          <Mono s={15} c={MW.orange} w={700} ls="0.28em">INPUT LOG // LIVE</Mono>
        </div>
        <Mono s={15} c={MW.amber} w={700} ls="0.08em">{`FRAME ${num(R.first + Math.floor(t))} / ${num(R.total)}`}</Mono>
      </div>
      <div style={{ position: "relative", marginTop: 12, height: KEYS.length * (rh + gap) }}>
        {KEYS.map((k, r) => (
          <Mono key={k} s={11} c={(cur >> r) & 1 ? MW.amber : MW.dim} ls="0.1em" style={{ position: "absolute", left: 0, top: r * (rh + gap) - 2 }}>{k}</Mono>
        ))}
        <svg width={w - 64} height={KEYS.length * (rh + gap)} style={{ position: "absolute", left: 64, top: 0 }}>
          {KEYS.map((_, r) => <rect key={r} x={0} y={r * (rh + gap)} width={w - 64} height={rh} fill="rgba(40,46,56,0.55)" />)}
          {cols.map((k, c) => KEYS.map((_, r) => ((k >> r) & 1 ? (
            <rect key={`${c}.${r}`} x={c * cw} y={r * (rh + gap)} width={Math.max(1, cw - 0.6)} height={rh} fill={c === N - 1 ? "#fff2c8" : "#ffcf7a"} opacity={0.35 + 0.65 * (c / N)} />
          ) : null)))}
          <rect x={(N - 1) * cw - 1} y={-2} width={cw + 2} height={KEYS.length * (rh + gap) + 2} fill="none" stroke={MW.amber} strokeWidth={1.2} />
        </svg>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
        <Mono s={13} c={MW.dim} ls="0.2em">HELD NOW</Mono>
        <Mono s={15} c={cur ? MW.amber : MW.faint} w={700} ls="0.12em">{keyName(cur)}</Mono>
      </div>
    </div>
  );
};

/** The game strip along the top, MW's loadout tabs: the one on screen lit, the ones shown already dimmed and ticked. */
const Tabs: React.FC<{ f: number; cur: number }> = ({ f, cur }) => (
  <div style={{ position: "absolute", left: 90, right: 90, top: BAR + 22, display: "flex", gap: 14, opacity: prog(f, INTRO - 16, INTRO - 6) }}>
    {GAMES.map((g, i) => {
      const on = i === cur, done = i < cur || cur === 5;
      return (
        <div key={g.id} style={{ flex: 1, display: "flex", alignItems: "center", gap: 12, height: 36, paddingLeft: 14,
          background: on ? "rgba(240,138,36,0.16)" : "rgba(8,9,10,0.6)", borderBottom: `2px solid ${on ? MW.orange : done ? MW.green : MW.faint}` }}>
          <Mono s={13} c={on ? MW.orange : MW.faint} w={700} ls="0.2em">{`0${i + 1}`}</Mono>
          <Mono s={15} c={on ? MW.text : done ? MW.dim : MW.faint} w={700} ls="0.16em">{g.name}</Mono>
          {done && !on ? <div style={{ marginLeft: "auto", marginRight: 12, width: 8, height: 8, background: MW.green, boxShadow: `0 0 8px ${MW.green}` }} /> : null}
        </div>
      );
    })}
  </div>
);

/** The game's own clock, called out as in the primer: an amber box over it in game pixels, and its tag. */
const ClockCall: React.FC<{ c: Clock; t: number; mx: number; my: number; w: number; h: number }> = ({ c, t, mx, my, w, h }) => {
  const k = prog(t, 64, 74) * (1 - prog(t, 300, 312));
  if (k <= 0) return null;
  const gw = w * 0.9, sc = gw / 240, gx = mx + (w - gw) / 2;
  const x = gx + c.x0 * sc - 6, y = my + c.y0 * (h / 160) - 6, bw = (c.x1 - c.x0) * sc + 12, bh = (c.y1 - c.y0) * (h / 160) + 12;
  const blink = t < 84 && Math.floor(t / 3) % 2 === 1 ? 0.3 : 1;
  return (
    <>
      <div style={{ position: "absolute", left: x, top: y, width: bw, height: bh, border: `2px solid ${MW.amber}`, opacity: k * blink,
        boxShadow: `0 0 18px ${MW.amber}66, inset 0 0 12px ${MW.amber}22`, transform: `scale(${lerp(1.18, 1, easeOutExpo(prog(t, 64, 76)))})` }} />
      <div style={{ position: "absolute", left: x, top: c.above ? y - 34 - (c.lift ?? 0) : y + bh + 8, padding: "4px 10px", background: "rgba(5,5,6,0.86)",
        borderLeft: `3px solid ${MW.amber}`, opacity: k * prog(t, 70, 76) }}>
        <Mono s={15} c={MW.amber} w={700} ls="0.22em">{c.tag}</Mono>
      </div>
    </>
  );
};

/** One game's shot: the CRT on one side, its file and the live input log on the other; sides alternate. */
const GameShot: React.FC<{ f: number; i: number; at: (i: number) => number }> = ({ f, i, at }) => {
  const g = GAMES[i], t = f - at(i);
  const left = i % 2 === 0;
  const MWd = 1000, MH = 600, MX = left ? 110 : W - 110 - MWd, MY = BAR + 96;
  const CX = left ? MX + MWd + 90 : 110, CW = 600;
  const on = prog(t, 0, 9);
  const fit = Math.min(92, (CW / (g.name.length * 0.5)));
  return (
    <>
      <div style={{ position: "absolute", left: MX - 300, top: MY - 200, width: MWd + 600, height: MH + 400, opacity: 0.55 * on,
        background: "radial-gradient(ellipse at 50% 50%, rgba(140,190,255,0.16) 0%, rgba(140,190,255,0.05) 40%, rgba(0,0,0,0) 70%)" }} />
      <div style={{ position: "absolute", left: MX, top: MY }}>
        <Screen id={g.id} idx={t} w={MWd} h={MH} on={on} />
      </div>
      <ClockCall c={g.clock} t={t} mx={MX} my={MY} w={MWd} h={MH} />
      <div style={{ position: "absolute", left: CX, top: MY - 6, width: CW }}>
        <Mono s={17} c={MW.orange} w={700} ls="0.4em" style={{ opacity: t > 8 && !(t > 10 && t < 12) ? 1 : 0 }}>{`GAME 0${i + 1} / 05`}</Mono>
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: fit, lineHeight: 1, letterSpacing: "0.02em", color: MW.text, marginTop: 14,
          clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, 12, 26))}% 0 0)`, textShadow: "0 0 30px rgba(124,196,255,0.18)" }}>{g.name}</div>
        <Mono s={18} c={MW.dim} ls="0.26em" style={{ marginTop: 14, opacity: prog(t, 22, 30) }}>{g.genre}</Mono>
        <div style={{ height: 2, background: MW.orange, marginTop: 18, width: `${100 * easeOutExpo(prog(t, 24, 40))}%`, opacity: 0.8 }} />
      </div>
      <Card f={t} at={34} x={CX} y={MY + 196} w={CW} h={148} head="FILE">
        {g.rows.map(([k, v]) => <Row key={k} k={k} v={v} />)}
        <Row k="ROUTE" v="A RECORDED FULL RUN" c={MW.amber} />
      </Card>
      <InputLog id={g.id} t={t} x={CX} y={MY + 384} w={CW} appear={prog(t, 50, 60)} />
    </>
  );
};

/** The wall at the end: all five running at once, then the line that ties them to the proof. */
const Wall: React.FC<{ f: number; out0: number }> = ({ f, out0 }) => {
  const t = f - out0;
  const w = 440, h = 264, gx = 56;
  const pos = GAMES.map((_, i) => i < 3
    ? { x: (W - (3 * w + 2 * gx)) / 2 + i * (w + gx), y: BAR + 96 }
    : { x: (W - (2 * w + gx)) / 2 + (i - 3) * (w + gx), y: BAR + 96 + h + 46 });
  return (
    <>
      {GAMES.map((g, i) => {
        const s = i * 5, on = prog(t, s, s + 9);
        return (
          <div key={g.id} style={{ position: "absolute", left: pos[i].x, top: pos[i].y }}>
            <Screen id={g.id} idx={(t + 120 + i * 47) % FOOT} w={w} h={h} on={on} />
            <div style={{ position: "absolute", left: 10, top: 10, padding: "5px 10px", background: "rgba(5,5,6,0.82)", borderLeft: `3px solid ${MW.orange}`,
              opacity: prog(t, s + 10, s + 14) }}>
              <Mono s={14} c={MW.text} w={700} ls="0.18em">{`0${i + 1}  ${g.name}`}</Mono>
            </div>
            <div style={{ position: "absolute", right: 10, top: 10, display: "flex", alignItems: "center", gap: 8, padding: "5px 10px",
              background: "rgba(5,5,6,0.82)", opacity: prog(t, 40 + i * 6, 46 + i * 6) }}>
              <div style={{ width: 8, height: 8, background: MW.green, boxShadow: `0 0 8px ${MW.green}` }} />
              <Mono s={13} c={MW.green} w={700} ls="0.2em">LOGGED</Mono>
            </div>
          </div>
        );
      })}
      {t > 90 ? (
        <div style={{ position: "absolute", left: pos[4].x + w + 64, top: pos[4].y + 84, width: 300,
          transform: `scale(${lerp(1.25, 1, easeOutExpo(prog(t, 90, 102)))})`, transformOrigin: "0% 50%" }}>
          <Mono s={22} c={MW.green} w={700} ls="0.3em">5 / 5 GAMES</Mono>
          <div style={{ height: 2, background: MW.green, opacity: 0.7, marginTop: 12, width: `${100 * easeOutExpo(prog(t, 96, 110))}%` }} />
          <Mono s={15} c={MW.dim} ls="0.22em" style={{ marginTop: 12, opacity: prog(t, 104, 112) }}>{"EVERY RUN\nLOGGED FROM BOOT"}</Mono>
        </div>
      ) : null}
    </>
  );
};

/** shot: frames a game (SHOT, or SHORT_SHOT in the submission cut, which also has shorter lines). */
export const GameReel: React.FC<{ shot?: number }> = ({ shot = SHOT }) => {
  const f = useCurrentFrame();
  const { at, out0, len: total } = timing(shot);
  const LINES = linesFor(shot);
  const i = f < INTRO ? -1 : Math.min(5, Math.floor((f - INTRO) / shot));
  const s0 = i < 0 ? 0 : at(i), len = i < 0 ? INTRO : i === 5 ? OUTRO : shot;
  const t = f - s0;
  const push = 1 + 0.008 * (t / 60);                                   // MW3's locked-off creep, reset on every cut
  const cuts = [at(0), at(1), at(2), at(3), at(4), out0];
  const c = cuts.filter((q) => f >= q && f < q + 3)[0];
  const flash = c !== undefined ? 0.24 - 0.08 * (f - c) : 0;
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${push}) ${kick(f, cuts, 5)}`, transformOrigin: "50% 48%", opacity: i < 0 ? prog(f, 0, 14) : 1 }}>
        <Board f={f} t={clamp(t / len)} dir={i < 0 ? 0.4 : i % 2 === 0 ? 1 : -1}>
          {i >= 0 && i < 5 ? <GameShot f={f} i={i} at={at} /> : null}
          {i === 5 ? <Wall f={f} out0={out0} /> : null}
        </Board>
      </AbsoluteFill>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.72) 100%)" }} />
      {i < 0 ? (
        <Slate f={f} part="LOADOUT // BUILT FOR THE CONSOLE" title="FIVE GAMES" num="5" len={INTRO} />
      ) : null}
      <Tabs f={f} cur={Math.max(0, i)} />
      <Subs f={f} lines={LINES} />
      <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />
      <Bars />
      <div style={{ position: "absolute", inset: 0, background: "#000", opacity: easeInOut(prog(f, total - 12, total)) }} />
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, Freeze, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame } from "remotion";
import { BAR, Card, H, Line, Mono, MW, Row, Subs, W } from "../acts/common";
import { FONT } from "../theme";
import { clamp, easeOutExpo, lerp, prog, rnd } from "../util";

/* The final film's kit: the house look (MW3 briefing) for new footage. Everything here is a frame of the shot it sits
   in; scenes pass their own local frame. Placeholders for takes not shot yet carry TODO(live) in small amber text in the
   top bar, so the loop can find and swap them. */

export const FPS = 60;
export const sec = (s: number) => Math.round(s * FPS);
export const TOP = BAR + 14, BOT = H - BAR - 14;                      // the picture between the letterbox bars

/** The dark tactical board behind framed footage: radial shade, a fine grid, a slow light scan. */
export const Board: React.FC<{ f: number; tint?: string }> = ({ f, tint = "124,196,255" }) => (
  <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 44%, #171a1d 0%, #0b0d0f 55%, #040506 100%)", overflow: "hidden" }}>
    <AbsoluteFill style={{ opacity: 0.11, backgroundSize: "64px 64px",
      backgroundImage: `linear-gradient(rgba(${tint},0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(${tint},0.35) 1px, transparent 1px)` }} />
    <div style={{ position: "absolute", left: 0, right: 0, top: ((f * 3.2) % (H + 600)) - 300, height: 220, opacity: 0.45,
      background: `linear-gradient(180deg, rgba(${tint},0) 0%, rgba(${tint},0.05) 50%, rgba(${tint},0) 100%)` }} />
    {Array.from({ length: 22 }, (_, i) => (
      <Mono key={i} s={11} c={MW.faint} style={{ position: "absolute", left: 40 + (i % 2) * 1780, top: 150 + Math.floor(i / 2) * 26, opacity: 0.35 }}>
        {`${(0x2000 + Math.floor(rnd(i, 7) * 50000)).toString(16).toUpperCase()}  ${(rnd(i, 8) * 99).toFixed(2)}`}
      </Mono>
    ))}
  </AbsoluteFill>
);

/** MW3's locked-off creep: a linear push-in of about 0.66 % a second, no easing. */
export const Push: React.FC<{ f: number; origin?: string; rate?: number; children: React.ReactNode }> = ({ f, origin = "50% 48%", rate = 0.0066, children }) => (
  <AbsoluteFill style={{ transform: `scale(${1 + rate * (f / FPS)})`, transformOrigin: origin }}>{children}</AbsoluteFill>
);

/** Where a shot came from, top left inside the letterbox bar. */
export const Tag: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ position: "absolute", left: 60, top: BAR - 50, display: "flex", alignItems: "center", gap: 12 }}>
    <div style={{ width: 11, height: 11, background: MW.orange }} />
    <Mono s={22} c="#b4b6b3" w={700} ls="0.1em">{text}</Mono>
  </div>
);

/** A take that is not shot yet: amber text, top right inside the bar. */
export const Todo: React.FC<{ text: string }> = ({ text }) => (
  <Mono s={22} c={MW.amber} w={700} ls="0.06em" style={{ position: "absolute", right: 60, top: BAR - 50, textAlign: "right" }}>
    {`TODO(live) ${text}`}
  </Mono>
);

/** A white flash on the first frames of a cut (the acts' grammar). */
export const CutFlash: React.FC<{ f: number; amt?: number }> = ({ f, amt = 0.08 }) =>
  f < 3 ? <AbsoluteFill style={{ background: "#fff", opacity: amt * (3 - f) }} /> : null;

export const Vignette: React.FC<{ k?: number }> = ({ k = 0.7 }) => (
  <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 48%, rgba(0,0,0,${k}) 100%)`, pointerEvents: "none" }} />
);

/** The console's 800 x 480 screen in a dark bezel. Children fill the screen. */
export const Screen: React.FC<{ x: number; y: number; w: number; children: React.ReactNode; glow?: string }> = ({ x, y, w, children, glow = "124,196,255" }) => {
  if (w <= 0) return null;                                              // SAFE mode hides an empty console frame
  const h = (w * 480) / 800;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: 10, overflow: "hidden", background: "#07080a",
      boxShadow: `0 0 0 10px #141619, 0 0 0 12px #2a2d31, 0 30px 90px rgba(0,0,0,0.75), 0 0 80px rgba(${glow},0.10)` }}>
      {children}
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none",
        background: "radial-gradient(ellipse at 28% 18%, rgba(255,255,255,0.06), rgba(255,255,255,0) 45%)" }} />
    </div>
  );
};

/** The real console UI (record.py, 800 x 480, 30 fps), from a second of the take; `hold` freezes that frame. */
export const Rec: React.FC<{ file?: string; from: number; hold?: boolean }> = ({ file = "final/rec/sample_board.mp4", from, hold }) => {
  const v = <OffthreadVideo src={staticFile(file)} trimBefore={sec(from)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />;
  return hold ? <Freeze frame={0}>{v}</Freeze> : v;
};

/** The earlier demos' launcher frames (mock sponsors, MOCK pill on screen): a stand-in until the live take.
    `dir` is under public/, frames are NNN.jpg (or NN.jpg with digits=2). */
export const Flip: React.FC<{ f: number; dir: string; count: number; every?: number; start?: number; digits?: number }> = ({ f, dir, count, every = 2, start = 0, digits = 3 }) => {
  const i = Math.min(count - 1, start + Math.max(0, Math.floor(f / every)));
  return <Img src={staticFile(`${dir}/${String(i).padStart(digits, "0")}.jpg`)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />;
};

/** A web still (1600 x 1000) framed on a focus rectangle (image px), with the push-in about the focus centre. */
export const Web: React.FC<{ f: number; src: string; focus: [number, number, number, number]; to?: [number, number, number, number];
  focus2?: [number, number, number, number]; at2?: number; dim?: number }> = ({ f, src, focus, to, focus2, at2 = 1e9, dim = 0 }) => {
  const [ax, ay, aw, ah] = to ?? [0, TOP - 14, W, BOT - TOP + 28];
  const k = focus2 ? easeOutExpo(prog(f, at2, at2 + 40)) : 0;                     // an optional second framing, eased in
  const fx = focus2 ? focus.map((v, i) => lerp(v, focus2[i], k)) : focus;
  const s = Math.min(aw / fx[2], ah / fx[3]) * (1 + 0.0066 * (f / FPS));
  // keep the page covering the frame: the centre never lets an edge of the still show inside the area
  const hw = aw / s / 2, hh = ah / s / 2;
  const cx = hw * 2 >= 1600 ? 800 : Math.min(1600 - hw, Math.max(hw, fx[0] + fx[2] / 2));
  const cy = hh * 2 >= 1000 ? 500 : Math.min(1000 - hh, Math.max(hh, fx[1] + fx[3] / 2));
  return (
    <div style={{ position: "absolute", left: ax, top: ay, width: aw, height: ah, overflow: "hidden", background: "#0b0c0d" }}>
      <Img src={staticFile(src)} style={{ position: "absolute", width: 1600 * s, height: 1000 * s, maxWidth: "none",
        left: aw / 2 - cx * s, top: ah / 2 - cy * s }} />
      {dim ? <AbsoluteFill style={{ background: `rgba(0,0,0,${dim})` }} /> : null}
    </div>
  );
};

/** A URL as a caption strip, for web stills shot without the address bar. */
export const Url: React.FC<{ f: number; at?: number; text: string; x?: number; y?: number; s?: number }> = ({ f, at = 10, text, x = 70, y = TOP + 10, s = 20 }) => {
  if (f < at) return null;
  const k = prog(f, at, at + 12);
  return (
    <div style={{ position: "absolute", left: x, top: y, background: "rgba(5,5,6,0.88)", borderLeft: `3px solid ${MW.blue}`, padding: "8px 18px 9px",
      clipPath: `inset(0 ${100 - 100 * k}% 0 0)` }}>
      <Mono s={s} c={MW.ice} w={700} ls="0.04em">{text}</Mono>
    </div>
  );
};

/** A stand-in for a take not shot yet, drawn in the console's own type: what the screen will show, values only where a
    real screen already showed them, `<take>` everywhere else. */
export const ConsolePH: React.FC<{ f: number; id: string; title: string; rows?: [string, string][]; note?: string; accent?: string }> = ({ f, id, title, rows = [], note, accent = "#7cc4ff" }) => (
  <AbsoluteFill style={{ background: "linear-gradient(180deg, #10141b 0%, #0b0e13 100%)" }}>
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 46, background: "#0a0c10", display: "flex", alignItems: "center", gap: 22, paddingLeft: 22 }}>
      {["PB", "World", "Arkiv", "Hedera"].map((t) => <Mono key={t} s={18} c="#c9d1d9" w={700}>{t}</Mono>)}
    </div>
    <div style={{ position: "absolute", left: 230, right: 34, top: 74, bottom: 210, background: "#161b22", borderRadius: 10, border: `3px solid ${accent}66`, padding: "26px 34px" }}>
      <div style={{ fontFamily: FONT.ui, fontWeight: 700, fontSize: 42, color: "#e6edf3", marginBottom: 22, lineHeight: 1.1 }}>
        {title.split(/(<take[^>]*>)/).map((p, i) => <span key={i} style={{ color: p.startsWith("<take") ? MW.amber : undefined }}>{p}</span>)}
      </div>
      {rows.map(([k, v], i) => (
        <div key={i} style={{ display: "flex", gap: 24, marginBottom: 12, opacity: prog(f, 6 + i * 4, 12 + i * 4) }}>
          <Mono s={24} c="#8b949e" style={{ width: 290 }}>{k}</Mono>
          <Mono s={24} c={v.includes("<take") ? MW.amber : "#e6edf3"} w={700}>{v}</Mono>
        </div>
      ))}
    </div>
    <div style={{ position: "absolute", left: 30, top: 300, width: 170, height: 170, borderRadius: 14, border: "4px solid #3b4a66", background: "#22314d" }} />
    <div style={{ position: "absolute", left: 30, right: 34, bottom: 30, height: 150, borderRadius: 14, border: "4px solid #4a5f8a", background: "#1c2742", padding: "22px 30px" }}>
      <Mono s={24} c="#9fb0cc">{note ?? "PB's line, from the take"}</Mono>
    </div>
    <PHMark id={id} />
  </AbsoluteFill>
);

/** The mark every placeholder wears: its shot id, and that it is not a capture. */
export const PHMark: React.FC<{ id: string; dark?: boolean; bottom?: boolean }> = ({ id, dark, bottom }) => (
  <div style={{ position: "absolute", right: 14, ...(bottom ? { bottom: 14 } : { top: 54 }), background: dark ? "rgba(0,0,0,0.6)" : "rgba(255,178,63,0.12)", border: `1px solid ${MW.amber}`, padding: "3px 10px 4px" }}>
    <Mono s={16} c={MW.amber} w={700} ls="0.1em">{`PLACEHOLDER // ${id} // NOT A CAPTURE`}</Mono>
  </div>
);

/** A terminal window stand-in: the real command, and what the take is expected to print, marked as expected. */
export const TermPH: React.FC<{ f: number; id: string; x?: number; y?: number; w?: number; h?: number; lines: { t: string; c?: string; at?: number }[]; real?: boolean }> = ({ f, id, x = 150, y = TOP + 40, w = W - 300, h = 600, lines, real }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, background: "#0c0d0f", borderRadius: 8, border: "1px solid #2b2e33",
    boxShadow: "0 30px 90px rgba(0,0,0,0.7)", overflow: "hidden" }}>
    <div style={{ height: 34, background: "#1a1c20", display: "flex", alignItems: "center", paddingLeft: 16, gap: 8 }}>
      {["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 12, height: 12, borderRadius: 6, background: c, opacity: 0.6 }} />)}
      <Mono s={18} c="#8b949e" style={{ marginLeft: 12 }}>TERMINAL</Mono>
    </div>
    <div style={{ padding: "18px 26px" }}>
      {lines.map((l, i) => {
        const at = l.at ?? i * 10;
        if (f < at) return null;
        const cmd = l.t.startsWith("$ ");
        const n = cmd ? Math.floor((f - at) * 2.2) : 1e9;                               // commands type in
        return <Mono key={i} s={27} c={l.c ?? (cmd ? "#e6edf3" : "#7d8590")} style={{ marginBottom: 6, whiteSpace: "pre-wrap" }}>{l.t.slice(0, n)}</Mono>;
      })}
    </div>
    {real ? null : <PHMark id={id} bottom />}
  </div>
);

/** World App's sheet on the owner's phone, as a stand-in: the exact text the take must show. */
export const PhonePH: React.FC<{ f: number; id: string; x: number; y: number; h: number; title: string; text: string; button?: string }> = ({ f, id, x, y, h, title, text, button = "Approve" }) => {
  const w = h * 0.47;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: 36, background: "#0b0b0c", border: "3px solid #2c2e33",
      boxShadow: "0 30px 90px rgba(0,0,0,0.75)", overflow: "hidden" }}>
      <div style={{ position: "absolute", left: 14, right: 14, bottom: 14, top: h * 0.32, borderRadius: 26, background: "#f4f4f2", padding: "26px 24px" }}>
        <div style={{ fontFamily: FONT.sub, fontWeight: 600, fontSize: 28, color: "#111", marginBottom: 14 }}>{title}</div>
        <div style={{ fontFamily: FONT.sub, fontWeight: 500, fontSize: 25, color: "#222", lineHeight: 1.35 }}>
          {text.split(/(<take[^>]*>)/).map((p, i) => <span key={i} style={{ color: p.startsWith("<take") ? "#b26a00" : undefined }}>{p}</span>)}
        </div>
        <div style={{ position: "absolute", left: 24, right: 24, bottom: 24, height: 58, borderRadius: 29, background: "#111", display: "flex",
          alignItems: "center", justifyContent: "center", opacity: prog(f, 20, 30) }}>
          <div style={{ fontFamily: FONT.sub, fontWeight: 600, fontSize: 22, color: "#fff" }}>{button}</div>
        </div>
      </div>
      <Mono s={14} c="#8b949e" ls="0.2em" style={{ position: "absolute", left: 26, top: 64 }}>WORLD APP</Mono>
      <div style={{ position: "absolute", left: 0, right: 0, top: 120, display: "flex", justifyContent: "center" }}>
        <div style={{ background: "rgba(0,0,0,0.6)", border: `1px solid ${MW.amber}`, padding: "3px 10px 4px" }}>
          <Mono s={15} c={MW.amber} w={700} ls="0.1em">{`PLACEHOLDER // ${id}`}</Mono>
        </div>
      </div>
    </div>
  );
};

/** A browser-page stand-in (explorer, repo), for web takes that need the new build first. */
export const WebPH: React.FC<{ f: number; id: string; url: string; x?: number; y?: number; w?: number; h?: number; head: string; rows: [string, string][]; accent?: string }> = ({ f, id, url, x = 150, y = TOP + 30, w = W - 300, h = 620, head, rows, accent = MW.blue }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, background: "#121417", borderRadius: 8, border: "1px solid #2b2e33",
    boxShadow: "0 30px 90px rgba(0,0,0,0.7)", overflow: "hidden" }}>
    <div style={{ height: 52, background: "#1d2024", display: "flex", alignItems: "center", padding: "0 18px" }}>
      <div style={{ flex: 1, height: 34, borderRadius: 17, background: "#0d0f11", display: "flex", alignItems: "center", paddingLeft: 16 }}>
        <Mono s={20} c="#c9d1d9">{url}</Mono>
      </div>
    </div>
    <div style={{ padding: "26px 34px" }}>
      <Mono s={30} c="#e6edf3" w={700} style={{ marginBottom: 20 }}>{head}</Mono>
      {rows.map(([k, v], i) => (
        <div key={i} style={{ display: "flex", gap: 26, padding: "9px 0", borderBottom: "1px solid #24272b", opacity: prog(f, 8 + i * 5, 14 + i * 5) }}>
          <Mono s={25} c="#8b949e" style={{ width: Math.min(300, Math.round(w * 0.3)), flexShrink: 0 }}>{k}</Mono>
          <Mono s={25} c={v.includes("<take") ? MW.amber : accent} w={700} style={{ whiteSpace: "pre-wrap" }}>{v}</Mono>
        </div>
      ))}
    </div>
    <PHMark id={id} />
  </div>
);

/** The film's act slate (common.tsx's Slate, with the title sized to fit). */
export const Slate2: React.FC<{ f: number; part: string; title: string; num: string; len?: number }> = ({ f, part, title, num, len = 60 }) => {
  const ts = Math.min(92, Math.floor(1560 / (title.length * 0.98)));
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "radial-gradient(ellipse at 50% 46%, #15181b 0%, #0a0c0e 55%, #030405 100%)" }}>
      <AbsoluteFill style={{ opacity: 0.12, backgroundSize: "64px 64px",
        backgroundImage: "linear-gradient(rgba(124,196,255,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(124,196,255,0.35) 1px, transparent 1px)" }} />
      <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${1 + 0.05 * (f / len)})` }}>
        <div style={{ fontFamily: "Archivo Black", fontSize: 520, lineHeight: 1, color: "transparent", letterSpacing: "0.02em",
          WebkitTextStroke: `3px rgba(240,138,36,${(0.34 * prog(f, 0, 8)).toFixed(3)})` }}>{num}</div>
      </AbsoluteFill>
      <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 18 }}>
        <Mono s={24} c={MW.orange} w={700} ls="0.6em" style={{ opacity: f > 4 ? 1 : 0 }}>{part}</Mono>
        <div style={{ fontFamily: FONT.head, fontWeight: 700, fontSize: ts, lineHeight: 1, letterSpacing: "0.16em", paddingLeft: "0.16em", color: MW.text,
          whiteSpace: "nowrap", clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(f, 6, 18))}% 0 0)`, textShadow: "0 0 40px rgba(124,196,255,0.18)" }}>{title}</div>
        <div style={{ width: 620 * easeOutExpo(prog(f, 10, 24)), height: 3, background: MW.orange, opacity: 0.9 }} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** A shot: local frame, board, push-in, its media, cards, tag, TODO, subtitles; the bars are drawn once by the film. */
export type ShotProps = { f: number };
export const useLocal = () => useCurrentFrame();

/** Lines with times in seconds from the scene's start, ended where the next begins (minus a beat) or at `end`. */
export const lines = (end: number, ls: [number, string][], who = "Handler"): Line[] =>
  ls.map(([t, text], i) => {
    const at = sec(t);
    const next = i + 1 < ls.length ? sec(ls[i + 1][0]) - 6 : sec(end) - 4;
    return { at, len: next - at, who, text };
  });

export { Card, Mono, MW, Row, Subs, Sequence, clamp };

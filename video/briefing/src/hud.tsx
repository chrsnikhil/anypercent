import React from "react";
import { C, FONT, H, W, glow } from "./theme";
import { clamp, rnd } from "./util";

export const Mono: React.FC<{ size?: number; color?: string; style?: React.CSSProperties; children: React.ReactNode }> = ({
  size = 18, color = C.ink, style, children,
}) => (
  <div style={{ fontFamily: FONT.mono, fontSize: size, color, letterSpacing: "0.04em", whiteSpace: "pre", ...style }}>
    {children}
  </div>
);

export const Head: React.FC<{ size?: number; color?: string; weight?: number; spacing?: string; style?: React.CSSProperties; children: React.ReactNode }> = ({
  size = 40, color = C.ink, weight = 600, spacing = "0.14em", style, children,
}) => (
  <div style={{ fontFamily: FONT.head, fontWeight: weight, fontSize: size, color, letterSpacing: spacing, textTransform: "uppercase",
    whiteSpace: "pre", lineHeight: 1, ...style }}>
    {children}
  </div>
);

/** A block cursor that blinks at 2 Hz. */
export const Cursor: React.FC<{ f: number; color?: string; on?: boolean }> = ({ f, color = C.ink, on = true }) =>
  on && Math.floor(f / 15) % 2 === 0 ? <span style={{ background: color, color: "transparent", marginLeft: 2 }}>_</span> : null;

/** Corner brackets round a box. */
export const Brackets: React.FC<{ x: number; y: number; w: number; h: number; len?: number; color?: string; width?: number; opacity?: number }> = ({
  x, y, w, h, len = 22, color = C.ink, width = 2, opacity = 1,
}) => {
  const p = (d: string) => <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="square" />;
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity }} width={W} height={H}>
      {p(`M${x},${y + len} V${y} H${x + len}`)}
      {p(`M${x + w - len},${y} H${x + w} V${y + len}`)}
      {p(`M${x + w},${y + h - len} V${y + h} H${x + w - len}`)}
      {p(`M${x + len},${y + h} H${x} V${y + h - len}`)}
    </svg>
  );
};

/** The frame every shot sits in: an inset border with corner brackets and two corner labels. */
export const Frame: React.FC<{ f: number; tl?: string; tr?: string; bl?: string; br?: string; opacity?: number }> = ({
  f, tl, tr, bl, br, opacity = 1,
}) => {
  const m = 34;
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <Brackets x={m} y={m} w={W - 2 * m} h={H - 2 * m} len={44} color={C.ink} width={2} opacity={0.75} />
      <svg style={{ position: "absolute", inset: 0 }} width={W} height={H}>
        {/* ruler ticks along the top and bottom edges */}
        {Array.from({ length: 49 }, (_, i) => {
          const x = m + 120 + i * ((W - 2 * m - 240) / 48);
          const l = i % 8 === 0 ? 10 : 5;
          return (
            <g key={i} stroke={C.line} strokeOpacity={0.45} strokeWidth={1}>
              <line x1={x} y1={m} x2={x} y2={m + l} />
              <line x1={x} y1={H - m} x2={x} y2={H - m - l} />
            </g>
          );
        })}
      </svg>
      {tl ? <Mono size={17} color={C.ink} style={{ position: "absolute", left: m + 60, top: m + 18 }}>{tl}</Mono> : null}
      {tr ? <Mono size={17} color={C.ink} style={{ position: "absolute", right: m + 60, top: m + 18 }}>{tr}</Mono> : null}
      {bl ? <Mono size={15} color={C.dim} style={{ position: "absolute", left: m + 60, bottom: m + 16 }}>{bl}</Mono> : null}
      {br ? <Mono size={15} color={C.dim} style={{ position: "absolute", right: m + 60, bottom: m + 16 }}>{br}</Mono> : null}
    </div>
  );
};

/** A column of scrolling hex, like a data feed; deterministic per frame. */
export const DataFeed: React.FC<{ f: number; x: number; y: number; rows?: number; cols?: number; opacity?: number; seed?: number }> = ({
  f, x, y, rows = 14, cols = 4, opacity = 0.55, seed = 1,
}) => {
  const tick = Math.floor(f / 3);
  return (
    <div style={{ position: "absolute", left: x, top: y, opacity }}>
      {Array.from({ length: rows }, (_, r) => {
        const row = tick + r;
        const words = Array.from({ length: cols }, (_, c) =>
          Math.floor(rnd(row, c, seed) * 0xffff).toString(16).toUpperCase().padStart(4, "0"));
        const hot = rnd(row, 99, seed) > 0.9;
        return <Mono key={r} size={14} color={hot ? C.accent : C.dim} style={{ lineHeight: "19px" }}>{words.join(" ")}</Mono>;
      })}
    </div>
  );
};

/** Horizontal glitch bars over the whole frame for a few frames around `at`. */
export const Glitch: React.FC<{ f: number; at: number; len?: number }> = ({ f, at, len = 10 }) => {
  const k = f - at;
  if (k < 0 || k >= len) return null;
  const n = 7 + Math.floor(rnd(k, 3) * 6);
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {Array.from({ length: n }, (_, i) => {
        const y = rnd(k, i, 1) * H;
        const h = 2 + rnd(k, i, 2) * 38;
        const bright = rnd(k, i, 4) > 0.55;
        return (
          <div key={i} style={{ position: "absolute", left: rnd(k, i, 5) * 300 - 150, top: y, width: W + 300, height: h,
            background: bright ? `rgba(214, 238, 252, ${0.25 + rnd(k, i, 6) * 0.5})` : "rgba(0, 0, 0, 0.85)",
            mixBlendMode: bright ? "screen" : "normal" }} />
        );
      })}
    </div>
  );
};

/** Whole-frame x jitter used with Glitch. */
export const jitter = (f: number, at: number, len = 10) => {
  const k = f - at;
  return k >= 0 && k < len ? (rnd(k, 77) - 0.5) * 40 : 0;
};

/** A flash to white that decays. */
export const Flash: React.FC<{ f: number; at: number; len?: number; color?: string; peak?: number }> = ({
  f, at, len = 14, color = C.ink, peak = 0.9,
}) => {
  const k = f - at;
  if (k < 0 || k > len) return null;
  return <div style={{ position: "absolute", inset: 0, background: color, opacity: peak * Math.pow(1 - k / len, 2), mixBlendMode: "screen" }} />;
};

/** Text that types on, with a cursor while typing. */
export const TypeText: React.FC<{ f: number; text: string; start: number; cps: number; size?: number; color?: string;
  head?: boolean; style?: React.CSSProperties; cursor?: boolean }> = ({
  f, text, start, cps, size = 20, color = C.ink, head = false, style, cursor = true,
}) => {
  const n = Math.max(0, Math.min(text.length, Math.floor(((f - start) * cps) / 60)));
  if (f < start) return null;
  const typing = n < text.length;
  const content = (
    <>
      {text.slice(0, n)}
      <Cursor f={f} color={color} on={cursor && (typing || f - start < 40 + (text.length * 60) / cps)} />
    </>
  );
  return head ? <Head size={size} color={color} style={style}>{content}</Head> : <Mono size={size} color={color} style={style}>{content}</Mono>;
};

/** Fade helper for whole layers. */
export const fade = (f: number, a: number, b: number, c: number, d: number) =>
  clamp(Math.min((f - a) / Math.max(1, b - a), (d - f) / Math.max(1, d - c)));

export const textGlow = (color = C.ink) => ({ textShadow: glow(color, 6) });

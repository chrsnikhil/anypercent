import { TL } from "./theme";

export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
/** 0..1 progress of frame f through [a, b]. */
export const prog = (f: number, a: number, b: number) => clamp((f - a) / (b - a));
export const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
export const easeIn = (t: number) => t * t * t;
export const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
export const smooth = (t: number) => t * t * (3 - 2 * t);

/** Deterministic noise in [0, 1) from integers. */
export const rnd = (a: number, b = 0, c = 0) => {
  let h = (a * 374761393 + b * 668265263 + c * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
};

/** A typed line from the timeline: how many characters show at frame f. */
export const typeEntry = (id: string) => {
  const e = TL.type.find((t) => t.id === id);
  if (!e) throw new Error("no type entry " + id);
  return e;
};
export const typedCount = (f: number, start: number, cps: number, len: number) =>
  Math.max(0, Math.min(len, Math.floor(((f - start) * cps) / TL.fps)));
export const typed = (f: number, id: string) => {
  const e = typeEntry(id);
  return e.text.slice(0, typedCount(f, e.frame, e.cps, e.text.length));
};
export const typedDone = (f: number, id: string) => {
  const e = typeEntry(id);
  return f >= e.frame + Math.ceil((e.text.length * TL.fps) / e.cps);
};

export const pad = (n: number, w = 2) => String(Math.floor(n)).padStart(w, "0");
export const fmtNum = (n: number) => Math.round(n).toLocaleString("en-US");

/** Clock text for frame f, starting at h:m:s at frame f0. */
export const clock = (f: number, f0: number, h: number, m: number, s: number) => {
  const t = h * 3600 + m * 60 + s + Math.max(0, f - f0) / TL.fps;
  return `${pad((t / 3600) % 24)}:${pad((t / 60) % 60)}:${pad(t % 60)}`;
};

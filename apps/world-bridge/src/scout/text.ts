/**
 * The scout's words (spec: scout and pivot, "Fact check and text"). Every number the console shows
 * comes from the lap times: our template sentence is always computed, and the model's own reason
 * is used only when it passes the fact check below.
 */
import { fmtTime } from "../arkiv/publish.js";

/** The words the console never shows (launcher handler/__init__.py BANNED_WORDS), plus the scout's own. */
export const BANNED_WORDS = ["prove", "proof", "verified human", "earn", "win", "wins", "cash out", "prize", "staked", "bounty", "human ghost"] as const;
export const SCOUT_EXTRA_WORDS = ["human", "person", "people", "price", "usdc", "pay", "paid", "payout", "money", "winning"] as const;

/** Frames -> centiseconds, as fmtTime rounds (60 fps). */
export const cs = (frames: number) => Math.round((frames * 100) / 60);
/** Frames -> seconds with 2 decimals (a number: 6414 -> 106.9). */
export const secs = (frames: number) => cs(frames) / 100;
const two = (n: number) => n.toFixed(2);

/** YOU's lap minus the pick's, per lap, in seconds with 2 decimals (positive: the pick is faster there). */
export function loseSeconds(you: readonly number[], it: readonly number[]): number[] {
  return you.map((y, k) => (cs(y) - cs(it[k])) / 100);
}

/** The lap (1-based) where the pick gains most on YOU. */
export function bestGainLap(you: readonly number[], it: readonly number[]): number {
  const d = loseSeconds(you, it);
  let best = 0;
  for (let k = 1; k < d.length; k++) if (d[k] > d[best]) best = k;
  return best + 1;
}

/**
 * Our sentence: "You lose {d} s in lap {k}: {name} runs it in {it} s, you in {you} s." When the
 * asked lap is not one where the pick is faster, k becomes the pick's best-gain lap.
 */
export function templateText(name: string, you: readonly number[], it: readonly number[], lap: number | null): { lap: number; text: string } {
  const d = loseSeconds(you, it);
  let k = lap !== null && lap >= 1 && lap <= d.length ? lap : bestGainLap(you, it);
  if (d[k - 1] <= 0) k = bestGainLap(you, it);
  return { lap: k, text: `You lose ${two(d[k - 1])} s in lap ${k}: ${name} runs it in ${two(secs(it[k - 1]))} s, you in ${two(secs(you[k - 1]))} s.` };
}

/** The board rule's sentence, for a pick ahead of YOU overall. */
export function ruleText(name: string, itFrames: number, youFrames: number): string {
  return `${name} is the listed ghost just ahead of you: ${fmtTime(itFrames)} against your ${fmtTime(youFrames)}.`;
}

export interface FactContext {
  /** The pick's name (BOT-A2 or ANY-XXX). */
  name: string;
  laps: number;
  you: { frames: number; splits: readonly number[] };
  it: { frames: number; splits: readonly number[] };
  max: number;
}

const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;
const r1 = (v: number) => Math.round(v * 10) / 10;
const r2 = (v: number) => Math.round(v * 100) / 100;

/**
 * The model's reason, checked: printable ASCII, at most `max` characters; every ANY-.../BOT-... token
 * is the pick's name; every m:ss.cc time is YOU's or the pick's; every other number is a lap index
 * or one of YOU's or the pick's lap, total or "you lose" values (or its absolute value), to 2
 * decimals or rounded to 1; no banned word. Anything else: why not (the template is used instead).
 */
export function factCheck(reason: unknown, c: FactContext): { ok: true; text: string } | { ok: false; why: string } {
  if (typeof reason !== "string") return { ok: false, why: "no reason" };
  const text = reason.trim();
  if (text === "") return { ok: false, why: "empty" };
  if (!/^[\x20-\x7e]+$/.test(text)) return { ok: false, why: "not printable ASCII" };
  if (text.length > c.max) return { ok: false, why: `over ${c.max} characters` };
  for (const w of [...BANNED_WORDS, ...SCOUT_EXTRA_WORDS]) {
    if (new RegExp(`\\b${w.replace(/ /g, "\\s+")}\\b`, "i").test(text)) return { ok: false, why: `the word "${w}"` };
  }
  let rest = text;
  for (const m of text.match(/\b(?:ANY|BOT)-[A-Za-z0-9]+\b/gi) ?? []) {
    if (m !== c.name) return { ok: false, why: `names ${m}` };
  }
  rest = rest.replace(/\b(?:ANY|BOT)-[A-Za-z0-9]+\b/gi, " ");
  if (/\bc\d+\b/i.test(rest)) return { ok: false, why: "a candidate id" };
  const times = new Set([fmtTime(c.you.frames), fmtTime(c.it.frames)]);
  for (const m of rest.match(/\d+:\d{2}\.\d{2}/g) ?? []) if (!times.has(m)) return { ok: false, why: `the time ${m}` };
  rest = rest.replace(/\d+:\d{2}\.\d{2}/g, " ");
  const values: number[] = [secs(c.you.frames), secs(c.it.frames), ...c.you.splits.map(secs), ...c.it.splits.map(secs), ...loseSeconds(c.you.splits, c.it.splits)];
  const ok = (n: number) =>
    (Number.isInteger(n) && n >= 1 && n <= c.laps) || values.some((v) => near(n, r2(v)) || near(n, r2(Math.abs(v))) || near(n, r1(v)) || near(n, r1(Math.abs(v))));
  for (const m of rest.match(/\d+(?:\.\d+)?/g) ?? []) if (!ok(Number(m))) return { ok: false, why: `the number ${m}` };
  return { ok: true, text };
}

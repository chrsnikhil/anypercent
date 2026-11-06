/**
 * Which listed ghosts the scout may choose from (spec: scout and pivot, "Eligibility"). Plain code:
 * the model only ever sees what passed here, and PB's guards (hedera/agent.ts) still run in full on
 * the purchase. The scout only reads; it never reserves.
 *
 * A candidate is a listing on the board (boardListings) whose run counts (boardRuns: a checker stamp
 * names it and its console wrote both) with:
 * - the one listed price (ARKIV_GHOST_PRICE_C);
 * - a `pay_to` that can take USDC (the agent's 10-minute mirror cache);
 * - the run's log_h equal to the listing's, and the same time on both;
 * - not the buyer's own book;
 * - for a label listing: a BOT label, never HUMAN, paying the house account (else skipped and counted);
 * - faster than YOU overall, or (both with splits) faster than YOU in at least one split.
 */
import { sellerName, type ListingRow, type RunRow } from "../arkiv/client.js";
import { HOUSE_LABEL_RE } from "../config.js";
import { decCents } from "../hedera/resource.js";
import { loseSeconds, secs } from "./text.js";

export interface You {
  frames: number;
  splits: number[] | null;
}

export interface Candidate {
  /** BOT-A2 or ANY-XXX. */
  name: string;
  listing: ListingRow;
  run: RunRow;
  frames: number;
  /** The run's lap splits, when it has them and as many laps as YOU's. */
  splits: number[] | null;
}

export interface EligibleInput {
  buyer: string;
  game: string;
  you: You;
  runs: RunRow[];
  listings: ListingRow[];
  priceC: number;
  houseId: string;
  canReceive: (account: string) => Promise<boolean>;
}

export interface Eligible {
  candidates: Candidate[];
  /** Label listings refused (not the house's). */
  refusedLabels: number;
}

/** At most this many go to the model, the fastest first. */
export const MODEL_MAX = 12;

export async function eligible(i: EligibleInput): Promise<Eligible> {
  const runs = new Map(i.runs.map((r) => [r.key, r]));
  const out: Candidate[] = [];
  let refusedLabels = 0;
  const receivable = new Map<string, boolean>();
  for (const l of i.listings) {
    if (l.game !== i.game) continue;
    const run = runs.get(l.run);
    if (!run || run.game !== i.game || run.log_h !== l.log_h || run.frames !== l.frames) continue;
    if (decCents(l.price) !== i.priceC) continue;
    if (l.book !== undefined && l.book === i.buyer) continue;
    if (l.book === undefined) {
      const house = l.label !== undefined && HOUSE_LABEL_RE.test(l.label) && l.human === false && i.houseId !== "" && l.pay_to === i.houseId;
      if (!house) {
        refusedLabels += 1;
        continue;
      }
    }
    if (!l.pay_to) continue;
    if (!receivable.has(l.pay_to)) receivable.set(l.pay_to, await i.canReceive(l.pay_to).catch(() => false));
    if (!receivable.get(l.pay_to)) continue;
    const frames = Number(l.frames);
    const splits = run.splits && i.you.splits && run.splits.length === i.you.splits.length ? [...run.splits] : null;
    const aheadOverall = frames < i.you.frames;
    const aheadInALap = splits !== null && i.you.splits !== null && splits.some((s, k) => s < (i.you.splits as number[])[k]);
    if (!aheadOverall && !aheadInALap) continue;
    out.push({ name: sellerName(l), listing: l, run, frames, splits });
  }
  out.sort((a, b) => a.frames - b.frames || a.name.localeCompare(b.name));
  return { candidates: out, refusedLabels };
}

/**
 * The board's rule: the candidate with the largest time below YOU's (the ghost just ahead); when
 * none is ahead overall, the one that gains most in any one split.
 */
export function rulePick(cands: readonly Candidate[], you: You): Candidate | null {
  const ahead = cands.filter((c) => c.frames < you.frames).sort((a, b) => b.frames - a.frames);
  if (ahead.length) return ahead[0];
  let best: { c: Candidate; gain: number } | null = null;
  for (const c of cands) {
    if (!c.splits || !you.splits) continue;
    const gain = Math.max(...you.splits.map((y, k) => y - (c.splits as number[])[k]));
    if (!best || gain > best.gain) best = { c, gain };
  }
  return best?.c ?? null;
}

/** The candidates the model sees: with splits, the fastest first, at most MODEL_MAX. */
export function modelSet(cands: readonly Candidate[]): Candidate[] {
  return cands.filter((c) => c.splits !== null).slice(0, MODEL_MAX);
}

export interface ScoutFacts {
  game: string;
  laps: number;
  you: { total_s: number; laps_s: number[] };
  candidates: Array<{ id: string; name: string; total_s: number; laps_s: number[]; you_lose_s: number[] }>;
}

/** The facts the model gets: seconds with 2 decimals, ids c1..cN. No buyer's book, console or key. */
export function factsFor(title: string, you: { frames: number; splits: number[] }, set: readonly Candidate[]): ScoutFacts {
  return {
    game: title,
    laps: you.splits.length,
    you: { total_s: secs(you.frames), laps_s: you.splits.map(secs) },
    candidates: set.map((c, k) => ({
      id: `c${k + 1}`,
      name: c.name,
      total_s: secs(c.frames),
      laps_s: (c.splits as number[]).map(secs),
      you_lose_s: loseSeconds(you.splits, c.splits as number[]),
    })),
  };
}


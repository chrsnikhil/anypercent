/**
 * PB's scout (spec: scout and pivot, section 4): which listed ghost PB buys for this player. Never
 * whether to pay, how much or to whom: PB's guards (hedera/agent.ts) run in full on the purchase.
 *
 *   POST /scout {book, game, log (base64), console?, price_c} -> {id: "s-1a2b3c4d", expires_s: 60}
 *   GET  /scout/{id} -> {stage: "replay" | "read" | "think" | "done", ok, failure, data}
 *
 *   replay  YOU's log through the checker and arcade_splits (no lap times: the rule runs, and says so)
 *   read    the board on Arkiv: the checker's stamps joined to each console's runs and listings
 *           (boardRuns, boardListings); the candidates (eligible.ts)
 *   think   Groq chooses one candidate by id (groq.ts), unless there is nothing for it to compare
 *   done    the pick, the laps, the reason and who chose: the model, or the board's rule
 *
 * Failures: buy_budget (the book's day cap, the agent's USDC), nobody_ahead (no eligible ghost),
 * buy_suspended {why: console_not_linked}, buy_down (Arkiv or the mirror did not answer). A model
 * that fails, times out or answers something that does not check out falls back to the rule, with
 * a note the console shows. Picks are held 1 h, so INTENT can carry the scout's model and reason.
 *
 * Logged: the scout id, book, game, the pick, by whom and how long. Never the key, the prompt or a
 * console id.
 */
import { randomBytes } from "node:crypto";
import { BOOK_RE } from "../approvals.js";
import type { ArkivPort } from "../arkiv/client.js";
import { CheckerError, LOG_MAX, LOG_MIN, parseHeader, splitsVerdict, verdict, type CheckerPort, type SplitsPort } from "../arkiv/checker.js";
import { sha256Hex } from "../arkiv/ghost.js";
import { fmtTime } from "../arkiv/publish.js";
import { GAMES } from "../arkiv/schema.js";
import { CONSOLE_ID_RE } from "../consoles.js";
import { centsToAtomic } from "../hedera/x402.js";
import { localDay, type HeldScout } from "../hedera/agent.js";
import type { Store } from "../store.js";
import { eligible, factsFor, modelSet, rulePick, type Candidate, type You } from "./eligible.js";
import type { GroqPort, GroqWhy } from "./groq.js";
import { factCheck, ruleText, templateText } from "./text.js";

export type ScoutFailure = "buy_budget" | "nobody_ahead" | "buy_suspended" | "buy_down";

export interface ScoutView {
  stage: "replay" | "read" | "think" | "done";
  ok: boolean | null;
  failure: ScoutFailure | null;
  data: Record<string, unknown>;
}

export class ScoutRefused extends Error {
  constructor(public readonly status: number, public readonly error: string) {
    super(error);
  }
}

export interface ScoutOptions {
  store: Store;
  arkiv: Pick<ArkivPort, "boardRuns" | "boardListings">;
  checker: CheckerPort;
  splits: SplitsPort | null;
  /** PB's mirror reads, cached as its guards cache them. */
  agent: { canReceive(account: string): Promise<boolean>; agentUsdc(): Promise<bigint | null> };
  /** The model; null: no usable GROQ_API_KEY (the rule runs). */
  groq: GroqPort | null;
  consoles: { canSpend(id: string, book: string): { ok: boolean; tag: string | null } } | null;
  season: number;
  priceC: number;
  houseId: string;
  bookDayC: number;
  /** SCOUT_REASON_MAX (110). */
  reasonMax: number;
  /** Arkiv and Hedera payments are on (the live view); off: POST /scout answers 503. */
  on: () => boolean;
  now?: () => number;
  holdMs?: number;
  log?: (line: string) => void;
}

export const SCOUT_EXPIRES_S = 60;
export const MAX_SCOUT_BODY = 96 * 1024;

interface Body {
  book: string;
  game: string;
  log: Uint8Array;
  logH: string;
  headerFrames: number;
  console?: string;
  price_c: number;
}

interface Job {
  id: string;
  body: Body;
  view: ScoutView;
  createdMs: number;
  held: HeldScout | null;
}

const B64 = /^[A-Za-z0-9+/]*={0,2}$/;

function parseBody(raw: Record<string, unknown>): Body {
  const bad = () => new ScoutRefused(400, "bad_body");
  const { book, game, log, console: consoleId, price_c } = raw;
  if (typeof book !== "string" || !BOOK_RE.test(book)) throw bad();
  if (typeof game !== "string" || !GAMES[game]) throw bad();
  if (consoleId !== undefined && consoleId !== null && (typeof consoleId !== "string" || !CONSOLE_ID_RE.test(consoleId))) throw bad();
  if (typeof price_c !== "number" || !Number.isInteger(price_c) || price_c < 0 || price_c > 1_000_000) throw bad();
  if (typeof log !== "string" || !B64.test(log) || log.length % 4 !== 0) throw bad();
  const bytes = Uint8Array.from(Buffer.from(log, "base64"));
  if (bytes.length < LOG_MIN || bytes.length > LOG_MAX) throw bad();
  const header = parseHeader(bytes);
  if (!header || header.game !== game) throw bad();
  return {
    book,
    game,
    log: bytes,
    logH: sha256Hex(bytes),
    headerFrames: header.frames,
    ...(typeof consoleId === "string" ? { console: consoleId } : {}),
    price_c,
  };
}

/** What the console shows when the rule ran instead of the model. */
const NOTE: Record<GroqWhy | "no_key" | "no_you" | "no_them", string> = {
  timeout: "the model did not answer in 6 s",
  rate_limit: "Groq rate limit",
  refused: "Groq refused the key",
  bad_answer: "the model's answer did not check out",
  unreachable: "Groq could not be reached",
  no_key: "no Groq key",
  no_you: "no lap times for your run",
  no_them: "no lap times on the listed ghosts",
};

export class ScoutService {
  private readonly jobs = new Map<string, Job>();
  private readonly now: () => number;
  private readonly holdMs: number;
  /** Groq refused the key: the rule until restart. */
  private keyRefused = false;

  constructor(private readonly opts: ScoutOptions) {
    this.now = opts.now ?? Date.now;
    this.holdMs = opts.holdMs ?? 3_600_000;
  }

  /** /health's "scout": off (Arkiv or Hedera pay off), model, or rule (no key, or the key refused). */
  mode(): "model" | "rule" | "off" {
    if (!this.opts.on()) return "off";
    return this.opts.groq && !this.keyRefused ? "model" : "rule";
  }

  start(raw: Record<string, unknown>): { id: string; expires_s: number } {
    const body = parseBody(raw);
    if (this.mode() === "off") throw new ScoutRefused(503, "scout_off");
    this.prune();
    const job: Job = { id: this.newId(), body, view: { stage: "replay", ok: null, failure: null, data: {} }, createdMs: this.now(), held: null };
    this.jobs.set(job.id, job);
    this.run(job).catch((err: unknown) => this.fail(job, "buy_down", `internal: ${(err as Error)?.name ?? "error"}`));
    return { id: job.id, expires_s: SCOUT_EXPIRES_S };
  }

  view(id: string): ScoutView | undefined {
    return this.jobs.get(id)?.view;
  }

  /** A finished pick, for INTENT (the agent matches buyer, game and listing itself). */
  held(id: string): HeldScout | undefined {
    const j = this.jobs.get(id);
    return j && this.now() - j.createdMs <= this.holdMs ? (j.held ?? undefined) : undefined;
  }

  private newId(): string {
    for (;;) {
      const id = `s-${randomBytes(4).toString("hex")}`;
      if (!this.jobs.has(id)) return id;
    }
  }

  private fail(job: Job, failure: ScoutFailure, why: string, data: Record<string, unknown> = {}): void {
    if (job.view.stage === "done") return;
    job.view = { stage: "done", ok: false, failure, data };
    this.opts.log?.(`scout ${job.id} ${job.body.book} ${job.body.game}: ${failure} (${why})`);
  }

  private async run(job: Job): Promise<void> {
    const b = job.body;
    const o = this.opts;

    // Spending follows the binding, and the caps come first: nothing is read for a refused buyer.
    if (b.console !== undefined) {
      const c = o.consoles?.canSpend(b.console, b.book) ?? { ok: false, tag: null };
      if (!c.ok) return this.fail(job, "buy_suspended", `console ${c.tag ?? "?"} is not linked to ${b.book}`, { why: "console_not_linked" });
    }
    if (!o.store.recordForBook(b.book)) return this.fail(job, "buy_budget", "the buyer book was not issued here");
    if (o.store.spentOn(localDay(this.now()), b.book) + o.priceC > o.bookDayC) return this.fail(job, "buy_budget", "the book's daily cap");
    let usdc: bigint | null;
    try {
      usdc = await o.agent.agentUsdc();
    } catch {
      return this.fail(job, "buy_down", "the mirror node did not answer");
    }
    if (usdc === null || usdc < BigInt(centsToAtomic(o.priceC))) return this.fail(job, "buy_budget", "the agent is out of USDC");

    // replay: YOU's time and laps, by the checker's own tools.
    const you: You = { frames: b.headerFrames, splits: null };
    let youNote: string | null = null;
    try {
      const r = await o.checker.replay(b.game, b.logH, b.log);
      const v = verdict(b.game, r);
      if (!v.ok) youNote = NOTE.no_you;
      else {
        you.frames = v.frames;
        if (o.splits && o.splits.games.includes(b.game)) {
          const s = splitsVerdict(await o.splits.splits(b.game, b.logH, b.log), v.frames, r.final_hash);
          if (s.ok) you.splits = s.splits;
        }
        if (!you.splits) youNote = NOTE.no_you;
      }
    } catch (err) {
      if (!(err instanceof CheckerError)) throw err;
      youNote = NOTE.no_you;
    }

    // read: the board and its listings, straight from Arkiv.
    job.view = { stage: "read", ok: null, failure: null, data: {} };
    let cands: Candidate[];
    let refusedLabels: number;
    try {
      const [runs, listings] = await Promise.all([o.arkiv.boardRuns(b.game, o.season), o.arkiv.boardListings(b.game, o.season)]);
      ({ candidates: cands, refusedLabels } = await eligible({
        buyer: b.book,
        game: b.game,
        you,
        runs,
        listings,
        priceC: o.priceC,
        houseId: o.houseId,
        canReceive: (a) => o.agent.canReceive(a),
      }));
    } catch {
      return this.fail(job, "buy_down", "Arkiv did not answer");
    }
    if (cands.length === 0) return this.fail(job, "nobody_ahead", "no eligible listed ghost");
    const forModel = you.splits ? modelSet(cands) : [];
    const skipped = refusedLabels + cands.filter((c) => c.splits === null).length;

    // think: the model chooses among the candidates with laps; anything else is the rule.
    let pick: Candidate | null = null;
    let by: "model" | "rule" = "rule";
    let lap: number | null = null;
    let reason = "";
    let text: "model" | "template" = "template";
    let note: string | null = youNote;
    let logWhy: string | null = null;
    let ms = 0;
    if (!note && forModel.length === 0) note = NOTE.no_them;
    if (!note && (!o.groq || this.keyRefused)) note = NOTE.no_key;
    if (!note && o.groq && you.splits) {
      job.view = { stage: "think", ok: null, failure: null, data: {} };
      const facts = factsFor(GAMES[b.game], { frames: you.frames, splits: you.splits }, forModel);
      const a = await o.groq.choose(facts);
      ms = a.ms;
      if (a.ok) {
        pick = forModel[Number(a.pick.slice(1)) - 1] ?? null;
        if (pick && pick.splits) {
          by = "model";
          const t = templateText(pick.name, you.splits, pick.splits, a.lap);
          const fc = factCheck(a.reason, { name: pick.name, laps: you.splits.length, you: { frames: you.frames, splits: you.splits }, it: { frames: pick.frames, splits: pick.splits }, max: o.reasonMax });
          if (fc.ok) {
            reason = fc.text;
            text = "model";
            lap = a.lap;
          } else {
            reason = t.text;
            lap = t.lap;
            this.opts.log?.(`scout ${job.id}: the model's sentence did not check out (${fc.why}); our template instead`);
          }
        } else {
          pick = null;
          note = NOTE.bad_answer;
        }
      } else {
        if (a.why === "refused") this.keyRefused = true;
        note = a.why === "timeout" ? `the model did not answer in ${Math.round(o.groq.timeoutMs / 1000)} s` : NOTE[a.why];
        logWhy = a.why === "timeout" ? `model timed out after ${a.ms} ms` : `${note}, ${a.ms} ms`;
      }
    }
    if (!pick) {
      pick = rulePick(cands, you);
      if (!pick) return this.fail(job, "nobody_ahead", "no eligible listed ghost");
      by = "rule";
      text = "template";
      if (pick.frames < you.frames) {
        reason = ruleText(pick.name, pick.frames, you.frames);
        lap = pick.splits && you.splits ? templateText(pick.name, you.splits, pick.splits, null).lap : null;
      } else {
        // Ahead in a lap only: "just ahead" would not be true, so the lap sentence.
        const t = templateText(pick.name, you.splits as number[], pick.splits as number[], null);
        reason = t.text;
        lap = t.lap;
      }
    }

    const model = by === "model" ? o.groq?.model ?? null : null;
    job.held = {
      buyer: b.book,
      game: b.game,
      listing: pick.listing.key,
      intent: { by, model, lap, you: you.splits ?? [], it: pick.splits ?? [], text, why: reason },
    };
    job.view = {
      stage: "done",
      ok: true,
      failure: null,
      data: {
        scout: job.id,
        seller: pick.name,
        pick: {
          name: pick.name,
          label: pick.listing.label ?? null,
          book: pick.listing.book ?? null,
          listing: pick.listing.key,
          run: pick.run.key,
          log_h: pick.listing.log_h,
          frames: pick.frames,
          time: fmtTime(pick.frames),
          splits: pick.splits,
          price_c: o.priceC,
          pay_to: pick.listing.pay_to ?? null,
          human: pick.listing.human,
        },
        you: { frames: you.frames, time: fmtTime(you.frames), splits: you.splits },
        lap,
        reason,
        by,
        text,
        model,
        note: by === "model" ? null : note,
        candidates: cands.length,
        skipped,
      },
    };
    const tail = by === "model" ? `model picked ${pick.name} (lap ${lap}), ${ms} ms` : `rule: ${pick.name} (${logWhy ?? note ?? "the ghost just ahead"})`;
    this.opts.log?.(`scout ${job.id} ${b.book} ${b.game}: ${tail}`);
  }

  private prune(): void {
    const nowMs = this.now();
    for (const [id, j] of this.jobs) if (j.view.stage === "done" && nowMs - j.createdMs > this.holdMs) this.jobs.delete(id);
  }
}

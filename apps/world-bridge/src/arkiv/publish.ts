/**
 * POST /arkiv/publish: one World listing approval allows exactly one write, a run row plus a
 * listing row in one batch (spec: Write path). Jobs are keyed by id and by the approval's jti:
 *
 *   check   the approval, the book, the log header, the replay, the approved text, the dedupe (Q7)
 *   write   the approval is bound to this log and the transaction is out
 *   done    {run, listing, tx}, or one of the handler's own failure names
 *
 * Failures (service side; the launcher adds "service unreachable" itself):
 *   ls_expired       approval unknown to this bridge, or older than 24 h and unspent
 *   ls_wrong         approved for another book; book not issued here; this log is listed under
 *                    another book
 *   ls_mismatch      approved text differs (its hash, the title, the time, the price), or the log's
 *                    header names another game, or the replayed time is not the one asked
 *   ls_reused        the approval already put another log on Arkiv
 *   ls_publish_fail  the replay refused or failed; Arkiv down, a revert, out of gas, a timeout
 *
 * A failed write keeps the approval bound to its log, so the console's retry with the same jti goes
 * through; a retry after success answers the same keys. Logged: book, game, time, keys, tx and the
 * failure's reason. Never the jti, the log, a key or a secret.
 *
 * Hedera (optional): the body may carry `pay_to`, the seller's Hedera account. It must equal the
 * book's registered account (`npm run hedera:payto`; both absent is fine) and the approved text then
 * reads "... USDC to <pay_to> on the public board". The listing row carries `pay_to` and, when the
 * record step put a LISTING on HCS for this approval, `hcs` = "<topic>/<seq>". Publish never needs
 * a LISTING. A relist whose `pay_to` differs from the run's live listing writes a new listing and
 * deletes the old one in the same batch, so a run listed before payouts existed can be put up for sale.
 */
import { createHash, randomBytes } from "node:crypto";
import { BOOK_RE } from "../approvals.js";
import { ACCOUNT_RE } from "../config.js";
import type { Store } from "../store.js";
import { ArkivError, type ArkivPort, type CreateSpec, type ListingValues, type RunValues } from "./client.js";
import { CheckerError, LOG_MAX, LOG_MIN, parseHeader, verdict, type CheckerPort } from "./checker.js";
import { encryptGhost, sha256Hex } from "./ghost.js";
import { GAME_IDS, LISTING_DAYS, LISTING_FLAGS, RUN_FLAGS } from "./schema.js";

export type PublishFailure = "ls_expired" | "ls_wrong" | "ls_mismatch" | "ls_reused" | "ls_publish_fail";

export interface PublishView {
  stage: "check" | "write" | "done";
  ok: boolean | null;
  failure: PublishFailure | null;
  data: Record<string, unknown>;
}

/** A request the service refuses before any job starts: 400 bad_body, 503 not configured or unavailable. */
export class PublishRefused extends Error {
  constructor(public readonly status: number, public readonly error: string) {
    super(error);
  }
}

export type WriteGate = () => null | "arkiv_not_configured" | "arkiv_unavailable";

export interface PublisherOptions {
  arkiv: ArkivPort;
  checker: CheckerPort;
  store: Store;
  season: number;
  /** When run rows expire: season end + 30 d. */
  runExpiry: Date;
  /** ARKIV_GHOST_PRICE_C. */
  priceC: number;
  /** ARKIV_GHOST_SECRET (64 hex). */
  ghostSecret: string;
  /** Whether a new job may start (config complete, right chain, funded checker). Default: yes. */
  gate?: WriteGate;
  now?: () => number;
  log?: (line: string) => void;
  /** How long a job is held for repeat POSTs and GETs (1 h). */
  holdMs?: number;
  /** An unspent approval older than this is ls_expired (24 h). */
  approvalTtlMs?: number;
  /** A write still out after this long fails the job (ls_publish_fail); the queue waits it out. */
  writeTimeoutMs?: number;
}

/** How long the console should keep asking about a job. */
export const PUBLISH_EXPIRES_S = 120;
export const MAX_PUBLISH_BODY = 192 * 1024;

interface Body {
  book: string;
  jti: string;
  action: string;
  game: string;
  title: string;
  frames: number;
  price_c: number;
  /** The seller's Hedera account, when the book has one. */
  pay_to?: string;
  log: Uint8Array;
  logH: string;
  rules: number;
  headerGame: string;
}

interface Job {
  id: string;
  key: string;
  body: Body;
  view: PublishView;
  createdMs: number;
  running: boolean;
}

/** coach.fmt_time: m:ss.cc at 60 fps (cs = round(frames * 100 / 60); never a .5 tie at 60 fps). */
export function fmtTime(frames: number): string {
  const cs = Math.round((frames * 100) / 60);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${Math.floor(cs / 6000)}:${two(Math.floor(cs / 100) % 60)}.${two(cs % 100)}`;
}

/** "%.2f" of cents, as the launcher prints a price: 10 -> "0.10". */
export function priceText(cents: number): string {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}

/** The price as a dec value: 10 -> "0.1" (the canonical form Arkiv stores). */
export function priceDec(cents: number): string {
  const whole = Math.floor(cents / 100);
  const frac = String(cents % 100).padStart(2, "0").replace(/0+$/, "");
  return frac === "" ? String(whole) : `${whole}.${frac}`;
}

/** What World App showed for the listing: the only text an approval allows. */
export function actionText(title: string, frames: number, priceC: number, payTo?: string | null): string {
  const to = payTo ? ` to ${payTo}` : "";
  return `List ${title} ${fmtTime(frames)} ghost for ${priceText(priceC)} USDC${to} on the public board`;
}

const CONTROL = /[\u0000-\u001f\u007f]/;
const B64 = /^[A-Za-z0-9+/]*={0,2}$/;

function bad(): PublishRefused {
  return new PublishRefused(400, "bad_body");
}

/** The body's shape (step 1). Anything off: 400 bad_body. */
export function parseBody(raw: Record<string, unknown>): Body {
  const { book, jti, action, game, title, frames, price_c, log, pay_to } = raw;
  if (typeof book !== "string" || !BOOK_RE.test(book)) throw bad();
  if (typeof jti !== "string" || !/^[\x21-\x7e]{1,256}$/.test(jti)) throw bad();
  if (typeof action !== "string" || action === "" || action.length > 160 || CONTROL.test(action)) throw bad();
  if (typeof game !== "string" || !GAME_IDS.includes(game)) throw bad();
  if (typeof title !== "string" || title.trim() === "" || Buffer.byteLength(title) > 64 || CONTROL.test(title)) throw bad();
  if (typeof frames !== "number" || !Number.isInteger(frames) || frames < 1 || frames > 0xffffffff) throw bad();
  if (typeof price_c !== "number" || !Number.isInteger(price_c) || price_c < 0 || price_c > 1_000_000) throw bad();
  if (pay_to !== undefined && pay_to !== null && (typeof pay_to !== "string" || !ACCOUNT_RE.test(pay_to))) throw bad();
  if (typeof log !== "string" || !B64.test(log) || log.length % 4 !== 0) throw bad();
  const bytes = Uint8Array.from(Buffer.from(log, "base64"));
  if (bytes.length < LOG_MIN || bytes.length > LOG_MAX) throw bad();
  const header = parseHeader(bytes);
  if (!header) throw bad();
  return {
    book,
    jti,
    action,
    game,
    title,
    frames,
    price_c,
    ...(typeof pay_to === "string" ? { pay_to } : {}),
    log: bytes,
    logH: sha256Hex(bytes),
    rules: header.rules,
    headerGame: header.game,
  };
}

export class Publisher {
  private readonly jobs = new Map<string, Job>();
  private readonly byKey = new Map<string, string>();
  private readonly now: () => number;
  private readonly holdMs: number;
  private readonly approvalTtlMs: number;
  private readonly writeTimeoutMs: number;
  private section: Promise<unknown> = Promise.resolve();

  constructor(private readonly opts: PublisherOptions) {
    this.now = opts.now ?? Date.now;
    this.holdMs = opts.holdMs ?? 3_600_000;
    this.approvalTtlMs = opts.approvalTtlMs ?? 24 * 3_600_000;
    this.writeTimeoutMs = opts.writeTimeoutMs ?? 60_000;
  }

  /** Start (or find) the job for this approval. Throws PublishRefused (400 or 503). */
  start(raw: Record<string, unknown>): { id: string; expires_s: number } {
    const body = parseBody(raw);
    const nowMs = this.now();
    this.prune(nowMs);
    const key = createHash("sha256").update(body.jti).digest("hex");
    const held = this.jobs.get(this.byKey.get(key) ?? "");
    if (held && !(held.view.stage === "done" && held.view.ok === false)) {
      return { id: held.id, expires_s: PUBLISH_EXPIRES_S };
    }
    const gate = this.opts.gate?.() ?? null;
    if (gate) throw new PublishRefused(503, gate);
    // A held job that failed runs again, under the same id, with this body (the console's retry).
    const job: Job = held ?? { id: randomBytes(16).toString("base64url"), key, body, view: this.checking(), createdMs: nowMs, running: false };
    job.body = body;
    job.view = this.checking();
    job.createdMs = nowMs;
    this.jobs.set(job.id, job);
    this.byKey.set(key, job.id);
    this.launch(job);
    return { id: job.id, expires_s: PUBLISH_EXPIRES_S };
  }

  view(id: string): PublishView | undefined {
    return this.jobs.get(id)?.view;
  }

  private checking(): PublishView {
    return { stage: "check", ok: null, failure: null, data: {} };
  }

  private launch(job: Job): void {
    job.running = true;
    this.run(job)
      .catch((err: unknown) => this.fail(job, "ls_publish_fail", `internal: ${(err as Error)?.name ?? "error"}`))
      .finally(() => {
        job.running = false;
      });
  }

  private what(b: Body, frames = b.frames): string {
    return `${b.book} ${b.game} ${fmtTime(frames)}`;
  }

  private fail(job: Job, failure: PublishFailure, why: string): void {
    if (job.view.stage === "done") return;
    job.view = { stage: "done", ok: false, failure, data: {} };
    this.opts.log?.(`arkiv publish ${this.what(job.body)}: ${failure} (${why})`);
  }

  private done(job: Job, result: { run: string; listing: string; tx: string | null }, note = ""): void {
    job.view = { stage: "done", ok: true, failure: null, data: { run: result.run, listing: result.listing, tx: result.tx } };
    this.opts.log?.(
      `arkiv publish ${this.what(job.body)}: run ${result.run} listing ${result.listing}${result.tx ? ` tx ${result.tx}` : ""}${note}`,
    );
  }

  /** The dedupe-spend-write section runs one job at a time, so two approvals of one log can't both write it. */
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.section.then(fn, fn);
    this.section = run.catch(() => undefined);
    return run;
  }

  private async run(job: Job): Promise<void> {
    const b = job.body;
    const { store, arkiv, checker } = this.opts;

    // 2. The approval: granted here, for this book and this text, and not spent on another log.
    const rec = store.approvalFor(b.jti);
    if (!rec) return this.fail(job, "ls_expired", "approval unknown to this bridge");
    if (rec.log_h === undefined && this.now() - rec.at * 1000 > this.approvalTtlMs) {
      return this.fail(job, "ls_expired", "approval older than 24 h");
    }
    if (rec.book !== b.book) return this.fail(job, "ls_wrong", "approved for another book");
    if (createHash("sha256").update(b.action).digest("hex") !== rec.action_sha) {
      return this.fail(job, "ls_mismatch", "not the text World App showed");
    }
    if (rec.log_h !== undefined && rec.log_h !== b.logH) return this.fail(job, "ls_reused", "approval already used for another run");
    if (rec.log_h === b.logH && rec.result) return this.done(job, rec.result, " (already written)");

    // 3. The book: issued by this bridge after a World ID proof.
    const book = store.recordForBook(b.book);
    if (!book) return this.fail(job, "ls_wrong", "book not issued by this bridge");

    // 4. The log: its header names the game it claims.
    if (b.headerGame !== b.game) return this.fail(job, "ls_mismatch", "the log is another game's");

    // 5. The replay: the checker's own time, or nothing.
    let frames: number;
    try {
      const v = verdict(b.game, await checker.replay(b.game, b.logH, b.log));
      if (!v.ok) return this.fail(job, "ls_publish_fail", `replay refused: ${v.why}`);
      frames = v.frames;
    } catch (err) {
      const why = err instanceof CheckerError ? err.message : "error";
      return this.fail(job, "ls_publish_fail", `replay tool: ${why}`);
    }
    if (frames !== b.frames) return this.fail(job, "ls_mismatch", `replayed ${fmtTime(frames)}, asked ${fmtTime(b.frames)}`);

    // 6. The approved text must be this run's: title, replayed time and price.
    if (b.price_c !== this.opts.priceC) return this.fail(job, "ls_mismatch", "price differs from ARKIV_GHOST_PRICE_C");
    if ((b.pay_to ?? null) !== (store.paytoFor(b.book) ?? null)) return this.fail(job, "ls_mismatch", "pay_to is not the book's registered account");
    if (b.action !== actionText(b.title, frames, this.opts.priceC, b.pay_to)) {
      return this.fail(job, "ls_mismatch", "approved text does not match the replayed run");
    }
    let tool: string;
    try {
      tool = await checker.toolTag(b.game);
    } catch {
      return this.fail(job, "ls_publish_fail", "could not hash the replay tool");
    }

    const run: CreateSpec<RunValues> = {
      values: {
        game: b.game,
        title: b.title,
        season: this.opts.season,
        rules: b.rules,
        frames,
        log_h: b.logH,
        runner: book.runner_id,
        book: b.book,
        human: true,
        credential: book.credential,
        tool,
        log_enc: encryptGhost(this.opts.ghostSecret, b.logH, b.log),
      },
      flags: { ...RUN_FLAGS },
      expiry: { kind: "atDate", date: this.opts.runExpiry, atLeastDays: 1 },
    };
    const listing: CreateSpec<ListingValues> = {
      values: {
        game: b.game,
        season: this.opts.season,
        frames,
        log_h: b.logH,
        price: priceDec(this.opts.priceC),
        seller: book.runner_id,
        book: b.book,
        human: true,
        ...(b.pay_to ? { pay_to: b.pay_to } : {}),
        ...hcsRef(store, b.jti),
      },
      flags: { ...LISTING_FLAGS },
      expiry: { kind: "days", days: LISTING_DAYS },
    };

    await this.serial(async () => {
      // 7. Dedupe (Q7): a log is on the board once, under one book.
      let existing;
      let live = null;
      try {
        existing = await arkiv.runByLogHash(b.logH);
        if (existing && existing.book === b.book) live = await arkiv.liveListingFor(existing.key);
      } catch (err) {
        return this.fail(job, "ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
      }
      if (existing && existing.book !== b.book) return this.fail(job, "ls_wrong", "this log is already on the board under another book");

      // 8. Spend: bind the approval to this log before anything goes out.
      const spent = store.spendApproval(b.jti, b.logH);
      if (spent === "unknown") return this.fail(job, "ls_expired", "approval unknown to this bridge");
      if (spent === "other") return this.fail(job, "ls_reused", "approval already used for another run");
      job.view = { stage: "write", ok: null, failure: null, data: {} };

      if (existing && live && (live.pay_to ?? null) === (b.pay_to ?? null)) {
        const result = { run: existing.key, listing: live.key, tx: store.resultForLog(b.logH)?.tx ?? null };
        store.setApprovalResult(b.jti, result);
        return this.done(job, result, " (already on the board)");
      }

      // 9. Write: one batch (or the listing alone for a run already on the board; a live listing
      //    with another pay_to is replaced in the same batch).
      const replaces = existing && live ? live.key : undefined;
      const write: Promise<{ run: string; listing: string; tx: string }> = existing
        ? arkiv.writeListing(existing.key, listing, replaces).then((w) => ({ run: existing.key, listing: w.listing, tx: w.tx }))
        : arkiv.writeRunAndListing(run, listing);
      let timer: NodeJS.Timeout | undefined;
      const timedOut = new Promise<"timeout">((ok) => {
        timer = setTimeout(() => ok("timeout"), this.writeTimeoutMs);
      });
      const outcome = await Promise.race([write.then((w) => ({ w }), (err: unknown) => ({ err })), timedOut]);
      clearTimeout(timer);
      if (outcome === "timeout") {
        this.fail(job, "ls_publish_fail", "Arkiv write timed out");
        // Hold the section until the transaction settles, so a retry's dedupe sees it.
        const late = await write.then((w) => w, () => null);
        if (late) {
          store.setApprovalResult(b.jti, late);
          this.opts.log?.(`arkiv publish ${this.what(b, frames)}: landed after the timeout: run ${late.run} listing ${late.listing}`);
        }
        return;
      }
      if ("err" in outcome) {
        const why = outcome.err instanceof ArkivError ? outcome.err.message : "write failed";
        return this.fail(job, "ls_publish_fail", `Arkiv write: ${why}`);
      }
      store.setApprovalResult(b.jti, outcome.w);
      // 10. Done.
      return this.done(job, outcome.w);
    });
  }

  /** Forget jobs an hour after they were made (or last retried), unless still running. */
  private prune(nowMs: number): void {
    for (const [id, j] of this.jobs) {
      if (!j.running && nowMs - j.createdMs > this.holdMs) {
        this.jobs.delete(id);
        if (this.byKey.get(j.key) === id) this.byKey.delete(j.key);
      }
    }
  }
}

/** The listing's `hcs` column: "<topic>/<seq>" of the LISTING message for this approval, if it landed. */
function hcsRef(store: Store, jti: string): { hcs?: string } {
  const rec = store.hcsListingFor(jti);
  return rec?.seq ? { hcs: `${rec.topic}/${rec.seq}` } : {};
}

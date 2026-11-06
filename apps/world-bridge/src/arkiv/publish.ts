/**
 * POST /arkiv/publish: one World listing approval allows exactly one listed run. The console owns
 * the record of it (spec: the console owns its records, the server stamps them real): the bridge
 * runs every check, then issues the run and listing for the console's own wallet to sign; once the
 * console reports its transaction, the bridge reads both entities back from Arkiv and, when they
 * are exactly what it issued and their creator is the World-approved wallet of a console bound to
 * the book, the checker writes one anypercent.stamp naming the run. The bridge writes no run or
 * listing for a player and holds no console key. Jobs are keyed by id and by the approval's jti:
 *
 *   check   the approval, the book, the log header, the replay, the approved text, the dedupe (Q7
 *           on stamps), a World-approved wallet for the book
 *   sign    data.issue = {chain_id, rpc, run, run_key, listing, replaces}: `run` and `listing` are
 *           SpecJSON (spec-json.ts) the console writes as they are, in one transaction, its listing
 *           naming the run's key; for a relist of a stamped run, `run` is null, `run_key` names
 *           the run and `replaces` the console's own live listing the same transaction deletes
 *           (one with another pay_to), else null. The console then calls
 *           POST /arkiv/publish/{id}/written {tx, run, listing} (`written`): {ok: true}
 *   write   the console's entities are read back and the stamp transaction is out
 *   done    {run, listing, tx, stamp, stamp_tx, explorer?, replay?}: tx is the console's (null
 *           when the bridge found its entities without being told), stamp and stamp_tx the
 *           checker's; replay is {frames, final_hash} of this job's own replay (final_hash as the
 *           tool printed it, null when it printed none), absent when the approval's record answered
 *           without a replay. Or one of the handler's own failure names.
 *
 * Failures (service side; the launcher adds "service unreachable" itself):
 *   ls_expired       approval unknown to this bridge, or older than 24 h and unspent
 *   ls_wrong         approved for another book, or the book was not issued here (this bridge's own
 *                    checks of the approval against the book, not a refusal by World)
 *   ls_mismatch      approved text differs (its hash, the title, the time, the price), or the log's
 *                    header names another game, or the replayed time is not the one asked
 *   ls_reused        the approval already put another log on Arkiv
 *   ls_copied        this exact log is already stamped under another book: a copied run (the
 *                    dedupe below; /hedera/record runs the same check before its LISTING)
 *   ls_not_linked    no console bound to the book has a World-approved wallet (before anything is
 *                    issued, the approval unspent), or the run was created by a wallet that is not
 *                    one: a reflashed console needs a new link (Review Focus 2)
 *   ls_publish_fail  the replay refused or failed; Arkiv down; the console's entities missing or not
 *                    what was issued; the stamp write reverted, ran out of gas or timed out
 *
 * Retries. A failed job runs again under the same id on the console's next POST with the same jti,
 * and so does one waiting at sign: before issuing again it looks for a run and listing a linked
 * wallet already wrote for this log (the console's transaction landed but it was never told: Review
 * Focus 5) and stamps those. A `written` again after a failed stamp (or after a new link) checks
 * and stamps again: the records already exist. A repeated `written` answers {ok: true} and stamps
 * nothing new. A done job's result is kept on the approval, so a retry after success answers the
 * same keys and stamp. One stamp per log: a stamp the approval already records for this run, or one
 * that landed meanwhile for this log, answers instead; a stamp write that errs is looked up (it may
 * have landed before its receipt was lost) before the job fails, so a retry never writes a second.
 *
 * The console's entities, checked (spec: The flow, step 4): each is live, carries its schema's tag,
 * is owned by its creator (an owner or flags the node does not report count as a mismatch) and has
 * the issued flags, no payload and no content type; every attribute is exactly the issued one
 * (types and values as the SDK reads them back) with nothing added, except `log_enc`, which must
 * decrypt under the ghost key to this job's log (a retry issues a fresh nonce); the listing's `run`
 * names the run, and both come from the same wallet. A relist that replaces a listing is done only
 * once that listing is gone. The stamp copies the run's columns, names that wallet as `console` and
 * expires with the run, never after the run's issued expiry (the earlier of the run's own expiry
 * block and the issued date's block).
 *
 * Logged: book, game, time, keys, tx and the failure's reason. Never the jti, the log, a key or a
 * secret.
 *
 * Hedera (optional): the body may carry `pay_to`, the seller's Hedera account. It must equal the
 * book's registered account (`npm run hedera:payto`; both absent is fine) and the approved text then
 * reads "... USDC to <pay_to> on the public board". The listing carries `pay_to` and, when the
 * record step put a LISTING on HCS for this approval, `hcs` = "<topic>/<seq>". Publish never needs
 * a LISTING.
 *
 * Splits: for a game in SPLIT_GAMES the run carries its lap splits (`s1`..`sN`, `split_kind` "lap")
 * from `arcade_splits`, issued only when they add up to the replayed time and come from the same
 * replay (the same final hash). A missing tool, an error or a disagreement issues the run without
 * splits and logs why: splits never fail a publish.
 *
 * An approval spent on an owner op (`used_for`: a console link or release, a house batch) is
 * ls_reused here. The done view carries explorer links for both transactions and the entities.
 */
import { createHash, randomBytes } from "node:crypto";
import { BOOK_RE } from "../approvals.js";
import { ACCOUNT_RE } from "../config.js";
import type { PublishResult, Store } from "../store.js";
import { shortWallet } from "../consoles.js";
import {
  ArkivError,
  expiryBlock,
  splitValues,
  stampValues,
  type ArkivPort,
  type CreateSpec,
  type EntityRow,
  type ExpirySpec,
  type ListingValues,
  type RunValues,
  type StampRow,
  type StampValues,
  type TypedValue,
} from "./client.js";
import { CheckerError, LOG_MAX, LOG_MIN, parseHeader, splitsVerdict, verdict, type CheckerPort, type SplitsPort } from "./checker.js";
import { decryptGhost, encryptGhost, sha256Hex } from "./ghost.js";
import { KEY_RE } from "./queries.js";
import { GAME_IDS, LISTING_DAYS, LISTING_FLAGS, LISTING_SCHEMA, RUN_FLAGS, RUN_SCHEMA, STAMP_FLAGS, toSdkValues, type EntityKind } from "./schema.js";
import { toSpecJson } from "./spec-json.js";

export type PublishFailure = "ls_expired" | "ls_wrong" | "ls_mismatch" | "ls_reused" | "ls_copied" | "ls_not_linked" | "ls_publish_fail";

export interface PublishView {
  stage: "check" | "sign" | "write" | "done";
  ok: boolean | null;
  failure: PublishFailure | null;
  data: Record<string, unknown>;
}

/** A request the service refuses: 400 bad_body, 404 unknown_id, 409 not_signing, 503 not configured or unavailable. */
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
  /** ARKIV_CHAIN_ID, issued to the console with the specs. */
  chainId: number;
  /** ARKIV_RPC without the access key (what /arkiv/config answers), issued to the console. */
  rpc: string;
  /** Whether a new job may start (config complete, right chain, funded checker). Default: yes. */
  gate?: WriteGate;
  /** The lap-splits tool (absent: runs are issued without splits). */
  splits?: SplitsPort | null;
  /** Explorer links for the done view (absent: no `explorer` in it). */
  explorer?: { tx(hash: string | null): string | null; entity(key: string | null): string | null } | null;
  now?: () => number;
  log?: (line: string) => void;
  /** How long a job is held for repeat POSTs and GETs (1 h). */
  holdMs?: number;
  /** An unspent approval older than this is ls_expired (24 h). */
  approvalTtlMs?: number;
  /** A stamp write still out after this long fails the job (ls_publish_fail); the queue waits it out. */
  writeTimeoutMs?: number;
  /** A console entity the node does not have yet is asked for this many times... (4) */
  verifyTries?: number;
  /** ...this far apart (1500 ms). */
  verifyGapMs?: number;
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

/** What the checker's replay of this job's log gave: its time, and the game's hash after the last step. */
interface Replayed {
  frames: number;
  finalHash: number | undefined;
}

/** What a job issued for the console to sign. */
interface Issued {
  /** The run to write; null for a relist (the run is `runKey`, already stamped). */
  run: CreateSpec<RunValues> | null;
  runKey: string | null;
  /** The relisted run's stamp. */
  stamp: StampRow | null;
  listing: CreateSpec<ListingValues>;
  /** The console's own live listing of the run this relist replaces. */
  replaces: string | null;
  replay: Replayed;
  tool: string;
}

/** What the console reported: its transaction and the two entity keys (lowercase). */
interface Report {
  tx: string | null;
  run: string;
  listing: string;
}

interface Job {
  id: string;
  key: string;
  body: Body;
  view: PublishView;
  createdMs: number;
  running: boolean;
  issued: Issued | null;
  /** The console's last report (kept so a failed stamp can be retried and a repeat recognised). */
  reported: Report | null;
  /** What the done view answered, and this job's replay (a late report fills in the console's tx). */
  result: PublishResult | null;
  replay?: Replayed;
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

/**
 * The dedupe rule (Q7): a log is on the board once, under one book. True when the live run (or
 * stamp) of this log belongs to another book, so this one is a copy. Publish and the HCS record
 * both ask it.
 */
export function isCopy(existing: { book?: string } | null | undefined, book: string): boolean {
  return !!existing && existing.book !== book;
}

/** The logged reason for ls_copied. */
export const COPIED = "this log is already on the board under another book";

/** What World App showed for the listing: the only text an approval allows. */
export function actionText(title: string, frames: number, priceC: number, payTo?: string | null): string {
  const to = payTo ? ` to ${payTo}` : "";
  return `List ${title} ${fmtTime(frames)} ghost for ${priceText(priceC)} USDC${to} on the public board`;
}

const CONTROL = /[\u0000-\u001f\u007f]/;
const B64 = /^[A-Za-z0-9+/]*={0,2}$/;
const TX_RE = /^0x[0-9a-fA-F]{64}$/;

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

/** POST /arkiv/publish/{id}/written's body: {tx, run, listing}, all 0x + 64 hex, two distinct keys. */
export function parseReport(raw: Record<string, unknown>): { tx: string; run: string; listing: string } {
  const { tx, run, listing } = raw;
  if (typeof tx !== "string" || !TX_RE.test(tx)) throw bad();
  if (typeof run !== "string" || !KEY_RE.test(run)) throw bad();
  if (typeof listing !== "string" || !KEY_RE.test(listing)) throw bad();
  if (run.toLowerCase() === listing.toLowerCase()) throw bad();
  return { tx: tx.toLowerCase(), run: run.toLowerCase(), listing: listing.toLowerCase() };
}

/** Two typed values are the same (key, bytes and addr compared as lowercase hex). */
function sameValue(a: TypedValue, b: TypedValue): boolean {
  if (a.type !== b.type) return false;
  if (a.type === "key" || a.type === "bytes" || a.type === "addr") return String(a.value).toLowerCase() === String(b.value).toLowerCase();
  return a.value === b.value;
}

export class Publisher {
  private readonly jobs = new Map<string, Job>();
  private readonly byKey = new Map<string, string>();
  private readonly now: () => number;
  private readonly holdMs: number;
  private readonly approvalTtlMs: number;
  private readonly writeTimeoutMs: number;
  private readonly verifyTries: number;
  private readonly verifyGapMs: number;
  private section: Promise<unknown> = Promise.resolve();

  constructor(private readonly opts: PublisherOptions) {
    this.now = opts.now ?? Date.now;
    this.holdMs = opts.holdMs ?? 3_600_000;
    this.approvalTtlMs = opts.approvalTtlMs ?? 24 * 3_600_000;
    this.writeTimeoutMs = opts.writeTimeoutMs ?? 60_000;
    this.verifyTries = Math.max(1, opts.verifyTries ?? 4);
    this.verifyGapMs = opts.verifyGapMs ?? 1500;
  }

  /** Start (or find) the job for this approval. Throws PublishRefused (400 or 503). */
  start(raw: Record<string, unknown>): { id: string; expires_s: number } {
    const body = parseBody(raw);
    const nowMs = this.now();
    this.prune(nowMs);
    const key = createHash("sha256").update(body.jti).digest("hex");
    const held = this.jobs.get(this.byKey.get(key) ?? "");
    // A held job runs again (same id, this body) when it failed, or waits at sign: the console's retry.
    const again = !!held && !held.running && (held.view.stage === "sign" || (held.view.stage === "done" && held.view.ok === false));
    if (held && !again) return { id: held.id, expires_s: PUBLISH_EXPIRES_S };
    const gate = this.opts.gate?.() ?? null;
    if (gate) throw new PublishRefused(503, gate);
    const job: Job = held ?? { id: randomBytes(16).toString("base64url"), key, body, view: this.checking(), createdMs: nowMs, running: false, issued: null, reported: null, result: null };
    job.body = body;
    job.view = this.checking();
    job.createdMs = nowMs;
    job.issued = null;
    job.reported = null;
    job.result = null;
    delete job.replay;
    this.jobs.set(job.id, job);
    this.byKey.set(key, job.id);
    job.running = true;
    this.run(job)
      .catch((err: unknown) => this.fail(job, "ls_publish_fail", `internal: ${(err as Error)?.name ?? "error"}`))
      .finally(() => {
        job.running = false;
      });
    return { id: job.id, expires_s: PUBLISH_EXPIRES_S };
  }

  view(id: string): PublishView | undefined {
    return this.jobs.get(id)?.view;
  }

  /**
   * POST /arkiv/publish/{id}/written: the console's transaction and keys. Answers {ok: true} and
   * checks and stamps in the background. Throws PublishRefused: 404 unknown_id; 400 bad_body (the
   * body's shape, or a relist naming another run); 409 not_signing (nothing issued yet, or other
   * keys than those already answered).
   */
  written(id: string, raw: Record<string, unknown>): { ok: true } {
    const job = this.jobs.get(id);
    if (!job) throw new PublishRefused(404, "unknown_id");
    const r = parseReport(raw);
    if (job.issued?.runKey && r.run !== job.issued.runKey) throw bad();
    const sameKeys = (k: { run: unknown; listing: unknown } | null) => !!k && k.run === r.run && k.listing === r.listing;
    if (job.view.stage === "done" && job.view.ok === true) {
      if (!sameKeys(job.result)) throw new PublishRefused(409, "not_signing");
      if (job.result && job.result.tx === null) this.lateTx(job, r.tx);
      return { ok: true };
    }
    if (job.running) {
      if (job.view.stage === "write" && sameKeys(job.reported)) return { ok: true };
      throw new PublishRefused(409, "not_signing");
    }
    const retry = job.view.stage === "done" && job.reported !== null;
    if (!job.issued || !(job.view.stage === "sign" || retry)) throw new PublishRefused(409, "not_signing");
    job.reported = r;
    job.running = true;
    job.view = { stage: "write", ok: null, failure: null, data: {} };
    this.serial(() => this.verifyAndStamp(job, r))
      .catch((err: unknown) => this.fail(job, "ls_publish_fail", `internal: ${(err as Error)?.name ?? "error"}`))
      .finally(() => {
        job.running = false;
      });
    return { ok: true };
  }

  private checking(): PublishView {
    return { stage: "check", ok: null, failure: null, data: {} };
  }

  private what(b: Body, frames = b.frames): string {
    return `${b.book} ${b.game} ${fmtTime(frames)}`;
  }

  private fail(job: Job, failure: PublishFailure, why: string): void {
    if (job.view.stage === "done") return;
    job.view = { stage: "done", ok: false, failure, data: {} };
    this.opts.log?.(`arkiv publish ${this.what(job.body)}: ${failure} (${why})`);
  }

  /**
   * The job's done view. `replay` is what this job's own replay gave (the console shows it as the run's check): the
   * frames and the tool's final hash as it printed it (null when it printed none). A job answered from the
   * approval's record never replayed, so it has none.
   */
  private done(job: Job, result: PublishResult, note = "", replay?: Replayed): void {
    const ex = this.opts.explorer;
    const stamp = result.stamp ?? null;
    const stampTx = result.stamp_tx ?? null;
    const explorer = ex
      ? { explorer: { tx: ex.tx(result.tx), run: ex.entity(result.run), listing: ex.entity(result.listing), stamp: ex.entity(stamp), stamp_tx: ex.tx(stampTx) } }
      : {};
    const replayed = replay ? { replay: { frames: replay.frames, final_hash: replay.finalHash ?? null } } : {};
    job.result = { ...result };
    job.replay = replay;
    job.view = {
      stage: "done",
      ok: true,
      failure: null,
      data: { run: result.run, listing: result.listing, tx: result.tx, stamp, stamp_tx: stampTx, ...explorer, ...replayed },
    };
    const txs = `${result.tx ? ` tx ${result.tx}` : ""}${stampTx ? ` stamp tx ${stampTx}` : ""}`;
    this.opts.log?.(`arkiv publish ${this.what(job.body)}: run ${result.run} listing ${result.listing} stamp ${stamp ?? "none"}${txs}${note}`);
  }

  /** The console's report came after the bridge found its entities itself: the done view gains its tx. */
  private lateTx(job: Job, tx: string): void {
    if (!job.result) return;
    const result = { ...job.result, tx };
    this.opts.store.setApprovalResult(job.body.jti, result);
    this.done(job, result, " (the console's transaction, reported late)", job.replay);
  }

  /** The dedupe-spend-issue and check-stamp sections run one job at a time, so two approvals of one log can't both stamp it. */
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.section.then(fn, fn);
    this.section = run.catch(() => undefined);
    return run;
  }

  private async run(job: Job): Promise<void> {
    const b = job.body;
    const { store, checker } = this.opts;

    // 2. The approval: granted here, for this book and this text, and not spent on another log.
    const rec = store.approvalFor(b.jti);
    if (!rec) return this.fail(job, "ls_expired", "approval unknown to this bridge");
    if (rec.log_h === undefined && this.now() - rec.at * 1000 > this.approvalTtlMs) {
      return this.fail(job, "ls_expired", "approval older than 24 h");
    }
    if (rec.book !== b.book) return this.fail(job, "ls_wrong", "approved for another book");
    if (rec.used_for !== undefined) return this.fail(job, "ls_reused", "approval already spent on an owner op");
    if (createHash("sha256").update(b.action).digest("hex") !== rec.action_sha) {
      return this.fail(job, "ls_mismatch", "not the text World App showed");
    }
    if (rec.log_h !== undefined && rec.log_h !== b.logH) return this.fail(job, "ls_reused", "approval already used for another run");
    // A result from before console-owned records (no stamp) is not on the board: list it again.
    if (rec.log_h === b.logH && rec.result?.stamp) return this.done(job, rec.result, " (already written)");

    // 3. The book: issued by this bridge after a World ID proof.
    const book = store.recordForBook(b.book);
    if (!book) return this.fail(job, "ls_wrong", "book not issued by this bridge");

    // 4. The log: its header names the game it claims.
    if (b.headerGame !== b.game) return this.fail(job, "ls_mismatch", "the log is another game's");

    // 5. The replay: the checker's own time, or nothing.
    let frames: number;
    let finalHash: number | undefined;
    try {
      const replayed = await checker.replay(b.game, b.logH, b.log);
      const v = verdict(b.game, replayed);
      if (!v.ok) return this.fail(job, "ls_publish_fail", `replay refused: ${v.why}`);
      frames = v.frames;
      finalHash = replayed.final_hash;
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
    const splits = await this.splitsFor(b, frames, finalHash);
    const replay: Replayed = { frames, finalHash };

    // What the console writes: exactly what the checker wrote itself before console-owned records.
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
        ...splitValues(splits),
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

    await this.serial(() => this.issue(job, run, listing, replay, tool));
  }

  /** Steps 7-9, one job at a time: dedupe on stamps, a linked wallet, spend, then issue (or stamp what landed). */
  private async issue(job: Job, run: CreateSpec<RunValues>, listing: CreateSpec<ListingValues>, replay: Replayed, tool: string): Promise<void> {
    const b = job.body;
    const { store, arkiv } = this.opts;

    // 7. Dedupe (Q7): a log is on the board once, under one book: the checker's stamp of it.
    let stamp: StampRow | null;
    let live = null;
    try {
      stamp = await arkiv.stampByLogHash(b.logH);
      if (stamp && stamp.book === b.book) live = await arkiv.liveListingFor(stamp.run, stamp.console);
    } catch (err) {
      return this.fail(job, "ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
    }
    if (isCopy(stamp, b.book)) return this.fail(job, "ls_copied", COPIED);
    const listed = !!stamp && !!live && (live.pay_to ?? null) === (b.pay_to ?? null);

    // A linked wallet: only a World-approved wallet's records are stamped, so nothing is issued
    // (and the approval is not spent) while the book has none.
    const wallets = store.consoleWalletsFor(b.book);
    if (!listed && wallets.length === 0) return this.fail(job, "ls_not_linked", "no console bound to this book has a World-approved wallet");
    if (!listed && stamp && !wallets.includes(stamp.console)) {
      return this.fail(job, "ls_not_linked", `the run on the board was written by ${shortWallet(stamp.console)}, no longer linked to this book`);
    }

    // 8. Spend: bind the approval to this log before anything goes out.
    const spent = store.spendApproval(b.jti, b.logH);
    if (spent === "unknown") return this.fail(job, "ls_expired", "approval unknown to this bridge");
    if (spent === "other") return this.fail(job, "ls_reused", "approval already used for another run");

    if (stamp && live && listed) {
      const prior = store.resultForLog(b.logH);
      const result: PublishResult = {
        run: stamp.run,
        listing: live.key,
        tx: prior?.listing === live.key ? prior.tx : null,
        stamp: stamp.key,
        stamp_tx: prior?.stamp === stamp.key ? (prior.stamp_tx ?? null) : null,
      };
      store.setApprovalResult(b.jti, result);
      return this.done(job, result, " (already on the board)", replay);
    }

    if (stamp) {
      // 9a. A relist: a new listing for the stamped run, from its wallet; no new stamp.
      job.issued = { run: null, runKey: stamp.run, stamp, listing, replaces: live?.key ?? null, replay, tool };
      return this.toSign(job, `a listing for run ${stamp.run}`);
    }
    job.issued = { run, runKey: null, stamp: null, listing, replaces: null, replay, tool };

    // 9b. A run and listing a linked wallet already wrote for this log: the console's transaction
    //     landed but it was never told (a timeout). Check them and stamp, rather than sign again.
    let landed: Report | null = null;
    try {
      for (const w of wallets) {
        const r = await arkiv.runByLogHash(b.logH, w);
        const l = r ? await arkiv.liveListingFor(r.key, w) : null;
        if (r && l) {
          landed = { tx: null, run: r.key.toLowerCase(), listing: l.key.toLowerCase() };
          break;
        }
      }
    } catch (err) {
      return this.fail(job, "ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
    }
    if (landed) {
      const v = await this.verify(job, landed);
      if (v.ok) {
        this.opts.log?.(`arkiv publish ${this.what(b, replay.frames)}: found the console's run ${landed.run} listing ${landed.listing} on Arkiv`);
        job.reported = landed;
        job.view = { stage: "write", ok: null, failure: null, data: {} };
        return this.stamp(job, landed, v.run);
      }
      this.opts.log?.(`arkiv publish ${this.what(b, replay.frames)}: the console's earlier run ${landed.run} is not this one (${v.why}); issued again`);
    }
    // 9c. Issue: the console signs.
    return this.toSign(job, "run and listing");
  }

  private toSign(job: Job, what: string): void {
    const i = job.issued!;
    job.view = {
      stage: "sign",
      ok: null,
      failure: null,
      data: {
        issue: {
          chain_id: this.opts.chainId,
          rpc: this.opts.rpc,
          run: i.run ? toSpecJson(i.run) : null,
          run_key: i.runKey,
          listing: toSpecJson(i.listing),
          replaces: i.replaces,
        },
      },
    };
    this.opts.log?.(`arkiv publish ${this.what(job.body, i.replay.frames)}: issued to the console (${what})`);
  }

  /** The section `written` starts: check the console's entities, then stamp. */
  private async verifyAndStamp(job: Job, r: Report): Promise<void> {
    const v = await this.verify(job, r);
    if (!v.ok) return this.fail(job, v.failure, v.why);
    return this.stamp(job, r, v.run);
  }

  /** One entity, asked again while the node does not have it yet. */
  private async entity(key: string): Promise<EntityRow | null> {
    for (let i = 0; ; i++) {
      const e = await this.opts.arkiv.getEntity(key);
      if (e || i + 1 >= this.verifyTries) return e;
      await new Promise((ok) => setTimeout(ok, this.verifyGapMs));
    }
  }

  /** The console's entities, read back and checked against what this job issued (see the header). */
  private async verify(job: Job, r: Report): Promise<{ ok: true; run: EntityRow | null } | { ok: false; failure: PublishFailure; why: string }> {
    const b = job.body;
    const i = job.issued!;
    const no = (failure: PublishFailure, why: string) => ({ ok: false as const, failure, why });
    let runE: EntityRow | null = null;
    let listE: EntityRow | null;
    try {
      if (i.run) runE = await this.entity(r.run);
      listE = await this.entity(r.listing);
    } catch (err) {
      return no("ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
    }
    if (i.run && !runE) return no("ls_publish_fail", "the run is not on Arkiv");
    if (!listE) return no("ls_publish_fail", "the listing is not on Arkiv");
    const wallets = this.opts.store.consoleWalletsFor(b.book);
    const owner = runE ? runE.creator : i.stamp!.console;
    if (!owner || !wallets.includes(owner)) {
      const who = owner ? shortWallet(owner) : "an unknown wallet";
      return no("ls_not_linked", `the run was created by ${who}, not a wallet linked to this book`);
    }
    if (runE) {
      const off = this.mismatch("run", RUN_SCHEMA, runE, i.run!, {}, b);
      if (off) return no("ls_publish_fail", `the run on Arkiv is not the one issued (${off})`);
    }
    if (listE.creator !== owner) {
      if (!listE.creator || !wallets.includes(listE.creator)) return no("ls_not_linked", `the listing was created by ${listE.creator ? shortWallet(listE.creator) : "an unknown wallet"}, not a wallet linked to this book`);
      return no("ls_publish_fail", "the listing and the run come from different wallets");
    }
    const off = this.mismatch("listing", LISTING_SCHEMA, listE, i.listing, { run: i.runKey ?? r.run }, b);
    if (off) return no("ls_publish_fail", `the listing on Arkiv is not the one issued (${off})`);
    if (i.replaces) {
      // A relist deletes the listing it replaces in the same transaction: until it is gone, two
      // listings of the run (with different pay_to) would both be live.
      let old: EntityRow | null;
      try {
        old = await this.opts.arkiv.getEntity(i.replaces);
      } catch (err) {
        return no("ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
      }
      if (old) return no("ls_publish_fail", `the listing it replaces is still live (${i.replaces}): the relist deletes it in the same transaction`);
    }
    return { ok: true, run: runE };
  }

  /** The first thing on an entity that is not what was issued, or null. */
  private mismatch(kind: EntityKind, schema: string, e: EntityRow, spec: CreateSpec<object>, extra: Record<string, unknown>, b: Body): string | null {
    if (e.schema !== schema) return "its schema";
    // An owner or flags the node did not report are not what was issued: never stamped on trust.
    if (!e.owner || e.owner !== e.creator) return "its owner";
    if (!e.flags || e.flags.readonly !== spec.flags.readonly || e.flags.permissionlessExtension !== spec.flags.permissionlessExtension) return "its flags";
    if (e.payload) return "its payload";
    const want = toSdkValues(kind, { ...(spec.values as Record<string, unknown>), ...extra }) as Record<string, TypedValue>;
    for (const name of new Set([...Object.keys(want), ...Object.keys(e.values)])) {
      const w = want[name];
      const g = e.values[name];
      if (!w || !g) return name;
      if (kind === "run" && name === "log_enc") {
        // A retry issues a fresh nonce: any ghost that decrypts under the ghost key to this log is this one.
        const sealed = g.type === "bytes" && typeof g.value === "string" ? Uint8Array.from(Buffer.from(g.value.slice(2), "hex")) : null;
        const plain = sealed ? decryptGhost(this.opts.ghostSecret, b.logH, sealed) : null;
        if (!plain || !Buffer.from(plain).equals(Buffer.from(b.log))) return name;
        continue;
      }
      if (!sameValue(w, g)) return name;
    }
    return null;
  }

  /** The stamp, once the console's entities checked out (a relist keeps its run's stamp). */
  private async stamp(job: Job, r: Report, runE: EntityRow | null): Promise<void> {
    const b = job.body;
    const i = job.issued!;
    const { store, arkiv } = this.opts;
    const prior = store.approvalFor(b.jti)?.result;
    if (!i.run) {
      const result: PublishResult = { run: i.runKey!, listing: r.listing, tx: r.tx, stamp: i.stamp!.key, stamp_tx: prior?.stamp === i.stamp!.key ? (prior.stamp_tx ?? null) : null };
      store.setApprovalResult(b.jti, result);
      return this.done(job, result, " (relisted; the run keeps its stamp)", i.replay);
    }

    // A stamp this approval already records for this run (it landed after a timeout, or its receipt
    // was lost): it answers, whether or not the node shows it yet. Never a second stamp.
    if (prior?.stamp && prior.run === r.run) {
      const result: PublishResult = { run: r.run, listing: r.listing, tx: r.tx ?? prior.tx, stamp: prior.stamp, stamp_tx: prior.stamp_tx ?? null };
      store.setApprovalResult(b.jti, result);
      return this.done(job, result, " (the stamp this approval already records)", i.replay);
    }

    // One stamp per log: one that landed meanwhile (another approval of this log) answers instead.
    let existing: StampRow | null;
    try {
      existing = await arkiv.stampByLogHash(b.logH);
    } catch (err) {
      return this.fail(job, "ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
    }
    if (isCopy(existing, b.book)) return this.fail(job, "ls_copied", COPIED);
    if (existing) {
      let listingKey = r.listing;
      if (existing.run !== r.run) {
        try {
          listingKey = (await arkiv.liveListingFor(existing.run, existing.console))?.key ?? r.listing;
        } catch (err) {
          return this.fail(job, "ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
        }
      }
      const result: PublishResult = {
        run: existing.run,
        listing: listingKey,
        tx: existing.run === r.run ? r.tx : (store.resultForLog(b.logH)?.tx ?? null),
        stamp: existing.key,
        stamp_tx: prior?.stamp === existing.key ? (prior.stamp_tx ?? null) : null,
      };
      store.setApprovalResult(b.jti, result);
      return this.done(job, result, " (already stamped)", i.replay);
    }

    const fh = i.replay.finalHash;
    const spec: CreateSpec<StampValues> = {
      values: stampValues(i.run.values, r.run, runE!.creator!, typeof fh === "number" && Number.isSafeInteger(fh) && fh >= 0 ? fh : null, i.tool),
      flags: { ...STAMP_FLAGS },
      expiry: await this.stampExpiry(i.run.expiry, runE?.expiresAt ?? null),
    };
    const write = arkiv.writeStamp(spec);
    let timer: NodeJS.Timeout | undefined;
    const timedOut = new Promise<"timeout">((ok) => {
      timer = setTimeout(() => ok("timeout"), this.writeTimeoutMs);
    });
    const outcome = await Promise.race([write.then((w) => ({ w }), (err: unknown) => ({ err })), timedOut]);
    clearTimeout(timer);
    const resultOf = (w: { stamp: string; tx: string }): PublishResult => ({ run: r.run, listing: r.listing, tx: r.tx, stamp: w.stamp.toLowerCase(), stamp_tx: w.tx });
    if (outcome === "timeout") {
      this.fail(job, "ls_publish_fail", "stamp write timed out");
      // Hold the section until the transaction settles, so a retry's dedupe sees it.
      const late = await write.then((w) => w, () => null);
      if (late) {
        store.setApprovalResult(b.jti, resultOf(late));
        this.opts.log?.(`arkiv publish ${this.what(b, i.replay.frames)}: the stamp landed after the timeout: stamp ${late.stamp}`);
      }
      return;
    }
    if ("err" in outcome) {
      const why = outcome.err instanceof ArkivError ? outcome.err.message : "write failed";
      // The transaction may have gone out before the error (a receipt that never came back): look
      // for the stamp before failing, so the console's retry answers it rather than stamp again.
      const landed = await this.landedStamp(b.logH, r.run);
      if (landed) {
        const result: PublishResult = { run: r.run, listing: r.listing, tx: r.tx, stamp: landed.key, stamp_tx: null };
        store.setApprovalResult(b.jti, result);
        return this.done(job, result, ` (the stamp write said: ${why}; the stamp is on Arkiv)`, i.replay);
      }
      return this.fail(job, "ls_publish_fail", `stamp write: ${why}`);
    }
    const result = resultOf(outcome.w);
    store.setApprovalResult(b.jti, result);
    return this.done(job, result, "", i.replay);
  }

  /**
   * The stamp's expiry: with its run (the run entity's own block), but never after the run's issued
   * expiry (season end + 30 d), so a console cannot push the checker's stamp out to the chain's
   * maximum. Without the chain's clock: the issued expiry itself.
   */
  private async stampExpiry(issued: ExpirySpec, runBlock: bigint | null): Promise<ExpirySpec> {
    let cap: bigint;
    try {
      cap = expiryBlock(issued, await this.opts.arkiv.blockTiming());
    } catch {
      return issued;
    }
    return { kind: "atBlock", block: runBlock !== null && runBlock < cap ? runBlock : cap };
  }

  /** This run's stamp, if the node shows one for this log (asked a few times: it may be a block behind). */
  private async landedStamp(logH: string, runKey: string): Promise<StampRow | null> {
    for (let t = 0; t < this.verifyTries; t++) {
      try {
        const s = await this.opts.arkiv.stampByLogHash(logH);
        if (s && s.run.toLowerCase() === runKey) return s;
      } catch {
        // asked again below
      }
      if (t + 1 < this.verifyTries) await new Promise((ok) => setTimeout(ok, this.verifyGapMs));
    }
    return null;
  }

  /** The run's lap splits from arcade_splits, or null (logged): splits never fail a publish. */
  private async splitsFor(b: Body, frames: number, finalHash: number | undefined): Promise<number[] | null> {
    const port = this.opts.splits;
    if (!port || !port.games.includes(b.game)) return null;
    const note = (why: string) => {
      this.opts.log?.(`arkiv publish ${this.what(b, frames)}: splits not written (${why})`);
      return null;
    };
    try {
      const v = splitsVerdict(await port.splits(b.game, b.logH, b.log), frames, finalHash);
      return v.ok ? v.splits : note(v.why);
    } catch (err) {
      return note(`splits tool: ${err instanceof CheckerError ? err.message : "error"}`);
    }
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

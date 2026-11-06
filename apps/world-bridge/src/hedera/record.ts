/**
 * POST /hedera/record: the handler's `record` step puts the World-approved listing on the market
 * topic as a LISTING message, word for word, before the checker's replay (that comes at publish).
 * Jobs are keyed by id and by the approval's jti (sha256 of it; the jti is never stored or logged):
 *
 *   check   the approval, the book, the approved text, the payout account, then the copy check
 *   submit  the LISTING is out; waiting for its receipt (10 s)
 *   done    {topic, seq, tx, hashscan, hashscan_topic}, or one of the handler's own failure names
 *
 * Failures, in this order:
 *   ls_expired      approval unknown to this bridge, or unspent and older than 24 h
 *   ls_wrong        approved for another book, or the book was not issued here
 *   ls_mismatch     sha256(action) differs, price_c differs from ARKIV_GHOST_PRICE_C, action is not
 *                   actionText(title, frames, price_c, pay_to), or pay_to is not the book's
 *                   registered account
 *   ls_reused       the approval was already spent (published) with no LISTING for it, or spent on
 *                   an owner op (a console link or release, a house batch)
 *   ls_copied       the body's log_h is already on the board under another book: a copied run,
 *                   which publish would refuse, so no LISTING goes out for it
 *   ls_record_fail  HCS refused it, timed out, or is not configured; Arkiv could not be read for
 *                   the copy check
 *
 * The copy check is publish's own dedupe (Q7), asked of Arkiv before anything reaches the topic, so
 * the append-only topic never carries a LISTING for a listing publish refuses as a copy. It needs the
 * run's log_h, which a console sends from this build on; a body without it (an older console) is
 * recorded as before and publish still refuses the copy.
 *
 * The record does not spend the approval (publish does). A repeat with the same jti answers the same
 * id; a retry after a failure first asks for the earlier transaction's receipt and reuses it if it
 * landed, so one approval puts one LISTING on the topic.
 */
import { createHash, randomBytes } from "node:crypto";
import { BOOK_RE } from "../approvals.js";
import { ArkivError, type ArkivPort } from "../arkiv/client.js";
import { actionText, COPIED, fmtTime, isCopy, priceText } from "../arkiv/publish.js";
import { GAME_IDS } from "../arkiv/schema.js";
import { ACCOUNT_RE } from "../config.js";
import type { Store } from "../store.js";
import { listingMessage, seqNumber } from "./messages.js";
import { hashscan, shortSdkError, type HcsReceipt, type HederaPort } from "./net.js";

export type RecordFailure = "ls_expired" | "ls_wrong" | "ls_mismatch" | "ls_reused" | "ls_copied" | "ls_record_fail";

export interface RecordView {
  stage: "check" | "submit" | "done";
  ok: boolean | null;
  failure: RecordFailure | null;
  data: Record<string, unknown>;
}

/** A request refused before any job starts: 400 bad_body, 503 not configured or unavailable. */
export class RecordRefused extends Error {
  constructor(public readonly status: number, public readonly error: string) {
    super(error);
  }
}

export interface RecordBody {
  book: string;
  jti: string;
  action: string;
  game: string;
  title: string;
  frames: number;
  price_c: number;
  pay_to?: string;
  /** sha256 of the run's log (64 lowercase hex), for the copy check. Optional: older consoles omit it. */
  log_h?: string;
}

const CONTROL = /[\u0000-\u001f\u007f]/;
const LOG_H_RE = /^[0-9a-f]{64}$/;

/** The publish body without `log`, plus its optional `log_h` (spec: HTTP contract). Anything off: 400 bad_body. */
export function parseRecordBody(raw: Record<string, unknown>): RecordBody {
  const bad = () => new RecordRefused(400, "bad_body");
  const { book, jti, action, game, title, frames, price_c, pay_to, log_h } = raw;
  if (typeof book !== "string" || !BOOK_RE.test(book)) throw bad();
  if (typeof jti !== "string" || !/^[\x21-\x7e]{1,256}$/.test(jti)) throw bad();
  if (typeof action !== "string" || action === "" || action.length > 160 || CONTROL.test(action)) throw bad();
  if (typeof game !== "string" || !GAME_IDS.includes(game)) throw bad();
  if (typeof title !== "string" || title.trim() === "" || Buffer.byteLength(title) > 64 || CONTROL.test(title)) throw bad();
  if (typeof frames !== "number" || !Number.isInteger(frames) || frames < 1 || frames > 0xffffffff) throw bad();
  if (typeof price_c !== "number" || !Number.isInteger(price_c) || price_c < 0 || price_c > 1_000_000) throw bad();
  if (pay_to !== undefined && pay_to !== null && (typeof pay_to !== "string" || !ACCOUNT_RE.test(pay_to))) throw bad();
  if (log_h !== undefined && log_h !== null && (typeof log_h !== "string" || !LOG_H_RE.test(log_h))) throw bad();
  return {
    book,
    jti,
    action,
    game,
    title,
    frames,
    price_c,
    ...(typeof pay_to === "string" ? { pay_to } : {}),
    ...(typeof log_h === "string" ? { log_h } : {}),
  };
}

export type RecordGate = () => null | "hedera_not_configured" | "hedera_unavailable";

export interface RecorderOptions {
  store: Store;
  /** Null when the record is not configured (then every start is 503). */
  hedera: HederaPort | null;
  /** The copy check's Arkiv reads (Q7). Null or absent: Arkiv is off here, no copy check (publish is off too). */
  arkiv?: Pick<ArkivPort, "runByLogHash"> | null;
  topic: string;
  /** ARKIV_GHOST_PRICE_C. */
  priceC: number;
  gate: RecordGate;
  now?: () => number;
  log?: (line: string) => void;
  /** Submit and receipt, together (10 s). */
  timeoutMs?: number;
  /** The copy check's Arkiv read (3 s). */
  checkMs?: number;
  approvalTtlMs?: number;
  holdMs?: number;
}

/** How long the console should keep asking. */
export const RECORD_EXPIRES_S = 120;

interface Job {
  id: string;
  key: string;
  body: RecordBody;
  view: RecordView;
  createdMs: number;
  running: boolean;
}

function within<T>(p: Promise<T>, ms: number): Promise<T | "timeout"> {
  let timer: NodeJS.Timeout | undefined;
  const t = new Promise<"timeout">((ok) => {
    timer = setTimeout(() => ok("timeout"), ms);
  });
  return Promise.race([p, t]).finally(() => clearTimeout(timer));
}

export class Recorder {
  private readonly jobs = new Map<string, Job>();
  private readonly byKey = new Map<string, string>();
  private readonly now: () => number;
  private readonly timeoutMs: number;
  private readonly checkMs: number;
  private readonly approvalTtlMs: number;
  private readonly holdMs: number;

  constructor(private readonly opts: RecorderOptions) {
    this.now = opts.now ?? Date.now;
    this.timeoutMs = opts.timeoutMs ?? 10_000;
    this.checkMs = opts.checkMs ?? 3_000;
    this.approvalTtlMs = opts.approvalTtlMs ?? 24 * 3_600_000;
    this.holdMs = opts.holdMs ?? 3_600_000;
  }

  start(raw: Record<string, unknown>): { id: string; expires_s: number } {
    const body = parseRecordBody(raw);
    const nowMs = this.now();
    this.prune(nowMs);
    const key = createHash("sha256").update(body.jti).digest("hex");
    const held = this.jobs.get(this.byKey.get(key) ?? "");
    if (held && !(held.view.stage === "done" && held.view.ok === false)) return { id: held.id, expires_s: RECORD_EXPIRES_S };
    const gate = this.opts.gate();
    if (gate) throw new RecordRefused(503, gate);
    if (!this.opts.hedera) throw new RecordRefused(503, "hedera_not_configured");
    const job: Job = held ?? { id: randomBytes(16).toString("base64url"), key, body, view: this.checking(), createdMs: nowMs, running: false };
    job.body = body;
    job.view = this.checking();
    job.createdMs = nowMs;
    this.jobs.set(job.id, job);
    this.byKey.set(key, job.id);
    job.running = true;
    this.run(job)
      .catch((err: unknown) => this.fail(job, "ls_record_fail", `internal: ${(err as Error)?.name ?? "error"}`))
      .finally(() => {
        job.running = false;
      });
    return { id: job.id, expires_s: RECORD_EXPIRES_S };
  }

  view(id: string): RecordView | undefined {
    return this.jobs.get(id)?.view;
  }

  private checking(): RecordView {
    return { stage: "check", ok: null, failure: null, data: {} };
  }

  private what(b: RecordBody): string {
    return `${b.book} ${b.game} ${fmtTime(b.frames)}`;
  }

  private fail(job: Job, failure: RecordFailure, why: string): void {
    if (job.view.stage === "done") return;
    job.view = { stage: "done", ok: false, failure, data: {} };
    this.opts.log?.(`hedera record ${this.what(job.body)}: ${failure} (${why})`);
  }

  private done(job: Job, tx: string, seq: string, note = ""): void {
    const n = seqNumber(seq);
    job.view = { stage: "done", ok: true, failure: null, data: { topic: this.opts.topic, seq: n, tx, hashscan: hashscan.tx(tx), hashscan_topic: hashscan.topic(this.opts.topic) } };
    this.opts.log?.(`hedera record ${this.what(job.body)}: LISTING #${seq} on ${this.opts.topic}, tx ${tx}${note} ${hashscan.tx(tx)}`);
  }

  private async run(job: Job): Promise<void> {
    const b = job.body;
    const { store } = this.opts;
    const hedera = this.opts.hedera as HederaPort;

    // The approval: granted here, recent, for this book and this text.
    const rec = store.approvalFor(b.jti);
    if (!rec) return this.fail(job, "ls_expired", "approval unknown to this bridge");
    if (rec.log_h === undefined && this.now() - rec.at * 1000 > this.approvalTtlMs) return this.fail(job, "ls_expired", "approval older than 24 h");
    if (rec.book !== b.book) return this.fail(job, "ls_wrong", "approved for another book");
    if (rec.used_for !== undefined) return this.fail(job, "ls_reused", "approval already spent on an owner op");
    const book = store.recordForBook(b.book);
    if (!book) return this.fail(job, "ls_wrong", "book not issued by this bridge");
    if (createHash("sha256").update(b.action).digest("hex") !== rec.action_sha) return this.fail(job, "ls_mismatch", "not the text World App showed");
    if (b.price_c !== this.opts.priceC) return this.fail(job, "ls_mismatch", "price differs from ARKIV_GHOST_PRICE_C");
    if (b.action !== actionText(b.title, b.frames, b.price_c, b.pay_to)) return this.fail(job, "ls_mismatch", "approved text does not match the listing");
    if ((b.pay_to ?? null) !== (store.paytoFor(b.book) ?? null)) return this.fail(job, "ls_mismatch", "pay_to is not the book's registered account");

    // One approval, one LISTING: reuse what landed.
    const held = store.hcsListingFor(b.jti);
    if (held?.seq) return this.done(job, held.tx, held.seq, " (already on the topic)");
    if (held?.tx) {
      job.view = { stage: "submit", ok: null, failure: null, data: {} };
      const landed = await within(hedera.receiptOf(held.tx), this.timeoutMs).catch(() => null);
      if (landed && landed !== "timeout") {
        store.setHcsListing(b.jti, { topic: held.topic, tx: held.tx, seq: landed.seq });
        return this.done(job, held.tx, landed.seq, " (an earlier try landed)");
      }
    }
    if (rec.log_h !== undefined) return this.fail(job, "ls_reused", "approval already spent with no LISTING for it");

    // The copy check: publish's own dedupe, before anything reaches the append-only topic.
    const { arkiv } = this.opts;
    if (b.log_h !== undefined && arkiv) {
      const existing = await within(arkiv.runByLogHash(b.log_h), this.checkMs).catch((err: unknown) => ({ err }));
      if (existing === "timeout") return this.fail(job, "ls_record_fail", "Arkiv did not answer the copy check in time");
      if (existing && "err" in existing) {
        const why = existing.err instanceof ArkivError ? existing.err.message : "read failed";
        return this.fail(job, "ls_record_fail", `Arkiv could not be read for the copy check: ${why}`);
      }
      if (isCopy(existing, b.book)) return this.fail(job, "ls_copied", COPIED);
    }

    // Submit, then the receipt, within 10 s together.
    job.view = { stage: "submit", ok: null, failure: null, data: {} };
    let bytes: Uint8Array;
    try {
      bytes = listingMessage({
        book: b.book,
        runner: book.runner_id,
        game: b.game,
        frames: b.frames,
        price: priceText(b.price_c),
        ...(b.pay_to ? { pay_to: b.pay_to } : {}),
        action: b.action,
      });
    } catch {
      return this.fail(job, "ls_record_fail", "LISTING would not fit one message");
    }
    const deadline = this.now() + this.timeoutMs;
    const accepted = await within(hedera.submit(this.opts.topic, bytes), this.timeoutMs).catch((err: unknown) => ({ err }));
    if (accepted === "timeout") return this.fail(job, "ls_record_fail", "HCS did not accept it in time");
    if ("err" in accepted) return this.fail(job, "ls_record_fail", `HCS refused it: ${shortSdkError(accepted.err)}`);
    store.setHcsListing(b.jti, { topic: this.opts.topic, tx: accepted.tx });
    // Whenever the receipt comes, keep the sequence number (publish reads it for the row's `hcs`).
    accepted.receipt.then(
      (r: HcsReceipt) => {
        if (!store.hcsListingFor(b.jti)?.seq) store.setHcsListing(b.jti, { topic: this.opts.topic, tx: accepted.tx, seq: r.seq });
      },
      () => undefined,
    );
    const receipt = await within(accepted.receipt, Math.max(1, deadline - this.now())).catch((err: unknown) => ({ err }));
    if (receipt === "timeout") return this.fail(job, "ls_record_fail", "no receipt within 10 s (a retry reuses it if it lands)");
    if ("err" in receipt) return this.fail(job, "ls_record_fail", `HCS: ${shortSdkError(receipt.err)}`);
    store.setHcsListing(b.jti, { topic: this.opts.topic, tx: accepted.tx, seq: receipt.seq });
    return this.done(job, accepted.tx, receipt.seq);
  }

  private prune(nowMs: number): void {
    for (const [id, j] of this.jobs) {
      if (!j.running && nowMs - j.createdMs > this.holdMs) {
        this.jobs.delete(id);
        if (this.byKey.get(j.key) === id) this.byKey.delete(j.key);
      }
    }
  }
}

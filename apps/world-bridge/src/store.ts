/**
 * The bridge's only state on disk: data/state.json.
 *
 * - books:    nullifier HMAC -> the record book that World ID got (one per human), with the World ID
 *             session its owner proves for each listing approval (server-side only: never logged,
 *             never returned);
 * - bindings: book -> the HMAC of the Agent Pass (iss, sub) bound to it on first approval;
 * - jtis:     ID-token jtis already consumed;
 * - approvals: sha256(jti) -> each listing approval this bridge granted (book, sha256 of the text
 *             World App showed, when) and, once spent, the one log it allows on Arkiv and what the
 *             write answered. The jti itself is never stored or logged;
 * - receipts: payment receipt -> the one run whose ghost it paid for.
 *
 * Every operation is synchronous read-modify-write inside one event-loop turn, so two requests can
 * never interleave inside a claim: the check and the write are one atomic step for this process.
 * Writes go to a temp file and are renamed over the old one.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { bookCandidate } from "./hmac.js";

export interface BookRecord {
  book: string;
  credential: string;
  runner_id: string;
  created_at: number;
  /** World ID 4.0 session id ("session_<hex>") from the sign-up. Secret to this process. */
  session_id?: string;
}

/** What one listing approval allows: exactly one run row plus one listing row, for this book. */
export interface ApprovalRecord {
  book: string;
  /** sha256 (hex) of the action text World App showed. */
  action_sha: string;
  /** When it was granted, in Unix seconds. */
  at: number;
  /** Set when spent: the log (sha256 hex) this approval put on Arkiv. */
  log_h?: string;
  /** Set once the write landed: what /arkiv/publish answered. Keys and tx hashes are public. */
  result?: { run: string; listing: string; tx: string | null };
}

export type SpendResult = "spent" | "same" | "other" | "unknown";

interface StateFile {
  version: 1;
  books: Record<string, BookRecord>;
  bindings: Record<string, { sub_key: string; bound_at: number }>;
  jtis: Record<string, number>;
  approvals: Record<string, ApprovalRecord>;
  receipts: Record<string, string>;
}

/** The store key for an approval: sha256(jti), so the jti never lands on disk. */
export function approvalKey(jti: string): string {
  return createHash("sha256").update(jti).digest("hex");
}

export type BindResult = "bound" | "match" | "mismatch";

export class Store {
  private readonly file: string;
  private state: StateFile;

  constructor(private readonly dir: string, private readonly secret: string) {
    mkdirSync(dir, { recursive: true });
    this.file = join(dir, "state.json");
    this.state = this.read();
  }

  private read(): StateFile {
    try {
      const parsed = JSON.parse(readFileSync(this.file, "utf8")) as Partial<StateFile>;
      return {
        version: 1,
        books: parsed.books ?? {},
        bindings: parsed.bindings ?? {},
        jtis: parsed.jtis ?? {},
        approvals: parsed.approvals ?? {},
        receipts: parsed.receipts ?? {},
      };
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") {
        return { version: 1, books: {}, bindings: {}, jtis: {}, approvals: {}, receipts: {} };
      }
      throw new Error(`state file ${this.file} is unreadable; refusing to start over it`);
    }
  }

  private write(): void {
    const tmp = `${this.file}.tmp`;
    writeFileSync(tmp, JSON.stringify(this.state, null, 1));
    renameSync(tmp, this.file);
  }

  /** The book a nullifier already owns, if any. */
  bookFor(nKey: string): BookRecord | undefined {
    return this.state.books[nKey];
  }

  /**
   * One World ID, one record book. Returns the new book, or the existing one with created=false
   * when this nullifier already has a book (the caller answers id_dup).
   */
  claimBook(
    nKey: string,
    credential: string,
    runner: string,
    now: number,
    sessionId?: string,
  ): { created: boolean; record: BookRecord } {
    const existing = this.state.books[nKey];
    if (existing) return { created: false, record: existing };
    const taken = new Set<string>(Object.values(this.state.books).map((b) => b.book));
    for (const b of Object.keys(this.state.bindings)) taken.add(b);
    let book = "";
    for (let attempt = 0; ; attempt++) {
      book = bookCandidate(this.secret, nKey, attempt);
      if (!taken.has(book)) break;
    }
    const record: BookRecord = { book, credential, runner_id: runner, created_at: now };
    if (sessionId) record.session_id = sessionId;
    this.state.books[nKey] = record;
    this.write();
    return { created: true, record };
  }

  /** The record for a book id, if this bridge issued it. */
  recordForBook(book: string): BookRecord | undefined {
    return Object.values(this.state.books).find((r) => r.book === book);
  }

  /** Give a book its World ID session when it has none yet. False: no such book, or it already has one. */
  setSession(nKey: string, sessionId: string): boolean {
    const rec = this.state.books[nKey];
    if (!rec || rec.session_id) return false;
    rec.session_id = sessionId;
    this.write();
    return true;
  }

  /** Trust on first use: the first approval binds the book to that account; later ones must match. */
  bindOrCheck(book: string, sKey: string, now: number): BindResult {
    const bound = this.state.bindings[book];
    if (!bound) {
      this.state.bindings[book] = { sub_key: sKey, bound_at: now };
      this.write();
      return "bound";
    }
    return bound.sub_key === sKey ? "match" : "mismatch";
  }

  /** Read-only twin of bindOrCheck for an approval the console already backed out of. */
  checkBinding(book: string, sKey: string): BindResult {
    const bound = this.state.bindings[book];
    if (!bound) return "bound";
    return bound.sub_key === sKey ? "match" : "mismatch";
  }

  /** Consume a jti exactly once. False: it was already used. */
  useJti(key: string, now: number): boolean {
    if (this.state.jtis[key] !== undefined) return false;
    this.state.jtis[key] = now;
    this.write();
    return true;
  }

  // ---- Arkiv: listing approvals and ghost receipts ------------------------------------------

  /**
   * Record a listing approval the bridge just granted. Called by both approval providers on
   * success; an approval already recorded (and maybe spent) is never replaced.
   */
  recordApproval(jti: string, book: string, actionSha: string, nowS: number): void {
    const k = approvalKey(jti);
    if (this.state.approvals[k]) return;
    this.state.approvals[k] = { book, action_sha: actionSha, at: nowS };
    this.write();
  }

  approvalFor(jti: string): ApprovalRecord | undefined {
    return this.state.approvals[approvalKey(jti)];
  }

  /**
   * Bind an approval to the one log it puts on Arkiv. "spent": bound now; "same": already bound
   * to this log (a retry); "other": already bound to another log; "unknown": no such approval.
   */
  spendApproval(jti: string, logH: string): SpendResult {
    const rec = this.state.approvals[approvalKey(jti)];
    if (!rec) return "unknown";
    if (rec.log_h !== undefined) return rec.log_h === logH ? "same" : "other";
    rec.log_h = logH;
    this.write();
    return "spent";
  }

  /** Remember what a spent approval's write answered, so a retry answers the same. */
  setApprovalResult(jti: string, result: { run: string; listing: string; tx: string | null }): void {
    const rec = this.state.approvals[approvalKey(jti)];
    if (!rec) return;
    rec.result = result;
    this.write();
  }

  /** What an earlier write of this log answered, if this bridge made it. */
  resultForLog(logH: string): { run: string; listing: string; tx: string | null } | undefined {
    for (const rec of Object.values(this.state.approvals)) {
      if (rec.log_h === logH && rec.result) return rec.result;
    }
    return undefined;
  }

  /** A receipt pays for one run only: true when it is new (now bound to this run) or already this run's. */
  claimReceipt(receipt: string, run: string): boolean {
    const bound = this.state.receipts[receipt];
    if (bound !== undefined) return bound === run.toLowerCase();
    this.state.receipts[receipt] = run.toLowerCase();
    this.write();
    return true;
  }
}

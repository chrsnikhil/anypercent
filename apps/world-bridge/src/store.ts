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
 * - receipts: payment receipt -> the one run whose ghost it paid for (the launcher mock's);
 * - hcsListings: sha256(jti) -> the LISTING message the record step put on HCS for that approval;
 * - purchases: (buyer book, game, seller, run) -> PB's purchase of that ghost: reserved, settled
 *             or released, with the day it counts against the caps;
 * - sales:    settled payment transaction id -> the ghost it bought (run, listing, seller, pay_to,
 *             amount, payer, a counter n);
 * - payto:    book -> the Hedera account its ghosts pay. Kept in its own file, data/payto.json,
 *             written only by `npm run hedera:payto` and re-read here when it changes, so the CLI
 *             never writes state.json under a running service.
 * - consoles: HMAC of a console id -> its tag and the record book it is bound to (one console, one
 *             person). The raw console id is never stored or logged;
 * - house:    the house's BOT batches (labels, log hashes, status and what the write answered, never
 *             the logs) and the next batch letter.
 *
 * Every operation is synchronous read-modify-write inside one event-loop turn, so two requests can
 * never interleave inside a claim: the check and the write are one atomic step for this process.
 * Writes go to a temp file and are renamed over the old one.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from "node:fs";
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

/** What one listing approval allows: one run and its listing (the console writes them, the checker stamps), for this book. */
export interface ApprovalRecord {
  book: string;
  /** sha256 (hex) of the action text World App showed. */
  action_sha: string;
  /** When it was granted, in Unix seconds. */
  at: number;
  /** Set when spent: the log (sha256 hex) this approval put on Arkiv. */
  log_h?: string;
  /**
   * Set once the listing is done: what /arkiv/publish answered. Keys and tx hashes are public. `tx`
   * is the console's transaction (null when the bridge found its entities without being told),
   * `stamp`/`stamp_tx` the checker's stamp; results from before console-owned records have none.
   */
  result?: PublishResult;
  /** Set when spent on an owner op instead of a listing: "console-link:C-7QZP", "house:3f9c0a", ... */
  used_for?: string;
}

/** What one listing approval's publish answered (keys and transaction hashes, all public). */
export interface PublishResult {
  run: string;
  listing: string;
  tx: string | null;
  stamp?: string;
  stamp_tx?: string | null;
}

export type ConsoleState = "unbound" | "bound" | "released";

/** One console, by the HMAC of its id. */
export interface ConsoleRecord {
  /** "C-" + 4 characters of the book alphabet, unique among consoles. */
  tag: string;
  book: string | null;
  state: ConsoleState;
  /** What made the last binding change: a sign-up, a sign-in (id_dup naming the book), an owner op. */
  by: "signup" | "signin" | "link" | "release" | null;
  /** Unix seconds of the last change. */
  at: number;
  /** The Arkiv wallet the console last reported (lowercase 0x address); unauthenticated, like the id. */
  wallet_reported?: string;
  /** The wallet a World-approved link named (lowercase): the only one its runs are stamped from. */
  wallet?: string;
}

export type HouseStatus = "staged" | "approved" | "written";

/** One house batch, by its id (sha256 of the sorted log hashes, 6 hex). Never the logs. */
export interface HouseBatchRecord {
  letter: string;
  game: string;
  labels: string[];
  log_hs: string[];
  status: HouseStatus;
  at: number;
  /** The HOUSE message, once a node accepted it (seq once its receipt came). */
  hcs?: { topic: string; tx: string; seq?: string };
  /** What the write answered: every run, listing and transaction so far. */
  result?: HouseResult;
}

/**
 * A house batch's write: the house wallet's runs, listings and transactions, then the checker's
 * stamps and their transactions. A result from before console-owned records (the checker wrote the
 * rows itself) has no `stamps`.
 */
export interface HouseResult {
  runs: string[];
  listings: string[];
  txs: string[];
  stamps?: string[];
  stamp_txs?: string[];
}

export type SpendResult = "spent" | "same" | "other" | "unknown";

/** The LISTING message for one approval: the transaction once a node accepted it, then its place. */
export interface HcsListingRecord {
  topic: string;
  tx: string;
  /** The topic sequence number (a decimal string), once the receipt came back. */
  seq?: string;
}

export type PurchaseState = "reserved" | "settled" | "released";

/** One of PB's purchases. Reserved and settled ones count against the caps on their day. */
export interface PurchaseRecord {
  id: string;
  buyer: string;
  game: string;
  seller: string;
  run: string;
  listing: string;
  pay_to: string;
  price_c: number;
  /** The service's local day (YYYY-MM-DD) the money counts on. */
  day: string;
  state: PurchaseState;
  /** The payment's transaction id, once PB built it (before it is sent). */
  tx?: string;
  /** Set when settled: the transaction id the console gets as its receipt. */
  receipt?: string;
  late?: boolean;
  at: number;
  /** INTENT on the market topic: its transaction, and its sequence number once the receipt came. */
  intent_tx?: string;
  intent_seq?: number;
  /** RECEIPT on the market topic, once a node accepted it. */
  receipt_msg_tx?: string;
  receipt_msg_seq?: number;
}

/** A settled sale of a listed ghost through the paywall, keyed by its transaction id. */
export interface SaleRecord {
  n: number;
  run: string;
  listing: string;
  /** The seller's book. */
  seller: string;
  game: string;
  pay_to: string;
  /** Atomic units of the asset. */
  amount: string;
  asset: string;
  /** The paying account. */
  payer: string;
  /** The buyer's book when PB bought it, else null (any other x402 client). */
  buyer: string | null;
  at: number;
}

interface StateFile {
  version: 1;
  books: Record<string, BookRecord>;
  bindings: Record<string, { sub_key: string; bound_at: number }>;
  jtis: Record<string, number>;
  approvals: Record<string, ApprovalRecord>;
  receipts: Record<string, string>;
  hcsListings: Record<string, HcsListingRecord>;
  purchases: Record<string, PurchaseRecord>;
  sales: Record<string, SaleRecord>;
  saleSeq: number;
  consoles: Record<string, ConsoleRecord>;
  house: { batches: Record<string, HouseBatchRecord>; letters: number };
}

/** The caps a reservation must fit (cents, per local day). */
export interface PurchaseCaps {
  bookDayC: number;
  agentDayC: number;
}

export type ReserveResult = { ok: true } | { ok: false; why: "book_cap" | "agent_cap" } | { ok: false; why: "settled"; record: PurchaseRecord } | { ok: false; why: "in_flight"; record: PurchaseRecord };

/** The purchase key: (buyer book, game, seller, run). All public already. */
export function purchaseKey(buyer: string, game: string, seller: string, run: string): string {
  return `${buyer}|${game}|${seller}|${run.toLowerCase()}`;
}

const EMPTY = (): StateFile => ({
  version: 1,
  books: {},
  bindings: {},
  jtis: {},
  approvals: {},
  receipts: {},
  hcsListings: {},
  purchases: {},
  sales: {},
  saleSeq: 0,
  consoles: {},
  house: { batches: {}, letters: 0 },
});

/** The store key for an approval: sha256(jti), so the jti never lands on disk. */
export function approvalKey(jti: string): string {
  return createHash("sha256").update(jti).digest("hex");
}

export type BindResult = "bound" | "match" | "mismatch";

export class Store {
  private readonly file: string;
  private readonly paytoFile: string;
  private state: StateFile;
  private payto: Record<string, { account: string; at: number }> = {};
  private paytoStamp = "";

  constructor(private readonly dir: string, private readonly secret: string) {
    mkdirSync(dir, { recursive: true });
    this.file = join(dir, "state.json");
    this.paytoFile = join(dir, "payto.json");
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
        hcsListings: parsed.hcsListings ?? {},
        purchases: parsed.purchases ?? {},
        sales: parsed.sales ?? {},
        saleSeq: typeof parsed.saleSeq === "number" ? parsed.saleSeq : 0,
        consoles: parsed.consoles ?? {},
        house: {
          batches: parsed.house?.batches ?? {},
          letters: typeof parsed.house?.letters === "number" ? parsed.house.letters : 0,
        },
      };
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return EMPTY();
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
    if (rec.used_for !== undefined) return "other";
    if (rec.log_h !== undefined) return rec.log_h === logH ? "same" : "other";
    rec.log_h = logH;
    this.write();
    return "spent";
  }

  /**
   * Spend an approval on an owner op (console link or release, a house batch) instead of a listing.
   * "spent": now; "same": already spent on exactly this purpose (a retry); "other": spent on a
   * listing or another op; "unknown": no such approval.
   */
  spendApprovalFor(jti: string, purpose: string): SpendResult {
    const rec = this.state.approvals[approvalKey(jti)];
    if (!rec) return "unknown";
    if (rec.log_h !== undefined) return "other";
    if (rec.used_for !== undefined) return rec.used_for === purpose ? "same" : "other";
    rec.used_for = purpose;
    this.write();
    return "spent";
  }

  /** Remember what a spent approval's publish answered, so a retry answers the same. */
  setApprovalResult(jti: string, result: PublishResult): void {
    const rec = this.state.approvals[approvalKey(jti)];
    if (!rec) return;
    rec.result = result;
    this.write();
  }

  /** What an earlier publish of this log answered, if this bridge made it. */
  resultForLog(logH: string): PublishResult | undefined {
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

  // ---- Hedera: payout accounts (data/payto.json) -------------------------------------------

  private loadPayto(): void {
    let stamp = "";
    try {
      const st = statSync(this.paytoFile);
      stamp = `${st.mtimeMs}:${st.size}`;
    } catch {
      stamp = "none";
    }
    if (stamp === this.paytoStamp) return;
    this.paytoStamp = stamp;
    if (stamp === "none") {
      this.payto = {};
      return;
    }
    try {
      const parsed = JSON.parse(readFileSync(this.paytoFile, "utf8")) as Record<string, { account: string; at: number }>;
      this.payto = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch {
      // A half-written file: keep the last good copy and read it again next time.
      this.paytoStamp = "";
    }
  }

  /** The Hedera account registered for this book's sales, if any. Re-reads payto.json when it changed. */
  paytoFor(book: string): string | undefined {
    this.loadPayto();
    const rec = this.payto[book];
    return rec && typeof rec.account === "string" ? rec.account : undefined;
  }

  /** Register (or with null, remove) a book's payout account. Only `npm run hedera:payto` calls this. */
  setPayto(book: string, account: string | null, nowS: number): void {
    this.paytoStamp = "";
    this.loadPayto();
    const next = { ...this.payto };
    if (account === null) delete next[book];
    else next[book] = { account, at: nowS };
    const tmp = `${this.paytoFile}.tmp`;
    writeFileSync(tmp, JSON.stringify(next, null, 1));
    renameSync(tmp, this.paytoFile);
    this.payto = next;
    this.paytoStamp = "";
  }

  // ---- Hedera: LISTING messages ------------------------------------------------------------

  hcsListingFor(jti: string): HcsListingRecord | undefined {
    return this.state.hcsListings[approvalKey(jti)];
  }

  /** Remember the LISTING's transaction once a node accepted it, and later its sequence number. */
  setHcsListing(jti: string, rec: HcsListingRecord): void {
    this.state.hcsListings[approvalKey(jti)] = { ...rec };
    this.write();
  }

  // ---- Hedera: PB's purchases --------------------------------------------------------------

  purchaseFor(key: string): PurchaseRecord | undefined {
    return this.state.purchases[key];
  }

  purchaseById(id: string): { key: string; record: PurchaseRecord } | undefined {
    for (const [key, record] of Object.entries(this.state.purchases)) if (record.id === id) return { key, record };
    return undefined;
  }

  /** Cents reserved or settled on `day`, by one buyer book or (no buyer) across all books. */
  spentOn(day: string, buyer?: string): number {
    let sum = 0;
    for (const p of Object.values(this.state.purchases)) {
      if (p.day !== day || p.state === "released") continue;
      if (buyer !== undefined && p.buyer !== buyer) continue;
      sum += p.price_c;
    }
    return sum;
  }

  /** Cents reserved (not yet settled) across all books, on any day: money that may still leave. */
  inFlightC(exceptKey?: string): number {
    let sum = 0;
    for (const [k, p] of Object.entries(this.state.purchases)) if (p.state === "reserved" && k !== exceptKey) sum += p.price_c;
    return sum;
  }

  /**
   * The caps check and the reservation in one synchronous step, so two consoles can never overspend
   * together. A key already settled answers its record; one still reserved answers it as in flight.
   */
  reservePurchase(key: string, rec: PurchaseRecord, caps: PurchaseCaps): ReserveResult {
    const held = this.state.purchases[key];
    if (held?.state === "settled") return { ok: false, why: "settled", record: held };
    if (held?.state === "reserved") return { ok: false, why: "in_flight", record: held };
    if (this.spentOn(rec.day, rec.buyer) + rec.price_c > caps.bookDayC) return { ok: false, why: "book_cap" };
    if (this.spentOn(rec.day) + rec.price_c > caps.agentDayC) return { ok: false, why: "agent_cap" };
    this.state.purchases[key] = { ...rec, state: "reserved" };
    this.write();
    return { ok: true };
  }

  /** The payment's transaction id, recorded before the payment is sent. */
  notePurchaseTx(key: string, tx: string): void {
    const p = this.state.purchases[key];
    if (!p) return;
    p.tx = tx;
    this.write();
  }

  settlePurchase(key: string, receipt: string, late: boolean): void {
    const p = this.state.purchases[key];
    if (!p) return;
    p.state = "settled";
    p.receipt = receipt;
    p.late = late;
    this.write();
  }

  /** INTENT's and RECEIPT's places on the topic, as they become known (the chain ids the console shows). */
  notePurchaseMessages(key: string, m: { intent_tx?: string; intent_seq?: number; receipt_msg_tx?: string; receipt_msg_seq?: number }): void {
    const p = this.state.purchases[key];
    if (!p) return;
    for (const [k, v] of Object.entries(m)) if (v !== undefined) (p as unknown as Record<string, unknown>)[k] = v;
    this.write();
  }

  /** Nothing was paid: the reservation stops counting against the caps. */
  releasePurchase(key: string): void {
    const p = this.state.purchases[key];
    if (!p || p.state !== "reserved") return;
    p.state = "released";
    this.write();
  }

  // ---- Hedera: sales through the paywall ---------------------------------------------------

  saleFor(tx: string): SaleRecord | undefined {
    return this.state.sales[tx];
  }

  /** Record a settled sale once; a second call for the same transaction keeps the first. */
  recordSale(tx: string, sale: Omit<SaleRecord, "n">): SaleRecord {
    const held = this.state.sales[tx];
    if (held) return held;
    this.state.saleSeq += 1;
    const rec: SaleRecord = { ...sale, run: sale.run.toLowerCase(), listing: sale.listing.toLowerCase(), n: this.state.saleSeq };
    this.state.sales[tx] = rec;
    this.write();
    return rec;
  }

  /** PB names the buyer's book on a sale it paid for. */
  noteSaleBuyer(tx: string, buyer: string): void {
    const s = this.state.sales[tx];
    if (!s || s.buyer === buyer) return;
    s.buyer = buyer;
    this.write();
  }

  /** One seller's sales after counter `after`, oldest first. */
  salesFor(seller: string, after = 0): Array<SaleRecord & { tx: string }> {
    return Object.entries(this.state.sales)
      .filter(([, s]) => s.seller === seller && s.n > after)
      .map(([tx, s]) => ({ ...s, tx }))
      .sort((a, b) => a.n - b.n);
  }

  // ---- consoles: one console, one person ---------------------------------------------------

  consoleFor(key: string): ConsoleRecord | undefined {
    return this.state.consoles[key];
  }

  /** The console with this tag, and its key. */
  consoleByTag(tag: string): { key: string; record: ConsoleRecord } | undefined {
    for (const [key, record] of Object.entries(this.state.consoles)) if (record.tag === tag) return { key, record };
    return undefined;
  }

  /** Every tag in use (a new console's tag must differ from all of them). */
  consoleTags(): Set<string> {
    return new Set(Object.values(this.state.consoles).map((c) => c.tag));
  }

  /** Register an unseen console as unbound; an existing one is answered as it is. */
  registerConsole(key: string, tag: string, nowS: number): ConsoleRecord {
    const held = this.state.consoles[key];
    if (held) return held;
    const rec: ConsoleRecord = { tag, book: null, state: "unbound", by: null, at: nowS };
    this.state.consoles[key] = rec;
    this.write();
    return rec;
  }

  /**
   * Change a console's binding (the caller has checked the rules). `wallet`: the approved wallet
   * (a link names it), null to clear it (a release); absent leaves it as it is.
   */
  setConsole(key: string, change: Pick<ConsoleRecord, "book" | "state" | "by"> & { wallet?: string | null }, nowS: number): ConsoleRecord | undefined {
    const rec = this.state.consoles[key];
    if (!rec) return undefined;
    rec.book = change.book;
    rec.state = change.state;
    rec.by = change.by;
    if (change.wallet === null) delete rec.wallet;
    else if (change.wallet !== undefined) rec.wallet = change.wallet.toLowerCase();
    rec.at = nowS;
    this.write();
    return rec;
  }

  /** The wallet a console reports (lowercased). True when it changed. */
  reportConsoleWallet(key: string, wallet: string): boolean {
    const rec = this.state.consoles[key];
    const w = wallet.toLowerCase();
    if (!rec || rec.wallet_reported === w) return false;
    rec.wallet_reported = w;
    this.write();
    return true;
  }

  /** The approved wallets of the consoles bound to this book, each once: whose runs may be stamped for it. */
  consoleWalletsFor(book: string): string[] {
    const out = new Set<string>();
    for (const c of Object.values(this.state.consoles)) if (c.state === "bound" && c.book === book && c.wallet) out.add(c.wallet);
    return [...out];
  }

  // ---- the house's BOT batches ---------------------------------------------------------------

  houseBatch(batch: string): HouseBatchRecord | undefined {
    return this.state.house.batches[batch];
  }

  /** A batch staged for the first time takes the next letter (A, B, ... Z, AA, AB, ...); a known one keeps its own. */
  stageHouseBatch(batch: string, game: string, logHs: string[], nowS: number, labelsFor: (letter: string) => string[]): HouseBatchRecord {
    const held = this.state.house.batches[batch];
    if (held) return held;
    const letter = batchLetter(this.state.house.letters);
    this.state.house.letters += 1;
    const rec: HouseBatchRecord = { letter, game, labels: labelsFor(letter), log_hs: [...logHs], status: "staged", at: nowS };
    this.state.house.batches[batch] = rec;
    this.write();
    return rec;
  }

  updateHouseBatch(batch: string, change: Partial<Pick<HouseBatchRecord, "status" | "hcs" | "result">>): void {
    const rec = this.state.house.batches[batch];
    if (!rec) return;
    Object.assign(rec, change);
    this.write();
  }
}

/** The n-th batch letter, from 0: A..Z, then AA..ZZ. */
export function batchLetter(n: number): string {
  const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  if (n < 26) return A[n];
  const m = n - 26;
  return `${A[Math.floor(m / 26) % 26]}${A[m % 26]}`;
}

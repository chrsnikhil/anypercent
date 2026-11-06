/**
 * PB, the coach agent: buys the ghost the board names over x402 and pays the seller's own Hedera
 * account directly, in testnet USDC, with no approval step (spec: The x402 purchase). The guards are
 * plain code next to the key, outside any model; none of them reads model output.
 *
 *   POST /hedera/buy {book, game, seller, listing, run, log_h, frames, you_frames, price_c,
 *                     console?, scout?}
 *     -> {id: "p-3f9c0a1b", expires_s: 240}; a repeat for the same (book, game, seller, run) answers
 *        the same id, or a done job's result
 *   GET  /hedera/buy/{id} -> {stage: "guard"|"pay"|"settle"|"done", ok, failure, data}
 *        ok: data {receipt: "0.0.FEEPAYER@S.N", hashscan, late, intent: {seq, tx, hashscan},
 *                  receipt_msg: {seq, tx, hashscan} | null}; it keeps answering after done, and
 *                  intent.seq and receipt_msg fill in as their receipts come back
 *        buy_changed: data {now_price: "gone" | "0.25 USDC"}
 *        buy_suspended: data {why: own_book | run_changed | no_pay_to | cannot_receive | payto_402 |
 *                  not_for_sale | not_house | console_not_linked}
 *
 * The seller is a record book, or a BOT label of the house (BOT-A2): a label listing must name that
 * label, be open tier (`human` false) and pay HEDERA_HOUSE_ID, else not_house. With a `console`, the
 * console must be bound to the buying book (one console, one person), else console_not_linked;
 * without one (the hedera:agent CLI) the purchase runs as before and says so in the log. A `scout`
 * id that matches a held scout pick of this very purchase puts the scout's model, laps and reason
 * on INTENT; any other is ignored. The scout only ever chose the ghost: every guard below runs on
 * the purchase as it is, and no model output reaches one.
 *
 * One job, in order:
 *   guard   the buyer book; not its own book; the listing on Arkiv (live, the checker's, the
 *           console's seller, its price); the run (live, the checker's, the same log_h, log_enc);
 *           pay_to present and able to take USDC (mirror, cached 10 min); the caps (per purchase, per
 *           book per day, per agent per day, the agent's USDC balance, cached 30 s); then a
 *           reservation that counts against the caps at once
 *   pay     INTENT on the market topic (a node must accept it before anything is signed); the
 *           unpaid GET and its 402, checked against the listing (one exact entry on hedera:testnet,
 *           USDC, payTo = the listing's pay_to, the listed amount, the facilitator's fee payer); the
 *           payment built and signed (its transaction id recorded first)
 *   settle  the paid GET; the 200 checked (success, network, the fee payer's transaction, the
 *           log's hash); or, when settle gave no definite answer, the agent's own transaction id
 *           watched on the mirror until its 120 s valid window has passed plus 15 s
 *   done    then, in the background, the mirror is asked for both token-transfer rows (60 s) and a
 *           RECEIPT goes to the topic
 *
 * Failures are the handler's own: buy_budget, buy_changed, buy_suspended, buy_down. Nothing is signed
 * on any refusal before the payment step. Logged: purchase ids, books, accounts, transaction ids,
 * HashScan links. Never a payment header or a key.
 */
import { randomBytes } from "node:crypto";
import { BOOK_RE } from "../approvals.js";
import type { ArkivPort } from "../arkiv/client.js";
import { HOUSE_LABEL_RE } from "../config.js";
import { CONSOLE_ID_RE } from "../consoles.js";
import { fmtTime, priceText } from "../arkiv/publish.js";
import { KEY_RE, LOG_H_RE } from "../arkiv/queries.js";
import { GAME_IDS } from "../arkiv/schema.js";
import { purchaseKey, type PurchaseRecord, type Store } from "../store.js";
import { intentMessage, receiptMessage, seqNumber, type IntentScout } from "./messages.js";
import { hashscan, shortSdkError, transfersMatch, txAt, txValidStartMs, type HederaPort, type MirrorPort } from "./net.js";
import { decCents, sha256Hex } from "./resource.js";
import { atomicText, centsToAtomic, MAX_TIMEOUT_S, type BuiltPayment, type Facilitators, type PaymentBuilder, type PaymentRequired } from "./x402.js";

export type BuyFailure = "buy_budget" | "buy_changed" | "buy_suspended" | "buy_down";

/** Why a guard said buy_suspended (data.why). */
export type SuspendWhy = "own_book" | "run_changed" | "no_pay_to" | "cannot_receive" | "payto_402" | "not_for_sale" | "not_house" | "console_not_linked";

export const SCOUT_ID_RE = /^s-[0-9a-f]{8}$/;

/** A scout pick held by the scout service, as INTENT records it. */
export interface HeldScout {
  buyer: string;
  game: string;
  /** The listing the scout picked. */
  listing: string;
  intent: Omit<IntentScout, "id">;
}

export interface BuyView {
  stage: "guard" | "pay" | "settle" | "done";
  ok: boolean | null;
  failure: BuyFailure | null;
  data: Record<string, unknown>;
}

export class BuyRefused extends Error {
  constructor(public readonly status: number, public readonly error: string) {
    super(error);
  }
}

export interface BuyBody {
  book: string;
  game: string;
  seller: string;
  listing: string;
  run: string;
  log_h: string;
  /** The target's time, in frames. */
  frames: number;
  /** YOU's best, in frames; null when YOU has none. */
  you_frames: number | null;
  price_c: number;
  /** The console's id (consoles.ts); absent: a terminal purchase. */
  console?: string;
  /** The scout pick this purchase follows, if any. */
  scout?: string;
}

const isFrames = (v: unknown) => typeof v === "number" && Number.isInteger(v) && v >= 1 && v <= 0xffffffff;

export function parseBuyBody(raw: Record<string, unknown>): BuyBody {
  const bad = () => new BuyRefused(400, "bad_body");
  const { book, game, seller, listing, run, log_h, frames, you_frames, price_c, console: consoleId, scout } = raw;
  if (typeof book !== "string" || !BOOK_RE.test(book)) throw bad();
  if (typeof seller !== "string" || !(BOOK_RE.test(seller) || HOUSE_LABEL_RE.test(seller))) throw bad();
  if (consoleId !== undefined && consoleId !== null && (typeof consoleId !== "string" || !CONSOLE_ID_RE.test(consoleId))) throw bad();
  if (scout !== undefined && scout !== null && (typeof scout !== "string" || !SCOUT_ID_RE.test(scout))) throw bad();
  if (typeof game !== "string" || !GAME_IDS.includes(game)) throw bad();
  if (typeof listing !== "string" || !KEY_RE.test(listing)) throw bad();
  if (typeof run !== "string" || !KEY_RE.test(run)) throw bad();
  if (typeof log_h !== "string" || !LOG_H_RE.test(log_h)) throw bad();
  if (!isFrames(frames)) throw bad();
  if (you_frames !== undefined && you_frames !== null && !isFrames(you_frames)) throw bad();
  if (typeof price_c !== "number" || !Number.isInteger(price_c) || price_c < 0 || price_c > 1_000_000) throw bad();
  return {
    book,
    game,
    seller,
    listing: listing.toLowerCase(),
    run: run.toLowerCase(),
    log_h,
    frames: frames as number,
    you_frames: typeof you_frames === "number" ? you_frames : null,
    price_c,
    ...(typeof consoleId === "string" ? { console: consoleId } : {}),
    ...(typeof scout === "string" ? { scout } : {}),
  };
}

/** The service's local day, YYYY-MM-DD (as the launcher's ledger counts it). */
export function localDay(ms: number): string {
  const d = new Date(ms);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;
}

export type BuyGate = () => null | "hedera_not_configured" | "hedera_unavailable";

export interface AgentOptions {
  store: Store;
  arkiv: Pick<ArkivPort, "getListing" | "getRun">;
  mirror: MirrorPort;
  hedera: HederaPort;
  facilitators: Facilitators;
  builder: PaymentBuilder;
  /** HEDERA_TOPIC_ID, HEDERA_USDC, the CAIP-2 network, HEDERA_AGENT_ID, HEDERA_RESOURCE_BASE. */
  topic: string;
  usdc: string;
  network: string;
  agentId: string;
  resourceBase: string;
  /** ARKIV_GHOST_PRICE_C: the one listed price. */
  priceC: number;
  maxPriceC: number;
  bookDayC: number;
  agentDayC: number;
  /** X402_FEE_PAYERS (empty: any fee payer the facilitator names). */
  feePayersPin: string[];
  gate: BuyGate;
  /** HEDERA_HOUSE_ID: the only account a BOT (label) listing may pay ("" = none). */
  houseId?: string;
  /** One console, one person: may this console spend from this book? */
  consoles?: { canSpend(id: string, book: string): { ok: boolean; tag: string | null } } | null;
  /** The scout's held picks, for INTENT. */
  scouts?: { held(id: string): HeldScout | undefined } | null;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  log?: (line: string) => void;
  intentTimeoutMs?: number;
  askTimeoutMs?: number;
  payTimeoutMs?: number;
  pollMs?: number;
  graceMs?: number;
  receiptWatchMs?: number;
  /** The console's pay budget: a receipt past it is `late`. */
  consoleBudgetMs?: number;
  holdMs?: number;
  assocTtlMs?: number;
  balanceTtlMs?: number;
}

export const BUY_EXPIRES_S = 240;

interface Job {
  id: string;
  key: string;
  body: BuyBody;
  view: BuyView;
  createdMs: number;
  running: boolean;
}

/** Why a job stops, carried out of the pipeline. */
class Stop extends Error {
  constructor(public readonly failure: BuyFailure, public readonly why: string, public readonly data: Record<string, unknown> = {}) {
    super(why);
  }
}

/** A guard's buy_suspended, with its `why` code in data. */
const suspended = (code: SuspendWhy, why: string) => new Stop("buy_suspended", why, { why: code });

interface Guarded {
  listingFrames: number;
  pay_to: string;
  price_c: number;
  log_h: string;
}

async function timed<T>(p: Promise<T>, ms: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const t = new Promise<never>((_, no) => {
    timer = setTimeout(() => no(new Error("timeout")), ms);
  });
  try {
    return await Promise.race([p, t]);
  } finally {
    clearTimeout(timer);
  }
}

export class Agent {
  private readonly jobs = new Map<string, Job>();
  private readonly byKey = new Map<string, string>();
  private readonly assoc = new Map<string, { ok: boolean; at: number }>();
  private balance: { value: bigint | null; at: number } | null = null;
  private readonly now: () => number;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly t: Required<Pick<AgentOptions, "intentTimeoutMs" | "askTimeoutMs" | "payTimeoutMs" | "pollMs" | "graceMs" | "receiptWatchMs" | "consoleBudgetMs" | "holdMs" | "assocTtlMs" | "balanceTtlMs">>;
  /** Background RECEIPT work, so tests (and shutdown) can wait for it. */
  readonly background = new Set<Promise<void>>();

  constructor(private readonly opts: AgentOptions) {
    this.now = opts.now ?? Date.now;
    this.sleep = opts.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.t = {
      intentTimeoutMs: opts.intentTimeoutMs ?? 5000,
      askTimeoutMs: opts.askTimeoutMs ?? 8000,
      payTimeoutMs: opts.payTimeoutMs ?? 60_000,
      pollMs: opts.pollMs ?? 2000,
      graceMs: opts.graceMs ?? 15_000,
      receiptWatchMs: opts.receiptWatchMs ?? 60_000,
      consoleBudgetMs: opts.consoleBudgetMs ?? 8000,
      holdMs: opts.holdMs ?? 3_600_000,
      assocTtlMs: opts.assocTtlMs ?? 600_000,
      balanceTtlMs: opts.balanceTtlMs ?? 30_000,
    };
  }

  // ---- jobs ------------------------------------------------------------------------------

  start(raw: Record<string, unknown>): { id: string; expires_s: number } {
    const body = parseBuyBody(raw);
    const nowMs = this.now();
    this.prune(nowMs);
    const key = purchaseKey(body.book, body.game, body.seller, body.run);
    const held = this.jobs.get(this.byKey.get(key) ?? "");
    if (held && !(held.view.stage === "done" && held.view.ok === false)) return { id: held.id, expires_s: BUY_EXPIRES_S };

    const prior = this.opts.store.purchaseFor(key);
    if (!held && prior?.state === "settled" && prior.receipt) {
      const job: Job = { id: prior.id, key, body, view: this.okView(key, prior.receipt, prior.late ?? false), createdMs: nowMs, running: false };
      this.jobs.set(job.id, job);
      this.byKey.set(key, job.id);
      return { id: job.id, expires_s: BUY_EXPIRES_S };
    }
    const gate = this.opts.gate();
    if (gate) throw new BuyRefused(503, gate);

    const id = held?.id ?? (prior?.state === "reserved" ? prior.id : this.newId());
    const job: Job = held ?? { id, key, body, view: this.guarding(), createdMs: nowMs, running: false };
    job.body = body;
    job.view = this.guarding();
    job.createdMs = nowMs;
    this.jobs.set(job.id, job);
    this.byKey.set(key, job.id);
    job.running = true;
    this.run(job)
      .catch((err: unknown) => {
        if (err instanceof Stop) return this.fail(job, err.failure, err.why, err.data);
        this.opts.store.releasePurchase(job.key);
        return this.fail(job, "buy_down", `internal: ${(err as Error)?.name ?? "error"}`);
      })
      .finally(() => {
        job.running = false;
      });
    return { id: job.id, expires_s: BUY_EXPIRES_S };
  }

  view(id: string): BuyView | undefined {
    return this.jobs.get(id)?.view;
  }

  /** The job for a key, if one ran here (scripts). */
  jobFor(key: string): { id: string; view: BuyView } | undefined {
    const j = this.jobs.get(this.byKey.get(key) ?? "");
    return j ? { id: j.id, view: j.view } : undefined;
  }

  private newId(): string {
    for (;;) {
      const id = `p-${randomBytes(4).toString("hex")}`;
      if (!this.jobs.has(id) && !this.opts.store.purchaseById(id)) return id;
    }
  }

  private guarding(): BuyView {
    return { stage: "guard", ok: null, failure: null, data: {} };
  }

  /** The done view, with INTENT's and RECEIPT's places on the topic as far as they are known. */
  private okView(key: string, receipt: string, late: boolean): BuyView {
    const p = this.opts.store.purchaseFor(key);
    const intent = p?.intent_tx ? { seq: p.intent_seq ?? null, tx: p.intent_tx, hashscan: hashscan.tx(p.intent_tx) } : null;
    const receiptMsg = p?.receipt_msg_tx ? { seq: p.receipt_msg_seq ?? null, tx: p.receipt_msg_tx, hashscan: hashscan.tx(p.receipt_msg_tx) } : null;
    return { stage: "done", ok: true, failure: null, data: { receipt, hashscan: hashscan.tx(receipt), late, intent, receipt_msg: receiptMsg } };
  }

  /** A message's place came back after done: the view answers it from now on. */
  private refresh(job: Job): void {
    if (job.view.stage === "done" && job.view.ok === true) {
      job.view = this.okView(job.key, String(job.view.data.receipt), job.view.data.late === true);
    }
  }

  private what(b: BuyBody): string {
    return `${b.book} buys ${b.seller}'s ${b.game} ${fmtTime(b.frames)}`;
  }

  private fail(job: Job, failure: BuyFailure, why: string, data: Record<string, unknown> = {}): void {
    if (job.view.stage === "done") return;
    job.view = { stage: "done", ok: false, failure, data };
    this.opts.log?.(`PB ${job.id} ${this.what(job.body)}: ${failure} (${why})`);
  }

  private stage(job: Job, stage: "pay" | "settle"): void {
    if (job.view.stage !== "done") job.view = { stage, ok: null, failure: null, data: {} };
  }

  // ---- mirror reads, cached ----------------------------------------------------------------

  /** Can this account take USDC (the mirror, cached 10 min)? The scout reads the same cache. */
  async canReceive(account: string): Promise<boolean> {
    const hit = this.assoc.get(account);
    if (hit && this.now() - hit.at < this.t.assocTtlMs) return hit.ok;
    const ok = await this.opts.mirror.associated(account, this.opts.usdc);
    this.assoc.set(account, { ok, at: this.now() });
    return ok;
  }

  /** The agent's USDC (the mirror, cached 30 s). */
  async agentUsdc(): Promise<bigint | null> {
    if (this.balance && this.now() - this.balance.at < this.t.balanceTtlMs) return this.balance.value;
    const value = await this.opts.mirror.tokenBalance(this.opts.agentId, this.opts.usdc);
    this.balance = { value, at: this.now() };
    return value;
  }

  // ---- the pipeline ----------------------------------------------------------------------

  private async run(job: Job): Promise<void> {
    const prior = this.opts.store.purchaseFor(job.key);
    if (prior?.state === "reserved") {
      // A reservation from before a restart: settle what it paid, or let it go.
      const receipt = prior.tx ? await this.watch(prior.tx, prior.pay_to, BigInt(centsToAtomic(prior.price_c)), prior.tx) : null;
      if (receipt) return this.succeed(job, receipt, prior.pay_to, prior.price_c, null, true);
      this.opts.store.releasePurchase(job.key);
    }

    const g = await this.guard(job);
    const b = job.body;
    const day = localDay(this.now());
    const rec: PurchaseRecord = {
      id: job.id,
      buyer: b.book,
      game: b.game,
      seller: b.seller,
      run: b.run,
      listing: b.listing,
      pay_to: g.pay_to,
      price_c: g.price_c,
      day,
      state: "reserved",
      at: Math.floor(this.now() / 1000),
    };
    const caps = { bookDayC: this.opts.bookDayC, agentDayC: this.opts.agentDayC };
    const r = this.opts.store.reservePurchase(job.key, rec, caps);
    if (!r.ok) {
      if (r.why === "settled" && r.record.receipt) {
        job.view = this.okView(job.key, r.record.receipt, r.record.late ?? false);
        this.opts.log?.(`PB ${job.id} ${this.what(b)}: already bought, receipt ${r.record.receipt} (nothing paid)`);
        return;
      }
      throw new Stop("buy_budget", r.why === "book_cap" ? "the book's daily cap" : r.why === "agent_cap" ? "the agent's daily cap" : "already in flight");
    }

    try {
      await this.pay(job, g);
    } catch (err) {
      if (err instanceof Stop && job.view.stage !== "done") this.opts.store.releasePurchase(job.key);
      throw err;
    }
  }

  /** Every guard before anything is signed. Throws Stop. */
  private async guard(job: Job): Promise<Guarded> {
    const b = job.body;
    const { store, arkiv } = this.opts;
    if (!store.recordForBook(b.book)) throw new Stop("buy_budget", "the buyer book was not issued here");
    if (b.console !== undefined) {
      const c = this.opts.consoles?.canSpend(b.console, b.book) ?? { ok: false, tag: null };
      if (!c.ok) throw suspended("console_not_linked", `console ${c.tag ?? "?"} is not linked to ${b.book}`);
    }
    if (b.seller === b.book) throw suspended("own_book", "that is the buyer's own book");

    let listing;
    try {
      listing = await arkiv.getListing(b.listing);
    } catch {
      throw new Stop("buy_down", "Arkiv did not answer");
    }
    if (!listing || listing.game !== b.game) throw new Stop("buy_changed", "the listing is gone", { now_price: "gone" });
    if (listing.book === undefined) {
      // The house's BOT listing: its label, open tier, paying the house account.
      if (listing.label !== b.seller) throw new Stop("buy_changed", "the listing is gone", { now_price: "gone" });
      if (listing.human !== false || !this.opts.houseId || listing.pay_to !== this.opts.houseId) {
        throw suspended("not_house", `a BOT listing must pay the house (it names ${listing.pay_to ?? "no account"})`);
      }
    } else {
      if (listing.book !== b.seller) throw new Stop("buy_changed", "the listing is gone", { now_price: "gone" });
      if (listing.book === b.book) throw suspended("own_book", "that is the buyer's own book");
    }
    const listedC = decCents(listing.price);
    if (!Number.isInteger(listedC)) throw new Stop("buy_changed", "the listing's price is unreadable", { now_price: "gone" });
    if (listedC !== b.price_c || listedC !== this.opts.priceC) {
      throw new Stop("buy_changed", `listed at ${priceText(listedC)} USDC`, { now_price: `${priceText(listedC)} USDC` });
    }

    let run;
    try {
      run = await arkiv.getRun(listing.run, true);
    } catch {
      throw new Stop("buy_down", "Arkiv did not answer");
    }
    if (!run || run.key !== b.run || listing.run !== b.run || run.game !== b.game || run.log_h !== listing.log_h || listing.log_h !== b.log_h || !run.log_enc) {
      throw suspended("run_changed", "the run is gone or changed");
    }

    if (!listing.pay_to) throw suspended("no_pay_to", "the listing names no Hedera account (not for sale)");
    let receivable: boolean;
    try {
      receivable = await this.canReceive(listing.pay_to);
    } catch {
      throw new Stop("buy_down", "the mirror node did not answer");
    }
    if (!receivable) throw suspended("cannot_receive", `${listing.pay_to} cannot take USDC (not associated, no free slot)`);

    if (b.price_c > this.opts.maxPriceC) throw new Stop("buy_budget", "over the per-purchase cap");
    const day = localDay(this.now());
    if (store.spentOn(day, b.book) + b.price_c > this.opts.bookDayC) throw new Stop("buy_budget", "the book's daily cap");
    if (store.spentOn(day) + b.price_c > this.opts.agentDayC) throw new Stop("buy_budget", "the agent's daily cap");
    let held: bigint | null;
    try {
      held = await this.agentUsdc();
    } catch {
      throw new Stop("buy_down", "the mirror node did not answer");
    }
    const need = BigInt(centsToAtomic(b.price_c)) + BigInt(centsToAtomic(store.inFlightC(job.key)));
    if (held === null || held < need) throw new Stop("buy_budget", "the agent is out of USDC");

    return { listingFrames: Number(listing.frames), pay_to: listing.pay_to, price_c: listedC, log_h: listing.log_h };
  }

  private async pay(job: Job, g: Guarded): Promise<void> {
    const b = job.body;
    const o = this.opts;
    this.stage(job, "pay");
    // The console's 8 s pay budget runs from its start, so lateness is measured from the job's.
    const startedMs = job.createdMs;
    const amount = centsToAtomic(g.price_c);
    const day = localDay(this.now());

    // INTENT: a node must accept it before anything is signed.
    const left = Math.max(0, o.bookDayC - o.store.spentOn(day, b.book));
    let intentSeq: Promise<number | null> = Promise.resolve(null);
    let intentTx: string;
    const scout = this.scoutFor(job);
    try {
      const bytes = intentMessage({
        id: job.id,
        buyer: b.book,
        seller: b.seller,
        game: b.game,
        listing: b.listing,
        run: b.run,
        log_h: g.log_h,
        pay_to: g.pay_to,
        amount: priceText(g.price_c),
        asset: o.usdc,
        why: { you: b.you_frames, target: g.listingFrames },
        ...(scout ? { scout } : {}),
        left_today: priceText(left),
      });
      const accepted = await timed(o.hedera.submit(o.topic, bytes), this.t.intentTimeoutMs);
      intentTx = accepted.tx;
      o.store.notePurchaseMessages(job.key, { intent_tx: intentTx });
      intentSeq = accepted.receipt.then((r) => seqNumber(r.seq)).catch(() => null);
      void intentSeq.then((seq) => {
        if (seq === null) return;
        o.store.notePurchaseMessages(job.key, { intent_seq: seq });
        this.refresh(job);
      });
    } catch (err) {
      throw new Stop("buy_down", `INTENT not accepted: ${shortSdkError(err)}`);
    }
    const why = scout
      ? `the scout's pick, by ${scout.by === "model" ? scout.model : "the rule"}`
      : b.you_frames === null
        ? `no time yet; ${b.seller} at ${fmtTime(g.listingFrames)}`
        : `YOU ${fmtTime(b.you_frames)}, ${b.seller} ${fmtTime(g.listingFrames)} just ahead`;
    const where = b.console !== undefined ? `console ${this.opts.consoles?.canSpend(b.console, b.book).tag ?? "?"}` : "no console";
    o.log?.(`PB ${job.id} INTENT (${why}; ${where}): ${b.book} pays ${priceText(g.price_c)} USDC to ${g.pay_to}, tx ${intentTx} ${hashscan.tx(intentTx)}`);

    // Find the endpoint and ask unpaid.
    const url = `${o.resourceBase}/x402/ghost/${b.listing}`;
    let res: Response;
    try {
      res = await fetch(url, { signal: AbortSignal.timeout(this.t.askTimeoutMs) });
    } catch {
      throw new Stop("buy_down", "the paywall did not answer");
    }
    if (res.status === 404) {
      await res.body?.cancel();
      throw suspended("not_for_sale", "the paywall says it is not for sale");
    }
    if (res.status !== 402) {
      await res.body?.cancel();
      throw new Stop("buy_down", `the paywall answered ${res.status}`);
    }
    let pr: PaymentRequired;
    try {
      const body402 = await res.json().catch(() => ({}));
      pr = o.builder.read402((h) => res.headers.get(h), body402);
    } catch {
      throw new Stop("buy_down", "the 402 is unreadable");
    }

    // Check the 402 against what PB read from Arkiv itself.
    if (!Array.isArray(pr.accepts) || pr.accepts.length !== 1) throw new Stop("buy_down", "the 402 must offer exactly one way to pay");
    const a = pr.accepts[0];
    if (a.scheme !== "exact" || a.network !== o.network || a.asset !== o.usdc || !(a.maxTimeoutSeconds > 0 && a.maxTimeoutSeconds <= 300)) {
      throw new Stop("buy_down", "the 402 is not exact USDC on hedera:testnet within 300 s");
    }
    if (a.payTo !== g.pay_to) {
      o.log?.(`PB ${job.id} REFUSED payTo: the 402 names ${a.payTo}, the listing pays ${g.pay_to}; nothing signed`);
      throw suspended("payto_402", "REFUSED payTo");
    }
    if (a.amount !== amount) throw new Stop("buy_changed", `the 402 asks ${atomicText(a.amount)} USDC`, { now_price: `${atomicText(a.amount)} USDC` });
    const fp = typeof a.extra?.feePayer === "string" ? a.extra.feePayer : "";
    const cur = o.facilitators.current();
    if (!cur || fp !== cur.feePayer || (o.feePayersPin.length > 0 && !o.feePayersPin.includes(fp))) {
      throw new Stop("buy_down", `fee payer ${fp || "none"} is not the facilitator's`);
    }

    // Sign. The transaction id is recorded before the payment leaves.
    let built: BuiltPayment;
    try {
      built = await o.builder.build({ ...pr, accepts: [a] });
    } catch (err) {
      throw new Stop("buy_down", `could not build the payment: ${String((err as Error)?.message ?? "error").split("\n")[0].slice(0, 120)}`);
    }
    if (built.facts.feePayer !== fp || built.facts.payer !== o.agentId) throw new Stop("buy_down", "the built payment is not the agent's on that fee payer");
    o.store.notePurchaseTx(job.key, built.facts.tx);

    // Pay.
    this.stage(job, "settle");
    const tx = built.facts.tx;
    let paid: Response;
    try {
      paid = await fetch(url, { headers: built.header, signal: AbortSignal.timeout(this.t.payTimeoutMs) });
    } catch {
      return this.settleLater(job, tx, g, startedMs, intentSeq, "the paid request got no answer");
    }
    if (paid.status === 200) {
      const sr = o.builder.settleResponse((h) => paid.headers.get(h));
      const body = (await paid.json().catch(() => null)) as { log?: unknown; log_h?: unknown } | null;
      const log = typeof body?.log === "string" ? Buffer.from(body.log, "base64") : null;
      const settled = sr?.success === true && sr.network === o.network ? txAt(sr.transaction) : null;
      if (settled && settled.startsWith(`${fp}@`) && log && sha256Hex(log) === g.log_h && body?.log_h === g.log_h) {
        return this.succeed(job, settled, g.pay_to, g.price_c, intentSeq, this.now() - startedMs > this.t.consoleBudgetMs);
      }
      o.log?.(`PB ${job.id}: the 200 does not check out (settle response or log hash); asking the mirror for ${tx}`);
      return this.settleLater(job, tx, g, startedMs, intentSeq, "the 200 did not check out");
    }
    const err = (await paid.json().catch(() => ({}))) as { error?: unknown; stage?: unknown };
    if (paid.status === 402 && (err.stage === "check" || err.stage === "verify")) {
      throw new Stop("buy_down", `refused at ${String(err.stage)}: ${String(err.error ?? "?")}`);
    }
    if (paid.status === 404) throw suspended("not_for_sale", "the paywall would not sell this log");
    if (paid.status === 503) throw new Stop("buy_down", "the facilitator was unreachable at /verify");
    return this.settleLater(job, tx, g, startedMs, intentSeq, `settle: ${String(err.error ?? paid.status)}`);
  }

  /** No definite answer: watch the agent's own transaction on the mirror until its window has passed. */
  private async settleLater(job: Job, tx: string, g: Guarded, startedMs: number, intentSeq: Promise<number | null>, why: string): Promise<void> {
    this.opts.log?.(`PB ${job.id}: ${why}; watching ${tx} on the mirror`);
    const receipt = await this.watch(tx, g.pay_to, BigInt(centsToAtomic(g.price_c)), tx);
    if (!receipt) throw new Stop("buy_down", "nothing paid, checked twice (the facilitator and the mirror)");
    return this.succeed(job, receipt, g.pay_to, g.price_c, intentSeq, this.now() - startedMs > this.t.consoleBudgetMs);
  }

  /** The transaction on the mirror: its receipt when it settled with the right transfers, else null. */
  private async watch(tx: string, payTo: string, amount: bigint, label: string): Promise<string | null> {
    const deadline = Math.max(txValidStartMs(tx) ?? this.now(), this.now()) + MAX_TIMEOUT_S * 1000 + this.t.graceMs;
    for (;;) {
      try {
        const m = await this.opts.mirror.transaction(tx);
        if (m) {
          if (m.result === "SUCCESS" && transfersMatch(m, this.opts.usdc, this.opts.agentId, payTo, amount)) return txAt(tx);
          this.opts.log?.(`PB: ${label} is on the mirror as ${m.result}`);
          return null;
        }
      } catch {
        // the mirror did not answer: ask again
      }
      if (this.now() > deadline) return null;
      await this.sleep(this.t.pollMs);
    }
  }

  private succeed(job: Job, receipt: string, payTo: string, priceC: number, intentSeq: Promise<number | null> | null, late: boolean): void {
    const o = this.opts;
    o.store.settlePurchase(job.key, receipt, late);
    o.store.noteSaleBuyer(receipt, job.body.book);
    this.balance = null;
    job.view = this.okView(job.key, receipt, late);
    o.log?.(`PB ${job.id} ${this.what(job.body)}: paid ${priceText(priceC)} USDC to ${payTo}${late ? " (late)" : ""}, tx ${receipt} ${hashscan.tx(receipt)}`);
    const bg = this.postReceipt(job, receipt, payTo, priceC, intentSeq ?? Promise.resolve(null), late).catch(() => undefined);
    this.background.add(bg);
    void bg.finally(() => this.background.delete(bg));
  }

  /** After settlement: both token-transfer rows on the mirror (up to 60 s), then RECEIPT. */
  private async postReceipt(job: Job, tx: string, payTo: string, priceC: number, intentSeq: Promise<number | null>, late: boolean): Promise<void> {
    const o = this.opts;
    const amount = BigInt(centsToAtomic(priceC));
    const until = this.now() + this.t.receiptWatchMs;
    let seen = false;
    for (;;) {
      try {
        const m = await o.mirror.transaction(tx);
        if (m && m.result === "SUCCESS" && transfersMatch(m, o.usdc, o.agentId, payTo, amount)) {
          seen = true;
          break;
        }
      } catch {
        // ask again
      }
      if (this.now() >= until) break;
      await this.sleep(this.t.pollMs);
    }
    o.store.noteSaleBuyer(tx, job.body.book);
    const intent = await Promise.race([intentSeq, this.sleep(5000).then(() => null)]);
    try {
      const bytes = receiptMessage({
        id: job.id,
        intent,
        tx,
        from: o.agentId,
        pay_to: payTo,
        amount: priceText(priceC),
        asset: o.usdc,
        run: job.body.run,
        mirror: seen ? "SUCCESS" : "unseen",
        late,
      });
      const accepted = await timed(o.hedera.submit(o.topic, bytes), this.t.intentTimeoutMs * 2);
      o.store.notePurchaseMessages(job.key, { receipt_msg_tx: accepted.tx });
      this.refresh(job);
      const r = await accepted.receipt.catch(() => null);
      const seq = r ? seqNumber(r.seq) : null;
      if (seq !== null) {
        o.store.notePurchaseMessages(job.key, { receipt_msg_seq: seq });
        this.refresh(job);
      }
      o.log?.(`PB ${job.id} RECEIPT${r ? ` #${r.seq}` : ""} (mirror ${seen ? "SUCCESS" : "unseen"}), tx ${accepted.tx} ${hashscan.tx(accepted.tx)}`);
    } catch (err) {
      o.log?.(`PB ${job.id} RECEIPT not posted: ${shortSdkError(err)}`);
    }
  }

  /** The scout's pick for INTENT, when the body's scout id is a held pick of this very purchase. */
  private scoutFor(job: Job): IntentScout | null {
    const b = job.body;
    if (b.scout === undefined) return null;
    const held = this.opts.scouts?.held(b.scout);
    if (!held || held.buyer !== b.book || held.game !== b.game || held.listing !== b.listing) {
      this.opts.log?.(`PB ${job.id}: scout id ignored (not this purchase)`);
      return null;
    }
    return { id: b.scout, ...held.intent };
  }

  private prune(nowMs: number): void {
    for (const [id, j] of this.jobs) {
      if (!j.running && nowMs - j.createdMs > this.t.holdMs) {
        this.jobs.delete(id);
        if (this.byKey.get(j.key) === id) this.byKey.delete(j.key);
      }
    }
  }
}

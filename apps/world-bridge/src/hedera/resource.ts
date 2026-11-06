/**
 * GET /x402/ghost/{listing}: the x402 paywall on a listed ghost (spec: The x402 purchase, steps 5-11).
 * The same exchange for PB and for any outside x402 client.
 *
 *   unpaid        402, body {"error":"payment_required"}, header PAYMENT-REQUIRED: one `exact`
 *                 requirement on hedera:testnet, payTo = the listing's pay_to, amount = its price
 *                 x 10^6 (USDC), feePayer from the facilitator's /supported
 *   paid          the PAYMENT-SIGNATURE's `accepted` must equal the requirement issued now; /verify;
 *                 the ghost is decrypted and must hash to log_h (a bad log is never sold: 404, no
 *                 settle); /settle by the facilitator whose fee payer the payment names; the sale is
 *                 recorded (store.sales[tx]); 200 {"listing","run","log_h","log"} with PAYMENT-RESPONSE
 *   refused       402 with a fresh PAYMENT-REQUIRED whose `error` is the facilitator's reason, no log;
 *                 the body says at which stage: "check" or "verify" (nothing was submitted) or
 *                 "settle" (the transaction may have been submitted)
 *   not for sale  404 {"error":"not_for_sale"}: the listing or its run is not live, not the
 *                 checker's, has no pay_to, or the run has no log_enc
 *   off           503 {"error":"hedera_not_configured" | "hedera_unavailable"}
 *
 * A settle that failed or did not answer leaves the payment pending: the transaction is watched on
 * the mirror until its 120 s valid window has passed plus 15 s, and the sale is recorded if it shows
 * there with SUCCESS and the right token transfers. A paid request for a transaction already sold
 * for this run answers the log again without settling twice (re-download keyed by the payment's
 * transaction id). Logged: the listing, the payer, the amount, the transaction id and timings. Never
 * a payment header, a key or a log.
 */
import { createHash } from "node:crypto";
import { decryptGhost } from "../arkiv/ghost.js";
import { sellerName, type ArkivPort } from "../arkiv/client.js";
import { fmtTime } from "../arkiv/publish.js";
import { KEY_RE } from "../arkiv/queries.js";
import type { SaleRecord, Store } from "../store.js";
import { hashscan, transfersMatch, txAt, txValidStartMs, type MirrorPort } from "./net.js";
import {
  buildRequirement,
  centsToAtomic,
  atomicText,
  FacilitatorDown,
  headers,
  MAX_TIMEOUT_S,
  paymentFacts,
  paymentRequired,
  sameJson,
  type Facilitators,
  type PaymentPayload,
  type PaymentRequirements,
  type ResourceInfo,
  type SettleResponse,
} from "./x402.js";

/** One listed ghost for sale, as the paywall checked it. */
export interface Offer {
  listing: string;
  run: string;
  log_h: string;
  game: string;
  /** The seller's book, or the house's BOT label. */
  seller: string;
  pay_to: string;
  price_c: number;
  description: string;
  /** The plain log, or null when it does not open. */
  open(): Uint8Array | null;
}

export interface OfferSource {
  /** The offer, or null when not for sale. Throws when the source cannot be read. */
  offer(listing: string): Promise<Offer | null>;
}

/** USDC "0.1" (a dec) -> 10 cents; NaN when not a plain decimal with at most 2 places. */
export function decCents(dec: string): number {
  const m = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(dec);
  if (!m) return Number.NaN;
  return Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0") || "0");
}

export const sha256Hex = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

/**
 * Offers read from Arkiv (Q6 on the listing and on its run, both pinned to the checker), opened with
 * the ghost secret.
 */
export class ArkivOffers implements OfferSource {
  constructor(private readonly arkiv: Pick<ArkivPort, "getListing" | "getRun">, private readonly ghostSecret: string) {}

  async offer(listing: string): Promise<Offer | null> {
    const l = await this.arkiv.getListing(listing);
    if (!l || !l.pay_to) return null;
    const r = await this.arkiv.getRun(l.run, true);
    if (!r || !r.log_enc || r.log_h !== l.log_h || r.game !== l.game) return null;
    const priceC = decCents(l.price);
    if (!Number.isInteger(priceC) || priceC <= 0) return null;
    const sealed = r.log_enc;
    const secret = this.ghostSecret;
    const seller = sellerName(l);
    if (!seller) return null;
    // A house (BOT) listing says so in the paywall's own description.
    const made = l.book === undefined ? " (generated)" : "";
    return {
      listing: l.key,
      run: r.key,
      log_h: l.log_h,
      game: l.game,
      seller,
      pay_to: l.pay_to,
      price_c: priceC,
      description: `Any% ghost: ${r.title ?? l.game} ${fmtTime(Number(l.frames))} by ${seller}${made}`,
      open: () => decryptGhost(secret, r.log_h, sealed),
    };
  }
}

export interface X402Reply {
  status: number;
  headers: Record<string, string>;
  body: Record<string, unknown>;
}

export type PaywallGate = () => null | "hedera_not_configured" | "hedera_unavailable";

export interface ResourceOptions {
  source: OfferSource;
  facilitators: Facilitators;
  store: Pick<Store, "saleFor" | "recordSale">;
  mirror: MirrorPort;
  network: string;
  asset: string;
  /** HEDERA_RESOURCE_BASE: the 402's resource.url is <base>/x402/ghost/<listing>. */
  base: string;
  gate: PaywallGate;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  log?: (line: string) => void;
  /** Mirror poll interval for a pending payment (2 s). */
  pollMs?: number;
  /** Past the valid window (15 s). */
  graceMs?: number;
}

interface Pending {
  sale: Omit<SaleRecord, "n">;
  deadlineMs: number;
}

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-expose-headers": "PAYMENT-REQUIRED, PAYMENT-RESPONSE",
};

export class ResourceServer {
  private readonly now: () => number;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly pollMs: number;
  private readonly graceMs: number;
  private readonly inflight = new Map<string, Promise<X402Reply>>();
  private readonly pending = new Map<string, Pending>();

  constructor(private readonly opts: ResourceOptions) {
    this.now = opts.now ?? Date.now;
    this.sleep = opts.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.pollMs = opts.pollMs ?? 2000;
    this.graceMs = opts.graceMs ?? 15_000;
  }

  /** The CORS preflight for a browser x402 client. */
  preflight(): X402Reply {
    return {
      status: 204,
      headers: { ...CORS, "access-control-allow-methods": "GET, OPTIONS", "access-control-allow-headers": "PAYMENT-SIGNATURE, Content-Type", "access-control-max-age": "600" },
      body: {},
    };
  }

  private reply(status: number, body: Record<string, unknown>, extra: Record<string, string> = {}): X402Reply {
    return { status, headers: { ...CORS, ...extra }, body };
  }

  private reply402(resource: ResourceInfo, req: PaymentRequirements, error: string, stage?: "check" | "verify" | "settle"): X402Reply {
    const pr = paymentRequired(resource, req, error);
    return this.reply(402, stage ? { error, stage } : { error }, { "PAYMENT-REQUIRED": headers.encodeRequired(pr) });
  }

  async handle(listing: string, signature: string | null): Promise<X402Reply> {
    const off = this.opts.gate();
    if (off) return this.reply(503, { error: off });
    if (!KEY_RE.test(listing)) return this.reply(404, { error: "not_for_sale" });

    let offer: Offer | null;
    try {
      offer = await this.opts.source.offer(listing.toLowerCase());
    } catch {
      return this.reply(503, { error: "hedera_unavailable" });
    }
    if (!offer) return this.reply(404, { error: "not_for_sale" });
    const choice = this.opts.facilitators.current();
    if (!choice) return this.reply(503, { error: "hedera_unavailable" });

    const req = await buildRequirement({
      network: this.opts.network,
      payTo: offer.pay_to,
      amount: centsToAtomic(offer.price_c),
      asset: this.opts.asset,
      feePayer: choice.feePayer,
    });
    const resource: ResourceInfo = { url: `${this.opts.base}/x402/ghost/${offer.listing}`, description: offer.description, mimeType: "application/json" };
    if (signature === null) return this.reply402(resource, req, "payment_required");

    let payload: PaymentPayload;
    try {
      payload = headers.decodeSignature(signature);
    } catch {
      return this.reply402(resource, req, "invalid_payment", "check");
    }
    const facts = paymentFacts(payload, this.opts.asset);
    if (!facts || !facts.payer) return this.reply402(resource, req, "invalid_payment", "check");

    // Re-download: this transaction already bought this ghost.
    const sold = this.opts.store.saleFor(facts.tx);
    if (sold && sold.run === offer.run) return this.serve(offer, { success: true, transaction: facts.tx, network: req.network, payer: sold.payer });

    if (payload.x402Version !== 2 || !sameJson(payload.accepted, req)) return this.reply402(resource, req, "requirements_changed", "check");

    const held = this.inflight.get(facts.tx);
    if (held) return held;
    const work = this.sell(offer, payload, req, resource, facts.tx, facts.payer).finally(() => this.inflight.delete(facts.tx));
    this.inflight.set(facts.tx, work);
    return work;
  }

  private async sell(offer: Offer, payload: PaymentPayload, req: PaymentRequirements, resource: ResourceInfo, tx: string, payer: string): Promise<X402Reply> {
    const feePayer = String(req.extra.feePayer);
    const port = this.opts.facilitators.byFeePayer(feePayer);
    if (!port) return this.reply(503, { error: "hedera_unavailable" });
    const amount = atomicText(req.amount);

    const t0 = this.now();
    try {
      const v = await port.verify(payload, req);
      if (!v.ok) {
        this.opts.log?.(`x402 ghost ${offer.listing}: verify refused (${v.reason}), nothing settled`);
        return this.reply402(resource, req, v.reason, "verify");
      }
    } catch (err) {
      this.opts.log?.(`x402 ghost ${offer.listing}: facilitator unreachable at /verify (${err instanceof FacilitatorDown ? err.message : "error"})`);
      return this.reply(503, { error: "hedera_unavailable" });
    }
    const verifyMs = this.now() - t0;

    const plain = offer.open();
    if (!plain || sha256Hex(plain) !== offer.log_h) {
      this.opts.log?.(`x402 ghost ${offer.listing}: does not match its log_h, not sold`);
      return this.reply(404, { error: "not_for_sale" });
    }

    const sale: Omit<SaleRecord, "n"> = {
      run: offer.run,
      listing: offer.listing,
      seller: offer.seller,
      game: offer.game,
      pay_to: offer.pay_to,
      amount: req.amount,
      asset: req.asset,
      payer,
      buyer: null,
      at: Math.floor(this.now() / 1000),
    };
    const t1 = this.now();
    const s = await port.settle(payload, req);
    const settleMs = this.now() - t1;
    if (s.kind === "ok") {
      const settled = txAt(s.response.transaction) ?? s.response.transaction;
      if (settled !== tx) this.opts.log?.(`x402 ghost ${offer.listing}: the facilitator settled ${settled}, the payment named ${tx}`);
      this.opts.store.recordSale(settled, sale);
      this.opts.log?.(
        `x402 ghost ${offer.listing}: sold to ${payer} for ${amount} USDC, paid to ${offer.pay_to}, tx ${settled} (verify ${verifyMs} ms, settle ${settleMs} ms) ${hashscan.tx(settled)}`,
      );
      return this.serve(offer, { ...s.response, transaction: settled }, plain);
    }
    // Not settled as far as this request knows: the transaction may still land. Watch for it.
    this.track(tx, sale);
    const why = s.kind === "refused" ? s.reason : "settlement_pending";
    this.opts.log?.(`x402 ghost ${offer.listing}: settle ${s.kind === "refused" ? `refused (${s.reason})` : `gave no answer (${s.why})`}; watching ${tx} on the mirror`);
    return this.reply402(resource, req, why, "settle");
  }

  private serve(offer: Offer, response: SettleResponse, plain?: Uint8Array): X402Reply {
    const log = plain ?? offer.open();
    if (!log || sha256Hex(log) !== offer.log_h) return this.reply(404, { error: "not_for_sale" });
    return this.reply(
      200,
      { listing: offer.listing, run: offer.run, log_h: offer.log_h, log: Buffer.from(log).toString("base64") },
      { "PAYMENT-RESPONSE": headers.encodeResponse(response) },
    );
  }

  // ---- payments whose settle did not answer ----------------------------------------------

  private track(tx: string, sale: Omit<SaleRecord, "n">): void {
    if (this.pending.has(tx) || this.opts.store.saleFor(tx)) return;
    const start = txValidStartMs(tx) ?? this.now();
    this.pending.set(tx, { sale, deadlineMs: Math.max(start, this.now()) + MAX_TIMEOUT_S * 1000 + this.graceMs });
    void this.watch(tx);
  }

  /** Ask the mirror once: true when it shows the transaction with SUCCESS and the right transfers (and records the sale). */
  private async check(tx: string, p: Pending): Promise<"sold" | "failed" | "unseen"> {
    const m = await this.opts.mirror.transaction(tx);
    if (!m) return "unseen";
    if (m.result === "SUCCESS" && transfersMatch(m, p.sale.asset, p.sale.payer, p.sale.pay_to, BigInt(p.sale.amount))) {
      this.opts.store.recordSale(tx, p.sale);
      this.pending.delete(tx);
      this.opts.log?.(`x402 ghost ${p.sale.listing}: ${tx} landed after all (mirror: SUCCESS); sale recorded ${hashscan.tx(tx)}`);
      return "sold";
    }
    this.pending.delete(tx);
    this.opts.log?.(`x402 ghost ${p.sale.listing}: ${tx} is on the mirror as ${m.result}, not a sale`);
    return "failed";
  }

  private async watch(tx: string): Promise<void> {
    for (;;) {
      const p = this.pending.get(tx);
      if (!p) return;
      await this.sleep(this.pollMs);
      try {
        if ((await this.check(tx, p)) !== "unseen") return;
      } catch {
        // the mirror did not answer: try again
      }
      if (this.now() > p.deadlineMs) {
        this.pending.delete(tx);
        this.opts.log?.(`x402 ghost ${p.sale.listing}: ${tx} never showed on the mirror; nothing sold`);
        return;
      }
    }
  }

  /**
   * For /arkiv/ghost: does this transaction pay for this run? A recorded sale, or a pending one the
   * mirror now shows as settled.
   */
  async confirm(tx: string, run: string): Promise<boolean> {
    const sold = this.opts.store.saleFor(tx);
    if (sold) return sold.run === run.toLowerCase();
    const p = this.pending.get(tx);
    if (!p || p.sale.run !== run.toLowerCase()) return false;
    try {
      return (await this.check(tx, p)) === "sold";
    } catch {
      return false;
    }
  }

  /** Pending payments being watched (tests and the health log). */
  get pendingCount(): number {
    return this.pending.size;
  }
}

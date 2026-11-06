/**
 * The Hedera half of the bridge's HTTP contract (spec: HTTP contract), wired from what is configured:
 *
 *   GET  /hedera/config           network, mirror, hashscan, topic, usdc, agent, facilitator, fee payer,
 *                                 caps, the paywall's URL template and the house account. No keys.
 *   GET  /hedera/payto/{book}     {"book", "pay_to"} (null when none)
 *   POST /hedera/record           the LISTING message -> {id, expires_s: 120}         (record.ts)
 *   GET  /hedera/record/{id}      {stage, ok, failure, data}
 *   POST /hedera/buy              PB buys a ghost -> {id, expires_s: 240}               (agent.ts)
 *   GET  /hedera/buy/{id}         {stage, ok, failure, data}
 *   GET  /hedera/sales/{book}     {"sales": [{n, buyer, game, amount, tx}]}, ?after=<n>
 *   GET  /x402/ghost/{listing}    the paywall                                          (resource.ts)
 *
 * and three /health fields: "hedera" (the last 30 s probe reached the mirror and a facilitator's
 * /supported lists exact on hedera:testnet), "hedera_pay" (the configuration is complete, the agent
 * holds at least one price of USDC, a facilitator is up) and "hedera_record" (topic and operator
 * configured, the operator holds HBAR).
 *
 * Errors are non-2xx {"error", "failure"}: ls_record_fail on /hedera/record*, buy_down on the others.
 */
import { BOOK_RE } from "../approvals.js";
import type { HederaConfig } from "../config.js";
import { HASHSCAN, HEDERA_NETWORK_CAIP2 } from "../config.js";
import type { Store } from "../store.js";
import { BuyRefused, type Agent, type BuyView } from "./agent.js";
import type { HederaPort, MirrorPort } from "./net.js";
import { RecordRefused, type Recorder, type RecordView } from "./record.js";
import type { ResourceServer, X402Reply } from "./resource.js";
import { atomicText, centsToAtomic, type Facilitators } from "./x402.js";

export class HederaRouteError extends Error {
  constructor(public readonly status: number, public readonly body: Record<string, unknown>) {
    super(String(body.error));
  }
}

export interface HederaHealth {
  hedera: "ok" | "off";
  hedera_pay: boolean;
  hedera_record: boolean;
}

export interface HederaServiceOptions {
  cfg: HederaConfig;
  /** ARKIV_GHOST_PRICE_C: one price, for the agent's "holds at least one price" check. */
  priceC: number;
  /** hederaPayProblems / hederaRecordProblems (names only). */
  payProblems: string[];
  recordProblems: string[];
  store: Store | null;
  mirror: MirrorPort | null;
  hedera: HederaPort | null;
  facilitators: Facilitators | null;
  agent: Agent | null;
  recorder: Recorder | null;
  resource: ResourceServer | null;
  /** HEDERA_HOUSE_ID ("" or absent: no house account yet). */
  houseId?: string;
  log?: (line: string) => void;
}

const BUY = "buy_down";
const RECORD = "ls_record_fail";

export class HederaService {
  private mirrorSeen = false;
  private agentUsdc: bigint | null = null;
  private operatorHbar: bigint | null = null;
  /** null until checked; false when HEDERA_USDC is not a 6-decimal USDC token on the mirror. */
  private usdcOk: boolean | null = null;

  constructor(private readonly opts: HederaServiceOptions) {}

  get payConfigured(): boolean {
    return this.opts.payProblems.length === 0 && this.opts.agent !== null && this.opts.resource !== null;
  }

  get recordConfigured(): boolean {
    return this.opts.recordProblems.length === 0 && this.opts.recorder !== null;
  }

  // ---- health, probe and gates ------------------------------------------------------------

  health(): HederaHealth {
    const facUp = this.opts.facilitators?.up() ?? false;
    const price = BigInt(centsToAtomic(Math.max(0, Number.isInteger(this.opts.priceC) ? this.opts.priceC : 0)));
    return {
      hedera: this.mirrorSeen && facUp ? "ok" : "off",
      hedera_pay: this.payConfigured && this.usdcOk === true && facUp && this.agentUsdc !== null && this.agentUsdc >= price && price > 0n,
      hedera_record: this.recordConfigured && this.operatorHbar !== null && this.operatorHbar > 0n,
    };
  }

  /** New buys: refused when not configured, or when HEDERA_USDC failed its check or no facilitator answered the last probe. */
  readonly payGate = (): null | "hedera_not_configured" | "hedera_unavailable" => {
    if (!this.payConfigured) return "hedera_not_configured";
    if (this.usdcOk === false) return "hedera_unavailable";
    if (this.opts.facilitators && this.opts.facilitators.probedAt !== null && !this.opts.facilitators.up()) return "hedera_unavailable";
    return null;
  };

  /** The paywall: on whenever Hedera payments are configured (the facilitator is checked per request). */
  readonly paywallGate = (): null | "hedera_not_configured" | "hedera_unavailable" => {
    if (!this.payConfigured) return "hedera_not_configured";
    if (this.usdcOk === false) return "hedera_unavailable";
    return null;
  };

  readonly recordGate = (): null | "hedera_not_configured" | "hedera_unavailable" => (this.recordConfigured ? null : "hedera_not_configured");

  /** One probe: the mirror (and HEDERA_USDC once), the facilitators' /supported, the agent's USDC, the operator's HBAR. */
  async probe(): Promise<void> {
    const { mirror, facilitators, cfg } = this.opts;
    if (!mirror) return;
    const before = JSON.stringify(this.health());
    let reached = false;
    try {
      if (this.usdcOk === null) {
        const t = await mirror.token(cfg.usdc);
        reached = true;
        this.usdcOk = t !== null && t.decimals === 6 && t.type === "FUNGIBLE_COMMON" && t.symbol === "USDC";
        if (!this.usdcOk) this.opts.log?.(`hedera: HEDERA_USDC ${cfg.usdc} is not a 6-decimal USDC token on the mirror; payments off`);
      }
      if (this.payConfigured || /^0\.0\.\d+$/.test(cfg.agentId)) {
        this.agentUsdc = await mirror.tokenBalance(cfg.agentId, cfg.usdc);
        reached = true;
      }
      if (/^0\.0\.\d+$/.test(cfg.operatorId)) {
        this.operatorHbar = (await mirror.account(cfg.operatorId))?.balance ?? null;
        reached = true;
      }
      if (!reached) {
        await mirror.token(cfg.usdc);
        reached = true;
      }
    } catch {
      reached = false;
    }
    this.mirrorSeen = reached;
    if (facilitators) await facilitators.probe();
    const now = this.health();
    if (JSON.stringify(now) !== before) {
      const bits = [
        `mirror ${this.mirrorSeen ? "reachable" : "unreachable"}`,
        `facilitator ${facilitators?.current()?.port.url ?? "none"}`,
        this.agentUsdc !== null ? `agent ${atomicText(this.agentUsdc)} USDC` : "agent USDC unknown",
        this.operatorHbar !== null ? `operator ${(Number(this.operatorHbar) / 1e8).toFixed(2)} HBAR` : "operator HBAR unknown",
      ];
      const off = this.payConfigured ? "" : ` (payments off until set: ${this.opts.payProblems.join(", ")})`;
      this.opts.log?.(`hedera: ${bits.join(", ")}; pay ${now.hedera_pay ? "on" : "off"}${off}, record ${now.hedera_record ? "on" : "off"}`);
    }
  }

  // ---- routes ----------------------------------------------------------------------------

  config(): Record<string, unknown> {
    const { cfg } = this.opts;
    const cur = this.opts.facilitators?.current() ?? null;
    const acct = (v: string) => (/^0\.0\.\d{1,10}$/.test(v) ? v : null);
    return {
      network: HEDERA_NETWORK_CAIP2,
      mirror: cfg.mirror,
      hashscan: HASHSCAN,
      topic: acct(cfg.topicId),
      usdc: cfg.usdc,
      agent: acct(cfg.agentId),
      facilitator: cur?.port.url ?? cfg.facilitator,
      fee_payer: cur?.feePayer ?? null,
      caps: { max_c: cfg.maxPriceC, book_day_c: cfg.bookDayC, agent_day_c: cfg.agentDayC },
      resource: `${cfg.resourceBase}/x402/ghost/{listing}`,
      house: acct(this.opts.houseId ?? ""),
    };
  }

  payto(book: string): { book: string; pay_to: string | null } {
    if (!BOOK_RE.test(book)) throw new HederaRouteError(400, { error: "bad_body", failure: RECORD });
    return { book, pay_to: this.opts.store?.paytoFor(book) ?? null };
  }

  recordStart(body: Record<string, unknown>): { id: string; expires_s: number } {
    if (!this.opts.recorder) throw new HederaRouteError(503, { error: "hedera_not_configured", failure: RECORD });
    try {
      return this.opts.recorder.start(body);
    } catch (err) {
      if (err instanceof RecordRefused) throw new HederaRouteError(err.status, { error: err.error, failure: RECORD });
      throw err;
    }
  }

  recordView(id: string): RecordView {
    const v = this.opts.recorder?.view(id);
    if (!v) throw new HederaRouteError(404, { error: "unknown_id", failure: RECORD });
    return v;
  }

  buyStart(body: Record<string, unknown>): { id: string; expires_s: number } {
    if (!this.opts.agent) throw new HederaRouteError(503, { error: "hedera_not_configured", failure: BUY });
    try {
      return this.opts.agent.start(body);
    } catch (err) {
      if (err instanceof BuyRefused) throw new HederaRouteError(err.status, { error: err.error, failure: BUY });
      throw err;
    }
  }

  buyView(id: string): BuyView {
    const v = this.opts.agent?.view(id);
    if (!v) throw new HederaRouteError(404, { error: "unknown_id", failure: BUY });
    return v;
  }

  sales(book: string, after: string | null): { sales: Array<{ n: number; buyer: string; game: string; amount: string; tx: string }> } {
    if (!BOOK_RE.test(book)) throw new HederaRouteError(400, { error: "bad_body", failure: BUY });
    const n = after === null || after === "" ? 0 : /^\d{1,12}$/.test(after) ? Number(after) : Number.NaN;
    if (!Number.isInteger(n)) throw new HederaRouteError(400, { error: "bad_body", failure: BUY });
    if (!this.opts.store) throw new HederaRouteError(503, { error: "hedera_not_configured", failure: BUY });
    return {
      sales: this.opts.store.salesFor(book, n).map((s) => ({ n: s.n, buyer: s.buyer ?? s.payer, game: s.game, amount: atomicText(s.amount), tx: s.tx })),
    };
  }

  async x402(listing: string, signature: string | null): Promise<X402Reply> {
    if (!this.opts.resource) return { status: 503, headers: {}, body: { error: "hedera_not_configured" } };
    return this.opts.resource.handle(listing, signature);
  }

  x402Preflight(): X402Reply {
    return this.opts.resource?.preflight() ?? { status: 204, headers: {}, body: {} };
  }
}

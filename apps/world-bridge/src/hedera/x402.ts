/**
 * x402 v2 on Hedera (`@x402/core` and `@x402/hedera` 2.30.0, scheme `exact`, network
 * `hedera:testnet`), hand-wired on both sides:
 *
 * - the requirement for one listing (payTo from the listing, the atomic amount, USDC, and the fee
 *   payer the facilitator's /supported names, filled in by the Hedera server scheme);
 * - the PAYMENT-REQUIRED / PAYMENT-SIGNATURE / PAYMENT-RESPONSE headers (base64 JSON, the
 *   library's own encoders);
 * - FacilitatorPort (supported, verify, settle) and its HTTP implementation over the library's
 *   HTTPFacilitatorClient, with failover: the probe picks the first facilitator whose /supported
 *   lists the kind. That only changes which fee payer new 402s name: a payment is always settled
 *   by the facilitator whose fee payer its transaction names.
 * - PB's client side: x402Client with the Hedera client scheme, spend controls on (USDC on
 *   hedera:testnet only, the library's $1-per-payment cap), and x402HTTPClient for the headers.
 *   Not wrapFetchWithPayment: it would pay before PB's guards see the 402.
 *
 * Why not x402ResourceServer: it maps each kind to one facilitator at initialize() and cannot settle
 * by the fee payer a payment names, so /verify and /settle go through HTTPFacilitatorClient directly
 * (the spec's H0 choice). The requirement still comes from the library's Hedera server scheme.
 */
import { x402Client } from "@x402/core/client";
import {
  decodePaymentRequiredHeader,
  decodePaymentResponseHeader,
  decodePaymentSignatureHeader,
  encodePaymentRequiredHeader,
  encodePaymentResponseHeader,
  FacilitatorTimeoutError,
  HTTPFacilitatorClient,
  x402HTTPClient,
} from "@x402/core/http";
import type { PaymentPayload, PaymentRequired, PaymentRequirements, SettleResponse } from "@x402/core/types";
import type { ClientHederaSigner } from "@x402/hedera";
import { inspectHederaTransaction } from "@x402/hedera";
import { ExactHederaScheme as ClientScheme } from "@x402/hedera/exact/client";
import { ExactHederaScheme as ServerScheme } from "@x402/hedera/exact/server";
import { txAt } from "./net.js";

export type { PaymentPayload, PaymentRequired, PaymentRequirements, SettleResponse };

export const X402_VERSION = 2;
export const SCHEME = "exact";
/** The SDK's default valid duration, which the facilitators settle within. */
export const MAX_TIMEOUT_S = 120;
/** USDC has 6 decimals: one cent is 10^4 atomic units. */
export const ATOMIC_PER_CENT = 10_000n;

export const centsToAtomic = (c: number): string => (BigInt(c) * ATOMIC_PER_CENT).toString();
/** "0.10" for 100000 atomic units (cents rounded down). */
export function atomicText(atomic: string | bigint): string {
  const cents = BigInt(atomic) / ATOMIC_PER_CENT;
  return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}

export interface ResourceInfo {
  url: string;
  description: string;
  mimeType: string;
}

const serverScheme = new ServerScheme();

/** One requirement for one listing. Key order as the spec shows it; `extra.feePayer` from /supported. */
export async function buildRequirement(o: { network: string; payTo: string; amount: string; asset: string; feePayer: string }): Promise<PaymentRequirements> {
  const base: PaymentRequirements = {
    scheme: SCHEME,
    network: o.network as PaymentRequirements["network"],
    amount: o.amount,
    asset: o.asset,
    payTo: o.payTo,
    maxTimeoutSeconds: MAX_TIMEOUT_S,
    extra: {},
  };
  return serverScheme.enhancePaymentRequirements(base, { x402Version: X402_VERSION, scheme: SCHEME, network: base.network, extra: { feePayer: o.feePayer } }, []);
}

export function paymentRequired(resource: ResourceInfo, req: PaymentRequirements, error = "payment_required"): PaymentRequired {
  return { x402Version: X402_VERSION, error, resource, accepts: [req] };
}

/** Deep equality on JSON values with key order ignored. */
export function sameJson(a: unknown, b: unknown): boolean {
  const canon = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(canon);
    if (v && typeof v === "object") {
      return Object.fromEntries(
        Object.keys(v as Record<string, unknown>)
          .filter((k) => (v as Record<string, unknown>)[k] !== undefined)
          .sort()
          .map((k) => [k, canon((v as Record<string, unknown>)[k])]),
      );
    }
    return v;
  };
  return JSON.stringify(canon(a)) === JSON.stringify(canon(b));
}

export const headers = {
  encodeRequired: encodePaymentRequiredHeader,
  decodeRequired: decodePaymentRequiredHeader,
  decodeSignature: decodePaymentSignatureHeader,
  encodeResponse: encodePaymentResponseHeader,
  decodeResponse: decodePaymentResponseHeader,
};

/** What a payment's transaction says about itself (decoded from its bytes, no network). */
export interface PaymentFacts {
  /** `0.0.FEEPAYER@S.N`. */
  tx: string;
  feePayer: string;
  /** The one account that sends the asset (the payer). */
  payer: string | null;
}

export function paymentFacts(payload: PaymentPayload, asset: string): PaymentFacts | null {
  const b64 = (payload?.payload as { transaction?: unknown } | undefined)?.transaction;
  if (typeof b64 !== "string" || b64 === "") return null;
  try {
    const t = inspectHederaTransaction(b64);
    const rows = t.tokenTransfers[asset] ?? [];
    const senders = rows.filter((r) => BigInt(r.amount) < 0n).map((r) => r.accountId);
    const tx = txAt(t.transactionId);
    if (!tx) return null;
    return { tx, feePayer: t.transactionIdAccountId, payer: senders.length === 1 ? senders[0] : null };
  } catch {
    return null;
  }
}

// ---- facilitators ----------------------------------------------------------------------------

export interface SupportedKind {
  x402Version: number;
  scheme: string;
  network: string;
  extra?: Record<string, unknown>;
}

export type VerifyOutcome = { ok: true; payer: string | null } | { ok: false; reason: string };

/**
 * A settle that came back with an answer (`ok` or a refusal) or without one (`unknown`: a timeout,
 * a dropped connection, a 5xx). Only `ok` and `refused` are definite.
 */
export type SettleOutcome = { kind: "ok"; response: SettleResponse } | { kind: "refused"; reason: string } | { kind: "unknown"; why: string };

export interface FacilitatorPort {
  readonly url: string;
  supported(): Promise<SupportedKind[]>;
  /** Throws FacilitatorDown when it could not be asked. */
  verify(payload: PaymentPayload, req: PaymentRequirements): Promise<VerifyOutcome>;
  settle(payload: PaymentPayload, req: PaymentRequirements): Promise<SettleOutcome>;
}

export class FacilitatorDown extends Error {}

function reasonOf(err: unknown, field: "invalidReason" | "errorReason"): string | null {
  const e = err as Record<string, unknown> & { response?: Record<string, unknown> };
  for (const src of [e, e?.response, (e as { data?: Record<string, unknown> })?.data]) {
    const v = src?.[field];
    if (typeof v === "string" && v !== "") return v;
  }
  return null;
}

/** One facilitator over HTTP (no API key on testnet). */
export class HttpFacilitator implements FacilitatorPort {
  private readonly verifyClient: HTTPFacilitatorClient;
  private readonly settleClient: HTTPFacilitatorClient;

  constructor(readonly url: string, opts: { verifyTimeoutMs?: number; settleTimeoutMs?: number } = {}) {
    this.verifyClient = new HTTPFacilitatorClient({ url, timeoutMs: opts.verifyTimeoutMs ?? 15_000 });
    this.settleClient = new HTTPFacilitatorClient({ url, timeoutMs: opts.settleTimeoutMs ?? 45_000 });
  }

  async supported(): Promise<SupportedKind[]> {
    try {
      return (await this.verifyClient.getSupported()).kinds as SupportedKind[];
    } catch (err) {
      throw new FacilitatorDown(`/supported: ${(err as Error)?.message?.split("\n")[0]?.slice(0, 120) ?? "error"}`);
    }
  }

  async verify(payload: PaymentPayload, req: PaymentRequirements): Promise<VerifyOutcome> {
    try {
      const r = await this.verifyClient.verify(payload, req);
      return r.isValid ? { ok: true, payer: r.payer ?? null } : { ok: false, reason: r.invalidReason ?? "invalid" };
    } catch (err) {
      const reason = reasonOf(err, "invalidReason");
      if (reason) return { ok: false, reason };
      throw new FacilitatorDown(`/verify: ${(err as Error)?.name ?? "error"}`);
    }
  }

  async settle(payload: PaymentPayload, req: PaymentRequirements): Promise<SettleOutcome> {
    try {
      const r = await this.settleClient.settle(payload, req);
      return r.success ? { kind: "ok", response: r } : { kind: "refused", reason: r.errorReason ?? "settle_failed" };
    } catch (err) {
      if (err instanceof FacilitatorTimeoutError) return { kind: "unknown", why: "settle timed out" };
      const reason = reasonOf(err, "errorReason");
      if (reason) return { kind: "refused", reason };
      return { kind: "unknown", why: `settle: ${(err as Error)?.name ?? "error"}` };
    }
  }
}

export interface FacilitatorChoice {
  port: FacilitatorPort;
  feePayer: string;
}

/**
 * The configured facilitators in order (X402_FACILITATOR, then X402_FACILITATOR_FALLBACK). The
 * probe picks the first whose /supported lists exact on the network with a fee payer.
 */
export class Facilitators {
  private chosen: FacilitatorChoice | null = null;
  private readonly feePayers = new Map<FacilitatorPort, string>();
  private lastSeen: number | null = null;
  private lastProbe: number | null = null;

  constructor(readonly ports: FacilitatorPort[], private readonly network: string, private readonly log?: (line: string) => void) {}

  async probe(): Promise<FacilitatorChoice | null> {
    const before = this.chosen ? `${this.chosen.port.url} ${this.chosen.feePayer}` : "none";
    let pick: FacilitatorChoice | null = null;
    for (const port of this.ports) {
      try {
        const kinds = await port.supported();
        const kind = kinds.find((k) => k.x402Version === X402_VERSION && k.scheme === SCHEME && k.network === this.network);
        const fp = kind?.extra?.feePayer;
        if (typeof fp === "string" && fp !== "") {
          this.feePayers.set(port, fp);
          if (!pick) pick = { port, feePayer: fp };
        }
      } catch {
        // the next one
      }
      if (pick) break;
    }
    this.chosen = pick;
    this.lastProbe = Date.now();
    if (pick) this.lastSeen = Date.now();
    const after = pick ? `${pick.port.url} ${pick.feePayer}` : "none";
    if (after !== before) this.log?.(pick ? `x402 facilitator ${pick.port.url} (fee payer ${pick.feePayer})` : "x402 facilitator: none answered /supported");
    return pick;
  }

  /** The facilitator new 402s name, as last probed; null when none answered. */
  current(): FacilitatorChoice | null {
    return this.chosen;
  }

  /** The facilitator whose fee payer this is (as its last /supported said). */
  byFeePayer(feePayer: string): FacilitatorPort | null {
    for (const [port, fp] of this.feePayers) if (fp === feePayer) return port;
    return null;
  }

  up(): boolean {
    return this.chosen !== null;
  }

  get seenAt(): number | null {
    return this.lastSeen;
  }

  /** When the last probe finished (null before the first). */
  get probedAt(): number | null {
    return this.lastProbe;
  }
}

// ---- PB's client side ------------------------------------------------------------------------

export interface BuiltPayment {
  payload: PaymentPayload;
  /** { "PAYMENT-SIGNATURE": base64 } */
  header: Record<string, string>;
  facts: PaymentFacts;
}

/**
 * Builds PB's payments: a TransferTransaction of one HTS token from the agent to payTo, its
 * transaction id on the fee payer, valid 120 s, signed by the agent key only. Spend controls stay
 * on inside the library as a second guard: only default assets (USDC) on the one registered
 * network, at most $1 a payment.
 */
export class PaymentBuilder {
  private readonly client: x402Client;
  private readonly http: x402HTTPClient;

  constructor(signer: ClientHederaSigner, private readonly network: string, private readonly asset: string) {
    this.client = new x402Client().register(network as PaymentRequirements["network"], new ClientScheme(signer));
    this.client.setSpendControls({ maxAmountPerPayment: "$1" });
    this.http = new x402HTTPClient(this.client);
  }

  /** The 402's requirements, from its PAYMENT-REQUIRED header (body as the fallback). Throws when unreadable. */
  read402(getHeader: (name: string) => string | null, body: unknown): PaymentRequired {
    return this.http.getPaymentRequiredResponse(getHeader, body);
  }

  async build(pr: PaymentRequired): Promise<BuiltPayment> {
    const payload = await this.client.createPaymentPayload(pr);
    const facts = paymentFacts(payload, this.asset);
    if (!facts) throw new Error("the built payment does not decode");
    return { payload, header: this.http.encodePaymentSignatureHeader(payload), facts };
  }

  settleResponse(getHeader: (name: string) => string | null): SettleResponse | null {
    try {
      return this.http.getPaymentSettleResponse(getHeader);
    } catch {
      return null;
    }
  }
}

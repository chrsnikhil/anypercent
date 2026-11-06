/**
 * A fake x402 facilitator behind FacilitatorPort. /verify decodes the payment's real transaction
 * bytes and checks what the real ones check that can be checked offline (one asset, sums to zero,
 * payTo gets exactly amount, the fee payer sends nothing, the transaction id is the fee payer's,
 * the payer holds the amount on the fake mirror). /settle puts the transfer on the fake mirror, or
 * refuses, or gives no answer, as the test says. Every call is recorded.
 */
import { inspectHederaTransaction } from "@x402/hedera";
import type { FacilitatorPort, PaymentPayload, PaymentRequirements, SettleOutcome, SupportedKind, VerifyOutcome } from "../src/hedera/x402.js";
import { FacilitatorDown } from "../src/hedera/x402.js";
import { txAt } from "../src/hedera/net.js";
import { FEE_PAYER, type FakeMirror } from "./fake-hedera.js";

export type SettleMode =
  | "ok"
  | "refuse"
  /** No answer; the transfer lands on the mirror after `landAfterReads` reads. */
  | "timeout-lands"
  /** No answer; nothing ever lands. */
  | "timeout"
  /** Refused, but the transfer landed anyway (a receipt error after submission). */
  | "refuse-lands"
  /** Lands with a failure status. */
  | "fails-on-chain";

export class FakeFacilitator implements FacilitatorPort {
  calls: Array<{ op: "verify" | "settle"; payload: PaymentPayload; req: PaymentRequirements }> = [];
  supportedCalls = 0;
  down = false;
  verifyDown = false;
  /** Force verify to refuse with this reason. */
  verifyRefuse: string | null = null;
  settleMode: SettleMode = "ok";
  /** Mirror lag for the settled transaction, in reads. */
  landAfterReads = 0;

  constructor(private readonly mirror: FakeMirror, readonly url = "https://facilitator.test", readonly feePayer = FEE_PAYER, private readonly events: string[] = []) {}

  async supported(): Promise<SupportedKind[]> {
    this.supportedCalls += 1;
    if (this.down) throw new FacilitatorDown("/supported: down");
    return [
      { x402Version: 2, scheme: "exact", network: "eip155:84532" },
      { x402Version: 2, scheme: "exact", network: "hedera:testnet", extra: { feePayer: this.feePayer } },
    ];
  }

  private inspect(payload: PaymentPayload, req: PaymentRequirements): { ok: true; payer: string; tx: string } | { ok: false; reason: string } {
    const b64 = (payload.payload as { transaction?: string }).transaction;
    if (typeof b64 !== "string") return { ok: false, reason: "invalid_exact_hedera_payload_transaction" };
    let t;
    try {
      t = inspectHederaTransaction(b64);
    } catch {
      return { ok: false, reason: "invalid_exact_hedera_payload_transaction" };
    }
    if (t.hasNonTransferOperations || t.hbarTransfers.length > 0) return { ok: false, reason: "invalid_exact_hedera_payload_not_a_token_transfer" };
    const assets = Object.keys(t.tokenTransfers);
    if (assets.length !== 1 || assets[0] !== req.asset) return { ok: false, reason: "invalid_exact_hedera_payload_asset" };
    const rows = t.tokenTransfers[req.asset];
    if (rows.reduce((s, r) => s + BigInt(r.amount), 0n) !== 0n) return { ok: false, reason: "invalid_exact_hedera_payload_sum" };
    const to = rows.filter((r) => r.accountId === req.payTo).reduce((s, r) => s + BigInt(r.amount), 0n);
    if (to !== BigInt(req.amount)) return { ok: false, reason: "invalid_exact_hedera_payload_amount" };
    if (t.transactionIdAccountId !== req.extra.feePayer) return { ok: false, reason: "invalid_exact_hedera_payload_fee_payer" };
    if (rows.some((r) => r.accountId === req.extra.feePayer)) return { ok: false, reason: "invalid_exact_hedera_payload_fee_payer_transfers" };
    const payer = rows.find((r) => BigInt(r.amount) < 0n)?.accountId ?? "";
    return { ok: true, payer, tx: txAt(t.transactionId) as string };
  }

  async verify(payload: PaymentPayload, req: PaymentRequirements): Promise<VerifyOutcome> {
    this.calls.push({ op: "verify", payload, req });
    this.events.push("facilitator:verify");
    if (this.verifyDown) throw new FacilitatorDown("/verify: down");
    if (this.verifyRefuse) return { ok: false, reason: this.verifyRefuse };
    const r = this.inspect(payload, req);
    if (!r.ok) return r;
    const held = await this.mirror.tokenBalance(r.payer, req.asset);
    if (held === null || held < BigInt(req.amount)) return { ok: false, reason: "invalid_exact_hedera_payload_preflight_failed" };
    return { ok: true, payer: r.payer };
  }

  async settle(payload: PaymentPayload, req: PaymentRequirements): Promise<SettleOutcome> {
    this.calls.push({ op: "settle", payload, req });
    this.events.push("facilitator:settle");
    const r = this.inspect(payload, req);
    if (!r.ok) return { kind: "refused", reason: r.reason };
    const transfers = [
      { account: r.payer, amount: -BigInt(req.amount) },
      { account: req.payTo, amount: BigInt(req.amount) },
    ];
    switch (this.settleMode) {
      case "ok":
        this.mirror.addTx(r.tx, "SUCCESS", transfers, this.landAfterReads, req.asset);
        return { kind: "ok", response: { success: true, transaction: r.tx, network: req.network, payer: r.payer } };
      case "refuse":
        return { kind: "refused", reason: "transaction_failed" };
      case "refuse-lands":
        this.mirror.addTx(r.tx, "SUCCESS", transfers, this.landAfterReads, req.asset);
        return { kind: "refused", reason: "transaction_failed" };
      case "timeout-lands":
        this.mirror.addTx(r.tx, "SUCCESS", transfers, this.landAfterReads, req.asset);
        return { kind: "unknown", why: "settle timed out" };
      case "fails-on-chain":
        this.mirror.addTx(r.tx, "INSUFFICIENT_TOKEN_BALANCE", [], this.landAfterReads, req.asset);
        return { kind: "refused", reason: "transaction_failed" };
      case "timeout":
        return { kind: "unknown", why: "settle timed out" };
    }
  }

  ops(): string[] {
    return this.calls.map((c) => c.op);
  }
}

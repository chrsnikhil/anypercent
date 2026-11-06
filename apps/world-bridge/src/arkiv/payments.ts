/**
 * What releases a listed ghost's key: a payment receipt (spec: Decisions 7, `/arkiv/ghost`). Two
 * implementations:
 * - MockPayments (here): the launcher mock's receipts (`mock-` + 8 hex), only when
 *   ARKIV_MOCK_PAYMENTS=1 and Hedera payments are off. Each receipt pays for one run only, recorded in
 *   the store, so a receipt cannot unlock a second ghost.
 * - HederaPayments (src/hedera/payments.ts): a transaction id the x402 paywall settled for this run.
 *   With Hedera payments on, it is the only one, and mock receipts are refused.
 */
import type { Store } from "../store.js";

export interface PaymentCheck {
  /** True when this receipt pays for this run's ghost (and is now spent on it). */
  accept(receipt: string, run: string): boolean | Promise<boolean>;
}

export const MOCK_RECEIPT_RE = /^mock-[0-9a-f]{8}$/;

export class MockPayments implements PaymentCheck {
  constructor(private readonly enabled: boolean, private readonly store: Pick<Store, "claimReceipt">) {}

  accept(receipt: string, run: string): boolean {
    if (!this.enabled || !MOCK_RECEIPT_RE.test(receipt)) return false;
    return this.store.claimReceipt(receipt, run);
  }
}

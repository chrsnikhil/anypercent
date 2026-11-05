/**
 * What releases a listed ghost's key: a payment receipt (spec: Decisions 7, `/arkiv/ghost`).
 * Hedera is still mocked, so this build has one implementation: it accepts the launcher mock's
 * receipts (`mock-` + 8 hex) only when ARKIV_MOCK_PAYMENTS=1. Each receipt pays for one run only,
 * recorded in the store, so a receipt cannot unlock a second ghost. The x402 key sale replaces it
 * later behind the same interface.
 */
import type { Store } from "../store.js";

export interface PaymentCheck {
  /** True when this receipt pays for this run's ghost (and is now spent on it). */
  accept(receipt: string, run: string): boolean;
}

export const MOCK_RECEIPT_RE = /^mock-[0-9a-f]{8}$/;

export class MockPayments implements PaymentCheck {
  constructor(private readonly enabled: boolean, private readonly store: Pick<Store, "claimReceipt">) {}

  accept(receipt: string, run: string): boolean {
    if (!this.enabled || !MOCK_RECEIPT_RE.test(receipt)) return false;
    return this.store.claimReceipt(receipt, run);
  }
}

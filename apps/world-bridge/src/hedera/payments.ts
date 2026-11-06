/**
 * HederaPayments: what /arkiv/ghost accepts as a receipt while Hedera payments are on. The receipt
 * must be a payment transaction id that the x402 paywall settled for this run (store.sales), or one
 * whose settle gave no answer and that the mirror node now shows as settled with the right
 * transfers. Either id form works; a sale unlocks its own run only. The launcher mock's receipts are
 * refused even with ARKIV_MOCK_PAYMENTS=1 (logged once).
 */
import type { PaymentCheck } from "../arkiv/payments.js";
import { MOCK_RECEIPT_RE } from "../arkiv/payments.js";
import type { Store } from "../store.js";
import { txAt } from "./net.js";

export interface SaleConfirmer {
  /** True when this transaction pays for this run: a recorded sale, or a pending one the mirror now shows. */
  confirm(tx: string, run: string): Promise<boolean>;
}

export class HederaPayments implements PaymentCheck {
  private warnedMock = false;

  constructor(
    private readonly store: Pick<Store, "saleFor">,
    private readonly confirmer: SaleConfirmer | null,
    private readonly log?: (line: string) => void,
  ) {}

  async accept(receipt: string, run: string): Promise<boolean> {
    if (MOCK_RECEIPT_RE.test(receipt)) {
      if (!this.warnedMock) {
        this.warnedMock = true;
        this.log?.("arkiv ghost: mock receipts are refused while Hedera payments are on (ARKIV_MOCK_PAYMENTS is ignored)");
      }
      return false;
    }
    const tx = txAt(receipt);
    if (!tx) return false;
    const sale = this.store.saleFor(tx);
    if (sale) return sale.run === run.toLowerCase();
    return this.confirmer ? this.confirmer.confirm(tx, run) : false;
  }
}

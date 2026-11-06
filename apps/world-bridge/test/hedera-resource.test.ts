/** GET /x402/ghost/{listing}: the paywall over HTTP, against a fake facilitator, a fake Arkiv and a fake mirror. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, describe, it } from "node:test";
import { decodePaymentRequiredHeader, decodePaymentResponseHeader } from "@x402/core/http";
import { encryptGhost } from "../src/arkiv/ghost.js";
import { txAt } from "../src/hedera/net.js";
import type { PaymentRequired } from "../src/hedera/x402.js";
import { AGENT, FEE_PAYER, SELLER_ACCT, USDC } from "./fake-hedera.js";
import { GHOST, hedera, type Harness } from "./hedera-harness.js";
import { waitFor } from "./helpers.js";

const open: Harness[] = [];
after(async () => {
  for (const h of open) await h.close();
});
async function setup() {
  const h = await hedera();
  open.push(h);
  return h;
}

async function get(h: Harness, listing: string, sig?: string) {
  const res = await fetch(`${h.base}/x402/ghost/${listing}`, { headers: sig ? { "PAYMENT-SIGNATURE": sig } : {} });
  const body = (await res.json().catch(() => null)) as Record<string, any> | null;
  return { status: res.status, headers: res.headers, body };
}

/** The 402, then a payment built by PB's own builder from it (no agent guards). */
async function payFor(h: Harness, listing = h.listing) {
  const first = await get(h, listing);
  assert.equal(first.status, 402);
  const pr = h.builder.read402((n) => first.headers.get(n), first.body);
  const built = await h.builder.build(pr);
  return { pr, built, sig: built.header["PAYMENT-SIGNATURE"] };
}

describe("x402 paywall: the 402", () => {
  it("unpaid: 402, body payment_required, PAYMENT-REQUIRED decodes to exactly the requirement", async () => {
    const h = await setup();
    const r = await get(h, h.listing);
    assert.equal(r.status, 402);
    assert.deepEqual(r.body, { error: "payment_required" });
    const pr = decodePaymentRequiredHeader(r.headers.get("payment-required") as string) as PaymentRequired;
    assert.deepEqual(pr, {
      x402Version: 2,
      error: "payment_required",
      resource: { url: `${h.base}/x402/ghost/${h.listing}`, description: "Any% ghost: MARINE DRIVE GP 1:42.83 by " + h.seller.book, mimeType: "application/json" },
      accepts: [{ scheme: "exact", network: "hedera:testnet", amount: "100000", asset: USDC, payTo: SELLER_ACCT, maxTimeoutSeconds: 120, extra: { feePayer: FEE_PAYER } }],
    });
    assert.equal(r.headers.get("access-control-expose-headers"), "PAYMENT-REQUIRED, PAYMENT-RESPONSE");
    assert.equal(h.fac.calls.length, 0);
  });

  it("the requirement's JSON keys come in the spec's order", async () => {
    const h = await setup();
    const r = await get(h, h.listing);
    const raw = Buffer.from(r.headers.get("payment-required") as string, "base64").toString("utf8");
    assert.ok(raw.includes('"accepts":[{"scheme":"exact","network":"hedera:testnet","amount":"100000","asset":"0.0.429274","payTo":"0.0.5123456","maxTimeoutSeconds":120,"extra":{"feePayer":"0.0.9185802"}}]'), raw);
  });

  it("the fee payer follows the facilitator the probe picked (failover)", async () => {
    const h = await setup();
    h.fac.down = true;
    const { FakeFacilitator } = await import("./fake-facilitator.js");
    const fallback = new FakeFacilitator(h.mirror, "https://fallback.test", "0.0.7162784");
    const { Facilitators } = await import("../src/hedera/x402.js");
    const f = new Facilitators([h.fac, fallback], "hedera:testnet");
    assert.equal((await f.probe())?.feePayer, "0.0.7162784");
    h.fac.down = false;
    assert.equal((await f.probe())?.feePayer, FEE_PAYER);
    assert.equal(f.byFeePayer("0.0.7162784"), fallback, "a payment naming the fallback's fee payer settles there");
  });

  it("not for sale: 404 for no pay_to, a listing gone, a run without log_enc, a foreign listing, a bad key", async () => {
    const h = await setup();
    const v = h.arkiv.listings[0].spec.values;
    const noPay = h.arkiv.addListing(h.run, { ...v, pay_to: undefined });
    assert.equal((await get(h, noPay)).status, 404);
    assert.deepEqual((await get(h, noPay)).body, { error: "not_for_sale" });
    const foreign = h.arkiv.addListing(h.run, { ...v }, "0x2222222222222222222222222222222222222222");
    assert.equal((await get(h, foreign)).status, 404);
    const plainRun = h.arkiv.addRun({ ...h.arkiv.runs[0].spec.values, log_enc: undefined, log: h.ghostLog });
    const plainListing = h.arkiv.addListing(plainRun, { ...v });
    assert.equal((await get(h, plainListing)).status, 404);
    assert.equal((await get(h, `0x${"ab".repeat(32)}`)).status, 404);
    assert.equal((await get(h, "0x12")).status, 404);
    h.arkiv.listings[0].live = false;
    assert.equal((await get(h, h.listing)).status, 404);
    assert.equal(h.fac.calls.length, 0);
  });

  it("Hedera payments off: 503; Arkiv unreachable: 503 hedera_unavailable", async () => {
    const h = await setup();
    h.arkiv.readsDown = true;
    assert.deepEqual(await get(h, h.listing).then((r) => [r.status, r.body]), [503, { error: "hedera_unavailable" }]);
    h.arkiv.readsDown = false;
    const { ResourceServer } = await import("../src/hedera/resource.js");
    const off = new ResourceServer({ ...(h.resource as any).opts, gate: () => "hedera_not_configured" });
    assert.deepEqual(await off.handle(h.listing, null).then((r) => [r.status, r.body]), [503, { error: "hedera_not_configured" }]);
  });

  it("OPTIONS: the CORS preflight for a browser x402 client", async () => {
    const h = await setup();
    const res = await fetch(`${h.base}/x402/ghost/${h.listing}`, { method: "OPTIONS" });
    assert.equal(res.status, 204);
    assert.match(res.headers.get("access-control-allow-headers") ?? "", /PAYMENT-SIGNATURE/);
    assert.equal(res.headers.get("access-control-allow-origin"), "*");
  });
});

describe("x402 paywall: paid", () => {
  it("a valid payment: /verify then /settle with the requirement it issued; 200 with the log and PAYMENT-RESPONSE; the sale is recorded", async () => {
    const h = await setup();
    const { pr, built, sig } = await payFor(h);
    const r = await get(h, h.listing, sig);
    assert.equal(r.status, 200, JSON.stringify(r.body));
    assert.deepEqual(h.fac.ops(), ["verify", "settle"]);
    assert.deepEqual(h.fac.calls[0].req, pr.accepts[0]);
    assert.deepEqual(h.fac.calls[1].req, pr.accepts[0]);
    assert.deepEqual(Object.keys(r.body!).sort(), ["listing", "log", "log_h", "run"]);
    assert.deepEqual(Uint8Array.from(Buffer.from(r.body!.log, "base64")), h.ghostLog);
    assert.equal(r.body!.log_h, h.logH);
    const settled = decodePaymentResponseHeader(r.headers.get("payment-response") as string);
    assert.equal(settled.success, true);
    assert.equal(settled.transaction, built.facts.tx);
    assert.ok(settled.transaction.startsWith(`${FEE_PAYER}@`), "the transaction's account is the fee payer");
    assert.equal(settled.payer, AGENT);
    const sale = h.store.saleFor(built.facts.tx);
    assert.equal(sale?.run, h.run);
    assert.equal(sale?.pay_to, SELLER_ACCT);
    assert.equal(sale?.amount, "100000");
    assert.equal(sale?.payer, AGENT);
    assert.ok(!h.lines.join("\n").includes(sig), "the payment header is never logged");
  });

  it("the same payment again re-downloads the log without settling twice", async () => {
    const h = await setup();
    const { sig } = await payFor(h);
    assert.equal((await get(h, h.listing, sig)).status, 200);
    const again = await get(h, h.listing, sig);
    assert.equal(again.status, 200);
    assert.deepEqual(h.fac.ops(), ["verify", "settle"]);
  });

  it("/verify invalid: 402 with a fresh PAYMENT-REQUIRED whose error is the reason, no log, no settle", async () => {
    const h = await setup();
    const { sig } = await payFor(h);
    h.fac.verifyRefuse = "invalid_exact_hedera_payload_signature_invalid";
    const r = await get(h, h.listing, sig);
    assert.equal(r.status, 402);
    assert.deepEqual(r.body, { error: "invalid_exact_hedera_payload_signature_invalid", stage: "verify" });
    assert.equal(decodePaymentRequiredHeader(r.headers.get("payment-required") as string).error, "invalid_exact_hedera_payload_signature_invalid");
    assert.deepEqual(h.fac.ops(), ["verify"]);
    assert.equal(h.store.saleFor(txAt((await payFor(h)).built.facts.tx)!), undefined);
  });

  it("/settle refused: 402 with the reason, no log; a settle that lands later is still recorded from the mirror", async () => {
    const h = await setup();
    const { sig, built } = await payFor(h);
    h.fac.settleMode = "refuse-lands";
    h.fac.landAfterReads = 2;
    const r = await get(h, h.listing, sig);
    assert.equal(r.status, 402);
    assert.deepEqual(r.body, { error: "transaction_failed", stage: "settle" });
    await waitFor(() => h.store.saleFor(built.facts.tx) !== undefined);
    assert.equal(h.resource.pendingCount, 0);
  });

  it("/settle with no answer: 402 settlement_pending; nothing recorded when the mirror never shows it", async () => {
    const h = await setup();
    const { sig, built } = await payFor(h);
    h.fac.settleMode = "timeout";
    const r = await get(h, h.listing, sig);
    assert.deepEqual([r.status, r.body], [402, { error: "settlement_pending", stage: "settle" }]);
    await waitFor(() => h.resource.pendingCount === 0, 5000);
    assert.equal(h.store.saleFor(built.facts.tx), undefined);
    assert.ok(h.lines.some((l) => l.includes("never showed on the mirror")));
  });

  it("an `accepted` that differs from the requirement issued now: 402, nothing sent to the facilitator", async () => {
    const h = await setup();
    const { built } = await payFor(h);
    const tampered = { ...built.payload, accepted: { ...built.payload.accepted, amount: "1" } };
    const r = await get(h, h.listing, Buffer.from(JSON.stringify(tampered)).toString("base64"));
    assert.equal(r.status, 402);
    assert.deepEqual(r.body, { error: "requirements_changed", stage: "check" });
    // the price changed on Arkiv after the 402: the old payment no longer matches
    h.arkiv.listings[0].spec.values.price = "0.25";
    const r2 = await get(h, h.listing, built.header["PAYMENT-SIGNATURE"]);
    assert.deepEqual(r2.body, { error: "requirements_changed", stage: "check" });
    assert.equal(h.fac.calls.length, 0);
  });

  it("a garbled header: 402 invalid_payment", async () => {
    const h = await setup();
    const r = await get(h, h.listing, "not-base64-json");
    assert.deepEqual([r.status, r.body], [402, { error: "invalid_payment", stage: "check" }]);
  });

  it("a log that does not hash to log_h is never served, and never settled", async () => {
    const h = await setup();
    const { sig } = await payFor(h);
    h.arkiv.runs[0].spec.values.log_enc = encryptGhost(GHOST, h.logH, new Uint8Array(64));
    const r = await get(h, h.listing, sig);
    assert.deepEqual([r.status, r.body], [404, { error: "not_for_sale" }]);
    assert.deepEqual(h.fac.ops(), ["verify"]);
    assert.ok(h.lines.some((l) => l.includes("does not match its log_h")));
  });

  it("facilitator unreachable at /verify: 503, nothing settled", async () => {
    const h = await setup();
    const { sig } = await payFor(h);
    h.fac.verifyDown = true;
    const r = await get(h, h.listing, sig);
    assert.deepEqual([r.status, r.body], [503, { error: "hedera_unavailable" }]);
  });

  it("two identical payments at once settle once", async () => {
    const h = await setup();
    const { sig } = await payFor(h);
    const [a, b] = await Promise.all([get(h, h.listing, sig), get(h, h.listing, sig)]);
    assert.deepEqual([a.status, b.status], [200, 200]);
    assert.equal(h.fac.ops().filter((o) => o === "settle").length, 1);
  });

  it("sha256 of the served log is the listing's log_h", async () => {
    const h = await setup();
    const { sig } = await payFor(h);
    const r = await get(h, h.listing, sig);
    assert.equal(createHash("sha256").update(Buffer.from(r.body!.log, "base64")).digest("hex"), h.logH);
  });
});

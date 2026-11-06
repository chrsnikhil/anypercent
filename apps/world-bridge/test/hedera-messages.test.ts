/** The market topic's messages: exact bytes, key order, one chunk at every field's maximum length. */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { HCS_MAX_BYTES, intentMessage, listingMessage, MessageTooLarge, parseMessage, receiptMessage, seqNumber, smokeMessage } from "../src/hedera/messages.js";
import { parseTxId, txAt, txDash, txValidStartMs, hashscan, transfersMatch } from "../src/hedera/net.js";

const text = (b: Uint8Array) => Buffer.from(b).toString("utf8");
const K = `0x${"34cd".repeat(16)}`;
const R = `0x${"12ab".repeat(16)}`;
const H = "f".repeat(64);

describe("HCS messages: exact bytes", () => {
  it("LISTING, with pay_to, exactly as the spec shows it", () => {
    const b = listingMessage({
      book: "ANY-6PS",
      runner: "9f2c4e1a7b3d5f60",
      game: "MDGP",
      frames: 6170,
      price: "0.10",
      pay_to: "0.0.5123456",
      action: "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC to 0.0.5123456 on the public board",
    });
    assert.equal(
      text(b),
      '{"v":1,"t":"LISTING","book":"ANY-6PS","runner":"9f2c4e1a7b3d5f60","game":"MDGP","frames":6170,"price":"0.10","pay_to":"0.0.5123456","action":"List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC to 0.0.5123456 on the public board"}',
    );
  });

  it("LISTING without pay_to has no pay_to key", () => {
    const b = listingMessage({ book: "ANY-6PS", runner: "9f2c4e1a7b3d5f60", game: "MDGP", frames: 6170, price: "0.10", action: "List X 1:42.83 ghost for 0.10 USDC on the public board" });
    assert.ok(!text(b).includes("pay_to"));
    assert.ok(text(b).startsWith('{"v":1,"t":"LISTING",'));
  });

  it("INTENT, keys in order, no spaces", () => {
    const b = intentMessage({
      id: "p-3f9c0a1b",
      buyer: "ANY-K2Q",
      seller: "ANY-6PS",
      game: "MDGP",
      listing: K,
      run: R,
      log_h: H,
      pay_to: "0.0.5123456",
      amount: "0.10",
      asset: "0.0.429274",
      why: { you: 6290, target: 6170 },
      left_today: "0.90",
    });
    assert.equal(
      text(b),
      `{"v":1,"t":"INTENT","id":"p-3f9c0a1b","buyer":"ANY-K2Q","seller":"ANY-6PS","game":"MDGP","listing":"${K}","run":"${R}","log_h":"${H}","pay_to":"0.0.5123456","amount":"0.10","asset":"0.0.429274","why":{"you":6290,"target":6170},"left_today":"0.90"}`,
    );
    assert.ok(text(intentMessage({ ...JSON.parse(text(b)), why: { you: null, target: 6170 } })).includes('"why":{"you":null,"target":6170}'));
  });

  it("RECEIPT, keys in order", () => {
    const b = receiptMessage({
      id: "p-3f9c0a1b",
      intent: 42,
      tx: "0.0.9185802@1762412349.000000123",
      from: "0.0.6001234",
      pay_to: "0.0.5123456",
      amount: "0.10",
      asset: "0.0.429274",
      run: R,
      mirror: "SUCCESS",
      late: false,
    });
    assert.equal(
      text(b),
      `{"v":1,"t":"RECEIPT","id":"p-3f9c0a1b","intent":42,"tx":"0.0.9185802@1762412349.000000123","from":"0.0.6001234","pay_to":"0.0.5123456","amount":"0.10","asset":"0.0.429274","run":"${R}","mirror":"SUCCESS","late":false}`,
    );
  });

  it("SMOKE parses back", () => {
    assert.deepEqual(parseMessage(smokeMessage(3, "x")), { v: 1, t: "SMOKE", n: 3, at: "x" });
    assert.equal(parseMessage(Buffer.from("not json")), null);
    assert.equal(parseMessage(Buffer.from('{"v":2,"t":"X"}')), null);
  });

  it("sequence numbers: a Long's toString becomes a JSON number", () => {
    assert.equal(seqNumber({ toString: () => "41" }), 41);
    assert.equal(seqNumber("42"), 42);
    assert.equal(seqNumber(null), null);
  });
});

describe("HCS messages: one chunk at every field's maximum length", () => {
  const maxBook = "ANY-ZZZZZZZZ";
  const maxAcct = "0.0.9999999999";
  const maxPrice = "10000.00";
  const maxFrames = 0xffffffff;

  it("LISTING with a 160-character action of 3-byte characters (the worst case) fits", () => {
    const b = listingMessage({ book: maxBook, runner: "f".repeat(16), game: "ZIPG", frames: maxFrames, price: maxPrice, pay_to: maxAcct, action: "€".repeat(160) });
    assert.ok(b.length <= HCS_MAX_BYTES, `${b.length} B`);
    const quoted = listingMessage({ book: maxBook, runner: "f".repeat(16), game: "ZIPG", frames: maxFrames, price: maxPrice, pay_to: maxAcct, action: '"\\'.repeat(80) });
    assert.ok(quoted.length <= HCS_MAX_BYTES, `${quoted.length} B`);
  });

  it("INTENT and RECEIPT at maximum lengths fit", () => {
    const i = intentMessage({ id: "p-ffffffff", buyer: maxBook, seller: maxBook, game: "ZIPG", listing: K, run: R, log_h: H, pay_to: maxAcct, amount: maxPrice, asset: maxAcct, why: { you: maxFrames, target: maxFrames }, left_today: maxPrice });
    assert.ok(i.length <= HCS_MAX_BYTES, `${i.length} B`);
    const r = receiptMessage({ id: "p-ffffffff", intent: Number.MAX_SAFE_INTEGER, tx: `${maxAcct}@999999999999.999999999`, from: maxAcct, pay_to: maxAcct, amount: maxPrice, asset: maxAcct, run: R, mirror: "SUCCESS", late: true });
    assert.ok(r.length <= HCS_MAX_BYTES, `${r.length} B`);
  });

  it("anything over 1024 B is refused before it could become chunks", () => {
    assert.throws(() => listingMessage({ book: "ANY-6PS", runner: "f".repeat(16), game: "MDGP", frames: 1, price: "0.10", action: "x".repeat(1100) }), MessageTooLarge);
  });
});

describe("transaction ids and HashScan links", () => {
  it("both forms parse; nanos pad to 9 digits", () => {
    assert.deepEqual(parseTxId("0.0.9185802@1762412349.123"), { account: "0.0.9185802", seconds: "1762412349", nanos: "000000123" });
    assert.equal(txAt("0.0.9185802-1762412349-000000123"), "0.0.9185802@1762412349.000000123");
    assert.equal(txDash("0.0.9185802@1762412349.000000123"), "0.0.9185802-1762412349-000000123");
    assert.equal(txAt("mock-1a2b3c4d"), null);
    assert.equal(txValidStartMs("0.0.1@1762412349.500000000"), 1762412349500);
  });

  it("links", () => {
    assert.equal(hashscan.tx("0.0.9185802@1762412349.000000123"), "https://hashscan.io/testnet/transaction/0.0.9185802-1762412349-000000123");
    assert.equal(hashscan.topic("0.0.8001"), "https://hashscan.io/testnet/topic/0.0.8001");
    assert.equal(hashscan.message("1762412351.000000001"), "https://hashscan.io/testnet/transaction/1762412351.000000001/message");
    assert.equal(hashscan.account("0.0.5123456"), "https://hashscan.io/testnet/account/0.0.5123456");
  });

  it("transfersMatch: exactly amount from payer to payTo, nothing else of that token", () => {
    const tx = (rows: Array<[string, bigint]>) => ({ id: "x", consensusAt: "1", result: "SUCCESS", name: "CRYPTOTRANSFER", entityId: null, chargedFee: 0n, tokenTransfers: rows.map(([account, amount]) => ({ token: "0.0.429274", account, amount })) });
    assert.equal(transfersMatch(tx([["0.0.1", -100000n], ["0.0.2", 100000n]]), "0.0.429274", "0.0.1", "0.0.2", 100000n), true);
    assert.equal(transfersMatch(tx([["0.0.1", -100000n], ["0.0.3", 100000n]]), "0.0.429274", "0.0.1", "0.0.2", 100000n), false);
    assert.equal(transfersMatch(tx([["0.0.1", -200000n], ["0.0.2", 100000n], ["0.0.3", 100000n]]), "0.0.429274", "0.0.1", "0.0.2", 100000n), false);
  });
});

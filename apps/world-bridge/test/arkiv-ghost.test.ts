/** Listed ghosts: the HKDF + AES-256-GCM sealing, and POST /arkiv/ghost's rules. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { describe, it } from "node:test";
import { decryptGhost, encryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { MockPayments } from "../src/arkiv/payments.js";
import { ArkivService, RouteError } from "../src/arkiv/service.js";
import { Store } from "../src/store.js";
import { CHECKER, FakeArkiv, makeLog, STRANGER, WALLET_A } from "./fake-arkiv.js";
import { SECRET, tempDir } from "./helpers.js";

const GHOST = "cd".repeat(32);

describe("ghost crypto", () => {
  const log = makeLog("MDGP");
  const logH = sha256Hex(log);

  it("round trip: nonce(12) || ciphertext || tag(16)", () => {
    const sealed = encryptGhost(GHOST, logH, log);
    assert.equal(sealed.length, 12 + log.length + 16);
    assert.deepEqual(decryptGhost(GHOST, logH, sealed), log);
  });

  it("the wrong secret, or another log's key, opens nothing", () => {
    const sealed = encryptGhost(GHOST, logH, log);
    assert.equal(decryptGhost("ef".repeat(32), logH, sealed), null);
    assert.equal(decryptGhost(GHOST, "0".repeat(64), sealed), null);
  });

  it("a flipped byte fails the tag", () => {
    const sealed = encryptGhost(GHOST, logH, log);
    sealed[20] ^= 1;
    assert.equal(decryptGhost(GHOST, logH, sealed), null);
    assert.equal(decryptGhost(GHOST, logH, new Uint8Array(10)), null);
  });

  it("every sealing takes a fresh nonce", () => {
    const a = encryptGhost(GHOST, logH, log);
    const b = encryptGhost(GHOST, logH, log);
    assert.notDeepEqual(a.subarray(0, 12), b.subarray(0, 12));
    assert.notDeepEqual(a, b);
  });

  it("the key is HKDF-SHA256(secret, salt = log_h bytes, info 'anypercent ghost v1')", async () => {
    const { createDecipheriv, hkdfSync } = await import("node:crypto");
    const sealed = Buffer.from(encryptGhost(GHOST, logH, log));
    const key = Buffer.from(hkdfSync("sha256", Buffer.from(GHOST, "hex"), Buffer.from(logH, "hex"), "anypercent ghost v1", 32));
    const d = createDecipheriv("aes-256-gcm", key, sealed.subarray(0, 12));
    d.setAuthTag(sealed.subarray(sealed.length - 16));
    assert.deepEqual(Uint8Array.from(Buffer.concat([d.update(sealed.subarray(12, sealed.length - 16)), d.final()])), log);
  });
});

function service(over: { mock?: boolean; arkiv?: FakeArkiv } = {}) {
  const store = new Store(tempDir(), SECRET);
  const arkiv = over.arkiv ?? new FakeArkiv();
  const lines: string[] = [];
  const svc = new ArkivService({
    publicRpc: "https://rpc.example",
    chainId: 7794095,
    season: 1,
    priceC: 10,
    checker: CHECKER,
    arkiv,
    publisher: null,
    payments: new MockPayments(over.mock ?? true, store),
    ghostSecret: GHOST,
    problems: [],
    boardFile: "nope",
    snapshotFile: "nope",
    log: (l) => lines.push(l),
  });
  return { svc, arkiv, store, lines };
}

/** A console's listed run (WALLET_A), stamped by the checker unless `stamp` is false. */
function listedRun(arkiv: FakeArkiv, log: Uint8Array, over: Record<string, unknown> = {}, creator = WALLET_A, stamp = true): string {
  const logH = sha256Hex(log);
  return arkiv.addRun(
    { game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames: 6170, log_h: logH, runner: "0123456789abcdef", book: "ANY-6PS", human: true, credential: "Orb", tool: "t", log_enc: encryptGhost(GHOST, logH, log), ...over },
    creator,
    { stamp },
  );
}

async function refused(p: Promise<unknown>, status: number, error: string) {
  await assert.rejects(p, (e: unknown) => e instanceof RouteError && e.status === status && e.body.error === error && e.body.failure === "buy_load_fail");
}

describe("POST /arkiv/ghost", () => {
  const log = makeLog("MDGP");

  it("a listed ghost with a mock receipt (flag on): decrypted, and it hashes to log_h", async () => {
    const { svc, arkiv, lines } = service();
    const run = listedRun(arkiv, log);
    const out = await svc.ghost({ run, receipt: "mock-1a2b3c4d" });
    assert.deepEqual(Object.keys(out).sort(), ["log", "log_h"]);
    assert.deepEqual(Uint8Array.from(Buffer.from(out.log, "base64")), log);
    assert.equal(out.log_h, createHash("sha256").update(log).digest("hex"));
    assert.ok(!lines.join("\n").includes(GHOST));
  });

  it("the same receipt again for the same run is fine (a retry)", async () => {
    const { svc, arkiv } = service();
    const run = listedRun(arkiv, log);
    await svc.ghost({ run, receipt: "mock-1a2b3c4d" });
    await svc.ghost({ run, receipt: "mock-1a2b3c4d" });
  });

  it("402 with the flag off", async () => {
    const { svc, arkiv } = service({ mock: false });
    await refused(svc.ghost({ run: listedRun(arkiv, log), receipt: "mock-1a2b3c4d" }), 402, "payment_required");
  });

  it("402 for a receipt that is not the mock's", async () => {
    const { svc, arkiv } = service();
    await refused(svc.ghost({ run: listedRun(arkiv, log), receipt: "mock-XYZ" }), 402, "payment_required");
    await refused(svc.ghost({ run: listedRun(arkiv, log), receipt: "0.0.123@1700000000" }), 402, "payment_required");
  });

  it("402 for a receipt already spent on another run", async () => {
    const { svc, arkiv } = service();
    const a = listedRun(arkiv, log);
    const b = listedRun(arkiv, makeLog("MDGP", 4, 6461, 64, 5));
    await svc.ghost({ run: a, receipt: "mock-1a2b3c4d" });
    await refused(svc.ghost({ run: b, receipt: "mock-1a2b3c4d" }), 402, "payment_required");
  });

  it("404 for a run no checker stamp names, a stamp naming another wallet, and no run at all", async () => {
    const { svc, arkiv } = service();
    await refused(svc.ghost({ run: listedRun(arkiv, log, {}, WALLET_A, false), receipt: "mock-1a2b3c4d" }), 404, "not_on_board");
    const other = listedRun(arkiv, makeLog("MDGP", 4, 6461, 64, 9), {}, STRANGER, false);
    arkiv.stampRun(other, { console: WALLET_A });
    await refused(svc.ghost({ run: other, receipt: "mock-1a2b3c4d" }), 404, "not_on_board");
    await refused(svc.ghost({ run: `0x${"9".repeat(64)}`, receipt: "mock-1a2b3c4d" }), 404, "not_on_board");
  });

  it("a stamped run with no sealed ghost (a plain log) is not served", async () => {
    const { svc, arkiv, lines } = service();
    const run = arkiv.addRun({ game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames: 6170, log_h: sha256Hex(log), runner: "aaaaaaaaaaaaaaaa", book: "ANY-6PS", human: true, tool: "t", log });
    await refused(svc.ghost({ run, receipt: "mock-00000000" }), 404, "not_on_board");
    assert.match(lines.join("\n"), /has no sealed ghost, not served/);
  });

  it("a log_h mismatch is never served", async () => {
    const { svc, arkiv, lines } = service();
    const wrong = "1".repeat(64);
    const sealedUnderWrong = arkiv.addRun({ game: "MDGP", title: "M", season: 1, rules: 4, frames: 1, log_h: wrong, runner: "r", book: "ANY-6PS", human: true, tool: "t", log_enc: encryptGhost(GHOST, wrong, log) });
    await refused(svc.ghost({ run: sealedUnderWrong, receipt: "mock-1a2b3c4d" }), 404, "not_on_board");
    assert.match(lines.join("\n"), /does not match its log_h, not served/);
  });

  it("400 on a bad body; 503 when Arkiv does not answer or is not configured", async () => {
    const { svc, arkiv } = service();
    await refused(svc.ghost({ run: "0x12", receipt: "mock-1a2b3c4d" }), 400, "bad_body");
    await refused(svc.ghost({ run: `0x${"a".repeat(64)}` }), 400, "bad_body");
    arkiv.readsDown = true;
    await refused(svc.ghost({ run: `0x${"a".repeat(64)}`, receipt: "mock-1a2b3c4d" }), 503, "arkiv_unavailable");
    const bare = new ArkivService({ publicRpc: "x", chainId: 1, season: 1, priceC: 10, checker: null, arkiv: null, publisher: null, payments: new MockPayments(true, { claimReceipt: () => true }), ghostSecret: "", problems: ["ARKIV_CHECKER_KEY"], boardFile: "", snapshotFile: "" });
    await refused(bare.ghost({ run: `0x${"a".repeat(64)}`, receipt: "mock-1a2b3c4d" }), 503, "arkiv_not_configured");
  });
});

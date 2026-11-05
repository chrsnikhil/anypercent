/** The store's approvals (keyed by sha256(jti)) and receipts, and both providers recording approvals. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, before, describe, it } from "node:test";
import { AgentPass } from "../src/agentpass.js";
import { nullifierKey } from "../src/hmac.js";
import { IdkitApprovals } from "../src/idkit-approvals.js";
import type { DeviceGrantClient, PollResult } from "../src/oidc.js";
import { approvalKey, Store } from "../src/store.js";
import { ACTION, confirmed, FakeWorld, SESSION_A, sessionProof } from "./fake-world.js";
import { CLIENT_ID, idToken, ISS, makeKeys, ORB, SECRET, tempDir, waitFor, type TestKeys } from "./helpers.js";

const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const TEXT = "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC on the public board";

describe("Store: listing approvals", () => {
  it("records once, finds by jti, keeps the jti off disk", () => {
    const dir = tempDir();
    const store = new Store(dir, SECRET);
    store.recordApproval("jti-secret-value", "ANY-6PS", sha(TEXT), 100);
    store.recordApproval("jti-secret-value", "ANY-OTHER", "x", 200);
    assert.deepEqual(store.approvalFor("jti-secret-value"), { book: "ANY-6PS", action_sha: sha(TEXT), at: 100 });
    assert.equal(store.approvalFor("nope"), undefined);
    const disk = readFileSync(join(dir, "state.json"), "utf8");
    assert.ok(!disk.includes("jti-secret-value"));
    assert.ok(disk.includes(approvalKey("jti-secret-value")));
  });

  it("spendApproval binds one log: spent, then same for that log, other for any other; persists", () => {
    const dir = tempDir();
    const store = new Store(dir, SECRET);
    store.recordApproval("j", "ANY-6PS", "s", 1);
    assert.equal(store.spendApproval("j", "a".repeat(64)), "spent");
    assert.equal(store.spendApproval("j", "a".repeat(64)), "same");
    assert.equal(store.spendApproval("j", "b".repeat(64)), "other");
    assert.equal(store.spendApproval("unknown", "a".repeat(64)), "unknown");
    const again = new Store(dir, SECRET);
    assert.equal(again.spendApproval("j", "b".repeat(64)), "other");
  });

  it("the write's result is kept with the approval and found by log", () => {
    const store = new Store(tempDir(), SECRET);
    store.recordApproval("j", "ANY-6PS", "s", 1);
    store.spendApproval("j", "a".repeat(64));
    store.setApprovalResult("j", { run: "0x1", listing: "0x2", tx: "0x3" });
    assert.deepEqual(store.resultForLog("a".repeat(64)), { run: "0x1", listing: "0x2", tx: "0x3" });
    assert.equal(store.resultForLog("b".repeat(64)), undefined);
  });

  it("a receipt pays for one run only, across restarts", () => {
    const dir = tempDir();
    const store = new Store(dir, SECRET);
    assert.equal(store.claimReceipt("mock-1a2b3c4d", "0xAA"), true);
    assert.equal(store.claimReceipt("mock-1a2b3c4d", "0xaa"), true);
    assert.equal(store.claimReceipt("mock-1a2b3c4d", "0xbb"), false);
    assert.equal(new Store(dir, SECRET).claimReceipt("mock-1a2b3c4d", "0xbb"), false);
  });

  it("an old state.json without approvals or receipts still loads", () => {
    const dir = tempDir();
    const s1 = new Store(dir, SECRET);
    s1.claimBook(nullifierKey(SECRET, "a", "n"), "Orb", "r", 1);
    const s2 = new Store(dir, SECRET);
    assert.equal(s2.approvalFor("x"), undefined);
    assert.equal(s2.claimReceipt("mock-00000000", "0x1"), true);
  });
});

let keys: TestKeys;
before(async () => {
  keys = await makeKeys();
});
const stops: Array<() => void> = [];
afterEach(() => {
  while (stops.length) stops.pop()!();
});

describe("both approval providers record what they grant", () => {
  it("IDKit: on success, store.recordApproval(jti, book, sha256(action))", async () => {
    const store = new Store(tempDir(), SECRET);
    const book = store.claimBook(nullifierKey(SECRET, ACTION, "nil_rec"), "Orb", "runner", 1, SESSION_A).record.book;
    const ap = new IdkitApprovals({ deps: new FakeWorld((signal) => [confirmed(sessionProof(signal))]), store, secret: SECRET, action: ACTION, environment: "staging", pollMs: 2 });
    stops.push(() => ap.stopAll());
    const { id } = await ap.start(book, TEXT);
    await waitFor(() => ap.view(id)?.stage === "done");
    const v = ap.view(id)!;
    assert.equal(v.ok, true);
    const rec = store.approvalFor(String(v.data.jti));
    assert.equal(rec?.book, book);
    assert.equal(rec?.action_sha, sha(TEXT));
    assert.equal(rec?.log_h, undefined);
  });

  it("IDKit: a failed approval records nothing", async () => {
    const store = new Store(tempDir(), SECRET);
    const book = store.claimBook(nullifierKey(SECRET, ACTION, "nil_rec2"), "Orb", "runner", 1).record.book; // no session: ls_wrong
    const ap = new IdkitApprovals({ deps: new FakeWorld(() => []), store, secret: SECRET, action: ACTION, environment: "staging", pollMs: 2 });
    stops.push(() => ap.stopAll());
    const { id } = await ap.start(book, TEXT);
    assert.equal(ap.view(id)?.failure, "ls_wrong");
    assert.equal(readFileSync(join((store as unknown as { dir: string }).dir, "state.json"), "utf8").includes('"approvals": {}'), true);
  });

  it("Agent Pass: on success, the ID token's jti is recorded the same way; after Circle nothing is", async () => {
    const script: PollResult[] = [];
    const idp: DeviceGrantClient = {
      discover: async () => ({ issuer: ISS, acrSupported: [ORB] }),
      start: async () => ({ device_code: "d", user_code: "U", verification_uri: "https://x", expires_in: 1200, interval: 1 }),
      poll: async () => script.shift() ?? ({ kind: "error", error: "authorization_pending", status: 400 } as PollResult),
      keys: () => keys.getKey,
    };
    const store = new Store(tempDir(), SECRET);
    const ap = new AgentPass({ idp, store, secret: SECRET, clientId: CLIENT_ID, msPerSecond: 2 });
    stops.push(() => ap.stopAll());
    script.push({ kind: "tokens", idToken: await idToken(keys.privateKey, { jti: "ap-jti-1" }) });
    const { id } = await ap.start("ANY-7QZ", TEXT);
    await waitFor(() => ap.view(id)?.stage === "done");
    assert.equal(ap.view(id)?.ok, true);
    assert.deepEqual(store.approvalFor("ap-jti-1"), { book: "ANY-7QZ", action_sha: sha(TEXT), at: store.approvalFor("ap-jti-1")!.at });

    const second = await ap.start("ANY-7QZ", TEXT);
    ap.cancel(second.id);
    script.push({ kind: "tokens", idToken: await idToken(keys.privateKey, { jti: "ap-jti-late" }) });
    await new Promise((r) => setTimeout(r, 40));
    assert.equal(store.approvalFor("ap-jti-late"), undefined, "an approval after Circle allows nothing");
  });
});

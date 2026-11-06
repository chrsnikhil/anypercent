/**
 * The console's signer (signer.mjs): its address is the one viem derives from its key; a publish is ONE batch
 * from the console's own wallet whose listing names the run's predicted key, a relist one listing (deleting the
 * listing it replaces); every RPC request names the console; and each way it can fail is the error the launcher
 * maps (no_key, unfunded, rpc, rejected), with nothing key-shaped in the detail. The writes go to a local fake
 * node (tests/fake-node.mjs) that mints keys as the engine does: no network, nothing spent.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { predictEntityKey } from "@arkiv-network/sdk";
import { hexToString } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { classify, handle, liveClients, readKey, redact, USER_AGENT } from "../signer.mjs";
import { ARKIV_ADDRESS, decodeBatch, startFakeNode } from "./fake-node.mjs";

const SIGNER = fileURLToPath(new URL("../signer.mjs", import.meta.url));
// A well-known test key (Hardhat's first account): public, holds nothing anywhere that matters.
const KEY = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
const ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
const LOG_H = "4f1c0d2e9b8a7f6e5d4c3b2a19087f6e5d4c3b2a19087f6e5d4c3b2a19087f6e";
const RUN_KEY = "0x" + "12".repeat(32);
const OLD_LISTING = "0x" + "34".repeat(32);

const dir = mkdtempSync(join(tmpdir(), "arkiv-signer-"));
after(() => rmSync(dir, { recursive: true, force: true }));
function keyFile(text, name = `k${Math.random().toString(36).slice(2)}`) {
  const p = join(dir, name);
  writeFileSync(p, text, { mode: 0o600 });
  return p;
}
const KEY_FILE = keyFile(KEY + "\n", "arkiv-key");
const fast = (o) => liveClients({ ...o, pollingInterval: 20 });

const RUN = {
  values: {
    game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 3, frames: 5025, log_h: LOG_H, runner: "r_0123456789abcdef",
    book: "ANY-6PS", human: true, credential: "orb", tool: "arcade_replay 1", log_enc: { $bytes: "AAECA/r/" },
    s1: 1200, s2: 1300, s3: 1250, s4: 1275, split_kind: "lap",
  },
  flags: { readonly: true, permissionlessExtension: true },
  expiry: { kind: "atDate", date: { $date: "2027-01-30T00:00:00.000Z" }, atLeastDays: 1 },
};
const LISTING = {
  values: { game: "MDGP", season: 1, frames: 5025, log_h: LOG_H, price: "0.1", seller: "ANY-6PS", book: "ANY-6PS", human: true, pay_to: "0.0.12345", hcs: "0.0.777/12" },
  flags: { readonly: true, permissionlessExtension: false },
  expiry: { kind: "days", days: 7 },
};
const publish = (node, extra = {}) => ({ op: "write", key_file: KEY_FILE, rpc: node.url, chain_id: node.chainId, run: RUN, listing: LISTING, run_key: null, replaces: null, ...extra });

function runHelper(stdin) {
  const p = spawnSync(process.execPath, [SIGNER], { input: stdin, encoding: "utf8", timeout: 60_000 });
  return { status: p.status, lines: p.stdout.split("\n").filter((l) => l !== ""), stderr: p.stderr };
}

/** A port nothing listens on (taken, then let go). */
async function closedPort() {
  const s = createServer();
  await new Promise((ok) => s.listen(0, "127.0.0.1", ok));
  const { port } = s.address();
  await new Promise((ok) => s.close(ok));
  return port;
}

// ---- the address ------------------------------------------------------------------------------------------------

test("the helper's address of a fixed key is the address viem derives from it", () => {
  const { status, lines } = runHelper(JSON.stringify({ op: "address", key_file: KEY_FILE }) + "\n");
  assert.equal(status, 0);
  assert.equal(lines.length, 1);
  assert.deepEqual(JSON.parse(lines[0]), { address: privateKeyToAccount(`0x${KEY}`).address });
  assert.equal(JSON.parse(lines[0]).address, ADDRESS);
});

test("a key file may carry 0x, upper case and whitespace; it is read as the same key", async () => {
  for (const text of [`0x${KEY}`, `  ${KEY.toUpperCase()}\r\n`, `0X${KEY}\n`]) {
    assert.equal(readKey(keyFile(text)), `0x${KEY}`);
    assert.deepEqual(await handle({ op: "address", key_file: keyFile(text) }), { address: ADDRESS });
  }
});

test("a missing, empty, short or zero key is no_key, and the file's text never reaches the detail", async () => {
  const cases = [join(dir, "nope"), keyFile(""), keyFile(KEY.slice(2)), keyFile("00".repeat(32)), keyFile(`${KEY}zz`)];
  for (const kf of cases) {
    const r = await handle({ op: "address", key_file: kf });
    assert.equal(r.error, "no_key", kf);
    assert.ok(!r.detail.includes(KEY.slice(0, 16)), r.detail);
  }
});

test("stdin that is not one request object is rejected, on one stdout line", async () => {
  for (const stdin of ["", "nope\n"]) {                                          // the process: two (each start loads viem)
    const { status, lines } = runHelper(stdin);
    assert.equal(status, 2, stdin);
    assert.equal(lines.length, 1, stdin);
    assert.equal(JSON.parse(lines[0]).error, "rejected", stdin);
  }
  for (const req of [undefined, null, [1], "x", { op: "sign", key_file: KEY_FILE }, { op: "address" }, { op: "address", key_file: "" }]) {
    assert.equal((await handle(req)).error, "rejected", JSON.stringify(req));
  }
});

// ---- a publish: run and listing, one batch ------------------------------------------------------------------------

test("a publish is one batch from the console's wallet: the run, then its listing naming the run's predicted key", async () => {
  const node = await startFakeNode({ nonce: 5 });
  try {
    const r = await handle(publish(node), { clients: fast });
    assert.ok(!r.error, JSON.stringify(r));
    assert.equal(node.state.sent.length, 1);
    const { tx, creates, deletes } = decodeBatch(node.state.sent[0]);
    assert.equal(tx.chainId, node.chainId);
    assert.equal(tx.to.toLowerCase(), ARKIV_ADDRESS);
    assert.equal(creates.length, 2);
    assert.deepEqual(deletes, []);
    const runKey = predictEntityKey({ owner: ADDRESS, nonce: 5n, salt: creates[0].salt, chainId: node.chainId }).toLowerCase();
    const listingKey = predictEntityKey({ owner: ADDRESS, nonce: 6n, salt: creates[1].salt, chainId: node.chainId }).toLowerCase();
    assert.deepEqual(r, { tx: r.tx, run: runKey, listing: listingKey });
    assert.match(r.tx, /^0x[0-9a-f]{64}$/);
    assert.equal(creates[1].attrs.run.toLowerCase(), runKey);                       // the listing names the run
    assert.equal(hexToString(creates[0].attrs["arkiv.schema"]), "anypercent.run");
    assert.equal(hexToString(creates[1].attrs["arkiv.schema"]), "anypercent.listing");
    assert.equal(hexToString(creates[0].attrs.log_h), LOG_H);
    assert.equal(creates[0].attrs.log_enc, "0x00010203faff");
    assert.equal(hexToString(creates[1].attrs.pay_to), "0.0.12345");
    assert.ok(node.state.agents.length > 3);
    assert.deepEqual(new Set(node.state.agents), new Set([USER_AGENT]));               // every request names the console
  } finally {
    await node.close();
  }
});

test("a relist writes the listing alone, naming the stamped run, and deletes the listing it replaces", async () => {
  const node = await startFakeNode({ nonce: 9 });
  try {
    const r = await handle(publish(node, { run: null, run_key: RUN_KEY.toUpperCase().replace("0X", "0x"), replaces: OLD_LISTING }), { clients: fast });
    assert.ok(!r.error, JSON.stringify(r));
    const { creates, deletes } = decodeBatch(node.state.sent[0]);
    assert.equal(creates.length, 1);
    assert.deepEqual(deletes, [OLD_LISTING]);
    assert.equal(creates[0].attrs.run, RUN_KEY);
    const listingKey = predictEntityKey({ owner: ADDRESS, nonce: 9n, salt: creates[0].salt, chainId: node.chainId }).toLowerCase();
    assert.deepEqual(r, { tx: r.tx, run: RUN_KEY, listing: listingKey });
  } finally {
    await node.close();
  }
});

test("a relist with nothing to replace deletes nothing", async () => {
  const node = await startFakeNode();
  try {
    const r = await handle(publish(node, { run: null, run_key: RUN_KEY }), { clients: fast });
    assert.ok(!r.error, JSON.stringify(r));
    const { creates, deletes } = decodeBatch(node.state.sent[0]);
    assert.equal(creates.length, 1);
    assert.deepEqual(deletes, []);
  } finally {
    await node.close();
  }
});

// ---- failures -----------------------------------------------------------------------------------------------------

test("a wallet with no tGLM is unfunded, nothing is sent, and the balance read named the console", async () => {
  const node = await startFakeNode({ balance: 0n });
  try {
    const r = await handle(publish(node), { clients: fast });
    assert.equal(r.error, "unfunded");
    assert.equal(node.state.sent.length, 0);
    assert.deepEqual([...node.state.requests].sort(), ["eth_chainId", "eth_getBalance"]);
    assert.deepEqual(new Set(node.state.agents), new Set([USER_AGENT]));
  } finally {
    await node.close();
  }
});

test("a node that refuses the transaction for funds is unfunded too", async () => {
  const node = await startFakeNode({ sendError: { code: -32000, message: "insufficient funds for gas * price + value: balance 1, tx cost 2400000" } });
  try {
    const r = await handle(publish(node), { clients: fast });
    assert.equal(r.error, "unfunded", JSON.stringify(r));
    assert.equal(node.state.sent.length, 1);
  } finally {
    await node.close();
  }
});

test("keys that moved (another writer took the wallet's nonce) are rejected, naming the transaction", async () => {
  const node = await startFakeNode({ nonceSkew: 1 });
  try {
    const r = await handle(publish(node), { clients: fast });
    assert.equal(r.error, "rejected", JSON.stringify(r));
    assert.match(r.detail, /predicted keys moved/);
    assert.match(r.tx, /^0x[0-9a-f]{64}$/);
  } finally {
    await node.close();
  }
});

test("a node on another chain is rejected before anything is sent", async () => {
  const node = await startFakeNode({ chainId: 1 });
  try {
    const r = await handle({ ...publish(node), chain_id: 7794095 }, { clients: fast });
    assert.equal(r.error, "rejected", JSON.stringify(r));
    assert.equal(node.state.sent.length, 0);
  } finally {
    await node.close();
  }
});

test("a node that answers with HTTP errors, or nothing at all, is rpc", async () => {
  const node = await startFakeNode({ status: 503 });
  try {
    const r = await handle(publish(node), { clients: fast });
    assert.equal(r.error, "rpc", JSON.stringify(r));
    assert.ok(!r.detail.includes("127.0.0.1"), r.detail);                         // no URL in the detail
    assert.ok(node.state.agents.every((a) => a === USER_AGENT));
  } finally {
    await node.close();
  }
  const port = await closedPort();
  const r = await handle(publish({ url: `http://127.0.0.1:${port}/`, chainId: 7794095 }), { clients: fast });
  assert.equal(r.error, "rpc", JSON.stringify(r));
});

test("a request the helper cannot write is rejected before the network", async () => {
  const node = await startFakeNode();
  try {
    const bad = [
      { run_key: RUN_KEY },                                                      // both a run and a run_key
      { run: null },                                                             // neither
      { replaces: OLD_LISTING },                                                 // replaces without a relist
      { run: null, run_key: "0x1234" },
      { chain_id: 0 },
      { chain_id: "7794095" },
      { rpc: "ftp://node" },
      { listing: null },
      { listing: { ...LISTING, values: { ...LISTING.values, nickname: "x" } } },  // a column nobody has
      { run: { ...RUN, values: { ...RUN.values, frames: { $big: "nope" } } } },   // not SpecJSON
      { run: { ...RUN, expiry: { kind: "atDate", date: "2027-01-30", atLeastDays: 1 } } }, // a date that is no $date
      { listing: { ...LISTING, values: { ...LISTING.values, price: "a lot" } } }, // a dec that is no number
    ];
    for (const extra of bad) {
      const r = await handle(publish(node, extra), { clients: fast });
      assert.equal(r.error, "rejected", JSON.stringify(extra));
    }
    assert.equal(node.state.requests.length, 0);
  } finally {
    await node.close();
  }
});

test("the reply from the helper process is one stdout line, also on a failure", async () => {
  const port = await closedPort();
  const req = { op: "write", key_file: KEY_FILE, rpc: `http://127.0.0.1:${port}/`, chain_id: 7794095, run: RUN, listing: LISTING };
  const { status, lines } = runHelper(JSON.stringify(req) + "\n");
  assert.equal(status, 2);
  assert.equal(lines.length, 1);
  assert.equal(JSON.parse(lines[0]).error, "rpc");
});

test("classify: funds, the chain refusing, and the node failing", () => {
  assert.equal(classify(Object.assign(new Error("x"), { cause: { name: "InsufficientFundsError", message: "y" } })), "unfunded");
  assert.equal(classify(new Error("Transaction failed: insufficient funds for gas")), "unfunded");
  assert.equal(classify(Object.assign(new Error("x"), { cause: { name: "ContractFunctionRevertedError", message: "y" } })), "rejected");
  assert.equal(classify(new Error("Transaction 0xab reverted. Reason: ExpiryBeyondMaxLifetime")), "rejected");
  assert.equal(classify(Object.assign(new Error("x"), { name: "InvalidValueError" })), "rejected");
  assert.equal(classify(Object.assign(new Error("x"), { cause: { name: "HttpRequestError", message: "HTTP request failed. Status: 429" } })), "rpc");
  assert.equal(classify(Object.assign(new Error("x"), { cause: { name: "TimeoutError", message: "took too long" } })), "rpc");
  assert.equal(classify(new Error("fetch failed")), "rpc");
});

test("redact: no URL, no key, nothing key-shaped; entity keys and tx hashes stay; one short line", () => {
  const text = `failed at https://rpc.example/secret-access-key with 0x${KEY} and ${KEY} for ${RUN_KEY}\nstack`;
  const out = redact(text, [`0x${KEY}`, KEY]);
  assert.ok(!out.includes(KEY) && !out.includes("secret-access-key") && !out.includes("stack"), out);
  assert.ok(out.includes(RUN_KEY), out);
  assert.ok(redact("x".repeat(1000)).length <= 240);
});

#!/usr/bin/env node
/**
 * The console's Arkiv signer (spec: the console owns its records, the server stamps them real). The launcher
 * (handler/arkiv_sign.py) runs `node signer.mjs`, writes one JSON line on stdin and reads one JSON line from
 * stdout; nothing else is ever printed there.
 *
 *   {"op": "address", "key_file"}                        -> {"address"}   (no network)
 *   {"op": "write", "key_file", "rpc", "chain_id", "run", "listing", "run_key", "replaces"}
 *                                                        -> {"tx", "run", "listing"}
 *   any failure                                          -> {"error", "detail"} (and "tx" once one was sent)
 *
 * `run` and `listing` are SpecJSON as the bridge issued them at publish stage `sign` (the bridge's
 * spec-json.ts; decoded here exactly as there). A normal publish has `run` and no `run_key`: the run and its
 * listing go out in ONE executeBatch from the console's wallet, both keys predicted from its own address
 * (predictEntityKeys, count 2) so the listing's `run` names the run's key, exactly as the bridge's old
 * writeRunAndListing did; the keys the chain minted must be the predicted ones. A relist has no `run`, a
 * `run_key` (the already-stamped run) and maybe `replaces` (the console's own older listing): the batch
 * creates the listing alone, its `run` the run_key, and deletes `replaces` in the same transaction.
 *
 * Errors: "no_key" (the key file is missing or holds no key), "unfunded" (the wallet has no tGLM, or not
 * enough for this batch), "rpc" (no usable answer from the node: down, refused, timed out, rate limited) and
 * "rejected" (a request this helper cannot write: not the protocol, not SpecJSON, a value that does not fit
 * its column; or a transaction the chain refused or reverted). `detail` is one short line with URLs, the key
 * and anything key-shaped removed.
 *
 * The key file holds the console's private key as 64 hex digits (handler/arkiv_wallet.py makes it, 0600, in
 * the console's state dir). It is read here and nowhere else, used only to sign, and never printed or sent.
 * Every RPC request names the console in its User-Agent: Rabdi's Cloudflare refuses library defaults with 403.
 */
import { webcrypto } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { createPublicClient, createWalletClient, ExpirationTime } from "@arkiv-network/sdk";
import { defineChain, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { Listing, Run, toSdkValues } from "./schemas.mjs";

// Node 18 has no global WebCrypto; the SDK draws its salts from globalThis.crypto when it makes them.
if (typeof globalThis.crypto?.getRandomValues !== "function") {
  Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true, writable: true });
}

export const USER_AGENT = "AnyPercent-Console/1.0 (+https://github.com/chrsnikhil/anypercent)";
const MAX_REQUEST = 4 << 20;
const KEY_RE = /^0x[0-9a-fA-F]{64}$/;
const RPC_TIMEOUT_MS = 15_000;

// ---- SpecJSON (a copy of apps/world-bridge/src/arkiv/spec-json.ts's decoder; tests/spec-json.test.mjs) ----------

/** A SpecJSON document that does not decode exactly. */
export class SpecJsonError extends Error {}

const B64_RE = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const BIG_RE = /^-?(0|[1-9][0-9]*)$/;
const EXPIRY_KINDS = ["atDate", "days", "hours", "atBlock"];

function decode(v, path) {
  if (v === null || typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new SpecJsonError(`${path}: not a finite number`);
    return v;
  }
  if (Array.isArray(v)) return v.map((x, i) => decode(x, `${path}[${i}]`));
  if (typeof v !== "object") throw new SpecJsonError(`${path}: not JSON`);
  const entries = Object.entries(v);
  const tagged = entries.filter(([k]) => k.startsWith("$"));
  if (tagged.length > 0) {
    if (entries.length !== 1) throw new SpecJsonError(`${path}: a tag must stand alone`);
    const [tag, payload] = entries[0];
    if (typeof payload !== "string") throw new SpecJsonError(`${path}.${tag}: not a string`);
    switch (tag) {
      case "$bytes":
        if (!B64_RE.test(payload)) throw new SpecJsonError(`${path}.$bytes: not base64`);
        return Uint8Array.from(Buffer.from(payload, "base64"));
      case "$big":
        if (!BIG_RE.test(payload)) throw new SpecJsonError(`${path}.$big: not an integer`);
        return BigInt(payload);
      case "$date": {
        const d = new Date(payload);
        if (Number.isNaN(d.getTime()) || d.toISOString() !== payload) throw new SpecJsonError(`${path}.$date: not an ISO date`);
        return d;
      }
      default:
        throw new SpecJsonError(`${path}: unknown tag ${tag}`);
    }
  }
  const out = {};
  for (const [k, x] of entries) out[k] = decode(x, `${path}.${k}`);
  return out;
}

function isObject(v) {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** SpecJSON (parsed, or a JSON string) -> the CreateSpec it encodes ({values, flags, expiry}). Throws SpecJsonError. */
export function fromSpecJson(json) {
  let raw = json;
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw);
    } catch {
      throw new SpecJsonError("spec: not JSON");
    }
  }
  const spec = decode(raw, "spec");
  if (!isObject(spec)) throw new SpecJsonError("spec: not an object");
  const { values, flags, expiry } = spec;
  if (!isObject(values) || values instanceof Uint8Array || values instanceof Date) throw new SpecJsonError("spec.values: not an object");
  if (!isObject(flags) || typeof flags.readonly !== "boolean" || typeof flags.permissionlessExtension !== "boolean") {
    throw new SpecJsonError("spec.flags: readonly and permissionlessExtension must be booleans");
  }
  if (!isObject(expiry) || typeof expiry.kind !== "string" || !EXPIRY_KINDS.includes(expiry.kind)) {
    throw new SpecJsonError("spec.expiry: not a known kind");
  }
  return { values, flags, expiry };
}

/** An issued expiry as the SDK takes it (the bridge's toExpiration), its fields checked first. */
export function toExpiration(e) {
  const num = (v) => typeof v === "number" && Number.isFinite(v);
  switch (e.kind) {
    case "atDate":
      if (!(e.date instanceof Date) || !num(e.atLeastDays)) throw new SpecJsonError("spec.expiry: atDate needs a date and atLeastDays");
      return ExpirationTime.atDate(e.date, { atLeast: ExpirationTime.fromDays(e.atLeastDays) });
    case "days":
      if (!num(e.days)) throw new SpecJsonError("spec.expiry: days needs a number");
      return ExpirationTime.fromDays(e.days);
    case "hours":
      if (!num(e.hours)) throw new SpecJsonError("spec.expiry: hours needs a number");
      return ExpirationTime.fromHours(e.hours);
    case "atBlock":
      if (typeof e.block !== "bigint") throw new SpecJsonError("spec.expiry: atBlock needs a $big block");
      return ExpirationTime.atBlock(e.block);
    default:
      throw new SpecJsonError("spec.expiry: not a known kind");
  }
}

// ---- the key, the errors ------------------------------------------------------------------------------------------

/** The key file is missing, unreadable, or does not hold one secp256k1 private key. */
export class KeyFileError extends Error {}

/** A request that is not this helper's protocol. */
export class RequestError extends Error {}

/** The batch landed, but not as asked (the keys moved, or the node named other entities). */
class WriteError extends Error {
  constructor(message, kind, txHash) {
    super(message);
    this.kind = kind;
    this.txHash = txHash;
  }
}

/** The private key in a key file as 0x hex: 64 hex digits, a 0x and surrounding whitespace allowed. */
export function readKey(path) {
  let text;
  try {
    text = readFileSync(path, "ascii");
  } catch (err) {
    throw new KeyFileError(err?.code === "ENOENT" ? "the key file is missing" : "the key file cannot be read");
  }
  let hex = text.trim();
  if (hex.startsWith("0x") || hex.startsWith("0X")) hex = hex.slice(2);
  if (!/^[0-9a-fA-F]{64}$/.test(hex)) throw new KeyFileError("the key file does not hold a key");
  return `0x${hex.toLowerCase()}`;
}

function accountOf(key) {
  try {
    return privateKeyToAccount(key);
  } catch {
    throw new KeyFileError("the key file does not hold a valid key");
  }
}

/** A short reason for a log line: no URLs, no key, nothing key-shaped (the bridge's redact). */
export function redact(text, secrets = []) {
  let out = String(text ?? "");
  for (const s of secrets) if (s) out = out.split(s).join("<redacted>");
  out = out.replace(/https?:\/\/\S+/g, "<url>").replace(/(?<!0x)\b[0-9a-fA-F]{64}\b/g, "<hex>");
  return out.split("\n")[0].slice(0, 240);
}

const REJECTED_NAMES = new Set([
  // the SDK refusing a value or an expiry before anything is sent
  "InvalidValueError", "UntypedValueError", "MissingValueError", "InvalidAttributeNameError", "ConflictingMutationError",
  "TooManyAttributesError", "EntityTooLargeError", "SchemaMismatchError", "UnknownAttributeTypeError",
  "InvalidExpiryError", "InvalidCreationFlagsError", "InvalidSaltError", "SchemaValueError", "SpecJsonError",
  // the chain refusing the transaction, or the node being another chain
  "ContractFunctionRevertedError", "ExecutionRevertedError", "ChainMismatchError", "InvalidChainIdError",
  "IntrinsicGasTooHighError", "TipAboveFeeCapError",
]);
const RPC_NAMES = new Set(["HttpRequestError", "TimeoutError", "WebSocketRequestError", "SocketClosedError", "LimitExceededRpcError", "ResourceUnavailableRpcError"]);

/** Every error in a cause chain, outermost first (viem and the SDK wrap). */
function chainOf(err) {
  const out = [];
  for (let e = err; e && out.length < 12; e = e.cause) out.push(e);
  return out;
}

/** What went wrong, as the launcher tells it: "unfunded", "rejected" or "rpc" (anything else: retry). */
export function classify(err) {
  const chain = chainOf(err);
  const text = chain.map((e) => `${e?.shortMessage ?? ""} ${e?.details ?? ""} ${e?.message ?? ""}`).join(" ");
  if (chain.some((e) => e?.name === "InsufficientFundsError") || /insufficient funds/i.test(text)) return "unfunded";
  if (err instanceof WriteError) return err.kind;
  if (chain.some((e) => RPC_NAMES.has(e?.name))) return "rpc";
  if (chain.some((e) => REJECTED_NAMES.has(e?.name)) || /\brevert/i.test(text)) return "rejected";
  return "rpc";
}

// ---- the chain --------------------------------------------------------------------------------------------------

/**
 * The SDK's public and wallet clients on the issued chain and RPC, every request carrying the console's
 * User-Agent. Tests pass their own factory to handle().
 */
export function liveClients({ rpc, chainId, account, pollingInterval = 1000 }) {
  const chain = defineChain({
    id: chainId,
    name: "Arkiv",
    nativeCurrency: { name: "Golem", symbol: "tGLM", decimals: 18 },
    rpcUrls: { default: { http: [rpc] } },
  });
  const transport = http(rpc, { timeout: RPC_TIMEOUT_MS, retryCount: 1, fetchOptions: { headers: { "User-Agent": USER_AGENT } } });
  return {
    pub: createPublicClient({ chain, transport, pollingInterval }),
    wallet: createWalletClient({ chain, transport, account, pollingInterval }),
  };
}

function keyOrNull(v, name) {
  if (v === undefined || v === null) return null;
  if (typeof v !== "string" || !KEY_RE.test(v)) throw new RequestError(`${name} is not an entity key`);
  return v.toLowerCase();
}

/** The write request, checked and decoded before anything touches the network. */
function parseWrite(req) {
  if (typeof req.rpc !== "string" || !/^https?:\/\/\S+$/.test(req.rpc)) throw new RequestError("rpc is not an http(s) URL");
  if (!Number.isSafeInteger(req.chain_id) || req.chain_id <= 0) throw new RequestError("chain_id is not a chain id");
  const runKey = keyOrNull(req.run_key, "run_key");
  const replaces = keyOrNull(req.replaces, "replaces");
  const hasRun = req.run !== undefined && req.run !== null;
  if (hasRun === (runKey !== null)) throw new RequestError("exactly one of run and run_key");
  if (replaces !== null && runKey === null) throw new RequestError("replaces comes only with run_key (a relist)");
  if (req.listing === undefined || req.listing === null) throw new RequestError("no listing");
  const run = hasRun ? fromSpecJson(req.run) : null;
  const listing = fromSpecJson(req.listing);
  const runCreate = run
    ? { schema: Run, values: toSdkValues("run", run.values), expiration: toExpiration(run.expiry), flags: run.flags }
    : null;
  const listingExpiration = toExpiration(listing.expiry);
  const listingCreate = (k) => ({ schema: Listing, values: toSdkValues("listing", { ...listing.values, run: k }), expiration: listingExpiration, flags: listing.flags });
  listingCreate(runKey ?? `0x${"00".repeat(32)}`); // every listing value checked now, before the network
  return { rpc: req.rpc, chainId: req.chain_id, runCreate, listingCreate, runKey, replaces };
}

async function write(w, account, clients) {
  const { pub, wallet } = clients({ rpc: w.rpc, chainId: w.chainId, account });
  // The issued node must be the issued chain: keys are predicted from the chain id, and viem signs for it
  // without asking the node.
  const [chainId, balance] = await Promise.all([pub.getChainId(), pub.getBalance({ address: account.address })]);
  if (chainId !== w.chainId) throw new WriteError(`the node is chain ${chainId}, not the issued ${w.chainId}`, "rejected");
  if (balance === 0n) throw Object.assign(new Error("insufficient funds: the console's wallet holds no tGLM"), { name: "InsufficientFundsError" });
  if (w.runCreate) {
    const [r, l] = await pub.predictEntityKeys({ owner: account.address, count: 2 });
    const res = await wallet.executeBatch({
      creates: [
        { ...w.runCreate, salt: r.salt },
        { ...w.listingCreate(r.key), salt: l.salt },
      ],
    });
    const made = (res.createdEntities ?? []).map((k) => String(k).toLowerCase());
    if (made.length !== 2 || made[0] !== r.key.toLowerCase() || made[1] !== l.key.toLowerCase()) {
      // Another writer used this wallet's entity nonce in between: the listing names a key that moved.
      throw new WriteError(`the predicted keys moved (tx ${res.txHash})`, "rejected", res.txHash);
    }
    return { tx: res.txHash, run: made[0], listing: made[1] };
  }
  const res = await wallet.executeBatch({
    creates: [w.listingCreate(w.runKey)],
    ...(w.replaces ? { deletes: [{ entityKey: w.replaces }] } : {}),
  });
  const made = (res.createdEntities ?? []).map((k) => String(k).toLowerCase());
  if (made.length !== 1) throw new WriteError(`the node named ${made.length} new entities for one listing (tx ${res.txHash})`, "rpc", res.txHash);
  return { tx: res.txHash, run: w.runKey, listing: made[0] };
}

/** The request checked: null for an address, the decoded write otherwise. Anything wrong is a RequestError. */
function checked(req) {
  if (!isObject(req)) throw new RequestError("the request is not one JSON object");
  if (typeof req.key_file !== "string" || req.key_file === "") throw new RequestError("no key_file");
  if (req.op === "address") return null;
  if (req.op !== "write") throw new RequestError(`unknown op ${String(req.op).slice(0, 20)}`);
  try {
    return parseWrite(req);
  } catch (err) {
    throw err instanceof RequestError ? err : new RequestError(`${err?.name ?? "Error"}: ${err?.message ?? err}`);
  }
}

/** One request -> one reply object. Never throws. `clients` makes the SDK clients (liveClients unless a test). */
export async function handle(req, { clients = liveClients } = {}) {
  let key = null;
  try {
    const w = checked(req);
    key = readKey(req.key_file);
    const account = accountOf(key);
    if (!w) return { address: account.address };
    return await write(w, account, clients);
  } catch (err) {
    const secrets = key ? [key, key.slice(2)] : [];
    const detail = redact(err?.shortMessage ?? err?.message ?? String(err), secrets);
    const kind = err instanceof KeyFileError ? "no_key" : err instanceof RequestError ? "rejected" : classify(err);
    const tx = err?.txHash ?? chainOf(err).find((e) => typeof e?.txHash === "string")?.txHash;
    return { error: kind, detail, ...(typeof tx === "string" && KEY_RE.test(tx) ? { tx } : {}) };
  }
}

async function readStdin() {
  const chunks = [];
  let n = 0;
  for await (const c of process.stdin) {
    n += c.length;
    if (n > MAX_REQUEST) throw new RequestError("the request is too large");
    chunks.push(c);
  }
  return Buffer.concat(chunks).toString("utf8");
}

/** stdin one JSON line -> stdout one JSON line; exit 0 on success, 2 on an error reply. */
export async function main() {
  // stdout carries the reply alone: anything a library logs goes to stderr.
  console.log = console.info = console.debug = console.error;
  let reply;
  try {
    const line = (await readStdin()).split("\n").find((l) => l.trim() !== "") ?? "";
    let req;
    try {
      req = JSON.parse(line);
    } catch {
      req = undefined;
    }
    reply = await handle(req);
  } catch (err) {
    reply = { error: "rejected", detail: redact(err?.message ?? String(err)) };
  }
  process.stdout.write(JSON.stringify(reply) + "\n", () => process.exit(reply.error ? 2 : 0));
}

function invokedDirectly() {
  try {
    return !!process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href;
  } catch {
    return false;
  }
}

if (invokedDirectly()) main();

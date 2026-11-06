/**
 * A local stand-in for an Arkiv node, over real HTTP on 127.0.0.1, for the signer's tests: just enough JSON-RPC
 * for the SDK to predict keys, estimate, sign and send one batch and read its receipt. It mints entity keys the
 * way the engine does (predictEntityKey from the owner's entity nonce and each create's salt), so a test sees
 * exactly what the console's transaction asked for and what it would have created. Nothing leaves this machine.
 *
 * Options: balance (wei, default 1 tGLM), chainId, nonce (the owner's entity nonce), sendError (a JSON-RPC error
 * for eth_sendRawTransaction), status (HTTP status for every reply; 200), nonceSkew (mint keys as if another
 * writer had taken that many nonces first).
 */
import { createServer } from "node:http";
import { ENTITY_EVENTS_ABI, predictEntityKey } from "@arkiv-network/sdk";
import {
  decodeAbiParameters,
  decodeFunctionData,
  encodeAbiParameters,
  encodeEventTopics,
  keccak256,
  parseAbi,
  parseAbiParameters,
  parseTransaction,
  recoverTransactionAddress,
  toHex,
} from "viem";

export const ARKIV_ADDRESS = "0x4400000000000000000000000000000000000044";
const EXECUTE_ABI = parseAbi(["function execute((uint8 operation, bytes operationData)[] ops) external returns (bytes32[] keys)"]);
const CREATE_PARAMS = parseAbiParameters("(uint128 salt, uint64 expiresAt, uint64 minLifetime, uint8 creationFlags, (bytes32 name, uint8 typeId, bytes value)[] attributes)");
const DELETE_PARAMS = parseAbiParameters("(bytes32 entityKey)");
const BLOCK = 0x100;

/** One batch as the node read it: its creates (salt, attributes by name) and deletes. */
export function decodeBatch(raw) {
  const tx = parseTransaction(raw);
  const { args } = decodeFunctionData({ abi: EXECUTE_ABI, data: tx.data });
  const creates = [];
  const deletes = [];
  for (const op of args[0]) {
    if (op.operation === 1) {
      const [c] = decodeAbiParameters(CREATE_PARAMS, op.operationData);
      const attrs = {};
      for (const a of c.attributes) attrs[Buffer.from(a.name.slice(2), "hex").toString("utf8").replace(/\0+$/, "")] = a.value;
      creates.push({ salt: c.salt, creationFlags: c.creationFlags, attrs });
    } else if (op.operation === 5) {
      deletes.push(decodeAbiParameters(DELETE_PARAMS, op.operationData)[0].entityKey);
    } else {
      throw new Error(`the fake node does not take operation ${op.operation}`);
    }
  }
  return { tx, creates, deletes };
}

export async function startFakeNode(opts = {}) {
  const chainId = opts.chainId ?? 7794095;
  const state = {
    requests: [],
    agents: [],
    sent: [],
    receipts: new Map(),
    nonce: BigInt(opts.nonce ?? 5),
  };
  const word = (n) => toHex(BigInt(n), { size: 32 });

  async function answer(method, params) {
    switch (method) {
      case "eth_chainId":
        return toHex(chainId);
      case "eth_getBalance":
        return toHex(BigInt(opts.balance ?? 10n ** 18n));
      case "eth_call":
        return word(state.nonce); // entityNonce(owner): the only view the SDK calls
      case "eth_blockNumber":
        return toHex(BLOCK + state.sent.length);
      case "eth_estimateGas":
        return toHex(300_000);
      case "eth_getTransactionCount":
        return toHex(state.sent.length);
      case "eth_maxPriorityFeePerGas":
        return toHex(1);
      case "eth_gasPrice":
        return toHex(8);
      case "eth_getBlockByNumber":
        return {
          number: toHex(BLOCK + state.sent.length), hash: word(1), parentHash: word(0), timestamp: toHex(1_800_000_000),
          baseFeePerGas: toHex(7), gasLimit: toHex(30_000_000), gasUsed: toHex(0), miner: ARKIV_ADDRESS, nonce: "0x0000000000000000",
          difficulty: "0x0", totalDifficulty: "0x0", extraData: "0x", logsBloom: `0x${"00".repeat(256)}`, sha3Uncles: word(0),
          size: "0x0", stateRoot: word(0), receiptsRoot: word(0), transactionsRoot: word(0), transactions: [], uncles: [],
          mixHash: word(0),
        };
      case "eth_sendRawTransaction": {
        const raw = params[0];
        state.sent.push(raw);
        if (opts.sendError) throw opts.sendError;
        const from = await recoverTransactionAddress({ serializedTransaction: raw });
        const { creates } = decodeBatch(raw);
        const hash = keccak256(raw);
        const skew = BigInt(opts.nonceSkew ?? 0);
        const logs = creates.map((c, i) => {
          const entityKey = predictEntityKey({ owner: from, nonce: state.nonce + skew + BigInt(i), salt: c.salt, chainId });
          return {
            address: ARKIV_ADDRESS,
            topics: encodeEventTopics({ abi: ENTITY_EVENTS_ABI, eventName: "EntityCreated", args: { entityKey, owner: from } }),
            data: encodeAbiParameters(parseAbiParameters("uint64 expiresAt, uint8 creationFlags"), [999_999n, c.creationFlags]),
            blockHash: word(2), blockNumber: toHex(BLOCK + state.sent.length), logIndex: toHex(i), transactionHash: hash,
            transactionIndex: "0x0", removed: false,
          };
        });
        state.nonce += skew + BigInt(creates.length);
        state.receipts.set(hash, {
          blockHash: word(2), blockNumber: toHex(BLOCK + state.sent.length), contractAddress: null, cumulativeGasUsed: toHex(100_000),
          effectiveGasPrice: toHex(8), from, gasUsed: toHex(100_000), logs, logsBloom: `0x${"00".repeat(256)}`, status: "0x1",
          to: ARKIV_ADDRESS, transactionHash: hash, transactionIndex: "0x0", type: "0x2",
        });
        return hash;
      }
      case "eth_getTransactionReceipt":
        return state.receipts.get(params[0]) ?? null;
      case "eth_getTransactionByHash":
        return null;
      default:
        throw { code: -32601, message: `the fake node has no ${method}` };
    }
  }

  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", async () => {
      state.agents.push(req.headers["user-agent"]);
      if (opts.status && opts.status !== 200) {
        res.writeHead(opts.status, { "Content-Type": "text/plain" }).end("no");
        return;
      }
      const one = async (m) => {
        state.requests.push(m.method);
        try {
          return { jsonrpc: "2.0", id: m.id, result: await answer(m.method, m.params ?? []) };
        } catch (e) {
          return { jsonrpc: "2.0", id: m.id, error: { code: e.code ?? -32000, message: e.message ?? String(e) } };
        }
      };
      const msg = JSON.parse(body);
      const out = Array.isArray(msg) ? await Promise.all(msg.map(one)) : await one(msg);
      res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(out));
    });
  });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}/`,
    chainId,
    state,
    close: () => new Promise((ok) => server.close(ok)),
  };
}

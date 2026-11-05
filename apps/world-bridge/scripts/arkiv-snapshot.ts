/**
 * npm run arkiv:snapshot [-- --checker 0x...]
 *
 * Writes arkiv/snapshot.json at the repository root: the chain id, the block (and its time, so the
 * web board can still say "until about ..."), the checker, the season, the exact query strings, and
 * the raw rows of Q1 and Q2 for every arcade game. Reads only; no key needed (the checker defaults to
 * ARKIV_CHECKER_KEY's address). Commit it at freeze: testnets get retired, and the web board falls
 * back to it when the RPC does not answer. Never selects ghost bytes.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SdkArkiv } from "../src/arkiv/client.js";
import * as Q from "../src/arkiv/queries.js";
import { GAME_IDS, LISTING_SCHEMA, RUN_SCHEMA } from "../src/arkiv/schema.js";
import { arkivRpcUrl, PRIVATE_KEY_RE } from "../src/config.js";
import { arg, clientsFor, die, loadEnv, repoRoot, why } from "./arkiv-common.js";

const cfg = loadEnv();
const ak = cfg.arkiv;

async function main(): Promise<void> {
  const given = arg("checker");
  const address = given ?? (PRIVATE_KEY_RE.test(ak.checkerKey) ? clientsFor(cfg, ak.checkerKey).address : null);
  if (!address || !/^0x[0-9a-fA-F]{40}$/.test(address)) die("no checker: set ARKIV_CHECKER_KEY or pass --checker 0x...");
  const C = Q.checksum(address);
  const port = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerAddress: C });
  const chainId = await port.chainId();
  const timing = await port.publicClient.getBlockTiming();

  const games: Record<string, { block: string; q1: string; q2: string; runs: unknown[]; listings: unknown[] }> = {};
  let total = 0;
  for (const g of GAME_IDS) {
    const q1 = Q.q1Board(g, ak.season, C);
    const q2 = Q.q2Listings(g, ak.season, C);
    const runs = await port.query(q1, Q.selectOf(Q.RUN_BOARD_ATTRS));
    const listings = await port.query(q2, Q.selectOf(Q.LISTING_ATTRS));
    games[g] = { block: runs.blockNumber.toString(), q1, q2, runs: runs.data, listings: listings.data };
    total += runs.data.length;
    console.log(`${g}: ${runs.data.length} runs, ${listings.data.length} listings (block ${runs.blockNumber})`);
  }

  const snapshot = {
    chain_id: chainId,
    rpc: ak.rpc,
    block: timing.currentBlock.toString(),
    block_time_s: timing.currentBlockTime,
    block_duration_s: timing.blockDuration,
    checker: C,
    season: ak.season,
    schemas: { run: RUN_SCHEMA, listing: LISTING_SCHEMA },
    games,
  };
  const dir = join(repoRoot, "arkiv");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "snapshot.json"), `${JSON.stringify(snapshot, null, 1)}\n`);
  console.log(`wrote arkiv/snapshot.json: chain ${chainId}, block ${timing.currentBlock}, checker ${C}, ${total} runs`);
}

main().catch((err: unknown) => die(`arkiv:snapshot: ${why(err, cfg)}`));

/**
 * npm run arkiv:snapshot [-- --checker 0x...]
 *
 * Writes arkiv/snapshot.json at the repository root: the chain id, the block (and its time, so the
 * web board can still say "until about ..."), the checker, the season, the exact query strings, and
 * for every arcade game the raw pages a board is read from: the checker's stamps (Q1 on stamps),
 * then the runs and listings of every console wallet those stamps name (Q1 and Q2 pinned to that
 * wallet). The web board joins them exactly as it joins a live read (a run counts when a checker
 * stamp names it and its creator is the stamp's console). Reads only; no key needed (the checker
 * defaults to ARKIV_CHECKER_KEY's address). Commit it at freeze: testnets get retired, and the web
 * board falls back to it when the RPC does not answer. Never selects ghost bytes.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SdkArkiv } from "../src/arkiv/client.js";
import * as Q from "../src/arkiv/queries.js";
import { GAME_IDS, LISTING_SCHEMA, RUN_SCHEMA, STAMP_SCHEMA } from "../src/arkiv/schema.js";
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

  const games: Record<string, { block: string; q_stamps: string; stamps: unknown[]; runs: unknown[]; listings: unknown[] }> = {};
  let total = 0;
  for (const g of GAME_IDS) {
    const pages = await port.boardPages(g, ak.season);
    const counted = port.joinPages(pages);
    games[g] = { block: pages.block.toString(), q_stamps: Q.q1Stamps(g, ak.season, C), stamps: pages.stamps, runs: pages.runs, listings: pages.listings };
    total += counted.runs.length;
    console.log(`${g}: ${pages.stamps.length} stamps, ${counted.runs.length} stamped runs, ${counted.listings.length} listings (block ${pages.block})${counted.dropped ? `, ${counted.dropped} dropped` : ""}`);
  }

  const snapshot = {
    chain_id: chainId,
    rpc: ak.rpc,
    block: timing.currentBlock.toString(),
    block_time_s: timing.currentBlockTime,
    block_duration_s: timing.blockDuration,
    checker: C,
    season: ak.season,
    schemas: { run: RUN_SCHEMA, listing: LISTING_SCHEMA, stamp: STAMP_SCHEMA },
    queries: { stamps: Q.Q1_STAMPS_TEMPLATE, runs: Q.Q1_TEMPLATE },
    games,
  };
  const dir = join(repoRoot, "arkiv");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "snapshot.json"), `${JSON.stringify(snapshot, null, 1)}\n`);
  console.log(`wrote arkiv/snapshot.json: chain ${chainId}, block ${timing.currentBlock}, checker ${C}, ${total} stamped runs`);
}

main().catch((err: unknown) => die(`arkiv:snapshot: ${why(err, cfg)}`));

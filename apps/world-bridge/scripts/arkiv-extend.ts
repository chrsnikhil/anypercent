/**
 * npm run arkiv:extend -- <run key>
 *
 * The extension demo (spec: Scripts). The STRANGER wallet, which owns nothing:
 *   1. extends a stamped run (a console's own, or the house's) by one day: it succeeds (runs are
 *      created with permissionlessExtension);
 *   2. tries to patch that run: refused (readonly, and not the owner);
 *   3. tries to extend the run's listing: refused (listings are not permissionless; a listing never
 *      outlives its week).
 * It prints the run's old and new $expiresAt (blocks, and about when). The run's stamp can be kept
 * alive the same way (stamps are permissionless too).
 */
import { ExpirationTime, MAX_LIFETIME } from "@arkiv-network/sdk";
import { str } from "@arkiv-network/sdk/schema";
import type { Hex } from "viem";
import { SdkArkiv } from "../src/arkiv/client.js";
import { KEY_RE } from "../src/arkiv/queries.js";
import { Run } from "../src/arkiv/schema.js";
import { arkivRpcUrl, PRIVATE_KEY_RE } from "../src/config.js";
import { clientsFor, die, loadEnv, positional, why } from "./arkiv-common.js";

const cfg = loadEnv();
const ak = cfg.arkiv;
const runKey = (positional()[0] ?? "").toLowerCase();
const DAY_BLOCKS = 43_200n;

async function main(): Promise<void> {
  if (!KEY_RE.test(runKey)) die("usage: npm run arkiv:extend -- 0x<run key>");
  if (!PRIVATE_KEY_RE.test(ak.checkerKey) || !PRIVATE_KEY_RE.test(ak.strangerKey)) die("run npm run arkiv:keygen first");
  const checker = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerKey: ak.checkerKey });
  const stranger = clientsFor(cfg, ak.strangerKey);
  const run = await checker.getRun(runKey, false);
  if (!run || run.expiresAt === null) die("no live run with that key that a checker stamp names");
  const timing = await stranger.pub.getBlockTiming();
  const when = (block: bigint) =>
    new Date((timing.currentBlockTime + Number(block - timing.currentBlock) * timing.blockDuration) * 1000).toUTCString();
  console.log(`run ${run.key} (owned by ${run.owner}, stamp ${run.stamp}): ${run.book ?? run.label}, $expiresAt ${run.expiresAt} (about ${when(run.expiresAt)})`);

  // 1. Extend by a day (an extension sets an absolute expiry; it must be later than the current one).
  const cap = timing.currentBlock + MAX_LIFETIME;
  const target = run.expiresAt + DAY_BLOCKS <= cap ? run.expiresAt + DAY_BLOCKS : cap;
  const expiration = target === cap ? ExpirationTime.max() : ExpirationTime.atBlock(target);
  try {
    const r = await stranger.wallet!.extendEntity({ entityKey: runKey as Hex, expiration });
    console.log(`1. the stranger ${stranger.address} extended it: $expiresAt ${run.expiresAt} -> ${r.expiresAt} (about ${when(r.expiresAt)}), tx ${r.txHash}`);
  } catch (err) {
    console.log(`1. the stranger's extension failed: ${why(err, cfg)}`);
  }

  // 2. Patch: refused.
  try {
    await stranger.wallet!.patchEntity(Run, runKey as Hex, { set: { title: str("EDITED") } });
    console.log("2. the stranger's patch WENT THROUGH (it should not have)");
  } catch (err) {
    console.log(`2. the stranger's patch is refused: ${why(err, cfg)}`);
  }

  // 3. Extend the listing: refused.
  const listing = await checker.liveListingFor(runKey, run.owner);
  if (!listing) {
    console.log("3. this run has no live listing to try");
    return;
  }
  try {
    await stranger.wallet!.extendEntity({ entityKey: listing.key as Hex, expiration: ExpirationTime.fromDays(30) });
    console.log(`3. the stranger extended listing ${listing.key} (it should not have)`);
  } catch (err) {
    console.log(`3. the stranger cannot extend listing ${listing.key}: ${why(err, cfg)}`);
  }
}

main().catch((err: unknown) => die(`arkiv:extend: ${why(err, cfg)}`));

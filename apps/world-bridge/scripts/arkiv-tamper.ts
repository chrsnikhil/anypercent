/**
 * npm run arkiv:tamper -- <run key>
 *
 * The fairness demo: the CHECKER's own wallet (the server's key, the one that stamps) tries to change and to
 * delete a run a console owns. Both are refused by Arkiv itself: the run is read-only and owned by the console's
 * wallet, so the server decides what counts (it stamps or not) but cannot edit or destroy anyone's record.
 *   1. patch the run's title: refused;
 *   2. delete the run: refused;
 *   3. read it back: unchanged, same owner.
 */
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

async function main(): Promise<void> {
  if (!KEY_RE.test(runKey)) die("usage: npm run arkiv:tamper -- 0x<run key>");
  if (!PRIVATE_KEY_RE.test(ak.checkerKey)) die("run npm run arkiv:keygen first");
  const reader = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerKey: ak.checkerKey });
  const server = clientsFor(cfg, ak.checkerKey);
  const before = await reader.getRun(runKey, false);
  if (!before) die("no stamped run with that key");
  console.log(`run ${before.key}: ${before.book ?? before.label} ${before.frames} frames, owned by ${before.owner}`);
  console.log(`the server (checker) ${server.address} tries to change it ...`);
  try {
    await server.wallet!.patchEntity(Run, runKey as Hex, { set: { title: str("EDITED BY THE SERVER") } });
    console.log("1. the server's edit WENT THROUGH (it should not have)");
  } catch (err) {
    console.log(`1. the server's edit is refused: ${why(err, cfg)}`);
  }
  try {
    await server.wallet!.deleteEntity({ entityKey: runKey as Hex });
    console.log("2. the server's delete WENT THROUGH (it should not have)");
  } catch (err) {
    console.log(`2. the server's delete is refused: ${why(err, cfg)}`);
  }
  const after = await reader.getRun(runKey, false);
  console.log(after && after.frames === before.frames && after.owner === before.owner
    ? `3. read back: unchanged, ${after.frames} frames, still owned by ${after.owner}`
    : `3. read back: ${after ? "CHANGED" : "GONE"}`);
}

main().catch((err) => die(why(err, cfg)));

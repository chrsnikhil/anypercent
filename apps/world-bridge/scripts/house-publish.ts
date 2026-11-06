/**
 * npm run house:publish -- --dir ../../games/marinedrive/out/ghostgen/default [--game MDGP] [--bridge URL]
 *
 * Publishes a BOT batch made by games/marinedrive/dev/ghostgen.py, through the running bridge:
 *   1. reads <dir>/manifest.json and every log it names (each must hash to its log_h);
 *   2. POST /house/batch: the bridge replays every log with the checker and arcade_splits, checks
 *      none is on the board, and answers the labels (BOT-<letter><n>) and the exact text;
 *   3. prints the table, then POST /house/publish: the house owner (HOUSE_OWNER_BOOK) approves that
 *      exact text in World App (terminal QR); Ctrl-C cancels before anything is written;
 *   4. follows the write (the HOUSE message on HCS, then one Arkiv batch) and prints every run,
 *      listing and transaction with its explorer link.
 *
 * Rows are open tier: never HUMAN, no book, no credential, listings paying the house account.
 * Prints ids and links only.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { arg, bridgeBase, call, die, follow, loadEnv, row, showApproval } from "./approve-common.js";
import { appDir } from "./arkiv-common.js";

interface Entry {
  file: string;
  name?: string;
  frames?: number;
  time?: string;
  splits?: number[];
  log_h: string;
  gen?: string;
}

const cfg = loadEnv();
const base = bridgeBase(cfg, arg("bridge"));
const dirArg = arg("dir") ?? "";
const game = (arg("game") ?? "MDGP").toUpperCase();
if (!dirArg) die("Usage: npm run house:publish -- --dir ../../games/marinedrive/out/ghostgen/default");
const dir = isAbsolute(dirArg) ? dirArg : resolve(process.cwd(), dirArg);

let manifest: Entry[];
try {
  manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8")) as Entry[];
} catch {
  die(`No readable manifest.json in ${dir} (run dev/ghostgen.py first).`);
}
if (!Array.isArray(manifest) || manifest.length === 0) die("manifest.json lists no logs.");
const logs: string[] = [];
const gen: string[] = [];
for (const e of manifest) {
  let bytes: Buffer;
  try {
    bytes = readFileSync(join(dir, e.file));
  } catch {
    die(`${e.file} is missing from ${dir}.`);
  }
  const h = createHash("sha256").update(bytes).digest("hex");
  if (h !== e.log_h) die(`${e.file} does not hash to its manifest log_h (regenerate the set).`);
  logs.push(bytes.toString("base64"));
  gen.push(typeof e.gen === "string" && e.gen !== "" ? e.gen : `ghostgen ${e.file}`);
}

const health = await call(base, "GET", "/health", undefined, 5000).catch((err: Error) => die(err.message));
if (health.json.house !== true) die(`The bridge says house: ${String(health.json.house)} (needs HEDERA_HOUSE_ID, HOUSE_OWNER_BOOK, the splits tool and Arkiv writes; see its startup line "pivot: ...").`);

console.log(`Staging ${logs.length} ${game} logs from ${dir.replace(appDir, ".")} (the bridge replays each one) ...`);
const staged = await call(base, "POST", "/house/batch", { game, logs, gen });
if (staged.status !== 200) die(`/house/batch refused: ${staged.json.error}${staged.json.detail ? `: ${staged.json.detail}` : ""}`);
const s = staged.json;
console.log("");
console.log(`batch ${s.batch}: ${s.rows.length} ${s.title} ghosts, ${s.price} USDC each to house ${s.pay_to}`);
console.log(`${"label".padEnd(8)} ${"variant".padEnd(20)} ${"laps (frames)".padEnd(16)} ${"time".padEnd(8)} ${"log_h".padEnd(14)} check`);
for (const [i, r] of (s.rows as Array<Record<string, any>>).entries()) {
  const name = manifest.find((m) => m.log_h === r.log_h)?.name ?? `log ${i + 1}`;
  console.log(`${String(r.label).padEnd(8)} ${name.slice(0, 20).padEnd(20)} ${(r.splits as number[]).join("/").padEnd(16)} ${String(r.time).padEnd(8)} ${String(r.log_h).slice(0, 12)}.. replay ok, splits ok`);
}

const pub = await call(base, "POST", "/house/publish", { batch: s.batch });
if (pub.status !== 200) die(`/house/publish refused: ${pub.json.error}${pub.json.detail ? `: ${pub.json.detail}` : ""}`);
if (pub.json.approval) await showApproval(String(pub.json.action), pub.json.approval);
else console.log(`\nbatch ${s.batch} was approved in World App before: writing it again without a new approval.\n`);

const done = await follow(base, `/house/publish/${pub.json.id}`, `/house/publish/${pub.json.id}/cancel`, {
  scan: "waiting for the scan",
  approve: "waiting for the approval in World App",
  write: "approved: the HOUSE message on HCS, then the Arkiv batch",
  done: "done",
});
if (done.ok !== true) die(`Not published: ${done.failure} (a failed write keeps the approval for this batch: run the same command again to retry)`);
const d = done.data;
console.log("");
if (d.hcs) row("HOUSE on HCS", `#${d.hcs.seq} on ${d.hcs.topic}, tx ${d.hcs.tx}`, d.hcs.hashscan);
else row("HOUSE on HCS", "not posted (the rows carry no hcs)");
(d.txs as string[]).forEach((t, i) => row(`Arkiv tx ${i + 1}`, t, d.explorer?.txs?.[i] ?? null));
const entity = (k: string) => cfg.explorer.entity.replaceAll("{key}", k);
(d.runs as string[]).forEach((r, i) => {
  row(`${s.rows[i].label} run`, r, entity(r));
  row(`${s.rows[i].label} listing`, d.listings[i], d.listings[i] ? entity(d.listings[i]) : null);
});

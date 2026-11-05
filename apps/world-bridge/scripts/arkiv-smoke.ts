/**
 * npm run arkiv:smoke [-- --raw]
 *
 * The live smoke on Rabdi (spec: Tests, Part A live smoke), under the anypercent.smoke.* schemas
 * with a one-hour expiry. In order:
 *   1. chain id and both balances (stops here, naming what to fund, if either wallet is empty);
 *   2. one run+listing batch with predicted keys (and a second, plain open-tier run);
 *   3. Q1-Q7 equivalents: ORDER BY, $creator, bool, key, dec, the $expiresAt:u64 sort, select.count;
 *   4. a checker patch is refused (readonly), and so is the stranger's;
 *   5. the stranger can extend the run but not the listing;
 *   6. the stranger's look-alike row is absent from the pinned query and present without the pin;
 *   7. the checker deletes the smoke rows (and the stranger its look-alike).
 * It prints gas, tGLM spent and per-query latency for friction.md. --raw also prints one raw Q1
 * page (the launcher's decoder fixture). Never prints a key: addresses, entity keys and tx hashes.
 */
import { createHash, randomBytes } from "node:crypto";
import { ExpirationTime } from "@arkiv-network/sdk";
import { str } from "@arkiv-network/sdk/schema";
import type { Hex } from "viem";
import { SdkArkiv, type ListingValues, type RunValues } from "../src/arkiv/client.js";
import { decryptGhost, encryptGhost } from "../src/arkiv/ghost.js";
import * as Q from "../src/arkiv/queries.js";
import { decodePage } from "../src/arkiv/rows.js";
import { LISTING_FLAGS, LISTING_TYPES, RUN_FLAGS, RUN_TYPES, SMOKE, SmokeRun } from "../src/arkiv/schema.js";
import { arkivRpcUrl } from "../src/config.js";
import { clientsFor, die, flag, glm, loadEnv, timed, why } from "./arkiv-common.js";

const cfg = loadEnv();
const ak = cfg.arkiv;
const checker = clientsFor(cfg, ak.checkerKey);
const stranger = clientsFor(cfg, ak.strangerKey);
if (!checker.wallet || !checker.address) die("ARKIV_CHECKER_KEY is missing: run npm run arkiv:keygen first");
if (!stranger.wallet || !stranger.address) die("ARKIV_STRANGER_KEY is missing: run npm run arkiv:keygen first");
const C = checker.address as Hex;
const S = stranger.address as Hex;
const pub = checker.pub;

const latency: Array<[string, number]> = [];
const fees: Array<[string, bigint, bigint]> = []; // what, gas used, fee in wei
let failures = 0;

function ok(what: string, cond: boolean, detail = ""): void {
  console.log(`  ${cond ? "ok  " : "FAIL"} ${what}${detail ? `: ${detail}` : ""}`);
  if (!cond) failures++;
}

async function fee(what: string, tx: string): Promise<void> {
  const r = await pub.getTransactionReceipt({ hash: tx as Hex });
  const wei = r.gasUsed * r.effectiveGasPrice;
  fees.push([what, r.gasUsed, wei]);
  console.log(`  gas ${what}: ${r.gasUsed} (${glm(wei)} tGLM) tx ${tx}`);
}

async function q(name: string, query: string, attrs: readonly string[], limit = 100, count = false) {
  const port = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerAddress: C, names: SMOKE });
  const [res, ms] = await timed(() => port.query(query, Q.selectOf(attrs, { count }), limit));
  latency.push([name, ms]);
  return res;
}

/** Ask until the answer satisfies `pred` (a fresh block may take a moment to show up), up to 12 s. */
async function until<T>(fn: () => Promise<T>, pred: (t: T) => boolean): Promise<T> {
  const end = Date.now() + 12_000;
  for (;;) {
    const t = await fn();
    if (pred(t) || Date.now() > end) return t;
    await new Promise((r) => setTimeout(r, 1000));
  }
}

const keysOf = (data: unknown[]) => (data as Array<{ key: string }>).map((e) => e.key.toLowerCase());

async function main(): Promise<void> {
  console.log(`Rabdi via ${ak.accessKey ? "the keyed endpoint (ARKIV_ACCESS_KEY set)" : "the public endpoint (no ARKIV_ACCESS_KEY)"}`);
  console.log(`checker ${C}\nstranger ${S}`);

  // 1. chain id and both balances.
  console.log("1. chain and balances");
  const [chainId, msChain] = await timed(() => pub.getChainId());
  latency.push(["eth_chainId", msChain]);
  ok("eth_chainId", chainId === ak.chainId, `${chainId} (0x${chainId.toString(16)})`);
  const balC0 = await pub.getBalance({ address: C });
  const balS0 = await pub.getBalance({ address: S });
  console.log(`  checker ${glm(balC0)} tGLM, stranger ${glm(balS0)} tGLM`);
  if (balC0 === 0n || balS0 === 0n) {
    const empty = [balC0 === 0n ? `checker ${C}` : "", balS0 === 0n ? `stranger ${S}` : ""].filter(Boolean).join(" and ");
    die(`waiting on the owner: fund ${empty} with tGLM at https://hub.arkiv.network/faucet, then run this again`);
  }

  const port = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerKey: ak.checkerKey, names: SMOKE });
  const strangerPort = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerKey: ak.strangerKey, names: SMOKE });
  const secret = randomBytes(32).toString("hex");
  const logA = randomBytes(200);
  const logHA = createHash("sha256").update(logA).digest("hex");
  const logB = randomBytes(120);
  const logHB = createHash("sha256").update(logB).digest("hex");
  const hour = { kind: "hours", hours: 1 } as const;
  const created: { run?: string; run2?: string; listing?: string; lookalike?: string } = {};

  try {
    // 2. One run+listing batch with predicted keys, then a plain open-tier run.
    console.log("2. writes");
    const run1: RunValues = {
      game: "MDGP", title: "SMOKE MDGP", season: 1, rules: 4, frames: 6170, log_h: logHA, runner: "5a5a5a5a5a5a5a5a",
      book: "ANY-SMK", human: true, credential: "Orb", tool: "arcade_replay sha256:000000000000", log_enc: encryptGhost(secret, logHA, logA),
    };
    const listing1: ListingValues = { game: "MDGP", season: 1, frames: 6170, log_h: logHA, price: "0.1", seller: "5a5a5a5a5a5a5a5a", book: "ANY-SMK", human: true };
    const [w, msW] = await timed(() => port.writeRunAndListing({ values: run1, flags: RUN_FLAGS, expiry: hour }, { values: listing1, flags: LISTING_FLAGS, expiry: hour }));
    created.run = w.run;
    created.listing = w.listing;
    latency.push(["write run+listing (to receipt)", msW]);
    ok("batch landed with the predicted keys", true, `run ${w.run} listing ${w.listing}`);
    await fee("run+listing batch", w.tx);
    const run2: RunValues = {
      game: "MDGP", title: "SMOKE MDGP", season: 1, rules: 4, frames: 7000, log_h: logHB, runner: "6b6b6b6b6b6b6b6b",
      label: "BOT-7", human: false, tool: "arcade_replay sha256:000000000000", log: logB,
    };
    const [w2, msW2] = await timed(() => port.writeRun({ values: run2, flags: RUN_FLAGS, expiry: hour }));
    created.run2 = w2.run;
    latency.push(["write run (to receipt)", msW2]);
    await fee("open-tier run", w2.tx);

    // 3. The queries.
    console.log("3. queries");
    const q1 = await until(() => q("Q1", Q.q1Board("MDGP", 1, C, SMOKE), Q.RUN_BOARD_ATTRS), (r) => r.data.length >= 2);
    ok("Q1: ORDER BY frames:u64 ASC with the $creator pin", JSON.stringify(keysOf(q1.data)) === JSON.stringify([w.run, w2.run]), keysOf(q1.data).join(", "));
    const page = decodePage(q1.data, RUN_TYPES, Q.RUN_BOARD_ATTRS, SMOKE.run, C);
    ok("Q1 rows validate (types, creator, schema tag)", page.dropped === 0 && page.rows.length === 2, `${page.dropped} dropped`);
    const q2 = await q("Q2", Q.q2Listings("MDGP", 1, C, SMOKE), Q.LISTING_ATTRS);
    ok("Q2: the listing", JSON.stringify(keysOf(q2.data)) === JSON.stringify([w.listing]));
    const lp = decodePage(q2.data, LISTING_TYPES, Q.LISTING_ATTRS, SMOKE.listing, C);
    ok("the listing names the run's predicted key", lp.rows[0]?.values.run === w.run);
    const q3 = await q("Q3", Q.q3JustAhead("MDGP", 1, 6290, C, SMOKE), Q.LISTING_ATTRS, 1);
    ok("Q3: frames < u64(6290) ORDER BY frames DESC, limit 1", keysOf(q3.data)[0] === w.listing);
    const q3none = await q("Q3 (none ahead)", Q.q3JustAhead("MDGP", 1, 6170, C, SMOKE), Q.LISTING_ATTRS, 1);
    ok("Q3 below the fastest listing: nothing", q3none.data.length === 0);
    const q4 = await q("Q4", Q.q4BookRuns("ANY-SMK", C, SMOKE), Q.RUN_BOARD_ATTRS);
    ok("Q4: the book's runs", JSON.stringify(keysOf(q4.data)) === JSON.stringify([w.run]));
    const q5 = await q("Q5", Q.q5BookListings("ANY-SMK", C, SMOKE), Q.LISTING_ATTRS);
    ok("Q5: ORDER BY $expiresAt:u64 ASC", JSON.stringify(keysOf(q5.data)) === JSON.stringify([w.listing]));
    const q6l = await q("Q6 listing", Q.q6Listing(w.listing, C, SMOKE), Q.LISTING_ATTRS, 1);
    ok("Q6: $key = key(...) on listings", keysOf(q6l.data)[0] === w.listing);
    const ghostAsk = [...Q.RUN_ALL_ATTRS, "log", "log_enc"];
    const q6r = await q("Q6 run (with log_enc)", Q.q6Run(w.run, C, SMOKE), ghostAsk, 1);
    const g = decodePage(q6r.data, RUN_TYPES, ghostAsk, SMOKE.run, C).rows[0];
    const opened = g?.values.log_enc instanceof Uint8Array ? decryptGhost(secret, logHA, g.values.log_enc) : null;
    ok("Q6 run: log_enc comes back and decrypts to the log", !!opened && Buffer.from(opened).equals(logA));
    const q7 = await q("Q7", Q.q7RunByLogHash(logHA, C, SMOKE), Q.RUN_ALL_ATTRS, 1);
    ok("Q7: log_h = str(...)", keysOf(q7.data)[0] === w.run);
    const q9 = await q("Q9", Q.q9Human("MDGP", 1, C, SMOKE), Q.RUN_BOARD_ATTRS);
    ok("Q9: human = true (bool)", JSON.stringify(keysOf(q9.data)) === JSON.stringify([w.run]));
    const cnt = await q("count", Q.q1Board("MDGP", 1, C, SMOKE), [], 1, true);
    ok("select.count", cnt.count === 2n, String(cnt.count));
    const decQ = `arkiv.schema = str('${SMOKE.listing}') AND price = dec(0.1) AND $creator = addr(${Q.checksum(C)})`;
    const qd = await q("dec literal", decQ, Q.LISTING_ATTRS);
    ok("dec: price = dec(0.1)", keysOf(qd.data)[0] === w.listing);
    const qk = await q("key literal", Q.qListingForRun(w.run, C, SMOKE), Q.LISTING_ATTRS, 1);
    ok("key: run = key(...)", keysOf(qk.data)[0] === w.listing);
    if (flag("raw")) {
      const rawPage = await q("Q1 raw", Q.q1Board("MDGP", 1, C, SMOKE), Q.RUN_BOARD_ATTRS);
      console.log("--- raw Q1 page (arkiv_query result; anypercent.smoke.run rows) ---");
      console.log(JSON.stringify({ data: rawPage.data, blockNumber: `0x${rawPage.blockNumber.toString(16)}` }, null, 1));
      console.log("--- end raw ---");
    }

    // 4. Patches are refused.
    console.log("4. readonly");
    for (const [who, wallet] of [["checker", checker.wallet], ["stranger", stranger.wallet]] as const) {
      try {
        await wallet!.patchEntity(SmokeRun, w.run as Hex, { set: { title: str("PATCHED") } });
        ok(`${who}'s patch is refused`, false, "it went through");
      } catch (err) {
        ok(`${who}'s patch is refused`, true, why(err, cfg));
      }
    }

    // 5. The stranger extends the run (permissionless) but not the listing.
    console.log("5. extension");
    const before = (await pub.getEntity(w.run as Hex)) as unknown as { expiresAt?: bigint };
    const [ext, msExt] = await timed(() => stranger.wallet!.extendEntity({ entityKey: w.run as Hex, expiration: ExpirationTime.fromHours(2) }));
    latency.push(["stranger extend (to receipt)", msExt]);
    ok("the stranger extends the checker's run", true, `$expiresAt ${String(before?.expiresAt ?? "?")} -> ${ext.expiresAt}`);
    await fee("stranger extend", ext.txHash);
    try {
      await stranger.wallet!.extendEntity({ entityKey: w.listing as Hex, expiration: ExpirationTime.fromHours(2) });
      ok("the stranger cannot extend the listing", false, "it went through");
    } catch (err) {
      ok("the stranger cannot extend the listing", true, why(err, cfg));
    }

    // 6. The look-alike.
    console.log("6. look-alike");
    const fake: RunValues = { ...run1, frames: 6170 - 600, log_enc: undefined, log: logA };
    const lw = await strangerPort.writeRun({ values: fake, flags: RUN_FLAGS, expiry: hour });
    created.lookalike = lw.run;
    await fee("stranger look-alike", lw.tx);
    const pinned = await until(() => q("Q1 after look-alike", Q.q1Board("MDGP", 1, C, SMOKE), Q.RUN_BOARD_ATTRS), () => true);
    ok("absent from the pinned query", !keysOf(pinned.data).includes(lw.run));
    const any = await until(() => q("Q8", Q.q8AnyWallet("MDGP", 1, SMOKE), Q.RUN_BOARD_ATTRS), (r) => keysOf(r.data).includes(lw.run));
    const firstAny = (any.data as Array<{ key: string; creator: string }>)[0];
    ok("present without the pin, and first (it claims 600 frames faster)", firstAny?.key.toLowerCase() === lw.run && firstAny.creator.toLowerCase() === S.toLowerCase());
  } catch (err) {
    ok("smoke step", false, why(err, cfg));
  } finally {
    // 7. Clean up.
    console.log("7. delete");
    const mine = [created.run, created.run2, created.listing].filter(Boolean) as string[];
    if (mine.length) {
      try {
        const d = await checker.wallet!.executeBatch({ deletes: mine.map((k) => ({ entityKey: k as Hex })) });
        ok("the checker deletes its smoke rows", true, `${mine.length} rows`);
        await fee("checker deletes", d.txHash);
      } catch (err) {
        ok("the checker deletes its smoke rows", false, why(err, cfg));
      }
    }
    if (created.lookalike) {
      try {
        const d = await stranger.wallet!.deleteEntity({ entityKey: created.lookalike as Hex });
        await fee("stranger deletes its look-alike", d.txHash);
      } catch (err) {
        ok("the stranger deletes its look-alike", false, why(err, cfg));
      }
    }
  }

  const balC1 = await pub.getBalance({ address: C });
  const balS1 = await pub.getBalance({ address: S });
  console.log("\nFor friction.md");
  console.log(`  tGLM spent: checker ${glm(balC0 - balC1)}, stranger ${glm(balS0 - balS1)}`);
  for (const [what, gas, wei] of fees) console.log(`  ${what}: ${gas} gas, ${glm(wei)} tGLM`);
  for (const [what, ms] of latency) console.log(`  ${what}: ${ms} ms`);
  console.log(failures === 0 ? "\nSMOKE GREEN" : `\nSMOKE: ${failures} check(s) failed`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err: unknown) => die(`arkiv:smoke: ${why(err, cfg)}`));

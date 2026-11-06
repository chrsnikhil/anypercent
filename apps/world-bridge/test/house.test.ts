/**
 * The house's BOT batches: staging (replay, splits, the stamp dedupe, duplicates), the exact text
 * World App shows, the owner's approval only, one Arkiv transaction of 2N creates from the house
 * wallet with every column, then one transaction of N stamps from the checker, the HOUSE message, a
 * refused batch split into HOUSE_TX_PAIRS, idempotent retries, the house off without
 * HOUSE_ARKIV_KEY, and the HTTP routes.
 */
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { afterEach, describe, it } from "node:test";
import { decryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { batchId, houseListing, houseRun, houseText, HouseService, type HouseView } from "../src/arkiv/house.js";
import { STAMP_FLAGS } from "../src/arkiv/schema.js";
import { explorerLinks, houseProblems, loadConfig } from "../src/config.js";
import { HCS_MAX_BYTES, houseMessage } from "../src/hedera/messages.js";
import { nullifierKey, runnerId } from "../src/hmac.js";
import { buildServer, makeHealth, pivotHealth } from "../src/server.js";
import { batchLetter, Store } from "../src/store.js";
import { FakeApprovals } from "./fake-approvals.js";
import { CHECKER, FakeArkiv, FakeChecker, HOUSE_WALLET, makeLog, WALLET_A } from "./fake-arkiv.js";
import { FakeHedera, HOUSE, TOPIC } from "./fake-hedera.js";
import { FakeSplits } from "./fake-splits.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const GHOST = "cd".repeat(32);
/** The default ghostgen set: (laps) per variant. */
const LAPS = [
  [2087, 1995, 2088],
  [2248, 1994, 1994],
  [2087, 2088, 1994],
  [2168, 2078, 1994],
  [2087, 2080, 2077],
  [2168, 2078, 2079],
];
const GEN = LAPS.map((_, i) => `ghostgen v${i + 1} seed 0 @f88d15b`);

let live: HouseService[] = [];
afterEach(() => {
  for (const h of live) h.stopAll();
  live = [];
});

let n = 0;
function setup(o: { txPairs?: number; problems?: string[]; hedera?: boolean; houseWallet?: string | null } = {}) {
  n += 1;
  const store = new Store(tempDir(), SECRET);
  const owner = store.claimBook(nullifierKey(SECRET, "act", `owner-${n}`), "Orb", "0123456789abcdef", 1, "session_o").record;
  const arkiv = new FakeArkiv();
  if (o.houseWallet !== undefined) arkiv.house = o.houseWallet;
  const checker = new FakeChecker();
  const splits = new FakeSplits();
  const approvals = new FakeApprovals(store);
  const events: string[] = [];
  const hcs = new FakeHedera(events);
  const lines: string[] = [];
  const logs = LAPS.map((laps, i) => makeLog("MDGP", 4, laps.reduce((a, b) => a + b, 0), 96, 500 + n * 10 + i));
  for (const [i, log] of logs.entries()) {
    const laps = LAPS[i];
    checker.byLog.set(sha256Hex(log), { time_frames: laps.reduce((a, b) => a + b, 0) });
    splits.byLog.set(sha256Hex(log), laps);
  }
  const house = new HouseService({
    store,
    arkiv,
    checker,
    splits,
    approvals,
    hedera: o.hedera === false ? null : hcs,
    topic: TOPIC,
    houseId: HOUSE,
    ownerBook: owner.book,
    maxBatch: 8,
    txPairs: o.txPairs ?? 6,
    season: 1,
    runExpiry: new Date(Date.now() + 60 * 86_400_000),
    priceC: 10,
    ghostSecret: GHOST,
    secret: SECRET,
    problems: () => o.problems ?? [],
    explorer: explorerLinks(loadConfig({}, ".").explorer),
    pollMs: 2,
    hcsTimeoutMs: 200,
    writeTimeoutMs: 500,
    log: (l) => lines.push(l),
  });
  live.push(house);
  const body = (over: Record<string, unknown> = {}) => ({ game: "MDGP", logs: logs.map((l) => Buffer.from(l).toString("base64")), gen: GEN, ...over });
  return { store, owner, arkiv, checker, splits, approvals, hcs, lines, logs, house, body };
}

async function refusal(p: Promise<unknown>): Promise<string> {
  try {
    await p;
    return "ok";
  } catch (e) {
    const r = e as { status: number; message: string; detail?: string };
    return `${r.status} ${r.message}${r.detail ? `: ${r.detail}` : ""}`;
  }
}

async function publishDone(h: HouseService, batch: string): Promise<{ id: string; view: HouseView; approval: unknown }> {
  const p = await h.publish({ batch });
  await waitFor(() => h.view(p.id)?.stage === "done", 5000);
  return { id: p.id, view: h.view(p.id)!, approval: p.approval };
}

describe("the action text and the batch id", () => {
  it("is exactly the spec's text, at most 160 characters", () => {
    assert.equal(
      houseText("3f9c0a", 6, "MARINE DRIVE GP", 10, "0.0.9473064"),
      "Publish BOT batch 3f9c0a: 6 MARINE DRIVE GP ghosts made by a program, 0.10 USDC each to house 0.0.9473064 on the public board, never HUMAN",
    );
    assert.ok(houseText("ffffff", 8, "MARINE DRIVE GP", 1_000_000, "0.0.9999999999").length <= 160);
  });
  it("the batch id is the sha256 of the sorted log hashes joined by ',', 6 hex, whatever the order", () => {
    const hs = ["b".repeat(64), "a".repeat(64)];
    assert.equal(batchId(hs), batchId([...hs].reverse()));
    assert.match(batchId(hs), /^[0-9a-f]{6}$/);
  });
  it("batch letters: A..Z, then AA, AB", () => {
    assert.deepEqual([0, 1, 25, 26, 27, 51, 52].map(batchLetter), ["A", "B", "Z", "AA", "AB", "AZ", "BA"]);
  });
});

describe("POST /house/batch: staging", () => {
  it("replays and splits every log, labels BOT-A1..BOT-A6 in the order given, and answers the text", async () => {
    const s = setup();
    const a = await s.house.stage(s.body());
    const batch = batchId(s.logs.map(sha256Hex));
    assert.equal(a.batch, batch);
    assert.equal(a.action, houseText(batch, 6, "MARINE DRIVE GP", 10, HOUSE));
    assert.deepEqual([a.game, a.title, a.pay_to, a.price, a.expires_s], ["MDGP", "MARINE DRIVE GP", HOUSE, "0.10", 3600]);
    const rows = a.rows as Array<Record<string, unknown>>;
    assert.deepEqual(rows.map((r) => r.label), ["BOT-A1", "BOT-A2", "BOT-A3", "BOT-A4", "BOT-A5", "BOT-A6"]);
    assert.deepEqual(rows[1], { label: "BOT-A2", frames: 6236, time: "1:43.93", splits: [2248, 1994, 1994], log_h: sha256Hex(s.logs[1]) });
    assert.equal(s.checker.calls, 6);
    assert.equal(s.splits.calls, 6);
    // The store keeps labels, hashes and status, never the logs.
    const rec = s.store.houseBatch(batch)!;
    assert.deepEqual([rec.letter, rec.status, rec.labels.length], ["A", "staged", 6]);
    assert.ok(!JSON.stringify(rec).includes(Buffer.from(s.logs[0]).toString("base64").slice(0, 40)));
    // Staged again (another order): same batch, same labels; a second batch takes B.
    const again = await s.house.stage(s.body({ logs: [...s.body().logs].reverse(), gen: [...GEN].reverse() }));
    assert.deepEqual((again.rows as Array<Record<string, unknown>>).map((r) => r.label), ["BOT-A1", "BOT-A2", "BOT-A3", "BOT-A4", "BOT-A5", "BOT-A6"]);
    const b = await s.house.stage(s.body({ logs: s.body().logs.slice(0, 2), gen: GEN.slice(0, 2) }));
    assert.deepEqual((b.rows as Array<Record<string, unknown>>).map((r) => r.label), ["BOT-B1", "BOT-B2"]);
  });

  it("a replay refusal refuses the batch, naming the log", async () => {
    const s = setup();
    s.checker.byLog.set(sha256Hex(s.logs[2]), { claims_match: false });
    assert.equal(await refusal(s.house.stage(s.body())), "409 replay_refused: log 3: claims_match is false");
  });

  it("splits are required: missing or not adding up refuses the batch", async () => {
    const s = setup();
    s.splits.byLog.set(sha256Hex(s.logs[0]), [2087, 1995, 2000]);
    assert.match(await refusal(s.house.stage(s.body())), /^409 replay_refused: log 1: splits: the splits add up to 6082, not 6170$/);
    const t = setup();
    t.splits.missing = true;
    assert.match(await refusal(t.house.stage(t.body())), /^409 replay_refused: log 1: splits tool/);
  });

  it("a log already on the board (a checker stamp names a console's run of it) refuses the whole batch", async () => {
    const s = setup();
    const key = s.arkiv.addRun({ game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames: 6236, log_h: sha256Hex(s.logs[1]), runner: "0".repeat(16), book: "ANY-XYZ", human: true, tool: "t" }, WALLET_A);
    assert.equal(await refusal(s.house.stage(s.body())), `409 on_board: log 2 is run ${key}`);
  });

  it("a run of the log that no stamp names (a look-alike, an old checker row) is not on the board: staging goes on", async () => {
    const s = setup();
    s.arkiv.addRun({ game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames: 6236, log_h: sha256Hex(s.logs[1]), runner: "0".repeat(16), book: "ANY-XYZ", human: true, tool: "t" }, CHECKER, { stamp: false });
    assert.equal((await s.house.stage(s.body())).batch, batchId(s.logs.map(sha256Hex)));
  });

  it("a duplicate within the batch refuses it", async () => {
    const s = setup();
    const logs = s.body().logs;
    assert.equal(await refusal(s.house.stage(s.body({ logs: [logs[0], logs[1], logs[0]], gen: GEN.slice(0, 3) }))), "409 duplicate: log 3 is log 1 again");
  });

  it("bad bodies are 400; an unconfigured house is 503", async () => {
    const s = setup();
    assert.match(await refusal(s.house.stage({ game: "MDGP", logs: [] })), /^400 bad_body/);
    assert.match(await refusal(s.house.stage({ game: "MDGP", logs: Array(9).fill(s.body().logs[0]) })), /^400 bad_body/);
    assert.match(await refusal(s.house.stage({ game: "RUSH", logs: s.body().logs.slice(0, 1) })), /^400 bad_body/);
    assert.match(await refusal(s.house.stage(s.body({ gen: ["x"] }))), /^400 bad_body/);
    assert.match(await refusal(s.house.stage(s.body({ logs: ["!!!!"] , gen: undefined }))), /^400 bad_body/);
    const off = setup({ problems: ["HEDERA_HOUSE_ID"] });
    assert.equal(await refusal(off.house.stage(off.body())), "503 house_not_configured: set: HEDERA_HOUSE_ID");
  });

  it("no house wallet (HOUSE_ARKIV_KEY missing): the house is off, with that reason in /health", async () => {
    const s = setup({ houseWallet: null });
    assert.equal(await refusal(s.house.stage(s.body())), "503 house_not_configured: set: HOUSE_ARKIV_KEY");
    const env = { HEDERA_HOUSE_ID: HOUSE, HOUSE_OWNER_BOOK: "ANY-6PS", CHECKER_REPLAY: "/x/{game}/arcade_replay" };
    const missing = houseProblems(loadConfig(env, "."));
    assert.ok(missing.includes("HOUSE_ARKIV_KEY"), missing.join(", "));
    const checkerKey = `0x${"1".repeat(64)}`;
    const same = houseProblems(loadConfig({ ...env, ARKIV_CHECKER_KEY: checkerKey, HOUSE_ARKIV_KEY: checkerKey }, "."));
    assert.ok(same.includes("HOUSE_ARKIV_KEY (not the checker's key)"), "the house wallet is never the checker's");
    const own = houseProblems(loadConfig({ ...env, ARKIV_CHECKER_KEY: checkerKey, HOUSE_ARKIV_KEY: `0x${"2".repeat(64)}` }, "."));
    assert.ok(!own.some((p) => p.startsWith("HOUSE_ARKIV_KEY")), own.join(", "));
    const h = pivotHealth({ consoles: null, splits: true, scout: null, house: null, houseProblems: ["HOUSE_ARKIV_KEY"], arkivWrites: true });
    assert.deepEqual([h.house, h.house_off], [false, "set: HOUSE_ARKIV_KEY"]);
    const on = pivotHealth({ consoles: null, splits: true, scout: null, house: {}, houseProblems: [], arkivWrites: true });
    assert.deepEqual([on.house, on.house_off], [true, null]);
    const noWrites = pivotHealth({ consoles: null, splits: true, scout: null, house: {}, houseProblems: [], arkivWrites: false });
    assert.deepEqual([noWrites.house, noWrites.house_off], [false, "Arkiv writes are off"]);
  });
});

describe("POST /house/publish: the owner's World approval, then one Arkiv batch from the house wallet and one of stamps", () => {
  it("writes 2N creates in one house-wallet transaction with every column, after the HOUSE message, then the checker stamps every run in one more", async () => {
    const s = setup();
    const staged = await s.house.stage(s.body());
    const batch = String(staged.batch);
    const p = await s.house.publish({ batch });
    assert.match(p.id, /^h-[0-9a-f]{8}$/);
    assert.equal(p.action, staged.action);
    assert.deepEqual(s.approvals.started[0], { id: p.approval!.id, book: s.owner.book, action: staged.action, cancelled: false });
    await waitFor(() => s.house.view(p.id)?.stage === "done", 5000);
    const v = s.house.view(p.id)!;
    assert.equal(v.ok, true, JSON.stringify(v));

    // One house-wallet transaction of 12 creates, then one checker transaction of 6 stamps.
    assert.deepEqual(
      s.arkiv.batches.map((b) => [b.kind, b.creates, b.creator]),
      [
        ["house", 12, HOUSE_WALLET],
        ["stamp", 6, CHECKER],
      ],
    );
    assert.ok(s.arkiv.runs.every((r) => r.creator === HOUSE_WALLET) && s.arkiv.listings.every((l) => l.creator === HOUSE_WALLET), "the house wallet created every run and listing");
    // The HOUSE message, first, word for word.
    const [m] = s.hcs.of("HOUSE");
    assert.equal(
      Buffer.from(m.bytes).toString("utf8"),
      `{"v":1,"t":"HOUSE","batch":"${batch}","book":"${s.owner.book}","game":"MDGP","n":6,"price":"0.10","pay_to":"${HOUSE}","action":"${staged.action}"}`,
    );
    for (const [i, run] of s.arkiv.runs.entries()) {
      const rv = run.spec.values;
      const label = `BOT-A${i + 1}`;
      assert.deepEqual(
        { ...rv, log_enc: undefined },
        {
          game: "MDGP",
          title: "MARINE DRIVE GP",
          season: 1,
          rules: 4,
          frames: LAPS[i].reduce((a, b) => a + b, 0),
          log_h: sha256Hex(s.logs[i]),
          runner: runnerId(SECRET, `house|${label}`),
          label,
          human: false,
          tool: "arcade_replay sha256:a992006e6280",
          log_enc: undefined,
          s1: LAPS[i][0],
          s2: LAPS[i][1],
          s3: LAPS[i][2],
          split_kind: "lap",
          gen: GEN[i],
        },
      );
      assert.equal("book" in rv || "credential" in rv, false, "no book, no credential");
      assert.deepEqual(Buffer.from(decryptGhost(GHOST, rv.log_h, rv.log_enc!)!), Buffer.from(s.logs[i]), "log_enc decrypts to the log");
      assert.deepEqual(run.spec.flags, { readonly: true, permissionlessExtension: true });
      const l = s.arkiv.listings[i];
      assert.equal(l.run, run.key);
      assert.deepEqual(l.spec.values, {
        game: "MDGP",
        season: 1,
        frames: rv.frames,
        log_h: rv.log_h,
        price: "0.1",
        seller: rv.runner,
        label,
        human: false,
        pay_to: HOUSE,
        hcs: `${TOPIC}/${m.seq}`,
      });
      assert.deepEqual(l.spec.expiry, { kind: "days", days: 7 });
      // One stamp per run, by the checker, naming the house wallet as its console.
      const st = s.arkiv.stamps[i];
      assert.deepEqual(st.spec.values, {
        run: run.key,
        console: HOUSE_WALLET,
        game: "MDGP",
        season: 1,
        frames: rv.frames,
        log_h: rv.log_h,
        label,
        human: false,
        s1: LAPS[i][0],
        s2: LAPS[i][1],
        s3: LAPS[i][2],
        split_kind: "lap",
        final_hash: 576543229,
        tool: "arcade_replay sha256:a992006e6280",
      });
      assert.deepEqual(st.spec.flags, STAMP_FLAGS);
      assert.deepEqual(st.spec.expiry, run.spec.expiry, "the stamp expires with its run");
    }
    // Every reader ranks them now: stamped runs of the house wallet.
    const board = await s.arkiv.boardRuns("MDGP", 1);
    assert.deepEqual(new Set(board.map((r) => r.key)), new Set(s.arkiv.runs.map((r) => r.key)));
    assert.ok(board.every((r) => r.owner === HOUSE_WALLET));
    assert.equal((await s.arkiv.boardListings("MDGP", 1)).length, 6);
    const ex = (t: string) => `https://rabdi.explorer.arkiv.network/tx/${t}`;
    assert.deepEqual(v.data, {
      batch,
      runs: s.arkiv.runs.map((r) => r.key),
      listings: s.arkiv.listings.map((l) => l.key),
      stamps: s.arkiv.stamps.map((r) => r.key),
      txs: [s.arkiv.batches[0].tx],
      stamp_txs: [s.arkiv.batches[1].tx],
      explorer: { txs: [ex(s.arkiv.batches[0].tx)], stamp_txs: [ex(s.arkiv.batches[1].tx)] },
      hcs: { topic: TOPIC, seq: Number(m.seq), tx: m.tx, hashscan: `https://hashscan.io/testnet/transaction/${m.tx.replace("@", "-").replace(/\.(\d{9})$/, "-$1")}` },
    });
    const approvalJti = `jti-${p.approval!.id}`;
    assert.equal(s.store.approvalFor(approvalJti)?.used_for, `house:${batch}`);
    assert.equal(s.store.houseBatch(batch)?.status, "written");
    assert.ok(!s.lines.join("\n").includes(approvalJti), "never a jti in the log");
  });

  it("only HOUSE_OWNER_BOOK's approval counts: another book's is ls_wrong and nothing is written", async () => {
    const s = setup();
    const { batch } = await s.house.stage(s.body());
    s.approvals.recordAs = "ANY-ZZZ";
    const r = await publishDone(s.house, String(batch));
    assert.deepEqual([r.view.ok, r.view.failure], [false, "ls_wrong"]);
    assert.equal(s.arkiv.batches.length, 0);
    assert.equal(s.hcs.of("HOUSE").length, 0);
  });

  it("World App's refusal, or Ctrl-C before the write: nothing is written", async () => {
    const s = setup();
    const { batch } = await s.house.stage(s.body());
    s.approvals.outcome = "ls_denied";
    assert.equal((await publishDone(s.house, String(batch))).view.failure, "ls_denied");
    s.approvals.outcome = null;
    s.approvals.hold = true;
    const p = await s.house.publish({ batch });
    assert.equal(s.house.cancel(p.id), true);
    assert.equal(s.house.view(p.id)?.failure, "ls_denied");
    assert.equal(s.approvals.started.at(-1)?.cancelled, true);
    assert.equal(s.arkiv.batches.length, 0);
  });

  it("an approval already spent on a listing is ls_reused", async () => {
    const s = setup();
    const { batch, action } = await s.house.stage(s.body());
    const { createHash } = await import("node:crypto");
    s.store.recordApproval("jti-listing", s.owner.book, createHash("sha256").update(String(action)).digest("hex"), Math.floor(Date.now() / 1000));
    s.store.spendApproval("jti-listing", "e".repeat(64));
    s.approvals.reuseJti = "jti-listing";
    assert.equal((await publishDone(s.house, String(batch))).view.failure, "ls_reused");
  });

  it("a failed write keeps the approval spent on the batch: the retry writes it without a new approval, and again answers the same", async () => {
    const s = setup();
    const { batch } = await s.house.stage(s.body());
    s.arkiv.failWrites = 1;
    const first = await publishDone(s.house, String(batch));
    assert.deepEqual([first.view.ok, first.view.failure], [false, "ls_publish_fail"]);
    assert.equal(s.store.houseBatch(String(batch))?.status, "approved");
    const retry = await publishDone(s.house, String(batch));
    assert.equal(retry.approval, null, "no second approval");
    assert.equal(retry.view.ok, true);
    assert.equal(s.approvals.started.length, 1);
    assert.equal(s.hcs.of("HOUSE").length, 1, "one HOUSE message for the batch");
    const third = await publishDone(s.house, String(batch));
    assert.deepEqual(third.view.data, retry.view.data);
    assert.deepEqual(s.arkiv.batches.map((b) => b.kind), ["house", "stamp"], "nothing written twice");
  });

  it("the stamps fail after the house rows landed: the retry stamps the rows it finds, writing no row again", async () => {
    const s = setup();
    const { batch } = await s.house.stage(s.body());
    const realStamps = s.arkiv.writeStamps.bind(s.arkiv);
    let refuse = true;
    s.arkiv.writeStamps = async (specs) => {
      if (refuse) throw new (await import("../src/arkiv/client.js")).ArkivError("reverted");
      return realStamps(specs);
    };
    const first = await publishDone(s.house, String(batch));
    assert.deepEqual([first.view.ok, first.view.failure], [false, "ls_publish_fail"]);
    assert.deepEqual([s.arkiv.runs.length, s.arkiv.stamps.length], [6, 0]);
    assert.deepEqual(await s.arkiv.boardRuns("MDGP", 1), [], "unstamped house rows are on no board");
    refuse = false;
    const retry = await publishDone(s.house, String(batch));
    assert.equal(retry.view.ok, true, JSON.stringify(retry.view));
    assert.equal(retry.approval, null, "no second approval");
    assert.deepEqual(s.arkiv.batches.map((b) => b.kind), ["house", "stamp"], "the rows once, the stamps once");
    assert.deepEqual(retry.view.data.runs, s.arkiv.runs.map((r) => r.key));
    assert.equal((await s.arkiv.boardRuns("MDGP", 1)).length, 6);
  });

  it("a retry never stamps a found house run whose season, game or splits differ from this batch's: ls_publish_fail, no stamp", async () => {
    for (const [what, change] of [
      ["season", (v: Record<string, unknown>) => (v.season = 2)],
      ["game", (v: Record<string, unknown>) => (v.game = "SHIP")],
      ["splits", (v: Record<string, unknown>) => (v.s1 = 2000)],
    ] as const) {
      const s = setup();
      const { batch } = await s.house.stage(s.body());
      const realStamps = s.arkiv.writeStamps.bind(s.arkiv);
      let refuse = true;
      s.arkiv.writeStamps = async (specs) => {
        if (refuse) throw new (await import("../src/arkiv/client.js")).ArkivError("reverted");
        return realStamps(specs);
      };
      assert.equal((await publishDone(s.house, String(batch))).view.failure, "ls_publish_fail");
      change(s.arkiv.runs[0].spec.values as unknown as Record<string, unknown>); // the row on Arkiv is not what this batch replayed
      refuse = false;
      const retry = await publishDone(s.house, String(batch));
      assert.equal(retry.view.failure, "ls_publish_fail", what);
      assert.ok(s.lines.some((l) => l.includes(`BOT-A1's run on Arkiv (${s.arkiv.runs[0].key}) has another `)), s.lines.join(" | "));
      assert.equal(s.arkiv.stamps.length, 0, `${what}: nothing stamped`);
    }
  });

  it("an unfunded house wallet is refused before staging and before the owner's World approval is asked for", async () => {
    const s = setup();
    s.arkiv.balances.set(HOUSE_WALLET, 0n);
    assert.equal(await refusal(s.house.stage(s.body())), `503 house_not_funded: the house wallet ${HOUSE_WALLET} has 0.0000 tGLM: npm run arkiv:fund -- --to ${HOUSE_WALLET} --amount 1`);
    s.arkiv.balances.set(HOUSE_WALLET, 10n ** 18n);
    const { batch } = await s.house.stage(s.body());
    s.arkiv.balances.set(HOUSE_WALLET, 10n ** 15n); // below HOUSE_MIN_WEI (0.01 tGLM)
    assert.match(await refusal(s.house.publish({ batch })), /^503 house_not_funded: the house wallet .* has 0\.0010 tGLM/);
    assert.equal(s.approvals.started.length, 0, "no World approval asked for");
    assert.deepEqual(s.arkiv.batches, [], "nothing written");
  });

  it("the probe reads the house wallet's balance: unfunded, /health turns the house off and says why", async () => {
    const { ArkivService } = await import("../src/arkiv/service.js");
    const { MockPayments } = await import("../src/arkiv/payments.js");
    const arkiv = new FakeArkiv();
    const lines: string[] = [];
    const svc = new ArkivService({ publicRpc: "x", chainId: arkiv.chain, season: 1, priceC: 10, checker: CHECKER, arkiv, publisher: null, payments: new MockPayments(false, { claimReceipt: () => false }), ghostSecret: "", problems: [], boardFile: "", snapshotFile: "", house: HOUSE_WALLET, log: (l) => lines.push(l) });
    await svc.probe();
    assert.equal(svc.houseFunds(), null, "funded");
    arkiv.balances.set(HOUSE_WALLET, 0n);
    await svc.probe();
    const why = svc.houseFunds();
    assert.equal(why, `the house wallet ${HOUSE_WALLET} has 0.0000 tGLM: npm run arkiv:fund -- --to ${HOUSE_WALLET} --amount 1`);
    assert.ok(lines.some((l) => l === `arkiv: ${why}`), lines.join(" | "));
    const h = pivotHealth({ consoles: null, splits: true, scout: null, house: {}, houseProblems: [], houseFunds: why, arkivWrites: true });
    assert.deepEqual([h.house, h.house_off], [false, why]);
  });

  it("a batch written before by the checker itself (no stamps) is published again from the house wallet, after a new approval", async () => {
    const s = setup();
    const { batch } = await s.house.stage(s.body());
    // As the checker-era service left it: written, its rows the checker's own, never stamped.
    for (const [i, log] of s.logs.entries()) s.arkiv.addRun({ ...houseRun({ game: "MDGP", season: 1, rules: 4, frames: LAPS[i].reduce((a, b) => a + b, 0), log_h: sha256Hex(log), label: `BOT-A${i + 1}`, runner: "r", tool: "t", log_enc: new Uint8Array(4), splits: LAPS[i] }) }, CHECKER, { stamp: false });
    s.store.updateHouseBatch(String(batch), { status: "written", result: { runs: s.arkiv.runs.map((r) => r.key), listings: [], txs: [`0x${"e".repeat(64)}`] } });
    const r = await publishDone(s.house, String(batch));
    assert.notEqual(r.approval, null, "the owner approves this batch again in World App");
    assert.equal(r.view.ok, true, JSON.stringify(r.view));
    assert.deepEqual(s.arkiv.batches.map((b) => b.kind), ["house", "stamp"]);
    const board = await s.arkiv.boardRuns("MDGP", 1);
    assert.equal(board.length, 6);
    assert.ok(board.every((x) => x.owner === HOUSE_WALLET), "the house wallet's rows rank, the checker's old ones do not");
    assert.ok(!(r.view.data.txs as string[]).includes(`0x${"e".repeat(64)}`), "the old checker transaction is not this batch's any more");
  });

  it("a retry after a partial landing counts the batch's own rows and writes the rest", async () => {
    const s = setup({ txPairs: 3 });
    const { batch } = await s.house.stage(s.body());
    s.arkiv.maxCreates = 6;
    s.arkiv.failWrites = 0;
    // The first chunk lands, the second is refused.
    const realWrite = s.arkiv.writeHouse.bind(s.arkiv);
    let calls = 0;
    s.arkiv.writeHouse = async (pairs) => {
      calls += 1;
      if (calls === 3) throw new (await import("../src/arkiv/client.js")).ArkivError("reverted");
      return realWrite(pairs);
    };
    const first = await publishDone(s.house, String(batch));
    assert.equal(first.view.failure, "ls_publish_fail");
    assert.equal(s.arkiv.runs.length, 3);
    const retry = await publishDone(s.house, String(batch));
    assert.equal(retry.view.ok, true, JSON.stringify(retry.view));
    assert.equal(s.arkiv.runs.length, 6, "the first three were not written again");
    assert.deepEqual((retry.view.data.runs as string[]).length, 6);
  });

  it("a batch refused at 2N creates is split into HOUSE_TX_PAIRS pairs a transaction", async () => {
    const s = setup({ txPairs: 3 });
    const { batch } = await s.house.stage(s.body());
    s.arkiv.maxCreates = 6;
    const r = await publishDone(s.house, String(batch));
    assert.equal(r.view.ok, true, JSON.stringify(r.view));
    assert.deepEqual(s.arkiv.batches.map((b) => [b.kind, b.creates]), [["house", 6], ["house", 6], ["stamp", 6]]);
    assert.equal((r.view.data.txs as string[]).length, 2);
    assert.deepEqual(s.arkiv.runs.map((x) => x.spec.values.label), ["BOT-A1", "BOT-A2", "BOT-A3", "BOT-A4", "BOT-A5", "BOT-A6"]);
    assert.ok(s.lines.some((l) => /splitting into 3 pairs a transaction/.test(l)));
  });

  it("a copy on the board at write time is ls_copied", async () => {
    const s = setup();
    const { batch } = await s.house.stage(s.body());
    s.approvals.hold = true;
    const p = await s.house.publish({ batch });
    s.arkiv.addRun({ game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames: 6169, log_h: sha256Hex(s.logs[2]), runner: "0".repeat(16), book: "ANY-XYZ", human: true, tool: "t" }, WALLET_A);
    s.approvals.hold = false;
    await waitFor(() => s.house.view(p.id)?.stage === "done", 5000);
    assert.equal(s.house.view(p.id)?.failure, "ls_copied");
  });

  it("without the HOUSE message (Hedera off) the batch goes on without hcs", async () => {
    const s = setup({ hedera: false });
    const { batch } = await s.house.stage(s.body());
    const r = await publishDone(s.house, String(batch));
    assert.equal(r.view.ok, true);
    assert.equal(r.view.data.hcs, null);
    assert.equal(s.arkiv.listings[0].spec.values.hcs, undefined);
    const t = setup();
    t.hcs.refuse = 1;
    const tb = await t.house.stage(t.body());
    const tr = await publishDone(t.house, String(tb.batch));
    assert.equal(tr.view.ok, true);
    assert.equal(tr.view.data.hcs, null);
    assert.ok(t.lines.some((l) => /HOUSE message not accepted/.test(l)));
  });

  it("publishing an unknown or expired batch is 404", async () => {
    const s = setup();
    assert.match(await refusal(s.house.publish({ batch: "abcdef" })), /^404 unknown_batch/);
    assert.match(await refusal(s.house.publish({ batch: "xyz" })), /^400 bad_body/);
  });
});

describe("house rows and the HOUSE message", () => {
  it("the row builders take no human, book or credential and always write human false", () => {
    const run = houseRun({ game: "MDGP", season: 1, rules: 4, frames: 6236, log_h: "a".repeat(64), label: "BOT-A2", runner: "r", tool: "t", log_enc: new Uint8Array(1), splits: [2248, 1994, 1994] });
    assert.equal(run.human, false);
    assert.equal(run.book, undefined);
    assert.equal(run.credential, undefined);
    // @ts-expect-error a house row cannot be given a book
    houseRun({ game: "MDGP", season: 1, rules: 4, frames: 1, log_h: "a", label: "BOT-A1", runner: "r", tool: "t", log_enc: new Uint8Array(1), splits: [1], book: "ANY-6PS" });
    const listing = houseListing({ game: "MDGP", season: 1, frames: 6236, log_h: "a".repeat(64), priceC: 10, seller: "r", label: "BOT-A2", pay_to: HOUSE });
    assert.deepEqual([listing.human, listing.book, listing.label, listing.pay_to], [false, undefined, "BOT-A2", HOUSE]);
  });

  it("the HOUSE message fits one chunk at its maximum lengths", () => {
    const action = houseText("ffffff", 8, "MARINE DRIVE GP", 1_000_000, "0.0.9999999999");
    const bytes = houseMessage({ batch: "ffffff", book: "ANY-ZZZZZZZZ", game: "MDGP", n: 8, price: "10000.00", pay_to: "0.0.9999999999", action });
    assert.ok(bytes.length <= HCS_MAX_BYTES, `${bytes.length} B`);
  });
});

describe("the house routes", () => {
  it("POST /house/batch, POST /house/publish, GET /house/publish/{id}; errors are {error, detail}; logs are shapes", async () => {
    const s = setup();
    const lines: string[] = [];
    const server = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null, house: s.house, log: (l) => lines.push(l) });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const call = async (method: string, path: string, body?: unknown) => {
      const r = await fetch(`${base}${path}`, { method, headers: { "content-type": "application/json" }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
      return { status: r.status, json: (await r.json()) as Record<string, any> };
    };
    try {
      const st = await call("POST", "/house/batch", s.body());
      assert.equal(st.status, 200);
      const pub = await call("POST", "/house/publish", { batch: st.json.batch });
      assert.equal(pub.status, 200);
      assert.deepEqual(Object.keys(pub.json).sort(), ["action", "approval", "id"]);
      let v: Record<string, any>;
      do v = (await call("GET", `/house/publish/${pub.json.id}`)).json;
      while (v.stage !== "done");
      assert.equal(v.ok, true);
      assert.deepEqual(await call("POST", "/house/batch", { game: "MDGP", logs: [] }), { status: 400, json: { error: "bad_body", detail: "logs: 1 to 8" } });
      assert.deepEqual(await call("GET", "/house/publish/h-00000000"), { status: 404, json: { error: "unknown_id" } });
      const big = await fetch(`${base}/house/batch`, { method: "POST", body: "x".repeat(200 * 1024) });
      assert.equal(big.status, 400);
      assert.ok(lines.some((l) => l.startsWith("POST /house/batch 200")));
      assert.ok(lines.some((l) => l.startsWith("POST /house/publish 200")));
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });
});


/**
 * PB's scout: eligibility (one test per rule), the cap of 12 fastest first, the facts JSON, the
 * model's pick or the rule with its note, the fact check, the scout's failures, and the routes.
 * Fake Arkiv, fake checker and splits, fake Groq, a real console registry.
 */
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { describe, it } from "node:test";
import type { ListingRow, RunRow } from "../src/arkiv/client.js";
import { encryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { houseListing, houseRun } from "../src/arkiv/house.js";
import { Consoles } from "../src/consoles.js";
import { nullifierKey } from "../src/hmac.js";
import { eligible, factsFor, MODEL_MAX, modelSet, rulePick, type Candidate } from "../src/scout/eligible.js";
import type { GroqAnswer } from "../src/scout/groq.js";
import { ScoutService, type ScoutView } from "../src/scout/scout.js";
import { bestGainLap, factCheck, ruleText, templateText } from "../src/scout/text.js";
import { buildServer, makeHealth } from "../src/server.js";
import { Store } from "../src/store.js";
import { FakeArkiv, FakeChecker, makeLog } from "./fake-arkiv.js";
import { FakeGroq } from "./fake-groq.js";
import { HOUSE } from "./fake-hedera.js";
import { FakeSplits } from "./fake-splits.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const GHOST = "ef".repeat(32);
const YOU = [2140, 2165, 2109]; // ANY-6PS's listed run, 1:46.90
const VARIANTS: Array<[string, number[]]> = [
  ["BOT-A1", [2087, 1995, 2088]],
  ["BOT-A2", [2248, 1994, 1994]],
  ["BOT-A3", [2087, 2088, 1994]],
  ["BOT-A4", [2168, 2078, 1994]],
  ["BOT-A5", [2087, 2080, 2077]],
  ["BOT-A6", [2168, 2078, 2079]],
];
const CONSOLE = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

let seed = 0;
/** A BOT run and its listing, as a house batch writes them. */
function addBot(arkiv: FakeArkiv, label: string, laps: number[] | null, frames = laps ? sum(laps) : 6200, over: { pay_to?: string; human?: boolean; price?: string; label?: string } = {}) {
  seed += 1;
  const log = makeLog("MDGP", 4, frames, 64, 9000 + seed);
  const logH = sha256Hex(log);
  const run = arkiv.addRun({
    ...houseRun({ game: "MDGP", season: 1, rules: 4, frames, log_h: logH, label: over.label ?? label, runner: `${String(seed).padStart(16, "0")}`, tool: "t", log_enc: encryptGhost(GHOST, logH, log), splits: laps ?? [] }),
    ...(over.human ? { human: true } : {}),
  });
  const listing = arkiv.addListing(run, {
    ...houseListing({ game: "MDGP", season: 1, frames, log_h: logH, priceC: 10, seller: "s", label: over.label ?? label, pay_to: over.pay_to ?? HOUSE }),
    ...(over.human ? { human: true } : {}),
    ...(over.price ? { price: over.price } : {}),
  });
  return { run, listing, logH };
}

function setup(o: { groq?: FakeGroq | null; youLaps?: number[] | "none"; usdc?: bigint; spent?: number; bots?: Array<[string, number[]]> } = {}) {
  const store = new Store(tempDir(), SECRET);
  const buyer = store.claimBook(nullifierKey(SECRET, "act", `scout-${++seed}`), "Orb", "aaaaaaaaaaaaaaaa", 1, "session_b").record;
  const consoles = new Consoles({ store, secret: SECRET, approvals: null });
  consoles.bindAtSignup(CONSOLE, buyer.book, "signup");
  const arkiv = new FakeArkiv();
  // YOU's own listed run: own book, never a candidate.
  const youLog = makeLog("MDGP", 4, sum(YOU), 64, 77);
  const youKey = arkiv.addRun({ game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames: sum(YOU), log_h: sha256Hex(youLog), runner: buyer.runner_id, book: buyer.book, human: true, credential: "Orb", tool: "t", s1: YOU[0], s2: YOU[1], s3: YOU[2], split_kind: "lap", log_enc: encryptGhost(GHOST, sha256Hex(youLog), youLog) });
  arkiv.addListing(youKey, { game: "MDGP", season: 1, frames: sum(YOU), log_h: sha256Hex(youLog), price: "0.1", seller: buyer.runner_id, book: buyer.book, human: true, pay_to: "0.0.5123456" });
  const bots = (o.bots ?? VARIANTS).map(([label, laps]) => ({ label, ...addBot(arkiv, label, laps) }));
  const checker = new FakeChecker(sum(YOU));
  const splits = new FakeSplits(o.youLaps === "none" ? [1, 1] : (o.youLaps ?? YOU));
  if (o.youLaps === "none") splits.missing = true;
  const groq = o.groq === undefined ? new FakeGroq() : o.groq;
  const lines: string[] = [];
  const blocked = new Set<string>();
  const scout = new ScoutService({
    store,
    arkiv,
    checker,
    splits,
    agent: { canReceive: async (a) => !blocked.has(a), agentUsdc: async () => o.usdc ?? 20_000_000n },
    groq,
    consoles,
    season: 1,
    priceC: 10,
    houseId: HOUSE,
    bookDayC: 100,
    reasonMax: 110,
    on: () => true,
    log: (l) => lines.push(l),
  });
  if (o.spent) {
    store.reservePurchase("k", { id: "p-1", buyer: buyer.book, game: "MDGP", seller: "BOT-A9", run: "0x1", listing: "0x2", pay_to: HOUSE, price_c: o.spent, day: new Date().toLocaleDateString("sv"), state: "reserved", at: 1 }, { bookDayC: 1000, agentDayC: 1000 });
  }
  const body = (over: Record<string, unknown> = {}) => ({ book: buyer.book, game: "MDGP", log: Buffer.from(makeLog("MDGP", 4, sum(YOU), 64, 77)).toString("base64"), console: CONSOLE, price_c: 10, ...over });
  return { store, buyer, consoles, arkiv, bots, checker, splits, groq, lines, blocked, scout, body };
}

async function run(s: ReturnType<typeof setup>, over: Record<string, unknown> = {}): Promise<ScoutView & { id: string }> {
  const { id, expires_s } = s.scout.start(s.body(over));
  assert.match(id, /^s-[0-9a-f]{8}$/);
  assert.equal(expires_s, 60);
  await waitFor(() => s.scout.view(id)?.stage === "done");
  return { ...s.scout.view(id)!, id };
}

/** The model picks this candidate (by name) for this lap, with this reason. */
const picks = (name: string, lap: number, reason: string) => (f: { candidates: Array<{ id: string; name: string }> }): GroqAnswer => ({ ok: true, pick: f.candidates.find((c) => c.name === name)!.id, lap, reason, ms: 812 });

describe("eligibility (code, before any model)", () => {
  async function cands(mut: (arkiv: FakeArkiv, s: ReturnType<typeof setup>) => void, you = { frames: sum(YOU), splits: YOU }) {
    const s = setup({ bots: [] });
    mut(s.arkiv, s);
    const runs: RunRow[] = await s.arkiv.boardRuns("MDGP", 1);
    const listings: ListingRow[] = await s.arkiv.boardListings("MDGP", 1);
    return eligible({ buyer: s.buyer.book, game: "MDGP", you, runs, listings, priceC: 10, houseId: HOUSE, canReceive: async (a) => !s.blocked.has(a) });
  }
  it("a BOT ahead overall is a candidate; the buyer's own listing never is", async () => {
    const e = await cands((a) => addBot(a, "BOT-A2", [2248, 1994, 1994]));
    assert.deepEqual(e.candidates.map((c) => c.name), ["BOT-A2"]);
    assert.deepEqual(e.candidates[0].splits, [2248, 1994, 1994]);
  });
  it("another price is not a candidate", async () => assert.equal((await cands((a) => addBot(a, "BOT-A2", [2248, 1994, 1994], undefined, { price: "0.25" }))).candidates.length, 0));
  it("a pay_to that cannot take USDC is not a candidate", async () => {
    assert.equal((await cands((a, s) => (addBot(a, "BOT-A2", [2248, 1994, 1994], undefined, { pay_to: "0.0.666" }), s.blocked.add("0.0.666")))).candidates.length, 0);
  });
  it("a run whose log_h differs from the listing's is not a candidate", async () => {
    const e = await cands((a) => {
      const b = addBot(a, "BOT-A2", [2248, 1994, 1994]);
      a.listings.find((l) => l.key === b.listing)!.spec.values.log_h = "0".repeat(64);
    });
    assert.equal(e.candidates.length, 0);
  });
  it("a listing whose run is not on the board is not a candidate", async () => {
    const e = await cands((a) => {
      const b = addBot(a, "BOT-A2", [2248, 1994, 1994]);
      a.runs.find((r) => r.key === b.run)!.live = false;
    });
    assert.equal(e.candidates.length, 0);
  });
  it("a label listing that does not pay the house, or says HUMAN, or is not a BOT label: skipped and counted", async () => {
    const e = await cands((a) => {
      addBot(a, "BOT-A1", [2087, 1995, 2088], undefined, { pay_to: "0.0.5123456" });
      addBot(a, "BOT-A2", [2248, 1994, 1994], undefined, { human: true });
      addBot(a, "TEAM", [2087, 2088, 1994]);
      addBot(a, "BOT-A4", [2168, 2078, 1994]);
    });
    assert.deepEqual(e.candidates.map((c) => c.name), ["BOT-A4"]);
    assert.equal(e.refusedLabels, 3);
  });
  it("slower overall and in every lap: not a candidate; slower overall but faster in a lap: a candidate", async () => {
    const e = await cands((a) => {
      addBot(a, "BOT-A1", [2200, 2200, 2200]);
      addBot(a, "BOT-A2", [2300, 2000, 2200]);
    });
    assert.deepEqual(e.candidates.map((c) => c.name), ["BOT-A2"]);
  });
  it("without splits a candidate still counts (for the rule), the model never sees it", async () => {
    const e = await cands((a) => addBot(a, "BOT-A1", null, 6200));
    assert.equal(e.candidates.length, 1);
    assert.equal(e.candidates[0].splits, null);
    assert.equal(modelSet(e.candidates).length, 0);
  });
  it("at most 12 go to the model, the fastest first", async () => {
    const e = await cands((a) => {
      for (let i = 0; i < 15; i++) addBot(a, `BOT-B${(i % 8) + 1}`, [2000 + 15 - i, 2000, 2000]);
    });
    const set = modelSet(e.candidates);
    assert.equal(MODEL_MAX, 12);
    assert.equal(set.length, 12);
    assert.deepEqual(set.map((c) => c.frames), [...set.map((c) => c.frames)].sort((x, y) => x - y));
    assert.equal(set[0].frames, 6001);
  });
});

describe("the rule and the facts", () => {
  const c = (name: string, laps: number[] | null, frames = laps ? sum(laps) : 6000) => ({ name, frames, splits: laps }) as unknown as Candidate;
  it("the rule: the largest time below YOU's; none ahead: the most gained in one lap", () => {
    const you = { frames: sum(YOU), splits: YOU };
    assert.equal(rulePick([c("BOT-A1", VARIANTS[0][1]), c("BOT-A6", VARIANTS[5][1]), c("BOT-A2", VARIANTS[1][1])], you)?.name, "BOT-A6");
    assert.equal(rulePick([c("BOT-X1", [2300, 2100, 2200]), c("BOT-X2", [2300, 2000, 2200])], you)?.name, "BOT-X2");
  });
  it("the facts JSON, exactly (seconds with 2 decimals, ids c1..cN, no book, console or key)", () => {
    const f = factsFor("MARINE DRIVE GP", { frames: sum(YOU), splits: YOU }, [c("BOT-A2", [2248, 1994, 1994])]);
    assert.equal(
      JSON.stringify(f),
      '{"game":"MARINE DRIVE GP","laps":3,"you":{"total_s":106.9,"laps_s":[35.67,36.08,35.15]},"candidates":[{"id":"c1","name":"BOT-A2","total_s":103.93,"laps_s":[37.47,33.23,33.23],"you_lose_s":[-1.8,2.85,1.92]}]}',
    );
  });
  it("our sentences", () => {
    assert.equal(templateText("BOT-A2", YOU, [2248, 1994, 1994], 2).text, "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s.");
    assert.deepEqual(templateText("BOT-A2", YOU, [2248, 1994, 1994], 1), { lap: 2, text: "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s." }, "a lap the pick is slower in becomes its best-gain lap");
    assert.equal(bestGainLap(YOU, [2248, 1994, 1994]), 2);
    assert.equal(ruleText("BOT-A6", 6325, 6414), "BOT-A6 is the listed ghost just ahead of you: 1:45.42 against your 1:46.90.");
  });
});

describe("the fact check", () => {
  const ctx = { name: "BOT-A2", laps: 3, you: { frames: sum(YOU), splits: YOU }, it: { frames: 6236, splits: [2248, 1994, 1994] }, max: 110 };
  it("passes a reason whose every number is in the facts", () => {
    assert.deepEqual(factCheck("  You lose 2.85 s in lap 2: BOT-A2 does it in 33.23 s, you in 36.08 s. ", ctx), { ok: true, text: "You lose 2.85 s in lap 2: BOT-A2 does it in 33.23 s, you in 36.08 s." });
    assert.equal(factCheck("BOT-A2 is 1.8 s slower in lap 1 but 2.9 s faster in lap 2.", ctx).ok, true, "absolute values and 1-decimal rounding");
    assert.equal(factCheck("BOT-A2 runs 1:43.93 to your 1:46.90.", ctx).ok, true, "m:ss.cc times of YOU and the pick");
  });
  it("normalises the model's typographic spaces, dashes and quotes to ASCII (gpt-oss writes '2.85\\u202fs')", () => {
    const fancy = "You lose 2.85 s in lap 2 – BOT‑A2’s lap is 33.23 s…";
    assert.deepEqual(factCheck(fancy, ctx), { ok: true, text: "You lose 2.85 s in lap 2 - BOT-A2's lap is 33.23 s..." });
    assert.match((factCheck("BOT-A2 é is faster in lap 2.", ctx) as { why: string }).why, /ASCII/, "other non-ASCII still refused");
  });
  it("an invented number, another runner's name, a banned word, over 110 characters, not ASCII: refused", () => {
    assert.match((factCheck("You lose 3.50 s in lap 2.", ctx) as { why: string }).why, /3\.50/);
    assert.match((factCheck("BOT-A6 is faster in lap 2.", ctx) as { why: string }).why, /BOT-A6/);
    assert.match((factCheck("Take ANY-6PS's line in lap 2.", ctx) as { why: string }).why, /ANY-6PS/);
    assert.match((factCheck("Buy BOT-A2 to win lap 2.", ctx) as { why: string }).why, /win/);
    assert.match((factCheck("BOT-A2 is the best price for lap 2.", ctx) as { why: string }).why, /price/);
    assert.match((factCheck("A human drove BOT-A2.", ctx) as { why: string }).why, /human/);
    assert.match((factCheck("Pay for BOT-A2.", ctx) as { why: string }).why, /pay/);
    assert.match((factCheck("BOT-A2 at 1:44.00 beats you.", ctx) as { why: string }).why, /1:44\.00/);
    assert.match((factCheck(`Lap 2 ${"a".repeat(110)}`, ctx) as { why: string }).why, /over 110/);
    assert.match((factCheck("Lap 2 is faster → BOT-A2.", ctx) as { why: string }).why, /ASCII/);
    assert.match((factCheck("Pick c1 for lap 2.", ctx) as { why: string }).why, /candidate id/);
  });
});

describe("the scout: the model's pick, or the rule", () => {
  it("model ok: by model, the reason checked, the pick's laps and every field the console needs", async () => {
    const groq = new FakeGroq();
    groq.answer = picks("BOT-A2", 2, "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s.");
    const s = setup({ groq });
    const v = await run(s);
    assert.equal(v.ok, true, JSON.stringify(v));
    const bot = s.bots.find((b) => b.label === "BOT-A2")!;
    assert.deepEqual(v.data, {
      scout: v.id,
      seller: "BOT-A2",
      pick: { name: "BOT-A2", label: "BOT-A2", book: null, listing: bot.listing, run: bot.run, log_h: bot.logH, frames: 6236, time: "1:43.93", splits: [2248, 1994, 1994], price_c: 10, pay_to: HOUSE, human: false },
      you: { frames: 6414, time: "1:46.90", splits: YOU },
      lap: 2,
      reason: "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s.",
      by: "model",
      text: "model",
      model: "openai/gpt-oss-120b",
      note: null,
      candidates: 6,
      skipped: 0,
    });
    assert.equal(groq.asked[0].candidates.length, 6);
    assert.equal(JSON.stringify(groq.asked[0]).includes(s.buyer.book), false, "the facts never name the buyer's book");
    assert.ok(s.lines.includes(`scout ${v.id} ${s.buyer.book} MDGP: model picked BOT-A2 (lap 2), 812 ms`), s.lines.join("\n"));
    assert.deepEqual(s.scout.held(v.id), {
      buyer: s.buyer.book,
      game: "MDGP",
      listing: bot.listing,
      intent: { by: "model", model: "openai/gpt-oss-120b", lap: 2, you: YOU, it: [2248, 1994, 1994], text: "model", why: v.data.reason },
    });
  });

  it("a reason that does not check out: the model's pick, our template (text: template)", async () => {
    const groq = new FakeGroq();
    groq.answer = picks("BOT-A4", 3, "You lose 4.20 s in lap 3, buy it now.");
    const v = await run(setup({ groq }));
    assert.deepEqual([v.data.by, v.data.text, v.data.seller, v.data.lap], ["model", "template", "BOT-A4", 3]);
    assert.equal(v.data.reason, "You lose 1.92 s in lap 3: BOT-A4 runs it in 33.23 s, you in 35.15 s.");
  });

  const fallbacks: Array<[string, GroqAnswer, string]> = [
    ["a timeout", { ok: false, why: "timeout", ms: 6000 }, "the model did not answer in 6 s"],
    ["a 429", { ok: false, why: "rate_limit", ms: 40 }, "Groq rate limit"],
    ["an invalid pick or malformed JSON", { ok: false, why: "bad_answer", ms: 900 }, "the model's answer did not check out"],
    ["Groq unreachable", { ok: false, why: "unreachable", ms: 3 }, "Groq could not be reached"],
  ];
  for (const [name, answer, note] of fallbacks) {
    it(`${name}: the rule (the ghost just ahead), with the note`, async () => {
      const groq = new FakeGroq();
      groq.answer = answer;
      const s = setup({ groq });
      const v = await run(s);
      assert.deepEqual([v.ok, v.data.by, v.data.model, v.data.seller, v.data.note, v.data.text], [true, "rule", null, "BOT-A6", note, "template"]);
      assert.equal(v.data.reason, "BOT-A6 is the listed ghost just ahead of you: 1:45.42 against your 1:46.90.");
      assert.equal(s.scout.mode(), "model");
    });
  }

  it("the log says how the model failed", async () => {
    const groq = new FakeGroq();
    groq.answer = { ok: false, why: "timeout", ms: 6000 };
    const s = setup({ groq });
    const v = await run(s);
    assert.ok(s.lines.includes(`scout ${v.id} ${s.buyer.book} MDGP: rule: BOT-A6 (model timed out after 6000 ms)`), s.lines.join("\n"));
  });

  it("a 401: the rule, and /health says rule until restart", async () => {
    const groq = new FakeGroq();
    groq.answer = { ok: false, why: "refused", ms: 50 };
    const s = setup({ groq });
    assert.equal(s.scout.mode(), "model");
    const v = await run(s);
    assert.equal(v.data.note, "Groq refused the key");
    assert.equal(s.scout.mode(), "rule");
    const again = await run(s);
    assert.equal(again.data.note, "no Groq key");
    assert.equal(groq.asked.length, 1, "not asked again");
  });

  it("no key: the rule, note 'no Groq key'", async () => {
    const s = setup({ groq: null });
    assert.equal(s.scout.mode(), "rule");
    const v = await run(s);
    assert.deepEqual([v.data.by, v.data.note, v.data.seller], ["rule", "no Groq key", "BOT-A6"]);
  });

  it("YOU without splits: the rule, note 'no lap times for your run'", async () => {
    const groq = new FakeGroq();
    const s = setup({ groq, youLaps: "none" });
    const v = await run(s);
    assert.deepEqual([v.data.by, v.data.note], ["rule", "no lap times for your run"]);
    assert.equal(groq.asked.length, 0);
    assert.equal((v.data.you as { splits: unknown }).splits, null);
  });

  it("YOU's replay refused: the rule on the log's own claim, note 'no lap times for your run'", async () => {
    const s = setup();
    s.checker.result = { hash_matches: false };
    const v = await run(s);
    assert.deepEqual([v.ok, v.data.by, v.data.note], [true, "rule", "no lap times for your run"]);
  });

  it("no listed ghost has lap times: the rule, note 'no lap times on the listed ghosts'", async () => {
    const s = setup({ bots: [] });
    addBot(s.arkiv, "BOT-A1", null, 6300);
    const v = await run(s);
    assert.deepEqual([v.data.by, v.data.note, v.data.seller, v.data.skipped, v.data.candidates], ["rule", "no lap times on the listed ghosts", "BOT-A1", 1, 1]);
  });

  it("only a lap-only candidate under the rule: the lap sentence, never 'just ahead'", async () => {
    const s = setup({ groq: null, bots: [["BOT-C1", [2300, 2000, 2200]]] });
    const v = await run(s);
    assert.equal(v.data.seller, "BOT-C1");
    assert.equal(v.data.reason, "You lose 2.75 s in lap 2: BOT-C1 runs it in 33.33 s, you in 36.08 s.");
  });
});

describe("the scout's failures", () => {
  it("nobody ahead", async () => {
    const v = await run(setup({ bots: [] }));
    assert.deepEqual([v.ok, v.failure], [false, "nobody_ahead"]);
  });
  it("the book's daily cap, the agent out of USDC: buy_budget", async () => {
    assert.equal((await run(setup({ spent: 95 }))).failure, "buy_budget");
    assert.equal((await run(setup({ spent: 90 }))).ok, true, "one more purchase fits");
    assert.equal((await run(setup({ usdc: 50_000n }))).failure, "buy_budget");
  });
  it("another book's console (or an unbound one): buy_suspended, why console_not_linked", async () => {
    const s = setup();
    const v = await run(s, { console: "ffeeddccbbaa99887766554433221100" });
    assert.deepEqual([v.failure, v.data], ["buy_suspended", { why: "console_not_linked" }]);
    const other = s.store.claimBook(nullifierKey(SECRET, "act", "someone-else"), "Orb", "bbbbbbbbbbbbbbbb", 1).record;
    const w = await run(s, { book: other.book });
    assert.deepEqual([w.failure, w.data], ["buy_suspended", { why: "console_not_linked" }]);
  });
  it("without a console (a terminal) the scout runs", async () => {
    const s = setup();
    const v = await run(s, { console: undefined });
    assert.equal(v.ok, true);
  });
  it("Arkiv down: buy_down", async () => {
    const s = setup();
    s.arkiv.readsDown = true;
    assert.equal((await run(s)).failure, "buy_down");
  });
  it("bad bodies are refused before a job; scout off answers 503", () => {
    const s = setup();
    assert.throws(() => s.scout.start(s.body({ book: "nope" })), /bad_body/);
    assert.throws(() => s.scout.start(s.body({ log: Buffer.from(makeLog("RUSH")).toString("base64") })), /bad_body/);
    assert.throws(() => s.scout.start(s.body({ console: "pi" })), /bad_body/);
    const off = new ScoutService({ ...(s.scout as unknown as { opts: ConstructorParameters<typeof ScoutService>[0] }).opts, on: () => false });
    assert.equal(off.mode(), "off");
    assert.throws(() => off.start(s.body()), /scout_off/);
  });
});

describe("the scout routes", () => {
  it("POST /scout -> {id, expires_s: 60}; GET /scout/{id}; errors carry buy_down; the log has shapes only", async () => {
    const s = setup({ groq: null });
    const lines: string[] = [];
    const server = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null, scout: s.scout, log: (l) => lines.push(l) });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const r = await fetch(`${base}/scout`, { method: "POST", body: JSON.stringify(s.body()) });
      const j = (await r.json()) as { id: string; expires_s: number };
      assert.equal(r.status, 200);
      assert.deepEqual(Object.keys(j).sort(), ["expires_s", "id"]);
      let v: Record<string, unknown>;
      do v = (await (await fetch(`${base}/scout/${j.id}`)).json()) as Record<string, unknown>;
      while (v.stage !== "done");
      assert.equal(v.ok, true);
      const bad = await fetch(`${base}/scout`, { method: "POST", body: JSON.stringify({ book: "x" }) });
      assert.deepEqual([bad.status, await bad.json()], [400, { error: "bad_body", failure: "buy_down" }]);
      const big = await fetch(`${base}/scout`, { method: "POST", body: "x".repeat(97 * 1024) });
      assert.equal(big.status, 400);
      const unknown = await fetch(`${base}/scout/s-00000000`);
      assert.deepEqual([unknown.status, await unknown.json()], [404, { error: "unknown_id", failure: "buy_down" }]);
      assert.ok(lines.some((l) => l.startsWith("POST /scout 200")));
      assert.ok(!lines.join("\n").includes(CONSOLE));
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });
});

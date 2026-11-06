/**
 * The Groq request, exactly: the pinned model, strict structured output with the candidates and laps
 * as enums, no stream, the key only in the Authorization header, one try aborted after the timeout,
 * the error mapping, and the key never in an answer, an error or a log line.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { GROQ_DEFAULT_MODEL, loadConfig, scoutMode } from "../src/config.js";
import type { ScoutFacts } from "../src/scout/eligible.js";
import { GroqClient, groqBody, readAnswer, SYSTEM } from "../src/scout/groq.js";
import { completion, fakeFetch } from "./fake-groq.js";

const KEY = "gsk_test_key_never_shown_0123456789";
const FACTS: ScoutFacts = {
  game: "MARINE DRIVE GP",
  laps: 3,
  you: { total_s: 106.9, laps_s: [35.67, 36.08, 35.15] },
  candidates: [
    { id: "c1", name: "BOT-A2", total_s: 103.93, laps_s: [37.47, 33.23, 33.23], you_lose_s: [-1.8, 2.85, 1.92] },
    { id: "c2", name: "BOT-A6", total_s: 105.42, laps_s: [36.13, 34.63, 34.65], you_lose_s: [-0.46, 1.45, 0.5] },
  ],
};

function client(reply: Parameters<typeof fakeFetch>[0], timeoutMs = 6000) {
  const f = fakeFetch(reply);
  const c = new GroqClient({ apiKey: KEY, model: "openai/gpt-oss-120b", base: "https://api.groq.com/openai/v1", timeoutMs, fetch: f.fn });
  return { c, sent: f.sent };
}

describe("the request body, pinned", () => {
  it("is exactly the spec's body: model, messages, strict json_schema with enums, reasoning low, no stream", () => {
    assert.deepEqual(groqBody("openai/gpt-oss-120b", FACTS), {
      model: "openai/gpt-oss-120b",
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: JSON.stringify(FACTS) },
      ],
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "scout_pick",
          strict: true,
          schema: {
            type: "object",
            additionalProperties: false,
            required: ["pick", "lap", "reason"],
            properties: {
              pick: { type: "string", enum: ["c1", "c2"] },
              lap: { type: "integer", enum: [1, 2, 3] },
              reason: { type: "string" },
            },
          },
        },
      },
      reasoning_effort: "low",
      include_reasoning: false,
      max_completion_tokens: 400,
    });
  });

  it("the system prompt is the spec's, verbatim", () => {
    assert.equal(
      SYSTEM,
      "You are PB's scout in a kart racing game. You get one player's lap times and the lap times of ghost runs that are for sale. Choose the ONE ghost that would help this player most: usually the one that is fastest in the lap where the player loses the most time. Answer only with JSON: pick is a candidate id from the list, lap is the lap your reason is about, reason is one short sentence of at most 110 characters, written to the player as 'you', that uses only numbers that appear in the facts. Never mention money, prices, people, winning or anything that is not in the facts.",
    );
  });

  it("goes to {GROQ_BASE}/chat/completions with the key only in the Authorization header, and no stream", async () => {
    const { c, sent } = client({ status: 200, body: completion({ pick: "c1", lap: 2, reason: "Lap 2." }) });
    const a = await c.choose(FACTS);
    assert.equal(a.ok, true);
    assert.equal(sent.length, 1, "one try");
    assert.equal(sent[0].url, "https://api.groq.com/openai/v1/chat/completions");
    assert.equal(sent[0].method, "POST");
    assert.equal(sent[0].headers.authorization, `Bearer ${KEY}`);
    assert.ok(!sent[0].body.includes(KEY), "the key is not in the body");
    const body = JSON.parse(sent[0].body);
    assert.equal(body.model, "openai/gpt-oss-120b");
    assert.equal("stream" in body, false);
    assert.equal("tools" in body, false);
    assert.ok(sent[0].signal instanceof AbortSignal);
  });

  it("the pinned model and the 6 s timeout are the defaults; the scout runs the rule without a key", () => {
    const cfg = loadConfig({}, ".");
    assert.equal(cfg.groq.model, GROQ_DEFAULT_MODEL);
    assert.equal(GROQ_DEFAULT_MODEL, "openai/gpt-oss-120b");
    assert.equal(cfg.groq.timeoutMs, 6000);
    assert.equal(cfg.groq.base, "https://api.groq.com/openai/v1");
    assert.equal(cfg.groq.reasonMax, 110);
    assert.equal(scoutMode(cfg), "rule");
    assert.equal(scoutMode(loadConfig({ GROQ_API_KEY: KEY }, ".")), "model");
    assert.equal(scoutMode(loadConfig({ GROQ_API_KEY: KEY }, "."), true), "rule", "a refused key: the rule until restart");
  });
});

describe("answers and the error mapping", () => {
  it("a good answer: pick, lap and reason, with the time it took", async () => {
    const { c } = client({ status: 200, body: completion({ pick: "c1", lap: 2, reason: "You lose 2.85 s in lap 2." }) });
    const a = await c.choose(FACTS);
    assert.deepEqual({ ...a, ms: 0 }, { ok: true, pick: "c1", lap: 2, reason: "You lose 2.85 s in lap 2.", ms: 0 });
  });
  const cases: Array<[string, Parameters<typeof fakeFetch>[0], string]> = [
    ["429", { status: 429, body: { error: { message: "rate limited" } } }, "rate_limit"],
    ["401", { status: 401, body: { error: { message: "Invalid API Key" } } }, "refused"],
    ["403", { status: 403, body: {} }, "refused"],
    ["500", { status: 500, body: {} }, "unreachable"],
    ["a network error", "network", "unreachable"],
    ["content that is not JSON", { status: 200, body: completion("I pick c1") }, "bad_answer"],
    ["a pick outside the enum", { status: 200, body: completion({ pick: "c9", lap: 2, reason: "x" }) }, "bad_answer"],
    ["a lap outside the enum", { status: 200, body: completion({ pick: "c1", lap: 4, reason: "x" }) }, "bad_answer"],
    ["no choices", { status: 200, body: { choices: [] } }, "bad_answer"],
    ["the schema check failing at Groq", { status: 400, body: { error: { code: "json_validate_failed" } } }, "bad_answer"],
  ];
  for (const [name, reply, why] of cases) {
    it(`${name} -> ${why}`, async () => {
      const a = await client(reply).c.choose(FACTS);
      assert.equal(a.ok, false);
      assert.equal(!a.ok && a.why, why);
      assert.ok(!JSON.stringify(a).includes(KEY));
    });
  }
  it("a model that never answers is aborted at the timeout: timeout, no retry", async () => {
    const { c, sent } = client("never", 30);
    const t0 = Date.now();
    // AbortSignal.timeout's timer does not hold the process open; the service's server does.
    const keep = setInterval(() => undefined, 10);
    const a = await c.choose(FACTS).finally(() => clearInterval(keep));
    assert.deepEqual([a.ok, !a.ok && a.why], [false, "timeout"]);
    assert.ok(Date.now() - t0 < 2000);
    assert.equal(sent.length, 1);
    assert.equal(sent[0].signal.aborted, true);
  });
  it("readAnswer checks the enums of the facts it was asked with", () => {
    assert.deepEqual(readAnswer('{"pick":"c2","lap":1,"reason":"r"}', FACTS), { pick: "c2", lap: 1, reason: "r" });
    assert.equal(readAnswer('{"pick":"c2","lap":1.5,"reason":"r"}', FACTS), null);
    assert.equal(readAnswer('{"pick":"c2","lap":1}', FACTS), null);
    assert.equal(readAnswer(null, FACTS), null);
  });
});

/** Arkiv's .env section and what keeps writes off (names only, never values). */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { arkivProblems, arkivReady, arkivRpcUrl, loadConfig, runExpiry } from "../src/config.js";

const NOW = Date.parse("2030-01-01T00:00:00Z");
const DAY = 86_400_000;
const iso = (ms: number) => new Date(ms).toISOString();

const FULL = {
  SERVER_SECRET: "s".repeat(40),
  ARKIV_CHECKER_KEY: `0x${"1".repeat(64)}`,
  ARKIV_GHOST_SECRET: "ab".repeat(32),
  ARKIV_SEASON: "1",
  ARKIV_SEASON_END: iso(NOW + 30 * DAY),
  CHECKER_REPLAY: "/opt/arca-sandbox/games/arcade/{game}/arcade_replay",
  CHECKER_WSL: "Ubuntu-24.04",
};

const problems = (env: Record<string, string>) => arkivProblems(loadConfig(env, "."), NOW);

describe("Arkiv config", () => {
  it("defaults: Rabdi's public RPC, chain 7794095, season 1, 10 cents, mock payments off", () => {
    const a = loadConfig({}, ".").arkiv;
    assert.equal(a.rpc, "https://rpc.rabdi.db-chain.testnet.arkiv.network");
    assert.equal(a.chainId, 7794095);
    assert.equal(a.season, 1);
    assert.equal(a.priceC, 10);
    assert.equal(a.mockPayments, false);
    assert.equal(loadConfig({ ARKIV_MOCK_PAYMENTS: "1" }, ".").arkiv.mockPayments, true);
  });

  it("a complete config is ready", () => {
    assert.deepEqual(problems(FULL), []);
    assert.equal(arkivReady(loadConfig(FULL, "."), NOW), true);
  });

  it("nothing set: every missing name is reported, no value is", () => {
    const p = problems({});
    for (const n of ["SERVER_SECRET", "ARKIV_CHECKER_KEY", "ARKIV_GHOST_SECRET", "ARKIV_SEASON_END", "CHECKER_REPLAY"]) assert.ok(p.includes(n), n);
    assert.ok(!p.includes("ARKIV_RPC") && !p.includes("ARKIV_CHAIN_ID") && !p.includes("ARKIV_SEASON"));
  });

  it("the checker key must be 0x + 64 hex; the ghost secret 64 hex", () => {
    assert.ok(problems({ ...FULL, ARKIV_CHECKER_KEY: "1".repeat(64) }).includes("ARKIV_CHECKER_KEY"));
    assert.ok(problems({ ...FULL, ARKIV_GHOST_SECRET: "xyz" }).includes("ARKIV_GHOST_SECRET"));
  });

  it("season end + 30 d must be after now and within ~180 d of it", () => {
    assert.deepEqual(problems({ ...FULL, ARKIV_SEASON_END: iso(NOW - 10 * DAY) }), [], "ended 10 days ago: runs still live 20 more");
    assert.ok(problems({ ...FULL, ARKIV_SEASON_END: iso(NOW - 31 * DAY) }).includes("ARKIV_SEASON_END"));
    assert.deepEqual(problems({ ...FULL, ARKIV_SEASON_END: iso(NOW + 149 * DAY) }), []);
    assert.ok(problems({ ...FULL, ARKIV_SEASON_END: iso(NOW + 151 * DAY) }).includes("ARKIV_SEASON_END"));
    assert.ok(problems({ ...FULL, ARKIV_SEASON_END: "next friday" }).includes("ARKIV_SEASON_END"));
    assert.ok(problems({ ...FULL, ARKIV_SEASON_END: "2030-02-01" }).includes("ARKIV_SEASON_END"), "an instant, not a date");
    assert.equal(runExpiry(loadConfig(FULL, ".").arkiv)?.getTime(), NOW + 60 * DAY);
  });

  it("the replay tool needs {game}; CHECKER_WSL a distro name", () => {
    assert.ok(problems({ ...FULL, CHECKER_REPLAY: "/opt/x/arcade_replay" }).includes("CHECKER_REPLAY"));
    assert.ok(problems({ ...FULL, CHECKER_WSL: "Ubuntu 24.04; rm" }).includes("CHECKER_WSL"));
    assert.deepEqual(problems({ ...FULL, CHECKER_WSL: "" }), [], "empty: run the tool directly (Linux)");
  });

  it("chain id, season and price must be integers", () => {
    assert.ok(problems({ ...FULL, ARKIV_CHAIN_ID: "0x76edaf" }).includes("ARKIV_CHAIN_ID"));
    assert.ok(problems({ ...FULL, ARKIV_SEASON: "one" }).includes("ARKIV_SEASON"));
    assert.ok(problems({ ...FULL, ARKIV_SEASON: "0" }).includes("ARKIV_SEASON"));
    assert.ok(problems({ ...FULL, ARKIV_GHOST_PRICE_C: "0.10" }).includes("ARKIV_GHOST_PRICE_C"));
  });

  it("the access key rides as the RPC URL's last path segment, and only there", () => {
    const a = loadConfig({ ARKIV_RPC: "https://rpc.example/", ARKIV_ACCESS_KEY: "k/ey" }, ".").arkiv;
    assert.equal(a.rpc, "https://rpc.example");
    assert.equal(arkivRpcUrl(a), "https://rpc.example/k%2Fey");
    assert.equal(arkivRpcUrl(loadConfig({}, ".").arkiv), "https://rpc.rabdi.db-chain.testnet.arkiv.network");
  });
});

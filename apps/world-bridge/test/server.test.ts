/** The HTTP contract's shapes, exactly as the launcher adapter reads them. */
import assert from "node:assert/strict";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { hashSignal } from "@worldcoin/idkit-core/hashing";
import { AgentPass } from "../src/agentpass.js";
import { IdkitSessions } from "../src/idkit.js";
import type { DeviceGrantClient, PollResult } from "../src/oidc.js";
import { buildServer, type Health } from "../src/server.js";
import { Store } from "../src/store.js";
import { CLIENT_ID, idToken, ISS, makeKeys, ORB, SECRET, tempDir, type TestKeys } from "./helpers.js";

let keys: TestKeys;
let server: Server;
let base = "";
let health: Health = { world: "ok", idkit: true, agentpass: true };
let pollScript: PollResult[] = [];
const logLines: string[] = [];
let idkit: IdkitSessions;
let agentpass: AgentPass;

before(async () => {
  keys = await makeKeys();
  const store = new Store(tempDir(), SECRET);
  idkit = new IdkitSessions({
    deps: {
      async createRequest(signal) {
        let i = 0;
        const result = {
          protocol_version: "4.0",
          nonce: "0x01",
          action: "anypercent-record-book",
          environment: "staging",
          responses: [
            {
              identifier: "selfie",
              signal_hash: hashSignal(signal),
              proof: ["0x1", "0x2", "0x3", "0x4", "0x5"],
              nullifier: "0x0def",
              issuer_schema_id: 11,
              expires_at_min: 9_999_999_999,
            },
          ],
        };
        const statuses = [
          { type: "waiting_for_connection" },
          { type: "awaiting_confirmation" },
          { type: "confirmed", result },
        ];
        return {
          connectorURI: "https://staging.world.org/verify?t=x&i=y&k=key-material",
          pollOnce: async () => statuses[Math.min(i++, 2)] as never,
        };
      },
      async verify() {
        return { status: 200, body: { success: true, environment: "staging", action: "anypercent-record-book" } };
      },
    },
    store,
    secret: SECRET,
    action: "anypercent-record-book",
    environment: "staging",
    pollMs: 2,
    log: (l) => logLines.push(l),
  });
  const idp: DeviceGrantClient = {
    discover: async () => ({ issuer: ISS, acrSupported: [ORB] }),
    start: async () => ({
      device_code: "never-out",
      user_code: "WDJB-MJHT",
      verification_uri: "https://auth.test.example/device",
      verification_uri_complete: "https://auth.test.example/device?user_code=WDJB-MJHT",
      expires_in: 1200,
      interval: 1,
    }),
    poll: async () =>
      pollScript.shift() ?? ({ kind: "error", error: "authorization_pending", status: 400 } as PollResult),
    keys: () => keys.getKey,
  };
  agentpass = new AgentPass({ idp, store, secret: SECRET, clientId: CLIENT_ID, msPerSecond: 2, log: (l) => logLines.push(l) });
  server = buildServer({ health: () => health, idkit, agentpass, log: (l) => logLines.push(l) });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

after(() => {
  idkit.stopAll();
  agentpass.stopAll();
  server.close();
});

async function call(method: string, path: string, body?: unknown, raw?: string) {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: raw ?? (body === undefined ? undefined : JSON.stringify(body)),
  });
  assert.match(res.headers.get("content-type") ?? "", /^application\/json/);
  return { status: res.status, json: (await res.json()) as Record<string, any> };
}

async function until(path: string, stage: string) {
  for (let i = 0; i < 500; i++) {
    const v = (await call("GET", path)).json;
    if (v.stage === stage) return v;
    await new Promise((r) => setTimeout(r, 3));
  }
  throw new Error(`never reached ${stage}`);
}

describe("GET /health", () => {
  it("answers exactly {world, idkit, agentpass}", async () => {
    health = { world: "off", idkit: false, agentpass: false };
    assert.deepEqual((await call("GET", "/health")).json, { world: "off", idkit: false, agentpass: false });
    health = { world: "ok", idkit: true, agentpass: true };
    assert.deepEqual((await call("GET", "/health")).json, { world: "ok", idkit: true, agentpass: true });
  });
});

describe("IDKit routes", () => {
  it("POST /idkit/start then GET /idkit/{id} to done", async () => {
    const s = await call("POST", "/idkit/start", { console: "anypercent" });
    assert.equal(s.status, 200);
    assert.deepEqual(Object.keys(s.json).sort(), ["code", "expires_s", "id", "qr"]);
    assert.equal(typeof s.json.expires_s, "number");
    const first = (await call("GET", `/idkit/${s.json.id}`)).json;
    assert.deepEqual(Object.keys(first).sort(), ["data", "failure", "ok", "stage"]);
    const done = await until(`/idkit/${s.json.id}`, "done");
    assert.equal(done.ok, true);
    assert.equal(done.failure, null);
    assert.deepEqual(Object.keys(done.data).sort(), ["book", "credential", "runner_id"]);
  });

  it("POST /idkit/{id}/cancel answers {ok: true}, idempotently; GET then says done / id_rejected", async () => {
    const s = await call("POST", "/idkit/start", { console: "anypercent" });
    assert.deepEqual(await call("POST", `/idkit/${s.json.id}/cancel`), { status: 200, json: { ok: true } });
    assert.deepEqual((await call("POST", `/idkit/${s.json.id}/cancel`)).json, { ok: true });
    await new Promise((r) => setTimeout(r, 30));
    assert.deepEqual((await call("GET", `/idkit/${s.json.id}`)).json, {
      stage: "done",
      ok: false,
      failure: "id_rejected",
      data: {},
    });
    assert.equal((await call("POST", "/idkit/nope/cancel")).status, 404);
  });

  it("400 on a missing console, 404 on an unknown id", async () => {
    assert.equal((await call("POST", "/idkit/start", {})).status, 400);
    assert.equal((await call("POST", "/idkit/start", undefined, "not json")).status, 400);
    const unknown = await call("GET", "/idkit/nope");
    assert.equal(unknown.status, 404);
    assert.equal(unknown.json.failure, "id_offline");
  });
});

describe("Agent Pass routes", () => {
  it("POST /agentpass/start then GET to done with {jti}", async () => {
    pollScript = [{ kind: "tokens", idToken: await idToken(keys.privateKey, { jti: "route-jti" }) }];
    const s = await call("POST", "/agentpass/start", { book: "ANY-RTE", action: "list SHIP 1:23.45 ghost" });
    assert.equal(s.status, 200);
    assert.deepEqual(Object.keys(s.json).sort(), ["code", "expires_s", "id", "qr"]);
    assert.equal(s.json.code, "WDJB-MJHT");
    const done = await until(`/agentpass/${s.json.id}`, "done");
    assert.deepEqual(done, { stage: "done", ok: true, failure: null, data: { jti: "route-jti" } });
  });

  it("POST /agentpass/{id}/cancel answers {ok: true}, idempotently; GET then says done / ls_denied", async () => {
    pollScript = [
      { kind: "error", error: "authorization_pending", status: 400 },
      { kind: "tokens", idToken: await idToken(keys.privateKey, { jti: "late-route-jti" }) },
    ];
    const s = await call("POST", "/agentpass/start", { book: "ANY-CNL", action: "list MDGP 1:42.83 ghost at 0.10 USDC" });
    const c = await call("POST", `/agentpass/${s.json.id}/cancel`);
    assert.deepEqual(c, { status: 200, json: { ok: true } });
    assert.deepEqual((await call("POST", `/agentpass/${s.json.id}/cancel`)).json, { ok: true });
    const cancelled = { stage: "done", ok: false, failure: "ls_denied", data: {} };
    assert.deepEqual((await call("GET", `/agentpass/${s.json.id}`)).json, cancelled);
    await new Promise((r) => setTimeout(r, 30)); // the phone approves meanwhile
    assert.deepEqual((await call("GET", `/agentpass/${s.json.id}`)).json, cancelled);
  });

  it("400 on a malformed book or action, 404 on unknown ids", async () => {
    assert.equal((await call("POST", "/agentpass/start", { book: "nope", action: "x" })).status, 400);
    assert.equal((await call("POST", "/agentpass/start", { book: "ANY-ABC" })).status, 400);
    assert.equal((await call("POST", "/agentpass/start", { book: "ANY-ABC", action: "a\nb" })).status, 400);
    assert.equal((await call("GET", "/agentpass/nope")).status, 404);
    assert.equal((await call("POST", "/agentpass/nope/cancel")).status, 404);
    assert.equal((await call("GET", "/elsewhere")).status, 404);
  });
});

describe("503 when a service is not configured", () => {
  it("answers the step's down failure", async () => {
    const bare = buildServer({ health: () => health, idkit: null, agentpass: null });
    await new Promise<void>((r) => bare.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${(bare.address() as AddressInfo).port}`;
    const a = await fetch(`${url}/idkit/start`, { method: "POST", body: JSON.stringify({ console: "pi" }) });
    assert.equal(a.status, 503);
    assert.deepEqual(await a.json(), { error: "idkit_not_configured", failure: "id_offline" });
    const b = await fetch(`${url}/agentpass/start`, { method: "POST", body: JSON.stringify({ book: "ANY-ABC", action: "x" }) });
    assert.equal(b.status, 503);
    assert.deepEqual(await b.json(), { error: "agentpass_not_configured", failure: "ls_world_down" });
    bare.close();
  });
});

describe("logs", () => {
  it("never carry links, codes, ids, device codes or tokens", () => {
    const all = logLines.join("\n");
    assert.ok(all.length > 0);
    for (const bad of ["key-material", "verify?t=", "WDJB-MJHT", "never-out", "eyJ", "pairwise-subject"]) {
      assert.ok(!all.includes(bad), `log leaked ${bad.slice(0, 4)}...`);
    }
  });
});

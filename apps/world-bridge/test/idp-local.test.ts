/**
 * End to end over real HTTP with no World account: a local fake World IdP (discovery, RFC 8628
 * device authorization, token endpoint, JWKS) behind the real WorldIdp (oauth4webapi) and the real
 * bridge server. This checks the wire format the unit tests cannot: client_secret_basic, form
 * bodies, OAuth error bodies, and that the bridge never hands out the device_code or a token.
 */
import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { AgentPass } from "../src/agentpass.js";
import { WorldIdp } from "../src/oidc.js";
import { buildServer } from "../src/server.js";
import { Store } from "../src/store.js";
import { idToken, makeKeys, ORB, SECRET, tempDir, type TestKeys } from "./helpers.js";

const CLIENT = "client_local_1";
const CLIENT_SECRET = "worldidp_client_secret_local test/+&=";
const DEVICE_CODE = "local-device-code-secret";

type Answer = { status: number; body: Record<string, unknown> } | "approve";

let keys: TestKeys;
let idp: Server;
let issuer = "";
let script: Answer[] = [];
let tokenSub = "subject-owner";
let tokenJti = "jti-local-1";
const seen = { deviceAuthBasic: [] as string[], tokenForms: [] as string[] };

let bridge: Server;
let bridgeUrl = "";
let agentpass: AgentPass;

function basicOk(header: string | undefined): boolean {
  if (!header?.startsWith("Basic ")) return false;
  const [id, secret] = Buffer.from(header.slice(6), "base64").toString().split(":");
  // RFC 6749 2.3.1: both parts are form-urlencoded before base64.
  const dec = (s: string) => decodeURIComponent(s.replace(/\+/g, " "));
  return dec(id) === CLIENT && dec(secret) === CLIENT_SECRET;
}

async function body(req: import("node:http").IncomingMessage): Promise<string> {
  let s = "";
  for await (const c of req) s += c;
  return s;
}

before(async () => {
  keys = await makeKeys();
  idp = createServer(async (req, res) => {
    const json = (status: number, b: unknown) => {
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(b));
    };
    const path = req.url ?? "/";
    if (req.method === "GET" && path === "/.well-known/openid-configuration") {
      return json(200, {
        issuer,
        device_authorization_endpoint: `${issuer}/api/v1/device_authorization`,
        token_endpoint: `${issuer}/api/v1/token`,
        jwks_uri: `${issuer}/.well-known/jwks.json`,
        grant_types_supported: ["authorization_code", "urn:ietf:params:oauth:grant-type:device_code"],
        acr_values_supported: [ORB],
        id_token_signing_alg_values_supported: ["RS256"],
        token_endpoint_auth_methods_supported: ["client_secret_basic"],
      });
    }
    if (req.method === "GET" && path === "/.well-known/jwks.json") return json(200, keys.jwks);
    if (req.method === "POST" && path === "/api/v1/device_authorization") {
      const form = new URLSearchParams(await body(req));
      seen.deviceAuthBasic.push(String(basicOk(req.headers.authorization)));
      if (!basicOk(req.headers.authorization)) return json(401, { error: "invalid_client" });
      if (form.get("scope") !== "openid") return json(400, { error: "invalid_scope" });
      return json(200, {
        device_code: DEVICE_CODE,
        user_code: "WDJB-MJHT",
        verification_uri: `${issuer}/device`,
        verification_uri_complete: `${issuer}/device?user_code=WDJB-MJHT`,
        expires_in: 1200,
        interval: 1,
      });
    }
    if (req.method === "POST" && path === "/api/v1/token") {
      const form = await body(req);
      seen.tokenForms.push(form);
      const f = new URLSearchParams(form);
      if (!basicOk(req.headers.authorization)) return json(401, { error: "invalid_client" });
      if (f.get("grant_type") !== "urn:ietf:params:oauth:grant-type:device_code" || f.get("device_code") !== DEVICE_CODE) {
        return json(400, { error: "invalid_grant" });
      }
      const next = script.shift() ?? { status: 400, body: { error: "authorization_pending" } };
      if (next === "approve") {
        const t = await idToken(keys.privateKey, { iss: issuer, aud: CLIENT, sub: tokenSub, jti: tokenJti });
        return json(200, { id_token: t, access_token: "opaque-access", token_type: "Bearer", expires_in: 300 });
      }
      return json(next.status, next.body);
    }
    json(404, { error: "not_found" });
  });
  await new Promise<void>((r) => idp.listen(0, "127.0.0.1", r));
  issuer = `http://127.0.0.1:${(idp.address() as AddressInfo).port}`;

  const world = new WorldIdp({ issuer, clientId: CLIENT, clientSecret: CLIENT_SECRET, allowInsecure: true });
  agentpass = new AgentPass({
    idp: world,
    store: new Store(tempDir(), SECRET),
    secret: SECRET,
    clientId: CLIENT,
    msPerSecond: 5, // World's 1 s interval = 5 ms here
  });
  bridge = buildServer({ health: () => ({ world: "ok", idkit: false, agentpass: true }), idkit: null, agentpass });
  await new Promise<void>((r) => bridge.listen(0, "127.0.0.1", r));
  bridgeUrl = `http://127.0.0.1:${(bridge.address() as AddressInfo).port}`;
});

after(() => {
  agentpass.stopAll();
  bridge.close();
  idp.close();
});

const bodies: string[] = [];
async function call(method: string, path: string, payload?: unknown) {
  const res = await fetch(`${bridgeUrl}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const text = await res.text();
  bodies.push(text);
  return { status: res.status, json: JSON.parse(text) as Record<string, any> };
}

async function run(book: string, answers: Answer[], cancelAfterStart = false) {
  script = answers;
  const start = await call("POST", "/agentpass/start", { book, action: "list SHIP 1:23.45 ghost" });
  assert.equal(start.status, 200);
  if (cancelAfterStart) assert.equal((await call("POST", `/agentpass/${start.json.id}/cancel`)).status, 200);
  let view: Record<string, any> = {};
  for (let i = 0; i < 400; i++) {
    view = (await call("GET", `/agentpass/${start.json.id}`)).json;
    if (view.stage === "done") break;
    await new Promise((r) => setTimeout(r, 5));
  }
  return { start: start.json, view };
}

describe("Agent Pass over HTTP against a local World IdP", () => {
  it("start: World's link and user code, client_secret_basic form-encoded", async () => {
    const { start, view } = await run("ANY-LOC", ["approve"]);
    assert.equal(start.qr, `${issuer}/device?user_code=WDJB-MJHT`);
    assert.equal(start.code, "WDJB-MJHT");
    assert.equal(start.expires_s, 1200);
    assert.ok(seen.deviceAuthBasic.every((v) => v === "true"));
    assert.deepEqual(view, { stage: "done", ok: true, failure: null, data: { jti: "jti-local-1" } });
  });

  it("polls with the device-code grant and survives authorization_pending", async () => {
    tokenJti = "jti-local-2";
    const before = seen.tokenForms.length;
    const { view } = await run("ANY-LOC", [
      { status: 400, body: { error: "authorization_pending" } },
      { status: 400, body: { error: "authorization_pending" } },
      "approve",
    ]);
    assert.equal(view.ok, true);
    assert.equal(seen.tokenForms.length - before, 3);
  });

  it("access_denied from World: ls_denied", async () => {
    const { view } = await run("ANY-LOC", [{ status: 400, body: { error: "access_denied" } }]);
    assert.deepEqual(view, { stage: "done", ok: false, failure: "ls_denied", data: {} });
  });

  it("HTTP 503 from World ends the attempt: ls_world_down", async () => {
    const { view } = await run("ANY-LOC", [{ status: 503, body: { error: "temporarily_unavailable" } }]);
    assert.equal(view.failure, "ls_world_down");
  });

  it("another account for the bound book: ls_wrong", async () => {
    tokenSub = "subject-intruder";
    tokenJti = "jti-local-3";
    const { view } = await run("ANY-LOC", ["approve"]);
    assert.equal(view.failure, "ls_wrong");
    tokenSub = "subject-owner";
  });

  it("Circle then approve on the phone: the console's answer stays ls_denied and the late jti is burned", async () => {
    tokenJti = "jti-local-4";
    const { view } = await run("ANY-NEW", [{ status: 400, body: { error: "authorization_pending" } }, "approve"], true);
    assert.deepEqual(view, { stage: "done", ok: false, failure: "ls_denied", data: {} });
    for (let i = 0; i < 400 && script.length > 0; i++) await new Promise((r) => setTimeout(r, 5));
    assert.equal(script.length, 0, "the bridge kept listening and redeemed the late approval");
    await new Promise((r) => setTimeout(r, 20));
    const replay = await run("ANY-NEW", ["approve"]);
    assert.equal(replay.view.failure, "ls_reused", "that approval can never be used");
  });

  it("never returns the device code or a token in any response", () => {
    const all = bodies.join("\n");
    assert.ok(!all.includes(DEVICE_CODE));
    assert.ok(!all.includes("opaque-access"));
    assert.ok(!all.includes("eyJ"), "no JWT");
    assert.ok(!all.includes("subject-owner") && !all.includes("subject-intruder"), "no sub");
  });

  it("a wrong client secret: the bridge answers 503 with ls_world_down at start", async () => {
    const bad = new AgentPass({
      idp: new WorldIdp({ issuer, clientId: CLIENT, clientSecret: "wrong", allowInsecure: true }),
      store: new Store(tempDir(), SECRET),
      secret: SECRET,
      clientId: CLIENT,
    });
    const srv = buildServer({ health: () => ({ world: "ok", idkit: false, agentpass: true }), idkit: null, agentpass: bad });
    await new Promise<void>((r) => srv.listen(0, "127.0.0.1", r));
    const res = await fetch(`http://127.0.0.1:${(srv.address() as AddressInfo).port}/agentpass/start`, {
      method: "POST",
      body: JSON.stringify({ book: "ANY-LOC", action: "x" }),
    });
    assert.equal(res.status, 503);
    assert.deepEqual(await res.json(), { error: "world_unavailable", failure: "ls_world_down" });
    srv.close();
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { chooseApprovals, loadConfig } from "../src/config.js";

const IDKIT = {
  WORLD_APP_ID: "app_0123456789abcdef",
  WORLD_RP_ID: "rp_0123456789abcdef",
  WORLD_SIGNING_KEY: "ab".repeat(32),
  WORLD_ENVIRONMENT: "production",
};
const AGENTPASS = {
  AGENTPASS_ISSUER: "https://auth.world.org",
  AGENTPASS_CLIENT_ID: "client",
  AGENTPASS_CLIENT_SECRET: "secret",
};
const SECRET = { SERVER_SECRET: "s".repeat(40) };

const pick = (env: Record<string, string>) => chooseApprovals(loadConfig(env, "."));

describe("APPROVALS: which provider runs the listing approvals", () => {
  it("default: idkit when Agent Pass is not configured and IDKit is", () => {
    assert.deepEqual(pick({ ...IDKIT, ...SECRET }), { kind: "idkit", available: true });
  });

  it("default: agentpass when it is configured, even with IDKit configured too", () => {
    assert.deepEqual(pick({ ...IDKIT, ...AGENTPASS, ...SECRET }), { kind: "agentpass", available: true });
    assert.deepEqual(pick({ ...AGENTPASS, ...SECRET }), { kind: "agentpass", available: true });
  });

  it("default with neither configured: agentpass, not available", () => {
    assert.deepEqual(pick({ ...SECRET }), { kind: "agentpass", available: false });
    assert.deepEqual(pick({}), { kind: "agentpass", available: false });
  });

  it("APPROVALS=idkit wins over a configured Agent Pass", () => {
    assert.deepEqual(pick({ APPROVALS: "idkit", ...IDKIT, ...AGENTPASS, ...SECRET }), { kind: "idkit", available: true });
  });

  it("APPROVALS=agentpass keeps Agent Pass even when only IDKit is configured (then unavailable)", () => {
    assert.deepEqual(pick({ APPROVALS: "agentpass", ...IDKIT, ...SECRET }), { kind: "agentpass", available: false });
  });

  it("APPROVALS=idkit without IDKit configured: not available", () => {
    assert.deepEqual(pick({ APPROVALS: "idkit", ...AGENTPASS, ...SECRET }), { kind: "idkit", available: false });
  });

  it("is case-insensitive; an unknown value falls back to the default rule", () => {
    assert.deepEqual(pick({ APPROVALS: " IDKit ", ...IDKIT, ...AGENTPASS, ...SECRET }), { kind: "idkit", available: true });
    assert.deepEqual(pick({ APPROVALS: "both", ...IDKIT, ...SECRET }), { kind: "idkit", available: true });
  });
});

describe("World settings", () => {
  it("WORLD_ACTION defaults to the fresh action anypercent-book", () => {
    assert.equal(loadConfig({}, ".").world.action, "anypercent-book");
    assert.equal(loadConfig({ WORLD_ACTION: "other" }, ".").world.action, "other");
  });

  it("WORLD_SIGNUP_SESSION: combined unless set to separate", () => {
    assert.equal(loadConfig({}, ".").world.signupSession, "combined");
    assert.equal(loadConfig({ WORLD_SIGNUP_SESSION: "Separate" }, ".").world.signupSession, "separate");
    assert.equal(loadConfig({ WORLD_SIGNUP_SESSION: "bogus" }, ".").world.signupSession, "combined");
  });
});

describe("EXTRA_HOSTS: more addresses the bridge also listens on", () => {
  it("none by default", () => {
    assert.deepEqual(loadConfig({}, ".").extraHosts, []);
  });

  it("a comma list, trimmed, without blanks, repeats or HOST itself", () => {
    const cfg = loadConfig({ HOST: "172.18.96.1", EXTRA_HOSTS: " 100.71.192.6, ,172.18.96.1,100.71.192.6 " }, ".");
    assert.deepEqual(cfg.extraHosts, ["100.71.192.6"]);
  });
});

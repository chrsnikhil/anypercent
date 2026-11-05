import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { IDKitErrorCodes } from "@worldcoin/idkit-core";
import {
  devicePollStep,
  ID_FAILURES,
  idkitAppFailure,
  isReplay,
  LS_FAILURES,
  portalFailure,
  proofCheckFailure,
  tokenFailure,
  type TokenReason,
} from "../src/failures.js";

const ID = new Set<string>(ID_FAILURES);
const LS = new Set<string>(LS_FAILURES);

describe("IDKit World App / bridge errors -> handler failure names", () => {
  const expected: Record<string, string> = {
    user_rejected: "id_rejected",
    verification_rejected: "id_rejected",
    cancelled: "id_rejected",
    user_presence_failed: "id_rejected",
    credential_unavailable: "id_nocred",
    world_id_4_not_available: "id_nocred",
    world_id_3_not_available: "id_nocred",
    feature_unavailable: "id_nocred",
    identity_attributes_not_matched: "id_nocred",
    max_verifications_reached: "id_dup",
    nullifier_replayed: "id_dup",
    timeout: "id_expired",
    rp_signature_expired: "id_expired",
    invalid_rp_signature: "id_offline",
    duplicate_nonce: "id_offline",
    unknown_rp: "id_offline",
    inactive_rp: "id_offline",
    invalid_rp_id_format: "id_offline",
    timestamp_too_old: "id_offline",
    timestamp_too_far_in_future: "id_offline",
    invalid_timestamp: "id_offline",
    malformed_request: "id_offline",
    invalid_network: "id_offline",
    inclusion_proof_pending: "id_offline",
    inclusion_proof_failed: "id_offline",
    connection_failed: "id_offline",
    unexpected_response: "id_offline",
    generic_error: "id_offline",
    failed_by_host_app: "id_offline",
  };

  it("covers every code the pinned SDK can return, explicitly", () => {
    const sdkCodes = Object.values(IDKitErrorCodes) as string[];
    const missing = sdkCodes.filter((c) => !(c in expected));
    assert.deepEqual(missing, [], "a new SDK error code needs a deliberate mapping");
  });

  for (const [code, failure] of Object.entries(expected)) {
    it(`${code} -> ${failure}`, () => assert.equal(idkitAppFailure(code), failure));
  }

  it("unknown or missing codes mean World is not answering", () => {
    assert.equal(idkitAppFailure("something_new"), "id_offline");
    assert.equal(idkitAppFailure(undefined), "id_offline");
  });
});

describe("Developer Portal /api/v4/verify errors", () => {
  it("404, 429 and 5xx: id_offline", () => {
    for (const s of [404, 429, 500, 502, 503]) assert.equal(portalFailure(s, undefined), "id_offline");
  });
  it("a repeat verification at the top level or per result: id_dup", () => {
    assert.equal(portalFailure(400, { code: "max_verifications_reached" }), "id_dup");
    assert.equal(
      portalFailure(400, { code: "all_verifications_failed", results: [{ code: "nullifier_replayed" }] }),
      "id_dup",
    );
    assert.equal(isReplay({ code: "x", results: [{ code: "already_verified" }] }), true);
    assert.equal(isReplay(undefined), false);
  });
  it("our app's setup: id_offline", () => {
    assert.equal(portalFailure(400, { code: "app_not_migrated" }), "id_offline");
  });
  it("a refused proof: id_rejected", () => {
    assert.equal(
      portalFailure(400, { code: "all_verifications_failed", results: [{ code: "verification_error" }] }),
      "id_rejected",
    );
    assert.equal(portalFailure(400, undefined), "id_rejected");
  });
  it("our own proof checks", () => {
    assert.equal(proofCheckFailure("environment"), "id_rejected");
    assert.equal(proofCheckFailure("action"), "id_rejected");
    assert.equal(proofCheckFailure("signal"), "id_rejected");
    assert.equal(proofCheckFailure("no_nullifier"), "id_rejected");
    assert.equal(proofCheckFailure("credential"), "id_nocred");
  });
});

describe("Agent Pass device-grant poll responses", () => {
  it("authorization_pending keeps polling at the same interval", () => {
    assert.deepEqual(devicePollStep("authorization_pending", 400), { kind: "continue", slowDown: false });
  });
  it("slow_down keeps polling, 5 s slower", () => {
    assert.deepEqual(devicePollStep("slow_down", 400), { kind: "continue", slowDown: true });
  });
  const stops: Array<[string | undefined, number, string]> = [
    ["access_denied", 400, "ls_denied"],
    ["unmet_authentication_requirements", 400, "ls_denied"],
    ["expired_token", 400, "ls_expired"],
    ["invalid_grant", 400, "ls_expired"],
    ["invalid_client", 401, "ls_world_down"],
    ["invalid_client", 400, "ls_world_down"],
    ["invalid_request", 400, "ls_world_down"],
    ["unauthorized_client", 400, "ls_world_down"],
    ["unsupported_grant_type", 400, "ls_world_down"],
    ["invalid_scope", 400, "ls_world_down"],
    ["server_error", 500, "ls_world_down"],
    [undefined, 502, "ls_world_down"],
    // 503 and 429 end the attempt whatever the body says: "never approval".
    ["authorization_pending", 503, "ls_world_down"],
    ["slow_down", 429, "ls_world_down"],
  ];
  for (const [error, status, failure] of stops) {
    it(`${error ?? "(no error)"} / HTTP ${status} -> ${failure}`, () => {
      assert.deepEqual(devicePollStep(error, status), { kind: "fail", failure });
    });
  }
});

describe("ID-token refusals", () => {
  const expected: Record<TokenReason, string> = {
    signature: "ls_mismatch",
    issuer: "ls_mismatch",
    audience: "ls_mismatch",
    iat: "ls_mismatch",
    claims: "ls_mismatch",
    auth_time: "ls_mismatch",
    expired: "ls_expired",
    acr: "ls_wrong",
    jwks_unavailable: "ls_world_down",
  };
  for (const [reason, failure] of Object.entries(expected)) {
    it(`${reason} -> ${failure}`, () => assert.equal(tokenFailure(reason as TokenReason), failure));
  }
});

describe("only the handler's own names ever come out", () => {
  it("IDKit side", () => {
    for (const c of [...(Object.values(IDKitErrorCodes) as string[]), "zzz"]) assert.ok(ID.has(idkitAppFailure(c)));
    for (const s of [200, 400, 404, 500]) assert.ok(ID.has(portalFailure(s, { code: "zzz" })));
  });
  it("Agent Pass side", () => {
    for (const e of ["access_denied", "expired_token", "zzz", undefined]) {
      const step = devicePollStep(e, 400);
      if (step.kind === "fail") assert.ok(LS.has(step.failure));
    }
  });
});

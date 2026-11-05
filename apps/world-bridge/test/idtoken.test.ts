import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { SignJWT } from "jose";
import { DOCUMENTED_ACR, validateIdToken, type TokenPolicy } from "../src/idtoken.js";
import { CLIENT_ID, idToken, ISS, makeKeys, nowS, ORB, type TestKeys } from "./helpers.js";

let keys: TestKeys;
before(async () => {
  keys = await makeKeys();
});

const policy = (over: Partial<TokenPolicy> = {}): TokenPolicy => ({
  issuer: ISS,
  clientId: CLIENT_ID,
  acceptedAcr: new Set(DOCUMENTED_ACR),
  startedAt: nowS() - 5,
  now: nowS(),
  skew: 30,
  ...over,
});

async function reason(token: string, over: Partial<TokenPolicy> = {}): Promise<string> {
  const r = await validateIdToken(token, keys.getKey, policy(over));
  return r.ok ? "ok" : r.reason;
}

describe("ID token validation against a local test JWKS", () => {
  it("accepts a good World device-grant token (no nonce)", async () => {
    const r = await validateIdToken(await idToken(keys.privateKey), keys.getKey, policy());
    assert.equal(r.ok, true);
    if (r.ok) {
      assert.equal(r.claims.acr, ORB);
      assert.equal(typeof r.claims.jti, "string");
    }
  });

  it("refuses a token signed by a key outside the JWKS", async () => {
    assert.equal(await reason(await idToken(keys.rogue)), "signature");
  });

  it("refuses a token whose kid is not in the JWKS", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, {}, "unknown-kid")), "signature");
  });

  it("refuses HS256 (alg confusion)", async () => {
    const t = nowS();
    const hs = await new SignJWT({ iss: ISS, sub: "s", aud: CLIENT_ID, exp: t + 60, iat: t, jti: "j", auth_time: t, acr: ORB })
      .setProtectedHeader({ alg: "HS256", kid: "k1" })
      .sign(new TextEncoder().encode("0123456789abcdef0123456789abcdef"));
    assert.equal(await reason(hs), "signature");
  });

  it("refuses the wrong issuer, even one differing only by a trailing slash", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { iss: "https://evil.example" })), "issuer");
    assert.equal(await reason(await idToken(keys.privateKey, { iss: `${ISS}/` })), "issuer");
  });

  it("refuses the wrong audience", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { aud: "someone-else" })), "audience");
  });

  it("refuses an expired token (past the skew)", async () => {
    const t = nowS();
    assert.equal(
      await reason(await idToken(keys.privateKey, { exp: t - 120, iat: t - 400, auth_time: t - 2 }), {
        startedAt: t - 10,
      }),
      "expired",
    );
  });

  it("refuses an iat in the future", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { iat: nowS() + 600 })), "iat");
  });

  it("refuses a stale auth_time: authentication from before this attempt started", async () => {
    const t = nowS();
    assert.equal(
      await reason(await idToken(keys.privateKey, { auth_time: t - 600 }), { startedAt: t - 10 }),
      "auth_time",
    );
  });

  it("allows auth_time just inside the clock skew, refuses one just outside", async () => {
    const t = nowS();
    assert.equal(await reason(await idToken(keys.privateKey, { auth_time: t - 35 }), { startedAt: t - 10 }), "ok");
    assert.equal(
      await reason(await idToken(keys.privateKey, { auth_time: t - 45 }), { startedAt: t - 10 }),
      "auth_time",
    );
  });

  it("refuses an auth_time in the future", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { auth_time: nowS() + 600 })), "auth_time");
  });

  it("refuses an acr outside the accepted set, or none (an unverified account)", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { acr: "https://world.org/oidc/acr/none" })), "acr");
    assert.equal(await reason(await idToken(keys.privateKey, { acr: undefined })), "acr");
    assert.equal(
      await reason(await idToken(keys.privateKey), { acceptedAcr: new Set(["https://world.org/oidc/acr/orb-face"]) }),
      "acr",
    );
  });

  it("accepts the Selfie Check class World documents", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { acr: "https://world.org/oidc/acr/selfie" })), "ok");
  });

  it("requires jti, sub and auth_time", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { jti: undefined })), "claims");
    assert.equal(await reason(await idToken(keys.privateKey, { sub: undefined })), "claims");
    assert.equal(await reason(await idToken(keys.privateKey, { auth_time: undefined })), "claims");
  });

  it("refuses a malformed amr", async () => {
    assert.equal(await reason(await idToken(keys.privateKey, { amr: "pop" })), "claims");
  });

  it("reports an unreachable key set as such, not as a bad token", async () => {
    const down = async () => {
      throw new TypeError("fetch failed");
    };
    const r = await validateIdToken(await idToken(keys.privateKey), down, policy());
    assert.deepEqual(r, { ok: false, reason: "jwks_unavailable" });
  });
});

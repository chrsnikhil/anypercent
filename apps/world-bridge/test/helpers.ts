/** Shared test fixtures. Nothing here prints a token, sub, nullifier or secret. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT, type JWK, type JWTVerifyGetKey } from "jose";

type Key = Awaited<ReturnType<typeof generateKeyPair>>["privateKey"];

export const ISS = "https://auth.test.example";
export const CLIENT_ID = "client_test_123";
export const ORB = "https://world.org/oidc/acr/orb";
export const SECRET = "test-server-secret-0123456789abcdef-xyz";

const tempDirs: string[] = [];
process.on("exit", () => {
  for (const d of tempDirs) rmSync(d, { recursive: true, force: true });
});

export function tempDir(): string {
  const d = mkdtempSync(join(tmpdir(), "world-bridge-test-"));
  tempDirs.push(d);
  return d;
}

export interface TestKeys {
  privateKey: Key;
  jwks: { keys: JWK[] };
  getKey: JWTVerifyGetKey;
  /** A second key pair that is NOT in the JWKS. */
  rogue: Key;
}

export async function makeKeys(): Promise<TestKeys> {
  const { privateKey, publicKey } = await generateKeyPair("RS256", { extractable: true });
  const rogue = (await generateKeyPair("RS256")).privateKey;
  const jwk = { ...(await exportJWK(publicKey)), kid: "k1", alg: "RS256", use: "sig" };
  const jwks = { keys: [jwk] };
  return { privateKey, jwks, getKey: createLocalJWKSet(jwks), rogue };
}

export const nowS = (): number => Math.floor(Date.now() / 1000);

/** A World-shaped device-grant ID token (no nonce), with overrides. */
export async function idToken(
  key: Key,
  over: Record<string, unknown> = {},
  kid = "k1",
): Promise<string> {
  const t = nowS();
  const claims: Record<string, unknown> = {
    iss: ISS,
    sub: "pairwise-subject-A",
    aud: CLIENT_ID,
    exp: t + 300,
    iat: t,
    jti: `jti-${Math.random().toString(36).slice(2)}`,
    auth_time: t,
    acr: ORB,
    amr: ["pop"],
    ...over,
  };
  for (const k of Object.keys(claims)) if (claims[k] === undefined) delete claims[k];
  return new SignJWT(claims).setProtectedHeader({ alg: "RS256", kid, typ: "JWT" }).sign(key);
}

export async function waitFor(pred: () => boolean, timeoutMs = 3000, stepMs = 2): Promise<void> {
  const end = Date.now() + timeoutMs;
  while (!pred()) {
    if (Date.now() > end) throw new Error("timed out waiting for condition");
    await new Promise((r) => setTimeout(r, stepMs));
  }
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * ID-token validation for the Agent Pass device grant, per World's OIDC guide and step-up guide:
 * RS256 signature from the discovered JWKS, `iss` exactly as discovered, `aud` = our client id,
 * `exp`, `iat`, `auth_time` inside this attempt, `acr` in the accepted set. Device tokens carry no
 * nonce. The jti and sub checks need the store, so agentpass.ts does them after this.
 */
import { jwtVerify, type JWTPayload, type JWTVerifyGetKey } from "jose";
import type { TokenReason } from "./failures.js";

/** World's documented classes (id-token guide). Production discovery lists only the
 *  Orb two, but Selfie Check accounts receive the selfie ones when the client accepts them. */
export const DOCUMENTED_ACR = [
  "https://world.org/oidc/acr/orb",
  "https://world.org/oidc/acr/orb-face",
  "https://world.org/oidc/acr/selfie",
  "https://world.org/oidc/acr/selfie-face",
];

export interface TokenPolicy {
  issuer: string;
  clientId: string;
  acceptedAcr: ReadonlySet<string>;
  /** Unix seconds when this device authorization was started. */
  startedAt: number;
  /** Unix seconds, now. */
  now: number;
  /** Allowed clock difference with World, seconds. */
  skew: number;
}

export interface WorldClaims extends JWTPayload {
  iss: string;
  sub: string;
  jti: string;
  auth_time: number;
  acr: string;
  amr?: string[];
}

export type TokenCheck = { ok: true; claims: WorldClaims } | { ok: false; reason: TokenReason };

function joseReason(err: unknown): TokenReason {
  const code = (err as { code?: string }).code;
  const claim = (err as { claim?: string }).claim;
  switch (code) {
    case "ERR_JWT_EXPIRED":
      return "expired";
    case "ERR_JWT_CLAIM_VALIDATION_FAILED":
      if (claim === "iss") return "issuer";
      if (claim === "aud") return "audience";
      if (claim === "iat" || claim === "nbf") return "iat";
      return "claims";
    case "ERR_JWS_SIGNATURE_VERIFICATION_FAILED":
    case "ERR_JWKS_NO_MATCHING_KEY":
    case "ERR_JWKS_MULTIPLE_MATCHING_KEYS":
    case "ERR_JOSE_ALG_NOT_ALLOWED":
    case "ERR_JOSE_NOT_SUPPORTED":
    case "ERR_JWS_INVALID":
    case "ERR_JWT_INVALID":
      return "signature";
    case "ERR_JWKS_TIMEOUT":
    case "ERR_JWKS_INVALID":
      return "jwks_unavailable";
    default:
      // Not a JOSE verdict on the token: the key set could not be fetched (network, abort).
      return code && code.startsWith("ERR_J") ? "signature" : "jwks_unavailable";
  }
}

export async function validateIdToken(
  token: string,
  getKey: JWTVerifyGetKey,
  policy: TokenPolicy,
): Promise<TokenCheck> {
  let payload: JWTPayload;
  try {
    ({ payload } = await jwtVerify(token, getKey, {
      issuer: policy.issuer,
      audience: policy.clientId,
      algorithms: ["RS256"],
      clockTolerance: policy.skew,
      currentDate: new Date(policy.now * 1000),
      requiredClaims: ["iss", "sub", "aud", "exp", "iat", "jti", "auth_time"],
    }));
  } catch (err) {
    return { ok: false, reason: joseReason(err) };
  }

  if (typeof payload.iat !== "number" || payload.iat > policy.now + policy.skew) {
    return { ok: false, reason: "iat" };
  }
  if (typeof payload.sub !== "string" || payload.sub === "") return { ok: false, reason: "claims" };
  if (typeof payload.jti !== "string" || payload.jti === "") return { ok: false, reason: "claims" };

  // The authentication must belong to THIS attempt: at or after its start, and not in the future.
  const authTime = payload.auth_time;
  if (
    typeof authTime !== "number" ||
    authTime < policy.startedAt - policy.skew ||
    authTime > policy.now + policy.skew
  ) {
    return { ok: false, reason: "auth_time" };
  }

  // `acr` is the achieved class; it must be one we accept (missing: an unverified account).
  if (typeof payload.acr !== "string" || !policy.acceptedAcr.has(payload.acr)) {
    return { ok: false, reason: "acr" };
  }

  if (payload.amr !== undefined && !(Array.isArray(payload.amr) && payload.amr.every((m) => typeof m === "string"))) {
    return { ok: false, reason: "claims" };
  }

  return { ok: true, claims: payload as WorldClaims };
}

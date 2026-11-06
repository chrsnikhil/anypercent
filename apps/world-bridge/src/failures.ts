/**
 * Every World error ends on one of the handler's own failure names (launcher handler/mock.py
 * `_OUTCOMES` and `_DOWN_FAILURE`). No new names, no new screens: an error World may send that the
 * handler has no screen for lands on the closest existing one, and the choice is written next to it.
 */

/**
 * `id_taken` (one console, one person): the console is bound to another record book, so the sign-up
 * was refused before the portal saw the proof. A launcher from before consoles never gets it: only
 * a console that sends a console id can be bound.
 */
export const ID_FAILURES = ["id_rejected", "id_expired", "id_nocred", "id_dup", "id_offline", "id_taken"] as const;
export const LS_FAILURES = [
  "ls_denied",
  "ls_expired",
  "ls_wrong",
  "ls_mismatch",
  "ls_reused",
  "ls_world_down",
] as const;

export type IdFailure = (typeof ID_FAILURES)[number];
export type LsFailure = (typeof LS_FAILURES)[number];

// ---- IDKit: World App / bridge error codes (IDKitErrorCodes in @worldcoin/idkit-core 4.6.0) ----

const IDKIT_APP_ERRORS: Record<string, IdFailure> = {
  // The person said no on the phone.
  user_rejected: "id_rejected",
  verification_rejected: "id_rejected", // older bridge's name for user_rejected
  cancelled: "id_rejected", // client-side abort: only the bridge's own cancel produces it
  user_presence_failed: "id_rejected", // liveness not completed (we never request it)
  // The phone holds no credential this request accepts.
  credential_unavailable: "id_nocred",
  world_id_4_not_available: "id_nocred",
  world_id_3_not_available: "id_nocred",
  feature_unavailable: "id_nocred", // the World App cannot satisfy the request
  identity_attributes_not_matched: "id_nocred", // we never request attributes
  // This World ID already verified this action: one per person.
  max_verifications_reached: "id_dup",
  nullifier_replayed: "id_dup",
  // Time ran out.
  timeout: "id_expired",
  rp_signature_expired: "id_expired", // the signed request outlived its 300 s TTL
  // Our registration, clock or World's plumbing: nothing the person can fix.
  invalid_rp_signature: "id_offline",
  duplicate_nonce: "id_offline",
  unknown_rp: "id_offline",
  inactive_rp: "id_offline",
  invalid_rp_id_format: "id_offline",
  timestamp_too_old: "id_offline",
  timestamp_too_far_in_future: "id_offline",
  invalid_timestamp: "id_offline",
  malformed_request: "id_offline",
  invalid_network: "id_offline", // staging/production mismatch between request and World App
  inclusion_proof_pending: "id_offline",
  inclusion_proof_failed: "id_offline",
  connection_failed: "id_offline",
  unexpected_response: "id_offline",
  generic_error: "id_offline",
  failed_by_host_app: "id_offline", // widget-only; never reaches a bridge poll
};

/** A World App / bridge error code from a failed IDKit poll. Unknown codes: World is not answering. */
export function idkitAppFailure(code: string | undefined): IdFailure {
  return (code && IDKIT_APP_ERRORS[code]) || "id_offline";
}

/** Codes the Developer Portal may use, at the top level or per result, for a repeat verification. */
const REPLAY_CODES = new Set([
  "max_verifications_reached",
  "nullifier_replayed",
  "already_verified",
  "duplicate_nullifier",
  "nullifier_already_used",
]);

/** Portal errors that mean our app/RP setup, not this proof, is at fault. */
const PORTAL_CONFIG_CODES = new Set([
  "app_not_migrated",
  "app_not_found",
  "not_registered",
  "unknown_rp",
  "inactive_rp",
  "invalid_rp_id_format",
  "invalid_app",
]);

export interface PortalError {
  code?: string;
  results?: Array<{ code?: string }>;
}

/** True when a portal error says this human already verified the action. */
export function isReplay(body: PortalError | undefined): boolean {
  if (!body) return false;
  if (body.code && REPLAY_CODES.has(body.code)) return true;
  return (body.results ?? []).some((r) => !!r.code && REPLAY_CODES.has(r.code));
}

/**
 * POST /api/v4/verify answered with an error. 404 and 5xx: the portal or our app is unavailable.
 * A repeat verification: id_dup. Any other refused proof (all_verifications_failed,
 * verification_error, ...): World rejected it, nothing saved -> id_rejected.
 */
export function portalFailure(status: number, body: PortalError | undefined): IdFailure {
  if (status === 404 || status >= 500 || status === 429) return "id_offline";
  if (isReplay(body)) return "id_dup";
  if (body?.code && PORTAL_CONFIG_CODES.has(body.code)) return "id_offline";
  return "id_rejected";
}

/** Our own checks on a proof the portal accepted (environment, action, signal, credential). */
export type ProofCheck = "environment" | "action" | "signal" | "session" | "credential" | "no_nullifier";

export function proofCheckFailure(check: ProofCheck): IdFailure {
  // A proof for another environment, action or request, or without an accepted credential, is a
  // proof World would not stand behind here: refused, nothing saved.
  return check === "credential" ? "id_nocred" : "id_rejected";
}

// ---- Listing approvals on IDKit (APPROVALS=idkit): the same World App request, ls_* names --------

const APPROVAL_APP_ERRORS: Record<string, LsFailure> = {
  // The person said no on the phone, or the request was aborted.
  user_rejected: "ls_denied",
  verification_rejected: "ls_denied",
  cancelled: "ls_denied",
  user_presence_failed: "ls_denied", // liveness not completed (we never request it)
  // Time ran out.
  timeout: "ls_expired",
  rp_signature_expired: "ls_expired",
  // This phone's World ID cannot approve: it holds no credential the request accepts.
  credential_unavailable: "ls_wrong",
  world_id_4_not_available: "ls_wrong",
  world_id_3_not_available: "ls_wrong",
  feature_unavailable: "ls_wrong",
  identity_attributes_not_matched: "ls_wrong",
  // Approvals are World ID session proofs: a refused repeat is a replayed proof, used once already.
  max_verifications_reached: "ls_reused",
  nullifier_replayed: "ls_reused",
  // RP, clock and config errors, and World's plumbing.
  invalid_rp_signature: "ls_world_down",
  duplicate_nonce: "ls_world_down",
  unknown_rp: "ls_world_down",
  inactive_rp: "ls_world_down",
  invalid_rp_id_format: "ls_world_down",
  timestamp_too_old: "ls_world_down",
  timestamp_too_far_in_future: "ls_world_down",
  invalid_timestamp: "ls_world_down",
  malformed_request: "ls_world_down",
  invalid_network: "ls_world_down",
  inclusion_proof_pending: "ls_world_down",
  inclusion_proof_failed: "ls_world_down",
  connection_failed: "ls_world_down",
  unexpected_response: "ls_world_down",
  generic_error: "ls_world_down",
  failed_by_host_app: "ls_world_down",
};

/** A World App / bridge error code from a failed IDKit approval poll. Unknown: World is down. */
export function approvalAppFailure(code: string | undefined): LsFailure {
  return (code && APPROVAL_APP_ERRORS[code]) || "ls_world_down";
}

/**
 * The portal refused an approval proof. Unavailable or our setup: ls_world_down. A replayed session
 * proof: ls_reused. Any other refusal of the proof itself: ls_mismatch.
 */
export function approvalPortalFailure(status: number, body: PortalError | undefined): LsFailure {
  if (status === 404 || status >= 500 || status === 429) return "ls_world_down";
  if (isReplay(body)) return "ls_reused";
  if (body?.code && PORTAL_CONFIG_CODES.has(body.code)) return "ls_world_down";
  return "ls_mismatch";
}

/** Our own checks on an approval proof. A proof for another request, session, action or environment,
 *  or a malformed one: ls_mismatch. No credential we accept: this World ID cannot approve -> ls_wrong. */
export function approvalProofFailure(check: ProofCheck): LsFailure {
  return check === "credential" ? "ls_wrong" : "ls_mismatch";
}

// ---- Agent Pass: RFC 8628 device grant at World IdP (auth.world.org) -------------------------

export type PollStep = { kind: "continue"; slowDown: boolean } | { kind: "fail"; failure: LsFailure };

/**
 * One token-endpoint poll answered with an OAuth error. World's rules (OIDC guide, device flow):
 * keep polling on authorization_pending, add 5 s on slow_down, stop on everything else.
 */
export function devicePollStep(error: string | undefined, status: number): PollStep {
  if (status === 503 || status === 429) return { kind: "fail", failure: "ls_world_down" }; // "never approval"
  switch (error) {
    case "authorization_pending":
      return { kind: "continue", slowDown: false };
    case "slow_down":
      return { kind: "continue", slowDown: true };
    case "access_denied": // the person tapped Deny, or an essential requirement was unmet
    case "unmet_authentication_requirements":
      return { kind: "fail", failure: "ls_denied" };
    case "expired_token": // the 20-minute device code lapsed
    case "invalid_grant": // the code is dead: consumed, expired or bound elsewhere
      return { kind: "fail", failure: "ls_expired" };
    default:
      // invalid_client, invalid_request, unauthorized_client, unsupported_grant_type, invalid_scope,
      // server_error, temporarily_unavailable, anything unknown: we cannot ask World right now.
      return { kind: "fail", failure: "ls_world_down" };
  }
}

/** Why a returned ID token was refused (idtoken.ts). */
export type TokenReason =
  | "signature"
  | "issuer"
  | "audience"
  | "expired"
  | "iat"
  | "claims"
  | "auth_time"
  | "acr"
  | "jwks_unavailable";

export function tokenFailure(reason: TokenReason): LsFailure {
  switch (reason) {
    case "expired":
      return "ls_expired";
    case "acr":
      return "ls_wrong"; // an account without an accepted credential class cannot approve
    case "jwks_unavailable":
      return "ls_world_down";
    default:
      // A token that is not World's, not for us, or not from this attempt (signature, iss, aud,
      // iat, missing claims, auth_time before the start): it belongs to another request.
      return "ls_mismatch";
  }
}

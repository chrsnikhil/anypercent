/**
 * The checks every IDKit proof goes through, shared by the record-book sign-up (idkit.ts) and the
 * IDKit listing approval (idkit-approvals.ts). Each caller turns the outcome into its own failure
 * names.
 *
 * Three kinds of proof:
 * - "uniqueness": the sign-up. A 4.0 proof for WORLD_ACTION, whose action nullifier makes one book
 *   per human. Requested with session_id "create", it also carries the World ID session the owner
 *   proves later.
 * - "session-create": a createSession proof (the separate-scan fallback). Carries a new session id.
 * - "session": a proveSession proof (the listing approval). Its session_id must be the book's.
 *
 * 1. Before spending a portal call: a 4.0 proof in our environment, of the right kind, bound to this
 *    request's signal (the portal does not know which signal we meant).
 * 2. POST the IDKit result verbatim to /api/v4/verify/{rp_id}.
 * 3. On 200: the response's environment, action and session id again where it names them, then an
 *    item the portal did not fail, bound to our signal, with a credential we accept.
 *
 * Everything after the portal's answer is synchronous, so a caller that checks for a cancel right
 * after `await checkProof(...)` cannot be overtaken by one before it acts.
 *
 * `expires_at_min` on an item is the request's lower bound (about the time the request was made, so
 * already past by now), not the credential's expiry: validity is the portal's check, never read here.
 */
import { hashSignal } from "@worldcoin/idkit-core/hashing";
import { Nullifier } from "@worldcoin/idkit-core/nullifier";
import type { WorldEnvironment } from "./config.js";
import type { PortalError, ProofCheck } from "./failures.js";
import type { IdkitDeps } from "./idkit.js";

export const SCHEMA_CREDENTIAL: Record<number, string> = { 1: "Orb", 11: "Selfie Check" };

export interface ProofContext {
  deps: IdkitDeps;
  environment: WorldEnvironment;
  action: string;
}

export type ProofKind =
  | { kind: "uniqueness" }
  | { kind: "session-create" }
  | { kind: "session"; sessionId: string };

export type ProofResult =
  | {
      ok: true;
      credential: string;
      /** uniqueness only: the canonical action nullifier. */
      canonical: string | null;
      /** The proof's World ID session ("session_<hex>"), when it carries one. Never log it. */
      sessionId: string | null;
    }
  | { ok: false; kind: "check"; check: ProofCheck }
  /** The portal refused it. `canonicals`: the bound items' nullifiers, for naming a book on a repeat. */
  | { ok: false; kind: "portal"; status: number; body: PortalError | undefined; canonicals: string[] }
  | { ok: false; kind: "network" };

type Item = {
  identifier?: unknown;
  signal_hash?: unknown;
  nullifier?: unknown;
  issuer_schema_id?: unknown;
};

const SESSION_RE = /^session_[0-9a-fA-F]+$/;

export function isSessionId(v: unknown): v is string {
  return typeof v === "string" && SESSION_RE.test(v);
}

function sameField(a: unknown, b: string): boolean {
  try {
    return typeof a === "string" && BigInt(a) === BigInt(b);
  } catch {
    return false;
  }
}

function canonicalOf(item: Item): string | null {
  try {
    return Nullifier.fromHex(String(item.nullifier)).toCanonicalString();
  } catch {
    return null;
  }
}

export async function checkProof(
  ctx: ProofContext,
  signal: string,
  result: unknown,
  mode: ProofKind = { kind: "uniqueness" },
): Promise<ProofResult> {
  const r = (result ?? {}) as Record<string, unknown>;
  const check = (c: ProofCheck): ProofResult => ({ ok: false, kind: "check", check: c });

  if (r.environment !== ctx.environment) return check("environment");
  // A legacy 3.0 proof is refused here.
  if (r.protocol_version !== "4.0") return check("action");
  let sessionId: string | null = null;
  if (mode.kind === "uniqueness") {
    if (r.action !== ctx.action) return check("action");
    sessionId = isSessionId(r.session_id) ? r.session_id : null;
  } else {
    // A session proof names no action; a uniqueness proof sent in its place is the wrong kind.
    if (r.action !== undefined) return check("action");
    if (!isSessionId(r.session_id)) return check("session");
    if (mode.kind === "session" && r.session_id !== mode.sessionId) return check("session");
    sessionId = r.session_id;
  }
  const expected = hashSignal(signal);
  const items = (Array.isArray(r.responses) ? r.responses : []) as Item[];
  const bound = items.filter((it) => sameField(it.signal_hash, expected));
  if (bound.length === 0) return check("signal");

  let status: number;
  let body: Record<string, unknown> | undefined;
  try {
    ({ status, body } = (await ctx.deps.verify(result)) as { status: number; body: Record<string, unknown> | undefined });
  } catch {
    return { ok: false, kind: "network" };
  }

  if (status !== 200 || body?.success !== true) {
    const canonicals = mode.kind === "uniqueness" ? bound.map(canonicalOf).filter((c): c is string => c !== null) : [];
    return { ok: false, kind: "portal", status, body: body as PortalError | undefined, canonicals };
  }
  if (body.environment !== undefined && body.environment !== ctx.environment) return check("environment");
  if (mode.kind === "uniqueness" && body.action !== undefined && body.action !== ctx.action) return check("action");
  // The portal names the session it verified ({success, session_id, results, message}): it must be the proof's.
  if (body.session_id !== undefined && sessionId !== null && body.session_id !== sessionId) return check("session");

  // 200 means at least one item verified: use one the portal did not fail, with a credential we accept.
  const portalResults = (Array.isArray(body.results) ? body.results : []) as Array<{ identifier?: unknown; success?: unknown }>;
  let chosen: { item: Item; credential: string } | null = null;
  for (const it of bound) {
    const pr = portalResults.find((p) => p.identifier === it.identifier);
    if (pr && pr.success === false) continue;
    const credential = typeof it.issuer_schema_id === "number" ? SCHEMA_CREDENTIAL[it.issuer_schema_id] : undefined;
    if (!credential) continue;
    if (!chosen || credential === "Orb") chosen = { item: it, credential };
  }
  if (!chosen) return check("credential");

  if (mode.kind !== "uniqueness") return { ok: true, credential: chosen.credential, canonical: null, sessionId };
  const canonical = canonicalOf(chosen.item);
  if (canonical === null) return check("no_nullifier");
  return { ok: true, credential: chosen.credential, canonical, sessionId };
}

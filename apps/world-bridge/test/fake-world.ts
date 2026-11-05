/** A scripted World for IDKit tests: the bridge's statuses and the portal's answers, no network. */
import { hashSignal } from "@worldcoin/idkit-core/hashing";
import type { BridgeRequest, IdkitDeps } from "../src/idkit.js";

export const ACTION = "anypercent-record-book";
export type Status = Awaited<ReturnType<BridgeRequest["pollOnce"]>>;

/** The World ID session a sign-up proof creates by default, and another one. */
export const SESSION_A = "session_" + "a1".repeat(32);
export const SESSION_B = "session_" + "b2".repeat(32);

/** A sign-up proof World App would send for this request's signal: uniqueness on ACTION, plus the
 *  session it created (pass `{ session_id: undefined }` for none). */
export function proof(signal: string, nullifier: string, over: Record<string, unknown> = {}, item: Record<string, unknown> = {}) {
  return {
    protocol_version: "4.0",
    nonce: "0x01",
    action: ACTION,
    session_id: SESSION_A,
    environment: "staging",
    responses: [
      {
        identifier: "selfie",
        signal_hash: hashSignal(signal),
        proof: ["0x1", "0x2", "0x3", "0x4", "0x5"],
        nullifier,
        issuer_schema_id: 11,
        expires_at_min: Math.floor(Date.now() / 1000) + 3600,
        sybil_score: 10,
        ...item,
      },
    ],
    ...over,
  };
}

/** A session proof (createSession or proveSession): no action, the session's id, a session nullifier. */
export function sessionProof(signal: string, sessionId = SESSION_A, over: Record<string, unknown> = {}, item: Record<string, unknown> = {}) {
  return {
    protocol_version: "4.0",
    nonce: "0x02",
    session_id: sessionId,
    environment: "staging",
    responses: [
      {
        identifier: "proof_of_human",
        signal_hash: hashSignal(signal),
        proof: ["0x1", "0x2", "0x3", "0x4", "0x5"],
        session_nullifier: ["0x0777", "0x0888"],
        issuer_schema_id: 1,
        expires_at_min: Math.floor(Date.now() / 1000) - 20,
        ...item,
      },
    ],
    ...over,
  };
}

export const portalOk = (identifier = "selfie") => ({
  status: 200,
  body: { success: true, action: ACTION, environment: "staging", results: [{ identifier, success: true }] },
});

/** The portal's answer to a session proof, as seen live. */
export const portalSessionOk = (sessionId = SESSION_A) => ({
  status: 200,
  body: {
    success: true,
    session_id: sessionId,
    results: [{ identifier: "proof_of_human", sessionId, success: true, nullifier: "0x0777" }],
    message: "Session proof verified successfully",
  },
});

/** The portal for whatever comes: a session proof gets the session answer, anything else portalOk. */
export const portalAuto = (payload: unknown) => {
  const p = payload as { action?: unknown; session_id?: unknown; responses?: Array<{ identifier?: unknown }> };
  if (p.action === undefined && typeof p.session_id === "string") return portalSessionOk(p.session_id);
  return portalOk(String(p.responses?.[0]?.identifier ?? "selfie"));
};

type Kind = "request" | "createSession" | "proveSession";

/** A scripted World: each request walks `statuses(signal)` (sign-ups start "anyb1|", fallback
 *  session scans "anys1|", approvals "anyl1|"); verify answers `portal`. */
export class FakeWorld implements IdkitDeps {
  signals: string[] = [];
  verified: unknown[] = [];
  created: Array<{ kind: Kind; sessionId?: string; description?: string; nonce: string }> = [];
  createFails = false;
  private n = 0;
  constructor(
    public statuses: (signal: string) => Array<Status | Error>,
    public portal: (payload: unknown) => { status: number; body: unknown } | Error = portalAuto,
  ) {}
  private make(kind: Kind, signal: string, extra: { sessionId?: string; description?: string } = {}): BridgeRequest {
    if (this.createFails) throw new Error("bridge down");
    this.signals.push(signal);
    const nonce = `0x${(++this.n).toString(16).padStart(64, "0")}`;
    this.created.push({ kind, nonce, ...extra });
    const script = this.statuses(signal);
    let i = 0;
    return {
      connectorURI: kind === "request" ? "https://staging.world.org/verify?t=fake" : `https://staging.world.org/verify?t=fake-${kind}`,
      nonce,
      pollOnce: async () => {
        const next = script[Math.min(i++, script.length - 1)];
        if (next instanceof Error) throw next;
        return next;
      },
    };
  }
  async createRequest(signal: string): Promise<BridgeRequest> {
    return this.make("request", signal);
  }
  async createSession(signal: string): Promise<BridgeRequest> {
    return this.make("createSession", signal);
  }
  async proveSession(sessionId: string, signal: string, description: string): Promise<BridgeRequest> {
    return this.make("proveSession", signal, { sessionId, description });
  }
  async verify(payload: unknown) {
    this.verified.push(payload);
    const r = this.portal(payload);
    if (r instanceof Error) throw r;
    return r;
  }
}

export const waiting: Status = { type: "waiting_for_connection" };
export const awaiting: Status = { type: "awaiting_confirmation" };
export const confirmed = (result: unknown): Status => ({ type: "confirmed", result: result as never });
export const failed = (error: string): Status => ({ type: "failed", error: error as never });

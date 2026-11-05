/** A scripted World for IDKit tests: the bridge's statuses and the portal's answers, no network. */
import { hashSignal } from "@worldcoin/idkit-core/hashing";
import type { BridgeRequest, IdkitDeps } from "../src/idkit.js";

export const ACTION = "anypercent-record-book";
export type Status = Awaited<ReturnType<BridgeRequest["pollOnce"]>>;

/** A proof World App would send for this request's signal. */
export function proof(signal: string, nullifier: string, over: Record<string, unknown> = {}, item: Record<string, unknown> = {}) {
  return {
    protocol_version: "4.0",
    nonce: "0x01",
    action: ACTION,
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

export const portalOk = (identifier = "selfie") => ({
  status: 200,
  body: { success: true, action: ACTION, environment: "staging", results: [{ identifier, success: true }] },
});

/** A scripted World: each request walks `statuses(signal)`; verify answers `portal`. */
export class FakeWorld implements IdkitDeps {
  signals: string[] = [];
  verified: unknown[] = [];
  createFails = false;
  constructor(
    public statuses: (signal: string) => Array<Status | Error>,
    public portal: (payload: unknown) => { status: number; body: unknown } | Error = () => portalOk(),
  ) {}
  async createRequest(signal: string): Promise<BridgeRequest> {
    if (this.createFails) throw new Error("bridge down");
    this.signals.push(signal);
    const script = this.statuses(signal);
    let i = 0;
    return {
      connectorURI: "https://staging.world.org/verify?t=fake",
      pollOnce: async () => {
        const next = script[Math.min(i++, script.length - 1)];
        if (next instanceof Error) throw next;
        return next;
      },
    };
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

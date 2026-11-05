/**
 * What every listing-approval provider gives the /agentpass/* routes. Two providers implement it:
 * AgentPass (World IdP device grant, agentpass.ts) and IdkitApprovals (an IDKit proof by the
 * book's owner, idkit-approvals.ts). APPROVALS in .env picks one; the HTTP contract is the same.
 */
import type { LsFailure } from "./failures.js";

export type ApprovalsKind = "idkit" | "agentpass";

export interface ApprovalView {
  stage: "scan" | "approve" | "done";
  ok: boolean | null;
  failure: LsFailure | null;
  data: Record<string, unknown>;
}

export interface StartedApproval {
  id: string;
  qr: string;
  code: string;
  expires_s: number;
}

export class StartFailure extends Error {
  constructor(public readonly failure: LsFailure, public readonly status: number, message: string) {
    super(message);
  }
}

export interface ApprovalProvider {
  readonly kind: ApprovalsKind;
  /** Throws StartFailure when World cannot be asked. */
  start(book: string, action: string): Promise<StartedApproval>;
  view(id: string): ApprovalView | undefined;
  /** The console's Circle: idempotent; afterwards view() is done / ls_denied. False: unknown id. */
  cancel(id: string): boolean;
  stopAll(): void;
}

export const BOOK_RE = /^ANY-[A-Z0-9]{3,8}$/;

/** What the console answers for an approval it backed out of. */
export const CANCEL_FAILURE: LsFailure = "ls_denied";

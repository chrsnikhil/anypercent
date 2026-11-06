/**
 * A scripted listing-approval provider (the ApprovalProvider behind /agentpass/*), for the owner ops
 * and the house batch: each start walks scan -> approve -> done, and on approval records the approval
 * in the store exactly as IdkitApprovals does (book, sha256 of the text World App showed, now).
 */
import { createHash } from "node:crypto";
import type { ApprovalProvider, ApprovalView, StartedApproval } from "../src/approvals.js";
import type { LsFailure } from "../src/failures.js";
import type { Store } from "../src/store.js";

export interface Started {
  id: string;
  book: string;
  action: string;
  cancelled: boolean;
}

export class FakeApprovals implements ApprovalProvider {
  readonly kind = "idkit" as const;
  started: Started[] = [];
  /** The outcome of the next approvals: null = approved; a failure name = refused. */
  outcome: LsFailure | null = null;
  /** Record the approval for another book than the one asked (a stranger's World ID). */
  recordAs: string | null = null;
  /** Hand back this jti instead of a fresh one (a replayed or reused approval). */
  reuseJti: string | null = null;
  /** Keep every approval at "approve" until released. */
  hold = false;
  private n = 0;
  private views = new Map<string, ApprovalView>();
  private polls = new Map<string, number>();

  constructor(private readonly store: Store) {}

  async start(book: string, action: string): Promise<StartedApproval> {
    this.n += 1;
    const id = `appr-${this.n}`;
    this.started.push({ id, book, action, cancelled: false });
    this.views.set(id, { stage: "scan", ok: null, failure: null, data: {} });
    this.polls.set(id, 0);
    return { id, qr: `https://world.org/verify?t=fake-${this.n}`, code: "ABC-DEF", expires_s: 300 };
  }

  view(id: string): ApprovalView | undefined {
    const v = this.views.get(id);
    if (!v || v.stage === "done") return v;
    const p = (this.polls.get(id) ?? 0) + 1;
    this.polls.set(id, p);
    if (p === 1) return v;
    if (p === 2 || this.hold) {
      const next: ApprovalView = { stage: "approve", ok: null, failure: null, data: {} };
      this.views.set(id, next);
      return next;
    }
    const s = this.started.find((x) => x.id === id)!;
    if (this.outcome) {
      const done: ApprovalView = { stage: "done", ok: false, failure: this.outcome, data: {} };
      this.views.set(id, done);
      return done;
    }
    const jti = this.reuseJti ?? `jti-${id}`;
    if (!this.reuseJti) this.store.recordApproval(jti, this.recordAs ?? s.book, createHash("sha256").update(s.action).digest("hex"), Math.floor(Date.now() / 1000));
    const done: ApprovalView = { stage: "done", ok: true, failure: null, data: { jti } };
    this.views.set(id, done);
    return done;
  }

  cancel(id: string): boolean {
    const s = this.started.find((x) => x.id === id);
    if (!s) return false;
    s.cancelled = true;
    this.views.set(id, { stage: "done", ok: false, failure: "ls_denied", data: {} });
    return true;
  }

  stopAll(): void {}
}

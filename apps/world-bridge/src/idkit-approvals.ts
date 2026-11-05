/**
 * Listing approvals on IDKit (APPROVALS=idkit), behind the same /agentpass/* contract as Agent Pass.
 *
 * World ID 4.0 nullifiers are one-time-use per action, so a second proof on the record book's action
 * is refused. Each approval is instead a proof of the book's World ID session (stored at sign-up,
 * idkit.ts): IDKit.proveSession(book's session, { action_description: the listing }), which World
 * App shows to the person, bound to this approval by its signal
 * "anyl1|<book>|<sha256(action digest)[:16]>|<approval id>". Only the World ID that created the
 * session can prove it.
 *
 * Checks: the signal hash, the result's session_id equal to the book's, and the portal's success
 * (it names the same session_id). A book with no stored session answers ls_wrong at once.
 *
 * Stages are real, unlike the device grant: waiting_for_connection -> "scan",
 * awaiting_confirmation (and the portal check after it) -> "approve", then "done".
 * On success `data` is {jti}: a one-time approval id, sha256(approval id | request nonce)[:16],
 * consumed in the store so a replayed proof gives ls_reused. Neither the jti nor the session id is
 * ever logged. The approval is also recorded for Arkiv (store.recordApproval: the book and the
 * sha256 of the text World App showed), so /arkiv/publish can hold the write to exactly it.
 *
 * Circle wins: after a cancel the session answers done / ls_denied, polling stops, and a proof
 * that still arrives (even one already at the portal) is discarded.
 */
import { createHash, randomBytes } from "node:crypto";
import {
  CANCEL_FAILURE,
  StartFailure,
  type ApprovalProvider,
  type ApprovalView,
  type StartedApproval,
} from "./approvals.js";
import type { WorldEnvironment } from "./config.js";
import {
  approvalAppFailure,
  approvalPortalFailure,
  approvalProofFailure,
  type LsFailure,
} from "./failures.js";
import { jtiKey } from "./hmac.js";
import { displayCode, type BridgeRequest, type IdkitDeps } from "./idkit.js";
import { checkProof } from "./proof.js";
import type { Store } from "./store.js";

export interface IdkitApprovalOptions {
  deps: IdkitDeps;
  store: Store;
  secret: string;
  /** WORLD_ACTION, for the shared proof checks (a session proof itself names no action). */
  action: string;
  environment: WorldEnvironment;
  ttlS?: number;
  pollMs?: number;
  now?: () => number;
  networkGraceMs?: number;
  maxActive?: number;
  /** Outcome lines: failure names, book, action digest. Never links, signals, session ids or jtis. */
  log?: (line: string) => void;
}

interface Session {
  id: string;
  book: string;
  action: string;
  signal: string;
  /** The book's World ID session. Never logged, never returned. */
  worldSession: string;
  request: BridgeRequest | null;
  expiresAtMs: number;
  view: ApprovalView;
  cancelled: boolean;
  /** The proof is in hand and at the portal: polling has stopped. */
  verifying: boolean;
  networkFailSinceMs: number | null;
  timer: NodeJS.Timeout | null;
}

/** The one-time approval id: this approval's id and its RP request's nonce. */
export function approvalJti(approvalId: string, nonce: string): string {
  return createHash("sha256").update(`${approvalId}|${nonce}`).digest("hex").slice(0, 16);
}

/** Store key for a used approval id, kept apart from Agent Pass's (iss, jti) keys. */
const JTI_SPACE = "idkit-approval";

const NO_SESSION = " (this book has no World session: sign up again)";

export class IdkitApprovals implements ApprovalProvider {
  readonly kind = "idkit" as const;
  private readonly sessions = new Map<string, Session>();
  private readonly ttlS: number;
  private readonly pollMs: number;
  private readonly now: () => number;
  private readonly networkGraceMs: number;
  private readonly maxActive: number;

  constructor(private readonly opts: IdkitApprovalOptions) {
    this.ttlS = opts.ttlS ?? 300;
    this.pollMs = opts.pollMs ?? 1500;
    this.now = opts.now ?? Date.now;
    this.networkGraceMs = opts.networkGraceMs ?? 20_000;
    this.maxActive = opts.maxActive ?? 16;
  }

  async start(book: string, action: string): Promise<StartedApproval> {
    let active = 0;
    for (const s of this.sessions.values()) if (s.view.stage !== "done") active++;
    if (active >= this.maxActive) throw new StartFailure("ls_world_down", 503, "too many approvals in flight");

    const id = randomBytes(16).toString("base64url");
    const digest = createHash("sha256").update(action).digest("hex").slice(0, 16);
    // Starts with "anyl1", never "0x", so hashSignal always takes its UTF-8 branch.
    const signal = `anyl1|${book}|${digest}|${id}`;
    const nowMs = this.now();
    const s: Session = {
      id,
      book,
      action,
      signal,
      worldSession: this.opts.store.recordForBook(book)?.session_id ?? "",
      request: null,
      expiresAtMs: nowMs + this.ttlS * 1000,
      view: { stage: "scan", ok: null, failure: null, data: {} },
      cancelled: false,
      verifying: false,
      networkFailSinceMs: null,
      timer: null,
    };

    if (!s.worldSession) {
      // Nothing for World App to prove: a book from before sessions, or one this bridge never issued.
      this.sessions.set(id, s);
      this.finish(s, "ls_wrong", {}, NO_SESSION);
      return { id, qr: "", code: displayCode(), expires_s: this.ttlS };
    }

    try {
      s.request = await this.opts.deps.proveSession(s.worldSession, signal, action);
    } catch {
      throw new StartFailure("ls_world_down", 503, "could not create the IDKit request");
    }
    this.sessions.set(id, s);
    this.schedule(s, this.pollMs);
    this.prune(nowMs);
    return { id, qr: s.request.connectorURI, code: displayCode(), expires_s: this.ttlS };
  }

  view(id: string): ApprovalView | undefined {
    return this.sessions.get(id)?.view;
  }

  cancel(id: string): boolean {
    const s = this.sessions.get(id);
    if (!s) return false;
    if (s.cancelled) return true;
    s.cancelled = true;
    if (s.timer) clearTimeout(s.timer);
    s.timer = null;
    s.view = { stage: "done", ok: false, failure: CANCEL_FAILURE, data: {} };
    this.opts.log?.(`approval (World ID) ${s.book} "${s.action}": cancelled on the console (Circle)`);
    return true;
  }

  stopAll(): void {
    for (const s of this.sessions.values()) if (s.timer) clearTimeout(s.timer);
  }

  private schedule(s: Session, delayMs: number): void {
    s.timer = setTimeout(() => {
      s.timer = null;
      this.tick(s).catch(() => this.finish(s, "ls_world_down"));
    }, delayMs);
  }

  private finish(s: Session, failure: LsFailure | null, data: Record<string, unknown> = {}, note = ""): void {
    if (s.view.stage === "done") return;
    if (s.timer) clearTimeout(s.timer);
    s.timer = null;
    s.view = { stage: "done", ok: failure === null, failure, data };
    this.opts.log?.(`approval (World ID) ${s.book} "${s.action}": ${failure ?? "approved"}${note}`);
  }

  private async tick(s: Session): Promise<void> {
    if (s.view.stage === "done" || s.verifying || !s.request) return;
    // A few seconds of grace past the lifetime for an approval already on its way.
    if (this.now() >= s.expiresAtMs + 5000) return this.finish(s, "ls_expired");

    let status: Awaited<ReturnType<BridgeRequest["pollOnce"]>>;
    try {
      status = await s.request.pollOnce({ timeout: 8000 });
    } catch {
      s.networkFailSinceMs ??= this.now();
      if (this.now() - s.networkFailSinceMs >= this.networkGraceMs) return this.finish(s, "ls_world_down");
      return this.schedule(s, this.pollMs * 2);
    }
    s.networkFailSinceMs = null;
    if (isDone(s)) return; // cancelled while the poll was in flight

    switch (status.type) {
      case "waiting_for_connection":
        return this.schedule(s, this.pollMs);
      case "awaiting_confirmation":
        s.view = { ...s.view, stage: "approve" };
        return this.schedule(s, this.pollMs);
      case "failed":
        // World App's own error code is no secret, and the only way to tell a refusal (another person's
        // World App cannot prove this book's session) from a real outage.
        return this.finish(s, approvalAppFailure(status.error), {}, ` (World App: ${String(status.error)})`);
      case "confirmed":
        s.view = { ...s.view, stage: "approve" };
        s.verifying = true;
        return this.accept(s, status.result);
      default:
        return this.schedule(s, this.pollMs);
    }
  }

  private async accept(s: Session, result: unknown): Promise<void> {
    const ctx = { deps: this.opts.deps, environment: this.opts.environment, action: this.opts.action };
    const r = await checkProof(ctx, s.signal, result, { kind: "session", sessionId: s.worldSession });
    // Circle won while the portal was answering: discard the proof. From here to the store write
    // everything is synchronous, so a cancel cannot slip in after this check.
    if (s.cancelled) return;

    if (!r.ok) {
      if (r.kind === "network") return this.finish(s, "ls_world_down");
      if (r.kind === "check") {
        const why = r.check === "session" ? " (the proof is for another World session)" : "";
        return this.finish(s, approvalProofFailure(r.check), {}, why);
      }
      return this.finish(s, approvalPortalFailure(r.status, r.body), {}, " (the portal refused the session proof)");
    }

    const jti = approvalJti(s.id, s.request?.nonce ?? "");
    const nowS = Math.floor(this.now() / 1000);
    if (!this.opts.store.useJti(jtiKey(JTI_SPACE, jti), nowS)) {
      return this.finish(s, "ls_reused");
    }
    this.opts.store.recordApproval(jti, s.book, createHash("sha256").update(s.action).digest("hex"), nowS);
    return this.finish(s, null, { jti }, ` (${r.credential}, the book's World session, approval id used once)`);
  }

  /** Forget finished sessions an hour after their expiry so memory stays bounded. */
  private prune(nowMs: number): void {
    for (const [id, s] of this.sessions) {
      if (s.view.stage === "done" && nowMs - s.expiresAtMs > 3_600_000) this.sessions.delete(id);
    }
  }
}

/** Read through a function so TypeScript does not keep a narrowing across an await. */
function isDone(s: { view: { stage: string } }): boolean {
  return s.view.stage === "done";
}

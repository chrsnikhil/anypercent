/**
 * Agent Pass listing approvals: one RFC 8628 device grant per money action, run from this backend.
 *
 * The console shows verification_uri_complete as a QR and the user_code; the device_code never
 * leaves this process. World's device flow has no "scanned" signal (polls answer
 * authorization_pending until the human approves or denies), so `stage` stays "scan" until the
 * terminal state and then goes straight to "done".
 *
 * Success needs every check: a valid ID token (idtoken.ts), an unused jti, and an account that
 * matches the book (the first approval for a book binds it: trust on first use).
 *
 * Circle wins: POST /cancel ends the session for the console at once (done, ls_denied) and nothing
 * is ever bound or authorised for it again. The bridge listens on for a short while only so a late
 * phone approval can be logged as ignored and its jti burned; the session's answer never changes.
 */
import { randomBytes } from "node:crypto";
import { devicePollStep, tokenFailure, type LsFailure } from "./failures.js";
import { jtiKey, subKey } from "./hmac.js";
import { DOCUMENTED_ACR, validateIdToken } from "./idtoken.js";
import type { DeviceGrantClient } from "./oidc.js";
import type { Store } from "./store.js";
import {
  CANCEL_FAILURE,
  StartFailure,
  type ApprovalProvider,
  type ApprovalView,
  type StartedApproval,
} from "./approvals.js";

export { BOOK_RE, CANCEL_FAILURE, StartFailure, type ApprovalView, type StartedApproval } from "./approvals.js";

export interface AgentPassOptions {
  idp: DeviceGrantClient;
  store: Store;
  secret: string;
  clientId: string;
  /** AGENTPASS_ACCEPTED_ACR: added to discovery's acr_values_supported and World's documented set. */
  extraAcr?: string[];
  /** Milliseconds clock. */
  now?: () => number;
  /** How long one of World's "seconds" lasts here; tests shrink it. */
  msPerSecond?: number;
  /** Clock difference tolerated against World, seconds. */
  skewS?: number;
  /** Connection failures in a row for this long end the attempt as ls_world_down. */
  networkGraceMs?: number;
  /** After Circle, keep listening this long so a late approval is logged as ignored and burned. */
  cancelListenMs?: number;
  maxActive?: number;
  /** Outcome lines: failure names, book, action digest. Never tokens, codes or subs. */
  log?: (line: string) => void;
}

interface Session {
  id: string;
  book: string;
  action: string;
  deviceCode: string;
  startedAtS: number;
  expiresAtMs: number;
  intervalS: number;
  view: ApprovalView;
  cancelledAtMs: number | null;
  /** The poll loop has ended (it can outlive the console's answer after a cancel). */
  stopped: boolean;
  networkFailSinceMs: number | null;
  timer: NodeJS.Timeout | null;
}


const CHECKS = " (checked: RS256 signature via JWKS, iss, aud, exp, iat, auth_time in this attempt, acr, jti unused)";

export class AgentPass implements ApprovalProvider {
  readonly kind = "agentpass" as const;
  private readonly sessions = new Map<string, Session>();
  private readonly now: () => number;
  private readonly msPerSecond: number;
  private readonly skewS: number;
  private readonly networkGraceMs: number;
  private readonly cancelListenMs: number;
  private readonly maxActive: number;

  constructor(private readonly opts: AgentPassOptions) {
    this.now = opts.now ?? Date.now;
    this.msPerSecond = opts.msPerSecond ?? 1000;
    this.skewS = opts.skewS ?? 30;
    this.networkGraceMs = opts.networkGraceMs ?? 30_000;
    this.cancelListenMs = opts.cancelListenMs ?? 120_000;
    this.maxActive = opts.maxActive ?? 16;
  }

  private active(): number {
    let n = 0;
    for (const s of this.sessions.values()) if (!s.stopped) n++;
    return n;
  }

  async start(book: string, action: string): Promise<StartedApproval> {
    if (this.active() >= this.maxActive) {
      throw new StartFailure("ls_world_down", 503, "too many approvals in flight");
    }
    let started;
    try {
      started = await this.opts.idp.start();
    } catch {
      // Discovery failed, invalid_client, 429 (Retry-After: 60), network: World cannot be asked.
      throw new StartFailure("ls_world_down", 503, "device authorization failed");
    }
    const nowMs = this.now();
    const id = randomBytes(16).toString("base64url");
    const s: Session = {
      id,
      book,
      action,
      deviceCode: started.device_code,
      startedAtS: Math.floor(nowMs / 1000),
      expiresAtMs: nowMs + started.expires_in * this.msPerSecond,
      intervalS: Math.max(1, started.interval ?? 5),
      view: { stage: "scan", ok: null, failure: null, data: {} },
      cancelledAtMs: null,
      stopped: false,
      networkFailSinceMs: null,
      timer: null,
    };
    this.sessions.set(id, s);
    this.schedule(s, s.intervalS * this.msPerSecond);
    this.prune(nowMs);
    return {
      id,
      // Never build the approval link ourselves: World's complete URI, else its plain one.
      qr: started.verification_uri_complete ?? started.verification_uri,
      code: started.user_code,
      expires_s: started.expires_in,
    };
  }

  view(id: string): ApprovalView | undefined {
    return this.sessions.get(id)?.view;
  }

  /**
   * The console's Circle. Idempotent. From now on the session answers done / ls_denied, whatever
   * the phone does; a late approval is logged as ignored and its jti burned, never acted on.
   * False: unknown id.
   */
  cancel(id: string): boolean {
    const s = this.sessions.get(id);
    if (!s) return false;
    if (s.cancelledAtMs !== null) return true;
    s.cancelledAtMs = this.now();
    s.view = { stage: "done", ok: false, failure: CANCEL_FAILURE, data: {} };
    this.opts.log?.(`agentpass ${s.book} "${s.action}": cancelled on the console (Circle)`);
    return true;
  }

  stopAll(): void {
    for (const s of this.sessions.values()) this.stop(s);
  }

  // ---- the poll loop ----------------------------------------------------------------------

  private schedule(s: Session, delayMs: number): void {
    s.timer = setTimeout(() => {
      s.timer = null;
      this.tick(s).catch(() => this.finish(s, "ls_world_down"));
    }, delayMs);
  }

  private stop(s: Session): void {
    if (s.timer) clearTimeout(s.timer);
    s.timer = null;
    s.stopped = true;
    s.deviceCode = "";
  }

  /** End the loop with an outcome. After a cancel the console's answer stays ls_denied: the
   *  outcome is only logged. */
  private finish(s: Session, failure: LsFailure | null, data: Record<string, unknown> = {}, note = ""): void {
    if (s.stopped) return;
    this.stop(s);
    if (s.cancelledAtMs !== null) {
      const what = failure === null ? "phone approved after Circle: ignored, nothing bound, jti burned" : `after Circle: ${failure}`;
      this.opts.log?.(`agentpass ${s.book} "${s.action}": ${what}${note}`);
      return;
    }
    s.view = { stage: "done", ok: failure === null, failure, data };
    this.opts.log?.(`agentpass ${s.book} "${s.action}": ${failure ?? "approved"}${note}`);
  }

  private async tick(s: Session): Promise<void> {
    if (s.stopped) return;
    const nowMs = this.now();
    if (nowMs >= s.expiresAtMs) return this.finish(s, "ls_expired");
    if (s.cancelledAtMs !== null && nowMs - s.cancelledAtMs >= this.cancelListenMs) {
      return this.finish(s, "ls_expired"); // stopped listening; nothing was approved in time
    }

    const result = await this.opts.idp.poll(s.deviceCode);
    if (s.stopped) return;

    if (result.kind === "network") {
      // World: back off before polling again. A long outage ends the attempt.
      s.networkFailSinceMs ??= nowMs;
      if (this.now() - s.networkFailSinceMs >= this.networkGraceMs) return this.finish(s, "ls_world_down");
      return this.schedule(s, Math.min(s.intervalS * 2, 30) * this.msPerSecond);
    }
    s.networkFailSinceMs = null;

    if (result.kind === "error") {
      const step = devicePollStep(result.error, result.status);
      if (step.kind === "fail") return this.finish(s, step.failure);
      if (step.slowDown) s.intervalS += 5; // for all later polls
      return this.schedule(s, s.intervalS * this.msPerSecond);
    }

    await this.accept(s, result.idToken);
  }

  /** Validate the ID token and apply the jti and book checks; then finish the session. */
  private async accept(s: Session, idToken: string): Promise<void> {
    let disc;
    try {
      disc = await this.opts.idp.discover();
    } catch {
      return this.finish(s, "ls_world_down");
    }
    const accepted = new Set<string>([...disc.acrSupported, ...DOCUMENTED_ACR, ...(this.opts.extraAcr ?? [])]);
    const check = await validateIdToken(idToken, this.opts.idp.keys(), {
      issuer: disc.issuer,
      clientId: this.opts.clientId,
      acceptedAcr: accepted,
      startedAt: s.startedAtS,
      now: Math.floor(this.now() / 1000),
      skew: this.skewS,
    });
    if (s.stopped) return;
    if (!check.ok) return this.finish(s, tokenFailure(check.reason));

    // From here to finish() is synchronous: a cancel cannot slip in between the checks and the bind.
    const { iss, sub, jti } = check.claims;
    const nowS = Math.floor(this.now() / 1000);
    // One token, one approval: consumed here whatever happens next, including after Circle.
    if (!this.opts.store.useJti(jtiKey(iss, jti), nowS)) return this.finish(s, "ls_reused");

    const sKey = subKey(this.opts.secret, iss, sub);
    if (s.cancelledAtMs !== null) {
      // Circle already won: bind nothing.
      const wrong = this.opts.store.checkBinding(s.book, sKey) === "mismatch";
      return this.finish(s, wrong ? "ls_wrong" : null, {}, wrong ? "" : CHECKS);
    }
    const bind = this.opts.store.bindOrCheck(s.book, sKey, nowS);
    if (bind === "mismatch") return this.finish(s, "ls_wrong", {}, " (account does not own the book)");
    const how = bind === "bound" ? "bound to the book (first approval)" : "matches the book";
    return this.finish(s, null, { jti }, `${CHECKS}, account ${how}`);
  }

  /** Forget finished sessions an hour after their expiry so memory stays bounded. */
  private prune(nowMs: number): void {
    for (const [id, s] of this.sessions) {
      if (s.stopped && nowMs - s.expiresAtMs > 3_600_000) this.sessions.delete(id);
    }
  }
}

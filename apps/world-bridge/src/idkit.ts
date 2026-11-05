/**
 * IDKit record-book sign-up: one World ID, one record book, and the World ID session its owner
 * proves for every listing approval.
 *
 * The backend signs the request (RP signature), creates it on World's bridge with
 * @worldcoin/idkit-core, and polls it. The console only renders `qr` (the World App connect link)
 * and our short display code. Stages follow the bridge's status:
 *   waiting_for_connection -> "scan", awaiting_confirmation -> "confirm",
 *   confirmed (proof in hand, checking with the Developer Portal) -> "verify", then "done".
 *
 * The sign-up is a uniqueness request on WORLD_ACTION with session_id "create": its action nullifier
 * gives one book per human (World ID 4.0 nullifiers are one-time-use per action, so a second
 * sign-up by the same human is refused), and its session_id is stored with the book for the
 * approvals (idkit-approvals.ts). The session id never leaves this process: not logged, not returned.
 *
 * Fallback (WORLD_SIGNUP_SESSION=separate): when the sign-up result carries no session, a second
 * scan, a createSession request, follows right after; while it waits the view stays at "verify" and
 * carries data.session_qr / data.session_code for the console to show. The launcher must draw that
 * QR, so this needs a launcher change before it is switched on.
 *
 * The proof is bound to this sign-up by its signal ("anyb1|<console hash>|<sign-up id>"), checked
 * here because the portal does not know which signal we meant. The nullifier is stored only as an
 * HMAC; the book id is derived from it, so the same human always gets the same book.
 */
import { createHash, randomBytes } from "node:crypto";
import { CredentialRequest, IDKit, type IDKitRequest } from "@worldcoin/idkit-core";
import { signRequest } from "@worldcoin/idkit-core/signing";
import type { Config, WorldEnvironment } from "./config.js";
import { idkitAppFailure, portalFailure, proofCheckFailure, type IdFailure } from "./failures.js";
import { BOOK_CHARS, nullifierKey, runnerId } from "./hmac.js";
import { checkProof } from "./proof.js";
import type { Store } from "./store.js";

export interface IdkitView {
  stage: "scan" | "confirm" | "verify" | "done";
  ok: boolean | null;
  failure: IdFailure | null;
  data: Record<string, unknown>;
}

export interface StartedIdkit {
  id: string;
  qr: string;
  code: string;
  expires_s: number;
}

/** A created World request: its link, its poll, and the RP signature's nonce (for one-time ids). */
export type BridgeRequest = Pick<IDKitRequest, "connectorURI" | "pollOnce"> & { nonce?: string };

/** What the session managers need from World; tests swap in fakes. */
export interface IdkitDeps {
  /** The sign-up: a uniqueness request on WORLD_ACTION that also creates a World ID session. */
  createRequest(signal: string): Promise<BridgeRequest>;
  /** The separate-scan fallback: a createSession request. */
  createSession(signal: string): Promise<BridgeRequest>;
  /** A listing approval: proveSession for a book's session, showing `description` in World App. */
  proveSession(sessionId: string, signal: string, description: string): Promise<BridgeRequest>;
  /** POST the IDKit result, verbatim, to /api/v4/verify/{rp_id}. Throws on network failure. */
  verify(payload: unknown): Promise<{ status: number; body: unknown }>;
}

/**
 * The real thing, with the call shapes proven live on an Orb World App in production:
 * - one `proof_of_human` CredentialRequest through `.constraints()` (session flows reject presets,
 *   and an any() with `selfie` in it made World App fail silently: "something went wrong");
 * - `allow_legacy_proofs: false` (sessions are 4.0 only);
 * - session requests are signed without an action; the sign-up's uniqueness request with it.
 */
export function realIdkitDeps(cfg: Config, ttlS: number): IdkitDeps {
  const w = cfg.world;
  const key = w.signingKey.replace(/^0x/, "");
  const rp = (action?: string) => {
    const s = signRequest({ signingKeyHex: key, ...(action ? { action } : {}), ttl: ttlS });
    return {
      nonce: s.nonce,
      ctx: { rp_id: w.rpId, nonce: s.nonce, created_at: s.createdAt, expires_at: s.expiresAt, signature: s.sig },
    };
  };
  const poh = (signal: string) => CredentialRequest("proof_of_human", { signal });
  const wrap = (req: IDKitRequest, nonce: string): BridgeRequest => ({
    connectorURI: req.connectorURI,
    pollOnce: (o) => req.pollOnce(o),
    nonce,
  });
  const app_id = w.appId as `app_${string}`;
  return {
    async createRequest(signal) {
      const { ctx, nonce } = rp(w.action);
      const req = await IDKit.request({
        app_id,
        action: w.action,
        rp_context: ctx,
        allow_legacy_proofs: false,
        session_id: "create",
        environment: w.environment,
      }).constraints(poh(signal), { timeout: 8000 });
      return wrap(req, nonce);
    },
    async createSession(signal) {
      const { ctx, nonce } = rp();
      const req = await IDKit.createSession({
        app_id,
        rp_context: ctx,
        environment: w.environment,
        action_description: "Any% record book",
      }).constraints(poh(signal), { timeout: 8000 });
      return wrap(req, nonce);
    },
    async proveSession(sessionId, signal, description) {
      const { ctx, nonce } = rp();
      const req = await IDKit.proveSession(sessionId as `session_${string}`, {
        app_id,
        rp_context: ctx,
        environment: w.environment,
        action_description: description,
      }).constraints(poh(signal), { timeout: 8000 });
      return wrap(req, nonce);
    },
    async verify(payload) {
      const res = await fetch(`${w.portalBase}/api/v4/verify/${encodeURIComponent(w.rpId)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(8000),
      });
      let body: unknown = undefined;
      try {
        body = await res.json();
      } catch {
        body = undefined;
      }
      return { status: res.status, body };
    },
  };
}

export type SignupSessionMode = "combined" | "separate";

export interface IdkitOptions {
  deps: IdkitDeps;
  store: Store;
  secret: string;
  action: string;
  environment: WorldEnvironment;
  /** combined (default): the sign-up proof carries the session. separate: a second createSession scan. */
  signupSession?: SignupSessionMode;
  ttlS?: number;
  pollMs?: number;
  now?: () => number;
  networkGraceMs?: number;
  maxActive?: number;
  /** Outcome lines: failure names and book ids. Never links, signals, nullifiers or session ids. */
  log?: (line: string) => void;
}

interface Session {
  id: string;
  /** The signal of the request now being polled. */
  signal: string;
  request: BridgeRequest;
  expiresAtMs: number;
  view: IdkitView;
  cancelled: boolean;
  /** A proof is at the portal: polling has stopped. */
  verifying: boolean;
  phase: "signup" | "session";
  /** The separate-scan fallback: the book waiting for its session, and the sign-up's own outcome. */
  pending: { nKey: string; failure: IdFailure | null; data: Record<string, unknown> } | null;
  networkFailSinceMs: number | null;
  timer: NodeJS.Timeout | null;
}

/** What the console answers for a sign-up it backed out of. */
export const CANCEL_FAILURE: IdFailure = "id_rejected";

const NO_SESSION_NOTE =
  " (no World session in the sign-up proof: listing approvals will answer ls_wrong; set WORLD_SIGNUP_SESSION=separate)";

export class IdkitStartFailure extends Error {
  constructor(public readonly failure: IdFailure, public readonly status: number, message: string) {
    super(message);
  }
}

export function displayCode(): string {
  const b = randomBytes(6);
  const ch = (i: number) => BOOK_CHARS[b[i] % BOOK_CHARS.length];
  return `${ch(0)}${ch(1)}${ch(2)}-${ch(3)}${ch(4)}${ch(5)}`;
}

export class IdkitSessions {
  private readonly sessions = new Map<string, Session>();
  private readonly ttlS: number;
  private readonly pollMs: number;
  private readonly now: () => number;
  private readonly networkGraceMs: number;
  private readonly maxActive: number;
  private readonly mode: SignupSessionMode;

  constructor(private readonly opts: IdkitOptions) {
    this.ttlS = opts.ttlS ?? 300;
    this.pollMs = opts.pollMs ?? 1500;
    this.now = opts.now ?? Date.now;
    this.networkGraceMs = opts.networkGraceMs ?? 20_000;
    this.maxActive = opts.maxActive ?? 16;
    this.mode = opts.signupSession ?? "combined";
  }

  async start(consoleId: string): Promise<StartedIdkit> {
    let active = 0;
    for (const s of this.sessions.values()) if (s.view.stage !== "done") active++;
    if (active >= this.maxActive) throw new IdkitStartFailure("id_offline", 503, "too many sign-ups in flight");

    const id = randomBytes(16).toString("base64url");
    const consoleTag = createHash("sha256").update(consoleId).digest("hex").slice(0, 16);
    // Never starts with "0x", so hashSignal always takes its UTF-8 branch.
    const signal = `anyb1|${consoleTag}|${id}`;
    let request: BridgeRequest;
    try {
      request = await this.opts.deps.createRequest(signal);
    } catch {
      throw new IdkitStartFailure("id_offline", 503, "could not create the IDKit request");
    }
    const nowMs = this.now();
    const s: Session = {
      id,
      signal,
      request,
      expiresAtMs: nowMs + this.ttlS * 1000,
      view: { stage: "scan", ok: null, failure: null, data: {} },
      cancelled: false,
      verifying: false,
      phase: "signup",
      pending: null,
      networkFailSinceMs: null,
      timer: null,
    };
    this.sessions.set(id, s);
    this.schedule(s, this.pollMs);
    this.prune(nowMs);
    return { id, qr: request.connectorURI, code: displayCode(), expires_s: this.ttlS };
  }

  view(id: string): IdkitView | undefined {
    return this.sessions.get(id)?.view;
  }

  /**
   * The console's Circle. Idempotent. From now on the session answers done / id_rejected, and a
   * proof that still arrives (even one already at the portal) is discarded: no book is made or
   * named. False: unknown id.
   */
  cancel(id: string): boolean {
    const s = this.sessions.get(id);
    if (!s) return false;
    if (s.cancelled) return true;
    s.cancelled = true;
    if (s.timer) clearTimeout(s.timer);
    s.timer = null;
    s.view = { stage: "done", ok: false, failure: CANCEL_FAILURE, data: {} };
    this.opts.log?.("idkit sign-up: cancelled on the console (Circle)");
    return true;
  }

  stopAll(): void {
    for (const s of this.sessions.values()) if (s.timer) clearTimeout(s.timer);
  }

  private schedule(s: Session, delayMs: number): void {
    s.timer = setTimeout(() => {
      s.timer = null;
      this.tick(s).catch(() => this.finish(s, "id_offline"));
    }, delayMs);
  }

  private finish(s: Session, failure: IdFailure | null, data: Record<string, unknown> = {}, note = ""): void {
    if (s.view.stage === "done") return;
    if (s.timer) clearTimeout(s.timer);
    s.timer = null;
    s.view = { stage: "done", ok: failure === null, failure, data };
    const book = typeof data.book === "string" ? ` ${data.book}` : "";
    const cred = typeof data.credential === "string" ? ` (${data.credential})` : "";
    this.opts.log?.(`idkit sign-up: ${failure ?? "verified"}${book}${cred}${note}`);
  }

  private async tick(s: Session): Promise<void> {
    if (s.view.stage === "done" || s.verifying) return;
    // A few seconds of grace past the TTL for a confirmation already on its way.
    if (this.now() >= s.expiresAtMs + 5000) return this.finish(s, "id_expired", {}, this.phaseNote(s));

    let status: Awaited<ReturnType<BridgeRequest["pollOnce"]>>;
    try {
      status = await s.request.pollOnce({ timeout: 8000 });
    } catch {
      s.networkFailSinceMs ??= this.now();
      if (this.now() - s.networkFailSinceMs >= this.networkGraceMs) return this.finish(s, "id_offline", {}, this.phaseNote(s));
      return this.schedule(s, this.pollMs * 2);
    }
    s.networkFailSinceMs = null;
    if (isDone(s)) return; // cancelled while the poll was in flight

    switch (status.type) {
      case "waiting_for_connection":
        return this.schedule(s, this.pollMs);
      case "awaiting_confirmation":
        if (s.phase === "signup") s.view = { ...s.view, stage: "confirm" };
        return this.schedule(s, this.pollMs);
      case "failed":
        return this.finish(s, idkitAppFailure(status.error), {}, ` (World App: ${String(status.error)})${this.phaseNote(s)}`);
      case "confirmed":
        s.verifying = true;
        if (s.phase === "session") return this.verifySession(s, status.result);
        s.view = { ...s.view, stage: "verify" };
        return this.verify(s, status.result);
      default:
        return this.schedule(s, this.pollMs);
    }
  }

  private phaseNote(s: Session): string {
    return s.phase === "session" ? " (in the World session scan; the book has no session yet)" : "";
  }

  private ctx() {
    return { deps: this.opts.deps, environment: this.opts.environment, action: this.opts.action };
  }

  private async verify(s: Session, result: unknown): Promise<void> {
    const r = await checkProof(this.ctx(), s.signal, result, { kind: "uniqueness" });
    // Circle won while the portal was answering: discard the proof, make and name no book. From
    // here to claimBook everything is synchronous, so a cancel cannot slip in after this check.
    if (s.cancelled) return;

    if (!r.ok) {
      if (r.kind === "network") return this.finish(s, "id_offline");
      if (r.kind === "check") return this.finish(s, proofCheckFailure(r.check));
      const failure = portalFailure(r.status, r.body);
      if (failure === "id_dup") {
        // World refused a repeat of a proof it otherwise holds: name the book this nullifier owns.
        const nKey = this.lookup(r.canonicals);
        const rec = nKey ? this.opts.store.bookFor(nKey) : undefined;
        if (nKey && rec) return this.settle(s, nKey, { failure: "id_dup", data: { book: rec.book } });
        return this.finish(s, "id_dup");
      }
      return this.finish(s, failure);
    }

    const nowS = Math.floor(this.now() / 1000);
    const nKey = nullifierKey(this.opts.secret, this.opts.action, r.canonical!);
    const runner = runnerId(this.opts.secret, `${this.opts.action}|${r.canonical}`);
    const { created, record } = this.opts.store.claimBook(nKey, r.credential, runner, nowS, r.sessionId ?? undefined);
    if (!created) {
      // A verified repeat by the book's owner may still carry the session the book lacks.
      if (r.sessionId) this.opts.store.setSession(nKey, r.sessionId);
      return this.settle(s, nKey, { failure: "id_dup", data: { book: record.book } });
    }
    return this.settle(s, nKey, {
      failure: null,
      data: { book: record.book, credential: record.credential, runner_id: record.runner_id },
    });
  }

  /** The sign-up's outcome is known. A book with its session finishes now; one without either says
   *  so (combined) or runs the second, createSession scan first (separate). */
  private async settle(
    s: Session,
    nKey: string,
    outcome: { failure: IdFailure | null; data: Record<string, unknown> },
  ): Promise<void> {
    if (this.opts.store.bookFor(nKey)?.session_id) return this.finish(s, outcome.failure, outcome.data);
    if (this.mode === "combined") return this.finish(s, outcome.failure, outcome.data, NO_SESSION_NOTE);

    const signal = `anys1|${s.id}`;
    let request: BridgeRequest;
    try {
      request = await this.opts.deps.createSession(signal);
    } catch {
      return this.finish(s, "id_offline", {}, " (could not create the World session request; the book has no session yet)");
    }
    if (s.cancelled) return;
    s.phase = "session";
    s.signal = signal;
    s.request = request;
    s.pending = { nKey, ...outcome };
    s.verifying = false;
    s.expiresAtMs = this.now() + this.ttlS * 1000;
    s.view = {
      stage: "verify",
      ok: null,
      failure: null,
      data: { session_qr: request.connectorURI, session_code: displayCode() },
    };
    const book = typeof outcome.data.book === "string" ? ` ${outcome.data.book}` : "";
    this.opts.log?.(`idkit sign-up:${book} needs its World session: waiting for the second scan`);
    this.schedule(s, this.pollMs);
  }

  private async verifySession(s: Session, result: unknown): Promise<void> {
    const r = await checkProof(this.ctx(), s.signal, result, { kind: "session-create" });
    if (s.cancelled) return;
    const note = this.phaseNote(s);
    if (!r.ok) {
      if (r.kind === "network") return this.finish(s, "id_offline", {}, note);
      if (r.kind === "check") return this.finish(s, proofCheckFailure(r.check), {}, note);
      return this.finish(s, portalFailure(r.status, r.body), {}, note);
    }
    const pending = s.pending!;
    this.opts.store.setSession(pending.nKey, r.sessionId!);
    return this.finish(s, pending.failure, pending.data, " (World session stored)");
  }

  private lookup(canonicals: string[]): string | undefined {
    for (const c of canonicals) {
      const nKey = nullifierKey(this.opts.secret, this.opts.action, c);
      if (this.opts.store.bookFor(nKey)) return nKey;
    }
    return undefined;
  }

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

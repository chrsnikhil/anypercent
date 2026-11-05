/**
 * IDKit record-book sign-up: one World ID, one record book.
 *
 * The backend signs the request (RP signature), creates it on World's bridge with
 * @worldcoin/idkit-core, and polls it. The console only renders `qr` (the World App connect link)
 * and our short display code. Stages follow the bridge's status:
 *   waiting_for_connection -> "scan", awaiting_confirmation -> "confirm",
 *   confirmed (proof in hand, checking with the Developer Portal) -> "verify", then "done".
 *
 * The proof is bound to this sign-up by its signal ("anyb1|<console hash>|<session id>"), checked
 * here because the portal does not know which signal we meant. The nullifier is stored only as an
 * HMAC; the book id is derived from it, so the same human always gets the same book.
 */
import { createHash, randomBytes } from "node:crypto";
import { IDKit, CredentialRequest, any, type IDKitRequest } from "@worldcoin/idkit-core";
import { hashSignal } from "@worldcoin/idkit-core/hashing";
import { Nullifier } from "@worldcoin/idkit-core/nullifier";
import { signRequest } from "@worldcoin/idkit-core/signing";
import type { Config, WorldEnvironment } from "./config.js";
import {
  idkitAppFailure,
  portalFailure,
  proofCheckFailure,
  type IdFailure,
  type PortalError,
  type ProofCheck,
} from "./failures.js";
import { BOOK_CHARS, nullifierKey, runnerId } from "./hmac.js";
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

export type BridgeRequest = Pick<IDKitRequest, "connectorURI" | "pollOnce">;

/** What the session manager needs from World; tests swap in fakes. */
export interface IdkitDeps {
  createRequest(signal: string): Promise<BridgeRequest>;
  /** POST the IDKit result, verbatim, to /api/v4/verify/{rp_id}. Throws on network failure. */
  verify(payload: unknown): Promise<{ status: number; body: unknown }>;
}

/** The real thing: RP-signed IDKit request, Orb (Proof of Human) or Selfie Check, 4.0 proofs only. */
export function realIdkitDeps(cfg: Config, ttlS: number): IdkitDeps {
  const w = cfg.world;
  return {
    async createRequest(signal) {
      const s = signRequest({ signingKeyHex: w.signingKey.replace(/^0x/, ""), action: w.action, ttl: ttlS });
      return IDKit.request({
        app_id: w.appId as `app_${string}`,
        action: w.action,
        rp_context: {
          rp_id: w.rpId,
          nonce: s.nonce,
          created_at: s.createdAt,
          expires_at: s.expiresAt,
          signature: s.sig,
        },
        allow_legacy_proofs: false,
        environment: w.environment,
      }).constraints(
        any(CredentialRequest("proof_of_human", { signal }), CredentialRequest("selfie", { signal })),
        { timeout: 8000 },
      );
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

export interface IdkitOptions {
  deps: IdkitDeps;
  store: Store;
  secret: string;
  action: string;
  environment: WorldEnvironment;
  ttlS?: number;
  pollMs?: number;
  now?: () => number;
  networkGraceMs?: number;
  maxActive?: number;
  /** Outcome lines: failure names and book ids. Never links, signals or nullifiers. */
  log?: (line: string) => void;
}

interface Session {
  id: string;
  signal: string;
  request: BridgeRequest;
  expiresAtMs: number;
  view: IdkitView;
  cancelled: boolean;
  networkFailSinceMs: number | null;
  timer: NodeJS.Timeout | null;
}

const SCHEMA_CREDENTIAL: Record<number, string> = { 1: "Orb", 11: "Selfie Check" };

/** What the console answers for a sign-up it backed out of. */
export const CANCEL_FAILURE: IdFailure = "id_rejected";

export class IdkitStartFailure extends Error {
  constructor(public readonly failure: IdFailure, public readonly status: number, message: string) {
    super(message);
  }
}

function displayCode(): string {
  const b = randomBytes(6);
  const ch = (i: number) => BOOK_CHARS[b[i] % BOOK_CHARS.length];
  return `${ch(0)}${ch(1)}${ch(2)}-${ch(3)}${ch(4)}${ch(5)}`;
}

function sameField(a: unknown, b: string): boolean {
  try {
    return typeof a === "string" && BigInt(a) === BigInt(b);
  } catch {
    return false;
  }
}

type Item = {
  identifier?: unknown;
  signal_hash?: unknown;
  nullifier?: unknown;
  issuer_schema_id?: unknown;
  expires_at_min?: unknown;
};

export class IdkitSessions {
  private readonly sessions = new Map<string, Session>();
  private readonly ttlS: number;
  private readonly pollMs: number;
  private readonly now: () => number;
  private readonly networkGraceMs: number;
  private readonly maxActive: number;

  constructor(private readonly opts: IdkitOptions) {
    this.ttlS = opts.ttlS ?? 300;
    this.pollMs = opts.pollMs ?? 1500;
    this.now = opts.now ?? Date.now;
    this.networkGraceMs = opts.networkGraceMs ?? 20_000;
    this.maxActive = opts.maxActive ?? 16;
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
    if (s.view.stage === "done" || s.view.stage === "verify") return;
    // A few seconds of grace past the TTL for a confirmation already on its way.
    if (this.now() >= s.expiresAtMs + 5000) return this.finish(s, "id_expired");

    let status: Awaited<ReturnType<BridgeRequest["pollOnce"]>>;
    try {
      status = await s.request.pollOnce({ timeout: 8000 });
    } catch {
      s.networkFailSinceMs ??= this.now();
      if (this.now() - s.networkFailSinceMs >= this.networkGraceMs) return this.finish(s, "id_offline");
      return this.schedule(s, this.pollMs * 2);
    }
    s.networkFailSinceMs = null;
    if (isDone(s)) return; // cancelled while the poll was in flight

    switch (status.type) {
      case "waiting_for_connection":
        return this.schedule(s, this.pollMs);
      case "awaiting_confirmation":
        s.view = { ...s.view, stage: "confirm" };
        return this.schedule(s, this.pollMs);
      case "failed":
        return this.finish(s, idkitAppFailure(status.error));
      case "confirmed":
        s.view = { ...s.view, stage: "verify" };
        return this.verify(s, status.result);
      default:
        return this.schedule(s, this.pollMs);
    }
  }

  private async verify(s: Session, result: unknown): Promise<void> {
    const r = (result ?? {}) as Record<string, unknown>;
    const fail = (check: ProofCheck) => this.finish(s, proofCheckFailure(check));

    // Before spending a portal call: the proof must be a 4.0 uniqueness proof for our action in our
    // environment, bound to this sign-up's signal.
    if (r.environment !== this.opts.environment) return fail("environment");
    if (r.protocol_version !== "4.0" || r.action !== this.opts.action) return fail("action");
    const expected = hashSignal(s.signal);
    const items = (Array.isArray(r.responses) ? r.responses : []) as Item[];
    const bound = items.filter((it) => sameField(it.signal_hash, expected));
    if (bound.length === 0) return fail("signal");

    let status: number;
    let body: Record<string, unknown> | undefined;
    try {
      ({ status, body } = (await this.opts.deps.verify(result)) as {
        status: number;
        body: Record<string, unknown> | undefined;
      });
    } catch {
      return this.finish(s, "id_offline");
    }
    // Circle won while the portal was answering: discard the proof, make and name no book. From
    // here to claimBook everything is synchronous, so a cancel cannot slip in after this check.
    if (s.cancelled) return;

    if (status !== 200 || body?.success !== true) {
      const failure = portalFailure(status, body as PortalError | undefined);
      if (failure === "id_dup") {
        // World refused a repeat of a proof it otherwise holds: name the book this nullifier owns.
        const known = this.lookup(bound);
        return this.finish(s, "id_dup", known ? { book: known } : {});
      }
      return this.finish(s, failure);
    }
    if (body.environment !== undefined && body.environment !== this.opts.environment) return fail("environment");
    if (body.action !== undefined && body.action !== this.opts.action) return fail("action");

    // 200 means at least one item verified: use an item the portal did not fail, with a credential
    // we accept, still valid.
    const portalResults = (Array.isArray(body.results) ? body.results : []) as Array<{
      identifier?: unknown;
      success?: unknown;
    }>;
    const nowS = Math.floor(this.now() / 1000);
    let chosen: { item: Item; credential: string } | null = null;
    for (const it of bound) {
      const pr = portalResults.find((p) => p.identifier === it.identifier);
      if (pr && pr.success === false) continue;
      const credential =
        typeof it.issuer_schema_id === "number" ? SCHEMA_CREDENTIAL[it.issuer_schema_id] : undefined;
      if (!credential) continue;
      if (typeof it.expires_at_min === "number" && it.expires_at_min < nowS) continue; // credential lapsed
      if (!chosen || credential === "Orb") chosen = { item: it, credential };
    }
    if (!chosen) return fail("credential");

    let canonical: string;
    try {
      canonical = Nullifier.fromHex(String(chosen.item.nullifier)).toCanonicalString();
    } catch {
      return fail("no_nullifier");
    }
    const nKey = nullifierKey(this.opts.secret, this.opts.action, canonical);
    const runner = runnerId(this.opts.secret, `${this.opts.action}|${canonical}`);
    const { created, record } = this.opts.store.claimBook(nKey, chosen.credential, runner, nowS);
    if (!created) return this.finish(s, "id_dup", { book: record.book });
    return this.finish(s, null, { book: record.book, credential: record.credential, runner_id: record.runner_id });
  }

  private lookup(items: Item[]): string | undefined {
    for (const it of items) {
      try {
        const canonical = Nullifier.fromHex(String(it.nullifier)).toCanonicalString();
        const rec = this.opts.store.bookFor(nullifierKey(this.opts.secret, this.opts.action, canonical));
        if (rec) return rec.book;
      } catch {
        // not a nullifier
      }
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

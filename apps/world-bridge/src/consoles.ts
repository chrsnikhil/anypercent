/**
 * One console, one person (spec: scout and pivot, section 1).
 *
 * A console names itself by a random id kept in a file in its --state directory. The bridge never
 * stores or logs that id: a console is keyed by HMAC-SHA256(SERVER_SECRET, "console|" + id) and shown
 * as its tag, "C-" plus 4 characters of the book alphabet.
 *
 * - A console is registered as unbound the first time any route names it (GET /console/{id},
 *   /idkit/start, /scout, /hedera/buy).
 * - The first World sign-up on an unbound (or released) console binds it to the book it made (or,
 *   on id_dup that names the book, to that book). On a bound console another person's sign-up is
 *   refused before anything reaches World's portal (idkit.ts, id_taken).
 * - Linking an unbound or released console, and releasing a bound one, are owner ops: each starts
 *   one World session approval of the book's owner with an exact text, checks the approval record as
 *   publish does (same book, the text's hash, unspent, under 24 h), spends it on this op
 *   (`used_for`) and only then changes the binding.
 * - Spending follows the binding: /scout and /hedera/buy with a console need it bound to the buying
 *   book.
 *
 * The bridge has no client authentication: anyone who can reach it can name a console id. Logged:
 * tags, books and outcomes. Never a console id, a jti or an approval id.
 */
import { createHash, createHmac, randomBytes } from "node:crypto";
import { BOOK_RE, StartFailure, type ApprovalProvider } from "./approvals.js";
import type { LsFailure } from "./failures.js";
import { BOOK_CHARS } from "./hmac.js";
import type { ConsoleRecord, ConsoleState, Store } from "./store.js";

/** A console id as consoles send it: a random token from the console's state directory. */
export const CONSOLE_ID_RE = /^[A-Za-z0-9_-]{16,128}$/;
/** A console's tag, as the console shows it and the owner CLIs take it. */
export const CONSOLE_TAG_RE = /^C-[A-HJKMNP-Z2-9]{4}$/;

/** The store key for a console id. The raw id is never stored. */
export function consoleKey(secret: string, id: string): string {
  return createHmac("sha256", secret).update(`console|${id}`).digest("hex");
}

/** A tag candidate for a console key, as bookCandidate derives a book id from a nullifier. */
export function tagCandidate(secret: string, key: string, attempt: number): string {
  const d = createHmac("sha256", secret).update(`tag\u0000${key}\u0000${attempt}`).digest();
  let out = "";
  for (let i = 0; i < 4; i++) out += BOOK_CHARS[d[i] % BOOK_CHARS.length];
  return `C-${out}`;
}

/** What World App shows for a link, word for word. */
export function linkText(tag: string, book: string): string {
  return `Link console ${tag} to record book ${book}: PB on it spends this book's coach budget`;
}

/** What World App shows for a release, word for word. */
export function releaseText(tag: string, book: string): string {
  return `Release console ${tag} from record book ${book}`;
}

export interface ConsoleView {
  tag: string;
  book: string | null;
  state: ConsoleState;
  credential: string | null;
}

export type OpFailure = LsFailure | "already_bound" | "not_bound";

export interface OpView {
  stage: "scan" | "approve" | "apply" | "done";
  ok: boolean | null;
  failure: OpFailure | null;
  data: Record<string, unknown>;
}

/** A request refused before an op starts. */
export class ConsoleOpRefused extends Error {
  constructor(public readonly status: number, public readonly error: string) {
    super(error);
  }
}

export interface ConsolesOptions {
  store: Store;
  secret: string;
  /** The approval provider behind /agentpass/* (null: ops answer 503). */
  approvals: ApprovalProvider | null;
  now?: () => number;
  pollMs?: number;
  /** An unspent approval older than this is ls_expired (24 h). */
  approvalTtlMs?: number;
  /** How long a finished op is kept for GETs (1 h). */
  holdMs?: number;
  log?: (line: string) => void;
}

interface Op {
  id: string;
  op: "link" | "release";
  key: string;
  tag: string;
  book: string;
  action: string;
  approvalId: string;
  view: OpView;
  createdMs: number;
  timer: NodeJS.Timeout | null;
  cancelled: boolean;
}

/** Wait for the approval's verdict at most this long past its own lifetime. */
const OP_GRACE_MS = 30_000;

export class Consoles {
  private readonly ops = new Map<string, Op>();
  private readonly now: () => number;
  private readonly pollMs: number;
  private readonly approvalTtlMs: number;
  private readonly holdMs: number;

  constructor(private readonly opts: ConsolesOptions) {
    this.now = opts.now ?? Date.now;
    this.pollMs = opts.pollMs ?? 500;
    this.approvalTtlMs = opts.approvalTtlMs ?? 24 * 3_600_000;
    this.holdMs = opts.holdMs ?? 3_600_000;
  }

  private nowS(): number {
    return Math.floor(this.now() / 1000);
  }

  /** The console's record, registered as unbound when unseen. The id must match CONSOLE_ID_RE. */
  register(id: string): { key: string; record: ConsoleRecord } {
    if (!CONSOLE_ID_RE.test(id)) throw new ConsoleOpRefused(400, "bad_console");
    const key = consoleKey(this.opts.secret, id);
    const held = this.opts.store.consoleFor(key);
    if (held) return { key, record: held };
    const taken = this.opts.store.consoleTags();
    let tag = "";
    for (let attempt = 0; ; attempt++) {
      tag = tagCandidate(this.opts.secret, key, attempt);
      if (!taken.has(tag)) break;
    }
    const record = this.opts.store.registerConsole(key, tag, this.nowS());
    this.opts.log?.(`console ${tag}: registered (unbound)`);
    return { key, record };
  }

  /** GET /console/{id}: {tag, book, state, credential}; registers an unseen console. */
  view(id: string): ConsoleView {
    const { record } = this.register(id);
    const credential = record.state === "bound" && record.book ? (this.opts.store.recordForBook(record.book)?.credential ?? null) : null;
    return { tag: record.tag, book: record.state === "bound" ? record.book : null, state: record.state, credential };
  }

  /** The book this console is bound to (the sign-up hook asks before the portal), or null. */
  boundTo(id: string): { book: string; tag: string } | null {
    if (!CONSOLE_ID_RE.test(id)) return null;
    const { record } = this.register(id);
    return record.state === "bound" && record.book ? { book: record.book, tag: record.tag } : null;
  }

  /**
   * A sign-up proved this book on this console: bind an unbound or released console to it. Returns
   * the tag when it bound, null otherwise (another binding stands, or no usable console id).
   */
  bindAtSignup(id: string, book: string, by: "signup" | "signin"): string | null {
    if (!CONSOLE_ID_RE.test(id)) return null;
    const { key, record } = this.register(id);
    if (record.state === "bound") return null;
    this.opts.store.setConsole(key, { book, state: "bound", by }, this.nowS());
    this.opts.log?.(`console ${record.tag}: bound to ${book} (${by === "signup" ? "sign-up" : "sign-in: id_dup named the book"})`);
    return record.tag;
  }

  /**
   * Spending follows the binding: may this console spend from this book? Registers an unseen
   * console. An id that is not a console id is refused.
   */
  canSpend(id: string, book: string): { ok: boolean; tag: string | null } {
    if (!CONSOLE_ID_RE.test(id)) return { ok: false, tag: null };
    const { record } = this.register(id);
    return { ok: record.state === "bound" && record.book === book, tag: record.tag };
  }

  /** A console's tag by id (registering it), for log lines. */
  tagOf(id: string): string | null {
    return CONSOLE_ID_RE.test(id) ? this.register(id).record.tag : null;
  }

  // ---- owner ops: link and release, each on one World approval ---------------------------------

  /** POST /console/op. Throws ConsoleOpRefused (400, 404, 409, 503). */
  async startOp(body: Record<string, unknown>): Promise<{ id: string; action: string; approval: { id: string; qr: string; code: string; expires_s: number } }> {
    const { op, console: tag, book } = body;
    if (op !== "link" && op !== "release") throw new ConsoleOpRefused(400, "bad_body");
    if (typeof tag !== "string" || !CONSOLE_TAG_RE.test(tag)) throw new ConsoleOpRefused(400, "bad_body");
    if (book !== undefined && book !== null && (typeof book !== "string" || !BOOK_RE.test(book))) throw new ConsoleOpRefused(400, "bad_body");
    if (op === "link" && typeof book !== "string") throw new ConsoleOpRefused(400, "bad_body");
    const found = this.opts.store.consoleByTag(tag);
    if (!found) throw new ConsoleOpRefused(404, "unknown_console");
    const rec = found.record;
    let target: string;
    if (op === "link") {
      if (rec.state === "bound") throw new ConsoleOpRefused(409, "already_bound");
      target = book as string;
      if (!this.opts.store.recordForBook(target)) throw new ConsoleOpRefused(404, "unknown_book");
    } else {
      if (rec.state !== "bound" || !rec.book) throw new ConsoleOpRefused(409, "not_bound");
      if (typeof book === "string" && book !== rec.book) throw new ConsoleOpRefused(409, "not_bound");
      target = rec.book;
    }
    const approvals = this.opts.approvals;
    if (!approvals) throw new ConsoleOpRefused(503, "approvals_not_configured");
    const action = op === "link" ? linkText(tag, target) : releaseText(tag, target);
    let started;
    try {
      started = await approvals.start(target, action);
    } catch (err) {
      if (err instanceof StartFailure) throw new ConsoleOpRefused(503, "world_unavailable");
      throw err;
    }
    this.prune();
    const o: Op = {
      id: this.newId(),
      op,
      key: found.key,
      tag,
      book: target,
      action,
      approvalId: started.id,
      view: { stage: "scan", ok: null, failure: null, data: {} },
      createdMs: this.now(),
      timer: null,
      cancelled: false,
    };
    this.ops.set(o.id, o);
    this.opts.log?.(`console ${tag}: ${op} to ${target} waits for the owner's World approval`);
    this.schedule(o);
    return { id: o.id, action, approval: { id: started.id, qr: started.qr, code: started.code, expires_s: started.expires_s } };
  }

  opView(id: string): OpView | undefined {
    return this.ops.get(id)?.view;
  }

  /** The owner's Ctrl-C: the approval is cancelled and nothing changes. False: unknown id. */
  cancelOp(id: string): boolean {
    const o = this.ops.get(id);
    if (!o) return false;
    if (o.view.stage === "done" || o.view.stage === "apply") return true;
    o.cancelled = true;
    if (o.timer) clearTimeout(o.timer);
    o.timer = null;
    this.opts.approvals?.cancel(o.approvalId);
    this.finish(o, "ls_denied", "cancelled in the terminal");
    return true;
  }

  stopAll(): void {
    for (const o of this.ops.values()) if (o.timer) clearTimeout(o.timer);
  }

  private newId(): string {
    for (;;) {
      const id = `o-${randomBytes(4).toString("hex")}`;
      if (!this.ops.has(id)) return id;
    }
  }

  private schedule(o: Op): void {
    o.timer = setTimeout(() => {
      o.timer = null;
      this.tick(o);
    }, this.pollMs);
  }

  private finish(o: Op, failure: OpFailure | null, why: string, data: Record<string, unknown> = {}): void {
    if (o.view.stage === "done") return;
    if (o.timer) clearTimeout(o.timer);
    o.timer = null;
    o.view = { stage: "done", ok: failure === null, failure, data };
    this.opts.log?.(`console ${o.tag}: ${o.op} ${o.book}: ${failure ?? "done"} (${why})`);
  }

  private tick(o: Op): void {
    if (o.cancelled || o.view.stage === "done") return;
    const v = this.opts.approvals?.view(o.approvalId);
    if (!v) return this.finish(o, "ls_world_down", "the approval is gone");
    if (v.stage !== "done") {
      o.view = { stage: v.stage, ok: null, failure: null, data: {} };
      if (this.now() - o.createdMs > 300_000 + OP_GRACE_MS) return this.finish(o, "ls_expired", "no answer from World App");
      return this.schedule(o);
    }
    if (!v.ok) return this.finish(o, v.failure ?? "ls_world_down", "the approval did not pass");
    const jti = typeof v.data.jti === "string" ? v.data.jti : "";
    o.view = { stage: "apply", ok: null, failure: null, data: {} };
    this.apply(o, jti);
  }

  /** The approval passed: check its record as publish does, spend it on this op, change the binding. */
  private apply(o: Op, jti: string): void {
    const { store } = this.opts;
    const rec = jti ? store.approvalFor(jti) : undefined;
    if (!rec) return this.finish(o, "ls_expired", "approval unknown to this bridge");
    if (rec.book !== o.book) return this.finish(o, "ls_wrong", "approved for another book");
    if (createHash("sha256").update(o.action).digest("hex") !== rec.action_sha) return this.finish(o, "ls_mismatch", "not the text World App showed");
    if (rec.log_h !== undefined) return this.finish(o, "ls_reused", "approval already spent on a listing");
    const purpose = `console-${o.op}:${o.tag}`;
    if (rec.used_for !== undefined && rec.used_for !== purpose) return this.finish(o, "ls_reused", "approval already spent on another op");
    if (rec.used_for === undefined && this.now() - rec.at * 1000 > this.approvalTtlMs) return this.finish(o, "ls_expired", "approval older than 24 h");

    const now = store.consoleFor(o.key);
    if (!now) return this.finish(o, "ls_world_down", "the console is gone");
    if (o.op === "link" && now.state === "bound") return this.finish(o, "already_bound", `bound to ${now.book} meanwhile`);
    if (o.op === "release" && (now.state !== "bound" || now.book !== o.book)) return this.finish(o, "not_bound", "not bound to this book any more");

    const spent = store.spendApprovalFor(jti, purpose);
    if (spent === "unknown") return this.finish(o, "ls_expired", "approval unknown to this bridge");
    if (spent === "other") return this.finish(o, "ls_reused", "approval already spent");
    const after =
      o.op === "link"
        ? store.setConsole(o.key, { book: o.book, state: "bound", by: "link" }, this.nowS())
        : store.setConsole(o.key, { book: null, state: "released", by: "release" }, this.nowS());
    this.finish(o, null, o.op === "link" ? `linked to ${o.book}, the owner's World approval` : `released from ${o.book}, the owner's World approval`, {
      tag: o.tag,
      book: after?.book ?? null,
      state: after?.state ?? (o.op === "link" ? "bound" : "released"),
    });
  }

  private prune(): void {
    const nowMs = this.now();
    for (const [id, o] of this.ops) if (o.view.stage === "done" && nowMs - o.createdMs > this.holdMs) this.ops.delete(id);
  }
}

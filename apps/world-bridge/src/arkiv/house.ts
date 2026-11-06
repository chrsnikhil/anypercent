/**
 * The house's BOT ghosts (spec: scout and pivot, section 2; console-owned records). A batch of logs
 * made by a program (games/marinedrive/dev/ghostgen.py: the route bot, slowed down on purpose in
 * chosen laps) is put on the board as BOT runs with listings that pay the house account, only after
 * the house owner's World approval of exactly that batch. The house is a writer like any console:
 * its own Arkiv wallet (HOUSE_ARKIV_KEY, never the checker's key) creates the runs and listings, and
 * the checker then stamps each run, so every reader ranks them by the same rule as a console's.
 *
 *   POST /house/batch   {game, logs: [base64], gen?: [...]}: every log through the checker's header
 *                       checks, the replay tool and the splits tool (splits are required here), then
 *                       the stamp dedupe (a log a checker stamp already names refuses the whole
 *                       batch) and the duplicates check. Answers the batch id, labels BOT-<letter><n>
 *                       and the exact text World App will show. The logs are held in memory for 1 h;
 *                       the store keeps labels, log hashes and status, never the logs.
 *   POST /house/publish {batch} -> {id: "h-...", action, approval}: starts the approval of
 *                       HOUSE_OWNER_BOOK through the configured provider.
 *   GET  /house/publish/{id}    {stage: scan | approve | write | done, ok, failure, data}
 *
 * Once the approval is recorded it is checked as publish checks one (same book, the text's hash,
 * unspent, under 24 h) and spent with used_for = "house:<batch>". Then the HOUSE message goes to the
 * market topic (10 s for its receipt; without it the batch goes on with no `hcs`), the rows go to
 * Arkiv from the house wallet in one transaction of 2N creates (run, listing, run, ...), split into
 * transactions of HOUSE_TX_PAIRS pairs when Arkiv refuses that size, and then the checker stamps
 * every run in one more transaction (split the same way if refused). A failed write keeps the
 * approval spent on this batch, so a retry of the same batch finishes it without a new approval:
 * runs it finds stamped under their own BOT labels count as done, house-wallet runs it finds under
 * their own labels are stamped, and only what is missing is written. A batch the checker wrote
 * itself before console-owned records (written, no stamps) is not on any board any more: it is
 * published again from the house wallet, after a new approval.
 *
 * A house row is never HUMAN: `human` false, no book, no credential, `label` BOT-..., `pay_to` the
 * house. The row builders take no such fields, so a house row with HUMAN, a book or a credential
 * cannot be built.
 *
 * Errors are {"error", "detail"} (these routes are for the owner's CLI, not the console). Logged: the
 * batch, labels, times, keys, tx hashes and failure names. Never a log, a jti or a key.
 */
import { createHash, randomBytes } from "node:crypto";
import { StartFailure, type ApprovalProvider } from "../approvals.js";
import type { LsFailure } from "../failures.js";
import { houseMessage, seqNumber, type HouseMessage } from "../hedera/messages.js";
import { hashscan, shortSdkError, type HederaPort } from "../hedera/net.js";
import { runnerId } from "../hmac.js";
import type { HouseResult, Store } from "../store.js";
import { ArkivError, splitValues, stampValues, type ArkivPort, type CreateSpec, type HousePair, type ListingValues, type RunRow, type RunValues, type StampRow, type StampValues } from "./client.js";
import { CheckerError, LOG_MAX, LOG_MIN, parseHeader, splitsVerdict, verdict, type CheckerPort, type SplitsPort } from "./checker.js";
import { encryptGhost, sha256Hex } from "./ghost.js";
import { fmtTime, priceDec, priceText } from "./publish.js";
import { GAMES, LISTING_DAYS, LISTING_FLAGS, RUN_FLAGS, STAMP_FLAGS } from "./schema.js";

/** The text World App shows for a batch, word for word (at most 160 characters). */
export function houseText(batch: string, n: number, title: string, priceC: number, houseId: string): string {
  return `Publish BOT batch ${batch}: ${n} ${title} ghosts made by a program, ${priceText(priceC)} USDC each to house ${houseId} on the public board, never HUMAN`;
}

/** The batch id: sha256 of the sorted log hashes joined by ",", first 6 hex. */
export function batchId(logHs: readonly string[]): string {
  return createHash("sha256").update([...logHs].sort().join(",")).digest("hex").slice(0, 6);
}

/** The approval's purpose once spent on a batch. */
export const housePurpose = (batch: string) => `house:${batch}`;

/** A BOT run's runner id: an HMAC of its label (never a person's). */
export const houseRunner = (secret: string, label: string) => runnerId(secret, `house|${label}`);

export const MAX_HOUSE_BODY = 192 * 1024;
export const HOUSE_HOLD_S = 3600;
export const HOUSE_ACTION_MAX = 160;

/** What a BOT run row is built from. No `human`, `book` or `credential`: a house row has none. */
export interface HouseRunInput {
  game: string;
  season: number;
  rules: number;
  frames: number;
  log_h: string;
  label: string;
  runner: string;
  tool: string;
  log_enc: Uint8Array;
  splits: readonly number[];
  gen?: string;
}

/** A BOT run row: never HUMAN, no book, no credential. */
export function houseRun(i: HouseRunInput): RunValues {
  return {
    game: i.game,
    title: GAMES[i.game],
    season: i.season,
    rules: i.rules,
    frames: i.frames,
    log_h: i.log_h,
    runner: i.runner,
    label: i.label,
    human: false,
    tool: i.tool,
    log_enc: i.log_enc,
    ...splitValues(i.splits),
    ...(i.gen ? { gen: i.gen } : {}),
  };
}

export interface HouseListingInput {
  game: string;
  season: number;
  frames: number;
  log_h: string;
  priceC: number;
  /** The run's runner id. */
  seller: string;
  label: string;
  /** HEDERA_HOUSE_ID. */
  pay_to: string;
  hcs?: string;
}

/** A BOT listing: the label, never a book, never HUMAN, paying the house. */
export function houseListing(i: HouseListingInput): ListingValues {
  return {
    game: i.game,
    season: i.season,
    frames: i.frames,
    log_h: i.log_h,
    price: priceDec(i.priceC),
    seller: i.seller,
    label: i.label,
    human: false,
    pay_to: i.pay_to,
    ...(i.hcs ? { hcs: i.hcs } : {}),
  };
}

/** A request refused before a job starts: {error, detail}. */
export class HouseRefused extends Error {
  constructor(public readonly status: number, public readonly error: string, public readonly detail?: string) {
    super(error);
  }
}

export type HouseFailure = LsFailure | "ls_copied" | "ls_publish_fail";

export interface HouseView {
  stage: "scan" | "approve" | "write" | "done";
  ok: boolean | null;
  failure: HouseFailure | null;
  data: Record<string, unknown>;
}

export interface HouseOptions {
  store: Store;
  /** Reads, the house wallet's writes (writeHouse) and the checker's stamps (writeStamps). */
  arkiv: ArkivPort;
  checker: CheckerPort;
  splits: SplitsPort | null;
  approvals: ApprovalProvider | null;
  /** The market topic for the HOUSE message (null: no message, the rows carry no `hcs`). */
  hedera: HederaPort | null;
  topic: string;
  houseId: string;
  ownerBook: string;
  maxBatch: number;
  txPairs: number;
  season: number;
  runExpiry: Date;
  priceC: number;
  ghostSecret: string;
  /** SERVER_SECRET (runner ids). */
  secret: string;
  /** What keeps house batches off, by .env name (houseProblems). */
  problems: () => string[];
  /** The Arkiv write gate (config, chain, a funded checker). */
  gate?: () => string | null;
  explorer?: { tx(hash: string | null): string | null } | null;
  now?: () => number;
  pollMs?: number;
  /** The HOUSE message's receipt (10 s). */
  hcsTimeoutMs?: number;
  /** One Arkiv transaction (90 s); the queue waits it out after that. */
  writeTimeoutMs?: number;
  approvalTtlMs?: number;
  log?: (line: string) => void;
}

interface HeldLog {
  log: Uint8Array;
  log_h: string;
  rules: number;
  frames: number;
  splits: number[];
  /** The replay's final hash as the tool printed it (the stamp's `final_hash`). */
  finalHash: number | null;
  gen?: string;
}

interface Held {
  batch: string;
  game: string;
  title: string;
  logs: HeldLog[];
  tool: string;
  action: string;
  expiresMs: number;
}

interface Job {
  id: string;
  batch: string;
  approvalId: string | null;
  view: HouseView;
  createdMs: number;
  timer: NodeJS.Timeout | null;
  cancelled: boolean;
  running: boolean;
}

const B64 = /^[A-Za-z0-9+/]*={0,2}$/;
const GEN_RE = /^[\x20-\x7e]{1,80}$/;

function within<T>(p: Promise<T>, ms: number): Promise<T | "timeout"> {
  let timer: NodeJS.Timeout | undefined;
  const t = new Promise<"timeout">((ok) => {
    timer = setTimeout(() => ok("timeout"), ms);
  });
  return Promise.race([p, t]).finally(() => clearTimeout(timer));
}

/** A result written since console-owned records: it carries the stamps (maybe none yet). One from before has none. */
const houseEra = (r: HouseResult | undefined): r is HouseResult & { stamps: string[] } => !!r && Array.isArray(r.stamps);

export class HouseService {
  private readonly held = new Map<string, Held>();
  private readonly jobs = new Map<string, Job>();
  private readonly now: () => number;
  private readonly pollMs: number;
  private readonly hcsTimeoutMs: number;
  private readonly writeTimeoutMs: number;
  private readonly approvalTtlMs: number;

  constructor(private readonly opts: HouseOptions) {
    this.now = opts.now ?? Date.now;
    this.pollMs = opts.pollMs ?? 500;
    this.hcsTimeoutMs = opts.hcsTimeoutMs ?? 10_000;
    this.writeTimeoutMs = opts.writeTimeoutMs ?? 90_000;
    this.approvalTtlMs = opts.approvalTtlMs ?? 24 * 3_600_000;
  }

  private log(line: string): void {
    this.opts.log?.(`house ${line}`);
  }

  private refuseIfOff(): void {
    const problems = this.opts.problems();
    if (problems.length) throw new HouseRefused(503, "house_not_configured", `set: ${problems.join(", ")}`);
    if (!this.opts.arkiv.house) throw new HouseRefused(503, "house_not_configured", "set: HOUSE_ARKIV_KEY");
    const gate = this.opts.gate?.() ?? null;
    if (gate) throw new HouseRefused(503, "house_not_configured", gate);
  }

  // ---- staging ---------------------------------------------------------------------------------

  /** POST /house/batch. Throws HouseRefused (400, 409, 503). */
  async stage(raw: Record<string, unknown>): Promise<Record<string, unknown>> {
    this.refuseIfOff();
    const { game, logs, gen } = raw;
    const bad = (detail: string) => new HouseRefused(400, "bad_body", detail);
    if (typeof game !== "string" || !GAMES[game]) throw bad("game must be an arcade id");
    if (!this.opts.splits || !this.opts.splits.games.includes(game)) throw bad(`no lap splits for ${game}`);
    if (!Array.isArray(logs) || logs.length < 1 || logs.length > this.opts.maxBatch) throw bad(`logs: 1 to ${this.opts.maxBatch}`);
    if (gen !== undefined && gen !== null && (!Array.isArray(gen) || gen.length !== logs.length || !gen.every((g) => typeof g === "string" && GEN_RE.test(g)))) {
      throw bad("gen: one printable string (at most 80 characters) per log");
    }
    const decoded: Array<{ log: Uint8Array; log_h: string; rules: number; gen?: string }> = [];
    const seen = new Map<string, number>();
    logs.forEach((text, i) => {
      if (typeof text !== "string" || !B64.test(text) || text.length % 4 !== 0) throw bad(`log ${i + 1} is not base64`);
      const log = Uint8Array.from(Buffer.from(text, "base64"));
      if (log.length < LOG_MIN || log.length > LOG_MAX) throw bad(`log ${i + 1} is not 32 B to 64 KiB`);
      const header = parseHeader(log);
      if (!header) throw bad(`log ${i + 1} is not a plain .acl log`);
      if (header.game !== game) throw bad(`log ${i + 1} is ${header.game}'s, not ${game}'s`);
      const logH = sha256Hex(log);
      const first = seen.get(logH);
      if (first !== undefined) throw new HouseRefused(409, "duplicate", `log ${i + 1} is log ${first + 1} again`);
      seen.set(logH, i);
      decoded.push({ log, log_h: logH, rules: header.rules, ...(Array.isArray(gen) ? { gen: gen[i] as string } : {}) });
    });

    // The checker's replay and the splits tool, on every log; splits are required here.
    const { checker } = this.opts;
    const splitsPort = this.opts.splits;
    const checked: HeldLog[] = [];
    for (const [i, d] of decoded.entries()) {
      let frames: number;
      let finalHash: number | undefined;
      try {
        const r = await checker.replay(game, d.log_h, d.log);
        const v = verdict(game, r);
        if (!v.ok) throw new HouseRefused(409, "replay_refused", `log ${i + 1}: ${v.why}`);
        frames = v.frames;
        finalHash = r.final_hash;
      } catch (err) {
        if (err instanceof HouseRefused) throw err;
        throw new HouseRefused(409, "replay_refused", `log ${i + 1}: replay tool: ${err instanceof CheckerError ? err.message : "error"}`);
      }
      let splits: number[];
      try {
        const v = splitsVerdict(await splitsPort.splits(game, d.log_h, d.log), frames, finalHash);
        if (!v.ok) throw new HouseRefused(409, "replay_refused", `log ${i + 1}: splits: ${v.why}`);
        splits = v.splits;
      } catch (err) {
        if (err instanceof HouseRefused) throw err;
        throw new HouseRefused(409, "replay_refused", `log ${i + 1}: splits tool: ${err instanceof CheckerError ? err.message : "error"}`);
      }
      const fh = typeof finalHash === "number" && Number.isSafeInteger(finalHash) && finalHash >= 0 ? finalHash : null;
      checked.push({ log: d.log, log_h: d.log_h, rules: d.rules, frames, splits, finalHash: fh, ...(d.gen ? { gen: d.gen } : {}) });
    }
    let tool: string;
    try {
      tool = await checker.toolTag(game);
    } catch {
      throw new HouseRefused(409, "replay_refused", "could not hash the replay tool");
    }

    const batch = batchId(checked.map((c) => c.log_h));
    const known = this.opts.store.houseBatch(batch);
    // The stamp dedupe on each: a log a checker stamp already names refuses the whole batch (unless it is this batch's own row).
    for (const [i, c] of checked.entries()) {
      let existing: StampRow | null;
      try {
        existing = await this.opts.arkiv.stampByLogHash(c.log_h);
      } catch (err) {
        throw new HouseRefused(503, "arkiv_unavailable", err instanceof ArkivError ? err.message : "read failed");
      }
      if (existing && !(known && this.ownRow(known, c.log_h, existing))) throw new HouseRefused(409, "on_board", `log ${i + 1} is run ${existing.run}`);
    }

    const nowS = Math.floor(this.now() / 1000);
    const rec = this.opts.store.stageHouseBatch(
      batch,
      game,
      checked.map((c) => c.log_h),
      nowS,
      (letter) => checked.map((_, i) => `BOT-${letter}${i + 1}`),
    );
    const title = GAMES[game];
    const action = houseText(batch, checked.length, title, this.opts.priceC, this.opts.houseId);
    if (action.length > HOUSE_ACTION_MAX) throw new HouseRefused(400, "action_too_long", `${action.length} characters`);
    // Labels follow the batch's first staging, whatever order the logs come in now.
    const ordered = rec.log_hs.map((h) => checked.find((c) => c.log_h === h) as HeldLog);
    this.held.set(batch, { batch, game, title, logs: ordered, tool, action, expiresMs: this.now() + HOUSE_HOLD_S * 1000 });
    this.prune();
    this.log(`batch ${batch} staged: ${ordered.map((c, i) => `${rec.labels[i]} ${fmtTime(c.frames)}`).join(", ")} (replay and splits ok)`);
    return {
      batch,
      game,
      title,
      pay_to: this.opts.houseId,
      price: priceText(this.opts.priceC),
      action,
      rows: ordered.map((c, i) => ({ label: rec.labels[i], frames: c.frames, time: fmtTime(c.frames), splits: c.splits, log_h: c.log_h })),
      expires_s: HOUSE_HOLD_S,
    };
  }

  /**
   * A row on Arkiv that this batch itself wrote: its own BOT label, never HUMAN, no book, and (a
   * stamp) naming the house wallet as its console, or (a run) created by the house wallet.
   */
  private ownRow(rec: { labels: string[]; log_hs: string[] }, logH: string, row: { label?: string; book?: string; human: boolean; console?: string; creator?: string | null }): boolean {
    const i = rec.log_hs.indexOf(logH);
    const house = this.opts.arkiv.house;
    const wallet = "console" in row && row.console !== undefined ? row.console : row.creator;
    return i >= 0 && row.label === rec.labels[i] && row.human === false && row.book === undefined && !!house && (wallet ?? "").toLowerCase() === house;
  }

  // ---- publishing --------------------------------------------------------------------------------

  /** POST /house/publish {batch}. Throws HouseRefused (400, 404, 503). */
  async publish(raw: Record<string, unknown>): Promise<{ id: string; action: string; approval: { id: string; qr: string; code: string; expires_s: number } | null }> {
    const { batch } = raw;
    if (typeof batch !== "string" || !/^[0-9a-f]{6}$/.test(batch)) throw new HouseRefused(400, "bad_body", "batch: 6 hex");
    this.refuseIfOff();
    const held = this.held.get(batch);
    const rec = this.opts.store.houseBatch(batch);
    if (!held || held.expiresMs < this.now() || !rec) throw new HouseRefused(404, "unknown_batch", "stage it with POST /house/batch first (logs are held 1 h)");
    for (const j of this.jobs.values()) if (j.batch === batch && j.view.stage !== "done") return { id: j.id, action: held.action, approval: null };

    const job: Job = { id: this.newId(), batch, approvalId: null, view: { stage: "scan", ok: null, failure: null, data: {} }, createdMs: this.now(), timer: null, cancelled: false, running: false };
    // Approved (or written) since console-owned records: a retry finishes it without a new approval.
    // A batch the checker wrote itself before (no stamps) is on no board: the owner approves it again.
    if (rec.status === "approved" || (rec.status === "written" && houseEra(rec.result))) {
      this.jobs.set(job.id, job);
      this.log(`batch ${batch}: approved before, ${rec.status === "written" ? "already written" : "writing again"} (no new approval)`);
      void this.write(job);
      return { id: job.id, action: held.action, approval: null };
    }
    const approvals = this.opts.approvals;
    if (!approvals) throw new HouseRefused(503, "approvals_not_configured");
    let started;
    try {
      started = await approvals.start(this.opts.ownerBook, held.action);
    } catch (err) {
      if (err instanceof StartFailure) throw new HouseRefused(503, "world_unavailable");
      throw err;
    }
    job.approvalId = started.id;
    this.jobs.set(job.id, job);
    this.log(`batch ${batch}: waiting for ${this.opts.ownerBook}'s World approval`);
    this.schedule(job);
    return { id: job.id, action: held.action, approval: { id: started.id, qr: started.qr, code: started.code, expires_s: started.expires_s } };
  }

  view(id: string): HouseView | undefined {
    return this.jobs.get(id)?.view;
  }

  /** Ctrl-C in the owner's terminal: before the write, the approval is cancelled and nothing is written. */
  cancel(id: string): boolean {
    const j = this.jobs.get(id);
    if (!j) return false;
    if (j.view.stage === "done" || j.view.stage === "write" || j.running) return true;
    j.cancelled = true;
    if (j.timer) clearTimeout(j.timer);
    j.timer = null;
    if (j.approvalId) this.opts.approvals?.cancel(j.approvalId);
    this.fail(j, "ls_denied", "cancelled in the terminal");
    return true;
  }

  stopAll(): void {
    for (const j of this.jobs.values()) if (j.timer) clearTimeout(j.timer);
  }

  private newId(): string {
    for (;;) {
      const id = `h-${randomBytes(4).toString("hex")}`;
      if (!this.jobs.has(id)) return id;
    }
  }

  private schedule(j: Job): void {
    j.timer = setTimeout(() => {
      j.timer = null;
      this.tick(j);
    }, this.pollMs);
  }

  private fail(j: Job, failure: HouseFailure, why: string): void {
    if (j.view.stage === "done") return;
    if (j.timer) clearTimeout(j.timer);
    j.timer = null;
    j.view = { stage: "done", ok: false, failure, data: {} };
    this.log(`batch ${j.batch}: ${failure} (${why})`);
  }

  private tick(j: Job): void {
    if (j.cancelled || j.view.stage === "done" || !j.approvalId) return;
    const v = this.opts.approvals?.view(j.approvalId);
    if (!v) return this.fail(j, "ls_world_down", "the approval is gone");
    if (v.stage !== "done") {
      j.view = { stage: v.stage, ok: null, failure: null, data: {} };
      if (this.now() - j.createdMs > 330_000) return this.fail(j, "ls_expired", "no answer from World App");
      return this.schedule(j);
    }
    if (!v.ok) return this.fail(j, v.failure ?? "ls_world_down", "the approval did not pass");
    const jti = typeof v.data.jti === "string" ? v.data.jti : "";
    const why = this.spend(j, jti);
    if (why) return this.fail(j, why.failure, why.why);
    void this.write(j);
  }

  /** The approval's record, checked as publish checks one, then spent on this batch. Null: spent. */
  private spend(j: Job, jti: string): { failure: HouseFailure; why: string } | null {
    const { store } = this.opts;
    const held = this.held.get(j.batch);
    const rec = jti ? store.approvalFor(jti) : undefined;
    if (!rec) return { failure: "ls_expired", why: "approval unknown to this bridge" };
    if (rec.book !== this.opts.ownerBook) return { failure: "ls_wrong", why: `approved by ${rec.book}, not HOUSE_OWNER_BOOK` };
    if (!held || createHash("sha256").update(held.action).digest("hex") !== rec.action_sha) return { failure: "ls_mismatch", why: "not the text World App showed" };
    if (rec.log_h !== undefined) return { failure: "ls_reused", why: "approval already spent on a listing" };
    const purpose = housePurpose(j.batch);
    if (rec.used_for !== undefined && rec.used_for !== purpose) return { failure: "ls_reused", why: "approval already spent on another op" };
    if (rec.used_for === undefined && this.now() - rec.at * 1000 > this.approvalTtlMs) return { failure: "ls_expired", why: "approval older than 24 h" };
    const spent = store.spendApprovalFor(jti, purpose);
    if (spent === "unknown") return { failure: "ls_expired", why: "approval unknown to this bridge" };
    if (spent === "other") return { failure: "ls_reused", why: "approval already spent" };
    store.updateHouseBatch(j.batch, { status: "approved" });
    this.log(`batch ${j.batch}: approved by ${rec.book} in World App (approval spent on this batch)`);
    return null;
  }

  // ---- the write -----------------------------------------------------------------------------------

  private async write(j: Job): Promise<void> {
    j.running = true;
    try {
      await this.writeBatch(j);
    } catch (err) {
      this.fail(j, "ls_publish_fail", `internal: ${(err as Error)?.name ?? "error"}`);
    } finally {
      j.running = false;
    }
  }

  /** One house run as written (and as its stamp copies it). */
  private runValues(held: Held, i: number, label: string): RunValues {
    const l = held.logs[i];
    return houseRun({
      game: held.game,
      season: this.opts.season,
      rules: l.rules,
      frames: l.frames,
      log_h: l.log_h,
      label,
      runner: houseRunner(this.opts.secret, label),
      tool: held.tool,
      log_enc: encryptGhost(this.opts.ghostSecret, l.log_h, l.log),
      splits: l.splits,
      ...(l.gen ? { gen: l.gen } : {}),
    });
  }

  private async writeBatch(j: Job): Promise<void> {
    const { store, arkiv } = this.opts;
    j.view = { stage: "write", ok: null, failure: null, data: {} };
    const held = this.held.get(j.batch);
    const rec = store.houseBatch(j.batch);
    if (!held || !rec) return this.fail(j, "ls_publish_fail", "the batch's logs are no longer held: stage it again");
    if (rec.status === "written" && houseEra(rec.result)) return this.done(j, rec.result);
    const house = arkiv.house;
    if (!house) return this.fail(j, "ls_publish_fail", "no house wallet (HOUSE_ARKIV_KEY)");

    const hcs = await this.houseMessage(j.batch, held);
    const expiry = { kind: "atDate", date: this.opts.runExpiry, atLeastDays: 1 } as const;

    // What is on Arkiv already: a stamp of this log (this batch's own: done; anyone else's: a copy),
    // else a house-wallet run of it under its own label (written, not stamped yet).
    const n = held.logs.length;
    const runs: Array<string | null> = Array(n).fill(null);
    const listings: Array<string | null> = Array(n).fill(null);
    const stamps: Array<string | null> = Array(n).fill(null);
    for (const [i, l] of held.logs.entries()) {
      try {
        const st = await arkiv.stampByLogHash(l.log_h);
        if (st) {
          if (!this.ownRow(rec, l.log_h, st)) return this.fail(j, "ls_copied", `${rec.labels[i]}'s log is already on the board as run ${st.run}`);
          runs[i] = st.run;
          stamps[i] = st.key;
          listings[i] = (await arkiv.liveListingFor(st.run, house))?.key ?? null;
          continue;
        }
        const r: RunRow | null = await arkiv.runByLogHash(l.log_h, house);
        if (r) {
          if (!this.ownRow(rec, l.log_h, r) || Number(r.frames) !== l.frames) {
            return this.fail(j, "ls_publish_fail", `the house wallet has another run of ${rec.labels[i]}'s log (${r.key})`);
          }
          runs[i] = r.key;
          listings[i] = (await arkiv.liveListingFor(r.key, house))?.key ?? null;
        }
      } catch (err) {
        return this.fail(j, "ls_publish_fail", `Arkiv: ${err instanceof ArkivError ? err.message : "read failed"}`);
      }
    }

    const prior = houseEra(rec.result) ? rec.result : undefined;
    const txs = [...(prior?.txs ?? [])];
    const stampTxs = [...(prior?.stamp_txs ?? [])];
    const partial = (): HouseResult => ({
      runs: runs.filter((r): r is string => r !== null),
      listings: listings.filter((l): l is string => l !== null),
      txs,
      stamps: stamps.filter((s): s is string => s !== null),
      stamp_txs: stampTxs,
    });

    // 1. The rows, from the house wallet.
    const toWrite = held.logs.map((_, i) => i).filter((i) => runs[i] === null);
    const pairs = (items: number[]): HousePair[] =>
      items.map((i) => {
        const label = rec.labels[i];
        const run: CreateSpec<RunValues> = { values: this.runValues(held, i, label), flags: { ...RUN_FLAGS }, expiry };
        const l = held.logs[i];
        const listing: CreateSpec<ListingValues> = {
          values: houseListing({
            game: held.game,
            season: this.opts.season,
            frames: l.frames,
            log_h: l.log_h,
            priceC: this.opts.priceC,
            seller: run.values.runner,
            label,
            pay_to: this.opts.houseId,
            ...(hcs?.seq !== null && hcs?.seq !== undefined ? { hcs: `${hcs.topic}/${hcs.seq}` } : {}),
          }),
          flags: { ...LISTING_FLAGS },
          expiry: { kind: "days", days: LISTING_DAYS },
        };
        return { run, listing };
      });
    const rowsOut = await this.chunked(j, "rows", toWrite, async (items) => {
      const w = await arkiv.writeHouse(pairs(items));
      items.forEach((i, k) => {
        runs[i] = w.runs[k];
        listings[i] = w.listings[k];
      });
      txs.push(w.tx);
      this.log(`batch ${j.batch}: ${items.map((i) => rec.labels[i]).join(", ")} written by the house wallet, tx ${w.tx}`);
    });
    if (rowsOut) {
      store.updateHouseBatch(j.batch, { result: partial() });
      return this.fail(j, "ls_publish_fail", `Arkiv write: ${rowsOut}`);
    }
    if (runs.some((r) => r === null)) return this.fail(j, "ls_publish_fail", "not every row was written");

    // 2. The stamps, from the checker: one per run, naming the house wallet, the run's columns copied.
    const toStamp = held.logs.map((_, i) => i).filter((i) => stamps[i] === null);
    const stampsOut = await this.chunked(j, "stamps", toStamp, async (items) => {
      const specs: CreateSpec<StampValues>[] = items.map((i) => ({
        values: stampValues(this.runValues(held, i, rec.labels[i]), runs[i] as string, house, held.logs[i].finalHash, held.tool),
        flags: { ...STAMP_FLAGS },
        expiry,
      }));
      const w = await arkiv.writeStamps(specs);
      items.forEach((i, k) => (stamps[i] = w.stamps[k]));
      stampTxs.push(w.tx);
      this.log(`batch ${j.batch}: ${items.map((i) => rec.labels[i]).join(", ")} stamped by the checker, tx ${w.tx}`);
    });
    if (stampsOut) {
      store.updateHouseBatch(j.batch, { result: partial() });
      return this.fail(j, "ls_publish_fail", `stamp write: ${stampsOut} (a retry of this batch stamps the rows it finds)`);
    }
    const result: HouseResult = { runs: runs as string[], listings: listings.map((l) => l ?? ""), txs, stamps: stamps as string[], stamp_txs: stampTxs };
    store.updateHouseBatch(j.batch, { status: "written", result });
    this.done(j, result);
  }

  /**
   * One write of all `items` in a transaction; when Arkiv refuses that size, again in chunks of
   * HOUSE_TX_PAIRS. Null when every item went out, else why not.
   */
  private async chunked(j: Job, what: string, items: number[], write: (items: number[]) => Promise<void>): Promise<string | null> {
    if (items.length === 0) return null;
    const once = async (part: number[]): Promise<"ok" | { refused: string } | { failed: string }> => {
      const p = write(part);
      const out = await within(p.then(() => ({ ok: true as const }), (err: unknown) => ({ err })), this.writeTimeoutMs);
      if (out === "timeout") {
        // A retry of this batch finds what landed on Arkiv by its own labels.
        void p.then(
          () => this.log(`batch ${j.batch}: a write of ${what} landed after the timeout (retry the batch to finish it)`),
          () => undefined,
        );
        return { failed: "Arkiv write timed out (a retry of this batch finds what landed)" };
      }
      if ("err" in out) {
        const why = out.err instanceof ArkivError ? out.err.message : "write failed";
        return /timed? ?out|timeout/i.test(why) ? { failed: why } : { refused: why };
      }
      return "ok";
    };
    const first = await once(items);
    if (first === "ok") return null;
    if ("failed" in first) return first.failed;
    const size = Math.max(1, this.opts.txPairs);
    if (items.length <= size) return first.refused;
    this.log(`batch ${j.batch}: one transaction of ${what} for ${items.length} runs was refused (${first.refused}); splitting into ${size} pairs a transaction`);
    for (let k = 0; k < items.length; k += size) {
      const r = await once(items.slice(k, k + size));
      if (r !== "ok") return "failed" in r ? r.failed : r.refused;
    }
    return null;
  }

  /** The HOUSE message on the market topic (reused when an earlier try landed). Null: none. */
  private async houseMessage(batch: string, held: Held): Promise<{ topic: string; seq: number | null; tx: string } | null> {
    const { hedera, topic, store } = this.opts;
    if (!hedera || !/^0\.0\.\d+$/.test(topic)) return null;
    const rec = store.houseBatch(batch);
    if (rec?.hcs?.seq) return { topic: rec.hcs.topic, seq: seqNumber(rec.hcs.seq), tx: rec.hcs.tx };
    if (rec?.hcs?.tx) {
      const landed = await within(hedera.receiptOf(rec.hcs.tx), this.hcsTimeoutMs).catch(() => null);
      if (landed && landed !== "timeout") {
        store.updateHouseBatch(batch, { hcs: { ...rec.hcs, seq: landed.seq } });
        return { topic: rec.hcs.topic, seq: seqNumber(landed.seq), tx: rec.hcs.tx };
      }
    }
    let bytes: Uint8Array;
    const m: HouseMessage = {
      batch,
      book: this.opts.ownerBook,
      game: held.game,
      n: held.logs.length,
      price: priceText(this.opts.priceC),
      pay_to: this.opts.houseId,
      action: held.action,
    };
    try {
      bytes = houseMessage(m);
    } catch {
      this.log(`batch ${batch}: HOUSE message would not fit one chunk; going on without hcs`);
      return null;
    }
    const accepted = await within(hedera.submit(topic, bytes), this.hcsTimeoutMs).catch((err: unknown) => ({ err }));
    if (accepted === "timeout" || "err" in accepted) {
      this.log(`batch ${batch}: HOUSE message not accepted (${accepted === "timeout" ? "timed out" : shortSdkError(accepted.err)}); going on without hcs`);
      return null;
    }
    store.updateHouseBatch(batch, { hcs: { topic, tx: accepted.tx } });
    const receipt = await within(accepted.receipt, this.hcsTimeoutMs).catch(() => null);
    if (!receipt || receipt === "timeout") {
      this.log(`batch ${batch}: HOUSE message ${accepted.tx} gave no receipt within 10 s; going on without hcs`);
      return null;
    }
    store.updateHouseBatch(batch, { hcs: { topic, tx: accepted.tx, seq: receipt.seq } });
    this.log(`batch ${batch}: HOUSE #${receipt.seq} on ${topic}, tx ${accepted.tx} ${hashscan.tx(accepted.tx)}`);
    return { topic, seq: seqNumber(receipt.seq), tx: accepted.tx };
  }

  private done(j: Job, result: HouseResult): void {
    const rec = this.opts.store.houseBatch(j.batch);
    const h = rec?.hcs?.seq ? { topic: rec.hcs.topic, seq: seqNumber(rec.hcs.seq), tx: rec.hcs.tx, hashscan: hashscan.tx(rec.hcs.tx) } : null;
    const ex = this.opts.explorer;
    const stampTxs = result.stamp_txs ?? [];
    j.view = {
      stage: "done",
      ok: true,
      failure: null,
      data: {
        batch: j.batch,
        runs: result.runs,
        listings: result.listings,
        stamps: result.stamps ?? [],
        txs: result.txs,
        stamp_txs: stampTxs,
        explorer: { txs: result.txs.map((t) => ex?.tx(t) ?? null), stamp_txs: stampTxs.map((t) => ex?.tx(t) ?? null) },
        hcs: h,
      },
    };
    this.log(`batch ${j.batch}: done: ${result.runs.length} BOT runs and listings by the house wallet ${this.opts.arkiv.house ?? ""} paying ${this.opts.houseId}, stamped by the checker; ${result.txs.length + stampTxs.length} transaction(s)`);
  }

  private prune(): void {
    const nowMs = this.now();
    for (const [b, h] of this.held) if (h.expiresMs < nowMs) this.held.delete(b);
    for (const [id, j] of this.jobs) if (j.view.stage === "done" && nowMs - j.createdMs > HOUSE_HOLD_S * 1000) this.jobs.delete(id);
  }
}

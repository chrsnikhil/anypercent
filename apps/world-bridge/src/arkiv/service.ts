/**
 * The Arkiv half of the bridge's HTTP contract (spec: HTTP contract), wired from what is configured:
 *
 *   GET  /arkiv/config        chain id, public RPC, explorer, checker, season, schemas, price, listing days
 *   POST /arkiv/publish       a World-approved listing -> {id, expires_s}        (publish.ts)
 *   GET  /arkiv/publish/{id}  {stage, ok, failure, data}; at stage "sign", data.issue is what the
 *                             console signs from its own wallet
 *   POST /arkiv/publish/{id}/written  {tx, run, listing}: the console's transaction -> {ok: true};
 *                             the job then checks its entities, stamps and reaches done
 *   POST /arkiv/ghost         {run, receipt} -> {log, log_h}: a listed ghost, decrypted here
 *   GET  /board, /board/snapshot.json   the web board and its fallback snapshot
 *
 * and three /health fields: "arkiv" (the last probe saw eth_chainId == ARKIV_CHAIN_ID),
 * "arkiv_writes" (config complete, right chain, checker funded) and "checker".
 *
 * Errors are non-2xx {"error", "failure"}; the failure is ls_publish_fail on the publish routes and
 * buy_load_fail on /arkiv/ghost.
 */
import { readFileSync } from "node:fs";
import { ARKIV_EXPLORER, ARKIV_EXPLORER_ENTITY, ARKIV_EXPLORER_TX, GHOST_SECRET_RE, type ExplorerConfig } from "../config.js";
import { ArkivError, type ArkivPort } from "./client.js";
import { decryptGhost, sha256Hex } from "./ghost.js";
import type { PaymentCheck } from "./payments.js";
import { PublishRefused, priceText, type Publisher, type PublishView, type WriteGate } from "./publish.js";
import { KEY_RE } from "./queries.js";
import { LISTING_DAYS, LISTING_SCHEMA, RUN_SCHEMA, SPLIT_COLUMNS, STAMP_SCHEMA } from "./schema.js";

export class RouteError extends Error {
  constructor(public readonly status: number, public readonly body: { error: string; failure: string }) {
    super(body.error);
  }
}

export interface ArkivHealth {
  arkiv: "ok" | "off";
  arkiv_writes: boolean;
  checker: string | null;
}

export interface ArkivServiceOptions {
  /** ARKIV_RPC without the access key. */
  publicRpc: string;
  chainId: number;
  season: number;
  priceC: number;
  /** The checker's address (EIP-55), or null without a well-formed key. */
  checker: string | null;
  /** The port reads and writes go through; null when not even the RPC is usable. */
  arkiv: ArkivPort | null;
  /** The publish pipeline; null when SERVER_SECRET (books) is missing. */
  publisher: Publisher | null;
  payments: PaymentCheck;
  /** ARKIV_GHOST_SECRET ("" when missing). */
  ghostSecret: string;
  /** What arkivProblems() says (names only): empty means the configuration is complete. */
  problems: string[];
  boardFile: string;
  snapshotFile: string;
  /** ARKIV_EXPLORER_TX / ARKIV_EXPLORER_ENTITY (default: Rabdi's explorer). */
  explorer?: ExplorerConfig;
  log?: (line: string) => void;
}

const PUBLISH_FAILURE = "ls_publish_fail";
const GHOST_FAILURE = "buy_load_fail";

export class ArkivService {
  /** What the last probe saw: null before the first one answers. */
  private chainSeen: number | null = null;
  private balanceSeen: bigint | null = null;
  private reachable = false;

  constructor(private readonly opts: ArkivServiceOptions) {}

  // ---- health and the write gate ---------------------------------------------------------

  health(): ArkivHealth {
    return {
      arkiv: this.reachable && this.chainSeen === this.opts.chainId ? "ok" : "off",
      arkiv_writes: this.writesOn(),
      checker: this.opts.checker,
    };
  }

  private writesOn(): boolean {
    return (
      this.opts.problems.length === 0 &&
      this.opts.publisher !== null &&
      this.reachable &&
      this.chainSeen === this.opts.chainId &&
      this.balanceSeen !== null &&
      this.balanceSeen > 0n
    );
  }

  /**
   * Whether a new publish job may start: refused when the config is incomplete, or when the last
   * probe saw the wrong chain or an empty checker. A probe that merely failed to answer does not
   * refuse: the job then fails on its own if Arkiv is really down.
   */
  readonly gate: WriteGate = () => {
    if (this.opts.problems.length > 0 || this.opts.publisher === null) return "arkiv_not_configured";
    if (this.chainSeen !== null && this.chainSeen !== this.opts.chainId) return "arkiv_unavailable";
    if (this.balanceSeen !== null && this.balanceSeen === 0n) return "arkiv_unavailable";
    return null;
  };

  /** One probe: chain id and the checker's balance. Logs only changes, never a URL or a key. */
  async probe(): Promise<void> {
    const port = this.opts.arkiv;
    if (!port) return;
    const before = JSON.stringify(this.health());
    try {
      this.chainSeen = await port.chainId();
      this.reachable = true;
      if (this.opts.checker) this.balanceSeen = await port.balance(this.opts.checker);
    } catch (err) {
      this.reachable = false;
      const why = err instanceof ArkivError ? err.message : "no answer";
      if (before !== JSON.stringify(this.health()) || this.chainSeen === null) this.opts.log?.(`arkiv unreachable (${why})`);
      return;
    }
    const now = this.health();
    if (before !== JSON.stringify(now)) {
      const chain = this.chainSeen === this.opts.chainId ? `chain ${this.chainSeen}` : `chain ${this.chainSeen}, not ARKIV_CHAIN_ID ${this.opts.chainId}: writes off`;
      const bal = this.balanceSeen === null ? "" : `, checker balance ${formatGlm(this.balanceSeen)} tGLM`;
      const off = this.opts.problems.length
        ? ` (set: ${this.opts.problems.join(", ")})`
        : this.balanceSeen === 0n
          ? " (the checker has no tGLM: fund it at hub.arkiv.network/faucet)"
          : "";
      const writes = now.arkiv_writes ? "writes on" : `writes off${off}`;
      this.opts.log?.(`arkiv reachable (${chain}${bal}); ${writes}`);
    }
  }

  // ---- routes ----------------------------------------------------------------------------

  config(): Record<string, unknown> {
    return {
      chain_id: this.opts.chainId,
      rpc: this.opts.publicRpc,
      explorer: ARKIV_EXPLORER,
      checker: this.opts.checker,
      season: this.opts.season,
      schemas: { run: RUN_SCHEMA, listing: LISTING_SCHEMA, stamp: STAMP_SCHEMA },
      price: Number.isInteger(this.opts.priceC) ? priceText(this.opts.priceC) : null,
      listing_days: LISTING_DAYS,
      split_columns: [...SPLIT_COLUMNS],
      explorer_tx: this.opts.explorer?.tx ?? ARKIV_EXPLORER_TX,
      explorer_entity: this.opts.explorer?.entity ?? ARKIV_EXPLORER_ENTITY,
    };
  }

  publish(body: Record<string, unknown>): { id: string; expires_s: number } {
    if (!this.opts.publisher) throw new RouteError(503, { error: "arkiv_not_configured", failure: PUBLISH_FAILURE });
    try {
      return this.opts.publisher.start(body);
    } catch (err) {
      if (err instanceof PublishRefused) throw new RouteError(err.status, { error: err.error, failure: PUBLISH_FAILURE });
      throw err;
    }
  }

  publishView(id: string): PublishView {
    const v = this.opts.publisher?.view(id);
    if (!v) throw new RouteError(404, { error: "unknown_id", failure: PUBLISH_FAILURE });
    return v;
  }

  /** The console's report of its transaction: 404 unknown_id, 400 bad_body, 409 not_signing. */
  written(id: string, body: Record<string, unknown>): { ok: true } {
    if (!this.opts.publisher) throw new RouteError(404, { error: "unknown_id", failure: PUBLISH_FAILURE });
    try {
      return this.opts.publisher.written(id, body);
    } catch (err) {
      if (err instanceof PublishRefused) throw new RouteError(err.status, { error: err.error, failure: PUBLISH_FAILURE });
      throw err;
    }
  }

  /**
   * A ghost by run key. The run must count (board.ts): live, named by a checker stamp, created by
   * the console the stamp names. It carries `log_enc`: a receipt that pays for this run is needed,
   * the ghost is decrypted here and must hash to the run's log_h. A run with no sealed ghost is not
   * served.
   */
  async ghost(body: Record<string, unknown>): Promise<{ log: string; log_h: string }> {
    const { run, receipt } = body;
    if (typeof run !== "string" || !KEY_RE.test(run)) throw new RouteError(400, { error: "bad_body", failure: GHOST_FAILURE });
    if (typeof receipt !== "string" || !/^[\x21-\x7e]{1,128}$/.test(receipt)) {
      throw new RouteError(400, { error: "bad_body", failure: GHOST_FAILURE });
    }
    const port = this.opts.arkiv;
    if (!port || !this.opts.checker) throw new RouteError(503, { error: "arkiv_not_configured", failure: GHOST_FAILURE });
    let row;
    try {
      row = await port.getRun(run, true);
    } catch {
      throw new RouteError(503, { error: "arkiv_unavailable", failure: GHOST_FAILURE });
    }
    if (!row) throw new RouteError(404, { error: "not_on_board", failure: GHOST_FAILURE });

    if (!row.log_enc) {
      this.opts.log?.(`arkiv ghost ${row.key}: has no sealed ghost, not served`);
      throw new RouteError(404, { error: "not_on_board", failure: GHOST_FAILURE });
    }
    if (!GHOST_SECRET_RE.test(this.opts.ghostSecret)) throw new RouteError(503, { error: "arkiv_not_configured", failure: GHOST_FAILURE });
    if (!(await this.opts.payments.accept(receipt, row.key))) throw new RouteError(402, { error: "payment_required", failure: GHOST_FAILURE });
    const plain = decryptGhost(this.opts.ghostSecret, row.log_h, row.log_enc);
    if (!plain || sha256Hex(plain) !== row.log_h) {
      this.opts.log?.(`arkiv ghost ${row.key}: does not match its log_h, not served`);
      throw new RouteError(404, { error: "not_on_board", failure: GHOST_FAILURE });
    }
    this.opts.log?.(`arkiv ghost ${row.key}: served (decrypted, receipt accepted)`);
    return { log: Buffer.from(plain).toString("base64"), log_h: row.log_h };
  }

  boardHtml(): Buffer | null {
    return readOrNull(this.opts.boardFile);
  }

  snapshot(): Buffer | null {
    return readOrNull(this.opts.snapshotFile);
  }
}

function readOrNull(file: string): Buffer | null {
  try {
    return readFileSync(file);
  } catch {
    return null;
  }
}

/** wei -> tGLM with 4 decimals. */
export function formatGlm(wei: bigint): string {
  const whole = wei / 10n ** 18n;
  const frac = ((wei % 10n ** 18n) * 10_000n) / 10n ** 18n;
  return `${whole}.${String(frac).padStart(4, "0")}`;
}

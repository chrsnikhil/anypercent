/**
 * The HTTP contract the launcher adapter (launcher/arca_launcher/handler/world.py) depends on.
 * See the README for the contract. JSON in, JSON out.
 *
 *   GET  /health                 {"world": "ok"|"off", "idkit": bool, "agentpass": bool,
 *                                 "approvals": "idkit"|"agentpass"|null}
 *                                ("agentpass": listing approvals are available, by either provider)
 *   POST /idkit/start            {"console"}       -> {"id", "qr", "code", "expires_s"}
 *   GET  /idkit/{id}             {"stage", "ok", "failure", "data"}
 *   POST /agentpass/start        {"book", "action"} -> {"id", "qr", "code", "expires_s"}
 *                                (run by APPROVALS: Agent Pass device grant, or an IDKit proof)
 *   GET  /agentpass/{id}         {"stage", "ok", "failure", "data"}
 *   POST /agentpass/{id}/cancel  the console's Circle -> {"ok": true}; idempotent
 *   POST /idkit/{id}/cancel      the same for a sign-up (added for the launcher)
 *
 *   GET  /arkiv/config, POST /arkiv/publish, GET /arkiv/publish/{id},
 *   POST /arkiv/publish/{id}/written {"tx", "run", "listing"} -> {"ok": true}  (the console's own
 *                                transaction of what the job issued at stage "sign"), POST /arkiv/ghost,
 *   GET  /board, /board/snapshot.json   the Arkiv module (src/arkiv/service.ts); /health then
 *                                adds "arkiv", "arkiv_writes" and "checker"
 *
 *   GET  /hedera/config, /hedera/payto/{book}, /hedera/sales/{book}; POST /hedera/record,
 *   GET  /hedera/record/{id}, POST /hedera/buy, GET /hedera/buy/{id}; GET /x402/ghost/{listing}
 *                                the Hedera module (src/hedera/service.ts); /health then adds
 *                                "hedera", "hedera_pay" and "hedera_record"
 *
 *   GET  /console/{console}[?wallet=0x...]  {"tag", "book", "state", "credential", "wallet",
 *                                "wallet_pending"}; registers an unseen console and the Arkiv wallet
 *                                it reports (used only once a World-approved link names it)
 *   POST /console/op             {"op": "link"|"release", "console": tag, "book"?} -> {"id", "action",
 *                                "approval": {"id", "qr", "code", "expires_s"}}  (owner CLIs)
 *   GET  /console/op/{id}        {"stage", "ok", "failure", "data"};  POST /console/op/{id}/cancel
 *   POST /scout, GET /scout/{id} PB's scout (src/scout/scout.ts)
 *   POST /house/batch, POST /house/publish, GET /house/publish/{id}, POST /house/publish/{id}/cancel
 *                                the house's BOT batches (src/arkiv/house.ts; owner CLI only)
 *
 * After a cancel every GET answers {"stage": "done", "ok": false, "failure": "id_rejected" |
 * "ls_denied", "data": {}}, and nothing the phone sends later makes or binds anything.
 *
 * Bodies are limited to 4 KiB, except POST /arkiv/publish and POST /house/batch (192 KiB: they carry
 * logs) and POST /scout (96 KiB). Errors on /console/* carry failure id_offline, on /scout* buy_down;
 * the /house/* routes answer {"error", "detail"}.
 * /x402/ghost answers the x402 exchange itself (402 with PAYMENT-REQUIRED, 200 with
 * PAYMENT-RESPONSE, 404 {"error": "not_for_sale"}, 503); a payment header is never logged.
 *
 * Every 2xx body is exactly the contract's shape. Errors are non-2xx: 400 bad body, 404 unknown id,
 * 503 when a service is not configured or World cannot be reached at start; their body carries the
 * step's failure name: {"error", "failure"}. The launcher treats any non-2xx as World down.
 *
 * The access log has method, route shape, status and time only: never bodies, links or codes.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { BOOK_RE, StartFailure, type ApprovalProvider, type ApprovalsKind } from "./approvals.js";
import { HouseRefused, MAX_HOUSE_BODY, type HouseView } from "./arkiv/house.js";
import { MAX_PUBLISH_BODY, type PublishView } from "./arkiv/publish.js";
import { ConsoleOpRefused, type ConsoleView, type OpView } from "./consoles.js";
import { MAX_SCOUT_BODY, ScoutRefused, type ScoutView } from "./scout/scout.js";
import { RouteError, type ArkivHealth } from "./arkiv/service.js";
import { HederaRouteError, type HederaHealth } from "./hedera/service.js";
import type { BuyView } from "./hedera/agent.js";
import type { RecordView } from "./hedera/record.js";
import type { X402Reply } from "./hedera/resource.js";
import { IdkitSessions, IdkitStartFailure } from "./idkit.js";

export interface Health {
  world: "ok" | "off";
  idkit: boolean;
  agentpass: boolean;
  approvals: ApprovalsKind | null;
}

/** /health from what is wired: `agentpass` means approvals are available, by either provider. */
export function makeHealth(idkit: unknown | null, approvals: ApprovalProvider | null, reachable: boolean): Health {
  return {
    world: (idkit !== null || approvals !== null) && reachable ? "ok" : "off",
    idkit: idkit !== null,
    agentpass: approvals !== null,
    approvals: approvals?.kind ?? null,
  };
}

/** The scout-and-pivot fields of /health. */
export interface PivotHealth {
  /** Consoles are bound (one console, one person). */
  console: boolean;
  /** The splits tool is configured (CHECKER_SPLITS). */
  splits: boolean;
  /** PB's scout: "model" (Groq), "rule" (no key, or the key refused), "off" (Arkiv or Hedera pay off). */
  scout: "model" | "rule" | "off";
  /** House batches can be published (house account, owner book, a funded house wallet, Arkiv writes). */
  house: boolean;
  /** Why the house is off ("set: HOUSE_ARKIV_KEY", "Arkiv writes are off", "the house wallet 0x... has 0.0000 tGLM: ..."), or null while it is on. */
  house_off: string | null;
}

/** The pivot fields from what is wired: house is on only while Arkiv writes are; off, it says why. */
export function pivotHealth(w: {
  consoles: unknown | null;
  splits: boolean;
  scout: { mode(): "model" | "rule" | "off" } | null;
  house: unknown | null;
  /** houseProblems(cfg): what keeps the house off, by .env name. */
  houseProblems?: readonly string[];
  /** ArkivService.houseFunds(): the house wallet below HOUSE_MIN_WEI at the last probe, else null. */
  houseFunds?: string | null;
  arkivWrites: boolean;
}): PivotHealth {
  const funds = w.houseFunds ?? null;
  const on = w.house !== null && w.arkivWrites && funds === null;
  const problems = w.houseProblems ?? [];
  const off = on ? null : problems.length ? `set: ${problems.join(", ")}` : w.house === null ? "not configured" : !w.arkivWrites ? "Arkiv writes are off" : funds;
  return { console: w.consoles !== null, splits: w.splits, scout: w.scout?.mode() ?? "off", house: on, house_off: off };
}

/** /health with the Arkiv and Hedera modules' fields when they are wired. */
export type FullHealth = Health & Partial<ArkivHealth> & Partial<HederaHealth> & Partial<PivotHealth>;

/** What the routes need of the console registry (Consoles). */
export interface ConsoleRoutes {
  view(id: string, wallet?: string): ConsoleView;
  startOp(body: Record<string, unknown>): Promise<{ id: string; action: string; approval: Record<string, unknown> }>;
  opView(id: string): OpView | undefined;
  cancelOp(id: string): boolean;
}

/** What the routes need of the scout (ScoutService). */
export interface ScoutRoutes {
  start(body: Record<string, unknown>): { id: string; expires_s: number };
  view(id: string): ScoutView | undefined;
}

/** What the routes need of the house (HouseService). */
export interface HouseRoutes {
  stage(body: Record<string, unknown>): Promise<Record<string, unknown>>;
  publish(body: Record<string, unknown>): Promise<{ id: string; action: string; approval: Record<string, unknown> | null }>;
  view(id: string): HouseView | undefined;
  cancel(id: string): boolean;
}

/** What the routes need of the Arkiv module (ArkivService). */
export interface ArkivRoutes {
  config(): Record<string, unknown>;
  publish(body: Record<string, unknown>): { id: string; expires_s: number };
  publishView(id: string): PublishView;
  written(id: string, body: Record<string, unknown>): { ok: true };
  ghost(body: Record<string, unknown>): Promise<{ log: string; log_h: string }>;
  boardHtml(): Buffer | null;
  snapshot(): Buffer | null;
}

/** What the routes need of the Hedera module (HederaService). */
export interface HederaRoutes {
  config(): Record<string, unknown>;
  payto(book: string): { book: string; pay_to: string | null };
  recordStart(body: Record<string, unknown>): { id: string; expires_s: number };
  recordView(id: string): RecordView;
  buyStart(body: Record<string, unknown>): { id: string; expires_s: number };
  buyView(id: string): BuyView;
  sales(book: string, after: string | null): { sales: unknown[] };
  x402(listing: string, signature: string | null): Promise<X402Reply>;
  x402Preflight(): X402Reply;
}

export interface ServerDeps {
  health(): FullHealth;
  idkit: IdkitSessions | null;
  /** The listing-approval provider behind /agentpass/*, or null when none is configured. */
  approvals: ApprovalProvider | null;
  /** The Arkiv routes; null or absent: they answer 503 (the board pages 404). */
  arkiv?: ArkivRoutes | null;
  /** The Hedera routes; null or absent: they answer 503. */
  hedera?: HederaRoutes | null;
  /** One console, one person; null or absent: /console/* answers 503. */
  consoles?: ConsoleRoutes | null;
  /** PB's scout; null or absent: /scout answers 503. */
  scout?: ScoutRoutes | null;
  /** The house's BOT batches; null or absent: /house/* answers 503. */
  house?: HouseRoutes | null;
  log?: (line: string) => void;
}

class HttpError extends Error {
  constructor(public readonly status: number, public readonly body: Record<string, unknown>) {
    super(String(body.error));
  }
}

const MAX_BODY = 4096;

/** A non-JSON 2xx answer (the web board's page and snapshot). */
class Raw {
  constructor(public readonly body: Buffer, public readonly type: string) {}
}

/** A JSON answer with its own status and headers (the x402 exchange). */
class WithHeaders {
  constructor(public readonly reply: X402Reply) {}
}
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

async function readJson(
  req: IncomingMessage,
  max = MAX_BODY,
  tooLarge: Record<string, unknown> = { error: "body_too_large" },
  status = 413,
): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > max) throw new HttpError(status, tooLarge);
    chunks.push(chunk as Buffer);
  }
  if (size === 0) return {};
  try {
    const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
  } catch {
    // fall through
  }
  throw new HttpError(400, { error: "bad_json" });
}

function send(res: ServerResponse, status: number, body: unknown): void {
  if (body instanceof WithHeaders) {
    const r = body.reply;
    const text = r.status === 204 ? "" : JSON.stringify(r.body);
    res.writeHead(r.status, {
      ...r.headers,
      ...(r.status === 204 ? {} : { "content-type": "application/json; charset=utf-8" }),
      "cache-control": "no-store",
      "content-length": Buffer.byteLength(text),
    });
    res.end(text);
    return;
  }
  if (body instanceof Raw) {
    res.writeHead(status, { "content-type": body.type, "cache-control": "no-store", "content-length": body.body.length });
    res.end(body.body);
    return;
  }
  const text = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(text),
  });
  res.end(text);
}

async function route(deps: ServerDeps, req: IncomingMessage): Promise<[number, unknown]> {
  const url = new URL(req.url ?? "/", "http://bridge");
  const parts = url.pathname.split("/").filter(Boolean);
  const method = req.method ?? "GET";

  if (method === "GET" && url.pathname === "/health") return [200, deps.health()];

  if (parts[0] === "idkit") {
    if (method === "POST" && parts.length === 2 && parts[1] === "start") {
      const body = await readJson(req);
      const consoleId = body.console;
      if (typeof consoleId !== "string" || consoleId.length < 1 || consoleId.length > 128) {
        throw new HttpError(400, { error: "bad_console", failure: "id_offline" });
      }
      if (!deps.idkit) throw new HttpError(503, { error: "idkit_not_configured", failure: "id_offline" });
      try {
        return [200, await deps.idkit.start(consoleId)];
      } catch (err) {
        if (err instanceof IdkitStartFailure) throw new HttpError(err.status, { error: "world_unavailable", failure: err.failure });
        throw err;
      }
    }
    if (parts.length === 2 && method === "GET") {
      const view = deps.idkit?.view(parts[1]);
      if (!view) throw new HttpError(404, { error: "unknown_id", failure: "id_offline" });
      return [200, view];
    }
    if (parts.length === 3 && parts[2] === "cancel" && method === "POST") {
      if (!deps.idkit?.cancel(parts[1])) throw new HttpError(404, { error: "unknown_id", failure: "id_offline" });
      return [200, { ok: true }];
    }
  }

  if (parts[0] === "agentpass") {
    if (method === "POST" && parts.length === 2 && parts[1] === "start") {
      const body = await readJson(req);
      const { book, action } = body;
      if (typeof book !== "string" || !BOOK_RE.test(book)) {
        throw new HttpError(400, { error: "bad_book", failure: "ls_world_down" });
      }
      if (typeof action !== "string" || action.trim() === "" || action.length > 160 || CONTROL_CHARS.test(action)) {
        throw new HttpError(400, { error: "bad_action", failure: "ls_world_down" });
      }
      if (!deps.approvals) throw new HttpError(503, { error: "approvals_not_configured", failure: "ls_world_down" });
      try {
        return [200, await deps.approvals.start(book, action.trim())];
      } catch (err) {
        if (err instanceof StartFailure) throw new HttpError(err.status, { error: "world_unavailable", failure: err.failure });
        throw err;
      }
    }
    if (parts.length === 2 && method === "GET") {
      const view = deps.approvals?.view(parts[1]);
      if (!view) throw new HttpError(404, { error: "unknown_id", failure: "ls_world_down" });
      return [200, view];
    }
    if (parts.length === 3 && parts[2] === "cancel" && method === "POST") {
      if (!deps.approvals?.cancel(parts[1])) throw new HttpError(404, { error: "unknown_id", failure: "ls_world_down" });
      return [200, { ok: true }];
    }
  }

  if (parts[0] === "arkiv") return arkivRoute(deps, req, method, parts);
  if (parts[0] === "console") return consoleRoute(deps, req, method, parts, url);
  if (parts[0] === "scout") return scoutRoute(deps, req, method, parts);
  if (parts[0] === "house") return houseRoute(deps, req, method, parts);
  if (parts[0] === "hedera") return hederaRoute(deps, req, method, parts, url);
  if (parts[0] === "x402" && parts[1] === "ghost" && parts.length === 3) {
    const h = deps.hedera ?? null;
    if (method === "OPTIONS") return [204, new WithHeaders(h ? h.x402Preflight() : { status: 204, headers: {}, body: {} })];
    if (method === "GET") {
      if (!h) return [503, new WithHeaders({ status: 503, headers: {}, body: { error: "hedera_not_configured" } })];
      const sig = req.headers["payment-signature"];
      const reply = await h.x402(parts[2], typeof sig === "string" && sig !== "" ? sig : null);
      return [reply.status, new WithHeaders(reply)];
    }
  }

  if (method === "GET" && (url.pathname === "/board" || url.pathname === "/board/")) {
    const html = deps.arkiv?.boardHtml();
    if (!html) throw new HttpError(404, { error: "not_found" });
    return [200, new Raw(html, "text/html; charset=utf-8")];
  }
  if (method === "GET" && url.pathname === "/board/snapshot.json") {
    const snap = deps.arkiv?.snapshot();
    if (!snap) throw new HttpError(404, { error: "not_found" });
    return [200, new Raw(snap, "application/json; charset=utf-8")];
  }

  throw new HttpError(404, { error: "not_found" });
}

/** /arkiv/*: failures are ls_publish_fail on the publish routes and buy_load_fail on /arkiv/ghost. */
async function arkivRoute(deps: ServerDeps, req: IncomingMessage, method: string, parts: string[]): Promise<[number, unknown]> {
  const a = deps.arkiv ?? null;
  const pub = { error: "arkiv_not_configured", failure: "ls_publish_fail" };
  try {
    if (method === "GET" && parts.length === 2 && parts[1] === "config") {
      if (!a) throw new HttpError(503, pub);
      return [200, a.config()];
    }
    if (method === "POST" && parts.length === 2 && parts[1] === "publish") {
      const bad = { error: "bad_body", failure: "ls_publish_fail" };
      const body = await readJson(req, MAX_PUBLISH_BODY, bad, 400).catch((err: unknown) => {
        throw err instanceof HttpError && err.status === 400 ? new HttpError(400, bad) : err;
      });
      if (!a) throw new HttpError(503, pub);
      return [200, a.publish(body)];
    }
    if (method === "GET" && parts.length === 3 && parts[1] === "publish") {
      if (!a) throw new HttpError(404, { error: "unknown_id", failure: "ls_publish_fail" });
      return [200, a.publishView(parts[2])];
    }
    if (method === "POST" && parts.length === 4 && parts[1] === "publish" && parts[3] === "written") {
      const bad = { error: "bad_body", failure: "ls_publish_fail" };
      const body = await readJson(req, MAX_BODY, bad, 400).catch((err: unknown) => {
        throw err instanceof HttpError && err.status === 400 ? new HttpError(400, bad) : err;
      });
      if (!a) throw new HttpError(404, { error: "unknown_id", failure: "ls_publish_fail" });
      return [200, a.written(parts[2], body)];
    }
    if (method === "POST" && parts.length === 2 && parts[1] === "ghost") {
      const bad = { error: "bad_body", failure: "buy_load_fail" };
      const body = await readJson(req, MAX_BODY, bad, 400).catch((err: unknown) => {
        throw err instanceof HttpError && err.status === 400 ? new HttpError(400, bad) : err;
      });
      if (!a) throw new HttpError(503, { error: "arkiv_not_configured", failure: "buy_load_fail" });
      return [200, await a.ghost(body)];
    }
  } catch (err) {
    if (err instanceof RouteError) throw new HttpError(err.status, err.body);
    throw err;
  }
  throw new HttpError(404, { error: "not_found" });
}

/** /hedera/*: failures are ls_record_fail on the record routes and buy_down on the others. */
async function hederaRoute(deps: ServerDeps, req: IncomingMessage, method: string, parts: string[], url: URL): Promise<[number, unknown]> {
  const h = deps.hedera ?? null;
  const off = (failure: string) => new HttpError(503, { error: "hedera_not_configured", failure });
  try {
    if (method === "GET" && parts.length === 2 && parts[1] === "config") {
      if (!h) throw off("buy_down");
      return [200, h.config()];
    }
    if (method === "GET" && parts.length === 3 && parts[1] === "payto") {
      if (!h) throw off("ls_record_fail");
      return [200, h.payto(parts[2])];
    }
    if (method === "GET" && parts.length === 3 && parts[1] === "sales") {
      if (!h) throw off("buy_down");
      return [200, h.sales(parts[2], url.searchParams.get("after"))];
    }
    for (const [name, failure] of [["record", "ls_record_fail"], ["buy", "buy_down"]] as const) {
      if (parts[1] !== name) continue;
      if (method === "POST" && parts.length === 2) {
        const bad = { error: "bad_body", failure };
        const body = await readJson(req, MAX_BODY, bad, 400).catch((err: unknown) => {
          throw err instanceof HttpError && err.status === 400 ? new HttpError(400, bad) : err;
        });
        if (!h) throw off(failure);
        return [200, name === "record" ? h.recordStart(body) : h.buyStart(body)];
      }
      if (method === "GET" && parts.length === 3) {
        if (!h) throw new HttpError(404, { error: "unknown_id", failure });
        return [200, name === "record" ? h.recordView(parts[2]) : h.buyView(parts[2])];
      }
    }
  } catch (err) {
    if (err instanceof HederaRouteError) throw new HttpError(err.status, err.body);
    throw err;
  }
  throw new HttpError(404, { error: "not_found" });
}

/** /console/*: failure id_offline (the launcher only GETs; the ops are the owner's CLIs). */
async function consoleRoute(deps: ServerDeps, req: IncomingMessage, method: string, parts: string[], url: URL): Promise<[number, unknown]> {
  const c = deps.consoles ?? null;
  const err = (status: number, error: string) => new HttpError(status, { error, failure: "id_offline" });
  try {
    if (method === "POST" && parts.length === 2 && parts[1] === "op") {
      const body = await readJson(req, MAX_BODY, { error: "bad_body", failure: "id_offline" }, 400).catch((e: unknown) => {
        throw e instanceof HttpError && e.status === 400 ? err(400, "bad_body") : e;
      });
      if (!c) throw err(503, "consoles_not_configured");
      return [200, await c.startOp(body)];
    }
    if (method === "GET" && parts.length === 3 && parts[1] === "op") {
      const v = c?.opView(parts[2]);
      if (!v) throw err(404, "unknown_id");
      return [200, v];
    }
    if (method === "POST" && parts.length === 4 && parts[1] === "op" && parts[3] === "cancel") {
      if (!c?.cancelOp(parts[2])) throw err(404, "unknown_id");
      return [200, { ok: true }];
    }
    if (method === "GET" && parts.length === 2) {
      if (!/^[A-Za-z0-9_-]{16,128}$/.test(parts[1])) throw err(400, "bad_console");
      if (!c) throw err(503, "consoles_not_configured");
      const wallet = url.searchParams.get("wallet");
      return [200, wallet === null ? c.view(parts[1]) : c.view(parts[1], wallet)];
    }
  } catch (e) {
    if (e instanceof ConsoleOpRefused) throw err(e.status, e.error);
    throw e;
  }
  throw new HttpError(404, { error: "not_found" });
}

/** /scout*: failure buy_down. */
async function scoutRoute(deps: ServerDeps, req: IncomingMessage, method: string, parts: string[]): Promise<[number, unknown]> {
  const s = deps.scout ?? null;
  const err = (status: number, error: string) => new HttpError(status, { error, failure: "buy_down" });
  try {
    if (method === "POST" && parts.length === 1) {
      const body = await readJson(req, MAX_SCOUT_BODY, { error: "bad_body", failure: "buy_down" }, 400).catch((e: unknown) => {
        throw e instanceof HttpError && e.status === 400 ? err(400, "bad_body") : e;
      });
      if (!s) throw err(503, "scout_off");
      return [200, s.start(body)];
    }
    if (method === "GET" && parts.length === 2) {
      const v = s?.view(parts[1]);
      if (!v) throw err(404, "unknown_id");
      return [200, v];
    }
  } catch (e) {
    if (e instanceof ScoutRefused) throw err(e.status, e.error);
    throw e;
  }
  throw new HttpError(404, { error: "not_found" });
}

/** /house/*: the owner's CLI; errors are {error, detail}. */
async function houseRoute(deps: ServerDeps, req: IncomingMessage, method: string, parts: string[]): Promise<[number, unknown]> {
  const h = deps.house ?? null;
  const err = (status: number, error: string, detail?: string) => new HttpError(status, detail ? { error, detail } : { error });
  try {
    if (method === "POST" && parts.length === 2 && (parts[1] === "batch" || parts[1] === "publish")) {
      const max = parts[1] === "batch" ? MAX_HOUSE_BODY : MAX_BODY;
      const body = await readJson(req, max, { error: "bad_body", detail: "body too large" }, 400).catch((e: unknown) => {
        throw e instanceof HttpError && e.status === 400 ? err(400, "bad_body", String(e.body.detail ?? "not a JSON object")) : e;
      });
      if (!h) throw err(503, "house_not_configured");
      return [200, parts[1] === "batch" ? await h.stage(body) : await h.publish(body)];
    }
    if (method === "GET" && parts.length === 3 && parts[1] === "publish") {
      const v = h?.view(parts[2]);
      if (!v) throw err(404, "unknown_id");
      return [200, v];
    }
    if (method === "POST" && parts.length === 4 && parts[1] === "publish" && parts[3] === "cancel") {
      if (!h?.cancel(parts[2])) throw err(404, "unknown_id");
      return [200, { ok: true }];
    }
  } catch (e) {
    if (e instanceof HouseRefused) throw err(e.status, e.error, e.detail);
    throw e;
  }
  throw new HttpError(404, { error: "not_found" });
}

/** "/agentpass/AbC.../cancel" -> "/agentpass/:id/cancel": ids stay out of the log. */
function shape(path: string): string {
  const parts = path.split("?")[0].split("/");
  if (parts.length >= 3 && (parts[1] === "idkit" || parts[1] === "agentpass") && parts[2] !== "start") parts[2] = ":id";
  if (parts.length >= 4 && parts[1] === "arkiv" && parts[2] === "publish") parts[3] = ":id";
  if (parts.length >= 4 && parts[1] === "hedera" && ["record", "buy", "payto", "sales"].includes(parts[2])) parts[3] = parts[2] === "payto" || parts[2] === "sales" ? ":book" : ":id";
  if (parts.length >= 4 && parts[1] === "x402" && parts[2] === "ghost") parts[3] = ":listing";
  if (parts.length >= 3 && parts[1] === "console") {
    if (parts[2] === "op") {
      if (parts.length >= 4) parts[3] = ":id";
    } else parts[2] = ":console";
  }
  if (parts.length >= 3 && parts[1] === "scout") parts[2] = ":id";
  if (parts.length >= 4 && parts[1] === "house" && parts[2] === "publish") parts[3] = ":id";
  return parts.join("/");
}

export function buildServer(deps: ServerDeps): Server {
  const log = deps.log ?? (() => {});
  return createServer((req, res) => {
    const t0 = Date.now();
    route(deps, req)
      .then(([status, body]) => send(res, status, body))
      .catch((err: unknown) => {
        if (err instanceof HttpError) send(res, err.status, err.body);
        else send(res, 500, { error: "internal" });
      })
      .finally(() => {
        // Skip the launcher's steady /health and status polls; log everything else by shape.
        const path = shape(req.url ?? "/");
        if (req.method !== "GET") log(`${req.method} ${path} ${res.statusCode} ${Date.now() - t0}ms`);
      });
  });
}

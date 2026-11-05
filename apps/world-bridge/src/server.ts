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
 *   GET  /arkiv/config, POST /arkiv/publish, GET /arkiv/publish/{id}, POST /arkiv/ghost,
 *   GET  /board, /board/snapshot.json   the Arkiv module (src/arkiv/service.ts); /health then
 *                                adds "arkiv", "arkiv_writes" and "checker"
 *
 * After a cancel every GET answers {"stage": "done", "ok": false, "failure": "id_rejected" |
 * "ls_denied", "data": {}}, and nothing the phone sends later makes or binds anything.
 *
 * Bodies are limited to 4 KiB, except POST /arkiv/publish (192 KiB: it carries the run's log).
 *
 * Every 2xx body is exactly the contract's shape. Errors are non-2xx: 400 bad body, 404 unknown id,
 * 503 when a service is not configured or World cannot be reached at start; their body carries the
 * step's failure name: {"error", "failure"}. The launcher treats any non-2xx as World down.
 *
 * The access log has method, route shape, status and time only: never bodies, links or codes.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { BOOK_RE, StartFailure, type ApprovalProvider, type ApprovalsKind } from "./approvals.js";
import { MAX_PUBLISH_BODY, type PublishView } from "./arkiv/publish.js";
import { RouteError, type ArkivHealth } from "./arkiv/service.js";
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

/** /health with the Arkiv module's three fields when it is wired. */
export type FullHealth = Health & Partial<ArkivHealth>;

/** What the routes need of the Arkiv module (ArkivService). */
export interface ArkivRoutes {
  config(): Record<string, unknown>;
  publish(body: Record<string, unknown>): { id: string; expires_s: number };
  publishView(id: string): PublishView;
  ghost(body: Record<string, unknown>): Promise<{ log: string; log_h: string }>;
  boardHtml(): Buffer | null;
  snapshot(): Buffer | null;
}

export interface ServerDeps {
  health(): FullHealth;
  idkit: IdkitSessions | null;
  /** The listing-approval provider behind /agentpass/*, or null when none is configured. */
  approvals: ApprovalProvider | null;
  /** The Arkiv routes; null or absent: they answer 503 (the board pages 404). */
  arkiv?: ArkivRoutes | null;
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

/** "/agentpass/AbC.../cancel" -> "/agentpass/:id/cancel": ids stay out of the log. */
function shape(path: string): string {
  const parts = path.split("?")[0].split("/");
  if (parts.length >= 3 && (parts[1] === "idkit" || parts[1] === "agentpass") && parts[2] !== "start") parts[2] = ":id";
  if (parts.length >= 4 && parts[1] === "arkiv" && parts[2] === "publish") parts[3] = ":id";
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

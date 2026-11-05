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
 * After a cancel every GET answers {"stage": "done", "ok": false, "failure": "id_rejected" |
 * "ls_denied", "data": {}}, and nothing the phone sends later makes or binds anything.
 *
 * Every 2xx body is exactly the contract's shape. Errors are non-2xx: 400 bad body, 404 unknown id,
 * 503 when a service is not configured or World cannot be reached at start; their body carries the
 * step's failure name: {"error", "failure"}. The launcher treats any non-2xx as World down.
 *
 * The access log has method, route shape, status and time only: never bodies, links or codes.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { BOOK_RE, StartFailure, type ApprovalProvider, type ApprovalsKind } from "./approvals.js";
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

export interface ServerDeps {
  health(): Health;
  idkit: IdkitSessions | null;
  /** The listing-approval provider behind /agentpass/*, or null when none is configured. */
  approvals: ApprovalProvider | null;
  log?: (line: string) => void;
}

class HttpError extends Error {
  constructor(public readonly status: number, public readonly body: Record<string, unknown>) {
    super(String(body.error));
  }
}

const MAX_BODY = 4096;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY) throw new HttpError(413, { error: "body_too_large" });
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

  throw new HttpError(404, { error: "not_found" });
}

/** "/agentpass/AbC.../cancel" -> "/agentpass/:id/cancel": ids stay out of the log. */
function shape(path: string): string {
  const parts = path.split("?")[0].split("/");
  if (parts.length >= 3 && (parts[1] === "idkit" || parts[1] === "agentpass") && parts[2] !== "start") parts[2] = ":id";
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

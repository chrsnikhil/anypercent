/**
 * Shared by the owner CLIs that need one World approval (console:link, console:release,
 * house:publish). They drive the running bridge over HTTP:
 *
 * - print the exact text World App will show, the QR to scan with World App (in the terminal) and
 *   the short code;
 * - poll the op every 1 s and print each stage; Ctrl-C cancels the op on the bridge;
 * - end with the chain ids and explorer links the op answers.
 *
 * Never printed: a jti, the approval's id, a key or any .env value.
 */
import QRCode from "qrcode";
import { loadEnv } from "./arkiv-common.js";
import type { Config } from "../src/config.js";

export { arg, die, flag } from "./arkiv-common.js";
export { loadEnv };

/** Where the running bridge answers: --bridge, else http://<HOST, 0.0.0.0 -> 127.0.0.1>:<PORT>. */
export function bridgeBase(cfg: Config, override?: string): string {
  if (override) return override.replace(/\/+$/, "");
  const host = cfg.host === "0.0.0.0" || cfg.host === "::" ? "127.0.0.1" : cfg.host;
  return `http://${host.includes(":") ? `[${host}]` : host}:${cfg.port}`;
}

export interface Answer {
  status: number;
  json: Record<string, any>;
}

export async function call(base: string, method: "GET" | "POST", path: string, body?: unknown, timeoutMs = 120_000): Promise<Answer> {
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method,
      headers: { "content-type": "application/json" },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new Error(`the bridge does not answer at ${base} (is npm start running? --bridge http://HOST:PORT)`);
  }
  const json = (await res.json().catch(() => ({}))) as Record<string, any>;
  return { status: res.status, json };
}

/** What the person sees before scanning: the exact text, the QR, the short code. */
export async function showApproval(action: string, approval: { qr: string; code: string; expires_s: number }): Promise<void> {
  console.log("");
  console.log("World App will show, word for word:");
  console.log(`  ${action}`);
  console.log("");
  if (approval.qr) console.log(await QRCode.toString(approval.qr, { type: "terminal", small: true }));
  console.log(`Scan it with World App (code ${approval.code}); it expires in ${approval.expires_s} s.`);
  console.log("");
}

/**
 * Poll GET <viewPath> every 1 s until stage "done", printing each new stage. Ctrl-C posts
 * <cancelPath> and exits. Returns the done view.
 */
export async function follow(base: string, viewPath: string, cancelPath: string, labels: Record<string, string> = {}): Promise<Record<string, any>> {
  let stopping = false;
  const onInt = () => {
    if (stopping) process.exit(130);
    stopping = true;
    console.log("\nCancelling on the bridge ...");
    call(base, "POST", cancelPath, undefined, 5000)
      .catch(() => null)
      .finally(() => {
        console.log("Cancelled: nothing was changed.");
        process.exit(130);
      });
  };
  process.on("SIGINT", onInt);
  let stage = "";
  try {
    for (;;) {
      const v = await call(base, "GET", viewPath, undefined, 15_000);
      if (v.status !== 200) throw new Error(`GET ${viewPath.replace(/\/[^/]+$/, "/:id")}: ${v.status} ${v.json.error ?? ""}`);
      if (v.json.stage !== stage) {
        stage = String(v.json.stage);
        console.log(`  ${labels[stage] ?? stage}`);
      }
      if (v.json.stage === "done") return v.json;
      await new Promise((r) => setTimeout(r, 1000));
    }
  } finally {
    process.off("SIGINT", onInt);
  }
}

export function row(label: string, value: string, link?: string | null): void {
  console.log(`${label.padEnd(18)} ${value}${link ? `\n${"".padEnd(19)}${link}` : ""}`);
}

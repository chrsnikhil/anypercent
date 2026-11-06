/**
 * Shared by the hedera:* scripts: .env loading and appending (never overwriting), the operator's SDK
 * client, the mirror, the facilitators, and output helpers. Nothing here prints a key or any .env
 * value: account ids, topic ids, transaction ids, HashScan links, balances and timings only.
 */
import { appendFileSync, existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { AccountId, Client, type PrivateKey } from "@hiero-ledger/sdk";
import { ACCOUNT_RE, DER_KEY_RE, HEDERA_NETWORK_CAIP2, type Config } from "../src/config.js";
import { hashscan, parseDerKey, RestMirror, type MirrorAccount, type MirrorKey } from "../src/hedera/net.js";
import { Facilitators, HttpFacilitator } from "../src/hedera/x402.js";
import { appDir, arg, die, envFile, flag, loadEnv, positional } from "./arkiv-common.js";

export { appDir, arg, die, envFile, flag, hashscan, loadEnv, positional };

export const NETWORK = HEDERA_NETWORK_CAIP2;

/** Set NAME=value in .env for each name that has no value yet; a value already there is never touched. */
export function fillEnv(file: string, entries: Array<[string, string]>, header: string): Map<string, "new" | "kept"> {
  const text = existsSync(file) ? readFileSync(file, "utf8") : "";
  const lines = text.split(/\r?\n/);
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  const status = new Map<string, "new" | "kept">();
  const append: string[] = [];
  let changedInPlace = false;
  for (const [name, value] of entries) {
    let hit: { index: number; value: string } | null = null;
    lines.forEach((line, index) => {
      const m = new RegExp(`^\\s*${name}\\s*=(.*)$`).exec(line);
      if (m) hit = { index, value: m[1].replace(/\s+#.*$/, "").trim().replace(/^["']|["']$/g, "") };
    });
    const found = hit as { index: number; value: string } | null;
    if (found && found.value !== "") {
      status.set(name, "kept");
      continue;
    }
    status.set(name, "new");
    if (found) {
      lines[found.index] = `${name}=${value}`;
      changedInPlace = true;
    } else append.push(`${name}=${value}`);
  }
  if (changedInPlace) {
    const tmp = `${file}.tmp`;
    writeFileSync(tmp, lines.join(eol));
    renameSync(tmp, file);
  }
  if (append.length) {
    const now = existsSync(file) ? readFileSync(file, "utf8") : "";
    const lead = now === "" || now.endsWith("\n") ? "" : eol;
    appendFileSync(file, `${lead}${["", header, ...append].join(eol)}${eol}`);
  }
  return status;
}

/** The operator's id and parsed key, or exit naming what is missing (names only). */
export function operator(cfg: Config): { id: string; key: PrivateKey } {
  const h = cfg.hedera;
  if (h.network !== "testnet") die("HEDERA_NETWORK must be testnet in this build.");
  if (!ACCOUNT_RE.test(h.operatorId)) die("Set HEDERA_OPERATOR_ID (0.0.N, your portal.hedera.com testnet account) in apps/world-bridge/.env.");
  if (!DER_KEY_RE.test(h.operatorKey)) die("Set HEDERA_OPERATOR_KEY to the DER-encoded private key the portal shows (it starts with 30...).");
  try {
    return { id: h.operatorId, key: parseDerKey(h.operatorKey) };
  } catch {
    return die("HEDERA_OPERATOR_KEY does not parse as a DER private key.");
  }
}

/** An SDK client on testnet paid by the operator. Close it when done. */
export function operatorClient(op: { id: string; key: PrivateKey }): Client {
  return Client.forTestnet().setOperator(AccountId.fromString(op.id), op.key);
}

export function mirrorOf(cfg: Config): RestMirror {
  return new RestMirror(cfg.hedera.mirror, 15_000);
}

export function facilitatorsOf(cfg: Config, log?: (line: string) => void): Facilitators {
  return new Facilitators(
    [cfg.hedera.facilitator, cfg.hedera.facilitatorFallback].filter((u) => u !== "").map((u) => new HttpFacilitator(u)),
    NETWORK,
    log,
  );
}

/** Does this key match the account's on-chain key (as the mirror shows it)? */
export function keyMatches(key: PrivateKey, mirrorKey: MirrorKey | null): boolean {
  if (!mirrorKey) return false;
  return mirrorKey.key.toLowerCase() === key.publicKey.toStringRaw().toLowerCase();
}

export const hbar = (tinybar: bigint) => `${(Number(tinybar) / 1e8).toFixed(2)} HBAR`;
export const usdc = (atomic: bigint | null) => (atomic === null ? "not associated" : `${(Number(atomic) / 1e6).toFixed(2)} USDC`);

export async function timed<T>(fn: () => Promise<T>): Promise<[T, number]> {
  const t0 = performance.now();
  const out = await fn();
  return [out, Math.round(performance.now() - t0)];
}

export function p50(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor((s.length - 1) / 2)] : Number.NaN;
}

export function line(label: string, value: string, link?: string, ms?: number): void {
  console.log(`${label.padEnd(26)} ${value}${ms !== undefined ? `  (${ms} ms)` : ""}${link ? `\n${"".padEnd(27)}${link}` : ""}`);
}

export async function mustAccount(mirror: RestMirror, id: string, what: string): Promise<MirrorAccount> {
  const a = await mirror.account(id).catch(() => null);
  if (!a) return die(`${what} ${id} is not on the testnet mirror (wrong id, or not created yet).`);
  if (a.deleted) return die(`${what} ${id} is deleted.`);
  return a;
}

/** A short reason for an SDK or network error, never a key or URL. */
export function why(err: unknown): string {
  const e = err as { status?: { toString(): string }; message?: string };
  if (e?.status) return String(e.status.toString());
  return String(e?.message ?? err)
    .split("\n")[0]
    .replace(/https?:\/\/\S+/g, "<url>")
    .replace(/\b(0x)?30[0-9a-fA-F]{60,}\b/g, "<key>")
    .slice(0, 200);
}

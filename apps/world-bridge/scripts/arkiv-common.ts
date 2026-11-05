/**
 * Shared by the arkiv:* scripts: .env loading, the SDK clients for one key, argument parsing and
 * output helpers. Nothing here prints a key, the access key or any .env value: addresses, entity
 * keys, transaction hashes, gas and balances only.
 */
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createPublicClient, createWalletClient, type PublicArkivClient, type WalletArkivClient } from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { http, type Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { redact } from "../src/arkiv/client.js";
import { formatGlm } from "../src/arkiv/service.js";
import { arkivRpcUrl, loadConfig, PRIVATE_KEY_RE, type Config } from "../src/config.js";

export const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");
export const repoRoot = resolve(appDir, "..", "..");
export const envFile = join(appDir, ".env");

export function loadEnv(): Config {
  if (existsSync(envFile)) process.loadEnvFile(envFile);
  return loadConfig(process.env, appDir);
}

/** --name value, or the fallback. */
export function arg(name: string, fallback?: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
}
export const flag = (name: string) => process.argv.includes(`--${name}`);
/** The positional arguments (not --flags or their values). */
export function positional(): string[] {
  const out: string[] = [];
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i].startsWith("--")) {
      if (i + 1 < a.length && !a[i + 1].startsWith("--")) i++;
      continue;
    }
    out.push(a[i]);
  }
  return out;
}

export interface Clients {
  pub: PublicArkivClient;
  wallet: WalletArkivClient | null;
  address: string | null;
}

/** SDK clients on Rabdi for one key (or read-only without one). */
export function clientsFor(cfg: Config, key?: string): Clients {
  const chain = rabdi({ accessKey: cfg.arkiv.accessKey });
  const transport = http(arkivRpcUrl(cfg.arkiv), { timeout: 15_000, retryCount: 1 });
  const pub = createPublicClient({ chain, transport, pollingInterval: 1000 }) as unknown as PublicArkivClient;
  if (!key || !PRIVATE_KEY_RE.test(key)) return { pub, wallet: null, address: null };
  const account = privateKeyToAccount(key as Hex);
  const wallet = createWalletClient({ chain, transport, account, pollingInterval: 1000 }) as unknown as WalletArkivClient;
  return { pub, wallet, address: account.address };
}

/** A short reason for an error: no URLs, no access key, no private keys. */
export function why(err: unknown, cfg: Config): string {
  const e = err as { shortMessage?: string; message?: string };
  return redact(e?.shortMessage ?? e?.message ?? String(err), [
    cfg.arkiv.accessKey,
    encodeURIComponent(cfg.arkiv.accessKey),
    cfg.arkiv.checkerKey,
    cfg.arkiv.strangerKey,
    cfg.arkiv.ghostSecret,
    cfg.serverSecret,
  ]);
}

export async function timed<T>(fn: () => Promise<T>): Promise<[T, number]> {
  const t0 = performance.now();
  const out = await fn();
  return [out, Math.round(performance.now() - t0)];
}

export const glm = formatGlm;

export function die(message: string): never {
  console.error(message);
  process.exit(1);
}

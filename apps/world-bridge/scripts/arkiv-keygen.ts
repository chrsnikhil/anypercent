/**
 * npm run arkiv:keygen
 *
 * Adds any missing ARKIV_CHECKER_KEY, ARKIV_STRANGER_KEY, HOUSE_ARKIV_KEY and ARKIV_GHOST_SECRET to
 * apps/world-bridge/.env. It never overwrites a value that is there (a name present with an empty
 * value is filled in place; a missing name is appended), never prints a key or the secret, and
 * prints only the PUBLIC addresses to fund at https://hub.arkiv.network/faucet.
 *
 * Back the values up offline: losing ARKIV_GHOST_SECRET loses every listed ghost, and the checker
 * key is the only wallet whose stamps the board counts. The house wallet (HOUSE_ARKIV_KEY) writes
 * the BOT runs and listings; it is never the checker's key.
 */
import { randomBytes } from "node:crypto";
import { appendFileSync, existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import type { Hex } from "viem";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { GHOST_SECRET_RE, PRIVATE_KEY_RE } from "../src/config.js";
import { arg, envFile as defaultEnvFile } from "./arkiv-common.js";

// --env-file only for trying the script on a scratch copy; the default is apps/world-bridge/.env.
const envFile = arg("env-file") ?? defaultEnvFile;

type Name = "ARKIV_CHECKER_KEY" | "ARKIV_STRANGER_KEY" | "HOUSE_ARKIV_KEY" | "ARKIV_GHOST_SECRET";
const NAMES: Name[] = ["ARKIV_CHECKER_KEY", "ARKIV_STRANGER_KEY", "HOUSE_ARKIV_KEY", "ARKIV_GHOST_SECRET"];

const text = existsSync(envFile) ? readFileSync(envFile, "utf8") : "";
const lines = text.split(/\r?\n/);
const eol = text.includes("\r\n") ? "\r\n" : "\n";

/** The line index and value of NAME=..., if present (the last one wins, as dotenv reads it). */
function find(name: Name): { index: number; value: string } | null {
  let hit: { index: number; value: string } | null = null;
  lines.forEach((line, index) => {
    const m = new RegExp(`^\\s*${name}\\s*=(.*)$`).exec(line);
    if (m) hit = { index, value: m[1].replace(/\s+#.*$/, "").trim().replace(/^["']|["']$/g, "") };
  });
  return hit;
}

const fresh = (name: Name): string => (name === "ARKIV_GHOST_SECRET" ? randomBytes(32).toString("hex") : generatePrivateKey());
const wellFormed = (name: Name, v: string) => (name === "ARKIV_GHOST_SECRET" ? GHOST_SECRET_RE : PRIVATE_KEY_RE).test(v);

const values = new Map<Name, string>();
const status = new Map<Name, string>();
const fillInPlace: Array<[number, string]> = [];
const append: string[] = [];

for (const name of NAMES) {
  const hit = find(name);
  if (hit && hit.value !== "") {
    values.set(name, hit.value);
    status.set(name, wellFormed(name, hit.value) ? "kept" : "kept as is, but it is not well-formed: fix it by hand");
    continue;
  }
  const v = fresh(name);
  values.set(name, v);
  status.set(name, "new");
  if (hit) fillInPlace.push([hit.index, `${name}=${v}`]);
  else append.push(`${name}=${v}`);
}

if (fillInPlace.length) {
  for (const [i, line] of fillInPlace) lines[i] = line;
  const tmp = `${envFile}.tmp`;
  writeFileSync(tmp, lines.join(eol));
  renameSync(tmp, envFile);
}
if (append.length) {
  const lead = text === "" || text.endsWith("\n") ? "" : eol;
  const block = [
    "",
    "# ---- Arkiv (npm run arkiv:keygen). Service only: never on the Pi, never shared. Back these up offline. ----",
    ...append,
  ].join(eol);
  appendFileSync(envFile, `${lead}${block}${eol}`);
}

const addr = (name: Name) => {
  const v = values.get(name) ?? "";
  return PRIVATE_KEY_RE.test(v) ? privateKeyToAccount(v as Hex).address : "(not a valid key)";
};

console.log(`checker   ${addr("ARKIV_CHECKER_KEY")}   (${status.get("ARKIV_CHECKER_KEY")})  stamps every run the board counts; funds consoles (arkiv:fund)`);
console.log(`stranger  ${addr("ARKIV_STRANGER_KEY")}   (${status.get("ARKIV_STRANGER_KEY")})  look-alike and extension demos only`);
console.log(`house     ${addr("HOUSE_ARKIV_KEY")}   (${status.get("HOUSE_ARKIV_KEY")})  writes the BOT runs and listings`);
console.log(`ghost secret: ${status.get("ARKIV_GHOST_SECRET")} (not shown)`);
console.log("Fund the checker and the stranger at https://hub.arkiv.network/faucet (the house too, or npm run arkiv:fund -- --to <house> --amount 1), then run: npm run arkiv:smoke");

/**
 * Every identifier the bridge stores or shows is an HMAC-SHA256 under SERVER_SECRET, never the
 * raw World value: a nullifier or an IdP `sub` never leaves this process and never lands on disk.
 * Each use has its own label so one HMAC can never stand in for another.
 */
import { createHash, createHmac } from "node:crypto";

/** The console's alphabet: no 0/O/1/I/L, read off a small screen at a glance (ledger.py _BOOK_CHARS). */
export const BOOK_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";

export function hmacHex(secret: string, label: string, value: string): string {
  return createHmac("sha256", secret).update(`${label}\u0000${value}`).digest("hex");
}

/** Public runner id: HMAC-SHA256(server_secret, value), truncated to 16 hex chars (64 bits). */
export function runnerId(secret: string, value: string): string {
  return hmacHex(secret, "runner", value).slice(0, 16);
}

/** Storage key for a nullifier (already canonical) under one action. */
export function nullifierKey(secret: string, action: string, canonicalNullifier: string): string {
  return hmacHex(secret, "nullifier", `${action}|${canonicalNullifier}`);
}

/** Storage key for an IdP account: (iss, sub), as World says to key accounts. */
export function subKey(secret: string, iss: string, sub: string): string {
  return hmacHex(secret, "sub", `${iss}|${sub}`);
}

/** Storage key for a used ID-token jti (not secret, but kept uniform and short). */
export function jtiKey(iss: string, jti: string): string {
  return createHash("sha256").update(`${iss}\u0000${jti}`).digest("hex");
}

/**
 * The book id candidate for a nullifier: "ANY-" plus 3 characters, derived from the nullifier's
 * HMAC so it is stable per human. `attempt` > 0 only when an earlier candidate is already taken by
 * someone else; past 64 attempts the id grows to 4 characters.
 */
export function bookCandidate(secret: string, nKey: string, attempt: number): string {
  const digest = createHmac("sha256", secret).update(`book\u0000${nKey}\u0000${attempt}`).digest();
  const len = attempt < 64 ? 3 : 4;
  let out = "";
  for (let i = 0; i < len; i++) out += BOOK_CHARS[digest[i] % BOOK_CHARS.length];
  return `ANY-${out}`;
}

/**
 * Listed ghosts are stored on Arkiv encrypted (spec: Decisions 7, `anypercent.run.log_enc`):
 *
 *   key      = HKDF-SHA256(ikm = ARKIV_GHOST_SECRET (32 bytes), salt = log_h (32 bytes),
 *                          info = "anypercent ghost v1", 32 bytes)
 *   log_enc  = nonce (12, random) || AES-256-GCM ciphertext || tag (16)
 *
 * One key per log, derived here; the key never leaves this service and is never logged. A buyer
 * checks sha256(log) == log_h against the row it read itself, so a wrong key or a swapped
 * ciphertext can never pass as a ghost.
 */
import { createCipheriv, createDecipheriv, createHash, hkdfSync, randomBytes } from "node:crypto";

const INFO = "anypercent ghost v1";
const NONCE = 12;
const TAG = 16;

export function sha256Hex(data: Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

function ghostKey(secretHex: string, logH: string): Buffer {
  if (!/^[0-9a-fA-F]{64}$/.test(secretHex)) throw new Error("ghost secret must be 64 hex");
  if (!/^[0-9a-f]{64}$/.test(logH)) throw new Error("log_h must be 64 lowercase hex");
  return Buffer.from(hkdfSync("sha256", Buffer.from(secretHex, "hex"), Buffer.from(logH, "hex"), INFO, 32));
}

/** nonce || ciphertext || tag, for the plain log whose sha256 is logH. */
export function encryptGhost(secretHex: string, logH: string, log: Uint8Array): Uint8Array {
  const nonce = randomBytes(NONCE);
  const cipher = createCipheriv("aes-256-gcm", ghostKey(secretHex, logH), nonce);
  const body = Buffer.concat([cipher.update(log), cipher.final()]);
  return Uint8Array.from(Buffer.concat([nonce, body, cipher.getAuthTag()]));
}

/** The plain log, or null when the key or the bytes are wrong (GCM's tag does not check out). */
export function decryptGhost(secretHex: string, logH: string, sealed: Uint8Array): Uint8Array | null {
  if (sealed.length < NONCE + TAG) return null;
  const buf = Buffer.from(sealed);
  try {
    const decipher = createDecipheriv("aes-256-gcm", ghostKey(secretHex, logH), buf.subarray(0, NONCE));
    decipher.setAuthTag(buf.subarray(buf.length - TAG));
    return Uint8Array.from(Buffer.concat([decipher.update(buf.subarray(NONCE, buf.length - TAG)), decipher.final()]));
  } catch {
    return null;
  }
}

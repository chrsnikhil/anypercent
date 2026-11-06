/**
 * SpecJSON: a CreateSpec (values, flags, expiry) as plain JSON, so the bridge can issue the exact
 * run and listing a console's signer writes (spec: The flow, step 2). Three JavaScript values have
 * no JSON form; each becomes a one-key object:
 *
 *   Uint8Array  {"$bytes": "<standard base64>"}     (log_enc, a plain log)
 *   bigint      {"$big": "<decimal digits>"}       (an atBlock expiry, any u64 given as a bigint)
 *   Date        {"$date": "<ISO 8601, ms, Z>"}      (an atDate expiry: the season's end + 30 d)
 *
 * Everything else (strings, finite numbers, booleans, null, arrays, plain objects) is itself; an
 * undefined property is left out, as JSON.stringify would. fromSpecJson(toSpecJson(spec)) equals
 * spec exactly (a test checks it, Uint8Array and bigint included). The decoder refuses what it
 * cannot read back exactly: a tag that is not one of the three, a malformed payload, a spec
 * without `values`, boolean `flags` or a known expiry kind.
 */
import type { CreateSpec, ExpirySpec, Flags } from "./client.js";

export type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

/** A CreateSpec as SpecJSON. */
export interface SpecJson {
  values: Record<string, Json>;
  flags: { readonly: boolean; permissionlessExtension: boolean };
  expiry: Record<string, Json>;
}

/** A SpecJSON document that does not decode exactly. */
export class SpecJsonError extends Error {}

const B64_RE = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const BIG_RE = /^-?(0|[1-9][0-9]*)$/;
const EXPIRY_KINDS = ["atDate", "days", "hours", "atBlock"];

function encode(v: unknown, path: string): Json {
  if (v instanceof Uint8Array) return { $bytes: Buffer.from(v.buffer, v.byteOffset, v.byteLength).toString("base64") };
  if (typeof v === "bigint") return { $big: v.toString() };
  if (v instanceof Date) {
    if (Number.isNaN(v.getTime())) throw new SpecJsonError(`${path}: an invalid date`);
    return { $date: v.toISOString() };
  }
  if (v === null || typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new SpecJsonError(`${path}: a number JSON cannot hold`);
    return v;
  }
  if (Array.isArray(v)) return v.map((x, i) => encode(x, `${path}[${i}]`));
  if (typeof v === "object" && Object.getPrototypeOf(v) === Object.prototype) {
    const out: Record<string, Json> = {};
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      if (x === undefined) continue;
      if (k.startsWith("$")) throw new SpecJsonError(`${path}.${k}: a name SpecJSON reserves`);
      out[k] = encode(x, `${path}.${k}`);
    }
    return out;
  }
  throw new SpecJsonError(`${path}: a ${typeof v} SpecJSON cannot hold`);
}

function decode(v: unknown, path: string): unknown {
  if (v === null || typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new SpecJsonError(`${path}: not a finite number`);
    return v;
  }
  if (Array.isArray(v)) return v.map((x, i) => decode(x, `${path}[${i}]`));
  if (typeof v !== "object") throw new SpecJsonError(`${path}: not JSON`);
  const entries = Object.entries(v as Record<string, unknown>);
  const tagged = entries.filter(([k]) => k.startsWith("$"));
  if (tagged.length > 0) {
    if (entries.length !== 1) throw new SpecJsonError(`${path}: a tag must stand alone`);
    const [tag, payload] = entries[0];
    if (typeof payload !== "string") throw new SpecJsonError(`${path}.${tag}: not a string`);
    switch (tag) {
      case "$bytes":
        if (!B64_RE.test(payload)) throw new SpecJsonError(`${path}.$bytes: not base64`);
        return Uint8Array.from(Buffer.from(payload, "base64"));
      case "$big":
        if (!BIG_RE.test(payload)) throw new SpecJsonError(`${path}.$big: not an integer`);
        return BigInt(payload);
      case "$date": {
        const d = new Date(payload);
        if (Number.isNaN(d.getTime()) || d.toISOString() !== payload) throw new SpecJsonError(`${path}.$date: not an ISO date`);
        return d;
      }
      default:
        throw new SpecJsonError(`${path}: unknown tag ${tag}`);
    }
  }
  const out: Record<string, unknown> = {};
  for (const [k, x] of entries) out[k] = decode(x, `${path}.${k}`);
  return out;
}

/** A CreateSpec as SpecJSON (plain JSON: JSON.stringify it as it is). */
export function toSpecJson<V extends object>(spec: CreateSpec<V>): SpecJson {
  return encode({ values: spec.values, flags: spec.flags, expiry: spec.expiry }, "spec") as unknown as SpecJson;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** SpecJSON (parsed, or a JSON string) -> the CreateSpec it encodes. Throws SpecJsonError. */
export function fromSpecJson<V extends object = Record<string, unknown>>(json: unknown): CreateSpec<V> {
  let raw = json;
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw);
    } catch {
      throw new SpecJsonError("spec: not JSON");
    }
  }
  const spec = decode(raw, "spec");
  if (!isObject(spec)) throw new SpecJsonError("spec: not an object");
  const { values, flags, expiry } = spec;
  if (!isObject(values) || values instanceof Uint8Array || values instanceof Date) throw new SpecJsonError("spec.values: not an object");
  if (!isObject(flags) || typeof flags.readonly !== "boolean" || typeof flags.permissionlessExtension !== "boolean") {
    throw new SpecJsonError("spec.flags: readonly and permissionlessExtension must be booleans");
  }
  if (!isObject(expiry) || typeof expiry.kind !== "string" || !EXPIRY_KINDS.includes(expiry.kind)) {
    throw new SpecJsonError("spec.expiry: not a known kind");
  }
  return { values: values as V, flags: flags as unknown as Flags, expiry: expiry as unknown as ExpirySpec };
}

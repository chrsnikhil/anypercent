/**
 * Decoding and validating raw `arkiv_query` rows, as every raw reader must (spec: Entities, "Every
 * raw reader validates rows itself"). Anyone can write a row a query matches, so a row is dropped,
 * and counted, when:
 * - it lacks a required column it was asked for, or carries one with the wrong type;
 * - its creator is not the pinned checker (when a checker is pinned);
 * - its `arkiv.schema` is not the expected one;
 * - (runs, when both ghost columns were asked for) it has neither or both of `log` and `log_enc`.
 *
 * JSON encodings (spec: Queries): u64 and u256 are 0x quantities, i32 a number, bool bare, dec and
 * str strings, key, addr and bytes 0x hex.
 *
 * Rabdi tags a `key` column "bytes32" in arkiv_query replies, although the SDK writes it as a key
 * (typeId 10) and calls bytes32 reserved; the SDK's own decoder reads "bytes32" as a key
 * (schema/codec.ts asTypeTag), and so does this one. Without that, every listing would be dropped.
 */
import { SCHEMA_ATTR } from "./queries.js";

export type ColumnSpec = Record<string, { type: string; required: boolean }>;
export type Value = string | number | bigint | boolean | Uint8Array;

export interface RawAttribute {
  name: string;
  type: string;
  value: unknown;
}

export interface RawEntity {
  key?: string;
  owner?: string;
  creator?: string;
  expiresAt?: string;
  attributes?: RawAttribute[];
}

export interface DecodedRow {
  key: string;
  creator: string | null;
  owner: string | null;
  expiresAt: bigint | null;
  values: Record<string, Value>;
}

const HEX_RE = /^0x[0-9a-fA-F]*$/;

/** The type tag as the node spelled it, narrowed as the SDK narrows it: "bytes32" is a key. */
export function typeTag(tag: unknown): string | undefined {
  if (typeof tag !== "string") return undefined;
  return tag === "bytes32" ? "key" : tag;
}

function decodeValue(type: string, value: unknown): Value | undefined {
  switch (type) {
    case "str":
    case "dec":
      return typeof value === "string" ? value : undefined;
    case "i32":
      return typeof value === "number" && Number.isInteger(value) ? value : undefined;
    case "bool":
      return typeof value === "boolean" ? value : undefined;
    case "u64":
    case "u256":
      return typeof value === "string" && /^0x[0-9a-fA-F]+$/.test(value) ? BigInt(value) : undefined;
    case "key":
      return typeof value === "string" && /^0x[0-9a-fA-F]{64}$/.test(value) ? value.toLowerCase() : undefined;
    case "addr":
      return typeof value === "string" && /^0x[0-9a-fA-F]{40}$/.test(value) ? value.toLowerCase() : undefined;
    case "bytes":
      return typeof value === "string" && HEX_RE.test(value) && value.length % 2 === 0
        ? Uint8Array.from(Buffer.from(value.slice(2), "hex"))
        : undefined;
    default:
      return undefined;
  }
}

/**
 * One raw row, checked: the decoded row, or why it was dropped.
 * `asked`: the attribute names the request selected (only those are required to be present).
 */
export function decodeRow(
  raw: RawEntity,
  spec: ColumnSpec,
  asked: readonly string[],
  schemaName: string,
  checker: string | null,
): { row: DecodedRow } | { dropped: string } {
  if (typeof raw !== "object" || raw === null) return { dropped: "not an entity" };
  if (typeof raw.key !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(raw.key)) return { dropped: "no key" };
  const creator = typeof raw.creator === "string" ? raw.creator.toLowerCase() : null;
  if (checker !== null && creator !== checker.toLowerCase()) return { dropped: "not created by the checker" };
  const attrs = Array.isArray(raw.attributes) ? raw.attributes : [];
  const values: Record<string, Value> = {};
  let tag: unknown;
  for (const a of attrs) {
    if (!a || typeof a.name !== "string") continue;
    if (a.name === SCHEMA_ATTR) {
      tag = a.type === "str" ? a.value : null;
      continue;
    }
    const col = spec[a.name];
    if (!col) continue; // an attribute the schema does not know: ignored, as the SDK does
    if (typeTag(a.type) !== col.type) return { dropped: `${a.name} is a ${String(a.type)}, not a ${col.type}` };
    const v = decodeValue(col.type, a.value);
    if (v === undefined) return { dropped: `${a.name} is malformed` };
    values[a.name] = v;
  }
  if (tag !== undefined && tag !== schemaName) return { dropped: "another schema" };
  for (const name of asked) {
    if (name === SCHEMA_ATTR) continue;
    const col = spec[name];
    if (col?.required && values[name] === undefined) return { dropped: `no ${name}` };
  }
  if (asked.includes("log") && asked.includes("log_enc") && (values.log === undefined) === (values.log_enc === undefined)) {
    return { dropped: "needs exactly one of log and log_enc" };
  }
  let expiresAt: bigint | null = null;
  if (typeof raw.expiresAt === "string" && /^0x[0-9a-fA-F]+$/.test(raw.expiresAt)) expiresAt = BigInt(raw.expiresAt);
  const owner = typeof raw.owner === "string" ? raw.owner.toLowerCase() : null;
  return { row: { key: raw.key.toLowerCase(), creator, owner, expiresAt, values } };
}

/** A page of raw rows, checked: the rows that fit, and how many were dropped (and why). */
export function decodePage(
  data: unknown,
  spec: ColumnSpec,
  asked: readonly string[],
  schemaName: string,
  checker: string | null,
): { rows: DecodedRow[]; dropped: number; why: string[] } {
  const rows: DecodedRow[] = [];
  const why: string[] = [];
  for (const raw of Array.isArray(data) ? data : []) {
    const r = decodeRow(raw as RawEntity, spec, asked, schemaName, checker);
    if ("row" in r) rows.push(r.row);
    else why.push(r.dropped);
  }
  return { rows, dropped: why.length, why };
}

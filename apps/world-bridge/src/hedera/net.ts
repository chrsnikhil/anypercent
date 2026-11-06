/**
 * The two ports the Hedera module talks through, so every pipeline is tested against fakes
 * (test/fake-hedera.ts) and runs live on testnet:
 *
 * - HederaPort: HCS submissions, signed by the operator (the market topic's submit key). The real
 *   one is the Hiero SDK (`@hiero-ledger/sdk` 2.90.1, the exact version `@x402/hedera` pins).
 * - MirrorPort: reads from the public mirror node over plain fetch (no key): accounts, token
 *   associations and balances, transactions, topics and their messages.
 *
 * Also the transaction-id forms and the HashScan links. Nothing here logs a key: the operator key is
 * parsed once into the SDK client and never leaves it.
 */
import {
  AccountId,
  Client,
  PrivateKey,
  Status,
  TopicMessageSubmitTransaction,
  TransactionId,
  TransactionReceiptQuery,
} from "@hiero-ledger/sdk";
import { HASHSCAN } from "../config.js";

// ---- transaction ids ---------------------------------------------------------------------------

export interface TxIdParts {
  account: string;
  seconds: string;
  nanos: string;
}

/** `0.0.X@S.N` or the mirror's `0.0.X-S-N`; null when neither. */
export function parseTxId(text: string): TxIdParts | null {
  const m = /^(0\.0\.\d{1,10})[@-](\d{1,12})[.-](\d{1,9})$/.exec(text.trim());
  if (!m) return null;
  return { account: m[1], seconds: m[2], nanos: m[3].padStart(9, "0") };
}

/** The SDK's form, `0.0.X@S.NNNNNNNNN`: what the facilitator answers and the console keeps. */
export function txAt(text: string): string | null {
  const p = parseTxId(text);
  return p ? `${p.account}@${p.seconds}.${p.nanos}` : null;
}

/** The mirror's form, `0.0.X-S-NNNNNNNNN` (its /transactions/<id> takes only this one). */
export function txDash(text: string): string | null {
  const p = parseTxId(text);
  return p ? `${p.account}-${p.seconds}-${p.nanos}` : null;
}

/** When the transaction's valid window opened, in ms. */
export function txValidStartMs(text: string): number | null {
  const p = parseTxId(text);
  return p ? Number(p.seconds) * 1000 + Math.floor(Number(p.nanos) / 1e6) : null;
}

export const hashscan = {
  /** A transaction, by either id form or by consensus timestamp. */
  tx: (id: string) => `${HASHSCAN}/transaction/${txDash(id) ?? id}`,
  /** One topic message, by its consensus timestamp (from the mirror). */
  message: (consensusAt: string) => `${HASHSCAN}/transaction/${consensusAt}/message`,
  topic: (id: string) => `${HASHSCAN}/topic/${id}`,
  account: (id: string) => `${HASHSCAN}/account/${id}`,
  token: (id: string) => `${HASHSCAN}/token/${id}`,
};

// ---- HCS -------------------------------------------------------------------------------------

export interface HcsReceipt {
  /** The topic sequence number, as a decimal string (it arrives as a Long). */
  seq: string;
  /** The topic running hash after this message (48 bytes, hex). */
  runningHash: string;
}

export interface SubmitAccepted {
  /** The submission's transaction id, `0.0.X@S.N`. */
  tx: string;
  /** Its receipt: resolves once it reached consensus with SUCCESS, rejects otherwise. */
  receipt: Promise<HcsReceipt>;
}

export interface HederaPort {
  /**
   * Submit one single-chunk message to a topic. Resolves once a node accepted it (the SDK's
   * `execute()` returned); rejects when it was refused. The receipt is awaited separately.
   */
  submit(topic: string, message: Uint8Array): Promise<SubmitAccepted>;
  /** The receipt of an earlier submission if it landed with SUCCESS; null when it did not (or not yet). */
  receiptOf(tx: string): Promise<HcsReceipt | null>;
}

/** HCS refused a message, or could not be reached. */
export class HederaError extends Error {}

// ---- the mirror node -------------------------------------------------------------------------

export interface MirrorKey {
  type: string;
  key: string;
}

export interface MirrorAccount {
  account: string;
  /** Tinybars. */
  balance: bigint;
  /** -1: unlimited auto-association; 0: none. */
  maxAutoAssociations: number;
  key: MirrorKey | null;
  evmAddress: string | null;
  deleted: boolean;
}

export interface MirrorTokenTransfer {
  token: string;
  account: string;
  amount: bigint;
}

export interface MirrorTx {
  /** Dash form. */
  id: string;
  consensusAt: string;
  result: string;
  name: string;
  entityId: string | null;
  tokenTransfers: MirrorTokenTransfer[];
  chargedFee: bigint;
}

export interface MirrorMessage {
  topic: string;
  seq: string;
  consensusAt: string;
  message: Uint8Array;
  /** Hex. */
  runningHash: string;
  runningHashVersion: number;
  payer: string;
  /** The submitting transaction's id (dash form), from chunk_info, when the mirror gives it. */
  tx: string | null;
}

export interface MirrorTopic {
  topic: string;
  memo: string;
  adminKey: MirrorKey | null;
  submitKey: MirrorKey | null;
  feeScheduleKey: MirrorKey | null;
  customFees: unknown[];
  deleted: boolean;
}

export interface MirrorToken {
  token: string;
  symbol: string;
  name: string;
  decimals: number;
  type: string;
}

export interface MirrorPort {
  account(id: string): Promise<MirrorAccount | null>;
  /**
   * Can this account receive the token? The facilitator's own preflight rule: associated with it,
   * or unlimited (-1) auto-association, or a free auto-association slot.
   */
  associated(account: string, token: string): Promise<boolean>;
  /** The account's balance of the token, or null when it is not associated with it. */
  tokenBalance(account: string, token: string): Promise<bigint | null>;
  /** A transaction by id (either form); null while the mirror has not indexed it (404). */
  transaction(txId: string): Promise<MirrorTx | null>;
  topic(id: string): Promise<MirrorTopic | null>;
  /** Messages of a topic, oldest first, after a sequence number (exclusive). */
  topicMessages(topic: string, opts?: { afterSeq?: string; limit?: number }): Promise<MirrorMessage[]>;
  /** One message by its consensus timestamp. */
  messageAt(consensusAt: string): Promise<MirrorMessage | null>;
  token(id: string): Promise<MirrorToken | null>;
}

/** The mirror could not be reached or answered an error other than 404. */
export class MirrorError extends Error {}

/** Does this transaction move exactly `amount` of `token` from `from` to `to` (and nothing else of it)? */
export function transfersMatch(tx: MirrorTx, token: string, from: string, to: string, amount: bigint): boolean {
  const rows = tx.tokenTransfers.filter((t) => t.token === token);
  const net = new Map<string, bigint>();
  for (const r of rows) net.set(r.account, (net.get(r.account) ?? 0n) + r.amount);
  if (net.get(from) !== -amount || net.get(to) !== amount) return false;
  for (const [acct, v] of net) if (acct !== from && acct !== to && v !== 0n) return false;
  return true;
}

function mirrorKey(raw: unknown): MirrorKey | null {
  const k = raw as { _type?: unknown; key?: unknown } | null;
  return k && typeof k._type === "string" && typeof k.key === "string" ? { type: k._type, key: k.key } : null;
}

function b64hex(text: unknown): string {
  return typeof text === "string" ? Buffer.from(text, "base64").toString("hex") : "";
}

function toMessage(raw: Record<string, unknown>): MirrorMessage {
  const chunk = raw.chunk_info as { initial_transaction_id?: { account_id?: string; transaction_valid_start?: string } } | null;
  const init = chunk?.initial_transaction_id;
  const tx =
    init && typeof init.account_id === "string" && typeof init.transaction_valid_start === "string"
      ? txDash(`${init.account_id}@${init.transaction_valid_start}`)
      : null;
  return {
    topic: String(raw.topic_id),
    seq: String(raw.sequence_number),
    consensusAt: String(raw.consensus_timestamp),
    message: Uint8Array.from(Buffer.from(String(raw.message ?? ""), "base64")),
    runningHash: b64hex(raw.running_hash),
    runningHashVersion: Number(raw.running_hash_version ?? 0),
    payer: String(raw.payer_account_id ?? ""),
    tx,
  };
}

/** The public mirror node over plain fetch. `base` is HEDERA_MIRROR (without /api/v1). */
export class RestMirror implements MirrorPort {
  private readonly api: string;

  constructor(base: string, private readonly timeoutMs = 8000) {
    this.api = `${base.replace(/\/+$/, "")}/api/v1`;
  }

  private async get<T>(path: string): Promise<T | null> {
    let res: Response;
    try {
      res = await fetch(`${this.api}${path}`, { signal: AbortSignal.timeout(this.timeoutMs), headers: { accept: "application/json" } });
    } catch (err) {
      throw new MirrorError(`mirror unreachable (${(err as Error)?.name ?? "error"})`);
    }
    if (res.status === 404) {
      await res.body?.cancel();
      return null;
    }
    if (!res.ok) {
      await res.body?.cancel();
      throw new MirrorError(`mirror answered ${res.status}`);
    }
    try {
      return (await res.json()) as T;
    } catch {
      throw new MirrorError("mirror answered something that is not JSON");
    }
  }

  async account(id: string): Promise<MirrorAccount | null> {
    const raw = await this.get<Record<string, any>>(`/accounts/${encodeURIComponent(id)}?transactions=false`);
    if (!raw) return null;
    return {
      account: String(raw.account),
      balance: BigInt(raw.balance?.balance ?? 0),
      maxAutoAssociations: Number(raw.max_automatic_token_associations ?? 0),
      key: mirrorKey(raw.key),
      evmAddress: typeof raw.evm_address === "string" ? raw.evm_address : null,
      deleted: raw.deleted === true,
    };
  }

  async tokenBalance(account: string, token: string): Promise<bigint | null> {
    const raw = await this.get<{ tokens?: Array<{ token_id: string; balance: number | string }> }>(
      `/accounts/${encodeURIComponent(account)}/tokens?token.id=${encodeURIComponent(token)}`,
    );
    const row = raw?.tokens?.find((t) => t.token_id === token);
    return row ? BigInt(row.balance) : null;
  }

  async associated(account: string, token: string): Promise<boolean> {
    if ((await this.tokenBalance(account, token)) !== null) return true;
    const acct = await this.account(account);
    if (!acct || acct.deleted) return false;
    if (acct.maxAutoAssociations === -1) return true;
    if (acct.maxAutoAssociations <= 0) return false;
    let used = 0;
    let next: string | null = `/accounts/${encodeURIComponent(account)}/tokens?limit=100`;
    for (let pages = 0; next && pages < 20; pages++) {
      const page: { tokens?: Array<{ automatic_association?: boolean }>; links?: { next?: string | null } } | null = await this.get(next);
      used += (page?.tokens ?? []).filter((t) => t.automatic_association === true).length;
      if (used >= acct.maxAutoAssociations) return false;
      const link: string | null = page?.links?.next ?? null;
      next = link ? link.replace(/^\/api\/v1/, "") : null;
    }
    return used < acct.maxAutoAssociations;
  }

  async transaction(txId: string): Promise<MirrorTx | null> {
    const dash = txDash(txId);
    if (!dash) return null;
    const raw = await this.get<{ transactions?: Array<Record<string, any>> }>(`/transactions/${dash}`);
    const all = raw?.transactions ?? [];
    // The user transaction is nonce 0 and not scheduled; prefer its SUCCESS entry over a duplicate's.
    const own = all.filter((t) => Number(t.nonce ?? 0) === 0 && t.scheduled !== true);
    const pick = own.find((t) => t.result === "SUCCESS") ?? own[0];
    if (!pick) return null;
    return {
      id: String(pick.transaction_id),
      consensusAt: String(pick.consensus_timestamp),
      result: String(pick.result),
      name: String(pick.name),
      entityId: typeof pick.entity_id === "string" ? pick.entity_id : null,
      tokenTransfers: (Array.isArray(pick.token_transfers) ? pick.token_transfers : []).map((t: any) => ({
        token: String(t.token_id),
        account: String(t.account),
        amount: BigInt(t.amount),
      })),
      chargedFee: BigInt(pick.charged_tx_fee ?? 0),
    };
  }

  async topic(id: string): Promise<MirrorTopic | null> {
    const raw = await this.get<Record<string, any>>(`/topics/${encodeURIComponent(id)}`);
    if (!raw) return null;
    const fees = raw.custom_fees as { fixed_fees?: unknown[] } | null;
    return {
      topic: String(raw.topic_id),
      memo: String(raw.memo ?? ""),
      adminKey: mirrorKey(raw.admin_key),
      submitKey: mirrorKey(raw.submit_key),
      feeScheduleKey: mirrorKey(raw.fee_schedule_key),
      customFees: Array.isArray(fees?.fixed_fees) ? fees.fixed_fees : [],
      deleted: raw.deleted === true,
    };
  }

  async topicMessages(topic: string, opts: { afterSeq?: string; limit?: number } = {}): Promise<MirrorMessage[]> {
    const q = new URLSearchParams({ limit: String(opts.limit ?? 100), order: "asc" });
    if (opts.afterSeq !== undefined) q.set("sequencenumber", `gt:${opts.afterSeq}`);
    const raw = await this.get<{ messages?: Array<Record<string, unknown>> }>(`/topics/${encodeURIComponent(topic)}/messages?${q}`);
    return (raw?.messages ?? []).map(toMessage);
  }

  async messageAt(consensusAt: string): Promise<MirrorMessage | null> {
    const raw = await this.get<Record<string, unknown>>(`/topics/messages/${encodeURIComponent(consensusAt)}`);
    return raw ? toMessage(raw) : null;
  }

  async token(id: string): Promise<MirrorToken | null> {
    const raw = await this.get<Record<string, any>>(`/tokens/${encodeURIComponent(id)}`);
    if (!raw) return null;
    return {
      token: String(raw.token_id),
      symbol: String(raw.symbol ?? ""),
      name: String(raw.name ?? ""),
      decimals: Number(raw.decimals),
      type: String(raw.type ?? ""),
    };
  }
}

// ---- the SDK client for HCS ------------------------------------------------------------------

/** A DER private key from .env (with or without 0x). Raw hex is never accepted: the SDK would read it as ED25519. */
export function parseDerKey(text: string): PrivateKey {
  return PrivateKey.fromStringDer(text.replace(/^0x/, ""));
}

export interface SdkHederaOptions {
  operatorId: string;
  /** DER hex. Parsed here, never kept as text. */
  operatorKey: string;
  /** For a receipt older than the nodes keep (about 3 minutes): find the message on the mirror. */
  mirror?: MirrorPort;
  requestTimeoutMs?: number;
}

/** HCS on testnet through the Hiero SDK, paid and signed by the operator. */
export class SdkHedera implements HederaPort {
  private readonly client: Client;
  private readonly timeoutMs: number;

  constructor(private readonly opts: SdkHederaOptions) {
    this.client = Client.forTestnet();
    this.client.setOperator(AccountId.fromString(opts.operatorId), parseDerKey(opts.operatorKey));
    this.timeoutMs = opts.requestTimeoutMs ?? 10_000;
  }

  /** The operator's public key, DER hex (for the topic's submit key check). */
  get operatorPublicKey(): string {
    return this.client.operatorPublicKey?.toStringDer() ?? "";
  }

  get sdkClient(): Client {
    return this.client;
  }

  async submit(topic: string, message: Uint8Array): Promise<SubmitAccepted> {
    let tx: string;
    let receipt: Promise<HcsReceipt>;
    try {
      const resp = await new TopicMessageSubmitTransaction()
        .setTopicId(topic)
        .setMessage(message)
        .setMaxChunks(1)
        .execute(this.client, this.timeoutMs);
      tx = resp.transactionId.toString();
      receipt = resp.getReceipt(this.client).then((r) => {
        if (r.topicSequenceNumber === null || r.topicRunningHash === null) throw new HederaError("receipt without a sequence number");
        return { seq: r.topicSequenceNumber.toString(), runningHash: Buffer.from(r.topicRunningHash).toString("hex") };
      });
    } catch (err) {
      throw new HederaError(shortSdkError(err));
    }
    receipt.catch(() => undefined);
    return { tx, receipt };
  }

  async receiptOf(tx: string): Promise<HcsReceipt | null> {
    try {
      const r = await new TransactionReceiptQuery().setTransactionId(TransactionId.fromString(tx)).execute(this.client);
      if (r.status === Status.Success && r.topicSequenceNumber !== null && r.topicRunningHash !== null) {
        return { seq: r.topicSequenceNumber.toString(), runningHash: Buffer.from(r.topicRunningHash).toString("hex") };
      }
    } catch {
      // Not on the nodes (never landed, failed, or older than they keep): ask the mirror.
    }
    if (!this.opts.mirror) return null;
    try {
      const m = await this.opts.mirror.transaction(tx);
      if (!m || m.result !== "SUCCESS" || m.name !== "CONSENSUSSUBMITMESSAGE") return null;
      const msg = await this.opts.mirror.messageAt(m.consensusAt);
      return msg ? { seq: msg.seq, runningHash: msg.runningHash } : null;
    } catch {
      return null;
    }
  }

  close(): void {
    this.client.close();
  }
}

/** The SDK's error, cut to its status name or first line (no key or URL ever appears in these). */
export function shortSdkError(err: unknown): string {
  const e = err as { status?: { toString(): string }; message?: string; name?: string };
  if (e?.status) return String(e.status.toString());
  return String(e?.message ?? e?.name ?? err)
    .split("\n")[0]
    .replace(/https?:\/\/\S+/g, "<url>")
    .slice(0, 160);
}

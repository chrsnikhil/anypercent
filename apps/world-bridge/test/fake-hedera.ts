/**
 * An in-memory Hedera for the Hedera tests: HCS (FakeHedera, behind HederaPort) and the mirror node
 * (FakeMirror, behind MirrorPort). Nothing here touches the network. A shared `events` list records
 * the order things happened in (INTENT accepted, payment signed, ...), so tests can assert it.
 */
import { createHash } from "node:crypto";
import { HederaError, txDash, type HcsReceipt, type HederaPort, type MirrorAccount, type MirrorMessage, type MirrorPort, type MirrorToken, type MirrorTopic, type MirrorTx, type SubmitAccepted } from "../src/hedera/net.js";

export const USDC = "0.0.429274";
export const OPERATOR = "0.0.7001";
export const AGENT = "0.0.6001234";
export const SELLER_ACCT = "0.0.5123456";
export const TOPIC = "0.0.8001";
export const FEE_PAYER = "0.0.9185802";
export const FEE_PAYER_2 = "0.0.7162784";
/** The house account BOT listings pay (associated with USDC). */
export const HOUSE = "0.0.4004004";

export interface SentMessage {
  topic: string;
  json: Record<string, any>;
  bytes: Uint8Array;
  tx: string;
  seq: string;
  landed: boolean;
}

let txCounter = 0;

export class FakeHedera implements HederaPort {
  messages: SentMessage[] = [];
  private seqs = new Map<string, number>();
  /** Refuse the next n submissions (precheck). */
  refuse = 0;
  /** Accept, but never give a receipt (until `land()`). */
  holdReceipts = false;
  private held: Array<{ m: SentMessage; resolve: (r: HcsReceipt) => void }> = [];

  constructor(private readonly events: string[] = [], private readonly mirror?: FakeMirror) {}

  async submit(topic: string, message: Uint8Array): Promise<SubmitAccepted> {
    if (this.refuse > 0) {
      this.refuse -= 1;
      throw new HederaError("INVALID_TOPIC_ID");
    }
    if (message.length > 1024) throw new HederaError("over one chunk");
    txCounter += 1;
    const tx = `${OPERATOR}@1800000000.${String(txCounter).padStart(9, "0")}`;
    const seq = (this.seqs.get(topic) ?? 0) + 1;
    this.seqs.set(topic, seq);
    const json = JSON.parse(Buffer.from(message).toString("utf8"));
    const m: SentMessage = { topic, json, bytes: message, tx, seq: String(seq), landed: false };
    this.messages.push(m);
    this.events.push(`hcs:${json.t}`);
    const receipt = this.holdReceipts
      ? new Promise<HcsReceipt>((resolve) => this.held.push({ m, resolve }))
      : Promise.resolve(this.landMessage(m));
    return { tx, receipt };
  }

  private landMessage(m: SentMessage): HcsReceipt {
    m.landed = true;
    const runningHash = createHash("sha384").update(m.bytes).digest("hex");
    this.mirror?.addMessage(m.topic, m.seq, m.bytes, runningHash, m.tx);
    return { seq: m.seq, runningHash };
  }

  /** Let every held receipt come back now. */
  land(): void {
    for (const h of this.held.splice(0)) h.resolve(this.landMessage(h.m));
  }

  async receiptOf(tx: string): Promise<HcsReceipt | null> {
    const m = this.messages.find((x) => x.tx === tx);
    if (!m || !m.landed) return null;
    return { seq: m.seq, runningHash: createHash("sha384").update(m.bytes).digest("hex") };
  }

  of(type: string): SentMessage[] {
    return this.messages.filter((m) => m.json.t === type);
  }
}

interface StoredTx {
  tx: MirrorTx;
  /** Hidden until this many reads of it have happened (mirror lag). */
  hiddenReads: number;
}

export class FakeMirror implements MirrorPort {
  accounts = new Map<string, MirrorAccount>();
  /** account|token -> balance (present = associated). */
  holdings = new Map<string, bigint>();
  txs = new Map<string, StoredTx>();
  messages: MirrorMessage[] = [];
  topics = new Map<string, MirrorTopic>();
  tokens = new Map<string, MirrorToken>([[USDC, { token: USDC, symbol: "USDC", name: "USD Coin", decimals: 6, type: "FUNGIBLE_COMMON" }]]);
  down = false;
  reads = { associated: 0, tokenBalance: 0, transaction: 0 };

  constructor() {
    this.addAccount(OPERATOR, { balance: 1000n * 100_000_000n });
    this.addAccount(AGENT, { balance: 5n * 100_000_000n, maxAuto: 0 });
    this.holdings.set(`${AGENT}|${USDC}`, 20_000_000n);
    this.addAccount(SELLER_ACCT, { balance: 0n, maxAuto: 0 });
    this.holdings.set(`${SELLER_ACCT}|${USDC}`, 0n);
    this.addAccount(HOUSE, { balance: 2n * 100_000_000n, maxAuto: 0 });
    this.holdings.set(`${HOUSE}|${USDC}`, 0n);
  }

  addAccount(id: string, o: { balance?: bigint; maxAuto?: number } = {}): void {
    this.accounts.set(id, { account: id, balance: o.balance ?? 0n, maxAutoAssociations: o.maxAuto ?? 0, key: null, evmAddress: null, deleted: false });
  }

  private check(): void {
    if (this.down) throw new Error("mirror down");
  }

  async account(id: string): Promise<MirrorAccount | null> {
    this.check();
    return this.accounts.get(id) ?? null;
  }

  async associated(account: string, token: string): Promise<boolean> {
    this.check();
    this.reads.associated += 1;
    if (this.holdings.has(`${account}|${token}`)) return true;
    const a = this.accounts.get(account);
    return a?.maxAutoAssociations === -1;
  }

  async tokenBalance(account: string, token: string): Promise<bigint | null> {
    this.check();
    this.reads.tokenBalance += 1;
    return this.holdings.get(`${account}|${token}`) ?? null;
  }

  /** Put a transaction on the mirror, visible after `hiddenReads` reads of it. */
  addTx(txId: string, result: string, transfers: Array<{ account: string; amount: bigint }>, hiddenReads = 0, token = USDC): void {
    const id = txDash(txId) as string;
    this.txs.set(id, {
      hiddenReads,
      tx: { id, consensusAt: "1800000001.000000001", result, name: "CRYPTOTRANSFER", entityId: null, tokenTransfers: transfers.map((t) => ({ token, account: t.account, amount: t.amount })), chargedFee: 1_000_000n },
    });
    if (result === "SUCCESS") {
      for (const t of transfers) {
        const k = `${t.account}|${token}`;
        this.holdings.set(k, (this.holdings.get(k) ?? 0n) + t.amount);
      }
    }
  }

  async transaction(txId: string): Promise<MirrorTx | null> {
    this.check();
    this.reads.transaction += 1;
    const s = this.txs.get(txDash(txId) ?? "");
    if (!s) return null;
    if (s.hiddenReads > 0) {
      s.hiddenReads -= 1;
      return null;
    }
    return s.tx;
  }

  addMessage(topic: string, seq: string, message: Uint8Array, runningHash: string, tx: string): void {
    this.messages.push({ topic, seq, consensusAt: `1800000100.${seq.padStart(9, "0")}`, message, runningHash, runningHashVersion: 3, payer: OPERATOR, tx: txDash(tx) });
  }

  async topic(id: string): Promise<MirrorTopic | null> {
    this.check();
    return this.topics.get(id) ?? null;
  }

  async topicMessages(topic: string, opts: { afterSeq?: string; limit?: number } = {}): Promise<MirrorMessage[]> {
    this.check();
    const after = Number(opts.afterSeq ?? "0");
    return this.messages.filter((m) => m.topic === topic && Number(m.seq) > after).slice(0, opts.limit ?? 100);
  }

  async messageAt(consensusAt: string): Promise<MirrorMessage | null> {
    this.check();
    return this.messages.find((m) => m.consensusAt === consensusAt) ?? null;
  }

  async token(id: string): Promise<MirrorToken | null> {
    this.check();
    return this.tokens.get(id) ?? null;
  }
}

/** A fake clock: sleep() moves it forward at once, so 135 s windows pass in milliseconds. */
export function fakeClock(start = Date.now()) {
  const clock = {
    ms: start,
    now: () => clock.ms,
    sleep: async (ms: number) => {
      clock.ms += ms;
      await new Promise((r) => setImmediate(r));
    },
  };
  return clock;
}

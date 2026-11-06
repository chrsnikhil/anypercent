/**
 * The market topic's messages (spec: HCS): UTF-8 JSON, keys in the order shown, no spaces, `v`
 * first. Every message is one chunk: each builder asserts it is at most 1024 bytes, and the
 * submitter sets setMaxChunks(1) as well. No names, nullifiers, jtis, session ids or console ids:
 * books, runner ids, keys and account ids are public already. Sequence numbers come back as a
 * Long and are converted with .toString() before they go into JSON (as numbers here).
 *
 *   LISTING  the record step: what the seller approved in World App, word for word
 *   INTENT   PB's purchase, submitted before the payment is signed; with the scout's pick (which
 *            model, the laps it compared, its reason) when PB's scout chose this ghost
 *   RECEIPT  after settlement, once the mirror node shows the transfer
 *   HOUSE    a BOT batch the house owner approved in World App, word for word, before its rows
 *   SMOKE    hedera:smoke's test message
 *
 * START and END (the Live-run stretch, cut item 1) are not built.
 */

/** HCS's per-message (per-chunk) limit. */
export const HCS_MAX_BYTES = 1024;

export class MessageTooLarge extends Error {}

function encode(obj: Record<string, unknown>): Uint8Array {
  const bytes = Buffer.from(JSON.stringify(obj), "utf8");
  if (bytes.length > HCS_MAX_BYTES) throw new MessageTooLarge(`${String(obj.t)} is ${bytes.length} B, over ${HCS_MAX_BYTES} B`);
  return Uint8Array.from(bytes);
}

/** A Long (or anything with toString) or a decimal string -> a JSON number. */
export function seqNumber(seq: { toString(): string } | string | null | undefined): number | null {
  if (seq === null || seq === undefined) return null;
  const n = Number(seq.toString());
  return Number.isSafeInteger(n) ? n : null;
}

export interface ListingMessage {
  book: string;
  runner: string;
  game: string;
  frames: number;
  /** "0.10" */
  price: string;
  pay_to?: string;
  /** The text World App showed, word for word. */
  action: string;
}

export function listingMessage(m: ListingMessage): Uint8Array {
  return encode({
    v: 1,
    t: "LISTING",
    book: m.book,
    runner: m.runner,
    game: m.game,
    frames: m.frames,
    price: m.price,
    ...(m.pay_to ? { pay_to: m.pay_to } : {}),
    action: m.action,
  });
}

export interface IntentMessage {
  id: string;
  buyer: string;
  seller: string;
  game: string;
  listing: string;
  run: string;
  log_h: string;
  pay_to: string;
  /** "0.10" */
  amount: string;
  asset: string;
  /** PB's reason in numbers: YOU's best (null when none) and the target's time, in frames. */
  why: { you: number | null; target: number };
  /** What the buyer book has left today after this purchase, "0.90". */
  left_today: string;
  /** PB's scout picked this ghost: which model (null for the board's rule), the laps, the reason. */
  scout?: IntentScout;
}

export interface IntentScout {
  id: string;
  by: "model" | "rule";
  model: string | null;
  /** The lap the reason is about (null when there were no laps to compare). */
  lap: number | null;
  /** YOU's and the ghost's lap splits, in frames. */
  you: number[];
  it: number[];
  /** "model": the model's own sentence passed the fact check; "template": ours. */
  text: "model" | "template";
  /** The reason the console showed, at most 110 printable ASCII characters. */
  why: string;
}

export function intentMessage(m: IntentMessage): Uint8Array {
  return encode({
    v: 1,
    t: "INTENT",
    id: m.id,
    buyer: m.buyer,
    seller: m.seller,
    game: m.game,
    listing: m.listing,
    run: m.run,
    log_h: m.log_h,
    pay_to: m.pay_to,
    amount: m.amount,
    asset: m.asset,
    why: { you: m.why.you, target: m.why.target },
    ...(m.scout
      ? {
          scout: {
            id: m.scout.id,
            by: m.scout.by,
            model: m.scout.model,
            lap: m.scout.lap,
            you: m.scout.you,
            it: m.scout.it,
            text: m.scout.text,
            why: m.scout.why,
          },
        }
      : {}),
    left_today: m.left_today,
  });
}

export interface HouseMessage {
  batch: string;
  /** HOUSE_OWNER_BOOK: whose World approval published it. */
  book: string;
  game: string;
  n: number;
  /** "0.10" */
  price: string;
  pay_to: string;
  /** The text World App showed, word for word. */
  action: string;
}

export function houseMessage(m: HouseMessage): Uint8Array {
  return encode({ v: 1, t: "HOUSE", batch: m.batch, book: m.book, game: m.game, n: m.n, price: m.price, pay_to: m.pay_to, action: m.action });
}

export interface ReceiptMessage {
  id: string;
  /** INTENT's sequence number; null if its receipt never came. */
  intent: number | null;
  /** The payment's transaction id (its account is the facilitator's fee payer). */
  tx: string;
  from: string;
  pay_to: string;
  amount: string;
  asset: string;
  run: string;
  /** "SUCCESS" once the mirror showed both token-transfer rows; "unseen" after 60 s without. */
  mirror: "SUCCESS" | "unseen";
  late: boolean;
}

export function receiptMessage(m: ReceiptMessage): Uint8Array {
  return encode({
    v: 1,
    t: "RECEIPT",
    id: m.id,
    intent: m.intent,
    tx: m.tx,
    from: m.from,
    pay_to: m.pay_to,
    amount: m.amount,
    asset: m.asset,
    run: m.run,
    mirror: m.mirror,
    late: m.late,
  });
}

export function smokeMessage(n: number, at: string): Uint8Array {
  return encode({ v: 1, t: "SMOKE", n, at });
}

/** A message read back from the mirror, if it is one of ours (v 1, a known type). */
export function parseMessage(bytes: Uint8Array): Record<string, unknown> | null {
  try {
    const obj = JSON.parse(Buffer.from(bytes).toString("utf8")) as Record<string, unknown>;
    if (obj && obj.v === 1 && typeof obj.t === "string") return obj;
  } catch {
    // not ours
  }
  return null;
}

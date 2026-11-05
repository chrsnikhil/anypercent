import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";
import { BOOK_CHARS, bookCandidate, hmacHex, jtiKey, nullifierKey, runnerId, subKey } from "../src/hmac.js";
import { Store } from "../src/store.js";
import { SECRET, tempDir } from "./helpers.js";

describe("HMACs", () => {
  it("is HMAC-SHA256 under the server secret, with a label", () => {
    const want = createHmac("sha256", SECRET).update("runner\u0000value").digest("hex");
    assert.equal(hmacHex(SECRET, "runner", "value"), want);
  });

  it("runner_id is the truncated HMAC: 16 hex chars, stable, secret-dependent", () => {
    const a = runnerId(SECRET, "nil_00ab");
    assert.match(a, /^[0-9a-f]{16}$/);
    assert.equal(a, runnerId(SECRET, "nil_00ab"));
    assert.equal(a, hmacHex(SECRET, "runner", "nil_00ab").slice(0, 16));
    assert.notEqual(a, runnerId(`${SECRET}-other`, "nil_00ab"));
    assert.notEqual(a, runnerId(SECRET, "nil_00ac"));
  });

  it("labels keep the uses apart: the same input never gives the same key twice", () => {
    const v = "same-input";
    const keys = new Set([
      hmacHex(SECRET, "runner", v),
      nullifierKey(SECRET, "act", v),
      subKey(SECRET, "act", v),
      hmacHex(SECRET, "book", v),
    ]);
    assert.equal(keys.size, 4);
  });

  it("never contains the raw value", () => {
    const sub = "raw-subject-should-not-appear";
    assert.ok(!subKey(SECRET, "https://iss", sub).includes(sub));
    assert.match(subKey(SECRET, "https://iss", sub), /^[0-9a-f]{64}$/);
  });

  it("sub keys are per (iss, sub)", () => {
    assert.notEqual(subKey(SECRET, "https://a", "s"), subKey(SECRET, "https://b", "s"));
  });

  it("jti keys are per issuer", () => {
    assert.notEqual(jtiKey("https://a", "j"), jtiKey("https://b", "j"));
    assert.equal(jtiKey("https://a", "j"), jtiKey("https://a", "j"));
  });

  it("book ids are ANY- plus 3 console-safe characters, stable per input", () => {
    const n = nullifierKey(SECRET, "anypercent-record-book", "nil_01");
    const b = bookCandidate(SECRET, n, 0);
    assert.match(b, new RegExp(`^ANY-[${BOOK_CHARS}]{3}$`));
    assert.equal(b, bookCandidate(SECRET, n, 0));
    assert.match(bookCandidate(SECRET, n, 64), new RegExp(`^ANY-[${BOOK_CHARS}]{4}$`));
  });
});

describe("Store: nullifier -> book", () => {
  it("one World ID gets one book; the same human again gets the same book back (id_dup)", () => {
    const store = new Store(tempDir(), SECRET);
    const n = nullifierKey(SECRET, "act", "nil_aa");
    const first = store.claimBook(n, "Selfie Check", "r1", 1);
    assert.equal(first.created, true);
    const again = store.claimBook(n, "Orb", "r1", 2);
    assert.equal(again.created, false);
    assert.equal(again.record.book, first.record.book);
    assert.equal(again.record.credential, "Selfie Check");
  });

  it("different humans get different books, even when their first candidates collide", () => {
    const store = new Store(tempDir(), SECRET);
    const a = nullifierKey(SECRET, "act", "nil_a");
    // Find a second nullifier whose first candidate collides with a's.
    const target = bookCandidate(SECRET, a, 0);
    let b = "";
    for (let i = 0; i < 200_000; i++) {
      const k = nullifierKey(SECRET, "act", `nil_${i}`);
      if (k !== a && bookCandidate(SECRET, k, 0) === target) {
        b = k;
        break;
      }
    }
    assert.ok(b, "found a colliding nullifier");
    const ra = store.claimBook(a, "Orb", "ra", 1).record.book;
    const rb = store.claimBook(b, "Orb", "rb", 1).record.book;
    assert.equal(ra, target);
    assert.notEqual(rb, ra);
    assert.equal(store.claimBook(b, "Orb", "rb", 2).record.book, rb, "and stays stable");
  });

  it("persists across restarts and stores no raw nullifier", () => {
    const dir = tempDir();
    const n = nullifierKey(SECRET, "act", "nil_raw_value_xyz");
    const book = new Store(dir, SECRET).claimBook(n, "Orb", "r", 1).record.book;
    const reopened = new Store(dir, SECRET);
    assert.equal(reopened.bookFor(n)?.book, book);
    const disk = readFileSync(join(dir, "state.json"), "utf8");
    assert.ok(!disk.includes("nil_raw_value_xyz"));
  });

  it("a book id already bound by an approval is never handed to a new human", () => {
    const store = new Store(tempDir(), SECRET);
    const n = nullifierKey(SECRET, "act", "nil_q");
    const first = bookCandidate(SECRET, n, 0);
    store.bindOrCheck(first, "some-sub-key", 1);
    assert.notEqual(store.claimBook(n, "Orb", "r", 2).record.book, first);
  });
});

describe("Store: book -> bound account (trust on first use) and jtis", () => {
  it("binds on first approval, then matches or refuses", () => {
    const store = new Store(tempDir(), SECRET);
    assert.equal(store.checkBinding("ANY-AAA", "s1"), "bound", "read-only check binds nothing");
    assert.equal(store.bindOrCheck("ANY-AAA", "s1", 1), "bound");
    assert.equal(store.bindOrCheck("ANY-AAA", "s1", 2), "match");
    assert.equal(store.bindOrCheck("ANY-AAA", "s2", 3), "mismatch");
    assert.equal(store.checkBinding("ANY-AAA", "s2"), "mismatch");
    assert.equal(store.bindOrCheck("ANY-BBB", "s2", 4), "bound", "books are independent");
  });

  it("a jti is consumed exactly once, across restarts", () => {
    const dir = tempDir();
    const store = new Store(dir, SECRET);
    assert.equal(store.useJti("k", 1), true);
    assert.equal(store.useJti("k", 2), false);
    assert.equal(new Store(dir, SECRET).useJti("k", 3), false);
  });
});

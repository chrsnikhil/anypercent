/**
 * A console's Arkiv wallet is part of its World-approved link (spec: Console registration): the
 * console reports its wallet when it registers (GET /console/{id}?wallet=0x...), the link text
 * names it, and only an approved link makes it the wallet the bridge stamps runs from. A different
 * wallet reported later is pending until the owner approves a new link; a release clears it.
 */
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { afterEach, describe, it } from "node:test";
import { consoleKey, Consoles, linkText, shortWallet, type OpView } from "../src/consoles.js";
import { nullifierKey } from "../src/hmac.js";
import { buildServer, makeHealth } from "../src/server.js";
import { Store } from "../src/store.js";
import { FakeApprovals } from "./fake-approvals.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const PI = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const LAPTOP = "ffeeddccbbaa99887766554433221100";
const A = "0x1A2B3c4d5e6f708192a3b4c5d6e7f8091a2b9F3E";
const B = "0x9999888877776666555544443333222211110000";

let live: Array<{ stopAll(): void }> = [];
afterEach(() => {
  for (const s of live) s.stopAll();
  live = [];
});

let n = 0;
function setup() {
  n += 1;
  const store = new Store(tempDir(), SECRET);
  const lines: string[] = [];
  const approvals = new FakeApprovals(store);
  const consoles = new Consoles({ store, secret: SECRET, approvals, pollMs: 2, log: (l) => lines.push(l) });
  live.push(consoles);
  const book = store.claimBook(nullifierKey(SECRET, "act", `wallet-${n}`), "Orb", "0123456789abcdef", 1, "session_w").record.book;
  return { store, lines, approvals, consoles, book };
}

async function op(c: Consoles, body: Record<string, unknown>): Promise<OpView> {
  const { id } = await c.startOp(body);
  await waitFor(() => c.opView(id)?.stage === "done");
  return c.opView(id)!;
}

describe("the link text names the console's wallet", () => {
  it("0x and 4 hex, an ellipsis, the last 4 hex, all lowercase", () => {
    assert.equal(shortWallet(A), "0x1a2b…9f3e");
    assert.equal(
      linkText("C-FMHE", "ANY-6PS", A),
      "Link console C-FMHE (wallet 0x1a2b…9f3e) to record book ANY-6PS: PB on it spends this book's coach budget",
    );
  });

  it("a console that reports no wallet is linked with the text it always had (it can spend, never be stamped)", () => {
    assert.equal(linkText("C-FMHE", "ANY-6PS", null), "Link console C-FMHE to record book ANY-6PS: PB on it spends this book's coach budget");
  });
});

describe("registration reports a wallet; an approved link binds it", () => {
  it("register with wallet A, approve the link: boundTo(id).wallet is A; reporting B later is pending and A stays", async () => {
    const s = setup();
    const before = s.consoles.view(PI, A);
    assert.deepEqual({ ...before, tag: "x" }, { tag: "x", book: null, state: "unbound", credential: null, wallet: null, wallet_pending: true });
    const tag = before.tag;
    const { action } = await s.consoles.startOp({ op: "link", console: tag, book: s.book });
    assert.equal(action, linkText(tag, s.book, A));
    await waitFor(() => s.consoles.boundTo(PI) !== null);
    assert.deepEqual(s.consoles.boundTo(PI), { book: s.book, tag, wallet: A.toLowerCase() });
    assert.deepEqual(s.consoles.view(PI), { tag, book: s.book, state: "bound", credential: "Orb", wallet: A.toLowerCase(), wallet_pending: false });
    assert.deepEqual(s.store.consoleWalletsFor(s.book), [A.toLowerCase()]);

    const again = s.consoles.view(PI, B);
    assert.equal(again.wallet_pending, true);
    assert.equal(again.wallet, A.toLowerCase());
    assert.equal(s.consoles.boundTo(PI)?.wallet, A.toLowerCase(), "the approved wallet stays until a new link");
    assert.deepEqual(s.store.consoleWalletsFor(s.book), [A.toLowerCase()]);
    assert.ok(s.lines.some((l) => l.includes(`console ${tag}: reports wallet 0x9999…0000`)), s.lines.join("\n"));
  });

  it("a GET without a wallet changes nothing about the wallet", async () => {
    const s = setup();
    const tag = s.consoles.view(PI, A).tag;
    await op(s.consoles, { op: "link", console: tag, book: s.book });
    assert.deepEqual([s.consoles.view(PI).wallet, s.consoles.view(PI).wallet_pending], [A.toLowerCase(), false]);
  });

  it("a bound console with a pending wallet takes one new link to its own book; that approval binds the new wallet", async () => {
    const s = setup();
    const tag = s.consoles.view(PI, A).tag;
    await op(s.consoles, { op: "link", console: tag, book: s.book });
    s.consoles.view(PI, B); // a reflashed console: same id, a new key
    const v = await op(s.consoles, { op: "link", console: tag, book: s.book });
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(s.approvals.started.at(-1)?.action, linkText(tag, s.book, B));
    assert.deepEqual(s.consoles.boundTo(PI), { book: s.book, tag, wallet: B.toLowerCase() });
    assert.equal(s.consoles.view(PI).wallet_pending, false);
  });

  it("a console bound at sign-up with no wallet yet: its first wallet needs the same one link", async () => {
    const s = setup();
    const tag = s.consoles.view(LAPTOP).tag;
    s.consoles.bindAtSignup(LAPTOP, s.book, "signup");
    assert.equal(s.consoles.boundTo(LAPTOP)?.wallet, null);
    assert.equal(s.consoles.view(LAPTOP, A).wallet_pending, true);
    assert.deepEqual(s.store.consoleWalletsFor(s.book), [], "a sign-up approves no wallet");
    assert.equal((await op(s.consoles, { op: "link", console: tag, book: s.book })).ok, true);
    assert.equal(s.consoles.boundTo(LAPTOP)?.wallet, A.toLowerCase());
  });

  it("a bound console with nothing pending is still already_bound; another book is still already_bound", async () => {
    const s = setup();
    const tag = s.consoles.view(PI, A).tag;
    await op(s.consoles, { op: "link", console: tag, book: s.book });
    await assert.rejects(s.consoles.startOp({ op: "link", console: tag, book: s.book }), /already_bound/);
    s.consoles.view(PI, B);
    const other = s.store.claimBook(nullifierKey(SECRET, "act", `wallet-other-${n}`), "Orb", "fedcba9876543210", 1, "session_o").record.book;
    await assert.rejects(s.consoles.startOp({ op: "link", console: tag, book: other }), /already_bound/);
  });

  it("the approval binds the wallet its text named, even if another is reported while World App waits", async () => {
    const s = setup();
    const tag = s.consoles.view(PI, A).tag;
    s.approvals.hold = true;
    const { id } = await s.consoles.startOp({ op: "link", console: tag, book: s.book });
    await waitFor(() => s.consoles.opView(id)?.stage === "approve");
    s.consoles.view(PI, B);
    s.approvals.hold = false;
    await waitFor(() => s.consoles.opView(id)?.stage === "done");
    assert.equal(s.consoles.boundTo(PI)?.wallet, A.toLowerCase());
    assert.equal(s.consoles.view(PI).wallet_pending, true, "B still waits for its own link");
  });

  it("a release clears the approved wallet: a released console's later runs are not stamped", async () => {
    const s = setup();
    const tag = s.consoles.view(PI, A).tag;
    await op(s.consoles, { op: "link", console: tag, book: s.book });
    assert.equal((await op(s.consoles, { op: "release", console: tag })).ok, true);
    assert.equal(s.consoles.boundTo(PI), null);
    assert.equal(s.consoles.view(PI).wallet, null);
    assert.deepEqual(s.store.consoleWalletsFor(s.book), []);
  });

  it("only bound consoles of the book count, each approved wallet once", async () => {
    const s = setup();
    const pi = s.consoles.view(PI, A).tag;
    const laptop = s.consoles.view(LAPTOP, B).tag;
    await op(s.consoles, { op: "link", console: pi, book: s.book });
    await op(s.consoles, { op: "link", console: laptop, book: s.book });
    assert.deepEqual(s.store.consoleWalletsFor(s.book).sort(), [A.toLowerCase(), B.toLowerCase()].sort());
    assert.deepEqual(s.store.consoleWalletsFor("ANY-ZZZ"), []);
    assert.ok(s.store.consoleFor(consoleKey(SECRET, PI))?.wallet === A.toLowerCase());
  });

  it("a wallet that is not an address is refused (400 bad_wallet)", () => {
    const s = setup();
    for (const bad of ["0x12", "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b9f3e", `0x${"g".repeat(40)}`, ""]) {
      assert.throws(() => s.consoles.view(PI, bad), (e: unknown) => (e as { status?: number; error?: string }).status === 400 && (e as { error: string }).error === "bad_wallet", bad);
    }
  });
});

describe("GET /console/{id}?wallet=0x...", () => {
  it("registers the reported wallet; the reply adds wallet and wallet_pending; a bad wallet is 400 id_offline", async () => {
    const s = setup();
    const lines: string[] = [];
    const server = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null, consoles: s.consoles, log: (l) => lines.push(l) });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const get = async (path: string) => {
        const r = await fetch(`${base}${path}`);
        return { status: r.status, json: (await r.json()) as Record<string, unknown> };
      };
      const g = await get(`/console/${PI}?wallet=${A}`);
      assert.equal(g.status, 200);
      assert.deepEqual(Object.keys(g.json).sort(), ["book", "credential", "state", "tag", "wallet", "wallet_pending"]);
      assert.deepEqual([g.json.wallet, g.json.wallet_pending], [null, true]);
      await op(s.consoles, { op: "link", console: g.json.tag, book: s.book });
      const after = await get(`/console/${PI}`);
      assert.deepEqual([after.json.wallet, after.json.wallet_pending, after.json.book], [A.toLowerCase(), false, s.book]);
      assert.deepEqual(await get(`/console/${PI}?wallet=0x12`), { status: 400, json: { error: "bad_wallet", failure: "id_offline" } });
      assert.ok(!lines.join("\n").includes(PI), "no console id in the access log");
      assert.ok(!s.lines.join("\n").includes(PI), "no console id in the service log");
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });
});

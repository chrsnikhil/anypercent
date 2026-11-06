/**
 * npm run hedera:payto -- --book ANY-6PS --account 0.0.5123456
 * npm run hedera:payto -- --book ANY-6PS --clear
 *
 * Registers the Hedera account a record book's ghosts pay (spec: Accounts and the seller's payTo).
 * Checks on the mirror that the account exists and can take USDC (associated, or unlimited
 * auto-association, or a free auto-association slot: the facilitator's own preflight rule), then
 * writes data/payto.json. No route writes it. A running service sees the change at once (it re-reads
 * the file when it changes) and never has state.json written under it by this script.
 *
 * From then on the console's listing text names the account ("... USDC to 0.0.N on the public
 * board"), World App shows it, and the listing row carries it as `pay_to`. Prints ids and links only.
 */
import { BOOK_RE } from "../src/approvals.js";
import { ACCOUNT_RE } from "../src/config.js";
import { Store } from "../src/store.js";
import { arg, die, flag, hashscan, line, loadEnv, mirrorOf, mustAccount, usdc } from "./hedera-common.js";

const cfg = loadEnv();
const book = arg("book") ?? "";
const account = arg("account") ?? "";
const clear = flag("clear");
if (!BOOK_RE.test(book)) die("Usage: npm run hedera:payto -- --book ANY-XXX --account 0.0.N   (or --clear)");
if (!clear && !ACCOUNT_RE.test(account)) die("--account must be a plain 0.0.N account id (an EVM address is refused by the facilitators).");

const store = new Store(cfg.dataDir, cfg.serverSecret);
if (!store.recordForBook(book)) die(`${book} is not a record book this bridge issued (data/state.json).`);

if (clear) {
  const was = store.paytoFor(book);
  store.setPayto(book, null, Math.floor(Date.now() / 1000));
  line(book, was ? `no payout account (was ${was}): its ghost is on the board but not for sale` : "had no payout account");
  process.exit(0);
}

const mirror = mirrorOf(cfg);
const acct = await mustAccount(mirror, account, "--account");
const held = await mirror.tokenBalance(account, cfg.hedera.usdc).catch(() => null);
const receivable = held !== null || (await mirror.associated(account, cfg.hedera.usdc).catch(() => false));
if (!receivable) {
  die(`${account} cannot take USDC ${cfg.hedera.usdc}: associate the token (HashPack: Tokens, Associate, ${cfg.hedera.usdc}) or allow auto-association, then run this again.`);
}
const how = held !== null ? `associated, ${usdc(held)}` : acct.maxAutoAssociations === -1 ? "unlimited auto-association" : "a free auto-association slot";
store.setPayto(book, account, Math.floor(Date.now() / 1000));
line(book, `pays ${account} (${how})`, hashscan.account(account));
console.log(`The next listing approval for ${book} names ${account} in World App; relist a run to put it up for sale.`);

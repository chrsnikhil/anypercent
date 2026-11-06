/**
 * npm run hedera:setup
 *
 * From the owner's operator account (HEDERA_OPERATOR_ID / HEDERA_OPERATOR_KEY, a portal.hedera.com
 * testnet account), makes what the Hedera module needs and appends it to apps/world-bridge/.env:
 *
 *   1. checks the operator: on the mirror, its key matches HEDERA_OPERATOR_KEY, its HBAR balance;
 *   2. PB's agent account (unless HEDERA_AGENT_ID/KEY are set): AccountCreateTransaction with a new
 *      ECDSA key set without an EVM alias (setKeyWithoutAlias), 5 HBAR. HEDERA_AGENT_ID and
 *      HEDERA_AGENT_KEY (DER) go into .env at once, before anything else can fail;
 *   3. the agent's USDC association (TokenAssociateTransaction, signed by the agent key, paid by the
 *      operator), unless the mirror already shows it;
 *   4. the market topic (unless HEDERA_TOPIC_ID is set): TopicCreateTransaction with the operator's
 *      public key as the submit key, memo "anypercent market v1", no admin key, no fee schedule key,
 *      no custom fees. Nobody, including us, can delete or update it.
 *
 * It never overwrites a value in .env (a name present with an empty value is filled in place) and
 * prints only account ids, the topic id, transaction ids and HashScan links. Never a key.
 *
 * npm run hedera:setup -- --house [--owner ANY-6PS]
 *
 * Only the house account (scout and pivot: the account BOT listings pay): a new ECDSA key set
 * without an EVM alias, 2 HBAR from the operator, then its USDC association (signed by the house
 * key). HEDERA_HOUSE_ID and HEDERA_HOUSE_KEY are appended to .env at once; with --owner,
 * HOUSE_OWNER_BOOK too (the only book whose World approval publishes a house batch). An existing
 * house account is checked and kept. The service never signs with the house key: it is there so the
 * owner can move the house's testnet USDC later. Back it up offline.
 */
import { AccountCreateTransaction, Hbar, PrivateKey, Status, TokenAssociateTransaction, TopicCreateTransaction } from "@hiero-ledger/sdk";
import { BOOK_RE } from "../src/approvals.js";
import { ACCOUNT_RE, DER_KEY_RE } from "../src/config.js";
import { parseDerKey } from "../src/hedera/net.js";
import { arg, die, envFile, fillEnv, flag, hashscan, hbar, keyMatches, line, loadEnv, mirrorOf, mustAccount, operator, operatorClient, timed, usdc, why } from "./hedera-common.js";

const cfg = loadEnv();
const h = cfg.hedera;
const op = operator(cfg);
const mirror = mirrorOf(cfg);
const client = operatorClient(op);
const HEADER = "# ---- Hedera (npm run hedera:setup). Service only: never on the Pi, never shared. Back the key up offline. ----";
const HOUSE_HEADER = "# ---- The house account (npm run hedera:setup -- --house). Never used by the service; back the key up offline. ----";

/** The house account: create (or check) it, associate it with USDC, put its id and key in .env. */
async function setupHouse(): Promise<void> {
  const owner = arg("owner")?.toUpperCase();
  if (owner !== undefined && !BOOK_RE.test(owner)) die("--owner must be a record book id, e.g. ANY-6PS.");
  const opAcct = await mustAccount(mirror, op.id, "HEDERA_OPERATOR_ID");
  if (!keyMatches(op.key, opAcct.key)) die(`HEDERA_OPERATOR_KEY is not the key of ${op.id} on testnet.`);
  line("operator", `${op.id}  ${hbar(opAcct.balance)}`, hashscan.account(op.id));
  if (opAcct.balance < 5n * 100_000_000n) die(`The operator holds ${hbar(opAcct.balance)}; the house needs 2 HBAR plus fees.`);
  const token = await mirror.token(h.usdc);
  if (!token || token.decimals !== 6 || token.symbol !== "USDC") die(`HEDERA_USDC ${h.usdc} is not a 6-decimal USDC token on testnet.`);

  const houseId0 = cfg.house.id;
  const houseKey0 = process.env.HEDERA_HOUSE_KEY?.trim() ?? "";
  let houseId = houseId0;
  let houseKey: PrivateKey;
  if (houseId0 !== "" || houseKey0 !== "") {
    if (!ACCOUNT_RE.test(houseId0) || !DER_KEY_RE.test(houseKey0)) die("HEDERA_HOUSE_ID and HEDERA_HOUSE_KEY must both be set (or both empty for a new house account).");
    houseKey = parseDerKey(houseKey0);
    const a = await mustAccount(mirror, houseId0, "HEDERA_HOUSE_ID");
    if (!keyMatches(houseKey, a.key)) die(`HEDERA_HOUSE_KEY is not the key of ${houseId0}.`);
    line("house (kept)", `${houseId0}  ${hbar(a.balance)}`, hashscan.account(houseId0));
  } else {
    houseKey = PrivateKey.generateECDSA();
    const [receipt, ms] = await timed(async () => {
      const resp = await new AccountCreateTransaction()
        .setKeyWithoutAlias(houseKey.publicKey)
        .setInitialBalance(new Hbar(2))
        .setAccountMemo("anypercent house")
        .execute(client);
      return { r: await resp.getReceipt(client), tx: resp.transactionId.toString() };
    });
    if (!receipt.r.accountId) die("The house account was not created (no account id in the receipt).");
    houseId = receipt.r.accountId.toString();
    // Into .env before anything else can fail: the key exists nowhere else.
    fillEnv(envFile, [
      ["HEDERA_HOUSE_ID", houseId],
      ["HEDERA_HOUSE_KEY", houseKey.toStringDer()],
      ...(owner ? ([["HOUSE_OWNER_BOOK", owner]] as Array<[string, string]>) : []),
    ], HOUSE_HEADER);
    line("house (new, ECDSA, no alias)", `${houseId}  2 HBAR, tx ${receipt.tx}`, hashscan.account(houseId), ms);
  }

  const held = await mirror.tokenBalance(houseId, h.usdc).catch(() => null);
  if (held !== null) {
    line("house USDC", `associated, ${usdc(held)}`, hashscan.token(h.usdc));
  } else {
    try {
      const [tx, ms] = await timed(async () => {
        const signed = await new TokenAssociateTransaction().setAccountId(houseId).setTokenIds([h.usdc]).freezeWith(client).sign(houseKey);
        const resp = await signed.execute(client);
        await resp.getReceipt(client);
        return resp.transactionId.toString();
      });
      line("house USDC", `associated ${h.usdc}, tx ${tx}`, hashscan.tx(tx), ms);
    } catch (err) {
      const status = (err as { status?: Status }).status;
      if (status === Status.TokenAlreadyAssociatedToAccount) line("house USDC", "already associated");
      else throw err;
    }
  }
  if (owner) {
    // A new account wrote it with the id and key; for a kept one, fill it now if it has no value.
    const st = houseId0 === "" ? null : fillEnv(envFile, [["HOUSE_OWNER_BOOK", owner]], HOUSE_HEADER);
    const already = cfg.house.ownerBook;
    line("house owner book", st?.get("HOUSE_OWNER_BOOK") === "kept" && already !== owner ? `kept as set in .env (${already || "set"}; edit .env to change it)` : owner);
  }
  console.log("");
  console.log(`.env: HEDERA_HOUSE_ID and HEDERA_HOUSE_KEY are set (the key is not shown). Back the key up offline.`);
  console.log(`Check ${houseId} on HashScan (associated with USDC ${h.usdc}), set HOUSE_OWNER_BOOK if it is not, then restart npm start (/health house: true).`);
}

try {
  if (flag("house")) {
    await setupHouse();
    client.close();
    process.exit(0);
  }
  // 1. The operator.
  const opAcct = await mustAccount(mirror, op.id, "HEDERA_OPERATOR_ID");
  if (!keyMatches(op.key, opAcct.key)) die(`HEDERA_OPERATOR_KEY is not the key of ${op.id} on testnet (check you copied the DER private key of this account).`);
  line("operator", `${op.id}  ${hbar(opAcct.balance)}`, hashscan.account(op.id));
  if (opAcct.balance < 20n * 100_000_000n) die(`The operator holds ${hbar(opAcct.balance)}; it needs about 20 HBAR (the portal refills to 1000 a day).`);
  const token = await mirror.token(h.usdc);
  if (!token || token.decimals !== 6 || token.symbol !== "USDC") die(`HEDERA_USDC ${h.usdc} is not a 6-decimal USDC token on testnet.`);

  // 2. PB's agent account.
  let agentId = h.agentId;
  let agentKey: PrivateKey;
  if (agentId !== "" || h.agentKey !== "") {
    if (!ACCOUNT_RE.test(agentId) || !DER_KEY_RE.test(h.agentKey)) die("HEDERA_AGENT_ID and HEDERA_AGENT_KEY must both be set (or both empty for a new agent).");
    agentKey = parseDerKey(h.agentKey);
    const a = await mustAccount(mirror, agentId, "HEDERA_AGENT_ID");
    if (!keyMatches(agentKey, a.key)) die(`HEDERA_AGENT_KEY is not the key of ${agentId}.`);
    line("agent (kept)", `${agentId}  ${hbar(a.balance)}`, hashscan.account(agentId));
  } else {
    agentKey = PrivateKey.generateECDSA();
    const [receipt, ms] = await timed(async () => {
      const resp = await new AccountCreateTransaction()
        .setKeyWithoutAlias(agentKey.publicKey)
        .setInitialBalance(new Hbar(5))
        .setAccountMemo("anypercent PB agent")
        .execute(client);
      return { r: await resp.getReceipt(client), tx: resp.transactionId.toString() };
    });
    if (!receipt.r.accountId) die("The account was not created (no account id in the receipt).");
    agentId = receipt.r.accountId.toString();
    // Into .env before anything else can fail: the key exists nowhere else.
    fillEnv(envFile, [
      ["HEDERA_AGENT_ID", agentId],
      ["HEDERA_AGENT_KEY", agentKey.toStringDer()],
    ], HEADER);
    line("agent (new, ECDSA, no alias)", `${agentId}  5 HBAR, tx ${receipt.tx}`, hashscan.account(agentId), ms);
  }

  // 3. The agent's USDC association.
  const held = await mirror.tokenBalance(agentId, h.usdc).catch(() => null);
  if (held !== null) {
    line("agent USDC", `associated, ${usdc(held)}`, hashscan.token(h.usdc));
  } else {
    try {
      const [tx, ms] = await timed(async () => {
        const signed = await new TokenAssociateTransaction().setAccountId(agentId).setTokenIds([h.usdc]).freezeWith(client).sign(agentKey);
        const resp = await signed.execute(client);
        await resp.getReceipt(client);
        return resp.transactionId.toString();
      });
      line("agent USDC", `associated ${h.usdc}, tx ${tx}`, hashscan.tx(tx), ms);
    } catch (err) {
      const status = (err as { status?: Status }).status;
      if (status === Status.TokenAlreadyAssociatedToAccount) line("agent USDC", "already associated");
      else throw err;
    }
  }

  // 4. The market topic.
  let topicId = h.topicId;
  if (topicId !== "") {
    if (!ACCOUNT_RE.test(topicId)) die("HEDERA_TOPIC_ID is set but is not 0.0.N.");
    const t = await mirror.topic(topicId).catch(() => null);
    if (!t) die(`HEDERA_TOPIC_ID ${topicId} is not on the testnet mirror.`);
    line("topic (kept)", `${topicId}  admin key ${t.adminKey ? "SET (not ours to trust)" : "none"}, memo "${t.memo}"`, hashscan.topic(topicId));
  } else {
    const [res, ms] = await timed(async () => {
      const resp = await new TopicCreateTransaction().setSubmitKey(op.key.publicKey).setTopicMemo("anypercent market v1").execute(client);
      return { r: await resp.getReceipt(client), tx: resp.transactionId.toString() };
    });
    if (!res.r.topicId) die("The topic was not created (no topic id in the receipt).");
    topicId = res.r.topicId.toString();
    fillEnv(envFile, [["HEDERA_TOPIC_ID", topicId]], HEADER);
    line("topic (new, no admin key)", `${topicId}  submit key = the operator's, tx ${res.tx}`, hashscan.topic(topicId), ms);
  }

  console.log("");
  console.log(`.env: HEDERA_AGENT_ID, HEDERA_AGENT_KEY and HEDERA_TOPIC_ID are set (the key is not shown). Back the key up offline.`);
  console.log(`Next: get test USDC at https://faucet.circle.com (Hedera Testnet) for ${agentId} (the 0.0.N id, never an EVM address),`);
  console.log(`check it is ${h.usdc} on HashScan, then: npm run hedera:payto -- --book ANY-XXX --account 0.0.N and npm run hedera:smoke -- --pay-to 0.0.N`);
} catch (err) {
  die(`hedera:setup stopped: ${why(err)}`);
} finally {
  client.close();
}

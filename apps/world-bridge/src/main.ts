/**
 * Entry point: `npm start`. Loads apps/world-bridge/.env (if present), wires whatever is configured,
 * and serves the HTTP contract. Missing configuration never stops the service: /health reports the
 * missing parts as false and their start endpoints answer 503 with the step's down failure.
 *
 * Arkiv (src/arkiv/*): the checker's key lives only in this .env. A probe every 30 s checks
 * eth_chainId against ARKIV_CHAIN_ID and the checker's balance, so /health never waits on Arkiv.
 *
 * Hedera (src/hedera/*): the operator and agent keys live only in this .env. A probe every 30 s
 * reads the mirror (HEDERA_USDC once, the agent's USDC, the operator's HBAR) and the
 * facilitators' /supported, so /health never waits on Hedera. With Hedera payments configured,
 * /arkiv/ghost takes only receipts the paywall settled; mock receipts are refused.
 *
 * Scout and pivot: consoles are bound to one record book (src/consoles.ts); run rows carry lap
 * splits (CHECKER_SPLITS); PB's scout picks which listed ghost to buy (src/scout/*, Groq when
 * GROQ_API_KEY is set, else the board's rule); the house publishes BOT batches after its owner's
 * World approval (src/arkiv/house.ts). /health adds "console", "splits", "scout" and "house".
 */
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { AgentPass } from "./agentpass.js";
import type { ApprovalProvider } from "./approvals.js";
import { RealChecker } from "./arkiv/checker.js";
import { SdkArkiv } from "./arkiv/client.js";
import { HouseService } from "./arkiv/house.js";
import { MockPayments, type PaymentCheck } from "./arkiv/payments.js";
import { Publisher } from "./arkiv/publish.js";
import { checksum } from "./arkiv/queries.js";
import { ArkivService } from "./arkiv/service.js";
import {
  arkivProblems,
  arkivRpcUrl,
  chooseApprovals,
  explorerLinks,
  groqKeyReady,
  HEDERA_NETWORK_CAIP2,
  hederaPayProblems,
  hederaRecordProblems,
  houseProblems,
  idkitReady,
  loadConfig,
  PRIVATE_KEY_RE,
  runExpiry,
  secretReady,
  splitsReady,
} from "./config.js";
import { Consoles } from "./consoles.js";
import { createClientHederaSigner } from "@x402/hedera";
import { Agent } from "./hedera/agent.js";
import { parseDerKey, RestMirror, SdkHedera } from "./hedera/net.js";
import { HederaPayments } from "./hedera/payments.js";
import { Recorder } from "./hedera/record.js";
import { ArkivOffers, ResourceServer } from "./hedera/resource.js";
import { HederaService } from "./hedera/service.js";
import { Facilitators, HttpFacilitator, PaymentBuilder } from "./hedera/x402.js";
import { IdkitSessions, realIdkitDeps } from "./idkit.js";
import { IdkitApprovals } from "./idkit-approvals.js";
import { WorldIdp } from "./oidc.js";
import { GroqClient } from "./scout/groq.js";
import { ScoutService } from "./scout/scout.js";
import { buildServer, makeHealth, pivotHealth } from "./server.js";
import { Store } from "./store.js";

const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const envFile = join(appDir, ".env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

const cfg = loadConfig(process.env, appDir);
const log = (line: string) => console.log(`${new Date().toISOString()} ${line}`);

const store = secretReady(cfg) ? new Store(cfg.dataDir, cfg.serverSecret) : null;
const IDKIT_TTL_S = 300;

// One request builder for sign-ups and IDKit approvals (proof_of_human through .constraints(), sessions).
const idkitDeps = store && idkitReady(cfg) ? realIdkitDeps(cfg, IDKIT_TTL_S) : null;

// Listing approvals: APPROVALS=idkit|agentpass (default: idkit when only IDKit is configured).
const choice = chooseApprovals(cfg);
if (cfg.approvals !== "" && cfg.approvals !== choice.kind) {
  log(`APPROVALS="${cfg.approvals}" is not idkit or agentpass; using ${choice.kind}`);
}

const idp =
  choice.kind === "agentpass" && choice.available
    ? new WorldIdp({
        issuer: cfg.agentpass.issuer,
        clientId: cfg.agentpass.clientId,
        clientSecret: cfg.agentpass.clientSecret,
      })
    : null;

let approvals: ApprovalProvider | null = null;
if (store && idp) {
  approvals = new AgentPass({
    idp,
    store,
    secret: cfg.serverSecret,
    clientId: cfg.agentpass.clientId,
    extraAcr: cfg.agentpass.acceptedAcr,
    log,
  });
} else if (store && idkitDeps && choice.kind === "idkit") {
  approvals = new IdkitApprovals({
    deps: idkitDeps,
    store,
    secret: cfg.serverSecret,
    action: cfg.world.action,
    environment: cfg.world.environment,
    ttlS: IDKIT_TTL_S,
    log,
  });
}

// One console, one person: bindings at sign-up, and the owner's link / release on a World approval.
const consoles = store ? new Consoles({ store, secret: cfg.serverSecret, approvals, log }) : null;

const idkit =
  store && idkitDeps
    ? new IdkitSessions({
        deps: idkitDeps,
        store,
        secret: cfg.serverSecret,
        action: cfg.world.action,
        environment: cfg.world.environment,
        signupSession: cfg.world.signupSession,
        ttlS: IDKIT_TTL_S,
        consoles,
        log,
      })
    : null;

// ---- is World reachable? Probed in the background so /health never waits on the network. ----
let reachable = false;
async function probe(): Promise<void> {
  const checks: Promise<boolean>[] = [];
  if (idp) checks.push(idp.discover(true).then(() => true, () => false));
  if (idkitDeps) {
    checks.push(
      fetch(cfg.world.portalBase, { method: "HEAD", signal: AbortSignal.timeout(5000) }).then(
        () => true,
        () => false,
      ),
    );
  }
  const results = await Promise.all(checks);
  const now = results.some(Boolean);
  if (now !== reachable) log(`world ${now ? "reachable" : "unreachable"}`);
  reachable = now;
}
void probe();
const probeTimer = setInterval(() => void probe(), 30_000);
probeTimer.unref();

// ---- Arkiv: the board's writes (checker key, here only) and the listed-ghost key release ----
const ak = cfg.arkiv;
const arkivIssues = arkivProblems(cfg);
const checkerKey = PRIVATE_KEY_RE.test(ak.checkerKey) ? ak.checkerKey : undefined;
let arkivPort: SdkArkiv | null = null;
try {
  arkivPort = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerKey });
} catch {
  log("arkiv off (ARKIV_RPC is not usable)");
}
const checkerAddress = arkivPort?.checker ? checksum(arkivPort.checker) : null;
const expiry = runExpiry(ak);
const links = explorerLinks(cfg.explorer);
// The replay tool and, beside it, the splits tool (same runner, same data/checker directory).
const realChecker = new RealChecker({
  replay: ak.replay,
  wsl: ak.wsl,
  dir: join(cfg.dataDir, "checker"),
  ...(splitsReady(cfg) ? { splits: cfg.splits.tool, splitGames: cfg.splits.games } : {}),
});
const splitsPort = splitsReady(cfg) ? realChecker : null;
const publisher: Publisher | null =
  store && arkivPort && checkerKey && expiry && arkivIssues.length === 0
    ? new Publisher({
        arkiv: arkivPort,
        checker: realChecker,
        splits: splitsPort,
        explorer: links,
        store,
        season: ak.season,
        runExpiry: expiry,
        priceC: ak.priceC,
        ghostSecret: ak.ghostSecret,
        // Called per request, after `arkiv` below exists: config, chain and balance as last probed.
        gate: () => arkiv.gate(),
        log,
      })
    : null;
// ---- Hedera: the LISTING record, PB's purchases (agent key, here only) and the x402 paywall ----
const hc = cfg.hedera;
const payProblems = hederaPayProblems(cfg);
const recordProblems = hederaRecordProblems(cfg);
let mirror: RestMirror | null = null;
try {
  mirror = new RestMirror(hc.mirror);
} catch {
  log("hedera off (HEDERA_MIRROR is not usable)");
}
let hcs: SdkHedera | null = null;
if (recordProblems.length === 0 && mirror) {
  try {
    hcs = new SdkHedera({ operatorId: hc.operatorId, operatorKey: hc.operatorKey, mirror });
  } catch {
    log("hedera: HEDERA_OPERATOR_KEY does not parse as a DER private key; record and payments off");
  }
}
const facilitators = new Facilitators(
  [hc.facilitator, hc.facilitatorFallback].filter((u) => u !== "").map((u) => new HttpFacilitator(u)),
  HEDERA_NETWORK_CAIP2,
  log,
);
let builder: PaymentBuilder | null = null;
if (payProblems.length === 0) {
  try {
    builder = new PaymentBuilder(createClientHederaSigner(hc.agentId, parseDerKey(hc.agentKey), { network: HEDERA_NETWORK_CAIP2 }), HEDERA_NETWORK_CAIP2, hc.usdc);
  } catch {
    log("hedera: HEDERA_AGENT_KEY does not parse as a DER private key; payments off");
  }
}
const payOn = store !== null && arkivPort !== null && arkivPort.checker !== null && mirror !== null && hcs !== null && builder !== null;
const recorder =
  store && hcs
    ? new Recorder({ store, hedera: hcs, arkiv: publisher ? arkivPort : null, topic: hc.topicId, priceC: ak.priceC, gate: () => hedera.recordGate(), log })
    : null;
const resource =
  payOn && store && arkivPort && mirror
    ? new ResourceServer({
        source: new ArkivOffers(arkivPort, ak.ghostSecret),
        facilitators,
        store,
        mirror,
        network: HEDERA_NETWORK_CAIP2,
        asset: hc.usdc,
        base: hc.resourceBase,
        gate: () => hedera.paywallGate(),
        log,
      })
    : null;
const agent =
  payOn && store && arkivPort && mirror && hcs && builder
    ? new Agent({
        store,
        arkiv: arkivPort,
        mirror,
        hedera: hcs,
        facilitators,
        builder,
        topic: hc.topicId,
        usdc: hc.usdc,
        network: HEDERA_NETWORK_CAIP2,
        agentId: hc.agentId,
        resourceBase: hc.resourceBase,
        priceC: ak.priceC,
        maxPriceC: hc.maxPriceC,
        bookDayC: hc.bookDayC,
        agentDayC: hc.agentDayC,
        feePayersPin: hc.feePayers,
        houseId: cfg.house.id,
        consoles,
        scouts: { held: (id: string) => scout?.held(id) },
        gate: () => hedera.payGate(),
        log,
      })
    : null;
const hedera: HederaService = new HederaService({
  cfg: hc,
  priceC: ak.priceC,
  payProblems: payOn ? payProblems : payProblems.length ? payProblems : ["HEDERA_OPERATOR_KEY or HEDERA_AGENT_KEY (unparsable)"],
  recordProblems: hcs ? recordProblems : recordProblems.length ? recordProblems : ["HEDERA_OPERATOR_KEY (unparsable)"],
  store,
  mirror,
  hedera: hcs,
  facilitators,
  agent,
  recorder,
  resource,
  houseId: cfg.house.id,
  log,
});
// With Hedera payments on, a ghost's key is released only for a sale the paywall settled.
const payments: PaymentCheck = resource && store ? new HederaPayments(store, resource, log) : new MockPayments(ak.mockPayments, store ?? { claimReceipt: () => false });
void hedera.probe();
const hederaTimer = setInterval(() => void hedera.probe(), 30_000);
hederaTimer.unref();

const arkiv: ArkivService = new ArkivService({
  publicRpc: ak.rpc,
  chainId: ak.chainId,
  season: ak.season,
  priceC: ak.priceC,
  checker: checkerAddress,
  arkiv: arkivPort,
  publisher,
  payments,
  ghostSecret: ak.ghostSecret,
  problems: arkivIssues,
  boardFile: join(appDir, "public", "board.html"),
  snapshotFile: resolve(appDir, "..", "..", "arkiv", "snapshot.json"),
  explorer: cfg.explorer,
  log,
});
void arkiv.probe();
const arkivTimer = setInterval(() => void arkiv.probe(), 30_000);
arkivTimer.unref();

// ---- PB's scout: which listed ghost to buy (Groq picks among code-eligible candidates, or the rule) ----
const groq = groqKeyReady(cfg)
  ? new GroqClient({ apiKey: cfg.groq.apiKey, model: cfg.groq.model, base: cfg.groq.base, timeoutMs: Number.isInteger(cfg.groq.timeoutMs) && cfg.groq.timeoutMs > 0 ? cfg.groq.timeoutMs : 6000 })
  : null;
const scout: ScoutService | null =
  store && arkivPort && arkivPort.checker && agent
    ? new ScoutService({
        store,
        arkiv: arkivPort,
        checker: realChecker,
        splits: splitsPort,
        agent,
        groq,
        consoles,
        season: ak.season,
        priceC: ak.priceC,
        houseId: cfg.house.id,
        bookDayC: hc.bookDayC,
        reasonMax: Number.isInteger(cfg.groq.reasonMax) && cfg.groq.reasonMax > 0 ? cfg.groq.reasonMax : 110,
        on: () => hedera.health().hedera_pay && arkiv.health().arkiv === "ok",
        log,
      })
    : null;

// ---- the house's BOT batches (written only after HOUSE_OWNER_BOOK's World approval) ----
const houseIssues = houseProblems(cfg);
const house: HouseService | null =
  store && arkivPort && checkerKey && expiry && houseIssues.length === 0
    ? new HouseService({
        store,
        arkiv: arkivPort,
        checker: realChecker,
        splits: splitsPort,
        approvals,
        hedera: hcs,
        topic: hc.topicId,
        houseId: cfg.house.id,
        ownerBook: cfg.house.ownerBook,
        maxBatch: cfg.house.maxBatch,
        txPairs: cfg.house.txPairs,
        season: ak.season,
        runExpiry: expiry,
        priceC: ak.priceC,
        ghostSecret: ak.ghostSecret,
        secret: cfg.serverSecret,
        problems: () => houseIssues,
        gate: () => arkiv.gate(),
        explorer: links,
        log,
      })
    : null;

const health = () => ({
  ...makeHealth(idkit, approvals, reachable),
  ...arkiv.health(),
  ...hedera.health(),
  ...pivotHealth({ consoles, splits: splitsReady(cfg), scout, house, arkivWrites: arkiv.health().arkiv_writes }),
});

const server = buildServer({ health, idkit, approvals, arkiv, hedera, consoles, scout, house, log });
server.on("error", (err: NodeJS.ErrnoException) => {
  if (err.code === "EADDRINUSE") log(`port ${cfg.port} is already in use (another bridge running?)`);
  else if (err.code === "EADDRNOTAVAIL") log(`HOST ${cfg.host} is not an address of this machine right now (hotspot off?)`);
  else log(`server error: ${err.code ?? err.message}`);
  process.exit(1);
});
server.listen(cfg.port, cfg.host, () => {
  log(
    `world-bridge on http://${cfg.host}:${cfg.port} ` +
      `(idkit ${idkit ? `on, ${cfg.world.environment}, ${cfg.world.action}, session ${cfg.world.signupSession}` : "off"}, approvals ${approvals ? approvals.kind : "off"}` +
      `${store ? "" : ", SERVER_SECRET missing"})`,
  );
  log(
    `arkiv: checker ${checkerAddress ?? "none"}, season ${ak.season}, ` +
      (arkivIssues.length === 0 ? "writes configured" : `writes off until set: ${arkivIssues.join(", ")}`) +
      `, mock payments ${resource ? "refused (Hedera pays)" : ak.mockPayments ? "on" : "off"}`,
  );
  log(
    `hedera: ${hc.network}, agent ${hc.agentId || "none"}, topic ${hc.topicId || "none"}, paywall ${hc.resourceBase}/x402/ghost/{listing}, ` +
      `payments ${resource ? "configured" : `off until set: ${payProblems.join(", ") || "a parsable key"}`}, ` +
      `record ${recorder ? "configured" : `off until set: ${recordProblems.join(", ") || "a parsable key"}`}`,
  );
  log(
    `pivot: consoles ${consoles ? "on" : "off"}, splits ${splitsReady(cfg) ? `${cfg.splits.games.join(",")} via ${cfg.splits.tool}` : "off"}, ` +
      `scout ${scout ? (groq ? `model ${cfg.groq.model}` : "rule (no GROQ_API_KEY)") : "off (needs Arkiv and Hedera payments)"}, ` +
      `house ${house ? `${cfg.house.id} for ${cfg.house.ownerBook}` : `off until set: ${houseIssues.join(", ")}`}`,
  );
});

function shutdown(): void {
  idkit?.stopAll();
  approvals?.stopAll();
  consoles?.stopAll();
  house?.stopAll();
  hcs?.close();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1000).unref();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

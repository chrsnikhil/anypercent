/**
 * One wired Hedera module for the tests: a store with a buyer book and a seller book (its payout
 * account registered), a fake Arkiv holding the seller's listed run, a fake mirror, a fake HCS, a
 * fake facilitator, the real paywall served over HTTP by the real router, and PB's real agent
 * signing with a throwaway ECDSA key (offline: the SDK freezes and signs without the network).
 */
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";
import { PrivateKey } from "@hiero-ledger/sdk";
import { createClientHederaSigner, type ClientHederaSigner } from "@x402/hedera";
import { encryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { Agent, type AgentOptions } from "../src/hedera/agent.js";
import { HederaPayments } from "../src/hedera/payments.js";
import { Recorder } from "../src/hedera/record.js";
import { ArkivOffers, ResourceServer } from "../src/hedera/resource.js";
import { HederaService } from "../src/hedera/service.js";
import { Facilitators, PaymentBuilder, type FacilitatorPort } from "../src/hedera/x402.js";
import { loadConfig } from "../src/config.js";
import { nullifierKey } from "../src/hmac.js";
import { buildServer, makeHealth, type ServerDeps } from "../src/server.js";
import { Store } from "../src/store.js";
import { FakeFacilitator } from "./fake-facilitator.js";
import { FakeArkiv, makeLog } from "./fake-arkiv.js";
import { AGENT, fakeClock, FakeHedera, FakeMirror, HOUSE, SELLER_ACCT, TOPIC, USDC } from "./fake-hedera.js";
import { SECRET, tempDir } from "./helpers.js";

export const GHOST = "5e".repeat(32);
export const NETWORK = "hedera:testnet";

let n = 0;

export interface HarnessOptions {
  maxPriceC?: number;
  bookDayC?: number;
  agentDayC?: number;
  feePayersPin?: string[];
  /** Point the agent at another paywall (an evil one). */
  resourceBase?: string;
  extraFacilitators?: FacilitatorPort[];
  /** The agent's console registry and held scout picks (absent: none). */
  consoles?: AgentOptions["consoles"];
  scouts?: AgentOptions["scouts"];
}

export async function hedera(opts: HarnessOptions = {}) {
  n += 1;
  const events: string[] = [];
  const lines: string[] = [];
  const log = (l: string) => lines.push(l);
  const clock = fakeClock();
  const store = new Store(tempDir(), SECRET);
  const buyer = store.claimBook(nullifierKey(SECRET, "act", `buyer-${n}`), "Orb", "aaaaaaaaaaaaaaaa", 1, "session_b").record;
  const seller = store.claimBook(nullifierKey(SECRET, "act", `seller-${n}`), "Orb", "1111222233334444", 1, "session_s").record;
  store.setPayto(seller.book, SELLER_ACCT, 1);

  const arkiv = new FakeArkiv();
  const ghostLog = makeLog("MDGP", 4, 6170, 64, n);
  const logH = sha256Hex(ghostLog);
  const run = arkiv.addRun({
    game: "MDGP",
    title: "MARINE DRIVE GP",
    season: 1,
    rules: 4,
    frames: 6170,
    log_h: logH,
    runner: seller.runner_id,
    book: seller.book,
    human: true,
    credential: "Orb",
    tool: "arcade_replay sha256:a992006e6280",
    log_enc: encryptGhost(GHOST, logH, ghostLog),
  });
  const listing = arkiv.addListing(run, { game: "MDGP", season: 1, frames: 6170, log_h: logH, price: "0.1", seller: seller.runner_id, book: seller.book, human: true, pay_to: SELLER_ACCT });

  const mirror = new FakeMirror();
  const hcs = new FakeHedera(events, mirror);
  const fac = new FakeFacilitator(mirror, "https://facilitator.test", undefined, events);
  const facilitators = new Facilitators([fac, ...(opts.extraFacilitators ?? [])], NETWORK, log);
  await facilitators.probe();

  const key = PrivateKey.generateECDSA();
  const real = createClientHederaSigner(AGENT, key, { network: NETWORK });
  const signs = { count: 0 };
  const signer: ClientHederaSigner = {
    accountId: real.accountId,
    createPartiallySignedTransferTransaction: async (req) => {
      signs.count += 1;
      events.push("signed");
      return real.createPartiallySignedTransferTransaction(req);
    },
  };
  const builder = new PaymentBuilder(signer, NETWORK, USDC);

  const deps: ServerDeps = { health: () => ({ ...makeHealth(null, null, false), ...(svc?.health() ?? {}) }), idkit: null, approvals: null, hedera: null, log };
  const server: Server = buildServer(deps);
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

  const cfg = loadConfig({ HEDERA_TOPIC_ID: TOPIC, HEDERA_AGENT_ID: AGENT, HEDERA_OPERATOR_ID: "0.0.7001", HEDERA_RESOURCE_BASE: base }, ".").hedera;
  let svc: HederaService | null = null;
  const resource = new ResourceServer({
    source: new ArkivOffers(arkiv, GHOST),
    facilitators,
    store,
    mirror,
    network: NETWORK,
    asset: USDC,
    base,
    gate: () => svc?.paywallGate() ?? null,
    now: clock.now,
    sleep: clock.sleep,
    log,
  });
  const agentOpts: AgentOptions = {
    store,
    arkiv,
    mirror,
    hedera: hcs,
    facilitators,
    builder,
    topic: TOPIC,
    usdc: USDC,
    network: NETWORK,
    agentId: AGENT,
    resourceBase: opts.resourceBase ?? base,
    priceC: 10,
    maxPriceC: opts.maxPriceC ?? 10,
    bookDayC: opts.bookDayC ?? 100,
    agentDayC: opts.agentDayC ?? 500,
    feePayersPin: opts.feePayersPin ?? [],
    houseId: HOUSE,
    consoles: opts.consoles ?? null,
    scouts: opts.scouts ?? null,
    gate: () => svc?.payGate() ?? null,
    now: clock.now,
    sleep: clock.sleep,
    log,
  };
  const agent = new Agent(agentOpts);
  const recorder = new Recorder({ store, hedera: hcs, arkiv, topic: TOPIC, priceC: 10, gate: () => svc?.recordGate() ?? null, log, timeoutMs: 300 });
  svc = new HederaService({
    cfg,
    priceC: 10,
    payProblems: [],
    recordProblems: [],
    store,
    mirror,
    hedera: hcs,
    facilitators,
    agent,
    recorder,
    resource,
    houseId: HOUSE,
    log,
  });
  deps.hedera = svc;
  const payments = new HederaPayments(store, resource, log);

  const body = (over: Record<string, unknown> = {}) => ({
    book: buyer.book,
    game: "MDGP",
    seller: seller.book,
    listing,
    run,
    log_h: logH,
    frames: 6170,
    you_frames: 6290,
    price_c: 10,
    ...over,
  });

  return {
    events,
    lines,
    clock,
    store,
    buyer,
    seller,
    arkiv,
    ghostLog,
    logH,
    run,
    listing,
    mirror,
    hcs,
    fac,
    facilitators,
    signs,
    builder,
    server,
    base,
    resource,
    agent,
    agentOpts,
    recorder,
    svc,
    payments,
    body,
    close: () => new Promise<void>((r) => server.close(() => r())),
  };
}

export type Harness = Awaited<ReturnType<typeof hedera>>;

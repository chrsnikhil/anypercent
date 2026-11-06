/**
 * Configuration, read once from the environment (main.ts loads apps/world-bridge/.env first).
 *
 * Nothing here is ever logged. The "ready" checks only test that a value is present and
 * well-formed; whether World accepts it is only known at the first live call.
 */
import { resolve } from "node:path";

export type WorldEnvironment = "production" | "staging" | "sandbox";

export interface Config {
  port: number;
  host: string;
  dataDir: string;
  world: {
    appId: string;
    rpId: string;
    signingKey: string;
    action: string;
    environment: WorldEnvironment;
    /** WORLD_SIGNUP_SESSION: "combined" (default, one scan) or "separate" (a second createSession scan). */
    signupSession: "combined" | "separate";
    /** Developer Portal base, overridable only for tests. */
    portalBase: string;
  };
  agentpass: {
    issuer: string;
    clientId: string;
    clientSecret: string;
    /** Extra accepted `acr` values (AGENTPASS_ACCEPTED_ACR); empty: use the default set. */
    acceptedAcr: string[];
  };
  /** APPROVALS as written ("idkit", "agentpass", or anything else / empty: the default rule). */
  approvals: string;
  serverSecret: string;
  arkiv: ArkivConfig;
  hedera: HederaConfig;
}

/**
 * The Hedera module (src/hedera/*). Testnet only. Missing or malformed values never stop the
 * bridge: /health says hedera_pay: false / hedera_record: false and the routes answer 503. The
 * operator and agent keys are never logged, returned or written anywhere but this .env.
 */
export interface HederaConfig {
  /** HEDERA_NETWORK as written: "testnet" is the only value accepted in this build. */
  network: string;
  /** HEDERA_MIRROR: the mirror node's base URL, without /api/v1. */
  mirror: string;
  /** HEDERA_OPERATOR_ID (0.0.N): pays HCS, holds the market topic's submit key. */
  operatorId: string;
  /** HEDERA_OPERATOR_KEY: DER hex, as the portal shows it. */
  operatorKey: string;
  /** HEDERA_AGENT_ID / HEDERA_AGENT_KEY: PB's wallet, the x402 client (hedera:setup fills both). */
  agentId: string;
  agentKey: string;
  /** HEDERA_TOPIC_ID: the market topic (hedera:setup creates it, with no admin key). */
  topicId: string;
  /** HEDERA_USDC: testnet USDC, 6 decimals. */
  usdc: string;
  /** X402_FACILITATOR and X402_FACILITATOR_FALLBACK (no trailing slash). */
  facilitator: string;
  facilitatorFallback: string;
  /** X402_FEE_PAYERS: an optional pin, the only fee payers the agent accepts. */
  feePayers: string[];
  /** HEDERA_RESOURCE_BASE: where the agent reaches /x402/* (empty: http://<HOST>:<PORT>). */
  resourceBase: string;
  /** Caps in cents. NaN when malformed. */
  maxPriceC: number;
  bookDayC: number;
  agentDayC: number;
  /** HEDERA_LIVE_TOPIC_ID: the Live-run stretch only (not built). */
  liveTopicId: string;
}

export const HEDERA_NETWORK_CAIP2 = "hedera:testnet";
export const HEDERA_DEFAULT_MIRROR = "https://testnet.mirrornode.hedera.com";
export const HEDERA_TESTNET_USDC = "0.0.429274";
export const HASHSCAN = "https://hashscan.io/testnet";
export const X402_DEFAULT_FACILITATOR = "https://x402.org/facilitator";
export const X402_DEFAULT_FALLBACK = "https://api.testnet.blocky402.com";
/** A plain Hedera account or token id (no EVM alias). */
export const ACCOUNT_RE = /^0\.0\.[0-9]{1,10}$/;
/** A DER-encoded private key in hex (ECDSA secp256k1 or ED25519), as the portal shows it. */
export const DER_KEY_RE = /^(0x)?30[0-9a-fA-F]{90,200}$/;

/**
 * The Arkiv module (src/arkiv/*). Missing or malformed values never stop the bridge: /health says
 * arkiv_writes: false and /arkiv/publish answers 503. Keys and the ghost secret are never logged.
 */
export interface ArkivConfig {
  /** ARKIV_RPC without the access key (the public endpoint's URL). */
  rpc: string;
  /** ARKIV_CHAIN_ID: checked against eth_chainId; writes stay off when they differ. NaN when malformed. */
  chainId: number;
  /** ARKIV_ACCESS_KEY: appended as the RPC URL's last path segment. Service only. */
  accessKey: string;
  /** ARKIV_CHECKER_KEY: 0x + 64 hex. Creates every row. */
  checkerKey: string;
  /** ARKIV_STRANGER_KEY: the look-alike and extension demos only. */
  strangerKey: string;
  /** ARKIV_GHOST_SECRET: 64 hex, the HKDF master for listed ghosts. */
  ghostSecret: string;
  /** ARKIV_SEASON (default 1). NaN when malformed. */
  season: number;
  /** ARKIV_SEASON_END as written: an ISO 8601 instant. */
  seasonEnd: string;
  /** ARKIV_GHOST_PRICE_C (default 10): must equal the launcher's ledger.GHOST_PRICE. NaN when malformed. */
  priceC: number;
  /** ARKIV_MOCK_PAYMENTS=1: /arkiv/ghost accepts the launcher mock's receipts. */
  mockPayments: boolean;
  /** CHECKER_REPLAY: the replay tool's path, with {game} for the arcade id. */
  replay: string;
  /** CHECKER_WSL: run the tool through `wsl.exe -d <distro> -e`. Empty: run it directly. */
  wsl: string;
}

export const ARKIV_DEFAULT_RPC = "https://rpc.rabdi.db-chain.testnet.arkiv.network";
export const ARKIV_DEFAULT_CHAIN_ID = 7794095;
export const ARKIV_EXPLORER = "https://rabdi.explorer.arkiv.network";
/** Runs stay on the board this long after the season ends. */
export const RUN_GRACE_DAYS = 30;
/** Season end + RUN_GRACE_DAYS must land within this many days of now (the chain's cap is ~182.5). */
export const MAX_RUN_LIFETIME_DAYS = 180;
const DAY_MS = 86_400_000;

const ENVIRONMENTS: readonly WorldEnvironment[] = ["production", "staging", "sandbox"];

function str(env: NodeJS.ProcessEnv, name: string, fallback = ""): string {
  const v = env[name];
  return typeof v === "string" && v.trim() !== "" ? v.trim() : fallback;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env, baseDir = process.cwd()): Config {
  const envName = str(env, "WORLD_ENVIRONMENT", "production").toLowerCase();
  const port = Number.parseInt(str(env, "PORT", "8787"), 10);
  return {
    port: Number.isInteger(port) && port > 0 && port < 65536 ? port : 8787,
    host: str(env, "HOST", "127.0.0.1"),
    dataDir: resolve(baseDir, str(env, "DATA_DIR", "data")),
    world: {
      appId: str(env, "WORLD_APP_ID"),
      rpId: str(env, "WORLD_RP_ID"),
      signingKey: str(env, "WORLD_SIGNING_KEY"),
      action: str(env, "WORLD_ACTION", "anypercent-book"),
      environment: (ENVIRONMENTS as readonly string[]).includes(envName)
        ? (envName as WorldEnvironment)
        : ("invalid" as WorldEnvironment),
      signupSession: str(env, "WORLD_SIGNUP_SESSION").toLowerCase() === "separate" ? "separate" : "combined",
      portalBase: "https://developer.world.org",
    },
    agentpass: {
      issuer: str(env, "AGENTPASS_ISSUER").replace(/\/+$/, ""),
      clientId: str(env, "AGENTPASS_CLIENT_ID"),
      clientSecret: str(env, "AGENTPASS_CLIENT_SECRET"),
      acceptedAcr: str(env, "AGENTPASS_ACCEPTED_ACR")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    },
    approvals: str(env, "APPROVALS").toLowerCase(),
    serverSecret: str(env, "SERVER_SECRET"),
    arkiv: loadArkiv(env),
    hedera: loadHedera(env, Number.isInteger(port) && port > 0 && port < 65536 ? port : 8787, str(env, "HOST", "127.0.0.1")),
  };
}

function loadHedera(env: NodeJS.ProcessEnv, port: number, host: string): HederaConfig {
  const loopback = host === "0.0.0.0" || host === "::" ? "127.0.0.1" : host;
  const hostPart = loopback.includes(":") ? `[${loopback}]` : loopback;
  return {
    network: str(env, "HEDERA_NETWORK", "testnet").toLowerCase(),
    mirror: str(env, "HEDERA_MIRROR", HEDERA_DEFAULT_MIRROR).replace(/\/+$/, "").replace(/\/api\/v1$/, ""),
    operatorId: str(env, "HEDERA_OPERATOR_ID"),
    operatorKey: str(env, "HEDERA_OPERATOR_KEY"),
    agentId: str(env, "HEDERA_AGENT_ID"),
    agentKey: str(env, "HEDERA_AGENT_KEY"),
    topicId: str(env, "HEDERA_TOPIC_ID"),
    usdc: str(env, "HEDERA_USDC", HEDERA_TESTNET_USDC),
    facilitator: str(env, "X402_FACILITATOR", X402_DEFAULT_FACILITATOR).replace(/\/+$/, ""),
    facilitatorFallback: str(env, "X402_FACILITATOR_FALLBACK", X402_DEFAULT_FALLBACK).replace(/\/+$/, ""),
    feePayers: str(env, "X402_FEE_PAYERS")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    resourceBase: str(env, "HEDERA_RESOURCE_BASE", `http://${hostPart}:${port}`).replace(/\/+$/, ""),
    maxPriceC: intOrNaN(str(env, "HEDERA_MAX_PRICE_C", "10")),
    bookDayC: intOrNaN(str(env, "HEDERA_BOOK_DAY_C", "100")),
    agentDayC: intOrNaN(str(env, "HEDERA_AGENT_DAY_C", "500")),
    liveTopicId: str(env, "HEDERA_LIVE_TOPIC_ID"),
  };
}

function intOrNaN(text: string): number {
  return /^-?\d+$/.test(text) ? Number.parseInt(text, 10) : Number.NaN;
}

function loadArkiv(env: NodeJS.ProcessEnv): ArkivConfig {
  return {
    rpc: str(env, "ARKIV_RPC", ARKIV_DEFAULT_RPC).replace(/\/+$/, ""),
    chainId: intOrNaN(str(env, "ARKIV_CHAIN_ID", String(ARKIV_DEFAULT_CHAIN_ID))),
    accessKey: str(env, "ARKIV_ACCESS_KEY"),
    checkerKey: str(env, "ARKIV_CHECKER_KEY"),
    strangerKey: str(env, "ARKIV_STRANGER_KEY"),
    ghostSecret: str(env, "ARKIV_GHOST_SECRET"),
    season: intOrNaN(str(env, "ARKIV_SEASON", "1")),
    seasonEnd: str(env, "ARKIV_SEASON_END"),
    priceC: intOrNaN(str(env, "ARKIV_GHOST_PRICE_C", "10")),
    mockPayments: str(env, "ARKIV_MOCK_PAYMENTS") === "1",
    replay: str(env, "CHECKER_REPLAY"),
    wsl: str(env, "CHECKER_WSL"),
  };
}

/** The RPC URL the service itself uses: ARKIV_RPC with the access key as its last path segment. */
export function arkivRpcUrl(a: ArkivConfig): string {
  return a.accessKey === "" ? a.rpc : `${a.rpc}/${encodeURIComponent(a.accessKey)}`;
}

export const PRIVATE_KEY_RE = /^0x[0-9a-fA-F]{64}$/;
export const GHOST_SECRET_RE = /^[0-9a-fA-F]{64}$/;

/** The season's end as a Date, or null when ARKIV_SEASON_END is missing or not an ISO 8601 instant. */
export function seasonEndDate(a: ArkivConfig): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.test(a.seasonEnd)) return null;
  const d = new Date(a.seasonEnd);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** When run rows expire: the season's end plus RUN_GRACE_DAYS. Null without a season end. */
export function runExpiry(a: ArkivConfig): Date | null {
  const end = seasonEndDate(a);
  return end ? new Date(end.getTime() + RUN_GRACE_DAYS * DAY_MS) : null;
}

/**
 * What keeps Arkiv writes off, by .env name (never a value). Empty: the configuration is complete.
 * Checked: SERVER_SECRET (books and runner ids), the RPC and chain id, the checker key and ghost
 * secret are well-formed, the season, the season end (season end + 30 d after now and within
 * ~180 d of it), the price and the replay tool.
 */
export function arkivProblems(c: Config, nowMs = Date.now()): string[] {
  const a = c.arkiv;
  const out: string[] = [];
  if (!secretReady(c)) out.push("SERVER_SECRET");
  let rpcOk = false;
  try {
    rpcOk = /^https?:$/.test(new URL(a.rpc).protocol);
  } catch {
    rpcOk = false;
  }
  if (!rpcOk) out.push("ARKIV_RPC");
  if (!Number.isInteger(a.chainId) || a.chainId <= 0) out.push("ARKIV_CHAIN_ID");
  if (!PRIVATE_KEY_RE.test(a.checkerKey)) out.push("ARKIV_CHECKER_KEY");
  if (!GHOST_SECRET_RE.test(a.ghostSecret)) out.push("ARKIV_GHOST_SECRET");
  if (!Number.isInteger(a.season) || a.season < 1 || a.season > 2_147_483_647) out.push("ARKIV_SEASON");
  const expiry = runExpiry(a);
  if (!expiry || expiry.getTime() <= nowMs || expiry.getTime() > nowMs + MAX_RUN_LIFETIME_DAYS * DAY_MS) {
    out.push("ARKIV_SEASON_END");
  }
  if (!Number.isInteger(a.priceC) || a.priceC < 0 || a.priceC > 1_000_000) out.push("ARKIV_GHOST_PRICE_C");
  if (!a.replay.includes("{game}")) out.push("CHECKER_REPLAY");
  if (a.wsl !== "" && !/^[A-Za-z0-9._-]{1,64}$/.test(a.wsl)) out.push("CHECKER_WSL");
  return out;
}

/** Arkiv writes can run, as far as configuration goes (see arkivProblems). */
export function arkivReady(c: Config, nowMs = Date.now()): boolean {
  return arkivProblems(c, nowMs).length === 0;
}

/** SERVER_SECRET keys every HMAC (runner ids, stored nullifiers, bound subs): at least 32 chars. */
export function secretReady(c: Config): boolean {
  return c.serverSecret.length >= 32;
}

/** IDKit can run: app id, rp id, a 32-byte hex signing key, a known environment and the HMAC secret. */
export function idkitReady(c: Config): boolean {
  const w = c.world;
  return (
    /^app_[A-Za-z0-9_]+$/.test(w.appId) &&
    /^rp_[A-Za-z0-9_]+$/.test(w.rpId) &&
    /^(0x)?[0-9a-fA-F]{64}$/.test(w.signingKey) &&
    /^[A-Za-z0-9._-]{1,64}$/.test(w.action) &&
    ENVIRONMENTS.includes(w.environment) &&
    secretReady(c)
  );
}

/** Agent Pass can run: an https issuer, the confidential client's id and secret, and the HMAC secret. */
export function agentpassReady(c: Config): boolean {
  const a = c.agentpass;
  let issuerOk = false;
  try {
    issuerOk = new URL(a.issuer).protocol === "https:";
  } catch {
    issuerOk = false;
  }
  return issuerOk && a.clientId !== "" && a.clientSecret !== "" && secretReady(c);
}

/**
 * Which provider runs the listing approvals (the /agentpass/* routes). APPROVALS=idkit|agentpass;
 * unset or unknown: idkit when Agent Pass is not configured and IDKit is, else agentpass.
 * `available`: the chosen provider's configuration is present.
 */
export function chooseApprovals(c: Config): { kind: "idkit" | "agentpass"; available: boolean } {
  const kind =
    c.approvals === "idkit" || c.approvals === "agentpass"
      ? c.approvals
      : !agentpassReady(c) && idkitReady(c)
        ? "idkit"
        : "agentpass";
  return { kind, available: kind === "idkit" ? idkitReady(c) : agentpassReady(c) };
}

function httpUrl(text: string, httpsOnly = false): boolean {
  try {
    const u = new URL(text);
    return httpsOnly ? u.protocol === "https:" : /^https?:$/.test(u.protocol);
  } catch {
    return false;
  }
}

const capOk = (n: number) => Number.isInteger(n) && n >= 0 && n <= 1_000_000;

/**
 * What keeps the LISTING record (HCS) off, by .env name: testnet, a mirror URL, the operator's id
 * and DER key, the market topic. Empty: /hedera/record can run.
 */
export function hederaRecordProblems(c: Config): string[] {
  const h = c.hedera;
  const out: string[] = [];
  if (h.network !== "testnet") out.push("HEDERA_NETWORK");
  if (!httpUrl(h.mirror)) out.push("HEDERA_MIRROR");
  if (!ACCOUNT_RE.test(h.operatorId)) out.push("HEDERA_OPERATOR_ID");
  if (!DER_KEY_RE.test(h.operatorKey)) out.push("HEDERA_OPERATOR_KEY");
  if (!ACCOUNT_RE.test(h.topicId)) out.push("HEDERA_TOPIC_ID");
  return out;
}

/**
 * What keeps Hedera payments off, by .env name: everything the record needs (INTENT and RECEIPT go
 * to the same topic), the agent's id and DER key, USDC, the facilitators, the resource base, the
 * caps, and the Arkiv values the paywall reads with (the checker, the ghost secret, SERVER_SECRET).
 * Empty: PB can pay, /x402/ghost sells, and /arkiv/ghost takes only settled receipts.
 */
export function hederaPayProblems(c: Config): string[] {
  const h = c.hedera;
  const out = hederaRecordProblems(c);
  if (!ACCOUNT_RE.test(h.agentId)) out.push("HEDERA_AGENT_ID");
  if (!DER_KEY_RE.test(h.agentKey)) out.push("HEDERA_AGENT_KEY");
  if (!ACCOUNT_RE.test(h.usdc)) out.push("HEDERA_USDC");
  if (!httpUrl(h.facilitator, true)) out.push("X402_FACILITATOR");
  if (h.facilitatorFallback !== "" && !httpUrl(h.facilitatorFallback, true)) out.push("X402_FACILITATOR_FALLBACK");
  if (!h.feePayers.every((f) => ACCOUNT_RE.test(f))) out.push("X402_FEE_PAYERS");
  if (!httpUrl(h.resourceBase)) out.push("HEDERA_RESOURCE_BASE");
  if (!capOk(h.maxPriceC)) out.push("HEDERA_MAX_PRICE_C");
  if (!capOk(h.bookDayC)) out.push("HEDERA_BOOK_DAY_C");
  if (!capOk(h.agentDayC)) out.push("HEDERA_AGENT_DAY_C");
  if (!secretReady(c)) out.push("SERVER_SECRET");
  if (!PRIVATE_KEY_RE.test(c.arkiv.checkerKey)) out.push("ARKIV_CHECKER_KEY");
  if (!GHOST_SECRET_RE.test(c.arkiv.ghostSecret)) out.push("ARKIV_GHOST_SECRET");
  if (!capOk(c.arkiv.priceC)) out.push("ARKIV_GHOST_PRICE_C");
  return [...new Set(out)];
}

/** Every Hedera name that is missing or malformed (the startup log names them; never a value). */
export function hederaProblems(c: Config): string[] {
  return hederaPayProblems(c);
}

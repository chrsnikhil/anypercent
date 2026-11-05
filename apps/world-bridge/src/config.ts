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
}

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
      action: str(env, "WORLD_ACTION", "anypercent-record-book"),
      environment: (ENVIRONMENTS as readonly string[]).includes(envName)
        ? (envName as WorldEnvironment)
        : ("invalid" as WorldEnvironment),
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
  };
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

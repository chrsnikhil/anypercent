/**
 * Entry point: `npm start`. Loads apps/world-bridge/.env (if present), wires whatever is configured,
 * and serves the HTTP contract. Missing configuration never stops the service: /health reports the
 * missing parts as false and their start endpoints answer 503 with the step's down failure.
 */
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { AgentPass } from "./agentpass.js";
import type { ApprovalProvider } from "./approvals.js";
import { chooseApprovals, idkitReady, loadConfig, secretReady } from "./config.js";
import { IdkitSessions, realIdkitDeps } from "./idkit.js";
import { IdkitApprovals } from "./idkit-approvals.js";
import { WorldIdp } from "./oidc.js";
import { buildServer, makeHealth } from "./server.js";
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
        log,
      })
    : null;

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

const health = () => makeHealth(idkit, approvals, reachable);

const server = buildServer({ health, idkit, approvals, log });
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
});

function shutdown(): void {
  idkit?.stopAll();
  approvals?.stopAll();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1000).unref();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

/**
 * npm run arkiv:open-run -- --game MDGP --label TEAM --log <path to .acl>
 *
 * Writes one open-tier run row from the team's own logs (spec: Decisions 3): the same replay check
 * as /arkiv/publish, then a run row with the plain `log` (anyone can replay it), no book, no person:
 * `label` is a display name such as TEAM (never a person's name), `runner` an HMAC of
 * "open|<label>", `human` false. No listing. A log already on the board is not written twice.
 * Labels starting with BOT- are refused: BOT rows come only from a house batch its owner approved in
 * World App (npm run house:publish).
 *
 * The shipped test logs live in the WSL sandbox; from Windows, pass them by their \\wsl.localhost path.
 * Do not run this while the service is publishing: both sign with the checker's wallet.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { CheckerError, parseHeader, RealChecker, verdict } from "../src/arkiv/checker.js";
import { SdkArkiv } from "../src/arkiv/client.js";
import { sha256Hex } from "../src/arkiv/ghost.js";
import { fmtTime } from "../src/arkiv/publish.js";
import { GAMES, RUN_FLAGS } from "../src/arkiv/schema.js";
import { arkivProblems, arkivRpcUrl, runExpiry } from "../src/config.js";
import { runnerId } from "../src/hmac.js";
import { arg, die, loadEnv, why } from "./arkiv-common.js";

const cfg = loadEnv();
const ak = cfg.arkiv;
const game = arg("game") ?? "";
const label = (arg("label") ?? "").toUpperCase();
const logPath = arg("log") ?? "";

async function main(): Promise<void> {
  if (!GAMES[game]) die(`--game must be one of ${Object.keys(GAMES).join(", ")}`);
  if (!/^[A-Z0-9][A-Z0-9-]{0,11}$/.test(label)) die("--label must be 1-12 of A-Z, 0-9 and -, e.g. TEAM (never a person's name)");
  if (label.startsWith("BOT-")) die("BOT- labels come only from a World-approved house batch: npm run house:publish -- --dir <ghostgen output>");
  if (!logPath) die("--log <path to the .acl> is required");
  const missing = arkivProblems(cfg).filter((n) => n !== "ARKIV_GHOST_SECRET");
  if (missing.length) die(`set these in .env first: ${missing.join(", ")}`);

  const log = Uint8Array.from(readFileSync(logPath));
  const header = parseHeader(log);
  if (!header || log.length > 64 * 1024) die("not a plain .acl log (ACL1, 32 B to 64 KiB)");
  if (header.game !== game) die(`the log is ${header.game}'s, not ${game}'s`);
  const logH = sha256Hex(log);

  const checker = new RealChecker({ replay: ak.replay, wsl: ak.wsl, dir: join(cfg.dataDir, "checker") });
  let frames: number;
  let tool: string;
  try {
    const v = verdict(game, await checker.replay(game, logH, log));
    if (!v.ok) die(`the replay refused the log: ${v.why}`);
    frames = v.frames;
    tool = await checker.toolTag(game);
  } catch (err) {
    die(`replay tool: ${err instanceof CheckerError ? err.message : "error"}`);
  }
  console.log(`replayed ${game} ${fmtTime(frames)} (${frames} frames), ${tool}`);

  const port = new SdkArkiv({ rpcUrl: arkivRpcUrl(ak), accessKey: ak.accessKey, checkerKey: ak.checkerKey });
  const existing = await port.runByLogHash(logH);
  if (existing) {
    console.log(`already on the board: run ${existing.key} (${existing.book ?? existing.label ?? existing.runner})`);
    return;
  }
  const w = await port.writeRun({
    values: {
      game,
      title: GAMES[game],
      season: ak.season,
      rules: header.rules,
      frames,
      log_h: logH,
      runner: runnerId(cfg.serverSecret, `open|${label}`),
      label,
      human: false,
      tool,
      log,
    },
    flags: { ...RUN_FLAGS },
    expiry: { kind: "atDate", date: runExpiry(ak)!, atLeastDays: 1 },
  });
  console.log(`arkiv open-run ${label} ${game} ${fmtTime(frames)}: run ${w.run} tx ${w.tx}`);
}

main().catch((err: unknown) => die(`arkiv:open-run: ${why(err, cfg)}`));

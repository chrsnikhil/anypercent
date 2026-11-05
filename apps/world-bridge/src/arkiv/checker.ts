/**
 * The checker: every time on the board was replayed here before it was written.
 *
 * - The log header (arcade/py/arcade_save.py parse_log_header): 32 bytes, "ACL1", the game's id in
 *   bytes 4-8, then u32 LE rules version, seed, frames, final hash, score and trophies.
 * - The tool is the game's own `arcade_replay` (CHECKER_REPLAY, `{game}` -> the arcade id). It
 *   prints one JSON line: {"game", "frames", "final_hash", "claimed_hash", "hash_matches",
 *   "complete", "claims_match", "finished", "score", "time_frames", "trophies"}.
 * - On Windows the tools are the WSL sandbox's Linux builds: CHECKER_WSL runs them through
 *   `wsl.exe -d <distro> -e`, with C:\ paths mapped to /mnt/c/.
 * - The tool's hash goes on every row (`tool`), so a row says which build checked it.
 */
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

export const LOG_MIN = 32;
export const LOG_MAX = 64 * 1024;
export const REPLAY_TIMEOUT_MS = 30_000;

export interface LogHeader {
  game: string;
  rules: number;
  /** The frames the log claims (the replay re-derives the time itself). */
  frames: number;
}

/** The header of a plain .acl log, or null when it is not one. */
export function parseHeader(log: Uint8Array): LogHeader | null {
  if (log.length < LOG_MIN) return null;
  const b = Buffer.from(log.buffer, log.byteOffset, log.byteLength);
  if (b.toString("latin1", 0, 4) !== "ACL1") return null;
  return { game: b.toString("latin1", 4, 8), rules: b.readUInt32LE(8), frames: b.readUInt32LE(16) };
}

export interface ReplayResult {
  game: string;
  hash_matches: boolean;
  complete: boolean;
  claims_match: boolean;
  finished: boolean;
  time_frames: number;
}

export type Verdict = { ok: true; frames: number } | { ok: false; why: string };

/** Accept only a replay of this game that matches its hash, ran to completion, matches its claims and finished. */
export function verdict(game: string, r: ReplayResult): Verdict {
  if (r.game !== game) return { ok: false, why: `the tool replayed ${r.game}, not ${game}` };
  for (const k of ["hash_matches", "complete", "claims_match", "finished"] as const) {
    if (r[k] !== true) return { ok: false, why: `${k} is false` };
  }
  if (!Number.isInteger(r.time_frames) || r.time_frames <= 0) return { ok: false, why: "no finish time" };
  return { ok: true, frames: r.time_frames };
}

/** A tool that could not run, or ran out of time. Its message holds no log bytes and no secrets. */
export class CheckerError extends Error {}

export interface CheckerPort {
  /** Replay a log with its game's tool. Throws CheckerError on a tool error or timeout. */
  replay(game: string, logH: string, log: Uint8Array): Promise<ReplayResult>;
  /** "arcade_replay sha256:<first 12 hex of the tool binary>". Throws CheckerError. */
  toolTag(game: string): Promise<string>;
}

/** C:\Users\x\a.acl -> /mnt/c/Users/x/a.acl (paths already POSIX pass through). */
export function toWslPath(p: string): string {
  const m = /^([A-Za-z]):[\\/](.*)$/.exec(p);
  if (!m) return p.replace(/\\/g, "/");
  return `/mnt/${m[1].toLowerCase()}/${m[2].replace(/\\/g, "/")}`;
}

export type Exec = (cmd: string, args: string[], timeoutMs: number) => Promise<string>;

const realExec: Exec = (cmd, args, timeoutMs) =>
  new Promise((ok, fail) => {
    execFile(cmd, args, { timeout: timeoutMs, windowsHide: true, maxBuffer: 1 << 20 }, (err, stdout) => {
      if (err) {
        const e = err as NodeJS.ErrnoException & { killed?: boolean; code?: string | number };
        fail(new CheckerError(e.killed ? "timed out" : `exit ${String(e.code ?? "error")}`));
      } else ok(String(stdout));
    });
  });

export interface RealCheckerOptions {
  /** CHECKER_REPLAY, with {game}. */
  replay: string;
  /** CHECKER_WSL distro, or "" to run the tool directly. */
  wsl: string;
  /** Where logs are written before a replay (data/checker). */
  dir: string;
  timeoutMs?: number;
  exec?: Exec;
}

export class RealChecker implements CheckerPort {
  private readonly tags = new Map<string, string>();
  private readonly exec: Exec;

  constructor(private readonly opts: RealCheckerOptions) {
    this.exec = opts.exec ?? realExec;
  }

  private tool(game: string): string {
    if (!/^[A-Z0-9]{4}$/.test(game)) throw new CheckerError("bad game id");
    return this.opts.replay.replaceAll("{game}", game);
  }

  private run(argv: string[], timeoutMs: number): Promise<string> {
    if (this.opts.wsl) return this.exec("wsl.exe", ["-d", this.opts.wsl, "-e", ...argv], timeoutMs);
    return this.exec(argv[0], argv.slice(1), timeoutMs);
  }

  async replay(game: string, logH: string, log: Uint8Array): Promise<ReplayResult> {
    if (!/^[0-9a-f]{64}$/.test(logH)) throw new CheckerError("bad log hash");
    mkdirSync(this.opts.dir, { recursive: true });
    const file = resolve(join(this.opts.dir, `${logH}.acl`));
    writeFileSync(file, log);
    const path = this.opts.wsl ? toWslPath(file) : file;
    const out = await this.run([this.tool(game), path], this.opts.timeoutMs ?? REPLAY_TIMEOUT_MS);
    const line = out.trim().split(/\r?\n/).pop() ?? "";
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      throw new CheckerError("the tool printed no JSON");
    }
    const r = parsed as Record<string, unknown>;
    if (typeof r.game !== "string" || typeof r.time_frames !== "number") throw new CheckerError("unexpected tool output");
    return {
      game: r.game,
      hash_matches: r.hash_matches === true,
      complete: r.complete === true,
      claims_match: r.claims_match === true,
      finished: r.finished === true,
      time_frames: r.time_frames,
    };
  }

  async toolTag(game: string): Promise<string> {
    const cached = this.tags.get(game);
    if (cached) return cached;
    const tool = this.tool(game);
    let hex: string;
    if (this.opts.wsl) {
      const out = await this.run(["sha256sum", tool], 15_000);
      const m = /^([0-9a-f]{64})\s/.exec(out.trim());
      if (!m) throw new CheckerError("could not hash the tool");
      hex = m[1];
    } else {
      try {
        hex = createHash("sha256").update(readFileSync(tool)).digest("hex");
      } catch {
        throw new CheckerError("could not read the tool");
      }
    }
    const tag = `arcade_replay sha256:${hex.slice(0, 12)}`;
    this.tags.set(game, tag);
    return tag;
  }
}

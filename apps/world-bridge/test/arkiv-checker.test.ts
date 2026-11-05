/** The checker: the .acl header, the verdict, WSL path mapping, and how the tool is run. */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";
import { CheckerError, parseHeader, RealChecker, toWslPath, verdict, type Exec } from "../src/arkiv/checker.js";
import { makeLog } from "./fake-arkiv.js";
import { tempDir } from "./helpers.js";

const OUT = '{"game":"MDGP","frames":6461,"final_hash":576543229,"claimed_hash":576543229,"hash_matches":true,"complete":true,"claims_match":true,"finished":true,"score":1,"time_frames":6076,"trophies":15}\n';
const H = "a".repeat(64);

describe("the log header", () => {
  it("ACL1, the game in bytes 4-8, rules = u32 LE at offset 8", () => {
    assert.deepEqual(parseHeader(makeLog("MDGP", 4, 6461)), { game: "MDGP", rules: 4, frames: 6461 });
    assert.deepEqual(parseHeader(makeLog("SHIP", 0x01020304)), { game: "SHIP", rules: 0x01020304, frames: 6461 });
  });
  it("not a log: too short, or not ACL1", () => {
    assert.equal(parseHeader(makeLog().subarray(0, 31)), null);
    const b = Buffer.from(makeLog());
    b.write("ACG1", 0, "latin1");
    assert.equal(parseHeader(b), null);
  });
});

describe("the verdict", () => {
  const ok = { game: "MDGP", hash_matches: true, complete: true, claims_match: true, finished: true, time_frames: 6076 };
  it("accepts only a full, matching, finished replay of the same game", () => {
    assert.deepEqual(verdict("MDGP", ok), { ok: true, frames: 6076 });
    for (const k of ["hash_matches", "complete", "claims_match", "finished"] as const) {
      assert.equal(verdict("MDGP", { ...ok, [k]: false }).ok, false, k);
    }
    assert.equal(verdict("RUSH", ok).ok, false);
    assert.equal(verdict("MDGP", { ...ok, time_frames: 0 }).ok, false);
  });
});

describe("running the tool", () => {
  it("maps Windows paths into WSL", () => {
    assert.equal(toWslPath("C:\\Users\\chrsn\\data\\checker\\x.acl"), "/mnt/c/Users/chrsn/data/checker/x.acl");
    assert.equal(toWslPath("D:/a/b.acl"), "/mnt/d/a/b.acl");
    assert.equal(toWslPath("/home/pi/x.acl"), "/home/pi/x.acl");
  });

  it("through WSL: wsl.exe -d <distro> -e <tool> <log>, with the log written to data/checker/<log_h>.acl", async () => {
    const dir = tempDir();
    const calls: Array<[string, string[], number]> = [];
    const exec: Exec = async (cmd, args, t) => {
      calls.push([cmd, args, t]);
      return args.includes("sha256sum") ? `${"c0ffee".repeat(10)}abcd  /opt/x\n` : OUT;
    };
    const c = new RealChecker({ replay: "/opt/arca-sandbox/games/arcade/{game}/arcade_replay", wsl: "Ubuntu-24.04", dir, exec });
    const log = makeLog();
    const r = await c.replay("MDGP", H, log);
    assert.equal(r.time_frames, 6076);
    assert.equal(r.hash_matches, true);
    const [cmd, args, timeout] = calls[0];
    assert.equal(cmd, "wsl.exe");
    assert.deepEqual(args.slice(0, 4), ["-d", "Ubuntu-24.04", "-e", "/opt/arca-sandbox/games/arcade/MDGP/arcade_replay"]);
    assert.match(args[4], /^\/mnt\/[a-z]\/.*\/aaaa+\.acl$/);
    assert.equal(timeout, 30_000);
    assert.ok(existsSync(join(dir, `${H}.acl`)));
    assert.deepEqual(Uint8Array.from(readFileSync(join(dir, `${H}.acl`))), log);
    assert.equal(await c.toolTag("MDGP"), "arcade_replay sha256:c0ffeec0ffee");
    await c.toolTag("MDGP");
    assert.equal(calls.filter((x) => x[1].includes("sha256sum")).length, 1, "the tag is cached");
  });

  it("directly on Linux (no CHECKER_WSL): <tool> <log>", async () => {
    const calls: string[][] = [];
    const exec: Exec = async (cmd, args) => {
      calls.push([cmd, ...args]);
      return OUT;
    };
    const dir = tempDir();
    await new RealChecker({ replay: "/opt/{game}/arcade_replay", wsl: "", dir, exec }).replay("MDGP", H, makeLog());
    assert.equal(calls[0][0], "/opt/MDGP/arcade_replay");
    assert.equal(calls[0][1], join(dir, `${H}.acl`));
  });

  it("a tool that fails, times out or prints no JSON is a CheckerError", async () => {
    const dir = tempDir();
    const failing: Exec = async () => {
      throw new CheckerError("timed out");
    };
    await assert.rejects(new RealChecker({ replay: "/x/{game}", wsl: "", dir, exec: failing }).replay("MDGP", H, makeLog()), CheckerError);
    await assert.rejects(new RealChecker({ replay: "/x/{game}", wsl: "", dir, exec: async () => "bad log header\n" }).replay("MDGP", H, makeLog()), CheckerError);
    await assert.rejects(new RealChecker({ replay: "/x/{game}", wsl: "", dir, exec: async () => OUT }).replay("../x", H, makeLog()), CheckerError);
  });
});

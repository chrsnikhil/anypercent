/**
 * npm run arkiv:lookalike -- --game MDGP --book ANY-6PS
 *
 * The look-alike demo (spec: Scripts). The STRANGER wallet writes a well-formed anypercent.run row:
 * it copies the board's top row, 600 frames (10 s) faster, under the owner's own book (--book; it
 * must be a book this bridge issued, never another person's). Every column checks out; only
 * `$creator` gives it away. Then it shows the row absent from the pinned board query (Q1) and
 * present, first, without the pin (Q8). The console and the web board must ignore it.
 */
import { SdkArkiv, type RunValues } from "../src/arkiv/client.js";
import { fmtTime } from "../src/arkiv/publish.js";
import * as Q from "../src/arkiv/queries.js";
import { RUN_FLAGS } from "../src/arkiv/schema.js";
import { arkivRpcUrl, PRIVATE_KEY_RE } from "../src/config.js";
import { Store } from "../src/store.js";
import { arg, die, loadEnv, why } from "./arkiv-common.js";

const cfg = loadEnv();
const ak = cfg.arkiv;
const game = arg("game") ?? "MDGP";
const book = arg("book") ?? "";

async function main(): Promise<void> {
  if (!Q.GAME_RE.test(game)) die("--game must be an arcade id such as MDGP");
  if (!Q.BOOK_RE.test(book)) die("--book ANY-XXX is required: the owner's own record book (never another person's)");
  if (!PRIVATE_KEY_RE.test(ak.checkerKey) || !PRIVATE_KEY_RE.test(ak.strangerKey)) die("run npm run arkiv:keygen first");
  const mine = new Store(cfg.dataDir, cfg.serverSecret).recordForBook(book);
  if (!mine) die(`${book} was not issued by this bridge: use the owner's own book`);

  const rpcUrl = arkivRpcUrl(ak);
  const checker = new SdkArkiv({ rpcUrl, accessKey: ak.accessKey, checkerKey: ak.checkerKey });
  const stranger = new SdkArkiv({ rpcUrl, accessKey: ak.accessKey, checkerKey: ak.strangerKey });
  const C = checker.checker!;

  const board = await checker.query(Q.q1Board(game, ak.season, C), Q.selectOf(Q.RUN_BOARD_ATTRS), 1);
  const topKey = (board.data[0] as { key?: string } | undefined)?.key;
  if (!topKey) die(`no ${game} run on the board to copy yet`);
  const top = await checker.getRun(topKey, true);
  if (!top) die("the top row did not validate");
  console.log(`top of the ${game} board: ${top.book ?? top.label} ${fmtTime(Number(top.frames))} (run ${top.key})`);

  const fake: RunValues = {
    game: top.game,
    title: top.title ?? game,
    season: top.season ?? ak.season,
    rules: Number(top.rules ?? 0n),
    frames: Number(top.frames) - 600,
    log_h: top.log_h,
    runner: mine.runner_id,
    book,
    human: true,
    credential: mine.credential,
    tool: top.tool ?? "arcade_replay",
    ...(top.log_enc ? { log_enc: top.log_enc } : { log: top.log }),
  };
  const w = await stranger.writeRun({ values: fake, flags: { ...RUN_FLAGS }, expiry: { kind: "days", days: 30 } });
  console.log(`stranger ${stranger.checker} wrote a look-alike: ${book} ${fmtTime(fake.frames)} (run ${w.run}, tx ${w.tx})`);

  await new Promise((r) => setTimeout(r, 2500));
  const pinned = await checker.query(Q.q1Board(game, ak.season, C), Q.selectOf(Q.RUN_BOARD_ATTRS));
  const any = await checker.query(Q.q8AnyWallet(game, ak.season), Q.selectOf(Q.RUN_BOARD_ATTRS));
  const has = (data: unknown[]) => (data as Array<{ key: string }>).some((e) => e.key.toLowerCase() === w.run);
  console.log(`Q1 (pinned to the checker): ${has(pinned.data) ? "PRESENT (wrong)" : "absent: the board ignores it"}`);
  console.log(`Q8 (no pin): ${has(any.data) ? "present" : "absent"}; first row ${(any.data[0] as { key?: string })?.key ?? "-"}`);
  console.log(`\nQ1: ${Q.q1Board(game, ak.season, C)}\nQ8: ${Q.q8AnyWallet(game, ak.season)}`);
}

main().catch((err: unknown) => die(`arkiv:lookalike: ${why(err, cfg)}`));

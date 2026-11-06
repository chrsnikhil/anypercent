/**
 * npm run arkiv:fund -- --to 0x... --amount 1
 *
 * Sends tGLM from the checker wallet to a console's own Arkiv wallet (or the house wallet), so it can
 * pay the gas of the run and listing it writes itself (spec: Funding). The console shows its wallet
 * on My record book (short form) and logs the full address once; `npm run console:link` prints it in
 * full too. The owner runs this: there is no faucet for strangers' consoles.
 *
 * Prints the transaction hash, its explorer link and both balances after. At most MAX_FUND_GLM per
 * run (a typo never drains the checker, whose tGLM pays for every stamp). Never prints a key.
 */
import { pathToFileURL } from "node:url";
import { formatEther, getAddress, parseEther, type Hex } from "viem";
import { explorerLinks, PRIVATE_KEY_RE } from "../src/config.js";
import { arg, clientsFor, die, glm, loadEnv, why } from "./arkiv-common.js";

/** The most one run sends, in tGLM. */
export const MAX_FUND_GLM = 10;

/** The transfer `--to` and `--amount` ask for, checked; or why not. */
export function fundPlan(to: string | undefined, amount: string | undefined, checker: string): { to: Hex; wei: bigint } | { error: string } {
  if (!to || !/^0x[0-9a-fA-F]{40}$/.test(to)) return { error: "--to must be a wallet address: 0x and 40 hex (the console's, as console:link prints it)" };
  if (/^0x0{40}$/.test(to)) return { error: "--to is the zero address" };
  if (to.toLowerCase() === checker.toLowerCase()) return { error: "--to is the checker itself" };
  if (!amount || !/^\d{1,6}(\.\d{1,18})?$/.test(amount)) return { error: "--amount is tGLM as a decimal, e.g. 1 or 0.5" };
  const wei = parseEther(amount);
  if (wei <= 0n) return { error: "--amount must be above 0" };
  if (wei > parseEther(String(MAX_FUND_GLM))) return { error: `--amount is at most ${MAX_FUND_GLM} tGLM a run` };
  return { to: getAddress(to), wei };
}

async function main(): Promise<void> {
  const cfg = loadEnv();
  if (!PRIVATE_KEY_RE.test(cfg.arkiv.checkerKey)) die("ARKIV_CHECKER_KEY is missing: run npm run arkiv:keygen first");
  const checker = clientsFor(cfg, cfg.arkiv.checkerKey);
  if (!checker.wallet || !checker.address) die("ARKIV_CHECKER_KEY does not make a wallet");
  const plan = fundPlan(arg("to"), arg("amount"), checker.address);
  if ("error" in plan) die(`Usage: npm run arkiv:fund -- --to 0x<wallet> --amount 1\n${plan.error}`);
  try {
    const before = await checker.pub.getBalance({ address: checker.address as Hex });
    if (before < plan.wei) die(`the checker ${checker.address} has ${glm(before)} tGLM, less than ${formatEther(plan.wei)}: fund it at https://hub.arkiv.network/faucet`);
    console.log(`sending ${formatEther(plan.wei)} tGLM from the checker ${checker.address} to ${plan.to} ...`);
    const hash = await checker.wallet.sendTransaction({ to: plan.to, value: plan.wei } as never);
    const receipt = await checker.pub.waitForTransactionReceipt({ hash });
    if (receipt.status !== "success") die(`the transfer did not go through (status ${receipt.status}), tx ${hash}`);
    const link = explorerLinks(cfg.explorer).tx(hash);
    console.log(`tx       ${hash}${link ? `\n         ${link}` : ""}`);
    console.log(`checker  ${glm(await checker.pub.getBalance({ address: checker.address as Hex }))} tGLM`);
    console.log(`wallet   ${plan.to}: ${glm(await checker.pub.getBalance({ address: plan.to }))} tGLM (enough to sign its own listings)`);
  } catch (err) {
    die(`arkiv:fund: ${why(err, cfg)}`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) void main();

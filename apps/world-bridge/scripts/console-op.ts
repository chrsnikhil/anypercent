/**
 * npm run console:link -- --console C-7QZP --book ANY-6PS
 * npm run console:release -- --console C-7QZP [--book ANY-6PS]
 *
 * The owner's console ops (one console, one person). The console shows its tag on My record book.
 * Each op starts one World session approval of the book's owner on the running bridge, with the
 * exact text World App shows:
 *
 *   link:    Link console C-7QZP (wallet 0x1a2b…9f3e) to record book ANY-6PS: PB on it spends this book's coach budget
 *   release: Release console C-7QZP from record book ANY-6PS
 *
 * and changes the binding only after that approval is recorded (checked as publish checks one, then
 * spent on this op). Ctrl-C cancels it. The console follows within 5 s. Prints the text, the QR and
 * the code, the stages, and the console's binding at the end. [--bridge http://HOST:PORT]
 *
 * The link names the Arkiv wallet the console reported (its runs are stamped only from that wallet;
 * a console that reported none is linked with the text above minus the wallet). A bound console
 * that reports a new wallet takes one more link to its own book.
 */
import { arg, bridgeBase, call, die, follow, loadEnv, row, showApproval } from "./approve-common.js";

const op = process.argv[2];
const cfg = loadEnv();
const tag = (arg("console") ?? "").toUpperCase();
const book = arg("book")?.toUpperCase();
const base = bridgeBase(cfg, arg("bridge"));

if (op !== "link" && op !== "release") die("Usage: npm run console:link -- --console C-XXXX --book ANY-XXX | npm run console:release -- --console C-XXXX");
if (!/^C-[A-Z2-9]{4}$/.test(tag)) die("--console is the console's tag, C- and 4 characters, as My record book shows it (e.g. C-7QZP).");
if (op === "link" && !book) die("--book ANY-XXX: the record book to link the console to.");

const started = await call(base, "POST", "/console/op", { op, console: tag, ...(book ? { book } : {}) });
if (started.status !== 200) {
  const why: Record<string, string> = {
    unknown_console: `no console ${tag} has asked this bridge (open My record book on it first)`,
    unknown_book: `${book} is not a record book of this bridge`,
    already_bound: `${tag} is already linked: release it first`,
    not_bound: `${tag} is not linked${book ? ` to ${book}` : ""}`,
    approvals_not_configured: "World approvals are not configured on the bridge",
    world_unavailable: "World cannot be reached right now",
  };
  die(`${op} refused: ${why[started.json.error] ?? `${started.status} ${started.json.error ?? "no answer"}`}`);
}
await showApproval(String(started.json.action), started.json.approval);
const done = await follow(base, `/console/op/${started.json.id}`, `/console/op/${started.json.id}/cancel`, {
  scan: "waiting for the scan",
  approve: "waiting for the approval in World App",
  apply: "approved: changing the binding",
  done: "done",
});
if (done.ok !== true) die(`${op} did not happen: ${done.failure} (nothing changed)`);
console.log("");
row("console", String(done.data.tag));
row("state", done.data.state === "bound" ? `linked to ${done.data.book}` : String(done.data.state));
console.log("The console follows within 5 s (GET /console/{id} with its health check).");

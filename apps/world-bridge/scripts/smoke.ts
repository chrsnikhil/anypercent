/**
 * Live smoke test against a RUNNING bridge (npm start in another terminal), for the owner once
 * apps/world-bridge/.env has real values. Never prints tokens, device codes, subs or secrets: only
 * what the console itself would show (the QR link and the short code) and the outcome.
 *
 *   npm run smoke                      health, then one IDKit sign-up (scan with World App, or paste
 *                                      the link into simulator.worldcoin.org when WORLD_ENVIRONMENT=staging)
 *   npm run smoke -- --agentpass ANY-XXX   one Agent Pass approval for that book
 *   BRIDGE_URL=http://172.18.96.1:8787 npm run smoke   another address
 */
const base = (process.env.BRIDGE_URL ?? "http://127.0.0.1:8787").replace(/\/+$/, "");
const args = process.argv.slice(2);
const apIdx = args.indexOf("--agentpass");

async function j(method: string, path: string, body?: unknown): Promise<{ status: number; json: any }> {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  });
  return { status: res.status, json: await res.json() };
}

async function follow(path: string, maxS: number): Promise<any> {
  let last = "";
  const end = Date.now() + maxS * 1000;
  while (Date.now() < end) {
    const v = (await j("GET", path)).json;
    if (v.stage !== last) {
      console.log(`  stage: ${v.stage}`);
      last = v.stage;
    }
    if (v.stage === "done") return v;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("no answer in time");
}

async function main(): Promise<void> {
  const h = await j("GET", "/health");
  console.log(`health: ${JSON.stringify(h.json)}`);

  if (apIdx >= 0) {
    const book = args[apIdx + 1];
    if (!h.json.agentpass) throw new Error("agentpass is not configured in .env");
    const s = await j("POST", "/agentpass/start", { book, action: "smoke test approval" });
    if (s.status !== 200) throw new Error(`start failed: ${JSON.stringify(s.json)}`);
    console.log(`open on the phone: ${s.json.qr}`);
    console.log(`user code: ${s.json.code}   expires in ${s.json.expires_s} s`);
    const v = await follow(`/agentpass/${s.json.id}`, s.json.expires_s + 10);
    console.log(v.ok ? `APPROVED (jti received)${v.data.ignored ? ", ignored" : ""}` : `FAILED: ${v.failure}`);
    return;
  }

  if (!h.json.idkit) throw new Error("idkit is not configured in .env");
  const s = await j("POST", "/idkit/start", { console: "smoke" });
  if (s.status !== 200) throw new Error(`start failed: ${JSON.stringify(s.json)}`);
  console.log(`World App link (the console's QR): ${s.json.qr}`);
  console.log(`display code: ${s.json.code}   expires in ${s.json.expires_s} s`);
  const v = await follow(`/idkit/${s.json.id}`, s.json.expires_s + 15);
  console.log(v.ok ? `VERIFIED: book ${v.data.book} (${v.data.credential})` : `FAILED: ${v.failure}${v.data.book ? ` (existing book ${v.data.book})` : ""}`);
}

main().catch((e: unknown) => {
  console.error(`smoke: ${(e as Error).message}`);
  process.exit(1);
});

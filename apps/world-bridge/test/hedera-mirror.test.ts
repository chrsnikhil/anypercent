/**
 * The public mirror's own query rules, which the fake mirror cannot catch: a topic read "after message N" must be
 * sent as sequencenumber=gte:N+1. The mirror refuses gt:0 ("Invalid parameter: sequencenumber", sequence numbers start
 * at 1), so reading after nothing (a topic's first message) silently came back empty.
 */
import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { RestMirror } from "../src/hedera/net.js";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

function capture(): string[] {
  const urls: string[] = [];
  globalThis.fetch = (async (url: string | URL) => {
    urls.push(String(url));
    return new Response(JSON.stringify({ messages: [] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return urls;
}

describe("RestMirror topic reads", () => {
  it("asks for messages after N as sequencenumber=gte:N+1, never gt:0", async () => {
    const urls = capture();
    const mirror = new RestMirror("https://mirror.example");
    await mirror.topicMessages("0.0.7", { afterSeq: "0", limit: 1 });
    await mirror.topicMessages("0.0.7", { afterSeq: "41" });
    const q0 = new URL(urls[0]).searchParams, q41 = new URL(urls[1]).searchParams;
    assert.equal(q0.get("sequencenumber"), "gte:1");
    assert.equal(q41.get("sequencenumber"), "gte:42");
    assert.ok(!urls.some((u) => u.includes("gt%3A0") || u.includes("gt:0")));
  });

  it("reads from the start with no sequence filter when there is no afterSeq", async () => {
    const urls = capture();
    await new RestMirror("https://mirror.example").topicMessages("0.0.7");
    assert.equal(new URL(urls[0]).searchParams.get("sequencenumber"), null);
  });
});

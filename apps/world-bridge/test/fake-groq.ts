/**
 * Groq for the scout tests, two ways: FakeGroq is a GroqPort that answers what the test scripts (and
 * keeps the facts it was asked with); fakeFetch stands in for fetch under the real GroqClient, keeps
 * every request, and can answer a status, a body, or never (until the request is aborted).
 */
import type { ScoutFacts } from "../src/scout/eligible.js";
import type { GroqAnswer, GroqPort } from "../src/scout/groq.js";

export class FakeGroq implements GroqPort {
  readonly model = "openai/gpt-oss-120b";
  readonly timeoutMs = 6000;
  asked: ScoutFacts[] = [];
  /** What the next choose() answers; a function sees the facts. */
  answer: GroqAnswer | ((f: ScoutFacts) => GroqAnswer) = { ok: false, why: "unreachable", ms: 1 };

  async choose(facts: ScoutFacts): Promise<GroqAnswer> {
    this.asked.push(facts);
    return typeof this.answer === "function" ? this.answer(facts) : this.answer;
  }
}

export interface SentRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
  signal: AbortSignal;
}

/** A fetch that answers `reply` (or never, until aborted). */
export function fakeFetch(reply: { status: number; body: unknown } | "never" | "network") {
  const sent: SentRequest[] = [];
  const fn = async (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }): Promise<Response> => {
    sent.push({ url, ...init });
    if (reply === "network") throw new TypeError("fetch failed");
    if (reply === "never") {
      return new Promise<Response>((_, fail) => {
        init.signal.addEventListener("abort", () => fail(init.signal.reason));
      });
    }
    return new Response(typeof reply.body === "string" ? reply.body : JSON.stringify(reply.body), { status: reply.status, headers: { "content-type": "application/json" } });
  };
  return { fn, sent };
}

/** A chat completion whose message content is `content`. */
export function completion(content: unknown) {
  return { id: "chatcmpl-1", object: "chat.completion", model: "openai/gpt-oss-120b", choices: [{ index: 0, message: { role: "assistant", content: typeof content === "string" ? content : JSON.stringify(content) }, finish_reason: "stop" }] };
}

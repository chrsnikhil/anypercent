/**
 * PB's scout asks a language model on Groq which listed ghost would help most (spec: scout and
 * pivot, "The Groq call"). The model chooses one candidate id and a lap, and writes one short
 * sentence; it never decides whether to pay, how much or to whom.
 *
 *   POST {GROQ_BASE}/chat/completions, Authorization: Bearer {GROQ_API_KEY}
 *   model GROQ_MODEL (pinned: openai/gpt-oss-120b), strict structured output (json_schema), the
 *   candidate ids and the laps as enums, reasoning_effort low, no reasoning returned, 400 tokens.
 *
 * One try, aborted after GROQ_TIMEOUT_MS (6 s). 429: rate_limit; 401 or 403: refused (the scout runs
 * the rule until restart); any other non-2xx or a network error: unreachable; content that is not
 * JSON or fails the enums: bad_answer. The key goes only into the Authorization header: never into
 * a log line, an error text or the body. Plain fetch, no SDK.
 */
import type { ScoutFacts } from "./eligible.js";

/** The system prompt, verbatim. */
export const SYSTEM =
  "You are PB's scout in a kart racing game. You get one player's lap times and the lap times of ghost runs that are for sale. " +
  "Choose the ONE ghost that would help this player most: usually the one that is fastest in the lap where the player loses the most time. " +
  "Answer only with JSON: pick is a candidate id from the list, lap is the lap your reason is about, reason is one short sentence of at most " +
  "110 characters, written to the player as 'you', that uses only numbers that appear in the facts. " +
  "Never mention money, prices, people, winning or anything that is not in the facts.";

export type GroqWhy = "timeout" | "rate_limit" | "refused" | "bad_answer" | "unreachable";

export type GroqAnswer = { ok: true; pick: string; lap: number; reason: string; ms: number } | { ok: false; why: GroqWhy; ms: number };

export interface GroqPort {
  /** The model id, as INTENT records it. */
  readonly model: string;
  readonly timeoutMs: number;
  choose(facts: ScoutFacts): Promise<GroqAnswer>;
}

/** The exact request body for these facts. */
export function groqBody(model: string, facts: ScoutFacts): Record<string, unknown> {
  return {
    model,
    messages: [
      { role: "system", content: SYSTEM },
      { role: "user", content: JSON.stringify(facts) },
    ],
    response_format: {
      type: "json_schema",
      json_schema: {
        name: "scout_pick",
        strict: true,
        schema: {
          type: "object",
          additionalProperties: false,
          required: ["pick", "lap", "reason"],
          properties: {
            pick: { type: "string", enum: facts.candidates.map((c) => c.id) },
            lap: { type: "integer", enum: Array.from({ length: facts.laps }, (_, k) => k + 1) },
            reason: { type: "string" },
          },
        },
      },
    },
    reasoning_effort: "low",
    include_reasoning: false,
    max_completion_tokens: 400,
  };
}

export type Fetch = (url: string, init: { method: string; headers: Record<string, string>; body: string; signal: AbortSignal }) => Promise<Response>;

export interface GroqClientOptions {
  apiKey: string;
  model: string;
  base: string;
  timeoutMs: number;
  fetch?: Fetch;
  now?: () => number;
}

/** Parse the model's answer against the request's own enums. */
export function readAnswer(content: unknown, facts: ScoutFacts): { pick: string; lap: number; reason: string } | null {
  if (typeof content !== "string") return null;
  let j: unknown;
  try {
    j = JSON.parse(content);
  } catch {
    return null;
  }
  const a = j as { pick?: unknown; lap?: unknown; reason?: unknown };
  if (!a || typeof a !== "object") return null;
  if (typeof a.pick !== "string" || !facts.candidates.some((c) => c.id === a.pick)) return null;
  if (typeof a.lap !== "number" || !Number.isInteger(a.lap) || a.lap < 1 || a.lap > facts.laps) return null;
  if (typeof a.reason !== "string") return null;
  return { pick: a.pick, lap: a.lap, reason: a.reason };
}

export class GroqClient implements GroqPort {
  readonly model: string;
  readonly timeoutMs: number;
  private readonly fetch: Fetch;
  private readonly now: () => number;

  constructor(private readonly opts: GroqClientOptions) {
    this.model = opts.model;
    this.timeoutMs = opts.timeoutMs;
    this.fetch = opts.fetch ?? ((url, init) => fetch(url, init));
    this.now = opts.now ?? Date.now;
  }

  async choose(facts: ScoutFacts): Promise<GroqAnswer> {
    const t0 = this.now();
    const ms = () => this.now() - t0;
    let res: Response;
    try {
      res = await this.fetch(`${this.opts.base}/chat/completions`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${this.opts.apiKey}` },
        body: JSON.stringify(groqBody(this.model, facts)),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      const name = (err as { name?: string })?.name;
      return { ok: false, why: name === "TimeoutError" || name === "AbortError" ? "timeout" : "unreachable", ms: ms() };
    }
    let body: unknown;
    try {
      body = await res.json();
    } catch (err) {
      const name = (err as { name?: string })?.name;
      if (name === "TimeoutError" || name === "AbortError") return { ok: false, why: "timeout", ms: ms() };
      body = null;
    }
    if (res.status === 429) return { ok: false, why: "rate_limit", ms: ms() };
    if (res.status === 401 || res.status === 403) return { ok: false, why: "refused", ms: ms() };
    if (res.status === 400 && (body as { error?: { code?: unknown } } | null)?.error?.code === "json_validate_failed") {
      // The model's output did not fit the schema: its answer, not Groq, is at fault.
      return { ok: false, why: "bad_answer", ms: ms() };
    }
    if (res.status < 200 || res.status > 299) return { ok: false, why: "unreachable", ms: ms() };
    const content = (body as { choices?: Array<{ message?: { content?: unknown } }> } | null)?.choices?.[0]?.message?.content;
    const a = readAnswer(content, facts);
    if (!a) return { ok: false, why: "bad_answer", ms: ms() };
    return { ok: true, ...a, ms: ms() };
  }
}

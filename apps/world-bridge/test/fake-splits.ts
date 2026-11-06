/**
 * A scripted arcade_splits (the SplitsPort): per log hash it answers the laps the test gives, by
 * default laps that add up to the fake checker's time with the same final hash. Nothing runs.
 */
import { CheckerError, type SplitsPort, type SplitsResult } from "../src/arkiv/checker.js";

export class FakeSplits implements SplitsPort {
  readonly games: readonly string[];
  calls = 0;
  /** Default laps (they must add up to the replayed time for the splits to be written). */
  laps: number[];
  finalHash = 576543229;
  /** Per log hash: laps, or a whole answer, or an error. */
  byLog = new Map<string, number[] | Partial<SplitsResult> | "error">();
  /** Every call fails (the tool is missing). */
  missing = false;

  constructor(laps: number[] = [2087, 1995, 2088], games: string[] = ["MDGP"]) {
    this.laps = laps;
    this.games = games;
  }

  async splits(game: string, logH: string): Promise<SplitsResult> {
    this.calls += 1;
    if (this.missing) throw new CheckerError("exit 127");
    const per = this.byLog.get(logH);
    if (per === "error") throw new CheckerError("exit 2");
    const laps = Array.isArray(per) ? per : this.laps;
    const base: SplitsResult = { game, kind: "lap", splits: [...laps], time_frames: laps.reduce((a, b) => a + b, 0), finished: true, final_hash: this.finalHash };
    return per && !Array.isArray(per) ? { ...base, ...per } : base;
  }
}

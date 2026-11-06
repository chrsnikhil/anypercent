/* arcade_splits LOG: replay a run log through MARINE DRIVE GP's rules, as arcade_replay does, and print the player's
   lap times as one JSON line:
     {"game":"MDGP","kind":"lap","splits":[2087,1995,1994],"time_frames":6076,"finished":true,"final_hash":576543229}
   ac_replay() leaves the game at the log's last step, so the rules' lap times (rules_lap_frames) are read right after
   it. splits holds the laps completed (non-zero), in order; time_frames and finished are game_result()'s, final_hash
   the replay's, so a caller can check the splits came from the same run arcade_replay checked. The same header checks
   as arcade_replay: a bad header, another game's log or a claim that is too long prints to stderr and exits 2. */
#include <stdio.h>
#include "ac_game.h"
#include "ac_log.h"
#include "ac_replay.h"
#include "game.h"
#include "tuning.h"

static uint8_t buf[1 << 20];

int main(int argc, char **argv) {
    FILE *f;
    uint32_t len, t;
    int lap, n = 0;
    ac_replay_out o;
    if (argc < 2) { fprintf(stderr, "usage: arcade_splits LOG\n"); return 2; }
    f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", argv[1]); return 2; }
    len = (uint32_t)fread(buf, 1, sizeof buf, f);
    fclose(f);
    if (!ac_replay(buf, len, &o)) { fprintf(stderr, "bad log header, another game's log, or too long\n"); return 2; }
    printf("{\"game\":\"%.4s\",\"kind\":\"lap\",\"splits\":[", (const char *)buf + 4);
    for (lap = 1; lap <= LAPS; lap++) {
        t = rules_lap_frames(lap);
        if (t) printf("%s%u", n++ ? "," : "", t);
    }
    printf("],\"time_frames\":%u,\"finished\":%s,\"final_hash\":%u}\n", o.result.time_frames,
           o.result.finished ? "true" : "false", o.final_hash);
    return 0;
}

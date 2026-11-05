/* arcade_replay LOG [--ghost OUT]: replay a run log through the linked game; print a JSON result. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ac_game.h"
#include "ac_log.h"
#include "ac_replay.h"
#include "ac_save.h"

static uint8_t buf[1 << 20];
static ac_ghost_pt pts[2728];

int main(int argc, char **argv) {
    FILE *f;
    uint32_t len;
    ac_replay_out o;
    if (argc < 2) { fprintf(stderr, "usage: arcade_replay LOG [--ghost OUT]\n"); return 2; }
    f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", argv[1]); return 2; }
    len = (uint32_t)fread(buf, 1, sizeof buf, f);
    fclose(f);
    if (!ac_replay(buf, len, &o)) { fprintf(stderr, "bad log header, another game's log, or too long\n"); return 2; }
    printf("{\"game\":\"%.4s\",\"frames\":%u,\"final_hash\":%u,\"claimed_hash\":%u,\"hash_matches\":%s,"
           "\"complete\":%s,\"claims_match\":%s,\"finished\":%s,\"score\":%u,\"time_frames\":%u,\"trophies\":%u}\n",
           (const char *)buf + 4, o.frames, o.final_hash, ac_log_u32(buf + 20), o.hash_matches ? "true" : "false",
           o.complete ? "true" : "false", o.claims_match ? "true" : "false", o.result.finished ? "true" : "false",
           o.result.score, o.result.time_frames, o.result.trophies);
    if (argc >= 4 && !strcmp(argv[2], "--ghost")) {
        uint16_t period;
        uint32_t n = ac_ghost_extract(buf, len, GAME_INFO.ghost_period, pts, 2728, &period), i;
        uint8_t hdr[16];
        FILE *g = fopen(argv[3], "wb");
        if (!g) return 2;
        memcpy(hdr, "ACG1", 4); memcpy(hdr + 4, buf + 4, 4); memcpy(hdr + 8, buf + 20, 4);
        hdr[12] = (uint8_t)period; hdr[13] = (uint8_t)(period >> 8); hdr[14] = (uint8_t)n; hdr[15] = (uint8_t)(n >> 8);
        fwrite(hdr, 1, 16, g);
        for (i = 0; i < n; i++) {
            uint8_t p[6] = {(uint8_t)pts[i].x, (uint8_t)((uint16_t)pts[i].x >> 8), (uint8_t)pts[i].y,
                            (uint8_t)((uint16_t)pts[i].y >> 8), pts[i].angle, pts[i].flags};
            fwrite(p, 1, 6, g);
        }
        fclose(g);
    }
    return 0;
}

/* Headless GBA runner on libmgba, for the SHIP IT! tests.
   gba_run ROM SCRIPT [--watch ADDR[,ADDR...]] [--shot FRAME OUT.rgba]... [--save-in SAV] [--save-out SAV]
   SCRIPT lines: "<keys hex> <frames>" (GBA key bits: A0 B1 Select2 Start3 Right4 Left5 Up6 Down7 R8 L9).
   Prints one line per frame: the frame number, then each watched 32-bit value in hex, or an FNV-1a hash
   of IWRAM and EWRAM when nothing is watched. --shot writes that frame as raw 240 x 160 RGBA. --save-in loads
   cartridge save memory before the run; --save-out writes it after the last frame (nothing if the game never
   saved). */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <mgba/core/core.h>
#include <mgba/core/log.h>

#define MAX_WATCH 8
#define MAX_SHOTS 16

static void quiet(struct mLogger *l, int c, enum mLogLevel lv, const char *f, va_list a) {
    (void)l; (void)c; (void)lv; (void)f; (void)a;
}

static void save(const char *path, const color_t *buf, unsigned n) {
    FILE *out = fopen(path, "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", path); exit(1); }
    for (unsigned i = 0; i < n; i++) {
        color_t c = buf[i];
        uint8_t px[4] = { (uint8_t)(c & 0xFF), (uint8_t)((c >> 8) & 0xFF), (uint8_t)((c >> 16) & 0xFF), 255 };
        fwrite(px, 1, 4, out);
    }
    fclose(out);
}

int main(int argc, char **argv) {
    static struct mLogger logger = { .log = quiet };
    uint32_t watch[MAX_WATCH];
    unsigned nwatch = 0, nshots = 0, shot_frame[MAX_SHOTS];
    const char *shot_path[MAX_SHOTS];
    const char *save_in = NULL, *save_out = NULL;
    if (argc < 3) { fprintf(stderr, "usage: gba_run ROM SCRIPT [--watch A,B] [--shot FRAME OUT]\n"); return 2; }
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "--watch") && i + 1 < argc) {
            char *p = argv[++i];
            while (*p && nwatch < MAX_WATCH) {
                watch[nwatch++] = (uint32_t)strtoul(p, &p, 16);
                if (*p == ',') p++;
            }
        } else if (!strcmp(argv[i], "--shot") && i + 2 < argc && nshots < MAX_SHOTS) {
            shot_frame[nshots] = (unsigned)atoi(argv[++i]);
            shot_path[nshots++] = argv[++i];
        } else if (!strcmp(argv[i], "--save-in") && i + 1 < argc) {
            save_in = argv[++i];
        } else if (!strcmp(argv[i], "--save-out") && i + 1 < argc) {
            save_out = argv[++i];
        } else {
            fprintf(stderr, "bad argument %s\n", argv[i]);
            return 2;
        }
    }
    mLogSetDefaultLogger(&logger);
    struct mCore *core = mCoreFind(argv[1]);
    if (!core || !core->init(core)) { fprintf(stderr, "cannot open %s\n", argv[1]); return 1; }
    mCoreInitConfig(core, NULL);
    unsigned w, h;
    core->desiredVideoDimensions(core, &w, &h);
    color_t *buf = calloc(w * h, sizeof(color_t));
    core->setVideoBuffer(core, buf, w);
    if (!mCoreLoadFile(core, argv[1])) { fprintf(stderr, "cannot load %s\n", argv[1]); return 1; }
    if (save_in) {
        FILE *f = fopen(save_in, "rb");
        if (!f) { fprintf(stderr, "cannot read %s\n", save_in); return 1; }
        static uint8_t data[0x20000];
        size_t n = fread(data, 1, sizeof(data), f);
        fclose(f);
        core->savedataRestore(core, data, n, false);
    }
    core->reset(core);
    FILE *sc = fopen(argv[2], "r");
    if (!sc) { fprintf(stderr, "cannot read %s\n", argv[2]); return 1; }
    unsigned keys, frames, frame = 0;
    while (fscanf(sc, "%x %u", &keys, &frames) == 2) {
        for (unsigned i = 0; i < frames; i++) {
            core->setKeys(core, keys);
            core->runFrame(core);
            printf("%u", ++frame);
            if (nwatch) {
                for (unsigned k = 0; k < nwatch; k++) printf(" %08x", core->busRead32(core, watch[k]));
            } else {
                uint32_t hsh = 2166136261u;
                for (uint32_t a = 0x03000000; a < 0x03008000; a += 4) hsh = (hsh ^ core->busRead32(core, a)) * 16777619u;
                for (uint32_t a = 0x02000000; a < 0x02040000; a += 64) hsh = (hsh ^ core->busRead32(core, a)) * 16777619u;
                printf(" %08x", hsh);
            }
            printf("\n");
            for (unsigned k = 0; k < nshots; k++)
                if (shot_frame[k] == frame) save(shot_path[k], buf, w * h);
        }
    }
    fclose(sc);
    if (save_out) {
        void *data = NULL;
        size_t n = core->savedataClone(core, &data);
        if (n) {
            FILE *f = fopen(save_out, "wb");
            if (!f) { fprintf(stderr, "cannot write %s\n", save_out); return 1; }
            fwrite(data, 1, n, f);
            fclose(f);
        }
        free(data);
    }
    core->deinit(core);
    return 0;
}

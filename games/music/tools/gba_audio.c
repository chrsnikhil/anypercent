/* Record what a GBA ROM plays: runs it headless on libmgba for FRAMES frames (no keys pressed) and writes the
   sound as a 16-bit stereo WAV at 32768 Hz. The music previews of the real ROMs, and the check that a game's theme
   really plays (games/music/tests/test_roms.py). Built like game/tools/gba_run (the static libmgba):

     gcc -O2 -o gba_audio gba_audio.c -I$MGBA/include -I$MGBA/build/include $MGBA/build/libmgba.a -lm -lpthread
     gba_audio ROM FRAMES OUT.wav */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <mgba/core/blip_buf.h>
#include <mgba/core/core.h>
#include <mgba/core/log.h>

#define RATE 32768

static void quiet(struct mLogger *l, int c, enum mLogLevel lv, const char *f, va_list a) {
    (void)l; (void)c; (void)lv; (void)f; (void)a;
}

static void put32(FILE *f, uint32_t v) { fwrite(&v, 4, 1, f); }
static void put16(FILE *f, uint16_t v) { fwrite(&v, 2, 1, f); }

int main(int argc, char **argv) {
    static struct mLogger logger = { .log = quiet };
    if (argc != 4) { fprintf(stderr, "usage: gba_audio ROM FRAMES OUT.wav\n"); return 2; }
    unsigned frames = (unsigned)atoi(argv[2]);
    mLogSetDefaultLogger(&logger);
    struct mCore *core = mCoreFind(argv[1]);
    if (!core || !core->init(core)) { fprintf(stderr, "cannot open %s\n", argv[1]); return 1; }
    mCoreInitConfig(core, NULL);
    unsigned w, h;
    core->desiredVideoDimensions(core, &w, &h);
    color_t *video = calloc(w * h, sizeof(color_t));
    core->setVideoBuffer(core, video, w);
    if (!mCoreLoadFile(core, argv[1])) { fprintf(stderr, "cannot load %s\n", argv[1]); return 1; }
    core->setAudioBufferSize(core, 4096);
    struct blip_t *left = core->getAudioChannel(core, 0), *right = core->getAudioChannel(core, 1);
    blip_set_rates(left, core->frequency(core), RATE);
    blip_set_rates(right, core->frequency(core), RATE);
    core->reset(core);

    FILE *out = fopen(argv[3], "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", argv[3]); return 1; }
    fwrite("RIFF\0\0\0\0WAVEfmt ", 1, 16, out);
    put32(out, 16); put16(out, 1); put16(out, 2); put32(out, RATE); put32(out, RATE * 4); put16(out, 4); put16(out, 16);
    fwrite("data\0\0\0\0", 1, 8, out);
    uint32_t bytes = 0;
    static short l[8192], r[8192], lr[16384];
    for (unsigned f = 0; f < frames; f++) {
        core->setKeys(core, 0);
        core->runFrame(core);
        int n = blip_samples_avail(left);
        while (n > 0) {
            int k = n > 8192 ? 8192 : n;
            blip_read_samples(left, l, k, 0);
            blip_read_samples(right, r, k, 0);
            for (int i = 0; i < k; i++) { lr[2 * i] = l[i]; lr[2 * i + 1] = r[i]; }
            fwrite(lr, 4, (size_t)k, out);
            bytes += (uint32_t)k * 4;
            n -= k;
        }
    }
    fseek(out, 4, SEEK_SET); put32(out, 36 + bytes);
    fseek(out, 40, SEEK_SET); put32(out, bytes);
    fclose(out);
    core->deinit(core);
    printf("%s: %u frames, %.1f s\n", argv[3], frames, bytes / 4.0 / RATE);
    return 0;
}

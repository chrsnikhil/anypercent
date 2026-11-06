/* gba_film: gba_run's sibling for the demo film (games/clips/render_race.py). Plays a run log's buttons into the ROM
   headless, game step by game step, and writes every frame and the sound.
   gba_film ROM STEPS --steps-addr ADDR --hash-addr ADDR [--seed-addr ADDR] [--save-in SAV] [--tail FRAMES]
            [--max-frames N] --video OUT.rgb [--audio OUT.pcm --rate HZ]
   STEPS: one u16 LE per game step, the log's buttons (GBA key bits). Before each emulator frame the runner reads the
   ROM's step counter (g_dbg_steps at ADDR, games/common/src/arcade_runtime.cpp) and holds the buttons of the step that
   frame runs, so a frame with no step (boot, a lag frame) never shifts the run. After the last step it runs TAIL more
   frames with nothing pressed. --video: every frame as raw 240 x 160 RGB24. --audio: the sound as 16-bit stereo PCM,
   resampled to HZ (the caller picks HZ so that each frame is a whole number of samples at the rate it plays at).
   Prints one JSON line at the end: frames run, the step count, g_dbg_hash right after the last step (the log's
   final hash when the replay is faithful) and g_dbg_seed. Exit 1 when the steps never all ran within --max-frames. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <mgba/core/blip_buf.h>
#include <mgba/core/core.h>
#include <mgba/core/log.h>

static void quiet(struct mLogger *l, int c, enum mLogLevel lv, const char *f, va_list a) {
    (void)l; (void)c; (void)lv; (void)f; (void)a;
}

static uint8_t *slurp(const char *path, size_t *n) {
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", path); exit(1); }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = malloc(size > 0 ? (size_t)size : 1);
    *n = fread(buf, 1, (size_t)size, f);
    fclose(f);
    return buf;
}

int main(int argc, char **argv) {
    static struct mLogger logger = { .log = quiet };
    uint32_t steps_addr = 0, hash_addr = 0, seed_addr = 0;
    unsigned tail = 240, max_frames = 216000;
    double rate = 0;
    const char *save_in = NULL, *video_path = NULL, *audio_path = NULL;
    if (argc < 3) {
        fprintf(stderr, "usage: gba_film ROM STEPS --steps-addr A --hash-addr A --video OUT [--audio OUT --rate HZ]\n");
        return 2;
    }
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "--steps-addr") && i + 1 < argc) steps_addr = (uint32_t)strtoul(argv[++i], NULL, 16);
        else if (!strcmp(argv[i], "--hash-addr") && i + 1 < argc) hash_addr = (uint32_t)strtoul(argv[++i], NULL, 16);
        else if (!strcmp(argv[i], "--seed-addr") && i + 1 < argc) seed_addr = (uint32_t)strtoul(argv[++i], NULL, 16);
        else if (!strcmp(argv[i], "--save-in") && i + 1 < argc) save_in = argv[++i];
        else if (!strcmp(argv[i], "--tail") && i + 1 < argc) tail = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-frames") && i + 1 < argc) max_frames = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--video") && i + 1 < argc) video_path = argv[++i];
        else if (!strcmp(argv[i], "--audio") && i + 1 < argc) audio_path = argv[++i];
        else if (!strcmp(argv[i], "--rate") && i + 1 < argc) rate = atof(argv[++i]);
        else { fprintf(stderr, "bad argument %s\n", argv[i]); return 2; }
    }
    if (!steps_addr || !hash_addr || !video_path || (audio_path && rate <= 0)) {
        fprintf(stderr, "--steps-addr, --hash-addr and --video are needed (and --rate with --audio)\n");
        return 2;
    }
    size_t nbytes;
    uint8_t *raw = slurp(argv[2], &nbytes);
    size_t nsteps = nbytes / 2;

    mLogSetDefaultLogger(&logger);
    struct mCore *core = mCoreFind(argv[1]);
    if (!core || !core->init(core)) { fprintf(stderr, "cannot open %s\n", argv[1]); return 1; }
    mCoreInitConfig(core, NULL);
    unsigned w, h;
    core->desiredVideoDimensions(core, &w, &h);
    color_t *buf = calloc(w * h, sizeof(color_t));
    uint8_t *rgb = malloc(w * h * 3);
    core->setVideoBuffer(core, buf, w);
    if (!mCoreLoadFile(core, argv[1])) { fprintf(stderr, "cannot load %s\n", argv[1]); return 1; }
    if (save_in) {
        size_t n;
        uint8_t *data = slurp(save_in, &n);
        core->savedataRestore(core, data, n, false);
        free(data);
    }
    core->reset(core);
    FILE *video = fopen(video_path, "wb");
    if (!video) { fprintf(stderr, "cannot write %s\n", video_path); return 1; }
    FILE *audio = NULL;
    struct blip_t *left = NULL, *right = NULL;
    int16_t samples[2 * 4096];
    if (audio_path) {
        audio = fopen(audio_path, "wb");
        if (!audio) { fprintf(stderr, "cannot write %s\n", audio_path); return 1; }
        core->setAudioBufferSize(core, 4096);
        left = core->getAudioChannel(core, 0);
        right = core->getAudioChannel(core, 1);
        blip_set_rates(left, core->frequency(core), rate);
        blip_set_rates(right, core->frequency(core), rate);
    }
    unsigned frame = 0, end_frame = 0;
    int ended = 0;
    uint32_t steps_at_end = 0, hash_at_end = 0;
    unsigned long long audio_samples = 0;
    for (;;) {
        uint32_t s = core->busRead32(core, steps_addr);
        if (!ended && s >= nsteps) {
            ended = 1;
            end_frame = frame;
            steps_at_end = s;
            hash_at_end = core->busRead32(core, hash_addr);
        }
        if (ended && frame >= end_frame + tail) break;
        if (frame >= max_frames) break;
        uint16_t keys = s < nsteps ? (uint16_t)(raw[2 * s] | (raw[2 * s + 1] << 8)) : 0;
        core->setKeys(core, keys & 0x3FF);
        core->runFrame(core);
        ++frame;
        for (unsigned i = 0; i < w * h; i++) {
            color_t c = buf[i];
            rgb[3 * i] = (uint8_t)(c & 0xFF);
            rgb[3 * i + 1] = (uint8_t)((c >> 8) & 0xFF);
            rgb[3 * i + 2] = (uint8_t)((c >> 16) & 0xFF);
        }
        fwrite(rgb, 1, w * h * 3, video);
        if (audio) {
            int avail;
            while ((avail = blip_samples_avail(left)) > 0) {
                if (avail > 4096) avail = 4096;
                blip_read_samples(left, samples, avail, 1);
                blip_read_samples(right, samples + 1, avail, 1);
                fwrite(samples, sizeof(int16_t) * 2, (size_t)avail, audio);
                audio_samples += (unsigned)avail;
            }
        }
    }
    fclose(video);
    if (audio) fclose(audio);
    printf("{\"frames\": %u, \"steps\": %zu, \"ended\": %s, \"end_frame\": %u, \"steps_at_end\": %u, "
           "\"hash_at_end\": %u, \"seed\": %u, \"audio_samples\": %llu, \"width\": %u, \"height\": %u}\n",
           frame, nsteps, ended ? "true" : "false", end_frame, steps_at_end, hash_at_end,
           seed_addr ? core->busRead32(core, seed_addr) : 0, audio_samples, w, h);
    core->deinit(core);
    return ended ? 0 : 1;
}

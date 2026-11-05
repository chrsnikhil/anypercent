#include "ac_save.h"

static const uint16_t OFF[5] = {0, AC_OFF_PROFILE, AC_OFF_BEST, AC_OFF_RUN, AC_OFF_GHOST};
static const uint16_t CAP[5] = {0, 64, 32, 14336, 16384};

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }

uint16_t ac_save_sum(const uint8_t *p, uint32_t n) {
    uint16_t s = 0x5A5A;
    uint32_t i;
    for (i = 0; i < n; i++) s = (uint16_t)(s + p[i]);
    return s;
}

static int header_ok(const uint8_t *save) {
    const uint8_t *h = save + AC_SAVE_BASE;
    return h[0] == 'A' && h[1] == 'C' && h[2] == 'S' && h[3] == 'V' && rd16(h + 4) == AC_SAVE_VERSION;
}

void ac_save_format(uint8_t *save, const char game[4]) {
    uint8_t *h = save + AC_SAVE_BASE;
    int s, i;
    h[0] = 'A'; h[1] = 'C'; h[2] = 'S'; h[3] = 'V';
    wr16(h + 4, AC_SAVE_VERSION);
    for (i = 0; i < 4; i++) h[6 + i] = (uint8_t)game[i];
    for (s = 1; s <= 4; s++) {
        uint8_t *e = h + 10 + (s - 1) * 12;
        wr16(e, OFF[s]); wr16(e + 2, CAP[s]); wr16(e + 4, 0); wr16(e + 6, 0);
        for (i = 8; i < 12; i++) e[i] = 0;
    }
}

int ac_save_commit(uint8_t *save, int sec, uint32_t len, uint16_t sum, uint8_t flags) {
    uint8_t *e;
    if (sec < 1 || sec > 4 || !header_ok(save) || len > CAP[sec]) return 0;
    e = save + AC_SAVE_BASE + 10 + (sec - 1) * 12;
    wr16(e + 4, (uint16_t)len);
    wr16(e + 6, sum);
    e[8] = flags;
    return 1;
}

int ac_save_put(uint8_t *save, int sec, const uint8_t *data, uint32_t len, uint8_t flags) {
    uint32_t i;
    if (sec < 1 || sec > 4 || !header_ok(save) || len > CAP[sec]) return 0;
    for (i = 0; i < len; i++) save[OFF[sec] + i] = data[i];
    return ac_save_commit(save, sec, len, ac_save_sum(data, len), flags);
}

const uint8_t *ac_save_get(const uint8_t *save, const char game[4], int sec, uint32_t *len, uint8_t *flags) {
    const uint8_t *h = save + AC_SAVE_BASE, *e;
    uint16_t n;
    int i;
    if (sec < 1 || sec > 4 || !header_ok(save)) return 0;
    for (i = 0; i < 4; i++) if (h[6 + i] != (uint8_t)game[i]) return 0;
    e = h + 10 + (sec - 1) * 12;
    n = rd16(e + 4);
    if (rd16(e) != OFF[sec] || n == 0 || n > CAP[sec] || rd16(e + 6) != ac_save_sum(save + OFF[sec], n)) return 0;
    *len = n;
    *flags = e[8];
    return save + OFF[sec];
}

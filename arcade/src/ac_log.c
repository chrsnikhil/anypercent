#include "ac_log.h"
#include "ac_buttons.h"

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
uint32_t ac_log_u32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

/* A run longer than this is split, so a toggle token's count << 5 always fits in 32 bits. */
#define RUN_MAX 0x07FFFFFFu

void ac_rec_begin(ac_rec *r, uint8_t *buf, uint32_t cap, const char game[4], uint32_t rules_version, uint32_t seed) {
    uint32_t i;
    r->buf = buf; r->cap = cap; r->len = AC_LOG_HEADER; r->frames = 0; r->last = 0; r->count = 0; r->full = 0;
    r->prev = 0;
    for (i = 0; i < AC_LOG_HEADER; i++) buf[i] = 0;
    buf[0] = 'A'; buf[1] = 'C'; buf[2] = 'L'; buf[3] = '1';
    for (i = 0; i < 4; i++) buf[4 + i] = (uint8_t)game[i];
    put32(buf + 8, rules_version);
    put32(buf + 12, seed);
}

/* Writes the open run as one token; a run that does not fit is dropped and the log marked full. Only written
   runs count toward frames, so a truncated log's header matches what it holds. */
static void flush(ac_rec *r) {
    uint8_t tmp[7];
    uint32_t n = 0, v, i;
    uint16_t d = (uint16_t)(r->last ^ r->prev);
    int set = 1;
    if (r->count == 0 || r->full) return;
    if (d && !(d & (d - 1))) {
        uint32_t bit = 0;
        while (!(d & 1)) { d >>= 1; bit++; }
        v = r->count << 5 | bit << 1;
        set = 0;
    } else {
        v = r->count << 1 | 1u;
    }
    while (v >= 0x80) { tmp[n++] = (uint8_t)(v | 0x80); v >>= 7; }
    tmp[n++] = (uint8_t)v;
    if (set) { tmp[n++] = (uint8_t)r->last; tmp[n++] = (uint8_t)(r->last >> 8); }
    if (r->len + n > r->cap) { r->full = 1; return; }
    for (i = 0; i < n; i++) r->buf[r->len + i] = tmp[i];
    r->len += n;
    r->frames += r->count;
    r->prev = r->last;
}

void ac_rec_push(ac_rec *r, uint16_t buttons) {
    buttons &= BTN_MASK;
    if (r->full) return;
    if (r->count && buttons == r->last && r->count < RUN_MAX) { r->count++; }
    else { flush(r); r->last = buttons; r->count = 1; }
}

uint32_t ac_rec_finish(ac_rec *r, uint32_t final_hash, uint32_t score, uint32_t trophies) {
    flush(r);
    r->count = 0;
    put32(r->buf + 16, r->frames);
    put32(r->buf + 20, final_hash);
    put32(r->buf + 24, score);
    put32(r->buf + 28, trophies);
    return r->len;
}

int ac_log_open(ac_log_reader *rd, const uint8_t *buf, uint32_t len) {
    if (len < AC_LOG_HEADER || buf[0] != 'A' || buf[1] != 'C' || buf[2] != 'L' || buf[3] != '1') return 0;
    rd->buf = buf; rd->len = len; rd->pos = AC_LOG_HEADER; rd->left = 0; rd->buttons = 0;
    return 1;
}

int ac_log_next(ac_log_reader *rd, uint16_t *buttons) {
    if (rd->left == 0) {
        uint32_t v = 0, shift = 0, c;
        for (;;) {
            uint8_t b;
            if (rd->pos >= rd->len || shift > 28) return 0;
            b = rd->buf[rd->pos++];
            v |= (uint32_t)(b & 0x7F) << shift;
            if (!(b & 0x80)) {
                if (b == 0 && shift) return 0;    /* a non-minimal varint: one value, one encoding */
                break;
            }
            shift += 7;
        }
        if (v & 1) {
            uint16_t raw;
            c = v >> 1;
            if (rd->pos + 2 > rd->len) return 0;
            raw = (uint16_t)(rd->buf[rd->pos] | rd->buf[rd->pos + 1] << 8);
            if (raw & ~BTN_MASK) return 0;        /* buttons use bits 0-9 only */
            rd->buttons = raw;
            rd->pos += 2;
        } else {
            uint32_t bit = (v >> 1) & 15;
            c = v >> 5;
            if (bit > 9) return 0;
            rd->buttons = (uint16_t)(rd->buttons ^ (1u << bit));
        }
        if (c == 0) return 0;
        rd->left = c;
    }
    rd->left--;
    *buttons = rd->buttons;
    return 1;
}

/* The run log: a 32-byte header, then one varint token V (LE base-128) per run of identical buttons:
     V even: toggle token. bit = (V >> 1) & 15 (0..9), count = V >> 5 (>= 1); the run's buttons are the
             previous run's buttons XOR (1 << bit).
     V odd:  set token. count = V >> 1 (>= 1), followed by the run's buttons as u16 LE (bits 10-15 zero).
   The previous buttons start at 0. The recorder emits a toggle token when exactly one bit differs. Each value has
   one encoding: the reader ends the log at a non-minimal varint, a toggle of bit 10-15, a count of 0 or a set token
   with any of bits 10-15. */
#ifndef AC_LOG_H
#define AC_LOG_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define AC_LOG_HEADER 32
typedef struct {
    uint8_t *buf;
    uint32_t cap, len, frames;
    uint16_t last;
    uint32_t count;       /* frames in the open run */
    uint8_t full;         /* 1 once a run did not fit: the log is truncated (and frames counts only what is in it) */
    uint16_t prev;        /* buttons of the last run written, for toggle tokens */
} ac_rec;
void ac_rec_begin(ac_rec *r, uint8_t *buf, uint32_t cap, const char game[4], uint32_t rules_version, uint32_t seed);
void ac_rec_push(ac_rec *r, uint16_t buttons);
/* Closes the open run, fills frames/final_hash/score/trophies, returns the log length in bytes. */
uint32_t ac_rec_finish(ac_rec *r, uint32_t final_hash, uint32_t score, uint32_t trophies);

typedef struct {
    const uint8_t *buf;
    uint32_t len, pos, left;
    uint16_t buttons;
} ac_log_reader;
int ac_log_open(ac_log_reader *rd, const uint8_t *buf, uint32_t len);   /* 1 if the header is valid */
int ac_log_next(ac_log_reader *rd, uint16_t *buttons);                  /* 1 and a frame's buttons, 0 at end */
uint32_t ac_log_u32(const uint8_t *p);                                    /* little-endian read */
#ifdef __cplusplus
}
#endif
#endif

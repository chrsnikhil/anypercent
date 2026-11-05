/* Cartridge save layout: a section table at AC_SAVE_BASE, then fixed-offset
   payload areas for profile, best, run-log and ghost data. Bytes 0..0xFF are
   legacy area and are never touched by this module. */
#ifndef AC_SAVE_H
#define AC_SAVE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define AC_SAVE_SIZE     32768
#define AC_SAVE_BASE     0x0100
enum { AC_SEC_PROFILE = 1, AC_SEC_BEST = 2, AC_SEC_RUN = 3, AC_SEC_GHOST = 4 };
#define AC_SAVE_VERSION  2      /* 2: RUN 0x0400 cap 14336, GHOST 0x3C00; any other version reads as unformatted */
/* Section table at AC_SAVE_BASE: "ACSV", u16 version, 4 game-id bytes, then 4 entries of
   (u16 offset, u16 capacity, u16 length, u16 checksum, u8 flags, 3 reserved) = 12 bytes each. */
#define AC_OFF_PROFILE 0x0200   /* cap 64 */
#define AC_OFF_BEST    0x0240   /* cap 32 */
#define AC_OFF_RUN     0x0400   /* cap 14336 */
#define AC_OFF_GHOST   0x3C00   /* cap 16384 */
#define AC_FLAG_TRUNCATED 1

uint16_t ac_save_sum(const uint8_t *p, uint32_t n);        /* 0x5A5A + sum of bytes, mod 65536 */
void ac_save_format(uint8_t *save, const char game[4]);     /* header + empty table; leaves 0..0xFF untouched */
/* Writes one section's payload and its table entry; 0 if it does not fit or the header is missing. */
int ac_save_put(uint8_t *save, int sec, const uint8_t *data, uint32_t len, uint8_t flags);
/* Fills in one section's table entry for a payload already in its slot (sum = ac_save_sum of it), for callers
   that build a payload in place over several frames; 0 if it does not fit or the header is missing. */
int ac_save_commit(uint8_t *save, int sec, uint32_t len, uint16_t sum, uint8_t flags);
/* Returns the payload pointer and length, or 0 if absent, bad checksum, bad header or wrong game. */
const uint8_t *ac_save_get(const uint8_t *save, const char game[4], int sec, uint32_t *len, uint8_t *flags);

/* Profile payload (64 B): name[12] ASCII (NUL padded), tag[8], trophies u32, seed nonce u32, boot count u32,
   32 reserved. The launcher writes a fresh non-zero nonce and boot count 0 before each launch; the ROM bumps the
   boot count at every boot and seeds the run with ac_seed_mix(nonce, boots). Nonce 0 (or no profile): seed 0. */
#define AC_PROFILE_SEED_NONCE 24
#define AC_PROFILE_BOOTS      28
/* Best payload (32 B): frames u32, score u32, trophies u32, final_hash u32, 16 reserved. */
/* Ghost payload: "ACG1", game[4], source_final_hash u32, period u16, count u16, then count points of
   (i16 x, i16 y, u8 angle, u8 flags) = 6 bytes each. */
typedef struct { int16_t x, y; uint8_t angle, flags; } ac_ghost_pt;

#ifdef __cplusplus
}
#endif
#endif

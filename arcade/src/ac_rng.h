#ifndef AC_RNG_H
#define AC_RNG_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint16_t ac_rng16(uint16_t x);   /* xorshift16 (7, 9, 8), as SHIP IT! rng_next */
uint32_t ac_rng32(uint32_t x);   /* xorshift32 (13, 17, 5) */
/* A run's seed from the profile's seed nonce (written fresh by the launcher before each launch) and the boot count
   since then (the ROM bumps it every boot, so a run started from the results without the launcher gets its own seed
   too). No nonce (0) gives 0: the classic, unseeded game. Otherwise never 0: xorshift32 of the FNV-1a hash of
   (nonce, boots), a zero hash replaced by 0x9E3779B9. */
uint32_t ac_seed_mix(uint32_t nonce, uint32_t boots);
#ifdef __cplusplus
}
#endif
#endif

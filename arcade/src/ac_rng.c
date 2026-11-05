#include "ac_rng.h"
#include "ac_hash.h"
uint16_t ac_rng16(uint16_t x) {
    x ^= (uint16_t)(x << 7);
    x ^= (uint16_t)(x >> 9);
    x ^= (uint16_t)(x << 8);
    return x;
}
uint32_t ac_rng32(uint32_t x) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}
uint32_t ac_seed_mix(uint32_t nonce, uint32_t boots) {
    ac_hash h;
    if (nonce == 0) return 0;
    ac_hash_begin(&h);
    ac_hash_u32(&h, nonce);
    ac_hash_u32(&h, boots);
    return ac_rng32(h.h ? h.h : 0x9E3779B9u);   /* xorshift32 maps a non-zero value to a non-zero value */
}

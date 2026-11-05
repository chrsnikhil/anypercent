#include "rng.h"

/* xorshift16 (7, 9, 8): a full-period 16-bit generator; never returns 0 for a non-zero seed */
uint16_t rng_next(uint16_t x) {
    x ^= (uint16_t)(x << 7);
    x ^= (uint16_t)(x >> 9);
    x ^= (uint16_t)(x << 8);
    return x;
}

#include "ac_fix.h"

extern const int16_t ac_sin_q[257];
extern const uint16_t ac_atan_t[257];

static ac_fix sat(int64_t v) {
    if (v > INT32_MAX) return INT32_MAX;
    if (v < INT32_MIN) return INT32_MIN;
    return (ac_fix)v;
}

ac_fix ac_fmul(ac_fix a, ac_fix b) { return sat(((int64_t)a * b) >> 16); }

ac_fix ac_fdiv(ac_fix a, ac_fix b) {
    if (b == 0) return a > 0 ? INT32_MAX : (a < 0 ? INT32_MIN : 0);    /* defined on every target: no trap */
    return sat(((int64_t)a * 65536) / b);
}

int16_t ac_sin(uint16_t a) {
    uint16_t q = (uint16_t)(a & 1023u);
    if (q < 256) return ac_sin_q[q];
    if (q < 512) return ac_sin_q[512 - q];
    if (q < 768) return (int16_t)-ac_sin_q[q - 512];
    return (int16_t)-ac_sin_q[1024 - q];
}

int16_t ac_cos(uint16_t a) { return ac_sin((uint16_t)(a + 256u)); }

uint16_t ac_atan2(int32_t y, int32_t x) {
    uint32_t ax = x < 0 ? (uint32_t)0 - (uint32_t)x : (uint32_t)x;
    uint32_t ay = y < 0 ? (uint32_t)0 - (uint32_t)y : (uint32_t)y;
    uint16_t base;
    if (ax == 0 && ay == 0) return 0;
    if (ay <= ax) base = ac_atan_t[(uint32_t)(((uint64_t)ay * 256u + ax / 2u) / ax)];
    else base = (uint16_t)(256u - ac_atan_t[(uint32_t)(((uint64_t)ax * 256u + ay / 2u) / ay)]);
    if (x >= 0 && y >= 0) return base;
    if (x < 0 && y >= 0) return (uint16_t)(512u - base);
    if (x < 0) return (uint16_t)(512u + base);
    return (uint16_t)((1024u - base) & 1023u);
}

uint32_t ac_isqrt(uint32_t v) {
    uint32_t r = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit) {
        if (v >= r + bit) { v -= r + bit; r = (r >> 1) + bit; }
        else r >>= 1;
        bit >>= 2;
    }
    return r;
}

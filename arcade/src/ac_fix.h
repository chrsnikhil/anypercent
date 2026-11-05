/* Q16.16 fixed point and 1024-step angles. No floats. */
#ifndef AC_FIX_H
#define AC_FIX_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef int32_t ac_fix;
#define AC_FIX_ONE 65536
#define AC_ANGLE_STEPS 1024
ac_fix ac_fmul(ac_fix a, ac_fix b);          /* saturates to INT32_MIN..INT32_MAX */
ac_fix ac_fdiv(ac_fix a, ac_fix b);          /* saturates; a / 0 is INT32_MAX for a > 0, INT32_MIN for a < 0, 0 for 0 */
int16_t ac_sin(uint16_t a);     /* Q1.14; the angle wraps modulo 1024 */
int16_t ac_cos(uint16_t a);
/* The angle of (x, y) in 1024 steps, 0 along +x and 256 along +y, within 2 steps; ac_atan2(0, 0) is 0. Any int32
   inputs, including INT32_MIN, are safe (magnitudes are taken as uint32). */
uint16_t ac_atan2(int32_t y, int32_t x);
/* floor(sqrt(v)) for every uint32 v: ac_isqrt(0) is 0, ac_isqrt(0xFFFFFFFF) is 65535. */
uint32_t ac_isqrt(uint32_t v);
#ifdef __cplusplus
}
#endif
#endif

#ifndef AC_HASH_H
#define AC_HASH_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { uint32_t h; } ac_hash;
void ac_hash_begin(ac_hash *s);
void ac_hash_u8(ac_hash *s, uint8_t v);
void ac_hash_u16(ac_hash *s, uint16_t v);
void ac_hash_u32(ac_hash *s, uint32_t v);
void ac_hash_i32(ac_hash *s, int32_t v);
#ifdef __cplusplus
}
#endif
#endif

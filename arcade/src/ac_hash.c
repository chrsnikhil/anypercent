#include "ac_hash.h"
void ac_hash_begin(ac_hash *s) { s->h = 2166136261u; }
void ac_hash_u8(ac_hash *s, uint8_t v) { s->h = (s->h ^ v) * 16777619u; }
void ac_hash_u16(ac_hash *s, uint16_t v) { ac_hash_u8(s, (uint8_t)v); ac_hash_u8(s, (uint8_t)(v >> 8)); }
void ac_hash_u32(ac_hash *s, uint32_t v) { ac_hash_u16(s, (uint16_t)v); ac_hash_u16(s, (uint16_t)(v >> 16)); }
void ac_hash_i32(ac_hash *s, int32_t v) { ac_hash_u32(s, (uint32_t)v); }

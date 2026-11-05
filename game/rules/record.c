#include "record.h"

static uint16_t record_sum(const uint8_t *b) {
    uint16_t sum = 0x5A5A;
    uint8_t i;
    for (i = 0; i < 6; i++) sum = (uint16_t)(sum + b[i]);
    return sum;
}

void record_encode(uint32_t frames, uint8_t out[8]) {
    uint8_t i;
    uint16_t sum;
    out[0] = 'S';
    out[1] = 'I';
    for (i = 0; i < 4; i++) out[2 + i] = (uint8_t)(frames >> (8 * i));
    sum = record_sum(out);
    out[6] = (uint8_t)sum;
    out[7] = (uint8_t)(sum >> 8);
}

uint32_t record_decode(const uint8_t in[8]) {
    uint32_t frames = 0;
    uint8_t i;
    uint16_t sum = record_sum(in);
    if (in[0] != 'S' || in[1] != 'I' || in[6] != (uint8_t)sum || in[7] != (uint8_t)(sum >> 8)) return 0;
    for (i = 0; i < 4; i++) frames |= (uint32_t)in[2 + i] << (8 * i);
    return frames;
}

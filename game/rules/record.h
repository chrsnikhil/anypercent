/* The best-time record kept in cartridge save memory (8 bytes): 'S' 'I', the run's frames (4 bytes, little
   endian), and a checksum (2 bytes, little endian: 0x5A5A plus bytes 0 to 5). Not part of the rules or the hash. */
#ifndef RECORD_H
#define RECORD_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void record_encode(uint32_t frames, uint8_t out[8]);
uint32_t record_decode(const uint8_t in[8]);      /* 0 for a blank or corrupted record */

#ifdef __cplusplus
}
#endif

#endif

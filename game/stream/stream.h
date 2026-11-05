/* Background streaming bookkeeping for SHIP IT!: which room cells go into which video-memory tile slots.
   Pure C with no hardware access; the ROM copies the tiles, and the PC tests model video memory. */
#ifndef STREAM_H
#define STREAM_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define STREAM_COLS       32
#define STREAM_SLOT_ROWS  24
#define STREAM_MAP_ROWS   32
#define STREAM_SLOTS      (STREAM_COLS * STREAM_SLOT_ROWS)
#define STREAM_VIEW_W     240
#define STREAM_VIEW_H     160
#define STREAM_MAX_WRITES (31 * 21)
#define STREAM_EMPTY      0xFFFFu

typedef struct {
    uint16_t held[STREAM_SLOTS];            /* the room cell each slot holds, or STREAM_EMPTY */
    uint16_t room_w_cells, room_h_cells;
} stream_state;

typedef struct {
    uint16_t count;
    uint16_t slot[STREAM_MAX_WRITES];       /* copy room cell `cell`'s tile into this slot */
    uint16_t map_index[STREAM_MAX_WRITES];  /* and point this hardware map entry at the slot */
    uint16_t cell[STREAM_MAX_WRITES];
} stream_writes;

void stream_init(stream_state* s, uint16_t room_w_cells, uint16_t room_h_cells);
/* writes at most max_writes cells; the rest stay stale until a later update */
void stream_update(stream_state* s, int16_t cam_x, int16_t cam_y, stream_writes* out, uint16_t max_writes);
uint16_t stream_slot(uint16_t cx, uint16_t cy);
uint16_t stream_map_index(uint16_t cx, uint16_t cy);

#ifdef __cplusplus
}
#endif

#endif

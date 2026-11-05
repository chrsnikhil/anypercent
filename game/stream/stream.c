#include "stream.h"

uint16_t stream_slot(uint16_t cx, uint16_t cy) {
    return (uint16_t)((cx % STREAM_COLS) + STREAM_COLS * (cy % STREAM_SLOT_ROWS));
}

uint16_t stream_map_index(uint16_t cx, uint16_t cy) {
    return (uint16_t)((cx % STREAM_COLS) + STREAM_COLS * (cy % STREAM_MAP_ROWS));
}

void stream_init(stream_state* s, uint16_t room_w_cells, uint16_t room_h_cells) {
    uint16_t i;
    for (i = 0; i < STREAM_SLOTS; i++) s->held[i] = STREAM_EMPTY;
    s->room_w_cells = room_w_cells;
    s->room_h_cells = room_h_cells;
}

void stream_update(stream_state* s, int16_t cam_x, int16_t cam_y, stream_writes* out, uint16_t max_writes) {
    int16_t x0 = cam_x < 0 ? 0 : cam_x, y0 = cam_y < 0 ? 0 : cam_y;
    uint16_t cx0 = (uint16_t)(x0 / 8), cy0 = (uint16_t)(y0 / 8);
    uint16_t cx1 = (uint16_t)((x0 + STREAM_VIEW_W - 1) / 8), cy1 = (uint16_t)((y0 + STREAM_VIEW_H - 1) / 8);
    uint16_t cx, cy, slot, cell;
    if (cx1 >= s->room_w_cells) cx1 = (uint16_t)(s->room_w_cells - 1);
    if (cy1 >= s->room_h_cells) cy1 = (uint16_t)(s->room_h_cells - 1);
    out->count = 0;
    for (cy = cy0; cy <= cy1; cy++) {
        for (cx = cx0; cx <= cx1; cx++) {
            slot = stream_slot(cx, cy);
            cell = (uint16_t)(cy * s->room_w_cells + cx);
            if (s->held[slot] == cell) continue;
            if (out->count >= max_writes) return;
            s->held[slot] = cell;
            out->slot[out->count] = slot;
            out->map_index[out->count] = stream_map_index(cx, cy);
            out->cell[out->count] = cell;
            out->count++;
        }
    }
}

// The raycaster (view code, ARM in IWRAM): draws the 3D view into mode 4's hidden page in the rotated layout the
// Task 0 spike chose -- the BG2 matrix shows memory row c (240 bytes) as screen columns 2c and 2c+1, byte y of it as
// screen row y -- so a screen column is contiguous memory. 120 columns x 128 rows of view; bytes 128..159 of each
// row are the HUD strip. Walls, doors and billboards are composed per column in an IWRAM buffer, then copied out.
// Colour index = light level * 64 + base colour (tools/art/build_art.py): fog and side shading OR the level in.
#ifndef SEGF_RAYCASTER_H
#define SEGF_RAYCASTER_H

#include <stdint.h>

namespace ray
{
    constexpr int cols = 120;
    constexpr int view_h = 128;
    constexpr int max_billboards = 32;       // every bug (MAX_BUGS <= 32: drawn_mask() bits)

    struct camera
    {
        int32_t px, py;          // Q16 map units
        int32_t dirx, diry;      // Q16 unit vector
        int32_t planex, planey;  // Q16, dir rotated a quarter turn right, scaled to the field of view
    };

    struct billboard
    {
        int32_t x, y;            // Q16 map position
        const uint8_t* frame;    // 64 x 64, column-major, 0 transparent
        int32_t height;          // world units Q16 (1.0 = a wall's height)
        int id;                  // the caller's number for it (0..31): drawn_mask() bit
        // filled by project():
        int32_t depth;           // Q16
        int left, right;         // columns [left, right)
        int32_t lcol;            // Q16 left edge in columns
        int32_t xscale;          // texels per column, Q16
        int top, bottom;         // rows [top, bottom) unclipped
        int32_t yscale;          // texels per row, Q16
        uint32_t mask;           // light level, OR-ed into each texel
    };

    // Once at boot: textures to EWRAM, the tables.
    void setup();

    // Before a view: the rules' map (CELL_* per cell), then the slide amount (0..30) of each sliding cell it lists.
    void load_map(const uint8_t* rules_cells);
    int sliding_count();
    int sliding_cell(int i);                    // cell index (y * 48 + x)
    void set_slide(int i, uint8_t amount);

    // The radar window into the HUD strip in RAM: w x h cells from map cell (ox, oy), one memory column x two rows
    // per cell at (x0, y0); colours[cell kind] (colours[15] outside the map), doors by their state.
    void draw_radar(uint8_t* hud_ram, int ox, int oy, int w, int h, int x0, int y0, const uint8_t* colours,
                    uint8_t open_door, uint8_t shut_door);

    // Starts a view: camera and billboards (projected and sorted here; up to max_billboards).
    void begin(const camera& cam, billboard* bills, int count);

    // Draws columns [c0, c1) into page (the hidden page's base).
    void render(uint8_t* page, int c0, int c1);

    // Bit id of each billboard that put at least one pixel on the page since begin().
    uint32_t drawn_mask();

    // The depth (Q16) the walls left in column c after render; for the ghost's occlusion test.
    int32_t depth_at(int c);

    // Projects a map point: screen column (0..119, may be outside) and depth (Q16); false when behind the camera.
    bool project(const camera& cam, int32_t x, int32_t y, int32_t& col_q16, int32_t& depth);

    // Word copy in 8-word blocks (words: a multiple of 8; both pointers word-aligned).
    void copy_blocks(void* dst, const void* src, int words);

    // The bug billboards (EWRAM copy of segf_bugs).
    const uint8_t* bug_frames();

    // The HUD strip in RAM (120 x 32, [x][y]); the view edits it and copy_hud() puts it on the page.
    uint8_t* hud();
    void copy_hud(uint8_t* page);

    // Darkens view rows [y0, y1) (multiples of 4) of every column to the darkest light level: a band for text.
    void darken_rows(uint8_t* page, int y0, int y1);
}

#endif

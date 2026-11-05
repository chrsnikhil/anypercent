// The per-column renderer and the other per-view loops, ARM code in IWRAM (see raycaster.h; the measurements are
// in the README). A column with no billboard in it goes straight to VRAM in 32-bit words (ceiling, wall, floor);
// a column with one is composed in an IWRAM buffer first, then copied out in 8-word blocks.
#include "raycaster_state.h"

#include "bn_common.h"

namespace ray
{

using namespace detail;

namespace
{
    struct block { uint32_t w[8]; };
    alignas(4) uint8_t colbuf[view_h];

    inline int32_t fm(int32_t a, int32_t b)
    {
        return int32_t((int64_t(a) * b) >> 16);
    }

    inline int32_t rcp(int32_t a)
    {
        int32_t i = a >> 4;
        return i <= 0 ? 0x7FFFFFFF : recip[i < recip_n ? i : recip_n - 1];
    }

    // texture number + 1 of each rules cell kind (CELL_* in rules/game.h): walls 1..11 are CELL_RACK..CELL_PUSH
    constexpr uint8_t cell_texture[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 12, 0, 0};

    // One column: ceiling words, the wall [ds, de) (partial words at both ends mixed with the background), floor.
    [[gnu::always_inline]] inline void wall_words(uint32_t* dst, int ds, int de, const uint8_t* t, int32_t pos,
                                                  int32_t step, uint32_t mask4)
    {
        int w0 = ds >> 2, w1 = (de + 3) >> 2;
        for(int w = 0; w < w0; ++w)
        {
            dst[w] = bg_words[w];
        }
        // the texel position at the first word's first row; texels are read unmasked (pos stays inside the column,
        // give or take the last row's rounding, which reads the next column's first texel)
        pos -= (ds & 3) * step;
        for(int w = w0; w < w1; ++w)
        {
            int y = w << 2;
            uint32_t word;
            if(y >= ds && y + 4 <= de)
            {
                uint32_t p0 = t[uint32_t(pos) >> 16]; pos += step;
                uint32_t p1 = t[uint32_t(pos) >> 16]; pos += step;
                uint32_t p2 = t[uint32_t(pos) >> 16]; pos += step;
                uint32_t p3 = t[uint32_t(pos) >> 16]; pos += step;
                word = (p0 | (p1 << 8) | (p2 << 16) | (p3 << 24)) | mask4;
            }
            else
            {
                uint32_t bg = bg_words[w];
                word = 0;
                for(int k = 0; k < 4; ++k)
                {
                    int yy = y + k;
                    uint32_t v;
                    if(yy >= ds && yy < de)
                    {
                        v = t[uint32_t(pos) >> 16] | (mask4 & 0xFF);
                    }
                    else
                    {
                        v = (bg >> (8 * k)) & 0xFF;
                    }
                    pos += step;
                    word |= v << (8 * k);
                }
            }
            dst[w] = word;
        }
        for(int w = w1; w < view_h / 4; ++w)
        {
            dst[w] = bg_words[w];
        }
    }
}

BN_CODE_IWRAM void copy_blocks(void* dst, const void* src, int words)
{
    auto* d = static_cast<block*>(dst);
    auto* s = static_cast<const block*>(src);
    for(int i = 0; i < words / 8; ++i)
    {
        d[i] = s[i];
    }
}

BN_CODE_IWRAM void load_map(const uint8_t* rules_cells)
{
    int n = 0;
    for(int i = 0; i < map_w * map_w; ++i)
    {
        uint8_t c = rules_cells[i];
        raw[i] = c;
        cells[i] = cell_texture[c & 15];
        if((c == 5 || c == 11 || c == 13) && n < max_sliding)   // CELL_DOOR, CELL_PUSH, CELL_LOCKED
        {
            door_list[n++] = uint16_t(i);
        }
    }
    n_door_list = n;
}

BN_CODE_IWRAM void draw_radar(uint8_t* hud_ram, int ox, int oy, int w, int h, int x0, int y0,
                              const uint8_t* colours, uint8_t open_door, uint8_t shut_door)
{
    for(int wx = 0; wx < w; ++wx)
    {
        uint8_t* col = hud_ram + (x0 + wx) * 32 + y0;
        int cx = ox + wx;
        for(int wy = 0; wy < h; ++wy)
        {
            int cy = oy + wy;
            uint8_t v = colours[15];
            if(unsigned(cx) < unsigned(map_w) && unsigned(cy) < unsigned(map_w))
            {
                int i = cy * map_w + cx;
                uint8_t c = raw[i];
                v = colours[c & 15];
                if(c == 5 || c == 13)                    // CELL_DOOR, CELL_LOCKED
                {
                    v = doors[i] == slide_frames ? open_door : shut_door;
                }
            }
            col[wy * 2] = v;
            col[wy * 2 + 1] = v;
        }
    }
}

BN_CODE_IWRAM void render(uint8_t* page, int c0, int c1)
{
    const camera& c = cam;
    for(int col = c0; col < c1; ++col)
    {
        // ---- cast the ray (DDA over the grid) ----
        int32_t rdx = c.dirx + fm(c.planex, camx[col]);
        int32_t rdy = c.diry + fm(c.planey, camx[col]);
        int mx = c.px >> 16, my = c.py >> 16;
        int32_t ddx = rcp(rdx < 0 ? -rdx : rdx), ddy = rcp(rdy < 0 ? -rdy : rdy);
        int sx, sy;
        int32_t sdx, sdy;
        if(rdx < 0) { sx = -1; sdx = fm(c.px - (mx << 16), ddx); } else { sx = 1; sdx = fm(((mx + 1) << 16) - c.px, ddx); }
        if(rdy < 0) { sy = -1; sdy = fm(c.py - (my << 16), ddy); } else { sy = 1; sdy = fm(((my + 1) << 16) - c.py, ddy); }
        int side = 0, texno = 0, tx = 0;
        int32_t perp = 0x7FFFFFFF;
        for(int guard = 0; guard < 2 * map_w; ++guard)
        {
            if(sdx < sdy) { sdx += ddx; mx += sx; side = 0; }
            else { sdy += ddy; my += sy; side = 1; }
            if(unsigned(mx) >= unsigned(map_w) || unsigned(my) >= unsigned(map_w))
            {
                break;
            }
            int cell = cells[my * map_w + mx];
            if(! cell)
            {
                continue;
            }
            int32_t p = side == 0 ? sdx - ddx : sdy - ddy;
            int32_t wallx = side == 0 ? c.py + fm(p, rdy) : c.px + fm(p, rdx);
            int t = (wallx >> 10) & (tex - 1);
            if((side == 0 && rdx < 0) || (side == 1 && rdy > 0))      // y-down map: keep textures unmirrored
            {
                t = tex - 1 - t;
            }
            if(cell - 1 == door_tex || cell - 1 == push_tex || cell - 1 == locked_tex)
            {
                int open = (doors[my * map_w + mx] * (tex * 2185)) >> 16;      // amount * 64 / 30
                if(t < open)
                {
                    continue;                                   // the ray passes the slid-away part
                }
                t -= open;
            }
            texno = cell - 1;
            tx = t;
            perp = p;
            break;
        }
        if(perp < 0x1000)
        {
            perp = 0x1000;
        }
        zbuf[col] = perp;

        int ds = view_h, de = view_h;
        int32_t pos = 0, step = 0;
        uint32_t mask4 = 0;
        const uint8_t* t = textures;
        if(perp != 0x7FFFFFFF)
        {
            int li = perp >> lh_shift;
            int lh = line_heights[li < lh_n ? li : lh_n - 1];
            ds = view_h / 2 - lh / 2;
            de = ds + lh;
            step = fm(perp, step_per_perp);
            if(ds < 0) { pos = -ds * step; ds = 0; }
            if(de > view_h) de = view_h;
            int level = side + (perp < 0x30000 ? 0 : perp < 0x60000 ? 1 : perp < 0xA0000 ? 2 : 3);
            mask4 = uint32_t(level > 3 ? 3 : level) * 0x40404040u;
            t = textures + (texno * tex + tx) * tex;
        }

        bool sprite = false;
        for(int i = 0; i < n_bills; ++i)
        {
            const billboard& b = *bills[i];
            if(col >= b.left && col < b.right && b.depth < perp)
            {
                sprite = true;
                break;
            }
        }
        auto* vram = reinterpret_cast<uint32_t*>(page + col * 240);
        if(! sprite)
        {
            wall_words(vram, ds, de, t, pos, step, mask4);
            continue;
        }

        // ---- billboards, far to near, where nearer than the wall: compose in IWRAM ----
        wall_words(reinterpret_cast<uint32_t*>(colbuf), ds, de, t, pos, step, mask4);
        for(int i = 0; i < n_bills; ++i)
        {
            const billboard& b = *bills[i];
            if(col < b.left || col >= b.right || b.depth >= perp)
            {
                continue;
            }
            int bx = int((int64_t((col << 16) + 0x8000 - b.lcol) * b.xscale) >> 32);
            if(unsigned(bx) >= unsigned(tex))
            {
                continue;
            }
            const uint8_t* f = b.frame + bx * tex;
            drawn |= 1u << b.id;
            int y0 = b.top < 0 ? 0 : b.top;
            int y1 = b.bottom > view_h ? view_h : b.bottom;
            int32_t bpos = (y0 - b.top) * b.yscale;
            unsigned mask = b.mask;
            for(int y = y0; y < y1; ++y)
            {
                unsigned p = f[uint32_t(bpos) >> 16];
                bpos += b.yscale;
                if(p)
                {
                    colbuf[y] = uint8_t(p | mask);
                }
            }
        }
        auto* src = reinterpret_cast<const block*>(colbuf);
        auto* dst = reinterpret_cast<block*>(vram);
        dst[0] = src[0];
        dst[1] = src[1];
        dst[2] = src[2];
        dst[3] = src[3];
    }
}

}

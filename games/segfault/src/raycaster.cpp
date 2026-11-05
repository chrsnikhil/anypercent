#include "raycaster_state.h"

#include "bn_common.h"
#include "bn_memory.h"

extern "C" {
#include "segf_art.h"
}

namespace ray
{

namespace detail
{
    namespace
    {
        BN_DATA_EWRAM_BSS alignas(4) uint8_t texture_store[SEGF_TEX_COUNT * tex * tex];
        BN_DATA_EWRAM_BSS int32_t recip_store[recip_n];
        BN_DATA_EWRAM_BSS alignas(4) uint8_t hud_store[cols * 32];
        BN_DATA_EWRAM_BSS uint16_t lh_store[lh_n];
        BN_DATA_EWRAM_BSS uint8_t door_store[map_w * map_w];
        BN_DATA_EWRAM_BSS uint8_t raw_store[map_w * map_w];
        BN_DATA_EWRAM_BSS alignas(4) uint8_t bug_store[sizeof(segf_bugs)];
    }

    uint16_t* line_heights = lh_store;
    uint8_t* doors = door_store;
    uint8_t* raw = raw_store;

    uint8_t* textures = texture_store;
    int32_t* recip = recip_store;
    uint8_t cells[map_w * map_w];
    uint16_t door_list[max_sliding];
    int n_door_list;
    int32_t camx[cols];
    int32_t zbuf[cols];
    uint32_t bg_words[view_h / 4];
    camera cam;
    billboard* bills[max_billboards];
    int n_bills;
    uint32_t drawn;
}

using namespace detail;

void setup()
{
    bn::memory::copy(segf_textures[0], int(sizeof(segf_textures)), texture_store[0]);
    recip_store[0] = 0x7FFFFFFF;
    for(int i = 1; i < recip_n; ++i)
    {
        recip_store[i] = int32_t((1 << 28) / i);
    }
    lh_store[0] = 8191;
    for(int i = 1; i < lh_n; ++i)
    {
        int v = (proj << 10) / i;
        lh_store[i] = uint16_t(v > 8191 ? 8191 : v);
    }
    for(int c = 0; c < cols; ++c)
    {
        camx[c] = ((2 * c + 1 - cols) << 16) / cols;
    }
    for(int w = 0; w < view_h / 4; ++w)
    {
        const uint8_t* b = segf_bg_column + w * 4;
        bg_words[w] = uint32_t(b[0]) | (uint32_t(b[1]) << 8) | (uint32_t(b[2]) << 16) | (uint32_t(b[3]) << 24);
    }
    bn::memory::copy(segf_hud[0], int(sizeof(segf_hud)), hud_store[0]);
    bn::memory::copy(segf_bugs[0], int(sizeof(segf_bugs)), bug_store[0]);
}

int sliding_count()
{
    return n_door_list;
}

int sliding_cell(int i)
{
    return door_list[i];
}

void set_slide(int i, uint8_t amount)
{
    doors[door_list[i]] = amount;
}

const uint8_t* bug_frames()
{
    return bug_store;
}

uint8_t* hud()
{
    return hud_store;
}

void copy_hud(uint8_t* page)
{
    for(int c = 0; c < cols; ++c)
    {
        auto* dst = reinterpret_cast<uint32_t*>(page + c * 240 + view_h);
        auto* src = reinterpret_cast<const uint32_t*>(hud_store + c * 32);
        for(int w = 0; w < 8; ++w)
        {
            dst[w] = src[w];
        }
    }
}

void darken_rows(uint8_t* page, int y0, int y1)
{
    for(int c = 0; c < cols; ++c)
    {
        auto* row = reinterpret_cast<uint32_t*>(page + c * 240);
        for(int w = y0 / 4; w < y1 / 4; ++w)
        {
            row[w] |= 0xC0C0C0C0u;
        }
    }
}

uint32_t drawn_mask()
{
    return drawn;
}

int32_t depth_at(int c)
{
    return c >= 0 && c < cols ? zbuf[c] : 0;
}

bool project(const camera& c, int32_t x, int32_t y, int32_t& col_q16, int32_t& depth)
{
    int64_t rx = x - c.px, ry = y - c.py;
    depth = int32_t((rx * c.dirx + ry * c.diry) >> 16);
    if(depth < 0x3000)
    {
        return false;
    }
    int32_t lat = int32_t((rx * -c.diry + ry * c.dirx) >> 16);
    // 60 columns per 0.66 of lateral offset at depth 1: 90.9 * lat / depth, one 32-bit division
    int32_t inv = int32_t((1u << 30) / uint32_t(depth));                 // Q14 of 1 / depth
    col_q16 = (60 << 16) + int32_t((int64_t(lat) * inv * 5957) >> 20);   // 5957 = 90.9 in Q6
    return true;
}

void begin(const camera& c, billboard* list, int count)
{
    cam = c;
    n_bills = 0;
    drawn = 0;
    for(int i = 0; i < count && n_bills < max_billboards; ++i)
    {
        billboard& b = list[i];
        int32_t colq;
        if(! project(c, b.x, b.y, colq, b.depth) || b.depth < 0x6000)     // nearer: under the player's feet
        {
            continue;
        }
        int32_t inv = int32_t((1u << 30) / uint32_t(b.depth));        // Q14 of 1 / depth
        int h = int((int64_t(proj) * b.height * inv) >> 30);          // pixels
        if(h < 2)
        {
            continue;
        }
        int wcols = h / 2;                                            // square frame; a column is 2 pixels
        if(wcols < 1)
        {
            wcols = 1;
        }
        b.lcol = colq - (wcols << 15);
        b.left = b.lcol >> 16;
        b.right = b.left + wcols + 1;
        if(b.right <= 0 || b.left >= cols)
        {
            continue;
        }
        b.xscale = (tex << 16) / wcols;
        b.bottom = view_h / 2 + int((int64_t(proj / 2) * inv) >> 14);
        b.top = b.bottom - h;
        b.yscale = (tex << 16) / h;
        int level = b.depth < 0x30000 ? 0 : b.depth < 0x60000 ? 1 : b.depth < 0xA0000 ? 2 : 3;
        b.mask = uint32_t(level) << 6;
        // insertion sort, far to near
        int k = n_bills++;
        while(k > 0 && bills[k - 1]->depth < b.depth)
        {
            bills[k] = bills[k - 1];
            --k;
        }
        bills[k] = &b;
    }
}

}

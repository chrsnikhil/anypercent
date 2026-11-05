#include "mode7.h"

#include "track_props.h"

namespace md
{

namespace
{
    // per line: lam = CAM_H / d plane px per screen px (8.8) and the line's distance z = lam * FOCAL (1/16 px)
    struct line_table
    {
        int lam[160];
        int z16[160];

        constexpr line_table() : lam(), z16()
        {
            for(int line = HORIZON + HAZE; line < 160; ++line)
            {
                lam[line] = (CAM_H << 8) / (line - HORIZON + 1);
                z16[line] = (lam[line] * FOCAL) >> 4;
            }
        }
    };

    constexpr line_table lines;
}

void ground_lines(int cam_x, int cam_y, int s, int c, int16_t* pa, int16_t* pc, int* dx, int* dy)
{
    for(int line = HORIZON + HAZE; line < 160; ++line)
    {
        int lam = lines.lam[line];
        int z16 = lines.z16[line];
        int a = -(lam * s) >> 14;
        int b = (lam * c) >> 14;
        pa[line] = int16_t(a);
        pc[line] = int16_t(b);
        dx[line] = cam_x + ((z16 * c) >> 10) - 120 * a;
        dy[line] = cam_y + ((z16 * s) >> 10) - 120 * b;
    }
}

bool project(int cam_x, int cam_y, int s, int c, int px8, int py8, int& sx, int& sy, int& z8)
{
    int rx = (px8 - cam_x) >> 4;                   // 1/16 px: the products below fit 32 bits
    int ry = (py8 - cam_y) >> 4;
    if(rx > FAR * 16 || rx < -FAR * 16 || ry > FAR * 16 || ry < -FAR * 16)
    {
        return false;
    }
    int z16 = (rx * c + ry * s) >> 14;
    if(z16 < NEAR * 16)
    {
        return false;
    }
    int xr16 = (ry * c - rx * s) >> 14;
    if(xr16 > z16 * 2 || xr16 < -z16 * 2)          // well outside the view cone (it is +-120 / 128 wide)
    {
        return false;
    }
    z8 = z16 << 4;
    sy = HORIZON - 1 + (CAM_H * FOCAL * 16) / z16;
    sx = 120 + (xr16 * FOCAL) / z16;
    return sx > -80 && sx < 320 && sy < 240;
}

int cull_props(int cam_x, int cam_y, int s, int c, bool orbs, int max, int* idx, int* zs, int* sxs, int* sys)
{
    // the gantry's three pieces go together, once any of them is nearer than the player (the camera is under it)
    bool gantry = true;
    for(int i = 0; i < props_count; ++i)
    {
        if(props[i].kind >= GANTRY_L && props[i].kind <= GANTRY_R)
        {
            int rx = ((props[i].x << 8) - cam_x) >> 4;
            int ry = ((props[i].y << 8) - cam_y) >> 4;
            if(((rx * c + ry * s) >> 14) < CAM_DIST * 16 && ((rx * c + ry * s) >> 14) > -FAR * 16)
            {
                gantry = false;
            }
        }
    }
    int n = 0;
    for(int i = 0; i < props_count; ++i)
    {
        int sx, sy, z8;
        if(! project(cam_x, cam_y, s, c, props[i].x << 8, props[i].y << 8, sx, sy, z8) || z8 > (FAR << 8) ||
           z8 < (PROP_NEAR << 8))
        {
            continue;
        }
        int kind = props[i].kind;
        if((kind == ORB && (! orbs || z8 < (CAM_DIST << 8))) || (kind >= GANTRY_L && kind <= GANTRY_R && ! gantry))
        {
            continue;                              // the gantry and the orbs go once they reach the player
        }
        if(n == max && z8 >= zs[n - 1])
        {
            continue;
        }
        int j = n < max ? n++ : n - 1;
        while(j > 0 && zs[j - 1] > z8)
        {
            idx[j] = idx[j - 1];
            zs[j] = zs[j - 1];
            sxs[j] = sxs[j - 1];
            sys[j] = sys[j - 1];
            --j;
        }
        idx[j] = i;
        zs[j] = z8;
        sxs[j] = sx;
        sys[j] = sy;
    }
    return n;
}

}

#include "view.h"

#include "bn_bg_palettes.h"
#include "bn_blending.h"
#include "bn_core.h"
#include "bn_color.h"
#include "bn_sprite_palette_item.h"
#include "bn_string.h"

#include "arcade_runtime.h"
#include "common_variable_8x8_sprite_font.h"
#include "mode7.h"
#include "track_props.h"
#include "bn_affine_bg_items_track.h"
#include "bn_regular_bg_items_skyline.h"
#include "bn_sprite_items_banner.h"
#include "bn_sprite_items_billboard.h"
#include "bn_sprite_items_count.h"
#include "bn_sprite_items_digits.h"
#include "bn_sprite_items_gantry.h"
#include "bn_sprite_items_kart0.h"
#include "bn_sprite_items_kart1.h"
#include "bn_sprite_items_kart2.h"
#include "bn_sprite_items_kart3.h"
#include "bn_sprite_items_logo.h"
#include "bn_sprite_items_orb.h"
#include "bn_sprite_items_palm.h"
#include "bn_sprite_items_place.h"
#include "bn_sprite_items_puff.h"
#include "bn_sprite_items_spark.h"
#include "bn_sprite_items_speed.h"

extern "C" {
#include "ac_fix.h"
#include "game.h"
#include "track.h"
#include "tuning.h"
}

// Read by the tests at its ELF symbol address: the last frame's CPU use in 1/1000 of a frame; and how the player's
// kart looks: its sprite frame (bits 0-7), the drift hop under way (bit 8), puffs on screen (bits 12-14), the
// exhaust flame (bit 16), the camera shaking (bit 20) and the steering pose (bits 24-25: 0 left, 1 straight, 2 right);
// and the gap to the ghost on screen, in frames the player is behind it (negative: ahead; 0x80000000: none shown).
extern "C" {
volatile uint32_t g_md_cpu;
volatile uint32_t g_md_look;
volatile uint32_t g_md_gap = 0x80000000u;         // none shown, from power-on
}

namespace md
{

namespace
{
    // The Mode 7 camera (mode7.h): a point at distance z (px, along the view) meets the ground at line
    // HORIZON - 1 + CAM_H * FOCAL / z. The camera sits CAM_DIST px behind the player, so the player's kart stands at
    // line HORIZON - 1 + CAM_H * FOCAL / CAM_DIST = 135.
    constexpr int KART_ANCHOR = 10;         // px above the ground line to the kart sprite's centre (at scale 1)
    constexpr int GHOST_FRAMES_PER_TURN = 16;

    constexpr bn::color SEA(5, 13, 21);

    // The gap to the ghost: the ghost's step nearest the player's position is tracked from frame to frame (it moves
    // on about one step a frame, so a climb from the last match finds it in a few looks); the gap is how many frames
    // later than the ghost the player reached that spot. Shown from GAP_FROM race frames, right-aligned under the
    // place badge, red while behind and green while ahead, redrawn at most every GAP_REDRAW frames.
    constexpr int GAP_WINDOW = 4;                    // steps a frame the match may climb: past a boosting kart's pace
    constexpr int GAP_FROM = 30;
    constexpr int GAP_REDRAW = 4;
    constexpr int GAP_RIGHT = 112;
    constexpr int GAP_Y = -52;
    constexpr uint32_t NO_GAP = 0x80000000u;

    // The gap's glyphs in the digit sheet (tools/art/build_sprites.py digits): after the clock's 12 white ones, 0-9
    // . + - in green (ahead), then the same in red (behind).
    constexpr int GAP_GREEN_FRAME = 12;
    constexpr int GAP_RED_FRAME = 25;

    int gap_frame(char ch, bool behind)
    {
        int i = ch == '.' ? 10 : ch == '+' ? 11 : ch == '-' ? 12 : ch - '0';
        return (behind ? GAP_RED_FRAME : GAP_GREEN_FRAME) + i;
    }

    // The ghost's palette: the player's kart sheet recoloured by brightness (index 0, transparent, kept) from a navy
    // outline to a pale cyan, so the ghost never reads as a copy of the player's lime kart. Worked out once, when
    // the view is made; the race's one extra sprite palette (the GBA has 16).
    bn::color ghost_colors[16];

    // every colour but index 0 becomes base + its brightness (0..31) times span / 31, per channel
    void tint(const bn::sprite_palette_item& from, bn::color* out, const int base[3], const int span[3])
    {
        const bn::span<const bn::color>& in = from.colors_ref();
        for(int i = 0; i < 16; ++i)
        {
            bn::color c = i < in.size() ? in[i] : bn::color();
            if(i > 0)
            {
                int lum = (c.red() * 5 + c.green() * 9 + c.blue() * 2) / 16;
                c = bn::color(bn::min(31, base[0] + lum * span[0] / 31), bn::min(31, base[1] + lum * span[1] / 31),
                              bn::min(31, base[2] + lum * span[2] / 31));
            }
            out[i] = c;
        }
    }

    bn::sprite_palette_item ghost_palette()
    {
        static const int navy[3] = {2, 6, 11}, cyan[3] = {12, 25, 20};      // base and span per channel
        tint(bn::sprite_items::kart0.palette_item(), ghost_colors, navy, cyan);
        return bn::sprite_palette_item(bn::span<const bn::color>(ghost_colors, 16), bn::bpp_mode::BPP_4);
    }

    const bn::sprite_item* const KART_ITEMS[4] = {
        &bn::sprite_items::kart0, &bn::sprite_items::kart1, &bn::sprite_items::kart2, &bn::sprite_items::kart3 };

    // frames -> "M:SS.T" or, with hundredths, "M:SS.HH".
    bn::string<16> time_text(uint32_t frames, bool hundredths)
    {
        uint32_t secs = frames / 60;
        bn::string<16> s = bn::to_string<8>(int(secs / 60));
        s.push_back(':');
        s.push_back(char('0' + (secs % 60) / 10));
        s.push_back(char('0' + secs % 10));
        s.push_back('.');
        uint32_t h = (frames % 60) * 100 / 60;
        s.push_back(char('0' + h / 10));
        if(hundredths)
        {
            s.push_back(char('0' + h % 10));
        }
        return s;
    }

    md_kart kart(int i)
    {
        md_kart k;
        rules_kart(i, &k);
        return k;
    }

    bn::fixed scale_of(int k, int z8)
    {
        // k px of sprite per 1 at distance k: scale = k / z, as bn::fixed (12 fraction bits)
        int s = (k << 20) / z8;
        return bn::fixed::from_data(bn::min(s, 2 << 12));
    }

    // Sprite depth layers (Butano allows 16 sort layers): nearer is a lower z order, so drawn in front. The player
    // (always CAM_DIST ahead of the camera) has a layer of its own, PLAYER_LAYER, between everything nearer than it
    // and everything at or beyond it, so no sprite in its depth bucket can cover it by insertion order.
    constexpr int PLAYER_LAYER = 4;

    int layer(int z8)
    {
        constexpr int bounds[] = {40, 56, 64, 72, 96, 128, 176, 240, 330, 450, 600};
        int z = z8 >> 8;
        int l = 0;
        while(l < 11 && z >= bounds[l])
        {
            ++l;
        }
        return l + 1 >= PLAYER_LAYER ? l + 2 : l + 1;
    }

    // set_tiles / set_z_order only on a change (both cost more than they look)
    void show_frame(bn::sprite_ptr& spr, const bn::sprite_item& item, int frame, int& cache)
    {
        if(cache != frame)
        {
            spr.set_tiles(item.tiles_item(), frame);
            cache = frame;
        }
    }

    void show_z(bn::sprite_ptr& spr, int z, int& cache)
    {
        if(cache != z)
        {
            spr.set_z_order(z);
            cache = z;
        }
    }

    int frame_for(int heading, int bearing)
    {
        return (((heading - bearing) & 1023) + 32) >> 6 & 15;
    }

    // The kart sheets hold three poses per heading (tools/render/render_karts.py): the wheel left, straight, right.
    constexpr int POSES = 3;
    constexpr int POSE_AT = 3;                    // |wheel| (md_kart.steer) from which a kart shows its turned pose
    constexpr int DRIFT_YAW = 48;                 // heading steps a drifting kart is drawn angled into the drift
    constexpr int HOP[] = {2, 4, 5, 6, 6, 5, 4, 2, 1};   // the drift hop, px above the road, frame by frame
    constexpr int HOP_FRAMES = int(sizeof(HOP) / sizeof(HOP[0]));
    constexpr int PUFF_LIFE = 14;                 // frames a puff of smoke or dust stays on screen
    constexpr int SHAKE_FRAMES = 10;              // the camera shakes this long after a wall hit

    int pose_of(int steer)
    {
        return steer <= -POSE_AT ? 0 : steer >= POSE_AT ? 2 : 1;
    }

    int kart_frame(int heading, int bearing, int steer)
    {
        return frame_for(heading, bearing) * POSES + pose_of(steer);
    }
}

view::view() :
    _ground(bn::affine_bg_items::track.create_bg(0, 0)),
    _skyline(bn::regular_bg_items::skyline.create_bg(0, 32)),
    _pa_hbe(bn::affine_bg_pa_register_hbe_ptr::create(_ground, _pa)),
    _pc_hbe(bn::affine_bg_pc_register_hbe_ptr::create(_ground, _pc)),
    _dx_hbe(bn::affine_bg_dx_register_hbe_ptr::create(_ground, _dx)),
    _dy_hbe(bn::affine_bg_dy_register_hbe_ptr::create(_ground, _dy)),
    _text(common::variable_8x8_sprite_font),
    _player(bn::sprite_items::kart0.create_sprite(0, 0)),
    _ghost(bn::sprite_items::kart0.create_sprite(0, 0)),
    _marker(bn::sprite_items::spark.create_sprite(0, 0, 2)),
    _flame(bn::sprite_items::puff.create_sprite(0, 0, 4))
{
    bn::bg_palettes::set_transparent_color(SEA);
    _ground.set_wrapping_enabled(false);
    _ground.set_z_order(1);
    _skyline.set_z_order(0);
    for(int i = 1; i < 4; ++i)
    {
        _rivals.push_back(KART_ITEMS[i]->create_sprite(0, 0));
        _rivals.back().set_visible(false);
    }
    _player.set_visible(false);
    _ghost.set_visible(false);
    _ghost.set_palette(ghost_palette());
    for(int i = 0; i < _gap_digits.max_size(); ++i)               // made now, hidden: the race never pays for them
    {
        _gap_digits.push_back(bn::sprite_items::digits.create_sprite(0, GAP_Y, GAP_GREEN_FRAME));
        _gap_digits.back().set_visible(false);
        _gap_digits.back().set_z_order(-10);
        _gap_digit_frame[i] = GAP_GREEN_FRAME;
    }
    _ghost.set_blending_enabled(true);
    for(int i = 0; i < 2; ++i)
    {
        _sparks.push_back(bn::sprite_items::spark.create_sprite(0, 0));
        _sparks.back().set_visible(false);
    }
    _marker.set_visible(false);
    _marker.set_z_order(PLAYER_LAYER);
    // the effects sit under the player in its layer, sorted there once (put_below re-sorts: never per frame)
    _flame.set_visible(false);
    _flame.set_z_order(PLAYER_LAYER);
    _flame.put_below();
    for(int i = 0; i < max_puffs; ++i)
    {
        _puff_sprites.push_back(bn::sprite_items::puff.create_sprite(0, 0));
        _puff_sprites.back().set_visible(false);
        _puff_sprites.back().set_z_order(PLAYER_LAYER);
        _puff_sprites.back().put_below();
    }
    _text.set_z_order(-10);
    for(int i = 0; i < int(bn::display::height()); ++i)
    {
        _pa[i] = 0;
        _pc[i] = 0;
        _dx[i] = -(1 << 22);
        _dy[i] = -(1 << 22);
    }
    // Draw the title once and let it reach VRAM before the first game step: the track's 32 KB and the title's
    // sprites take more than one frame to upload, and the rules must step every frame from step 1.
    update(nullptr);
    bn::core::update();
}

void view::_set_fade(int level)
{
    if(level == _fade)
    {
        return;
    }
    _fade = level;
    if(level == 0)
    {
        bn::blending::set_fade_alpha(0);
        bn::blending::set_transparency_alpha(0.7);    // the ghost: clearly there, still see-through
        _ground.set_blending_enabled(false);
        _skyline.set_blending_enabled(false);
    }
    else
    {
        bn::blending::set_transparency_alpha(1);
        bn::blending::set_black_fade_color();
        bn::blending::set_fade_alpha(bn::fixed(level) / 16);
        _ground.set_blending_enabled(true);
        _skyline.set_blending_enabled(true);
    }
}

void view::_update_camera(int scene)
{
    int target;
    int x8;
    int y8;
    if(scene == SC_TITLE || scene == SC_HOWTO)
    {
        // an attract-mode flyover along the centre line, 2 px a frame
        static int t = 0;
        ++t;
        int f = (t >> 2) % TRACK_POINTS;
        int nxt = (f + 3) % TRACK_POINTS;
        int sub = t & 3;
        x8 = (md_points[f][0] << 8) + (md_points[(f + 1) % TRACK_POINTS][0] - md_points[f][0]) * 64 * sub;
        y8 = (md_points[f][1] << 8) + (md_points[(f + 1) % TRACK_POINTS][1] - md_points[f][1]) * 64 * sub;
        target = ac_atan2(md_points[nxt][1] - md_points[f][1], md_points[nxt][0] - md_points[f][0]);
        int d = ((target * 16 - _cam_h16) & (1024 * 16 - 1));
        if(d >= 512 * 16)
        {
            d -= 1024 * 16;
        }
        _cam_h16 = (_cam_h16 + d / 8) & (1024 * 16 - 1);
        int h = _cam_h16 >> 4;
        _cam.x = x8 - (ac_cos(uint16_t(h)) * CAM_DIST >> 6);
        _cam.y = y8 - (ac_sin(uint16_t(h)) * CAM_DIST >> 6);
        _cam.heading = h;
        _cam.sin = ac_sin(uint16_t(h));
        _cam.cos = ac_cos(uint16_t(h));
        return;
    }

    md_kart p = kart(0);
    target = p.heading;
    if(_scene != scene && (_scene == SC_TITLE || _scene == SC_HOWTO || _scene < 0))
    {
        _cam_h16 = target * 16;                    // cut from the flyover to the grid
    }
    int d = ((target * 16 - _cam_h16) & (1024 * 16 - 1));
    if(d >= 512 * 16)
    {
        d -= 1024 * 16;
    }
    _cam_h16 = (_cam_h16 + d / 5) & (1024 * 16 - 1);
    int h = _cam_h16 >> 4;
    x8 = p.x >> 8;
    y8 = p.y >> 8;
    // the camera sits CAM_DIST px behind the player along its own heading (ac_cos is Q14: * 256 / 16384 = >> 6)
    _cam.x = x8 - (ac_cos(uint16_t(h)) * CAM_DIST >> 6);
    _cam.y = y8 - (ac_sin(uint16_t(h)) * CAM_DIST >> 6);
    _cam.heading = h;
    _cam.sin = ac_sin(uint16_t(h));
    _cam.cos = ac_cos(uint16_t(h));
    // a wall hit shakes the camera across the view for SHAKE_FRAMES (a new race resets the count: no shake then)
    if(int(p.wall_hits) > _last_walls)
    {
        _shake = SHAKE_FRAMES;
    }
    _last_walls = p.wall_hits;
    if(_shake > 0)
    {
        --_shake;
        int off = (_shake & 2) ? 2 : -2;            // px; the view's right is (-sin, cos)
        _cam.x += (-_cam.sin * off) >> 6;
        _cam.y += (_cam.cos * off) >> 6;
    }
}

void view::_update_ground()
{
    ground_lines(_cam.x, _cam.y, _cam.sin, _cam.cos, _pa, _pc, _dx, _dy);
    _pa_hbe.reload_values_ref();
    _pc_hbe.reload_values_ref();
    _dx_hbe.reload_values_ref();
    _dy_hbe.reload_values_ref();
    _skyline.set_x(-_cam.heading);
}

bool view::_project(int px8, int py8, int& sx, int& sy, int& z8) const
{
    return project(_cam.x, _cam.y, _cam.sin, _cam.cos, px8, py8, sx, sy, z8);
}

void view::_draw_karts(int scene, const ac_ghost_pt* ghost)
{
    // the fades of the cards dim only the backgrounds, so the karts leave with them (pause, results)
    bool race = scene == SC_COUNTDOWN || scene == SC_RACE || scene == SC_FINISH;
    _player.set_visible(race);
    int player_z = CAM_DIST << 8;
    uint32_t look = 0;
    if(race)
    {
        md_kart p = kart(0);
        int sx = 120, sy = 80, z8;
        int t = int(rules_race_frames());
        bool racing = scene == SC_RACE;
        int speed = p.speed < 0 ? -p.speed : p.speed;
        // the drift hop: a new drift lifts the kart off the road for HOP_FRAMES
        if(p.drift != DRIFT_NONE && _last_drift == DRIFT_NONE)
        {
            _hop = 1;
        }
        _last_drift = p.drift;
        int lift = 0;
        if(_hop > 0)
        {
            lift = HOP[_hop - 1];
            _hop = _hop >= HOP_FRAMES ? 0 : _hop + 1;
        }
        // the suspension: a 1 px shake that quickens with speed; on sand or grass a rougher bounce
        _bob_phase += unsigned(speed >> 12);
        int bob = racing ? int((_bob_phase >> 7) & 1) : 0;
        if(racing && p.surface == SURF_SLOW && speed > 0x8000)
        {
            bob = (t * 7 >> 1) % 3;
        }
        if(_project(p.x >> 8, p.y >> 8, sx, sy, z8))
        {
            player_z = z8;
            // a drifting kart is drawn angled into the drift; the pose shows its wheel
            int shown = p.heading + (p.drift == DRIFT_RIGHT ? DRIFT_YAW : p.drift == DRIFT_LEFT ? -DRIFT_YAW : 0);
            int frame = kart_frame(shown, _cam.heading, p.steer);
            show_frame(_player, bn::sprite_items::kart0, frame, _kart_frame[0]);
            _player.set_position(sx - 120, sy - 80 - KART_ANCHOR - lift - bob);
            show_z(_player, PLAYER_LAYER, _kart_z[0]);
            look = uint32_t(frame) | (uint32_t(pose_of(p.steer)) << 24);
        }
        // the drift charge: sparks at the rear wheels once a release would boost, blue, then gold for the bigger one
        bool charged = p.drift != DRIFT_NONE && p.drift_charge >= DRIFT_CHARGE && racing;
        int tier = p.drift_charge >= DRIFT_CHARGE_2 ? 1 : 0;
        for(int i = 0; i < 2; ++i)
        {
            _sparks[i].set_visible(charged);
            if(charged)
            {
                int flick = ((t >> 1) + i) & 1;
                show_frame(_sparks[i], bn::sprite_items::spark, tier, _spark_frame[i]);
                _sparks[i].set_position(sx - 120 + (i ? 11 : -11), sy - 80 - 1 - flick - lift);
                show_z(_sparks[i], PLAYER_LAYER, _spark_z[i]);
            }
        }
        // puffs left behind the rear wheels: tyre smoke in a drift, sand dust off the road
        if(racing && speed > 0x8000)
        {
            int kind = -1;
            int every = 3;
            if(p.drift != DRIFT_NONE)
            {
                kind = 0;
            }
            else if(p.surface == SURF_SLOW)
            {
                kind = 1;
                every = 5;
            }
            if(kind >= 0 && t % every == 0)
            {
                puff& q = _puffs[_puff_next];
                _puff_next = (_puff_next + 1) % max_puffs;
                q.x = ((t / every) & 1) ? 10 : -10;
                q.dx = q.x > 0 ? 1 : -1;
                q.y = sy - 80 - lift;
                q.kind = kind;
                q.life = PUFF_LIFE;
            }
        }
        int puffs = 0;
        for(int i = 0; i < max_puffs; ++i)
        {
            puff& q = _puffs[i];
            bn::sprite_ptr& spr = _puff_sprites[i];
            bool show = q.life > 0;
            spr.set_visible(show);
            if(show)
            {
                int age = PUFF_LIFE - q.life;
                --q.life;
                show_frame(spr, bn::sprite_items::puff, q.kind * 2 + (age > PUFF_LIFE / 2 ? 1 : 0), _puff_frame[i]);
                spr.set_position(sx - 120 + q.x + (age >> 2) * q.dx, q.y + (age >> 1));   // left behind: down, apart
                ++puffs;
            }
        }
        // the exhaust flame while boosting
        bool flame = racing && p.boost > 0;
        _flame.set_visible(flame);
        if(flame)
        {
            show_frame(_flame, bn::sprite_items::puff, 4 + ((t >> 1) & 1), _flame_frame);
            _flame.set_position(sx - 120, sy - 80 - lift + 4);
        }
        look |= (_hop > 0 ? 1u : 0u) << 8 | uint32_t(puffs) << 12 | (flame ? 1u : 0u) << 16 | (_shake > 0 ? 1u : 0u) << 20;
        // the player's marker: a lime arrow over its helmet on the grid, just after GO and whenever a rival is close
        bool marker = scene == SC_COUNTDOWN || (scene == SC_RACE && rules_race_frames() < 180);
        for(int i = 1; i < 4 && ! marker && scene == SC_RACE; ++i)
        {
            md_kart k = kart(i);
            int dx = (k.x - p.x) >> 16;
            int dy = (k.y - p.y) >> 16;
            marker = dx * dx + dy * dy < 40 * 40;
        }
        _marker.set_visible(marker);
        _marker.set_position(0, sy - 80 - KART_ANCHOR - 20 + ((rules_scene_frames() >> 3) & 1));
    }
    else
    {
        _sparks[0].set_visible(false);
        _sparks[1].set_visible(false);
        _marker.set_visible(false);
        _flame.set_visible(false);
        for(int i = 0; i < max_puffs; ++i)
        {
            _puffs[i].life = 0;
            _puff_sprites[i].set_visible(false);
        }
        _hop = 0;
    }
    g_md_look = look;

    for(int i = 1; i < 4; ++i)
    {
        bn::sprite_ptr& spr = _rivals[i - 1];
        md_kart k = kart(i);
        int sx, sy, z8;
        bool show = race && _project(k.x >> 8, k.y >> 8, sx, sy, z8);
        spr.set_visible(show);
        if(show)
        {
            bn::fixed sc = scale_of(CAM_DIST, z8);
            int xr = sx - 120;
            int bearing = _cam.heading + ac_atan2(xr, FOCAL);
            show_frame(spr, *KART_ITEMS[i], kart_frame(k.heading, bearing, k.steer), _kart_frame[i]);
            spr.set_scale(sc);
            spr.set_position(sx - 120, bn::fixed(sy - 80) - sc * KART_ANCHOR);
            show_z(spr, layer(z8), _kart_z[i]);
        }
    }

    // the ghost: translucent, and always behind the player (the GBA blends a sprite only with the backgrounds, so a
    // ghost in front would wash the player out)
    _ghost_shown = false;
    bool ghost_scene = scene == SC_COUNTDOWN || scene == SC_RACE || scene == SC_FINISH;
    if(ghost_scene && ghost)
    {
        int sx, sy, z8;
        if(_project(int(ghost->x) << 8, int(ghost->y) << 8, sx, sy, z8))
        {
            bn::fixed sc = scale_of(CAM_DIST, z8);
            int bearing = _cam.heading + ac_atan2(sx - 120, FOCAL);
            int frame = (frame_for((ghost->angle * 1024) / 256, bearing) % GHOST_FRAMES_PER_TURN) * POSES + 1;
            show_frame(_ghost, bn::sprite_items::kart0, frame, _ghost_frame);
            _ghost.set_scale(sc);
            _ghost.set_position(sx - 120, bn::fixed(sy - 80) - sc * KART_ANCHOR);
            _ghost.set_z_order(bn::max(layer(z8), layer(player_z)));
            _ghost.put_below();
            _ghost_shown = true;
        }
    }
    _ghost.set_visible(_ghost_shown);
}

void view::_draw_props(bool show, bool orbs)
{
    // the nearest visible props, nearest first, each with a shared affine matrix per scale step
    int idx[max_props];
    int zs[max_props];
    int sxs[max_props];
    int sys[max_props];
    int n = show ? cull_props(_cam.x, _cam.y, _cam.sin, _cam.cos, orbs, max_props, idx, zs, sxs, sys) : 0;
    int levels[max_mats];
    int used_mats = 0;
    for(int k = 0; k < n; ++k)
    {
        const prop& p = props[idx[k]];
        int kind = p.kind;
        int size = kind == GANTRY_L || kind == GANTRY_M || kind == GANTRY_R ? 80 : CAM_DIST;
        // px (at scale 1) from the ground line up to the sprite's centre: palms and the gantry stand on the ground
        // (the gantry's frames are 64 tall, its banner on top), orbs hover
        int anchor = kind == PALM ? 30 : kind == ORB ? 20 : kind == BILLBOARD ? 15 : 32;
        bn::fixed sc = scale_of(size, zs[k]);
        int level = bn::max(1, (sc * 32).round_integer());
        int m = 0;
        while(m < used_mats && levels[m] != level)
        {
            ++m;
        }
        if(m == used_mats)
        {
            if(m == _mats.size())
            {
                _mats.push_back(bn::sprite_affine_mat_ptr::create());
            }
            _mats[m].set_scale(bn::fixed(level) / 32);
            levels[m] = level;
            ++used_mats;
        }
        const bn::sprite_item* item = kind == PALM ? &bn::sprite_items::palm :
                kind == BILLBOARD ? &bn::sprite_items::billboard :
                kind == ORB ? &bn::sprite_items::orb : &bn::sprite_items::gantry;
        int frame = kind == GANTRY_L ? 0 : kind == GANTRY_M ? 1 : kind == GANTRY_R ? 2 :
                kind == ORB ? int((rules_scene_frames() >> 3) & 1) : 0;
        bn::fixed y = bn::fixed(sys[k] - 80) - bn::fixed(level) / 32 * anchor;
        int look = kind * 4 + frame;
        if(k == _props.size())
        {
            _props.push_back(item->create_sprite(sxs[k] - 120, y, frame));
            _prop_look[k] = look;
            _prop_mat[k] = -1;
            _prop_layer[k] = -1;
        }
        else
        {
            if(_prop_look[k] != look)
            {
                if(_prop_look[k] / 4 == kind || (_prop_look[k] / 4 >= GANTRY_L && _prop_look[k] / 4 <= GANTRY_R &&
                                                 kind >= GANTRY_L && kind <= GANTRY_R))
                {
                    _props[k].set_tiles(item->tiles_item(), frame);
                }
                else
                {
                    _props[k].set_item(*item, frame);
                }
                _prop_look[k] = look;
            }
            _props[k].set_position(sxs[k] - 120, y);
        }
        bn::sprite_ptr& spr = _props[k];
        if(_prop_mat[k] != m)
        {
            spr.set_affine_mat(_mats[m]);
            _prop_mat[k] = m;
        }
        int lay = layer(zs[k]);
        if(_prop_layer[k] != lay)
        {
            spr.set_z_order(lay);
            _prop_layer[k] = lay;
        }
        if(! spr.visible())
        {
            spr.set_visible(true);
        }
    }
    for(int k = n; k < _props.size(); ++k)
    {
        if(_props[k].visible())
        {
            _props[k].set_visible(false);
        }
    }
}

bool view::_draw_big(int scene)
{
    // key: what the big sprites show (logo, a countdown digit, a banner)
    int key = -1;
    if(scene == SC_TITLE)
    {
        key = 100;
    }
    else if(scene == SC_COUNTDOWN)
    {
        key = 200 + (COUNTDOWN_FRAMES - rules_countdown()) / 60;
    }
    else if(scene == SC_RACE && rules_race_frames() < 45)
    {
        key = 203;
    }
    else if(scene == SC_RACE && _banner > 0)
    {
        key = 300;
    }
    else if(scene == SC_FINISH)
    {
        key = 301;
    }
    else if(scene == SC_RESULTS && rules_finished() && arcade::best_is_new())
    {
        key = 302;
    }
    if(key == _big_key)
    {
        return false;
    }
    _big_key = key;
    _big.clear();
    if(key == 100)
    {
        for(int i = 0; i < 6; ++i)
        {
            _big.push_back(bn::sprite_items::logo.create_sprite(-64 + 64 * (i % 3), -52 + 32 * (i / 3), i));
        }
    }
    else if(key >= 200 && key < 300)
    {
        _big.push_back(bn::sprite_items::count.create_sprite(0, -24, key - 200));
    }
    else if(key >= 300)
    {
        int f = (key - 300) * 2;
        int y = key == 302 ? -22 : -24;
        _big.push_back(bn::sprite_items::banner.create_sprite(-32, y, f));
        _big.push_back(bn::sprite_items::banner.create_sprite(32, y, f + 1));
    }
    for(bn::sprite_ptr& s : _big)
    {
        s.set_z_order(-20);
    }
    return true;
}

void view::_say(int x, int y, const bn::string_view& text)
{
    if(! _pending.full())
    {
        _pending.push_back(pending_line{ x, y, _align, _blink_next, bn::string<40>(text) });
        _blink_next = false;
    }
}

void view::_draw_text(int scene, bool busy)
{
    bool blink = (rules_scene_frames() >> 5) & 1;
    int placement = rules_placement();
    md_kart p = kart(0);
    int lap = bn::min(int(p.lap), LAPS);
    int key = scene * 1000;
    if(scene == SC_RACE || scene == SC_COUNTDOWN)
    {
        key += bn::max(lap, 1) * 10 + (_lap_flash > 0 ? 1 : 0);
    }
    else if(scene == SC_PAUSE)
    {
        key += rules_paused_from();
    }
    if(key != _text_key && ! busy)                   // on a frame that built the big sprites, the card waits a frame
    {
        busy = true;
        _text_key = key;
        _words.clear();
        _blink.clear();
        _pending.clear();
        _align = 1;
        if(scene == SC_TITLE)
        {
            _say(0, 6, "3 laps of Marine Drive, Mumbai");
            _blink_next = true;
            _say(0, 26, "PRESS START");
            if(arcade::best_time_frames())
            {
                bn::string<32> b("Best ");
                b.append(time_text(arcade::best_time_frames(), true));
                _say(0, 44, b);
            }
            const char* name = arcade::profile_name();
            if(name[0])
            {
                bn::string<32> who("Driver ");
                who.append(name);
                _say(0, 58, who);
            }
            if(arcade::has_ghost())
            {
                _say(0, 70, "Ghost loaded");
            }
        }
        else if(scene == SC_HOWTO)
        {
            _say(0, -66, "HOW TO RACE");
            _align = 0;
            const char* keys[] = { "A", "B", "D-PAD", "R + steer", "", "World orbs", "START" };
            const char* what[] = { "accelerate", "brake, reverse", "steer", "drift; let go of R", "for a boost",
                                   "boost pads", "pause" };
            int y = -46;
            for(int i = 0; i < 7; ++i)
            {
                _say(-100, y, keys[i]);
                _say(-24, y, what[i]);
                y += 12;
            }
            _align = 1;
            _say(0, 42, "3 laps. Beat the 3 rivals.");
            _say(0, 62, "A or START: to the grid");
        }
        else if(scene == SC_RACE || scene == SC_COUNTDOWN)
        {
            _align = 0;
            bn::string<16> l("LAP ");
            l.append(bn::to_string<4>(bn::max(lap, 1)));
            l.append("/3");
            _say(-114, -72, l);
            if(_lap_flash > 0 && lap >= 2)
            {
                _align = 1;
                bn::string<32> t("LAP ");
                t.append(bn::to_string<4>(lap - 1));
                t.append("  ");
                t.append(time_text(rules_lap_frames(lap - 1), true));
                _say(0, -58, t);
            }
        }
        else if(scene == SC_PAUSE)
        {
            _say(0, -20, "PAUSED");
            _say(0, 4, "START  resume");
            _say(0, 18, "SELECT  retire");
        }
        else if(scene == SC_RESULTS)
        {
            ac_result r;
            game_result(&r);
            if(! r.finished)
            {
                _say(0, -60, "RETIRED");
            }
            else
            {
                bn::string<32> t("TIME ");
                t.append(time_text(r.time_frames, true));
                _say(0, -2, t);
                if(! arcade::best_is_new() && arcade::best_time_frames())
                {
                    bn::string<32> b("BEST ");
                    b.append(time_text(arcade::best_time_frames(), true));
                    _say(0, -20, b);
                }
                bn::string<48> laps("Laps ");
                for(int i = 1; i <= LAPS; ++i)
                {
                    uint32_t f = rules_lap_frames(i);
                    bn::string<16> s = bn::to_string<8>(int(f / 60));
                    s.push_back('.');
                    uint32_t h = (f % 60) * 100 / 60;
                    s.push_back(char('0' + h / 10));
                    s.push_back(char('0' + h % 10));
                    laps.append(s);
                    if(i < LAPS)
                    {
                        laps.append("  ");
                    }
                }
                _say(0, 10, laps);
            }
            int y = 26;
            for(int i = 0; i < GAME_INFO.n_trophies; ++i)
            {
                if(r.trophies & (1u << i))
                {
                    bn::string<48> t("* ");
                    t.append(GAME_INFO.trophy_names[i]);
                    _say(0, y, t);
                    y += 11;
                }
            }
            _say(0, 72, "START");
        }
    }

    // queued card text: at most one line a frame, and none on a frame that already cleared the card or built the
    // big sprites (generating text sprites is slow; a lap crossing does all three at once and would drop a frame)
    for(int n = 0; n < 1 && ! busy && ! _pending.empty(); ++n)
    {
        const pending_line& l = _pending.front();
        if(l.align)
        {
            _text.set_center_alignment();
        }
        else
        {
            _text.set_left_alignment();
        }
        if(l.blink)
        {
            _text.generate(l.x, l.y, l.text, _blink);
        }
        else
        {
            _text.generate(l.x, l.y, l.text, _words);
        }
        _pending.erase(_pending.begin());
    }
    for(bn::sprite_ptr& spr : _blink)
    {
        spr.set_visible(! blink);
    }

    // the clock, the place badge and the speed bar in the race
    bool hud = scene == SC_RACE || scene == SC_COUNTDOWN || scene == SC_FINISH;
    {
        // the race clock: one digit sprite per character, re-tiled only when that character changes
        bn::string<16> t;
        if(hud)
        {
            t = time_text(scene == SC_FINISH ? p.finish_frame : rules_race_frames(), scene == SC_FINISH);
        }
        int width = t.size() * 7;
        for(int i = 0; i < _clock.max_size(); ++i)
        {
            if(i >= t.size())
            {
                if(i < _clock.size())
                {
                    _clock[i].set_visible(false);
                }
                continue;
            }
            char ch = t[i];
            int frame = ch == ':' ? 10 : ch == '.' ? 11 : ch - '0';
            int x = -width / 2 + i * 7 + 3;
            if(i == _clock.size())
            {
                _clock.push_back(bn::sprite_items::digits.create_sprite(x, -70, frame));
                _clock.back().set_z_order(-10);
                _clock_frame[i] = frame;
            }
            show_frame(_clock[i], bn::sprite_items::digits, frame, _clock_frame[i]);
            _clock[i].set_position(x, -70);
            _clock[i].set_visible(true);
        }
    }

    bool badge = hud || scene == SC_RESULTS;
    if(badge)
    {
        int frame = bn::max(0, bn::min(3, placement - 1));
        if(! _place)
        {
            _place = bn::sprite_items::place.create_sprite(0, 0, frame);
            _place->set_z_order(-10);
        }
        show_frame(*_place, bn::sprite_items::place, frame, _place_frame);
        if(scene == SC_RESULTS)
        {
            _place->set_scale(2);
            _place->set_position(0, -54);
            _place->set_visible(rules_finished());
        }
        else
        {
            _place->remove_affine_mat();
            _place->set_position(98, -70);
            _place->set_visible(true);
        }
    }
    else if(_place)
    {
        _place->set_visible(false);
    }

    if(scene == SC_RACE || scene == SC_COUNTDOWN)
    {
        int level = bn::max(0, bn::min(8, int((int64_t(p.speed) * 8 + TOP_ROAD / 2) / TOP_ROAD)));
        if(p.boost)
        {
            level = 8;
        }
        if(! _speed)
        {
            _speed = bn::sprite_items::speed.create_sprite(-96, 70, level);
            _speed->set_z_order(-10);
        }
        show_frame(*_speed, bn::sprite_items::speed, level, _speed_frame);
        _speed->set_visible(true);
    }
    else if(_speed)
    {
        _speed->set_visible(false);
    }
}

void view::_track_gap(int scene)
{
    if(scene == SC_TITLE || scene == SC_HOWTO || scene == SC_COUNTDOWN || ! arcade::has_ghost())
    {
        _gap_k = 0;
        _gap_on = false;
        return;
    }
    if(scene != SC_RACE)
    {
        return;                                      // paused or past the line: the last gap stays
    }

    int s = int(arcade::steps());
    md_kart p = kart(0);
    int px = int(p.x >> 16);
    int py = int(p.y >> 16);
    if(_gap_k == 0)
    {
        _gap_k = s;                                  // the race starts with the ghost's: both countdowns are as long
    }

    // from the step after the last match, climb while a neighbour is nearer: forward first, else back, at most
    // GAP_WINDOW steps (each look is an interpolated ghost_at, slow enough to count). A tie stays put, so a ghost
    // that has stopped past its finish never drags the match backwards.
    auto dist = [px, py](int k, int& d)
    {
        ac_ghost_pt g;
        if(k <= 0 || ! arcade::ghost_at(uint32_t(k), g))
        {
            return false;
        }
        int dx = int(g.x) - px;
        int dy = int(g.y) - py;
        d = dx * dx + dy * dy;
        return true;
    };
    int k = _gap_k + 1;
    int d;
    if(dist(k, d))
    {
        for(int dir = 1; dir >= -1; dir -= 2)
        {
            int moved = 0;
            int nd;
            while(moved < GAP_WINDOW && dist(k + dir, nd) && nd < d)
            {
                k += dir;
                d = nd;
                ++moved;
            }
            if(moved)
            {
                break;                               // climbed one way: the other is uphill
            }
        }
        _gap_k = k;
    }
    _gap = s - _gap_k;
    _gap_on = rules_race_frames() >= GAP_FROM;
}

void view::_draw_gap(int scene)
{
    bool show = _gap_on && (scene == SC_RACE || scene == SC_FINISH);
    g_md_gap = show ? uint32_t(_gap) : NO_GAP;
    if(! show)
    {
        for(bn::sprite_ptr& spr : _gap_digits)
        {
            spr.set_visible(false);
        }
        _gap_key = -1;
        return;
    }

    bool behind = _gap > 0;
    int tenths = ((behind ? _gap : -_gap) * 10 + 30) / 60;
    int key = tenths * 2 + (behind ? 1 : 0);
    if(key == _gap_key || (_gap_key >= 0 && (arcade::steps() % GAP_REDRAW) != 0))
    {
        return;
    }
    _gap_key = key;

    bn::string<8> t;
    t.push_back(behind ? '+' : '-');
    t.append(bn::to_string<6>(tenths / 10));
    t.push_back('.');
    t.push_back(char('0' + tenths % 10));
    int n = t.size();
    for(int i = 0; i < _gap_digits.size(); ++i)
    {
        if(i >= n)
        {
            _gap_digits[i].set_visible(false);
            continue;
        }
        int x = GAP_RIGHT - (n - 1 - i) * 7;
        show_frame(_gap_digits[i], bn::sprite_items::digits, gap_frame(t[i], behind), _gap_digit_frame[i]);
        _gap_digits[i].set_position(x, GAP_Y);
        _gap_digits[i].set_visible(true);
    }
}

void view::update(const ac_ghost_pt* ghost)
{
    g_md_cpu = uint32_t((bn::core::last_cpu_usage() * 1000).round_integer());
    int scene = rules_scene();
    uint8_t ev = rules_events();
    if(ev & EV_FINAL_LAP)
    {
        _banner = 120;
    }
    else if(_banner > 0 && scene == SC_RACE)
    {
        --_banner;
    }
    if(ev & EV_LAP)
    {
        _lap_flash = 150;
    }
    else if(_lap_flash > 0 && scene == SC_RACE)
    {
        --_lap_flash;
    }

    // WRONG WAY: the player's progress has fallen for a second while it is moving
    if(scene == SC_RACE)
    {
        md_kart p = kart(0);
        if(p.progress < _last_progress && (p.speed > 0x4000 || p.speed < -0x4000))
        {
            _backwards = bn::min(_backwards + 1, 600);
        }
        else if(p.progress > _last_progress)
        {
            _backwards = 0;
        }
        _last_progress = p.progress;
    }
    else
    {
        _backwards = 0;
    }
    bool warn = _backwards > 60 && ((rules_scene_frames() >> 4) & 1);
    if(warn && _warn.empty())
    {
        _text.set_center_alignment();
        _text.generate(0, 20, "WRONG WAY", _warn);
    }
    for(bn::sprite_ptr& spr : _warn)
    {
        spr.set_visible(warn);
    }

    int draw_scene = scene == SC_PAUSE ? rules_paused_from() : scene;
    if(scene != SC_PAUSE && scene != SC_RESULTS)
    {
        _update_camera(draw_scene);
        _update_ground();
    }
    else if(_scene < 0)
    {
        _update_camera(draw_scene);
        _update_ground();
    }
    _set_fade(scene == SC_TITLE ? 6 : scene == SC_HOWTO ? 10 : scene == SC_PAUSE ? 9 : scene == SC_RESULTS ? 11 : 0);
    _draw_karts(scene, ghost);
    _draw_props(scene != SC_HOWTO && scene != SC_RESULTS && scene != SC_PAUSE, scene != SC_TITLE);
    bool built = _draw_big(scene);
    _draw_text(scene, built);
    _track_gap(scene);
    _draw_gap(scene);
    _scene = scene;
}

}

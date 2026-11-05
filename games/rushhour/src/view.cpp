#include "view.h"

#include "bn_bg_palettes.h"
#include "bn_blending.h"
#include "bn_color.h"
#include "bn_math.h"
#include "bn_regular_bg_items_level_bg.h"
#include "bn_regular_bg_items_skyline.h"
#include "bn_sprite_items_bug.h"
#include "bn_sprite_items_chai.h"
#include "bn_sprite_items_door.h"
#include "bn_sprite_items_flag.h"
#include "bn_sprite_items_glow.h"
#include "bn_sprite_items_hero.h"
#include "bn_sprite_items_orb.h"
#include "bn_sprite_items_shelf.h"

#include "arcade_runtime.h"
#include "common_variable_8x8_sprite_font.h"

extern "C" {
#include "game.h"
#include "tuning.h"
}

// Read by the view tests at its ELF symbol address: the camera's top-left in level pixels, (x << 16) | y as u16s.
extern "C" {
volatile uint32_t g_dbg_camera_xy;
}

namespace game
{

namespace
{
    constexpr int screen_w = 240;
    constexpr int screen_h = 160;
    constexpr int sprite_priority = 1;              // over the level map (2) and the skyline (3)
    constexpr int sky_above = 48;                   // the camera may rise this far above the level's top

    enum { HERO_IDLE = 0, HERO_RUN = 1, HERO_JUMP = 2, HERO_FALL = 3, HERO_DEAD = 4 };

    int level_w() { return rules_level_w() * TILE; }
    int level_h() { return rules_level_h() * TILE; }
    int bg_w() { return (level_w() + 255) / 256 * 256; }

    int hero_frame(int pose, int tick, bool fast)
    {
        switch(pose)
        {
        case POSE_RUN: return (tick / (fast ? 5 : 8)) % 2 ? HERO_RUN : HERO_IDLE;
        case POSE_JUMP: return HERO_JUMP;
        case POSE_FALL: return HERO_FALL;
        case POSE_HURT: return HERO_FALL;
        case POSE_DEAD: return HERO_DEAD;
        default: return HERO_IDLE;
        }
    }

    bn::sprite_ptr make(const bn::sprite_item& item, int frame, int z = 0)
    {
        bn::sprite_ptr s = item.create_sprite(0, 0, frame);
        s.set_bg_priority(sprite_priority);
        s.set_z_order(z);
        return s;
    }
}

// ---- the world ---------------------------------------------------------------------------------------------------

world::world() :
    _level(bn::regular_bg_items::level_bg.create_bg(0, 0)),
    _skyline(bn::regular_bg_items::skyline.create_bg(0, 0)),
    _hero(make(bn::sprite_items::hero, 0)),
    _ghost(make(bn::sprite_items::hero, 0, 1)),
    _glow(make(bn::sprite_items::glow, 0, -1)),
    _flag(make(bn::sprite_items::flag, 0))
{
    _level.set_priority(2);
    _skyline.set_priority(3);
    _ghost.set_blending_enabled(true);               // half transparent: blends with the backgrounds
    _ghost.set_visible(false);
    _glow.set_visible(false);
    _flag.set_visible(false);
    bn::blending::set_transparency_alpha(0.5);
    for(int i = 0, n = rules_ent_count(); i < n && i < _ents.max_size(); ++i)
    {
        _ents.emplace_back();
    }
    _move_camera(true);
}

void world::_move_camera(bool snap)
{
    int px = rules_px() + PLAYER_W / 2;
    int py = rules_py() + PLAYER_H / 2;
    int face = rules_facing_left() ? -1 : 1;
    int fast = rules_vx() > 0x0100 || rules_vx() < -0x0100;
    int look = face * (fast ? 40 : 20);
    if(snap)
    {
        _look = look;
    }
    else if(_look < look)
    {
        _look += 1;
    }
    else if(_look > look)
    {
        _look -= 1;
    }
    int tx = bn::clamp(px - screen_w / 2 + _look, 0, level_w() - screen_w);
    if(snap)
    {
        _cam_x = tx;
    }
    else
    {
        int d = tx - _cam_x;
        int step = d / 6;
        if(step == 0 && d != 0)
        {
            step = d > 0 ? 1 : -1;
        }
        _cam_x += step;
    }
    int sy = py - _cam_y;
    if(snap || sy < 40)
    {
        _cam_y = py - 40;
    }
    if(sy > 104)
    {
        _cam_y = py - 104;
    }
    // Never above the level's top while the hero is inside the level (the landing zone stays in view); open sky
    // above it only while the hero is above row 0.
    int top = rules_py() < 0 ? bn::max(-sky_above, rules_py() - 24) : 0;
    _cam_y = bn::clamp(_cam_y, top, level_h() - screen_h);
    g_dbg_camera_xy = (uint32_t(uint16_t(_cam_x)) << 16) | uint16_t(_cam_y);

    _level.set_position(bg_w() / 2 - _cam_x - screen_w / 2, 128 - _cam_y - screen_h / 2);
    _skyline.set_position(136 - (_cam_x / 4) % 512, -2 - _cam_y / 2);
}

void world::_place(bn::sprite_ptr& sprite, int cx, int cy)
{
    sprite.set_position(cx - _cam_x - screen_w / 2, cy - _cam_y - screen_h / 2);
}

void world::_draw_hero(int tick)
{
    int pose = rules_pose();
    bool fast = rules_vx() > 0x0200 || rules_vx() < -0x0200;
    int cx = rules_px() + PLAYER_W / 2;
    int cy = rules_py() + 2;                        // the character's feet on the hitbox's bottom row
    if(pose == POSE_DEAD)
    {
        int t = DEATH_FRAMES - rules_dead();       // hop up, then fall off
        cy += t * t / 12 - 3 * t;
    }
    _hero.set_tiles(bn::sprite_items::hero.tiles_item(), hero_frame(pose, tick, fast));
    _hero.set_horizontal_flip(rules_facing_left());
    _place(_hero, cx, cy);
    bool blink = rules_invuln() && pose != POSE_DEAD && (tick & 4);
    _hero.set_visible(! blink);
    _glow.set_visible(rules_shield() && ! rules_dead());
    if(rules_shield())
    {
        _glow.set_tiles(bn::sprite_items::glow.tiles_item(), (tick / 8) % 2);
        _place(_glow, cx, cy);
    }
}

void world::_draw_ghost(const ac_ghost_pt* ghost, bool show, int tick)
{
    _ghost_shown = false;
    if(show && ghost)
    {
        int cx = ghost->x + PLAYER_W / 2;
        int cy = ghost->y + 2;
        int sx = cx - _cam_x;
        int sy = cy - _cam_y;
        _ghost_shown = sx > -24 && sx < screen_w + 24 && sy > -24 && sy < screen_h + 24;
        if(_ghost_shown)
        {
            _ghost.set_tiles(bn::sprite_items::hero.tiles_item(),
                             hero_frame((ghost->angle >> 1) & 7, tick, (ghost->angle & 0x10) != 0));
            _ghost.set_horizontal_flip(ghost->angle & 1);
            _place(_ghost, cx, cy);
            // Butano reinserts a sprite into its layer on a tiles change and puts it in front: send the ghost
            // behind the hero every frame, or the hero (the GBA blends a sprite only with the backgrounds, and
            // only the front sprite pixel is drawn) would look half transparent where they overlap.
            _ghost.put_below();
        }
    }
    _ghost.set_visible(_ghost_shown);
}

void world::_draw_entities(int tick)
{
    bool door_seen = false;
    int created = 0;                                // new sprites this frame (at most 2: creating one is slow)
    for(int i = 0; i < _ents.size(); ++i)
    {
        bn::optional<bn::sprite_ptr>& slot = _ents[i];
        int type = rules_ent_type(i);
        int state = rules_ent_state(i);
        int ex = rules_ent_x(i);
        int ey = rules_ent_y(i);
        bool near = ex > _cam_x - 48 && ex < _cam_x + screen_w + 48;
        if(state == ES_GONE || ! near)
        {
            if(slot && state == ES_GONE && (type == E_CHAI || type == E_ORB) && ! _pops.full())
            {
                _pops.push_back(pop{ bn::move(*slot), ex + 6, ey + 5, 0 });
            }
            slot.reset();
            continue;
        }
        const bn::sprite_item* item = nullptr;
        int frame = 0, cx = ex, cy = ey;
        switch(type)
        {
        case E_BUG:
            item = &bn::sprite_items::bug;
            frame = state == ES_SQUASHED ? 2 : (tick / 8 + i) % 2;
            cx = ex + BUG_W / 2;
            cy = ey;
            break;
        case E_CHAI:
            item = &bn::sprite_items::chai;
            frame = (tick / 8 + i) % 4;
            cx = ex + 5;
            cy = ey + 5 - ((tick / 16 + i) % 2);
            break;
        case E_ORB:
            item = &bn::sprite_items::orb;
            frame = (tick / 6) % 4;
            cx = ex + 6;
            cy = ey + 6 - ((tick / 12) % 2);
            break;
        case E_CHECK:
            item = &bn::sprite_items::shelf;
            frame = state == ES_ON ? 1 + (tick / 16) % 2 : 0;
            cx = ex + 6;
            cy = ey + 16;
            break;
        default:
            item = &bn::sprite_items::door;
            cx = ex + 16;
            cy = ey;
            door_seen = true;
            _flag.set_tiles(bn::sprite_items::flag.tiles_item(), (tick / 12) % 2);
            _place(_flag, ex + 38, ey - 24);
            break;
        }
        if(! slot)
        {
            if(created == 2)
            {
                continue;                           // next frame (it is still off screen, in the 48 px margin)
            }
            ++created;
            slot = make(*item, frame);
        }
        else
        {
            slot->set_tiles(item->tiles_item(), frame);
        }
        if(type == E_BUG)
        {
            slot->set_horizontal_flip(rules_ent_dir(i) > 0);
        }
        _place(*slot, cx, cy);
    }
    _flag.set_visible(door_seen);
}

void world::_draw_pops(int tick)
{
    for(int i = 0; i < _pops.size();)
    {
        pop& p = _pops[i];
        ++p.t;
        if(p.t > 24)
        {
            _pops.erase(_pops.begin() + i);
            continue;
        }
        _place(p.sprite, p.x, p.y - p.t);
        p.sprite.set_visible(p.t < 12 || (tick & 2));
        ++i;
    }
}

void world::update(int tick, const ac_ghost_pt* ghost, bool show_ghost)
{
    _move_camera(false);
    _draw_entities(tick);
    _draw_pops(tick);
    _draw_hero(tick);
    _draw_ghost(ghost, show_ghost, tick);
}

// ---- the view ----------------------------------------------------------------------------------------------------

view::view() :
    _text(common::variable_8x8_sprite_font),
    _cards(_text)
{
    _text.set_bg_priority(0);
    bn::bg_palettes::set_transparent_color(bn::color(15, 23, 29));    // the morning sky behind everything
}

void view::update(const ac_ghost_pt* ghost)
{
    int scene = rules_scene();
    ++_tick;
    bool world_on = scene == SC_PLAY || scene == SC_PAUSE || scene == SC_RESULTS;
    bool hud_on = scene == SC_PLAY || scene == SC_PAUSE;
    _cards.update(scene, _tick);                    // first: the title's palettes go before the level's arrive
    if(! world_on)
    {
        _world.reset();
    }
    else if(! _world)
    {
        _world.emplace();
    }
    if(! hud_on)
    {
        _hud.reset();
    }
    else if(! _hud)
    {
        _hud.emplace(_text);
    }
    if(_world)
    {
        _world->update(_tick, ghost, scene == SC_PLAY || scene == SC_PAUSE);
    }
    if(_hud)
    {
        _hud->update(_tick);
    }
    bn::bg_palettes::set_fade(bn::color(0, 0, 0), scene == SC_PAUSE ? bn::fixed(0.6) : bn::fixed(0));
}

}

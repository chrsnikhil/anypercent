#include "view.h"

#include "bn_bg_palettes.h"
#include "bn_blending.h"
#include "bn_color.h"
#include "bn_core.h"
#include "bn_sprite_palette_item.h"
#include "bn_string.h"

#include "arcade_runtime.h"
#include "common_variable_8x8_sprite_font.h"
#include "common_variable_8x16_sprite_font.h"
#include "bn_regular_bg_items_hall.h"
#include "bn_regular_bg_items_level.h"
#include "bn_regular_bg_items_panel.h"
#include "bn_regular_bg_items_title.h"
#include "bn_sprite_items_booster.h"
#include "bn_sprite_items_bug.h"
#include "bn_sprite_items_icons.h"
#include "bn_sprite_items_packet.h"
#include "bn_sprite_items_rack.h"
#include "bn_sprite_items_spring.h"
#include "bn_sprite_items_trail.h"
#include "bn_sprite_items_zip.h"

extern "C" {
#include "game.h"
#include "tuning.h"
#include "zip_level.h"
#include "zip_world.h"
}

// Read by the headless tests at its ELF symbol address: the camera's top-left in the level, (x << 16) | y.
extern "C" {
volatile uint32_t g_dbg_cam_xy;
volatile uint32_t g_dbg_cpu;       // the previous frame's CPU use, in 1/1000 of a frame (bn::core::last_cpu_usage)
}

namespace game
{

namespace
{
    // Zip's frames (tools/art/build_art.py ZIP_FRAMES)
    enum { F_STAND = 0, F_BLINK = 1, F_WALK = 2, F_RUN = 6, F_DASH = 10, F_ROLL = 14, F_SPRING = 18, F_HURT = 19,
           F_FALL = 20 };

    constexpr int screen_w = 240;
    constexpr int screen_h = 160;

    // frames -> "M:SS.hh" (at most 99:59.99: a save from elsewhere may hold any number)
    bn::string<16> time_text(uint32_t frames, bool hundredths)
    {
        constexpr uint32_t cap = (100u * 60u - 1u) * 60u + 59u;
        frames = frames > cap ? cap : frames;
        uint32_t secs = frames / 60;
        bn::string<16> s = bn::to_string<8>(int(secs / 60));
        s.push_back(':');
        s.push_back(char('0' + (secs % 60) / 10));
        s.push_back(char('0' + secs % 10));
        if(hundredths)
        {
            uint32_t h = (frames % 60) * 100 / 60;
            s.push_back('.');
            s.push_back(char('0' + h / 10));
            s.push_back(char('0' + h % 10));
        }
        return s;
    }

    int iabs(int v) { return v < 0 ? -v : v; }

    // A rules angle (0-255 per turn, rising to the right positive) as Butano degrees.
    bn::fixed degrees(int angle)
    {
        return bn::fixed(((angle & 255) * 360) / 256);
    }

    int first_ent_from(const zip_level* lv, int x)
    {
        int lo = 0, hi = lv->n_ents;
        while(lo < hi)
        {
            int mid = (lo + hi) / 2;
            if(lv->ents[mid].x < x) { lo = mid + 1; } else { hi = mid; }
        }
        return lo;
    }

    // The ghost's palette: Zip's sheet recoloured by brightness (index 0, transparent, kept) from a dusk violet to a
    // near white, so on the dark hall the ghost reads as a pale spirit, never as a dimmer copy of cyan Zip (as
    // Marine Drive GP's pale cyan kart). Worked out once, when the view is made: one extra sprite palette.
    bn::color ghost_colors[16];

    bn::sprite_palette_item ghost_palette()
    {
        static const int base[3] = {12, 12, 18}, span[3] = {28, 28, 22}; // per channel: dark -> base, bright -> +span
        const bn::span<const bn::color>& in = bn::sprite_items::zip.palette_item().colors_ref();
        for(int i = 0; i < 16; ++i)
        {
            bn::color c = i < in.size() ? in[i] : bn::color();
            if(i > 0)
            {
                int lum = (c.red() * 5 + c.green() * 9 + c.blue() * 2) / 16;
                c = bn::color(bn::min(31, base[0] + lum * span[0] / 31), bn::min(31, base[1] + lum * span[1] / 31),
                              bn::min(31, base[2] + lum * span[2] / 31));
            }
            ghost_colors[i] = c;
        }
        return bn::sprite_palette_item(bn::span<const bn::color>(ghost_colors, 16), bn::bpp_mode::BPP_4);
    }
}

view::view() :
    _small(common::variable_8x8_sprite_font),
    _big(common::variable_8x16_sprite_font),
    _camera(bn::camera_ptr::create(120, 80)),
    _zip(bn::sprite_items::zip.create_sprite(0, 0, F_STAND)),
    _trail(bn::sprite_items::trail.create_sprite(0, 0, 0)),
    _ghost(bn::sprite_items::zip.create_sprite(0, 0, F_RUN + 1))
{
    bn::bg_palettes::set_transparent_color(bn::color(2, 2, 5));
    bn::blending::set_transparency_alpha(0.5);
    _small.set_bg_priority(0);
    _big.set_bg_priority(0);
    for(bn::sprite_ptr* s : { &_zip, &_trail, &_ghost })
    {
        s->set_camera(_camera);
        s->set_bg_priority(1);
        s->set_visible(false);
    }
    _trail.set_blending_enabled(true);
    _trail.set_z_order(2);
    _ghost.set_palette(ghost_palette());
    _ghost.set_blending_enabled(true);
    _ghost.set_z_order(1);
    _zip.set_z_order(0);
}

// ---- scenes -------------------------------------------------------------------------------------------------------

void view::_say(int x, int y, const char* text, bool big, bool centre)
{
    if(_queue.full())
    {
        return;
    }
    line l;
    l.text = text;
    l.x = int16_t(x);
    l.y = int16_t(y);
    l.big = big;
    l.align = centre;
    _queue.push_back(l);
}

void view::_flush_queue(int lines)
{
    int done = 0;
    while(done < lines && ! _queue.empty())
    {
        const line& l = _queue.front();
        bn::sprite_text_generator& gen = l.big ? _big : _small;
        if(l.align)
        {
            gen.set_center_alignment();
        }
        else
        {
            gen.set_left_alignment();
        }
        gen.generate(l.x, l.y, l.text, _words);
        _queue.erase(_queue.begin());
        ++done;
    }
}

void view::_show_card(int kind)
{
    if(kind == _card_kind)
    {
        return;
    }
    _card.reset();
    if(kind == 0)
    {
        _card = bn::regular_bg_items::title.create_bg(8, 48);          // the 256 x 256 card, top-left on the screen
    }
    else if(kind == 1)
    {
        _card = bn::regular_bg_items::panel.create_bg(8, 48);
    }
    if(_card)
    {
        _card->set_priority(3);
    }
    _card_kind = kind;
}

void view::_show_level(bool on)
{
    if(on && ! _level)
    {
        const zip_level* lv = zip_level_current();
        int w = lv->w * 16, h = lv->h * 16;
        _level = bn::regular_bg_items::level.create_bg(w / 2, h / 2);
        _level->set_camera(_camera);
        _level->set_priority(2);
        _hall = bn::regular_bg_items::hall.create_bg(0, 0);
        _hall->set_priority(3);
    }
    else if(! on && _level)
    {
        _level.reset();
        _hall.reset();
    }
}

void view::_title_text()
{
    _words.clear();
    _say(0, 38, "a packet's race to demo day", false, true);
    const char* name = arcade::profile_name();
    int y = 56;
    if(name[0])
    {
        bn::string<32> who("Player ");
        who.append(name);
        _say(0, y, who.c_str(), false, true);
        y += 10;
    }
    if(arcade::best_time_frames())
    {
        bn::string<32> b("Best ");
        b.append(time_text(arcade::best_time_frames(), true));
        if(arcade::has_ghost())
        {
            b.append("  ghost ready");
        }
        _say(0, y, b.c_str(), false, true);
    }
    else if(arcade::has_ghost())
    {
        _say(0, y, "Ghost ready", false, true);
    }
}

void view::_howto_text()
{
    _words.clear();
    _say(0, -62, "HOW TO ZIP", true, true);
    const char* lines[] = {
        "D-PAD      run (build up speed)",
        "A          jump - hold for height",
        "DOWN       roll at speed: smash bugs",
        "SPRINGS    launch you up",
        "ORB GATES  boost you to max speed",
        "HIT        you drop your packets",
        "           (none left: checkpoint)",
        "Roll down the big hill into the loop!",
    };
    int y = -38;
    for(const char* text : lines)
    {
        _say(-100, y, text, false, false);
        y += 11;
    }
    _say(0, 62, "START  go!     (START in play: pause)", false, true);
}

void view::_results_text()
{
    _words.clear();
    _icons.clear();
    ac_result r;
    game_result(&r);
    _say(0, -62, r.finished ? "DEMO DAY!" : "RUN ENDED", true, true);
    if(r.finished)
    {
        bn::string<32> t("Time ");
        t.append(time_text(r.time_frames, true));
        t.append("   Packets ");
        t.append(bn::to_string<8>(int(r.score)));
        _say(0, -38, t.c_str(), false, true);
        if(arcade::best_is_new())
        {
            _say(0, -22, "NEW BEST", true, true);
        }
        else if(arcade::best_time_frames())
        {
            bn::string<32> b("Best ");
            b.append(time_text(arcade::best_time_frames(), true));
            _say(0, -22, b.c_str(), false, true);
        }
    }
    else
    {
        _say(0, -38, "The packet never reached the screen.", false, true);
    }
    int y = 2;
    for(int i = 0; i < GAME_INFO.n_trophies; ++i)
    {
        bool got = r.trophies & (1u << i);
        bn::sprite_ptr icon = bn::sprite_items::icons.create_sprite(-72, y, got ? 2 : 3);
        icon.set_bg_priority(0);
        _icons.push_back(bn::move(icon));
        _say(-58, y - 4, GAME_INFO.trophy_names[i], false, false);
        y += 16;
    }
}

void view::_pause_text(bool on)
{
    _words.clear();
    if(on)
    {
        _say(0, -10, "PAUSED", true, true);
        _say(0, 10, "START resume   SELECT give up", false, true);
    }
}

void view::_enter_scene(int scene)
{
    _words.clear();
    _queue.clear();
    _icons.clear();
    _banner.clear();
    _banner_on = false;
    switch(scene)
    {
    case SC_TITLE:
        _show_level(false);
        _show_card(0);
        _title_text();
        break;
    case SC_HOWTO:
        _show_level(false);
        _show_card(1);
        _howto_text();
        break;
    case SC_PLAY:
        _show_card(-1);
        _show_level(true);
        if(_scene != SC_PAUSE)
        {
            _update_camera(true);
        }
        break;
    case SC_PAUSE:
        _pause_text(true);
        break;
    default:
        _show_level(false);
        _show_card(1);
        _results_text();
        break;
    }
    _scene = scene;
}

// ---- play ---------------------------------------------------------------------------------------------------------

void view::_update_camera(bool snap)
{
    const world_t* w = world();
    const zip_level* lv = zip_level_current();
    int px = int(w->x >> 8), py = int(w->y >> 8);
    int vx = w->mode == MODE_AIR ? w->xv : (w->mode == MODE_GROUND ? w->gsp : 0);
    if(w->mode == MODE_GROUND && (w->angle & 255) != 0)
    {
        vx = vx * 7 / 8;
    }
    // look ahead in the direction of travel, proportional to speed (in 1/16 px)
    int target = vx * 16 * 16 / 256;                   // 16 px of look-ahead per px/frame: 96 px at top speed
    int limit = 96 * 16;
    target = target > limit ? limit : target < -limit ? -limit : target;
    if(snap)
    {
        _look = target;
    }
    else
    {
        int d = target - _look;
        int step = 12;                                  // 1/16 px per frame toward the target
        _look += d > step ? step : d < -step ? -step : d;
    }
    int want_x = px - screen_w / 2 + _look / 16;
    int want_y = _cam_y;
    int top = py - _cam_y;
    if(snap)
    {
        want_y = py - 88;
    }
    else if(top < 56)
    {
        want_y = py - 56;
    }
    else if(top > 104)
    {
        want_y = py - 104;
    }
    if(! snap)
    {
        int dy = want_y - _cam_y;
        int maxdy = w->mode == MODE_LOOP ? 12 : 16;
        want_y = _cam_y + (dy > maxdy ? maxdy : dy < -maxdy ? -maxdy : dy);
    }
    int max_x = lv->w * 16 - screen_w, max_y = lv->h * 16 - screen_h;
    _cam_x = want_x < 0 ? 0 : want_x > max_x ? max_x : want_x;
    _cam_y = want_y < 0 ? 0 : want_y > max_y ? max_y : want_y;
    _camera.set_position(_cam_x + screen_w / 2, _cam_y + screen_h / 2);
    g_dbg_cam_xy = (uint32_t(_cam_x) << 16) | uint32_t(_cam_y);
    if(_hall)
    {
        // the hall scrolls at a quarter of the speed; its floor line sits low on the screen at the level's floor
        int sx = (_cam_x / 4) % 512, sy = 96 + (_cam_y - max_y) / 8;
        _hall->set_position(136 - sx, 48 - sy);
    }
}

void view::_update_zip()
{
    const world_t* w = world();
    int speed = iabs(w->mode == MODE_AIR ? w->xv : w->gsp);
    int frame = F_STAND;
    bool rotate = w->mode != MODE_AIR;
    _anim += speed + 64;
    switch(w->pose)
    {
    case POSE_STAND:
        frame = (_frame % 180) < 8 ? F_BLINK : F_STAND;
        break;
    case POSE_RUN:
        if(speed < 0x0300)
        {
            frame = F_WALK + (_anim / (10 * 256)) % 4;
        }
        else if(speed < 0x0600)
        {
            frame = F_RUN + (_anim / (14 * 256)) % 4;
        }
        else
        {
            frame = F_DASH + (_anim / (12 * 256)) % 4;
        }
        break;
    case POSE_ROLL:
    case POSE_JUMP:
        frame = F_ROLL + (_anim / (6 * 256)) % 4;
        rotate = false;
        break;
    case POSE_SPRING:
        frame = F_SPRING;
        break;
    case POSE_HURT:
        frame = F_HURT;
        break;
    default:
        frame = F_FALL;
        break;
    }
    bool blink = w->invuln && (_frame & 4);
    _zip.set_visible(! blink);
    _zip.set_tiles(bn::sprite_items::zip.tiles_item(), frame);
    _zip.set_position(int(w->x >> 8), int(w->y >> 8));
    _zip.set_horizontal_flip(w->facing != 0);
    _zip.set_rotation_angle(rotate ? degrees(w->angle) : bn::fixed(0));

    // the speed trail: behind Zip at dash speed
    bool trail = w->mode != MODE_AIR && speed >= 0x0680 && ! w->rolling;
    _trail.set_visible(trail);
    if(trail)
    {
        int back = w->facing ? 16 : -16;
        int len = speed >= 0x0B00 ? 2 : speed >= 0x0800 ? 1 : 0;
        _trail.set_tiles(bn::sprite_items::trail.tiles_item(), len);
        _trail.set_horizontal_flip(w->facing != 0);
        _trail.set_rotation_angle(degrees(w->angle));
        // along the surface, behind the player
        int a = w->angle & 255;
        int dx = back, dy = 0;
        if(a != 0)
        {
            // small table-free approximation: 22.5 and 45 degree slopes, and the loop quarter points
            int s = (a < 128) ? 1 : -1;
            int steep = (a == 32 || a == 224) ? 2 : (a == 16 || a == 240) ? 1 : 0;
            dy = (w->facing ? -1 : 1) * s * (back < 0 ? -back : back) * steep / 4;
            dy = -dy;
        }
        _trail.set_position(int(w->x >> 8) + dx, int(w->y >> 8) + dy);
    }
}

void view::_update_things()
{
    const zip_level* lv = zip_level_current();
    int left = _cam_x - 24, right = _cam_x + screen_w + 24, top = _cam_y - 40, bottom = _cam_y + screen_h + 40;
    int np = 0, nt = 0;
    int created = 0;                                  // new sprites this frame: creating one is slow, and a hit
                                                      // scatters up to SCATTER_MAX packets at once (a lag frame)
    int spin = (_frame / 6) % 4;

    auto packet = [&](int x, int y, bool on)
    {
        int phase = (spin + (x >> 4)) & 3;            // neighbours spin out of step, never all edge-on at once
        if(np >= packet_pool)
        {
            return;
        }
        if(np >= _packets.size())
        {
            if(created >= max_new_sprites)
            {
                return;                               // drawn from a later frame on, once its sprite exists
            }
            ++created;
            bn::sprite_ptr s = bn::sprite_items::packet.create_sprite(0, 0, 0);
            s.set_camera(_camera);
            s.set_bg_priority(1);
            s.set_z_order(3);
            _packets.push_back(bn::move(s));
        }
        bn::sprite_ptr& s = _packets[np++];
        s.set_visible(on);
        s.set_position(x, y);
        s.set_tiles(bn::sprite_items::packet.tiles_item(), phase);
    };
    auto thing = [&](const bn::sprite_item& item, int frame, int x, int y, bool flip)
    {
        if(nt >= thing_pool)
        {
            return;
        }
        if(nt >= _things.size())
        {
            if(created >= max_new_sprites)
            {
                return;
            }
            ++created;
            bn::sprite_ptr s = item.create_sprite(0, 0, frame);
            s.set_camera(_camera);
            s.set_bg_priority(1);
            s.set_z_order(4);
            _things.push_back(bn::move(s));
        }
        bn::sprite_ptr& s = _things[nt++];
        s.set_item(item, frame);
        s.set_visible(true);
        s.set_position(x, y);
        s.set_horizontal_flip(flip);
    };

    for(int i = first_ent_from(lv, left - 32); i < lv->n_ents && lv->ents[i].x <= right + 32; ++i)
    {
        const zip_ent& e = lv->ents[i];
        if(e.y < top || e.y > bottom + 32)
        {
            continue;
        }
        uint8_t st = world_ent_state(i);
        switch(e.kind)
        {
        case ENT_PACKET:
            if(! st)
            {
                packet(e.x, e.y, true);
            }
            break;
        case ENT_SPRING_Y:
        case ENT_SPRING_R:
        {
            int f = st > SPRING_ANIM - 4 ? 1 : st ? 2 : 0;
            thing(bn::sprite_items::spring, (e.kind == ENT_SPRING_R ? 3 : 0) + f, e.x, e.y - 8, false);
            break;
        }
        case ENT_BOOSTER:
            thing(bn::sprite_items::booster, (_frame / 6) % 3, e.x, e.y - 16, false);
            break;
        case ENT_BUG:
            if(! st)
            {
                int bx = int(world_bug_x(i) >> 8);
                thing(bn::sprite_items::bug, (_frame / 10) % 2, bx, e.y - 8, world_bug_left(i));
            }
            break;
        case ENT_CHECKPOINT:
            thing(bn::sprite_items::rack, st ? 1 : 0, e.x, e.y - 16, false);
            break;
        default:
            break;
        }
    }
    for(int i = 0; i < SCATTER_MAX; ++i)
    {
        const zip_scatter* p = world_scatter(i);
        if(! p->age)
        {
            continue;
        }
        int x = int(p->x >> 8), y = int(p->y >> 8);
        if(x < left || x > right || y < top || y > bottom)
        {
            continue;
        }
        bool on = p->age < SCATTER_LIFE - 60 || (_frame & 2);
        packet(x, y, on);
    }
    for(int i = np; i < _packets.size(); ++i)
    {
        _packets[i].set_visible(false);
    }
    for(int i = nt; i < _things.size(); ++i)
    {
        _things[i].set_visible(false);
    }
}

void view::_update_hud(bool on)
{
    if(! on)
    {
        _hud_time.clear();
        _hud_packets.clear();
        if(_icons.size() && _scene != SC_RESULTS)
        {
            _icons.clear();
        }
        _hud_seconds = -1;
        _hud_count = -1;
        return;
    }
    if(_icons.empty())
    {
        bn::sprite_ptr p = bn::sprite_items::icons.create_sprite(-110, -70, 0);
        p.set_bg_priority(0);
        _icons.push_back(bn::move(p));
        bn::sprite_ptr c = bn::sprite_items::icons.create_sprite(-110, -52, 1);
        c.set_bg_priority(0);
        _icons.push_back(bn::move(c));
    }
    int seconds = int(rules_run_frames() / 60);
    if(seconds != _hud_seconds)
    {
        _hud_time.clear();
        _small.set_left_alignment();
        _small.generate(-98, -52, time_text(rules_run_frames(), false), _hud_time);
        _hud_seconds = seconds;
    }
    int count = world()->packets;
    if(count != _hud_count)
    {
        _hud_packets.clear();
        _small.set_left_alignment();
        _small.generate(-98, -70, bn::to_string<8>(count), _hud_packets);
        _hud_count = count;
    }
    // no packets: the counter flashes (the next hit sends you back)
    bool flash = count == 0 && (_frame & 16);
    for(bn::sprite_ptr& s : _hud_packets)
    {
        s.set_visible(! flash);
    }
}

void view::_update_ghost(const ac_ghost_pt* ghost, bool play)
{
    _ghost_shown = play && ghost != nullptr && (ghost->flags & 0x80);
    _ghost.set_visible(_ghost_shown);
    if(! _ghost_shown)
    {
        return;
    }
    _ghost.set_position(ghost->x, ghost->y);
    _ghost.set_rotation_angle(degrees(ghost->angle));
    _ghost.set_tiles(bn::sprite_items::zip.tiles_item(), F_RUN + (_frame / 8) % 4);
    // The GBA blends a half-transparent sprite with the backgrounds only, never with another sprite, and draws only
    // the frontmost sprite pixel: the ghost goes below the player every frame (a re-inserted sprite lands in front
    // of its layer), so the player stays solid where they overlap.
    _ghost.put_below();
}

void view::update(const ac_ghost_pt* ghost)
{
    ++_frame;
    g_dbg_cpu = uint32_t((bn::core::last_cpu_usage() * 1000).right_shift_integer());
    _flush_queue(2);
    int scene = rules_scene();
    if(scene != _scene)
    {
        if(_scene == SC_PAUSE && scene == SC_PLAY)
        {
            _pause_text(false);
            _scene = scene;
        }
        else
        {
            _enter_scene(scene);
        }
    }
    bool play = scene == SC_PLAY || scene == SC_PAUSE;
    _zip.set_visible(play);
    if(play)
    {
        const world_t* w = world();
        bool snap = w->respawns != _respawns;
        _respawns = w->respawns;
        if(scene == SC_PLAY)
        {
            _update_camera(snap);
            _update_zip();
        }
        _update_things();
        if(scene == SC_PLAY && rules_finished() && ! _banner_on)
        {
            _big.set_center_alignment();
            _big.generate(0, -60, "GOAL!", _banner);
            _banner_on = true;
        }
    }
    else
    {
        _trail.set_visible(false);
        for(bn::sprite_ptr& s : _packets)
        {
            s.set_visible(false);
        }
        for(bn::sprite_ptr& s : _things)
        {
            s.set_visible(false);
        }
    }
    _update_hud(play);
    _update_ghost(ghost, scene == SC_PLAY);
    if(scene == SC_TITLE)
    {
        // PRESS START blinks
        if((_frame % 60) == 0 || (_frame % 60) == 40)
        {
            if(_banner.empty())
            {
                _small.set_center_alignment();
                _small.generate(0, 20, "PRESS START", _banner);
            }
            else
            {
                _banner.clear();
            }
        }
    }
    else if(scene == SC_RESULTS && rules_scene_frames() > RESULTS_LOCK)
    {
        if((_frame % 60) == 0)
        {
            _small.set_center_alignment();
            _small.generate(0, 70, "START", _banner);
        }
        else if((_frame % 60) == 40)
        {
            _banner.clear();
        }
    }
}

}

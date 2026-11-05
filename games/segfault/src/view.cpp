#include "view.h"

#include "bn_affine_mat_attributes.h"
#include "bn_bg_palette_item.h"
#include "bn_bg_palettes.h"
#include "bn_blending.h"
#include "bn_core.h"
#include "bn_math.h"
#include "bn_color.h"
#include "bn_fixed.h"
#include "bn_string.h"
#include "bn_timer.h"

#include "arcade_runtime.h"
#include "common_variable_8x8_sprite_font.h"
#include "bn_sprite_items_blaster.h"
#include "bn_sprite_items_blip.h"
#include "bn_sprite_items_crosshair.h"
#include "bn_sprite_items_phantom.h"

extern "C" {
#include "ac_fix.h"
#include "game.h"
#include "segf_art.h"
#include "tuning.h"
}

// Frame timing for the README's measurement: timer ticks of this frame's view work, the worst so far, and views
// (flips) completed. ticks_per_frame is 4389.
extern "C" {
volatile uint32_t g_dbg_view_ticks;
volatile uint32_t g_dbg_view_max;
volatile uint32_t g_dbg_views;
volatile uint32_t g_dbg_drawn;          // bug bits whose billboard reached the screen in the last completed view
}

namespace game
{

namespace
{
    // the frame's time budget for the view, in timer ticks (4389 a frame), and cost guesses for the fixed parts
    constexpr int frame_budget = 3950;
    constexpr int start_cost = 450;
    constexpr int map_cost = 1100;
    constexpr int text_deadline = 2400;
    constexpr int hud_cost = 400;
    constexpr int chunk = 4;
    constexpr int radar_w = SEGF_RADAR_X1 - SEGF_RADAR_X0;
    constexpr int radar_h = (SEGF_RADAR_Y1 - SEGF_RADAR_Y0) / 2;

    // radar colour of each cell kind (CELL_*); 15: outside the map
    uint8_t radar_colours[16] = {
        SEGF_C_RADAR_BG, SEGF_C_RADAR_WALL, SEGF_C_RADAR_WALL, SEGF_C_RADAR_WALL, SEGF_C_RADAR_WALL,
        SEGF_C_RADAR_DOOR, SEGF_C_RADAR_SHELF, SEGF_C_RADAR_WALL, SEGF_C_RADAR_READER, SEGF_C_RADAR_WALL,
        SEGF_C_RADAR_EXIT, SEGF_C_RADAR_WALL, SEGF_C_RADAR_WALL, SEGF_C_RADAR_DOOR, SEGF_C_RADAR_BG, SEGF_C_RADAR_BG
    };

    bn::color game_colors[256];
    bn::color card_colors[256];

    void convert(const uint16_t* src, bn::color* dst)
    {
        for(int i = 0; i < 256; ++i)
        {
            dst[i] = bn::color(src[i] & 31, (src[i] >> 5) & 31, (src[i] >> 10) & 31);
        }
    }

    bn::bg_palette_item palette_item(const bn::color* colors)
    {
        return bn::bg_palette_item(bn::span<const bn::color>(colors, 256), bn::bpp_mode::BPP_8);
    }

    uint8_t* hidden_page(bn::palette_bitmap_bg_ptr& bg)
    {
        return reinterpret_cast<uint8_t*>(bg.page().data());
    }

    void set_rotated(bn::palette_bitmap_bg_ptr& bg, bool rotated)
    {
        bn::affine_mat_attributes m;
        if(rotated)
        {
            // screen (x, y) shows memory (y, x / 2): a screen column pair is one memory row (the spike's layout)
            m.set_rotation_angle(1);
            m.unsafe_set_register_values(0, 256, 128, 0);
            bg.set_mat_attributes(m);
            bg.set_pivot_position(-40, -20);
        }
        else
        {
            bg.set_mat_attributes(m);
            bg.set_pivot_position(0, 0);
        }
    }

    // frames -> "M:SS.HH"
    bn::string<16> time_text(uint32_t frames, bool hundredths)
    {
        uint32_t secs = frames / 60;
        bn::string<16> s = bn::to_string<8>(secs / 60);
        s.push_back(':');
        s.push_back(char('0' + (secs % 60) / 10));
        s.push_back(char('0' + secs % 10));
        s.push_back('.');
        uint32_t part = (frames % 60) * 100 / 60;
        s.push_back(char('0' + part / 10));
        if(hundredths)
        {
            s.push_back(char('0' + part % 10));
        }
        return s;
    }

    const char* message(int msg)
    {
        switch(msg)
        {
        case MSG_NEED_KEY: return "ACCESS DENIED: keycard needed";
        case MSG_GOT_KEY: return "World ID verified: keycard issued";
        case MSG_HEALTH: return "Arkiv shelf: +25 health";
        case MSG_HEALTH_FULL: return "Health is already full";
        case MSG_SHELF_EMPTY: return "This shelf is empty";
        case MSG_READER_DONE: return "Already verified";
        case MSG_SECRET: return "Secret room found!";
        case MSG_ALL_BUGS: return "All bugs squashed!";
        case MSG_REBOOT: return "Rebooting the build server...";
        case MSG_LOCKED: return "LOCKED: keycard required";
        default: return "";
        }
    }
}

view::view() :
    _bg(bn::palette_bitmap_bg_ptr::create((convert(segf_palette, game_colors), convert(segf_card_palette, card_colors),
                                           palette_item(card_colors)))),
    _text(common::variable_8x8_sprite_font),
    _blaster(bn::sprite_items::blaster.create_sprite(0, 48)),
    _crosshair(bn::sprite_items::crosshair.create_sprite(0, -16)),
    _phantom(bn::sprite_items::phantom.create_sprite(0, 0)),
    _blip(bn::sprite_items::blip.create_sprite(0, 0))
{
    ray::setup();
    _blaster.set_z_order(1);
    _crosshair.set_z_order(1);
    _phantom.set_blending_enabled(true);           // half transparent over the view
    _blip.set_blending_enabled(true);
    _phantom.set_z_order(3);                       // behind every other sprite: a blended sprite only mixes with the BG
    _blip.set_z_order(3);
    bn::blending::set_transparency_alpha(0.5);
    _text.set_bg_priority(0);
    _enter_card(0);                                // before the first game step: no lag frame at boot
    _scene = SC_TITLE;
    _update_texts();
    bn::core::update();                            // commit the card, palette and sprites before the loop
}

void view::_enter_card(int card)
{
    uint8_t* page = hidden_page(_bg);
    ray::copy_blocks(page, segf_cards[card], 38400 / 4);
    set_rotated(_bg, false);
    _bg.set_palette(palette_item(card_colors));
    bn::bg_palettes::set_fade(bn::color(0, 0, 0), 0);
    _bg.flip_page_later();
    _rotate_on_flip = false;
}

void view::_start_view()
{
    for(int i = 0, n = ray::sliding_count(); i < n; ++i)
    {
        int c = ray::sliding_cell(i);
        ray::set_slide(i, rules_door_amount(c % MAP_W, c / MAP_W));
    }
    uint16_t a = rules_angle();
    int32_t dx = int32_t(ac_cos(a)) << 2, dy = int32_t(ac_sin(a)) << 2;
    _cam.px = rules_px();
    _cam.py = rules_py();
    _cam.dirx = dx;
    _cam.diry = dy;
    _cam.planex = -((dy * 43) >> 6);               // 0.67 of the right-hand perpendicular
    _cam.planey = (dx * 43) >> 6;
    int n = 0;
    int count = rules_bug_count();
    static_assert(MAX_BUGS <= ray::max_billboards, "a billboard for every bug");
    for(int i = 0; i < count && n < ray::max_billboards; ++i)
    {
        int state = rules_bug_state(i);
        int frame;
        if(state == BUG_DEAD)
        {
            frame = 4;
        }
        else if(state == BUG_HURT)
        {
            frame = 3;
        }
        else if(rules_bug_biting(i))
        {
            frame = 2;
        }
        else
        {
            frame = (rules_bug_anim(i) / (state == BUG_CHASE ? 6 : 20)) & 1;
        }
        ray::billboard& b = _bills[n++];
        b.x = rules_bug_x(i);
        b.y = rules_bug_y(i);
        b.frame = ray::bug_frames() + frame * SEGF_TEX_SIZE * SEGF_TEX_SIZE;
        b.height = 0xB000;
        b.id = i;
    }
    ray::begin(_cam, _bills, n);
}

void view::_draw_hud()
{
    uint8_t* hud = ray::hud();
    // health bar
    int w = SEGF_HUD_BAR_X1 - SEGF_HUD_BAR_X0 + 1;
    int health = rules_health();
    int fill = (w * health + HEALTH_MAX - 1) / HEALTH_MAX;
    uint8_t colour = uint8_t(health > 50 ? SEGF_C_GREEN : health > 25 ? SEGF_C_AMBER : SEGF_C_RED);
    for(int x = 0; x < w; ++x)
    {
        uint8_t* col = hud + (SEGF_HUD_BAR_X0 + x) * 32;
        for(int y = SEGF_HUD_BAR_Y0; y <= SEGF_HUD_BAR_Y1; ++y)
        {
            col[y] = x < fill ? colour : uint8_t(SEGF_C_BAR_BG);
        }
    }
    // keycard
    const uint8_t* icon = segf_key_icons[rules_has_key() ? 1 : 0];
    for(int x = 0; x < 8; ++x)
    {
        for(int y = 0; y < 16; ++y)
        {
            hud[(SEGF_HUD_KEY_X + x) * 32 + SEGF_HUD_KEY_Y + y] = icon[x * 16 + y];
        }
    }
    // radar: a window of the map around the player, one cell = one memory column x two rows (2 x 2 on screen)
    int pcx = rules_px() >> 16, pcy = rules_py() >> 16;
    int ox = pcx - radar_w / 2, oy = pcy - radar_h / 2;
    radar_colours[CELL_SECRET] = rules_secret_found() ? uint8_t(SEGF_C_RADAR_BG) : uint8_t(SEGF_C_RADAR_WALL);
    ray::draw_radar(hud, ox, oy, radar_w, radar_h, SEGF_RADAR_X0, SEGF_RADAR_Y0, radar_colours, SEGF_C_RADAR_OPEN,
                    SEGF_C_RADAR_DOOR);
    int count = rules_bug_count();
    for(int i = 0; i < count; ++i)
    {
        if(rules_bug_state(i) == BUG_CHASE || rules_bug_state(i) == BUG_HURT)
        {
            int wx = (rules_bug_x(i) >> 16) - ox, wy = (rules_bug_y(i) >> 16) - oy;
            if(wx >= 0 && wy >= 0 && wx < radar_w && wy < radar_h)
            {
                uint8_t* p = hud + (SEGF_RADAR_X0 + wx) * 32 + SEGF_RADAR_Y0 + wy * 2;
                p[0] = p[1] = SEGF_C_RADAR_BUG;
            }
        }
    }
    {
        uint8_t* p = hud + (SEGF_RADAR_X0 + radar_w / 2) * 32 + SEGF_RADAR_Y0 + (radar_h / 2) * 2;
        p[0] = p[1] = SEGF_C_RADAR_ME;
        uint16_t a = rules_angle();
        int ddx = ac_cos(a) > 6000 ? 1 : ac_cos(a) < -6000 ? -1 : 0;
        int ddy = ac_sin(a) > 6000 ? 1 : ac_sin(a) < -6000 ? -1 : 0;
        uint8_t* q = hud + (SEGF_RADAR_X0 + radar_w / 2 + ddx) * 32 + SEGF_RADAR_Y0 + (radar_h / 2 + ddy) * 2;
        q[0] = q[1] = SEGF_C_RADAR_DIR;
    }
}

void view::_update_ghost(const ac_ghost_pt* ghost)
{
    bool world = false, blip = false;
    if(ghost && rules_scene() == SC_PLAY)
    {
        // the phantom in the world (x, y are 1/16 tiles), hidden behind walls and when too near to fit a sprite
        int32_t colq, depth;
        int32_t gx = int32_t(ghost->x) << 12, gy = int32_t(ghost->y) << 12;
        if(ray::project(_cam, gx, gy, colq, depth) && depth > 0x8000)
        {
            int col = colq >> 16;
            int h = int((int64_t(182) * 0xB000) / depth);
            if(col >= 0 && col < ray::cols && h <= 60 && ray::depth_at(col) > depth)
            {
                int bottom = 64 + int((int64_t(91) << 16) / depth);
                _phantom.set_position(col * 2 + 1 - 120, bottom - h / 2 - 80);
                _phantom.set_scale(bn::max(bn::fixed(h) / 32, bn::fixed(0.1)));
                world = true;
            }
        }
        // the radar blip
        int ox = (rules_px() >> 16) - radar_w / 2, oy = (rules_py() >> 16) - radar_h / 2;
        int rx = int(ghost->x) - ox * 16, ry = int(ghost->y) - oy * 16;       // 1/16 cells in the window
        if(rx >= 0 && ry >= 0 && rx < radar_w * 16 && ry < radar_h * 16)
        {
            _blip.set_position(SEGF_RADAR_X0 * 2 + rx / 8 - 120, 128 + SEGF_RADAR_Y0 + ry / 8 - 80);
            blip = true;
        }
    }
    _phantom.set_visible(world);
    _blip.set_visible(blip);
    _ghost_shown = world || blip;
}

bool view::top_message() const
{
    return rules_scene() == SC_PLAY && ! rules_paused() && ! rules_dead_timer() &&
           (rules_msg() != MSG_NONE || rules_run_frames() < 240);
}

void view::_update_texts()
{
    if(bn::core::current_cpu_ticks() > text_deadline)
    {
        return;                                    // a heavy rules frame: the text catches up next frame
    }
    int scene = rules_scene();
    // HUD numbers
    int hud_key = -1;
    if(scene == SC_PLAY)
    {
        hud_key = (rules_health() << 20) ^ (rules_bugs_left() << 14) ^ int(rules_run_frames() / 60);
    }
    if(hud_key != _hud_key)
    {
        _hud_key = hud_key;
        _hud_words.clear();
        if(scene == SC_PLAY)
        {
            _text.set_left_alignment();
            _text.generate(-96, 72, bn::to_string<8>(rules_health()), _hud_words);
            bn::string<16> bugs = bn::to_string<8>(rules_bugs_left());
            _text.generate(32, 57, bugs, _hud_words);
            bn::string<16> clock = time_text(rules_run_frames(), false);
            clock.shrink(clock.size() - 2);                             // "M:SS": one text update a second
            _text.generate(10, 72, clock, _hud_words);
        }
    }
    // the message line, the pause menu, the core dump
    int msg_key = -1;
    if(scene == SC_PLAY)
    {
        msg_key = rules_msg() | (rules_paused() << 5) | (rules_pause_sel() << 6) | ((rules_dead_timer() > 0) << 7);
        if(rules_msg() == MSG_NONE && rules_run_frames() < 240 && ! rules_paused())
        {
            msg_key |= 1 << 8;
        }
    }
    if(msg_key != _msg_key)
    {
        _msg_key = msg_key;
        _msg_words.clear();
        if(scene == SC_PLAY)
        {
            _text.set_center_alignment();
            if(rules_paused())
            {
                _text.generate(0, -30, "PAUSED", _msg_words);
                _text.generate(0, -10, rules_pause_sel() == 0 ? "> Resume <" : "Resume", _msg_words);
                _text.generate(0, 4, rules_pause_sel() == 1 ? "> Quit <" : "Quit", _msg_words);
            }
            else if(rules_dead_timer())
            {
                _text.generate(0, -24, "Segmentation fault", _msg_words);
                _text.generate(0, -12, "(core dumped)", _msg_words);
                _text.generate(0, 8, "Restarting the level...", _msg_words);
            }
            else if(msg_key & (1 << 8))
            {
                _text.generate(0, -70, "Squash the bugs. Find the keycard.", _msg_words);
            }
            else if(rules_msg() != MSG_NONE)
            {
                _text.generate(0, -70, message(rules_msg()), _msg_words);
            }
        }
    }
    // the cards' text
    int screen_key = -1;
    if(scene == SC_TITLE)
    {
        screen_key = 1 + ((arcade::steps() / 32) & 1);
    }
    else if(scene == SC_RESULTS)
    {
        // one line a frame: the card copy and a dozen lines of sprite text do not fit in one frame together
        screen_key = 10 + bn::min(_results_line++, 11);
    }
    if(screen_key != _screen_key)
    {
        _screen_key = screen_key;
        if(scene != SC_RESULTS || screen_key == 10)
        {
            _screen_words.clear();
        }
        _text.set_center_alignment();
        if(scene == SC_TITLE)
        {
            if(screen_key == 1)
            {
                _text.generate(0, 36, "PRESS START", _screen_words);
            }
            const char* name = arcade::profile_name();
            if(name[0])
            {
                bn::string<32> who("Player ");
                who.append(name);
                _text.generate(0, -72, who, _screen_words);
            }
            if(arcade::best_time_frames())
            {
                bn::string<32> b("Best ");
                b.append(time_text(arcade::best_time_frames(), true));
                if(arcade::has_ghost())
                {
                    b.append("  ghost loaded");
                }
                _text.generate(0, 48, b, _screen_words);
            }
            else if(arcade::has_ghost())
            {
                _text.generate(0, 48, "Ghost loaded", _screen_words);
            }
        }
        else if(scene == SC_RESULTS && screen_key > 10)
        {
            ac_result r;
            game_result(&r);
            _text.set_left_alignment();
            int line = screen_key - 11;
            bn::string<40> t;
            int y = -50;
            if(line == 0)
            {
                t = r.finished ? "BUILD SERVER REBOOTED" : "RUN ABORTED";
            }
            else if(line == 1)
            {
                t = "Time    ";
                t.append(time_text(r.time_frames, true));
                y = -34;
            }
            else if(line == 2)
            {
                t = "Bugs    ";
                t.append(bn::to_string<4>(r.score));
                t.push_back('/');
                t.append(bn::to_string<4>(rules_bug_count()));
                t.append("   Deaths ");
                t.append(bn::to_string<4>(rules_deaths()));
                y = -22;
            }
            else if(line < 3 + GAME_INFO.n_trophies)
            {
                int i = line - 3;
                t = (r.trophies & (1u << i)) ? "[x] " : "[ ] ";
                t.append(GAME_INFO.trophy_names[i]);
                y = -4 + 11 * i;
            }
            else if(line == 7)
            {
                if(arcade::best_is_new())
                {
                    t = "NEW BEST!";
                }
                else if(arcade::best_time_frames())
                {
                    t = "Best    ";
                    t.append(time_text(arcade::best_time_frames(), true));
                }
                y = 44;
            }
            else if(line == 8)
            {
                t = "START: back to the title";
                y = 60;
            }
            if(! t.empty())
            {
                _text.generate(-100, y, t, _screen_words);
            }
        }
    }
}

void view::_update_sprites()
{
    bool play = rules_scene() == SC_PLAY;
    bool alive = play && ! rules_dead_timer();
    _blaster.set_visible(alive);
    _crosshair.set_visible(alive && ! rules_paused());
    if(alive)
    {
        int age = rules_shot_age();
        uint16_t walk = rules_walk();
        int bx = (ac_sin(uint16_t(walk * 2)) * 4) >> 14;
        int by = (ac_cos(uint16_t(walk * 4)) * 2) >> 14;
        by = by < 0 ? -by : by;
        int recoil = age < 3 ? 4 : age < 6 ? 2 : 0;
        _blaster.set_position(8 + bx, 10 + by + recoil);             // the grip ends at the HUD's top edge
        _blaster.set_tiles(bn::sprite_items::blaster.tiles_item(), age < 4 ? 1 : 0);
    }
    // the damage flash and the core dump tint
    if(play && rules_dead_timer())
    {
        bn::bg_palettes::set_fade(bn::color(24, 0, 2), 0.45);
    }
    else if(play && rules_hurt_age() < 10)
    {
        bn::bg_palettes::set_fade(bn::color(31, 0, 0), bn::fixed(10 - rules_hurt_age()) / 22);
    }
    else
    {
        bn::bg_palettes::set_fade(bn::color(0, 0, 0), 0);
    }
}

void view::update(const ac_ghost_pt* ghost)
{
    bn::timer timer;
    int scene = rules_scene();
    if(scene != _scene)
    {
        if(scene == SC_TITLE)
        {
            _enter_card(0);
        }
        else if(scene == SC_HOWTO)
        {
            _enter_card(1);
        }
        else if(scene == SC_RESULTS)
        {
            _enter_card(2);
            _results_line = 0;
        }
        else
        {
            _next = -1;
            _rotate_on_flip = true;
        }
        _scene = scene;
    }
    _update_ghost(ghost);
    _update_texts();
    _update_sprites();
    if(scene == SC_PLAY && ! rules_paused())
    {
        // Render as many columns as this frame has time for: the rules must step every frame (the runtime's
        // contract), so the view never pushes a frame past its V-Blank; a view takes two frames, sometimes three.
        uint8_t* page = hidden_page(_bg);
        if(rules_map_version() != _map_version && bn::core::current_cpu_ticks() + map_cost < frame_budget)
        {
            ray::load_map(rules_cells());                // the whole map, only when a cell changed
            _map_version = rules_map_version();
        }
        if(_next < 0 && _map_version == rules_map_version() &&
           bn::core::current_cpu_ticks() + start_cost < frame_budget)
        {
            _start_view();
            _next = 0;
        }
        while(_next >= 0 && _next < ray::cols)
        {
            int t0 = bn::core::current_cpu_ticks();
            if(t0 + _chunk_cost > frame_budget)
            {
                break;
            }
            int end = bn::min(ray::cols, _next + chunk);
            ray::render(page, _next, end);
            int cost = bn::core::current_cpu_ticks() - t0;
            _chunk_cost = bn::max(cost, (_chunk_cost * 7) / 8);
            _next = end;
        }
        if(_next == ray::cols && bn::core::current_cpu_ticks() + hud_cost < frame_budget)
        {
            _draw_hud();
            ray::copy_hud(page);
            if(top_message())
            {
                ray::darken_rows(page, 4, 16);             // a dark band under the message line
            }
            if(_rotate_on_flip)
            {
                set_rotated(_bg, true);
                _bg.set_palette(palette_item(game_colors));
                _rotate_on_flip = false;
            }
            _bg.flip_page_later();
            g_dbg_drawn = ray::drawn_mask();
            _next = -1;
            g_dbg_views = g_dbg_views + 1;
            // the next view's set-up is CPU work only: start it now if there is time, its columns go next frame
            // (the hidden page is the one on screen until the flip is committed)
            if(_map_version == rules_map_version() && bn::core::current_cpu_ticks() + start_cost < frame_budget)
            {
                _start_view();
                _next = 0;
            }
        }
    }
    uint32_t ticks = uint32_t(timer.elapsed_ticks());
    g_dbg_view_ticks = ticks;
    if(ticks > g_dbg_view_max)
    {
        g_dbg_view_max = ticks;
    }
}

}

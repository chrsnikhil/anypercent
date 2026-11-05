#include "view.h"

#include "best.h"

#include "bn_bg_palette_ptr.h"
#include "bn_blending.h"
#include "bn_bg_palettes.h"
#include "bn_bg_palette_items_hall_palette.h"
#include "bn_bg_palette_items_office_dawn_palette.h"
#include "bn_bg_palette_items_office_night_palette.h"
#include "bn_bg_palette_items_office_palette.h"
#include "bn_color.h"
#include "bn_math.h"
#include "bn_regular_bg_map_cell_info.h"
#include "bn_size.h"
#include "bn_sprite_items_bug.h"
#include "bn_sprite_items_card.h"
#include "bn_sprite_items_confetti.h"
#include "bn_sprite_items_flash.h"
#include "bn_sprite_items_grade.h"
#include "bn_sprite_items_spot.h"
#include "bn_sprite_items_crowd0.h"
#include "bn_sprite_items_crowd1.h"
#include "bn_sprite_items_crowd2.h"
#include "bn_sprite_items_gate.h"
#include "bn_sprite_items_dev0.h"
#include "bn_sprite_items_dev1.h"
#include "bn_sprite_items_dev2.h"
#include "bn_sprite_items_hud_bar.h"
#include "bn_sprite_items_hud_strip.h"
#include "bn_sprite_items_icons.h"
#include "bn_sprite_items_logo_small.h"
#include "bn_sprite_items_logo_title.h"
#include "bn_sprite_items_meter.h"
#include "bn_sprite_items_pill.h"
#include "bn_sprite_items_pizza.h"
#include "bn_sprite_items_player_bottom.h"
#include "bn_sprite_items_player_top.h"
#include "bn_sprite_items_rain.h"
#include "bn_sprite_items_spark.h"
#include "bn_tile.h"
#include "common_variable_8x16_sprite_font.h"
#include "common_variable_8x8_sprite_font.h"

extern "C" {
#include "ac_game.h"
#include "rules.h"
#include "scene_hall.h"
#include "scene_office.h"
#include "tuning.h"
}
#include "sprites.h"

namespace shipit
{

namespace
{
    constexpr int screen_w = 240;
    constexpr int screen_h = 160;
    constexpr int play_h = 136;                    // rows above the HUD
    constexpr int cam_step = 8;                    // px per frame per axis: at most one new tile column and row
    constexpr int dead_left = 96, dead_right = 144, dead_top = 70, dead_bottom = 104;
    constexpr int head_above_dev = DEV_HEAD;       // px from a dev's seat to the top of the head (measured)
    constexpr int head_above_player = PLAYER_HEAD; // px from the player's feet to the top of the head (measured)
    constexpr int text_lines_per_frame = 4;        // building more sprite text than this in one frame overruns it
    constexpr int refill_writes = 64;              // tile writes per frame while the screen is black (a room swap)
    constexpr int refill_frames = 12;              // a whole screen of cells at refill_writes per frame
    constexpr int squash_frames = 20;
    constexpr int flash_frames = 4, cheer_frames = 20, confetti_frames = 120, shake_frames = 12;
    constexpr int shake_offsets[shake_frames] = { 2, -2, 1, -1, 2, -1, 1, -2, 1, 0, -1, 0 };
    constexpr int card_x = 24, card_y = 12;       // the results card: 3 x 4 pieces of 64 x 32
    constexpr int router_top_dx = -16, router_top_dy = -36;    // the router on the side table, from its use spot

    int text_budget = 0;                           // text lines that may still be rebuilt this frame

    const bn::sprite_item* const dev_items[DEVS] = {
        &bn::sprite_items::dev0, &bn::sprite_items::dev1, &bn::sprite_items::dev2 };
    const int dev_x[DEVS] = { DEV0_X, DEV1_X, DEV2_X };
    const int dev_y[DEVS] = { DEV0_Y, DEV1_Y, DEV2_Y };
    const bn::sprite_item* const crowd_items[3] = {
        &bn::sprite_items::crowd0, &bn::sprite_items::crowd1, &bn::sprite_items::crowd2 };
    const room_data* const room_table[4] = { &room_office_day, &room_office_night, &room_office_dawn, &room_hall };
    const bn::bg_palette_item* const palette_table[4] = {
        &bn::bg_palette_items::office_palette, &bn::bg_palette_items::office_night_palette,
        &bn::bg_palette_items::office_dawn_palette, &bn::bg_palette_items::hall_palette };
    const char* const slide_titles[PITCH_SLIDES] = { "Problem", "Demo", "Arkiv", "World ID", "Ask" };
    const int window_x[2] = { WINDOW1_X, WINDOW3_X };
    const int window_y[2] = { WINDOW1_Y, WINDOW3_Y };

    // Butano (centre-origin) position of a w x h sprite whose top-left lands on screen pixel (x, y).
    bn::fixed_point top_left(int x, int y, int w, int h)
    {
        return bn::fixed_point(x + w / 2 - screen_w / 2, y + h / 2 - screen_h / 2);
    }

    void two_digits(bn::istring& out, int value)
    {
        if(value < 10)
        {
            out.push_back('0');
        }
        out.append(bn::to_string<8>(value));
    }

    // mm:ss.ff, ff in frames (60 to the second)
    void append_time(bn::istring& out, uint32_t frames)
    {
        two_digits(out, int(frames / 3600));
        out.push_back(':');
        two_digits(out, int(frames / 60 % 60));
        out.push_back('.');
        two_digits(out, int(frames % 60));
    }
}

void text_line::show(bn::sprite_text_generator& generator, int x, int y, const bn::istring& text)
{
    if(text == _text && x == _x && y == _y)
    {
        return;
    }
    if(text_budget <= 0)
    {
        return;                                    // over budget: this line catches up next frame
    }
    --text_budget;
    _sprites.clear();
    _text = text;
    _x = x;
    _y = y;
    if(! text.empty())
    {
        generator.generate(x, y, text, _sprites);
    }
}

room_bg::room_bg() :
    _map_item(_cells[0], bn::size(32, 32)),
    _tiles(bn::regular_bg_tiles_ptr::allocate(STREAM_SLOTS * 2, bn::bpp_mode::BPP_8, false)),
    _map(bn::regular_bg_map_ptr::create(_map_item, _tiles, bn::bg_palette_items::office_palette.create_palette())),
    _bg(bn::regular_bg_ptr::create(_map)),
    _src(&room_office_day)
{
    for(bn::regular_bg_map_cell& cell : _cells)
    {
        cell = 0;
    }
    stream_init(&_stream, _src->w_cells, _src->h_cells);
    _bg.set_priority(3);
}

void room_bg::use_room(const room_data& room)
{
    _src = &room;
    stream_init(&_stream, room.w_cells, room.h_cells);
}

void room_bg::set_palette(const bn::bg_palette_item& palette)
{
    // An 8 bpp background owns the whole palette RAM, so there is no room for a second 8 bpp palette to switch
    // to: recolour the one in use instead.
    bn::bg_palette_ptr in_use = _map.palette();
    in_use.set_colors(palette);
}

void room_bg::show(int cam_x, int cam_y, int budget)
{
    stream_update(&_stream, int16_t(cam_x), int16_t(cam_y), &_writes, uint16_t(budget));
    if(_writes.count)
    {
        bn::span<bn::tile> vram = *_tiles.vram();
        const bn::tile* src = reinterpret_cast<const bn::tile*>(_src->tiles);
        for(int i = 0; i < _writes.count; ++i)
        {
            int slot = _writes.slot[i];
            int tile = _src->map[_writes.cell[i]];
            vram[slot * 2] = src[tile * 2];
            vram[slot * 2 + 1] = src[tile * 2 + 1];
            bn::regular_bg_map_cell_info info;
            info.set_tile_index(slot);
            _cells[_writes.map_index[i]] = info.cell();
        }
        _map.reload_cells_ref();
    }
    // A 256 x 256 background at Butano position (8, 48) shows its pixel (0, 0) at the screen's top-left.
    _bg.set_position(8 - (cam_x & 255), 48 - (cam_y & 255));
}

view::view() :
    _player_top(bn::sprite_items::player_top.create_sprite(0, 0)),
    _player_bottom(bn::sprite_items::player_bottom.create_sprite(0, 0)),
    _ghost_top(bn::sprite_items::player_top.create_sprite(0, 0)),         // frame 0 shares the player's tiles
    _ghost_bottom(bn::sprite_items::player_bottom.create_sprite(0, 0)),
    _cup(bn::sprite_items::icons.create_sprite(0, 0, ICON_CHAI)),
    _arrow(bn::sprite_items::icons.create_sprite(0, 0, ICON_ARROW_DOWN)),
    _pill(bn::sprite_items::pill.create_sprite(0, 0)),
    _spark(bn::sprite_items::spark.create_sprite(0, 0)),
    _pizza(bn::sprite_items::pizza.create_sprite(0, 0)),
    _commit_meter(bn::sprite_items::meter.create_sprite(0, 0)),
    _gate(bn::sprite_items::gate.create_sprite(0, 0)),
    _slide_key(bn::sprite_items::icons.create_sprite(0, 0, ICON_BTN_A)),
    _small(common::variable_8x8_sprite_font),
    _big(common::variable_8x16_sprite_font)
{
    for(bn::sprite_ptr* s : { &_player_top, &_player_bottom, &_ghost_top, &_ghost_bottom, &_cup, &_spark, &_pizza,
                              &_gate })
    {
        s->set_bg_priority(1);
    }
    for(bn::sprite_ptr* s : { &_ghost_top, &_ghost_bottom })
    {
        s->set_visible(false);
        s->set_blending_enabled(true);             // half transparent (the spotlight uses the same alpha)
    }
    bn::blending::set_transparency_alpha(0.5);
    for(bn::sprite_ptr* s : { &_arrow, &_pill, &_commit_meter, &_slide_key })
    {
        s->set_bg_priority(0);
    }
    for(bn::sprite_ptr* s : { &_arrow, &_pill, &_commit_meter, &_spark, &_pizza, &_gate, &_slide_key })
    {
        s->set_visible(false);
    }
    _commit_meter.set_z_order(-1);                 // over the pill
    _make_devs();
    for(int i = 0; i < DEVS; ++i)
    {
        bn::sprite_ptr meter = bn::sprite_items::meter.create_sprite(0, 0);
        meter.set_bg_priority(1);
        _meters.push_back(meter);
        bn::sprite_ptr bubble = bn::sprite_items::icons.create_sprite(0, 0, ICON_BUBBLE);
        bubble.set_bg_priority(1);
        _bubbles.push_back(bubble);
    }
    for(int i = 0; i < MAX_BUGS; ++i)
    {
        bn::sprite_ptr bug = bn::sprite_items::bug.create_sprite(0, 0);
        bug.set_bg_priority(1);
        bug.set_visible(false);
        _bugs.push_back(bug);
    }
    for(int i = 0; i < 2; ++i)
    {
        bn::sprite_ptr rain = bn::sprite_items::rain.create_sprite(0, 0);
        rain.set_bg_priority(2);                   // on the window, behind the devs
        rain.set_visible(false);
        _rain.push_back(rain);
    }
    for(int i = 0; i < 4; ++i)
    {
        bn::sprite_ptr strip = bn::sprite_items::hud_strip.create_sprite(top_left(i * 64, 128, 64, 32));
        strip.set_bg_priority(0);
        strip.set_z_order(10);
        _strip.push_back(strip);
    }
    for(int i = 0; i < 8; ++i)
    {
        bn::sprite_ptr segment = bn::sprite_items::hud_bar.create_sprite(top_left(140 + 8 * i, 150, 8, 8), 0);
        segment.set_bg_priority(0);
        _bar.push_back(segment);
    }
    _small.set_bg_priority(0);
    _big.set_bg_priority(0);
    _cam_max_x = room_office_day.w - screen_w;
    _cam_max_y = room_office_day.h - screen_h;
    _follow(START_X, START_Y, true);
    _room.show(_cam_x, _cam_y, STREAM_MAX_WRITES);
}

void view::_make_devs()
{
    for(int i = 0; i < DEVS; ++i)
    {
        bn::sprite_ptr dev = dev_items[i]->create_sprite(0, 0);
        dev.set_bg_priority(2);
        _devs.push_back(dev);
    }
}

int view::_wanted_room(int scene) const
{
    int act = rules_act();
    if(scene == SC_TITLE || scene == SC_HOWTO) return SHOWN_DAY;
    if(scene == SC_NIGHTFALL) return rules_nightfall() <= 80 ? SHOWN_NIGHT : SHOWN_DAY;
    if(scene == SC_DEMODAY) return rules_demoday() <= 80 ? SHOWN_DAWN : SHOWN_NIGHT;
    if(act == 3) return rules_room() == ROOM_HALL ? SHOWN_HALL : SHOWN_DAWN;
    return act == 2 ? SHOWN_NIGHT : SHOWN_DAY;
}

// Every room change goes through here, on a black screen: the new image and palette, the camera limits and a
// snap to where the camera should be, a fast refill, and the room's own sprites (devs in the office, the crowd
// in the hall: both at once would not fit sprite memory).
void view::_swap_room(int room)
{
    const room_data& data = *room_table[room];
    _room.use_room(data);
    _room.set_palette(*palette_table[room]);
    _shown = room;
    _cam_max_x = data.w - screen_w;
    _cam_max_y = data.h - screen_h;
    int scene = rules_scene();
    if(scene == SC_TITLE || scene == SC_HOWTO)
    {
        _follow(START_X, START_Y, true);
    }
    else
    {
        _follow(rules_px(), rules_py(), true);
    }
    _refill_left = refill_frames;
    if(room == SHOWN_HALL)
    {
        _devs.clear();
        _crowd.clear();
        for(int k = 0; k < HALL_CROWD_N; ++k)
        {
            bn::sprite_ptr person = crowd_items[k % 3]->create_sprite(0, 0);
            person.set_bg_priority(1);
            person.set_visible(false);
            _crowd.push_back(person);
        }
    }
    else
    {
        _crowd.clear();                            // the devs come back next frame (see update): one big upload a frame
    }
}

void view::_follow(int px, int py, bool snap)
{
    int want_x = _cam_x;
    int want_y = _cam_y;
    if(snap)
    {
        want_x = px - screen_w / 2;
        want_y = py - (dead_top + dead_bottom) / 2;
    }
    else
    {
        if(px - want_x < dead_left) want_x = px - dead_left;
        if(px - want_x > dead_right) want_x = px - dead_right;
        if(py - want_y < dead_top) want_y = py - dead_top;
        if(py - want_y > dead_bottom) want_y = py - dead_bottom;
    }
    want_x = bn::clamp(want_x, 0, _cam_max_x);
    want_y = bn::clamp(want_y, 0, _cam_max_y);
    if(snap)
    {
        _cam_x = want_x;
        _cam_y = want_y;
        return;
    }
    _cam_x += bn::clamp(want_x - _cam_x, -cam_step, cam_step);
    _cam_y += bn::clamp(want_y - _cam_y, -cam_step, cam_step);
}

void view::update()
{
    ++_tick;
    text_budget = text_lines_per_frame;
    int scene = rules_scene();
    bool play = scene == SC_PLAY;
    if(scene == SC_CLEAR && ! _recorded)
    {
        best::record(rules_run_frames());          // the timer stopped on the last press: this is the run's time
        _recorded = true;
        _confetti_left = confetti_frames;
        _shake_left = shake_frames;
    }
    else if(scene != SC_CLEAR)
    {
        _recorded = false;
    }
    int wanted = _wanted_room(scene);
    if(wanted != _shown)
    {
        _swap_room(wanted);
    }
    else if(_devs.empty() && _shown != SHOWN_HALL)
    {
        _make_devs();
    }
    bool transition = scene == SC_NIGHTFALL || scene == SC_DEMODAY || scene == SC_WALKOUT;
    if(play && rules_slide() != 0)
    {
        _follow(HALL_SCREEN_X - 60, HALL_SCREEN_Y + 30, false);    // the pitch: frame the stage screen and the player
    }
    else if(play || scene == SC_CLEAR || scene == SC_MISSED)
    {
        _follow(rules_px(), rules_py(), false);
    }
    else if(! transition)
    {
        _follow(START_X, START_Y, false);           // glide back to the opening view, one tile per frame
    }
    int shake = _shake_left > 0 ? shake_offsets[shake_frames - _shake_left] : 0;
    if(_shake_left > 0)
    {
        --_shake_left;
    }
    int steady_cam_x = _cam_x;
    _cam_x += shake;                                 // everything drawn in the room shakes with it this frame
    int budget = STREAM_MAX_WRITES;
    bn::fixed fade = 0;
    if(scene == SC_NIGHTFALL || scene == SC_DEMODAY)
    {
        int left = scene == SC_NIGHTFALL ? rules_nightfall() : rules_demoday();
        fade = left > 80 ? bn::fixed(NIGHTFALL_FRAMES - left) / 40 : left <= 40 ? bn::fixed(left) / 40 : bn::fixed(1);
        budget = refill_writes;
    }
    else if(scene == SC_WALKOUT)
    {
        int left = rules_walkout();
        fade = left > WALKOUT_FRAMES / 2 ? bn::fixed(WALKOUT_FRAMES - left) / (WALKOUT_FRAMES / 2)
                                         : bn::fixed(left) / (WALKOUT_FRAMES / 2);
        budget = refill_writes;
    }
    else if(! play || rules_paused())
    {
        fade = scene == SC_HOWTO ? bn::fixed(0.75) : bn::fixed(0.5);
    }
    if(_refill_left > 0)
    {
        --_refill_left;
        budget = refill_writes;
        if(! play)
        {
            fade = 1;                               // in play (a quick restart) the refill streams in the open
        }
    }
    bn::bg_palettes::set_fade(bn::color(0, 0, 0), bn::min(fade, bn::fixed(1)));
    _room.show(_cam_x, _cam_y, budget);
    if(! _devs.empty())
    {
        _update_devs(play);
        for(bn::sprite_ptr& dev : _devs)
        {
            dev.set_visible(! transition && (_refill_left == 0 || play));
        }
    }
    else
    {
        for(int i = 0; i < DEVS; ++i)
        {
            _meters[i].set_visible(false);
            _bubbles[i].set_visible(false);
        }
    }
    _update_player(play);
    _update_act_two(play, scene);
    _update_hall(play, scene);
    _update_pointers(play);
    _update_hud(play);
    _update_screens(scene);
    _update_card(scene);
    _update_confetti();
    _cam_x = steady_cam_x;
}

void view::_update_hall(bool play, int scene)
{
    bool show = scene == SC_PLAY || scene == SC_CLEAR || scene == SC_MISSED;
    int slide_now = rules_slide();                 // stays 6 after the last slide, 0 in a new run
    if(slide_now > _last_slide && _last_slide >= 1)
    {
        _flash_left = flash_frames;                // a correct slide: flash the screen, the crowd cheers
        _cheer_left = cheer_frames;
    }
    _last_slide = slide_now;
    for(int k = 0; k < _crowd.size(); ++k)
    {
        bn::sprite_ptr& person = _crowd[k];
        int x = rules_crowd_x(uint8_t(k));
        int y = rules_crowd_y(uint8_t(k));
        bool still = rules_crowd_standing(uint8_t(k)) || ! play;                        // no walk cycle in place
        int step = still ? 0 : (_tick / 4 + k) % CROWD_WALK_N;
        int hop = _cheer_left > 0 && rules_crowd_gathered(uint8_t(k)) && (_cheer_left / 4) % 2 ? 2 : 0;
        person.set_visible(show);
        person.set_tiles(crowd_items[k % 3]->tiles_item(), rules_crowd_facing(uint8_t(k)) * CROWD_WALK_N + step);
        person.set_position(top_left(x - _cam_x - CROWD_FEET_X, y - _cam_y - CROWD_FEET_Y - hop, 64, 64));
        person.set_z_order(-y);                    // lower on the screen is nearer: drawn over
    }
    _gate.set_visible(_shown == SHOWN_HALL && show && ! rules_verified());
    _gate.set_position(top_left(HALL_GATE_X - 16 - _cam_x, HALL_GATE_Y - 12 - _cam_y, 32, 16));
    int slide = play ? rules_slide() : 0;
    bool pitching = slide >= 1 && slide <= PITCH_SLIDES;
    int sx = HALL_SCREEN_X - _cam_x;
    int sy = HALL_SCREEN_Y - _cam_y;
    bn::string<64> title;
    if(pitching)
    {
        title = slide_titles[slide - 1];
    }
    _big.set_center_alignment();
    _slide.show(_big, pitching ? sx - screen_w / 2 : 0, pitching ? sy - 10 - screen_h / 2 : 0, title);
    int key = rules_pitch_key();
    _slide_key.set_visible(pitching && ! (rules_stumble() && (_tick / 8) % 2));
    _slide_key.set_tiles(bn::sprite_items::icons.tiles_item(),
                         key == BTN_A ? ICON_BTN_A : key == BTN_B ? ICON_BTN_B : key == BTN_RIGHT ? ICON_ARROW_RIGHT
                                                                                            : ICON_ARROW_UP);
    _slide_key.set_position(top_left(sx - 8, sy + 2, 16, 16));

    if(_flash_left > 0)
    {
        if(! _flash)
        {
            _flash = bn::sprite_items::flash.create_sprite(0, 0);
            _flash->set_bg_priority(0);
            _flash->set_z_order(3);                // under the slide's text
        }
        _flash->set_position(top_left(sx - 32, sy - 16, 64, 32));
        --_flash_left;
    }
    else
    {
        _flash.reset();
    }
    if(_cheer_left > 0)
    {
        --_cheer_left;
    }
    if(pitching)                                   // the spotlight: a half-transparent pool under the pitcher
    {
        if(! _spot)
        {
            _spot = bn::sprite_items::spot.create_sprite(0, 0);
            _spot->set_bg_priority(2);             // over the room, under the player
            _spot->set_blending_enabled(true);
            bn::blending::set_transparency_alpha(0.5);
        }
        _spot->set_position(top_left(rules_px() - 32 - _cam_x, rules_py() - 16 - _cam_y, 64, 32));
    }
    else
    {
        _spot.reset();
    }
}

void view::_update_confetti()
{
    if(_confetti_left <= 0)
    {
        _confetti.clear();
        return;
    }
    int t = confetti_frames - _confetti_left;
    if(_confetti.empty())
    {
        for(int i = 0; i < 16; ++i)
        {
            bn::sprite_ptr piece = bn::sprite_items::confetti.create_sprite(0, 0, i % 4);
            piece.set_bg_priority(0);
            piece.set_z_order(1);
            _confetti.push_back(piece);
        }
    }
    for(int i = 0; i < 16; ++i)                    // a fixed pattern: each piece its own speed and drift
    {
        int x = 8 + 14 * i + ((i % 3) - 1) * t / 8;
        int y = -8 - (i * 23) % 64 + (1 + i % 3) * t;
        _confetti[i].set_tiles(bn::sprite_items::confetti.tiles_item(), (i + t / 6) % 4);
        _confetti[i].set_position(top_left(x, y, 8, 8));
    }
    --_confetti_left;
}

void view::_update_card(int scene)
{
    bool card = (scene == SC_CLEAR && rules_clear_frames() >= SHIPPED_FRAMES) || scene == SC_MISSED;
    if(! card)
    {
        _card.clear();
        _grade.reset();
        _card_step = 0;
        return;
    }
    // Built over several frames: Butano frees a destroyed sprite's tiles only at the next frame, so the crowd
    // goes first (the card covers it and needs its sprite memory), then one row of pieces a frame (creating all
    // twelve at once overran the frame), then the grade.
    if(_card_step == 0)
    {
        _crowd.clear();
        ++_card_step;
        return;
    }
    if(_card_step <= 4)
    {
        int row = _card_step - 1;
        int slice_row = row == 0 ? 0 : row == 3 ? 2 : 1;
        for(int col = 0; col < 3; ++col)
        {
            bn::sprite_ptr piece = bn::sprite_items::card.create_sprite(
                top_left(card_x + 64 * col, card_y + 32 * row, 64, 32), slice_row * 3 + col);
            piece.set_bg_priority(0);
            piece.set_z_order(5);                  // under the card's text
            _card.push_back(piece);
        }
        ++_card_step;
        return;
    }
    if(! _grade)
    {
        int grade = rules_grade();
        int frame = grade == 'S' ? 0 : grade == 'A' ? 1 : grade == 'B' ? 2 : grade == 'C' ? 3 : 4;
        _grade = bn::sprite_items::grade.create_sprite(top_left(card_x + 192 - 40, card_y + 6, 32, 32), frame);
        _grade->set_bg_priority(0);
    }
}

void view::_update_devs(bool play)
{
    for(int i = 0; i < DEVS; ++i)
    {
        int energy = rules_energy(uint8_t(i));
        bool dawn = _shown == SHOWN_DAWN;                         // the build is done: the team has crashed
        bool tired = energy == 0 || dawn;
        int frame = tired ? DEV_TIRED : DEV_TYPE + (_tick / 8 + i) % DEV_TYPE_N;
        int x = dev_x[i] - _cam_x;
        int y = dev_y[i] - _cam_y;
        _devs[i].set_tiles(dev_items[i]->tiles_item(), frame);
        _devs[i].set_position(top_left(x - DEV_FEET_X, y - DEV_FEET_Y, 64, 64));
        _meters[i].set_visible(play && ! tired);
        if(dawn)
        {
            _bubbles[i].set_visible(false);
            continue;
        }
        _meters[i].set_tiles(bn::sprite_items::meter.tiles_item(), bn::min(energy * METER_FRAMES / 256, METER_FRAMES - 1));
        _meters[i].set_position(top_left(x - 16, y - 6, 32, 8));      // over the laptop: on screen whenever the dev is
        _bubbles[i].set_visible(play && tired && (_tick / 16) % 2 == 0);
        _bubbles[i].set_position(top_left(x - 8, y - head_above_dev - 18, 16, 16));
    }
}

void view::_update_player(bool play)
{
    _player_top.set_visible(play);
    _player_bottom.set_visible(play);
    bool carry = play && rules_carrying() != ITEM_NONE;
    _cup.set_visible(carry);
    if(! play)
    {
        _update_ghost(false, 0);
        return;
    }
    int base;
    int count;
    int rate;
    if(rules_moving())
    {
        base = carry ? PLAYER_CARRY_WALK : PLAYER_WALK;
        count = PLAYER_WALK_N;
        rate = 4;
    }
    else
    {
        base = carry ? PLAYER_CARRY_IDLE : PLAYER_IDLE;
        count = PLAYER_IDLE_N;
        rate = 12;
    }
    int step = base + (_tick / rate) % count;
    int frame = rules_facing() * PLAYER_FRAMES_PER_DIR + step;
    int x = rules_px() - _cam_x - SPRITE_FEET_X;
    int y = rules_py() - _cam_y - SPRITE_FEET_Y;
    _player_top.set_tiles(bn::sprite_items::player_top.tiles_item(), frame);
    _player_bottom.set_tiles(bn::sprite_items::player_bottom.tiles_item(), frame);
    _player_top.set_position(top_left(x, y, 64, 64));
    _player_bottom.set_position(top_left(x, y + PLAYER_TOP_H, 64, 32));
    int feet = rules_py();
    _player_top.set_z_order(-feet);
    _player_bottom.set_z_order(-feet);
    _update_ghost(true, step);                 // after the player's tiles: a hidden ghost holds them
    _cup.set_z_order(-feet - 1);
    if(carry)
    {
        _cup.set_tiles(bn::sprite_items::icons.tiles_item(), rules_carrying() == ITEM_LAPTOP ? ICON_LAPTOP : ICON_CHAI);
        _cup.set_position(top_left(rules_px() - _cam_x + player_hand_x[frame] - 8,
                                   rules_py() - _cam_y + player_hand_y[frame] - 11, 16, 16));
    }
}

void view::set_ghost(const ac_ghost_pt* ghost)
{
    _has_ghost = ghost != nullptr;
    if(ghost)
    {
        _ghost = *ghost;
    }
}

void view::_update_ghost(bool play, int step)
{
    // The saved run's player, in the player's current animation step but facing its own way; only in play and in
    // the player's room (flags). A facing the player also has shares the player's tiles.
    constexpr int facings = bn::sprite_items::player_top.tiles_item().graphics_count() / PLAYER_FRAMES_PER_DIR;
    _ghost_shown = play && _has_ghost && (_ghost.flags & ~AC_GHOST_PLAY) == rules_room() && _ghost.angle < facings;
    _ghost_top.set_visible(_ghost_shown);
    _ghost_bottom.set_visible(_ghost_shown);
    if(play)
    {
        // The player's own sort layer, shown or not: Butano has only 16 (bg priority, z order) layers and the
        // results card needs the rest. Within a layer Butano draws the sprite (re)inserted last in front, and a
        // z order change reinserts, so this call alone would put the ghost in front of the player. The GBA blends a
        // half-transparent sprite only with the backgrounds, never with another sprite: in front, the ghost would
        // hide the player where they overlap and the live player would look half transparent. So the ghost is sent
        // to the back of the layer every frame (after the z order, which may have moved it to the front): the
        // player stays solid, and the ghost still blends with the room wherever the player does not cover it.
        // tests/test_arcade.py test_the_player_stays_solid_over_its_ghost checks it.
        _ghost_top.set_z_order(-rules_py());
        _ghost_bottom.set_z_order(-rules_py());
        _ghost_top.put_below();
        _ghost_bottom.put_below();
    }
    if(! _ghost_shown)
    {
        // Hidden, it holds the player's own tiles: frames of its own would cost 96 sprite tiles, which the results
        // card needs.
        _ghost_top.set_tiles(_player_top.tiles());
        _ghost_bottom.set_tiles(_player_bottom.tiles());
        return;
    }
    int frame = _ghost.angle * PLAYER_FRAMES_PER_DIR + step;
    int x = _ghost.x - _cam_x - SPRITE_FEET_X;
    int y = _ghost.y - _cam_y - SPRITE_FEET_Y;
    _ghost_top.set_tiles(bn::sprite_items::player_top.tiles_item(), frame);
    _ghost_bottom.set_tiles(bn::sprite_items::player_bottom.tiles_item(), frame);
    _ghost_top.set_position(top_left(x, y, 64, 64));
    _ghost_bottom.set_position(top_left(x, y + PLAYER_TOP_H, 64, 32));
}

void view::_update_act_two(bool play, int scene)
{
    for(int i = 0; i < MAX_BUGS; ++i)
    {
        if(scene != SC_PLAY)
        {
            _bug_was_on[i] = false;                 // a new run must not open with squashed bugs
            _squash_left[i] = 0;
        }
        bool on = rules_bug_on(uint8_t(i));
        if(on)
        {
            _squash_x[i] = rules_bug_x(uint8_t(i));
            _squash_y[i] = rules_bug_y(uint8_t(i));
            _squash_left[i] = 0;
        }
        else if(_bug_was_on[i] && play && scene == SC_PLAY)
        {
            _squash_left[i] = squash_frames;        // gone during play: stomped, leave it squashed for a moment
        }
        _bug_was_on[i] = on;
        bn::sprite_ptr& bug = _bugs[i];
        bug.set_visible(play && (on || _squash_left[i] > 0));
        if(! bug.visible())
        {
            continue;
        }
        int frame = BUG_FRAMES - 1;
        if(on)
        {
            frame = rules_bug_sitting(uint8_t(i)) ? (_tick / 16) % 2 : (_tick / 8) % 2;    // chewing, or crawling
        }
        else
        {
            --_squash_left[i];
        }
        bug.set_tiles(bn::sprite_items::bug.tiles_item(), frame);
        bug.set_position(top_left(_squash_x[i] - _cam_x - 8, _squash_y[i] - _cam_y - 12, 16, 16));
    }

    _spark.set_visible(play && rules_router_fried());
    if(_spark.visible())
    {
        _spark.set_tiles(bn::sprite_items::spark.tiles_item(), (_tick / 4) % SPARK_FRAMES);
        _spark.set_position(top_left(ROUTER_X + router_top_dx - 8 - _cam_x, ROUTER_Y + router_top_dy - 10 - _cam_y, 16, 16));
    }

    _pizza.set_visible(play && rules_pizza() == 1);
    _pizza.set_position(top_left(DOOR_X - 16 - _cam_x, DOOR_Y - 30 - _cam_y, 32, 32));

    bool rain = _shown == SHOWN_NIGHT && (scene == SC_PLAY || scene == SC_CLEAR || scene == SC_MISSED);
    for(int i = 0; i < 2; ++i)
    {
        _rain[i].set_visible(rain);
        _rain[i].set_tiles(bn::sprite_items::rain.tiles_item(), (_tick / 6 + i) % RAIN_FRAMES);
        _rain[i].set_position(top_left(window_x[i] - 8 - _cam_x, window_y[i] - 16 - _cam_y, 16, 32));
    }

    bn::string<64> message;
    int msg = play ? rules_message() : 0;
    if(msg == MSG_SAVED) message = "Build saved to Arkiv";
    else if(msg == MSG_PAID) message = "Paid with Arc";
    else if(msg == MSG_ROLLBACK) message = "Rolled back to your last commit";
    else if(msg == MSG_VERIFIED) message = "Verified human";
    else if(msg == MSG_STUMBLE) message = "Uh...";
    _big.set_center_alignment();
    _message.show(_big, 0, -48, message);
}

void view::_update_pointers(bool play)
{
    int hint = play ? rules_hint() : HINT_NONE;
    bn::string<64> prompt;
    _pill.set_visible(hint != HINT_NONE);
    _commit_meter.set_visible(hint == HINT_COMMIT && rules_commit_hold() > 0 && rules_commit_hold() < COMMIT_FRAMES);
    if(hint != HINT_NONE)
    {
        int px = rules_px() - _cam_x;
        int feet = rules_py() - _cam_y;
        int py = feet - head_above_player - 18;                     // the pill's 16 visible rows, above the head
        if(py < 2)
        {
            py = feet + 4;                                          // no room above (the camera keeps the feet
        }                                                           // high near the counter): show it below
        py = bn::min(py, play_h - 26);                              // room for the commit meter under it
        _pill.set_position(top_left(px - 32, py - 8, 64, 32));      // the pill is drawn in rows 8-23 of its frame
        const char* const texts[10] = { "", "Take chai", "Give chai", "Stomp bug", "Fix router", "Pay (Arc)", "Hold A",
                                        "Take laptop", "Scan (World)", "Pitch" };
        prompt = texts[hint];
        bool held_done = hint == HINT_COMMIT && rules_commit_hold() >= COMMIT_FRAMES;
        if(held_done)
        {
            prompt = "Release A";                                   // a commit finished: holding on does nothing
        }
        _small.set_left_alignment();
        _prompt_text.show(_small, px - 32 + 13 - screen_w / 2, py + 8 - screen_h / 2, prompt);
        if(_commit_meter.visible())
        {
            int frame = bn::min(rules_commit_hold() * (METER_FRAMES - 1) / COMMIT_FRAMES, METER_FRAMES - 1);
            _commit_meter.set_tiles(bn::sprite_items::meter.tiles_item(), frame);
            _commit_meter.set_position(top_left(px - 16, py + 17, 32, 8));    // just under the pill
        }
    }
    else
    {
        _prompt_text.show(_small, 0, 0, prompt);
    }
    bool pitching = rules_slide() != 0;
    _arrow.set_visible(play && hint == HINT_NONE && ! pitching);
    if(! play || hint != HINT_NONE || pitching)
    {
        return;
    }
    int target = rules_target();
    int tx;
    int ty;
    if(target == TARGET_LAPTOP)
    {
        tx = BUGDESK0_X;
        ty = BUGDESK0_Y - 14;
    }
    else if(target == TARGET_ORB)
    {
        tx = HALL_ORBTOP_X;
        ty = HALL_ORBTOP_Y - 12;
    }
    else if(target == TARGET_STAGE)
    {
        tx = HALL_STAGE_X;
        ty = HALL_STAGE_Y - 50;
    }
    else if(target >= TARGET_BUG)
    {
        tx = rules_bug_x(uint8_t(target - TARGET_BUG));
        ty = rules_bug_y(uint8_t(target - TARGET_BUG)) - 14;
    }
    else if(target == TARGET_ROUTER)
    {
        tx = ROUTER_X + router_top_dx;
        ty = ROUTER_Y + router_top_dy - 14;
    }
    else if(target == TARGET_DOOR)
    {
        tx = DOOR_X;
        ty = DOOR_Y - 34;
    }
    else if(target == TARGET_SHELF)
    {
        tx = SHELF_X;
        ty = SHELF_Y - 50;
    }
    else if(target == TARGET_COUNTER)
    {
        tx = COUNTER_X - 12;
        ty = COUNTER_Y - 30;
    }
    else
    {
        tx = dev_x[target - TARGET_DEV];
        ty = dev_y[target - TARGET_DEV] - head_above_dev - 22;
    }
    tx -= _cam_x;
    ty -= _cam_y;
    int bounce = (_tick / 6) % 4;
    bounce = bounce == 3 ? 1 : bounce;
    int frame = ICON_ARROW_DOWN;
    if(tx < 8) { tx = 8; frame = ICON_ARROW_LEFT; }
    else if(tx > screen_w - 8) { tx = screen_w - 8; frame = ICON_ARROW_RIGHT; }
    if(ty < 8) { ty = 8; frame = frame == ICON_ARROW_DOWN ? ICON_ARROW_UP : frame; }
    else if(ty > play_h - 16) { ty = play_h - 16; }
    _arrow.set_tiles(bn::sprite_items::icons.tiles_item(), frame);
    _arrow.set_position(top_left(tx - 8, ty - 8 + (frame == ICON_ARROW_DOWN ? bounce * 2 : 0), 16, 16));
}

void view::_update_hud(bool play)
{
    bn::string<64> objective;
    bn::string<64> act;
    bn::string<64> clock;
    bn::string<64> percent;
    int filled = 0;
    for(bn::sprite_ptr& s : _strip)
    {
        s.set_visible(play);
    }
    if(play)
    {
        int target = rules_target();
        if(rules_act() == 3)
        {
            if(rules_stun()) objective = "Watch the crowd!";
            else if(rules_slide()) objective = "Pitch: press the button on the slide";
            else if(rules_room() == ROOM_OFFICE)
                objective = rules_carrying() == ITEM_LAPTOP ? "Take it out the door to the hall" : "Grab Arjun's laptop";
            else objective = rules_verified() ? "Get on stage and pitch!" : "Get verified at the World orb";
        }
        else if(rules_router_fried())
        {
            objective = "Router down! Reset it";
        }
        else if(target >= TARGET_BUG && target < TARGET_BUG + MAX_BUGS)
        {
            int i = target - TARGET_BUG;
            if(rules_bug_sitting(uint8_t(i)))
            {
                objective = "Bug on ";
                objective.append(dev_names[rules_bug_desk(uint8_t(i))]);
                objective.append("'s desk! Stomp it");
            }
            else
            {
                objective = "Bug loose! Stomp it";
            }
        }
        else if(rules_pizza() == 1)
        {
            objective = "Pizza's here! Pay at the door";
        }
        else if(rules_carrying() != ITEM_NONE && target >= TARGET_DEV && target < TARGET_DEV + DEVS)
        {
            objective = "Give ";
            objective.append(dev_names[target - TARGET_DEV]);
            objective.append(" the chai");
        }
        else if(target == TARGET_SHELF)
        {
            objective = "Commit to Arkiv: hold A at the shelf";
        }
        else if(! rules_clock_running())
        {
            objective = "Clock starts with your first chai!";
        }
        else
        {
            int tired = 0;
            for(int i = 1; i < DEVS; ++i)
            {
                if(rules_energy(uint8_t(i)) < rules_energy(uint8_t(tired))) tired = i;
            }
            if(rules_energy(uint8_t(tired)) < 64)
            {
                objective = dev_names[tired];
                objective.append(" is fading! Grab chai at the counter");
            }
            else
            {
                objective = "Grab chai at the counter";
            }
        }
        act = rules_act() == 3 ? "ACT 3 DEMO" : rules_act() == 2 ? "ACT 2 MIDNIGHT" : "ACT 1 BUILD";
        two_digits(clock, rules_hour());
        clock.push_back(':');
        two_digits(clock, rules_hour_frames() * 60 / FRAMES_PER_HOUR);
        percent.append(bn::to_string<8>(rules_progress() / 10));
        percent.push_back('%');
        filled = rules_progress() * 64 / PROGRESS_MAX;
    }
    _small.set_left_alignment();
    _objective.show(_small, 6 - screen_w / 2, 141 - screen_h / 2, objective);
    _act.show(_small, 6 - screen_w / 2, 153 - screen_h / 2, act);
    _clock.show(_small, 108 - screen_w / 2, 153 - screen_h / 2, clock);
    _percent.show(_small, 210 - screen_w / 2, 153 - screen_h / 2, percent);
    for(int i = 0; i < 8; ++i)
    {
        _bar[i].set_visible(play);
        _bar[i].set_tiles(bn::sprite_items::hud_bar.tiles_item(), bn::clamp(filled - 8 * i, 0, 8));
    }
}

void view::_update_screens(int scene)
{
    bn::string<64> headline;
    bn::string<64> lines[8];
    int line_y[8] = { 20, 40, 0, 0, 0, 0, 0, 0 };  // below the headline
    bool blink = (_tick / 32) % 2 == 0;
    // The logos exist only on the screens that show them: hidden sprites still hold their tiles, and the hall
    // (six attendees) leaves no sprite memory to spare for them.
    bool title_logo = scene == SC_TITLE;
    bool small_logo = scene == SC_CLEAR && rules_clear_frames() < SHIPPED_FRAMES;
    _title_frames = title_logo ? _title_frames + 1 : 0;
    // One 64 x 64 piece a frame (three at once overran a frame), and only once the screen before has let go of
    // its text (four lines a frame) and card, so the two never hold sprite memory together.
    if(title_logo && _title_frames > 4 && _logo.size() < 3)
    {
        int i = _logo.size();
        bn::sprite_ptr part = bn::sprite_items::logo_title.create_sprite(top_left(24 + 64 * i, 6, 64, 64), i);
        part.set_bg_priority(0);
        _logo.push_back(part);
    }
    else if(! title_logo)
    {
        _logo.clear();
    }
    if(small_logo && _logo_small.empty())
    {
        for(int i = 0; i < 2; ++i)
        {
            bn::sprite_ptr part = bn::sprite_items::logo_small.create_sprite(top_left(106 + 64 * i, 2, 64, 32), i);
            part.set_bg_priority(0);
            _logo_small.push_back(part);
        }
    }
    else if(! small_logo)
    {
        _logo_small.clear();
    }
    int headline_y = -24;
    if(scene == SC_TITLE)
    {
        headline = "SHIP IT!";
        headline_y = 2;
        lines[0] = "36 hours. 3 devs. 1 demo.";
        if(blink) lines[1] = "PRESS START";
    }
    else if(scene == SC_HOWTO)
    {
        headline = "HOW TO PLAY";
        headline_y = -64;
        lines[0] = "D-PAD";
        lines[1] = "A";
        lines[2] = "B";
        lines[3] = "START";
        lines[4] = "Keep your 3 devs caffeinated.";
        lines[5] = "Fill the ship bar before 36:00.";
        lines[6] = "A   LET'S BUILD";
        lines[7] = "Night: stomp bugs, fix router, hold A to commit";
    }
    else if(scene == SC_PLAY && rules_paused())
    {
        headline = "PAUSED";
    }
    else if(scene == SC_NIGHTFALL)
    {
        int left = rules_nightfall();
        if(left <= 80 && left > 40)                 // on the black screen between the fades
        {
            headline = "NIGHT FALLS";
            lines[0] = "Act 1  ";
            append_time(lines[0], rules_split(1));
        }
    }
    else if(scene == SC_DEMODAY)
    {
        int left = rules_demoday();
        if(left <= 80 && left > 40)
        {
            headline = "DEMO DAY";
            lines[0] = "Act 2  ";
            append_time(lines[0], rules_split(2));
        }
    }
    else if(scene == SC_CLEAR || scene == SC_MISSED)
    {
        bool shipped = scene == SC_CLEAR;
        headline = shipped ? "SHIPPED!" : "MISSED THE DEADLINE";
        if(! shipped || rules_clear_frames() >= SHIPPED_FRAMES)       // the results card (drawn by _update_card)
        {
            headline_y = card_y + 14 - screen_h / 2;
            bn::string<64> times[4];
            const char* const labels[4] = { "Act 1", "Act 2", "Act 3", "Total" };
            for(int i = 0; i < 4; ++i)
            {
                uint32_t frames = i < 3 ? rules_split(uint8_t(i + 1)) : rules_run_frames();
                if(frames || i == 3)
                {
                    append_time(times[i], frames);
                }
                else
                {
                    times[i] = "--:--.--";                             // an act the run never finished
                }
            }
            bn::string<64> best_line;
            if(shipped && best::was_new())
            {
                best_line = best::had_best() ? (blink ? "NEW BEST!" : "") : "First run!";
            }
            else if(best::frames())
            {
                best_line = "Best  ";
                append_time(best_line, best::frames());
            }
            bn::string<64> deadline(shipped ? "Deadline met at " : "Out of time at ");
            two_digits(deadline, rules_hour());
            deadline.push_back(':');
            two_digits(deadline, rules_hour_frames() * 60 / FRAMES_PER_HOUR);
            _big.set_center_alignment();
            _headline.show(_big, -20, headline_y, headline);
            for(int i = 0; i < 4; ++i)
            {
                bn::string<64> label(labels[i]);
                int y = card_y + 46 + 12 * i - screen_h / 2;      // below the grade letter
                _small.set_left_alignment();
                _lines[i].show(_small, card_x + 20 - screen_w / 2, y, label);
                _small.set_right_alignment();
                _desc[i].show(_small, card_x + 172 - screen_w / 2, y, times[i]);
            }
            bn::string<64> press;
            if(blink) press = "PRESS START";
            bn::string<64> none;
            _small.set_center_alignment();
            _lines[4].show(_small, 0, card_y + 98 - screen_h / 2, best_line);
            _lines[5].show(_small, 0, card_y + 110 - screen_h / 2, deadline);
            _lines[6].show(_small, 0, card_y + 122 - screen_h / 2, press);
            _lines[7].show(_small, 0, 0, none);
            return;
        }
    }
    _big.set_center_alignment();
    _headline.show(_big, 0, headline_y, headline);
    if(scene == SC_HOWTO)
    {
        _small.set_left_alignment();
        const char* const what[4] = { "walk", "take chai / give chai", "dash", "pause" };
        for(int i = 0; i < 4; ++i)
        {
            bn::string<64> desc(what[i]);
            _lines[i].show(_small, 40 - screen_w / 2, -40 + 14 * i, lines[i]);
            _desc[i].show(_small, 96 - screen_w / 2, -40 + 14 * i, desc);
        }
        _small.set_center_alignment();
        _lines[4].show(_small, 0, 24, lines[4]);
        _lines[5].show(_small, 0, 36, lines[5]);
        _lines[7].show(_small, 0, 48, lines[7]);
        _lines[6].show(_small, 0, 64, lines[6]);
    }
    else
    {
        _small.set_center_alignment();
        for(int i = 0; i < 8; ++i)
        {
            _lines[i].show(_small, 0, lines[i].empty() ? 0 : headline_y + line_y[i], lines[i]);
        }
        for(text_line& d : _desc)
        {
            d.show(_small, 0, 0, lines[6]);        // empty outside the how-to card
        }
    }
}

}

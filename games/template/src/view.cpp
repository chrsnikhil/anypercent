#include "view.h"

#include "bn_bg_palettes.h"
#include "bn_blending.h"
#include "bn_color.h"
#include "bn_string.h"

#include "arcade_runtime.h"
#include "common_variable_8x8_sprite_font.h"
#include "bn_sprite_items_dot.h"

extern "C" {
#include "game.h"
#include "tuning.h"
}

namespace game
{

namespace
{
    constexpr const char* title = "TEMPLATE";      // new_game.sh replaces it with the ROM title

    // Butano places sprites by their centre, relative to the screen centre.
    bn::fixed_point top_left(int x, int y, int w, int h)
    {
        return bn::fixed_point(x - 120 + w / 2, y - 80 + h / 2);
    }

    // frames -> "S.HH" (seconds and hundredths).
    bn::string<16> time_text(uint32_t frames)
    {
        bn::string<16> s = bn::to_string<10>(frames / 60);
        uint32_t hundredths = (frames % 60) * 100 / 60;
        s.push_back('.');
        s.push_back(char('0' + hundredths / 10));
        s.push_back(char('0' + hundredths % 10));
        return s;
    }
}

view::view() :
    _text(common::variable_8x8_sprite_font),
    _dot(bn::sprite_items::dot.create_sprite(0, 0, 0)),
    _goal(bn::sprite_items::dot.create_sprite(0, 0, 1)),
    _ghost(bn::sprite_items::dot.create_sprite(0, 0, 0))    // shares the dot's tiles and palette
{
    bn::bg_palettes::set_transparent_color(bn::color(3, 4, 8));
    _goal.set_position(top_left(rules_goal_x(), rules_goal_y(), 8, 8));   // after arcade::boot(): the seeded goal
    _ghost.set_blending_enabled(true);                         // half transparent
    _ghost.set_z_order(1);                                      // behind the dot where they overlap
    bn::blending::set_transparency_alpha(0.5);
}

void view::_rebuild_text(int scene, int paused, int tenths)
{
    _words.clear();
    _text.set_center_alignment();
    if(scene == SC_TITLE)
    {
        _text.generate(0, -40, title, _words);
        _text.generate(0, -8, "Move the dot to the square", _words);
        _text.generate(0, 8, "START to play", _words);
        const char* name = arcade::profile_name();
        if(name[0])
        {
            bn::string<32> who("Player ");
            who.append(name);
            _text.generate(0, 40, who, _words);
        }
        if(arcade::has_ghost())
        {
            _text.generate(0, 56, "Ghost loaded", _words);
        }
    }
    else if(scene == SC_PLAY)
    {
        _text.set_left_alignment();
        bn::string<16> t = bn::to_string<8>(tenths / 10);
        t.push_back('.');
        t.push_back(char('0' + tenths % 10));
        _text.generate(-116, -72, t, _words);
        if(paused)
        {
            _text.set_center_alignment();
            _text.generate(0, 0, "PAUSED", _words);
        }
    }
    else
    {
        ac_result r;
        game_result(&r);
        _text.generate(0, -48, r.finished ? "GOAL!" : "RUN ENDED", _words);
        bn::string<32> t("Time ");
        t.append(time_text(r.time_frames));
        _text.generate(0, -32, t, _words);
        if(arcade::best_is_new())
        {
            _text.generate(0, -16, "NEW BEST", _words);
        }
        else if(arcade::best_time_frames())
        {
            bn::string<32> b("Best ");
            b.append(time_text(arcade::best_time_frames()));
            _text.generate(0, -16, b, _words);
        }
        int y = 4;
        for(int i = 0; i < GAME_INFO.n_trophies; ++i)
        {
            if(r.trophies & (1u << i))
            {
                _text.generate(0, y, GAME_INFO.trophy_names[i], _words);
                y += 12;
            }
        }
        _text.generate(0, 64, "START", _words);
    }
}

void view::update(const ac_ghost_pt* ghost)
{
    int scene = rules_scene();
    bool play = scene == SC_PLAY;
    int paused = play ? rules_paused() : 0;
    int tenths = play ? int(rules_run_frames() / 6) : 0;
    if(scene != _scene || paused != _paused || tenths != _tenths)
    {
        _rebuild_text(scene, paused, tenths);
        _scene = scene;
        _paused = paused;
        _tenths = tenths;
    }

    _dot.set_visible(play);
    _goal.set_visible(play);
    _dot.set_position(top_left(rules_x(), rules_y(), 8, 8));
    _ghost_shown = play && ghost != nullptr;
    _ghost.set_visible(_ghost_shown);
    if(_ghost_shown)
    {
        _ghost.set_position(top_left(ghost->x, ghost->y, 8, 8));
        // Butano's sorter re-inserted into the same (bg_priority, z_order) layer later goes in front. The GBA
        // blends a half-transparent sprite only with the backgrounds, and only the frontmost sprite pixel is
        // drawn, so a ghost drawn in front of the dot would wash the dot out where they overlap. Send it behind
        // every frame (after any z_order change), so the dot always stays solid over its ghost.
        _ghost.put_below();
    }
}

}

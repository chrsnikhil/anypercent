#include "cards.h"

#include "bn_regular_bg_items_card.h"
#include "bn_regular_bg_items_title.h"
#include "bn_sprite_palette_items_text_dim.h"
#include "bn_sprite_palette_items_text_gold.h"
#include "bn_sprite_palette_items_text_lime.h"
#include "bn_string.h"

#include "arcade_runtime.h"
#include "common_variable_8x8_sprite_font.h"
#include "hud.h"

extern "C" {
#include "game.h"
#include "tuning.h"
}

namespace game
{

namespace
{
    // A 256 x 256 background with its top-left on the screen's top-left.
    constexpr int bg_x = 128 - 120;
    constexpr int bg_y = 128 - 80;

    const bn::sprite_palette_item& ink() { return common::variable_8x8_sprite_font.item().palette_item(); }
}

cards::cards(bn::sprite_text_generator& text) :
    _text(text)
{
}

void cards::_line(int y, const char* s, int ink, bool blink, int left)
{
    _queue.push_back(line{ y, ink, blink, bn::string<48>(s), left });
}

void cards::_flush(int lines)
{
    for(; lines > 0 && _next < _queue.size(); --lines, ++_next)
    {
        const line& l = _queue[_next];
        switch(l.ink)
        {
        case GOLD: _text.set_palette_item(bn::sprite_palette_items::text_gold); break;
        case DIM: _text.set_palette_item(bn::sprite_palette_items::text_dim); break;
        case LIME: _text.set_palette_item(bn::sprite_palette_items::text_lime); break;
        default: _text.set_palette_item(ink()); break;
        }
        int x = 0;
        if(l.left == centred)
        {
            _text.set_center_alignment();
        }
        else
        {
            _text.set_left_alignment();
            x = l.left;
        }
        if(l.blink)
        {
            _text.generate(x, l.y, l.text, _blink);
        }
        else
        {
            _text.generate(x, l.y, l.text, _words);
        }
    }
    _text.set_palette_item(ink());
}

void cards::_build(int scene)
{
    _words.clear();
    _blink.clear();
    _queue.clear();
    _next = 0;
    bool title_bg = scene == SC_TITLE || scene == SC_HOWTO;
    bool card_bg = scene == SC_HOWTO || scene == SC_RESULTS;
    if(! title_bg)
    {
        _title.reset();
    }
    else if(! _title)
    {
        _title = bn::regular_bg_items::title.create_bg(bg_x, bg_y);
        _title->set_priority(3);
    }
    if(! card_bg)
    {
        _card.reset();
    }
    else if(! _card)
    {
        _card = bn::regular_bg_items::card.create_bg(bg_x, bg_y);
        _card->set_priority(0);
    }

    if(scene == SC_TITLE)
    {
        _line(38, "Late for ETHGlobal Mumbai!");
        _line(52, "PRESS START", GOLD, true);
        const char* name = arcade::profile_name();
        bn::string<48> who;
        if(name[0])
        {
            who.append("Player ");
            who.append(name);
        }
        if(arcade::best_time_frames())
        {
            if(! who.empty())
            {
                who.append("   ");
            }
            who.append("Best ");
            who.append(clock_text(arcade::best_time_frames(), false));
        }
        if(! who.empty())
        {
            _line(64, who.c_str(), DIM);
        }
        if(arcade::has_ghost())
        {
            _line(who.empty() ? 64 : 75, "Ghost loaded: beat your best", DIM);
        }
    }
    else if(scene == SC_HOWTO)
    {
        _line(-62, "HOW TO PLAY", GOLD);
        _line(-48, "Registration closes soon! Run across");
        _line(-38, "Mumbai to the venue door.");
        _line(-22, "D-PAD move      B hold to run", LIME);
        _line(-12, "A jump (hold A: jump higher)", LIME);
        _line(-2, "DOWN + A drop through awnings", LIME);
        _line(14, "Stomp the bears. Grab the USDC.");
        _line(24, "World orb: a shield for one hit.");
        _line(34, "Arkiv shelf: your checkpoint.");
        _line(44, "START pauses.");
        _line(60, "A or START: GO!", GOLD, true);
    }
    else if(scene == SC_PAUSE)
    {
        _line(-16, "PAUSED", GOLD);
        _line(4, "START  resume");
        _line(16, "SELECT  give up");
    }
    else if(scene == SC_RESULTS)
    {
        ac_result r;
        game_result(&r);
        _line(-60, r.finished ? "REGISTERED!" : r.time_frames >= TIME_UP_FRAMES ? "TIME UP" : "GAVE UP", GOLD);
        bn::string<32> t("Time ");
        t.append(clock_text(r.time_frames, false));
        int y = -44;
        _line(y, t.c_str());
        y += 12;
        if(r.finished && arcade::best_is_new())
        {
            _line(y, "NEW BEST", LIME);
            y += 12;
        }
        else if(arcade::best_time_frames())
        {
            bn::string<32> b("Best ");
            b.append(clock_text(arcade::best_time_frames(), false));
            _line(y, b.c_str(), DIM);
            y += 12;
        }
        bn::string<32> c("USDC ");
        c.append(bn::to_string<4>(rules_chai()));
        c.push_back('/');
        c.append(bn::to_string<4>(rules_chai_total()));
        _line(y + 2, c.c_str());
        y += 18;
        _line(y, "TROPHIES");
        y += 12;
        for(int i = 0; i < GAME_INFO.n_trophies; ++i)
        {
            bool got = r.trophies & (1u << i);
            bn::string<32> l(got ? "* " : "- ");
            l.append(GAME_INFO.trophy_names[i]);
            _line(y + i * 11, l.c_str(), got ? GOLD : DIM, false, -46);
        }
        _line(62, "START", LIME, true);
    }
}

void cards::update(int scene, int tick)
{
    if(scene != _scene)
    {
        _scene = scene;
        _build(scene);                              // the backgrounds this frame, the text from the next one
    }
    else
    {
        _flush(2);
    }
    bool on = (tick & 31) < 22;
    for(bn::sprite_ptr& s : _blink)
    {
        s.set_visible(on);
    }
}

}

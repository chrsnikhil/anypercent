#include "hud.h"

#include "bn_sprite_items_chai.h"
#include "bn_sprite_items_hud.h"

extern "C" {
#include "game.h"
}

namespace game
{

namespace
{
    enum { ICON_HEART = 0, ICON_EMPTY = 1, ICON_CHAI = 2, ICON_SHIELD = 3 };

    // Screen top-left pixels -> Butano's centred sprite position.
    bn::fixed_point at(int x, int y, int w, int h)
    {
        return bn::fixed_point(x - 120 + w / 2, y - 80 + h / 2);
    }
}

bn::string<16> clock_text(uint32_t frames, bool tenths)
{
    uint32_t seconds = frames / 60;
    bn::string<16> s = bn::to_string<8>(seconds / 60);
    s.push_back(':');
    s.push_back(char('0' + (seconds % 60) / 10));
    s.push_back(char('0' + seconds % 10));
    s.push_back('.');
    uint32_t hundredths = (frames % 60) * 100 / 60;
    s.push_back(char('0' + hundredths / 10));
    if(! tenths)
    {
        s.push_back(char('0' + hundredths % 10));
    }
    return s;
}

hud::hud(bn::sprite_text_generator& text) :
    _text(text),
    _cup(bn::sprite_items::hud.create_sprite(at(172, 2, 16, 16), ICON_CHAI))
{
    for(int i = 0; i < 4; ++i)
    {
        bn::sprite_ptr icon = bn::sprite_items::hud.create_sprite(at(3 + i * 15, 2, 16, 16), ICON_HEART);
        icon.set_bg_priority(0);
        _icons.push_back(bn::move(icon));
    }
    _cup.set_bg_priority(0);
}

void hud::update(int tick)
{
    int hp = rules_hp();
    bool dead = rules_dead() != 0;
    bool blink = rules_invuln() && (tick & 4);
    for(int i = 0; i < 3; ++i)
    {
        _icons[i].set_tiles(bn::sprite_items::hud.tiles_item(), i < hp && ! dead ? ICON_HEART : ICON_EMPTY);
        _icons[i].set_visible(! (blink && i == hp));
    }
    _icons[3].set_tiles(bn::sprite_items::hud.tiles_item(), ICON_SHIELD);
    _icons[3].set_visible(rules_shield() != 0);

    int tenths = int(rules_run_frames() / 6);
    int chai = rules_chai();
    if(tenths != _shown_tenths)
    {
        _shown_tenths = tenths;
        _clock.clear();
        _text.set_center_alignment();
        _text.generate(0, -71, clock_text(rules_run_frames(), true), _clock);
    }
    else if(chai != _shown_chai)                     // never both in one frame: text generation is slow
    {
        _shown_chai = chai;
        _count.clear();
        bn::string<16> c = bn::to_string<4>(chai);
        c.push_back('/');
        c.append(bn::to_string<4>(rules_chai_total()));
        _text.set_left_alignment();
        _text.generate(70, -71, c, _count);
    }
}

}

// The play HUD: hearts (and the orb's shield), the run clock, chai collected. Text is rebuilt only on a change.
#ifndef RUSH_HUD_H
#define RUSH_HUD_H

#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_string.h"
#include "bn_vector.h"

namespace game
{

// frames -> "M:SS.HH" (hundredths) or, with tenths, "M:SS.T".
bn::string<16> clock_text(uint32_t frames, bool tenths);

class hud
{
public:
    explicit hud(bn::sprite_text_generator& text);
    void update(int tick);

private:
    bn::sprite_text_generator& _text;
    bn::vector<bn::sprite_ptr, 4> _icons;       // three hearts and the shield
    bn::sprite_ptr _cup;
    bn::vector<bn::sprite_ptr, 8> _clock;
    bn::vector<bn::sprite_ptr, 8> _count;
    int _shown_tenths = -1;
    int _shown_chai = -1;
};

}

#endif

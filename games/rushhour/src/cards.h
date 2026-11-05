// The full-screen cards: the title (Mumbai skyline, RUSH HOUR), the how-to card, the pause overlay text and the
// results card (time, chai, trophies earned this run, NEW BEST). Rebuilt only when the scene changes.
#ifndef RUSH_CARDS_H
#define RUSH_CARDS_H

#include "bn_optional.h"
#include "bn_regular_bg_ptr.h"
#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_string.h"
#include "bn_vector.h"

namespace game
{

class cards
{
public:
    explicit cards(bn::sprite_text_generator& text);
    void update(int scene, int tick);

private:
    bn::sprite_text_generator& _text;
    bn::optional<bn::regular_bg_ptr> _title;
    bn::optional<bn::regular_bg_ptr> _card;
    bn::vector<bn::sprite_ptr, 80> _words;
    bn::vector<bn::sprite_ptr, 8> _blink;       // "PRESS START": blinks
    int _scene = -1;

    // A card's text is queued on a scene change and drawn a few lines a frame (text generation is slow, and every
    // frame must keep its game step).
    enum { INK, GOLD, DIM, LIME };
    struct line { int y; int ink; bool blink; bn::string<48> text; int left; };   // left: x, or centred
    bn::vector<line, 16> _queue;
    int _next = 0;

    static constexpr int centred = -1000;
    void _line(int y, const char* s, int ink = INK, bool blink = false, int left = centred);
    void _build(int scene);
    void _flush(int lines);
};

}

#endif

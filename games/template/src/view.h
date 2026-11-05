// Draws the rules' state: the title, the dot, the goal, the translucent ghost, the HUD and the results. Never changes
// the rules; reads them through rules/game.h and the runtime (profile, best) through arcade_runtime.h.
#ifndef TEMPLATE_VIEW_H
#define TEMPLATE_VIEW_H

#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_vector.h"

extern "C" {
#include "ac_save.h"
}

namespace game
{

class view
{
public:
    view();
    // Draws this frame; ghost: the saved ghost for this step (nullptr: none), drawn only in play.
    void update(const ac_ghost_pt* ghost);
    [[nodiscard]] bool ghost_shown() const { return _ghost_shown; }

private:
    bn::sprite_text_generator _text;
    bn::sprite_ptr _dot;
    bn::sprite_ptr _goal;
    bn::sprite_ptr _ghost;
    bn::vector<bn::sprite_ptr, 48> _words;     // every text sprite on screen
    int _scene = -1;                            // what the text shows now, to rebuild it only on a change
    int _paused = -1;
    int _tenths = -1;
    bool _ghost_shown = false;

    void _rebuild_text(int scene, int paused, int tenths);
};

}

#endif

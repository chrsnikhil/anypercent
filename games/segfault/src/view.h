// Draws the rules' state: the title / how-to / results cards, the raycast view with the bugs, the blaster, the HUD
// (health bar, keycard, radar, numbers), messages, the pause menu, the "core dumped" screen and the ghost (a
// translucent phantom in the world and a blip on the radar). Never changes the rules.
#ifndef SEGF_VIEW_H
#define SEGF_VIEW_H

#include "bn_palette_bitmap_bg_ptr.h"
#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_vector.h"

#include "raycaster.h"

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
    bn::palette_bitmap_bg_ptr _bg;
    bn::sprite_text_generator _text;
    bn::sprite_ptr _blaster;
    bn::sprite_ptr _crosshair;
    bn::sprite_ptr _phantom;
    bn::sprite_ptr _blip;
    bn::vector<bn::sprite_ptr, 24> _hud_words;
    bn::vector<bn::sprite_ptr, 24> _msg_words;
    bn::vector<bn::sprite_ptr, 64> _screen_words;
    ray::billboard _bills[ray::max_billboards];     // one per bug (the rules hold MAX_BUGS)
    ray::camera _cam = {};
    int _scene = -1;
    bool _rotate_on_flip = false;
    int _map_version = -1;          // the rules' map version the raycaster's copy was built from
    int _next = -1;                 // the next column to render; -1: the view is not started
    int _chunk_cost = 400;          // ticks the last chunks of columns took (a running maximum)
    int _hud_key = -1;
    int _msg_key = -1;
    int _screen_key = -1;
    int _results_line = 0;
    bool _ghost_shown = false;

    [[nodiscard]] bool top_message() const;    // the message line at the top of the view is showing
    void _enter_card(int card);
    void _start_view();
    void _draw_hud();
    void _update_ghost(const ac_ghost_pt* ghost);
    void _update_texts();
    void _update_sprites();
};

}

#endif

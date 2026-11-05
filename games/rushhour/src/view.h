// RUSH HOUR's view: draws the rules' state and never changes it. The world (the level map over a parallax skyline,
// the hero, the ghost, bugs, chai, the orb, shelves and the door) scrolls with a camera; the HUD and the cards
// (title, how-to, pause, results) sit on top. Reads the rules through rules/game.h and the runtime (profile, best,
// ghost) through arcade_runtime.h.
#ifndef RUSH_VIEW_H
#define RUSH_VIEW_H

#include "bn_optional.h"
#include "bn_regular_bg_ptr.h"
#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_vector.h"

#include "cards.h"
#include "hud.h"

extern "C" {
#include "ac_save.h"
}

namespace game
{

// The scrolling level: backgrounds, camera and every sprite that lives in level coordinates.
class world
{
public:
    world();
    void update(int tick, const ac_ghost_pt* ghost, bool show_ghost);
    [[nodiscard]] bool ghost_shown() const { return _ghost_shown; }

private:
    bn::regular_bg_ptr _level;
    bn::regular_bg_ptr _skyline;
    bn::sprite_ptr _hero;
    bn::sprite_ptr _ghost;
    bn::sprite_ptr _glow;
    bn::sprite_ptr _flag;
    bn::vector<bn::optional<bn::sprite_ptr>, 64> _ents;
    struct pop { bn::sprite_ptr sprite; int x, y, t; };  // a picked-up chai or orb floats up and blinks out
    bn::vector<pop, 4> _pops;
    int _cam_x = 0;             // the screen's top-left in level pixels
    int _cam_y = 0;
    int _look = 0;              // look-ahead in the run direction, eased
    bool _ghost_shown = false;

    void _move_camera(bool snap);
    void _place(bn::sprite_ptr& sprite, int cx, int cy);
    void _draw_hero(int tick);
    void _draw_ghost(const ac_ghost_pt* ghost, bool show, int tick);
    void _draw_entities(int tick);
    void _draw_pops(int tick);
};

class view
{
public:
    view();
    // Draws this frame; ghost: the saved ghost for this step (nullptr: none), drawn only in play.
    void update(const ac_ghost_pt* ghost);
    [[nodiscard]] bool ghost_shown() const { return _world && _world->ghost_shown(); }

private:
    bn::sprite_text_generator _text;
    bn::optional<world> _world;
    bn::optional<hud> _hud;
    cards _cards;
    int _tick = 0;
};

}

#endif

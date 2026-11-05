// Draws MARINE DRIVE GP from the rules' state: the Mode 7 ground (an affine BG whose pa/pc/dx/dy registers are
// rewritten every scanline from a camera behind the player), the skyline, the karts and the props as sprites scaled
// by distance, the translucent ghost, the HUD and every card (title, how-to, countdown, pause, finish, results).
// Never changes the rules; reads them through rules/game.h and the runtime (profile, best) through arcade_runtime.h.
#ifndef MD_VIEW_H
#define MD_VIEW_H

#include "bn_affine_bg_dx_register_hbe_ptr.h"
#include "bn_affine_bg_dy_register_hbe_ptr.h"
#include "bn_affine_bg_pa_register_hbe_ptr.h"
#include "bn_affine_bg_pc_register_hbe_ptr.h"
#include "bn_affine_bg_ptr.h"
#include "bn_display.h"
#include "bn_optional.h"
#include "bn_regular_bg_ptr.h"
#include "bn_sprite_affine_mat_ptr.h"
#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_string.h"
#include "bn_vector.h"

extern "C" {
#include "ac_save.h"
}

namespace md
{

// The camera on the track plane, in 1/256 px, heading in 1024 steps.
struct camera
{
    int x = 0;
    int y = 0;
    int heading = 0;
    int sin = 0;                                  // of the heading, Q14
    int cos = 16384;
};

class view
{
public:
    view();
    // Draws this frame; ghost: the saved ghost for this step (nullptr: none), drawn only in the race.
    void update(const ac_ghost_pt* ghost);
    [[nodiscard]] bool ghost_shown() const { return _ghost_shown; }

private:
    static constexpr int max_props = 8;
    static constexpr int max_mats = 14;

    bn::affine_bg_ptr _ground;
    bn::regular_bg_ptr _skyline;
    alignas(int) int16_t _pa[bn::display::height()];
    alignas(int) int16_t _pc[bn::display::height()];
    int _dx[bn::display::height()];
    int _dy[bn::display::height()];
    bn::affine_bg_pa_register_hbe_ptr _pa_hbe;
    bn::affine_bg_pc_register_hbe_ptr _pc_hbe;
    bn::affine_bg_dx_register_hbe_ptr _dx_hbe;
    bn::affine_bg_dy_register_hbe_ptr _dy_hbe;

    bn::sprite_text_generator _text;
    bn::sprite_ptr _player;
    bn::vector<bn::sprite_ptr, 3> _rivals;
    bn::sprite_ptr _ghost;
    bn::sprite_ptr _marker;                       // the player's lime arrow
    bn::vector<bn::sprite_ptr, 2> _sparks;
    bn::sprite_ptr _flame;                        // the exhaust while boosting
    static constexpr int max_puffs = 4;
    struct puff
    {
        int life = 0;                             // frames left (0: free)
        int x = 0;                                // px from the player's centre, when it was left behind
        int y = 0;                                // screen line - 80
        int dx = 0;                               // spreading outward: -1 or 1 px every 4 frames
        int kind = 0;                             // 0 tyre smoke, 1 sand dust
    };
    bn::vector<bn::sprite_ptr, max_puffs> _puff_sprites;
    puff _puffs[max_puffs];
    int _puff_frame[max_puffs] = {-1, -1, -1, -1};
    int _puff_next = 0;                           // the pool slot the next puff takes
    int _flame_frame = -1;
    int _last_drift = 0;                          // the player's drift last frame (a new drift hops)
    int _hop = 0;                                 // frames into the drift hop (0: none)
    unsigned _bob_phase = 0;                      // the suspension's phase: advances with speed
    int _last_walls = 0;                          // the player's wall hits last frame (a new one shakes)
    int _shake = 0;                               // camera shake frames left
    bn::vector<bn::sprite_ptr, max_props> _props;
    bn::vector<bn::sprite_affine_mat_ptr, max_mats> _mats;
    int _prop_look[max_props] = {};               // kind * 4 + frame each prop sprite shows
    int _prop_mat[max_props] = {};                // its affine matrix (index in _mats)
    int _prop_layer[max_props] = {};              // its z order
    int _kart_frame[4] = {-1, -1, -1, -1};       // the frame and z order each sprite shows (set on a change)
    int _kart_z[4] = {-1, -1, -1, -1};
    int _spark_frame[2] = {-1, -1};
    int _spark_z[2] = {-1, -1};
    int _ghost_frame = -1;
    int _place_frame = -1;
    int _speed_frame = -1;
    int _clock_frame[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
    bn::optional<bn::sprite_ptr> _place;
    bn::optional<bn::sprite_ptr> _speed;
    bn::vector<bn::sprite_ptr, 6> _big;           // logo / countdown / banner pieces
    bn::vector<bn::sprite_ptr, 56> _words;        // card and HUD text that changes rarely
    bn::vector<bn::sprite_ptr, 8> _clock;         // the race clock, one sprite per character
    bn::vector<bn::sprite_ptr, 6> _gap_digits;    // the gap to the ghost, one sprite per character
    int _gap_digit_frame[6] = {-1, -1, -1, -1, -1, -1};
    int _gap_k = 0;                               // the ghost's step matched to the player's position (0: none yet)
    int _gap = 0;                                 // frames the player is behind the ghost there (negative: ahead)
    bool _gap_on = false;                         // a gap is shown
    int _gap_key = -1;                            // the shown gap: tenths * 2 + behind (-1: none)

    struct pending_line
    {
        int x;
        int y;
        int align;                                // 0 left, 1 centre
        bool blink;                               // into _blink (blinking) rather than _words
        bn::string<40> text;
    };
    bn::vector<pending_line, 20> _pending;        // card text waiting to be generated
    int _align = 1;
    bool _blink_next = false;
    bn::vector<bn::sprite_ptr, 4> _blink;         // blinking text (PRESS START)
    bn::vector<bn::sprite_ptr, 4> _warn;          // WRONG WAY
    int _backwards = 0;                           // frames the player's progress has been falling
    int _last_progress = 0;

    camera _cam;
    int _cam_h16 = 0;                             // smoothed camera heading, 1/16 steps
    int _scene = -1;
    int _text_key = -1;
    int _big_key = -1;
    int _fade = -1;                               // 0: transparency (ghost), else the fade level
    int _banner = -1;                             // FINAL LAP banner frames left
    int _lap_flash = 0;                           // frames left showing the last lap time
    bool _ghost_shown = false;

    void _update_camera(int scene);
    void _update_ground();
    void _draw_karts(int scene, const ac_ghost_pt* ghost);
    void _draw_props(bool show, bool orbs);
    void _draw_text(int scene, bool busy);  // busy: this frame already did slow sprite work
    void _say(int x, int y, const bn::string_view& text);
    bool _draw_big(int scene);               // true: rebuilt the big sprites this frame
    void _track_gap(int scene);              // the gap to the ghost: which ghost step matches the player
    void _draw_gap(int scene);               // ... and its digits under the place badge
    void _set_fade(int level);
    bool _project(int px8, int py8, int& sx, int& sy, int& z8) const;
};

}

#endif

// ZIP's view: draws the rules' state and never changes it. Title card, how-to card, the run (a big level BG with a
// server-hall parallax, a look-ahead camera, Zip rotated to the ground, packets, springs, boosters, bugs, the
// checkpoint, the HUD, the translucent ghost), pause, and the results card with trophies.
#ifndef ZIP_VIEW_H
#define ZIP_VIEW_H

#include "bn_camera_ptr.h"
#include "bn_optional.h"
#include "bn_regular_bg_ptr.h"
#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_string.h"
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
    static constexpr int packet_pool = 56;          // up to 32 scattered + the level's on screen
    static constexpr int thing_pool = 16;
    static constexpr int max_new_sprites = 4;       // packet/thing sprites created per frame (a hit scatters many)

    // Card text is queued and drawn a few lines a frame: generating a whole card at once takes longer than a frame,
    // and a frame without a game step would break the one-step-per-frame contract.
    struct line
    {
        bn::string<48> text;
        int16_t x, y;
        uint8_t big, align;                     // align: 0 left, 1 centre
    };
    bn::vector<line, 24> _queue;

    bn::sprite_text_generator _small;
    bn::sprite_text_generator _big;
    bn::optional<bn::regular_bg_ptr> _card;      // title or panel
    bn::optional<bn::regular_bg_ptr> _level;
    bn::optional<bn::regular_bg_ptr> _hall;
    bn::camera_ptr _camera;
    bn::sprite_ptr _zip;
    bn::sprite_ptr _trail;
    bn::sprite_ptr _ghost;
    bn::vector<bn::sprite_ptr, packet_pool> _packets;
    bn::vector<bn::sprite_ptr, thing_pool> _things;
    bn::vector<bn::sprite_ptr, 8> _icons;
    bn::vector<bn::sprite_ptr, 64> _words;       // card / pause / results text
    bn::vector<bn::sprite_ptr, 16> _hud_time;
    bn::vector<bn::sprite_ptr, 8> _hud_packets;
    bn::vector<bn::sprite_ptr, 8> _banner;        // GOAL!

    int _scene = -1;
    int _card_kind = -1;                          // 0 title, 1 panel
    int _hud_seconds = -1;
    int _hud_count = -1;
    int _frame = 0;
    int _anim = 0;                                // Zip's animation clock (in 1/256 frames)
    int _cam_x = 0;
    int _cam_y = 0;
    int _look = 0;                                // look-ahead, 1/16 px
    int _respawns = -1;
    bool _ghost_shown = false;
    bool _banner_on = false;

    void _say(int x, int y, const char* text, bool big, bool centre);
    void _flush_queue(int lines);
    void _enter_scene(int scene);
    void _show_card(int kind);
    void _show_level(bool on);
    void _title_text();
    void _howto_text();
    void _results_text();
    void _pause_text(bool on);
    void _update_camera(bool snap);
    void _update_zip();
    void _update_things();
    void _update_hud(bool on);
    void _update_ghost(const ac_ghost_pt* ghost, bool play);
};

}

#endif

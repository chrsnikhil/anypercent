// Draws the rules' state: the streamed room, the characters, the pointers and the HUD. Never changes the rules.
#ifndef SHIPIT_VIEW_H
#define SHIPIT_VIEW_H

#include "bn_bg_palette_item.h"
#include "bn_optional.h"
#include "bn_regular_bg_map_cell.h"
#include "bn_regular_bg_map_item.h"
#include "bn_regular_bg_map_ptr.h"
#include "bn_regular_bg_ptr.h"
#include "bn_regular_bg_tiles_ptr.h"
#include "bn_sprite_ptr.h"
#include "bn_sprite_text_generator.h"
#include "bn_string.h"
#include "bn_vector.h"

extern "C" {
#include "rooms.h"
#include "stream.h"
#include "ac_save.h"
}

namespace shipit
{

class text_line
{
public:
    // Regenerates the sprites only when the text or position changes.
    void show(bn::sprite_text_generator& generator, int x, int y, const bn::istring& text);

private:
    bn::vector<bn::sprite_ptr, 24> _sprites;
    bn::string<64> _text;
    int _x = 0;
    int _y = 0;
};

// The room image streamed into a 32 x 32 background through 768 tile slots (see stream.h).
class room_bg
{
public:
    room_bg();
    // Switches the streamed source (day or night room): every visible cell is fetched again from the new one.
    void use_room(const room_data& room);
    void set_palette(const bn::bg_palette_item& palette);
    // Streams at most budget tile writes this frame (STREAM_MAX_WRITES in play; more on a black screen).
    void show(int cam_x, int cam_y, int budget);

private:
    alignas(int) bn::regular_bg_map_cell _cells[32 * 32];
    bn::regular_bg_map_item _map_item;
    bn::regular_bg_tiles_ptr _tiles;
    bn::regular_bg_map_ptr _map;
    bn::regular_bg_ptr _bg;
    stream_state _stream;
    stream_writes _writes;
    const room_data* _src;
};

// Which room image is streamed.
enum shown_room { SHOWN_DAY, SHOWN_NIGHT, SHOWN_DAWN, SHOWN_HALL };

class view
{
public:
    view();
    void update();
    [[nodiscard]] int cam_x() const { return _cam_x; }
    [[nodiscard]] int cam_y() const { return _cam_y; }
    // The saved ghost this frame (nullptr: none), drawn by the next update() when it is in the player's room.
    void set_ghost(const ac_ghost_pt* ghost);
    [[nodiscard]] bool ghost_shown() const { return _ghost_shown; }

private:
    room_bg _room;
    bn::sprite_ptr _player_top;
    bn::sprite_ptr _player_bottom;
    bn::sprite_ptr _ghost_top;                 // the saved ghost: the player's sprites, half transparent
    bn::sprite_ptr _ghost_bottom;
    bn::sprite_ptr _cup;
    bn::sprite_ptr _arrow;
    bn::sprite_ptr _pill;
    bn::vector<bn::sprite_ptr, 3> _devs;
    bn::vector<bn::sprite_ptr, 3> _meters;
    bn::vector<bn::sprite_ptr, 3> _bubbles;
    bn::vector<bn::sprite_ptr, 4> _strip;
    bn::vector<bn::sprite_ptr, 8> _bar;
    bn::vector<bn::sprite_ptr, 3> _logo;
    bn::vector<bn::sprite_ptr, 2> _logo_small;
    bn::vector<bn::sprite_ptr, 6> _bugs;
    bn::sprite_ptr _spark;
    bn::sprite_ptr _pizza;
    bn::vector<bn::sprite_ptr, 2> _rain;
    bn::sprite_ptr _commit_meter;
    bn::sprite_ptr _gate;
    bn::sprite_ptr _slide_key;
    bn::vector<bn::sprite_ptr, 6> _crowd;
    bn::vector<bn::sprite_ptr, 12> _card;     // the results card, only while it shows
    bn::vector<bn::sprite_ptr, 16> _confetti;
    bn::optional<bn::sprite_ptr> _flash;
    bn::optional<bn::sprite_ptr> _spot;
    bn::optional<bn::sprite_ptr> _grade;
    bn::sprite_text_generator _small;
    bn::sprite_text_generator _big;
    text_line _objective;
    text_line _act;
    text_line _clock;
    text_line _percent;
    text_line _prompt_text;
    text_line _headline;
    text_line _lines[8];
    text_line _desc[4];
    text_line _message;
    text_line _slide;
    int _cam_x = 0;
    int _cam_y = 0;
    int _tick = 0;
    int _shown = SHOWN_DAY;
    int _cam_max_x = 0;
    int _cam_max_y = 0;
    bool _recorded = false;
    int _last_slide = 0;
    int _flash_left = 0;
    int _cheer_left = 0;
    int _confetti_left = 0;
    int _shake_left = 0;
    int _card_step = 0;
    int _title_frames = 0;                     // frames on the title: its logo waits for the last screen's text to go                        // the card is built over several frames (see _update_card)                   // this run's time went to the best-time record
    ac_ghost_pt _ghost = {};
    bool _has_ghost = false;
    bool _ghost_shown = false;
    int _refill_left = 0;                      // frames of fast refill (screen black) after a room swap
    bool _bug_was_on[6] = {};
    int _squash_left[6] = {};                  // frames the squashed bug stays where it was stomped
    int _squash_x[6] = {};
    int _squash_y[6] = {};

    void _follow(int px, int py, bool snap);
    [[nodiscard]] int _wanted_room(int scene) const;
    void _swap_room(int room);
    void _make_devs();
    void _update_devs(bool play);
    void _update_player(bool play);
    void _update_ghost(bool play, int step);
    void _update_act_two(bool play, int scene);
    void _update_hall(bool play, int scene);
    void _update_pointers(bool play);
    void _update_hud(bool play);
    void _update_screens(int scene);
    void _update_card(int scene);
    void _update_confetti();
};

}

#endif

// SHIP IT! main loop: one rules step per frame from the raw keypad, then draw the rules' state.
#include "bn_core.h"
#include "bn_sprite_tiles.h"
#include "bn_unique_ptr.h"
#include "bn_dmg_music.h"
#include "bn_dmg_music_items_theme.h"

#include "best.h"
#include "runlog.h"
#include "view.h"

extern "C" {
#include "ac_game.h"
#include "rules.h"
}

// Read by the headless tests at their ELF symbol addresses.
extern "C" {
volatile uint32_t g_dbg_hash;
volatile uint32_t g_dbg_steps;
volatile uint32_t g_dbg_scene;
volatile uint32_t g_dbg_cam;
volatile uint32_t g_dbg_best;           // bit 0: this run set a new best; bit 1: there was a best before it
volatile uint32_t g_dbg_sprite_tiles;    // sprite tiles in use (of 1024), for the VRAM budget test
volatile uint32_t g_dbg_ghost;           // 1 while the saved ghost is drawn, else 0
volatile uint32_t g_dbg_ghost_xy;        // the ghost's room position, (x << 16) | y (while it is drawn)
}

namespace
{
    uint16_t read_buttons()
    {
        // KEYINPUT is active-low; the low 10 bits are the GBA keys in the rules' bit order.
        return uint16_t(~*reinterpret_cast<volatile uint16_t*>(0x04000130) & 0x03FF);
    }
}

int main()
{
    bn::core::init();
    shipit::best::load();
    shipit::runlog::begin();                                    // seeds this boot, game_init(seed), records from it
    bn::dmg_music_items::theme.play();                      // the theme (games/music): sound only, never the rules
    bn::dmg_music::set_master_volume(bn::dmg_music_master_volume::HALF);   // the chip at 50 % (default 25 %)
    bn::unique_ptr<shipit::view> view(new shipit::view());     // big (map cells, stream state): not on the stack
    uint32_t steps = 0;                                         // rules steps since boot

    while(true)
    {
        uint16_t buttons = read_buttons();
        game_step(buttons);                                     // rules_step, counted for game_result()
        shipit::runlog::push(buttons);
        shipit::runlog::flush();                                // the save steps start the frame after
        shipit::runlog::finish_if_ended();
        shipit::runlog::reset_after_results();                  // Start on the results: save, then reboot
        g_dbg_hash = rules_hash();
        ++steps;
        g_dbg_steps = steps;
        g_dbg_scene = rules_scene();
        ac_ghost_pt ghost = {};
        bool has_ghost = shipit::runlog::ghost_at(steps, ghost);   // aligned on play start (runlog.h)
        view->set_ghost(has_ghost ? &ghost : nullptr);
        view->update();
        g_dbg_ghost = view->ghost_shown() ? 1 : 0;
        g_dbg_ghost_xy = view->ghost_shown() ? (uint32_t(uint16_t(ghost.x)) << 16) | uint16_t(ghost.y) : 0;
        g_dbg_cam = (uint32_t(view->cam_x()) << 16) | uint32_t(view->cam_y());
        g_dbg_sprite_tiles = uint32_t(bn::sprite_tiles::used_tiles_count());
        g_dbg_best = (uint32_t(shipit::best::had_best()) << 1) | uint32_t(shipit::best::was_new());
        bn::core::update();
    }
}

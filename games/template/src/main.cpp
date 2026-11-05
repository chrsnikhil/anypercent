// The frame loop every arcade game keeps: one rules step per frame from the raw keypad, the runtime right after it
// (record, save, reset), then the view. Keep this order; see games/common/src/arcade_runtime.h.
#include "bn_core.h"
#include "bn_sprite_tiles.h"
#include "bn_unique_ptr.h"

#include "arcade_runtime.h"
#include "view.h"

extern "C" {
#include "game.h"
}

// Read by the headless tests at its ELF symbol address (the runtime defines the other g_dbg_* symbols).
extern "C" {
volatile uint32_t g_dbg_sprite_tiles;    // sprite tiles in use (of 1024), for the VRAM budget test
}

int main()
{
    bn::core::init();
    arcade::boot();                                         // seeds this boot, game_init(seed), records from it
    bn::unique_ptr<game::view> view(new game::view());

    while(true)
    {
        uint16_t buttons = arcade::read_buttons();
        game_step(buttons);
        arcade::after_step(buttons);                        // leaving the results resets here
        ac_ghost_pt ghost = {};
        bool has_ghost = arcade::ghost_at(arcade::steps(), ghost);   // steps since boot: the ghost's run began at boot too
        view->update(has_ghost ? &ghost : nullptr);
        arcade::report_ghost(view->ghost_shown(), ghost);
        g_dbg_sprite_tiles = uint32_t(bn::sprite_tiles::used_tiles_count());
        bn::core::update();
    }
}

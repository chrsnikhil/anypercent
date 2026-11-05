// The common arcade runtime: records every frame's buttons from boot, saves the run log (and a new best) to the
// cartridge when the run ends, resets the ROM once the player leaves the results, and serves the saved ghost and
// the launcher's profile. Generalised from SHIP IT!'s game/src/runlog.cpp; driven only by the game_* interface
// (arcade/src/ac_game.h) plus game_ended() (arcade_game_ext.h).
//
// The frame loop, in this order (see games/template/src/main.cpp):
//
//     bn::core::init();
//     arcade::boot();                        // seeds this boot and calls game_init(seed)
//     while(true) {
//         uint16_t b = arcade::read_buttons();
//         game_step(b);
//         arcade::after_step(b);             // may reset the ROM (never returns then)
//         ac_ghost_pt g;
//         bool has = arcade::ghost_at(arcade::steps(), g);
//         ... draw, with the ghost if has ...
//         arcade::report_ghost(drawn, g);    // what the view really drew, for the tests
//         g_dbg_sprite_tiles = bn::sprite_tiles::used_tiles_count();
//         bn::core::update();
//     }
//
// Save memory: bytes 0..0xFF are never touched; the section table, BEST and RUN are written over several frames
// after the run ends, payloads first and the table last. GHOST is only read (the launcher writes it) and never
// affects the rules. PROFILE is written by the launcher; at boot the runtime bumps its boot count (and writes the
// profile and the table back) when it carries a seed nonce, and seeds the run with ac_seed_mix(nonce, boots).
#ifndef ARCADE_RUNTIME_H
#define ARCADE_RUNTIME_H

#include <stdint.h>

extern "C" {
#include "ac_save.h"
#include "arcade_game_ext.h"
}

namespace arcade
{
    // After bn::core::init(): loads the SRAM image (formats it in RAM if it is blank, another game's or another
    // version; it reaches SRAM with the first saved run), parses ghost and profile, picks this boot's seed (the
    // profile's seed nonce and bumped boot count; 0 without a nonce), calls game_init(seed) and starts the recorder
    // with that seed in the log header, so the replayer's game_init(header seed) matches.
    void boot();

    // KEYINPUT as the rules' buttons: active high, BTN_MASK (arcade/src/ac_buttons.h).
    uint16_t read_buttons();

    // Right after game_step(buttons), every frame: records the buttons, closes the log on game_ended()'s rising edge,
    // runs one step of the staged save, and on the falling edge finishes the save and calls bn::core::reset().
    // Latches the first step whose game_ghost() has AC_GHOST_PLAY (the ghost's alignment point).
    // Updates g_dbg_hash, g_dbg_steps, g_dbg_phase, g_dbg_player_xy, g_dbg_best.
    //
    // What is saved when the run ends: RUN keeps the cartridge's best run. A stored RUN that is absent, truncated or
    // unfinished is replaced; a finished one only by a finished run with a smaller time_frames (a tie keeps it).
    // (The stored RUN counts as finished when BEST's final hash is its log's.) BEST is replaced by a finished run
    // with a smaller time_frames, or set by the first finished run. A run that replaces nothing writes nothing.
    // SHIP IT! (game/src/runlog.cpp) keeps last-run semantics instead.
    void after_step(uint16_t buttons);

    // The ghost for the step `step` (game steps since boot), interpolated between samples (x and y in game_ghost()
    // units); false if there is no valid ghost or step is 0. A ghost with in-play samples (AC_GHOST_PLAY,
    // arcade_game_ext.h) is aligned on play start: nothing before this run's first in-play step, then its first
    // in-play sample on that step and on from there. A ghost without them runs from boot. After the last sample the
    // ghost stays where its run ended.
    bool ghost_at(uint32_t step, ac_ghost_pt& out);

    // What the view drew this frame: sets g_dbg_ghost (1 if shown) and g_dbg_ghost_xy ((x << 16) | y as u16s).
    void report_ghost(bool shown, const ac_ghost_pt& pt);

    uint32_t steps();                      // game steps since boot
    const char* profile_name();            // the launcher's display name (printable ASCII, <= 12 chars); "" if none
    uint32_t profile_trophies();           // trophies the launcher says this player has on this game; 0 if none
    bool has_ghost();                      // a valid ghost section was loaded at boot

    // Valid from the frame the run ends (game_ended() rises) on:
    bool best_is_new();                    // the run just ended is finished and beats the stored best (or there was none)
    uint32_t best_time_frames();           // the best time after this run (the stored one before a run ends); 0: none
}

#endif

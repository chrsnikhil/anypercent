// The arcade kit's last-run log and best entry in cartridge save memory (arcade/src/ac_save.h). The recorder
// runs from boot, like the rules, so the log replays from game_init(the seed in its header); leaving the results
// resets the ROM, so every run starts at boot, with its own seed when the launcher's profile carries a seed nonce
// (the boot count in the profile is bumped and written back at boot). The legacy 8-byte best record at
// offset 0 stays best.cpp's; this module only ever writes 0x100 and up.
#ifndef SHIPIT_RUNLOG_H
#define SHIPIT_RUNLOG_H

#include <stdint.h>

extern "C" {
#include "ac_save.h"
}

namespace shipit::runlog
{
    void begin();                                    // read the save image (and ghost), pick the seed, game_init(seed),
                                                     // start recording
    void push(uint16_t buttons);                     // the buttons given to this frame's game_step
    void finish_if_ended();                          // on the first SC_CLEAR / SC_MISSED: save RUN (and BEST)
    void flush();                                    // every frame: one step of saving an ended run
    void reset_after_results();                      // once the results are left: finish the save, reset the ROM
    // Every frame, after the step: the ghost to draw after `step` rules steps since boot; false: none. A ghost with
    // in-play samples (AC_GHOST_PLAY) is aligned on play start, like games/common's arcade_runtime.
    bool ghost_at(uint32_t step, ac_ghost_pt& out);
}

#endif

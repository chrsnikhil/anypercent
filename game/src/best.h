// The best total time, kept in cartridge save memory (see rules/record.h). The rules never see it: it is
// read at boot and written by the view when a shipped run beats it.
#ifndef SHIPIT_BEST_H
#define SHIPIT_BEST_H

#include <stdint.h>

namespace shipit::best
{
    void load();                        // read the record at boot
    [[nodiscard]] uint32_t frames();    // the best total in frames, 0 = none yet
    bool record(uint32_t run_frames);   // a shipped run: save it if it beats the best; true when it did
    [[nodiscard]] bool was_new();       // the last record() set a new best
    [[nodiscard]] bool had_best();      // there was a best before the last record()
}

#endif

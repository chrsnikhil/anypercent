#include "best.h"

#include "bn_sram.h"

extern "C" {
#include "record.h"
}

namespace shipit::best
{

namespace
{
    struct saved
    {
        uint8_t bytes[8];
    };

    uint32_t best_frames = 0;
    bool last_was_new = false;
    bool last_had_best = false;
}

void load()
{
    saved data;
    bn::sram::read(data);
    best_frames = record_decode(data.bytes);
}

uint32_t frames()
{
    return best_frames;
}

bool record(uint32_t run_frames)
{
    last_had_best = best_frames != 0;
    last_was_new = run_frames != 0 && (best_frames == 0 || run_frames < best_frames);
    if(last_was_new)
    {
        best_frames = run_frames;
        saved data;
        record_encode(run_frames, data.bytes);
        bn::sram::write(data);
    }
    return last_was_new;
}

bool was_new()
{
    return last_was_new;
}

bool had_best()
{
    return last_had_best;
}

}

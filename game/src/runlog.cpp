#include "runlog.h"

#include "bn_common.h"
#include "bn_core.h"
#include "bn_math.h"
#include "bn_span.h"
#include "bn_sram.h"

extern "C" {
#include "ac_game.h"
#include "ac_log.h"
#include "ac_rng.h"
#include "rules.h"
}

// Read by the headless tests at its ELF symbol address.
extern "C" {
volatile uint32_t g_dbg_run_written;     // number of last-run sections written
volatile uint32_t g_dbg_run_frames;      // game_result().frames when the run's log closed
volatile uint32_t g_dbg_seed;            // this boot's seed (game_init's and the log header's)
}

namespace shipit::runlog
{

namespace
{
    constexpr uint32_t log_cap = 14336;           // the RUN section's capacity (ac_save.h)

    struct save_image
    {
        alignas(4) uint8_t bytes[AC_SAVE_SIZE];
    };

    BN_DATA_EWRAM_BSS save_image image;
    ac_rec rec;
    bool done = false;

    // Saving a run is spread over the frames after it ends, one step a frame (at once, copying and summing a 7 KB log
    // alone cost a whole frame): the log is recorded straight into the image's RUN slot, so there is no copy; its
    // checksum is summed 1 KB a frame and the section committed in place; then BEST; then SRAM is written 1 KB a
    // frame (Butano writes it a byte at a time), payloads first and the section table (0x100..0x1FF) last, so a power
    // cut midway leaves sections whose checksums fail rather than a table pointing at half-written data.
    enum stage_t { stage_idle, stage_sum, stage_best, stage_write };
    constexpr int chunk = 1024;
    constexpr int table_end = AC_OFF_PROFILE;
    uint8_t* const log_buf = image.bytes + AC_OFF_RUN;
    stage_t stage = stage_idle;
    ac_result result;
    uint32_t final_hash = 0;
    uint32_t log_len = 0;
    bool truncated = false;         // the log did not fit (rec.full when it closed)
    uint32_t summed = 0;            // log bytes summed so far
    uint16_t sum = 0;               // their ac_save_sum
    int pending_from = 0;           // next payload byte to write
    int pending_end = 0;            // end of the payload span

    const char game_id[4] = {'S', 'H', 'I', 'P'};

    bool header_ok()
    {
        const uint8_t* h = image.bytes + AC_SAVE_BASE;
        return h[0] == 'A' && h[1] == 'C' && h[2] == 'S' && h[3] == 'V' && h[4] == AC_SAVE_VERSION && h[5] == 0 &&
               h[6] == 'S' && h[7] == 'H' && h[8] == 'I' && h[9] == 'P';
    }

    void put32(uint8_t* p, uint32_t v)
    {
        p[0] = uint8_t(v);
        p[1] = uint8_t(v >> 8);
        p[2] = uint8_t(v >> 16);
        p[3] = uint8_t(v >> 24);
    }

    // The saved ghost, checked once at boot (ac_save_get sums the whole payload). Its points stay where they are in
    // the image (EWRAM): the recorder writes only the RUN slot, which ends where the GHOST slot starts, and the
    // table and BEST lie before both.
    const uint8_t* ghost_points = nullptr;
    uint32_t ghost_period = 0;
    uint32_t ghost_count = 0;
    uint32_t ghost_anchor = 0;      // ghost step (k * period + 1) of its first sample in play; 0: unaligned ghost
    uint32_t live_step = 0;         // this run's first step whose game_ghost() is in play; 0: not yet

    void load_ghost()
    {
        ghost_points = nullptr;
        ghost_period = 0;
        ghost_count = 0;
        ghost_anchor = 0;
        live_step = 0;
        uint32_t len;
        uint8_t flags;
        const uint8_t* g = ac_save_get(image.bytes, game_id, AC_SEC_GHOST, &len, &flags);
        if(! g || len < 16 || g[0] != 'A' || g[1] != 'C' || g[2] != 'G' || g[3] != '1' ||
           g[4] != game_id[0] || g[5] != game_id[1] || g[6] != game_id[2] || g[7] != game_id[3])
        {
            return;
        }

        uint32_t period = uint32_t(g[12] | (g[13] << 8));
        uint32_t count = uint32_t(g[14] | (g[15] << 8));
        if(period == 0 || count == 0 || len < 16 + 6 * count)
        {
            return;
        }

        ghost_points = g + 16;
        ghost_period = period;
        ghost_count = count;
        for(uint32_t k = 0; k < count; ++k)
        {
            if(g[16 + 6 * k + 5] & AC_GHOST_PLAY)
            {
                ghost_anchor = k * period + 1;
                break;
            }
        }
    }

    // This boot's seed, as the arcade games' runtime picks it (games/common/src/arcade_runtime.cpp): with a profile
    // carrying a seed nonce (written fresh by the launcher before each launch) the boot count in it is bumped and
    // written back first (payload, then the section table), so every boot, including one started from the results
    // without the launcher, gets its own seed. No profile, or no nonce: seed 0, the classic run.
    uint32_t boot_seed()
    {
        uint32_t len;
        uint8_t flags;
        const uint8_t* p = ac_save_get(image.bytes, game_id, AC_SEC_PROFILE, &len, &flags);
        if(! p || len < AC_PROFILE_BOOTS + 4)
        {
            return 0;
        }

        uint32_t nonce = ac_log_u32(p + AC_PROFILE_SEED_NONCE);
        if(nonce == 0)
        {
            return 0;
        }

        uint32_t boots = ac_log_u32(p + AC_PROFILE_BOOTS) + 1;
        alignas(4) uint8_t profile[64];
        uint32_t n = bn::min(len, uint32_t(sizeof(profile)));
        for(uint32_t i = 0; i < n; ++i)
        {
            profile[i] = p[i];
        }

        put32(profile + AC_PROFILE_BOOTS, boots);
        ac_save_put(image.bytes, AC_SEC_PROFILE, profile, n, flags);
        bn::sram::write_span_offset(bn::span<const uint8_t>(image.bytes + AC_OFF_PROFILE, int(n)), AC_OFF_PROFILE);
        bn::sram::write_span_offset(
                bn::span<const uint8_t>(image.bytes + AC_SAVE_BASE, table_end - AC_SAVE_BASE), AC_SAVE_BASE);
        return ac_seed_mix(nonce, boots);
    }

    ac_ghost_pt ghost_point(uint32_t i)
    {
        const uint8_t* p = ghost_points + 6 * i;
        ac_ghost_pt pt;
        pt.x = int16_t(uint16_t(p[0] | (p[1] << 8)));
        pt.y = int16_t(uint16_t(p[2] | (p[3] << 8)));
        pt.angle = p[4];
        pt.flags = p[5];
        return pt;
    }
}

void begin()
{
    bn::sram::read(image);
    if(! header_ok())
    {
        ac_save_format(image.bytes, game_id);      // blank, another game's or an old version: written with the first run
    }

    load_ghost();
    uint32_t seed = boot_seed();
    game_init(seed);                                 // the replayer starts from game_init(the header's seed) too
    ac_rec_begin(&rec, log_buf, log_cap, game_id, GAME_INFO.rules_version, seed);
    g_dbg_seed = seed;
    done = false;
    stage = stage_idle;
}

void push(uint16_t buttons)
{
    if(! done)                                       // the log is closed once the run ends
    {
        ac_rec_push(&rec, buttons);
    }
}

void finish_if_ended()
{
    uint8_t scene = rules_scene();
    if(done || (scene != SC_CLEAR && scene != SC_MISSED))
    {
        return;
    }

    // The run's end frame is already a heavy one (the results card): only close the log here.
    done = true;
    game_result(&result);
    g_dbg_run_frames = result.frames;
    final_hash = rules_hash();
    log_len = ac_rec_finish(&rec, final_hash, 0, result.trophies);
    truncated = rec.full;
    summed = 0;
    sum = ac_save_sum(log_buf, 0);                  // the checksum's seed (0x5A5A)
    stage = stage_sum;
}

void flush()
{
    switch(stage)
    {

    case stage_sum:
        if(summed < log_len)
        {
            uint32_t n = bn::min(uint32_t(chunk), log_len - summed);
            sum = uint16_t(sum + ac_save_sum(log_buf + summed, n) - ac_save_sum(log_buf, 0));
            summed += n;
        }
        else
        {
            ac_save_commit(image.bytes, AC_SEC_RUN, log_len, sum, truncated ? AC_FLAG_TRUNCATED : 0);
            stage = stage_best;
        }
        break;

    case stage_best:
        if(result.finished)
        {
            uint32_t best_len;
            uint8_t best_flags;
            const uint8_t* best = ac_save_get(image.bytes, game_id, AC_SEC_BEST, &best_len, &best_flags);
            if(! best || best_len < 4 || result.time_frames < ac_log_u32(best))
            {
                uint8_t entry[32] = {};
                put32(entry, result.time_frames);
                put32(entry + 4, result.score);
                put32(entry + 8, result.trophies);
                put32(entry + 12, final_hash);
                ac_save_put(image.bytes, AC_SEC_BEST, entry, sizeof(entry), 0);
            }
        }

        // Everything changed lies in 0x100 .. the end of the log (the table, BEST and RUN); bytes 0..0xFF (the
        // legacy best record) are never written here.
        pending_from = table_end;
        pending_end = AC_OFF_RUN + int(log_len);
        stage = stage_write;
        break;

    case stage_write:
        if(pending_from < pending_end)
        {
            int n = bn::min(chunk, pending_end - pending_from);
            bn::sram::write_span_offset(bn::span<const uint8_t>(image.bytes + pending_from, n), pending_from);
            pending_from += n;
        }
        else
        {
            bn::sram::write_span_offset(bn::span<const uint8_t>(image.bytes + AC_SAVE_BASE, table_end - AC_SAVE_BASE),
                                        AC_SAVE_BASE);
            stage = stage_idle;
            g_dbg_run_written = g_dbg_run_written + 1;
        }
        break;

    default:
        break;
    }
}

void reset_after_results()
{
    uint8_t scene = rules_scene();
    if(! done || scene == SC_CLEAR || scene == SC_MISSED)
    {
        return;
    }

    // The player left the results (Start: back to the title). The rules would start the next run without
    // game_init(), so its log could not replay from boot: finish the save now (a few frames at most), then restart
    // the ROM, which boots into a fresh seed, game_init(seed) and recorder.
    while(stage != stage_idle)
    {
        flush();
    }

    bn::core::reset();
}

bool ghost_at(uint32_t step, ac_ghost_pt& out)
{
    ac_ghost_pt me;
    game_ghost(&me);
    if(live_step == 0 && step != 0 && (me.flags & AC_GHOST_PLAY))
    {
        live_step = step;                            // play started: an aligned ghost starts here
    }

    // arcade/src/ac_replay.c samples after steps 1, period + 1, 2 * period + 1, ... (it samples once it has stepped,
    // counting from 0), so sample k shows the run after k * period + 1 steps: step s lies between samples
    // (s - 1) / period and the next one.
    if(ghost_count == 0 || step == 0)
    {
        return false;
    }

    // An aligned ghost (one with in-play samples) shows its first in-play sample on this run's first in-play step and
    // runs on from there, so time spent on the title does not offset it. An unaligned one runs from boot.
    if(ghost_anchor)
    {
        if(live_step == 0 || step < live_step)
        {
            return false;
        }

        step = ghost_anchor + (step - live_step);
    }

    uint32_t i = (step - 1) / ghost_period;
    if(i >= ghost_count - 1)
    {
        out = ghost_point(ghost_count - 1);          // the ghost stays where its run ended
        return true;
    }

    ac_ghost_pt a = ghost_point(i);
    ac_ghost_pt b = ghost_point(i + 1);
    int t = int((step - 1) % ghost_period);
    int period = int(ghost_period);
    out = a;
    if((a.flags & ~AC_GHOST_PLAY) == (b.flags & ~AC_GHOST_PLAY))     // never slide across a room change
    {
        out.x = int16_t(a.x + (int(b.x) - int(a.x)) * t / period);
        out.y = int16_t(a.y + (int(b.y) - int(a.y)) * t / period);
    }
    return true;
}

}

// See arcade_runtime.h. Ported from SHIP IT!'s game/src/runlog.cpp: rules_scene() checks became game_ended() edges,
// rules_hash() became game_hash(), the game id comes from GAME_INFO.
#include "arcade_runtime.h"

#include "bn_common.h"
#include "bn_core.h"
#include "bn_math.h"
#include "bn_span.h"
#include "bn_sram.h"

extern "C" {
#include "ac_buttons.h"
#include "ac_game.h"
#include "ac_log.h"
#include "ac_rng.h"
#include "arcade_game_ext.h"
}

// Read by the headless tests at their ELF symbol addresses (games/common/py/arcade_test.py).
extern "C" {
volatile uint32_t g_dbg_hash;          // game_hash() after the last step
volatile uint32_t g_dbg_steps;         // game steps since boot
volatile uint32_t g_dbg_run_written;   // last-run sections written to SRAM since boot
volatile uint32_t g_dbg_ghost;         // 1 while the saved ghost is drawn (report_ghost), else 0
volatile uint32_t g_dbg_ghost_xy;      // the drawn ghost's (x << 16) | y, u16 each, game_ghost() units
volatile uint32_t g_dbg_phase;         // 0 recording, 1 saving, 2 saved or kept (3 resetting: set just before
                                       // bn::core::reset(), which clears it: never observable by the tests)
volatile uint32_t g_dbg_player_xy;     // game_ghost() of the current state: (x << 16) | y, u16 each
volatile uint32_t g_dbg_best;         // (had_best << 1) | was_new: a BEST existed at boot; the run just ended set a new one
volatile uint32_t g_dbg_seed;         // this boot's seed (game_init's and the log header's)
}

namespace arcade
{

namespace
{
    constexpr uint32_t log_cap = AC_OFF_GHOST - AC_OFF_RUN;    // the RUN section's capacity (14336, ac_save.h)
    static_assert(log_cap == 14336, "RUN capacity changed in ac_save.h");

    struct save_image
    {
        alignas(4) uint8_t bytes[AC_SAVE_SIZE];
    };

    BN_DATA_EWRAM_BSS save_image image;
    ac_rec rec;
    bool done = false;              // the run ended: the log is closed
    uint32_t step_count = 0;

    // Saving a run is spread over the frames after it ends, one step a frame: the log is recorded straight into the
    // image's RUN slot (no copy); its checksum is summed 1 KB a frame and the section committed in place; then BEST;
    // then SRAM is written 1 KB a frame (Butano writes it a byte at a time), payloads first and the section table
    // (0x100..0x1FF) last, so a power cut midway leaves sections whose checksums fail rather than a table pointing
    // at half-written data.
    enum stage_t { stage_idle, stage_sum, stage_best, stage_write };
    constexpr int chunk = 1024;
    constexpr int table_end = AC_OFF_PROFILE;
    uint8_t* const log_buf = image.bytes + AC_OFF_RUN;
    stage_t stage = stage_idle;
    ac_result result;
    uint32_t final_hash = 0;
    uint32_t log_len = 0;
    bool truncated = false;
    uint32_t summed = 0;
    uint16_t sum = 0;
    int pending_from = 0;
    int pending_end = 0;

    bool best_new = false;
    bool had_best = false;          // a BEST section was stored at boot
    // The stored RUN, read at boot before the recorder overwrites its slot in the image: it counts as finished with
    // BEST's time when BEST's final hash is the log's (the runtime writes BEST only with the RUN it came from).
    bool stored_run_finished = false;
    uint32_t stored_run_time = 0;
    bool keep_run = false;          // this run did not beat the stored one: nothing is written
    uint32_t best_time = 0;

    char name[13] = {};
    uint32_t trophies_owned = 0;

    const uint8_t* ghost_points = nullptr;
    uint32_t ghost_period = 0;
    uint32_t ghost_count = 0;
    uint32_t ghost_anchor = 0;      // ghost step (k * period + 1) of its first sample in play; 0: unaligned ghost
    uint32_t live_step = 0;         // this run's first step whose game_ghost() is in play; 0: not yet

    const char* game_id()
    {
        return GAME_INFO.id;
    }

    bool header_ok()
    {
        const uint8_t* h = image.bytes + AC_SAVE_BASE;
        const char* id = game_id();
        return h[0] == 'A' && h[1] == 'C' && h[2] == 'S' && h[3] == 'V' && h[4] == (AC_SAVE_VERSION & 0xFF) &&
               h[5] == (AC_SAVE_VERSION >> 8) && h[6] == uint8_t(id[0]) && h[7] == uint8_t(id[1]) &&
               h[8] == uint8_t(id[2]) && h[9] == uint8_t(id[3]);
    }

    void put32(uint8_t* p, uint32_t v)
    {
        p[0] = uint8_t(v);
        p[1] = uint8_t(v >> 8);
        p[2] = uint8_t(v >> 16);
        p[3] = uint8_t(v >> 24);
    }

    // The ghost is checked once at boot (ac_save_get sums the whole payload). Its points stay in the image (EWRAM):
    // the recorder writes only the RUN slot, which ends where the GHOST slot starts.
    void load_ghost()
    {
        ghost_points = nullptr;
        ghost_period = 0;
        ghost_count = 0;
        ghost_anchor = 0;
        uint32_t len;
        uint8_t flags;
        const char* id = game_id();
        const uint8_t* g = ac_save_get(image.bytes, id, AC_SEC_GHOST, &len, &flags);
        if(! g || len < 16 || g[0] != 'A' || g[1] != 'C' || g[2] != 'G' || g[3] != '1' ||
           g[4] != uint8_t(id[0]) || g[5] != uint8_t(id[1]) || g[6] != uint8_t(id[2]) || g[7] != uint8_t(id[3]))
        {
            return;                                  // absent, damaged, or another game's track
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
        ghost_anchor = 0;
        for(uint32_t k = 0; k < count; ++k)
        {
            if(g[16 + 6 * k + 5] & AC_GHOST_PLAY)
            {
                ghost_anchor = k * period + 1;
                break;
            }
        }
    }

    void load_profile()
    {
        name[0] = 0;
        trophies_owned = 0;
        uint32_t len;
        uint8_t flags;
        const uint8_t* p = ac_save_get(image.bytes, game_id(), AC_SEC_PROFILE, &len, &flags);
        if(! p || len < 24)
        {
            return;
        }

        int n = 0;
        while(n < 12 && p[n] >= 32 && p[n] < 127)    // printable ASCII only: the font has nothing else
        {
            name[n] = char(p[n]);
            ++n;
        }

        name[n] = 0;
        trophies_owned = ac_log_u32(p + 20);
    }

    // A RUN recorded by an older ROM (another rules version) can no longer be verified or give a ghost: the replay
    // tools open only logs of their own rules. It and BEST (written only with the RUN it came from, so as old) are
    // dropped from the image, so the first run under these rules is saved whatever its time instead of being kept
    // out by a best the launcher can no longer use. SRAM follows with the next save of the table.
    void drop_older_rules_run()
    {
        uint32_t len;
        uint8_t flags;
        const uint8_t* run = ac_save_get(image.bytes, game_id(), AC_SEC_RUN, &len, &flags);
        if(run && len >= AC_LOG_HEADER && ac_log_u32(run + 8) != GAME_INFO.rules_version)
        {
            ac_save_commit(image.bytes, AC_SEC_RUN, 0, 0, 0);      // length 0 reads as absent
            ac_save_commit(image.bytes, AC_SEC_BEST, 0, 0, 0);
        }
    }

    void load_best()
    {
        best_time = 0;
        had_best = false;
        uint32_t len;
        uint8_t flags;
        const uint8_t* b = ac_save_get(image.bytes, game_id(), AC_SEC_BEST, &len, &flags);
        if(b && len >= 4)
        {
            had_best = true;
            best_time = ac_log_u32(b);
        }
    }

    void load_stored_run()
    {
        stored_run_finished = false;
        stored_run_time = 0;
        uint32_t len, best_len;
        uint8_t flags, best_flags;
        const uint8_t* run = ac_save_get(image.bytes, game_id(), AC_SEC_RUN, &len, &flags);
        const uint8_t* best = ac_save_get(image.bytes, game_id(), AC_SEC_BEST, &best_len, &best_flags);
        if(run && ! (flags & AC_FLAG_TRUNCATED) && len >= AC_LOG_HEADER && best && best_len >= 16 &&
           ac_log_u32(best + 12) == ac_log_u32(run + 20))
        {
            stored_run_finished = true;
            stored_run_time = ac_log_u32(best);
        }
    }

    // This boot's seed. With a profile carrying a seed nonce (written fresh by the launcher before each launch), the
    // boot count in it is bumped and written back first (payload, then the section table, as the run save does), so
    // every boot, including one started from the results without the launcher, gets its own seed. No profile, or no
    // nonce: seed 0, the classic game.
    uint32_t boot_seed()
    {
        uint32_t len;
        uint8_t flags;
        const uint8_t* p = ac_save_get(image.bytes, game_id(), AC_SEC_PROFILE, &len, &flags);
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
        for(uint32_t i = 0; i < len && i < sizeof(profile); ++i)
        {
            profile[i] = p[i];
        }

        put32(profile + AC_PROFILE_BOOTS, boots);
        uint32_t n = bn::min(len, uint32_t(sizeof(profile)));
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

    uint32_t pack_xy(int16_t x, int16_t y)
    {
        return (uint32_t(uint16_t(x)) << 16) | uint16_t(y);
    }

    // The run ended this step. Its end frame is already a heavy one (the results appear): only close the log and
    // decide the best here; the rest is flushed over the next frames.
    void finish()
    {
        done = true;
        game_result(&result);
        final_hash = game_hash();
        log_len = ac_rec_finish(&rec, final_hash, result.score, result.trophies);
        truncated = rec.full;
        summed = 0;
        sum = ac_save_sum(log_buf, 0);               // the checksum's seed (0x5A5A)

        best_new = false;
        if(result.finished)
        {
            uint32_t len;
            uint8_t flags;
            const uint8_t* best = ac_save_get(image.bytes, game_id(), AC_SEC_BEST, &len, &flags);
            if(! best || len < 4 || result.time_frames < ac_log_u32(best))
            {
                best_new = true;
                best_time = result.time_frames;
            }
        }

        // RUN keeps the cartridge's best run: an absent, truncated or unfinished stored run is replaced; a finished one
        // only by a finished run with a smaller time (a tie keeps it). A kept run leaves SRAM untouched (a new best
        // always replaces RUN, so nothing else changed either).
        keep_run = stored_run_finished && ! (result.finished && result.time_frames < stored_run_time);
        stage = keep_run ? stage_idle : stage_sum;
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
            if(best_new)
            {
                uint8_t entry[32] = {};
                put32(entry, result.time_frames);
                put32(entry + 4, result.score);
                put32(entry + 8, result.trophies);
                put32(entry + 12, final_hash);
                ac_save_put(image.bytes, AC_SEC_BEST, entry, sizeof(entry), 0);
            }

            // Everything changed lies in 0x100 .. the end of the log (the table, BEST and RUN); 0..0xFF never.
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
                bn::sram::write_span_offset(
                        bn::span<const uint8_t>(image.bytes + AC_SAVE_BASE, table_end - AC_SAVE_BASE), AC_SAVE_BASE);
                stage = stage_idle;
                g_dbg_run_written = g_dbg_run_written + 1;
            }
            break;

        default:
            break;
        }
    }
}

void boot()
{
    bn::sram::read(image);
    if(! header_ok())
    {
        ac_save_format(image.bytes, game_id());     // blank, another game's or another version: saved with the first run
    }

    drop_older_rules_run();
    load_ghost();
    load_profile();
    load_best();
    load_stored_run();                          // before ac_rec_begin reuses the RUN slot
    uint32_t seed = boot_seed();
    game_init(seed);                            // the replayer starts from game_init(the header's seed) too
    ac_rec_begin(&rec, log_buf, log_cap, game_id(), GAME_INFO.rules_version, seed);
    g_dbg_seed = seed;
    done = false;
    best_new = false;
    stage = stage_idle;
    step_count = 0;
    live_step = 0;
    g_dbg_phase = 0;
    g_dbg_steps = 0;
    g_dbg_hash = game_hash();
}

uint16_t read_buttons()
{
    // KEYINPUT is active-low; the low 10 bits are the GBA keys in the rules' bit order.
    return uint16_t(~*reinterpret_cast<volatile uint16_t*>(0x04000130) & BTN_MASK);
}

void after_step(uint16_t buttons)
{
    ++step_count;
    if(! done)                                       // the log is closed once the run ends
    {
        ac_rec_push(&rec, buttons);
    }

    flush();                                         // the save steps start the frame after the end
    bool ended = game_ended() != 0;
    if(! done && ended)
    {
        finish();
    }
    else if(done && ! ended)
    {
        // The player left the results. The rules would start the next run without game_init(), so its log could
        // not replay from boot: finish the save now (a few frames' work at most), then restart the ROM, which boots
        // into a fresh seed, game_init(seed) and recorder.
        while(stage != stage_idle)
        {
            flush();
        }

        g_dbg_phase = 3;
        bn::core::reset();
    }

    g_dbg_hash = game_hash();
    g_dbg_steps = step_count;
    g_dbg_phase = ! done ? 0 : (stage != stage_idle ? 1 : 2);
    ac_ghost_pt me;
    game_ghost(&me);
    if(live_step == 0 && (me.flags & AC_GHOST_PLAY))
    {
        live_step = step_count;                      // play started: an aligned ghost starts here
    }
    g_dbg_player_xy = pack_xy(me.x, me.y);
    g_dbg_best = (uint32_t(had_best) << 1) | uint32_t(best_new);
}

bool ghost_at(uint32_t step, ac_ghost_pt& out)
{
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
    if((a.flags & ~AC_GHOST_PLAY) == (b.flags & ~AC_GHOST_PLAY))    // never slide across a room, lap, ... change
    {
        out.x = int16_t(a.x + (int(b.x) - int(a.x)) * t / period);
        out.y = int16_t(a.y + (int(b.y) - int(a.y)) * t / period);
    }
    return true;
}

void report_ghost(bool shown, const ac_ghost_pt& pt)
{
    g_dbg_ghost = shown ? 1 : 0;
    g_dbg_ghost_xy = shown ? pack_xy(pt.x, pt.y) : 0;
}

uint32_t steps()
{
    return step_count;
}

const char* profile_name()
{
    return name;
}

uint32_t profile_trophies()
{
    return trophies_owned;
}

bool has_ghost()
{
    return ghost_count != 0;
}

bool best_is_new()
{
    return best_new;
}

uint32_t best_time_frames()
{
    return best_time;
}

}

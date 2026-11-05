"""Sizes, colours and timings for the 800 x 480 screen (layout C of the approved mockup)."""
W, H = 800, 480
MARGIN = 22

BG = (11, 13, 18)
PANEL = (22, 24, 30)
ACCENT = (240, 102, 61)   # highlights; themes.apply() changes BG, PANEL, ACCENT and TINT
CURRENT = "anypercent"    # the theme id, for its sponsor logo
TINT = 0                  # how strongly BG washes over a game's blurred art on Home
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

TOP_Y = 12
TAB_SIZE = 15
TAB_GAP = 22

ROW_Y = 86
TILE_BIG = 150
TILE = 120
TILE_GAP = 18
TILE_RADIUS = 10
OUTLINE = 3
LABEL_SIZE = 12

TITLE_SIZE = 28
META_SIZE = 14
DETAILS_BOTTOM = H - 44
PLAY_W, PLAY_H = 120, 42
MORE_D = 42

HINT_SIZE = 12

SLIDE_MS = 120
FADE_MS = 150
NOTICE_MS = 3000
OSD_MS = 1500                            # the volume / brightness bar after a PS + D-pad step
CRASH_NOTICE_MS = 8000                   # "... closed unexpectedly": long enough to be seen after a restart

MASCOT_CPS = 40                          # PB's words type out at this many characters a second
MASCOT_HOLD_MS = 6000                    # then stay this long before PB moves on by itself
VOICE_WAIT_MS = 1500                     # the optional voice gets this long to reword a line, else PB's own words

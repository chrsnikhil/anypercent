from arca_launcher.actions import Action as A
from arca_launcher.library import Game
from arca_launcher.model import (SETTINGS_ROWS, Launch, Nav, PowerOff, Screen, SetBrightness, SetTouchControls,
                                 SetVolume, Sleep, Visitor, Wake)


def g(title, rom_exists=True, shots=("s0.png", "s1.png")):
    gid = title.lower().replace(" ", "-")
    return Game(id=gid, title=title, rom=f"/roms/{gid}.gb", rom_origin="built", rom_exists=rom_exists, shots=shots)


GAMES = [g("uCity"), g("2048gb"), g("AIRPLANZ"), g("Broken", rom_exists=False)]


def titles(row):
    return [x.title if x else "LIBRARY" for x in row]


def test_row_is_a_to_z_then_the_library_tile():
    assert titles(Nav(GAMES).row) == ["2048gb", "AIRPLANZ", "Broken", "uCity", "LIBRARY"]


def test_recently_played_come_first_newest_first():
    nav = Nav(GAMES, last_played={"ucity": 1.0, "airplanz": 2.0})
    assert titles(nav.row) == ["AIRPLANZ", "uCity", "2048gb", "Broken", "LIBRARY"]


def test_row_stops_at_both_ends():
    nav = Nav(GAMES)
    nav.apply(A.LEFT)
    assert nav.row_index == 0
    for _ in range(20):
        nav.apply(A.RIGHT)
    assert nav.row_index == 4 and nav.selected is None


def test_a_launches_the_selected_game():
    nav = Nav(GAMES)
    assert nav.apply(A.A) == Launch(nav.row[0])


def test_missing_rom_gives_a_notice_not_a_launch():
    nav = Nav(GAMES)
    nav.apply(A.RIGHT)
    nav.apply(A.RIGHT)
    assert nav.apply(A.A) is None
    assert nav.notice == "Broken: ROM file missing"


def test_start_opens_info_but_not_on_the_library_tile():
    nav = Nav(GAMES)
    nav.apply(A.START)
    assert nav.screen is Screen.INFO and nav.info_game.title == "2048gb"
    nav.apply(A.B)
    for _ in range(4):
        nav.apply(A.RIGHT)
    nav.apply(A.START)
    assert nav.screen is Screen.HOME


def test_buttons_row():
    nav = Nav(GAMES)
    nav.apply(A.DOWN)
    assert nav.home_focus == "buttons" and nav.button_index == 0
    nav.apply(A.RIGHT)
    nav.apply(A.RIGHT)
    assert nav.button_index == 1
    nav.apply(A.A)
    assert nav.screen is Screen.INFO
    nav.apply(A.B)
    nav.apply(A.UP)
    assert nav.home_focus == "tiles"


def test_library_tile_has_one_button_and_opens_the_grid():
    nav = Nav(GAMES)
    for _ in range(4):
        nav.apply(A.RIGHT)
    nav.apply(A.DOWN)
    nav.apply(A.RIGHT)
    assert nav.button_index == 0
    nav.apply(A.A)
    assert nav.screen is Screen.LIBRARY


def test_played_moves_the_game_to_the_front_and_goes_home():
    nav = Nav(GAMES)
    nav.apply(A.RIGHT)
    nav.apply(A.RIGHT)
    nav.apply(A.RIGHT)              # uCity
    nav.apply(A.START)              # its info page
    nav.played("ucity", 10.0)
    assert nav.stack == [Screen.HOME]
    assert nav.row_index == 0 and nav.selected.title == "uCity"


def test_game_finished_badly_sets_a_notice_until_cleared():
    nav = Nav(GAMES)
    nav.game_finished(True)
    assert nav.notice is None
    nav.game_finished(False)
    assert nav.notice == "The game closed unexpectedly"
    nav.clear_notice()
    assert nav.notice is None


def test_a_crash_notice_names_the_game():
    nav = Nav(GAMES)
    nav.game_finished(False, "Snake")
    assert nav.notice == "Snake closed unexpectedly"


def test_tabs_switch_only_at_the_top_level():
    nav = Nav(GAMES)
    nav.apply(A.R)
    assert nav.screen is Screen.SETTINGS and nav.tab == "settings"
    nav.apply(A.R)
    assert nav.screen is Screen.SETTINGS
    nav.apply(A.L)
    assert nav.screen is Screen.HOME and nav.tab == "games"
    nav.apply(A.START)
    nav.apply(A.R)
    assert nav.screen is Screen.INFO


def test_settings_volume_and_brightness():
    nav = Nav(GAMES, volume=95, brightness=20)
    nav.apply(A.R)
    assert nav.apply(A.RIGHT) == SetVolume(100)
    assert nav.apply(A.RIGHT) is None
    nav.apply(A.DOWN)
    assert nav.apply(A.LEFT) == SetBrightness(10)
    assert nav.apply(A.LEFT) is None and nav.brightness == 10


def test_brightness_unavailable_does_nothing():
    nav = Nav(GAMES, brightness_available=False)
    nav.apply(A.R)
    nav.apply(A.DOWN)
    assert nav.apply(A.RIGHT) is None and nav.brightness == 100


def test_about_and_back():
    nav = Nav(GAMES)
    nav.apply(A.R)
    for _ in SETTINGS_ROWS:
        nav.apply(A.DOWN)
    assert nav.settings_index == len(SETTINGS_ROWS) - 1
    while SETTINGS_ROWS[nav.settings_index] != "about":
        nav.apply(A.UP)
    nav.apply(A.A)
    assert nav.screen is Screen.ABOUT
    nav.apply(A.B)
    assert nav.screen is Screen.SETTINGS
    nav.apply(A.B)
    assert nav.screen is Screen.HOME


def test_library_grid_navigation():
    many = [g(f"Game {i:02d}") for i in range(12)]          # 5 + 5 + 2
    nav = Nav(many)
    nav.row_index = len(nav.row) - 1
    nav.apply(A.A)
    assert nav.screen is Screen.LIBRARY
    nav.apply(A.LEFT)
    nav.apply(A.UP)
    assert nav.grid_index == 0
    for _ in range(9):
        nav.apply(A.RIGHT)
    assert nav.grid_index == 4                              # stops at the row end
    nav.apply(A.DOWN)
    assert nav.grid_index == 9
    nav.apply(A.DOWN)
    assert nav.grid_index == 11                             # partial last row: the last game
    nav.apply(A.A)
    assert nav.screen is Screen.INFO and nav.info_game.title == "Game 11"
    nav.apply(A.B)
    assert nav.screen is Screen.LIBRARY
    nav.apply(A.B)
    assert nav.screen is Screen.HOME


def test_info_screenshots_wrap_and_zero_shots_is_safe():
    nav = Nav([g("Solo", shots=("a", "b", "c")), g("Bare", shots=())])
    nav.apply(A.RIGHT)
    nav.apply(A.START)                                      # "Solo" is second A to Z
    nav.apply(A.LEFT)
    assert nav.shot_index == 2
    nav.apply(A.B)
    nav.apply(A.LEFT)
    nav.apply(A.START)
    nav.apply(A.RIGHT)
    assert nav.screen is Screen.INFO


def test_empty_library_never_crashes():
    nav = Nav([])
    for a in list(A) * 3:
        nav.apply(a)
    nav.stack = [Screen.HOME]
    nav.apply(A.A)
    assert nav.screen is Screen.LIBRARY
    for a in list(A):
        nav.apply(a)


# touch ------------------------------------------------------------------------------------------------------------
# Views report what a tap landed on as a target: ("tile", i), ("button", i), ("tab", name), ("grid", i),
# ("play",), ("shot",), ("card",), ("setting", i), ("slider", i, fraction), ("back",); None is empty space.

def test_tap_a_tile_selects_it_and_tap_again_launches():
    nav = Nav(GAMES)
    assert nav.tap(("tile", 1)) is None
    assert nav.row_index == 1 and nav.home_focus == "tiles"
    assert nav.tap(("tile", 1)) == Launch(nav.row[1])


def test_tap_the_selected_tile_launches_even_from_the_buttons():
    nav = Nav(GAMES)
    nav.apply(A.DOWN)
    assert nav.tap(("tile", 0)) == Launch(nav.row[0])


def test_tap_the_library_tile_twice_opens_the_library():
    nav = Nav(GAMES)
    nav.tap(("tile", 4))
    assert nav.screen is Screen.HOME and nav.selected is None
    nav.tap(("tile", 4))
    assert nav.screen is Screen.LIBRARY


def test_tap_play_and_more_buttons():
    nav = Nav(GAMES)
    assert nav.tap(("button", 0)) == Launch(nav.row[0])
    assert nav.tap(("button", 1)) is None
    assert nav.screen is Screen.INFO and nav.info_game is nav.row[0]


def test_tap_tabs():
    nav = Nav(GAMES)
    nav.tap(("tab", "settings"))
    assert nav.screen is Screen.SETTINGS
    nav.tap(("tab", "games"))
    assert nav.screen is Screen.HOME
    nav.tap(("tab", "games"))
    assert nav.screen is Screen.HOME


def test_empty_space_and_unknown_targets_do_nothing_on_home():
    nav = Nav(GAMES)
    before = (nav.stack[:], nav.row_index, nav.home_focus)
    for target in (None, ("grid", 2), ("play",), ("slider", 0, 0.5), ("back",), ("tile", 99)):
        assert nav.tap(target) is None
    assert (nav.stack, nav.row_index, nav.home_focus) == before


def test_swipe_scrolls_the_home_row_by_tiles_and_stops_at_the_ends():
    nav = Nav(GAMES)
    nav.apply(A.DOWN)                                         # focus on the buttons: a swipe brings it back
    nav.swipe(2, 0)
    assert nav.row_index == 2 and nav.home_focus == "tiles"
    nav.swipe(10, 0)
    assert nav.row_index == 4
    nav.swipe(-1, 0)
    assert nav.row_index == 3
    nav.swipe(0, 3)                                           # vertical does nothing on Home
    assert nav.row_index == 3 and nav.home_focus == "tiles" and nav.screen is Screen.HOME


def library_nav(n=12):
    nav = Nav([g(f"Game {i:02d}") for i in range(n)])        # 5 + 5 + 2
    nav.tap(("tile", len(nav.row) - 1))
    nav.tap(("tile", len(nav.row) - 1))
    assert nav.screen is Screen.LIBRARY
    return nav


def test_library_tap_selects_then_opens_info():
    nav = library_nav()
    nav.tap(("grid", 7))
    assert nav.grid_index == 7 and nav.screen is Screen.LIBRARY
    nav.tap(("grid", 7))
    assert nav.screen is Screen.INFO and nav.info_game.title == "Game 07"


def test_library_swipes_scroll_rows_and_columns():
    nav = library_nav()
    nav.swipe(0, 1)
    assert nav.grid_index == 5
    nav.swipe(3, 0)
    assert nav.grid_index == 8
    nav.swipe(0, 5)
    assert nav.grid_index == 11                               # the last game, like DOWN onto a partial row
    nav.swipe(0, -9)
    assert nav.grid_index == 1
    nav.swipe(9, 0)
    assert nav.grid_index == 4                                # a row end stops it, like RIGHT


def test_back_leaves_every_inner_screen():
    nav = library_nav()
    nav.tap(("grid", 0))
    nav.tap(("grid", 0))
    assert nav.screen is Screen.INFO
    nav.tap(("back",))
    assert nav.screen is Screen.LIBRARY
    nav.tap(("back",))
    assert nav.screen is Screen.HOME
    nav.tap(("tab", "settings"))
    nav.tap(("setting", SETTINGS_ROWS.index("about")))
    nav.tap(("setting", SETTINGS_ROWS.index("about")))
    assert nav.screen is Screen.ABOUT
    nav.tap(("back",))
    assert nav.screen is Screen.SETTINGS


def test_info_tap_outside_closes_and_inside_does_not():
    nav = Nav([g("Solo", shots=("a", "b", "c"))])
    nav.tap(("button", 1))
    assert nav.screen is Screen.INFO
    nav.tap(("card",))
    assert nav.screen is Screen.INFO
    nav.tap(("shot",))
    assert nav.shot_index == 1
    nav.swipe(-1, 0)
    assert nav.shot_index == 0
    nav.swipe(1, 0)
    assert nav.shot_index == 1
    assert nav.tap(("play",)) == Launch(nav.info_game)
    nav.tap(None)
    assert nav.screen is Screen.HOME


def test_settings_tap_selects_a_row_then_the_slider_sets_the_value():
    nav = Nav(GAMES, volume=50, brightness=40)
    nav.tap(("tab", "settings"))
    assert nav.tap(("setting", 1)) is None and nav.settings_index == 1
    assert nav.tap(("setting", 1)) is None and nav.screen is Screen.SETTINGS
    assert nav.tap(("slider", 0, 0.72)) == SetVolume(70)     # tapping a slider selects its row and sets it
    assert nav.settings_index == 0
    assert nav.tap(("slider", 0, 0.7)) is None               # same value: no command
    assert nav.tap(("slider", 0, 1.3)) == SetVolume(100)
    assert nav.tap(("slider", 0, -1)) == SetVolume(0)
    assert nav.tap(("slider", 1, 0.0)) == SetBrightness(10)  # never fully dark
    assert nav.tap(("slider", 1, 1.0)) == SetBrightness(100)


def test_settings_slider_does_nothing_when_brightness_is_unavailable():
    nav = Nav(GAMES, brightness_available=False)
    nav.tap(("tab", "settings"))
    assert nav.tap(("slider", 1, 0.2)) is None and nav.brightness == 100


def test_taps_in_about_and_empty_space_in_settings_do_nothing():
    nav = Nav(GAMES)
    nav.tap(("tab", "settings"))
    nav.tap(None)
    nav.swipe(3, 3)
    assert nav.screen is Screen.SETTINGS and nav.settings_index == 0
    nav.tap(("setting", SETTINGS_ROWS.index("about")))
    nav.tap(("setting", SETTINGS_ROWS.index("about")))
    nav.tap(None)
    nav.tap(("tab", "games"))                                  # tabs are not on the About screen
    assert nav.screen is Screen.ABOUT


def test_touch_on_an_empty_library_never_crashes():
    nav = Nav([])
    for target in (None, ("tile", 0), ("tile", 0), ("grid", 0), ("grid", 3), ("back",), ("shot",), ("play",)):
        nav.tap(target)
        nav.swipe(1, 1)
        nav.swipe(-1, -1)
        nav.press(target)
        nav.drag_grid(0, 2, 2)
        nav.select_row(5)
        nav.release()


# press and release: tiles select the instant the finger lands; everything acts on release --------------------------

def test_press_on_a_tile_selects_it_at_once_and_its_release_does_not_launch():
    nav = Nav(GAMES)
    assert nav.press(("tile", 2)) is None
    assert nav.row_index == 2 and nav.pressed == ("tile", 2)
    assert nav.release() is None and nav.pressed is None and nav.screen is Screen.HOME


def test_press_on_the_selected_tile_launches_only_on_release():
    nav = Nav(GAMES)
    assert nav.press(("tile", 0)) is None
    assert nav.release() == Launch(nav.row[0])


def test_a_press_that_becomes_a_drag_never_acts():
    nav = Nav(GAMES)
    nav.press(("tile", 0))
    nav.cancel_press()
    assert nav.pressed is None and nav.release() is None
    nav.press(("tab", "settings"))
    nav.cancel_press()
    assert nav.release() is None and nav.screen is Screen.HOME


def test_buttons_show_pressed_and_act_on_release():
    nav = Nav(GAMES)
    for target, screen in ((("tab", "settings"), Screen.SETTINGS), (("tab", "games"), Screen.HOME),
                           (("button", 1), Screen.INFO), (("back",), Screen.HOME)):
        assert nav.press(target) is None
        assert nav.pressed == target and nav.screen is not screen
        nav.release()
        assert nav.screen is screen and nav.pressed is None
    assert nav.press(("button", 0)) is None
    assert nav.release() == Launch(nav.row[0])


def test_info_outside_press_closes_on_release():
    nav = Nav(GAMES)
    nav.apply(A.START)
    nav.press(None)
    assert nav.screen is Screen.INFO
    nav.release()
    assert nav.screen is Screen.HOME


def test_library_press_selects_and_release_on_the_selected_opens_info():
    nav = library_nav()
    nav.press(("grid", 6))
    assert nav.grid_index == 6
    nav.release()
    assert nav.screen is Screen.LIBRARY
    nav.press(("grid", 6))
    nav.release()
    assert nav.screen is Screen.INFO


def test_slider_press_sets_the_value_at_once():
    nav = Nav(GAMES, volume=80)
    nav.tap(("tab", "settings"))
    assert nav.press(("slider", 0, 0.3)) == SetVolume(30)
    assert nav.release() is None and nav.volume == 30


def test_settings_row_press_selects_on_release():
    nav = Nav(GAMES)
    nav.tap(("tab", "settings"))
    nav.press(("setting", 2))
    assert nav.settings_index == 0
    nav.release()
    assert nav.settings_index == 2


def test_select_row_clamps_and_focuses_the_tiles():
    nav = Nav(GAMES)
    nav.apply(A.DOWN)
    nav.select_row(3)
    assert nav.row_index == 3 and nav.home_focus == "tiles"
    nav.select_row(99)
    assert nav.row_index == 4
    nav.select_row(-3)
    assert nav.row_index == 0


def test_drag_grid_moves_from_where_the_drag_began():
    nav = library_nav()                                           # 12 games: rows of 5, 5, 2
    nav.drag_grid(2, 0, 1)
    assert nav.grid_index == 7
    nav.drag_grid(2, 0, 0)
    assert nav.grid_index == 2                                    # back where it began, no drift
    nav.drag_grid(2, 0, 9)
    assert nav.grid_index == 11                                   # the short last row: its last game
    nav.drag_grid(2, 9, 0)
    assert nav.grid_index == 4                                    # a row end stops it
    nav.drag_grid(2, -9, -9)
    assert nav.grid_index == 0
    nav.drag_grid(10, 3, 0)
    assert nav.grid_index == 11


def settings_nav(**kw):
    nav = Nav(GAMES, **kw)
    nav.apply(A.R)
    return nav


def test_on_screen_controls_row_sits_above_about():
    assert SETTINGS_ROWS.index("controls") == SETTINGS_ROWS.index("about") - 1
    assert Nav(GAMES).touch_controls is False


def test_on_screen_controls_toggle_with_a_left_and_right():
    nav = settings_nav()
    while SETTINGS_ROWS[nav.settings_index] != "controls":
        nav.apply(A.DOWN)
    assert nav.apply(A.A) == SetTouchControls(True) and nav.touch_controls is True        # A flips it
    assert nav.apply(A.LEFT) == SetTouchControls(False) and nav.touch_controls is False   # left is Off
    assert nav.apply(A.LEFT) is None and nav.touch_controls is False                      # a held D-pad repeats
    assert nav.apply(A.RIGHT) == SetTouchControls(True) and nav.touch_controls is True     # right is On
    assert nav.apply(A.RIGHT) is None and nav.touch_controls is True
    assert nav.screen is Screen.SETTINGS


def test_on_screen_controls_tap_selects_then_toggles():
    i = SETTINGS_ROWS.index("controls")
    nav = settings_nav(touch_controls=True)
    assert nav.tap(("setting", i)) is None and nav.settings_index == i and nav.touch_controls is True
    assert nav.tap(("setting", i)) == SetTouchControls(False)
    assert nav.tap(("switch", i)) == SetTouchControls(True)


def test_on_screen_controls_switch_acts_on_release_and_selects_its_row():
    i = SETTINGS_ROWS.index("controls")
    nav = settings_nav()
    assert nav.press(("switch", i)) is None and nav.touch_controls is False
    assert nav.release() == SetTouchControls(True) and nav.settings_index == i
    nav.press(("switch", i))
    nav.cancel_press()                                         # a drag off the switch does nothing
    assert nav.release() is None and nav.touch_controls is True


# --- sleep and power off ---------------------------------------------------------------------------------------

def to_row(nav, key):
    while SETTINGS_ROWS[nav.settings_index] != key:
        nav.apply(A.DOWN if SETTINGS_ROWS.index(key) > nav.settings_index else A.UP)


def test_sleep_and_power_off_sit_at_the_bottom_power_off_last():
    assert SETTINGS_ROWS[-2:] == ("sleep", "power")
    assert SETTINGS_ROWS.index("about") < SETTINGS_ROWS.index("sleep")


def test_sleep_dims_and_any_button_wakes_to_where_it_was():
    nav = settings_nav()
    to_row(nav, "sleep")
    assert nav.apply(A.A) == Sleep() and nav.screen is Screen.SLEEP
    assert nav.apply(A.R) == Wake()                       # even L / R wake it: they do not switch tabs
    assert nav.screen is Screen.SETTINGS and SETTINGS_ROWS[nav.settings_index] == "sleep"


def test_any_tap_or_press_on_the_sleep_screen_wakes_it():
    nav = settings_nav()
    to_row(nav, "sleep")
    nav.apply(A.A)
    assert nav.wake() == Wake() and nav.screen is Screen.SETTINGS
    assert nav.wake() is None                              # awake already: nothing to do


def test_power_off_needs_a_second_press_to_confirm():
    nav = settings_nav()
    to_row(nav, "power")
    assert nav.apply(A.A) is None and nav.power_armed
    assert nav.apply(A.A) == PowerOff()


def test_moving_away_or_b_cancels_a_pending_power_off():
    nav = settings_nav()
    to_row(nav, "power")
    nav.apply(A.A)
    nav.apply(A.UP)
    assert not nav.power_armed
    nav.apply(A.DOWN)
    nav.apply(A.A)
    nav.apply(A.B)
    assert not nav.power_armed and nav.screen is Screen.HOME


def test_power_off_by_touch_is_select_then_tap_then_tap_to_confirm():
    i = SETTINGS_ROWS.index("power")
    nav = settings_nav()
    assert nav.tap(("setting", i)) is None and nav.settings_index == i and not nav.power_armed
    assert nav.tap(("setting", i)) is None and nav.power_armed
    assert nav.tap(("setting", i)) == PowerOff()


def test_a_tap_elsewhere_cancels_a_pending_power_off():
    i = SETTINGS_ROWS.index("power")
    nav = settings_nav()
    nav.tap(("setting", i))
    nav.tap(("setting", i))
    nav.tap(None)
    assert not nav.power_armed


def test_the_controller_page_opens_from_settings_and_b_comes_back():
    nav = settings_nav()
    to_row(nav, "gamepad")
    nav.apply(A.A)
    assert nav.screen is Screen.GAMEPAD
    nav.apply(A.B)
    assert nav.screen is Screen.SETTINGS and SETTINGS_ROWS[nav.settings_index] == "gamepad"


def test_the_controller_page_opens_by_touch_select_then_tap():
    i = SETTINGS_ROWS.index("gamepad")
    nav = settings_nav()
    nav.tap(("setting", i))
    assert nav.screen is Screen.SETTINGS
    nav.tap(("setting", i))
    assert nav.screen is Screen.GAMEPAD
    nav.tap(("back",))
    assert nav.screen is Screen.SETTINGS


# --- theme menu and attract mode ---------------------------------------------------------------------------------

def test_the_theme_trick_opens_the_menu_and_a_picks_a_theme():
    from arca_launcher.model import SetTheme
    from arca_launcher.themes import THEMES
    nav = Nav(GAMES)
    assert nav.apply(A.THEMES) is None and nav.screen is Screen.THEMES
    nav.apply(A.DOWN)
    assert nav.apply(A.A) == SetTheme(THEMES[1].id)
    assert nav.screen is Screen.HOME and nav.theme == THEMES[1].id


def test_b_closes_the_theme_menu_without_changing_anything():
    nav = Nav(GAMES, theme="arkiv")
    nav.apply(A.THEMES)
    nav.apply(A.DOWN)
    assert nav.apply(A.B) is None and nav.screen is Screen.HOME and nav.theme == "arkiv"


def test_the_theme_menu_opens_on_the_current_theme():
    from arca_launcher.themes import THEMES
    nav = Nav(GAMES, theme="hedera")
    nav.apply(A.THEMES)
    assert THEMES[nav.theme_index].id == "hedera"


def test_the_theme_menu_by_touch():
    from arca_launcher.model import SetTheme
    from arca_launcher.themes import THEMES
    nav = Nav(GAMES)
    nav.apply(A.THEMES)
    assert nav.tap(("theme", 2)) == SetTheme(THEMES[2].id)
    nav.apply(A.THEMES)
    assert nav.tap(None) is None and nav.screen is Screen.HOME            # outside the menu closes it


def test_attract_mode_starts_only_from_home_and_any_button_leaves_it():
    nav = Nav(GAMES)
    assert nav.attract() is True and nav.screen is Screen.ATTRACT
    assert nav.apply(A.A) == Visitor() and nav.screen is Screen.HOME       # the press only wakes it, plays nothing
    nav.apply(A.R)
    assert nav.attract() is False and nav.screen is Screen.SETTINGS        # never over Settings or a game page


def test_a_tap_leaves_attract_mode_and_does_nothing_else():
    nav = Nav(GAMES)
    nav.attract()
    assert nav.tap(("tile", 2)) == Visitor() and nav.screen is Screen.HOME and nav.row_index == 0


def test_a_game_with_a_saved_place_offers_continue_and_restart():
    nav = Nav(GAMES)
    g = nav.selected
    nav.resumable = {g.id}
    assert nav.apply(A.A) == Launch(g, resume=True)                # A on the tile continues
    nav.apply(A.DOWN)                                               # to the buttons: Continue, Restart, ...
    nav.apply(A.RIGHT)
    assert nav.apply(A.A) == Launch(g, resume=False)               # Restart starts afresh
    nav.apply(A.RIGHT)
    nav.apply(A.A)
    assert nav.screen is Screen.INFO                                     # the third button is the info page
    assert nav.apply(A.A) == Launch(g, resume=True)                # Play on the info page continues too


def test_without_a_saved_place_play_starts_afresh_and_the_second_button_is_info():
    nav = Nav(GAMES)
    g = nav.selected
    assert nav.apply(A.A) == Launch(g, resume=False)
    nav.apply(A.DOWN)
    nav.apply(A.RIGHT)
    nav.apply(A.A)
    assert nav.screen is Screen.INFO


def test_device_health_opens_from_settings_and_b_comes_back():
    nav = Nav(GAMES)
    nav.apply(A.R)                                       # the Settings tab
    nav.settings_index = SETTINGS_ROWS.index("health")
    nav.apply(A.A)
    assert nav.screen is Screen.HEALTH
    nav.apply(A.B)
    assert nav.screen is Screen.SETTINGS

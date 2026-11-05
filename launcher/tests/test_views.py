import os
from arca_launcher import model
from arca_launcher.actions import Action
from arca_launcher.model import Nav, Screen
from arca_launcher.render.chrome import Status
from arca_launcher.render.views import Views
from conftest import LONG_TITLE, distinct_colours, snapshot

STATUS = Status("9:41 PM", None)


def draw(screen, nav, name, frames=30):
    views = Views(screen.gfx, screen.art)
    for _ in range(frames):
        views.draw(nav, 16, STATUS)
    out = snapshot(screen.ren, name)
    assert out.get_size() == (800, 480) and distinct_colours(out) > 3
    return out


def open_library(nav):
    nav.row_index = len(nav.row) - 1
    nav.apply(Action.A)
    assert nav.screen is Screen.LIBRARY


def test_library_grid(screen):
    nav = Nav(screen.games)
    open_library(nav)
    nav.apply(Action.RIGHT)
    draw(screen, nav, "library")


def test_library_grid_when_empty(screen):
    nav = Nav([])
    open_library(nav)
    draw(screen, nav, "library-empty")


def test_info_page(screen):
    nav = Nav(screen.games)
    nav.apply(Action.START)                        # Alpha Quest
    nav.apply(Action.RIGHT)
    assert nav.screen is Screen.INFO
    draw(screen, nav, "info")


def test_info_page_with_long_texts_and_no_art(screen):
    nav = Nav(screen.games)
    for title in ("Gamma", LONG_TITLE):
        nav.stack = [Screen.HOME]
        nav.row_index = next(i for i, x in enumerate(nav.row) if x is not None and x.title == title)
        nav.apply(Action.START)
        draw(screen, nav, "info-" + title.split()[0].lower())


def test_settings_and_about(screen):
    nav = Nav(screen.games, brightness_available=False)
    nav.apply(Action.R)
    draw(screen, nav, "settings")
    for _ in range(model.SETTINGS_ROWS.index("about")):
        nav.apply(Action.DOWN)
    nav.apply(Action.A)
    assert nav.screen is Screen.ABOUT
    draw(screen, nav, "about")


def test_notice_starting_card_and_message(screen):
    nav = Nav(screen.games)
    nav.notice = "The game closed unexpectedly"
    draw(screen, nav, "notice")
    views = Views(screen.gfx, screen.art)
    views.starting(screen.games[0])
    snapshot(screen.ren, "starting")
    views.message("No game library", "No game library at /nowhere. Build it with: bash run.sh launcher", STATUS)
    snapshot(screen.ren, "message")


def test_notice_stays_clear_of_the_buttons_and_hints(screen):
    from arca_launcher.render import chrome, theme
    screen.gfx.fill(theme.BG)
    short = chrome.toast(screen.gfx, "The game closed unexpectedly")
    long = chrome.toast(screen.gfx, "The Extraordinarily Long Title of a Game That Keeps Going: ROM file missing")
    for rect in (short, long):
        assert rect.top >= theme.DETAILS_BOTTOM and rect.bottom <= theme.H     # below the Play button row
        assert rect.left >= theme.MARGIN and rect.right <= theme.W - 300       # left of the button hints


def test_hints_name_the_dualsense_buttons(screen, monkeypatch):
    """The console's only pad is a DualSense: hints draw Cross, Circle, Square and Triangle as the pad's own symbols,
    and say OPTIONS and L1 R1, never A, B, START or L R."""
    from arca_launcher.render import chrome, theme
    seen = drawn_text(screen, monkeypatch)
    glyphs = []
    real = screen.gfx.pad_glyph
    monkeypatch.setattr(screen.gfx, "pad_glyph", lambda name, size: (glyphs.append(name), real(name, size))[1])
    screen.gfx.fill(theme.BG)
    chrome.hints(screen.gfx, [("A", "Play"), ("B", "Back"), ("X", "OK"), ("O", "Back"), ("S", "Mock"),
                              ("Y", "PB"), ("START", "Info"), ("L R", "Tabs"), ("←→", "Screens")])
    snapshot(screen.ren, "hints_dualsense")
    assert glyphs == ["triangle", "square", "circle", "cross", "circle", "cross"]   # drawn right to left
    assert "OPTIONS" in seen and "L1 R1" in seen and "←→" in seen
    assert not {"A", "B", "X", "O", "S", "Y", "START", "L R"} & set(seen)


def test_home_hints_name_triangle_for_pb_on_an_arcade_game(screen):
    from dataclasses import replace
    from arca_launcher.render import chrome, theme
    arcade = replace(screen.games[0], arcade={"id": "MDGP", "replay": "/x"})
    nav = Nav([arcade] + list(screen.games[1:]))
    views = Views(screen.gfx, screen.art)
    assert ("Y", "PB") not in views.home._hints(nav)                       # the handler is off
    nav.handler_enabled = True
    hints = views.home._hints(nav)
    assert hints[:2] == [("A", "Play"), ("Y", "PB")]
    screen.gfx.fill(theme.BG)
    assert chrome.hints(screen.gfx, hints) >= theme.W - 300                # clear of a notice
    nav.row_index = next(i for i, x in enumerate(nav.row) if x is not None and not x.arcade)
    assert ("Y", "PB") not in views.home._hints(nav)                       # no board, no PB to race


def test_the_library_and_info_hints_name_triangle_for_pb_too(screen, monkeypatch):
    from dataclasses import replace
    from arca_launcher.render import chrome
    seen = []
    real = chrome.hints
    monkeypatch.setattr(chrome, "hints", lambda gfx, items, **kw: (seen.append(list(items)), real(gfx, items, **kw)))
    arcade = replace(screen.games[0], arcade={"id": "MDGP", "replay": "/x"})
    nav = Nav([arcade] + list(screen.games[1:]))
    nav.handler_enabled = True
    open_library(nav)
    nav.grid_index = next(i for i, g in enumerate(nav.az) if g.arcade)
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    assert ("Y", "PB") in seen[-1]
    nav.apply(Action.A)                                                     # its Info page
    assert nav.screen is Screen.INFO
    views.draw(nav, 16, STATUS)
    assert ("Y", "PB") in seen[-1]
    nav.handler_enabled = False
    views.draw(nav, 16, STATUS)
    assert ("Y", "PB") not in seen[-1]


def test_the_starting_card_says_what_the_pad_does_in_a_game(screen, monkeypatch):
    """A game's title screen says PRESS START, and a DualSense has no Start: the card shown while it loads says
    OPTIONS is Start, Cross is A, Circle is B, and how to get back. An app (the Browser) gets no game controls."""
    from dataclasses import replace
    seen = drawn_text(screen, monkeypatch)
    glyphs = []
    real = screen.gfx.pad_glyph
    monkeypatch.setattr(screen.gfx, "pad_glyph", lambda name, size: (glyphs.append(name), real(name, size))[1])
    views = Views(screen.gfx, screen.art)
    views.starting(screen.games[0])
    snapshot(screen.ren, "starting_controls")
    assert {"OPTIONS", "Start", "A", "B"} <= set(seen) and {"cross", "circle"} <= set(glyphs)
    assert any("PS" in s for s in seen)
    seen.clear()
    views.starting(replace(screen.games[0], app="browser"))
    assert "OPTIONS" not in seen


def test_library_rows_scrolled_above_the_top_bar_are_not_drawn(screen):
    from dataclasses import replace
    from arca_launcher.render.library_view import LibraryView
    many = [replace(screen.games[0], id=f"g{i:02d}", title=f"Game {i:02d}") for i in range(12)]
    nav = Nav(many)
    open_library(nav)
    nav.apply(Action.DOWN)
    nav.apply(Action.DOWN)                         # third row selected: the grid scrolls up one row
    view = LibraryView(screen.gfx, screen.art)
    for _ in range(40):
        view.draw(nav, 16, STATUS)
    assert not set(range(5)) & set(view.visible)   # no half-cut first row under the top bar
    assert {5, 10} <= set(view.visible)


def drawn_text(screen, monkeypatch):
    seen = []
    real = screen.gfx.text

    def record(s, *a, **k):
        seen.append(s)
        return real(s, *a, **k)
    monkeypatch.setattr(screen.gfx, "text", record)
    return seen


def test_the_name_on_screen_is_any_percent(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    nav.apply(Action.R)
    for _ in range(model.SETTINGS_ROWS.index("about")):
        nav.apply(Action.DOWN)
    nav.apply(Action.A)                             # About
    Views(screen.gfx, screen.art).draw(nav, 16, STATUS)
    assert "Any% launcher" in " ".join(seen) or "ANY% LAUNCHER" in seen
    assert any("Outfit" in s for s in seen) and not any("Inter" in s or "ARCA" in s for s in seen)
    seen.clear()
    Views(screen.gfx, screen.art).message("No game library", "Nothing here.", STATUS)
    assert "Any%" in seen and "ARCA" not in seen


# touch targets ------------------------------------------------------------------------------------------------------

def settle(views, nav, frames=40):
    for _ in range(frames):
        views.draw(nav, 16, STATUS)


def test_home_touch_targets(screen):
    from arca_launcher.render import theme
    nav = Nav(screen.games)
    views = Views(screen.gfx, screen.art)
    settle(views, nav)
    big, small = theme.TILE_BIG, theme.TILE
    y = theme.ROW_Y + big // 2
    assert views.hit(theme.MARGIN + big // 2, y) == ("tile", 0)
    second = theme.MARGIN + big + theme.TILE_GAP
    assert views.hit(second + small // 2, y) == ("tile", 1)
    assert views.hit(second - theme.TILE_GAP // 2 + 1, y) == ("tile", 1)    # the gap is split: no dead zone
    assert views.hit(second + small // 2, theme.ROW_Y + big + 16) == ("tile", 1)   # the label counts as the tile
    assert views.hit(*views.home.play_rect.center) == ("button", 0)
    assert views.hit(*views.home.more_rect.center) == ("button", 1)
    assert views.hit(theme.MARGIN + 10, theme.TOP_Y + 8) == ("tab", "games")
    assert views.hit(theme.MARGIN + 90, theme.TOP_Y + 8) == ("tab", "settings")
    assert views.hit(400, 30) is None
    assert views.hit(-5, 900) is None


def test_the_back_arrow_is_on_every_inner_screen(screen):
    from arca_launcher.render import chrome
    nav = Nav(screen.games)
    views = Views(screen.gfx, screen.art)
    back = chrome.BACK_HIT.center
    settle(views, nav, 2)
    assert views.hit(*back) != ("back",)                      # Home has the tabs there instead
    open_library(nav)
    settle(views, nav)
    assert views.hit(*back) == ("back",)
    out = snapshot(screen.ren, "library-back")
    assert tuple(out.get_at(chrome.BACK_ARROW.center))[:3] != (0, 0, 0)
    nav.apply(Action.A)
    assert nav.screen is Screen.INFO
    settle(views, nav)
    assert views.hit(*back) == ("back",)
    nav.stack = [Screen.SETTINGS, Screen.ABOUT]
    settle(views, nav, 2)
    assert views.hit(*back) == ("back",)
    snapshot(screen.ren, "about-back")
    nav.stack = [Screen.SETTINGS]
    settle(views, nav, 2)
    assert views.hit(*back) != ("back",)


def test_library_touch_targets(screen):
    from arca_launcher.render import library_view, theme
    nav = Nav(screen.games)
    open_library(nav)
    views = Views(screen.gfx, screen.art)
    settle(views, nav)
    y = library_view.Y0 + theme.TILE // 2
    for i in range(len(screen.games)):
        x = library_view.X0 + i * (theme.TILE + theme.TILE_GAP) + theme.TILE // 2
        assert views.hit(x, y) == ("grid", i)
    assert views.hit(700, y) is None                          # no fifth game in the fixture


def test_info_touch_targets(screen):
    from arca_launcher.render import info, theme
    nav = Nav(screen.games)
    nav.apply(Action.START)
    views = Views(screen.gfx, screen.art)
    settle(views, nav)
    assert views.hit(theme.MARGIN + 150, 200) == ("shot",)
    assert views.hit(info.COL_X + 100, 150) == ("card",)
    assert views.hit(info.COL_X + 20, theme.DETAILS_BOTTOM - 10) == ("play",)
    assert views.hit(400, theme.H - 8) is None                # the strip under the card: outside, closes it
    assert views.hit(theme.W - 8, 240) is None


def test_settings_touch_targets(screen):
    from arca_launcher.render import theme
    nav = Nav(screen.games, volume=30)
    nav.apply(Action.R)
    views = Views(screen.gfx, screen.art)
    settle(views, nav, 2)
    bar = views.settings.bars[0]
    assert views.hit(80, bar.centery) == ("setting", 0)
    kind, row, frac = views.hit(bar.x + bar.w // 4, bar.centery)
    assert (kind, row) == ("slider", 0) and abs(frac - 0.25) < 0.01
    assert views.hit(bar.x + bar.w // 4, bar.centery + 20)[:2] == ("slider", 0)    # a finger-sized strip
    assert views.hit(80, views.settings.rows[2].centery) == ("setting", 2)
    assert views.hit(theme.W - 8, 470) is None


def test_the_message_screen_has_no_touch_targets(screen):
    nav = Nav(screen.games)
    views = Views(screen.gfx, screen.art)
    settle(views, nav, 2)
    views.message("No game library", "Nothing here.", STATUS)
    assert views.hit(40, 20) is None and views.hit(97, 161) is None


def pixel(screen, xy):
    return tuple(screen.ren.to_surface().get_at(xy))[:3]


def test_a_pressed_button_is_drawn_pressed(screen):
    from arca_launcher.render import theme
    nav = Nav(screen.games)
    views = Views(screen.gfx, screen.art)
    settle(views, nav)
    play = views.home.play_rect
    ring = (play.centerx, play.top - 3)                         # just outside the white Play button
    tab = (theme.MARGIN + 90, theme.TOP_Y + 8)                  # inside the Settings tab
    before = pixel(screen, ring), pixel(screen, tab)
    nav.press(("button", 0))
    settle(views, nav, 1)
    assert pixel(screen, ring) != before[0]
    snapshot(screen.ren, "home-play-pressed")
    nav.cancel_press()
    nav.press(("tab", "settings"))
    settle(views, nav, 1)
    assert pixel(screen, tab) != before[1] and pixel(screen, ring) == before[0]
    nav.cancel_press()
    settle(views, nav, 1)
    assert (pixel(screen, ring), pixel(screen, tab)) == before


def test_the_home_row_follows_a_held_finger_then_eases_back(screen):
    from arca_launcher.render import theme
    nav = Nav(screen.games)
    views = Views(screen.gfx, screen.art)
    settle(views, nav)
    tile0 = next(h.rect for h in views.hits if h.target == ("tile", 0))
    views.home.hold(-50)                                        # dragged 50 px to the right
    settle(views, nav, 3)
    moved = next(h.rect for h in views.hits if h.target == ("tile", 0))
    assert moved.x == tile0.x + 50
    views.home.release()
    assert views.home.scroll.value == -50                       # no jump when the finger lifts
    settle(views, nav, 40)
    assert views.home.scroll.value == 0 and next(h.rect for h in views.hits if h.target == ("tile", 0)) == tile0


def test_on_screen_controls_row_shows_off_or_on_and_has_a_switch(screen):
    nav = Nav(screen.games)
    nav.apply(Action.R)
    i = model.SETTINGS_ROWS.index("controls")
    views = Views(screen.gfx, screen.art)
    settle(views, nav, 2)
    row = views.settings.rows[i]
    sw = views.settings.switches[i]
    assert sw is not None and row.contains(sw)
    assert views.hit(80, row.centery) == ("setting", i)
    assert views.hit(sw.centerx, sw.centery) == ("switch", i)
    assert views.hit(sw.centerx, sw.centery + 20) == ("switch", i)            # a finger-sized strip
    assert views.settings.label(nav, "controls") == "Off"
    snapshot(screen.ren, "settings-controls-off")
    nav.touch_controls = True
    nav.settings_index = i
    settle(views, nav, 2)
    assert views.settings.label(nav, "controls") == "On"
    snapshot(screen.ren, "settings-controls-on")



def test_sleep_screen_shows_the_clock_and_battery_and_no_targets(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    nav.apply(Action.R)
    for _ in range(model.SETTINGS_ROWS.index("sleep")):
        nav.apply(Action.DOWN)
    nav.apply(Action.A)
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    assert STATUS.clock in seen and any("wake" in s for s in seen)
    assert views.hit(400, 240) is None


def test_settings_rows_all_fit_above_the_hints(screen):
    nav = Nav(screen.games)
    nav.apply(Action.R)
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    assert len(views.settings.rows) == len(model.SETTINGS_ROWS)
    assert views.settings.rows[-1].bottom <= 480 - 40                      # clear of the button hints


def test_controller_page_lists_the_dualsense_buttons(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    nav.apply(Action.R)
    for _ in range(model.SETTINGS_ROWS.index("gamepad")):
        nav.apply(Action.DOWN)
    nav.apply(Action.A)
    Views(screen.gfx, screen.art).draw(nav, 16, STATUS)
    snapshot(screen.gfx.r, "controller")
    text = " ".join(seen).lower()
    for words in ("Controller", "Cross", "Circle", "L1 + R1", "Quit to the launcher", "RetroArch menu", "Launcher", "In games"):
        assert words.lower() in text, words
    assert "Launcher: PB hub, mock pick" not in seen                       # --no-handler: Triangle does nothing
    seen.clear()
    nav.handler_enabled = True
    Views(screen.gfx, screen.art).draw(nav, 16, STATUS)
    assert "Launcher: PB hub, mock pick" in seen



def test_theme_menu_lists_every_theme(screen, monkeypatch):
    from arca_launcher.themes import THEMES
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    nav.apply(Action.THEMES)
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    snapshot(screen.gfx.r, "themes")
    for t in THEMES:
        assert t.name in seen
    assert views.hit(400, 240) is not None                                   # the rows take taps


def test_attract_mode_shows_a_game_and_how_to_play(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    nav.attract()
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    snapshot(screen.gfx.r, "attract")
    text = " ".join(seen).lower()
    assert "press any button" in text and any(g.title.lower() in text for g in screen.games)
    assert "Run to beat" not in seen                                     # no board read for it


def test_attract_mode_shows_the_booth_link_as_a_qr_code(screen, monkeypatch):
    from arca_launcher.model import Screen
    from arca_launcher.render import handler_art
    seen = drawn_text(screen, monkeypatch)
    coded = []
    real = handler_art.qr_surface
    monkeypatch.setattr(handler_art, "qr_surface", lambda text: (coded.append(text), real(text))[1])
    nav = Nav(screen.games)
    nav.stack = [Screen.ATTRACT]
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    assert coded == [] and "Scan for the project" not in seen                # no link set: no code
    nav.booth_url = "https://ethglobal.com/showcase/any-percent"
    views.draw(nav, 16, STATUS)
    snapshot(screen.gfx.r, "attract_booth_qr")
    assert coded == ["https://ethglobal.com/showcase/any-percent"] and "Scan for the project" in seen


def test_attract_mode_shows_games_never_apps(screen, monkeypatch):
    """The booth display cycles the games; the Browser (an app) has nothing to show there."""
    from dataclasses import replace
    from arca_launcher.model import Screen
    from arca_launcher.render import booth_views
    seen = drawn_text(screen, monkeypatch)
    app = replace(screen.games[1], id="browser", title="Browser", app="browser", rom_exists=True)
    nav = Nav([screen.games[0], app])
    nav.stack = [Screen.ATTRACT]
    views = Views(screen.gfx, screen.art)
    for _ in range(4):                                                     # a whole cycle and more
        views.draw(nav, booth_views.CYCLE_MS, STATUS)
    assert screen.games[0].title in seen and "Browser" not in seen


def test_attract_mode_shows_an_arcade_games_run_to_beat(screen, monkeypatch):
    """A booth hook: an arcade game whose board PB has read shows whose time to beat, with PB's face."""
    from arca_launcher.model import Screen
    seen = drawn_text(screen, monkeypatch)
    nav = Nav([screen.games[0]])
    nav.stack = [Screen.ATTRACT]
    nav.board_times[screen.games[0].id] = ("RIA", "1:41.17")
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, STATUS)
    assert "Run to beat" not in seen                                     # the handler is off
    nav.handler_enabled = True
    views.draw(nav, 16, STATUS)
    snapshot(screen.gfx.r, "attract_board")
    assert {"Run to beat", "RIA", "1:41.17", "Race her ghost"} <= set(seen)



def test_top_bar_shows_no_wifi_and_a_power_warning(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    views = Views(screen.gfx, screen.art)
    views.draw(nav, 16, Status("9:41 PM", 80, wifi=0, warning="Low power"))
    snapshot(screen.gfx.r, "status_warnings")
    assert "No Wi-Fi" in seen and "Low power" in seen
    seen.clear()
    views.draw(nav, 16, Status("9:41 PM", 80, wifi=70))
    assert "No Wi-Fi" not in seen and "Low power" not in seen


def test_a_heat_warning_carries_the_temperature(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    views = Views(screen.gfx, screen.art)
    views.draw(Nav(screen.games), 16, Status("9:41 PM", 80, warning="Hot", temp=63))
    snapshot(screen.gfx.r, "status_hot")
    assert "Hot 63°C" in seen
    seen.clear()
    views.draw(Nav(screen.games), 16, Status("9:41 PM", 80, warning="Low power", temp=50))
    assert "Low power" in seen and not any("°C" in s for s in seen)       # the temperature only explains heat



def test_sponsor_themes_show_their_logo_and_any_percent_does_not(screen):
    from arca_launcher import themes
    from arca_launcher.render import chrome
    try:
        for t in themes.THEMES:
            themes.apply(t.id)
            r = chrome.sponsor_logo(screen.gfx, 20, 440, 24)
            assert (r is None) == (t.id == "anypercent"), t.id
    finally:
        themes.apply("anypercent")


def test_home_carries_the_sponsor_logo(screen):
    from arca_launcher import themes
    try:
        themes.apply("ethglobal")
        draw(screen, Nav(screen.games), "home_ethglobal")
        themes.apply("chainlink")
        draw(screen, Nav(screen.games), "home_chainlink")
    finally:
        themes.apply("anypercent")


def test_top_bar_shows_the_controller_battery(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    Views(screen.gfx, screen.art).draw(Nav(screen.games), 16, Status("9:41 PM", None, pad=77))
    snapshot(screen.gfx.r, "status_pad")
    assert "77%" in seen


def test_a_game_with_a_saved_place_shows_continue_and_restart(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    views = Views(screen.gfx, screen.art)
    nav = Nav(screen.games)
    nav.resumable = {nav.selected.id}
    views.draw(nav, 16, Status("9:41 PM", 80))
    snapshot(screen.gfx.r, "home_continue")
    assert "Continue" in seen and "Restart" in seen and "Play" not in seen
    assert ("A", "Continue") in [(k, v) for k, v in views.home._hints(nav)]
    assert len([h for h in views.hits if h.target[0] == "button"]) == 3
    seen.clear()
    nav.resumable = set()
    views.draw(nav, 16, Status("9:41 PM", 80))
    assert "Play" in seen and "Continue" not in seen


def test_the_level_overlay_draws_a_bar(screen, monkeypatch):
    seen = drawn_text(screen, monkeypatch)
    views = Views(screen.gfx, screen.art)
    nav = Nav(screen.games)
    nav.osd = ("volume", 70)
    views.draw(nav, 16, Status("9:41 PM", 80))
    snapshot(screen.gfx.r, "osd_volume")
    assert "Volume" in seen and "70%" in seen


def test_the_info_page_says_how_to_play(screen, monkeypatch):
    import dataclasses
    seen = drawn_text(screen, monkeypatch)
    g = dataclasses.replace(screen.games[0], how_to={"goal": "Bounce to the flag and grab every coin.",
                                                     "controls": [["D-pad", "Roll"], ["A", "Jump"]]})
    nav = Nav([g] + screen.games[1:])
    nav._open_info(g)
    Views(screen.gfx, screen.art).draw(nav, 16, Status("9:41 PM", 80))
    snapshot(screen.gfx.r, "info_how_to")
    text = " ".join(seen)
    assert "HOW TO PLAY" in text and "Bounce to the flag" in text and "Jump" in text and "D-pad" in text


def test_the_how_to_card_names_the_dualsense_buttons(screen, monkeypatch):
    """games.json says A, B, Start, L and R, the GBA's buttons; the card says what to press on the DualSense."""
    import dataclasses
    from arca_launcher.render.info import pad_key
    assert [pad_key(k) for k in ("R + steer", "Down + A", "B (hold)", "L / R", "A / B / Start", "Select", "D-pad",
                                 "Start on title", "PS (hold)")] == \
        ["R1 + steer", "Down + Cross", "Circle (hold)", "L1 / R1", "Cross / Circle / OPTIONS", "Create", "D-pad",
         "OPTIONS on title", "PS (hold)"]
    seen = drawn_text(screen, monkeypatch)
    glyphs = []
    real = screen.gfx.pad_glyph
    monkeypatch.setattr(screen.gfx, "pad_glyph", lambda name, size: (glyphs.append(name), real(name, size))[1])
    g = dataclasses.replace(screen.games[0], how_to={"goal": "Three laps.", "controls": [
        ["A", "Accelerate"], ["B", "Brake"], ["R + steer", "Drift"], ["Start", "Pause"]]})
    nav = Nav([g] + screen.games[1:])
    nav._open_info(g)
    Views(screen.gfx, screen.art).draw(nav, 16, Status("9:41 PM", 80))
    snapshot(screen.gfx.r, "info_how_to_dualsense")
    assert {"cross", "circle"} <= set(glyphs) and {"R1 + steer", "OPTIONS"} <= set(seen)
    assert not {"R + steer", "Start"} & set(seen)


def test_the_health_screen_shows_readings_and_recent_crashes(screen, monkeypatch):
    from arca_launcher.model import Screen
    seen = drawn_text(screen, monkeypatch)
    nav = Nav(screen.games)
    nav.stack = [Screen.SETTINGS, Screen.HEALTH]
    nav.health = {"cpu_mhz": 1200, "uptime_s": 3725, "disks": [("Card", 48000), ("Saves", 205)],
                  "since_boot": ["Hot"]}
    nav.crashes = [(2000.0, "GTA III", "exit-code exited 139")]
    Views(screen.gfx, screen.art).draw(nav, 16, Status("9:41 PM", 80, warning="Hot", temp=63))
    snapshot(screen.gfx.r, "health")
    text = " ".join(seen)
    assert "Device health" in text and "63°C" in text and "1200 MHz" in text and "GTA III" in text
    assert "1 h 2 min" in text


def test_attract_mode_plays_a_games_clip(screen, monkeypatch):
    import dataclasses
    from PIL import Image
    from arca_launcher.model import Screen
    art_dir = os.path.join(screen.art.dir, "art")
    frames = []
    for i in range(3):
        rel = f"art/clipgame-clip-{i:02d}.png"
        Image.new("RGB", (160, 144), (0, 80 * i, 0)).save(os.path.join(screen.art.dir, rel))
        frames.append(rel)
    g = dataclasses.replace(screen.games[0], clip=tuple(frames))
    nav = Nav([g])
    nav.stack = [Screen.ATTRACT]
    views = Views(screen.gfx, screen.art)
    used = []
    real = screen.art.clip_frame
    monkeypatch.setattr(screen.art, "clip_frame", lambda game, i: used.append(i) or real(game, i))
    views.draw(nav, 16, Status("9:41 PM", 80))
    for _ in range(2):
        views.draw(nav, 100, Status("9:41 PM", 80))               # 10 frames a second
    snapshot(screen.gfx.r, "attract_clip")
    assert used[:3] == [0, 1, 2]


def test_only_one_games_clip_is_kept_in_memory(screen):
    import dataclasses
    from PIL import Image
    for gid in ("x", "y"):
        Image.new("RGB", (160, 144), (9, 9, 9)).save(os.path.join(screen.art.dir, f"art/{gid}-clip-00.png"))
    x = dataclasses.replace(screen.games[0], id="x", clip=("art/x-clip-00.png",))
    y = dataclasses.replace(screen.games[0], id="y", clip=("art/y-clip-00.png",))
    screen.art.clip_frame(x, 0)
    screen.art.clip_frame(y, 0)
    assert not [k for k in screen.art._cache if k[0] == "clip" and k[1] == "x"]

"""PB the handler on screen (render/handler_view.py, render/handler_cards.py): every state of the table drawn from a
real Flow on a mock sponsor whose clock never moves, so each call stays in flight and nothing changes state under the
drawing. Snapshots land in tests/out/handler_<state>.png for a look next to the mockup."""
import dataclasses

import pytest

from arca_launcher.handler.board import build
from arca_launcher.handler.flow import Flow
from arca_launcher.handler.ledger import Ledger
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.handler.sponsors import SponsorNames
from arca_launcher.handler.states import PLACEHOLDERS, STATES
from arca_launcher.handler_glue import MOCK_WALLET
from arca_launcher.model import Nav, Screen
from arca_launcher.render.chrome import Status
from conftest import distinct_colours, snapshot

STATUS = Status("9:41 PM", 80)
TODAY = "2026-11-06"
GREEN, RED, AMBER, GREY = (95, 209, 122), (224, 83, 61), (255, 177, 92), (92, 99, 114)
# A sample value for every placeholder the copy uses, plus the board rows the board card draws.
CTX = {"game": "Marine Drive GP", "target": "RIA", "target_time": "1:41.27", "gap": "1.6 s", "rank": "7th",
       "new_rank": "3rd", "split": "0:42 to 0:51, -0.40 s", "board_case": "ok", "best_frames": 6290,
       "run_frames": 6170, "run_time": "1:42.83", "ghost_look": "the *cyan kart*", "wallet": MOCK_WALLET,
       "other_book": "ANY-2KD", "runs": 14, "sold": 2, "buyer": "ARJUN", "code": "R4D-91X", "jti": "5e1f0c2a",
       "receipt": "mock-1a2b3c4d", "ghost_kept": "RIA's ghost is still yours. ", "board_rows": build(6070, 6290).rows}


class RealSponsors(MockSponsors):
    mock = False


def make_flow(tmp_path, name, sponsors=None, **ctx):
    """A real Flow sitting in state `name`, its words fully typed out."""
    sponsors = sponsors or MockSponsors(lambda: 0)
    ledger = Ledger(book="ANY-7QZ", listings=[{"game": "MDGP", "frames": 6170, "price": 10, "sold": 2}])
    flow = Flow(sponsors, ledger, str(tmp_path / "handler.json"), "MDGP", dict(CTX, **ctx), today=lambda: TODAY)
    flow.start(name)
    assert flow.state.name == name
    flow.ms_in_state = 60000
    return flow


def show(screen, flow, views=None, frames=1, nav=None):
    from arca_launcher.render.views import Views
    nav = nav or Nav(screen.games)
    nav.handler = flow
    nav.stack.append(Screen.HANDLER)
    views = views or Views(screen.gfx, screen.art)
    for _ in range(frames):
        views.draw(nav, 16, STATUS)
    return nav, views


def has_colour(surf, rect, colour):
    return any(tuple(surf.get_at((x, y)))[:3] == colour
               for x in range(rect.left, rect.right) for y in range(rect.top, rect.bottom))


def test_the_sample_context_fills_every_placeholder():
    names = {f.name for f in dataclasses.fields(SponsorNames)}
    engine = {"book", "price", "budget_left", "listing_days", "credential", "approve_how",
              "approve_via"}                                    # the flow fills these
    assert PLACEHOLDERS - names - engine <= set(CTX)


def test_every_state_draws(screen, tmp_path):
    from arca_launcher.coach import Line
    views = None
    for name in STATES:
        flow = make_flow(tmp_path, name)
        nav = Nav(screen.games)
        nav.mascot, nav.mascot_text = Line("happy", "Home's PB must not talk here."), "Home's PB must not talk here."
        nav, views = show(screen, flow, views, frames=40, nav=nav)
        out = snapshot(screen.ren, f"handler_{name}")
        assert out.get_size() == (800, 480) and distinct_colours(out) > 3, name
        assert views.mascot.shown == ""                              # Home's PB is not drawn on HANDLER
        assert views.handler.mascot.shown, name                      # the handler's PB is


def test_no_state_cuts_its_card_or_dialogue_short(screen, tmp_path, monkeypatch):
    """With demo-length values (the sample context), every state's card and PB's words fit: nothing is cut with an
    ellipsis. The cards still shrink text that would not fit, so a longer real value degrades, never overflows."""
    from arca_launcher.render import handler_cards, handler_view, text
    cut = []

    def spy(real):
        def ellipsize(s, width, measure):
            out = real(s, width, measure)
            if out != s:
                cut.append((name, s))
            return out
        return ellipsize
    real = text.ellipsize
    for module in (text, handler_cards, handler_view):
        monkeypatch.setattr(module, "ellipsize", spy(real))
    views = None
    for name in STATES:
        nav, views = show(screen, make_flow(tmp_path, name), views, frames=2)
    assert cut == []


def test_border_colours_follow_kind(screen, tmp_path):
    from arca_launcher.render.handler_view import CARD
    for name, colour in (("id_done", GREEN), ("id_rejected", RED), ("id_nocred", AMBER)):
        show(screen, make_flow(tmp_path, name))
        surf = screen.ren.to_surface()
        assert tuple(surf.get_at((CARD.x + 1, CARD.centery)))[:3] == colour, name


def test_mock_pill_is_drawn_and_tappable(screen, tmp_path):
    nav, views = show(screen, make_flow(tmp_path, "id_confirm"))
    pill = next(h for h in views.hits if h.target == ("handler", "square"))
    assert views.hit(*pill.shape.center) == ("handler", "square")
    assert has_colour(screen.ren.to_surface(), pill.shape, AMBER)
    nav, views = show(screen, make_flow(tmp_path, "id_confirm", sponsors=RealSponsors(lambda: 0)))
    assert not any(h.target == ("handler", "square") for h in views.hits)


def test_mascot_view_still_types(screen):
    import pygame
    import test_mascot
    from arca_launcher.render.mascot import BOX, NAME_COL, MascotView
    test_mascot.test_words_type_out_over_time(screen)
    test_mascot.test_pb_thinking_shows_no_words_yet(screen)
    view = MascotView(screen.gfx)
    view.draw_line("happy", "Scan this with *World App* now.", 60000)
    assert view.shown == "Scan this with World App now."
    view.draw_line("happy", "Scan this with *World App* now.", 250)  # 10 characters in
    assert view.shown == "Scan this "
    first_line = pygame.Rect(BOX.x + 20, BOX.y + 16, BOX.w - 40, 38)
    screen.gfx.fill((0, 0, 0))
    view.draw_line("happy", "Scan this with *World App* now.", 60000)
    assert has_colour(screen.ren.to_surface(), first_line, NAME_COL)   # the emphasis, in the name tag's amber
    screen.gfx.fill((0, 0, 0))
    view.draw_line("happy", "Scan this with World App now.", 60000)
    assert not has_colour(screen.ren.to_surface(), first_line, NAME_COL)


def test_step_strip_marks_done_now_and_fail(screen, tmp_path):
    from arca_launcher.render.handler_view import CARD, strip_segments
    from arca_launcher.render import theme
    segs = strip_segments(CARD, 4)                                   # Check, Pay, Load, Race
    show(screen, make_flow(tmp_path, "buy_load"))                    # at Load
    surf = screen.ren.to_surface()
    assert has_colour(surf, segs[0], GREEN) and has_colour(surf, segs[1], GREEN)
    assert tuple(surf.get_at((segs[2].x + 6, segs[2].centery)))[:3] == AMBER
    assert not has_colour(surf, segs[3], GREEN)
    assert tuple(surf.get_at((segs[3].x + 6, segs[3].centery)))[:3] == theme.PANEL
    show(screen, make_flow(tmp_path, "buy_down"))                    # failed at Pay
    surf = screen.ren.to_surface()
    assert has_colour(surf, segs[0], GREEN)
    assert tuple(surf.get_at((segs[1].x + 6, segs[1].centery)))[:3] == RED
    show(screen, make_flow(tmp_path, "buy_budget"))                  # halted at Pay
    assert tuple(screen.ren.to_surface().get_at((segs[1].x + 6, segs[1].centery)))[:3] == GREY


def test_card_box_back_rows_and_picks_are_tappable(screen, tmp_path):
    from arca_launcher.render.handler_view import CARD
    from arca_launcher.render.mascot import BOX
    nav, views = show(screen, make_flow(tmp_path, "hub"))
    assert views.hit(CARD.right - 10, CARD.bottom - 10) == ("handler", "cross")
    assert views.hit(BOX.right - 30, BOX.centery) == ("handler", "cross", "box")   # Cross, its own pressed look
    assert views.hit(20, 20) == ("back",)
    rows = [h for h in views.hits if h.target[:2] == ("handler", "row")]
    assert [h.target[2] for h in rows] == list(range(5))                 # mock: Start over shows
    assert views.hit(*rows[2].shape.center) == ("handler", "row", 2)
    nav, views = show(screen, make_flow(tmp_path, "hub", sponsors=RealSponsors(lambda: 0)))
    assert len([h for h in views.hits if h.target[:2] == ("handler", "row")]) == 4
    flow = make_flow(tmp_path, "ls_approve")
    flow.press("square")
    assert flow.outcomes_open
    nav, views = show(screen, flow)
    picks = [h for h in views.hits if h.target[:2] == ("handler", "pick")]
    assert len(picks) == len(flow.outcomes) == 5
    assert views.hit(*picks[3].shape.center) == ("handler", "pick", 3)
    snapshot(screen.ren, "handler_outcomes")


def test_hints_say_working_while_a_call_is_in_flight(screen, tmp_path, monkeypatch):
    from arca_launcher.render import chrome
    seen = []
    real = chrome.hints
    monkeypatch.setattr(chrome, "hints", lambda gfx, items, **kw: (seen.append(list(items)), real(gfx, items, **kw)))
    flow = make_flow(tmp_path, "buy_pay")
    assert flow.in_flight
    show(screen, flow)
    assert [label for _, label in seen[-1]] == ["working...", "Mock"]   # Square still works mid-call
    show(screen, make_flow(tmp_path, "id_verifying"))                # in flight, no outcomes to force
    assert [label for _, label in seen[-1]] == ["working..."]
    show(screen, make_flow(tmp_path, "buy_pay", sponsors=RealSponsors(lambda: 0)))
    assert [label for _, label in seen[-1]] == ["working..."]
    show(screen, make_flow(tmp_path, "id_confirm"))                  # a phone step: Cross works, Square has outcomes
    assert [label for _, label in seen[-1]] == ["OK", "Back", "Mock"]
    show(screen, make_flow(tmp_path, "id_done"))                     # no outcomes here
    assert [label for _, label in seen[-1]] == ["OK", "Back"]
    show(screen, make_flow(tmp_path, "id_confirm", sponsors=RealSponsors(lambda: 0)))
    assert [label for _, label in seen[-1]] == ["OK", "Back"]


def _texts(screen, monkeypatch):
    """Every string gfx.text draws from now on."""
    drawn, real = [], screen.gfx.text

    def spy(s, *a, **kw):
        drawn.append(s)
        return real(s, *a, **kw)
    monkeypatch.setattr(screen.gfx, "text", spy)
    return drawn


def test_the_qr_code_carries_a_mock_tag(screen, tmp_path):
    from arca_launcher.render.handler_cards import qr_box
    from arca_launcher.render.handler_view import CARD, STRIP_H
    content = CARD.copy()
    content.h -= STRIP_H                                             # id_scan has a step strip
    around = qr_box(content).inflate(16, 16)                         # the code and its corners
    show(screen, make_flow(tmp_path, "id_scan"))
    assert has_colour(screen.ren.to_surface(), around, AMBER)
    show(screen, make_flow(tmp_path, "id_scan", sponsors=RealSponsors(lambda: 0)))
    assert not has_colour(screen.ren.to_surface(), around, AMBER)


def test_the_qr_card_draws_a_real_code(screen, tmp_path, monkeypatch):
    """The QR scans: in mock mode it says so ("ANY% MOCK CODE ..."), a real adapter's link when its call gives one,
    else the bare code."""
    from arca_launcher.render import handler_art
    seen = []
    real = handler_art.qr_surface
    monkeypatch.setattr(handler_art, "qr_surface", lambda text: (seen.append(text), real(text))[1])
    flow = make_flow(tmp_path, "id_scan")
    show(screen, flow)
    assert seen[-1] == "ANY% MOCK CODE " + flow.ctx["code"]
    flow = make_flow(tmp_path, "id_scan", sponsors=RealSponsors(lambda: 0))
    show(screen, flow)
    assert seen[-1] == flow.ctx["code"]
    flow.ctx["qr"] = "https://example.org/verify?i=1"
    show(screen, flow)
    assert seen[-1] == "https://example.org/verify?i=1"


def test_the_qr_surface_is_the_code_with_a_quiet_zone():
    from arca_launcher import qr
    from arca_launcher.render import handler_art
    text = "ANY% MOCK CODE R4D-91X"
    surf, m = handler_art.qr_surface(text), qr.encode(text, "M")
    n = len(m)
    assert surf.get_size() == (n + 8, n + 8)
    assert all((tuple(surf.get_at((x + 4, y + 4)))[:3] == handler_art.INK) == m[y][x] for y in range(n) for x in range(n))
    assert all(tuple(surf.get_at((x, y)))[:3] == handler_art.WHITE for x in range(n + 8) for y in (0, 3, n + 4, n + 7))


def test_a_sign_in_link_gets_modules_a_phone_reads_and_an_impossible_one_never_crashes(screen, tmp_path):
    from arca_launcher.render import handler_art
    from arca_launcher.render.handler_cards import QR_BOX
    link = "https://world.org/verify?t=wld&i=" + "a" * 36 + "&k=" + "b" * 44 + "&v=2"       # about 120 bytes
    assert QR_BOX // handler_art.qr_surface(link).get_width() >= 4
    flow = make_flow(tmp_path, "id_scan")
    flow.ctx["qr"] = "x" * 3000                                       # more than any QR code holds
    show(screen, flow)                                                # drawn without its code, never a crash
    assert flow.ctx["code"]


def test_my_listings_show_the_games_title_and_days_left(screen, tmp_path, monkeypatch):
    import time
    from arca_launcher.render.handler_cards import days_left
    now = time.time()
    assert [days_left(now - d * 86400, now) for d in (0, 0.5, 2.5, 6.9, 7, 30)] == [7, 7, 5, 1, 0, 0]
    flow = make_flow(tmp_path, "listings_view", game_titles={"MDGP": "Marine Drive GP"})
    flow.ledger.listings = [{"game": "MDGP", "frames": 6170, "price": 10, "sold": 2, "at": now - 2.5 * 86400},
                            {"game": "gone", "frames": 6100, "price": 10, "sold": 0, "at": now - 30 * 86400}]
    drawn = _texts(screen, monkeypatch)
    show(screen, flow)
    snapshot(screen.ren, "handler_listings_days")
    assert "Marine Drive GP" in drawn and "MDGP" not in drawn
    assert "gone" in drawn                                           # a game no longer in the library: its id
    assert any("5 days left" in s for s in drawn) and any("0 days left" in s for s in drawn)


def test_a_hub_with_no_arcade_game_draws_three_rows(screen, tmp_path, monkeypatch):
    drawn = _texts(screen, monkeypatch)
    nav, views = show(screen, make_flow(tmp_path, "hub", arcade=False))
    rows = [h for h in views.hits if h.target[:2] == ("handler", "row")]
    assert len(rows) == 3
    assert [s for s in drawn if s in STATES["hub"].card["rows"]] == ["My record book", "My listings",
                                                                   "Start over (mock)"]
    nav.tap(views.hit(*rows[0].shape.center))
    assert nav.handler.state.name == "book_view"

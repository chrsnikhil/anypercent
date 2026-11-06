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
       "receipt": "mock-1a2b3c4d", "ghost_kept": "RIA's ghost is still yours. ", "board_rows": build(6070, 6290).rows,
       "console_tag": "C-7QZP", "console_line": "linked to ANY-7QZ",
       "scout_reason": "You lose 1.50 s in lap 2: RIA runs it in 33.25 s, you in 34.75 s.",
       "scout_by": "Picked by openai/gpt-oss-120b on Groq", "you_laps": (2140, 2085, 2065),
       "it_laps": (2087, 1995, 1994), "scout_lap": 2, "you_time": "1:44.83"}


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
              "approve_via", "now_price", "receipt_text", "payee", "refused_why", "scout_down",
              "record_line"}                                                 # the flow fills these
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


# ---- the scout, the chain ids, Humans only, one console: live-style stub data -----------------------------------------

HOUSE = "0.0.7700001"
ARKIV_TX = "0x" + "5c1d" * 15 + "9e02"
ARKIV_TX_URL = "https://rabdi.explorer.arkiv.network/tx/" + ARKIV_TX              # the longest link: 106 characters
REASON = "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s. Lap 2 is where the ghost gains most."
LIVE_CHAIN = {
    "buy": [{"label": "Hedera INTENT #7", "value": "tx 0.0.9185802@1793930440",
             "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1793930440-112233445"},
            {"label": "Paid 0.10 USDC", "value": "tx 0.0.9185802@1793930445",
             "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1793930445-643007633"},
            {"label": "Hedera RECEIPT #8", "value": "tx 0.0.9185802@1793930462",
             "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1793930462-001122334"}],
    "late": [{"label": "Hedera INTENT #7", "value": "tx 0.0.9185802@1793930440",
              "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1793930440-112233445"},
             {"label": "Paid 0.10 USDC", "value": "tx 0.0.9185802@1793930445",
              "url": "https://hashscan.io/testnet/transaction/0.0.9185802-1793930445-643007633"},
             {"label": "Hedera RECEIPT", "value": "waiting for the mirror", "url": None}],
    "list": [{"label": "Hedera LISTING #41", "value": "topic 0.0.11332437 · tx 0.0.6421420@1793929992",
              "url": "https://hashscan.io/testnet/transaction/0.0.6421420-1793929992-000000001"},
             {"label": "Arkiv listing", "value": "0x23bf…af44",
              "url": "https://rabdi.explorer.arkiv.network/entity/0x" + "23bf" * 15 + "af44"},
             {"label": "Arkiv tx", "value": "0x5c1d…9e02", "url": ARKIV_TX_URL}]}


def _live_board(humans=True):
    from arca_launcher.handler.board import build_real
    from arca_launcher.handler.sponsors import RunRow
    laps = {"A1": 6170, "A2": 6236, "A3": 6169, "A4": 6240, "A5": 6244, "A6": 6325}
    rows = [RunRow(key="0x%064x" % i, game="MDGP", title="MARINE DRIVE GP", frames=frames, runner="r%015d" % i,
                   book=None, label="BOT-" + name, human=False, credential=None, log_h="%064x" % i, rules=4,
                   expires_block=1, listing="0x%064x" % (100 + i), price="0.1", pay_to=HOUSE)
            for i, (name, frames) in enumerate(laps.items())]
    rows.append(RunRow(key="0x" + "08e7" * 16, game="MDGP", title="MARINE DRIVE GP", frames=6414, runner="6ps0" * 4,
                       book="ANY-6PS", label=None, human=True, credential="Orb", log_h="ab" * 32, rules=4,
                       expires_block=1, listing="0x" + "23bf" * 16, price="0.1", pay_to="0.0.9473064",
                       splits=(2140, 2165, 2109)))
    return build_real(sorted(rows, key=lambda r: r.frames), 6414, "ANY-6PS", "Orb" if humans else None,
                      need_pay_to=True)


def live_flow(tmp_path, name, **ctx):
    """A flow with every sponsor real (no MOCK pill), the owner's console: ANY-6PS on MARINE DRIVE GP, the scout's pick
    BOT-A2 (paid to the house), the chain ids of a real purchase and listing."""
    board = _live_board()
    base = dict(CTX, game="MARINE DRIVE GP", target="BOT-A2", target_time="1:43.93", target_frames=6236,
                target_pay_to=HOUSE, gap="3.0 s", rank="7th", new_rank="2nd", board_rows=board.rows, best_frames=6414,
                run_time="1:46.90", wallet="0.0.9473064", ghost_look="the *cyan kart*", other_book="ANY-6PS",
                console_tag="C-7QZP", console_line="linked to ANY-6PS", scout_reason=REASON,
                scout_by="Picked by openai/gpt-oss-120b on Groq", you_laps=(2140, 2165, 2109),
                it_laps=(2248, 1994, 1994), scout_lap=2, you_time="1:46.90", receipt="0.0.9185802@1793930445.643007633",
                refused_why="this console is not linked to ANY-6PS", record_line="Recorded: Hedera LISTING #41",
                credential="Orb")
    base.update(ctx)
    flow = Flow(RealSponsors(lambda: 0), Ledger(book="ANY-6PS", credential="Orb", world_verified=True),
                str(tmp_path / "handler.json"), "MDGP", dict(base), today=lambda: TODAY)
    if name in ("buy_load", "buy_done", "buy_late"):                  # paid for by now
        flow.ledger.purchases["MDGP:BOT-A2"] = {"price": 10, "receipt": base["receipt"], "at": 0}
    flow.start(name)
    flow._seller = "BOT-A2"
    flow.ctx.update({k: base[k] for k in ("refused_why", "record_line")}, **ctx)   # as the step that led here set them
    flow._sync()
    flow.ms_in_state = 60000
    return flow


_RULE = {"you_laps": None, "it_laps": None, "scout_lap": None, "target": "BOT-A6", "target_time": "1:45.42",
         "scout_by": "Picked by PB's rule: the ghost just ahead (the model did not answer in 6 s)",
         "scout_reason": "BOT-A6 is the listed ghost just ahead of you: 1:45.42 against your 1:46.90."}
LIVE_SCREENS = {"board": {}, "board_humans_only": {"humans_only": True}, "scout": {}, "scout_pick": {},
                "scout_pick_rule": _RULE,
                "target": {"scout_down": "My scout is not answering, so here is the ghost just ahead. "},
                "buy_check": {}, "buy_pay": {}, "buy_load": {}, "buy_done": {"chain": LIVE_CHAIN["buy"], "chain_i": 1},
                "buy_late": {"chain": LIVE_CHAIN["late"], "chain_i": 1}, "ls_arkiv": {},
                "ls_done": {"chain": LIVE_CHAIN["list"], "chain_i": 2}, "buy_suspended": {}, "id_done": {},
                "id_scan": {}, "book_view": {}}


def test_the_new_screens_live_and_their_text_fits(screen, tmp_path, monkeypatch):
    """Drawn to tests/out/handler_live_<screen>.png (every sponsor real, live-style stub data), beside the all-mock
    handler_<state>.png every_state_draws writes. Nothing on these cards or in PB's words is cut short."""
    from arca_launcher.render import handler_cards, handler_view, text
    cut, real = [], text.ellipsize

    def ellipsize(s, width, measure):
        out = real(s, width, measure)
        if out != s:
            cut.append(s)
        return out
    for module in (text, handler_cards, handler_view):
        monkeypatch.setattr(module, "ellipsize", ellipsize)
    drawn = _texts(screen, monkeypatch)
    for shot, ctx in LIVE_SCREENS.items():
        state = shot.replace("_humans_only", "").replace("_rule", "")
        flow = live_flow(tmp_path / shot, state, **ctx)
        if state == "scout_pick":
            flow.ms_in_state = 1500                                   # the countdown a third of the way down
        drawn.clear()
        show(screen, flow, frames=2)
        out = snapshot(screen.ren, f"handler_live_{shot}")
        assert out.get_size() == (800, 480) and distinct_colours(out) > 3, shot
        assert "MOCK" not in drawn, shot
        if state == "scout_pick":                                     # and PB's whole line, typed out, fits too
            flow.ms_in_state = 60000
            show(screen, flow, frames=2)
            snapshot(screen.ren, f"handler_live_{shot}_said")
    assert cut == []


def test_the_live_board_counts_its_tiers_and_tags_every_bot(screen, tmp_path, monkeypatch):
    drawn = _texts(screen, monkeypatch)
    show(screen, live_flow(tmp_path, "board"))
    assert "HUMAN 1 · BOT 6" in drawn and "= made by a program" in drawn
    assert drawn.count("BOT") >= 5 + 1                               # the rows on screen, and the legend's tag
    drawn.clear()
    flow = live_flow(tmp_path / "only", "board")
    flow.press("square")
    show(screen, flow)
    assert "Humans only" in drawn and "YOU" in drawn and "ANY-6PS" not in drawn      # YOU is ANY-6PS's row
    assert not any(f"BOT-A{n}" in drawn for n in (1, 3, 4, 5, 6))   # the BOT rows hidden (PB's words name A2)
    assert drawn.count("BOT") == 1                                   # the legend's tag only
    from arca_launcher.render.handler_view import hint_items
    assert ("S", "All runners") in hint_items(flow)
    flow.press("square")
    assert ("S", "Humans only") in hint_items(flow)


def test_the_chain_card_draws_the_chosen_rows_qr_big_enough_to_scan(screen, tmp_path, monkeypatch):
    from arca_launcher.render import handler_art
    from arca_launcher.render.handler_cards import QR_BOX
    from arca_launcher.render.handler_view import hint_items
    assert len(ARKIV_TX_URL) == 106
    modules = handler_art.qr_surface(ARKIV_TX_URL).get_width()       # with its quiet zone
    assert QR_BOX // modules >= 3, (modules, QR_BOX // modules)
    seen, real = [], handler_art.qr

    def spy(g, text, rect, t, beam=True):
        box = real(g, text, rect, t, beam)
        seen.append((text, beam, box.w // handler_art.qr_surface(text).get_width()))
        return box
    monkeypatch.setattr(handler_art, "qr", spy)
    flow = live_flow(tmp_path, "ls_done", chain=LIVE_CHAIN["list"], chain_i=2)
    show(screen, flow)
    assert seen[-1][:2] == (ARKIV_TX_URL, False) and seen[-1][2] >= 3    # no scan beam over a dense code
    flow.press("up")
    show(screen, flow)
    assert seen[-1][:2] == (LIVE_CHAIN["list"][1]["url"], False)
    assert ("U/D", "Next") in hint_items(flow)
    drawn = _texts(screen, monkeypatch)
    flow = live_flow(tmp_path / "mock", "buy_done", chain=[])         # none (the mock): exactly the done card
    show(screen, flow)
    assert "Budget left" in drawn and ("U/D", "Next") not in hint_items(flow)
    drawn.clear()
    flow = live_flow(tmp_path / "nolink", "buy_late", chain=LIVE_CHAIN["late"], chain_i=2)
    seen.clear()
    show(screen, flow)
    assert seen == [] and "waiting for the mirror" in drawn           # a row with no link: its text, no QR


def test_the_chain_cards_qr_is_a_tap_that_opens_its_link(screen, tmp_path):
    from arca_launcher.render.handler_cards import qr_box
    from arca_launcher.render.handler_view import CARD, STRIP_H
    content = CARD.copy()
    content.h -= STRIP_H                                             # ls_done has a step strip
    nav, views = show(screen, live_flow(tmp_path, "ls_done", chain=LIVE_CHAIN["list"], chain_i=2))
    (qr,) = [h for h in views.hits if h.target == ("handler", "triangle")]
    assert qr_box(content).contains(qr.shape) and qr.rect.contains(qr.shape)
    assert views.hit(*qr.shape.center) == ("handler", "triangle")    # over the card's own Cross
    assert views.hit(CARD.right - 30, CARD.centery) == ("handler", "cross")
    for name, chain, i in (("buy_late", LIVE_CHAIN["late"], 2), ("buy_done", [], 0)):   # no link, no QR: no tap
        nav, views = show(screen, live_flow(tmp_path / name, name, chain=chain, chain_i=i))
        assert not [h for h in views.hits if h.target == ("handler", "triangle")], name


def test_the_hints_say_triangle_opens_a_link_and_keep_clear_of_the_notice(screen, tmp_path, monkeypatch):
    from arca_launcher.render import chrome, theme
    from arca_launcher.render.handler_view import hint_items
    lefts, real = [], chrome.hints
    monkeypatch.setattr(chrome, "hints", lambda gfx, items, **kw: (lefts.append(real(gfx, items, **kw)), lefts[-1])[1])
    flow = live_flow(tmp_path, "ls_done", chain=LIVE_CHAIN["list"], chain_i=2)
    assert hint_items(flow) == [("X", "OK"), ("O", "Back"), ("U/D", "Next"), ("Y", "Open link")]
    nav, views = show(screen, flow)
    assert lefts[-1] >= theme.MARGIN + chrome.TOAST_MAX_W            # never under a notice ("Opened in a window")
    flow = live_flow(tmp_path / "late", "buy_late", chain=LIVE_CHAIN["late"], chain_i=2)
    assert ("Y", "Open link") not in hint_items(flow)                # the chosen row has no link
    flow.press("up")
    assert ("Y", "Open link") in hint_items(flow)
    one = [dict(LIVE_CHAIN["buy"][1])]
    assert hint_items(live_flow(tmp_path / "one", "buy_done", chain=one)) == [("X", "OK"), ("O", "Back"),
                                                                               ("Y", "Open link")]
    assert ("Y", "Open link") not in hint_items(live_flow(tmp_path / "board", "board", chain=one))


def test_my_record_book_names_this_console(screen, tmp_path, monkeypatch):
    drawn = _texts(screen, monkeypatch)
    show(screen, live_flow(tmp_path, "book_view"))
    assert "C-7QZP" in drawn and any("linked to ANY-6PS" in s for s in drawn)
    drawn.clear()
    flow = live_flow(tmp_path / "released", "book_view", console_line="released")
    flow.ledger.book = None
    flow.refresh()
    show(screen, flow)
    snapshot(screen.ren, "handler_live_book_view_released")
    assert "No record book on this console" in drawn
    assert flow.line == "This console has no record book now. Its runs stay on the board."

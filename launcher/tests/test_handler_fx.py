"""PB the handler's motion: the prototype's CSS curves as pure functions of the ms since a state began
(render/handler_fx.py), then the drawing they move (render/handler_view.py, handler_cards.py, handler_art.py) on
the headless renderer. Timed snapshots land in tests/out/handler_fx_<state>_<ms>.png."""
import ast
import inspect
import os
import re
import time

import pygame
import pytest

from arca_launcher.handler import BANNED_WORDS
from arca_launcher.handler.flow import Flow
from arca_launcher.handler.ledger import Ledger
from arca_launcher.handler.mock import MockSponsors
from arca_launcher.model import Nav, Screen
from conftest import OUT_DIR, snapshot
from test_handler_view import CTX, STATUS, TODAY, has_colour, make_flow, show

RENDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "arca_launcher", "render")
CARD_TAP, BOX_TAP, BACK = ("handler", "cross"), ("handler", "cross", "box"), ("back",)


@pytest.fixture
def fx():
    from arca_launcher.render import handler_fx
    return handler_fx


# ---- the curves --------------------------------------------------------------------------------------------------

def test_curves_start_and_settle(fx):
    assert fx.slide_in(0) == (40, 0) and fx.slide_in(400) == (0, 255)
    assert fx.shake(0) == 0 and fx.shake(1000) == 0
    assert fx.draw_progress(0) == 0 and fx.draw_progress(800) == 1
    assert fx.pop(0) == pytest.approx(0.2) and fx.pop(400) == 1
    assert fx.hop(0) == 0 and fx.hop(450) == 0
    assert fx.toast_in(0) == 420 and fx.toast_in(600) == 0
    assert fx.flip(1200) == 0 and fx.flip(1800) == 1
    assert fx.glow(999) == 0
    assert fx.stagger(0, 0) == 0 and fx.stagger(300, 0) == 255
    assert fx.plus_label(999)[1] == 0 and fx.plus_label(1900)[1] == 0


def test_curves_keep_the_prototypes_numbers(fx):
    approx = pytest.approx
    dx, alpha = fx.slide_in(50)
    assert 0 < dx < 40 and 0 < alpha < 255                                    # on its way in
    assert fx.shake(450) == approx(-8) and fx.shake(550) == approx(8)         # 20% and 40% through the shake
    assert min(fx.hop(t) for t in range(450)) <= -18
    assert fx.bob(1100) == approx(-6) and fx.bob(2200) == approx(0)
    assert fx.pulse(0) == approx(1) and fx.pulse(400) == approx(1.7)
    assert fx.blink(0) and not fx.blink(600)
    assert fx.hourglass(600) == 0 and fx.hourglass(1000) == 180              # turns over between 40% and 60%
    assert fx.beam(0) == 0 and fx.beam(1600) == approx(1) and fx.beam(3200) == approx(0)
    assert fx.stripes(0) == 0 and fx.stripes(300) == approx(17)
    assert fx.buzz(600) == 0 and fx.buzz(780) == approx(-12) and fx.buzz(840) == approx(12)
    assert fx.stagger(120, 1) == 0 and fx.stagger(420, 1) == 255              # each row 120 ms after the last
    assert fx.glow(1700) == approx(1) and fx.step_pulse(600) == approx(1)
    assert fx.plus_label(1270)[1] == 255


def test_a_done_steps_tick_pops_without_the_icons_overshoot(fx):
    assert fx.tick_pop(0) == pytest.approx(0.2) and fx.tick_pop(400) == 1
    assert max(fx.tick_pop(t) for t in range(400)) <= 1                       # .steps .did b: pop with plain ease
    assert max(fx.pop(t) for t in range(400)) > 1                             # .pop: its own overshooting curve


def test_load_bar_reaches_90_percent_in_the_steps_usual_time_then_creeps_to_its_deadline(fx):
    from arca_launcher.handler.mock import _DELAY_MS
    assert set(fx.EXPECTED_MS) == {"idkit_verify", "check_listing", "pay", "load_ghost", "record", "publish", "scout"}
    assert all(fx.EXPECTED_MS[step] == _DELAY_MS[step] - 100 for step in fx.EXPECTED_MS if step != "scout")
    assert fx.fill(2500, "scout", 12000) == pytest.approx(0.9)                # the scout: no mock, a live guess
    approx = pytest.approx
    assert fx.fill(0, "pay", 8000) == 0 and fx.fill(950, "pay", 8000) == approx(0.45)
    assert fx.fill(1900, "pay", 8000) == approx(0.9) and fx.fill(4950, "pay", 8000) == approx(0.95)
    assert fx.fill(8000, "pay", 8000) == 1 and fx.fill(9000, "pay", 8000) == 1
    assert fx.fill(1600, "idkit_verify", 10000) == approx(0.9)
    assert fx.fill(1900, "racing", None) == approx(0.9)                       # an unknown step: 1900 ms
    assert fx.fill(60000, None, None) == approx(0.9)                          # no deadline: it waits at 90%


def test_coins_follow_the_arc(fx):
    assert fx.coins(0)[0] == (300, 205)
    assert fx.coins(1100)[0] == (680, 205)
    assert len(fx.coins(0)) == 3
    assert fx.coins(250)[1] == (300, 205) and fx.coins(500)[2] == (300, 205)    # 250 and 500 ms behind the first
    assert fx.coins(1600)[2] == (680, 205)
    x, y = fx.coins(550)[0]                                                     # half way: the top of a low hop
    assert 460 < x < 510 and 190 < y < 205


def test_confetti_is_deterministic_and_falls(fx):
    a = fx.confetti(7, 900)
    assert a == fx.confetti(7, 900) and a != fx.confetti(8, 900)
    assert len(a) == 46
    assert {(w, h) for _, _, w, h, _, _ in a} == {(10, 14)}
    assert {colour for *_, colour in a} == set(fx.CONFETTI_COLOURS)
    assert all(0 <= x < 800 for x, *_ in a)
    start, later, end = fx.confetti(7, 0), fx.confetti(7, 1500), fx.confetti(7, 3300)
    assert all(p[1] == -20 and p[4] == 0 for p in start)                       # above the screen, not turning yet
    assert all(b[1] >= s[1] for s, b in zip(start, later)) and any(b[1] > 100 for b in later)
    assert all(p[1] >= 480 and p[4] == 720 for p in end)                       # 540 px down, two turns: all gone


def test_pb_blinks_briefly_every_3_1_s(fx):
    shut = [t for t in range(10000) if fx.pb_blink(t)]
    assert shut == list(range(3100, 3240)) + list(range(6200, 6340)) + list(range(9300, 9440))


# ---- driving it by touch -----------------------------------------------------------------------------------------

def _tap(nav, views, target):
    """Draw a frame, then tap target where that frame drew it, as a finger would: through Views.hit, so only a
    target drawn (and not covered) in the last frame can be tapped."""
    views.draw(nav, 16, STATUS)
    hit = next((h for h in views.hits if h.target == target), None)
    assert hit is not None, f"{target} not drawn on {nav.handler.state.name}: {[h.target for h in views.hits]}"
    r = hit.rect
    for kx, ky in ((.5, .5), (.25, .25), (.75, .75), (.25, .75), (.75, .25), (.1, .5), (.9, .5)):
        x, y = r.x + round(r.w * kx), r.y + round(r.h * ky)
        if views.hit(x, y) == target:
            return nav.tap(views.hit(x, y))
    pytest.fail(f"{target} is covered on {nav.handler.state.name}")


def _wait(nav, views, flow, clock, name):
    """Frames go by, and the mock sponsors' clock with them, until the flow reaches state name."""
    for _ in range(100):
        if flow.state.name == name:
            return
        views.draw(nav, 16, STATUS)
        clock[0] += 100
        flow.tick(100)
    pytest.fail(f"stuck at {flow.state.name}, waiting for {name}")


def test_every_flow_can_be_finished_and_left_by_taps(screen, tmp_path):
    from arca_launcher.render.views import Views
    clock = [0]
    flow = Flow(MockSponsors(lambda: clock[0]), Ledger(), str(tmp_path / "handler.json"), "MDGP", dict(CTX),
                today=lambda: TODAY)
    nav, views = Nav(screen.games), Views(screen.gfx, screen.art)
    flows = (
        # the record book (none yet, so "My record book" asks for one first), through World App's two phone steps
        ([(("handler", "row", 2), "need_book"), (CARD_TAP, "s_boot"), (CARD_TAP, "id_scan"),
          (CARD_TAP, "id_confirm"), (BOX_TAP, "id_done")], [BACK, BACK]),
        # PB checks, pays for and loads the next target's ghost
        ([(("handler", "row", 0), "board"), (CARD_TAP, "target"), (BOX_TAP, "buy_done")], [BACK, BACK]),
        # list your best run: approve on the phone, record, list, then back to the hub (a sale comes from Home)
        ([(("handler", "row", 1), "ls_offer"), (CARD_TAP, "ls_scan"), (CARD_TAP, "ls_approve"),
          (CARD_TAP, "ls_done"), (CARD_TAP, "hub")], [BACK]),
    )
    for steps, leave in flows:
        nav.open_handler(flow, "hub")
        for target, then in steps:
            _tap(nav, views, target)
            _wait(nav, views, flow, clock, then)
        for target in leave:
            assert nav.screen is Screen.HANDLER
            _tap(nav, views, target)
        assert nav.screen is Screen.HOME, flow.state.name


def test_pressing_pbs_box_lights_the_box_not_the_card(screen, tmp_path, monkeypatch):
    from arca_launcher.render import chrome
    from arca_launcher.render.handler_view import CARD
    from arca_launcher.render.mascot import BOX
    lit, real = [], chrome.pressed
    monkeypatch.setattr(chrome, "pressed", lambda gfx, hit: (lit.append(hit.shape), real(gfx, hit)))
    nav, views = show(screen, make_flow(tmp_path, "id_done"))
    box, card = views.hit(BOX.right - 30, BOX.centery), views.hit(CARD.right - 10, CARD.bottom - 10)
    assert card == CARD_TAP and box[:2] == CARD_TAP and box != card        # both are Cross, told apart
    nav.pressed = box
    views.draw(nav, 16, STATUS)
    assert lit == [BOX.inflate(8, 8)]
    nav.pressed = card
    views.draw(nav, 16, STATUS)
    assert lit[-1] == CARD
    nav.pressed = None
    nav.tap(box)
    assert nav.handler.state.name == "hub"                                 # opened straight on id_done: the hub


def test_under_the_outcome_list_only_its_rows_back_and_mock_take_taps(screen, tmp_path):
    from arca_launcher.render.mascot import BOX
    flow = make_flow(tmp_path, "ls_approve")
    flow.press("square")
    assert flow.outcomes_open
    nav, views = show(screen, flow)
    assert {h.target[:2] for h in views.hits} == {("back",), ("handler", "square"), ("handler", "pick")}
    assert views.hit(BOX.right - 30, BOX.centery) is None


def test_the_drawing_code_uses_no_banned_words():
    words = [re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE) for w in BANNED_WORDS]
    for name in ("handler_cards.py", "handler_art.py", "handler_view.py", "handler_fx.py"):
        with open(os.path.join(RENDER, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for word in words:
                    assert not word.search(node.value), f"{name}: {node.value!r}"


# ---- the motion on screen ----------------------------------------------------------------------------------------

def _spy(monkeypatch, gfx, name):
    """Every call of gfx.<name> from now on, as a dict of its arguments."""
    calls, real = [], getattr(gfx, name)
    sig = inspect.signature(real)

    def spy(*a, **kw):
        args = sig.bind(*a, **kw)
        args.apply_defaults()
        calls.append(dict(args.arguments))
        return real(*a, **kw)
    monkeypatch.setattr(gfx, name, spy)
    return calls


def _show_at(screen, tmp_path, name, t, views=None):
    flow = make_flow(tmp_path, name)
    flow.ms_in_state = t
    return show(screen, flow, views)


def test_the_bar_pulses_a_busy_service_and_blinks_a_down_one(screen, tmp_path, monkeypatch):
    from arca_launcher.render.handler_art import RED, YELLOW
    calls = _spy(monkeypatch, screen.gfx, "round_rect")

    def dot(name, t, colour):
        calls.clear()
        _show_at(screen, tmp_path, name, t)
        found = [c for c in calls if c["color"] == colour and pygame.Rect(c["rect"]).bottom < 50]
        assert len(found) == 1, (name, t, found)
        return pygame.Rect(found[0]["rect"]).w, found[0]["alpha"]

    assert dot("buy_pay", 0, YELLOW)[0] == 9 and dot("buy_pay", 400, YELLOW)[0] >= 15     # up to 1.7 times
    assert dot("id_offline", 0, RED)[1] == 255 and dot("id_offline", 600, RED)[1] < 100  # on, then dim


def test_pb_hops_into_each_state_then_bobs_and_blinks(screen, tmp_path, monkeypatch):
    from arca_launcher.render.views import Views
    views = Views(screen.gfx, screen.art)
    seen, real = [], views.handler.mascot.draw_line
    monkeypatch.setattr(views.handler.mascot, "draw_line", lambda mood, text, ms, bob=0.0, blink=False: (
        seen.append((round(bob), blink)), real(mood, text, ms, bob, blink)))

    def pb(name, t):
        _show_at(screen, tmp_path, name, t, views)
        return seen[-1]
    assert pb("hub", 180)[0] <= -18                              # the hop's top, 40% in
    assert pb("hub", 1550)[0] == -6                              # then the bob, at its top 1.1 s after the hop
    assert pb("hub", 3150)[1] and not pb("hub", 3300)[1]         # a blink, 3.1 s in
    assert not pb("id_done", 3150)[1]                            # star eyes do not blink


def test_mascot_draws_the_bob_and_the_blink(screen):
    from arca_launcher.render.mascot import PORTRAIT, MascotView
    view = MascotView(screen.gfx)

    def portrait(mood, **kw):
        screen.gfx.fill((0, 0, 0))
        view.draw_line(mood, "Hi.", 60000, **kw)
        return pygame.image.tobytes(screen.ren.to_surface().subsurface(PORTRAIT.inflate(40, 40)), "RGB")
    rest = portrait("normal")
    assert portrait("normal", bob=-6) != rest and portrait("normal", blink=True) != rest
    assert portrait("excited", blink=True) == portrait("excited")


def test_qr_countdown_ticks_in_real_seconds_and_its_bar_shrinks(screen, tmp_path, monkeypatch):
    texts = _spy(monkeypatch, screen.gfx, "text")
    images = _spy(monkeypatch, screen.gfx, "image")

    def at(name, t):
        texts.clear()
        images.clear()
        _show_at(screen, tmp_path, name, t)
        clock = "".join(c["s"] for c in texts if c["size"] == 26 and len(c["s"]) == 1 and c["s"] in "0123456789:")
        return clock, [pygame.Rect(c["rect"]).w for c in images if c["src"] is not None and pygame.Rect(c["rect"]).h == 8]
    clock, bar = at("id_scan", 0)
    assert clock == "5:00" and len(bar) == 1
    assert at("id_scan", 1500)[0] == "4:59"
    clock, half = at("id_scan", 150000)
    assert clock == "2:30" and half[0] == pytest.approx(bar[0] / 2, abs=1)
    assert at("ls_scan", 0)[0] == "20:00" and at("ls_scan", 600000)[0] == "10:00"


def test_a_long_qr_countdown_makes_no_new_textures_as_it_ticks(screen, tmp_path, monkeypatch):
    from arca_launcher.render.views import Views
    g = screen.gfx
    flow = make_flow(tmp_path, "id_scan")
    nav, views = Nav(screen.games), Views(g, screen.art)
    nav.handler = flow
    nav.stack.append(Screen.HANDLER)

    def cached():
        return len(g._text) + len(g._shapes) + len(g.__dict__.get("_handler_tex", {}))
    flow.ms_in_state = 0
    views.draw(nav, 16, STATUS)
    before, made = cached(), _spy(monkeypatch, g, "texture")
    for t in range(0, 300001, 500):                              # the whole five minutes, twice a second
        flow.ms_in_state = t
        views.draw(nav, 16, STATUS)
    assert cached() - before <= 30 and len(made) <= 30, (cached() - before, len(made))


def test_effects_draw_only_on_their_states(screen, tmp_path, monkeypatch, fx):
    called = []
    for name in ("confetti", "coins"):
        real = getattr(fx, name)
        monkeypatch.setattr(fx, name, lambda *a, _name=name, _real=real: (called.append(_name), _real(*a))[1])
    for state, want in (("ls_done", ["confetti"]), ("id_done", ["confetti"]), ("buy_pay", ["coins"]),
                        ("board", []), ("buy_load", [])):
        called.clear()
        _show_at(screen, tmp_path, state, 500)
        assert called == want, state


def _frame(screen, tmp_path, name, t):
    _show_at(screen, tmp_path, name, t)
    return snapshot(screen.ren, f"handler_fx_{name}_{t}")


def test_the_coins_and_the_price_keep_off_the_cards_words(screen, tmp_path, monkeypatch, fx):
    """Paying: the coins fly and the price rises in the band between the card's rows and the name tags, so every
    word on the card stays readable all the way through (they used to cross both rows)."""
    from arca_launcher.render.handler_cards import H_Y, ROW_H, ROWS_Y, SIDE
    from arca_launcher.render.handler_view import CARD
    words = pygame.Rect(CARD.x + SIDE, CARD.y + H_Y, CARD.w - SIDE - 20, ROWS_Y + 2 * ROW_H - H_Y)   # heading, 2 rows
    real = fx.coins, fx.plus_label
    for t in (300, 550, 800, 1050, 1270, 1500, 1800):
        drawn = pygame.image.tobytes(_frame(screen, tmp_path, "buy_pay", t).subsurface(words).copy(), "RGB")
        monkeypatch.setattr(fx, "coins", lambda t: [])
        monkeypatch.setattr(fx, "plus_label", lambda t: (0, 0))
        bare = pygame.image.tobytes(_frame(screen, tmp_path, "buy_pay", t).subsurface(words).copy(), "RGB")
        monkeypatch.setattr(fx, "coins", real[0])
        monkeypatch.setattr(fx, "plus_label", real[1])
        assert drawn == bare, t


def test_the_coins_go_under_the_name_tags(screen, tmp_path, monkeypatch, fx):
    """The coins start on YOU and land on the payee: both names stay on top of them, readable."""
    from arca_launcher.render.handler_view import WHO_X, WHO_Y
    monkeypatch.setattr(fx, "plus_label", lambda t: (0, 0))
    real = fx.coins
    payee = make_flow(tmp_path, "buy_pay").fill("{target}")
    for t, x, name in ((0, WHO_X[0], "YOU"), (1800, WHO_X[1], payee)):   # all three coins on YOU, then on the payee
        tag = pygame.Rect(x, WHO_Y, screen.gfx.measure(name, 22, "pixel")[0] + 20, 26).inflate(-8, -8)  # in its corners
        drawn = pygame.image.tobytes(_frame(screen, tmp_path, "buy_pay", t).subsurface(tag).copy(), "RGB")
        monkeypatch.setattr(fx, "coins", lambda t: [])
        bare = pygame.image.tobytes(_frame(screen, tmp_path, "buy_pay", t).subsurface(tag).copy(), "RGB")
        monkeypatch.setattr(fx, "coins", real)
        assert drawn == bare, t


def test_snapshots_differ_over_time(screen, tmp_path, monkeypatch, fx):
    from arca_launcher.render.handler_art import GREEN, YELLOW
    from arca_launcher.render.handler_cards import PICTURE
    from arca_launcher.render.handler_view import CARD
    icon = PICTURE.move(CARD.topleft)
    early, late = _frame(screen, tmp_path, "id_done", 100), _frame(screen, tmp_path, "id_done", 900)
    assert pygame.image.tobytes(early, "RGB") != pygame.image.tobytes(late, "RGB")
    monkeypatch.setattr(fx, "confetti", lambda seed, t: [])                       # no green confetti over the icon
    early, late = _frame(screen, tmp_path, "id_done", 100), _frame(screen, tmp_path, "id_done", 900)
    assert not has_colour(early, icon, GREEN) and has_colour(late, icon, GREEN)    # the tick draws itself in
    early, late = _frame(screen, tmp_path, "buy_pay", 300), _frame(screen, tmp_path, "buy_pay", 1200)
    assert pygame.image.tobytes(early, "RGB") != pygame.image.tobytes(late, "RGB")
    payee = pygame.Rect(660, 185, 40, 40)                                         # where the coins land
    assert not has_colour(early, payee, YELLOW) and has_colour(late, payee, YELLOW)


def test_coins_tags_and_price_stay_off_the_outcome_list(screen, tmp_path, monkeypatch, fx):
    texts = _spy(monkeypatch, screen.gfx, "text")
    flown, real = [], fx.coins
    monkeypatch.setattr(fx, "coins", lambda t: (flown.append(t), real(t))[1])
    flow = make_flow(tmp_path, "buy_pay")
    flow.ms_in_state = 1300
    show(screen, flow)
    assert {"YOU", "RIA", "+0.10 USDC"} <= {c["s"] for c in texts} and flown     # money always says USDC
    texts.clear()
    flown.clear()
    flow.press("square")
    assert flow.outcomes_open
    show(screen, flow)
    assert not {"YOU", "RIA", "+0.10 USDC"} & {c["s"] for c in texts} and not flown


def test_each_load_bar_is_near_90_percent_as_its_mock_call_lands(screen, tmp_path, monkeypatch):
    from arca_launcher.handler.mock import _DELAY_MS
    from arca_launcher.handler.states import STATES
    from arca_launcher.render.handler_cards import SIDE
    from arca_launcher.render.handler_view import CARD
    loads = [st for st in STATES.values() if st.card["t"] == "load" and st.call]
    assert {st.name for st in loads} == {"id_verifying", "buy_check", "buy_pay", "buy_load", "ls_record", "ls_arkiv",
                                         "scout"}
    loads = [st for st in loads if st.call in _DELAY_MS]              # the scout runs only with Hedera real
    from arca_launcher.render.handler_fx import EXPECTED_MS
    assert EXPECTED_MS["scout"] < STATES["scout"].deadline_ms
    images = _spy(monkeypatch, screen.gfx, "image")
    track = pygame.Rect(CARD.x + SIDE, CARD.y + 176, CARD.w - SIDE - 22, 14)
    for st in loads:
        images.clear()
        _show_at(screen, tmp_path, st.name, _DELAY_MS[st.call] - 1)            # just before the mock answers
        fills = [pygame.Rect(c["rect"]) for c in images if c["src"] is not None and pygame.Rect(c["rect"]).h == 14]
        assert len(fills) == 1 and fills[0].topleft == track.topleft, st.name
        assert fills[0].w / track.w == pytest.approx(0.9, abs=0.05), st.name


def test_busiest_screens_frame_time(screen, tmp_path):
    """Not a pass mark (the Pi's check is Task 12): the mean ms a frame takes on this headless renderer, written
    to tests/out/handler_fx_frame_ms.txt. "draw" is the Python side alone (SDL queues the drawing until the frame
    is shown); "shown" adds present(), which here rasterises the whole frame in software."""
    from arca_launcher.render.views import Views
    views, lines = Views(screen.gfx, screen.art), []
    for name in ("ls_done", "buy_pay", "board"):
        flow = make_flow(tmp_path, name)
        nav = Nav(screen.games)
        nav.handler = flow
        nav.stack.append(Screen.HANDLER)
        flow.ms_in_state = 0
        views.draw(nav, 16, STATUS)                       # the textures are made once, outside the timing
        screen.ren.present()
        took = {}
        for kind in ("draw", "shown"):
            start = time.perf_counter()
            for i in range(120):                          # two seconds of the state: the confetti and coins fly
                flow.ms_in_state = i * 16
                views.draw(nav, 16, STATUS)
                if kind == "shown":
                    screen.ren.present()
            took[kind] = (time.perf_counter() - start) * 1000 / 120
            screen.ren.present()
        lines.append(f"{name}: draw {took['draw']:.2f} ms, shown {took['shown']:.2f} ms a frame (mean of 120)")
    with open(os.path.join(OUT_DIR, "handler_fx_frame_ms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))

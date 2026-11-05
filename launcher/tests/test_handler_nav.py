"""Nav wiring for the HANDLER screen: pushing/popping it, routing buttons and taps to the Flow
(handler/flow.py, Task 6), and Triangle opening the hub. The flow itself is a stub here: Nav must
not know anything about sponsors, ledgers or states, only Flow's press()/pick()/start() surface."""
from arca_launcher.actions import Action as A
from arca_launcher.handler.flow import CloseHandler
from arca_launcher.model import Nav, OpenHub, Screen
from test_model import GAMES


class StubFlow:
    """Records every call Nav makes on it. `start_result`, `press_result` and `pick_result` are
    returned by the next call of their kind (a one-shot, like the real Flow's commands)."""
    def __init__(self):
        self.calls = []
        self.start_result = None
        self.press_result = None
        self.pick_result = None
        self.hub_index = 0

    def start(self, entry):
        self.calls.append(("start", entry))
        return self.start_result

    def press(self, event):
        self.calls.append(("press", event))
        return self.press_result

    def pick(self, i):
        self.calls.append(("pick", i))
        return self.pick_result


def opened(entry="hub"):
    """A Nav sitting on Home, with a stub flow already open on HANDLER."""
    nav = Nav(GAMES)
    flow = StubFlow()
    nav.open_handler(flow, entry)
    flow.calls.clear()  # drop the start() call: tests below care about what happens after
    return nav, flow


def test_buttons_go_to_the_flow():
    nav, flow = opened()
    nav.apply(A.A)
    nav.apply(A.B)
    nav.apply(A.X)
    nav.apply(A.UP)
    nav.apply(A.DOWN)
    assert flow.calls == [("press", "cross"), ("press", "circle"), ("press", "square"),
                           ("press", "up"), ("press", "down")]
    # anything else is not a handler button and does nothing
    assert nav.apply(A.LEFT) is None and nav.apply(A.RIGHT) is None and nav.apply(A.Y) is None
    assert flow.calls == [("press", "cross"), ("press", "circle"), ("press", "square"),
                           ("press", "up"), ("press", "down")]


def test_pb_talking_does_not_swallow_handler_buttons():
    nav, flow = opened()
    nav.mascot = object()  # PB is "talking"; this must not matter on HANDLER
    assert nav.apply(A.A) is None
    assert flow.calls == [("press", "cross")]
    assert nav.mascot is not None  # not advanced: the swallow rule did not fire


def test_triangle_opens_the_hub_for_the_focused_game():
    nav = Nav(GAMES)
    assert nav.apply(A.Y) == OpenHub(nav.selected)

    nav.stack.append(Screen.LIBRARY)
    nav.grid_index = 1
    assert nav.apply(A.Y) == OpenHub(nav.grid_game)

    nav.stack = [Screen.HOME]
    nav.apply(A.START)
    assert nav.screen is Screen.INFO
    assert nav.apply(A.Y) == OpenHub(nav.info_game)


def test_triangle_on_the_library_tile_opens_the_hub_with_no_game():
    nav = Nav(GAMES)
    nav.row_index = len(nav.row) - 1
    assert nav.selected is None
    assert nav.apply(A.Y) == OpenHub(None)


def test_close_handler_returns_to_where_you_were():
    nav, flow = opened()
    flow.press_result = CloseHandler()
    assert nav.apply(A.B) is None
    assert nav.screen is Screen.HOME
    assert nav.handler is flow  # the app may still resume it


def test_taps_map_to_presses():
    nav, flow = opened()
    nav.tap(("handler", "cross"))
    nav.tap(("handler", "circle"))
    nav.tap(("handler", "square"))
    assert flow.calls == [("press", "cross"), ("press", "circle"), ("press", "square")]

    nav.tap(("handler", "pick", 2))
    assert flow.calls[-1] == ("pick", 2)

    nav.tap(("handler", "row", 3))
    assert flow.hub_index == 3
    assert flow.calls[-1] == ("pick", 3)

    before = list(flow.calls)
    assert nav.tap(None) is None
    assert flow.calls == before  # empty space does nothing


def test_sleep_and_attract_still_wake_first():
    nav, flow = opened()
    nav.stack.append(Screen.SLEEP)
    nav.apply(A.A)
    assert nav.screen is Screen.HANDLER
    assert flow.calls == []  # the wake, not the handler, consumed the button

    nav.stack.append(Screen.ATTRACT)
    nav.apply(A.B)
    assert nav.screen is Screen.HANDLER
    assert flow.calls == []


def test_resume_handler_brings_back_the_same_flow_without_restarting_it():
    nav, flow = opened()
    nav.close_handler()
    assert nav.screen is Screen.HOME
    nav.resume_handler()
    assert nav.screen is Screen.HANDLER
    assert nav.handler is flow
    assert [c for c in flow.calls if c[0] == "start"] == []  # start() was not called again


def test_resume_handler_without_a_flow_does_nothing():
    nav = Nav(GAMES)
    assert nav.resume_handler() is None
    assert nav.stack == [Screen.HOME]


# --- a way into PB's hub by touch: a "PB" button beside Play for arcade games ----------------------------------------
from dataclasses import replace  # noqa: E402

ARCADE = replace(GAMES[0], id="marine-drive-gp", title="MARINE DRIVE GP", arcade={"id": "MDGP", "replay": "/x"})


def test_an_arcade_game_gets_a_pb_button_when_the_handler_is_on():
    nav = Nav([ARCADE] + GAMES[1:])
    nav.row_index = nav.row.index(ARCADE)
    assert nav.home_buttons() == ["Play", "..."]                  # handler off: as before
    nav.handler_enabled = True
    assert nav.home_buttons() == ["Play", "PB", "..."]
    other = next(i for i, g in enumerate(nav.row) if g is not None and g.arcade is None)
    nav.row_index = other
    assert "PB" not in nav.home_buttons()                         # only arcade games have a board to race


def test_a_tap_on_a_button_the_selected_game_does_not_have_does_nothing():
    """A finger down on an arcade game's third button ("..."), the D-pad moves to a two-button game, the finger lifts:
    the tap lands on a button that is gone."""
    nav = Nav([ARCADE] + GAMES[1:])
    nav.handler_enabled = True
    nav.row_index = next(i for i, g in enumerate(nav.row) if g is not None and g.arcade is None)
    assert len(nav.home_buttons()) == 2
    assert nav.tap(("button", 2)) is None and nav.screen is Screen.HOME


def test_the_pb_button_opens_the_hub_by_button_and_by_tap():
    nav = Nav([ARCADE] + GAMES[1:])
    nav.handler_enabled = True
    nav.row_index = nav.row.index(ARCADE)
    nav.apply(A.DOWN)                                             # to the buttons
    nav.apply(A.RIGHT)                                            # Play -> PB
    assert nav.apply(A.A) == OpenHub(ARCADE)
    assert nav.tap(("button", 1)) == OpenHub(ARCADE)              # the touch way in: no controller needed
    assert nav.tap(("button", 2)) is None and nav.screen is Screen.INFO  # "..." still opens the info page

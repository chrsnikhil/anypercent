"""PB's optional voice: Claude rewords a line, and anything that changes the facts is thrown away."""
from types import SimpleNamespace

import pytest

from arca_launcher.coach import Line
from arca_launcher.coach_voice import MODEL, Voice, valid

LINE = Line("excited", "1:21.53! New personal best, 1.57 s faster. I replayed your log and it matches.", "new_best")


class FakeClient:
    """Stands in for anthropic.Anthropic: answers with `reply` (or raises it) and keeps the request."""
    def __init__(self, reply, stop_reason="end_turn"):
        self.reply, self.stop_reason, self.requests = reply, stop_reason, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.requests.append(kw)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.reply)])


def test_a_rewording_that_keeps_every_number_is_used():
    v = Voice(FakeClient("Whoa, 1:21.53! A new personal best by 1.57 s, and your log replays perfectly."))
    assert v.rephrase(LINE).startswith("Whoa, 1:21.53!")


def test_the_request_is_short_and_says_what_must_not_change():
    c = FakeClient("Whoa, 1:21.53! New best by 1.57 s. The replay matches.")
    Voice(c).rephrase(LINE)
    [req] = c.requests
    assert req["model"] == MODEL == "claude-haiku-4-5" and req["max_tokens"] <= 200
    assert "number" in req["system"].lower() and LINE.text in req["messages"][0]["content"]


@pytest.mark.parametrize("said", [
    "Whoa, 1:21.54! New best by 1.57 s.",                         # a number changed
    "Whoa, a new personal best by 1.57 s!",                       # a number dropped
    "1:21.53! New best by 1.57 s, top 3 on the board!",           # a number added
    "1:21.53! New best by 1.57 s! \U0001F525",                    # an emoji
    "1:21.53! New best by 1.57 s. Proof a human played it!",      # a claim PB must never make
    "1:21.53! New best by 1.57 s.\nNext line.",                   # more than one line
    "1:21.53 and 1.57 s " + "so " * 80,                           # far too long
    "",
])
def test_a_rewording_that_changes_the_facts_is_thrown_away(said):
    assert Voice(FakeClient(said)).rephrase(LINE) is None


def test_quotes_around_the_answer_are_dropped():
    assert Voice(FakeClient('"Whoa, 1:21.53! New best by 1.57 s."')).rephrase(LINE) == "Whoa, 1:21.53! New best by 1.57 s."


def test_a_refusal_or_a_failure_means_pb_uses_its_own_words():
    assert Voice(FakeClient("1:21.53 and 1.57 s", stop_reason="refusal")).rephrase(LINE) is None
    assert Voice(FakeClient(RuntimeError("network down"))).rephrase(LINE) is None


def test_submit_answers_in_the_background():
    v = Voice(FakeClient("Whoa, 1:21.53! New best by 1.57 s."))
    assert v.submit(LINE).result(timeout=5) == "Whoa, 1:21.53! New best by 1.57 s."


def test_a_key_file_with_no_key_is_refused(tmp_path):
    f = tmp_path / "coach-voice.key"
    f.write_text("  \n")
    with pytest.raises(ValueError):
        Voice.from_key_file(str(f))


def test_valid_compares_numbers_not_wording():
    assert valid("Nice! 0:41 to 0:52, 1.80 s.", "Lost 1.80 s between 0:41 and 0:52.")
    assert not valid("Nice! 0:41 to 0:53, 1.80 s.", "Lost 1.80 s between 0:41 and 0:52.")

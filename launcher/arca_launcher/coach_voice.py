"""PB's optional voice: Claude rewords a coach line in PB's manner, in the background.

Off unless a key file exists (the launcher's --coach-voice-key, default coach-voice.key beside its state file) and the
`anthropic` package is installed in the launcher's venv (pip install anthropic). Only the line itself and PB's mood are
sent. A rewording is used only when it keeps exactly the line's numbers and says nothing PB must never claim; anything
else (a changed number, an emoji, a refusal, a slow or failed request) leaves PB's own words on screen."""
import concurrent.futures as cf
import logging
import re

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 120             # one or two short sentences
TIMEOUT = 4.0                # seconds; the launcher waits less than this anyway (theme.VOICE_WAIT_MS)
MAX_CHARS = 180
NUMBER = re.compile(r"\d+(?:[.:]\d+)*")
NEVER = ("human", "proof", "prove", "cheat", "guarantee")
SYSTEM = (
    "You are PB, the coach on Any%, a handheld console for speedrunning: a small, friendly ghost of the player's "
    "personal best. Reword the line you are given in PB's voice: warm, upbeat and brief, like a partner in a "
    "dungeon-crawler game. Keep every number and time exactly as written and keep the facts the same; add no new "
    "facts, numbers or advice. Never say anything about who played or whether a person played. One or two "
    "sentences, at most 25 words, no emoji. Reply with the reworded line only."
)


def valid(said, original):
    """A rewording PB may say: one short line, exactly the original's numbers, no emoji, no claim PB must not make."""
    if not said or "\n" in said or len(said) > MAX_CHARS:
        return False
    if set(NUMBER.findall(said)) != set(NUMBER.findall(original)):
        return False
    if any(ord(c) >= 0x2600 for c in said):              # emoji and pictographs
        return False
    low = said.lower()
    return not any(w in low for w in NEVER)


class Voice:
    def __init__(self, client, model=MODEL):
        self.client, self.model = client, model
        self._pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="pb-voice")

    @classmethod
    def from_key_file(cls, path):
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
        if not key:
            raise ValueError(f"{path} holds no key")
        import anthropic                                   # only when the voice is on: the launcher runs without it
        return cls(anthropic.Anthropic(api_key=key, timeout=TIMEOUT, max_retries=0))

    def submit(self, line):
        """A future of the rewording (or None): the launcher shows PB's own words if it is late or None."""
        return self._pool.submit(self.rephrase, line)

    def rephrase(self, line):
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                messages=[{"role": "user", "content": f"Mood: {line.mood}\nLine: {line.text}"}],
            )
        except Exception as e:                             # every failure has one answer: PB's own words
            log.warning("PB's voice failed (%s): %s", type(e).__name__, e)
            return None
        if response.stop_reason == "refusal":
            return None
        said = "".join(b.text for b in response.content if b.type == "text").strip().strip('"').strip()
        return said if valid(said, line.text) else None

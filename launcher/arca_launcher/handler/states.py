"""The handler's state table: one `State` per screen PB can show, transcribed from the
mockups' prototype (`docs/superpowers/specs/2026-10-24-pb-handler-mockups/handler-states.html`,
the JS object `S`) with controller-ruled amendments layered on top:

- sponsor names, codes and run data are placeholders (`{world}`, `{price}`, ...), never the
  prototype's literal demo values -- `sponsors.SponsorNames.fill()` fills the sponsor-name ones,
  the flow engine (Task 6) fills the rest from its context dict;
- the prototype's `scan`/`approve` events and its `auto` delayed transitions become a `call`
  name plus `on["ok"]` / `on["timeout"]`, resolved against `sponsors.STEPS`/`TIMEOUT_MS`;
- a handful of denial events (`deny`, `expire`, `nocred`, ...) carry no `on` entry at all: they
  are reached by a sponsor's forced outcome, whose `failure` name already names the next state;
- eighteen states (`hub`, `need_book`, `board_new`, `buy_check_fail`, ...) are new, not in the
  prototype: the hub screen, the post-race outcomes the prototype's `racing` auto-advance never
  had to pick between (three after a bought ghost, `own_result`/`own_again` after racing your own
  best), a fresh-visitor board, the three down-sponsor timeouts Ruling 8 split out of
  `buy_down`/`ls_record_fail` so a failure's name always matches which step timed out, and
  `buy_late`, so a payment that landed late never leaves "nothing was paid" on screen;
- two more came with real World: `id_dup_unnamed`, the flow's `id_dup` when World App refused a
  second sign-up before the bridge could name the book (nothing to sign in to), and `ls_confirm`,
  the flow's `ls_approve` when the listing OK runs on World ID (IDKit), whose phone shows no code
  to check: tap Confirm, as for the record book.

This module is pure data (plus `copy_texts`/`PLACEHOLDERS`, small helpers over that data): no
pygame, no sponsor calls, no clock. Task 6 (`flow.py`) walks `on`; Task 9 draws `card` by its
`t`. Two banned words and a few literal sponsor names in the prototype's own copy ("sent a
proof", "Circle ... wins", "World ID") are reworded here to satisfy the Global Constraints that
bind every task in this plan, not just the prototype it was sketched from. A fix round (Ruling 6)
also replaced a handful of the prototype's own illustrative literals ("Marine Drive", "1.6
seconds ahead", a HashScan-shaped receipt) with placeholders or mock-safe copy, since those are
real per-run values or false money claims, not flavour text.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class State:
    name: str
    mood: str                              # one of coach.MOODS
    say: str                               # PB's line; placeholders, *word* marks emphasis
    card: dict                             # {"t": type, ...}; Task 9 draws by "t"
    on: dict[str, str]                     # event ("cross" | "circle" | "ok" | "timeout") -> state
    steps: tuple[str, ...] = ()            # the step strip, e.g. ID3/BUY/LS below
    at: int = 0                            # index into steps this state sits at
    halt: bool = False                     # the step strip shows this step as halted, not failed
    fail: bool = False                     # the step strip shows this step as failed
    kind: str = ""                         # "" | "ok" | "no" | "warn": the card's colour
    fx: str = ""                           # "" | "confetti" | "coin"
    call: str | None = None                # a sponsors.STEPS name begun on entry
    busy: str | None = None                # "world" | "board" | "third": the pill that pulses
    phone: bool = False                    # Cross resolves the call: a phone step
    deadline_ms: int | None = None         # ms with no result before on["timeout"] fires
    down: str | None = None                # "world" | "board" | "third": the pill shown off
    keep_call: bool = False                # a backed-out call is kept alive for a late result
    mock_outcomes: tuple[tuple[str, str], ...] = ()  # extra Square rows (label, state), mock only


# The prototype's step strips (handler-states.html, `var ID3 = ...`).
_ID3 = ("Scan", "Confirm", "Ready")
_BUY = ("Check", "Pay", "Load", "Race")
_LS = ("Scan", "Approve", "Record", "Listed")


STATES: dict[str, State] = {

    # ---- 1. record book: World IDKit -----------------------------------------------------
    "s_boot": State(
        name="s_boot", mood="happy", card={"t": "status"},
        say="Hi! Handler online. *{world}*, *{board}* and *{third}* are all answering. "
            "Want a record book so your runs go on the board?",
        on={"cross": "id_scan", "circle": "home"},
    ),
    "id_scan": State(
        name="id_scan", mood="serious",
        card={"t": "qr", "h": "Get your record book",
              "rows": ("World App > IDKit", "*One person, one record book*", "No name or face is kept")},
        say="Scan this with *World App*. It checks you are one person, so nobody runs two "
            "record books. I never see your name.",
        steps=_ID3, at=0, call="idkit_scan", phone=True, deadline_ms=300000,
        on={"ok": "id_confirm", "timeout": "id_expired", "circle": "id_cancel"},
    ),
    "id_confirm": State(
        name="id_confirm", mood="thinking",
        card={"t": "wait", "h": "Waiting for your phone",
              "rows": ("Open World App", "Tap *Confirm*", "Code *{code}*")},
        say="Got the scan. Now tap *Confirm* on your phone. No rush, it stays open for five minutes.",
        steps=_ID3, at=1, call="idkit_confirm", phone=True, deadline_ms=300000,
        on={"ok": "id_verifying", "timeout": "id_expired", "circle": "id_cancel"},
    ),
    "id_verifying": State(
        name="id_verifying", mood="thinking", busy="world",
        card={"t": "load", "h": "Checking with {world}",
              "rows": ("Your phone sent its answer", "Our server asks {world}: *valid?*")},
        say="Confirmed on your phone. Checking it with *{world}* now, one second.",
        steps=_ID3, at=1, call="idkit_verify", deadline_ms=10000,
        on={"ok": "id_done", "timeout": "id_offline"},
    ),
    "id_done": State(
        name="id_done", mood="excited", kind="ok", fx="confetti",
        card={"t": "done", "h": "Record book ready", "rows": ("*{book}* is yours",),
              "what": (("Verified", "by {world} ({credential})"), ("Stored", "a one-per-person code"),
                        ("Not stored", "your name or face"))},
        say="You are in! Record book *{book}* is yours. Every run you finish lands in it. "
            "Cross to carry on.",
        steps=_ID3, at=3, on={"cross": "hub", "circle": "hub"},  # Cross: the flow's remembered target
    ),
    "id_rejected": State(
        name="id_rejected", mood="normal", kind="no",
        card={"t": "no", "h": "You said no", "rows": ("You tapped *Reject* in World App",),
              "what": (("{world} ID", "not shared"), ("Record book", "not made"),
                        ("Games", "still play, off the board"))},
        say="No problem, you said no on your phone. Nothing was saved. Your runs just stay off "
            "the board. Cross for a new code.",
        steps=_ID3, at=1, halt=True, on={"cross": "id_scan", "circle": "home"},
    ),
    "id_expired": State(
        name="id_expired", mood="normal", kind="no",
        card={"t": "time", "h": "Code ran out", "rows": ("Five minutes passed with no answer",),
              "what": (("Shared", "nothing"), ("Code {code}", "dead for good"), ("Next", "a fresh code"))},
        say="The code ran out before your phone answered, so nothing happened. Cross for a fresh one.",
        steps=_ID3, at=1, halt=True, on={"cross": "id_scan", "circle": "home"},
    ),
    "id_dup": State(
        name="id_dup", mood="worried", kind="no",
        card={"t": "no", "h": "Already registered", "rows": ("This {world} ID owns *{other_book}*",),
              "what": (("Second book", "refused"), ("{other_book}", "untouched, runs kept"),
                        ("Rule", "one per person"))},
        say="That {world} ID already has record book *{other_book}*. One per person, so I can "
            "not make a second. Cross to sign in to it instead.",
        steps=_ID3, at=2, fail=True, on={"cross": "id_signed", "circle": "home"},
    ),
    "id_dup_unnamed": State(
        name="id_dup_unnamed", mood="worried", kind="no",
        card={"t": "no", "h": "Already registered", "rows": ("This {world} ID already has a record book",),
              "what": (("Second book", "refused"), ("Your book", "untouched, runs kept"),
                        ("Rule", "one per person"))},
        say="That {world} ID already has a record book. One per person, so World App said no to a "
            "second. The games still play.",
        steps=_ID3, at=2, fail=True, on={"cross": "home", "circle": "home"},
    ),
    "id_signed": State(
        name="id_signed", mood="happy", kind="ok", fx="confetti",
        card={"t": "done", "h": "Welcome back", "rows": ("Signed in to *{other_book}*",),
              "what": (("Runs", "{runs} on the board"),)},
        say="Welcome back! Signed in to *{other_book}*. Your {runs} runs are all still there.",
        steps=_ID3, at=3, on={"cross": "hub", "circle": "hub"},  # Cross: as id_done's
    ),
    "id_nocred": State(
        name="id_nocred", mood="thinking", kind="warn",
        card={"t": "warn", "h": "Selfie Check needed", "rows": ("Your World App has no Selfie Check yet",),
              "what": (("Where", "World App, Credentials"), ("How long", "about two minutes"),
                        ("Then", "scan again"))},
        say="Your World App has no *Selfie Check* yet. Add it in World App, about two minutes, "
            "then scan again. I will wait.",
        steps=_ID3, at=1, halt=True, on={"cross": "id_scan", "circle": "home"},
    ),
    "id_cancel": State(
        name="id_cancel", mood="normal", kind="no",
        card={"t": "back", "h": "Backed out", "rows": ("You pressed Circle on the console",),
              "what": (("Sent", "nothing"), ("Late phone tap", "ignored"))},
        say="Backed out. Nothing was sent, and if your phone says Confirm later I will ignore it.",
        steps=_ID3, at=0, halt=True, on={"cross": "id_scan", "circle": "home"},
    ),
    "id_offline": State(
        name="id_offline", mood="worried", kind="no", down="world",
        card={"t": "no", "h": "{world} is not answering", "rows": ("No reply for 10 seconds",),
              "what": (("Shared", "nothing"), ("Games", "still play"), ("Next", "try again in a minute"))},
        say="{world} is not answering, so I can not make your record book right now. The games "
            "still play. Cross to try again.",
        steps=_ID3, at=1, fail=True, on={"cross": "id_scan", "circle": "home"},
    ),

    # ---- 2. board, next target, PB buys the ghost: x402 on Hedera ------------------------
    "board": State(
        name="board", mood="happy", card={"t": "board"},
        say="Here is the *{game}* board. You are {rank}. *{target}* is {gap} ahead. "
            "Beat her and {new_rank} is yours.",
        on={"cross": "target", "circle": "hub"},
    ),
    "board_new": State(
        name="board_new", mood="happy", card={"t": "board"},
        say="Here is the *{game}* board. No time from you yet. *{target}* is the one to beat: "
            "{target_time}.",
        on={"cross": "target", "circle": "hub"},
    ),
    "target": State(
        name="target", mood="serious", card={"t": "target", "rows": ("Faster from {split}",)},
        say="Next run to beat: *{target}, {target_time}*. Her ghost is {price} USDC. "
            "Cross and I buy it.",
        on={"cross": "buy_check", "circle": "board"},
    ),
    "buy_check": State(
        name="buy_check", mood="thinking", busy="board",
        card={"t": "load", "h": "Checking {target}'s listing",
              "rows": ("Price *{price} USDC*", "Pays *{target}*'s record book")},
        say="Checking her listing on *{board}*: price, who gets paid, and that her run is verified.",
        steps=_BUY, at=0, call="check_listing", deadline_ms=8000,
        on={"ok": "buy_pay", "timeout": "buy_check_fail"},
    ),
    "buy_pay": State(
        name="buy_pay", mood="thinking", busy="third", fx="coin",
        card={"t": "load", "h": "Paying {target}",
              "rows": ("*{price} USDC* via {pay_rail}", "No approval: under your caps")},
        say="Paying {target} *{price} USDC* on {third}. It goes straight to her, from your "
            "coach budget.",
        steps=_BUY, at=1, call="pay", deadline_ms=8000,
        on={"ok": "buy_load", "timeout": "buy_down"},
    ),
    "buy_load": State(
        name="buy_load", mood="thinking",
        card={"t": "load", "h": "Loading her ghost",
              "rows": ("Downloaded", "Checked against her verified run")},
        say="Paid. Downloading her ghost and checking it matches her verified run.",
        steps=_BUY, at=2, call="load_ghost", deadline_ms=8000,
        on={"ok": "buy_done", "timeout": "buy_load_fail"},
    ),
    "buy_done": State(
        name="buy_done", mood="excited", kind="ok",
        card={"t": "done", "h": "Ghost loaded", "rows": ("{target} {target_time}, {ghost_look}",),
              "what": (("Paid", "{price} USDC to {target}"), ("Receipt", "mock receipt"),
                        ("Budget left", "{budget_left} today"))},
        say="Got it. {target}'s ghost is {ghost_look}. Beat it and {new_rank} is yours. "
            "Cross to race, then *OPTIONS* on the title screen!",
        steps=_BUY, at=4, on={"cross": "racing", "circle": "hub"},
    ),
    "racing": State(
        name="racing", mood="excited", card={"t": "load", "h": "Racing {target}"}, say="...",
        on={"circle": "home"},
    ),
    "result": State(
        name="result", mood="excited", kind="ok", fx="confetti", card={"t": "result"},
        say="*{run_time}!* You beat {target} by *{gap}*. You are {new_rank} now. "
            "Cross to list this run so others can race you.",
        on={"cross": "ls_offer", "circle": "home"},
    ),
    "buy_budget": State(
        name="buy_budget", mood="worried", kind="warn",
        card={"t": "warn", "h": "Over your budget", "rows": ("Coach budget: *1.00 of 1.00* spent today",),
              "what": (("Paid", "nothing"), ("Set by", "a guard outside the AI"), ("Resets", "at midnight"))},
        say="That would go past your *1.00 USDC* coach budget for today, so I did not buy it. "
            "Race your own best for now.",
        steps=_BUY, at=1, halt=True, on={"cross": "board", "circle": "home"},
    ),
    "buy_changed": State(
        name="buy_changed", mood="serious", kind="no",
        card={"t": "no", "h": "Listing changed", "rows": ("Price was {price}, now *{now_price}*",),
              "what": (("Paid", "nothing"), ("Rule", "never pay a changed listing"),
                        ("Next", "look again, or skip her"))},
        say="{target}'s price changed from {price} to *{now_price}* since I looked. I never pay a "
            "listing that changed under me. Cross to look again.",
        steps=_BUY, at=1, fail=True, on={"cross": "target", "circle": "board"},
    ),
    "buy_suspended": State(
        name="buy_suspended", mood="serious", kind="no",
        card={"t": "no", "h": "Sales suspended", "rows": ("{target}'s record book has a fraud finding",),
              "what": (("Paid", "nothing"), ("Her runs", "voided"), ("Next", "race your own best"))},
        say="{target}'s sales are suspended after a fraud finding, so I will not pay her. "
            "Nobody else ahead of you sells a ghost right now.",
        steps=_BUY, at=0, fail=True, on={"cross": "board", "circle": "home"},
    ),
    "buy_down": State(
        name="buy_down", mood="worried", kind="no", down="third",
        card={"t": "no", "h": "{third} did not answer", "rows": ("Payment timed out after 8 seconds",),
              "what": (("Paid", "nothing, checked twice"), ("Your game", "not affected"),
                        ("Next", "try again later"))},
        say="{third} is not answering, so *nothing was paid*. Race your own best for now, "
            "or try again later.",
        steps=_BUY, at=1, fail=True, keep_call=True,
        on={"ok": "buy_late", "cross": "board", "circle": "home"},
    ),
    "buy_late": State(
        name="buy_late", mood="happy", kind="ok",
        card={"t": "done", "h": "Payment landed late",
              "what": (("Paid", "{price} USDC to {target}"), ("Receipt", "mock receipt"),
                        ("Next", "load her ghost"))},
        say="{third} was slow, but your payment to {target} did land. Her ghost is yours. "
            "Cross to load it.",
        steps=_BUY, at=1, on={"cross": "buy_load", "circle": "hub"},
    ),
    "buy_check_fail": State(
        name="buy_check_fail", mood="worried", kind="no", down="board",
        card={"t": "no", "h": "{board} did not answer",
              "what": (("Paid", "nothing"), ("Next", "Cross tries again"))},
        say="{board} is not answering, so I could not check {target}'s listing. Nothing was paid.",
        steps=_BUY, at=0, fail=True, on={"cross": "buy_check", "circle": "hub"},
    ),
    "buy_load_fail": State(
        name="buy_load_fail", mood="worried", kind="no", down="third",
        card={"t": "no", "h": "Ghost did not load",
              "what": (("Paid", "{price} USDC to {target}"), ("Ghost", "yours, not loaded"),
                        ("Next", "Cross tries again"))},
        say="Paid, but {target}'s ghost did not arrive. It is yours: Cross to try loading it again.",
        steps=_BUY, at=2, fail=True, on={"cross": "buy_load", "circle": "hub"},
    ),

    # ---- 3. list your ghost: World Agent Pass approval, Hedera record, Arkiv listing -----
    "ls_offer": State(
        name="ls_offer", mood="happy", card={"t": "offer"},
        say="Want others to race this ghost? *{price} USDC* a copy, for a week. Cross and I ask "
            "{world} for your OK.",
        on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_scan": State(
        name="ls_scan", mood="serious",
        card={"t": "qr", "h": "Approve on your phone",
              "rows": ("{approve_via}", "*List ghost: {game} {run_time}*",
                        "{price} USDC to *{wallet}*")},
        say="Scan this with World App. It asks to list your *{run_time}* ghost for *{price} USDC*. "
            "{approve_how}, Circle to back out.",
        steps=_LS, at=0, call="approve_scan", phone=True, deadline_ms=1200000,
        on={"ok": "ls_approve", "timeout": "ls_expired", "circle": "ls_cancel"},
    ),
    "ls_approve": State(
        name="ls_approve", mood="thinking",
        card={"t": "wait", "h": "Waiting for your phone",
              "rows": ("Code on your phone must read", "*{code}*", "Then tap *Approve*")},
        say="Check the code on your phone says *{code}*, then tap Approve. If it says anything "
            "else, press Circle.",
        steps=_LS, at=1, call="approve", phone=True, deadline_ms=1200000,
        on={"ok": "ls_record", "timeout": "ls_expired", "circle": "ls_cancel"},
    ),
    "ls_confirm": State(
        name="ls_confirm", mood="thinking",
        card={"t": "wait", "h": "Waiting for your phone",
              "rows": ("Open World App", "Tap *Confirm*", "*List ghost: {game} {run_time}*")},
        say="Got the scan. Now tap *Confirm* in World App to list your *{run_time}* ghost. "
            "Changed your mind? Press Circle.",
        steps=_LS, at=1, call="approve", phone=True, deadline_ms=300000,
        on={"ok": "ls_record", "timeout": "ls_expired", "circle": "ls_cancel"},
    ),
    "ls_record": State(
        name="ls_record", mood="serious", busy="third",
        card={"t": "load", "h": "Recording on {record_rail}",
              "rows": ("Approval *{jti}* used once", "Listing for {listing_days} days")},
        say="Approved. Writing your listing to *{record_rail}*, a few seconds. You can put the "
            "controller down.",
        steps=_LS, at=2, call="record", deadline_ms=8000,
        on={"ok": "ls_arkiv", "timeout": "ls_record_fail"},
    ),
    "ls_arkiv": State(
        name="ls_arkiv", mood="serious", busy="board",
        card={"t": "load", "h": "Listing on {board}",
              "rows": ("Visible to every console's coach", "Ends in 7 days")},
        say="Recorded. Now putting it on *{board}* so other coaches can find it.",
        steps=_LS, at=3, call="publish", deadline_ms=8000,
        on={"ok": "ls_done", "timeout": "ls_publish_fail"},
    ),
    "ls_done": State(
        name="ls_done", mood="excited", kind="ok", fx="confetti",
        card={"t": "done", "h": "Listed", "rows": ("Your *{run_time}* ghost",),
              "what": (("Price", "{price} USDC a copy"), ("Sales go to", "{wallet}"),
                        ("Ends", "in 7 days"))},
        say="Done! Your ghost is listed for a week. I will tell you when someone buys it.",
        steps=_LS, at=4, on={"cross": "hub", "circle": "hub"},  # a sale only comes from Home (flow 4)
    ),
    "sale": State(
        name="sale", mood="excited", kind="ok", card={"t": "toast"},
        say="*{buyer}* just bought your *{game}* ghost: {price} USDC to your wallet.",
        on={"cross": "home", "circle": "hub"},
    ),
    "ls_denied": State(
        name="ls_denied", mood="normal", kind="no",
        card={"t": "no", "h": "You said no", "rows": ("You tapped *Deny* in World App",),
              "what": (("Listed", "nothing"), ("That approval", "gone for good"), ("Next", "a fresh code"))},
        say="You tapped Deny, so *nothing was listed* and that request is gone for good. "
            "Cross to try again.",
        steps=_LS, at=1, halt=True, on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_cancel": State(
        name="ls_cancel", mood="normal", kind="no",
        card={"t": "back", "h": "Backed out here", "rows": ("You pressed Circle on the console",),
              "what": (("Listed", "nothing"), ("Late Approve", "ignored: Circle decides"))},
        say="Backed out. Even if your phone says Approve later, I ignore it. Nothing was listed.",
        steps=_LS, at=1, halt=True, keep_call=True,
        mock_outcomes=(("Phone approves anyway", "ls_late"),),
        on={"ok": "ls_late", "cross": "ls_scan", "circle": "home"},
    ),
    "ls_late": State(
        name="ls_late", mood="serious", kind="no",
        card={"t": "no", "h": "Late approval ignored", "rows": ("Approved after you backed out",),
              "what": (("Listed", "nothing"), ("That approval", "used up, not acted on"),
                        ("Rule", "Circle always decides"))},
        say="Your phone approved after you backed out. I ignored it: *Circle on the console "
            "always decides*. Nothing was listed.",
        steps=_LS, at=1, fail=True, on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_expired": State(
        name="ls_expired", mood="normal", kind="no",
        card={"t": "time", "h": "Approval window closed", "rows": ("No answer from your phone in time",),
              "what": (("Listed", "nothing"), ("Code {code}", "dead for good"), ("Next", "a fresh code"))},
        say="The code ran out before your phone approved, so nothing was listed. Cross for a "
            "fresh code.",
        steps=_LS, at=1, halt=True, on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_wrong": State(
        name="ls_wrong", mood="worried", kind="no",
        card={"t": "no", "h": "Wrong {world} ID",
              "rows": ("Approved by a {world} ID that does not own *{book}*",),
              "what": (("Listed", "nothing"), ("Refused by", "{world} itself"),
                        ("Rule", "only the owner lists its runs"))},
        say="That phone's {world} ID does not own record book *{book}*, so {world} refused it. "
            "Only the owner can list these runs.",
        steps=_LS, at=1, fail=True, on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_mismatch": State(
        name="ls_mismatch", mood="serious", kind="warn",
        card={"t": "warn", "h": "Codes do not match", "rows": ("Your phone shows a different code",),
              "what": (("What I did", "cancelled this request"), ("Why", "someone else scanned it?"),
                        ("Next", "scan only from this screen"))},
        say="A different code on your phone means it is someone else's request. I cancelled "
            "this one. Scan only from this screen.",
        steps=_LS, at=1, halt=True, on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_reused": State(
        name="ls_reused", mood="serious", kind="no",
        card={"t": "no", "h": "Approval already used", "rows": ("It already listed another run",),
              "what": (("Listed", "nothing"), ("Rule", "one approval, one listing"), ("Next", "a fresh code"))},
        say="That approval was already used for another listing. Each one works *exactly once*. "
            "Cross for a fresh code.",
        steps=_LS, at=1, fail=True, on={"cross": "ls_scan", "circle": "home"},
    ),
    "ls_record_fail": State(
        name="ls_record_fail", mood="worried", kind="warn", down="third",
        card={"t": "warn", "h": "Approved, {record_rail} is slow", "rows": ("Your OK is saved for this listing only",),
              "what": (("Listed", "not yet"), ("Your approval", "kept for this listing"),
                        ("Next", "Cross tries again"))},
        say="You approved, but {record_rail} is not answering, so nothing is listed yet. "
            "Cross to try again.",
        steps=_LS, at=2, halt=True, on={"cross": "ls_record", "circle": "home"},
    ),
    "ls_publish_fail": State(
        name="ls_publish_fail", mood="worried", kind="warn", down="board",
        card={"t": "warn", "h": "Recorded, not listed yet",
              "what": (("Listed", "not yet"), ("Next", "Cross tries again"))},
        say="Your listing is recorded on {record_rail}, but {board} is not answering. Cross to "
            "try listing again.",
        steps=_LS, at=3, halt=True, on={"cross": "ls_arkiv", "circle": "home"},
    ),
    "ls_world_down": State(
        name="ls_world_down", mood="worried", kind="no", down="world",
        card={"t": "no", "h": "{world} is not answering", "rows": ("Can not ask for your approval",),
              "what": (("Listed", "nothing"), ("Your run", "saved, list it later"), ("Games", "still play"))},
        say="{world} is not answering, so I can not ask for your approval. Your run is saved; "
            "we can list it later.",
        on={"cross": "ls_scan", "circle": "home"},
    ),
    "home": State(
        name="home", mood="happy", card={"t": "back", "h": "Back home"},
        say="Back home. Pick a flow on the right to go again.",
        on={},
    ),

    # ---- new: the hub and the screens the prototype never needed -------------------------
    "hub": State(
        name="hub", mood="normal",
        card={"t": "hub", "rows": ("The board and your next run to beat", "List my best run",
                                   "My record book", "My listings", "Start over (mock)")},
        say="What are we doing? Pick one and press Cross.",
        on={"circle": "home"},
    ),
    "need_book": State(
        name="need_book", mood="thinking", kind="warn",
        card={"t": "warn", "h": "Record book needed", "rows": ("World App > IDKit, about a minute",),
              "what": (("Needed for", "buying and listing ghosts"), ("Without one", "the board still works"),
                       ("Next", "Cross gets one"))},
        say="You need a record book before you buy or list ghosts. It takes a minute. "
            "Cross to get one.",
        on={"cross": "s_boot", "circle": "hub"},
    ),
    "no_board": State(
        name="no_board", mood="normal", kind="warn",
        card={"t": "warn", "h": "No board yet", "rows": ("No run of {game} to race yet",),
              "what": (("Board", "none to show yet"), ("Games", "still play"), ("Next", "pick another game"))},
        say="There is no board for *{game}* yet. Pick a game on Home and press Triangle.",
        on={"cross": "hub", "circle": "hub"},
    ),
    "no_run": State(
        name="no_run", mood="normal", kind="warn",
        card={"t": "warn", "h": "No run to list yet", "rows": ("No finished run of {game} yet",),
              "what": (("Listed", "nothing"), ("Needs", "one finished run"), ("Next", "race, then list it"))},
        say="Finish a run of *{game}* first, then I can list it.",
        on={"cross": "hub", "circle": "hub"},
    ),
    "nobody_ahead": State(
        name="nobody_ahead", mood="excited", kind="ok",
        card={"t": "done", "h": "Nobody ahead sells", "rows": ("Faster runners keep their ghosts",),
              "what": (("Your place", "{rank}"), ("Race", "your own best ghost"), ("Cost", "nothing"))},
        say="Nobody ahead of you sells a ghost. Race your own best: Cross to go.",
        on={"cross": "racing", "circle": "hub"},
    ),
    "race_lost": State(
        name="race_lost", mood="serious", card={"t": "result", "h": "Not this time"},
        say="*{run_time}*. {target} is still *{gap}* ahead. Her ghost is yours: Cross races her "
            "again, no charge.",
        on={"cross": "racing", "circle": "hub"},
    ),
    "race_unfinished": State(
        name="race_unfinished", mood="normal",
        card={"t": "back", "h": "No time this run", "rows": ("No finished run this time",),
              "what": (("Board", "unchanged"), ("Charged", "nothing more"), ("Next", "Cross races again"))},
        say="No time this run. {ghost_kept}Cross to race again.",
        on={"cross": "racing", "circle": "hub"},
    ),
    "race_unverified": State(
        name="race_unverified", mood="worried", kind="no",
        card={"t": "no", "h": "Not counted", "rows": ("The replay check did not pass",),
              "what": (("Board", "unchanged"), ("Charged", "nothing"), ("Next", "Cross races again"))},
        say="That run did not verify, so it does not count. Nothing was charged. Cross to race again.",
        on={"cross": "racing", "circle": "hub"},
    ),
    "own_result": State(
        name="own_result", mood="excited", kind="ok", fx="confetti",
        card={"t": "result", "h": "New best"},
        say="*{run_time}!* A new best. Cross to list it so others can race you.",
        on={"cross": "ls_offer", "circle": "hub"},
    ),
    "own_again": State(
        name="own_again", mood="normal", card={"t": "result", "h": "Your best stands"},
        say="*{run_time}*. Your best stands. Cross to race it again.",
        on={"cross": "racing", "circle": "hub"},
    ),
    "book_view": State(
        name="book_view", mood="normal", card={"t": "book"},
        say="Record book *{book}*. {runs} runs on the board.",
        on={"cross": "hub", "circle": "hub"},
    ),
    "listings_view": State(
        name="listings_view", mood="normal", card={"t": "listings"},
        say="Your listings. Copies sold so far: {sold}.",
        on={"cross": "hub", "circle": "hub"},
    ),
    "start_over": State(
        name="start_over", mood="worried", kind="warn",
        card={"t": "warn", "h": "Start over (mock)", "rows": ("Mock only: a clean console",),
              "what": (("Forgets", "book, purchases, listings"), ("Keeps", "your runs and bests"),
                       ("Circle", "keeps everything"))},
        say="This forgets the record book, purchases and listings on this console. Cross to "
            "start over, Circle to keep them.",
        on={"cross": "hub", "circle": "hub"},
    ),
}


START = {"book": "s_boot", "board": "board", "list": "ls_offer", "hub": "hub"}


# A `{name}` placeholder in copy; the flow engine fills by the same pattern.
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def copy_texts(state: State) -> tuple[str, ...]:
    """Every piece of player-facing copy on a state: `say`, then the card's `h`, `rows`, the
    two strings of each `what` row, and each `mock_outcomes` label, in a fixed order. Shared by
    the tests below and by anything later that needs to walk a state's copy without re-deriving
    this shape."""
    card = state.card
    texts = [state.say]
    if "h" in card:
        texts.append(card["h"])
    texts.extend(card.get("rows", ()))
    for label, value in card.get("what", ()):
        texts.append(label)
        texts.append(value)
    for label, _next_state in state.mock_outcomes:
        texts.append(label)
    return tuple(texts)


# Every placeholder name any state's copy uses, derived from the table itself so this can never
# drift from it. Task 6's context dict must provide a value for each one it fills.
PLACEHOLDERS: frozenset[str] = frozenset(
    name
    for state in STATES.values()
    for text in copy_texts(state)
    for name in PLACEHOLDER_RE.findall(text)
)

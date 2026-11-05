"""PB the handler: walks the player through every mocked sponsor step on the console."""

# Words the copy must never use (ETHGlobal Mumbai anti-goal: no claim of proof of humanity, no
# wording that reads as gambling). A test over every state's copy checks against this list.
BANNED_WORDS = ("prove", "proof", "verified human", "earn", "win", "wins", "cash out",
                "prize", "staked", "bounty", "human ghost")

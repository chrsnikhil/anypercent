# Why Arkiv

## What players would lose on Postgres

Without Arkiv the board is a query on our database. Players would have to trust that our table holds what our checker
wrote, that nobody edited a time after the fact, and that the "ghost just ahead" we pick is really the one just ahead.
They could not check any of it without an API we choose to run.

With Arkiv, anyone runs the board's query themselves, against rows only our checker could have written:

- **The board is a public query.** The exact query string is on the web board and in the README. A stranger pastes it
  into `curl` and gets the same rows, from the chain, with no key and no backend of ours.
- **Who wrote a row is a fact, not a claim.** `$creator` is set by the chain. A row anyone else writes, however
  perfect, does not show (the look-alike demo).
- **Times can't be edited.** Run rows are read-only, for us too. Our checker could delete one; it cannot change one.
- **Rows outlive us if people want them.** Anyone can extend a run row, so a record does not depend on us paying to
  keep it.
- **Listings end on their own.** A listing's 7 days is the row's own lifetime, not a cron job of ours.
- **The board survives our laptop.** The console and the web board read Arkiv directly, so the board stays up when
  our service is off. Only buying a listed ghost needs our service, because it holds the ghost key.

## What stays off Arkiv, and why

| Kept off | Why |
|---|---|
| World ID nullifiers, the bridge's HMAC secret, World ID session ids | They tie a row to a person. Rows carry only an HMAC runner id and a record-book code, so the public board can't be joined to a World ID. |
| The ghost key | It is what a buyer pays for. It is derived on our service from a secret that never leaves it. |
| The listing approval's id (jti) | A one-time approval; publishing it would help nobody and could only be replayed against us. |
| Console ids, device ids and anyone's name | Privacy and consent: a run says which record book ran it, not who or where. |
| The approval text World App showed | It is checked by our service against the replayed run before anything is written; the row carries the facts it approved (game, time, price), not the text. |
| Hedera records and payments | Their own job, later; mocked in this build. |

Nothing about a player goes on Arkiv until they approve the listing in World App, and that approval says "on the
public board".

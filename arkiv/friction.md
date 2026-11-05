# Friction: our feedback to Arkiv

What we ran into building Any%'s board on Arkiv, each with a way to reproduce it. Items found while researching before
the event are labelled **(pre-event)**; everything else was found or re-checked at the event, on Rabdi with
`@arkiv-network/sdk` 1.0.1. The `npm run ...` commands run in `apps/world-bridge`.

Shell setup for the `curl` lines:

```bash
RPC=https://rpc.rabdi.db-chain.testnet.arkiv.network
q() { curl -s $RPC -H 'content-type: application/json' --data @-; }
```

## 1. The SDK and the network changed under 0.8 users in the event week, and the old network still answers

Our pre-event design was on SDK 0.8.1 and the Tiramisu testnet **(pre-event)**. At the event, `latest` was 1.0.1 and the
current testnet Rabdi. Everything we had moved:

| | 0.8.1 | 1.0.1 |
|---|---|---|
| Network | Tiramisu, chain 7738577 | Rabdi, chain 7794095 (the SDK's only chain) |
| Data | attributes plus one payload | `defineSchema` columns; `bytes` columns instead of the payload |
| Types | `bytes32` existed | no `bytes32` (typeId 6 reserved, reads back as `key`) |
| Page | 200 rows, cursor | 100 rows, `limit` + `offset` |
| Order | newest first only | `ORDER BY name:type ASC/DESC` |

A 0.8 client gets no signal that it is on the old network: Tiramisu still answers.

```bash
curl -s https://rpc.tiramisu.db-chain.testnet.arkiv.network -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'
# {"jsonrpc":"2.0","id":1,"result":"0x7614d1"}
```

Ask: a deprecation answer (or a warning field) from a superseded network's RPC, and a migration note per SDK major.

## 2. The node pages with a cursor nobody documents

Every `arkiv_query` reply carries a `cursor`, and the node accepts `cursor`/`atBlock`, but neither the 1.0.1 SDK nor
the docs mention it. The docs say to page with `offset`, which "can repeat or miss a row" while others write, and
suggest `$key > key(<last>)` instead.

```bash
q <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"arkiv_query","params":["$expiresAt > u64(0)",{"select":{"key":true},"limit":"0x2"}]}
EOF
# ... "blockNumber":"0x402b2","cursor":"b64:Fic6KMpHCAwAAAAAAAAAAg"}}
```

Ask: document the cursor (it reads one block, which is exactly what a consistent board wants), or drop it.

## 3. No hash type

SHA-256 has no type of its own since `bytes32` went. We store a log's hash as a 64-character `str` (`log_h`), indexed for
equality. `key` would fit 32 bytes, but it means "a reference to another entity". A `hash`/`bytes32` type would halve the
indexed bytes and say what the column is.

Reproduce: `apps/world-bridge/src/arkiv/schema.ts`, column `log_h`.

## 4. `$createdAt` can be selected but not filtered or sorted

"Newest runs" or "runs this week" is not one query: we would need our own timestamp column.

```bash
q <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"arkiv_query","params":["$expiresAt > u64(0) ORDER BY $createdAt:u64 DESC",{"select":{"key":true},"limit":"0x1"}]}
EOF
# {"code":-32002,"message":"$createdAt is not queryable — it is returned by projections only", ...}
```

## 5. No sponsored transactions: whoever signs pays

Every write is paid by its signer, and the signer becomes the owner **(pre-event: no paymaster or sponsored path in the
docs; still none in SDK 1.0.1)**. So our checker pays for every row, a fan who wants to keep a run alive
(`permissionlessExtension`) needs tGLM of their own, and runner-owned rows would need every runner's wallet funded.

Reproduce: `npm run arkiv:extend -- <run key>` with an unfunded `ARKIV_STRANGER_KEY` fails at gas.

## 6. `readonly` still allows delete and recreate

A read-only row cannot be patched, but its owner can delete it and write a different one. There is no "undeletable"
flag, so we cannot say "nobody can change a time"; we say "a run row can't be edited, not even by our checker; our
checker could delete one". A flag that blocks delete (with expiry still allowed) would make the stronger claim true.

Reproduce: `npm run arkiv:smoke` (step 4 refuses the patches, step 7 deletes the same read-only rows).

## 7. No expiry event **(pre-event, still true in 1.0.1)**

`watchEntityEvents` knows `EntityCreated`, `EntityPatched`, `ExpiryExtended`, `OwnershipTransferred` and
`EntityDeleted`, but nothing fires when a row expires. To learn that a listing ended we query again.

Reproduce: `node_modules/@arkiv-network/sdk/src/entity/events.ts`.

## 8. Every raw reader re-implements the SDK's schema checks

Through the SDK, a row that does not fit the schema is skipped and counted. A raw JSON-RPC reader gets every matching
row, including other wallets' rows built to look like ours, and has to check types, required columns, the
`arkiv.schema` tag and the creator itself. We wrote that check three times: TypeScript (the service,
`src/arkiv/rows.ts`), Python (the console), JavaScript (the web board). A published, language-neutral description of a
named schema (or a node-side "this schema, these types" filter) would remove that.

## 9. The access key leaks through error messages

On Rabdi the access key is the RPC URL's last path segment. viem's HTTP errors print the URL, so any app that logs an
RPC error logs its key. We cut every error down to a short reason with URLs removed before logging.

```ts
// apps/world-bridge, npx tsx: an unreachable host with a made-up key
const c = createPublicClient({ chain: rabdi({ accessKey: "made-up-key" }), transport: http("http://127.0.0.1:9/made-up-key") });
await c.getChainId().catch((e) => console.log(e.message.includes("made-up-key"))); // true
```

Ask: accept the key in a header too, or have the SDK redact it from errors.

## 10. Predicted keys need one writer per wallet

`predictEntityKeys` is what lets a run and its listing (which names the run's key) go in one transaction. It is valid
only while nothing else from that wallet is in flight, and there is no way to reserve the nonces. So every write from
the checker goes through one serial queue, and our CLI must not write while the service publishes. We also check that
the keys the engine minted equal the predicted ones and fail the job if not.

Reproduce: `apps/world-bridge/src/arkiv/client.ts`, `writeRunAndListing`.

## 11. Explorer URLs are not documented

`https://rabdi.explorer.arkiv.network` is a single-page app: every path answers 200 with the same HTML. We found its
routes (`/entity/<key>`, `/tx/<hash>`, `/address/<address>`, `/block/<n>`) by reading its JavaScript bundle. A short
list in the docs would let projects link rows to it with confidence.

## 12. A `key` column comes back from `arkiv_query` tagged `bytes32`

We write a listing's `run` column as a `key` (`key().indexed()` in the schema, `key(<run key>)` as the value; the SDK
sends typeId 10). The SDK's type table calls `bytes32` (typeId 6) reserved and says it "reads back as `key`". So we
expected `arkiv_query` to tag the column `key`. It tags it `bytes32`:

```json
{ "name": "run", "type": "bytes32", "value": "0x1a7d31fd898939adb76280fdaff8cc5f830c82ef6fd0a00105d4b0d45834cf1d" }
```

The value is right: it is the run's real key, predicted with `predictEntityKeys` and minted as predicted. The SDK
hides the tag (its decoder narrows `"bytes32"` to `key`, `schema/codec.ts` `asTypeTag`), so nothing goes wrong through
the SDK. Every raw reader that checks the type against the schema, as ours must (item 8), drops the row as "a
`bytes32`, not a `key`". For us that was every listing: the live smoke's "the listing names the run's predicted key"
check failed until all three of our readers (TypeScript, Python, the web board's JavaScript) read `bytes32` as `key`.
Filtering works either way: `run = key(0x...)` finds the row.

Reproduce: `npm run arkiv:smoke -- --raw` writes a smoke listing and prints a raw page; or, once a listing is on our board:

```bash
q <<'EOF2'
{"jsonrpc":"2.0","id":1,"method":"arkiv_query","params":["arkiv.schema = str('anypercent.listing') AND $creator = addr(0x3d3260425Cb52F0c6716212274a883337aFa3f63)",{"select":{"key":true,"attributes":{"run":true}},"limit":"0x1"}]}
EOF2
# ... "attributes":[{"name":"run","type":"bytes32","value":"0x..."}]
```

Ask: tag a `key` column `key` in `arkiv_query` replies (or document that `bytes32` means `key` on the wire).

## 13. Cost per operation and latency (measured)

From `npm run arkiv:smoke` on Rabdi through the public endpoint (no access key). The owner funded each wallet with
10 tGLM from the faucet; one full smoke (two runs, a listing, an extension, a look-alike, deletes) cost about 0.0012
tGLM in total.

| Operation | Gas | tGLM | Time to receipt |
|---|---|---|---|
| Run + listing, one batch (predicted keys) | 392,442 to 395,230 | 0.0003 | 4.6 to 4.7 s |
| One run (open tier, 120-byte plain log) | 185,348 | 0.0001 | 3.9 s |
| Extend a run (the stranger) | 42,961 | under 0.0001 | 4.3 s |
| A look-alike run (the stranger) | 194,622 | 0.0001 | |
| Delete three rows, one batch | 411,146 | 0.0004 | |
| Delete one row | 154,870 | 0.0001 | |

Every query (Q1-Q9, a `dec` and a `key` filter, `select.count`) answered in 0.27 to 0.42 s; `eth_chainId` in about
0.4 s. A patch on a read-only row is refused at gas estimation, so it costs nothing. With 10 tGLM the checker can write
about 30,000 run+listing batches, so cost does not limit a hackathon board.

## What worked well

- `ORDER BY` with a range filter answers "the listed ghost just ahead of me" in one call, sorted across all matches.
- The node's errors say what to do: `"unexpected input after ORDER BY — it ends the query, and sorts by one attribute"`,
  `"address fails its EIP-55 checksum — fix the capitalization, or write it all-lowercase"`.
- Anonymous `arkiv_query` with CORS `*` let the web board run in any browser with no backend.
- The SDK's query builder renders exactly the strings we send by hand; our tests compare the two.

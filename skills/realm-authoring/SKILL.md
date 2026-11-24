---
name: realm-authoring
description: Author or extend an Embabel realm, a git repo of declarative capabilities (actions, types, APIs, virtual joins that fetch remote records, MCP servers, commands, webhooks, event sources, event handlers, skills, personalities, apps) that a host installs into a world. Activate for any request to create/build/scaffold/extend a realm, add a capability to a realm (a new action, type, API, producer, virtual join, verb, webhook, event source, event handler/reaction, skill, command), wire a new integration as a realm, or understand the realm format. Pushdown is designed first, from the source's documentation, and a realm is finished when `embabel realm audit` scores it at or near 100 against REALM_QUALITY.md, `realm validate --strict` passes, and its battery ends `ALL CHECKS PASS`. The full contract is the spec at the repo root (README.md); this skill is the map; read the named section before writing a file.
---

# Authoring an Embabel realm

`realm.ts` is the preferred realm definition format, assembled from local definition files
as needed. The host reads it directly. Do not generate or commit YAML or manifests from it.
Start with [Composing a realm](https://github.com/embabel-worlds/realm-spec/blob/main/REALM_COMPOSITION.md) and the
[TypeScript contract](https://github.com/embabel-worlds/realm-spec/blob/main/TYPESCRIPT_REALMS.md). Existing YAML realms remain readable
under the [legacy compatibility and migration rules](https://github.com/embabel-worlds/realm-spec/blob/main/TYPESCRIPT_REALMS.md#source-selection-and-legacy-compatibility)
and receive no new YAML features. The directory recipes below describe that legacy
format and existing capability semantics; they are not a second declaration to create beside
`realm.ts`. A realm contains no JVM bytecode, host configuration or user credentials.

## First decision: WHICH AUTHORING PATH ARE YOU ON?

Answer this before anything else, because the two paths use different tools and only one
of them is available to you. Everything else in this skill — `npm install`, `npm test`,
`docker compose`, the harness scripts — assumes the first.

**On a checkout.** The realm is a git repo on disk that the operator has mounted. You edit
files with your own tools and it stays their repo, pushed by them. Loop:

    edit files -> realm_validate_path -> realm_refresh -> kg_query

**Through MCP, with no checkout mounted.** You have no filesystem; you have tools. You
write into an invisible draft and publish it:

    realm_write (one file per call) -> realm_validate -> realm_install

Two things about this path that nothing else tells you:
- `wasm/handlers.ts` is where TypeScript goes. Not `agents/` (that is YAML: agents and
  the routines that call into it), not `src/api/*.ts` (that is the checkout build, which this path does not run).
- **`realm_install` consumes the draft.** After a successful install the next
  `realm_write` starts a NEW empty draft — so a follow-up write, on its own, produces
  "realm.yml is missing" for a file you wrote minutes ago. Re-write the whole realm, or
  edit on a checkout instead.

`realm_brief` tells you which path this appliance is on; it says so explicitly when no
checkout is mounted.

## Second decision: declarative or handlers?

- **Start declarative.** If a declaration (an `actions/` step, a `types/` type, an
  `apis/` OpenAPI entry, a `producers/` virtual join) expresses it, use that — no build
  step, the host's planner reasons over it directly.
- **Reach for `src/` TypeScript handlers** only when there are invariants YAML can't hold:
  revision/optimistic-lock guards, multi-call orchestration, shaping a rich API into
  idiomatic methods, or giving a type *behaviour* (verbs). Handlers are separate from the realm definition.

## Pushdown first — before you write a producer

A realm's producers decide what every question over it costs. A filter the source applies costs
nothing; a filter the graph applies costs every record the source returned. And the large win is
not the filter's own page: the engine pushes a `LIMIT` (stop the page walk) and a `count()` (ask
for a number, not the records) **only when the graph has nothing left to filter**. One filter the
source could have applied and was not told about forfeits both, and the answer is identical, so
nothing tells you. That is why pushdown is designed first, from the source's documentation, and
not added later from a slow query.

The standard is [REALM_QUALITY.md](https://github.com/embabel-worlds/realm-spec/blob/main/REALM_QUALITY.md)
§5 and §6 (rules R1–R11). The full mechanics are the
[README, predicate pushdown](https://github.com/embabel-worlds/realm-spec/blob/main/README.md#predicate-pushdown-pushdown--scope-the-fetch-at-the-source)
and [Virtual Cypher](https://github.com/embabel-worlds/realm-spec/blob/main/VIRTUAL_CYPHER.md) (paging,
caching, aggregates, diagnostics).

### The method

Work through it in order. Each step has its reason; skip one and the next step's work is wasted.

1. **Read the source API's documentation and write an inventory before any YAML.** For each list
   endpoint: every filter parameter and its operator (equality, set, range, text search), its sort
   options, its maximum page size and paging style, whether the first page reports a total, its
   by-id or bulk-by-ids endpoints, its count or grouping endpoints, and its rate limit. *Why:* the
   planner can only push what you declare, and you can only declare what you listed.
2. **Prove each filter narrows: call it with and without, and compare the counts.** *Why:* many
   sources ignore an unknown or misspelled filter and return everything with a 200. A rule for a
   filter the source ignores is a full scan that looks like success. Write the counts in a comment
   beside the rule.
3. **Read the source's comparison semantics, not just its parameter names.** Exact or substring?
   Case-sensitive? Does a value outside its list return 422, empty, or everything? Is a date
   compared as a string, a midnight, a UTC instant? *Why:* a pushed filter must keep at least every
   row the graph's comparison keeps. Looser costs rows; stricter loses rows nothing can recover.
4. **Choose the doors.** One producer per way in: the scan door (a whole status, the whole book),
   a key-addressed door for single records, a batched door for "these 200 keys", a search door for
   free text. *Why:* pushing a predicate makes each call cheaper; only another door changes how
   many calls a question makes.
5. **Declare every verified filter as a `pushdown:` rule with an explicit `op`.** *Why:* an omitted
   `op` on a remote rule means `CONTAINS`, and an equality in a query never matches it.
6. **Set paging to the source's maximum page size, with `total` where page one reports one.**
   *Why:* fewer calls for the same records, and a known total lets the remaining pages be fetched
   together instead of one after another.
7. **Declare `orderedBy` for the order the source returns records in unasked.** *Why:* a top-N
   question then reads one page, not the book.
8. **Declare `aggregates:` where the source reports a true filtered total, and only there.** *Why:*
   "how many" becomes one call, but a source total that ignores a filter, or is cached by the
   source, is a confident wrong number.
9. **Declare a cache matched to how the records change, with `negativeTtlSeconds`.** *Why:* the
   default reads the source on every query, and a positive-only cache asks again for every clean
   miss ("this customer has no open cases" is the common answer).
10. **Write `pushdown: []` with a comment where the source filters nothing.** *Why:* an absent key
    says "not yet declared" and the engine warns about it on every read; the empty list is a
    statement.
11. **Validate with `--strict`, then read `EXPLAIN` for the questions the realm exists to answer.**
    *Why:* an unknown key is dropped at load and only `--strict` fails on it; `EXPLAIN` names, per
    join, what was pushed and what the graph applied after fetching.
12. **Prove the cost in the battery (L3, below) and put a before/after call table in the PR.**
    *Why:* pushdown changes cost and never rows, so no row-level test can see a rule that does
    nothing.

### Patterns, each with a correct declaration

The examples are from realm-lago, realm-chatwoot and realm-odoo, the reference realms for this
standard. Every key is the same key in `realm.ts`, where `producers` is an object keyed by the
producer's name (see the end of this section).

**An equality, with its `op`.** Lago's `external_id` is exact (verified: 1 of 3,356).

```yaml
pushdown:
  - { property: externalId, op: EQUALS, argPath: "external_id", clause: "{value}" }
```

**A set (`IN`).** A node that is exactly `"{values}"` becomes the member list as real JSON.

```yaml
- { property: partner_id, op: IN, argPath: "domain.-", clause: ["partner_id", "in", "{values}"] }
```

**A value the source would reject.** `valuePattern` admits only values the source accepts; any other
value stays a graph-side filter instead of failing the question with a 422.

```yaml
- { property: paymentStatus, op: EQUALS, argPath: "payment_status", clause: "{value}",
    valuePattern: '^(pending|succeeded|failed)$' }
```

**Ranges and dates.** Declare each bound as its own rule. Where the source compares a date as a
string, admit only the bare `YYYY-MM-DD`; the engine re-spells a range bound into canonical UTC
(`yyyy-MM-ddTHH:mm:ssZ`) and tries the pattern again, so write the pattern for the form the source
takes. An equality on a day is both bounds.

```yaml
- { property: issuedOn, op: GREATER_THAN_OR_EQUAL, argPath: "issuing_date_from", clause: "{value}",
    valuePattern: '^(\d{4}-\d{2}-\d{2})$' }
- { property: issuedOn, op: LESS_THAN_OR_EQUAL, argPath: "issuing_date_to", clause: "{value}",
    valuePattern: '^(\d{4}-\d{2}-\d{2})$' }
- { property: issuedOn, op: EQUALS, argPath: "issuing_date_from", clause: "{value}",
    valuePattern: '^(\d{4}-\d{2}-\d{2})$' }
- { property: issuedOn, op: EQUALS, argPath: "issuing_date_to", clause: "{value}",
    valuePattern: '^(\d{4}-\d{2}-\d{2})$' }
```

Do not push `>` a bare date against a date-time field: the source reads the date as midnight, the
graph reads `'2026-10-22 00:00:00'` as after `'2026-10-22'`, and a record at midnight is lost.

**Case-insensitive text (`match: ci`), and why it must not feed a count.** Odoo's `ilike` ignores case,
so declaring `match: ci` lets it answer `toLower(c.name) CONTAINS 'acme'` too. It also reads `%` and
`_` as wildcards, which only widens what comes back. The graph re-applies the query's own comparison,
so rows stay exact, but a number cannot be re-filtered: on a producer that declares `aggregates:`,
refuse wildcard characters so a widened match never becomes a count.

```yaml
- { property: name, op: CONTAINS, argPath: "domain.-", clause: ["name", "ilike", "{value}"],
    match: ci, valuePattern: '^([^%_\\]*)$' }
```

A substring search is never an equality. Lago's only text filter, `search_term`, matches name,
email and external id as substrings, so `name = 'Acme'` is NOT pushed through it: a count over a
superset is exact, confident and wrong. A name lookup goes through a search door whose join says
it is a search, and the query filters `c.name = …` on what it returns.

**A single record by key, not by listing.** Where the source has `GET /plans/{code}` beside
`GET /plans`, declare a producer over the by-key endpoint. `keyArgs` hands each key over as a
scalar path parameter (`keyArg` would send a one-element list); `keySplit` splits a composite key
on its delimiter.

```yaml
- name: lagoPlanByCode
  kind: api
  operation: lagoPlanGet
  records: "$.plan"
  keyArgs: [code]
  pushdown: []
  cache: { kind: ttl, seconds: 3600, negativeTtlSeconds: 3600 }
```

On the join, `materializedKeyField` tells the engine every record from that door carries the key in
that property, so `MATCH (c:SupportCase) WHERE c.accountKey = 'acme.com'` takes the one-company door
by itself instead of sweeping the desk.

**A batch, not N+1.** Where the source takes a list of keys, put the list at `keyArg` and set
`maxKeysPerCall` to the source's cap. A source whose key is a number matches nothing on strings,
silently: declare `keyType: int`. When each record carries the key it belongs to, compute the link
from the record rather than echoing it, because an echo costs one call per key.

```yaml
- name: unpaidInvoicesByPartner
  kind: api
  keyType: int
  operation: invoicesSearchRead
  records: "$[*]"
  keyArg: "domain.0.2"
  args:
    domain: [["partner_id", "in", []], ["state", "=", "posted"]]
    fields: [name, partner_id, amount_residual, invoice_date_due, currency_id]
  maxKeysPerCall: 200
  paging: { style: offset, param: offset, sizeParam: limit, size: 1000, maxPages: 50 }
  compute:
    partnerKey: "CASE r.partner_id WHEN false THEN null ELSE r.partner_id[0] END"
```

Keep `batchSafe: false` only for a source that really answers one key per call, such as a globally
ranked, capped search, where a batch would starve the low-volume keys.

**Page size at the source's maximum, with `total`.** Chatwoot's conversation list is 25 a page,
fixed; its first page reports the desk's count, so the rest of the walk runs in parallel.

```yaml
paging: { style: page, param: page, size: 25, maxPages: 2000, total: data.meta.all_count }
orderedBy: [{ property: createdAt }]
```

`maxPages` is the ceiling, sized so a real book is read whole: a walk that stops at the cap reports a
partial answer. With `orderedBy`, "the 10 newest" reads the pages that hold ten and stops. Pick a
size every supported source version accepts: Lago takes any `per_page` in one release and refuses
more than 200 from the next, so 200 is right.

**Counts the source answers.** Three shapes, one mechanism.

```yaml
# 1. A total on the listing's own envelope: the first page IS the count call.
aggregates:
  - { measure: count, valueField: data.meta.all_count, records: "$" }

# 2. A grouping endpoint: its own operation and its own args, which REPLACE the listing's.
aggregates:
  - measure: sum
    of: amount_residual
    operation: invoicesReadGroup
    args:
      domain: [["partner_id", "in", []], ["state", "=", "posted"]]
      fields: ["amount_residual:sum"]
      groupby: [partner_id]
    records: "$[*]"
    valueField: amount_residual
    keyField: partnerKey

# 3. The bare number as the whole body (Odoo search_count).
aggregates:
  - measure: count
    operation: invoicesSearchCount
    args: { domain: [["state", "=", "posted"]] }
    valueField: "$"
    keyField: scopeKey
```

An aggregate endpoint handed the listing's page arguments answers a different question: Odoo's
`search_count` reads the page `limit` as an upper bound. So declare its own `args:`, restating the
fixed conjuncts; the keys and every pushed filter are still added to it. `count`, `sum`, `min` and
`max` are delivered; `avg` is not supported, because an average cannot be recombined.

**When NOT to declare a count.** Lago caches its invoice `total_count` for up to 30 minutes under a
key built from scalar parameters only, so an array filter shares the unfiltered list's count. Its
invoice producers declare no `aggregates:` and say why in a comment. Chatwoot's text search computes
its count after cutting the page, so that door declares neither `total` nor a count. Before
declaring a count, check it against the records with a filter applied, twice, a minute apart.

**Caches matched to how records change.** One read holds records in every state, so the window is
set by the most volatile thing in it.

```yaml
cache: { kind: ttl, seconds: 60, negativeTtlSeconds: 60 }        # a support desk: changes by the minute
cache: { kind: ttl, seconds: 120, negativeTtlSeconds: 120 }      # invoices: payment status flips
cache: { kind: ttl, seconds: 3600, negativeTtlSeconds: 3600 }    # plans: edited rarely
cache: { kind: immutable }                                       # a filed document, a closed period
```

Put what changes into the key and the TTL can be long: Chatwoot's thread producer keys on the
conversation and its `lastActivityAt`, so a new message is a new key and an unchanged thread is
served for a day. Use `cache: { kind: none }` only when every read must be live, and say so.

**A source that filters nothing.** A conversation's thread comes back whole or not at all:

```yaml
# The endpoint has no filter: a `messageType = 0` in a query is always applied graph-side.
pushdown: []
```

A door meant to be shared by a family of views declares `readWhole: true` with a `ttl` cache
instead: the rules stay declared, none is sent, and every view reads the same cached collection.

**The same producer in `realm.ts`.** Conventional producers take the same keys, as an object keyed
by name:

```ts
producers: {
  lagoInvoicesAll: {
    kind: "api",
    operation: "lagoInvoicesList",
    records: "$.invoices[*]",
    keyTemplate: "{key}",
    echoKeyAs: "scopeKey",
    args: { per_page: 200, status: "finalized" },
    paging: { style: "page", param: "page", size: 200, maxPages: 250, total: "meta.total_count" },
    orderedBy: [{ property: "issuedOn", descending: true }],
    pushdown: [
      { property: "customerExternalId", op: "EQUALS", argPath: "external_customer_id", clause: "{value}" },
      { property: "issuedOn", op: "GREATER_THAN_OR_EQUAL", argPath: "issuing_date_from",
        clause: "{value}", valuePattern: "^(\\d{4}-\\d{2}-\\d{2})$" },
    ],
    // No aggregates: Lago's invoice total ignores array filters and is cached (see above).
    cache: { kind: "ttl", seconds: 120, negativeTtlSeconds: 120 },
  },
},
```

A captured realm's handler-backed producer pushes through `pushdown: [{ property, argument }]`
instead; see [Captured realms](#captured-realms-producers-graph-reads-apps-and-proposals).

### Per source kind

| Source | How a filter is sent | What to watch |
|---|---|---|
| REST with query parameters | `argPath` is the parameter name, `clause: "{value}"`; an array parameter (`status[]`) takes `clause: ["{value}"]` or `"{values}"` | Unknown parameters are often ignored with a 200. Some take an array form only (Lago's `status[]`; a scalar `status=` is ignored). A boolean `false` may arrive as the text "false" and read as true: push only the value that works. |
| JSON-RPC with domains (Odoo) | `argPath: "domain.-"` appends a triple; a domain is an implicit AND, so no `linkPrevious` | Set `fields:` to what the type projects. Domain values are typed: declare `keyType: int`. Counts are `search_count` and `read_group` with their own `args:`. A many2one arrives as `[id, name]`: compute the id back. |
| JSON filter payloads (Chatwoot) | `argPath: payload.-` with a `clause` object and `linkPrevious: { query_operator: AND }` | The conjunction lives on the preceding clause and must be absent from the last; a wrong shape is an HTTP 500. A clause on an undefined custom attribute is dropped silently and returns everything. |
| SQL | `pushdown:` entries with `type` and `ops`; the engine binds the value into the generated statement | No `args` on a SQL aggregate; `measure` and `of` are the whole declaration. |
| SPARQL | A `{{filter:<property>}}` slot in the query, before the expensive part; typed literals | Compare through the expression that makes the source agree with the graph (`expr: "STR(?label)"`), or a language-tagged literal is lost. |
| Cypher | A `{{filter:<property>}}` slot after an existing condition; `expr` is required | Same exactness rule as SPARQL. |
| GraphQL (a remote producer over an `apis/` entry of `type: graphql`) | `argPath` into the operation's variables (a `where:` input object), `clause` as its JSON | Set `first:` to the maximum; walk Relay cursors with `paging: { style: cursor }`. Read a `totalCount` from the envelope as a count only if it honours the filters. |
| Server-side text search (Chatwoot `q`, Lago `search_term`) | Its own producer, keyed by the text (`keyArg: q`), on a search door | A search is a superset: never push an equality through it, and never read its count unless the source documents it as exact. |

### Reading "filter not sent"

The engine says when a filter was applied in the graph instead of at the source. Each note names its
fix:

- **At load:** "pushes 1 of the 3 filter(s) its source accepts — `since`, `labels` are fetched
  over the wire and filtered in the graph." Declare the named ones, or say in a comment why not.
- **`EXPLAIN`**, per join: `pushed to source: …` and `applied by the graph after fetching: …`. A
  residual is the next rule to write, and it is costing on a query someone runs.
- **`FILTERED_IN_GRAPH`** on a read: a `WHERE` was applied after the fetch on a producer with no
  rule for it. Declare the rule, or `pushdown: []` if the source cannot filter.
- **`PUSHDOWN_VALUE_UNMATCHED`**: a rule exists for the property and operator, but the value failed
  every rule's `valuePattern`. The note quotes the value and the pattern. Fix the spelling or the
  pattern. A producer's rules are judged together, so a property whose values are split between
  rules raises nothing for a value one of them sends.
- **`UNPUSHED_FILTER`**: a bounded read (page cap or limit reached) omitted a declared filter, so it
  cannot prove absence. Push the filter or narrow the question; never report the zero as clean.
- **`EMPTY_NOT_KEPT`**: clean misses were not cached. Add `negativeTtlSeconds`.
- **`PARTIAL_RESULT` (`TRUNCATED`)**: the walk hit `maxPages`. Usually a filter that should have been
  pushed; otherwise raise the cap to the source's real size.

## The pieces (read the spec section before writing one)

| Want to… | Directory | Spec section |
|---|---|---|
| metadata | `realm.yml` | "`realm.yml`" |
| an LLM step the planner chains | `actions/` (`stepType: action`) | "`actions/`" |
| a deterministic rule over a signal | `actions/` (FQN `PolicyActionSpec`) | "Deterministic rules" |
| a domain / signal / mirror type | `types/` | "`types/`" |
| call an external REST/GraphQL API | `apis/` (+ vendored spec) | "`apis/`" (auth, OAuth2) |
| ask for an API key (conventional realm) | `keys.yml` | "`keys.yml`", "Keys and declared credentials" |
| ask for a secret the owner binds (captured realm, recommended for new realms) | `credentials` in `realm.ts` | TYPESCRIPT_REALMS.md "Credentials" |
| call a GraphQL API from a captured realm | `graphql` in `realm.ts` | TYPESCRIPT_REALMS.md "GraphQL" |
| a shared IDENTITY other realms attach to (an account, a product, a site) | `types/` `spine:` | Virtual Cypher §5.4.1 — see "Joining OTHER realms" below |
| attach your records to a spine (yours, another realm's, or Person/Organization) | `types/` `hub:` on the property carrying the key | Virtual Cypher §5.4 |
| a shared KIND of record (every ticket is a `SupportCase`) | `types/` `parents:` | LABELS_AND_COMPOSITION.md |
| fetch a type **on demand** by traversal | `types/` `virtualJoins:` + `producers/` | "Joining types on demand" (Virtual Cypher) |
| a named, parameterized ANSWER a caller runs by name | `views/` | "Views" — the realm's answer surface: ship one per question the realm exists to answer, so nobody hand-writes Cypher over your join surface. Rows are typed (`gateway.views.<Name>()`); add `returns:` for a column the host types `unknown` (a `CASE`, an `ai.*` call) — "Typed rows" |
| query the graph from a code_mode script or skill | `gateway.kg.query` | "CypherScript" |
| query the graph from a WASM HANDLER | `ctx.gateway.cypher.query` | "CypherScript" and "Captured realms" |
| a CAPTURED realm written in TypeScript (`defineRealm`) | `realm.ts`, read directly by the host | TYPESCRIPT_REALMS.md, and "Captured realms" below |
| hand-authored gateway methods / **verbs** | `src/api/*.ts` + `tests/` | "`src/` and `tests/`" |
| prove the answer surface survives the author | `tests/questions.yml` + `tests/verify.sh` | "`tests/`" — REQUIRED once anything takes words from a person |
| an MCP server (last resort — prefer `apis/` for anything API-backed) | `mcp/` | "`mcp/`" |
| a slash command | `commands/` | "`commands/`" |
| inbound events → typed `Signal`s | `events/` (webhook + poll) | "`events/`" |
| an agent, and WHICH signal/cron its routines react to (declarative YAML) | `agents/` | "`agents/`" |
| the TypeScript a wasm-host realm actually runs | `wasm/handlers.ts` (ONE file) | "`wasm/`" |
| scheduled KG enrichment | `decorations/` | "`decorations/`" |
| an HTML app | `apps/` | "`apps/`" |
| tips the host UIs show this realm's users | `hints/` | "`hints/`" — hand-authored; teach the answer surface you shipped |
| on-demand LLM guidance | `skills/<name>/SKILL.md` | "`skills/`" |
| a voice/persona | `personalities/` | "`personalities/`" |
| a scoped chat surface | `focuses/` | "`focuses/`" |

## Virtual joins that fetch remote records (the on-demand path)

For large/volatile external collections, don't mirror — **virtual-join** them: declare
`virtualJoins:` on the type and a **producer** (a Repository over the source) in
`producers/`. Key points (full detail in "Joining types on demand" and "`producers/`"):

The engine that probes anchors, fetches, materializes transient `:Virtual` nodes and rolls
back is **Virtual Cypher** — see "Virtual Cypher — the engine" under "Joining types on demand".

- A producer is `kind: remote` (externally-backed; `api` is a back-compat alias), `sql`,
  `compute` (local), or `vector` (similarity-as-join). **Batch contract**: keys batched per
  call, never N+1 — UNLESS the source is a globally-ranked capped search, where you set
  **`batchSafe: false`** so each key is fetched on its own call (else a low-volume key is
  starved; see "Per-key vs batched").
- **Predicate pushdown** (`pushdown:`): a `WHERE` on the target node renders into the
  source's native filter so the fetch is scoped at the source — not fetched broadly and
  filtered in the graph. Design it first: [Pushdown first](#pushdown-first--before-you-write-a-producer).
- **Pagination** (`paging:`): walk pages so a fetch exceeding one page is fully captured.
- A literal-pinned anchor (`{login:'x'}` or `WHERE a.login='x'`) uses the real node if it
  exists, else seeds a named entity even when no such node exists, fetched with the
  connecting user's credentials.
- **LLM query primitives (the `ai` namespace)** work over any virtual collection your producer fetches —
  you declare nothing. A query author can `WHERE ai.relevant(n, '<subjective criterion>')`
  (filter), `ORDER BY ai.score(n, '<criterion>') DESC` (rerank), or steer a *generative*
  producer with an `{ai: {hint: '…'}}` edge directive map. When a search producer is keyed by the words a
  person typed, a view can add `CALL ai.terms($q, '<what the terms name>') YIELD term` and key the same
  search by `term`: a model proposes synonyms and expansions, the producer decides what exists, and every
  suggestion is reported with the answer. The `ai` namespace is **reserved** — never name a
  stored property or producer field `ai` or `ai_*`. See "LLM query primitives" in the Virtual Cypher spec.

## Joining OTHER realms — decide this before you write a type

A realm that stands alone is a connector. The value is in the question that needs two of them —
*accounts with an open ticket and an overdue invoice* — and that question only has an answer if
both realms' records land on **the same node**. This does not happen by accident, and when it
fails it fails as an **empty result with no error**. Design it first.

**Step 1 — for each entity your realm knows, ask: if two systems each hold one, are those two
things or one?**

- **Two things → a parent label.** Every helpdesk conversation is a `SupportCase`; two systems'
  tickets are two tickets. Declare `parents: [SupportCase]` and `MATCH (c:SupportCase)` returns
  them all.
- **One thing → a spine.** A CRM customer and a billing customer for the same company are two
  records *about* one account. They must resolve onto one node. `parents:` is WRONG here — it
  produces one `:CustomerAccount` per system with nothing joining them. The host refuses it.

**Step 2 — find the spine, in this order:**

1. `Person` (by email) or `Organization` (by email domain) — built in. Put `hub: Person` on the
   email property. Done.
2. A spine an installed realm already declares. Check `realm_status` / the vocabulary realm you
   are building against. Put `hub: <ThatSpine>` on the property carrying the key.
3. None fits → declare one, in the most general realm that needs it (a vocabulary realm, not a
   product realm — the spine must outlive any one product):

```yaml
- name: CustomerAccount
  spine:
    key: accountKey
    identityProperties: [accountKey, website]
    normalize: [lowercase, extractDomain, stripTrailingDot]
    require: hasDot
    exclude: freemail
```

**Step 3 — put `hub:` on the property that identifies the ENTITY, which is often not the one
that identifies the record.** Keep `identity: true` on the source's own id (your realm's joins key
on it) and put `hub:` on the website / email / registration number:

```yaml
- name: OdooCustomer
  properties:
    id:      { identity: true }
    website: { hub: CustomerAccount }
```

**Step 4 — never normalize on your own side.** Send the spine the raw value. The spine's
`normalize` is the one definition of "the same"; a realm that lowercases or strips `www.` itself
has encoded another realm's format and will drift from it.

**Step 4b — if the source can only be SEARCHED for your key, join on the record's own field.**
Set `recordKeyField` to the source's field (`url`, `website`) and do NOT `echoKeyAs`: a substring
search returns strays, an echo links every one of them, and the spine — which reads the record's
field too — links only the right one. Then assert it in `tests/verify.sh`: zero records linked to
an anchor that is not theirs.

**Step 4c — opt in from every system that can name the entity, and ship the view that walks
your door.** Spine nodes exist only once some realm's records have been read. A realm that keys
the spine ships a small view over its door so a surface can read it first; a realm whose views
START at the spine says so in its README.

**Step 5 — prove the join, with a test that would fail.** In `tests/verify.sh`, run the
two-realm question against live sources and assert a NON-ZERO count for an entity you know is in
both. A cross-realm view that returns zero rows passes every other check you have.

Smells that mean the join is not really there:

- You seeded the same key by hand into both realms to make the demo work.
- Your producer has a rewrite whose only job is to match another realm's spelling.
- Your `policy:` ladder's fallback rungs exist because two systems format one key differently —
  that is a spine, not a ladder. (A ladder is for a join that genuinely has more than one key. Its
  `key` rungs work; `ask`, `ci` and `confidence` are not honoured yet — spec §5.15.)
- `hub:` names a label that is not a spine in the world (typo, or the vocabulary realm is not
  installed). Nothing errors; nothing joins. The host logs it at world build — read the log.

Which mechanism for which situation: the table in Virtual Cypher §5.4.3.

## CypherScript (querying the graph from realm code)

A Wasm handler has the signature `export function name(args, ctx)` and accesses the gateway
through `ctx.gateway`. Code-mode scripts use `gateway` directly. These execution surfaces
have different admitted operations.

Where supported, `ctx.gateway.cypher.query({cypher, params})` binds values through `params`;
arrays and nested objects remain structured. Raw SQL gateway calls are not a portable guest
capability. External SQL uses approved producers or typed operations. The governed captured
path reaches Cypher through the same call once the owner separately approves `cypher_query`;
the rules for that call are under "Captured realms" below. Check what the target host states
it supports ([host support statements](https://github.com/embabel-worlds/realm-spec/blob/main/HOSTED_EXECUTION.md#host-support-statements))
before using a host-resource callback.

A handler / decoration / skill runs **CypherScript** in `code_mode`: TS/JS that interleaves
`await gateway.kg.query({cypher, params})` (graph reads through Virtual Cypher — scoped,
read-only, virtual joins materialize) with plain JS, `gateway.<ns>.*` integration calls, and
`gateway.ai.*` inline LLM, in one program. Full detail in "CypherScript — Cypher woven into
TypeScript/JavaScript".

## Methods on a type (behaviour on what a query finds)

A type method lets code query its way to a customer, an issue or a ticket and then work on it
there: `acme.addNote(...)`, `issue.close()`. Write one in TypeScript whenever a type has
something to DO, including YAML-declared types and ones a virtual join materializes. The class
name must equal the type's name.

```ts
// src/api/customer.ts — the file name is the namespace; the class name is the type
import { Entity } from "@embabel/runtime-types";

/** The verbs this type calls (from apis/): Entity's type argument, so this.gateway is typed. */
interface CrmGateway {
  odoo: { partnerMessagePost(a: { ids: number[]; body: string; message_type: "comment"; subtype_xmlid: "mail.mt_note" }): Promise<number[]> };
}

/** The graph carries ids as strings; Odoo's are integers. One checked conversion. */
function odooId(id: string): number {
  const n = Number(id);
  if (!Number.isInteger(n) || n <= 0) throw new Error(`not an Odoo record id: '${id}'`);
  return n;
}

/** A customer in Odoo. */
export class OdooCustomer extends Entity<CrmGateway> {
  name?: string;

  /** Add an internal note to the customer's history. Nobody is emailed. */
  async addNote(text: string): Promise<number> {
    const [id] = await this.gateway.odoo.partnerMessagePost({
      ids: [odooId(this.id)], body: text, message_type: "comment", subtype_xmlid: "mail.mt_note",
    });
    return id;
  }
}
```

- **Name the gateway once** as `Entity<...>`'s type argument; never a getter that casts it.
- **One parameter**: a bare value when one is enough, else one options object. Its type and the
  return type become the schema; the first JSDoc paragraph is what a model reads.
- **Writes**: name the action in the business's words and reuse that name across realms
  (`addNote`, `scheduleFollowUp`, `bookCall`, `assign`, `reply`); make the safe outcome the
  default (internal, no invitation, no customer-facing message unless asked); validate before
  calling; call exactly one declared verb. `this.id` is the graph's string; convert it in one
  checked helper. See "Designing write methods".
- **Test** with `entityForTest(OdooCustomer, { id: "12114" }, mockGateway<CrmGateway>({ odoo: { ... } }))`
  and assert the exact verb arguments.
- **Ship**: `npm run build` writes `dist/` and the `onType` entries in `dist/manifest.json`.
  Commit `dist/`, including `dist/node_modules/@embabel/runtime-types` (force-add it past a
  `node_modules/` ignore rule): the compiled class requires it in the sandbox.
- **Call it** from a script: read with `gateway.cypher.query` or `gateway.kg.query` (one
  path under two names; its rows carry `__type` and `__labels`), `state.set("acme", row)`, then
  `state.get("acme").addNote(...)`. Methods compose through labels, parents included. See
  "Acting on what a query finds".

## The quality bar: metadata a model can act on

A realm is finished when it meets [REALM_QUALITY.md](https://github.com/embabel-worlds/realm-spec/blob/main/REALM_QUALITY.md):
46 rules, each with its reason and a good and bad example. `embabel realm audit <dir>` scores the
checked ones from the files; aim for 100, and document every remaining finding as a deliberate
exception in a comment beside the declaration. What a model is shown is cut short, so the words
that matter go first:

| Declared | A model sees | So |
|---|---|---|
| type `description` | first 320 characters, cut at a sentence | Open with what ONE node is, the system, and the property that identifies it. |
| property `description` | 160 characters | Unit or currency, every status value and its meaning, which moment a date is and its format, what empty means. |
| view `description` | first sentence, 80 characters, in the list a model picks from | Say what it answers in the first sentence; then what it leaves out. |
| join `description` | whole | Write it for the question that traverses it, with its cost. |
| `realm.yml` `description` | first sentence, 120 characters, in the realm index | Name the system and the kind of record. |
| type `examples:` | in the query generator's prompt | Worked `q`/`cypher` pairs over the main joins. Keep each one true. |

Checklist, with the reason for each:

- **`values:` is a hard contract.** A query comparing the property with anything outside the list is
  refused. Declare it only when the list is complete, in the case the data uses; otherwise list the
  common values in the description and say the list is open.
- **Declare measures as fields:** `unit:` (`cents`, `ms`, `kWh`), `currency:` (the name of the
  property holding each row's ISO code, or a fixed code such as `GBP`) and `format:`
  (`yyyy-MM-dd`). Models see them under the type whether or not the question names the property.
  See [Property measures](https://github.com/embabel-worlds/realm-spec/blob/main/DECLARING_TYPES.md#property-measures--unit-currency-format).
- **Never sum across currencies.** A view that totals money returns one row per currency. A
  mixed-currency total is never the right answer, however it is labelled.
- **Say which clock a date is.** `createdAt` may be when the row was written (system clock) or when
  the customer raised the case (business date). Name the moment and the format in the description,
  and give the business date its own property when both exist.
- **Name params match exactly by default.** "Acme" must not return "Acme Holdings". Partial or
  case-insensitive matching is a separate, documented param.
- **Near-named entities are distinct; join on keys.** Two customers can share a name, and two
  invoices a name and an amount. Views return ids beside names, and joins and dedupes key on ids.
- **Honest names.** A view or column counting `urgent` and `high` is `UrgentOrHigh…`, not
  `Urgent…`. The name is quoted before the body is read.
- **Declare numeric and boolean types.** An undeclared property keeps the source's encoding, and a
  quoted number compared with a number matches nothing.
- **Nothing the host ignores.** An unknown key is dropped at load. `embabel realm validate` warns
  with the nearest real key and `--strict` fails on it. `valuePattern` belongs on a pushdown rule,
  not a property; `default:`, `examples:` and `dimension:` on a property do nothing. A
  `fixes:` on a virtual join was silently ignored until validation started naming unknown keys.
- **State `maturity:`** in `realm.yml` (`experimental`, `beta`, `stable`, `deprecated`). Absent is
  read as unstated, never as finished.
- **`requires:` every realm whose labels a view or join reads.** A view naming another realm's label
  without requiring it leaves this realm degraded wherever that realm is missing. Use a Maven range
  (`"[0.2.0,1.0.0)"`) with the lower bound at the version you tested against.
- **A DERIVE rule set binds its params by name from the view's arguments** (Virtual Cypher §13.1).
  Give the view a param of the same name to anchor the rules to one entity, and default every rule
  param so implicit evaluation works.

## Before you install

Run these in order. Each catches a failure the next one cannot see.

1. **`embabel realm validate <dir> --strict`** (or `realm_validate` / `realm_validate_path`): zero
   errors, no new warnings. *Why:* strict mode fails on keys the host would silently drop.
2. **`embabel realm audit <dir> -v`**: 100, or every finding documented as deliberate. *Why:* it
   checks the metadata a model reads, which validation does not.
3. **The pushdown inventory is complete:** every verified source filter declared with an `op`,
   paging at the source maximum, a cache with `negativeTtlSeconds` on every remote producer,
   `pushdown: []` with a comment where the source filters nothing. *Why:* the audit can only
   check what is declared, not what the source offers.
4. **`requires:` names every realm whose labels you read.** *Why:* the realm installs and then
   reports itself degraded.
5. **The battery exists and passes** (below). *Why:* a realm whose files are perfect and whose every
   join matches nothing looks the same as an empty source.
6. **A version bump is installed with an update or a reinstall, not a refresh.** *Why:* a realm
   installed from git is pinned; a refresh reloads the pinned version.

## Build, test, ship

```bash
npm install && npm run typecheck && npm test && npm run build   # only if the realm has src/
```

- `@embabel/runtime-types` gives `Entity`, `mockGateway`, `entityForTest`, `hydrate*`, and
  `embabel-build-manifest` (writes `dist/manifest.json`). Tests run hermetically in Node.
- The host runs `npm install && npm run build` at install; `dist/` (incl. a vendored
  runtime-types) is the shippable bundle. `embabel-realm sync` regenerates `.embabel/gateway.d.ts`.

### The declarative half has no unit tests — run it against a live host

`npm test` covers `src/` handlers. It says **nothing** about the part of a realm that usually
breaks: producers, virtual joins and views are only exercised by a running host against the real
source. A realm whose YAML parses, whose types load, and whose every query silently returns
nothing is the normal failure — and it looks identical to "the source has no data".

**Before you call a realm done, run every view against a live host and require rows.** Ship that
as a test-views script under your own realm's `scripts/` directory, so it is repeatable by whoever
inherits it:

```bash
docker compose up -d --wait          # if the realm provisions its own store
python3 scripts/load-<source>.py     # …and loads it
# start the host with this realm installed, then:
python3 scripts/test-views.py 8046   # every view, real params, non-zero rows required
```

Call the host's own endpoints — never re-implement them. Re-implementing argument merging,
defaults, coercion or literal substitution in your script produces a copy of platform logic that
can pass while the platform's own is broken, which is the opposite of what a harness is for:

| Want | Endpoint |
|---|---|
| discover views + their declared params/defaults | `GET /api/v1/admin/kg/views` |
| run one view with args (rows + warnings) | `POST /api/v1/admin/kg/views/{name}/run` |
| see the Cypher a view would run (debugging) | `POST /api/v1/admin/kg/views/{name}/invocation` |
| run verbatim Cypher through the engine | `POST /api/v1/admin/kg/execute` |
| **reload your realm's YAML — NO app restart** | `POST /api/v1/realms/{name}/update` |

That last one is the difference between a two-minute edit loop and a two-second one: a realm
referenced by local path is reloaded in place, so edit YAML → update → re-run the harness.

**Every view needs a case; a view with no case is untested.** Fail the run if any view returns
zero rows.

What that catches, every time, and static review does not:

- a join whose keys never match (0 rows, no error) — the single most common realm bug;
- a fetch that never happens because the planner refused the hop as too wide;
- a property that vanishes between the source and the graph (an unstorable type);
- a view whose Cypher is valid but whose shape resolves names for thousands of rows to show ten.

Read the WARNINGS in every response, not just the rows. A `PRODUCER_ERROR` / `FIELDS_WITHHELD` /
`INCOMPLETE_TRAVERSAL` note is the host telling you the answer is not what it appears to be — a
0-row result with a warning is a broken realm, not an empty source.

### The battery: `tests/verify.sh`

Every realm ships one. The contract is small so that any host, CI job or reviewer can run any
realm's battery the same way:

- **Inputs:** `APPLIANCE` (the host's URL) and `AUTH` (`user:pass`) or `TOKEN`. Source keys come from
  environment variables the script's header names. Keep credentials off the command line.
- **L1 — every view answers by name on its defaults.** Not "no error": rows, or a stated empty. A
  view nobody has run is a view that does not work.
- **L2 — ground truth from the source.** Read the counts and figures directly from the source's own
  API and require the realm's to be EQUAL. A count off by one is a bug; a sum off by anything is a
  money bug. Include one non-zero cross-realm count for every spine you key.
- **L3 — cost.** Every pushdown you declared is checked: a single-entity read makes O(1) source calls,
  a filtered count is one call, a one-day window is one page. Read `apiCalls` from a query result
  and `metrics.externalCalls` from a view result. Run L3 on a cold cache (the edge directive
  `{ai: {fresh: true}}`, or before anything sweeps the book): a read the cache answered costs 0 calls
  and proves nothing about the request. A bound that fails means a filter was not sent.
- **Output:** one line per check; on success the LAST line is exactly `ALL CHECKS PASS`; any failure
  exits non-zero.

Write the expected numbers before running the checks, and break one input once to watch the
battery fail. Put the L3 calls before and after in the PR as a table:

| Question | Source calls before | After |
|---|---|---|
| one customer by its id | every page of the customer list | 1 |
| a count on one plan | every page of the subscriptions | 1 (the source's total) |
| invoices issued on one day | every page of the invoices | 1 |

### If anyone types WORDS at your realm, ship `tests/questions.yml`

Running every view proves the realm answers when called BY NAME. It says nothing about the form
most users actually meet it in — a question in their own words. Those are different code paths:
a realm whose every view returns rows while its natural-language questions return zero, or
answer confidently from the wrong join, is not done.

**Judgment call, one hard trigger.** A realm that is verbs, handlers or enrichment — called by
code, never typed at — needs no battery. The moment any surface takes words from a person it is
REQUIRED: an `apps/` page with a free-text ask, a `skills/`/`focuses/`/chat surface, views meant
to be reached by asking rather than by name, or a user who says they want to ask this realm
questions. **If you cannot tell, ask the user** — "will people type questions at this, or only
call it?" — rather than guessing.

Two halves, and the second is the one that finds fabrication:

1. **What it CAN answer.** One entry per question a person would really type. Reconcile figures
   with `matchesView: {name, column}` — the ask's number must equal the named view's, so the
   realm checks itself and the test survives data changes. `nonEmpty` is a floor, not an
   assertion: it once passed 72 rows of unrelated config as an answer to "how many places am I
   watching".
2. **What it CANNOT.** Questions whose answer the sources do not carry — a measure nobody
   publishes, the wrong granularity, a population the data never describes. Ask each one
   SEVERAL times: generation is stochastic, a fabrication that shows one run in five is still a
   fabrication, and one green run proves almost nothing. Check every response mechanically
   against `GET /api/v1/admin/kg/schema` — a property no label declares, or an answer column
   claiming a word the query never selects, is a fabrication and fails the run. Reading the
   queries by eye does not work; the failure mode is a query that looks entirely reasonable.

Every question that ever disappointed a user becomes a permanent entry. When the battery fails,
fix the REALM first — a missing view, a description that does not carry the asking vocabulary, a
`types/` `examples:` steer for a path the generator keeps missing — before blaming the model.

### If your realm ships an `agents/` colleague, test it AS the agent

Running the views and the queries YOURSELF proves the realm. It proves nothing about the agent,
and the two are different tests. What you reach has every tool the host offers; what the agent
reaches is narrowed twice before it gets there — by its focus, and by the categories its
`conversation.builtins` names — and then by which realms its binding admits. A realm whose every
view and query answers perfectly, fronted by an agent that cannot reach them, is not done. **A
realm-level check never counts as an agent-level check**, however thorough it was.

**The trigger is having one.** Ship `agents/*.yml` with a `conversation:` block and this is
REQUIRED, not a judgment call. The whole point of a focused colleague is that it uses the tools
and views of its realm; that is the behaviour under test, so it is the behaviour you have to see.

**Scope it narrowly before you test anything.** An agent is only as reliable as the set of tools it
chooses from. Give it `builtins: [memory, views]` and add a category only when a question it must
answer cannot be answered without it. Then read the surface a turn was actually offered — the host
reports it — and treat every tool outside the agent's job as a defect to remove before you judge
its answers: an agent that reaches for the wrong tool is usually an agent that was handed it. Do
not fix a misbehaving agent by giving it a bigger model. Fix what it is given — fewer tools, views
that cannot return a plausible wrong answer, exact call shapes in its persona — and test again on
the same model.

If the agent needs one skill that its categories leave out, name that skill in
`conversation.skills` instead of widening `builtins`: a category brings every tool in it, and a
name brings one skill. A realm's skills still come only with the realm, through `realms`.

What a view returns when a parameter is missing matters here too. A default that is a real value —
a fixed date, an example verse — answers a careless call with something plausible and wrong (the
Rosary for a Thursday, on a Sunday). For anything an agent reads, a missing parameter should return
nothing, or mean "today", never a sample.

1. **Ask the agent, as the agent.** `/talk <name>`, then the same two halves as
   `tests/questions.yml` — what it can answer, and what it cannot. Asking the world instead, or
   asking over a developer door, tests a different surface and will pass while the agent is
   broken.
2. **Require the TOOL CALL, not a plausible paragraph.** The answer has to be traceable to a view
   it ran or a query it issued. An agent answering from the model's own recall reads exactly like
   an agent answering from your realm, right up to the first figure that is wrong — so check what
   it called, not how the prose sounds. Hosts report the tool surface a conversation was given and
   the calls a turn made; read both.
3. **Every category you name is a claim to check.** `builtins: [views, graph, code]` promises
   running a view, querying the graph, and running code against that agent's own focus. Verify
   each one survives, by asking something that can only be answered that way. A capability can be
   present under one name and absent under another — the code runner a chat model calls is not
   spelled the way a developer door spells it — so confirm the capability, never the name.
4. **"The system had trouble finding…" is a FAILURE.** So is hedging, apologising, or offering to
   look somewhere else, when a view in the agent's own realm answers the question outright. Treat
   it as the realm's bug — a view it was never given, a description that does not carry the asking
   vocabulary, a category it does not name — and fix it there.
5. **Test the version that is in force.** A signed agent runs as SIGNED, persona included. Edit
   its definition or its persona and the change waits for a signature, so the agent answering you
   is the old one. Check for unsigned changes before you conclude anything, and sign first if you
   meant the edit to be live.

Something answerable only by the agent's own realm, asked in words a person would really use, is
the shape that finds this: a question needing two of the realm's facts joined, where recall gives
a confident near-miss. "Which verses mention both Jesus and Moses" over a scripture realm found
exactly that — the realm answered it in under a second from a declared join, while the agent in
front of it said the search had trouble and suggested they were in separate chapters. Nineteen
verses say otherwise.

### Cost declarations: `maxAnchors` is about the SOURCE, not the number

`maxAnchors` bounds how many distinct keys one fetch may ask its source for — a thousand anchors
sharing three keys spend three. Its default assumes a **per-key** source, where every key is
another API call. A source that answers the whole key set in one
statement (a database, a triplestore, a file) is nearly free per anchor, and the host now defaults
those far higher — so declare `maxAnchors` only when you know something the kind does not imply: a
metered API to protect (go lower), or a batch op behind a `remote` producer (go higher).

And shape the view so the cap rarely matters: **narrow before an enrichment hop.** Sort and `LIMIT`
the rows you will show, *then* resolve their names — not the other way round.

### What you DECLARE decides what the engine may do

Pushdown, a second door, aggregates and the shape of your views change the shape of every query
over the realm. None is an optimisation you can add later without changing what a question costs.
The method and the patterns are in [Pushdown first](#pushdown-first--before-you-write-a-producer);
the points below are about doors and views.

**1. Every filter the source accepts is declared** (see Pushdown first). A mined realm already has
the list: the scaffold writes `sourceFilters:` onto each producer, the parameters its specification
said it accepts. That is your checklist, and loading the realm names the ones you left.

**2. Declare a SECOND DOOR where your source offers one.** A join is one call per anchor, and the
anchor cap counts anchors rather than records — so pushing a predicate on the target makes each call
cheaper and leaves the number of calls untouched. What changes it is another way in:

```yaml
virtualJoins:
  - { anchorLabel: CustomerAccount, relationship: HAS_CASE, keyField: accountKey, … }   # one per account
  - { anchorLabel: ChatwootDesk,    relationship: HAS_CASE, keyField: status,     … }   # one for the desk
```

A query pinning `c.status` has bound the second door's key already. Pin it with `{via:'…'}`; where
the host enables access-path rewriting the engine may pick it, and will decline where the answer
would differ (an `OPTIONAL` hop, an aggregate over the anchor, an unapplied second predicate).

**3. Declare what your source can count (`aggregates:`).** A query that only counts then costs one
call instead of one per anchor. See the spec for the fields and why each is required.

**4. Write HOW MANY and WHICH as two views.**

`collect(c.subject)` needs the records whatever else the query asks. So a view that both counts and
collects always pays the collecting price — including when the question was triage across the whole
book and nobody was going to read a subject.

```yaml
# Triage across every account — the source can answer this.
- name: HealthOpenCaseCountsByAccount
  cypher: |
    MATCH (a:CustomerAccount)-[:HAS_CASE]->(c:SupportCase)
    WHERE c.status IN ['open', 'pending']
    RETURN a.accountKey AS accountKey, count(c) AS openCases

# The detail pane, for the handful of accounts it is showing.
- name: HealthOpenCasesByAccount
  cypher: |
    MATCH (a:CustomerAccount)-[:HAS_CASE]->(c:SupportCase)
    WHERE c.status IN ['open', 'pending']
    RETURN a.accountKey AS accountKey, collect(c.subject) AS subjects
```

Say so in the descriptions — the counts view should point at the detail one, and the detail one
should say to ask it about named accounts rather than the whole book.

The same applies to projecting the target bare: `RETURN c.subject, count(c)` needs the rows, so the
count cannot be pushed. If you want both, that is two views.

**What blocks a pushed aggregate, in the order the engine checks it:** `count(*)` (it folds rows of
the whole pattern, which no single source can answer); any `collect` over the target; the target
projected outside an aggregate; a predicate on the target the source does not absorb. `count`,
`sum`, `min` and `max` are delivered, each through its own declared aggregate, and the engine pushes
only when EVERY measure in the query is declared — so a view mixing `count` with an undeclared `max`
reads the records.

## Hard rules (don't get these wrong)

- Credentials stay in host-managed, owner-scoped storage. Governed guests use approved
  operations and sources; they receive no secrets or general credential lookup. Ambient
  environment variables do not authorize credential use for a captured realm; only a
  conventional realm in the local or first-party tier may resolve `token-env` from the
  environment.
- **A captured realm declares credentials; a conventional realm declares `keys.yml` entries.**
  Both work. New realms should be captured and declare credentials the owner binds. `token-env`
  is deprecated in favour of either. A captured API operation is pinned to the value it was
  approved with, so changing a key that a key entry and a captured realm share means approving
  that operation again.
- **Descriptions are for an LLM planner** — write them as routing signal, not prose.
- **Stable ids.** Renaming a `name` (realm/action/type/command) breaks every installed
  world wired to it — that's a major version bump.
- **`prompts/` is a tax on every turn** — keep it a one-line pointer; put real workflow
  guidance in a `skills/` SKILL.md (paid only when activated).
- **Naming**: lowercase-hyphenated ids, UpperCamelCase type names.
- **Every id has a name beside it.** A property that points at another record (`stage_id`,
  `user_id`, a partner key) ships with that record's readable name (`stageName`, `ownerName`),
  or the edge to it. A model given only the id answers with the id. Check every type: no
  reference without its name, and no name that comes back null on live data.
- **Money twice: minor and major units, plus currency.** `amountCents` goes out with `amount`
  and `currency`, each declaring `unit:` and `currency:` as fields, not only in the description. Without that pair, models divide by 100
  twice or not at all. See `DECLARING_TYPES.md` §3.3.
- **An identity is a spine; a record is a parent label.** Never `parents:` a spine; never
  normalize a shared key on your own side; always assert a non-zero cross-realm count in
  `tests/verify.sh`. A broken cross-realm join is an empty result, not an error.
- **Pushdown is designed first, from the source's documentation.** Every verified filter is a rule
  with an explicit `op`, paging is at the source's maximum, single records are read by key, keys are
  batched, and every remote producer declares a cache with `negativeTtlSeconds`. See
  [Pushdown first](#pushdown-first--before-you-write-a-producer).
- **A count is declared only where the source's total honours the filters.** A cached or
  filter-blind total is a confident wrong number; a widened match (`match: ci`, wildcards) never
  feeds one.
- **`values:` is a contract, and money is never summed across currencies.** A query outside the
  list is refused; a money view returns one row per currency.
- **`requires:` every realm whose labels you read**, or the realm goes degraded where it is missing.
- **Validate with `--strict` and audit before you install.** See [Before you install](#before-you-install).
- **How many and which are two views.** One view that counts AND `collect`s always pays the
  collecting price, so triage over the whole book costs what the detail pane costs.
- **An untested view is an unshipped view.** Declarative capabilities are only proven by a live
  run against the real source — see "The declarative half has no unit tests".
- **A realm people ask in words ships `tests/questions.yml`.** Views passing by name proves a
  different code path from the one users meet. Include the adversarial half — what the realm
  cannot answer, asked repeatedly — because that is where a generator invents.

## Channel sources and consumers

Declare sources and consumers in `data-pipes.yml` using the
[hosted data-pipe contract](https://github.com/embabel-worlds/realm-spec/blob/main/HOSTED_EXECUTION.md#data-pipes). A source names its stream
and event type. A consumer names a captured handler; the owner separately approves its exact
source and handler. A declaration creates no grant. In a TypeScript realm, write them as
`dataPipes` in `realm.ts`, and declare channel-fed sources and consumers with `connecting`; see
[sources, consumers and triggers](https://github.com/embabel-worlds/realm-spec/blob/main/TYPESCRIPT_REALMS.md#sources-consumers-and-triggers).

Use `gateway.channel.publish` in a captured Docker handler or `ctx.gateway.channel.publish`
in a Wasm handler. Keep `streamId`, `eventId` and payload stable on retry. The journal matches a retry on those,
so a retry that stamps a new `occurredAt` still gets the first receipt and keeps the first time.
Receipt and tombstone retention windows are bounded: a retry within them returns
its receipt or original offsets, while a retry outside them can append again and consume
quota. The returned receipt confirms durable acceptance; downstream effects still require
idempotency. All retained data and dependencies remain within host-enforced Realm limits.
Private SQLite is a dependency, not an external SQL gateway or a substitute for source
approval.

## Captured realms: producers, graph reads, apps and proposals

A captured realm runs from a copy the owner admitted, and every capability is its own owner
approval. Write `realm.ts`, importing definition fragments as needed;
[TypeScript realms](https://github.com/embabel-worlds/realm-spec/blob/main/TYPESCRIPT_REALMS.md) is the full contract, with the owner's approval
steps at the end. Use `defineRealm` in place of `satisfies Realm`: under it, a goal, producer,
lens, channel or consumer naming a handler the realm does not declare is a compile error. The host
refuses an undeclared handler everywhere a realm names one: a goal, producer, `dataPipes`
consumer, app, lens, channel or consumer. A realm with no `handlers` block declares none, so
every handler name in it is refused. An undeclared goal `input` or `output` type is a warning,
since another realm may declare it; if nothing does, the host drops the goal.

Validate with the host's published profile. The reference captured profile does not execute
conventional `actions`, `events` or `webhooks`, and refuses `layers`.

**A captured producer is a handler.** No `kind`, no `operation`, no `args`, no `cache`:

```ts
producers: {
  "incidents-by-service": {
    handler: "oncall.incidents",
    keyArgument: "serviceIds",
    joins: [{ targetLabel: "Incident", anchorLabel: "Service", relationship: "HAS_INCIDENT",
              keyField: "serviceId", recordKeyField: "serviceId" }],
    page: { argument: "cursor", maxPages: 4 },
    pushdown: [
      { property: "impact", argument: "impact" },
      { property: "status", argument: "status" },
      { property: "component", argument: "component" },
    ],
  },
},
```

- The handler gets the keys as a list under `keyArgument` and returns records that carry their
  key under `recordKeyField`. With `page`, it returns `{ rows, next }` and gets `next` back under
  the page argument on the following call, up to `maxPages` (1 to 16). `next: null` stops it.
- **Cover EVERY filter the source can apply with a `pushdown` rule.** The handler gets the values
  an `=` or `IN` allows as a list of strings under the rule's argument, on every page. A filter you
  leave out makes the handler fetch everything the key allows, and the answer comes out the same,
  so nothing tells you. Read the source's own parameter list and map each one. Where the host shows a
  query's `apiCallLog`, it names the arguments that reached the handler, so a filter missing
  there is the next rule to write.
- Only `=` and `IN` push. `>`, `CONTAINS` and a function over the value are applied by the graph
  after the fetch. Say so in the target type's description, so nobody assumes they are cheap.
- If the handler's input schema has `additionalProperties: false`, list the page and pushdown
  arguments in `properties`, or the host refuses the producer at bind time. List them in
  `properties` anyway: the SDK's inferred input type only has the fields the schema declares.
- A query reaches the target only along a join from a bound anchor. `MATCH (i:Incident)` on its
  own is refused; `MATCH (s:Service {serviceId: $id})-[:HAS_INCIDENT]->(i)` works. One
  producer's target can anchor the next producer's join, so chain them where a source is keyed
  on another source's records.
- Limits per fetch: 256 keys, 1 MiB of output, 1,024 rows across all pages. No result cache.

**Graph reads are `ctx.gateway.cypher.query`, under their own approval.** The SDK's inferred types
type API and GraphQL namespaces and `ctx.gateway.channel`, and leave `ctx.gateway.cypher` as
`unknown`, so give it a type in the handler:

```ts
type CypherGateway = {
  cypher: {
    query(request: { cypher: string; params?: Record<string, unknown> }): Promise<{
      rows: Record<string, unknown>[];
    }>;
  };
};

const { rows } = await (ctx.gateway as unknown as CypherGateway).cypher.query({
  cypher: "MATCH (s:Service)-[:HAS_INCIDENT]->(i:Incident) WHERE s.team = $team " +
          "RETURN s.name AS service, i.incidentId AS incident LIMIT 100",
  params: { team: input.team },
});
```

- End with a literal `LIMIT` from 1 to 512, name and label every node, and pass every value
  through `params`.
- It sees only what the owner owns outright. Variable-length paths, named paths, list
  comprehensions, procedures and most functions are refused, and every refusal is the same
  message, so keep queries plain.
- Read the owner's own views through `queries: { views: [{ alias, view }] }`; each alias is its
  own approval.

**Browser apps run sandboxed with no network.**

- Declare each page under `apps` with the handlers it may call; the host refuses a handler the
  realm does not declare. The page reaches the realm only through `realm.call(handler, args)`.
- **One `realm.call` at a time.** A second call while one is waiting rejects at once, so `await`
  each call before the next. Every refusal rejects with the same message; show one plain error.
- No `fetch`, sockets, remote scripts, styles, images or fonts. Bundle everything; declare CSS
  and JS under `resources` (`apps/<page>.assets/`) and embed images and fonts as `data:` URLs.
- The host operator sets the size limits. The defaults are 10 MiB for the page, 16 resources,
  and 10 MiB for one resource and for all of them together, and the host refuses an app past them.
  Use the target host's published limits for authoring checks.
  Otherwise stay well under them.

**Write through a proposal, never directly.** `ctx.writePropose({ version: 1, kind, target,
fields, effect, method? })` files a write for the owner to accept and resolves to `{ proposalId }`.
The handler never learns the outcome. The target must be one private record the owner already
has, under a label the operator opened to proposals. Accepting applies flat scalar `fields` with
`effect: "private-storage"` only. Keep a proposal small and name exactly the record it changes.


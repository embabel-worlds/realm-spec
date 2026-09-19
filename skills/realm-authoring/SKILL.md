---
name: realm-authoring
description: Author or extend an Embabel realm — a git repo of declarative capabilities (actions, types, APIs, virtual-join producers/RemoteRepositories, MCP servers, commands, webhooks, event sources, event handlers, skills, personalities, apps) that a host installs into a world. Activate for any request to create/build/scaffold/extend a realm, add a capability to a realm (a new action, type, API, producer, virtual join, verb, webhook, event source, event handler/reaction, skill, command), wire a new integration as a realm, or understand the realm format. The full contract is the spec at the repo root (README.md) — this skill is the map; read the named section before writing a file.
---

# Authoring an Embabel realm

A realm is a **git repo** named `realm-*` containing only declarative files (YAML) and
optional hand-authored TypeScript handlers — **no JVM bytecode, no host config, no user
credentials**. The host clones it into a world and wires its contents in. The
authoritative contract is `README.md` (the spec) in this repo; this skill routes you to
the right section and flags the easy mistakes.

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
- `wasm/handlers.ts` is where TypeScript goes. Not `handlers/` (that is YAML trigger
  bindings), not `src/api/*.ts` (that is the checkout build, which this path does not run).
- **`realm_install` consumes the draft.** After a successful install the next
  `realm_write` starts a NEW empty draft — so a follow-up write, on its own, produces
  "realm.yml is missing" for a file you wrote minutes ago. Re-write the whole realm, or
  edit on a checkout instead.

`realm_brief` tells you which path this appliance is on; it says so explicitly when no
checkout is mounted.

## Second decision: declarative or handlers?

- **Start declarative.** If a YAML capability (an `actions/` step, a `types/` type, an
  `apis/` OpenAPI entry, a `producers/` virtual join) expresses it, use that — no build
  step, the host's planner reasons over it directly.
- **Reach for `src/` TypeScript handlers** only when there are invariants YAML can't hold:
  revision/optimistic-lock guards, multi-call orchestration, shaping a rich API into
  idiomatic methods, or giving a type *behaviour* (verbs). Handlers and YAML mix freely.

## The pieces (read the spec section before writing one)

| Want to… | Directory | Spec section |
|---|---|---|
| metadata | `realm.yml` | "`realm.yml`" |
| an LLM step the planner chains | `actions/` (`stepType: action`) | "`actions/`" |
| a deterministic rule over a signal | `actions/` (FQN `PolicyActionSpec`) | "Deterministic rules" |
| a domain / signal / mirror type | `types/` | "`types/`" |
| call an external REST/GraphQL API | `apis/` (+ vendored spec) | "`apis/`" (auth, OAuth2) |
| a shared IDENTITY other realms attach to (an account, a product, a site) | `types/` `spine:` | Virtual Cypher §5.4.1 — see "Joining OTHER realms" below |
| attach your records to a spine (yours, another realm's, or Person/Organization) | `types/` `hub:` on the property carrying the key | Virtual Cypher §5.4 |
| a shared KIND of record (every ticket is a `SupportCase`) | `types/` `parents:` | LABELS_AND_COMPOSITION.md |
| fetch a type **on demand** by traversal | `types/` `virtualJoins:` + `producers/` | "Joining types on demand" (Virtual Cypher) |
| a named, parameterized ANSWER a caller runs by name | `views/` | "Views" — the realm's answer surface: ship one per question the realm exists to answer, so nobody hand-writes Cypher over your join surface |
| query the graph from a code_mode script or skill | `gateway.kg.query` | "CypherScript" |
| query the graph from a WASM HANDLER | `ctx.cypher.query` — see the warning under CypherScript | "CypherScript" |
| hand-authored gateway methods / **verbs** | `src/api/*.ts` + `tests/` | "`src/` and `tests/`" |
| prove the answer surface survives the author | `tests/questions.yml` + `tests/verify.sh` | "`tests/`" — REQUIRED once anything takes words from a person |
| an MCP server (last resort — prefer `apis/` for anything API-backed) | `mcp/` | "`mcp/`" |
| a slash command | `commands/` | "`commands/`" |
| inbound events → typed `Signal`s | `events/` (webhook + poll) | "`events/`" |
| WHICH signal/cron invokes a verb (declarative YAML) | `handlers/` | "`handlers/`" |
| the TypeScript a wasm-host realm actually runs | `wasm/handlers.ts` (ONE file) | "`wasm/`" |
| scheduled KG enrichment | `decorations/` | "`decorations/`" |
| an HTML app | `apps/` | "`apps/`" |
| tips the host UIs show this realm's users | `hints/` | "`hints/`" — hand-authored; teach the answer surface you shipped |
| on-demand LLM guidance | `skills/<name>/SKILL.md` | "`skills/`" |
| a voice/persona | `personalities/` | "`personalities/`" |
| a scoped chat surface | `focuses/` | "`focuses/`" |

## Virtual joins + RemoteRepositories (the on-demand path)

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
  source's native filter (`{filters}` in `args`) so the fetch is scoped at the source —
  not fetched broadly and filtered in the graph.
- **Pagination** (`paging:`): walk pages so a fetch exceeding one page is fully captured.
- A literal-pinned anchor (`{login:'x'}` or `WHERE a.login='x'`) uses the real node if it
  exists, else seeds a named entity even when no such node exists, fetched with the
  connecting user's credentials.
- **LLM query primitives (the `ai` namespace)** work over any virtual collection your producer fetches —
  you declare nothing. A query author can `WHERE ai.relevant(n, '<subjective criterion>')`
  (filter), `ORDER BY ai.score(n, '<criterion>') DESC` (rerank), or steer a *generative*
  producer with an `{ai: {hint: '…'}}` edge directive map. The `ai` namespace is **reserved** — never name a
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

> **A WASM handler is not a `code_mode` script, and this section's `gateway.*` examples do not
> run there.** A handler in `wasm/handlers.ts` is `export function name(args, ctx)` — args
> FIRST, and the surface is `ctx.gateway`. There is no global `gateway`: writing the code below
> verbatim inside a handler fails at the first call with `gateway is not defined`. The host tools
> granted inside wasm are `cypher_query`, `sql_query` and `sql_update` — `gateway.kg.query` is
> NOT one of them, so a handler reads the graph with `ctx.gateway.cypher.query`. An evaluation
> followed this section literally, got `gateway is not defined`, and recovered the real signature
> only by disassembling the sandbox shim.
>
> Note the sharp edge while it lasts: `cypher_query` takes no `params`, so a handler cannot yet
> bind a user-supplied value into a graph read. Filter in JS over a bounded read rather than
> concatenating a value into the Cypher string.

A handler / decoration / skill runs **CypherScript** in `code_mode`: TS/JS that interleaves
`await gateway.kg.query({cypher, params})` (graph reads through Virtual Cypher — scoped,
read-only, virtual joins materialize) with plain JS, `gateway.<ns>.*` integration calls, and
`gateway.ai.*` inline LLM, in one program. Full detail in "CypherScript — Cypher woven into
TypeScript/JavaScript".

## Verbs (behaviour on a type)

Export `class X extends Entity` in `src/api/x.ts`; its async methods are callable on an
in-scope instance — including ones materialized by a virtual join. **Pure** verbs compute
over fields; **effectful** verbs write back through `this.gateway.<ns>.*`. See "Type methods"
and "Verbs on virtual types".

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

### Cost declarations: `maxAnchors` is about the SOURCE, not the number

`maxAnchors` bounds how many nodes may drive one fetch. Its default assumes a **per-anchor**
source, where every anchor is another API call. A source that answers the whole key set in one
statement (a database, a triplestore, a file) is nearly free per anchor, and the host now defaults
those far higher — so declare `maxAnchors` only when you know something the kind does not imply: a
metered API to protect (go lower), or a batch op behind a `remote` producer (go higher).

And shape the view so the cap rarely matters: **narrow before an enrichment hop.** Sort and `LIMIT`
the rows you will show, *then* resolve their names — not the other way round.

### What you DECLARE decides what the engine may do

Three declarations cost a few lines each and change the shape of every query over your realm. None
of them is an optimisation you can add later without changing answers — they are what makes the
difference between one call and one call *per account*.

**1. Declare the filters your source can apply (`pushdown:`).** Without one, a `WHERE` on your
target is applied to the graph AFTER every record has been fetched. With one, the source scopes the
fetch.

That is the small win. The large one: what your source absorbs is what lets the engine push a
`LIMIT` (stop the page walk) and ask for a `count()` instead of the records. Neither is safe while
the graph still has filtering left to do, so **an undeclared filter costs far more than its own
page**.

If your source's query is text, use `qualifier`. If it is JSON — an Odoo domain, an Elasticsearch
`bool.filter`, a Chatwoot filter payload — use `argPath` + `clause`:

```yaml
pushdown:
  - property: status
    op: IN
    argPath: payload.-            # `-` APPENDS to the list there
    clause:
      attribute_key: status
      filter_operator: equal_to
      values: "{values}"          # a node that IS "{values}" becomes the member LIST
    linkPrevious: { query_operator: AND }   # only if the source links to the PRECEDING element
```

`linkPrevious` exists for sources that spell conjunction as a field on the previous clause, and
where that field must be absent from the last one — Chatwoot is the example. It is written at
append time, which is the only moment the engine knows which element stopped being last.

**Verify pushdown against the live source.** The shapes are unforgiving and the failures are not
subtle: Chatwoot answers HTTP 500 to a payload missing `query_operator`, and rejects one that
carries it on the final clause. A rule that renders nothing is correctly reported as absorbing
nothing, so a wrong rule is slow rather than incorrect — but slow is what you were fixing.

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
projected outside an aggregate; a predicate on the target the source does not absorb. Today `count`
is delivered; `sum`/`min`/`max` are recognised and left graph-side, and the engine pushes only when
EVERY measure in the query is deliverable — so a counts view mixing `count` with `max` does not yet
push.

## Hard rules (don't get these wrong)

- **No secrets in the realm.** Reference them by env-var/credential-store name; OAuth client
  creds live in the host admin, never the repo.
- **Descriptions are for an LLM planner** — write them as routing signal, not prose.
- **Stable ids.** Renaming a `name` (realm/action/type/command) breaks every installed
  world wired to it — that's a major version bump.
- **`prompts/` is a tax on every turn** — keep it a one-line pointer; put real workflow
  guidance in a `skills/` SKILL.md (paid only when activated).
- **Naming**: lowercase-hyphenated ids, UpperCamelCase type names.
- **An identity is a spine; a record is a parent label.** Never `parents:` a spine; never
  normalize a shared key on your own side; always assert a non-zero cross-realm count in
  `tests/verify.sh`. A broken cross-realm join is an empty result, not an error.
- **An undeclared filter is a per-anchor fetch.** If your source can filter, say so with
  `pushdown:` — and verify it against the live source, because a rule that renders nothing is
  silently just slow. See "What you DECLARE decides what the engine may do".
- **How many and which are two views.** One view that counts AND `collect`s always pays the
  collecting price, so triage over the whole book costs what the detail pane costs.
- **An untested view is an unshipped view.** Declarative capabilities are only proven by a live
  run against the real source — see "The declarative half has no unit tests".
- **A realm people ask in words ships `tests/questions.yml`.** Views passing by name proves a
  different code path from the one users meet. Include the adversarial half — what the realm
  cannot answer, asked repeatedly — because that is where a generator invents.

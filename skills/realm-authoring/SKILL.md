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
| fetch a type **on demand** by traversal | `types/` `virtualJoins:` + `producers/` | "Joining types on demand" (Virtual Cypher) |
| a named, parameterized ANSWER a caller runs by name | `views/` | "Views" — the realm's answer surface: ship one per question the realm exists to answer, so nobody hand-writes Cypher over your join surface |
| query the graph from realm code (TS+Cypher) | `gateway.kg.query` in a handler/skill | "CypherScript" |
| hand-authored gateway methods / **verbs** | `src/api/*.ts` + `tests/` | "`src/` and `tests/`" |
| an MCP server (last resort — prefer `apis/` for anything API-backed) | `mcp/` | "`mcp/`" |
| a slash command | `commands/` | "`commands/`" |
| inbound events → typed `Signal`s | `events/` (webhook + poll) | "`events/`" |
| WHICH signal/cron invokes a verb (declarative YAML) | `handlers/` | "`handlers/`" |
| the TypeScript a wasm-host realm actually runs | `wasm/handlers.ts` (ONE file) | "`wasm/`" |
| scheduled KG enrichment | `decorations/` | "`decorations/`" |
| an HTML app | `apps/` | "`apps/`" |
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

## CypherScript (querying the graph from realm code)

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

### Cost declarations: `maxAnchors` is about the SOURCE, not the number

`maxAnchors` bounds how many nodes may drive one fetch. Its default assumes a **per-anchor**
source, where every anchor is another API call. A source that answers the whole key set in one
statement (a database, a triplestore, a file) is nearly free per anchor, and the host now defaults
those far higher — so declare `maxAnchors` only when you know something the kind does not imply: a
metered API to protect (go lower), or a batch op behind a `remote` producer (go higher).

And shape the view so the cap rarely matters: **narrow before an enrichment hop.** Sort and `LIMIT`
the rows you will show, *then* resolve their names — not the other way round.

## Hard rules (don't get these wrong)

- **No secrets in the realm.** Reference them by env-var/credential-store name; OAuth client
  creds live in the host admin, never the repo.
- **Descriptions are for an LLM planner** — write them as routing signal, not prose.
- **Stable ids.** Renaming a `name` (realm/action/type/command) breaks every installed
  world wired to it — that's a major version bump.
- **`prompts/` is a tax on every turn** — keep it a one-line pointer; put real workflow
  guidance in a `skills/` SKILL.md (paid only when activated).
- **Naming**: lowercase-hyphenated ids, UpperCamelCase type names.
- **An untested view is an unshipped view.** Declarative capabilities are only proven by a live
  run against the real source — see "The declarative half has no unit tests".

---
name: pack-authoring
description: Author or extend an Embabel pack — a git repo of declarative capabilities (actions, types, APIs, virtual-join producers/RemoteRepositories, MCP servers, commands, webhooks, event sources, event handlers, skills, personalities, apps) that a host installs into a workspace. Activate for any request to create/build/scaffold/extend a pack, add a capability to a pack (a new action, type, API, producer, virtual join, verb, webhook, event source, event handler/reaction, skill, command), wire a new integration as a pack, or understand the pack format. The full contract is the spec at the repo root (README.md) — this skill is the map; read the named section before writing a file.
---

# Authoring an Embabel pack

A pack is a **git repo** named `pack-*` containing only declarative files (YAML) and
optional hand-authored TypeScript handlers — **no JVM bytecode, no host config, no user
credentials**. The host clones it into a workspace and wires its contents in. The
authoritative contract is `README.md` (the spec) in this repo; this skill routes you to
the right section and flags the easy mistakes.

## First decision: declarative or handlers?

- **Start declarative.** If a YAML capability (an `actions/` step, a `types/` type, an
  `apis/` OpenAPI entry, a `producers/` virtual join) expresses it, use that — no build
  step, the host's planner reasons over it directly.
- **Reach for `src/` TypeScript handlers** only when there are invariants YAML can't hold:
  revision/optimistic-lock guards, multi-call orchestration, shaping a rich API into
  idiomatic methods, or giving a type *behaviour* (verbs). Handlers and YAML mix freely.

## The pieces (read the spec section before writing one)

| Want to… | Directory | Spec section |
|---|---|---|
| metadata | `pack.yml` | "`pack.yml`" |
| an LLM step the planner chains | `actions/` (`stepType: action`) | "`actions/`" |
| a deterministic rule over a signal | `actions/` (FQN `PolicyActionSpec`) | "Deterministic rules" |
| a domain / signal / mirror type | `types/` | "`types/`" |
| call an external REST/GraphQL API | `apis/` (+ vendored spec) | "`apis/`" (auth, OAuth2) |
| fetch a type **on demand** by traversal | `types/` `virtualJoins:` + `producers/` | "Joining types on demand" (Virtual Cypher) |
| query the graph from pack code (TS+Cypher) | `gateway.kg.query` in a handler/skill | "CypherScript" |
| hand-authored gateway methods / **verbs** | `src/api/*.ts` + `tests/` | "`src/` and `tests/`" |
| an MCP server | `mcp/` | "`mcp/`" |
| a slash command | `commands/` | "`commands/`" |
| inbound events → typed `Signal`s | `events/` (webhook + poll) | "`events/`" |
| a TS reaction to a signal/cron the user activates | `handlers/` | "`handlers/`" |
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

## CypherScript (querying the graph from pack code)

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
npm install && npm run typecheck && npm test && npm run build   # only if the pack has src/
```

- `@embabel/runtime-types` gives `Entity`, `mockGateway`, `entityForTest`, `hydrate*`, and
  `embabel-build-manifest` (writes `dist/manifest.json`). Tests run hermetically in Node.
- The host runs `npm install && npm run build` at install; `dist/` (incl. a vendored
  runtime-types) is the shippable bundle. `embabel-pack sync` regenerates `.embabel/gateway.d.ts`.

## Hard rules (don't get these wrong)

- **No secrets in the pack.** Reference them by env-var/credential-store name; OAuth client
  creds live in the host admin, never the repo.
- **Descriptions are for an LLM planner** — write them as routing signal, not prose.
- **Stable ids.** Renaming a `name` (pack/action/type/command) breaks every installed
  workspace wired to it — that's a major version bump.
- **`prompts/` is a tax on every turn** — keep it a one-line pointer; put real workflow
  guidance in a `skills/` SKILL.md (paid only when activated).
- **Naming**: lowercase-hyphenated ids, UpperCamelCase type names.

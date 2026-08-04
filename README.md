# Embabel Realm Specification

Realms are self-contained, declarative bundles of agent capabilities that can be installed into an Embabel-based host. Each realm is a git repository (no JVM bytecode, no native binaries) that provides actions, types, APIs, MCP servers, commands, webhooks, event sources, event handlers, skills, prompts, and apps. The host platform reads the realm and wires its contents into the running agent.

This document is the spec.

> **Status: living draft.** Sections marked _forward-looking_ describe shape that is settled but may still be in implementation across hosts. Everything else describes the format current Embabel hosts already consume.

---

## Repository convention

A realm is a git repo whose name begins with `realm-` (e.g. `realm-github`, `realm-stripe`, `realm-research`). The host installs a realm by cloning it into a world's `realms/` directory.

Realm sources are configured at the host level. A typical host configuration:

```yaml
# host application.yml
embabel:
  directory:
    realm-sources:
      - name: embabel
        type: org
      - name: johnsonr
        type: user
```

Each entry exposes the realms whose name matches `realm-*` from the given GitHub org or user.

## Directory Structure

```
realm-name/
├── realm.yml              # Required: realm metadata
├── actions/              # Action specifications (YAML) — framework + host-extension stepTypes
│   └── my-action.yml
├── goals/                # Goal specifications (YAML)
│   └── my-goal.yml
├── types/                # Dynamic type definitions (YAML)
│   └── my-type.yml
├── producers/            # Virtual-join producers for on-demand types (YAML, optional)
│   └── my-producers.yml
├── reference/            # Reference/catalog data seeded into the KG on load (YAML, optional)
│   └── my-reference.yml
├── views/                # Named Cypher views (YAML, optional) — appear in the console Views list
│   └── my-views.yml
├── lenses/               # Named focused experiences (YAML, optional) — CypherScript/fixed/anchor/module
│   └── my-lens.yml
├── apis/                 # API entries (YAML)
│   └── my-api.yml
├── src/                  # Hand-authored TypeScript handlers (optional)
│   └── api/
│       └── my-handlers.ts
├── tests/                # Vitest specs for handlers
│   └── my-handlers.test.ts
├── mcp/                  # MCP server configurations (YAML)
│   └── my-server.yml
├── commands/             # Slash command mappings (YAML)
│   └── my-command.yml
├── webhooks/             # Webhook registrations (YAML)
│   └── my-webhook.yml
├── events/               # Event ingestion (forward-looking) — push + poll
│   └── my-source.yml
├── handlers/             # Event handlers — TS reactions to signals/cron the user activates
│   └── my-handler.yml
├── decorations/          # Scheduled KG node-decoration manifests
│   └── my-decoration.yml
├── apps/                 # Bundled HTML apps served at /apps/{name}
│   └── my-dashboard.html
├── artifacts.yml         # Custom artifact type registrations (optional)
├── prompts/              # Prompt contributions
│   └── examples.md
├── skills/               # Skills (Agent Skills spec)
│   └── my-skill/
│       └── SKILL.md
├── personalities/        # Voice / behaviour bundles (Jinja templates)
│   └── my-persona/
│       ├── identity.yml
│       └── personality.jinja
└── focuses/              # Named scopings of the chat surface
    └── my-focus.yml
```

All directories are optional. A realm needs only `realm.yml` and at least one capability directory.

## Realm shapes

A realm is a directory of capabilities. *How* those capabilities are
expressed is up to the author — realms span a spectrum from
pure-declarative to handlers-driven:

### Declarative-only (e.g. `realm-github`, `realm-email`)

YAML files describe everything; no code ships. The host parses the
declarations and wires them into the runtime.

- `realm-github`: `types/github.yml`, `events/*.yml`, `actions/*.yml`,
  `apis/apis.yml`, `skills/*/SKILL.md`. The framework's planner
  consumes the action specs; the poll executor consumes the event
  specs; the API allowlist consumes the apis manifest. No
  TypeScript, no `src/`.
- `realm-email`: a pure abstract-concept realm — `types/email.yml`
  declares the universal `email.thread` DomainType, and
  `actions/*.yml` ships the attention-worthiness policies that
  operate on it. Signal *producers* (in-tree Gmail today, future
  realm-exchange / realm-imap) live elsewhere; this realm carries only
  the abstraction and the rules.

### Handlers-driven (e.g. `realm-google`)

When the integration genuinely needs imperative code — guarded
mutations with revision checks, multi-step orchestration of vendor
APIs, custom domain logic — the realm ships TypeScript handlers
alongside the standard YAML.

- `realm-google`: `src/api/docs-editor.ts` implements an editing
  surface for Google Docs (outline / read / find / proposeEdits /
  applyEdits) with revisionId guards the framework can't express
  declaratively. `src/lib/*.ts` carries the supporting logic
  (outline construction, op validation, op translation).
  `src/types/edit-op.ts` declares the TypeScript types the handlers
  trade in. `tests/*.test.ts` are Vitest specs covering each
  handler's contract. `package.json` / `tsconfig.json` /
  `vitest.config.ts` complete the project. The realm also carries
  `apis/` (vendored OpenAPI specs), `skills/` (workflow docs for
  small models), and `prompts/` like any other realm — they aren't
  mutually exclusive.

The host loads the handlers through the framework's TypeScript
runtime; the standard YAML capabilities load the same way they do
for declarative realms. Authors choose freely per file.

### Choosing a shape

- Start declarative. If a YAML `stepType: action` (or any
  host-extension `ActionSpec` referenced by FQN) can express what
  you need, that's the right tool — no build step, no runtime code
  path, the host's planner reasons about it directly.
- Reach for handlers when the operation has invariants the planner
  can't enforce on its own (atomicity, revision guards, ordering
  across multiple vendor calls) or when the vendor's API grammar is
  rich enough that surfacing it as one tool collapses too much.
- A realm can mix freely. `actions/` and `src/` coexist; nothing in
  the spec says "if you ship handlers, ship only handlers."

## `realm.yml`

Required metadata file at the realm root.

```yaml
name: github
description: "GitHub integration — analyze and fix issues"
version: 0.1.0
author: Embabel
url: https://github.com/embabel/realm-github
tags:
  - integrations
  - developer-tools
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Realm name (kebab-case) |
| `description` | No | What the realm does |
| `version` | No | Semver version (default: `0.0.0`) |
| `author` | No | Author or organization name |
| `url` | No | Source repository or documentation URL |
| `tags` | No | Categorization tags |

## `actions/`

Action specifications — YAML files that define executable operations. The host's planner picks them by their declared input / output types and runs them as GOAP actions. The `stepType` discriminator selects the shape; the framework's `NameOrClassTypeIdResolver` resolves either a registered short name (e.g. `action`, `goal`) **or a fully-qualified class name** (`com.example.MyCustomActionSpec`) to an `ActionSpec` class on the classpath. Host extensions can use either path.

| `stepType` value | Shape |
|---|---|
| `action` | Framework `PromptedActionSpec` — typed LLM call producing `outputTypeName` |
| `<FQN>` | Any other `ActionSpec` subtype on the classpath. Use this when shipping a host-extension shape whose YAML contract isn't yet stable enough to claim a short name. |

**Short name vs FQN dispatch.** A short name like `action` is a public contract; once realm authors write it, you can't change the spec's shape without breaking their YAML. Reserve short names only for shapes that have stabilised. FQN dispatch lets a host iterate freely on field names, parsing, and dispatch semantics without committing to a YAML slot upstream.

Example host extension (the assistant's predicate-driven `PolicyActionSpec`):

```yaml
# realm-email/actions/policy_email_unreplied.yml
stepType: com.embabel.assistant.policy.spec.PolicyActionSpec
name: email_unreplied
description: A thread you're a participant in has activity from someone else, ≥ 24h ago
inputTypeNames:
  - email.thread
whenExpr: "$self in participants and last_sender != $self and age >= 24h"
cost: 0.01
value: 1.0
```

The framework's resolver calls `Class.forName(stepType)` and deserializes the rest of the YAML into that class. No `registerSubtypes(...)` call required, no `@JsonTypeName` annotation on the class.

### `stepType: action` — typed LLM call

The framework's general-purpose `PromptedActionSpec`. The LLM produces a typed object the planner can chain into other actions. `nullable: true` declares that the LLM may return null (no output) — the planner sees the missing binding and replans.

```yaml
# actions/triage-issue.yml
stepType: action
name: triage-issue
description: "Triage a GitHub issue"
inputTypeNames:
  - GitHubIssue
outputTypeName: TriagedIssue
prompt: |
  Triage issue #{{gitHubIssue.issue}} in {{gitHubIssue.owner}}/{{gitHubIssue.repo}}.
tools:
  - github
cost: 0.5
value: 1.0
```

Fields: `name`, `description`, `llm` (LlmOptions, optional), `inputTypeNames`, `outputTypeName`, `pre` / `post` (extra preconditions / effects, optional), `cost` / `value` (UtilityAI economics, default 0), `canRerun` (default false), `prompt`, `toolGroups` / `tools` / `references` (optional), `nullable` (default false), `export` (auto-generate a chat-callable goal, default false).

### LLM-judged signals — `stepType: action` producing `AttentionVerdict`

LLM-judged attention rules are vanilla `stepType: action` PromptedActionSpecs whose output is an `AttentionVerdict` (a typed `{reason, confidence, tier}` value) and which declare `nullable: true` so the LLM can return null = "skip". The host provides a generic wrap action that lifts `(AttentionVerdict, Signal)` to `AttentionCandidate`, closing the catchup chain.

```yaml
# realm-email/actions/triage_email_attention.yml
stepType: action
name: triage_email_attention
description: Judge whether an email thread warrants the user's attention

inputTypeNames:
  - email.thread

outputTypeName: AttentionVerdict
nullable: true

prompt: |
  Judge whether the thread is worth {{user}}'s attention.
  Return a verdict if so; return null to skip.

  Thread:
  {{emailThread}}

cost: 0.5
value: 1.0
```

The wrap is a two-step GOAP chain per signal: the PromptedActionSpec emits an `AttentionVerdict`, then the host's wrap action emits the final `AttentionCandidate`. The wrap is keyed off `(AttentionVerdict, Signal)` inputs so it composes generically with *any* LLM-judgment realm — realm-email, realm-slack, realm-calendar, etc. — without needing per-signal-type wrap classes.

### Deterministic rules — host-extension via FQN

The assistant ships an in-tree `PolicyActionSpec` for cheap, no-LLM rules over a single signal — fires when its predicate matches and writes an `AttentionCandidate`. **No `surface:` block** — how the candidate gets rendered into a notification is a downstream concern, not the producer's call.

The YAML uses FQN dispatch (the predicate DSL is still iterating, so we don't reserve a short stepType slot upstream yet):

```yaml
# actions/policy_pr_review_overdue.yml
stepType: com.embabel.assistant.policy.spec.PolicyActionSpec
name: pr_review_overdue
description: A review was requested from you and it's been over 48h

inputTypeNames:
  - github.pr_review_request

whenExpr: "reviewer == $self and age >= 48h"

# Same top-level cost / value as PromptedActionSpec. Cheap predicate:
# low cost, standard value — the planner picks this before any LLM
# judgment on the same signal type.
cost: 0.01
value: 1.0
```

#### `whenExpr` — the predicate DSL

A boolean expression over the matched signal's fields. Parser source: `com.embabel.assistant.policy.PolicyExprParser`. Grammar (today; expect additions as concrete rules need them):

**Operators**, lowest to highest precedence:

| Operator | Meaning |
|---|---|
| `or` | logical OR |
| `and` | logical AND |
| `not` | logical NOT (prefix) |
| `==`, `!=` | equality / inequality |
| `<`, `<=`, `>`, `>=` | numeric or duration comparison |
| `in` | membership in a collection (`field in collection`) |

**Literals:**

| Form | Type |
|---|---|
| `"..."` | string (`\` escapes the next character) |
| `42`, `3.14` | number |
| `true`, `false` | boolean |
| `30s`, `5m`, `48h`, `7d`, `2w` | duration (seconds / minutes / hours / days / weeks) |

**Identifiers** — dotted paths walk the signal's fields. `signal.subject`, `source.url`, `reviewer`, `last_sender`. Whatever properties the `inputTypeNames` DomainType declares is reachable. Unresolvable paths fail the comparison (logged at debug, not a parse error) so a misspelled field surfaces as "rule never fires" rather than a load-time crash.

**Special tokens:**

- `$self` — the user's identity bundle (username + configured aliases — emails, github handle, etc., from `assistant.policy.self.<username>` in `application.yml`). Use in `==`, `!=`, or as the LHS of `in`. `reviewer == $self`, `$self in participants`.
- `age` — derived `now - signal.occurredAt` as a `Duration`. Compare against a duration literal: `age >= 24h`, `age < 5m`.

**Grouping:** `()` for explicit precedence. `not (a or b)`.

**Worked examples:**

```
reviewer == $self and age >= 48h
$self in participants and last_sender != $self and age >= 24h
mentioned == $self and not acknowledged
source.kind == "email" and message_count > 1
```

Errors at parse time include source span and the unexpected token — realm authors see the column the parser tripped on.

### How policies and LLM-judgment actions compose

For each fresh signal of type `T`, the host runs one `AgentProcess` whose goal is "an `AttentionCandidate` exists on the blackboard". Every loaded action whose preconditions match `T` is a candidate; UtilityAI picks in value-minus-cost order. A cheap deterministic rule ((cost 0.01, value 1.0) → utility 0.99) wins over an LLM `stepType: action` producing AttentionVerdict ((cost 0.5, value 1.0) → utility 0.5) — so the cheap rule runs first, writes the AttentionCandidate, the goal is satisfied, and the LLM call never happens.

When the cheap policy doesn't match, its `hasRun_<name>=TRUE` blocks re-picking; the LLM action still has positive utility; the planner picks it; it produces an AttentionVerdict (or null = skip); if non-null, the host's wrap action fires; goal satisfied. If the LLM returns null and no other action can produce an AttentionCandidate, the planner terminates naturally with no candidate.

Actions are deployed to the host's planner on world load.

## `goals/`

Goal specifications — multi-step workflows composed of actions.

```yaml
# goals/fix-issue.yml
stepType: goal
name: fix-issue
description: "Triage and fix a GitHub issue"
inputTypeNames:
  - GitHubIssue
outputTypeName: BackgroundMessage
```

## `types/`

Dynamic type definitions — custom input/output types for actions, signal types, and the data dictionary in general. A type with `parents:` declared inherits properties from its parent types (which may be JVM-known host types or other realm-declared types).

```yaml
# types/github.yml
- name: GitHubIssue
  description: "A GitHub issue to process"
  properties:
    owner: "Repository owner"
    repo: "Repository name"
    issue: "Issue number"
    title: "Issue title"
    body: "Issue body"
```

A type whose `parents:` includes `Signal` (the host-defined signal base type) is a **signal type** — automatically eligible for the consequence engine, triage rules, and persistence as a `SignalRecord`. See [`events/`](#events--event-ingestion-forward-looking) below.

```yaml
# types/stripe.yml
- name: StripeEvent
  parents: [Signal]
  description: "A Stripe webhook event"
  properties:
    eventType: "Stripe event type, e.g. charge.failed"
    amount: "Charge amount in minor units"
    currency: "ISO 4217 currency code"
    customerId: "Stripe customer id"
```

### Persistence (graph-backed)

Every entry created via `create_entry` for a type defined here lands as a node in the world graph (the same graph the host's Cypher / schema-projector / proposition-recall tools talk to). Two consequences worth knowing when writing a realm:

- **The entry's `name` is the host's headline for it.** The host picks a single field per type to use as the node `name` for rendering — first `title`, then `name`, then `summary` if any exists. Add at least one of those if you want list / Cypher output to be human-readable.
- **The host adds an implicit edge to the world user on every create.** Default is `(entry)-[:OWNED_BY]->(user)` — fine for most types. When the predicate reads more naturally in the other direction, declare a `userAnchor:` on the type:

```yaml
# types/movies.yml
- name: MovieRating
  description: "The user's score for a Movie."
  userAnchor:
    predicate: RATED          # uppercase; stored uppercase
    direction: from-user      # `user -[RATED]-> rating` (default is `from-entry`)
  properties:
    imdbId: "IMDb id of the rated Movie."
    rating:
      type: int
      description: "1–10."
```

| Field | Default | Notes |
|-------|---------|-------|
| `predicate` | `OWNED_BY` | Cypher-style relationship name. Required when the key is declared. Stored uppercase. |
| `direction` | `from-entry` | `from-entry` → `(entry)-[:PREDICATE]->(user)`. `from-user` → `(user)-[:PREDICATE]->(entry)`. Pick whichever reads naturally. |
| (sentinel) | — | Set `userAnchor: false` to opt the type out of the implicit edge entirely (reference data, type registries, etc.). |

#### Explicit relations between entries

`create_entry` accepts an optional `relations:` array so a realm's skill can wire the new entry to another entry that already exists in the world. The host emits each requested edge on save; if any target can't be found in the same world, the whole create is refused (no orphan node, no orphan edge). Example shape, taken from the movie realm's `rate-movie` skill:

```jsonc
// inside execute_javascript / execute_python, via the repository tool:
create_entry({
  type: "MovieRating",
  data: { imdbId: "tt0113277", title: "Heat", rating: 9 },
  relations: [
    { predicate: "OF", to: { type: "Movie", imdbId: "tt0113277" } }
  ]
})
// Resulting graph: (User)-[:RATED]->(MovieRating)-[:OF]->(Movie)
//   - The RATED edge comes from `MovieRating.userAnchor` (implicit).
//   - The OF edge comes from `relations:` (explicit, from the skill).
```

Each relation is `{predicate, to: {type, ...keyProps}}` — `to.type` names the target's type, the remaining `to.*` fields are the key properties the host MATCHes against on the target's world-scoped nodes. Use this pattern any time a realm's typed records form a small connected graph (rating → movie, comment → ticket, note → contact, etc.) — the same graph is then walkable by Cypher and feeds the recall path automatically.

### Populating types from an external system (deterministic, no code)

The patterns above cover types the *user* creates. A realm can also declare a type that the host **populates automatically from a connected external system — deterministically, with no LLM and no Kotlin/Java in the realm.** A structured record (a CRM contact, an issue, a calendar attendee) is already typed at the source, so extracting it with an LLM is wasteful and error-prone; instead the realm declares a *projection* in property `metadata:` and the host's projector does the rest.

This builds on a small canonical-entity model the host ships: a `Contact` is a `Person` resolved by email. Declare a **mirror type** that `parents: [Contact]` and annotate each property:

```yaml
# types/hubspot.yml — populated from HubSpot CRM, no Kotlin in the realm
- name: HubSpotContact
  parents: [Contact]
  visibility: internal          # machinery, not a user-browsable repository type
  userAnchor: { predicate: OWNED_BY, direction: from-user }
  properties:
    email:                      # the deterministic merge key
      metadata: { identity: "true" }
    jobtitle:                   # projects onto the canonical Person
      metadata: { canonical: "jobTitle" }
    company:                    # resolve + link a related entity
      metadata: { relationship: "WORKS_FOR", target: "Organization", matchBy: "name" }
    phone:
      cardinality: LIST
      metadata: { canonical: "phones", multivalued: "true" }
    # undeclared fields (lifecyclestage, …) stay on the mirror, source-private
```

| Metadata key | Effect |
|--------------|--------|
| `identity: "true"` | This field's value is the email **merge key**: records with the same email resolve to one canonical `:Person` (no LLM entity resolution). Also unioned onto the Person's `emails`. |
| `canonical: <field>` | Project this source field onto the canonical Person's `<field>`. Single-valued → a winner is chosen by host precedence then most-recent; mark `multivalued: "true"` (or `cardinality: LIST`) to **union** instead. |
| `relationship: <EDGE>` + `target: <Label>` + `matchBy: <prop>` | Create-or-match a `<Label>` keyed on `matchBy`, and link `(:Person)-[:EDGE]->(:Label)`. |
| *(none)* | Source-private — the value lands only on the per-record mirror node. |

**Storage model.** Each source record becomes a per-record mirror node (`:<TypeName>:RemoteHandle`) holding the raw fields + provenance, linked to one canonical `:Person` that holds the *resolved* values (queryable: `MATCH (p:Person) WHERE p.jobTitle = 'CEO'`). The mirror's label is the namespace, so two sources never clash on a field; "what does HubSpot specifically say" is one hop to the mirror. A record with no email becomes a mirror-only orphan (reaped in the background).

**When it runs.** Declaring the type loads nothing. Once the user connects the account (OAuth), the host pulls on a schedule (cadence configurable per source), checkpointed by a persisted watermark so a large import drains over successive ticks and a mid-run failure safely retries the window (projection is idempotent). One-click backfill and real-time webhooks ride the same path. The realm supplies only the type (above) and the fetch (its `apis/` OpenAPI op or a handler); the projector and scheduling are host-side.

### Joining types on demand (virtual joins, not mirrored)

Population (above) **eagerly mirrors** a whole external collection into the graph on a schedule. For large or volatile collections you usually only ever touch a tiny slice — there a **virtual join** is better: the type's instances are fetched **on demand** when a Cypher query traverses to them, materialized transiently for that query, then **rolled back** (no persistence, no sync, no GC). It's the traversal-triggered sibling of `population:`.

**Virtual Cypher — the engine.** The host mechanism that powers on-demand joins is called **Virtual Cypher**. A realm never invokes it directly; you declare the pieces (`virtualJoins:` + `producers/`, and bridge `resolve:` chains) and it plans and runs the fetch. For a user query that traverses to a virtual label it:

1. **probes** the bound *real* anchors the query selects — applying the query's own `WHERE` / pinned-literal predicates so only the anchors that will survive are chosen (a filtered `… WHERE p.name CONTAINS 'governor'` resolves just those people, not the whole address book), preferring an existing real node and only **seeding** a transient one when none exists;
2. **plans** each fetch with a cost-based optimizer — pushing predicates to the source (below), fetching **per-key or batched** per the producer's declared capability (`batchSafe`), and budgeting calls against the source's shared rate bucket (`cost:`), emitting an `EXPLAIN` with rewrite **advice** when a query can't fit the budget;
3. **fetches** the external records through the named **producer**;
4. **materializes** them — and any `brings` sub-graph — as transient nodes carrying the extra `:Virtual` label, a `dateRetrieved` timestamp, and the acting user's `userId`;
5. runs the user's (scope-rewritten) query over the combined **real + virtual** graph;
6. **rolls back** — nothing persists.

Identity **bridges** (`writeThrough`, below) are the one exception: they persist as a warm cache and re-resolve after `refreshAfter`. The contract you write — declarative joins + producers — is the same whether the source is one record or a million; the engine handles probing, planning, fan-out caps and rollback. **Execution model + worked examples (including vector/semantic edges): [`VIRTUAL_CYPHER.md`](./VIRTUAL_CYPHER.md).**

A virtual type declares one or more `virtualJoins:`. Each says how the type is reached — from an anchor label along a relationship, keyed by an anchor field, fetched by a named **producer**:

```yaml
# types/hubspot.yml — fetched on demand, NOT mirrored
- name: HubSpotContact
  visibility: internal
  properties:
    id: { metadata: { identity: "true" } }   # MERGE key for dedup
    email: "Primary email."
    jobtitle: "Job title."
  virtualJoins:
    # Linking on an id match: anchor is a domain node, joined by a shared property.
    - anchorLabel: Person
      relationship: HAS_HUBSPOT_CONTACT
      keyField: email            # anchor property whose values become the producer keys
      recordKeyField: email      # field on each fetched record that maps it back to the anchor
      producer: contactsByEmail  # see producers/ below
      # brings: a fetched record may carry its own sub-graph (extracted from the record)
      brings:
        - childType: HubSpotComment
          relationship: HAS_COMMENT
          records: "$.comments[*]"   # JSONPath within the record to the child list
          id: id
```

`virtualJoins` fields: `anchorLabel`, `relationship`, `keyField`, `recordKeyField` (defaults to `keyField` — a same-property id-match), `producer`, optional `brings` (declared sub-graph), `maxAnchors`/`maxFanoutTotal` (caps). For a join to an **external-identity node** (a bridge like `GitHubIdentity` / `HubSpotOwner`), declare a `resolve:` rule chain + `writeThrough`/`refreshAfter` instead — see **Identity bridges** below (`persist: true` is the older eager-only form). A list with more than one entry, or any join that can fan in, requires an `identity` property so convergent paths dedupe to one node.

The query may only reach a virtual label by **traversing a declared join from a bound anchor** — a naked `MATCH (hc:HubSpotContact)` is rejected. Every materialized node carries the extra `:Virtual` label, a `dateRetrieved` ISO-8601 timestamp, and the acting user's `userId` (so the normal scope rewriter matches it); the user's query runs through the rewriter unchanged, and the whole materialization is rolled back when the query completes.

A query may also reach a virtual node by **pinning the anchor with a literal** — `MATCH (g:GitHubIdentity {login:'octocat'})-[:RAISED]->(i:GitHubIssue)` — even when no `GitHubIdentity{login:'octocat'}` exists in the graph. The literal (inline `{...}` **or** a `WHERE alias.login = '…'`) seeds a transient anchor, so a producer can be keyed on a *named* identity (any GitHub login, not just the connecting user's), fetched with the connecting user's credentials. Multiple joins onto the same virtual node compose: `(me)-[:RAISED]->(i)<-[:ASSIGNED]-(:GitHubIdentity {login:'octocat'})` materializes both sides and intersects them.

### `producers/`

Producers are the source-specific fetchers a `virtualJoins.producer` references — declared once, reused. Conceptually each is a **Repository** over an external store (the Spring Data analogue: one `Repository` abstraction, different stores underneath); the `kind` discriminator picks the store. Each `.yml` in `producers/` is a list. **Batch contract:** a producer takes ALL anchor keys at once and returns the matching records — never one call per key (no N+1).

```yaml
# producers/hubspot.yml
- name: contactsByEmail
  kind: remote                    # a RemoteRepository — gateway op (realm handler or learned API)
  operation: objectsSearch
  records: "$.results[*].properties"
  keyArg: "filterGroups.0.filters.0.values"   # where the key LIST is injected (list mode)
  args: { objectType: contacts, filterGroups: [ { filters: [ { propertyName: email, operator: IN } ] } ] }
  cache: { kind: ttl, seconds: 300 }

# producers/github.yml — string mode: keys render into a query string
- name: issuesByAuthor
  kind: remote
  operation: search/issues-and-pull-requests
  records: "$.items[*]"
  args: { q: "is:issue {keys} {filters}" }     # {filters} ← predicate pushdown (below)
  keyTemplate: "author:{key}"     # each key → author:<k>, joined by keyJoin, into the {keys} placeholder
  paging: { style: page, size: 100, maxPages: 10 }
  pushdown:
    - property: html_url
      qualifier: "repo:{value}"
      valuePattern: '(?:github\.com/|repos/)?([\w.-]+/[\w.-]+?)(?:/|$)'

# producers/warehouse.yml — relational source
- name: ordersByCustomer
  kind: sql
  datasource: warehouse           # a realm/world SQL datasource (sql/datasources.yml)
  query: "SELECT id, customer_email, total FROM orders WHERE customer_email IN (:keys)"
```

Producer `kind`s:

| kind | fetch | notes |
|------|-------|-------|
| `remote` (alias `api`) | a `gateway.<name>.*` op (realm handler or learned API) — a **RemoteRepository** | list mode (`keyArg` → array) or string mode (`keyTemplate` + `{keys}`); `records` JSONPaths the response |
| `sql` | a SELECT against a realm/world `datasource` | keys expand into `IN (…)`; rows are the records; SELECT-only, wallet/env creds |
| `compute` | an in-process computation over the keys | scores / rollups / synthesis — no external I/O; *local*, so NOT a RemoteRepository |
| `vector` | top-k **semantic similarity** to the anchor | for joins with no key — similarity *is* the join (related docs/chunks); rides the host embedder |
| `generative` | **GENERATES** the edge (resumably) rather than reading it — an LLM's world knowledge (`SIMILAR_TO`, `IN_INDUSTRY`) or a code function | pluggable generator (`llm` \| `function`); keeps generating; resolves each answer onto the type spine; provenance-stamped |
| `aggregate` | **REDUCES** an anchor's connected neighborhood to ONE node (fan-IN) — e.g. a per-user summary node distilled from many rows | gathers via a scoped graph read; delegates the reduction to an existing LLM aggregation (`synthesize`/`summarize`/…); TTL-cache = periodic refresh |

> **Naming:** `kind: remote` is the current spelling for an externally-backed repository; `kind: api` is accepted as a back-compat alias and still works in existing realms.

#### `kind: generative` — a generated edge

Where `remote`/`sql`/`vector` **retrieve** records from a store and `compute` derives them once, a
**generative** producer **generates** them — and can be asked for MORE (the generator model). The
generation is pluggable via `generator.kind`:

- **`llm`** — the model's world knowledge. The **prompt is authored by the realm, inline**; the host's
  generative backend is domain-agnostic and ships no prompt of its own. Parametric, so a `volatile` fact is
  refused (it would be confidently stale).
- **`function`** — a host/realm-supplied **resumable function** (a `GeneratorFunction` bean), the
  Python-generator analogue: given the keys, the exclusion set, constraints, demand and round, it yields
  candidates. No LLM, no volatility gate.

The rest — resolving each answer onto the type spine, provenance, and demand-driven re-probing — is shared.

```yaml
- name: similarMovies
  kind: generative
  edgeType: SIMILAR_TO            # the edge this fills (host may whitelist which edges generate)
  identityField: imdbId          # the target type's identity — records carry it after resolveVia
  anchorKeyField: similarTo      # record field the anchor key is echoed into (links each answer to its anchor)
  nameField: title               # the human name the generator emits (dedup/exclusion happen in THIS space)
  volatility: static             # static | slow | volatile — a volatile fact is refused for an `llm` generator
  confidenceFloor: 0.3           # drop answers below this confidence
  defaultWant: 25                # a view has no LIMIT; keep generating until this many SURVIVE the filters
  generator:                     # llm (prompt) OR function (operation)
    kind: llm
    prompt: |                    # REALM-AUTHORED. Rendered with: anchors[{n,title}], exclude[], want, round, constraints[]
      For each numbered item, name similar ones a fan would enjoy…
      {% for a in anchors %}{{ a.n }}. {{ a.title }}
      {% endfor %}
      {% if constraints %}Only suggest items where: {% for c in constraints %}{{ c }}; {% endfor %}{% endif %}
  resolveVia:                    # optional: resolve each emitted name onto the type spine (a nested remote op)
    kind: remote
    operation: getMovie
    args: { t: "{keys}" }
    project: { imdbId: imdbID, title: Title, year: Year, genre: Genre }   # fill the type's FULL property surface
```

A function generator instead:

```yaml
  generator:
    kind: function
    operation: mySimilarFn       # a GeneratorFunction bean: yield(keys, exclude, constraints, want, round)
```

Semantics (both generators):
- **Resumable / demand-driven.** The host re-probes (pushing a growing exclusion set into the generator)
  until `want` records *survive the query's filters* — a query `LIMIT`, else `defaultWant`. So a
  heavily-filtered view (most rows knocked out by a genre or availability filter) still fills up.
- **Constraints pushdown.** Target-node predicates in the query (e.g. `WHERE m.genre CONTAINS 'Noir'`) reach
  the generator as `constraints`, so it only proposes matching answers, and they count toward survival.
- **Fill the whole type.** A producer materialising a typed node fills that type's FULL property surface
  (via `resolveVia.project`), not just its identity.
- **Provenance.** Each record is stamped `_source` (the generator kind — `llm`/`function`), `_confidence`,
  `_asOf`.

`cache:` is orthogonal to kind (`none` / `ttl` / `session` / `immutable`).

#### `kind: aggregate` — a fan-IN summary NODE

Every other producer is **fan-OUT**: one anchor → many target records. An `aggregate` producer is the
**fan-IN** mirror: it gathers the anchor's connected neighborhood and **reduces it to ONE node**. Use it when
the reduction should itself be a node you can traverse to and cache — a per-user summary, a per-org rollup, a
per-topic digest — rather than a scalar computed inline.

It does **not** reimplement the reduction: it **delegates to an existing LLM aggregation** (`synthesize` /
`summarize` / `themes` / … — the same functions a query can call inline as `synthesize(text, goal)`). So there
is one implementation of "LLM-reduce a group of text", whether you write it in Cypher or declare it on a
producer. The neighborhood traversal, the per-item text, and the reduction goal are **all realm-authored** — the
host ships no domain prompt and no model (the aggregation uses the ops-controlled aggregation LLM).

```yaml
# producers/movie.yml — one MovieTasteSummary node distilled from all of a user's ratings
- name: movieTasteSummary
  kind: aggregate
  edgeType: HAS_MOVIE_TASTE_SUMMARY
  identityField: userId          # ONE node per user (MERGE on this folds the anchor's identity spellings)
  anchorKeyField: anchorKey      # the join's recordKeyField — links the one node back to the anchor
  collect:                       # the fan-IN neighborhood: a scoped read (a:anchorLabel)-[:via]->(t:targetLabel)
    anchorLabel: AssistantUser
    via: RATED
    targetLabel: MovieRating
    text: "{{ title }} — rated {{ rating }}/10"   # Jinja per neighbor node → one text item for the reducer
    where: "t.rating >= 1"       # optional extra predicate on the neighbor alias `t`
  reduce:
    using: synthesize            # a registered LLM aggregation
    into: summary                # the record field the reduced value lands in (a declared property on the type)
    args:                        # aggregation args — e.g. the GOAL for synthesize
      - "In ~100 words, second person, sum up this person's taste in film."
  cache: { kind: ttl, seconds: 604800 }   # weekly-refreshed node
```

The node is virtual like any other: reached only from a bound anchor (`(me:AssistantUser)-
[:HAS_MOVIE_TASTE_SUMMARY]->(ts:MovieTasteSummary)`), materialized on demand, rolled back after the query. Give
its type a Movie/Foo **prefix** so the label and edge can't collide with another realm's summary type.

#### A join is declared under the type it PRODUCES — and chains (multi-stage)

**Rule (easy to get wrong):** a `virtualJoins:` entry is declared under the **target type** — the type it
materializes — with `anchorLabel` naming where it starts. `SIMILAR_TO` produces `Movie`, so it lives under
`Movie` with `anchorLabel: MovieRating`; `AVAILABLE_ON` produces `StreamingService`, so it lives under
`StreamingService` with `anchorLabel: Movie`. A join does **not** go under its anchor type. Put it under the
wrong type and the planner registers it against the wrong target and it silently never fires.

The anchor of one join can be the **virtual target** of another, and the engine stages them in one read tx:
`StagedVirtualCypher` materializes stage 1, treats its target as real, re-probes, then materializes stage 2 off
it (up to `MAX_STAGES` deep). So a fan-IN → fan-OUT pipeline is expressible — reduce a user's ratings to one
`MovieTasteSummary` node, then generate films *from that summary*. Both joins go under the type each produces:

```yaml
# types/movies.yml — BOTH joins under Movie (what they produce), not under their anchors
- name: Movie
  virtualJoins:
    - anchorLabel: MovieRating          # films similar to ONE rated film (fan-OUT)
      relationship: SIMILAR_TO
      keyField: title
      producer: similarMovies
    - anchorLabel: MovieTasteSummary    # films matching the WHOLE taste (fan-OUT off the fan-IN summary node)
      relationship: SUGGESTS
      keyField: summary                 # the MovieTasteSummary.summary prose is the generator input
      recordKeyField: fromTaste
      producer: tasteBasedPicks         # a `generative` producer; MovieTasteSummary is an `aggregate` node
```

```cypher
-- two-stage chain: HAS_MOVIE_TASTE_SUMMARY (fan-IN) materializes ts, then SUGGESTS (fan-OUT) generates off it
MATCH (me:AssistantUser)-[:HAS_MOVIE_TASTE_SUMMARY]->(ts:MovieTasteSummary)-[:SUGGESTS]->(m:Movie)
WHERE NOT EXISTS { (me)-[:RATED]->(seen:MovieRating) WHERE seen.imdbId = m.imdbId }
RETURN DISTINCT m
```

The intermediate node is transient (materialized then rolled back with the read) — it need **not** be persisted
for the downstream join to see it, because both stages run in the same read tx. Give the summary type a TTL
`cache:` (weekly) so the expensive fan-IN reduction is reused across queries within the window.

#### Predicate pushdown (`pushdown:`) — scope the fetch at the source

By default the graph filters *after* materialization: a virtual join fetches broadly, then the query's `WHERE` drops non-matches. For a prolific anchor that's wasteful and can hit the source's result cap before the matches you want. **Pushdown** translates a query predicate on the virtual *target* node into the source's native filter so the fetch is scoped before it returns — the Spring Data analogue is pushing a `Specification`/`Criteria` to the store, with whatever can't be pushed still filtered in the graph (so correctness never depends on pushdown, only cost and coverage).

A `remote` repository declares `pushdown:` rules; the host renders matching predicates into the `{filters}` placeholder of `args`:

```yaml
pushdown:
  - property: html_url            # the target-node property the predicate is on
    op: contains                  # EQUALS (default) or CONTAINS
    qualifier: "repo:{value}"     # native fragment; {value} ← the predicate's value
    valuePattern: '…([\w.-]+/[\w.-]+?)(?:/|$)'   # optional regex; group 1 replaces {value}
```

So `WHERE i.html_url CONTAINS 'embabel/me'` turns `is:issue author:X {filters}` into `is:issue author:X repo:embabel/me` — one scoped search instead of fetching the author's thousands and intersecting in the graph. The mapping is declarative and source-specific; the engine knows nothing of `repo:`.

> **Verify that a pushdown actually narrows — some sources ignore unknown filters SILENTLY.** The engine cannot tell a filter the source honoured from one it discarded: both return 200 with records. A source that responds to an unrecognised filter key by returning the *entire unfiltered collection* turns a typo, a renamed upstream field, or an optimistic guess into a full-collection scan that looks like a success — the query still returns correct rows (the graph filters what pushdown didn't), so nothing fails; you just quietly fetch everything, every time. This is real: the NSW planning feed used by `realm-nsw-property` returns all 426,096 records for a misspelled filter and never errors.
>
> Before declaring a `pushdown:` rule, call the source twice — once with the filter, once without — and confirm the **counts differ**. Declare rules only for keys you have proven narrow, and say so in a comment. When a source's filter surface is partly unsupported, the honest producer declares the few verified keys and leaves the rest to graph-side filtering; document which properties do *not* push down, because a query author will otherwise assume a `WHERE` on any property is cheap.

**`project` paths: use `[*]`, never `[0]`.** An INDEXED path is not honoured and projects **null silently** — no warning, no error, just an empty property, and any predicate over it then drops every row. Only the `[*]` form reaches into a nested array, and it yields a **list**, so a single-valued nested field arrives as a one-element list the consumer must unwrap. Write `address: "Location[*].FullAddress"`, not `Location[0].FullAddress`. (Verified 2026-07-28: with `[0]`, every address and coordinate in a fetched collection was null while the flat scalar fields projected fine — the kind of defect that reads as "the source didn't return that field".)

Relatedly, **`project` does not coerce types**: values arrive as the source encodes them. A JSON feed that quotes its numbers yields strings, so `WHERE n.cost >= $min` compares a string to a number and quietly matches nothing. Coerce at the point of use (`toFloat(n.cost)`), and beware that a null-propagating comparison also *removes* rows with no value at all — which for something like a cost bound means records the user would have wanted to see silently vanish.

**Composing a key the source needs from more than one record field is not expressible declaratively.** `project` maps flat paths to properties (`lat: "Location[*].Y"`); there is no template, concatenation or expression form, and `keyField` names a single anchor property. So a source keyed on a *composite* — a `"longitude,latitude"` point for a geospatial lookup, a `"owner/repo"` slug assembled from two fields — cannot have that key derived in YAML. The options are to have the upstream shape expose the composite as one field, to add a **TypeScript handler** (`src/api/*.ts`) that returns records with the composite already assembled, or to do the lookup procedurally in a Lens rather than as a virtual join. Prefer the handler when the join should compose into arbitrary Cypher; a Lens-side lookup works but is reachable only from that Lens.

#### Pagination (`paging:`) — capture more than one page

A search/list op returns one page; `paging:` makes the producer walk pages and accumulate, bounded by `maxPages`, so a scoped fetch that still exceeds a page is fully captured (and a cross-join intersection doesn't silently miss matches past page 1).

```yaml
paging: { style: page, size: 100, maxPages: 10 }     # one-based page numbering (default)
paging: { style: page, startPage: 0, size: 200, maxPages: 25 } # zero-based source
# or, for opaque cursors (HubSpot ?after=… + paging.next.after):
paging: { style: cursor, size: 100, maxPages: 10, cursorParam: after, cursorPath: "$.paging.next.after" }
```

| Field | Default | Meaning |
|---|---|---|
| `style` | `page` | `page` (increment `param` from `startPage`) or `cursor` (opaque). |
| `param` / `sizeParam` | `page` / `per_page` | Page-number arg, and the page-size arg. |
| `startPage` | 1 | Page-number style only: first non-negative page number sent to the source. Set `0` for zero-based APIs. |
| `size` | 100 | Records per page (set to the endpoint's max). |
| `maxPages` | 5 | Hard cap on pages fetched, independent of page numbers. `startPage: 0, maxPages: 2` fetches pages 0 and 1. |
| `cursorParam` / `cursorPath` | `after` / — | Cursor style only: request arg + JSONPath to the next cursor. `startPage` is ignored. |

Omitting `startPage` preserves one-based requests (`1, 2, …`). A negative value is invalid. For either starting convention, a short page ends the walk normally; a full final page at `maxPages` reports the existing truncation warning.

`param` / `sizeParam` name **parameters declared on the operation**, so an API that takes paging somewhere other than the query string is addressed by naming the parameters it actually declares. A handful of APIs pass paging (and even filtering) as HTTP **headers** — the NSW planning feed used by `realm-nsw-property` takes `PageSize`, `PageNumber` and a JSON `filters` string as headers. Declare them as `in: header` parameters in the vendored spec and name them here; the walker then drives them correctly (verified against a live world, 2026-07-28).

> **Always set `param`/`sizeParam` when the endpoint's paging arguments are not literally named `page` and `per_page`.** The defaults are injected as *query* parameters, and a source that ignores unknown query parameters — many do, silently — will return **page 1 for every request**. The walker cannot detect this: it sees `maxPages` successful 200s with a full page of records each time, and reports the product as the record count. In the case that motivated this note it reported 3,200 records that were 400 records repeated eight times, with no warning, and every downstream statistic was computed over eight copies of the same page.
>
> The failure is silent by construction, so verify rather than assume: check that page 2's records differ from page 1's before trusting a paged producer. A count that is suspiciously close to `size × maxPages` is the tell.

> **A failed fetch produces zero rows — the `warnings` are what tell you it failed. NEVER discard them.** When a producer errors (a timeout, a 401, a cancelled request) it contributes **no records**, and the rows are then indistinguishable from a legitimately empty result. The engine does surface the failure: `gateway.kg.query` returns an **unconditional `{rows, warnings}` envelope**, and a fetch failure lands there as a diagnostic. A consumer that reads `result.rows` and ignores `result.warnings` throws away the only signal separating "the source says there is nothing here" from "we never found out", and renders a broken fetch as a confident negative.
>
> ```javascript
> const { rows, warnings } = await gateway.kg.query({ cypher, params });
> // A zero count with a FETCH_FAILURE warning is NOT a finding — report it as incomplete.
> ```
>
> For most joins, silently degrading to zero is tolerable. For any question where **absence is the reassuring answer** — is anything being built near this address, are there recalls on this product, does this person have open issues — it is the dangerous direction: a zero must never be presented as a finding when a warning says the fetch did not complete. Withhold the derived figure rather than computing a rate over a failed fetch.
>
> This bites hardest on a paged walk of a slow or throttling source: latency climbs page over page until the request is cancelled part-way, so the fetch that fails is the one that would have returned the *most* data — the large result set, not the empty one.

**Chunking (`maxKeysPerCall`).** Producers chunk the unioned anchor keys into batches of `maxKeysPerCall` — so a traversal over many anchors stays within the endpoint's limit and never becomes N+1. Set it to the endpoint's documented cap: a search `IN`/`OR` (query-length bound, ~50, the `api` default), a dedicated **bulk-by-ids** endpoint (HubSpot `/batch/read` 100, Jira `bulkfetch`), or a `$batch`/composite multiplex (Microsoft Graph 20, Salesforce 25). `sql` defaults to 500.

**Per-key vs batched (`batchSafe`).** A producer batches up to `maxKeysPerCall` keys per call by default. Set **`batchSafe: false`** when one call covering many keys is **not complete per key** — a globally-ranked, capped search is the classic case: GitHub issue search `author:a author:b` returns ONE `updated`-desc list capped at `paging.maxPages × size`, so a prolific author fills the cap and a low-volume colleague's results fall off the end (you'd list them for one question and find nothing for the next). With `batchSafe: false` Virtual Cypher fetches **one key per call**, giving each key its own budget. It is a declared **capability**, not a magic number — you do NOT also shrink `maxKeysPerCall`, so a realm can't reintroduce the starvation bug by forgetting to. (`echoKeyAs` already implies per-key.)

There is a second, more mundane reason to set it, distinct from the starvation case above: the source is **structurally single-key** — its endpoint accepts exactly one value and there is no batch form. A point-in-polygon lookup (`geometry=lng,lat`), a "get by id" path parameter, and a single-document fetch are all of this shape. Batching is not merely incomplete there, it is impossible, so declare `batchSafe: false` and size `cost:` for the fan-out you will actually incur. When the producer also stamps the key with `echoKeyAs`, per-key is already implied and `batchSafe` is redundant — but stating it costs nothing and documents the source's shape for the next author.

Conversely, do not reach for `batchSafe: false` just because a source *looks* single-valued: check whether the filter accepts a list. A source that takes one name per call in its examples may accept several (the NSW planning feed's `CouncilName` takes an array, verified by comparing counts for one council against two), and a genuine batch is an order of magnitude cheaper than a per-key fan-out.

**Search vs bulk-by-ids.** When the join key is the *target's own id*, prefer the source's dedicated bulk-read endpoint (`operation:` = that op, `keyArg:` = its ids array, `maxKeysPerCall:` = its cap) — it's cheaper than a search and supports field/expand selection. Use search (`IN`/`OR`) only when the key is a *secondary* field (email, login, domain), where there is no by-id endpoint. Pair `brings` with the endpoint's `expand`/`include`/sideload params so the sub-graph arrives in the same call rather than a follow-up. **If a search result doesn't carry the key you searched by** (so `recordKeyField` has nothing to match), set `echoKeyAs:` — the producer then calls one key per call and stamps the queried key onto each record (see **Identity bridges**).

**Field selection & cursor paging (set them in `args`/`paging`).** Two efficiency levers that need no producer code — just declare them:

- **Field masks / sparse fieldsets** — request only the fields the join needs via the op's field param (`fields`, `$fields`, `X-Goog-FieldMask`, `properties: [...]`). Smaller payloads, lower latency, less server CPU. Across Google, Zendesk, Jira, HubSpot this is the single cheapest win.
- **Cursor paging** — prefer `style: cursor` over offset in `paging:`. Beyond performance, some sources (e.g. Slack) grant a *higher rate-limit tier* to cursor-paginated calls than un-paginated ones, so cursor paging is a quota win too.

These hold across the ~13 SaaS APIs surveyed (Jira, Salesforce, Microsoft Graph, Shopify, HubSpot, Stripe, GitHub, Zendesk, Google, Slack, Notion, Airtable). The very tightest (Notion 3 req/s with no bulk endpoint; Airtable 5 req/s) make `cache:` and chunking mandatory, and are the case for the (deferred) `$batch`/composite multiplex producer kind.

### Connected-account identity bridges (`identityBridge:`)

A lightweight bridge type can be populated **reliably for the connecting user** from a connected account's resolved identity, on OAuth authorize — no producer needed. When the user authorizes the provider, the resolved account id (the apis.yml `identity.account-id-field`, e.g. GitHub `login`) becomes the bridge's identity, linked to the user's own anchor (matched by email):

```yaml
# types/github.yml
- name: GitHubIdentity
  visibility: internal
  properties:
    login: { metadata: { identity: "true" } }
  identityBridge: { provider: gh, relationship: HAS_GITHUB, linkFrom: Person }
  # then GitHubIssue can virtualJoin on GitHubIdentity by login
```

This covers the *user's own* identity (all OAuth knows). **Other people's** identities — "Jasper's HubSpot contacts", "who that I email raised a GitHub issue" — are resolved by the bridge's `resolve:` chain, below.

### Identity bridges (`resolve:` chains) — link Person/Organization to any external system

A **bridge** is a virtualJoin to an external-identity node (`GitHubIdentity`, `HubSpotOwner`, …) from a canonical `Person`/`Organization`. Instead of `persist`+`keyField`, declare an **ordered `resolve:` rule chain**. At query time, for the anchors a query actually binds — **any person/org, not just the connecting user** — the host resolves the bridge **lazily**, **first matching rule wins**, and (with `writeThrough`) **persists** it so it's reused next time. Downstream joins (e.g. `RAISED` on a resolved `GitHubIdentity`) then anchor on the now-real bridge.

```yaml
# types/github.yml
- name: GitHubIdentity
  visibility: internal
  properties:
    login: { metadata: { identity: "true" } }   # bridge MERGE key
  virtualJoins:
    - anchorLabel: Person
      relationship: HAS_GITHUB
      keyField: primaryEmail        # anchor key the pre-pass probe reads
      recordKeyField: email         # field on each resolved record that maps it back to the anchor
      writeThrough: true            # persist the resolved bridge (default true); reused + respected
      refreshAfter: 30d             # re-resolve a bridge older than this (optional; default 30d)
      resolve:                      # ordered; FIRST rule that yields a bridge (or finds one) wins
        - existingBridge                                    # respect a fresh bridge already linked
        - learnedHandle: { property: githubLogin, as: login }  # an explicit handle on the anchor (no email)
        - canonicalEmail: { producer: githubUsersByEmail }     # resolve via the Person's email set
```

**Rule kinds** (host-provided, referenced by name; the chain is per-realm so the link key can vary and need not be email):

| rule | does |
|---|---|
| `existingBridge` | If a fresh bridge is already linked to the anchor (persisted, learned, or manually added), use it — stop. |
| `learnedHandle: { property, as }` | Read an explicit identity stored on the anchor (e.g. `Person.githubLogin`) → bridge `{ <as>: handle }`. No email lookup. |
| `canonicalEmail: { producer }` | Resolve via the anchor's **canonical email set** (host-owned: `primaryEmail`/`email`/`emails`) → call `producer`. |
| `canonicalDomain: { producer }` | Same for an `Organization`'s `domain`/`domains`. |

Canonical identity is **host-owned** — realms never hardcode `email` vs `primaryEmail`; the `canonical*` rules read the right properties for you.

**Producer requirement for a `canonical*` rule:** the producer must return records carrying the bridge's `identity` property AND the matched `recordKeyField`. If the source can't echo the key you searched by (e.g. GitHub `search/users` returns `login` but not the queried email), set **`echoKeyAs`** on the producer — it calls the op one key per call and stamps `record[<echoKeyAs>] = <that key>`:

```yaml
# producers/github.yml — search returns login, NOT the queried email → echo it
- name: githubUsersByEmail
  kind: remote
  operation: search/users
  args: { q: "{keys}" }
  keyTemplate: "{key} in:email"     # q = "<email> in:email" (one email per call)
  echoKeyAs: email                  # stamp the queried email onto each {login,...} hit
  records: "$.items[*]"
```

Most producers don't need `echoKeyAs` — e.g. HubSpot owners/contacts records already carry `email`. A `canonical*` rule whose producer op has **no gateway tool** simply yields nothing (the chain falls through); wire the op (in `apis/`) or supply a `learnedHandle` for those anchors.

(`persist: true` without a `resolve:` chain is the older form: an eager enrichment over *all* anchors that commits the bridge. Prefer `resolve:` — it's lazy, works for any anchor, and self-heals.)

### CypherScript — Cypher woven into TypeScript/JavaScript

Anywhere a realm ships code that runs in the host's `code_mode` sandbox — a **handler** (`handlers/`), a **decoration** action, a skill recipe — it writes **CypherScript**: an ordinary TypeScript/JavaScript program that interleaves graph queries with procedural logic, integration calls, and inline LLM, all over the one typed `gateway.*` surface. It is not a separate language — it's TS/JS with first-class graph access:

- **Cypher for the graph** — `await gateway.kg.query({ cypher, params })`. The query runs through **Virtual Cypher** (above): scope-rewritten to the acting user, read-only, and materializing on-demand virtual joins exactly as a chat query would — so one `MATCH` spans persisted **and** virtual (integration) data.
- **TypeScript/JavaScript** for what Cypher can't express — branching, aggregation, reshaping, loops.
- **Integrations** — `gateway.<ns>.*` (the realm's own verbs + connected APIs), e.g. fetch the actual email body the graph only holds an edge for.
- **Inline LLM** — `gateway.ai.classify` / `gateway.ai.*` for fuzzy predicates Cypher can't state.

```ts
// CypherScript: a graph query (through Virtual Cypher) + JS + integration + LLM in ONE program.
const people = await gateway.kg.query({
  cypher: `MATCH (me:AssistantUser)-[:EMAILED]->(p:Person)-[:HAS_GITHUB]->(g:GitHubIdentity)-[:RAISED]->(i:GitHubIssue)
           WHERE toLower(p.name) CONTAINS $who
           RETURN p.name AS name, collect(i.title) AS issues`,
  params: JSON.stringify({ who: "governor" }),
});
const busy = people.filter(p => p.issues.length > 5);              // plain JS
for (const p of busy) {
  const verdict = await gateway.ai.classify({ text: p.issues.join("\n"), labels: ["bug", "feature"] }); // inline LLM
  if (!dryRun) await gateway.notifications.createNotification({ event: "BusyContributor", source: "demo", url: "" });
}
```

`cypher` is your own query and `params` is a JSON **string** (bind values as `$name`; never string-concatenate). Reads and `gateway.ai.*` are always safe; guard every write with `if (!dryRun)` in a handler. The same model underlies **lenses**: stored, named CypherScript or typed programs that open focused views. A realm can ship reusable lenses in `lenses/`; a world can override them by id.

## `lenses/`

Named focused experiences a realm installs alongside its types, producers and apps. Each `.yml`
file serializes one Lens. The host discovers world-authored lenses first and then installed-realm
lenses; a world lens with the same `id` shadows the realm definition. This is the same precedence
model as realm-bundled apps and lets a world customize an installed experience without modifying
the realm repository.

```yaml
# lenses/account-health.yml
id: account-health
name: Account Health
description: Live account health assembled from the CRM and support systems.
params:
  - name: accountId
    type: STRING
    label: Account
    required: true
spec:
  kind: cypherscript
  script: |
    const accountId = String(lensArgs.accountId || "");
    const result = await gateway.kg.query({
      cypher: `MATCH (a:Account {accountId:$accountId})-[:HAS_TICKET]->(t:SupportTicket)
               RETURN a.name AS account, collect(t) AS tickets`,
      params: JSON.stringify({ accountId }),
    });
    const rows = (result && result.rows) ? result.rows : (result || []);
    await gateway.lens.present({ content: JSON.stringify({
      kind: "account-health",
      rows,
    }) });
presentation:
  href: /apps/account-health.html
```

Fields:

| Field | Required | Description |
|---|---|---|
| `id` | Yes | Stable lens id. A world override uses the same id. |
| `name` | Yes | Human-readable name. |
| `description` | No | Routing and catalogue description. |
| `params` | No | Declared inputs. Types are `STRING`, `INT`, `DATE`, `DURATION`, or `BOOLEAN`; each parameter may declare `label`, `default`, and `required`. |
| `spec` | Yes | Execution definition selected by `kind` (below). |
| `persona` | No | Optional personality slug carried by the opened view. |
| `schedule` | No | Optional cron expression for refresh/change handling. |
| `presentation` | No | Optional top-level surface and/or app `href`. |

Supported `spec.kind` values:

| kind | Shape | Use |
|---|---|---|
| `cypherscript` | `script` | JavaScript/CypherScript that can combine Virtual Cypher, gateway integrations and bounded `gateway.ai.*` calls. |
| `module` | `className`, plus inline `source` or sibling `module`; optional `presentKind`/`dataType` | A typed program Lens whose `retrieve()` returns focus plus structured data. |
| `fixed` | `key`, optional `params` | A host-registered fixed query. |
| `anchor` | `ref` | A typed graph-node anchor. |

A realm-shipped Lens is code, not mutable per-user state: its definition is refreshed when the
realm is updated. One opening's arguments, focus, presentation, Watch snapshots and other user
state remain in the world. An app should invoke a named Lens or view through the host's typed
invocation surface; it should not accept or submit arbitrary Cypher or JavaScript from a browser.

A CypherScript Lens may depend on a reusable **node view** by referencing the view name as a label
inside `gateway.kg.query`, including an inline parameter map. View expansion happens before Virtual
Cypher planning, so the view owns the composable graph selection while the Lens owns procedural
classification and presentation. For example, a `DiseaseTrialRuns` view that returns one
`TrialSearchRun` node can be consumed as:

```javascript
const result = await gateway.kg.query({
  cypher: `MATCH (run:DiseaseTrialRuns {registryQuery:'Long COVID'})
           MATCH (run)-[:RETURNED]->(trial:ClinicalTrial)
           RETURN trial`,
  params: JSON.stringify({}),
});
```

Only identity-preserving node views compose this way. A tabular/projection view is terminal: invoke
it directly through the named-view surface rather than using its name as a label in a larger query.

## `sources.yml` — declaring how a COLLECTION behaves

`producers/` say how to *fetch* records. `sources.yml` says what the collection *is*: how big, what it
can be filtered by, what order it arrives in, how often it changes, and whether it should be mirrored
at all. The platform cannot infer any of that, and getting it wrong is not a performance problem —
it is a correctness one.

The failure that motivated this: a register of ~426,000 planning applications, filterable only by
council, **returned oldest-first with no sort option**. Reading it with a page cap looked prudent and
was silently catastrophic — the records outside the cap were always the most RECENT ones, so a
surface reporting "no application on this lot" was omitting exactly the applications a user was
asking about. Nothing in a producer spec could have expressed that hazard.

```yaml
# sources.yml
sources:
  - name: nsw-planning-register
    producer: applicationsByCouncil        # the producer that reads it
    label: PlanningApplication             # the node label it materializes

    shape: bounded                         # bounded | unbounded | per-key
    cardinality: 426000                    # order of magnitude is enough
    partition: council                     # the ONLY axis the source can filter
    queriedBy: [address, street, lot, date, cost]   # axes users ask on and the source CANNOT filter
    ordering: oldest-first                 # unordered | newest-first | oldest-first | irrelevant
    updates: daily

    sync:
      strategy: mirror                     # mirror | lazy | live
      trigger: on-first-use                # on-first-use | scheduled | manual
      refresh: full-rewalk                 # incremental | full-rewalk
      watermark: DateLastUpdated           # the field that dates a record
      watermarkFilterable: false           # can the SOURCE filter on it? here: no

    completeness:
      declaredTotal: TotalCount            # response field giving the true size of a partition
      aggregatesRequireComplete: true      # withhold derived statistics on partial coverage

    visibility: public                     # public | org | private
```

### The fields that carry real weight

**`ordering`.** The difference between a partial read being a *sample* and being a *lie*. An
unordered source truncated at a cap gives you an arbitrary subset; an `oldest-first` source truncated
at a cap gives you a subset that systematically excludes the present. Only the realm knows which.

**`queriedBy` vs `partition`.** When users query on axes the source cannot filter, every question
needs the whole partition, and partial fetching cannot be made safe by narrowing. This mismatch is
the single best predictor that a collection wants `strategy: mirror` rather than `live`.

**`watermarkFilterable`.** A record may CARRY a last-updated timestamp without the source being able
to FILTER on it. The first permits incremental refresh; the second forces a full re-walk with a local
diff. Assume the wrong one and a day of changes vanishes silently. Declare it.

**`declaredTotal`.** Where the source states a partition's true size, completeness stops being an
assumption and becomes checkable arithmetic.

### `Coverage` — completeness is a fact in the graph, not a hope

A mirrored source records what it actually holds, per partition:

```
(:Coverage:Public {
   source:        'nsw-planning-register',
   partition:     'Inner West Council',
   declaredTotal: 12905,          // what the source says exists
   ingested:      12905,          // what we hold
   completeAsAt:  '2026-07-29T04:10:00Z',
   status:        'COMPLETE'      // COMPLETE | PARTIAL | STALE | FAILED
})
```

Because the engine already knows which labels a query touches, it can attach the matching coverage to
every result through the **existing `{rows, warnings}` envelope** — no new plumbing, and no realm has
to remember to do it. A street-level question carries *"Inner West complete as at 29 Jul"*; a
statewide aggregate carries *"3 of 128 councils ingested — this is not a statewide figure"*.

Two rules follow, and they are not the same rule:

1. **Never block a query on coverage. Always qualify the answer.** Refusing is brittle and teaches
   users to distrust the surface; qualifying composes and stays honest.
2. **Withhold a DERIVED STATISTIC when coverage is inadequate.** An approval rate computed over
   whichever partitions happen to be ingested is not a weak figure, it is a wrong one. This is the
   same discipline as withholding a percentage over a tiny denominator — the denominator here is
   partitions, not rows.

**Coverage is what makes lazy ingestion safe.** Without it, every aggregate over a partially-mirrored
source is quietly incorrect, and the surface cannot tell. With it, `on-first-use` ingestion is honest
and a full statewide mirror becomes an optimisation rather than a correctness requirement — so build
the coverage record BEFORE building any ingestion.

### `visibility: public` — shared nodes, and why the scope differs from `reference/`

Mirrored public data is identical for every user, so mirroring it per world duplicates it, re-crawls
it per user, and lets each copy drift. Nodes from a `visibility: public` source therefore carry the
**`Public`** label and the scope rewriter never scopes them — the same treatment as a REFERENCE
taxonomy, for a very different kind of data.

The distinction matters operationally even though the scoping is identical. A `reference/` vocabulary
is a handful of curated nodes, seeded, static, safe to wipe and rebuild, small enough to project into
a prompt. A mirrored public dataset is hundreds of thousands of rows with a refresh cycle, a staleness
window, and an ingestion job as its only legitimate writer. Treating them as one thing invites a
factory reset that deletes the register, or a schema projection that inlines it.

Two hard rules:

- **Only an ingestion job for a declared `visibility: public` source may write `Public` nodes.** No
  user-facing path may create one, or the label becomes a cross-tenant write primitive.
- **`Public` is opt-in per label and never inferred.** The rewriter's default stays fail-closed at
  PRIVATE; an unregistered label is private, as it is today.

## `reference/`

Reference (catalog / config) data a realm **brings into the KG** — the set of entities a realm's types describe that should exist regardless of what the user has done. Where `producers/` fetch data on demand and `populate` mirrors an external system, `reference/` seeds a fixed, realm-authored dataset: a controlled vocabulary, a lookup catalog, a set of well-known entities. Each `.yml` file in `reference/` is a list of records seeded (idempotently) into the KG on world load.

A record is the **same `{type, data, relations}` shape as the `create_entry` tool**, so it rides the same identity-MERGE and user-anchor handling — no separate write path:

```yaml
# reference/streaming-services.yml — the catalog of services a Movie can be watched on
- type: StreamingService            # a declared type (types/*.yml)
  data: { serviceId: netflix, serviceName: Netflix }
- type: StreamingService
  data: { serviceId: stan, serviceName: Stan }
```

Semantics:

- **Idempotent.** A record whose `type` declares an `identity` property is upserted on that key, so re-seeding on every boot is a no-op (or an in-place update). Types with no identity would duplicate — give reference types an identity.
- **User-anchored reference is per-user.** If the `type` is `userAnchor`, each seeded record gets its `(:AssistantUser)-[:PREDICATE]->(record)` edge automatically — the way to seed a per-user preference (e.g. which services the user subscribes to). Global catalog data uses `userAnchor: false`.
- **Relations resolve like `create_entry`.** An optional `relations: [{ predicate, to: { type, ...keyProps } }]` links a record to another entry that must already exist (seed it first / in another realm's `reference/`), else the record is refused.
- **Merges with virtual data.** A reference type can also be a virtual-join *target* (e.g. `StreamingService` seeded here AND materialized on demand by a producer): both write paths MERGE on the shared identity, so a producer-fetched node picks up the catalog's stable fields.

This lets a realm own its reference data as *data*, not as a hardcoded list inside a query or a producer — the same "it's data, put it in the graph" discipline as types and producers.

## `apis/`

API entries — each `.yml` file in `apis/` is a list of API definitions loaded on world init. Each entry compiles into a typed `gateway.<name>.*` namespace inside `execute_javascript` / `execute_python`.

```yaml
# apis/petstore.yml
- url: https://petstore3.swagger.io/api/v3/openapi.json
  name: petstore
  type: openapi
  auth: api-key
  token-env: PETSTORE_API_KEY
```

### Entry fields

| Field | Required | Notes |
|---|---|---|
| `url` | yes | Spec source. HTTP(S), `file://`, or a bare relative path resolved against the apis.yml file's parent directory (used for vendored specs — see below). |
| `name` | recommended | Gateway namespace — `gateway.<name>.*`. Falls back to a slugified spec title if omitted. **Always set this** in published realms so the prompt examples work regardless of the spec's `info.title`. |
| `type` | no | `openapi` (default) or `graphql`. |
| `auth` | no | `none` (default), `bearer`, `api-key`, `oauth2`. See **Auth** below. |
| `token-env` | with bearer / api-key | Env-var or credential-store key holding the token. |
| `headers` | no | Custom HTTP headers; values support `${VAR}` interpolation from credential store / env. |
| `oauth2` | with `auth: oauth2` | OAuth2 config — see **OAuth2** below. |
| `tags` | no | Allowlist of OpenAPI tag names. Filters huge specs to a coarse subset. |
| `operation-ids` | no | Exact `operationId` allowlist. Composes with `tags` (tags pre-filter, operation-ids picks exact ops). Match is case-insensitive and treats `-`/`/` as `_`, so `repos/get`, `repos-get`, `repos_get` all match. |

### Vendored specs

`url` accepts a bare relative path. The loader resolves it against the file's own parent directory, so realms can ship a hand-curated spec next to their `apis.yml`:

```
realm-hubspot/
└── apis/
    ├── apis.yml          # url: hubspot-crm.json
    └── hubspot-crm.json  # the spec, vendored in-realm
```

Use this when the upstream provider has stopped publishing OpenAPI specs (or never did), or when you want to pin a specific subset of operations and types without depending on a moving public URL. HTTP(S) and `file://` URLs work too — the relative-path mode is just the most ergonomic for vendored specs.

### Auth

Four auth modes plus the implicit headers-only path:

```yaml
# 1. No auth
- url: https://api.example.com/openapi.yaml
  auth: none

# 2. Bearer token (most REST APIs)
- url: https://api.github.com/openapi.json
  name: gh
  auth: bearer
  token-env: GITHUB_PERSONAL_ACCESS_TOKEN

# 3. API key (sent as the header/query the spec declares)
- url: https://petstore3.swagger.io/api/v3/openapi.json
  auth: api-key
  token-env: PETSTORE_API_KEY

# 4. Custom headers only — for APIs that need multiple auth headers
#    (e.g. RapidAPI). No `auth:` field needed.
- url: https://weatherapi-com.p.rapidapi.com
  type: openapi
  headers:
    X-RapidAPI-Key: "${X_RAPIDAPI_KEY}"
    X-RapidAPI-Host: weatherapi-com.p.rapidapi.com

# 5. OAuth2 — see next section
```

Token-env and `${VAR}` values are resolved in this order: world credential store first (set via `set NAME = ...` in chat or via the admin UI), then process env var. Missing creds → the entry is skipped at world load with a logged warning; the API never appears in the gateway.

### OAuth2

For providers that use the OAuth2 authorization-code flow (HubSpot, Slack, Salesforce, GitHub, Google, etc.). The realm ships only the **provider facts** (URLs, scopes, identity introspection). Per-installation client app credentials live in the host admin file `oauth-apps.yml` — **never in the realm repo and never in any user's world**.

```yaml
# realm-hubspot/apis/apis.yml
- url: hubspot-crm.json
  name: hubspot
  type: openapi
  auth: oauth2
  oauth2:
    auth-url: https://app.hubspot.com/oauth/authorize
    token-url: https://api.hubapi.com/oauth/v1/token
    scopes: >-
      crm.objects.contacts.read crm.objects.contacts.write
      crm.objects.companies.read crm.objects.deals.read
    identity:
      url: https://api.hubapi.com/oauth/v1/access-tokens/{token}
      method: GET
      auth: path-token
      account-id-field: hub_id
      display-name-field: hub_domain
```

**`oauth2:` block fields**

| Field | Required | Notes |
|---|---|---|
| `auth-url` | yes | Provider's authorize endpoint. |
| `token-url` | yes | Provider's token endpoint. |
| `scopes` | usually | Space-separated scope list. |
| `client-id` / `client-secret` | NO in published realms | Power-user fallback only — accepts `${VAR}` interpolation. **Production setups put these in the host admin's `oauth-apps.yml`** so the realm stays public and credential-free. |
| `identity` | optional | Introspection block — see below. Without it the connect flow still completes, but the UI shows a generic label instead of the real account. |

**`identity:` block — provider-agnostic introspection**

The `identity:` block tells the host how to call the provider's `/userinfo` or `/whoami` endpoint and pull an `accountId` + display label out of the JSON response. This is what lets the UI show "Connected as alice@acme.com" rather than just "Connected".

| Field | Required | Notes |
|---|---|---|
| `url` | yes | Endpoint URL. May contain the literal `{token}` placeholder, substituted with the URL-encoded access token (used by HubSpot's path-token style). |
| `method` | no | `GET` (default) or `POST`. |
| `auth` | no | How to send the token: `bearer` (default — `Authorization: Bearer <token>`), `path-token` (interpolated into `{token}`, no header), `header:<NAME>` (custom header), `query:<NAME>` (URL query parameter). |
| `account-id-field` | yes | Top-level JSON field name to read as the stable account identifier. |
| `display-name-field` | no | Top-level JSON field name for the human-readable label. Falls back to `account-id-field` if absent or blank in the response. |

Examples:

```yaml
# Google (bearer token, /userinfo)
identity:
  url: https://www.googleapis.com/oauth2/v3/userinfo
  account-id-field: email
  display-name-field: name

# GitHub
identity:
  url: https://api.github.com/user
  account-id-field: login
  display-name-field: name

# Slack
identity:
  url: https://slack.com/api/auth.test
  method: POST
  account-id-field: user_id
  display-name-field: user
```

**Where the OAuth client credentials live** (host-admin-managed)

`client-id` and `client-secret` for the provider's Public App belong in the host installation admin directory (path is host-specific, but the file shape is portable):

```yaml
# admin/oauth-apps.yml
apps:
  hubspot:
    client-id: 12345-abcdef-...
    client-secret: secret-blah
  slack:
    client-id: ...
    client-secret: ...
```

The map keys (`hubspot`, `slack`, …) match the `name:` field of the matching `apis.yml` entry. Hot-reloaded — admins can edit the file without restarting the host.

A world can override the installation default by writing the same shape to `<world>/config/oauth-apps.yml` — useful when one team needs its own provider app under its own brand.

**Lookup order** for client_id / client_secret:
1. `<world>/config/oauth-apps.yml` (per-world override)
2. Host admin `oauth-apps.yml` (installation default)
3. `${VAR}` from the realm's `oauth2.client-id` / `client-secret` (escape hatch for power users)

If none resolve, the provider's status reports `not-configured` and Authorize returns an actionable error message instead of silently failing.

**End-user UX**

End users **never** paste tokens, IDs, or secrets. Settings → Connected Services → click **Authorize** → consent on the provider's page → done. ConnectedAccounts holds the real account label; `gateway.<name>.*` is live in chat.

**Token refresh** is automatic — the host's `OAuth2Service` rotates expired access tokens using the stored refresh token and writes back any new refresh token the provider issues (HubSpot rotates them on every refresh).

## `src/` and `tests/` — hand-authored TypeScript handlers

OpenAPI and MCP cover what an external system *already* exposes. Realms can also ship **hand-authored TypeScript** under `src/api/`, in two forms:

- **Namespace functions** — an exported `async function` becomes a `gateway.<namespace>.<name>(...)` method. Use these to shape, guard, or compose raw API primitives. Covered in [Handler signature](#handler-signature).
- **Type methods** — an exported `class` that `extends Entity` defines a *type* whose async methods are callable on an in-scope object (`movie.streaming({ country })`). Use these to give a realm's entities behaviour. Covered in [Type methods](#type-methods--classes-that-extend-entity).

Both compile to the same `dist/` and run in the same sandbox as LLM-generated code (no in-server JS engine), calling back through `gateway.<raw-api>.*` for primitives — no HTTP-from-inside-HTTP overhead, no second auth dance.

### When to add TS handlers

Reach for `src/` when you want to:

- **Shape a raw API into idiomatic methods** the LLM uses well (e.g. `docsEditor.getOutline` over `docs.documentsGet` + heading-walking).
- **Enforce safety invariants** that can't be expressed in the raw spec (e.g. a propose/apply edit flow with a revisionId guard, where you DON'T expose the raw mutating method to the LLM).
- **Compose multiple primitives** into one call (e.g. paginate, retry, dedupe, post-process).

Realms without TS handlers continue to work exactly as before — `src/` is purely additive.

### Realm project layout

A realm with TS handlers is a real TypeScript project. The framework provides scaffolding (`embabel-realm new`, in flight), but the shape is small:

```
realm-name/
├── realm.yml                    # existing
├── apis/                       # existing — raw OpenAPI surface
│   └── openapi.json
├── package.json                # devDeps: @embabel/runtime-types, typescript, vitest
├── tsconfig.json               # strict; output mode for runtime is CJS
├── tsconfig.build.json         # outDir: dist; module: CommonJS
├── vitest.config.ts
├── src/
│   ├── api/
│   │   └── docs-editor.ts      # one TS file per namespace; filename → namespace
│   ├── lib/                    # internal helpers (not exposed)
│   └── types/                  # shared TS types
├── tests/
│   └── docs-editor.test.ts     # Vitest, runs in pure Node against mockGateway
├── .embabel/
│   └── gateway.d.ts            # GENERATED: typed view of the host's gateway
└── dist/                       # GENERATED: compiled JS + manifest.json
```

`@embabel/runtime-types` provides `mockGateway<T>(impl)` for tests and the `embabel-build-manifest` CLI used by `npm run build`. It's pulled in as a git dependency (no npm-registry hosting required).

### Handler signature

Every exported async function with a `(ctx, args)` signature is registered as a gateway method.

```ts
// src/api/docs-editor.ts
import type { GatewayContext } from "../../.embabel/gateway";

/**
 * Return the heading outline of a Google Doc. PREFER this over
 * `gateway.docs.documentsGet` when you only need structure.
 */
export async function getOutline(
  ctx: GatewayContext,
  args: { documentId: string },
): Promise<{ revisionId: string; spans: Array<{ anchor: string; level: number; text: string }> }> {
  const doc = await ctx.docs.documentsGet({ documentId: args.documentId });
  return { revisionId: doc.revisionId ?? "", spans: /* walk doc.body.content */ [] };
}
```

The host's manifest extractor walks the TypeScript AST, converts the args parameter type and the unwrapped return type to JSON Schema, and writes them to `dist/manifest.json`. The first JSDoc paragraph becomes the LLM-visible description — **invest in JSDoc**: it's how the LLM picks the right method when multiple gateway surfaces overlap.

#### Authoring before `sync` — `GenericGatewayContext`

`embabel-realm sync` (which generates `.embabel/gateway.d.ts` with the host's fully-typed `GatewayContext`) is still in flight. Until it lands, a realm whose handlers only need to *call* gateway ops — not the static types of their results — can type `ctx` as **`GenericGatewayContext`** from `@embabel/runtime-types` (a loose `Record<string, Record<string, (args) => Promise<unknown>>>`). The manifest extractor reads each handler's `args` and return types, **not** `ctx`, so the typed LLM surface is identical either way.

A namespace function that only needs to *call* gateway ops can type `ctx` loosely:

```ts
// src/api/weather.ts
import type { GenericGatewayContext } from "@embabel/runtime-types";

/** Current conditions for a city. */
export async function current(
  ctx: GenericGatewayContext,
  args: { city: string },
): Promise<unknown> {
  return ctx.openWeather.getCurrent({ q: args.city });
}
```

Caveat: the `Record` index access trips `noUncheckedIndexedAccess`, so leave that
flag off in `tsconfig.json` when using `GenericGatewayContext` (the generated
`GatewayContext` has concrete properties and doesn't need it). Once `sync` lands,
swap `GenericGatewayContext` → `GatewayContext` for full result typing — nothing
else changes. The same applies to a type method's `this.gateway`.

### Type methods — classes that extend `Entity`

A namespace function is a free function on a gateway surface. A **type method** is
a method *on an in-scope object* — `movie.streaming({ country: "us" })`, not a
bare `gateway.movie.streaming(...)`. You author one by exporting a class that
extends `Entity` (from `@embabel/runtime-types`). Its fields are the type's
shape; its async methods are the affordances.

```ts
// src/api/movie.ts
import { Entity } from "@embabel/runtime-types";
import type { StreamingShow } from "../types/movie";

// The gateway ops this type calls, typed. Until `embabel-realm sync` generates the
// host's `GatewayContext`, the realm types the slice it uses and reads it through
// `this.api`, so bodies and return types are fully typed — no `unknown`.
interface MovieGateway {
  streamingAvailability: { getShow(args: { id: string; country: string }): Promise<StreamingShow> };
}

/** A film in the knowledge graph. Identity is `imdbId`. */
export class Movie extends Entity {
  imdbId!: string;
  title?: string;

  private get api(): MovieGateway {
    return this.gateway as unknown as MovieGateway;
  }

  /** Where this movie is streaming in a country (ISO-3166 alpha-2, lowercase). */
  async streaming(args: { country: string }): Promise<StreamingShow> {
    return this.api.streamingAvailability.getShow({ id: this.imdbId, country: args.country });
  }
}
```

There is no `ctx`/`self` plumbing: `this` is the object the host hydrated from the
entity's fields, and `this.gateway` is the injected context (typed loosely until
`sync` lands — read it through a typed `this.api` accessor, as above, for real
result types). Each method's single `args` parameter and return type drive the
JSON Schema; the first JSDoc paragraph is the LLM-visible description, exactly as
for namespace functions.

Extending `Entity` is what makes the host recognise `Movie` as a type, and it
brings **`neighbors()`** for free — graph navigation (`movie.neighbors({ hops })`)
every type inherits with no per-type code. `Entity` is a normal class, so a realm
can introduce its own intermediate base to share behaviour across its types; the
manifest walks the whole base chain. Plain data the user writes that has no
behaviour of its own (e.g. `MovieRating`) stays a plain `interface` — promote it
to a class only when it grows methods.

**Testing.** `entityForTest` builds a real instance with its fields set and a
mock gateway injected — the same shape the host uses at runtime — so a method is
tested in milliseconds with no live server:

```ts
// tests/movie.test.ts — hermetic, no live API
import { entityForTest, mockGateway } from "@embabel/runtime-types";
import type { GenericGatewayContext } from "@embabel/runtime-types";
import { Movie } from "../src/api/movie";

const getShow = vi.fn().mockResolvedValue({ streamingOptions: { au: [] } });
const movie = entityForTest(
  Movie,
  { imdbId: "tt0113451" },
  mockGateway<GenericGatewayContext>({ streamingAvailability: { getShow } }),
);

await movie.streaming({ country: "au" });
expect(getShow).toHaveBeenCalledWith({ id: "tt0113451", country: "au" });
```

**Runtime.** For `class Movie extends Entity` to instantiate in the sandbox, the
compiled handler must `require("@embabel/runtime-types")` for the base class.
`embabel-build-manifest` vendors the runtime's CommonJS build into the realm's
`dist/node_modules/@embabel/runtime-types/`, so the seeded handler bundle is
self-contained — you don't manage this.

`realm-movie` is the worked example: a `Movie` class with `streaming`, `details`,
and `rate` plus inherited `neighbors`.

#### Verbs on virtual types — pure compute and effectful write-back

A type method works the same whether the instance is a persisted entity or one
materialized on demand by a virtual join (a `GitHubIssue`, a `HubSpotContact`).
So a virtual type's class gives its on-demand instances behaviour:

- **pure** verbs compute over the instance's own fields, no I/O (`issue.ageDays()`,
  `issue.needsTriage()`, `pr.isReadyForReview()`);
- **effectful** verbs write back to the source through `this.gateway.<ns>.*`
  (`issue.close()`, `issue.addLabels('stale')`, `pr.requestReviewers('alice')`),
  and may reuse the host `gateway.sql` / `gateway.cypher` ops the generated
  `GatewayContext` exposes.

A read materialises transient nodes and rolls them back; an effectful verb commits
to the real source (the rollback never touches that side-effect). A program reads,
then acts: `const rows = await gateway.cypher.query({ cypher }); hydrateByType(rows,
{ GitHubIssue }, gateway).filter(i => i.needsTriage()).forEach(i => i.addLabels('stale'))`.
`realm-github` is the worked example (`GitHubIssue` / `GitHubPullRequest`).

### Manifest format

Auto-generated by `embabel-build-manifest` (provided by `@embabel/runtime-types`), so realm authors never hand-author it. The host reads it at install time.

```json
{
  "version": 1,
  "generatedAt": "2026-05-15T00:00:00Z",
  "entries": [
    {
      "namespace": "docs_editor",
      "name": "getOutline",
      "description": "Return the heading outline …",
      "inputSchema": { "type": "object", "properties": { "documentId": { "type": "string" } }, "required": ["documentId"] },
      "outputSchema": { "type": "object", "properties": { /* … */ } }
    }
  ]
}
```

| Field | Source | Purpose |
|---|---|---|
| `namespace` | `src/api/<filename>.ts` (kebab-case → snake) | Gateway namespace; LLM sees this camelCased (`docs_editor` → `docsEditor`). |
| `name` | exported function name | Method name on the namespace. |
| `description` | first JSDoc paragraph | LLM-visible documentation. |
| `inputSchema` | TS type of `args` parameter | JSON Schema; drives the typed surface on the LLM side. |
| `outputSchema` | TS type of the unwrapped `Promise<T>` | Same. |

### Build and test cycle

```bash
npm install            # @embabel/runtime-types from git, typescript, vitest
npm run typecheck      # tsc --noEmit
npm test               # vitest run — mockGateway against your handlers
npm run build          # tsc → dist/*.js (CommonJS) + manifest.json
```

`mockGateway<WorldTools>` lets you write hermetic tests in pure Node:

```ts
import { mockGateway } from "@embabel/runtime-types";
import type { WorldTools } from "../.embabel/gateway";
import { getOutline } from "../src/api/docs-editor";

it("extracts headings", async () => {
  const gateway = mockGateway<WorldTools>({
    docs: { documentsGet: vi.fn().mockResolvedValue({ revisionId: "r1", body: { content: [/* … */] } }) },
  });
  const outline = await getOutline(gateway, { documentId: "abc" });
  expect(outline.spans).toHaveLength(2);
});
```

No host running, no Docker, no live API.

### Install-time behaviour

When the host installs a realm:

1. **Clone** the realm repo (existing).
2. **If `package.json` has a `build` script, run `npm install && npm run build`.** Produces `dist/`. Skipped silently when `node`/`npm` isn't available; OpenAPI methods still work.
3. **Read `dist/manifest.json`** if present; register each entry as a gateway method alongside OpenAPI-derived ones.
4. **At sandbox session start**, copy each realm's `dist/` into `/world/realm-handlers/<realm-name>/`. The generated `gateway.js` `require()`s these modules and routes realm-method calls locally instead of via HTTP.

A handler call from inside the sandbox:

```
LLM-emitted script
   gateway.docsEditor.getOutline({ documentId })
       ↓ generated gateway.js routes to local handler
   require('/world/realm-handlers/google/api/docs-editor.js').getOutline(gateway, args)
       ↓ handler calls back through gateway for raw API
   gateway.docs.documentsGet({ documentId })   ←  HTTP to the host gateway
       ↓ returns
   handler shapes the result
       ↓
LLM-emitted script receives the typed outline
```

The raw `gateway.docs.*` call goes via HTTP (existing path). The wrapper dispatch is local — no extra hop.

### Trust model

Handlers run with the same trust as LLM-generated code (both are inside the sandbox). The handler's value over a raw OpenAPI call is in **what's exposed**, not where it runs:

- If a realm hides a method from its `apis.yml` allowlist *but* uses it inside a handler, the LLM cannot call the raw method directly.
- If a realm exposes both the raw method and a wrapper, the LLM can call either — the wrapper is a recommendation, not a barrier. Skills (`SKILL.md` files) are the right way to make sure the LLM picks the wrapper.

### Author tooling

The host ships a thin wrapper (`embabel-realm`) that drives the JVM-side surface generation. Most realm authors only ever need `npm run build` for everyday work; `embabel-realm sync` regenerates `.embabel/gateway.d.ts` when the host's surface changes (new realms, new APIs).

```bash
embabel-realm sync                        # from inside any realm repo
embabel-realm sync ~/dev/realm-hubspot     # or pass an explicit path
```

## `mcp/`

MCP server configurations — each file lists Model Context Protocol servers to connect.

**Prefer `apis/` (a vendored OpenAPI spec) over an MCP server whenever the
integration is API-backed.** A vendored spec gives the LLM full typed
request/response shapes instead of MCP's flat tool descriptions, needs no
Docker, starts instantly, and is testable without a container. Every realm the
product ships has migrated this way (Maps, arXiv, Wikipedia, Brave, YouTube).
Reach for `mcp/` only when there is no API to vendor — e.g. a server that
wraps a local binary or a stateful protocol — or when the user explicitly
brings their own MCP server.

```yaml
# mcp/example.yml
- name: example-server
  description: "What the server's tools do, written for the LLM"
  command: docker
  args: ["run", "-i", "--rm", "example/example-mcp:latest"]
  env:
    EXAMPLE_API_KEY: "${EXAMPLE_API_KEY}"
```

MCP servers are lazy-loaded — the Docker container starts on first tool use, not on world init. Multiple users with the same MCP config share a single container via the host's MCP client cache.

## `commands/`

Slash command mappings — map `/command` names to actions.

```yaml
# commands/fix-issue.yml
command: fix-issue
actionName: fix-issue
description: "Fix a GitHub issue"
```

## `webhooks/`

Webhook registrations — declare webhooks the realm wants to receive. When the realm is installed and the host has a public URL, these are registered with the external service.

```yaml
# webhooks/github-issues.yml
- name: github-issues
  description: "Receive GitHub issue events"
  source: github
  events: [issues, issue_comment]
  action: webhook-github-issue
  register:
    tool: create_repository_webhook
    args:
      owner: "{{owner}}"
      repo: "{{repo}}"
      config:
        url: "{{webhook_base_url}}/api/v1/webhooks/github-issues"
        content_type: json
        secret: "{{GITHUB_WEBHOOK_SECRET}}"
      events: ["issues", "issue_comment"]
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Webhook identifier |
| `description` | No | What events this webhook handles |
| `source` | Yes | Source identifier (matches webhook endpoint path) |
| `events` | No | Event types to subscribe to |
| `action` | Yes | Action name to execute when webhook fires |
| `register` | No | Auto-registration config (tool + args) |
| `register.tool` | Yes (if register) | Tool to call for registration |
| `register.args` | Yes (if register) | Arguments with `{{template}}` variables |

Template variables in `register.args` are resolved from:
- World config (`config.yml`)
- Credential store (secrets set by the user)
- Well-known variables: `{{webhook_base_url}}`, `{{owner}}`, `{{repo}}`

The bare-webhook flow — payload arrives, gets wrapped in a `WebhookEvent`, the named action fires — stays as documented above. For richer integration that emits **typed signals** into the host's consequence engine, use `events/` (next section).

## `events/` — event ingestion (forward-looking)

Unifies push (webhook) and pull (polling) sources behind a single contract: **emit typed `Signal`s into the host's consequence engine.** A signal type is a `DomainType` declared in `types/` whose `parents` includes `Signal`.

This section is **forward-looking** — the spec is settled but specific hosts may still be implementing it. Existing webhook receivers in `webhooks/` continue to work in parallel.

### Webhook event source

```yaml
# events/stripe.yml
- type: StripeEvent          # name of a signal type declared in types/
  webhook:
    signature: hmac-sha256   # one of: hmac-sha256, hmac-sha1, jwt, none
    signature-secret: STRIPE_WEBHOOK_SECRET
    tenancy: path-token      # one of: path-token, payload-field, header
    mapping:                 # type-property → JSONPath into the payload
      id: "$.id"
      occurredAt: "$.created"
      sourceKind: "stripe"
      sourceId: "$.id"
      eventType: "$.type"
      amount: "$.data.object.amount"
      currency: "$.data.object.currency"
      customerId: "$.data.object.customer"
    tier-when:                   # optional — override default tier
      INTERRUPTIVE: "{{ payload.type == 'charge.failed' }}"
      TIMELY:       "{{ payload.type == 'invoice.upcoming' }}"
```

The host receives the webhook, verifies the signature, resolves the tenant, projects the payload through the `mapping` into a `StripeEvent` instance, and emits it as a `Signal` into the consequence engine.

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | Name of a type declared in this realm (or another loaded realm) whose `parents` includes `Signal`. |
| `webhook.signature` | yes | Signature scheme the host's built-in verifiers handle. |
| `webhook.signature-secret` | conditional | Env-var name holding the shared secret. Required for any non-`none` scheme. |
| `webhook.tenancy` | yes | Strategy for routing the inbound webhook to a world. |
| `webhook.mapping` | yes | Map of type-property → JSONPath. Every required property of the `Signal` parent (`id`, `occurredAt`, `sourceKind`, `sourceId`) must be covered. |
| `webhook.tier-when` | no | Tier-override map. Each entry's value is a Jinja boolean expression evaluated against the parsed payload. First true wins; default tier is `AMBIENT`. |

### Polling event source

For services without webhook support — or where polling is preferable — declare a `poll` block instead of (or in addition to) `webhook`. Polling reuses the host's task scheduler and persists a per-`(user, type)` cursor so each run only sees what's new.

```yaml
# events/linear.yml
- type: LinearIssue
  poll:
    every: 10m
    api: linear                # the realm's already-learned API (apis/linear.yml)
    method: list_my_issues     # method name on that API
    args:
      assignee: "{{ user.email }}"
    cursor:
      param: updated_after     # the API parameter that takes the cursor value
      from: $.updatedAt        # how to extract the next cursor from each result
    mapping:
      id: "$.id"
      occurredAt: "$.updatedAt"
      sourceKind: "linear"
      sourceId: "$.id"
      title: "$.title"
      state: "$.state.name"
      url: "$.url"
```

| Field | Required | Meaning |
|---|---|---|
| `poll.every` | yes | Cadence (e.g. `5m`, `1h`). |
| `poll.api` | yes | Name of an API declared in `apis/` (this or another realm). |
| `poll.method` | yes | Method name on that API. |
| `poll.args` | no | Arguments to the call. Jinja-templated against `{ user, cursor }`. |
| `poll.cursor.param` | no | API parameter the host populates with the persisted cursor. |
| `poll.cursor.from` | no | JSONPath into each returned result, used to compute the next cursor (the maximum value across the batch becomes the new cursor). |
| `poll.mapping` | yes | Same shape as the webhook `mapping` block. |

A realm may declare both `webhook:` and `poll:` for the same type — the host prefers webhook delivery and uses polling as a backstop for catch-up after downtime.

### Why this matters

Both sources produce `Signal`s of the realm-declared type. From there, the consequence engine, triage rules, persistence (`SignalRecord`), notifications, and chat surfacing are all type-aware: `signal.type.isAssignableFrom(StripeEvent)` is a real predicate, not a string match.

No JVM bytecode is shipped — realms that need behaviour beyond mapping should expose it via `actions/` (LLM-driven) or `mcp/` (sandboxed servers).

## `handlers/` — event handlers (TypeScript reactions to signals & cron)

Where `events/` *produces* signals, `handlers/` *reacts* to them. A realm can ship ready-made **event handlers** the user activates — TypeScript programs that run when a matching signal arrives (from `events/`, a webhook, or any source) or on a cron schedule.

> Not to be confused with the `src/` **TypeScript handlers** that implement a realm type's gateway methods. Those are gateway *code*; these are *reactions*. (Same substrate — sandboxed TS — different job.)

A handler is the event-side mirror of a lens: a lens *queries → declares focus*; a handler *is handed a signal → queries/judges → takes an effect*. It's authored as TypeScript run through the host's per-user code-mode runtime — the same vibe-codeable substrate, so a handler can be generated or hand-written.

```yaml
# handlers/pr-review.yml
- id: pr-review                       # stable id (also the cron job name `handler-<id>`)
  name: Flag review requests on my PRs
  description: When a review is requested on one of my PRs, notify me
  match:
    signalType: github.pr_review_request   # a Signal type name (from events/ or types/); "*" = any
  schedule: "0 0 8 * * *"            # optional 6-field cron — fires on a schedule too (omit for signal-only)
  autonomous: false                  # ships OBSERVE-ONLY; user opts into external effects
  spec:
    kind: typescript
    module: pr-review.handler.ts      # sibling file, inlined at load (or inline `source: |`)
```

A handler may declare `match` (signal-triggered), `schedule` (cron-triggered), or both.

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable id; the world shadows a realm handler of the same id. |
| `name` | yes | Display name. |
| `description` | no | One line shown in the "available handlers" list. |
| `match.signalType` | no | Signal type that fires it — a JVM signal (`EmailSignal`) or a realm signal (`github.pr_review_request`). `*`/omitted = any signal. |
| `schedule` | no | 6-field cron expression. A scheduled handler is registered on the host's normal cron path (it *is* a cron job). |
| `autonomous` | no | `false` (default) = observe-only: it reads, judges, and logs what it *would* do, mutating nothing external. `true` lets it apply write effects. |
| `spec.kind` | yes | `typescript`. |
| `spec.source` / `spec.module` | yes | Inline TS, or a sibling file inlined at load. |

### What the handler sees

The triggering event is bound in scope as one normalised shape, whatever the signal type:

```ts
signal.id, signal.typeName, signal.subject, signal.occurredAt
signal.source.{ kind, id, label, url }
signal.properties.<field>   // type-specific fields — for a realm signal these are the event's
                            // mapping keys (repo, number, author, …); read them from here
trigger                     // "signal" | "cron"
now                         // ISO-8601 timestamp of this run
dryRun                      // true when being tested — GUARD every external effect with if (!dryRun)
```

It reacts through the typed `gateway.*` surface — read with `gateway.kg.query`, judge with `gateway.ai.classify`, act with realm verbs or `gateway.notifications.createNotification`. Reads and `gateway.ai.*` are always safe; **guard writes with `if (!dryRun)`**.

```ts
// pr-review.handler.ts
if (trigger !== "signal" || !signal) { console.log("not a signal event"); return; }
const { repo, number, author } = signal.properties;
const [owner, name] = String(repo).split("/");
const commits = await gateway.gh.reposListCommits({ owner, repo: name, author, per_page: 1 });
const isNew = commits.length === 0;
console.log(isNew ? `new contributor ${author}` : `${author} has prior commits`);
if (isNew) {
  console.log(dryRun ? `WOULD notify about PR #${number}` : `notifying about PR #${number}`);
  if (!dryRun) await gateway.notifications.createNotification({ event: "NewContributorPR", source: "pr-review", url: signal.source.url });
}
```

### Activation

A realm handler is **available, not firing**, until the user activates it (adopts it into their own handlers). The host surfaces every realm handler in its "which handlers are active" UX and over MCP; activating one respects the realm's `autonomous` default. A scheduled handler, once activated, is registered as an ordinary cron job — there's no separate handler scheduler. World handlers (`config/handlers/`) and realm handlers merge, the world shadowing a realm on id collision.

## `decorations/` — scheduled KG node enrichment

A realm drives enrichment of nodes already in the knowledge graph by declaring **decoration manifests**. Each manifest binds a realm-declared `action` to a set of Neo4j labels and a cadence; the host's decoration scheduler walks candidate rows, invokes the action per node, and persists the result.

This is the right shape for "keep these rows fresh", "add my realm's structured data to entities the user already has", and "re-summarise on a TTL" — without the realm needing to write any host code, manage scheduling, or implement dedup.

### Manifest

```yaml
# realm-hubspot/decorations/contact-enrich.yml
name: hubspot-contact-enrich       # required; stable kebab-case id (used as stamp key)
targetLabels: [HubSpotContact]     # required; ≥ 1 Neo4j label this decoration targets
action: enrichHubSpotContact       # required; an action declared in this realm's actions/
tickInterval: PT6H                 # ISO-8601 duration; how often the scheduler checks (default PT6H)
batchSize: 25                      # candidate rows per tick (default 25)
concurrency: 4                     # parallel decorate calls within a tick (default 4)
refreshAfter: P7D                  # ISO-8601 duration; null/omitted = one-shot
```

A file may carry a single manifest or a YAML list of them (`- name: ...` per entry).

### The action contract

The referenced action receives one node's identity + a world user binding and returns a structured `DecorationResult` describing what to write. The host owns persistence; the action stays pure.

**Input bindings** (the action's `inputs:` block in `actions/<name>.yml` must accept these):

| Binding | Type | Meaning |
|---|---|---|
| `nodeId` | string | The candidate node's stable id |
| `nodeName` | string | The node's display name |
| `nodeLabels` | list&lt;string&gt; | Every Neo4j label on the node |
| `nodeProperties` | object | Map of every property currently on the node |
| `userId` | string | The owning world user |

**Output type**: `DecorationResult` (a host-provided domain type). Action declarations set `outputType: com.embabel.assistant.kg.decoration.DecorationResult`.

```ts
interface DecorationResult {
  // Property keys to MERGE onto the node. Setting `description`
  // here updates the node's display description. Pre-existing
  // properties are preserved unless an entry here overrides them.
  propsToSet?: Record<string, unknown>

  // Relationships to MERGE from the node to other entities.
  // Idempotent — re-running doesn't duplicate edges.
  edgesToMerge?: Array<{
    type: string             // relationship type, e.g. "HAS_HUBSPOT_DEAL"
    targetNodeId: string     // the other end's stable id
    targetLabel?: string     // optional; helps some graph stores
    properties?: Record<string, unknown>
  }>
}
```

Empty result is fine — the scheduler stamps the row regardless, so the decorator doesn't re-run before its `refreshAfter` (or never, if one-shot). Return empty when the action surveyed the row and decided there was nothing to add (e.g. "no signature in this email", "no Wikipedia article for this person").

### Lifecycle

1. **Discovery.** At host startup, the decoration loader walks every installed realm for `decorations/*.yml` (or `*.yaml`).
2. **Wiring.** Each manifest becomes a scheduled decorator on the host's `TaskScheduler`, ticking at `tickInterval`. The decorator's stamp property is `<name>DecoratedAt`.
3. **Per tick.** A label-filtered Cypher predicate selects up to `batchSize` rows whose stamp is missing OR (when `refreshAfter` is set) older than the refresh window. Rows are dispatched to `decorate(...)` calls in parallel up to `concurrency`.
4. **Per node.** The host invokes the referenced action with the input bindings. On success, the host persists `propsToSet` and `edgesToMerge`, then stamps the row. On exception, the row stays un-stamped — next tick retries.

### Examples

**Single-shot enrichment from external API:**

```yaml
# realm-wikipedia/decorations/topic-wiki.yml
name: wikipedia-topic
targetLabels: [Topic]
action: fetchWikipediaTopic
tickInterval: PT12H
batchSize: 50
concurrency: 4
# no refreshAfter — Wikipedia summaries change so slowly that one-shot is right
```

**Periodic resummarisation:**

```yaml
# realm-hubspot/decorations/deal-summary.yml
name: hubspot-deal-summary
targetLabels: [HubSpotDeal]
action: summariseHubSpotDeal
tickInterval: PT2H
batchSize: 25
concurrency: 4
refreshAfter: P14D
```

**Second-order entity discovery (Bills from Billers):**

```yaml
# realm-finance/decorations/bills-from-biller.yml
name: bills-from-biller
targetLabels: [Biller]
action: scanBillsForBiller
tickInterval: PT6H
batchSize: 25
concurrency: 4
refreshAfter: P1D
```

The action body queries email threads from the biller's domain, extracts `:Bill` rows, and returns them as `edgesToMerge` entries with `type: "ISSUED_BILL"`.

### Choosing parameters

| Knob | Picking it |
|---|---|
| `tickInterval` | How quickly new rows of `targetLabels` should get decorated. For freshly-arriving entities, ~1h. For one-shot enrichments, can be 24h+ — the predicate empties after first pass. |
| `batchSize` | Throttle per-tick LLM / HTTP cost. 25 is generous; drop to 10 for expensive actions. |
| `concurrency` | Parallel calls within a tick. 1 for pure-Cypher actions (parallelism = contention). 4-8 for LLM / HTTP-bound actions. Honor your provider's rate limits. |
| `refreshAfter` | Set when re-decoration earns its rent (re-summarise after activity, re-fetch slowly-changing facts). Omit for genuinely one-shot enrichments. |

### Anti-patterns

- **Self-persisting actions.** Don't have the action call gateway methods to write graph properties directly. Return them via `DecorationResult` — the host's persistence + stamping is one atomic-ish step that keeps "what this decorator changed" auditable.
- **Cross-realm dependencies.** A manifest references one action from its own realm. If you need behaviour from another realm, call it through the gateway from inside the action body, don't pull it via manifest composition.
- **Sweep when an event works.** If the entity gets an enrichable signal on creation (a webhook fires, an EmailSignal lands), prefer the event path. Decorations are for what *can't* be done event-driven — refreshes, federations, cross-source joins, slow-moving fact maintenance.

## `apps/`

HTML apps the realm ships. They're served at `/apps/{name}` alongside the user's vibe-coded apps and the world template's apps. Resolution order is:

1. `<world>/data/apps/{name}` — user-owned (vibe-coded), highest priority
2. `<world>/config/apps/{name}` — world-template apps shipped with default-world
3. `<world>/config/realms/<realm>/apps/{name}` — realm-bundled apps (this directory)

A user can shadow a realm-bundled app by vibe-coding one with the same filename. Realm apps are read-only from the user's perspective; they're refreshed whenever the realm is updated.

```
apps/
├── github-dashboard.html
└── pr-review-board.html
```

Realm apps must use the same architecture as vibe-coded apps: tool-gateway calls via `fetch('/api/v1/tools/{name}')`, no direct external fetches. They have access to all the user's tools (MCP, learned APIs, etc.) because they run in the user's authenticated session.

**Prefer invoking a named Lens over calling raw tools.** An app that posts to `/api/v1/lenses/{id}/invoke` gets a result the realm has already shaped, scoped and caveated; an app that assembles raw tool calls duplicates that reasoning in a browser where it cannot be tested or reused. Keep the app to presentation: it should choose a Lens and render what comes back, never decide what to fetch. This also honours the rule below — an app must not accept or submit arbitrary Cypher or JavaScript from a browser.

**What "no direct external fetches" does and does not cover.** The prohibition is on the app reaching a third-party *data* API itself — that would bypass the gateway's auth, scoping, quotas and provenance, and would leak keys into the browser. It does not prohibit ordinary outbound *navigation*: an `<a href>` deep link to an external site (a map, a source document, a public register entry) is how a surface cites its sources and should be encouraged. Embedding third-party runtime assets — a map SDK, tiles, remote fonts — is a different question again: it adds a network dependency and a privacy surface the host does not mediate, so treat it as a deliberate choice rather than a default, and never let a provider's key reach the page. A realm that wants map rendering without that dependency can deep-link out instead, which also keeps provider terms about attribution and caching simple to honour.

## `artifacts.yml`

Optional. Register custom artifact types the realm introduces, in addition to the host's built-ins (`DOCUMENT`, `APP`, `CODE`, `DATASET`, `DIAGRAM`).

```yaml
- name: NOTEBOOK
  directory: data/notebooks
  defaultExtension: ipynb
- name: TEMPLATE
  directory: data/templates
  defaultExtension: jinja
  servable: true
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | UPPERCASE type identifier |
| `directory` | Yes | Path under world root. **Conventionally `data/<subdir>`** so the artifacts survive factory reset. |
| `defaultExtension` | No | File extension hint for new artifacts |
| `servable` | No | If `true`, artifacts of this type are served via the same path resolution as `APP` |

## `prompts/`

Prompt contributions — optional content **appended to every chat system prompt** for every user with the realm installed. Currently supports `examples.md`.

> **⚠️ Tax on every chat turn.** Bytes you add here are paid by every user, every turn, even when they're not invoking your realm. Hosts enforce a soft size ceiling (Embabel's reference host: 1024 bytes/realm, configurable via `assistant.realm-loader.prompt-max-bytes`); over-budget realms still load but the host surfaces a warning in the world problems list.
>
> **Treat `prompts/` as a pointer, not a manual.** Tell the LLM the capability *exists* and where to find the routing detail. Put the actual workflow examples in a [Skill](#skills--skill-descriptors), which the LLM activates on demand only when relevant — paid only when used.

### Recommended shape

A one-or-two-sentence pointer is the canonical pattern:

```markdown
HubSpot CRM is available — contacts, companies, deals, tickets, owners,
pipelines, associations. Activate the **`hubspot-crm`** skill via the
skill tool before making any HubSpot call; the skill carries the
workflow patterns, namespace conventions, and required-field details.
```

The substantive routing content (tool names, code-mode call shapes, edge cases, idiomatic patterns) goes into `skills/<realm>-skill/SKILL.md`. The skill loader makes it activatable; the LLM pulls it in only when it decides the user's intent matches.

### Anti-pattern

```markdown
User: "Show me the open issues in embabel/agent"
→ Call github tool → list_issues (GitHub issues, not world tasks)

User: "Create a GitHub issue for the memory leak bug"
→ Call github tool → issue_write (NOT world task creation)

[… ten more examples, code-mode call sketches, edge cases …]
```

This was the original convention and is being deprecated. Bulk routing examples in `prompts/` cost every user on every turn; the same examples in a Skill cost only users actively asking about that capability. Migrate existing realms by trimming `prompts/examples.md` to a pointer and moving the body into the realm's Skill.

## `skills/`

Skills follow the [Agent Skills specification](https://agentskills.io/specification). Each skill is a subdirectory containing a `SKILL.md` file.

```
skills/
└── creative-thinking/
    ├── SKILL.md
    └── references/
        └── techniques.md
```

Skills are loaded as references — the agent can activate them on demand for specialized tasks.

### `choices` payloads — asking the user to pick

When a skill flow needs the user to pick from a **small closed set** (a score, one of several
matching records), it must not guess, pick silently, or bury the options in prose. Instead the
script returns a `choices` payload as its result and the assistant presents the question and
options, then STOPS — no recording or lookup action until the user picks. The shape:

```json
{"kind": "choices",
 "question": "<one short question>",
 "options": ["<option>", "..."],
 "context": { "<ids the follow-up turn needs>": "..." },
 "hint": "Present these options to the user and wait for their pick."}
```

- **`options`** — the closed set, as display strings. Keep it small (≤ 10).
- **`context`** — carry the ids the next turn needs (an `imdbId`, a record key) so the follow-up
  never re-resolves what this turn already looked up.
- **`hint`** — one sentence for the presenting LLM; not shown to the user.

The payload travels as a **tool result**, so every surface renders at its own fidelity: the host's
own chat presents the options as a short list (or a native widget where the host has a `choices`
renderer), while an MCP client is told — via the host's MCP `instructions` — to use its most
structured input affordance (a form or selector where it can render one). Do **not** tunnel HTML
for this; ship the semantic payload and let each surface render it.

Exemplar: `realm-movie`'s `skills/movie/SKILL.md` — rating a film when no score was given
(options `"1"`–`"10"`, `context.imdbId`), and disambiguating a title with several OMDb matches
(one option per candidate, candidates in `context`).

## `personalities/`

Each subdirectory under `personalities/` is one persona the host can run the assistant as — its voice, behaviours, guardrails, and display name. The host renders the chat system prompt by including Jinja templates from the active persona's directory; switching personality is a directory swap, not a prompt rewrite.

```
personalities/
└── roger/
    ├── identity.yml
    ├── personality.jinja
    ├── behaviours.jinja
    ├── guardrails.jinja
    ├── response_format.jinja
    └── verbosity.jinja
```

- **`identity.yml`** — the only YAML in the bundle. `name:` is the assistant's display name under this persona (shown on chat bubbles, used by the LLM when introducing itself). `source:` is optional and is set automatically to `realm` for realm-shipped personalities; only set it explicitly when overriding the default.

```yaml
# personalities/roger/identity.yml
name: Roger
source: realm
```

- **`*.jinja`** files — included into the chat system prompt at the matching slots. `personality.jinja` carries the voice / character, `behaviours.jinja` carries do/don't rules, `guardrails.jinja` carries safety constraints, `response_format.jinja` carries output-shape rules, `verbosity.jinja` carries length / pacing rules. All five are optional — omit any file you don't need and the host skips its include line.

A realm's personality is referenced by slug (its directory name) from a `focuses/` file (`defaultPersona: roger`) or directly via the host's persona picker. Slug must be unique across the world; on collision with a world-authored personality, the world wins.

## `focuses/`

A **focus** is a named scoping of the chat surface — a subset of realms whose skills the chat LLM can see, plus an optional persona override. The point is routing reliability: a 30-skill world gives even a sharp realm skill room to lose to a competitor; strip the competitors out and the LLM has nothing to confuse the right skill with.

```yaml
# focuses/movies.yml
name: movies
displayName: Movies
description: "Recommend, rate, and recall films"
icon: "🎬"
defaultPersona: roger
realms: [movie]
builtins: true
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Stable slug — used by the `/focus <name>` slash command, the picker, and persistence. |
| `displayName` | No | Human label for the picker. Falls back to `name`. |
| `description` | No | One-line summary for the picker tooltip / chat badge. |
| `icon` | No | Emoji or single character for the picker. |
| `defaultPersona` | No | Persona slug to activate when a session enters this focus. Resolved against the same registry that `personalities/` populates — world-authored or realm-shipped. Null = keep the world's current persona. |
| `realms` | No | Realm names whose skills stay visible in this focus. Empty = no realm skills, only built-ins. |
| `tools` | No | By-name allowlist of additional tools/skills to pull into this focus regardless of realm membership. Additive with `realms`. |
| `builtins` | No (default `true`) | Whether to keep host-provided chat tools (memory, repository, reply, progress, the code runners). Set false only for narrowly-scoped focuses ("read-only public-info kiosk"). |

### `/focus` slash command

The host's `/focus <name>` slash command binds the user's chat session to a focus. `/focus off` clears the binding; bare `/focus` lists available focuses. Binding takes effect from the next chat turn; the conversation transcript stays under whatever scope was in force when each message was sent.

When a focus declares `defaultPersona`, the host swaps **both** the persona's Jinja includes (the voice the LLM speaks in) **and** the persona's `identity.yml#name` (the display name the LLM introduces itself as, and the label on the chat bubble) for the focused session. Toggle focus off and the world's default persona returns. The change is in-session — the world-level `activePersonality` is not rewritten.

### Discovery and precedence

World-authored focuses live at `config/focuses/<name>.yml`; realm-shipped focuses live at `<realm-dir>/focuses/<name>.yml`. On slug collision, the world entry wins (user-authored overrides realm-shipped). Realm focuses carry an internal `source = realm` marker for UI disambiguation.

---

## Installation

Realms are installed as git repos cloned into the world's `config/realms/` directory:

```
world/
└── config/
    └── realms/
        ├── github/        ← cloned from git
        ├── research/      ← cloned from git
        └── my-custom/     ← manually created
```

Default realms are listed in the world's `config/realms.yml`:

```yaml
# config/realms.yml
- name: research
  repo: https://github.com/embabel/realm-research.git
```

These are cloned automatically on first world provisioning.

## Realm Discovery

Realms are discoverable via the host's directory system:
- GitHub organizations / users configured in `realm-sources`
- Repos matching `realm-*` naming convention are listed
- Users can search and install realms via chat or the host UI

---

## What's intentionally not in a realm

- **JVM bytecode**, native libraries, scripts to be executed in-process.
- **Spring beans, classpath contributions, host configuration changes.**
- **User credentials.** Realms reference secrets by env-var name; the user supplies the secret out-of-band (host UI, env, etc.).
- **Per-user state.** A realm ships templates and types; the *world* holds the per-user instances.

If a capability needs real code, ship it via `actions/` (LLM in the loop), `mcp/` (sandboxed server, arbitrary code), or as a host-level extension out of band.

## Conventions

- **Naming**: lowercase-hyphenated for ids (realm name, action name, command name); UpperCamelCase for type names.
- **YAML**: prefer multi-doc files only when the entries are tightly related; otherwise one file per item.
- **Descriptions are LLM-readable**: write descriptions assuming an LLM planner is the primary reader.
- **Stable ids**: changing a `name` is a breaking change for any installed world that wired against it.

## Versioning

Realms follow semantic versioning in `realm.yml`. The `version` is informational; hosts may track it to detect upgrades but the contract is at the directory-and-field level — adding a new optional field is a minor change, removing or renaming a required field is a major one.

The spec itself is versioned by this repository's git history. Hosts target a spec revision; realms declare compatibility informally for now.

---

## License

This specification is released under the Apache License, Version 2.0. See [LICENSE](LICENSE).

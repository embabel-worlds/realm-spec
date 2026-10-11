# Embabel Realm Specification

Realms are self-contained, declarative bundles of agent capabilities that can be installed into an Embabel-based host. Each realm is a git repository (no JVM bytecode, no native binaries) that provides actions, types, APIs, MCP servers, commands, webhooks, event sources, agents, skills, prompts, and apps. The host platform reads the realm and wires its contents into the running agent.

The [hosted execution contract](HOSTED_EXECUTION.md) defines captured execution, channel
publication, finite capacity and credential mediation. It also records the governed reference
implementation's current support. Trusted-host examples below do not authorize a governed
guest to bypass those checks.

> **Status: living draft.** Sections marked _forward-looking_ describe shape that is settled but may still be in implementation across hosts. Other sections describe portable declarations and trusted-host formats; capability support differs by host profile. Where this document cites concrete defaults or behaviour of "the reference host", it means the host implementation this spec is developed against; those values are informative, not part of the contract.

**Writing a captured realm in TypeScript?** [TypeScript realms](TYPESCRIPT_REALMS.md) walks through
`defineRealm` from end to end: handlers and their context, credentials, APIs, channels, sources and
consumers, dependencies, producers, graph queries, goals, lenses, watches, apps, write proposals,
and the owner approvals each one needs.

**Exposing an existing application to worlds?** The
[Realm Publishing Protocol](https://github.com/embabel-worlds/publisher) (proposal, Apache 2.0) lets an
application declare its own types, lookups, verbs and identity bridges, so a world installs it from
its URL alone, with no realm authored by hand. [PUBLISHERS.md](PUBLISHERS.md) says how an Embabel
world maps a publisher onto Virtual Cypher and code mode.

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
├── icon.svg               # Realm icon (optional) — any path, named by realm.yml `icon`
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
├── views/                # Named Cypher views (YAML, optional) — runnable by name, and a node view composes as a label
│   └── my-views.yml
├── rules/                # DERIVE rule sets (YAML, optional) — derived labels/relationships, one rule set per file
│   └── my-rules.yml
├── lenses/               # Named lenses (YAML, optional) — captured handlers or host-specific definitions
│   └── my-lens.yml
├── apis/                 # API entries (YAML)
│   └── my-api.yml
├── keys.yml              # The API keys the realm needs, and how to check them (optional)
├── credentials.yml       # Captured realms: the credentials the owner binds (optional)
├── src/                  # Hand-authored TypeScript handlers (optional)
│   └── api/
│       └── my-handlers.ts
├── tests/                # Vitest specs for handlers
│   └── my-handlers.test.ts
├── wasm/                 # Handler source for the wasm host (optional)
│   └── handlers.js
├── mcp/                  # MCP server configurations (YAML)
│   └── my-server.yml
├── commands/             # Slash command mappings (YAML)
│   └── my-command.yml
├── webhooks/             # Webhook registrations (YAML)
│   └── my-webhook.yml
├── events/               # Event ingestion — push + poll
│   └── my-source.yml
├── data-pipes.yml        # Captured channel source and consumer declarations
├── channels/             # Realm-shipped provider connector drafts (YAML)
│   └── my-channel.yml
├── agents/               # Agents — named colleagues whose routines react to signals/cron, adopted by the world
│   └── my-handler.yml
├── decorations/          # Scheduled KG node-decoration manifests
│   └── my-decoration.yml
├── apps/                 # Bundled HTML apps served at /apps/{name}
│   └── my-dashboard.html
├── hints/                # Tips the host UIs show users of this realm (YAML, optional)
│   └── tips.yml
├── artifacts.yml         # Custom artifact type registrations (optional)
├── prompts/              # Prompt contributions
│   └── examples.md
├── skills/               # Skills (Agent Skills spec)
│   └── my-skill/
│       └── SKILL.md
├── notebook/             # Reusable sets of slots a persona keeps across a conversation
│   └── my-set.yml
├── personalities/        # Voice / behaviour bundles (Jinja templates)
│   └── my-persona/
│       ├── identity.yml
│       ├── brief.yml     # optional; the persona for a single non-chat call
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
icon: icon.svg
category: developer
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
| `icon` | No | An image the realm ships, as a path **relative to the realm root**. See [Icons](#icons). |
| `category` | No | What the realm is for: one id from the published list of categories. See [Category](#category). |
| `tags` | No | Free-text keywords, for finding the realm. They are not its category. |
| `maturity` | No | The author's own readiness claim: `experimental`, `beta`, `stable` or `deprecated`. Absent means the realm makes no claim — which is **not** a claim of being finished. See [Maturity](#maturity). |
| `host` | No | Execution host for the Realm's Functions: `docker` or `wasm`. Absent means the platform infers it from what's on disk. See [Execution hosts](#execution-hosts). |

### Icons

A realm may ship an image for hosts that draw a realm list — a launcher, a
directory, a settings pane:

```yaml
icon: icon.svg          # or assets/movie.png, or anything under the realm root
```

**Optional in every sense.** A realm without one is not diminished; hosts that
drew a letter tile before keep drawing it. Nothing else in the manifest depends
on it, and a host that ignores the field entirely is still conformant.

**It must be a file the realm ships**, addressed relative to the realm root.
Hosts are required to refuse anything else — an absolute path, a `..` that
climbs out of the realm, or a URL:

| Declared | Result |
|---|---|
| `icon.svg` | Served, if the file is there |
| `assets/movie.png` | Served, if the file is there |
| `../../elsewhere.svg` | Refused |
| `/etc/passwd` | Refused |
| `https://example.com/pixel.gif` | Refused |

The URL case is the one worth stating plainly, because it looks convenient. A
remote icon makes every host that renders a realm list fetch a third party on
the user's behalf — telling whoever serves the image which user is browsing
which realms, from what address, and handing the realm author a hit counter on
someone else's UI. A realm's icon travels with the realm, like the rest of it.

SVG is the sensible default (small, sharp at any tile size). Raster formats —
PNG, JPEG, WebP, AVIF, GIF, ICO — are also fine. Keep it square and legible at
about 40px: this is a tile, not an illustration.

**Apps declare their own**, separately and by the web's usual means — a
`<link rel="icon" href="…">` in the app's `<head>`, pointing at a file beside
it in `apps/`. Same principle, existing convention, no new field.

### Maturity

```yaml
maturity: experimental   # or: beta, stable, deprecated
```

The author is the only party who knows whether a realm is finished, so this is
where that is said. It is a **claim, not a measurement** — nothing inspects a
realm to verify it, and no host may imply otherwise.

Four values, compared case-insensitively: `Experimental` in a manifest and
`experimental` in a host's configuration are one claim. No other cleverness — no
plural folding, no synonyms, and no implied ranking between the four.

**Absence is not a claim of being finished.** Hosts are required to treat a
missing `maturity` as *unstated*, never as `stable`. Most realms that exist say
nothing, and a host that read stability out of silence would be marking every
one of them as ready. Hosts are required to treat an **unrecognized** value the
same way — unstated — rather than refusing the realm or guessing at what was
meant: a realm is an arbitrary git repository, and one misspelled line in one
repository must not break a directory everybody browses.

**It is not a tag.** Tags are free text, for finding things (`crime`, `maps`,
`open-data`). A readiness judgment read off free text fails silently in the one
direction that matters: a realm tagged `experimantal` is offered to everybody as
though finished, and nothing anywhere says so. So this is its own field, with a
closed set of values.

**What a host may do with it** *(informative — the behaviour of the reference
host, not part of the contract)*:

| Claim | Reference host behaviour |
|---|---|
| `experimental` | Installing requires the user's **explicit confirmation**: the host asks, carrying the realm's own warning, and only a yes proceeds. Surfaces that list realms leave it out by default, behind a visible opt-in that says how many were left out. An already-installed experimental realm is never hidden — it is part of that world whatever its author thinks of it. |
| `beta`, `stable`, `deprecated` | Shown as a badge where realms are listed. No other behaviour today. |

Two consequences worth stating, because they are easy to get backwards:

- **Hiding is a display default, not a gate.** A realm left out of a list is
  still installable by name, and the confirmation is what actually stands
  between a user and an experimental realm. A host that filtered a list and
  installed silently would have removed the gate rather than added one.
- **A host can only act on a claim it can read.** A directory that lists realms
  it has not installed has to carry `maturity` through from wherever it discovers
  them; one that discovers realms without reading their manifests (a repository
  scan working within an unauthenticated API budget, say) carries no claims, and
  must then show everything rather than infer.

### Category

```yaml
category: finance
```

What the realm is **for**, as one id from a closed list. It is how a store is
browsed by somebody who does not yet know which realm they want: a short list of
purposes to choose from, rather than every word any author has used.

**The list is published, and it is the authority.** It lives at
[`realm-categories.yml`](https://github.com/embabel/default-installation/blob/main/realm-categories.yml)
in `embabel/default-installation`, and is carried, whole, in the realm catalogue
built from it. Each entry has an `id`, a `label`, an `icon` and a `description`.
This document does not repeat the ids, because a copy here would drift from the
list realms are judged against. A category is added by a change to that file,
and an id is never renamed or reused once realms declare it.

One value, compared case-insensitively. A realm has one category: the thing it is
mainly for. A realm that could sit in two picks the one a person looking for it
would try first.

**Check it before publishing.** A manifest is judged against the list with no
token and no network:

```
python3 scripts/build-realms-index.py --check path/to/realm.yml
```

from a checkout of `embabel/default-installation`. It fails on a missing category
and on an id that is not listed, naming the ids it could have been.

**Absence is not an error.** Hosts are required to treat a missing `category` as
*uncategorised*, and an **unrecognized** value the same way, rather than refusing
the realm or guessing at what was meant — for the reason given under
[Maturity](#maturity): one misspelled line in one repository must not break a
directory everybody browses. An uncategorised realm is still listed, still found
by search and still installable.

**It is not a tag.** Tags are free text, for finding things, and nothing reviews
them. Many say how a realm is built (`openapi`, `skills`) rather than what it is
for, and most are used by one realm only. A realm keeps its tags as search
keywords; it says what it is for here.

**What a host may do with it** *(informative — the behaviour of the reference
host, not part of the contract)*: the catalogue carries a realm's `category` only
when it is on the list, and a store may offer the categories as a way to browse,
each with the list's own label and icon. A host that discovers realms without
reading their manifests carries no categories, and must then show those realms as
uncategorised rather than infer one.

## `actions/`

Me keeps this legacy host configuration outside Realm execution. Use the
[captured handler migration](HOSTED_EXECUTION.md#legacy-executable-migration) for Me Realms.

Action specifications — YAML files that define executable operations. The host's planner picks them by their declared input / output types and runs them as GOAP actions. The `stepType` discriminator selects the shape; the framework's `NameOrClassTypeIdResolver` resolves either a registered short name (e.g. `action`, `goal`) **or a fully-qualified class name** (`com.example.MyCustomActionSpec`) to an `ActionSpec` class on the classpath. Host extensions can use either path.

| `stepType` value | Shape |
|---|---|
| `action` | Framework `PromptedActionSpec` — typed LLM call producing `outputTypeName` |
| `<FQN>` | Any other `ActionSpec` subtype on the classpath. Use this when shipping a host-extension shape whose YAML contract isn't yet stable enough to claim a short name. |

**Short name vs FQN dispatch.** A short name like `action` is a public contract; once realm authors write it, you can't change the spec's shape without breaking their YAML. Reserve short names only for shapes that have stabilised. FQN dispatch lets a host iterate freely on field names, parsing, and dispatch semantics without committing to a YAML slot upstream. The flip side: an FQN that appears in published realm YAML is itself a public identifier — a host that moves or renames the class must keep the old name resolvable, or every realm that wired against it breaks.

Example host extension (the assistant's predicate-driven `PolicyActionSpec`):

```yaml
# realm-email/actions/policy_email_unreplied.yml
stepType: com.embabel.world.policy.spec.PolicyActionSpec
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
stepType: com.embabel.world.policy.spec.PolicyActionSpec
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

A boolean expression over the matched signal's fields. Parser source: `com.embabel.world.policy.PolicyExprParser`. Grammar (today; expect additions as concrete rules need them):

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

Me keeps this legacy host configuration outside Realm execution. For Me Realms, declare a
version-1 [captured goal](HOSTED_EXECUTION.md#me-captured-goal-profile) that binds one approved
handler to Realm-declared input and output types; a legacy file of the shape below inside a
captured Realm is reported and never parsed. See the
[captured handler migration](HOSTED_EXECUTION.md#legacy-executable-migration).

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

A type may also declare itself a **spine** (`spine:`) — a shared identity that records from *other* realms resolve onto, so that a CRM's customer, a helpdesk's company and a billing system's account are one node. That, and the rule for choosing between `parents:` and `spine:`, is [VIRTUAL_CYPHER.md §5.4.1–5.4.3](VIRTUAL_CYPHER.md); it is the foundation of every cross-realm join that is not already on a person or an email domain.

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

A type whose `parents:` includes `Signal` (the host-defined signal base type) is a **signal type** — automatically eligible for the consequence engine, triage rules, and persistence as a `SignalRecord`. See [`events/`](#events--event-ingestion) below.

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
- **The host can add an implicit edge to the acting human principal's `AssistantUser` node.** The
  compatibility default is `(entry)-[:OWNED_BY]->(principal)` — fine for most human-authored types.
  Service principals have no implicit anchor. When the predicate reads more naturally in the other
  direction, declare a `userAnchor:` on the type:

```yaml
# types/movies.yml
- name: MovieRating
  description: "The user's score for a Movie."
  userAnchor:
    predicate: RATED          # uppercase; stored uppercase
    direction: from-user      # `principal -[RATED]-> rating` (default is `from-entry`)
  properties:
    imdbId: "IMDb id of the rated Movie."
    rating:
      type: int
      description: "1–10."
```

| Field | Default | Notes |
|-------|---------|-------|
| `predicate` | `OWNED_BY` | Cypher-style relationship name. Required when the key is declared. Stored uppercase. |
| `direction` | `from-entry` | `from-entry` → `(entry)-[:PREDICATE]->(principal)`. `from-user` → `(principal)-[:PREDICATE]->(entry)`. Pick whichever reads naturally. |
| (sentinel) | — | Set `userAnchor: false` to opt the type out of the implicit edge entirely (reference data, type registries, etc.). |

#### Explicit relations between entries

`create_entry` accepts an optional `relations:` array so a realm's skill can wire the new entry to another entry that already exists in the host-bound visibility scope. The host emits each requested edge on save; if any target can't be found in that scope, the whole create is refused (no orphan node, no orphan edge). A cross-context relation requires an explicit policy-authorized bridge. Example shape, taken from the movie realm's `rate-movie` skill:

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

Each relation is `{predicate, to: {type, ...keyProps}}` — `to.type` names the target's type, and the
remaining `to.*` fields are the key properties the host MATCHes against on target nodes in the same
host-bound visibility scope. Cross-context matching is never implicit. Use this pattern any time a realm's typed records form a small
connected graph (rating → movie, comment → ticket, note → contact, etc.) — the same graph is then
walkable by Cypher and feeds the recall path automatically.

### Populating types from an external system (deterministic, no code)

The patterns above cover types the *user* creates. A realm can also declare a type that the host **populates automatically from a connected external system — deterministically, with no LLM and no Kotlin/Java in the realm.** A structured record (a CRM contact, an issue, a calendar attendee) is already typed at the source, so extracting it with an LLM is wasteful and error-prone; instead the realm declares a *projection* in property `metadata:` and the host's projector does the rest.

This builds on a small canonical-entity model the host ships: within one host-bound visibility scope,
a `Contact` is a `Person` resolved by email. The host-side merge key is
`(worldId, visibilityScopeId, type, email)` even though realm YAML does not repeat the scope fields.
`visibilityScopeId` is `WORLD` for world-visible data and `contextId` for context-private data.
Declare a **mirror type** that `parents: [Contact]` and annotate each property:

```yaml
# types/hubspot.yml — populated from HubSpot CRM, no Kotlin in the realm
- name: HubSpotContact
  parents: [Contact]
  visibility: internal          # machinery, not a user-browsable repository type
  userAnchor: { predicate: OWNED_BY, direction: from-user }
  properties:
    email:                      # the deterministic merge key, and the spine it keys
      identity: true
      hub: Person
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
| `identity: "true"` | This field's value is the email portion of the **merge key**: records with the same `(worldId, visibilityScopeId, type, email)` resolve to one canonical `:Person` (no LLM entity resolution). Also unioned onto the Person's `emails`. |
| `hub: <Spine>` | **The opt-in.** This field's value keys the named spine — `Person`, `Organization`, or a spine a realm declares with `spine:`. Without a `hub:` a type is never canonicalized, whatever its `identity`. May sit on a property other than the identity one, when what identifies the record (a CRM id) is not what identifies the entity (a website). Writable first-class (`hub: Person`) or under `metadata:`. See [VIRTUAL_CYPHER.md §5.4](VIRTUAL_CYPHER.md). |
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
4. **materializes** them — and any `brings` sub-graph — as transient nodes carrying the extra `:Virtual` label, a `dateRetrieved` timestamp, and the host-bound `worldId`, `contextId`, and access-policy revision (with the acting principal retained separately for audit);
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

`virtualJoins` fields: `anchorLabel`, `relationship`, `keyField`, `recordKeyField` (defaults to `keyField` — a same-property id-match), `producer`, optional `materializedKeyField` (the property on every fetched TARGET record that holds this join's key — see *Finding a virtual node by its key* below), optional `brings` (declared sub-graph), `maxAnchors`/`maxFanoutTotal` (caps). For a join to an **external-identity node** (a bridge like `GitHubIdentity` / `HubSpotOwner`), declare a `resolve:` rule chain + `writeThrough`/`refreshAfter` instead — see **Identity bridges** below (`persist: true` is the older eager-only form). A list with more than one entry, or any join that can fan in, requires an `identity` property so convergent paths dedupe to one node.

The query may only reach a virtual label by **traversing a declared join from a bound anchor** — a naked `MATCH (hc:HubSpotContact)` is rejected. Every materialized node carries the extra `:Virtual` label, a `dateRetrieved` ISO-8601 timestamp, and the host-bound `worldId`, `contextId`, and access-policy revision (so the normal scope rewriter matches it) — bookkeeping that `labels()`, `keys()` and `properties()` leave out, so a fetched node reads as the stored record would ([VIRTUAL_CYPHER.md §2](VIRTUAL_CYPHER.md#2-the-execution-model)); the user's query runs through the rewriter unchanged, and the whole materialization is rolled back when the query completes.

A query may also reach a virtual node by **pinning the anchor with a literal** — `MATCH (g:GitHubIdentity {login:'octocat'})-[:RAISED]->(i:GitHubIssue)` — even when no `GitHubIdentity{login:'octocat'}` exists in the graph. The literal (inline `{...}` **or** a `WHERE alias.login = '…'`) seeds a transient anchor, so a producer can be keyed on a *named* identity (any GitHub login, not just the connecting user's), fetched with the connecting user's credentials. Multiple joins onto the same virtual node compose: `(me)-[:RAISED]->(i)<-[:ASSIGNED]-(:GitHubIdentity {login:'octocat'})` materializes both sides and intersects them.

**Finding a virtual node by its key.** A join may declare `materializedKeyField` — the property on every fetched record of the TARGET that holds the join's key:

```yaml
- name: BiblePerson
  virtualJoins:
    - anchorLabel: BibleNameQuery     # a lookup anchor: identity `name`
      relationship: NAMED
      keyField: name
      recordKeyField: nameQueried
      materializedKeyField: name      # every BiblePerson record carries the looked-up name in `name`
      producer: biblePeopleByName
```

Then the target can be matched by that property directly, with no door written: `MATCH (p:BiblePerson {name:'Moses'})` — or `WHERE p.name = 'Moses'`, `WHERE p.name IN [...]`, or a value bound upstream — is answered as if `(:BibleNameQuery {name:'Moses'})-[:NAMED]->(p)` had been written, and `p` anchors any join that leaves it (`(p)-[:FATHER*]->(a:BiblePerson)`). The query's own predicate still applies to the fetched rows with Cypher's semantics, so a producer that matches keys case-insensitively may fetch rows an exact `=` then filters out. The declaration is required: a target property that merely shares the key's name is never treated as the key, because fetching by a coincidence of spelling answers a different question with full confidence. Without it the bare match is still rejected as a naked scan, and the rejection names the keyed form when one is declared. When several joins declare a `materializedKeyField` the query pins, the first in declaration order is taken.

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
| `sql` | a SELECT against a host-configured realm/world `datasource`, or a read-only stored procedure's result set (`procedure:`) | keys expand into `IN (…)`; rows are the records; SELECT-only. The host mediates approved credentials and operations; governed captured callers require a retained resource receiver. A `procedure:` is called once per key on a read-only datasource and rolled back after the read — see Virtual Cypher §5.15.1 |
| `compute` | an in-process computation over the keys | scores / rollups / synthesis — no external I/O; *local*, so NOT a RemoteRepository |
| `vector` | top-k **semantic similarity** to the anchor | for joins with no key — similarity *is* the join (related docs/chunks); rides the host embedder |
| `generative` | **GENERATES** the edge (resumably) rather than reading it — an LLM's world knowledge (`SIMILAR_TO`, `IN_INDUSTRY`) or a code function | pluggable generator (`llm` \| `function`); keeps generating; resolves each answer onto the type spine; provenance-stamped |
| `aggregate` | **REDUCES** an anchor's connected neighborhood to ONE node (fan-IN) — e.g. a per-principal or per-organization summary distilled from many rows | gathers via a scoped graph read; delegates the reduction to an existing LLM aggregation (`synthesize`/`summarize`/…); TTL-cache = periodic refresh |

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
- **Rejection feedback.** Constraints alone are not enough when the filtered property is one the generator
  cannot know precisely from memory — an exact runtime, a release year, a page count. So after each round the
  host feeds the REJECTED candidates back to the generator **with the real values they were rejected on**
  (`The Kid (runtimeMinutes=68)`), taken from the resolved record. The generator re-aims from evidence
  instead of guessing again, and a narrow range (`runtimeMinutes >= 80 AND <= 90`) stops starving. This is
  automatic for an `llm` generator: the host appends the correction itself, so a realm prompt needs no new
  variable and cannot forget to opt in. A `function` generator gets the typed `constraints` and evaluates
  them itself, so it is not sent the feedback. Coverage only — the query's `WHERE` is still the filter of record.
- **Starvation is reported, never silent.** If a round produces real candidates and the query's filters reject
  every one, the result carries a `FILTER_STARVED` warning naming the steer, the filters, and a sample of the
  near-misses with their values — enough for the answer to say "18 films matched your taste, but the shortest
  ran 94 minutes" rather than a bare "no results". Read the `warnings`, always.
- **Fill the whole type.** A producer materialising a typed node fills that type's FULL property surface
  (via `resolveVia.project`), not just its identity.
- **Provenance.** Each record is stamped `_source` (the generator kind — `llm`/`function`), `_confidence`,
  `_asOf`.

`cache:` is orthogonal to kind (`none` / `ttl` / `session` / `immutable`).

#### `kind: aggregate` — a fan-IN summary NODE

Every other producer is **fan-OUT**: one anchor → many target records. An `aggregate` producer is the
**fan-IN** mirror: it gathers the anchor's connected neighborhood and **reduces it to ONE node**. Use it when
the reduction should itself be a node you can traverse to and cache — a per-principal summary, a per-org rollup, a
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
  identityField: anchorKey       # ONE node per bound anchor inside the host-bound world
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
**Keep every hop pattern-bound.** The probe follows `MATCH` patterns. A node re-bound out of a list — `WITH collect(run) AS runs … UNWIND runs AS f MATCH (f)-[:HAS_JOB]->(j)` — is NOT probed for its joins: the second hop fetches nothing and the query returns no jobs, with no warning (verified 2026-09-23). Narrow with `WITH run ORDER BY … LIMIT n` and hop from `run` itself. `OPTIONAL MATCH` over a virtual hop is likewise not probed; use `MATCH`.

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

So `WHERE i.html_url CONTAINS 'acme-corp/widgets'` turns `is:issue author:X {filters}` into `is:issue author:X repo:acme-corp/widgets` — one scoped search instead of fetching the author's thousands and intersecting in the graph. The mapping is declarative and source-specific; the engine knows nothing of `repo:`.

**Only a LITERAL is pushed.** `run.created_at >= '2026-09-16T00:00:00Z'` renders into the source's filter; `run.created_at >= toString(datetime() - duration({days: 7}))` does not — the value is not known when the fetch is planned, so the fetch is broad and the comparison is applied in the graph. A view's declared params become literals before the query is read (VIRTUAL_CYPHER §7.6.1), which is how a windowed view gets a pushed-down window: take `since` as a parameter and let the app or the asker supply the date. A relative window ("the last 7 days") cannot be pushed by any spelling; say so in the view's description and bound the fetch with `paging.maxPages`.

**Three consequences of "attached" predicates, all verified the hard way (2026-09-23):**

1. Every predicate the engine attaches to the target node (the shapes in VIRTUAL_CYPHER §7.6.1) is part of the **fetch's cache key** — and attachment does not stop at a `WITH`: `MATCH …->(run) WITH run WHERE run.status = 'completed'` is attached exactly as if it were in the MATCH's own WHERE, and so is a wrapped one (`toInteger(run.id) = 123`). So is the **`LIMIT` of a terminal query** — each LIMIT value is its own read, on a `WITH` or on the `RETURN`. Two views over the same door whose attached sets or limits differ re-read the source separately, even inside the TTL. To make several views share ONE cached fetch: filter on **projected variables** (`WITH run, run.created_at AS createdAt, run.status AS status WHERE createdAt >= $since AND status = 'completed'` attaches nothing) and limit a terminal result by **list slice** (`ORDER BY … WITH collect(row) AS rows UNWIND rows[0..$limit] AS row`), never by LIMIT. But a predicate on a projected variable does **not** bound the anchors of a following hop — the hop is then refused as too wide — so a view that narrows and hops keeps ONE `LIMIT`, on the `WITH` directly before the hop, carrying its order key: `WITH run, createdAt ORDER BY createdAt DESC LIMIT $n MATCH (run)-[:HAS_JOB]->(j)` both shares the read and bounds the hop (a LIMIT that feeds a later stage sets no demand target). A `WITH` between that LIMIT and the hop hides it again. To look ONE record up for a hop, rank it first and take one (`WITH run, CASE WHEN toInteger(run.id) = $id THEN 0 ELSE 1 END AS pick ORDER BY pick LIMIT 1 MATCH (run)-[:HAS_JOB]->(j) WITH j, pick WHERE pick = 0`) rather than filtering on the id. Measured on a `periods:` door: these shapes took a 12-view app from 91 s to a few seconds, every view 0 calls after the first read.
2. **Two traversals of the same door in one query share ONE fetch, with every attached predicate from both.** A summary over all runs followed by a second `MATCH` over the same door `WHERE f.conclusion = 'failure'` silently narrows the FIRST traversal too, and the summary describes failed runs only — a wrong figure with no warning. Wrapping the predicate in a function does not help (§7.6.1: wrapping is still attached). Filter the second traversal on projected variables, or sort-and-`LIMIT` on a `WITH`, so nothing extra is attached.
3. A predicate that is attached is also what `pushdown:` sees; one that is not attached is never pushed. The two mechanisms read the same set.

> **Verify that a pushdown actually narrows — some sources ignore unknown filters SILENTLY.** The engine cannot tell a filter the source honoured from one it discarded: both return 200 with records. A source that responds to an unrecognised filter key by returning the *entire unfiltered collection* turns a typo, a renamed upstream field, or an optimistic guess into a full-collection scan that looks like a success — the query still returns correct rows (the graph filters what pushdown didn't), so nothing fails; you just quietly fetch everything, every time. This is real: the NSW planning feed used by `realm-nsw-property` returns all 426,096 records for a misspelled filter and never errors.
>
> Before declaring a `pushdown:` rule, call the source twice — once with the filter, once without — and confirm the **counts differ**. Declare rules only for keys you have proven narrow, and say so in a comment. When a source's filter surface is partly unsupported, the honest producer declares the few verified keys and leaves the rest to graph-side filtering; document which properties do *not* push down, because a query author will otherwise assume a `WHERE` on any property is cheap.

##### Declared pushdown for query, table, file and feed producers

`remote` is not the only kind that can filter at its source. A `sparql`, `sql`, `cypher`, `tabular` or `feed` producer declares `pushdown:` too. Each entry names a property the source can filter on, the operators it applies, and the type its values take at the source:

```yaml
- kind: sparql
  name: saintsOfCountry
  endpoint: https://query.wikidata.org/sparql
  keyVar: country
  query: |
    SELECT ?country ?saint ?died WHERE {
      VALUES ?country { {{keys}} }
      ?saint wdt:P27 ?country ; wdt:P570 ?died .
      {{filter:died}}                       # the filter goes HERE, before the label lookups
      ?saint rdfs:label ?saintLabel . FILTER(LANG(?saintLabel) = "en")
    }
  pushdown:
    - property: died
      type: dateTime                        # string | integer | decimal | boolean | date | dateTime | iri
      ops: [GREATER_THAN_OR_EQUAL, LESS_THAN]   # omit to allow every operator the type supports
```

Where the filter goes depends on the kind:

| Kind | Where the filter is applied |
|---|---|
| `sparql` | At its `{{filter:<property>}}` slot, as `FILTER(<expr> <op> <literal>)`. `expr` defaults to `?<property>`. For an aggregate, declare `having: true` with the aggregate as `expr` (`expr: "COUNT(DISTINCT ?s)"`, slot after `GROUP BY`), and the slot renders `HAVING(…)`. |
| `cypher` | At its `{{filter:<property>}}` slot, as ` AND (<expr> <op> $param)`, so place it after an existing condition (`WHERE o.customer IN $keys {{filter:total}}`). `expr` is required (`expr: "o.total"`). |
| `sql` | Appended to the generated statement as `AND (<column> <op> :param)`. The property is the column. No `expr`: the statement stays generated. |
| `tabular`, `feed` | Applied while reading, before a row becomes a record or counts against a per-key cap. A feed filters on `title`, `url`, `publishedAt` or `summary`. |
| `generative`, `aggregate`, `agentic-rag` | Not supported. Every predicate is applied after the fetch. |

The operators are `EQUALS`, `CONTAINS` (text only), `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL` and `IN`.

Rules:

- **Only the author knows where the filter saves work.** The host can always wrap a query and filter its result, but that saves the source nothing. The slot puts the filter inside the query, before the expensive part. If nothing is pushed, the slot renders as empty text.
- **The host binds or escapes every value; none is spliced in raw.** Each value is parsed as the declared `type` and written from the parsed value: a typed RDF literal (`"20"^^xsd:integer`, an `xsd:dateTime`, an escaped string), or a bound SQL or Cypher parameter. A value that does not parse as its type, or an operator the entry does not list, is not pushed. It stays a filter the graph applies after the fetch and never causes an error.
- **The cache key holds exactly the predicates pushed.** A predicate the producer pushes changes what the source returns, so it is keyed. A predicate it does not push shares the cached fetch with the unfiltered query.
- **A pushed filter must be exact.** The graph still applies every predicate after the fetch, so a looser source filter only costs extra rows. A stricter one, such as an equality that misses a language-tagged literal, loses rows nothing can recover. Compare through the expression that makes the source agree with the graph, for example `expr: "STR(?label)"`.
- **Validation.** `realm_validate` reports an error for a declared entry whose slot is missing from the query, and for an entry the kind cannot honour (`having` without `expr`, a `cypher` entry without `expr`, an `sql` entry on a stored procedure or an unexposed column, a field a feed item does not have). It warns about a slot with no entry, and about a declared property the query does not appear to project.

**`project` paths: use `[*]`, never `[0]`.** An INDEXED path is not honoured and projects **null silently** — no warning, no error, just an empty property, and any predicate over it then drops every row. Only the `[*]` form reaches into a nested array, and it yields a **list**, so a single-valued nested field arrives as a one-element list the consumer must unwrap. Write `address: "Location[*].FullAddress"`, not `Location[0].FullAddress`. (Verified 2026-07-28: with `[0]`, every address and coordinate in a fetched collection was null while the flat scalar fields projected fine — the kind of defect that reads as "the source didn't return that field".)

**`project` takes paths, not expressions.** A JSONPath filter (`steps[?(@.conclusion=='failure')].name`) or function (`steps.length()`) projects **null silently**, exactly like an indexed path. Project the parallel lists (`step_names: "steps[*].name"`, `step_conclusions: "steps[*].conclusion"`) and derive in Cypher: `[i IN range(0, size(j.step_names) - 1) WHERE j.step_conclusions[i] = 'failure' | j.step_names[i]]`.

Relatedly, **a declared type is what a value arrives as; an undeclared property arrives as the source encodes it.** A JSON feed that quotes its numbers sends strings. When the target type declares the property `int`/`long`/`decimal`/`number`/`boolean`, the fetched value is stored as that type — `"35703978620"` becomes a number, so `WHERE run.id = 35703978620` matches; a declared list is converted element by element. A property with **no** declared type keeps the source's own value, so `WHERE n.cost >= $min` on a quoted cost compares a string to a number and matches nothing: declare the property's type, or coerce at the point of use (`toFloat(n.cost)`). A value the declared type cannot read (`"n/a"` in an `int` property) is kept as sent rather than failing the fetch, and a numeric comparison against it does not match — say in the property's description when a source sends such values. And beware that a null-propagating comparison also *removes* rows with no value at all — which for something like a cost bound means records the user would have wanted to see silently vanish.

**Composite-key joins — when no single anchor property is the key.** A source keyed on a *pair* — a latitude/longitude point for a geospatial lookup, an owner/repo slug — declares the join with `producerKeyFields` and **omits `keyField`**:

```yaml
- anchorLabel: WeatherLocation
  relationship: HAS_CURRENT
  producerKeyFields: [latitude, longitude]   # composed, in this order, into ONE key per anchor
  recordKeyField: key                        # the record field carrying that key back
  producer: weather.current
```

The engine composes the named anchor properties, in order, into one opaque key per anchor and hands those to the producer. **The link is the whole composite**: each record must carry the exact key it was fetched for under `recordKeyField` — a `remote` producer gets this for free by declaring `echoKeyAs: key`; a TypeScript handler echoes the key it received. A record never links to an anchor that merely shares one component, and an anchor with any component absent contributes no key (the same null rule as a single `keyField`).

A **remote producer** destructures the composite back into separate request arguments with `keyArgs`, naming one argument per component in the same order:

```yaml
keyArgs: [latitude, longitude]    # → latitude=…&longitude=… per call
echoKeyAs: key
```

`keyArgs` implies one source call per key. The composite's own separator is reserved by the engine and always takes precedence over `keySplit` — and the two do **not** compose: a composite component is handed to `keyArgs` **as one argument**, never re-split by `keySplit`. So a source-shaped component like `"owner/repo"` does NOT become two path parameters; declare the parts as separate anchor properties (`producerKeyFields: [owner, repo, id]`, projected from the record that produced the anchor) and name one `keyArgs` entry per part. (Verified 2026-09-23: `producerKeyFields: [repository, id]` with `keyArgs: [owner, repo, run_id]` sent `owner=embabel/embabel-agent`, `repo=<the id>` and no `run_id`, a 404 that read like a missing run.)

A composite that is itself echoed (`echoKeyAs: runKey` on a first hop) may be a component of the NEXT hop's composite: `producerKeyFields: [runKey, id]` splits back into every part of `runKey` followed by `id`, so a three-hop chain (repository → run → job → annotation) threads the path parameters down without any record having to carry them. Name every part in `keyArgs`, in order, even the ones the operation does not declare — an undeclared name is simply not sent, and it keeps the positions aligned.

**A key with an empty path segment is refused, not sent.** A URL (`https://…`, whose `//` is an empty segment) is therefore never a usable key for a path-parameter producer, and `keySplit: "/"` over one is refused with a warning naming the key. Compose the parts instead, as above.

`project` itself still maps flat paths only — there is no template or concatenation form *inside* `project`; composition is the join declaration's job, as above. A TypeScript handler (`src/api/*.ts`) remains the escape hatch when the source needs more than destructured arguments.

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

Anywhere a realm ships code that runs in the host's `code_mode` sandbox — a **routine** (`agents/`), a **decoration** action, a skill recipe — it writes **CypherScript**: an ordinary TypeScript/JavaScript program that interleaves graph queries with procedural logic, integration calls, and inline LLM, all over the one typed `gateway.*` surface. It is not a separate language — it's TS/JS with first-class graph access:

- **Cypher for the graph** — `await gateway.kg.query({ cypher, params })`. The query runs through **Virtual Cypher** (above): rewritten to the host-bound world, context, and access policy, read-only, and materializing on-demand virtual joins exactly as a chat query would — so one `MATCH` spans persisted **and** virtual (integration) data.
- **TypeScript/JavaScript** for what Cypher can't express — branching, aggregation, reshaping, loops.
- **Integrations** — `gateway.<ns>.*` (the Realm's own Functions + connected APIs), e.g. fetch the actual email body the graph only holds an edge for.
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

`params` supplies bound query values as a JSON object; a JSON-encoded object is also supported. Bind values with `$name` parameters. Reads and model calls can expose private data and require the applicable host approvals. A handler's `dryRun` flag controls its proposed effects; it does not provide authorization. Compatibility lenses can use the host code-mode gateway. Captured installations use the handler-binding profile below. Virtual Cypher calls are available to a captured handler once the owner separately approves `cypher_query`, following [the captured graph-query profile](HOSTED_EXECUTION.md#me-captured-graph-query-profile).

## `views/` — saved queries, and the two shapes they come in

A realm ships named Cypher queries under `views/*.yml`. They appear in the console's Views list and
are runnable by name, which is most of what they are for. The part that is easy to miss is that one
of the two shapes **composes**: its name is a label, and a larger query may match it.

```yaml
# views/key-accounts.yml
- name: KeyAccounts
  description: Contacts worth more than £100k ARR, whoever owns them.
  cypher: |
    MATCH (me:AssistantUser)-[:HAS_HUBSPOT_OWNER]->()-[:OWNS_CONTACT]->(c:HubSpotContact)
    WHERE c.arr > 100000
    RETURN c
```

```cypher
-- Used as a label. The view's MATCH clauses are inlined, and `c` is a HubSpotContact like any other.
MATCH (c:KeyAccounts) WHERE c.renewalDate < date('2026-12-01')
MATCH (c)-[:HAS_HUBSPOT_DEAL]->(d:HubSpotDeal)
RETURN c.email, d.name
```

**Node view, or tabular view. The body decides, not a flag.**

| | Body | Used as |
|---|---|---|
| **Node view** | `MATCH … RETURN <one bare node variable>` | a label **or** by name. COMPOSES. |
| **Tabular view** | a projection — `RETURN c.email AS email, count(d) AS deals` | by name only. TERMINAL. |

A node view yields nodes of exactly one type and keeps their identity, so the view's name reads as a
named subtype: `KeyAccounts ⊆ HubSpotContact`. A tabular view's rows are not nodes, so matching it as
a label cannot answer — and is refused at validation rather than quietly returning nothing.

**The type may be VIRTUAL, and referencing the view materializes it.** This is the composition worth
knowing about: a node view whose body traverses a declared join to a virtual type is, as a label, a
way to say "these fetched records" once and reuse it. `MATCH (a:NdisDisabilityFilers)` expands the
view, materializes its `AisReturn`s through their producer, and the rest of the query treats them as
the §2 execution model always does — transient, rolled back with the read.

Two consequences follow from the fact that a reference is an INLINE of the body, not a subquery:

- **A view's own variables are private.** Only the returned variable becomes the caller's alias;
  every other variable the body declares is renamed per use. Two uses of one view in a query never
  share its internals, and a caller's `c` never meets the body's.
- **The anchor rules still apply, through the view.** A view does not grant a virtual label a bound
  anchor it would not otherwise have: what the body writes is what the engine sees. A body that pins
  its anchor composes the way the same query would written out longhand.

| Field | Required | Description |
|---|---|---|
| `name` | yes | What it is run and matched by. A node view may NOT be named like a label the world already holds — matching that label anywhere, including inside other views, would silently come to mean "the nodes this view selects". |
| `cypher` | yes | The body. Standard Cypher, parsed by the real parser; there is no `DEFINE VIEW` statement and no subquery form. |
| `description` | no | What it answers, for the Views list and for a model choosing between views. |
| `params` | no | Declared bind values, each with a `type` (`string`, `int`, `number`, `float`, `double`, `boolean`, `date`), a `description`, and ideally a `default` so the view stays runnable bare. One value each: a view needing a list reads it inside its own body rather than taking `IN $p`. |
| `outputLabel` | inferred | The type a node view's rows are. **Inferred** when the body returns a single bare node variable, which is why most views never declare it. REQUIRED on a `materialized` view, where there is nothing to infer from until the body runs. |
| `materialized` | no | `false` (default) expands the body at query time, always fresh. `true` commits the result and reads the cache until the TTL expires — the interactive query then does no producer calls at all. |
| `ttl` | no | Cache lifetime for a materialized view (`30m`, `2h`, `1d`). Default `1h`. Ignored when regular. |

**What is refused, rather than answered wrong:** a tabular view matched as a label; a node view named
like an existing label; an argument the view never reads; a fractional number for an `int` parameter;
and a label in the body that is a near miss for one the realm knows (`GitHubIsue` beside
`GitHubIssue`), reported at the view's file and line.

## `lenses/`

### Captured handler binding

A captured host uses versioned metadata to bind a lens to an approved handler in the
same installation. The declaration supplies no execution capability by itself.

```yaml
# lenses/movie-details.yml
version: 1
id: movie-details
name: Movie details
handler: movie.movieDetail
```

Required fields are `version`, `id`, `name` and `handler`; `description` and `result` are optional.
The ID is a lowercase letter followed by lowercase letters, digits or hyphens, at
most 64 characters. The name is at most 128 characters; description at most 512.
Fields are strict. Aliases, tags, malformed UTF-8, nested paths, duplicate IDs and
undeclared handlers are refused. Hosts accept at most 32 flat `.yml`/`.yaml` files,
8 KiB each and 64 KiB aggregate. IDs conflicting across installations are unavailable.
Owner World definitions and owner saves take precedence.

An opening passes JSON object arguments through the retained handler.
The handler returns a JSON object within 1 MiB, 32 nesting levels and 65,536
characters per string. `result: json` is the default and returns data only.

With `result: content`, the handler returns optional `focus` (up to 256 unique
entity ID strings, each at most 1,024 UTF-8 bytes), `data` (any JSON value),
`presentation` (`items`, `table` or `json`) and `complete` (boolean, default true).
Unknown fields are refused. Content lenses require the retained `cypher_query`
grant alongside handler approval. The host reads owned focus on access; missing,
ambiguous or inaccessible IDs are excluded and mark the result incomplete.
`complete: false` also marks it incomplete. A presentation preference selects an
existing compatible host view; guest HTML and executable references are refused.
Background envelopes are snapshots. Losing ownership of any already projected
focus entity invalidates the stored envelope at its next admission check.
The host retains the same target and serialized arguments through refresh, rechecks
owner World and approval on reads, and disables cache reuse. API calls inside the
handler require their own operation and credential approvals.

This is independent of the selected sandbox backend. The Me implementation exposes
it through `/api/v1/lenses/{id}/invoke` and the JSON view endpoint. Add
`background=true` or `waitSeconds` for deferred execution. Preparation retains the
selected target and serialized arguments; queued work cannot select a new revision.
Completion and every result response recheck admission. Revocation clears stored
data; new approval cannot revive an old run. Results and handles are in memory.

The reference host limits active work to 64 runs globally and eight per owner,
returning HTTP 429 at capacity. Cancelled workers consume capacity until they exit.
It retains up to 200 settled runs and cancels overdue work using the configured
background timeout. Cancellation cannot undo completed effects.
See [hosted execution](HOSTED_EXECUTION.md) for supported routes and limits.

### Host-specific legacy definitions

The definitions below describe the compatibility runtime. Captured Worlds do not
execute Realm-provided legacy module, CypherScript, fixed-query or anchor lenses.


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

A realm-shipped Lens is code, not mutable per-world or per-principal state: its definition is
refreshed when the realm is updated. One opening's arguments, focus, presentation, Watch snapshots
and other scoped state remain in the world. An app should invoke a named Lens or view through the host's typed
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
      trigger: on-first-use                # on-first-use | on-install | scheduled | manual
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

A coverage record describes one world's mirror. It is kept per world, source and partition, and
another world's walk of a source by the same name never answers for it.

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

### `visibility: public` — a world's mirror, and why the scope differs from `reference/`

A mirrored public dataset belongs to no user: its only writer is the source's ingestion, not a
person. A source that declares `visibility: public` therefore opens its `label`, and its anchor's
label, in the world that installs the realm. The records its ingestion writes there carry the
**`Public`** label and the world they were mirrored for, and the scope rewriter reads them without a
per-user predicate — the same treatment as a REFERENCE taxonomy, for a very different kind of data.

The distinction matters operationally even though the scoping is identical. A `reference/` vocabulary
is a handful of curated nodes, seeded, static, safe to wipe and rebuild, small enough to project into
a prompt. A mirrored public dataset is hundreds of thousands of rows with a refresh cycle, a staleness
window, and an ingestion job as its only legitimate writer. Treating them as one thing invites a
factory reset that deletes the register, or a schema projection that inlines it.

The declaration is narrow, and the engine holds it there:

- **It takes effect only in the world that installs the realm.** A label name is not a namespace:
  another world's `Customer` may be its owner's private CRM records, or a mirror of a different
  feed. Everywhere else the label keeps its ordinary scope. A world has one owner, so the mirrored
  records are readable by that owner and by everything acting in the world for them — chat,
  handlers, routines and agents — and by no other user. Removing the realm withdraws the
  declaration: once the world is rebuilt without it, the label is private again there too.
- **It opens only what ingestion wrote.** In the declaring world, `MATCH (c:Customer)` answers the
  source's mirrored records and the caller's own `Customer` records. It never answers another
  user's, and never another world's mirror filed under the same label: a declaration makes no
  user-owned node readable.
- **A source may not open a label somebody else declares.** A source whose label, or anchor label,
  is declared by another realm installed in the world, or by the world's own types, is refused at
  load and named in the realm's status, and nothing it declares takes effect. A label the platform
  itself scopes private or organization-shared is never opened.
- **Each world keeps its own mirror and coverage.** Two worlds that install a realm with the same
  public source each walk it and hold their own copy, merged on the record's identity *and* the
  world, so neither can read or rewrite the other's. A field in a fetched record that claims to name
  the world is dropped. Coverage is kept per world, source and partition. There is no mirror shared
  across worlds.
- **Only ingestion writes `Public`.** `Public` and `Coverage` are reserved to the platform's own
  writers. A realm type, a realm provenance label, a DERIVE head, a projection's `hub:` or
  `target:`, and any record a query fetches or materializes cannot carry either label. A type name,
  provenance label or rule set naming one is a load problem; a projection naming one is no spine;
  and a query that would materialize a node carrying one is refused.
- **`Public` is opt-in per label and never inferred.** The rewriter's default stays fail-closed at
  PRIVATE, and a label no source in the world declares public is private.

### Me source authority profile

Source contracts are kept per world. The contracts a world's realms declare decide how that world's
reads are served — which mirror answers, which coverage record judges a partition, what age limit
and completeness rule apply — and a realm in another world declaring the same source name or label
changes none of it. A world's contracts are replaced whole each time it is built, so a read in
progress sees one build or the next and never a mix, and they are dropped when the world is evicted.

Captured Worlds use the separate [captured collection snapshot
profile](HOSTED_EXECUTION.md#captured-collection-snapshots), which implements per-World source
read/storage approval and a retained, authority-partitioned mirror and coverage receiver. A producer
or handler grant does not authorize public graph access.

### `lane: documents` — a collection that lands as searchable DOCUMENTS

Everything above mirrors records into the graph. A collection of long-form, reasonably stable
*content* — a published text, a documentation site, a regulator's guidance, a policy library —
belongs in the document store instead: chunked, embedded, and reachable by document search and
relevance joins (`RELEVANT_TO`). `lane: documents` declares that, with no handler code: the host
reads the records, renders each into a document, and keeps them current.

```yaml
# sources.yml
sources:
  - name: bible-kjv
    lane: documents                      # graph (default) | documents
    from:                                # exactly one of:
      cypher: |                          #   a read over data the world holds (typically this realm's reference/)
        MATCH (b:Book)<-[:IN]-(p:Passage)<-[:IN]-(v:Verse)
        WITH b, p, v ORDER BY v.verse
        RETURN p.osis AS osis, p.name AS title, collect({n: v.verse, text: v.text}) AS verses
      # urls: [https://…, https://…]     #   pages the host fetches
    document:                            # Jinja; each record's columns are the model
      uri: "bible://kjv/{{ osis }}"      # the replace key — a stable `<scheme>://<id>`
      title: "{{ title }} (KJV)"
      content: |                         # markdown preferred: headings drive chunking
        # {{ title }}
        {% for v in verses %}{{ v.n }} {{ v.text }}
        {% endfor %}
      # url: "{{ link }}"                #   OR: a page to fetch per row, instead of uri + content
      # sourceModifiedAt: "{{ edition }}"#   the version token; see below for the default
      sourceKind: bible                  # the store, generically; defaults to the realm name
      tags: [bible, kjv]                 # stamped on every document and chunk
    sync:
      trigger: on-install                # on-install | scheduled | manual
      schedule: "0 0 3 * * SUN"          # six-field cron, host zone, for `scheduled`
      prune: true                        # remove documents no record produces any more
```

**Records.** `from.cypher` is read on behalf of the installing user, through the same scoping as that
user's own queries; a read the host cannot scope is a failed sync, never an unscoped one.
`from.urls` gives one record per URL, exposed to the templates as `url`.

**Two kinds of document.** A record renders either **text** (`document.uri` + `document.content`: the
realm renders the content itself, under a locator in its own scheme — the same `uri` contract as
[`EXTERNAL_DOCUMENTS.md`](EXTERNAL_DOCUMENTS.md) §3, so `http(s)://`, `file://` and `upload://` are
refused) or a **page** (`from.urls`, or `document.url` per row: the host fetches and converts it, and
the URL is its identity). Never both.

**Versions decide what is re-ingested.** Each document carries a version token, compared with the one
held before anything is fetched or embedded:

| | Token |
|---|---|
| `document.sourceModifiedAt` declared | the rendered value |
| rendered text, none declared | a hash of the rendered content — an unchanged record is never re-embedded |
| a page, none declared | the `Last-Modified` it is served with; a page that states none is re-read on every run |

**Triggers.** `on-install` runs a source when the world has never completed it, when its declaration
has changed since, or when its last run did not complete — after the realm's `reference/` data is
seeded, so a `cypher:` source reading it never sees an empty graph. `scheduled` runs it on its cron,
registered and removed with the realm. `manual` runs it only when asked. A run is always in the
background; a second trigger while one is running is reported, not queued.

**Pruning** removes documents this source holds that no record produced, and only after a COMPLETE
run: an empty read or a failed record deletes nothing, because "the source returned nothing" and "the
source is gone" are indistinguishable from the host's side.

**Status.** Each run's outcome — `COMPLETE`, `PARTIAL` (some records failed; retried next trigger),
`EMPTY` (no records; nothing pruned), `FAILED` (with the reason) — is recorded per world and reported
with the realm's status, alongside every declared source that has never run.

**Visibility.** Documents are held per user and context, like every other ingested document: each
world that installs the realm ingests its own copy. `visibility: public` is refused for a `documents`
source until a shared document corpus exists.

**When to write a handler instead.** Declarative sources cover content the host can read or fetch
unaided. A source behind OAuth, with a change feed, or needing a multi-step export (a Drive folder, a
Notion workspace) still uses a handler and `ctx.ingest.*` ([`EXTERNAL_DOCUMENTS.md`](EXTERNAL_DOCUMENTS.md) §6).

**Validation reads `sources.yml` as strictly as a producer.** A value outside a field's vocabulary
(`visibility: publc`, `ordering: version-order`) is an error at that field — reported, never quietly
read as the default, because the default is the dangerous reading: `unordered` switches off the bias
detection an ordered source needs, and `private` hides a label meant to be public. A source missing
its `name` is an error at its own path, and does not take the rest of the file with it. A misspelled
key is a warning that names the key it was probably meant to be.

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
- **Principal-anchored reference is per principal.** The compatibility type name is `userAnchor`;
  each seeded record gets its `(:AssistantUser)-[:PREDICATE]->(record)` edge automatically inside the
  host-bound world and context — the way to seed a human principal's preference (e.g. which services
  that person subscribes to). A service principal has no implicit `AssistantUser` anchor. Global
  catalog data uses `userAnchor: false`.
- **Relations resolve like `create_entry`.** An optional `relations: [{ predicate, to: { type, ...keyProps } }]` links a record to another entry that must already exist (seed it first / in another realm's `reference/`), else the record is refused.
- **Merges with virtual data.** A reference type can also be a virtual-join *target* (e.g. `StreamingService` seeded here AND materialized on demand by a producer): both write paths MERGE on the shared identity, so a producer-fetched node picks up the catalog's stable fields.

This lets a realm own its reference data as *data*, not as a hardcoded list inside a query or a producer — the same "it's data, put it in the graph" discipline as types and producers.

## `apis/`

API entries — each `.yml` file in `apis/` is a list of API definitions loaded on world init. Each entry compiles into a typed `gateway.<name>.*` namespace inside `execute_javascript` / `execute_python`.

**Trust tiers are normative.** In a marketplace/untrusted realm, `file://`, process-environment
fallback, `${VAR}`/raw-header credential interpolation, query/path/body credentials, and directly
networked credential-bearing MCP are rejected at load. Marketplace network access must use a
host-vetted typed credential slot and structured auth profile through the gateway; if the provider
cannot meet the deployment's marketplace credential policy, that integration is unavailable in the
marketplace tier. The `token-env`, custom-header interpolation, and credential-bearing MCP forms
documented below are compatibility features for local or explicitly first-party/org-reviewed
installations. Their trust tier is adoption-visible and they never become marketplace-safe merely
because they run in Docker.

The typed credential slot is a [key entry](#keysyml--the-keys-a-realm-needs) in a conventional
realm and a declared credential the owner binds in a captured realm. See
[keys and declared credentials](#keys-and-declared-credentials) for which applies where.

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
| `token-env` | with bearer / api-key | Env-var or credential-store key holding the token. Deprecated in favour of a [key entry](#keysyml--the-keys-a-realm-needs) for the same variable, or of a declared credential in a captured realm. |
| `headers` | no | Custom HTTP headers; values support `${VAR}` interpolation from credential store / env. |
| `oauth2` | with `auth: oauth2` | OAuth2 config — see **OAuth2** below. |
| `tags` | no | Allowlist of OpenAPI tag names. Filters huge specs to a coarse subset. |
| `operation-ids` | no | Exact `operationId` allowlist. Composes with `tags` (tags pre-filter, operation-ids picks exact ops). Match is case-insensitive and treats `-`/`/` as `_`, so `repos/get`, `repos-get`, `repos_get` all match. |
| `capability-tags` | no | Capability DECLARATION — what the API is FOR, in the host's vocabulary (`web-search`, `web-fetch`). Lets host code pick a tool by capability instead of by provider name. Unrelated to `tags`; see **Capability tags** below. |

### Capability tags

`capability-tags` says what an API IS FOR, in a vocabulary the host
defines — `web-search` (discovers information on the open web from a
query), `web-fetch` (reads a URL it is given, and cannot discover one).
Most tools are chosen by an LLM reading their descriptions, but some
consumers have to choose without one in the loop: the host's person
research needs *a* search tool before any model is asked anything. A
declaration is how such a consumer finds yours.

```yaml
- url: https://api.example.com/search/openapi.json
  name: example-search
  capability-tags: [web-search]
```

**Not `tags`.** `tags` filters WHICH OPERATIONS of the spec become tools,
using the spec's own OpenAPI tag names. `tags: [web-search]` therefore
filters the spec down to operations the provider happened to tag
`web-search` — usually none, leaving the entry with no tools at all. The
two fields do unrelated jobs and may both be set.

**The host owns the vocabulary; realms supply the providers.** A tag the
host does not recognise is carried but matches nothing, so inventing one
declares nothing. Only `web-search` and `web-fetch` are defined today.

**Declare on every provider you ship, not just one.** Selection is
all-or-nothing per capability: once anything in the world declares
`web-search`, only declarations count, and an untagged provider in the
same realm stops being selected. Where nothing at all declares the
capability the host falls back to matching tool names and logs that it
did — so a realm that predates this field keeps working, but a realm
that tags half its providers loses the other half.

**The tag sits on the ENTRY, so it covers every operation that entry
exposes.** Where only part of a spec carries the capability, narrow the
entry with `tags` / `operation-ids` — or split it into two entries, each
with its own declaration.

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

Credential references resolve through a host binding keyed by world, context, principal, connection, and
grant revision, with context access checked on every call. In the local/first-party compatibility
tier, `token-env` and `${VAR}` may then resolve from that world's credential store (set via
`set NAME = ...` in chat or via the admin UI), followed by the process environment. Process fallback
is unavailable in shared multi-world or untrusted marketplace deployments. Missing credentials mean
the entry is skipped at world load with a logged warning; the API never appears in the gateway.
A captured realm's API operations read only the owner's wallet, through the credential the owner
bound, and never fall back to the process environment.

### OAuth2

For providers that use the OAuth2 authorization-code flow (HubSpot, Slack, Salesforce, GitHub, Google, etc.). The pack ships only the **provider facts** (URLs, scopes, identity introspection). Per-deployment client app credentials live in the host's **org vault**, keyed by provider name — **never in the pack repo and never in any user's workspace**. (The host admin file `oauth-apps.yml` is retired; credentials are no longer read from disk.)

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
| `client-id` / `client-secret` | NO in published packs | Power-user fallback only — accepts `${VAR}` interpolation. **Production setups put these in the host's org vault** (or an individual user's wallet, which takes precedence) so the pack stays public and credential-free. |
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

**Where the OAuth client credentials live** (host-managed, never on disk)

`client-id` and `client-secret` for the provider's Public App belong in the host's **org vault**, keyed by provider name. The host manages them through its admin UI or REST; the exact surface is host-specific, but the key is always the provider name:

```bash
PUT /api/v1/admin/org-vault/provider/hubspot
{"client-id": "12345-abcdef-…", "client-secret": "…"}
```

The provider name (`hubspot`, `slack`, …) matches the `name:` field of the matching `apis.yml` entry.

Two properties a pack author can rely on:

- **Nothing is read from the filesystem.** The old `admin/oauth-apps.yml` and its per-workspace override are retired, so a pack must never instruct an operator to write credentials to a file.
- **A user can override the deployment's app with their own**, by putting it in their personal wallet. Packs should not assume the org's client app is the one in use — which matters for docs that tell a developer how to test against their own provider project.

**Lookup order** for client_id / client_secret:
1. The user's own **wallet** (per-user override — encrypted and self-service, replacing the retired per-workspace file)
2. The deployment's **org vault** (the default everyone gets)
3. `${VAR}` from the pack's `oauth2.client-id` / `client-secret` (escape hatch for power users)

If none resolve, the provider's status reports `not-configured` and Authorize returns an actionable error message instead of silently failing.

**End-user UX**

End users **never** paste tokens, IDs, or secrets. Settings → Connected Services → click **Authorize** → consent on the provider's page → done. ConnectedAccounts holds the real account label; `gateway.<name>.*` is live in chat.

**Token refresh** is automatic — the host's `OAuth2Service` rotates expired access tokens using the stored refresh token and writes back any new refresh token the provider issues (HubSpot rotates them on every refresh).

## `keys.yml` — the keys a realm needs

A realm that calls a vendor with an API key declares that key here: what to call it, where somebody
gets one, the value(s) it takes, and how the host can tell whether a value works. Hosts use the
declaration to ask for the key by name, show it on the realm's settings, check a value before
storing it, and re-check a stored value while it is in use.

Key entries belong to conventional realms. A captured realm declares credentials the owner binds
instead, which is the recommended path for a new realm.
[Keys and declared credentials](#keys-and-declared-credentials) compares the two.

```yaml
# keys.yml
- name: brave
  displayName: Brave Search
  description: Web and news search.
  getKeyUrl: https://brave.com/search/api/
  fields:
    - variable: BRAVE_API_KEY
      displayName: API key
  validate:
    api: brave                   # an API this realm declares in apis/
    operation: webSearch
    args: { q: test, count: 1 }
    refusedOn: [401, 403, 422]   # Brave answers a bad token 422

- name: maps
  displayName: Google Maps
  fields:
    - variable: GOOGLE_MAPS_API_KEY
      displayName: API key
    - variable: GOOGLE_MAPS_PROJECT_ID
      displayName: Project ID
      secret: false
  validate:
    api: maps
    operation: geocode
    args: { address: "1 Main St" }
    interpret: checkMapsAnswer   # optional Realm Function, see below

- youtube                        # shorthand: one field, YOUTUBE, called "youtube"
```

| Field | Required | Description |
|---|---|---|
| `name` | yes | Stable id, unique within the realm. |
| `displayName` | no | What a person is shown. Defaults to `name`. |
| `description` | no | One line on what the key unlocks. |
| `getKeyUrl` | no | Where somebody obtains a key. |
| `fields` | no | The values the key takes. Defaults to one field whose `variable` is `name` upper-snake-cased (`brave-search` → `BRAVE_SEARCH`). |
| `fields[].variable` | yes | The credential name the value is stored and resolved under — the same name `token-env` and `${VAR}` in `apis/` refer to. A captured realm names no variable; see [keys and declared credentials](#keys-and-declared-credentials). |
| `fields[].displayName` | no | Defaults to the entry's `displayName`. |
| `fields[].secret` | no | Default `true`. `false` marks a value safe to show back, like a project id. |
| `validate` | no | How to check the values. Without it a key can be set but never checked. |

**One declaration, any number of APIs.** A field's `variable` is the credential slot every `apis/`
entry naming that variable resolves. Two APIs that use one key share one entry, and a person is asked
once.

### Validation

`validate` names **one of the realm's own API operations** and the arguments to call it with. To check
a candidate value, the host calls that operation with the value bound into the entry's credential
slot, using the API's declared auth. The call is the host's, made through the gateway like any other;
the realm never sees the value.

| `validate` field | Required | Description |
|---|---|---|
| `api` | yes | An API this realm declares in `apis/`. |
| `operation` | yes | An operation of that API. Pick the cheapest one any valid key may call. |
| `args` | no | Arguments for the call. Fixed, so the answer can only be about the key. |
| `refusedOn` | no | Response statuses that mean the key is refused. Default `[401, 403]`. |
| `interpret` | no | A Realm Function that decides the verdict from the response, for a vendor whose refusal is not a status. |

**A check has four outcomes**, and every host reports them the same way:

| Outcome | Meaning |
|---|---|
| `accepted` | The issuer answered and the key works. |
| `refused` | The issuer answered and said no. |
| `unreachable` | No answer: DNS, connection, timeout. Says nothing about the key. |
| `failed` | An answer that is neither yes nor no, such as a 5xx or a rate limit. |

**Only `refused` is a verdict on the key.** A host stores nothing it was refused, and may tell the
person when a key already stored turns refused. `unreachable` and `failed` never block a write and
never mark a key bad: a vendor being down is not the key's fault.

**`interpret` never receives the key.** It is called with the check's response, not the request:

```ts
// src/api/keys.ts — Google answers 200 with status REQUEST_DENIED for a bad key
export async function checkMapsAnswer(input: { status: number; body: unknown }): Promise<{ outcome: string; detail?: string }> {
  const answer = (input.body as { status?: string }).status
  if (answer === 'REQUEST_DENIED') return { outcome: 'refused' }
  if (input.status === 200) return { outcome: 'accepted' }
  return { outcome: 'failed', detail: `HTTP ${input.status}` }
}
```

It must return one of the four outcomes. The host applies a short deadline to the whole check; an
`interpret` that throws or overruns is `failed`. `detail` is shown to the person and must not repeat
anything from the response that could identify the key.

### Guarantees

- **Values are never exposed.** A host never logs a key's value, returns it from any read, shows it
  back unless the field is `secret: false`, or passes it to realm code.
- **A check may run at any time**, repeatedly, and must not change anything at the vendor. `validate`
  names a read.
- **Declared keys are the typed credential slot** the [trust tiers](#apis) require: a marketplace realm
  declares its keys here rather than relying on `token-env` resolving from the environment.
  This applies to a conventional realm. A captured realm's typed slot is a declared credential
  the owner binds, and a captured realm never resolves a secret from the environment.

### Realms that declare nothing

`keys.yml` is optional, and a realm without one behaves as before. A host still derives one entry per
credential variable the realm's APIs refer to (`token-env`, `${VAR}` in `headers`), and presents it as:

| | Derived from the variable |
|---|---|
| `name` | the variable, as-is (`YOUTUBE_API_KEY`) |
| `displayName` | the variable less a trailing `_API_KEY`, `_KEY` or `_TOKEN`, title-cased (`Youtube`) |
| `fields` | one field, the variable |
| `validate` | none — a derived key can be set, never checked |

A declared entry takes precedence over a derived one for the same variable, so a realm can adopt
`keys.yml` one key at a time.

A derived entry resolves the way `token-env` does, so the process environment fallback applies
only in the local or first-party tier described under [Auth](#auth).

**Load problems.** A `validate.api` the realm does not declare, a `validate.operation` that API does
not have, an `interpret` naming no Realm Function, or two entries claiming one `variable`, is a
recorded problem. The entry still loads, without `validate`.

### Keys and declared credentials

A realm asks for a secret in one of two ways, and both keep working. A key entry in `keys.yml`
names the variable a value is stored under. A declared credential in `credentials.yml` names a
purpose, and the owner binds a wallet item to it. Declared credentials are the recommended path
for new realms.

| | Key entry (`keys.yml`) | Declared credential (`credentials.yml`) |
| --- | --- | --- |
| Applies to | Conventional realms: one installed from a directory, a first-party or org-reviewed realm, or a local one. | Captured realms, which run from a copy the owner admitted. See [hosted execution](HOSTED_EXECUTION.md#credentials). |
| The realm names | The variable, which `token-env` and `${VAR}` in `apis/` also name. | A purpose: kind, provider, description, docs link. Never a variable or where the secret lives. |
| The value comes from | A person sets the key, and the host stores it under the variable. | The owner binds a pasted secret or an existing wallet item when approving the realm. |
| The host reads it from | The world's credential store, then the process environment in the local or first-party tier ([Auth](#auth)). | The owner's wallet only. |
| Checking a value | `validate`, with an optional `interpret`. | No check. Binding an existing item checks only that its stored type fits the credential's kind. |
| Changing the value | Replace it, and the host re-checks it. | An approved API operation is pinned to the value it was approved with; a different value needs approval again. |
| Values | One or more fields, each secret or not. | One secret per credential. |

`token-env` is deprecated in favour of either declaration: a key entry for the variable in a
conventional realm, or a declared credential referenced with `credential:` in a captured realm.
Hosts still read it. A captured API entry that still uses `token-env` gets an implicit credential
whose id is the variable, the same name a derived key entry for that variable takes.

**When both name one secret.** A key entry and a captured realm reach the same wallet item when a
captured API entry still reads it through `token-env`, or when the owner binds a declared
credential to an existing item a key entry stored. Both then use one value. Replacing or deleting
that key through the key entry stops every captured API operation approved with the old value,
until the owner approves the new one or the approved value is restored. Hosts do not yet warn
before such a replacement, so expect to re-approve a captured realm's operations after changing a
key it shares.

### `credentials.yml`: declaring a credential

The file is a list with one entry per credential, each naming a purpose: an id, a kind, a plain
description written for the person who will be asked to bind it, and where somebody gets one. An
`apis/` entry or a channel then names a credential by that id. `connecting()` in embabel-ts emits
the file; it is equally hand-authored. A realm that declares nothing here behaves exactly as
described under `keys.yml`.

```yaml
# credentials.yml
- description: A bot token for the server you want the assistant in.
  docs: https://discord.com/developers/applications
  id: bot
  kind: bearer
  provider: discord
  scheme: Bot
- description: The application's public key, used to verify interaction webhooks.
  docs: https://discord.com/developers/applications
  id: signing
  kind: public-key
  provider: discord
```

```yaml
# apis/apis.yml
- auth: bearer
  credential: bot
  name: discord
  operation-ids:
    - getGatewayBot
  type: openapi
  url: discord.json
  write-operation-ids:
    - createMessage
```

| Field | Required | Description |
|---|---|---|
| `id` | yes | What an `apis/` entry or a channel names. Unique within the file. Either a lowercase letter followed by lowercase letters, digits and dashes (up to 64 characters), or an environment-variable style name: a letter or underscore followed by letters, digits and underscores (up to 128). The second form is what a credential migrated from `token-env` keeps. |
| `kind` | yes | One of `api-key`, `basic`, `bearer`, `oauth2`, `public-key`. |
| `description` | yes | What the credential is for, written for the person who is asked to bind it. Up to 512 characters. |
| `provider` | no | The service that issues it, when several credentials share one. Letters, digits, `_`, `.` and `-`, starting with a letter or digit, up to 64 characters. |
| `docs` | no | Where to get one. Must start with `https://`, contain no whitespace, and be at most 512 characters. |
| `scheme` | `bearer` only | The word in front of the token in the `Authorization` header, when it is not `Bearer` (Discord sends `Bot <token>`). Printable ASCII without whitespace, at most 32 characters. Refused on any other kind. |
| `scopes` | `oauth2` only | The scopes the grant asks for. At least one, no repeats, at most 32 entries of at most 128 characters each. Required on `oauth2`, because an unscoped grant cannot be judged; refused on any other kind. |

The file holds at most 32 entries. A host reads it whole and refuses the whole file, loading no
credential from it, when:

- it is not a non-empty list, or an id repeats;
- an entry has a field not in the table, a missing `id`, `kind` or `description`, or a `kind` outside
  the five above;
- an `id`, `provider`, `docs`, `scheme` or `scopes` breaks its rule in the table;
- an entry is not named by any `apis/` entry or channel in the realm, because asking for a secret
  nothing uses is a reason to doubt the rest of the list.

**Referencing one.** An `apis/` entry names a credential with `credential: <id>`, a channel names one
the same way, and a channel's webhook signature names one in its own `credential` field. A reference
to an id the file does not declare refuses the entry. One credential can back several entries and
channels. An entry carries `credential` or the older `token-env`: both together are accepted only
when they name the same thing, which is how a realm migrates one key at a time, while two different
names, or neither, refuse the entry.

**What the owner does.** Nothing is bound at install. For each declared credential the owner either
picks a key already in their wallet or pastes a new one, which the host files in the wallet for them,
and can unbind it again. A binding belongs to one installation of the realm: two installations of the
same realm hold their own, and can use different keys. Every change names the installation revision
the owner last read, and a stale one is refused. A credential with no binding has its calls refused,
and a channel that needs it is blocked until the owner binds it. A host never shows a bound secret
back, logs it, or records it in the grant.

A channel in a captured realm references a credential exactly as an `apis/` entry does. The channel
files themselves are described under `channels/`, which does not yet cover the captured form.

**Validation refuses a `keys.yml` field it would have to drop.** A field with no `variable` is an
error at its path rather than a key that silently does not exist; a misspelled key is a warning naming
the likely intended one; a `validate` naming an API or operation the realm does not declare is a
warning.

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

Every exported async function with a `(ctx, args)` signature becomes a manifest entry at build time; the host registers from the manifest, never by introspecting the code.

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

/** The gateway ops this type calls: the type argument to `Entity`. */
interface MovieGateway {
  streamingAvailability: { getShow(args: { id: string; country: string }): Promise<StreamingShow> };
}

/** A film in the knowledge graph. Identity is `imdbId`. */
export class Movie extends Entity<MovieGateway> {
  imdbId!: string;
  title?: string;

  /** Where this movie is streaming in a country (ISO-3166 alpha-2, lowercase). */
  async streaming(args: { country: string }): Promise<StreamingShow> {
    return this.gateway.streamingAvailability.getShow({ id: this.imdbId, country: args.country });
  }
}
```

There is no `ctx`/`self` plumbing: `this` is the object the host hydrated from the
entity's fields, and `this.gateway` is the injected context. **Name the gateway once,
as `Entity`'s type argument**: `this.gateway` is then typed with exactly the ops the
type calls, so every body and return type is real, with no cast. Without a type
argument the gateway is `GenericGatewayContext`, typed loosely; once `sync` generates
the host's `GatewayContext`, `Entity<GatewayContext>` types every op the host offers.

Each method's single parameter and return type drive the JSON Schema: a method that
needs one value takes it bare (`comment(body: string)`), one that needs several takes
one options object (`bookCall(call: CallBooking)`). The first JSDoc paragraph is the
LLM-visible description, exactly as for namespace functions.

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
import { Movie, type MovieGateway } from "../src/api/movie";

const getShow = vi.fn().mockResolvedValue({ streamingOptions: { au: [] } });
const movie = entityForTest(
  Movie,
  { imdbId: "tt0113451" },
  mockGateway<MovieGateway>({ streamingAvailability: { getShow } }),
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

#### Type methods on virtual types — pure compute and effectful write-back

A type method works the same whether the instance is a persisted entity or one
materialized on demand by a virtual join (a `GitHubIssue`, a `HubSpotContact`).
So a virtual type's class gives its on-demand instances behaviour:

- **pure** methods compute over the instance's own fields, no I/O (`issue.ageDays()`,
  `issue.needsTriage()`, `pr.isReadyForReview()`);
- **effectful** methods write back to the source through `this.gateway.<ns>.*`
  (`issue.close()`, `issue.addLabels('stale')`, `pr.requestReviewers('alice')`),
  and may use bound `gateway.cypher.query({cypher, params})` when the host has an
  admitted receiver. External SQL uses approved producers or typed operations; raw SQL
  gateway access is not a portable guest capability.

A read materialises transient nodes and rolls them back; an effectful method commits
to the real source (the rollback never touches that side-effect).
`realm-github` is the worked example (`GitHubIssue` / `GitHubPullRequest`).

#### Acting on what a query finds

The point of type methods is that code navigates the graph to what it needs and then
works on it there, the way an object model does. In a script:

```js
// 1. Read with gateway.cypher.query: every node in its rows carries __type and __labels,
//    virtual nodes included, so the host knows what each one is.
const { rows } = await gateway.cypher.query({ cypher: `
  MATCH (b:OdooBook)-[:HAS_CUSTOMER]->(c:OdooCustomer)
  WHERE c.name = 'Acme Corporation' RETURN c` });

// 2. Bind a row. state.set reads the row's labels, so state.get returns it with every
//    method its labels carry, from any realm. No type to name, no class to import.
state.set("acme", rows[0].c);
const acme = state.get("acme");

// 3. Work on it.
await acme.addNote("Second failed payment this month; chasing.");
await acme.scheduleFollowUp({ summary: "Call about the failed payments", due: "2026-10-15", kind: "call" });
```

- **Read through the Cypher gateway**, under either name: `gateway.cypher.query` is an
  alias for the one hand-written-Cypher path `gateway.kg.query` runs, and both tag every
  returned node, so either read gives rows that know what they are. The alias reads better
  for the fixed, literal queries a program embeds.
- **Methods compose through labels.** A node is the intersection of its labels, so a
  vendor node that declares `parents: [CrmAccount]` answers to its own type's methods
  and to any method declared for `CrmAccount`. `x.is(SomeType)` narrows a row whose type
  is known only at runtime.
- **A program that imports the classes** can hydrate instead: `hydrateByType(rows,
  { GitHubIssue }, gateway)` returns typed instances.

#### Designing write methods

A type's write methods are what an agent will do to a customer, a deal or a ticket, so
design them for that caller:

- **Name the action in the business's words, and use the same name across realms.** A
  CRM realm's customer offers `addNote`, `scheduleFollowUp`, `bookCall`, whatever the
  vendor calls them, so a routine written against one stack reads the same against
  another. The method hides the vendor's call shape (`ids: [id]`, Odoo's command lists,
  Chatwoot's message types).
- **Make the safe outcome the default.** A note is internal unless asked otherwise; a
  calendar booking sends no invitation unless asked; a message to the customer needs an
  explicit flag. Something that cannot be recalled happens only when the caller says so.
- **Check before writing.** Validate dates, ids and required fields in the method and
  throw with the reason; an exception before the call is better than a bad record after it.
  A graph id is a string; convert it to the source's own id type in one checked place.
- **Each method calls one declared verb**, so what can change in the source is visible in
  `apis/` with its effect metadata, and approving a method is approving that verb.

### Manifest format

For a TS realm, generated by `embabel-build-manifest` (provided by `@embabel/runtime-types`) — never hand-authored. A wasm realm with no TS build hand-authors the same format (see [Execution hosts](#execution-hosts)). The host reads it at install time.

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
| `schedule` | manifest author | Optional cron expression (Spring 6-field); the host also runs the Realm Function on this cadence. See [Execution hosts](#execution-hosts). |
| `onType` | `export class X extends Entity` methods (or manifest author) | The entry is a method on a declared type, surfaced as `<obj>.<name>(args)` rather than a bare gateway function. |
| `className` | exported class name | Set for class-based type methods; the class to instantiate before invoking `name`. Absent for the function form. |

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

## World execution and isolation boundary

> **Forward-looking contract.** Current Me commonly derives `worldId` from `user.id` and accepts
> legacy user/workspace scope alternatives. The guarantees below are release gates for multi-world
> and shared-store deployment, not a description of current isolation.

Canonical terminology is defined in the [Realm domain glossary](./CONTEXT.md).

The portable rule is simple: **isolate by world and context; authorize every execution as exactly one
principal.** A world may admit several human and service principals. Concurrent executions of the
same Realm in the same world may therefore run as different principals without changing their data
boundary.

| Field | Contract role |
|---|---|
| `worldId` | Opaque, durable identity that partitions all private data, configuration, credentials, routes, receipts, caches, execution state, and canonical entities. |
| `contextId` | Explicit confidentiality boundary within a world. It never replaces `worldId`. |
| `principalId` | Human or service identity whose authority the execution uses. It authorizes and attributes the operation; it is not a data-partition substitute for `worldId`. |
| `executionId` | Identity of one durably admitted logical execution, stable across recovery and worker attempts. |

`userId` is not a portable Realm scope. A host may use it for a human account that is a principal or
may map it to a `principalId`, but Realm manifests, guest inputs, persisted scope stamps, and cache
keys never use `userId` as an alias for `worldId` or as the general runtime authority. Administration,
billing, and ownership are host management-plane concerns, not portable execution identities.

`principalId` is an opaque, stable identifier in the host security domain and is never recycled.
For federated authentication the host derives it from a verified issuer and subject, not from an
email address, display name, or unqualified provider-local id. Membership and access to each world
and context are separate policy and are rechecked at admission and every privileged handoff.

`worldId` is globally unique, persisted with the world, and independent of its administrative
account, name, and filesystem or deployment location. Renaming, moving, restoring, or transferring the same world
preserves its id. A copy intended to become an independent world receives a new id. Administrative
transfer does not rewrite world data or silently transfer authority: existing adoptions and
credentials pause until an explicit transfer policy revalidates them.

A host may subdivide a world into named knowledge or memory contexts. Such a context is identified
by `(worldId, contextId)` and is a confidentiality boundary with a versioned access policy. Every
context-owned node, edge, vector record, materialization, and positive or negative cache entry
includes `contextId` and the applicable access-policy revision. The default context is explicit; an
absent context fails closed. A context may narrow which principals can read within a world; it never
replaces `worldId` as the isolation boundary or authorizes a cross-world read.

The host binds immutable `worldId`, `contextId`, `principalId`, and `executionId` on every execution.
Realm code and request payloads cannot choose or override them. On-demand work uses the authenticated
caller as `principalId`. Autonomous work uses the run-as human or service principal selected by its
adoption. A signal, webhook sender, or channel author is input data, never the principal merely
because it caused an execution.

An adoption records who created or approved it for audit, separately from its run-as principal.
Those audit identities grant no execution authority. A platform may record `workerId` for the
process handling an attempt, but it is operational telemetry only: it grants no authority and enters
no data, credential, cache, cursor, route, or receipt key. Credential resolution is keyed by world,
context, principal, connection, and grant revision. Audit records include world, context, principal,
adoption when present, execution, trigger or sender data, observed world epoch, and optionally the
worker.

Realms in one world intentionally compose over that world's typed graph and gateway surfaces. Realms
in different worlds do not share data, credentials, routes, receipts, canonical entities, or mutable
caches, even when the same person owns both. Deployment-approved `Public`/reference datasets are the
only exception.

A host may share immutable code only when the canonical full-package `realmDigest` addresses it.
Sharing a worker never relaxes world scoping. Local and single-tenant deployments run the same path
with one world; deployment topology is not an authorization control.

The default identity of a world-visible persisted `Person`, `Organization`, mirror, bridge, or other
canonical entity is consequently `(worldId, WORLD, type, merge key)`. Context-private identity is
`(worldId, contextId, type, merge key)`: it cannot add properties or edges to a world-visible spine
until an explicit, policy-checked promotion makes that information world-visible. Cross-world or
organization-wide identity is a separate host capability: it needs an `orgId`, verified membership,
an adoption-visible grant, and an organization-scoped merge key. A bare email or domain must never
merge canonical data between contexts or worlds.

### Restore, transfer, and fork

At most one **world incarnation** may be active. Activation allocates a monotonically increasing
`worldEpoch`; every lease, dispatch, gateway call, token, and delivery handoff proves the current
epoch. Restore or migration preserves `worldId` only through an exclusive handoff that fences the
old incarnation before the new one runs. Restoring a copy while the original remains active is
rejected.

Restore preserves effect receipts so their idempotency identity survives recovery. It invalidates
leases, sessions, tokens, and captured routes. Any `IN_FLIGHT` or `OUTCOME_UNKNOWN` effect is
reconciled or surfaced for a decision, never automatically replayed. `worldEpoch` is a fencing value,
not part of an effect receipt key; incrementing it must not make the same logical effect spend again.

Administrative transfer is an atomic suspended state. Before the world resumes, host policy
revalidates or revokes principal membership, context ACLs, service principals, grants/adoptions,
credentials, sessions, tokens, routes, and queued work. Data, receipts, and audit retain `worldId`;
authority does not silently transfer with them. The world resumes under a new `worldEpoch`.

A fork is a new world, not a second incarnation. It receives a new `worldId`, new context ids, and
rekeys every private/context/canonical identity. It copies no adoptions, credentials, service
principals, routes, sessions, tokens, leases, queued work, or effect receipts. Those capabilities
require adoption in the fork.

## Execution hosts

> **Forward-looking contract.** The portable Docker capability boundary, fail-closed unknown-host
> behavior, and atomic artifact-set publication below require host changes. Until implemented and
> tested, current Docker/source-validation behavior is not a marketplace security boundary.

A realm ships logic and declarations. The platform supplies the sandbox, identity binding, resource
limits, triggers, and observability. Data enters through declared surfaces and leaves through gateway
calls. A portable realm never reaches around that boundary: no ambient credentials, direct
infrastructure, or mutable runtime shared with another realm.

Two consequences are normative:

- **Isolation.** Each dispatch runs in a sandbox with exactly the capability set its host defines. One realm's dispatches cannot observe or interfere with another's mutable runtime state, and no realm can change the host-bound world, context, principal, or execution. Realms deliberately share declared types inside a world; graph data is readable only through the current context/access policy or an explicit policy-authorized bridge. An implementation may pool processes and immutable content-addressed code, but every mutable object and gateway call remains world-, context-, and where principal-dependent, principal-scoped.
- **Statelessness between dispatches.** A handler must assume nothing survives from one dispatch to the next — no globals, no accumulated caches, no in-memory session. Durable state lives in the graph, written and read through the gateway. This is what lets a host run one instance or a thousand: any dispatch can land on any instance, so a realm scales independently of every other realm and of the platform itself.
- **A binding the runner was not given is NOT DECLARED.** Referencing it throws a `ReferenceError`
  rather than yielding `undefined`, so `if (violation)` does not guard it and neither does
  `violation ?? null`. Only `typeof` does, and it holds whether the identifier was never declared or
  declared without a value:

  ```ts
  const row = typeof violation === 'undefined' ? null : violation
  if (!row) { console.log('run by the duty that binds a row; nothing to do alone'); return { done: null } }
  ```

  **Guard every binding a handler does not always get**, and especially one supplied by a single
  caller — a duty's violating row, a signal's payload. `autonomous: false` and a comment saying "run
  by the duty, never on its own" do not prevent the handler being invoked; only the guard does. A
  host may surface a failed handler to the user, so an unguarded read is a stack trace in somebody's
  chat: a realm shipped exactly this, was reached on a chat turn, and answered a user who had just
  said their wife had died with a `ReferenceError` and ten frames of Node.

  Prefer a fallback where one is obvious — the current time for `now`, doing the work for real for an
  absent `dryRun` — and a no-op that says why where one is not. A handler should not depend on being
  invoked the way its author expected.

The Realm Function contract is independent of placement. Each host declares which executable
and declarative surfaces it supports, and admits them against the captured Realm and resource
grants. Parsing a producer, lens, API or event declaration does not authorize its execution.
A handler that needs npm does not become a Wasm function by relabeling it.
Two hosts exist:

| Host | What runs | Choose it when |
|---|---|---|
| `docker` | the compiled `dist/` JS modules, in the host's Node code sandbox | Default. Handlers need npm dependencies or the full TS project layout. Portable realm code still has no raw network or ambient credential access. |
| `wasm` | `dist/handlers.wasm`, in-process inside the host runtime | Functions are small and dependency-free, per-dispatch latency matters, or the deployment has no container runtime. |

The portable contract is capability-based on both hosts: no sockets, DNS, arbitrary `fetch`, process
environment, inherited file descriptors, or ambient credentials. External access goes through the
host gateway, which applies world/context scope, policy, receipts, quotas, and audit. A deployment may define
a privileged container extension with raw network access, but that is organization-reviewed host
code outside the portable/marketplace realm contract and must not be selected merely by declaring
`host: docker`.

Adding a host that consumes an existing artifact class changes nothing for a Realm author except the `host:` value. Functions keep their names and schemas, signals keep their identity, gateway calls keep their envelope, and the audit format stays the same. A candidate host that needs more than that from authors is not a host.

### Placement

`host:` in `realm.yml` is optional. The platform reconciles the declared value with what is on disk:

| declared | on disk | placement |
|---|---|---|
| absent | `dist/handlers.wasm` present | wasm |
| absent | no wasm bundle | docker |
| `docker` | no wasm bundle | docker |
| `docker` | wasm bundle present | **conflict** |
| `wasm` | bundle present | wasm |
| `wasm` | no bundle, `wasm/handlers.js` present | wasm — bundle built on load |
| `wasm` | no bundle, `wasm/handlers.ts` present | wasm — TypeScript compiled and bundled on load |
| absent | `wasm/handlers.ts` present, nothing else | wasm — handler source under `wasm/` **is** the declaration. It placed such a realm on docker until me#1565, which loaded no functions and showed `verbs: []`; if a host still does that, declare `host: wasm`. |
| `wasm` | neither | **conflict** |

A conflict surfaces as a world-loading problem with a one-sentence reason and a suggested `host:` fix; the realm's declarative content still loads. `docker` with a bundle present is a conflict deliberately: a stale bundle must never sit silently beside a host that isn't running it.

An unrecognized `host:` value fails the executable surface closed: the host records a problem and
loads the realm's declarative content, but registers no functions and never infers an executable host.

Three consequences of the table worth stating:

- With no `host:` declared, wasm artifacts decide placement by themselves: `wasm/handlers.js` beside a docker-style `src/` project places the realm on wasm, and the docker handler modules are not used for dispatch. Declare `host: docker` to keep a mixed-source realm on docker (the wasm bundle then surfaces as the conflict above).
- When both `wasm/handlers.js` and a bundle exist, the source is the truth: the host rebuilds the bundle whenever the source fingerprint changes ([build on load](#build-on-load)).
- The wasm kill switch is a dispatch-time control, not a placement input: with wasm disabled the realm still loads its declarative content, but its functions are unavailable and attempted dispatches produce a recorded refusal.

### Authoring a wasm realm

A realm written with `defineRealm` gets `realm.yml` and `dist/manifest.json` generated from one
`realm.ts`, and synth copies the handler entry it names (`wasm/handlers.ts` by default) beside
them; see [TypeScript realms](TYPESCRIPT_REALMS.md). By hand, a realm needs at least the three
files below: the realm, the handlers and the manifest that registers them.

```yaml
# realm.yml
name: ping
host: wasm
```

```js
// wasm/handlers.js
export async function ping(input, ctx) {
  return "pong";
}
```

```json
// dist/manifest.json
{
  "version": 1,
  "entries": [
    {
      "namespace": "ping",
      "name": "ping",
      "description": "Answers pong.",
      "inputSchema": { "type": "object", "properties": {} },
      "outputSchema": { "type": "string" }
    }
  ]
}
```

A handler file **contributes named handler functions**, and the manifest binds each declared function to one by its `name` (the `namespace` is manifest-side and never encoded in the code). A handler is `async (input, ctx)`: it **returns its result value directly** — the value described by the manifest's `outputSchema` — or **throws** to fail. The host wraps the return into the `{ result }` / `{ error }` wire envelope; authors never write the envelope. A return value must be JSON-serializable; `undefined` serializes to a null result. Three forms are supported:

```js
// Named export — one handler per Realm Function (the default). input-first, ctx second.
export async function ping(input, ctx) {
  return "pong";
}

// Default-export object — group a file's functions.
export default {
  async ping(input, ctx) {
    return "pong";
  },
};

// Register by name — for a file that cannot use export syntax (e.g. generated).
defineHandler("ping", async (input, ctx) => "pong");
```

The name a form contributes is the export identifier, the property key, or the `defineHandler` string. **Resolution is deterministic:** for each manifest function the host looks up its `name` among the contributed functions; a name contributed more than once, or by more than one form, is a load-time problem — a name is defined exactly once. **Discovery is the manifest's; the module supplies implementations.** The host reads the manifest for what functions exist — it never executes guest code to *discover* functions — then evaluates the module to *resolve* each entry's implementation (collecting the exports and any `defineHandler` registrations) and binds them. A function with no manifest entry is unreachable; a manifest function with no contributed function is a recorded load problem and is unavailable for calls or triggers; a realm with no manifest registers no functions at all.

`input` is the dispatch input, described by the manifest's `inputSchema`: the call arguments for an on-demand call, or the trigger-discriminated event for a signal- or cron-bound dispatch (see [routines that call a Realm Function](#routines-that-call-a-realm-function-and-dispatch-scoped-replies--forward-looking)). An on-demand call passes the arguments verbatim, with no `trigger` key; a function that a routine also targets distinguishes the cases by the presence of `trigger`. `ctx` carries:

| Member | Contract |
|---|---|
| `ctx.gateway.<namespace>.<method>(args)` | Calls back into the host's gateway surface — the same namespaces and schemas a TS handler or LLM-generated script sees. The host binds the world, context, access-policy revision, execution, and principal. On-demand calls run as the authenticated caller; autonomous calls run as the adoption's pinned principal. The guest never holds or presents a credential or scope key. |
| `ctx.log(message)` | Guest logging, surfaced in the host's logs against the dispatch. |
| `ctx.reply({ text, idempotencyKey })` | Dispatch-scoped reply to the triggering channel thread ([routines that call a Realm Function](#routines-that-call-a-realm-function-and-dispatch-scoped-replies--forward-looking)). Returns `{ status }` (one of the reply results listed there). Always present; on a dispatch with no live route it returns `{ status: "NOT_REPLYABLE" }` rather than being absent. |

**Statelessness applies to every form.** Every dispatch runs in a fresh instance, so nothing in the file survives between dispatches — a module-level variable and a value closed over by a default-export object both reset each dispatch. Durable state lives in the graph, through the gateway. `wasm/handlers.js` is compiled as a module; `defineHandler` is a host-provided global available both in that module and in a file with no `export` syntax — reach for it when generating a file that cannot use export syntax.

A realistic Realm Function — an activity digest over signals the realm's own event source ingests:

```js
// wasm/handlers.js — manifest namespace "chatops", name "digest" binds to export `digest`
export async function digest(input, ctx) {
  const limit = Number(input && input.limit) > 0 ? Number(input.limit) : 5;
  const messages = await ctx.gateway.signals.recent({
    type: "chatops.message",
    hours: 24 * 7,
    limit: 200,
  });
  const byChannel = {};
  for (const m of messages) {
    const channel = (m.properties || {}).channel_name || "unknown";
    byChannel[channel] = (byChannel[channel] || 0) + 1;
  }
  ctx.log("digest over " + messages.length + " message(s)");
  // Return the value directly — the host wraps it into the wire envelope.
  // Throw to fail; the host turns the thrown error into { error }.
  return {
    totalMessages: messages.length,
    channels: Object.entries(byChannel)
      .map(([name, n]) => ({ name, messages: n }))
      .sort((a, b) => b.messages - a.messages),
    recent: messages.slice(0, limit).map((m) => ({
      subject: m.subject,
      at: m.occurredAt,
    })),
  };
}
```

What the guest has, and what it does not:

| Available | Absent |
|---|---|
| `ctx.gateway.*`, `ctx.log`, plain JavaScript, JSON | Node (`require`, `process`, `fs`), npm packages |
| The function's `input`, described by the manifest's `inputSchema` | Network sockets, filesystem, environment variables |
| | Any credential or scope key. World and principal are bound host-side; there is no key to read, leak, replay, or substitute. |

The absences are the point: a wasm function is pure logic over gateway calls. A handler that needs an npm library, streaming I/O, or the filesystem belongs on the docker host. The engine is an embedded modern-ECMAScript interpreter, not Node: the language and its built-ins (`JSON`, `Promise`, `Math`) are there; host-shaped globals (`require`, timers, `fetch`) are not.

### Single file, or a typed project

Two authoring shapes carry the same function contract:

- **`wasm/handlers.js` — the zero-toolchain single file.** Plain JavaScript, no `package.json`, no npm. Compiled to `dist/handlers.wasm` on load. The whole realm is `realm.yml` + this file + a hand-authored `dist/manifest.json`. This is the floor.

- **`src/` — a TypeScript project.** When a realm outgrows one file — multiple handlers, shared helpers, real types — it authors a normal TypeScript project: many `.ts` files under `src/`, ordinary `import` semantics between them, a `package.json`, and a typed view of the gateway. The build type-checks, bundles the reachable module graph into one module, **extracts `dist/manifest.json` from the typed exports** (function names, `inputSchema`/`outputSchema` from the handlers' parameter and return types — the same schema-from-types generation TS handlers already use), and compiles the bundle to `dist/handlers.wasm`. The author runs the build; the shipped artifacts are the bundle and the generated manifest. Extraction sees exports only: `defineHandler` is a single-file form, so a `defineHandler` call in a `src/` project contributes no manifest entry and the build warns.

Types come from two places, both already in the ecosystem: `@embabel/runtime-types` supplies the `Ctx`, event, and envelope types, and a generated `.embabel/gateway.d.ts` (via `embabel-realm sync`) types `ctx.gateway.<namespace>.<method>` against the world's actual tool surface. So `ctx.gateway.signals.recent({ … })` autocompletes and type-checks, and a handler's declared `input`/return types drive the manifest schemas rather than being hand-copied into JSON.

```ts
// src/api/chatops.ts — typed, multi-file project
import { digestByChannel } from "../lib/aggregate";
import type { Ctx } from "@embabel/runtime-types";

export async function digest(input: { limit?: number }, ctx: Ctx): Promise<Digest> {
  const messages = await ctx.gateway.signals.recent({ type: "chatops.message", hours: 168, limit: 200 });
  return digestByChannel(messages, input.limit ?? 5);
}
```

The project layout and toolchain are the docker `src/` project's: source under `src/api/<namespace>.ts` (the filename is the namespace), each exported handler a function in that namespace, helpers under `src/lib/` excluded from extraction. Functions resolve by `(namespace, name)`, so `a.get` and `b.get` are distinct. The build bundles the reachable module graph from those entrypoints into one module and compiles it to the artifact its placement runs — docker JS modules, or a wasm bundle. `wasm/handlers.js` stays the no-build escape hatch; `src/` is the path when you want types, imports, and tests.

A wasm-targeted `src/` project ships its built `dist/handlers.wasm` and generated manifest as one
`artifactDigest`-bound set; the host does not build `src/` on load (build-on-load covers
`wasm/handlers.js` only). A marketplace accepts that set only when the platform built it from the
reviewed source or can verify a reproducible-build attestation. A local or organization-reviewed
installation may choose a weaker provenance policy, but still verifies the artifact-set digest.

`artifactDigest` covers the executable and manifest correspondence. The broader canonical
`realmDigest` covers **all author-controlled package content**: the artifact set plus handlers,
events/mappings, channels, types, producers, APIs, MCP/webhook declarations, prompts, and other realm
surfaces. Adoption and dispatch pin `realmDigest`; changing a non-code declaration can change
behavior just as surely as changing code.

Two points of this are _forward-looking_ convergence, not shipped today:

- **One signature across hosts.** The canonical handler signature is `(input, ctx)` with the gateway under `ctx.gateway` (as shown throughout). The docker `src/` handler today is `(ctx, args)` with the gateway passed directly as the first argument. The invocation convention is selected by a top-level manifest field `handlerAbi` — one of `"input-ctx"` (the default when absent) or `"ctx-args-legacy"` — applying to the whole artifact, never inferred from parameter names or arity (both are arity-two). Unifying on `(input, ctx)` so one `src/` serves both hosts is the convergence; the `(ctx, args)` form persists only under an explicit `handlerAbi: "ctx-args-legacy"`.
- **Manifest from types.** The single-file JS path hand-authors `dist/manifest.json`; the TS build extracting it from the typed exports is the same generation the docker `src/` build already points at.

### The manifest, schedules, and type methods

A wasm realm ships `dist/manifest.json` in the same [manifest format](#manifest-format) as TS handlers — hand-authored for the single-file JS path, generated by the build for a `src/` TypeScript project. The schemas drive the typed LLM surface exactly as for docker-hosted functions and are enforced by the host at invocation. `outputSchema` describes the unwrapped payload — the value the handler returns, before the host wraps it in the wire envelope — never the envelope itself. Two entry fields matter here:

| Field | Meaning |
|---|---|
| `schedule` | A cron expression (Spring 6-field, evaluated in the host's timezone). Installation makes the schedule available but **does not activate it**. It starts only after adoption under the same digest-bound grant as a routine, and a realm update pauses it until that grant is valid again. A host shows a realm's Manifest Schedules as routines of an agent it proposes for the realm, so they are adopted the same way. A **Manifest Schedule** passes empty args (`{}`), so every `inputSchema` field must be optional. (A scheduled routine in `agents/` instead passes `{trigger: "cron", firedAt}` under a different input contract; see [routines that call a Realm Function](#routines-that-call-a-realm-function-and-dispatch-scoped-replies--forward-looking).) |
| `onType` | The function is a method on a declared type — callable as `<obj>.<name>(args)` on an in-scope object, not as a bare gateway function. The handler receives the object as `input.self` and the caller's arguments as `input.args`. `schedule` does not combine with `onType`: a scheduled invocation has no receiver. |

A Trigger Registration has one discriminated identity everywhere it appears in adoption, dispatch,
receipts, and audit: `routine:<agent name, routine name, routine revision>` for a routine in `agents/`, or
`manifest-schedule:<namespace, name, schedule revision>` for a manifest entry. The schedule revision
is a canonical digest of the entry's schedule and invocation schema; `realmDigest` still pins the
rest of the package.

```json
{
  "version": 1,
  "generatedAt": "2026-08-01T00:00:00Z",
  "entries": [
    {
      "namespace": "chatops",
      "name": "digest",
      "description": "Summarize ingested channel activity — counts per channel and the most recent messages.",
      "schedule": "0 30 * * * *",
      "inputSchema": {
        "type": "object",
        "properties": { "limit": { "type": "number" } },
        "required": []
      },
      "outputSchema": {
        "type": "object",
        "properties": {
          "totalMessages": { "type": "number" },
          "channels": { "type": "array" },
          "recent": { "type": "array" }
        }
      }
    }
  ]
}
```

### Build on load

A realm that ships `wasm/handlers.js` is compiled to `dist/handlers.wasm` by the host when the realm loads:

- A content fingerprint over the handler source, manifest, and host build-toolchain identity decides whether to rebuild — a change to any member rebuilds, timestamp games don't.
- The build writes a candidate and atomically replaces the published bundle only on success. A failed build — bad JavaScript, a hung compiler, a missing toolchain — leaves the previous good bundle (or no bundle) in place and the realm's declarative content loaded, with a warning.
- The host publishes the bundle and manifest atomically as one artifact set. A failed rebuild keeps the previous complete set; a new manifest can never pair with a stale bundle.
- Bundles are build output. Don't commit them from a `wasm/handlers.js` realm — the host rebuilds on load. A `src/` project is different: the host does not build `src/` on load, so the project ships its built `dist/handlers.wasm` (and generated manifest), and that bundle is the truth if it disagrees with the source.

A realm may instead ship a prebuilt `dist/handlers.wasm` and no source — a **self-contained** realm. The host loads the bundle as-is. This is the right shape when the module is compiled from a language the host has no toolchain for.

### Limits

Normative for every host: dispatch time, guest memory, and payload sizes are bounded, and crossing a bound is an error the caller sees — never a truncation, never a hang. The concrete values are host operations, not something a realm can declare or rely on. The reference host's defaults:

| Setting | Default | Behaviour at the limit |
|---|---|---|
| `assistant.wasm.enabled` | `true` | `false` rejects every dispatch with a clear error — the kill switch. Declarative content is unaffected. |
| `assistant.wasm.dispatch-timeout` | 30s | The dispatch is interrupted and returns an error. Work longer than the budget cannot run on this host. |
| `assistant.wasm.max-memory-pages` | 1024 (64 MiB) | A module declaring more is rejected with a clear message. |
| guest I/O | 1 MiB per payload | Each of the function's args, its result, and every host-call request/response is bounded — at 1 MiB or the module's memory cap, whichever is smaller. Oversized payloads error rather than truncate. |

In the reference host, every dispatch is observable: it records the bundle, function, elapsed time, error if any, and how many gateway calls the guest made.

### Shipping a compiled module

`wasm/handlers.js` is a convenience, not the contract. The contract is the module's ABI, and any language that can target it — Rust, TinyGo, AssemblyScript, Zig, hand-written WAT — can ship a self-contained realm. Two conventions are accepted, and the host tells them apart by export probe: a module exporting `embabel_dispatch` is a reactor; anything else runs as a WASI command. Reactor wins if a module fits both.

**Reactor.** The module exports `memory`, `embabel_alloc(len: i32) -> i32`, and `embabel_dispatch(functionPtr: i32, functionLen: i32, argsPtr: i32, argsLen: i32) -> i64`, plus optional WASI `_initialize` (invoked before dispatch when present; `_start` is not called). All strings are UTF-8. The returned i64 packs a pointer to the response in its high 32 bits and the response length in its low 32; each half is read as a non-negative 32-bit value (so bounded by 2³¹−1) and must lie inside the module's memory, or the dispatch fails. Allocation is one-way: the host writes the function and args into guest memory through `embabel_alloc`; the guest allocates its own response buffer; nothing is ever freed, because every dispatch runs in a fresh instance discarded afterwards — which is also what enforces statelessness. The response must be exactly one JSON envelope, `{"result": ...}` or `{"error": "..."}`: anything else fails the dispatch, an `error` envelope fails it with that message, and a guest trap fails it with the trap's.

Reactor host imports live under module `"embabel"`: `call(reqPtr: i32, reqLen: i32) -> i64` invokes a gateway tool — request `{"tool": "<gateway name>", "args": {...}}`, reply an envelope the host writes into guest memory through `embabel_alloc` and returns with the same pointer/length packing — and `log(level: i32, ptr: i32, len: i32)` logs UTF-8 text (level 0 = debug, 1 = info, 2 = warn, anything else = error).

**WASI command stdio.** For interpreter-in-wasm bundles. The host writes exactly one request line to stdin — `{"function": "<namespace>.<name>", "args": {...}}` plus a newline — and runs `_start`. Stdout is line-oriented: a line whose first byte is NUL is a protocol frame; every other line is guest logging. A frame is a NUL-delimited marker — `\0embabel:call\0` or `\0embabel:result\0` — followed on the same line by the frame's JSON. A call frame carries `{"tool": ..., "args": ...}`; the host invokes the gateway and appends the reply envelope to stdin as a new line before the guest's write returns, so the guest reads the reply by blocking on stdin. There is no correlation id — calls are strictly one at a time, request then reply, in order. The result frame carries the dispatch's response envelope and must appear exactly once: no result frame, a second result frame, or a nonzero exit status each fail the dispatch. A NUL-prefixed line matching neither marker is treated as logging.

Both conventions speak the same `{ result }` / `{ error }` envelope at every hop. The guest gets byte-array stdio only — no inherited descriptors, no preopened filesystem.

### Three realms, three hosts

The same authored form runs on different hosts by changing one line. A pure-logic Realm with no dependencies and millisecond Functions uses the in-process host:

```yaml
# realm-levies/realm.yml
name: levies
host: wasm
description: "Computes council levies from the rates types it ships."
```

A dependency-heavy realm — renders invoice PDFs with an npm library, needs real Node — takes the sandbox:

```yaml
# realm-invoices/realm.yml
name: invoices
host: docker
description: "Renders and files invoice PDFs from billing signals."
```

And a host that does not exist — _forward-looking_, an illustration rather than a value you can write. Suppose a managed isolate pool: the platform ships the built bundle to a remote pool and fans dispatches out a thousand wide for burst work. The bundle is the same wasm artifact; nothing about the realm changes shape — a new `host:` value, and the platform grows an adapter:

```yaml
# realm-translations/realm.yml — HYPOTHETICAL: no host implements `isolate`;
# a conforming host records a metadata problem and leaves the executable surface unavailable
name: translations
host: isolate
description: "Translates document batches on demand."
```

`isolate` is not part of this spec. It is here to state the test every proposed host must pass: if supporting it forces a realm author to change anything beyond `host:`, the design is wrong.


### Me captured handler schema profile

The host checks manifest schemas before binding an approved handler, validates input
before entering its backend, and validates the unwrapped result before returning it.
This applies to direct calls, schedules, channels, lenses and producers. A method's
schema describes `args`; its transport envelope independently requires object-valued
`self` and accepts no fields beyond `self` and `args`, but `args` itself is typed by
whatever schema the method declares — a method with no schema of its own admits any
JSON value there, not only an object. Validation does not coerce values or add defaults.

The current profile supports these JSON Schema keywords:

| Contract | Supported fields |
| --- | --- |
| Types | `type`, including nullable type arrays |
| Objects | `properties`, `required`, `additionalProperties`, `minProperties`, `maxProperties` |
| Arrays | One `items` schema, `minItems`, `maxItems` |
| Strings | `minLength`, `maxLength`, measured in Unicode code points |
| Numbers | `minimum`, `maximum`, numeric `exclusiveMinimum`/`exclusiveMaximum`, positive `multipleOf` |
| Values and alternatives | Scalar `enum`/`const`, `allOf`, `anyOf`, `oneOf`, `not`, nested boolean schemas |

`title`, `description`, `default`, `examples`, `readOnly`, `writeOnly` and `deprecated`
are annotations. `$schema` may identify draft 2020-12 or draft-07. Unsupported
keywords, including references, definitions, patterns, formats, tuples and
`uniqueItems`, refuse the binding. The host performs no schema network or file access.
This is a bounded subset of [JSON Schema validation](https://json-schema.org/draft/2020-12/json-schema-validation), not a claim of full dialect support.

Each schema is limited to 64 KiB, 2,048 schema nodes and 16 nested schema levels.
Objects declare at most 256 properties or required names; enums contain at most
256 scalar values; each combination contains at most 16 alternatives. Input and
output are each limited to 1 MiB, 32 JSON nesting levels, 65,536 characters per
string and 100,000 JSON nodes. Numeric precision and absolute decimal scale are
limited to 1,000. Validation allows 100,000 steps; exceeding a limit refuses the call.
An empty schema still permits any value within these limits, while function input
must remain an object. Backend and surface limits can be stricter.

Malformed schemas, invalid values and exhausted limits produce a fixed refusal
without returning schema or payload contents. Final Realm admission is checked again
after output validation. Validation cannot reverse effects the handler already made.

### What placement never changes

- Function names, namespaces, schemas, and the manifest format.
- The `{ result }` / `{ error }` envelope, at the function boundary and on every gateway call.
- Signal identity: a signal dispatched by a wasm-hosted function is indistinguishable downstream from the same signal dispatched by a docker-hosted one.
- The identity model: execution is bound independently to a world and acting principal by the host; no host puts a credential or scope key inside the unit.
- Declarative schemas remain independent of placement. Activating a declaration requires host support and the applicable Realm and resource approvals.

### Captured handler producers

The current Me captured-execution profile excludes producers and virtual joins loaded from live
Realm files. Owner-authored definitions remain available. Producer execution and cache reuse
retain World and declaration checks; shared cache partitions include both. The legacy Wasm
producer example demonstrates the compatibility route, not captured resource admission.
Me also accepts the following captured handler producer profile. Each flat
`producers/*.yml` or `.yaml` file contains one version-1 object:

```yaml
# producers/movie-records.yml
version: 1
name: movie-records
handler: movie.records
keyArgument: keys
joins:
  - targetLabel: MovieRecord
    anchorLabel: Person
    relationship: HAS_RECORD
    keyField: id
    recordKeyField: personId
```

The binding retains an approved handler from the same installation. The handler
receives a JSON object whose `keyArgument` contains an array of string keys and
returns an array of record objects. Declare the target type and identity separately;
`recordKeyField` links records to their matching anchor keys. The host owns graph
scope and overlay metadata; records cannot supply `userId`, `worldId`, `workspaceId`,
`visibleTo` or `__vc*` properties. Sharing uses an explicit host operation.
Owner producer names take precedence and suppress conflicting captured joins.

This profile has no caching. A producer may declare [filter pushdown](HOSTED_EXECUTION.md#me-captured-producer-pushdown-profile)
so its handler filters at the source, and the separate
[paging profile](HOSTED_EXECUTION.md#me-captured-producer-paging-profile) to walk a
handler's own cursor across multiple calls within one fetch.

```yaml
# producers/incidents-by-service.yml
version: 1
name: incidents-by-service
handler: status.incidents
keyArgument: serviceIds
joins:
  - {targetLabel: Incident, anchorLabel: Service, relationship: HAS_INCIDENT,
     keyField: serviceId, recordKeyField: serviceId}
page: {argument: cursor, maxPages: 4}
pushdown:
  - {property: impact, argument: impact}
  - {property: status, argument: status}
```

```typescript
// wasm/handlers.ts
export async function incidents(input, ctx) {
  // input.serviceIds: string[]; input.cursor: absent on the first page
  // input.impact / input.status: string[], present only when the query pinned them
  const page = await ctx.gateway.statuspage.listIncidents({
    services: input.serviceIds.join(","),
    impact: input.impact?.join(","),
    status: input.status?.join(","),
    after: input.cursor,
  });
  return { rows: page.items, next: page.nextCursor ?? null };
}
```

A query reaches the producer only by traversing one of its joins from a bound anchor, as in
[Virtual Cypher §2](VIRTUAL_CYPHER.md#two-concepts-the-rest-of-the-spec-leans-on). A producer's
target may anchor another producer's join, so producers chain. Declare a pushdown rule for
every property the handler can filter on, since a filter left undeclared makes the handler
fetch everything the key allows. [TypeScript realms](TYPESCRIPT_REALMS.md#producers) shows the
same producer written with `defineRealm`. Me limits each fetch to
256 keys, 2,048 characters per key, 64 KiB of encoded arguments, 1 MiB of output and
1,024 rows. It accepts 32 flat declaration files, 8 KiB per file, 64 KiB total and
eight joins per binding. `page` and `pushdown` are optional; every other field shown is
required. Unknown fields, duplicate names or joins, aliases, tags and undeclared handlers are refused. These are host
profile limits, independent of backend placement.

A handler grant does not grant API or datasource access. Each host call still needs
its resource approval. Me supports an explicitly approved owned-data query profile:
`gateway.cypher.query({cypher, params})` returns `{rows, warnings, coverage}` and invokes only
same-installation captured producers. Statements require named owned nodes and a
final literal LIMIT from 1 to 512. See [hosted execution](HOSTED_EXECUTION.md#me-captured-graph-query-profile)
for limits, owner approval and excluded host operations.

## `mcp/`

Me keeps this legacy host configuration outside Realm execution. Use the
[captured handler migration](HOSTED_EXECUTION.md#legacy-executable-migration) for Me Realms.

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

MCP servers are lazy-loaded — the Docker container starts on first tool use, not on world init. A
mutable or credential-bearing MCP instance is keyed by `(worldId, contextId, realmDigest,
principalId, access-policy revision, grant/credential revision)` and is never shared across
contexts, principals, or worlds. A `worldEpoch` change destroys the instance or fences it from
all later calls. Only an immutable, credential-free server proven to hold no caller-derived state
may use a deployment-wide cache. Existing credential-fingerprint or config-only sharing is not a
shared-tenancy boundary.

## `commands/`

Captured commands map a slash name to an approved handler in the same Realm installation.
They do not grant handler access or select a host action.

```yaml
# commands/read-notes.yml
version: 1
command: read-notes
handler: notes.read
description: Read notes
```

Each flat `.yml` or `.yaml` file contains one object. Required fields are `version: 1`,
`command` and `handler`; `description` is optional. Command names match
`[a-z][a-z0-9-]{0,63}`. Handler names identify a captured `namespace.function` entry.
Description text is limited to 512 characters. A capture contains at most 32 command files,
8 KiB per file and 64 KiB combined. File basenames contain 1–128 ASCII letters, digits, dots,
underscores or hyphens and start with a letter or digit. Nested YAML paths, duplicate fields or command names,
unknown fields, YAML aliases/tags, invalid UTF-8 and version coercion are refused. Invalid
command declarations do not disable independently approved handlers.

The host binds each alias to the captured digest, installation and approval revision. It
checks the current owner World and handler approval during discovery, before execution,
at host callbacks and before returning results. Changing live Realm files cannot redirect
an alias. Revocation or a changed approval revision refuses retained aliases. Aliases with
the same name in multiple installations are unavailable; built-ins, owner action commands
and skills reserve their names.

`/read-notes {"skus":["SKU-A","SKU-B"],"limit":2}` passes that JSON object to the handler.
A bare command passes `{}`. Matching is case-insensitive and requires whitespace before
arguments. The host preserves JSON value types and rejects duplicate keys, trailing documents,
non-object input and arguments over 1 MiB. The handler result returns directly to chat.
Command input and results remain conversation content; credentials belong in the owner
wallet and must use an approved host credential binding.

Owner discovery exposes the command, Realm, handler, description, installation ID and
revision. These descriptors confer no authority. Hosts using captured execution do not
load legacy Realm `actionName` mappings. A host may retain owner-managed action commands
as a separate configuration surface:

```yaml
command: fix-issue
actionName: fix-issue
description: Fix an issue
```

## `webhooks/`

Webhook registrations — declare webhooks the realm wants to receive. When the realm is installed and the host has a public URL, these are registered with the external service.

Registration runs under the same trust tier as `apis/`: marketplace realms cannot interpolate a
credential into `register.args` or call a directly networked tool holding a durable secret. The host
binds registration and callback authentication to the world, context, access-policy revision, full
`realmDigest`, source-registration generation, run-as principal, and grant revision. Callback routing
also verifies the current `worldEpoch`. The templated form below is local/first-party compatibility
syntax.

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

## `events/` — event ingestion

Unifies push (webhook) and pull (polling) sources behind a single contract: **emit typed `Signal`s into the host's consequence engine.** A signal type is a `DomainType` declared in `types/` whose `parents` includes `Signal`.

The reference host implements both delivery modes — the poll sweep with signal-id dedup, and webhook delivery. Existing webhook receivers in `webhooks/` continue to work in parallel.

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

The host receives the webhook, verifies the signature, resolves its registered world and context,
projects the payload through the `mapping` into a `StripeEvent` instance, and emits it as a `Signal`
into the consequence engine. The payload cannot select or override that route.

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | Name of a type declared in this realm (or another loaded realm) whose `parents` includes `Signal`. |
| `webhook.signature` | yes | Signature scheme the host's built-in verifiers handle. |
| `webhook.signature-secret` | conditional | Env-var name holding the shared secret. Required for any non-`none` scheme. Conventional realms only: a captured realm's webhook channel names a declared credential in `signature.credential` (see [TypeScript realms](TYPESCRIPT_REALMS.md#channels)). |
| `webhook.tenancy` | yes | Strategy for routing the inbound webhook to a world. |
| `webhook.mapping` | yes | Map of type-property → JSONPath. Every required property of the `Signal` parent (`id`, `occurredAt`, `sourceKind`, `sourceId`) must be covered. |
| `webhook.tier-when` | no | Tier-override map. Each entry's value is a Jinja boolean expression evaluated against the parsed payload. First true wins; default tier is `AMBIENT`. |

### Polling event source

For services without webhook support — or where polling is preferable — declare a `poll` block
instead of (or in addition to) `webhook`. Polling reuses the host's task scheduler. Like a handler,
the source must be adopted before it can run. Its cursor identity is `(worldId, contextId,
adoptionId, sourceRegistrationId, type)`; the cursor record also carries the current principal,
realm, access-policy, grant, and credential revisions as fences. A principal, credential, or revision
change pauses polling. The host may resume the existing cursor only after proving it addresses the
same source stream; otherwise an operator must explicitly reset it. A reset is audited, and events
already persisted under the source's stable event identity remain deduplicated. No change silently
starts a fresh cursor and replays the source.

```yaml
# events/linear.yml
- type: LinearIssue
  poll:
    every: 10m
    api: linear                # the realm's already-learned API (apis/linear.yml)
    method: list_my_issues     # method name on that API
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
| `poll.args` | no | Arguments to the call. Jinja-templated against `{ cursor }` only. World, context, principal, and credentials are host-bound and unavailable to the template. Methods such as `list_my_issues` derive the subject from the bound credential. |
| `poll.cursor.param` | no | API parameter the host populates with the persisted cursor. |
| `poll.cursor.from` | no | JSONPath into each returned result, used to compute the next cursor (the maximum value across the batch becomes the new cursor). |
| `poll.mapping` | yes | Same shape as the webhook `mapping` block. |

A realm may declare both `webhook:` and `poll:` for the same type — the host prefers webhook delivery and uses polling as a backstop for catch-up after downtime.

### Why this matters

Both sources produce `Signal`s of the realm-declared type. From there, the consequence engine, triage rules, persistence (`SignalRecord`), notifications, and chat surfacing are all type-aware: `signal.type.isAssignableFrom(StripeEvent)` is a real predicate, not a string match.

No JVM bytecode is shipped — realms that need behaviour beyond mapping should expose it via `actions/` (LLM-driven) or `mcp/` (sandboxed servers).

## `channels/` — realm-shipped channel connectors

A channel is a general data pipe, including provider messages, webhooks, database changes
and Realm-produced events. It may carry data in either direction. `channels/` declares
provider connector drafts; `data-pipes.yml` declares captured sources and consumers. See the
[hosted data-pipe contract](HOSTED_EXECUTION.md#data-pipes) for source identity, grants,
publication, atomic polling positions, receipts and checkpoints.

The governed host requires owner approval and owner-scoped credential references before
starting a provider connector. A Realm declaration, `auto-start` value or process environment
variable grants no runtime authority. The following legacy connector format applies only
where the host explicitly supports it; it does not replace the owner lifecycle API.

A realm configures a connector the host implements — host-extension via FQN, the same dispatch pattern as `PolicyActionSpec`:

```yaml
# channels/discord.yml
type: com.embabel.world.event.channel.discord.DiscordChannelConfig
name: discord
token-env: DISCORD_BOT_TOKEN
auto-start: true
```

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | FQN of a host-provided channel connector configuration. The host documents which connectors it ships; a realm cannot ship connector code. |
| `name` | yes | The channel's name on this world. |
| `token-env` | connector-specific | Legacy credential name resolved by a trusted host. Governed hosts require owner-scoped credential approval. Values never belong in the Realm. |
| `auto-start` | no | Legacy startup preference. Governed startup also requires current owner approval and a supported provider lifecycle. |

`auto-start` controls the connector lifecycle only; it does not adopt or activate any handler or
manifest schedule. A credential-backed live connector registration is owned by exactly one world in
the portable v1 contract. If another world attempts to use the same provider credential, the host
must reject the second registration rather than instantiate another session or silently attribute
both worlds to the first owner. Organization-owned shared connectors require a later explicit
`orgId` membership and route-attribution contract.

Within that world, every inbound and reply route is bound to one explicit context, access-policy
revision, and run-as principal. A connector session may multiplex such routes only when it keeps those
bindings separate; it never broadcasts an event or reply route into every context by default.

Provider adapters map incoming data to host events. The governed host appends the event to a
durable journal before acknowledgment, then projects signals or invokes approved consumers
with independent checkpoints. A provider message, a journal receipt and a completed consumer
effect have different completion semantics.

Provider-specific addressing, conversation identity and reply rules belong to the connector
implementation. `channels/` references only host-provided connector types; a Realm cannot
install JVM connector code. General Realm-produced sources use captured declarations and
sandbox callbacks instead.

An unknown `type` is reported against the file and that channel is skipped; the realm's other content loads.

## `agents/` — Agents and their Routines

An **Agent** is a named colleague a realm proposes: a job, the routines that do its work, and the
duties it keeps. Where `events/` produces signals, an agent's **Routines** react to them or to a
cron schedule. Everything here is a proposal. The world that installs the realm decides who answers
for the agent, what it may do, and whether it runs, so a realm never declares those things.

```yaml
# agents/reviewer.yml
name: reviewer                        # stable id; the world shadows a realm agent of the same name
job: Make sure nobody waits on a review from me
routing: Pull requests, review requests, who is waiting on whom   # "ask me about…"
persona: terse                        # optional; a personality the host already has
routines:
  - name: pr-review                   # stable within the agent
    description: When a review is requested on one of my PRs, notify me
    match:
      signalType: github.pr_review_request   # a Signal type name (from events/ or types/); "*" = any
    schedule: "0 0 8 * * *"          # optional 6-field cron; fires on a schedule too (omit for signal-only)
    spec:
      kind: typescript
      module: pr-review.routine.ts    # sibling file under agents/, inlined at load (or inline `source: |`)
duties:                               # forward-looking: declared and shown, not yet kept by a host
  - name: no-stale-reviews
    text: No review request waits more than a working day
    holds: StaleReviewRequest         # a view, lens or DERIVE label that should stay empty
    every: "0 0 * * * *"
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Stable id. A world agent of the same name shadows the realm's. |
| `job` | yes | One sentence, in the words of the person who will answer for it. |
| `routing` | no | What to ask this agent about, for a host that routes questions to colleagues. |
| `persona` | no | A personality the host already has, or one this realm ships under `personalities/`, named `<realm>/<slug>` to say which realm's (`realm-bible/jonathon`). A persona confers no authority, but it is part of what the sponsor signs: for an agent people talk to it is the behaviour, guardrails included (see [Signed versions](#signed-versions)). |
| `conversation` | no | How the agent is talked to: the realms it reaches, the host tools it keeps, the skills it brings in by name, its model role and the sampling a caller may ask for. See [Talking to an agent](#talking-to-an-agent). |
| `routines[]` | no | The work it does without being asked. Fields below. |
| `duties[]` | no | Conditions it keeps true, each naming the view, lens or DERIVE label that should hold. _Forward-looking._ |
| `state` | no | Only `retired`, to withdraw an agent the realm used to ship. Any other value is ignored. |

**What a realm does not declare.** `sponsor`, `owners`, `operators`, the agent's stage, and a
routine's or duty's stage are the world's to decide, and a host ignores them in a realm's agent
file. A realm that could name who answers for its own agent would be vouching for itself, and one
that could set its own stage would go on duty the moment it was signed. A realm agent arrives off
duty with no sponsor.

A routine may declare `match` (signal-triggered), `schedule` (cron-triggered), or both.

| Routine field | Required | Meaning |
|---|---|---|
| `name` | yes | Stable id within the agent. |
| `description` | no | One line shown with the agent. |
| `match.signalType` | no | Signal type that fires it — a host signal or a realm signal (`github.pr_review_request`). `*`/omitted = any signal. |
| `schedule` | no | 6-field cron expression, registered on the host's normal cron path. |
| `spec.kind` | yes | `typescript`, or `function` to target a manifest-declared Realm Function (below). |
| `spec.source` / `spec.module` | for `typescript` | Inline TS, or a sibling file inlined at load. |

### What an agent may ask for — _forward-looking_

These field names are reserved on an agent so that a realm can state what its agent needs and a
world can grant less. Each is a request; none is honoured by being written down, and a host that
does not yet read one ignores it.

| Field | A realm requests | The world decides |
|---|---|---|
| `authority` | Which verbs its routines call, at what level, with what argument rules | What is granted, which may narrow the request and never widen it |
| `qos` | Priority class, deadlines, freshness, serialisation, how to degrade | Budgets, source shares, freeze windows |
| `colleagues` | Which kinds of colleague it expects to message | Which it may actually reach |
| `roles` | Which [LLM roles](#llm-roles) its work leans on | Which model plays each |
| `battery` | Cases that must fire and must not fire, run before adoption | Whether the results are good enough to adopt |

### Stage: off duty, observing, on duty

Whether a routine runs, and whether it may change anything, is its agent's **stage**, set by the
world and never by the realm:

| Stage | Wire | Meaning |
|---|---|---|
| Off duty | `off` | Nothing it holds runs. |
| On duty, observing | `observing` | Its routines run against a read-only gateway: they read and judge, and every effect is refused and reported. |
| On duty | `on` | Its routines run and may take effects. |

The world may set a stage per routine as well as per agent. This replaces the Trigger Binding's
`autonomous` flag, which a routine does not have.

### Signed versions

A world runs the version of an agent its sponsor last **signed**: the definition, each routine's
body and trigger as they were, a digest of every view a duty names, and the files of its persona as
they render. A realm update, an edit, or
a changed view appears on the agent as an unsigned change and reaches nothing until the sponsor
signs again. An agent that has never been signed runs nothing.

### Talking to an agent

An agent with a persona and no routines or duties is one people **talk to**, and any agent may be
talked to. A conversation with an agent speaks in its persona and reaches only what its
`conversation` block allows:

```yaml
# agents/jonathon.yml
name: jonathon
job: Help people read scripture, and be known while they do.
routing: Ask me about the Bible, a passage, a person in the text, faith or doubt.
persona: realm-bible/jonathon
conversation:
  realms: [realm-bible]                  # default: the realm that ships the agent
  builtins: [memory, views]              # host tools kept; name the fewest the job needs
  skills: [diagrams]                     # skills by name, beside what realms and builtins bring
  llm: chat_best                         # an LLM role, never a model; default: the host's chat role
  sampling:                              # what a caller may ask for; omitted = the role's own settings
    temperature: [0, 0.7]
    maxTokens: 2000
authority:
  default: never
```

| `conversation` field | Meaning |
|---|---|
| `realms` | The realms the conversation reaches. The host binds the conversation to them and enforces the binding where every call is dispatched, not only in what the model is shown. |
| `builtins` | Which of the host's own tools the conversation keeps, by category: `code`, `graph`, `views`, `data`, `memory`, `documents`, `attachments`, `images`, `artifacts`, `apps`, `host`. `true` keeps all, `false` none. A host tool in no listed category is dropped. A realm's own tools are governed by `realms`, not this. Omitted means all, which is almost never what an agent should have — see [Scope it to the job](#scope-it-to-the-job). |
| `skills` | Skills brought in by name, in addition to what `realms` and `builtins` bring: a host-provided skill, or one the world installed or wrote, that the named `builtins` categories would otherwise leave out. Three limits. A realm's skills arrive only with the realm: naming a skill another realm ships, without that realm in `realms`, is refused, and the refusal says to add the realm. A name brings in a skill and never a tool — host tools stay by category. A name that matches no skill is a validation error for the agent, listing the skills that exist. See [Scope it to the job](#scope-it-to-the-job). |
| `llm` | The [LLM role](#llm-roles) the conversation runs on. A realm never names a model, and a caller cannot choose one. |
| `sampling.temperature` | The range a caller's `temperature` is clamped to. |
| `sampling.maxTokens` | The most a caller's `max_tokens` may ask for. |

#### Scope it to the job

An agent's conversation SHOULD reach the fewest tools its job needs, and a realm SHOULD name its
`builtins` rather than take the default. This is not tidiness. A model chooses among the tools it is
shown, and every tool outside the job is one more wrong turn it can take: offered forty tools, a
scripture agent reached for entity search, a vector search and a code runner instead of the view
that answered, then filled the gap from its own recall — fluent, confident, and wrong. Offered the
handful its job needs, the same model on the same question ran the view. A narrow scope is what
lets a small, cheap model be a reliable colleague, and no model is reliable choosing among tools it
should never have seen.

So:

- Start from `builtins: [memory, views]` for an agent that answers from a realm's views, and add a
  category only when the agent cannot do its job without it — and can show it.
- A view that retrieves inside itself (`RELEVANT_TO`, a producer) needs no `documents` or `graph`
  category; the host runs the retrieval when the view runs.
- Name realms the same way: `conversation.realms` lists the realms the job draws on, not every
  realm the world happens to have.
- Name `skills` with cause. Every skill added is one more choice the model makes on every turn —
  its description is read, weighed against the question, and sometimes chosen instead of the view
  that answers. Add a skill when a question the agent must answer needs it, and not because it might
  come in useful.

**What the conversation is offered.** Exactly four things: the tools and skills of the realms
`realms` names; the host tools of the categories `builtins` names, with any host skill that documents
one of those categories; the skills `skills` names; and the few a host keeps on every conversation
(its notes and progress reporting). Nothing else — not another realm's tools or skills, not the
world's own APIs, not a host tool or skill that belongs to no named category. A host SHOULD report the tool surface each turn
was offered, so an author can check it, and an author SHOULD check it before judging how the agent
behaves: an agent that misbehaves with tools it should not have is a scoping defect first.

**Who can be talked to.** Only an agent that may work: signed, with a sponsor, active, not off duty,
and in a world that is not halted. A host refuses a conversation with any other agent and says
which of these is missing, and it checks again on every turn, so standing an agent down ends its
conversations at the next message.

**What a stage means here.** Observing, an agent talks and reads, and every effect it attempts is
refused and reported. On duty, what it may change is its signed `authority`, exactly as for its
routines; a conversation borrows no authority from the person talking. Talking never shows the
person more than they could see themselves: the agent sees the intersection of its own scope and
the speaker's access.

**A caller can narrow, never widen.** Everything a caller may ask for (below) tightens what the
agent does or what is shown. Nothing a caller sends adds a realm, a tool, a verb or a model.

### From an OpenAI client — _host surface_

A host may expose every agent through the OpenAI chat API, so tools that speak it (Open WebUI,
LibreChat, an OpenAI SDK) talk to an agent unchanged. The caller authenticates as themselves, with
an API key sent as `Authorization: Bearer`, and is the speaker. A host should offer **agent keys**:
a key minted for named agents (or any) that talks only to them, reaches nothing else of its owner's,
and lists only them as models — the key to paste into a chat client.

| Path | Meaning |
|---|---|
| `GET <base>/openai/v1/models` | The agents the caller can talk to now, each an OpenAI model whose `id` is the agent's name. |
| `POST <base>/openai/v1/chat/completions` | Talk to the agent named in `model`. |
| `GET`/`POST <base>/agents/<name>/v1/…` | The same for one agent, for a client that cannot choose a model. `model` is ignored. |

**Standard parameters.**

| Parameter | What the host does |
|---|---|
| `model` | Names the agent. Never chooses a model: the model is the agent's `conversation.llm` role. |
| `messages` | The client's whole history. Only the newest user message is a new turn; the conversation is recognised as described below. |
| `stream` | Answered as server-sent `chat.completion.chunk` events ending in `[DONE]`. An agent produces messages rather than tokens, so each message arrives as one chunk. |
| `temperature`, `max_tokens` (`max_completion_tokens`) | Honoured within the agent's `sampling` bounds and clamped to them. With no bounds declared, the role's own settings stand and the value is ignored, since common clients send one on every request. |
| `top_p`, `stop`, `seed` | Passed to the model when the role's provider supports them; otherwise ignored. |
| `user` | The client's end-user id, kept apart in recognising conversations. |
| `tools`, `tool_choice`, `response_format` | Ignored. The agent's tools are its own, and a caller cannot hand it others. |

**Embabel parameters**, sent as extra fields in the request body. Each narrows; none widens.

| Field | Meaning |
|---|---|
| `embabel_conversation` | A conversation id the caller chooses. The same id from two clients is the same conversation. Without it, a conversation is recognised by the caller, the agent, `user` and the first user message. |
| `embabel_observing` | `true`: every effect the agent attempts in this turn is refused and reported, even if it is on duty. |
| `embabel_realms` | Narrow the conversation to some of the agent's `conversation.realms`. A realm outside them is ignored. |
| `embabel_verbosity` | `terse`, `normal` or `full`: how long an answer the agent gives. It shapes the reply and never changes the agent's rules. |
| `embabel_evidence` | `true`: the response carries an `embabel` object with the conversation id, the run and the requests the turn raised. |

**What the flat shape hides.** One answer per turn, with no progress or tool activity. A request the
agent raises for a person's approval is named after the answer, with where to approve or reject it:
a link to the host's approvals when the host knows where they are. Nothing is approved from the
client.

### What an inline routine sees

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

A routine reacts through the typed `gateway.*` surface — read with `gateway.kg.query`, judge with `gateway.ai.classify`, act with Realm Functions or `gateway.notifications.createNotification`. Reads and `gateway.ai.*` are always safe; **guard writes with `if (!dryRun)`**.

```ts
// agents/pr-review.routine.ts
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

### Activation — _forward-looking_

Installation makes a realm's agent **available, not runnable**. Adoption, which is putting the agent on duty, makes its routines runnable and pins
the full-package `realmDigest`, Trigger Registration identities, compiled capability-grant digest and
revision, `worldId`, `contextId`, access-policy revision, and one run-as **`principalId`**. The
principal may be the adopting human or a service principal they are allowed to delegate to. The
adoption retains its `adoptionId` across reapproval and records its creator and approvers for audit;
those records confer no runtime authority. A signal sender is data, never authority. Cron and signal
triggers run as the adoption's principal; an on-demand call runs as its authenticated caller.

Changing Realm content, the Trigger Registration, compiled grant, run-as principal, context, or its
access-policy revision increments the adoption revision and pauses new dispatches. Reapproval keeps
the same `adoptionId`; deleting and recreating an adoption creates a new one. Disabling or removing a
principal pauses every adoption that runs as it and invalidates its credentials and mutable caches.
Removing an approver triggers host-policy revalidation of adoptions they approved, but does not
silently revoke or inherit an independently authorized service principal's authority.
An organization may auto-approve a compatible change only under an explicit reviewed rule; the host
never silently carries approval forward or expands
an adoption's authority. The host surfaces a realm's agents in its activation UX and over MCP. Whoever adopts an agent
becomes its sponsor unless the world names another. A scheduled routine uses the normal cron path;
there is no second scheduler. World agents shadow realm agents on name collision.

An observing stage is a legibility aid, not a proof of future behaviour: realm code can branch on
inputs or time after adoption. Security comes from the host-bound grant and method classification.
Only host-vetted gateway metadata may classify a method as `READ`; realm, MCP, or tool-authored
claims are `UNKNOWN` until reviewed. Observing dispatches deny both `EFFECT` and `UNKNOWN`,
including nested gateway calls.

### Routines that call a Realm Function, and dispatch-scoped replies — _forward-looking_

A routine may target a Realm Function instead of embedding inline TypeScript. The same routine surface dispatches a manifest-declared function on either execution host:

```yaml
# agents/support.yml
name: support
job: Answer questions in the support channel
routines:
  - name: discord-autoreply
    description: Reply to questions in the support channel
    match:
      signalType: discord.message
    spec:
      kind: function
      function:
        namespace: discord
        name: onMessage
```

Rules:

- `function` resolves against the owning realm's manifest. A missing target, or a target carrying `schedule` or `onType`, rejects the routine at load with a recorded problem.
- The routine is declarative content: it loads (inactive) even when the manifest or executable surface is unavailable, and cannot dispatch in that state.
- One execution per (signal, routine); two routines targeting the same function create two executions.
  Before fan-out, the host durably admits autonomous work by atomically inserting its deterministic
  `executionId`, derived from `(adoptionId, trigger-registration generation, concrete trigger
  occurrence)`. The same occurrence therefore retains one id across crash recovery and worker
  attempts. An on-demand call receives an `executionId` at durable admission. Its request
  idempotency mapping is keyed by `(worldId, contextId, principalId, target function, request
  idempotency key)`, so transport retries reach the same execution without deduplicating or exposing
  another principal's work. The mapping stores a canonical request digest and rejects reuse of the
  same key with different arguments. A call without a request idempotency key is a new execution. An
  explicit operator replay creates a new `executionId` linked to the original in
  audit. A crash after signal deduplication but before queueing must leave a recoverable `QUEUED` or
  `ABANDONED` record, never only an in-memory gap. Multi-instance hosts put the lease epoch/fencing
  token in host-only dispatch context; every gateway, effect, and delivery handoff atomically
  verifies current `RUNNING` ownership, world epoch, principal authority, and adoption, refusing a
  partitioned stale worker. A host without those controls must declare itself single-instance. v1
  is at-most-once after admission and does not retry guest execution.
- Routines are **inactive until their agent is adopted**. An observing stage runs the function against a read-only gateway: mutating calls return a coded refusal (`channels.reply` returns `NOT_PERMITTED`). Enforcement is host-side; there is no flag the function is trusted to honor.
- The dispatch input is trigger-discriminated: `{trigger: "signal", signal: {id, typeName, subject, occurredAt, source, properties}}` for a signal firing; `{trigger: "cron", firedAt: <ISO-8601>}` — no `signal` key — for a scheduled one. A routine may declare both `match` and `schedule`. At load the host validates the target and schema and rejects any trigger shape it can prove incompatible. Immediately before every concrete signal or cron dispatch, it validates the complete input against `inputSchema`; invalid input records a failed dispatch and guest code does not run. Transport, thread, connector, `worldId`, and principal details never appear in either variant.

A Realm Function dispatched by a channel signal may reply to the originating thread. The handler receives the trigger-discriminated event as its first argument and `ctx` as its second:

```js
// wasm/handlers.js — invoked on discord.message by the support agent's routine
export async function onMessage(event, ctx) {
  if (event.trigger !== "signal") return null;                // no reply route off a cron firing
  if (!event.signal.properties.content.includes("?")) return null;
  const r = await ctx.reply({
    text: "Looking into it.",
    idempotencyKey: "autoreply-" + event.signal.id,
  });
  return { replied: r.status };
}
```

`ctx.reply({ text, idempotencyKey })` is the dispatch-scoped reply — sugar over `ctx.gateway.channels.reply`, which takes **no destination and no signal id**: the reply can only reach the thread that triggered the current dispatch, and only while that route is live (connector-configured expiry). It returns `{ status }`, where `status` is one of `SENT` (provider-acknowledged) | `OUTCOME_UNKNOWN` (handoff without acknowledgement) | `NOT_REPLYABLE` (no channel route: cron trigger, non-channel signal) | `NOT_PERMITTED` | `EXPIRED` | `CONNECTOR_UNAVAILABLE` | `REJECTED`. Multiple replies in one execution are serialized by host acceptance order and bounded by a host-configured per-routine and per-route reply budget; exhausting the budget returns `REJECTED`. The receipt key is `(worldId, contextId, executionId, surface, operation, idempotencyKey)`, so the same author key in independent executions never collides. `principalId`, `adoptionId`, `realmDigest`, policy/grant revisions, and `worldEpoch` remain immutable audit or fencing fields on the execution and receipt, not key fields; changing one cannot make the same logical execution spend again. An omitted key is derived from the durably recorded execution-local acceptance sequence. The outbound envelope is `{text}` only. A connector's own outbound messages never fire routines; the reply budget bounds loops involving other bots that self-echo suppression cannot identify.

Proactive sends to a channel with no triggering signal are a different authority and not part of this contract.

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

The referenced action receives one node snapshot and returns a structured `DecorationResult`
describing what to write. The host owns persistence and binds world, context, principal, and
execution out of band; none is serialized into the action input. The action stays pure.

**Input bindings** (the action's `inputs:` block in `actions/<name>.yml` must accept these):

| Binding | Type | Meaning |
|---|---|---|
| `nodeId` | string | The candidate node's stable id |
| `nodeName` | string | The node's display name |
| `nodeLabels` | list&lt;string&gt; | Every Neo4j label on the node |
| `nodeProperties` | object | Map of realm-visible properties on the node. Reserved host metadata is redacted. |

**Output type**: `DecorationResult` (a host-provided domain type). Action declarations set `outputType: com.embabel.world.kg.decoration.DecorationResult`.

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

Reserved host metadata includes scope, identity, policy, lease, provenance-control, and credential
fields such as `worldId`, `contextId`, `principalId`, `executionId`, and `worldEpoch`. Retired or
legacy host identity fields remain reserved so old data cannot be forged. Reserved metadata is never
included in `nodeProperties`. The host rejects `propsToSet`, relationship targets, or any other guest
result that attempts to set, remove, or substitute a reserved field.

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

HTML apps the realm ships. A realm-bundled app is served at **`/apps/{realm-name}/{name}.html`** (the reference host, verified 2026-09-23: `/apps/github-actions/ci-health.html`; `/apps/{name}` and `/api/v1/apps/{name}` answer 404 for it). Vibe-coded and world-template apps share the `/apps/{name}` resolution below:

1. `<world>/data/apps/{name}` — user-owned (vibe-coded), highest priority
2. `<world>/config/apps/{name}` — world-template apps shipped with default-world
3. `<world>/config/realms/<realm>/apps/{name}` — realm-bundled apps (this directory)

A realm app's manifest entry takes a `title` — the name shown for the app. Without one a host
may derive it from the file stem (`ci-health` → "Ci Health"), so an acronym needs it spelled:
`"title": "CI Health"`.

**Ship the Embabel badge.** An app is expected to carry the attribution block before `</body>`:
a fixed-position `<div id="embabel-badge">` linking to worlds.embabel.com. The host's check is
deliberately fuzzy — it looks for the well-known `embabel-badge` id, not for exact markup — and
the vibe-coding path *injects* the block when it is missing. Nothing injects it into a
realm-shipped app, so a realm ships its own, and the app harness
(`vibe-apps/browser-harness.md`) asserts it is visible in the viewport rather than merely present.

A user can shadow a realm-bundled app by vibe-coding one with the same filename. Realm apps are read-only from the user's perspective; they're refreshed whenever the realm is updated.

```
apps/
├── github-dashboard.html
├── github-dashboard.svg     # its icon (optional)
├── pr-review-board.html
└── shared/                  # assets several apps load (optional)
    ├── board-core.js
    └── board.css
```

**Apps may share files.** Every file under `apps/` is served at its own path — `/apps/<scope>/shared/board-core.js` —
with a content type from its extension (`.js`, `.mjs`, `.css`, `.json`, `.svg` and common images), so a realm
that ships several apps (or editions of one) keeps their common script, styles and data in one place and each
page loads them with an ordinary relative `<script src>` or `<link href>`. Subfolders are allowed. A host
serves nothing outside the realm's `apps/` directory: no `..`, no absolute paths, no hidden (dot) files or
folders, and no symlink that leads out. Only `.html` files directly in `apps/` are listed as apps; everything
else is an asset. When a user copies a realm app to customise it, a host should keep the copy pointing at the
realm's shared assets rather than copying them, so the fork still receives the realm's updates.

**An app may declare its own icon**, by the means the web already has — a
`<link rel="icon" href="…">` in its `<head>`. The `href` must be a plain
filename beside the app in this directory (no `/`, no `..`, no URL); a host
serves it from the same `/apps/{name}` resolution as the app itself and draws
it wherever the app is listed. An app that declares none is listed as before.
This is per-app and separate from the realm's own [`icon`](#icons): a realm
shipping three apps can give each its own.

**A captured realm's apps work differently.** Each page ships with an `apps/<name>.html.app.json`
declaration naming the handlers it may call, and the owner approves every app on its own. The
page runs in a sandboxed frame with no network: it reaches the realm only through
`realm.call(handler, arguments)`, one call at a time, and everything it needs is inlined into
the page. The rest of this section describes the conventional app runtime, which a captured
page does not get. See [captured browser apps](HOSTED_EXECUTION.md#captured-browser-apps) for
the declaration, the operator's size limits (10 MiB by default) and the bridge.

Realm apps must use the same architecture as vibe-coded apps: tool-gateway calls via `fetch('/api/v1/tools/{name}')`, no direct external fetches. They have access to all the user's tools (MCP, learned APIs, etc.) because they run in the user's authenticated session.

**Prefer invoking a named Lens over calling raw tools.** An app that posts to `/api/v1/lenses/{id}/invoke` gets a result the realm has already shaped, scoped and caveated; an app that assembles raw tool calls duplicates that reasoning in a browser where it cannot be tested or reused. Keep the app to presentation: it should choose a Lens and render what comes back, never decide what to fetch. This also honours the rule below — an app must not accept or submit arbitrary Cypher or JavaScript from a browser.

**What "no direct external fetches" does and does not cover.** The prohibition is on the app reaching a third-party *data* API itself — that would bypass the gateway's auth, scoping, quotas and provenance, and would leak keys into the browser. It does not prohibit ordinary outbound *navigation*: an `<a href>` deep link to an external site (a map, a source document, a public register entry) is how a surface cites its sources and should be encouraged. Embedding third-party runtime assets — a map SDK, tiles, remote fonts — is a different question again: it adds a network dependency and a privacy surface the host does not mediate, so treat it as a deliberate choice rather than a default, and never let a provider's key reach the page. A realm that wants map rendering without that dependency can deep-link out instead, which also keeps provider terms about attribution and caching simple to honour.

### Linking into an app

An **app link** opens an app at a place inside it:

```
app://<scope>/<name>#<route>
```

`<scope>/<name>` is the app's own address: the same one it is served at, `/apps/<scope>/<name>`. That
address is unique in a world, so an app link cannot collide with another app's, and nothing is
registered or declared to make one work. The `.html` suffix may be left off.

```
app://google/mail#/thread/18f3a2c
app://google/mail.html#/thread/18f3a2c     # the same app
```

**The route is the app's business.** A host opens the app with `#<route>` and does not read it. The
app reads `location.hash` when it loads and follows `hashchange` after that: when the app is already
open, a host changes only the route, and does not reload the app.

```js
// apps/mail.html
function route() {
  const m = location.hash.match(/^#\/thread\/([A-Za-z0-9_-]+)$/)
  if (m) showThread(m[1])
}
addEventListener('hashchange', route)
route()
```

**Treat the route as untrusted input.** Anything that can produce a link can put anything after the
`#`. An app matches the route against the shapes it expects, as above, and ignores the rest. It never
passes route text to `eval`, `innerHTML`, a lens argument, or a query without validating it.

**Where app links go.** Anywhere a host shows a link it may carry an app link. A notification's `url`
is the common case:

```ts
ctx.gateway.notifications.createNotification({
  event: 'Reply needed: contract renewal',
  source: 'email',
  url: 'app://google/mail#/thread/18f3a2c',
})
```

A realm should link to its OWN apps. Its producers and its apps ship together, so the link cannot
point at an app that is not there.

**The host's own places.** The scope `host` is reserved: no realm or vibe-coded app may occupy it, and
`app://host/<place>#<route>` names a place in the host's own interface rather than an app. What
follows `host/` is the host's to define, and a place one host has another may not:

```
app://host/settings#keys        # a console's Keys and connections, say
app://host/inbox
```

They exist mostly for notifications the host raises about itself, such as a key that stopped
working. A realm should rarely use them — its links belong in its own apps — and must not rely on one
existing. A host that does not recognise a place falls back as below.

**When the app is not there.** A user can uninstall a realm, or shadow its app. A host that cannot
resolve an app link opens the nearest list of the thing instead, such as the notification inbox. It
never shows an error for an unresolvable app link. External `http(s)` links are unchanged.

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

## LLM roles

A realm never names a model. The installing world may not run the model its author used, so a
realm names a **role**, and each world maps each role to a model it actually has. These role ids
are part of this contract: a realm that uses one can rely on every conforming host knowing it.

| Role | Intended use |
|---|---|
| `chat_best` | High-quality conversational responses — the model a person talks to |
| `chat_cheap` | Fast, low-cost conversational work where quality matters less |
| `code_best` | The strongest code generation: building apps, complex transforms |
| `code_cheap` | Cheaper code generation for simple or bulk edits |
| `routing` | A small fast model for classification, routing and extraction |
| `narration` | Rewriting a reply to be spoken aloud |
| `vc_execution` | Summarising, scoring and labelling query results inside Virtual Cypher: many small calls |
| `vc_relevance` | Judging whether each result is really *about* a criterion, where a cheap model over-matches |
| `agentic_rag` | Driving a bounded retrieval loop: searching, reformulating, judging fit |

A prompted action names its role where it would otherwise name a model:

```yaml
llm:
  role: code_best
```

A host resolves an unknown role to its own default model rather than refusing, so a realm written
against a newer role still runs on an older host, at whatever quality that default gives. An agent
may say which roles its work leans on, so a world can see before adopting it that, for example, its
duties need `vc_relevance` mapped to something better than the cheapest model. _Forward-looking._

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

## `notebook/`

What a persona keeps about one conversation, across its turns. Each file under `notebook/` is one
reusable **set** of typed **slots**; a persona includes sets by name.

A pastor writes an index card after a visit — their name, who they are worried about, what you left
them with, which chapter you read. That card is not one kind of fact. Some of it is a reading, some
is a note, some is a list of things to come back to, and some of it points at particular people and
passages. Declaring only the readings would have been a metrics facility, and a persona would then
keep its numbers in the host and its notes nowhere.

```yaml
# notebook/pastoral.yml
name: pastoral
description: What a pastor reads in a conversation, and how he is bearing it himself.
slots:
  - name: rapport
    scope: conversation
    description: "How much trust there is. 1 wary, 10 they tell you what they tell nobody."
    type: ordinal
    range: [1, 10]
    default: 4
  - name: stage
    scope: subject
    description: "What has actually been SAID about faith, not what he hopes."
    type: stage
    stages: [unspoken, curious, asking, wrestling, seeking, declined]
    default: unspoken
  - { name: contentment, scope: agent, type: ordinal, range: [1, 10], default: 6 }
  - { name: questionsOpen, scope: conversation, type: count, default: 0 }
  - { name: askedToStop, scope: subject, type: boolean, default: false }
  - { name: card, scope: subject, type: text, limit: 400, default: "" }
  - { name: toRead, scope: conversation, type: list, limit: 5, default: [] }
  - { name: about, scope: conversation, type: entities, limit: 8, default: [] }
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | The set's id, referenced from a persona. Unique across the world. |
| `description` | no | One line on what the set is for. |
| `slots[].name` | yes | The slot's id, unique within the set. |
| `slots[].scope` | yes | `subject` (the person spoken to), `agent` (itself), `conversation` (the exchange). |
| `slots[].type` | yes | One of the types below. |
| `slots[].description` | no | What it holds, in the words the extraction step reads. |
| `slots[].default` | yes | The value before anything has been observed. |
| `slots[].range` | for `ordinal`/`ratio` | `[min, max]` inclusive. A host clamps to it rather than failing a turn. |
| `slots[].stages` | for `stage` | The ordered states. Movement need not be forward. |
| `slots[].limit` | no | Longest `text`; most items in a `list` or `entities`. A host caps whether or not one is given. |

### The slot types

| Type | Holds | For |
|---|---|---|
| `ordinal` | a whole number on a declared scale | a reading: rapport, mood, confidence |
| `stage` | one of a declared, ordered set of states | where a decision has got to |
| `count` | a non-negative whole number | questions still owed |
| `ratio` | a real number on a declared scale | a proportion |
| `boolean` | true or false | a fact that has or has not happened |
| `text` | a short note in prose | what they said, what you left them with |
| `list` | bounded short strings | links, references, things to come back to |
| `entities` | `{label, id, name?}` references | WHICH people, passages or accounts this was about |

**`type` is load-bearing.** A funnel is not a one-to-ten score, an objection count is neither, and a
note is none of them: a facility that expressed everything as one scale would misreport most of the
card. A host validates a value against its slot's own declaration.

**`entities` is not a list of strings.** An entity reference points back into the graph, so an id
with its label can be resolved again and a conversation can carry what it was *about* rather than a
prose approximation. A reference missing either half is dropped rather than repaired: an id with no
label cannot be looked up, a label with no id names a type rather than a thing, and inventing the
missing half puts a reference in the notebook that resolves to nothing — or to something else.

**Two slot names are reserved behaviour.** `askedToStop` and `inDistress` are brakes: once `true`
they stay true for the conversation, and while either is set a host withholds the persona's
`objective`. An advocate asked to stop is not told to stop advocating — it is simply no longer told
what it was trying to achieve, because stating an objective and a prohibition together is
contradictory input, and a model resolves that by acknowledging the request and then proceeding
anyway.

### Who updates them

The host, once per turn, **before** the reply is written: a second model call reads what the person
has just said and returns the new contents, validated against the declarations above. That call is
named by [LLM role](#llm-roles), and the role must be one of the ids in that table — `routing` is the
one meant for it. An unknown role resolves to the host's default rather than refusing, so an invented
id does not fail; it silently runs whatever the default is and the author never learns which.

```yaml
# in a persona's brief.yml
notebook:
  sets: [pastoral]
  extraction:
    role: routing
    every: turn        # `turn`, or `close` to extract once when the conversation ends
```

Extraction runs before generation and not after, which is not an ordering preference. Extracting
afterwards leaves every slot one turn stale, and for a brake that is a defect rather than a lag: a
persona asked to stop said "no pressure" and volunteered a reading in the same breath, because the
prompt that wrote it still believed nobody had objected.

A realm **declares** notebook sets; the world **grants** them, and may grant some and refuse others.
A persona whose sets are all refused still runs — it simply keeps no notebook. The persona is the
only place sets are declared: a notebook belongs to the voice that keeps it, and an agent already
names its persona.

### What they are, and what they are not

A notebook holds **data about a person**, so it lives under the world's normal handling for that: its
scope, its retention, its export. It is not session scratch that escapes those rules because some of
it happens to be integers.

The **declaration** is inspectable by the operator. Whoever runs a persona should be able to read
what it is keeping, because they answer for it — and because a set is reusable, that should not
require reading a realm's source.

What this spec does not do is enumerate acceptable slots. A coach keeping `adherence`, a support
agent keeping `frustration`, a pastor keeping how open somebody is: one mechanism, and whether a
particular slot suits a particular deployment is the operator's judgement at grant time rather than
a list in this document.

## `personalities/`

Each subdirectory under `personalities/` is one persona the host can run the assistant as — its voice, behaviours, guardrails, and display name. The host renders the chat system prompt by including Jinja templates from the active persona's directory; switching personality is a directory swap, not a prompt rewrite.

```
personalities/
└── roger/
    ├── identity.yml
    ├── brief.yml
    ├── personality.jinja
    ├── behaviours.jinja
    ├── guardrails.jinja
    ├── response_format.jinja
    └── verbosity.jinja
```

- **`identity.yml`** — the persona's display metadata. `name:` is the display name under this persona (shown on chat bubbles, used by the LLM when introducing itself). `description:` is an optional one-liner for a picker, a column heading or a listing — a realm offering several personas as choices needs a label per persona, and this is where a label belongs. `source:` is optional and is set automatically to `realm` for realm-shipped personalities; only set it explicitly when overriding the default.

```yaml
# personalities/roger/identity.yml
name: Roger
description: "One line for a picker, where a realm offers several personas"  # optional
source: realm
```

- **`*.jinja`** files — included into the chat system prompt at the matching slots. `personality.jinja` carries the voice / character, `behaviours.jinja` carries do/don't rules, `guardrails.jinja` carries safety constraints, `response_format.jinja` carries output-shape rules, `verbosity.jinja` carries length / pacing rules. All five are optional — omit any file you don't need and the host skips its include line.

- **`brief.yml`** — optional. The persona in the form a **single non-chat call** needs. The `.jinja`
  files are slots a host assembles into a chat system prompt at session scope; a brief is the same
  persona compacted into one request, for a realm verb that calls a model directly rather than
  through chat. A persona with no `brief.yml` is chat-only and is simply not offered to a verb.

```yaml
# personalities/roger/brief.yml
objective: |
  What Roger is trying to achieve in a conversation. A persona with one advocates.
sampling:
  temperature: 0.4        # what this persona RUNS at
notebook:
  sets: [pastoral]
  extraction:
    role: routing
```

| Field | Required | Meaning |
|---|---|---|
| `objective` | no | What this persona is **trying to achieve** in a conversation. A persona with an objective advocates; one without it answers. |
| `openingMove` | no | How it opens when it speaks first. |
| `notebook` | no | The [notebook sets](#notebook) it keeps, and how they are extracted. |
| `sampling` | no | What this persona RUNS at — `temperature`, `topP`, `maxTokens`. Distinct from an agent's `conversation.sampling`, which bounds what a *caller* may ask for. |
| `brief` | no | The persona's voice compacted into a few hundred words, for a realm that calls a model **directly** rather than through chat. Omit it on the chat path: `personality.jinja` is already carrying the voice there, and a second copy of it is a second thing to keep true. It never renders in chat — a rule meant for conversations goes in `behaviours.jinja` or `guardrails.jinja`; written only here, it reaches no conversation. |

`objective`, `openingMove` and `notebook` do reach chat: a host renders them as the persona's agenda
on every turn. For an agent you talk to they are part of what its sponsor signs, like the `.jinja`
sections — an edited objective waits for a signature before it reaches a conversation.

An agent's `job` and a persona's `objective` are not the same sentence. `job` is what the agent is
**for**, in the words of whoever answers for it; `objective` is what it is **trying to achieve** in a
conversation. A brake suppresses the objective and never the job — an agent asked to stop advocating
still does its job.

What is NOT here, deliberately: subjects the persona avoids, and subjects it does not claim
competence in. `guardrails.jinja` says both already, in prose, more precisely than a list can — "name
the kind of professional they need and go back to what you can offer" is not expressible as
`unversed: [medicine]`. Two statements of one rule is one too many.

An `objective` is the field that turns a voice into an agent with an interest of its own, and it is
declared rather than implied for exactly that reason: a persona that is advocating should say so in a
file an operator can read, not only in the way it happens to argue.

#### `sampling` — what the persona runs at

Temperature is part of a character, not a deployment knob. A persona meant to surprise people needs
a high one; a persona whose job is to be exact needs a low one, and the same number cannot serve
both. The prior art is explicit about it: the 2024 chatbot this field generalises declared
`defaultTemperature: 1.38` with a floor of 1.3 and a ceiling of 1.4, because being a little
unpredictable was the point of her.

```yaml
# personalities/astrid/brief.yml
sampling:
  temperature: 1.38      # what she runs at
  maxTokens: 400
```

This is **not** an agent's `conversation.sampling`, and the two do different jobs:

| | Declares | Governs |
|---|---|---|
| `brief.yml` → `sampling` | what the persona runs at | the call the host makes when nobody asked for anything |
| `agents/<name>.yml` → `conversation.sampling` | a range | what a **caller** may ask for, clamped |

Precedence, highest first: a caller's request, clamped to the agent's range; then the persona's
declared value, clamped to the same range; then the role's own settings. A persona therefore cannot
escape an operator's bounds by declaring a number — it states a preference inside them, which is the
same request-and-grant that governs everything else a realm asks for.

A host that does not read `sampling` ignores it and runs the role's settings, so declaring one never
breaks a realm; it simply does not take effect. Worth knowing before relying on a temperature to
carry a character: a surface whose model call takes no sampling arguments at all — as a host's
general-purpose completion tool may not — cannot honour it, and the persona will run at whatever the
role gives.

A brief **resolves by the same rules as the rest of the bundle**: the slug is unique across the
world and a world-authored persona of that name shadows the realm's. So a brief is not a private
copy a realm owns — it is one more field of a persona the host resolves, and a realm must not
assume the persona a reader sees is the one in its own directory.

Resolution is therefore the HOST's. A realm that reads its own `personalities/` directory to find
a brief — which is all a realm can do until a host exposes personas to a verb — bypasses
shadowing, and should say so rather than present the result as the resolved persona.

**The two forms describe one person and must agree on substance**, differing only in form. Nothing
in the format enforces that, so a realm whose build can check it should: a persona whose voice and
whose brief disagree is a defect no reader can see. The least a build can do is fail when a brief
ships without an `identity.yml` beside it, or when a `focuses/` file names a `defaultPersona` that
ships no brief.

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
| `builtins` | No (default `true`) | Which host-provided chat tools the focus keeps: `true` all, `false` none, or a list of categories as for an agent's [`conversation.builtins`](#talking-to-an-agent) (`[memory, views]`). Name the fewest the focus needs — the reason a focus exists is that fewer tools route better, and that holds for the host's tools as much as for realm skills. |
| `skills` | No | Skills brought in by name, beside what `realms` and `builtins` bring — exactly as an agent's [`conversation.skills`](#talking-to-an-agent): never a realm's skill without its realm (refused), never a tool, and an unknown name is a validation error. Each one is another choice the model weighs on every turn, so add it with cause ([Scope it to the job](#scope-it-to-the-job)). |

### `/focus` slash command

The host's `/focus <name>` slash command binds the user's chat session to a focus. `/focus off` clears the binding; bare `/focus` lists available focuses. Binding takes effect from the next chat turn; the conversation transcript stays under whatever scope was in force when each message was sent.

When a focus declares `defaultPersona`, the host swaps **both** the persona's Jinja includes (the voice the LLM speaks in) **and** the persona's `identity.yml#name` (the display name the LLM introduces itself as, and the label on the chat bubble) for the focused session. Toggle focus off and the world's default persona returns. The change is in-session — the world-level `activePersonality` is not rewritten.

### Discovery and precedence

World-authored focuses live at `config/focuses/<name>.yml`; realm-shipped focuses live at `<realm-dir>/focuses/<name>.yml`. On slug collision, the world entry wins (user-authored overrides realm-shipped). Realm focuses carry an internal `source = realm` marker for UI disambiguation.

---

## `tests/`

The realm's regression guard — and the artifact that keeps the answer surface honest after the
author has moved on. Both files are plain enough for a USER to edit.

**Whether a realm needs `questions.yml` is a judgment call with one hard trigger.** A realm whose
surface is verbs, handlers or enrichment — called by code, never typed at — does not need a
natural-language battery, and inventing one is ceremony. But the moment ANY surface takes words
from a person, the battery is **required**, not optional:

- the realm ships an `apps/` page with a free-text ask box;
- it ships a `skills/`, `focuses/` or chat surface where people ask in their own words;
- its views are meant to be reachable by asking rather than by name;
- or the user says they want to ask this realm questions.

If you cannot tell which case you are in, **ask the user** — "will people type questions at this,
or only call it?" — rather than guessing. Guessing low ships an answer surface nobody has ever
tested in the form users will meet it; guessing high costs a file nobody reads.

### `tests/questions.yml` — the natural-language battery

The questions a person will actually type at this realm, with what a correct answer must
satisfy. These exist because the first thing a user does with a realm is ask it something in
their own words — and a realm whose hand-written queries work while its natural-language
questions return zero is not done. Generate the initial set mechanically from the realm's own
shape (per type: the count and list forms; per numeric field: the superlative in both
phrasings; per status/stage value: the filtered ask; per date field: absolute AND relative
windows; plus synonym-heavy free forms), then let users add every question that ever
disappointed them — each becomes a permanent regression test.

```yaml
# tests/questions.yml — run each through the ask surface; assert the expectation.
- question: "Which customers owe us most money"
  expect:
    # The NL answer's figure must EQUAL the named view's — reconciliation without
    # hardcoded literals, so the test survives data changes. This is the assertion
    # for MONEY: an answer that drifts from the curated view is wrong, whatever it is.
    matchesView: { name: OdooReceivablesByCustomer, column: totalOwed }
- question: "How many customers do we have"
  expect:
    matchesView: { name: OdooCustomerCount, column: customers }
- question: "what was our biggest win last quarter"
  expect:
    nonEmpty: true          # weaker assertion where a windowed figure has no stable reference
- question: "show me open opportunities"
  expect:
    nonEmpty: true
```

Expectation kinds: `nonEmpty: true` (rows must come back — the floor); `minRows: n`;
`matchesView: { name, column, args? }` — the top row's figure from the ask must equal the top
row's figure from invoking the named view (the realm reconciling against itself). Money and
count questions should always use `matchesView`; generation is stochastic, and "nonzero" once
passed a 3x-inflated sum. A count question can also reconcile against a list view's ROW COUNT —
the count form checked against the list form.

**Carry an ADVERSARIAL half, and repeat it.** The battery above asks what the realm CAN answer.
The other half asks what it cannot — a measure the sources do not carry, at the wrong
granularity, or about a population the data never describes — because that is where a generator
stops answering and starts inventing. A correct response there is a typed refusal, an honestly
named answer, or a flagged one; a query referencing a property no label declares, or an answer
column claiming a word the query never selects, is a fabrication and fails the run.

Ask each adversarial question SEVERAL times. Generation is stochastic: a fabrication that
appears one run in five is still a fabrication, and a single green run proves almost nothing.
Check every response mechanically against the live schema (`GET /api/v1/admin/kg/schema`) rather
than by reading it — the failure mode is a query that looks entirely reasonable.

### `tests/verify.sh` — the executable harness

Ground truth to answer surface in one command: reconcile figures against the SOURCE system
directly where reachable, invoke every view with every parameter, replay the battery above,
run the adversarial questions N times each, exit nonzero on any drift. Run it after every change
to producers, views or types; run money questions more than once. A harness that lives in the
author's head re-verifies nothing.

Scope the view sweep to THIS realm's own views — a world carries other realms' and the host's
too, and a harness that fails on a neighbour's defect is a harness people learn to ignore.

## `seed/`

Demo data for the SOURCE system, declared where anyone can read it before it runs. A realm
demonstrated against an empty or fictional dataset proves plumbing and nothing else — the
joins that make a realm worth having need entities that actually resolve on the other side.
Two files, both optional:

### `seed/records.yml` — what would be created

The records, declaratively, so the person approving the seed reads exactly what will exist
afterwards. The house pattern for demo data is **fictional relationship, real entity**: the
customer "Qantas" does not owe you $40,000, but qantas.com is a real domain, so every
enrichment join lights up — while a name-matched fake would attach someone else's company to
your record, which is worse than an empty table. Keep the shipped fictional records in place
untouched; they are the honest contrast (a placeholder domain resolves to nothing, and the
demo should say so).

```yaml
# seed/records.yml — applied by seed.sh, through the source's own API.
customers:
  - name: Qantas
    website: https://www.qantas.com
    invoices:
      - { ref: SEED-QF-1, amount: 40000, description: "Advisory services" }
```

### `seed/seed.sh` — how it gets there

Applies `records.yml` **through the same door the producers use** — the source's public API,
authenticated as a normal user. Never its database: a seed that writes to tables bypasses
every rule the application enforces and produces records the application itself could not
have made.

Three properties are not optional:

- **It refuses to run blind.** The target URL must be stated and a confirmation flag passed
  (`--yes`, or an env var the script names). A seed script that runs on a bare invocation
  will eventually run against a production system.
- **It is idempotent.** Look each record up by a natural key before creating it; a second run
  changes nothing and says so.
- **Its records are recognizable.** Mark what you create (a `SEED-` reference prefix, a tag —
  whatever the source offers), so seeded records can be listed and, where the source permits,
  removed (`seed.sh --remove`).

The engine never runs seeds. Like `verify.sh`, this is an authoring and demo artifact — a
person runs it, on a system they have decided is disposable.

## `hints/`

Tips the realm ships for the humans using the world it is installed in — shown by the host's
UIs (the chat surfaces, the worlds console) as tip-of-the-day cards. Content follows
capability: a realm that adds an answer surface ships the tips that teach it, and they arrive
and leave with the realm. Hand-authored, deliberately: a derived tip (restating a view
description at the user) is the machine talking to itself.

```yaml
# hints/tips.yml — a list; every field but title/body optional
- category: hint            # hint | did-you-know | fun-fact
  surface: all              # me | console | all (default all) — which UI shows it
  title: Ask about risk
  body: "Ask **which deals are at risk** — every open deal judged from its own chatter."
  action:
    label: Ask it
    chatInput: "which deals are at risk"
```

`body` is markdown. `action.chatInput` lands in the asking surface's input box when clicked —
pre-typed, not pre-sent, so the question stays the user's to edit. `surface` keeps a chat tip
("try /research") out of the console and a console tip ("open Handler Studio") out of chat.

Resolution order is the same as `views/`: world config tiers (`config/hints/`) first, then
each installed realm's `hints/`, one parse failure costing that file — recorded against
`realms/<name>` where its author will look — never the rest.

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

- **Code that runs with host privileges.** No JVM bytecode, no native libraries, no classpath contributions. Realm code executes only inside a host-managed sandbox — the code sandbox for `dist/` JS handlers, the capability-scoped wasm runtime for `dist/handlers.wasm` (see [Execution hosts](#execution-hosts)) — never as the host itself.
- **Spring beans, host configuration changes.**
- **User credentials.** Realms carry credential references, never values. Marketplace realms use
  host-vetted typed slots and auth profiles. Environment-variable references are local or explicitly
  first-party/org-reviewed compatibility syntax only.
- **World, context, or principal-owned state.** A realm ships templates and types; host-owned scopes
  hold mutable instances and their access policy.

If a capability needs real code, ship it as sandboxed handler code (`src/` or `wasm/`, run on an [execution host](#execution-hosts)), via `actions/` (LLM in the loop), via `mcp/` (sandboxed server, arbitrary code), or as a host-level extension out of band.

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

The specification **text** is licensed under
[Creative Commons Attribution-NoDerivatives 4.0 International](LICENSE) (CC BY-ND 4.0). The code,
YAML and Cypher **samples** remain under the [Apache License 2.0](LICENSE-SAMPLES-APACHE-2.0), so
you can copy and adapt them freely.

**Authoring realms, and building software that uses them, is free** — publicly, privately or
commercially, without permission, notification or royalty. Realms you author are yours and are not
derivative works of this document.

**Implementing these specifications in a competing engine or platform is a different matter** — that
is not licensed here and requires a separate written agreement with Embabel. All rights other than
those in the specification text are reserved, no patent licence is granted or implied, and
compatibility or conformance claims using the "Embabel" or "Virtual Cypher" marks require our
written permission.

See [NOTICE.md](NOTICE.md) for the full statement of rights.

The Me host also accepts [authenticated external source events](HOSTED_EXECUTION.md#authenticated-source-ingress)
under the same captured source approval and durable receipt contract.

The Me captured host excludes legacy Realm StepSpecs and MCP subprocess registrations.
Use captured handlers and their versioned surface bindings; see
[the migration contract](HOSTED_EXECUTION.md#legacy-executable-migration).

Me host SQL readers and learning use [approved owner targets](HOSTED_EXECUTION.md#approved-sql-callers).
Legacy datasource YAML does not authorize a connection. The current profile is read-only;
SQL remains behind Virtual Cypher and typed host operations, outside the guest protocol.

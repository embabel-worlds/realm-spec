# Embabel Pack Specification

Packs are self-contained, declarative bundles of agent capabilities that can be installed into an Embabel-based host. Each pack is a git repository (no JVM bytecode, no native binaries) that provides actions, types, APIs, MCP servers, commands, webhooks, skills, prompts, and event sources. The host platform reads the pack and wires its contents into the running agent.

This document is the spec.

> **Status: living draft.** Sections marked _forward-looking_ describe shape that is settled but may still be in implementation across hosts. Everything else describes the format current Embabel hosts already consume.

---

## Repository convention

A pack is a git repo whose name begins with `pack-` (e.g. `pack-github`, `pack-stripe`, `pack-research`). The host installs a pack by cloning it into a workspace's `packs/` directory.

Pack sources are configured at the host level. A typical host configuration:

```yaml
# host application.yml
embabel:
  directory:
    pack-sources:
      - name: embabel
        type: org
      - name: johnsonr
        type: user
```

Each entry exposes the packs whose name matches `pack-*` from the given GitHub org or user.

## Directory Structure

```
pack-name/
├── pack.yml              # Required: pack metadata
├── actions/              # Action specifications (YAML) — framework + host-extension stepTypes
│   └── my-action.yml
├── goals/                # Goal specifications (YAML)
│   └── my-goal.yml
├── types/                # Dynamic type definitions (YAML)
│   └── my-type.yml
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

All directories are optional. A pack needs only `pack.yml` and at least one capability directory.

## Pack shapes

A pack is a directory of capabilities. *How* those capabilities are
expressed is up to the author — packs span a spectrum from
pure-declarative to handlers-driven:

### Declarative-only (e.g. `pack-github`, `pack-email`)

YAML files describe everything; no code ships. The host parses the
declarations and wires them into the runtime.

- `pack-github`: `types/github.yml`, `events/*.yml`, `actions/*.yml`,
  `apis/apis.yml`, `skills/*/SKILL.md`. The framework's planner
  consumes the action specs; the poll executor consumes the event
  specs; the API allowlist consumes the apis manifest. No
  TypeScript, no `src/`.
- `pack-email`: a pure abstract-concept pack — `types/email.yml`
  declares the universal `email.thread` DomainType, and
  `actions/*.yml` ships the attention-worthiness policies that
  operate on it. Signal *producers* (in-tree Gmail today, future
  pack-exchange / pack-imap) live elsewhere; this pack carries only
  the abstraction and the rules.

### Handlers-driven (e.g. `pack-google`)

When the integration genuinely needs imperative code — guarded
mutations with revision checks, multi-step orchestration of vendor
APIs, custom domain logic — the pack ships TypeScript handlers
alongside the standard YAML.

- `pack-google`: `src/api/docs-editor.ts` implements an editing
  surface for Google Docs (outline / read / find / proposeEdits /
  applyEdits) with revisionId guards the framework can't express
  declaratively. `src/lib/*.ts` carries the supporting logic
  (outline construction, op validation, op translation).
  `src/types/edit-op.ts` declares the TypeScript types the handlers
  trade in. `tests/*.test.ts` are Vitest specs covering each
  handler's contract. `package.json` / `tsconfig.json` /
  `vitest.config.ts` complete the project. The pack also carries
  `apis/` (vendored OpenAPI specs), `skills/` (workflow docs for
  small models), and `prompts/` like any other pack — they aren't
  mutually exclusive.

The host loads the handlers through the framework's TypeScript
runtime; the standard YAML capabilities load the same way they do
for declarative packs. Authors choose freely per file.

### Choosing a shape

- Start declarative. If a YAML `stepType: action` or `stepType: policy`
  can express what you need, that's the right tool — no build step,
  no runtime code path, the host's planner reasons about it directly.
- Reach for handlers when the operation has invariants the planner
  can't enforce on its own (atomicity, revision guards, ordering
  across multiple vendor calls) or when the vendor's API grammar is
  rich enough that surfacing it as one tool collapses too much.
- A pack can mix freely. `actions/` and `src/` coexist; nothing in
  the spec says "if you ship handlers, ship only handlers."

## `pack.yml`

Required metadata file at the pack root.

```yaml
name: github
description: "GitHub integration — analyze and fix issues"
version: 0.1.0
author: Embabel
url: https://github.com/embabel/pack-github
tags:
  - integrations
  - developer-tools
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Pack name (kebab-case) |
| `description` | No | What the pack does |
| `version` | No | Semver version (default: `0.0.0`) |
| `author` | No | Author or organization name |
| `url` | No | Source repository or documentation URL |
| `tags` | No | Categorization tags |

## `actions/`

Action specifications — YAML files that define executable operations. The host's planner picks them by their declared input / output types and runs them as GOAP actions. The `stepType` discriminator selects the shape; the framework's `NameOrClassTypeIdResolver` resolves names to classes, so any `ActionSpec` implementation on the classpath (including host extensions) drops in next to the framework's own `stepType: action`.

| `stepType` | Purpose | Output |
|------------|---------|--------|
| `action` | Framework `PromptedActionSpec` — typed LLM call | declared `outputTypeName` |
| `policy` | Host extension — deterministic predicate over a signal, no LLM | `AttentionCandidate` |

Hosts register their own `ActionSpec` subtypes (e.g. `policy`) at startup via `ObjectMapper.registerSubtypes(...)` against the spec mapper. Once registered, files of all stepTypes coexist in the same `actions/` directory; the framework's loader dispatches on the discriminator.

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
# pack-email/actions/triage_email_attention.yml
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

The wrap is a two-step GOAP chain per signal: the PromptedActionSpec emits an `AttentionVerdict`, then the host's wrap action emits the final `AttentionCandidate`. The wrap is keyed off `(AttentionVerdict, Signal)` inputs so it composes generically with *any* LLM-judgment pack — pack-email, pack-slack, pack-calendar, etc. — without needing per-signal-type wrap classes.

### `stepType: policy` — host-extension deterministic rule

Cheap, no-LLM rule over a single signal — fires when its predicate matches and writes an `AttentionCandidate`. Predicate is the host's DSL (comparison + boolean ops + the `$self` symbol + derived `age`); field paths walk the signal's declared properties. **No `surface:` block** — how the candidate gets rendered into a notification is a downstream concern, not the producer's call.

```yaml
# actions/policy_pr_review_overdue.yml
stepType: policy
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

### How policies and LLM-judgment actions compose

For each fresh signal of type `T`, the host runs one `AgentProcess` whose goal is "an `AttentionCandidate` exists on the blackboard". Every loaded action whose preconditions match `T` is a candidate; UtilityAI picks in value-minus-cost order. A cheap `stepType: policy` ((cost 0.01, value 1.0) → utility 0.99) wins over an LLM `stepType: action` producing AttentionVerdict ((cost 0.5, value 1.0) → utility 0.5) — so the cheap policy runs first, writes the AttentionCandidate, the goal is satisfied, and the LLM call never happens.

When the cheap policy doesn't match, its `hasRun_<name>=TRUE` blocks re-picking; the LLM action still has positive utility; the planner picks it; it produces an AttentionVerdict (or null = skip); if non-null, the host's wrap action fires; goal satisfied. If the LLM returns null and no other action can produce an AttentionCandidate, the planner terminates naturally with no candidate.

Actions are deployed to the host's planner on workspace load.

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

Dynamic type definitions — custom input/output types for actions, signal types, and the data dictionary in general. A type with `parents:` declared inherits properties from its parent types (which may be JVM-known host types or other pack-declared types).

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

Every entry created via `create_entry` for a type defined here lands as a node in the workspace graph (the same graph the host's Cypher / schema-projector / proposition-recall tools talk to). Two consequences worth knowing when writing a pack:

- **The entry's `name` is the host's headline for it.** The host picks a single field per type to use as the node `name` for rendering — first `title`, then `name`, then `summary` if any exists. Add at least one of those if you want list / Cypher output to be human-readable.
- **The host adds an implicit edge to the workspace user on every create.** Default is `(entry)-[:OWNED_BY]->(user)` — fine for most types. When the predicate reads more naturally in the other direction, declare a `userAnchor:` on the type:

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

`create_entry` accepts an optional `relations:` array so a pack's skill can wire the new entry to another entry that already exists in the workspace. The host emits each requested edge on save; if any target can't be found in the same workspace, the whole create is refused (no orphan node, no orphan edge). Example shape, taken from the movie pack's `rate-movie` skill:

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

Each relation is `{predicate, to: {type, ...keyProps}}` — `to.type` names the target's type, the remaining `to.*` fields are the key properties the host MATCHes against on the target's workspace-scoped nodes. Use this pattern any time a pack's typed records form a small connected graph (rating → movie, comment → ticket, note → contact, etc.) — the same graph is then walkable by Cypher and feeds the recall path automatically.

## `apis/`

API entries — each `.yml` file in `apis/` is a list of API definitions loaded on workspace init. Each entry compiles into a typed `gateway.<name>.*` namespace inside `execute_javascript` / `execute_python`.

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
| `name` | recommended | Gateway namespace — `gateway.<name>.*`. Falls back to a slugified spec title if omitted. **Always set this** in published packs so the prompt examples work regardless of the spec's `info.title`. |
| `type` | no | `openapi` (default) or `graphql`. |
| `auth` | no | `none` (default), `bearer`, `api-key`, `oauth2`. See **Auth** below. |
| `token-env` | with bearer / api-key | Env-var or credential-store key holding the token. |
| `headers` | no | Custom HTTP headers; values support `${VAR}` interpolation from credential store / env. |
| `oauth2` | with `auth: oauth2` | OAuth2 config — see **OAuth2** below. |
| `tags` | no | Allowlist of OpenAPI tag names. Filters huge specs to a coarse subset. |
| `operation-ids` | no | Exact `operationId` allowlist. Composes with `tags` (tags pre-filter, operation-ids picks exact ops). Match is case-insensitive and treats `-`/`/` as `_`, so `repos/get`, `repos-get`, `repos_get` all match. |

### Vendored specs

`url` accepts a bare relative path. The loader resolves it against the file's own parent directory, so packs can ship a hand-curated spec next to their `apis.yml`:

```
pack-hubspot/
└── apis/
    ├── apis.yml          # url: hubspot-crm.json
    └── hubspot-crm.json  # the spec, vendored in-pack
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

Token-env and `${VAR}` values are resolved in this order: workspace credential store first (set via `set NAME = ...` in chat or via the admin UI), then process env var. Missing creds → the entry is skipped at workspace load with a logged warning; the API never appears in the gateway.

### OAuth2

For providers that use the OAuth2 authorization-code flow (HubSpot, Slack, Salesforce, GitHub, Google, etc.). The pack ships only the **provider facts** (URLs, scopes, identity introspection). Per-installation client app credentials live in the host admin file `oauth-apps.yml` — **never in the pack repo and never in any user's workspace**.

```yaml
# pack-hubspot/apis/apis.yml
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
| `client-id` / `client-secret` | NO in published packs | Power-user fallback only — accepts `${VAR}` interpolation. **Production setups put these in the host admin's `oauth-apps.yml`** so the pack stays public and credential-free. |
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

A workspace can override the installation default by writing the same shape to `<workspace>/config/oauth-apps.yml` — useful when one team needs its own provider app under its own brand.

**Lookup order** for client_id / client_secret:
1. `<workspace>/config/oauth-apps.yml` (per-workspace override)
2. Host admin `oauth-apps.yml` (installation default)
3. `${VAR}` from the pack's `oauth2.client-id` / `client-secret` (escape hatch for power users)

If none resolve, the provider's status reports `not-configured` and Authorize returns an actionable error message instead of silently failing.

**End-user UX**

End users **never** paste tokens, IDs, or secrets. Settings → Connected Services → click **Authorize** → consent on the provider's page → done. ConnectedAccounts holds the real account label; `gateway.<name>.*` is live in chat.

**Token refresh** is automatic — the host's `OAuth2Service` rotates expired access tokens using the stored refresh token and writes back any new refresh token the provider issues (HubSpot rotates them on every refresh).

## `src/` and `tests/` — hand-authored TypeScript handlers

OpenAPI and MCP cover what an external system *already* exposes. Packs can also ship **hand-authored TypeScript** that registers as gateway methods alongside OpenAPI-derived ones. Each TS file under `src/api/` becomes a namespace on `gateway.*`; each exported `async function` in that file becomes a method.

The compiled handler runs in the same sandbox as LLM-generated code (no in-server JS engine). Each handler receives the live gateway as its first argument, so it can call back through `gateway.<raw-api>.*` for primitives — no HTTP-from-inside-HTTP overhead, no second auth dance.

### When to add TS handlers

Reach for `src/` when you want to:

- **Shape a raw API into idiomatic methods** the LLM uses well (e.g. `docsEditor.getOutline` over `docs.documentsGet` + heading-walking).
- **Enforce safety invariants** that can't be expressed in the raw spec (e.g. a propose/apply edit flow with a revisionId guard, where you DON'T expose the raw mutating method to the LLM).
- **Compose multiple primitives** into one call (e.g. paginate, retry, dedupe, post-process).

Packs without TS handlers continue to work exactly as before — `src/` is purely additive.

### Pack project layout

A pack with TS handlers is a real TypeScript project. The framework provides scaffolding (`embabel-pack new`, in flight), but the shape is small:

```
pack-name/
├── pack.yml                    # existing
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

### Manifest format

Auto-generated by `embabel-build-manifest` (provided by `@embabel/runtime-types`), so pack authors never hand-author it. The host reads it at install time.

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

`mockGateway<WorkspaceTools>` lets you write hermetic tests in pure Node:

```ts
import { mockGateway } from "@embabel/runtime-types";
import type { WorkspaceTools } from "../.embabel/gateway";
import { getOutline } from "../src/api/docs-editor";

it("extracts headings", async () => {
  const gateway = mockGateway<WorkspaceTools>({
    docs: { documentsGet: vi.fn().mockResolvedValue({ revisionId: "r1", body: { content: [/* … */] } }) },
  });
  const outline = await getOutline(gateway, { documentId: "abc" });
  expect(outline.spans).toHaveLength(2);
});
```

No host running, no Docker, no live API.

### Install-time behaviour

When the host installs a pack:

1. **Clone** the pack repo (existing).
2. **If `package.json` has a `build` script, run `npm install && npm run build`.** Produces `dist/`. Skipped silently when `node`/`npm` isn't available; OpenAPI methods still work.
3. **Read `dist/manifest.json`** if present; register each entry as a gateway method alongside OpenAPI-derived ones.
4. **At sandbox session start**, copy each pack's `dist/` into `/workspace/pack-handlers/<pack-name>/`. The generated `gateway.js` `require()`s these modules and routes pack-method calls locally instead of via HTTP.

A handler call from inside the sandbox:

```
LLM-emitted script
   gateway.docsEditor.getOutline({ documentId })
       ↓ generated gateway.js routes to local handler
   require('/workspace/pack-handlers/google/api/docs-editor.js').getOutline(gateway, args)
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

- If a pack hides a method from its `apis.yml` allowlist *but* uses it inside a handler, the LLM cannot call the raw method directly.
- If a pack exposes both the raw method and a wrapper, the LLM can call either — the wrapper is a recommendation, not a barrier. Skills (`SKILL.md` files) are the right way to make sure the LLM picks the wrapper.

### Author tooling

The host ships a thin wrapper (`embabel-pack`) that drives the JVM-side surface generation. Most pack authors only ever need `npm run build` for everyday work; `embabel-pack sync` regenerates `.embabel/gateway.d.ts` when the host's surface changes (new packs, new APIs).

```bash
embabel-pack sync                        # from inside any pack repo
embabel-pack sync ~/dev/pack-hubspot     # or pass an explicit path
```

## `mcp/`

MCP server configurations — each file lists Model Context Protocol servers to connect.

```yaml
# mcp/arxiv.yml
- name: arxiv
  description: "Search and read arXiv research papers"
  command: docker
  args: ["run", "-i", "--rm", "mcp/arxiv-mcp-server:latest"]
```

```yaml
# mcp/web.yml
- name: brave-search
  description: "Web search via Brave"
  command: docker
  args: ["run", "-i", "--rm", "-e", "BRAVE_API_KEY=${BRAVE_API_KEY}", "mcp/brave-search:latest"]
  env:
    BRAVE_API_KEY: "${BRAVE_API_KEY}"
```

MCP servers are lazy-loaded — the Docker container starts on first tool use, not on workspace init. Multiple users with the same MCP config share a single container via the host's MCP client cache.

## `commands/`

Slash command mappings — map `/command` names to actions.

```yaml
# commands/fix-issue.yml
command: fix-issue
actionName: fix-issue
description: "Fix a GitHub issue"
```

## `webhooks/`

Webhook registrations — declare webhooks the pack wants to receive. When the pack is installed and the host has a public URL, these are registered with the external service.

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
- Workspace config (`config.yml`)
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
| `type` | yes | Name of a type declared in this pack (or another loaded pack) whose `parents` includes `Signal`. |
| `webhook.signature` | yes | Signature scheme the host's built-in verifiers handle. |
| `webhook.signature-secret` | conditional | Env-var name holding the shared secret. Required for any non-`none` scheme. |
| `webhook.tenancy` | yes | Strategy for routing the inbound webhook to a workspace. |
| `webhook.mapping` | yes | Map of type-property → JSONPath. Every required property of the `Signal` parent (`id`, `occurredAt`, `sourceKind`, `sourceId`) must be covered. |
| `webhook.tier-when` | no | Tier-override map. Each entry's value is a Jinja boolean expression evaluated against the parsed payload. First true wins; default tier is `AMBIENT`. |

### Polling event source

For services without webhook support — or where polling is preferable — declare a `poll` block instead of (or in addition to) `webhook`. Polling reuses the host's task scheduler and persists a per-`(user, type)` cursor so each run only sees what's new.

```yaml
# events/linear.yml
- type: LinearIssue
  poll:
    every: 10m
    api: linear                # the pack's already-learned API (apis/linear.yml)
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
| `poll.api` | yes | Name of an API declared in `apis/` (this or another pack). |
| `poll.method` | yes | Method name on that API. |
| `poll.args` | no | Arguments to the call. Jinja-templated against `{ user, cursor }`. |
| `poll.cursor.param` | no | API parameter the host populates with the persisted cursor. |
| `poll.cursor.from` | no | JSONPath into each returned result, used to compute the next cursor (the maximum value across the batch becomes the new cursor). |
| `poll.mapping` | yes | Same shape as the webhook `mapping` block. |

A pack may declare both `webhook:` and `poll:` for the same type — the host prefers webhook delivery and uses polling as a backstop for catch-up after downtime.

### Why this matters

Both sources produce `Signal`s of the pack-declared type. From there, the consequence engine, triage rules, persistence (`SignalRecord`), notifications, and chat surfacing are all type-aware: `signal.type.isAssignableFrom(StripeEvent)` is a real predicate, not a string match.

No JVM bytecode is shipped — packs that need behaviour beyond mapping should expose it via `actions/` (LLM-driven) or `mcp/` (sandboxed servers).

## `apps/`

HTML apps the pack ships. They're served at `/apps/{name}` alongside the user's vibe-coded apps and the workspace template's apps. Resolution order is:

1. `<workspace>/data/apps/{name}` — user-owned (vibe-coded), highest priority
2. `<workspace>/config/apps/{name}` — workspace-template apps shipped with default-workspace
3. `<workspace>/config/packs/<pack>/apps/{name}` — pack-bundled apps (this directory)

A user can shadow a pack-bundled app by vibe-coding one with the same filename. Pack apps are read-only from the user's perspective; they're refreshed whenever the pack is updated.

```
apps/
├── github-dashboard.html
└── pr-review-board.html
```

Pack apps must use the same architecture as vibe-coded apps: tool-gateway calls via `fetch('/api/v1/tools/{name}')`, no direct external fetches. They have access to all the user's tools (MCP, learned APIs, etc.) because they run in the user's authenticated session.

## `artifacts.yml`

Optional. Register custom artifact types the pack introduces, in addition to the host's built-ins (`DOCUMENT`, `APP`, `CODE`, `DATASET`, `DIAGRAM`).

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
| `directory` | Yes | Path under workspace root. **Conventionally `data/<subdir>`** so the artifacts survive factory reset. |
| `defaultExtension` | No | File extension hint for new artifacts |
| `servable` | No | If `true`, artifacts of this type are served via the same path resolution as `APP` |

## `prompts/`

Prompt contributions — optional content **appended to every chat system prompt** for every user with the pack installed. Currently supports `examples.md`.

> **⚠️ Tax on every chat turn.** Bytes you add here are paid by every user, every turn, even when they're not invoking your pack. Hosts enforce a soft size ceiling (Embabel's reference host: 1024 bytes/pack, configurable via `assistant.pack-loader.prompt-max-bytes`); over-budget packs still load but the host surfaces a warning in the workspace problems list.
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

The substantive routing content (tool names, code-mode call shapes, edge cases, idiomatic patterns) goes into `skills/<pack>-skill/SKILL.md`. The skill loader makes it activatable; the LLM pulls it in only when it decides the user's intent matches.

### Anti-pattern

```markdown
User: "Show me the open issues in embabel/agent"
→ Call github tool → list_issues (GitHub issues, not workspace tasks)

User: "Create a GitHub issue for the memory leak bug"
→ Call github tool → issue_write (NOT workspace task creation)

[… ten more examples, code-mode call sketches, edge cases …]
```

This was the original convention and is being deprecated. Bulk routing examples in `prompts/` cost every user on every turn; the same examples in a Skill cost only users actively asking about that capability. Migrate existing packs by trimming `prompts/examples.md` to a pointer and moving the body into the pack's Skill.

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

- **`identity.yml`** — the only YAML in the bundle. `name:` is the assistant's display name under this persona (shown on chat bubbles, used by the LLM when introducing itself). `source:` is optional and is set automatically to `pack` for pack-shipped personalities; only set it explicitly when overriding the default.

```yaml
# personalities/roger/identity.yml
name: Roger
source: pack
```

- **`*.jinja`** files — included into the chat system prompt at the matching slots. `personality.jinja` carries the voice / character, `behaviours.jinja` carries do/don't rules, `guardrails.jinja` carries safety constraints, `response_format.jinja` carries output-shape rules, `verbosity.jinja` carries length / pacing rules. All five are optional — omit any file you don't need and the host skips its include line.

A pack's personality is referenced by slug (its directory name) from a `focuses/` file (`defaultPersona: roger`) or directly via the host's persona picker. Slug must be unique across the workspace; on collision with a workspace-authored personality, the workspace wins.

## `focuses/`

A **focus** is a named scoping of the chat surface — a subset of packs whose skills the chat LLM can see, plus an optional persona override. The point is routing reliability: a 30-skill workspace gives even a sharp pack skill room to lose to a competitor; strip the competitors out and the LLM has nothing to confuse the right skill with.

```yaml
# focuses/movies.yml
name: movies
displayName: Movies
description: "Recommend, rate, and recall films"
icon: "🎬"
defaultPersona: roger
packs: [movie]
builtins: true
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Stable slug — used by the `/focus <name>` slash command, the picker, and persistence. |
| `displayName` | No | Human label for the picker. Falls back to `name`. |
| `description` | No | One-line summary for the picker tooltip / chat badge. |
| `icon` | No | Emoji or single character for the picker. |
| `defaultPersona` | No | Persona slug to activate when a session enters this focus. Resolved against the same registry that `personalities/` populates — workspace-authored or pack-shipped. Null = keep the workspace's current persona. |
| `packs` | No | Pack names whose skills stay visible in this focus. Empty = no pack skills, only built-ins. |
| `tools` | No | By-name allowlist of additional tools/skills to pull into this focus regardless of pack membership. Additive with `packs`. |
| `builtins` | No (default `true`) | Whether to keep host-provided chat tools (memory, repository, reply, progress, the code runners). Set false only for narrowly-scoped focuses ("read-only public-info kiosk"). |

### `/focus` slash command

The host's `/focus <name>` slash command binds the user's chat session to a focus. `/focus off` clears the binding; bare `/focus` lists available focuses. Binding takes effect from the next chat turn; the conversation transcript stays under whatever scope was in force when each message was sent.

When a focus declares `defaultPersona`, the host swaps **both** the persona's Jinja includes (the voice the LLM speaks in) **and** the persona's `identity.yml#name` (the display name the LLM introduces itself as, and the label on the chat bubble) for the focused session. Toggle focus off and the workspace's default persona returns. The change is in-session — the workspace-level `activePersonality` is not rewritten.

### Discovery and precedence

Workspace-authored focuses live at `config/focuses/<name>.yml`; pack-shipped focuses live at `<pack-dir>/focuses/<name>.yml`. On slug collision, the workspace entry wins (user-authored overrides pack-shipped). Pack focuses carry an internal `source = pack` marker for UI disambiguation.

---

## Installation

Packs are installed as git repos cloned into the workspace's `config/packs/` directory:

```
workspace/
└── config/
    └── packs/
        ├── github/        ← cloned from git
        ├── research/      ← cloned from git
        └── my-custom/     ← manually created
```

Default packs are listed in the workspace's `config/packs.yml`:

```yaml
# config/packs.yml
- name: research
  repo: https://github.com/embabel/pack-research.git
```

These are cloned automatically on first workspace provisioning.

## Pack Discovery

Packs are discoverable via the host's directory system:
- GitHub organizations / users configured in `pack-sources`
- Repos matching `pack-*` naming convention are listed
- Users can search and install packs via chat or the host UI

---

## What's intentionally not in a pack

- **JVM bytecode**, native libraries, scripts to be executed in-process.
- **Spring beans, classpath contributions, host configuration changes.**
- **User credentials.** Packs reference secrets by env-var name; the user supplies the secret out-of-band (host UI, env, etc.).
- **Per-user state.** A pack ships templates and types; the *workspace* holds the per-user instances.

If a capability needs real code, ship it via `actions/` (LLM in the loop), `mcp/` (sandboxed server, arbitrary code), or as a host-level extension out of band.

## Conventions

- **Naming**: lowercase-hyphenated for ids (pack name, action name, command name); UpperCamelCase for type names.
- **YAML**: prefer multi-doc files only when the entries are tightly related; otherwise one file per item.
- **Descriptions are LLM-readable**: write descriptions assuming an LLM planner is the primary reader.
- **Stable ids**: changing a `name` is a breaking change for any installed workspace that wired against it.

## Versioning

Packs follow semantic versioning in `pack.yml`. The `version` is informational; hosts may track it to detect upgrades but the contract is at the directory-and-field level — adding a new optional field is a minor change, removing or renaming a required field is a major one.

The spec itself is versioned by this repository's git history. Hosts target a spec revision; packs declare compatibility informally for now.

---

## License

This specification is released under the Apache License, Version 2.0. See [LICENSE](LICENSE).

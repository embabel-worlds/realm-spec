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
├── actions/              # Action specifications (YAML)
│   └── my-action.yml
├── goals/                # Goal specifications (YAML)
│   └── my-goal.yml
├── types/                # Dynamic type definitions (YAML)
│   └── my-type.yml
├── apis/                 # API entries (YAML)
│   └── my-api.yml
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
└── skills/               # Skills (Agent Skills spec)
    └── my-skill/
        └── SKILL.md
```

All directories are optional. A pack needs only `pack.yml` and at least one capability directory.

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

Action specifications — YAML files that define executable operations. Each file is a `PromptedActionSpec` (or other step type).

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
```

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

Prompt contributions — optional content that gets included in the chat system prompt to help the LLM route tool calls correctly. Currently supports `examples.md`.

### `prompts/examples.md`

Tool routing examples specific to this pack's tools. These are appended to the system prompt's `## Examples` section so the LLM learns the correct tool routing for this pack's capabilities.

```markdown
User: "Show me the open issues in embabel/agent"
→ Call github tool → list_issues (GitHub issues, not workspace tasks)

User: "Create a GitHub issue for the memory leak bug"
→ Call github tool → issue_write (NOT workspace task creation)
```

Guidelines for writing examples:
- Use natural user messages (not tool names)
- Show the correct tool and inner tool to call
- Add disambiguation notes when tools could be confused with others
- Keep to 2-5 examples per pack — quality over quantity

Examples are collected from all installed packs at runtime and included in the host's chat system prompt.

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

# Embabel Pack Specification

A **pack** is a portable, declarative bundle of agent capabilities that can be installed into an Embabel-based assistant. Packs are git repositories — no JVM bytecode, no native binaries — containing YAML, Jinja templates, and (optionally) MCP server descriptors. The host platform reads the pack and wires its contents into the running agent.

This document is the spec.

> Status: living draft. The shape of `events/` (event ingestion) is forward-looking; everything else is the format that current Embabel hosts already consume.

---

## Repository convention

A pack is a git repository whose name begins with `pack-` (e.g. `pack-github`, `pack-stripe`, `pack-research`). The host installs a pack by cloning it into a workspace's `packs/` directory.

Pack sources are configured at the host level. A typical host configuration:

```yaml
# host application.yml
embabel:
  directory:
    pack-sources:
      - name: embabel
        url: https://github.com/embabel
        prefix: pack-
```

Each entry exposes the packs whose name starts with `prefix` from the given GitHub org (or arbitrary git remote).

## Layout

A pack's root contains a `pack.yml` metadata file and one or more of the following directories. Every directory is optional — a pack may contribute only types, only an MCP server, only webhooks, etc.

```
pack-stripe/
├── pack.yml                    # required — metadata
├── types/                      # DomainType declarations
├── actions/                    # action specs (LLM-driven steps)
├── goals/                      # goal specs (action targets)
├── commands/                   # /slash chat commands
├── apis/                       # OpenAPI/GraphQL specs to learn
├── webhooks/                   # webhook receivers
├── events/                     # event ingestion (push + poll)  [forward-looking]
├── channels/                   # messaging channel templates
├── cron/                       # scheduled jobs
├── prompts/                    # Jinja templates
├── skills/                     # skill descriptors (agentskills.io)
└── mcp/                        # MCP server descriptors
```

Files are picked up by directory, not by listing in `pack.yml`. Add a YAML file to `types/`, restart-or-refresh the host, and the type is registered.

---

## `pack.yml` — metadata

Required at the pack root.

```yaml
name: stripe
description: "Stripe integration — types, webhooks, signal ingestion"
version: "0.3.0"
author: "Embabel"
url: https://github.com/embabel/pack-stripe
tags:
  - payments
  - webhooks
```

| field | required | meaning |
|---|---|---|
| `name` | yes | Stable short name. Lowercase, hyphenated, no spaces. |
| `description` | yes | One-line summary shown in pack browsers. |
| `version` | yes | Semver. The host may use this to detect upgrades. |
| `author` | no | Display name. |
| `url` | no | Canonical pack home. |
| `tags` | no | Free-form list, surfaced in pack browsers. |

---

## `types/` — DomainType declarations

A YAML file under `types/` declares one or more named types. Each type is a `DomainType` in the host's data dictionary, equally usable by actions, the consequence engine, and (forthcoming) event ingestion.

```yaml
# types/github.yml
- name: GitHubIssue
  description: "A GitHub issue identified by owner, repo, and issue number"
  properties:
    owner: "Repository owner (user or organization)"
    repo: "Repository name"
    issue: "Issue number"

- name: TriagedIssue
  description: "A GitHub issue assessed for automated fixing"
  properties:
    owner: "Repository owner"
    repo: "Repository name"
    issue: "Issue number"
    title: "Issue title"
    body: "Issue body/description"
    labels: "Comma-separated labels"
    assessment: "What needs to be done and how"
    repoPath: "Local filesystem path to the repository clone"
```

Properties are declared as `name: description` pairs. The description is what the LLM sees when reasoning about the type, so write it for an agent reader, not just a developer.

### Inheritance

A type may declare `parents:`, naming other types it extends. Parents may be JVM-known types (e.g. `Signal`, declared by the host platform) or types declared elsewhere — in this same pack, in another pack, or built into the host.

```yaml
- name: StripeEvent
  parents: [Signal]
  description: "A Stripe webhook event"
  properties:
    eventType: "Stripe event type, e.g. charge.failed"
    amount: "Charge amount in minor units"
    currency: "ISO 4217 currency code"
    customerId: "Stripe customer id"
```

A type with `parents: [Signal]` is a signal type — it inherits the signal contract (`id`, `occurredAt`, `sourceKind`, `sourceId`, `subject`, `contentVersion`) and is automatically eligible for the consequence engine, triage rules, and persistence as a `SignalRecord`.

---

## `actions/` — action specs

An action is a deterministic or LLM-driven step that consumes one or more typed inputs and produces a typed output.

```yaml
# actions/triage-github-issue.yml
stepType: action
name: triage-github-issue
description: "Triage a GitHub issue — fetch details, assess feasibility, decide whether to attempt an automated fix"
inputTypeNames:
  - GitHubIssue
outputTypeName: TriagedIssue
nullable: true            # may legitimately produce no output
canRerun: false           # if true, host may invoke repeatedly with the same input
pre:                      # SpEL guards — action only runs when all evaluate truthy
  - "spel:gitHubIssue.issue > 0"
prompt: |
  Triage GitHub issue #{{gitHubIssue.issue}} in {{gitHubIssue.owner}}/{{gitHubIssue.repo}}.

  1. Use the github tool to read the issue:
     gh api repos/{{gitHubIssue.owner}}/{{gitHubIssue.repo}}/issues/{{gitHubIssue.issue}}

  2. Decide whether the issue is suitable for automated fixing.
     If not, return null and explain why via the communicate tool.

  3. Otherwise, return a TriagedIssue with the title, body, labels, and your assessment.
tools:
  - github
  - progress
  - communicate
```

| field | required | meaning |
|---|---|---|
| `stepType` | yes | Always `action`. |
| `name` | yes | Action id. Unique within the host's action registry. |
| `description` | yes | What this action does, written for an LLM planner. |
| `inputTypeNames` | yes | One or more `DomainType` names this action consumes. |
| `outputTypeName` | yes | The `DomainType` name this action produces. |
| `nullable` | no | If true, the action may return no output (e.g. "this didn't apply"). Default `false`. |
| `canRerun` | no | If true, host may run this action multiple times with the same input. Default `false`. |
| `pre` | no | List of SpEL expressions (each prefixed `spel:`). Action only runs when all are truthy against the inputs. |
| `prompt` | conditional | Jinja template. Required for LLM-driven actions; omit for fully deterministic actions wired through other means. |
| `tools` | no | Names of tools the action may use. Includes built-in tools (`progress`, `communicate`) and any tool surfaced by the host or other packs (e.g. MCP-bundled tools). |

Inputs are referenced in the prompt by their lowercased type name (`{{gitHubIssue.issue}}` for a `GitHubIssue` input).

---

## `goals/` — goal specs

A goal is a higher-level outcome the planner can target, typically backed by one or more actions.

```yaml
# goals/research-topic.yml
stepType: goal
name: research-topic
description: "Research a topic in depth — gather information and return structured findings with source URLs"
outputTypeName: ResearchResult
export: true             # if true, surfaced as user-facing capability
```

| field | required | meaning |
|---|---|---|
| `stepType` | yes | Always `goal`. |
| `name` | yes | Goal id. |
| `description` | yes | What this goal achieves, written for the planner and the user. |
| `outputTypeName` | yes | The `DomainType` the goal produces. |
| `export` | no | If true, listed as a user-facing capability (chat menus, /commands). Default `false`. |

---

## `commands/` — chat commands

Maps a `/slash` chat command to an action.

```yaml
# commands/fix-issue.yml
command: fix-issue
actionName: triage-github-issue
description: "Triage a GitHub issue and attempt to fix it if suitable"
```

| field | required | meaning |
|---|---|---|
| `command` | yes | Slash name without leading `/`. Becomes `/fix-issue`. |
| `actionName` | yes | Name of an action defined in this pack or another loaded pack. |
| `description` | yes | What the command does. Shown in the slash-command picker. |

---

## `apis/` — learnable API specs

Declares an external HTTP API the host should learn from a spec (OpenAPI, GraphQL, etc.). The host compiles each operation into a callable action whose input/output are `DomainType`s — so APIs become first-class peers of pack-declared actions.

```yaml
# apis/linear.yml
name: linear
type: openapi
spec-url: https://developers.linear.app/api/openapi.yaml
auth: bearer
token-env: LINEAR_API_TOKEN
```

| field | required | meaning |
|---|---|---|
| `name` | yes | Namespace under which the host registers compiled methods (e.g. `linear.list_issues`). |
| `type` | yes | One of `openapi`, `graphql`. |
| `spec-url` | yes | URL the host fetches and compiles. |
| `auth` | no | One of `none`, `bearer`, `basic`, `api-key`. |
| `token-env` | conditional | Env-var name carrying the credential. Required when `auth != none`. |

---

## `webhooks/` — webhook receivers

Declares webhook endpoints the host should accept and route to actions. The host owns signature verification, tenancy resolution, and HTTP plumbing. Pack-declared webhooks describe **what to do with the payload**.

```yaml
# webhooks/github-issues.yml
- name: github-issues
  description: "Receive GitHub issue events"
  source: github-issues
  events: [issues, issue_comment]
  action: webhook-github-issue
```

| field | required | meaning |
|---|---|---|
| `name` | yes | Receiver id. Becomes part of the inbound URL path. |
| `description` | yes | What this receiver is for. |
| `source` | yes | Stable identifier for the webhook source (used for tenancy + UI). |
| `events` | no | List of event types this receiver accepts (provider-specific). |
| `action` | yes | Action invoked with the parsed payload. |

The bare-webhook flow stays as today: a webhook arrives, the host wraps the payload in a `WebhookEvent`, and dispatches the named action. For richer integration — emitting typed signals into the consequence engine — use `events/` instead.

---

## `events/` — event ingestion (forward-looking)

Unifies push (webhook) and pull (polling) event sources behind a single contract: **emit typed `Signal`s into the host's consequence engine.** A signal type is just a `DomainType` whose parent is `Signal`.

This section is **forward-looking** — the spec is settled but specific hosts may still be implementing it. Existing webhook receivers (the `webhooks/` block above) continue to work in parallel.

### Webhook event source

```yaml
# events/stripe.yml
- type: StripeEvent          # name of a type whose parents include Signal
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

| field | required | meaning |
|---|---|---|
| `type` | yes | Name of a `DomainType` declared in this pack (or another loaded pack) whose `parents` includes `Signal`. |
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

| field | required | meaning |
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

Both sources produce `Signal`s of the pack-declared type. From here the consequence engine, triage rules, persistence (`SignalRecord`), notifications, and chat surfacing are all type-aware: `signal.type.isAssignableFrom(StripeEvent)` is a real predicate, not a string match.

No JVM bytecode is shipped — packs that need behaviour beyond mapping should expose it via `actions/` (LLM-driven) or `mcp/` (sandboxed servers).

---

## `channels/` — messaging channel templates

Declares messaging-channel configurations the pack ships as defaults. These are templates: the user sets the secret(s) and starts the channel via the host UI.

```yaml
# channels/telegram.yml
type: com.embabel.assistant.event.channel.telegram.TelegramChannelConfig
name: telegram
token-env: TELEGRAM_BOT_TOKEN
auto-start: true
```

The `type` field is a fully qualified class name resolved by the host's polymorphic deserializer. Adding new channel kinds requires host changes today; future spec revisions may pull this into pack-declarable form.

---

## `cron/` — scheduled jobs

```yaml
# cron/morning-briefing.yml
name: morning-briefing
cron: "0 0 8 * * *"
actionName: cron-ping
description: "Daily 8am chime"
```

| field | required | meaning |
|---|---|---|
| `name` | yes | Job id. |
| `cron` | yes | Six-field Spring cron expression. |
| `actionName` | yes | Action invoked when the job fires. |
| `description` | no | Shown in the job list. |

The fired action receives a `CronTrigger` input carrying the job's `name` (matchable in action `pre:` SpEL guards).

---

## `prompts/` — Jinja templates

Pack-shipped Jinja templates can be referenced by actions or used to override host-default prompts. Templates resolve relative to the pack's `prompts/` directory; cross-pack references use the `pack-name:template-name` notation.

```jinja
{# prompts/triage.jinja #}
You are reviewing a GitHub issue for an AI coding agent.

Issue: #{{ issue.issue }} in {{ issue.owner }}/{{ issue.repo }}
{{ issue.title }}

{{ issue.body }}

Decide whether the agent should attempt this. Return TriagedIssue or null.
```

Inline action prompts (the `prompt:` field on an action spec) are also Jinja and have access to the same template helpers.

---

## `skills/` — skill descriptors

A skill is a self-contained set of instructions following the [agentskills.io](https://agentskills.io) spec. Packs declare their skills in `skills/skills.yml`:

```yaml
# skills/skills.yml
- type: github
  url: https://github.com/Orchestra-Research/AI-Research-SKILLs/blob/main/21-research-ideation/creative-thinking-for-research
- type: local
  path: ./skills/triage-issues
```

| field | meaning |
|---|---|
| `type` | `github` (resolved from URL) or `local` (resolved from path inside the pack). |
| `url` | Required for `type: github`. |
| `path` | Required for `type: local`. Relative to the pack root. |

---

## `mcp/` — MCP server descriptors

Declares Model Context Protocol servers the pack contributes.

```yaml
# mcp/arxiv.yml
- name: arxiv
  description: "Search and read arXiv research papers"
  command: docker
  args: ["run", "-i", "--rm", "mcp/arxiv-mcp-server:latest"]
```

| field | required | meaning |
|---|---|---|
| `name` | yes | MCP server id. Tools surface as `name.<tool>`. |
| `description` | yes | What the server provides. Surfaced to the LLM. |
| `command` | yes | Executable to launch the server (typically `docker`). |
| `args` | yes | Argument list passed to `command`. |

Multiple servers per file are allowed (the file is a list).

---

## What's intentionally not in a pack

- **JVM bytecode**, native libraries, scripts to be executed in-process.
- **Spring beans, classpath contributions, host configuration changes.**
- **User credentials.** Packs reference secrets by env-var name; the user supplies the secret out-of-band (host UI, env, etc.).
- **Per-user state.** A pack ships templates and types; the *workspace* holds the per-user instances.

If a capability needs real code, ship it via `actions/` (LLM in the loop), `mcp/` (sandboxed server, arbitrary code), or as a host-level extension out of band.

---

## Conventions

- **Naming**: lowercase-hyphenated for ids (pack name, action name, command name); UpperCamelCase for type names.
- **YAML**: prefer multi-doc files only when the entries are tightly related; otherwise one file per item.
- **Descriptions are LLM-readable**: write descriptions assuming an LLM planner is the primary reader.
- **Stable ids**: changing a `name` is a breaking change for any installed workspace that wired against it.

---

## Versioning

Packs follow semantic versioning in `pack.yml`. The `version` is informational; hosts may track it to detect upgrades but the contract is at the directory-and-field level — adding a new optional field is a minor change, removing or renaming a required field is a major one.

The spec itself is versioned by this repository's git history. Hosts target a spec revision; packs declare compatibility informally for now.

---

## License

This specification is released under the Apache License, Version 2.0. See [LICENSE](LICENSE).

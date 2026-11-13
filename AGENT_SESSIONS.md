# Agent sessions: a realm starts work on an agent and hears when it ends

> **Status: proposed capability.** No host implements any part of this yet. No host accepts the
> `agentSessions` field, the `sessions` app flag or the operation names below today; `ctx.call` with
> any of those names is refused like any other unknown name (see
> [the model call](TYPESCRIPT_REALMS.md#the-model-call)). It is written so the declaration, the
> calls and the refusals are fixed before any host reads them. The limits quoted are proposed
> reference values.

A realm can store, query and show work. With this capability it can also cause work: a handler
starts a session on an agent, the agent works in the owner's name, and the realm hears when the
session ends. The coding realm starts research on a task from its board; the research realm fans a
topic out into parallel sessions.

What the realm holds is small on purpose: a session id, and a `ref` of its own choosing that says
which of its items the session is for. The transcript, the agent's sign-in, the folder on disk and
every consent prompt stay with the host. A realm never renders a transcript and never sees a path.

## Contents

1. [Declaring agent sessions](#1-declaring-agent-sessions)
2. [Handler operations](#2-handler-operations)
3. [Opening a session from a page](#3-opening-a-session-from-a-page)
4. [The ended event](#4-the-ended-event)
5. [Workspaces](#5-workspaces)
6. [Sessions in Cypher](#6-sessions-in-cypher)
7. [How agents are reached](#7-how-agents-are-reached)
8. [Refusals](#8-refusals)
9. [Worked examples](#9-worked-examples)
10. [Limits at a glance](#10-limits-at-a-glance)

## 1. Declaring agent sessions

A captured realm asks for agent sessions with a top-level `agentSessions` field in `realm.ts`:

```typescript
export default defineRealm({
  name: "coding",
  version: "0.4.0",
  host: "wasm",
  execution: "captured",
  handlers: {
    startResearch: { namespace: "coding" },
    sessionEnded: { namespace: "coding" },
  },
  agentSessions: {
    providers: ["local", "host"],
    workspace: "project",
    maxConcurrent: 3,
    onEnded: "coding.sessionEnded",
  },
});
```

| Field | Rule |
| --- | --- |
| `providers` | Required. The provider kinds the realm may start sessions on, each once: `local` (a local agent tool on the owner's own machine), `host` (the host's own agent) and `remote` (an agent that runs elsewhere, under a key the owner chose). A kind is a category, never a vendor or a product. An unknown kind refuses the declaration, naming it. |
| `workspace` | `none` (the default) or `project`. With `none`, a session has no folder and any `workspace` on a start is refused. With `project`, a start may name one of the owner's projects; see [workspaces](#5-workspaces). |
| `maxConcurrent` | Whole number from 1 to 3, default 1. How many sessions may be open at once for one ticket (one `ref`, see below). The host's cap is three per ticket, so a larger number refuses the declaration. |
| `onEnded` | Optional. A handler this realm declares, written `namespace.verb`, that receives the [ended event](#4-the-ended-event). A name the realm does not declare refuses the declaration. Left out, the realm hears nothing and learns of ended sessions by listing them. |

Any other field is refused. A refused declaration is a load problem naming the field; the rest of
the realm loads, and the realm is treated as declaring no agent sessions.

**Guarantee: without the declaration, every call is refused.** A realm with no `agentSessions`
field gets `AGENT_SESSIONS_NOT_DECLARED` from every operation in section 2, and a page of that
realm cannot open a session. Nothing about a realm that does not declare it changes.

The declaration is new in `realm.ts` only. Legacy `realm.yml` receives no new features, as
[source selection](TYPESCRIPT_REALMS.md#source-selection-and-legacy-compatibility) says.

### What the owner approves

Installing grants nothing, as for every other capability. The owner decides three things, at
three moments:

1. **At admission**, the resource `agent_sessions`, separately from the handlers. The approval
   screen shows the declaration as written: which kinds, whether the realm may use projects, how
   many sessions per ticket, and which handler hears the end. Approving a handler never grants it,
   and the `onEnded` handler still needs its own handler approval.
2. **Per ticket and provider kind**, for `local` and `remote` sessions. The first start for a
   `ref` and kind the owner has not yet allowed asks the owner, showing the realm, the `ref`, the
   `title` and the provider kind; with no `title`, the prompt shows the `ref` alone. Until they
   agree, that start is refused with `AGENT_SESSION_CONSENT`. Once allowed, any later start under
   that `ref` and kind needs no prompt, whatever its title or prompt says, up to `maxConcurrent`
   open at once. Allowing `local` for a ref does not allow `remote` for it. A start while the
   owner has not yet answered is refused again and does not prompt again. Once the owner declines,
   a later start for that ref and kind is refused without a new prompt; only the owner reverses it,
   in the host's settings for the realm. `host` sessions run the host's own agent under the owner's
   existing budgets and need only the admission approval.
3. **Per project**, the first time any session asks for a project folder. See
   [workspaces](#5-workspaces).

**Approve all.** Every one of those approvals can be given once, for good. The admission screen
offers **Approve all**, and so does every ticket and project prompt. One click grants the
`agent_sessions` resource and the `onEnded` handler, and allows every ticket and every project the
realm asks for, now and later, for every provider kind the declaration names. After that the
realm never sees `AGENT_SESSION_CONSENT` or `AGENT_WORKSPACE_CONSENT`, and the owner is never
asked again. The standing grant covers only this installation of the realm and only what its
declaration named when the owner gave it: its provider kinds, its workspace mode, its
`maxConcurrent` and its `onEnded` handler. An upgrade or reinstall that widens any of these asks
again. Widening is any of:

- a provider kind the grant did not cover;
- `workspace: project` where the grant covered `none`;
- a higher `maxConcurrent`;
- adding an `onEnded` handler where there was none, or changing it to a different handler.

Narrowing any of them keeps the grant: dropping a provider kind, going back to `workspace: none`, a
lower `maxConcurrent`, or removing `onEnded`. `maxConcurrent` still applies under the grant, because it
limits load rather than asking the owner anything.

**Grants follow the installation, not the name.** Ownership of sessions, the standing grant, and
every ticket and project approval belong to the installation the owner admitted, which keeps one
identity for as long as it stays installed. A different realm installed later under a name that
was used before starts with nothing: no sessions, no grants, no approvals.

The owner can withdraw the standing grant at any time, which returns the realm to asking per
ticket and per project; sessions already open keep running, and ticket and project approvals
already given one by one stay given. Withdrawing it is not the same as revoking `agent_sessions`:
**Approve all** granted that resource as a separate approval, and withdrawing the standing grant
leaves it granted. Revoking it is described below.

A **ticket** is everything a realm starts under one `ref`. The host compares refs exactly and never
reads meaning into them: `task/42` and `task/42/a` are two tickets.

**One start, one prompt.** A start checks the request and its project first: an invalid field or a
project that does not exist is refused before the owner is asked anything. Then the host gathers
every approval the start still needs, the `agent_sessions` resource, the ticket and the project, and
asks for all of them in a single prompt. The start is refused with `AGENT_SESSION_CONSENT`, whose
message names everything pending. When the owner approves that prompt, the next start goes through.
`AGENT_WORKSPACE_CONSENT` is used only when the ticket is already allowed and the project is the one
thing missing.

The resource, the ticket and the project each have one of three answers: allowed, pending (asked,
not yet answered) or declined. Pending is never asked again: a start while anything it needs is
pending is refused with the same `AGENT_SESSION_CONSENT` and raises no new prompt. A declined
answer is never asked again either, and it is refused before any prompt is raised for the rest:

- When the owner declined the `agent_sessions` resource, every operation, `start` included, is
  refused with `AGENT_SESSIONS_NOT_GRANTED`.
- When the owner declined the ticket for this provider kind, the start is refused with
  `AGENT_SESSION_CONSENT` and its declined text.
- When the owner declined the project, the start is refused with `AGENT_WORKSPACE_CONSENT` and its
  declined text, even if the ticket has not been asked about yet.

Only the owner reverses a declined answer, in the host's settings for the realm.

Revoking `agent_sessions` cancels the realm's open sessions and refuses its next call. Every
approval and revocation moves the installation revision, as
[owner approval](TYPESCRIPT_REALMS.md#owner-approval-step-by-step) describes.

## 2. Handler operations

A handler calls each operation by name with `ctx.call`, as it calls the model:

```typescript
const { session, state } = await ctx.call("agent_session_start", {
  provider: "local",
  ref: "task/42",
  title: "Where does the importer drop rows?",
  prompt: "Find where the importer drops rows without an error, and say why.",
});
```

Each call resolves to the answer shown, or rejects with an error whose `code` is one of the codes in
[refusals](#8-refusals) and whose message says what was refused and what to do. Branch on the
`code`, never on the message.

### States and outcomes

A session is always in one of four states:

| State | Meaning |
| --- | --- |
| `running` | The agent is working on a turn. |
| `needs_input` | The agent has stopped to ask something: a question, or permission to act. |
| `idle` | The agent finished a turn and the session is open for another message. Only a session started with `stayOpen: true` goes idle. |
| `ended` | No further turns. An ended session carries an outcome. |

| Outcome | Meaning |
| --- | --- |
| `done` | The agent finished. A session without `stayOpen` ends `done` when its first turn finishes without a question; one with `stayOpen` ends `done` when it is cancelled while idle, or after the host's published idle period. |
| `failed` | The agent or its tool stopped with an error, or the workspace could not be prepared. |
| `cancelled` | The realm, the owner, or a revocation stopped it while it was running or waiting for input. |
| `limit` | The agent's tool reported a usage limit, or the session reached the host's time limit. |

A session never leaves `ended`. A realm cannot set a state or an outcome; the host records both.

### `agent_session_providers`

```typescript
const { providers } = await ctx.call("agent_session_providers", {});
// providers: Array<{ id, kind, label, access, state }>
```

Lists the providers this realm may use now: only the kinds it declared, and only those the owner has
in this installation. Each entry is:

- `id`: the host's id for the provider, stable for the installation. Pass it to `start`. It is
  opaque; a realm must not parse it or keep a list of known ids.
- `kind`: `local`, `host` or `remote`.
- `label`: the name the owner sees, for showing on a page.
- `access`: how the agent is signed in. `subscription` is the owner's own sign-in to their own
  tool; `key` is a key the owner chose; `local` is a tool that needs no sign-in; `host` is the
  host's own agent.
- `state`: `ready`, or `unavailable` when the owner has the provider but it cannot start a session
  now (signed out, not installed on this machine, or not offered in this installation).

An installation where no local agent tool can run lists no `local` provider at all.

### `agent_session_start`

| Input | Rule |
| --- | --- |
| `provider` | Required. A provider `id` from `agent_session_providers`, or a bare kind (`local`, `host`, `remote`), which picks the owner's default provider of that kind. |
| `prompt` | Required, not blank, at most 64 KiB. The first message to the agent. |
| `ref` | Required, 1 to 256 characters. The realm's own key for the item this session is for. The host stores it, compares it exactly, and never interprets it. |
| `title` | Optional, at most 200 characters. Shown to the owner in the consent prompt and the session view. |
| `workspace` | Optional, and only when the declaration says `workspace: project`. See [workspaces](#5-workspaces). |
| `stayOpen` | Optional boolean, default false. Keeps the session open for further messages after a turn. |

Any other field is refused, naming it. The answer is `{ session, state }`: a new session id and its
first state, normally `running`. The host issues the id. It is opaque, unique across every provider,
and stable for the life of the session: the same id names the session in `list`, `read`, the ended
event, Cypher and the host's view. The host stamps the session with the calling realm as its owner.
A realm cannot name another owner, and no input field can change it.

A start is one session. To ask two agents the same question, start two sessions; the count against
`maxConcurrent` is per ticket, and covers every session under that `ref` that has not ended.

### `agent_session_say`

```typescript
await ctx.call("agent_session_say", { session, text: "Also check the retry path." });
// resolves to { state }
```

Sends `text` (1 byte to 64 KiB) to the agent as a message in the session. In the owner's view it
shows as coming from the realm, never as the owner's own words. A message to a running session is
taken at the agent's next opportunity. A message answers a question the agent asked, but never a
permission request: only the owner, in the host's session view, can grant an agent permission to
act. A message sent while the agent waits on a permission is held for its next turn. A message to
an ended session, including a session without `stayOpen` that ended when its turn finished, is
refused with `AGENT_SESSION_ENDED`. When the provider cannot be reached, the message is refused
with `AGENT_PROVIDER_UNREACHABLE` and is not kept.

### `agent_session_cancel`

```typescript
await ctx.call("agent_session_cancel", { session });
// resolves to the session's summary, now ended
```

Ends the session. A running or waiting session ends `cancelled`; an idle one ends `done`, since
nothing was interrupted. Cancelling a session that has already ended changes nothing and answers
its summary, so a retried cancel is safe.

**Guarantee: cancel always succeeds.** A cancel ends the session in the host's record at once and
frees its place under `maxConcurrent`, even when the provider cannot be reached. The host passes the
cancel on to the provider as soon as it can, and keeps trying until the provider confirms it or no
longer knows the session. Revoking `agent_sessions` cancels the same way.

**Guarantee: the first end wins.** A session ends once. If the agent finishes and a cancel arrives
at the same moment, whichever the host records first is the outcome, and every later answer, the
ended event and the `AgentSession` node all report that one outcome.

### `agent_session_list`

```typescript
const { sessions } = await ctx.call("agent_session_list", { refPrefix: "task/42" });
```

| Input | Rule |
| --- | --- |
| `ref` | Optional. Sessions with exactly this ref. |
| `refPrefix` | Optional. Sessions whose ref starts with this text. Not with `ref`. |
| `state` | Optional. One of the four states. |
| `limit` | Optional, 1 to 100, default 50. |

Answers `{ sessions }`, newest first, each a summary:

```typescript
interface SessionSummary {
  session: string;
  ref: string;
  provider: string;          // the provider id
  kind: "local" | "host" | "remote";
  title?: string;
  state: "running" | "needs_input" | "idle" | "ended";
  outcome?: "done" | "failed" | "cancelled" | "limit";   // present when ended
  startedAt: string;         // ISO-8601
  endedAt?: string;
  workspaceRef?: string;     // the branch, when the session asked for one
  lastText?: string;         // the agent's latest message, cut to 1,000 characters
}
```

A list only ever holds sessions this realm started, for this owner. There is no way to ask for
another realm's sessions.

**Guarantee: a page never receives the agent's words.** In an invocation a page started through
`realm.call`, any summary a page receives leaves out `lastText`, whichever operation returned it:
`list`, `cancel`, or any other answer that carries a summary.

### `agent_session_read`

```typescript
const { parts, rev, truncated } = await ctx.call("agent_session_read", { session, afterRev: 0 });
```

Answers the session's finished parts after `afterRev` (0 when left out), in the order they were
finished. Each part is `{ id, rev, from, kind, text }`: `id` is stable for the part, `from` is
`agent`, `owner` or `realm`, and `kind` is `message` or `tool`, where a `tool` part carries a short
description of what the agent did. A message the agent is still writing is not returned until it
is finished, and a finished part never changes. `rev` is the last revision returned; pass it as
`afterRev` to read on. Reading the same `afterRev` twice answers the same parts in the same order,
so a retried read is safe. On a session that is still live, a later read from the same `afterRev`
starts with exactly the parts the earlier read returned, and may add parts finished since then
after them. `truncated` is true when more parts exist than fit one answer (at most 200 parts and
1 MiB); read again from `rev`. When the provider cannot be reached, a read is refused with
`AGENT_PROVIDER_UNREACHABLE`.

A read is for handlers that act on what the agent said, such as an `onEnded` handler writing a
result into the realm's own records. It is refused, with `AGENT_SESSION_READ_FROM_PAGE`, in any
invocation a page started through `realm.call`: a page shows a session by opening the host's view,
never by rendering its parts.

## 3. Opening a session from a page

A captured app that declares `sessions: true` gets one more call on its bridge:

```typescript
apps: {
  "board.html": {
    handlers: ["coding.board", "coding.startResearch"],
    sessions: true,
  },
},
```

```javascript
const { sessions } = await realm.call("coding.board", { task: "42" });
await realm.sessions.open(sessions[0].session);
```

`realm.sessions.open(session)` asks the host to show its own session view for that session, outside
the page's frame. It resolves once the host has shown it, and tells the page nothing about what
happens there. The view is the host's: it names the realm and the session's `title`, shows the
transcript, and lets the owner reply, answer a question, grant or refuse a permission, and cancel.
The page learns any change by calling one of its own handlers that lists sessions.

- The session must belong to this realm. The call follows the bridge's rules for
  [captured browser apps](HOSTED_EXECUTION.md#captured-browser-apps): one call at a time, and every
  refusal rejects with the same message, "Realm call refused or unavailable".
- An app without `sessions: true` has no `realm.sessions`. A realm whose declaration has no
  `agentSessions` cannot set the flag; the app is refused, naming the field.
- The flag gives the page no transcript, no session state of its own, and no way to start or
  cancel a session. A summary that reaches a page through one of its handlers never carries
  `lastText`. Those go through the realm's handlers, under their approvals.

## 4. The ended event

When a session ends, for any reason and whoever ended it, the host calls the `onEnded` handler with
a summary:

```typescript
interface AgentSessionEnded {
  session: string;
  ref: string;
  provider: string;
  kind: "local" | "host" | "remote";
  title?: string;
  outcome: "done" | "failed" | "cancelled" | "limit";
  startedAt: string;
  endedAt: string;
  workspaceRef?: string;
}
```

The event is a summary only. It carries no transcript and no final text; a handler that needs the
agent's words calls `agent_session_read`.

**Guarantee: at least once.** Every session that ends produces an event, and the host keeps trying,
with growing pauses and across a host restart, until the handler returns successfully or 24 hours
have passed. An event still undelivered after 24 hours is dropped and recorded where the owner can
see it. The same event may arrive more than once. It may arrive after a later
`agent_session_list` already shows the session ended, and it may arrive before the
`agent_session_start` call that began the session has returned. Key every effect on `session`:
publish with the session id as the event id, or check your own record before writing a second
time.

**Guarantee: no event without a grant.** While `agent_sessions` or the `onEnded` handler is not
approved, no event is delivered and none is kept for later. A realm that may have missed events
reconciles with `agent_session_list({ state: "ended" })`, which is the authority on what ended.

The handler runs like any other dispatch, with the same budgets. It may start a new session, for
example to retry on another provider, and that start counts against the ticket as usual.

## 5. Workspaces

A realm that declares `workspace: project` may give a session a folder to work in. It names a
project, and the host does the rest:

```typescript
workspace: { project: "importer" }                                       // the project as it is
workspace: { project: "importer", base: "main", branch: "task-42-fix" }  // its own branch
```

- `project` is the name of a project the owner has set up in the host, 1 to 128 characters. The
  realm gets the name from the owner, for example as a field on its own item. It never names a
  folder, and the host never tells it where the project lives.
- `branch` asks for a separate working copy on that branch, so sessions that change files do not
  disturb each other. A branch that already exists is used as it is, never reset. A branch that
  does not exist is created from `base`, the project's default branch when `base` is left out.
  `base` without `branch` is refused. If the owner has that branch checked out in their own
  project folder, the session gets a separate working copy of it; the owner's folder is never
  switched to another branch.
- A session may not work on the project's default branch, and may not use a branch that another
  open session is using. Either is refused with `AGENT_SESSION_INVALID`, naming the reason.
- `base` and `branch` each start with a letter or digit, then up to 199 more letters, digits, `.`,
  `_`, `/` or `-`. Neither may contain `..` or `//`, or end in `/` or `.lock`. Any other name is
  refused with `AGENT_SESSION_INVALID`, and the message states this rule.
- The session's `workspaceRef` is the branch name when one was asked for, and absent otherwise.
- Sessions that share a project without a branch share its files. Give each session its own branch
  when more than one may change files at once.

**Guarantee: approval is per project and held by the host.** The first session to use a project
asks the owner, naming the project and the realm. The answer covers that project for every
provider and every later session, until the owner withdraws it; it is not tied to one agent, and a
session that moves between agents keeps it. A realm never sees the approval, cannot grant it, and
learns of it only through `AGENT_SESSION_CONSENT` or `AGENT_WORKSPACE_CONSENT` while it is missing.

When a session with a branch ends, the branch and its commits remain the owner's. A realm cannot
delete a branch or a working copy.

## 6. Sessions in Cypher

Every session is a node of the host type `AgentSession`:

| Property | Meaning |
| --- | --- |
| `id` | The session id. |
| `owner` | The realm installation that started the session: an opaque value, stable while the realm stays installed. A different realm later installed under the same name has a different value. |
| `ref` | The ref the realm passed. |
| `provider` | The provider id. |
| `state` | One of the four states. |
| `outcome` | Present once ended. |
| `startedAt`, `endedAt` | Timestamps; `endedAt` once ended. |
| `workspaceRef` | The branch, when the session asked for one. |

A realm's query sees only the `AgentSession` nodes it owns. The owner sees all of their own. A
realm cannot declare `AgentSession`, add properties to it, or write it through a write proposal.
The node may trail a change by a few seconds; `agent_session_list` answers the current state.

There is no edge between a session and a realm's item. A realm joins them by value, on `ref`:

```typescript
const { rows } = await ctx.gateway.cypher.query({
  cypher: `MATCH (t:CodingTask), (s:AgentSession)
           WHERE t.id = $task AND s.ref = $ref
           RETURN s.id AS session, s.state AS state, s.outcome AS outcome
           LIMIT 20`,
  params: { task: "42", ref: "task/42" },
});
```

The usual rules of the [graph-query profile](HOSTED_EXECUTION.md#captured-graph-query-profile)
apply, including its `cypher_query` approval. Choosing refs that are a stable property of the item
(`task/<id>`) is what makes the join a single equality.

## 7. How agents are reached

These are guarantees to the owner. A realm can rely on them, and cannot change them.

- A `local` session runs the owner's own installed local agent tool, on the owner's own machine,
  under the owner's own sign-in to that tool. The host drives the tool; it does not install it,
  sign it in, or hold its login.
- The host never handles a login for any provider: it does not read, store, copy or refresh one,
  and never signs an agent in on the owner's behalf somewhere else.
- A `remote` session uses a key the owner chose for that provider. A realm never sees it.
- A `host` session runs the host's own agent, under the owner's existing budgets.
- An installation with no local agent tools, such as a server deployment, lists no `local`
  provider. A realm that declares only `local` gets an empty list there, and should say so on its
  page rather than fail.
- A session belongs to the owner who was signed in when it started. Another owner of the same host
  never sees it, and a local session refuses to run under a different sign-in than the one it
  started with.
- An agent in a session reaches the owner's tools, including a realm's published tools, the same
  way any agent the owner connects does, under the approvals that already exist. Starting a session
  grants the agent nothing new.

## 8. Refusals

Every refusal rejects with an error carrying a `code` and a message. The message names what was
refused and the lever that fixes it, so the person or the model reading it can act. It contains only
values the realm supplied or may already see: its own refs and titles, its declared kinds, provider
ids from its own list. The same call refused for the same reason gets the same message.

| Code | When | Message |
| --- | --- | --- |
| `AGENT_SESSIONS_NOT_DECLARED` | The realm declares no `agentSessions`. | "This realm cannot start agent sessions because it declares no agentSessions block. Add agentSessions to realm.ts with the provider kinds it needs, then reinstall." |
| `AGENT_SESSIONS_NOT_GRANTED` | Any operation other than `start` while the owner has not approved `agent_sessions`, or any operation, `start` included, once the owner has declined it. A `start` while the resource is unasked or pending is refused with `AGENT_SESSION_CONSENT` instead. | "The owner has not allowed this realm to run agent sessions. Ask the owner to approve agent sessions for this realm." If the owner declined: "The owner declined agent sessions for this realm. Do not start sessions unless the owner asks; the owner can change this in the realm's settings." |
| `AGENT_PROVIDER_UNKNOWN` | `provider` is a kind the realm did not declare, or not a kind or an id at all. | "Provider 'cloud' is not one this realm may use. Declared kinds: local, host. Pass one of these kinds, or an id from agent_session_providers." |
| `AGENT_PROVIDER_UNAVAILABLE` | A start names a provider that exists but cannot start a session now. Used only by `start`. | The message gives one reason and its lever. Not installed: "Provider 'p-2' is not available now: its local agent tool is not installed on this machine. Ready providers of kind local: p-1. Start with one of them, or ask the owner to install the tool." Signed out: "... it is signed out. ... or ask the owner to sign in." Machine not connected: "... the owner's machine that runs it is not connected. ... or start again once the owner is back." Other: "... it cannot start sessions right now. ... or try again later." When no provider of the kind is ready, the lever lists only the realm's declared kinds that have a ready provider: "No local provider is available in this installation. Ready kinds this realm may use: host." With none: "No provider this realm may use is ready. Tell the owner, and try again later." |
| `AGENT_PROVIDER_UNREACHABLE` | `say` or `read` while the session's provider cannot be reached. | "The provider running session 's-81f' cannot be reached. Try again later, or cancel the session to free its slot." |
| `AGENT_SESSION_LIMIT` | The ticket already has `maxConcurrent` open sessions, or the installation has reached the host's ceiling on open sessions (proposed: 12), or the provider is refusing new sessions because it is busy. | "Ticket 'task/42' already has 3 open sessions, the most this realm allows. Cancel one with agent_session_cancel, or start again after one ends." At the ceiling: "This realm already has 12 open sessions, the most the host allows for one installation. Cancel one, or start again after one ends." Provider busy: "Provider 'p-1' is not taking new sessions right now. Start again later, or use another provider." |
| `AGENT_SESSION_CONSENT` | Something the start needs is not yet approved: the `agent_sessions` resource, the ticket for this provider kind, or the project. One prompt asks for all of them. | "Waiting for the owner to allow: agent sessions for this realm; local sessions for 'Where does the importer drop rows?' (task/42); project 'importer'. They have been asked once for all of these; start again after they agree." With no title, the ticket is named by its ref alone. If the owner declined the ticket: "The owner declined local sessions for 'task/42'. Do not start again for this ticket unless the owner asks; the owner can change this in the realm's settings." |
| `AGENT_WORKSPACE_NOT_DECLARED` | A start names a `workspace` but the declaration says `none`. | "This realm declares workspace: none, so a session cannot have a project. Remove workspace from the start, or declare workspace: project and reinstall." |
| `AGENT_WORKSPACE_UNKNOWN` | No project of that name. | "There is no project named 'importr'. Check the name with the owner, or ask them to add the project." |
| `AGENT_WORKSPACE_CONSENT` | The ticket is allowed and the project is the only approval missing, or the owner has declined the project (then whatever the ticket's answer, and with no prompt). | "The owner has not yet allowed agents to work in project 'importer'. They have been asked; start again after they agree." If declined: "The owner declined agents in project 'importer'. Start without a workspace, or ask the owner." |
| `AGENT_SESSION_REF_TOO_LONG` | `ref` is longer than 256 characters. | "ref is 312 characters; the limit is 256. Use a shorter key, such as the item's id." |
| `AGENT_SESSION_NOT_OWNED` | The session id is unknown, or belongs to another realm or owner. | "No session 's-81f' belongs to this realm. Use a session id returned by agent_session_start or agent_session_list." |
| `AGENT_SESSION_ENDED` | `say` to an ended session. | "Session 's-81f' has ended (outcome: done). Start a new session to continue the work." |
| `AGENT_SESSION_READ_FROM_PAGE` | `read` in an invocation a page started. | "A page cannot read a session's messages. Call realm.sessions.open(session) to show it; read from a handler that runs without a page, such as onEnded." |
| `AGENT_SESSION_INVALID` | A field is missing, blank, out of range, or unknown, or a branch name breaks the rule in [workspaces](#5-workspaces). | "agent_session_start does not accept 'model'. Accepted fields: provider, prompt, ref, title, workspace, stayOpen." For a branch: "branch 'fix..retry' is not a usable branch name. A branch starts with a letter or digit, uses only letters, digits, '.', '_', '/' and '-', has no '..' or '//', and does not end in '/' or '.lock'." Default branch: "branch 'main' is the project's default branch, which a session may not work on. Name a branch of its own, for example 'task-42'." In use: "branch 'task-42' is in use by another open session. Name a different branch, or start again after that session ends." |

**Guarantee: another realm's session is indistinguishable from none.** An id that belongs to
another realm or another owner is refused with `AGENT_SESSION_NOT_OWNED` and the same message as an
id that does not exist, so a realm cannot learn that someone else's session exists.

The single fixed refusal message of other gateway calls does not apply here. Like the
[model call](TYPESCRIPT_REALMS.md#the-model-call) and the
[assistant call](HOSTED_EXECUTION.md#the-assistant-call), these refusals carry a code, because a
realm must be able to tell "ask the owner" from "pick another provider". A page's
`realm.sessions.open` is the exception: it keeps the bridge's one message.

## 9. Worked examples

### Coding: research on two local agents for one task

The board's "Start research" button calls `coding.startResearch` for a task. The handler picks two
ready local providers from the list, never from a list of vendor ids it keeps itself, and starts one
session on each under the task's ref. The prompt tells the agent to record what it finds with the
realm's own tool, so findings come back as the realm's own records, and the board reads them with
the Cypher it already has.

```typescript
export const startResearch = async (input: { task: string; question: string; project: string }, ctx) => {
  const ref = `task/${input.task}`;
  const { providers } = await ctx.call("agent_session_providers", {});
  const local = providers.filter((p) => p.kind === "local" && p.state === "ready").slice(0, 2);
  if (local.length === 0) return { started: [], note: "No local agent is available here." };
  const started = [];
  for (const p of local) {
    try {
      started.push(await ctx.call("agent_session_start", {
        provider: p.id,
        ref,
        title: input.question,
        workspace: { project: input.project },
        prompt: `${input.question}\n\nRecord each finding with the coding realm's record findings tool for task ${input.task}.`,
      }));
    } catch (e) {
      if (e.code === "AGENT_SESSION_CONSENT") return { started, waiting: true };  // the owner has been asked
      throw e;
    }
  }
  return { started };
};

export const sessionEnded = async (event, ctx) => {    // onEnded
  if (event.outcome === "done") return {};
  await ctx.gateway.channel.publish({
    source: "questions",
    eventId: `unfinished-${event.session}`,        // the same event twice files once
    streamId: event.ref,
    occurredAt: event.endedAt,
    payload: { ref: event.ref, title: event.title, outcome: event.outcome,
               text: "Research session did not finish" },
  });
  return {};
};
```

If the owner chose **Approve all**, the button starts both at once with no prompt. Otherwise the
first start for `task/42` asks the owner, once, for everything it needs; the handler catches
`AGENT_SESSION_CONSENT`, starts nothing more, and the page says it is waiting. When the owner
agrees, pressing the button again starts both. Partial starts are fine: if the second start is
refused for another reason, the first session keeps running and the board shows what started. The board lists
them with `agent_session_list({ ref: "task/42" })` and opens one with `realm.sessions.open`. A
session that ends `failed` or `limit` files an open question on the task, once, however many times
the event arrives.

### Research: fanning a topic out to the host's own agent

The research realm declares `providers: ["host"]`, `workspace: "none"` and `maxConcurrent: 3`, and
runs in an installation with no local agent tools, where `agent_session_providers` lists only the
host's agent. For each topic, its daily run starts one session per sub-question under the topic's
ref for that day:

```typescript
export const researchDaily = async (input: { topic: string; day: string; questions: string[] }, ctx) => {
  const ref = `topic/${input.topic}/${input.day}`;          // for example topic/7/2026-11-13
  for (const q of input.questions.slice(0, 3)) {
    await ctx.call("agent_session_start", { provider: "host", ref, title: q, prompt: q });
  }
  return {};
};

export const sessionEnded = async (event, ctx) => {    // onEnded
  if (event.outcome !== "done") return {};
  const { parts } = await ctx.call("agent_session_read", { session: event.session });
  // finished parts never change, so a redelivered event reads the same answer
  const answer = parts.filter((p) => p.from === "agent" && p.kind === "message").map((p) => p.text).join("\n\n");
  await ctx.gateway.channel.publish({
    source: "sections",
    eventId: event.session,                         // redelivery files nothing new
    streamId: event.ref,
    occurredAt: event.endedAt,
    payload: { ref: event.ref, question: event.title, answer },
  });
  return {};
};
```

`host` sessions need no per-ticket consent, so the schedule runs unattended once the owner has
approved `agent_sessions` and both handlers. A fourth sub-question would be refused with
`AGENT_SESSION_LIMIT`; the realm starts it from `onEnded` when one of the first three ends. Nothing
in this realm changes when it moves to an installation that also has local agent tools.

## 10. Limits at a glance

| What | Proposed limit |
| --- | --- |
| `maxConcurrent` | 1 to 3 open sessions per ticket |
| Open sessions per installation | 12, the host's ceiling |
| Ended event delivery | retried for up to 24 hours |
| `ref` | 1 to 256 characters |
| `title` | 200 characters |
| `prompt`, `say` text | 64 KiB |
| `project` | 1 to 128 characters |
| `list` | 1 to 100 summaries, default 50 |
| `read` | 200 parts or 1 MiB per answer |
| `lastText` | 1,000 characters |

# TypeScript realms

A TypeScript realm is one `realm.ts` file that describes the whole realm as a typed object, plus
the handler code it runs. `defineRealm` from
[`@embabel/realm-types`](https://github.com/embabel-worlds/embabel-ts) checks the object while you
write it, and `realm-synth` from the same repository turns it into the files this specification
describes: `realm.yml`, `dist/manifest.json`, `producers/`, `channels/`, `apps/` and the rest.
The host never reads `realm.ts`. It reads what synth wrote.

This document covers realms written with `execution: "captured"`. A captured realm runs from a
verified copy the owner has admitted, and every capability it reaches is approved by the owner on
its own. For each part of a realm it shows what you write, what synth accepts and refuses, and
what the host does with it. The host-side detail lives in
[hosted execution](HOSTED_EXECUTION.md), and each section here links to its part of it.

The rules for a conventional realm (no `execution`, or `execution: "conventional"`) are the rest of
this specification. The two never mix: `triggers`, `queries`, `apps`, `credentials`, `dataPipes`,
`capturedLenses` and `watches` are refused on a conventional realm, and `goals`, `producers` and
`apis` take the captured forms described here once `execution` is `"captured"`.

## Contents

- [Build a realm](#build-a-realm)
- [Realm metadata](#realm-metadata)
- [Handlers](#handlers)
- [The handler context](#the-handler-context)
- [Credentials](#credentials)
- [APIs](#apis)
- [GraphQL](#graphql)
- [Channels](#channels)
- [Sources, consumers and triggers](#sources-consumers-and-triggers)
- [Publishing events](#publishing-events)
- [Dependencies](#dependencies)
- [Types](#types)
- [Producers](#producers)
- [Graph queries and view references](#graph-queries-and-view-references)
- [Goals](#goals)
- [Lenses and watches](#lenses-and-watches)
- [Apps](#apps)
- [Write proposals](#write-proposals)
- [Owner approval, step by step](#owner-approval-step-by-step)
- [Limits at a glance](#limits-at-a-glance)

## Build a realm

```bash
# Scaffold realm.ts, the handler file and the project files.
bun packages/realm-synth/src/cli.ts init my-realm --runtime typescript

# Write the specification files, and the handler types.
bun packages/realm-synth/src/cli.ts my-realm/realm.ts --out my-realm/dist \
  --types my-realm/.embabel/realm.d.ts

# Re-run on every change.
bun packages/realm-synth/src/cli.ts my-realm/realm.ts --out my-realm/dist --watch
```

Synth clears the output directory and writes it again on every run, so keep nothing by hand in
it. It sorts every key, so the same `realm.ts` always gives the same bytes. It refuses a value with no
file form: a function, a `Date`, a `BigInt`, a `Map` or `Set`, a non-finite number, a circular
reference, or a top-level `undefined`. It copies the handler entry, every file that entry
imports, dependency init scripts, the icon, app pages and app resources into the output, and
refuses any of them that resolves outside the realm directory.

What lands where:

| You write | Synth writes |
| --- | --- |
| `name`, `version`, `host`, `description`, `icon`, `tags`, `exports` | `realm.yml` |
| `handlers` | `dist/manifest.json` |
| `credentials` | `credentials.yml` |
| `apis` | `apis/apis.yml` and each vendored document under `apis/` |
| `channels`, `sources`, `consumers` | `channels/<name>.yml`, `sources/<name>.yml`, `consumers/<name>.yml` |
| `dataPipes` | `data-pipes.yml` |
| `triggers` | `triggers/<name>.yml` |
| `dependencies`, `layers`, a non-TypeScript `runtime` | `dependencies/manifest.json` |
| `types` | `types/<realm name>.yml` |
| `producers` | `producers/<name>.yml` |
| `queries` | `queries/references.yml` |
| `goals` | `goals/<name>.yml` |
| `capturedLenses` | `lenses/<name>.yml` |
| `watches` | `watches/<name>.yml` |
| `apps` | `apps/<page>.app.json`, the page and its resources |

Each captured directory (`goals/`, `triggers/`, `producers/`, `lenses/`, `watches/`) holds at most
32 files, 8 KiB each and 64 KiB together. The host refuses the whole directory past those limits,
so synth refuses first. Every captured file is stamped `version: 1`, and the name a file carries
comes from its key in `realm.ts`. You never write `version`, `name`, `goal`, `trigger` or `id`
yourself; the types make them compile errors.

Wrap the realm in `defineRealm`. It is what makes every `namespace.verb` you write elsewhere a
checked name: a lens, app, channel or consumer naming a handler the realm does not declare is a
compile error on the line that named it.

## Realm metadata

```typescript
import { defineRealm } from "@embabel/realm-types";

export default defineRealm({
  name: "oncall-radar",
  version: "0.1.0",
  host: "wasm",
  execution: "captured",
  description: "Open incidents on the status pages you depend on.",
  tags: ["status", "incidents"],
  handlers: { /* ... */ },
});
```

| Field | Rule |
| --- | --- |
| `name`, `version` | Required, non-empty. |
| `host` | `"wasm"` or `"docker"`. Declare `"wasm"` for a TypeScript realm. Left out, the host infers placement from the files on disk (see [placement](README.md#placement)), and a guess is the last thing a captured realm wants. |
| `execution` | `"captured"` switches synth to the captured profiles. It is not written to `realm.yml`; the host runs the realm captured once the owner admits it. |
| `runtime` | The guest language: `"typescript"` (the default), `"python"`, `"ruby"`, `"lua"` or `"compiled"`. TypeScript is the only one a host builds from source. A realm in any other language cannot declare channels, sources or consumers. |
| `entry` | The handler source file, relative to the realm. Defaults to `wasm/handlers.ts`. |
| `icon` | An `https://` URL, or a file in the realm that synth copies. |

## Handlers

A handler is a named verb in a namespace. Every other part of the realm names it as
`namespace.verb`.

```typescript
handlers: {
  incidents: {
    namespace: "oncall",
    description: "Unresolved incidents on one status page, a page at a time.",
    input: {
      type: "object",
      properties: { pageId: { type: "array", items: { type: "string" } }, cursor: { type: "string" } },
      required: ["pageId"],
    },
    output: { type: "object" },
  },
  sweep: { namespace: "oncall", schedule: "0 */15 * * * *" },
},
```

The code lives in the entry file as exported functions named after the verbs. The generated
types (`--types`) give each one its input, output and context:

```typescript
// wasm/handlers.ts
import type { IncidentsHandler } from "../.embabel/realm.d.ts";

export const incidents: IncidentsHandler = async (input, ctx) => {
  ctx.log(`fetching ${input.pageId.length} pages`);
  return { rows: [], next: null };
};
```

- The verb must be a JavaScript identifier. Two verbs whose generated aliases collide
  (`FooHandler`) are refused.
- `input` and `output` are JSON Schema fragments. Left out, each is `{"type": "object"}`. The
  host holds them to the [handler schema profile](README.md#me-captured-handler-schema-profile):
  a bounded subset of JSON Schema, checked before binding, with input validated before the
  handler runs and output validated before the result is released. `$ref`, `pattern`, `format`
  and `uniqueItems` refuse the binding.
- `schedule` is a six-field cron expression (second, minute, hour, day of month, month, day of
  week). A scheduled handler is called with `{}`, so its `input` may require nothing. A schedule
  may not sit on a type method, and may not also be declared with `defineSchedule` in the
  handler source.
- `onType` turns the handler into a method on a graph label. `className` is refused on a Wasm
  realm.
- Declaring a handler grants it nothing. The owner approves each handler at
  [admission](#owner-approval-step-by-step).

## The handler context

A handler is called as `handler(input, ctx)`. What `ctx` carries depends on how it was called.

| Member | Where | What it does |
| --- | --- | --- |
| `ctx.log(message)` | every handler | Writes one line to the host log under the realm's name. |
| `ctx.gateway.<api>.<operation>(args)` | every handler | Calls an approved API operation. The host attaches the owner's bound credential; the guest never sees it. See [APIs](#apis). |
| `ctx.gateway.cypher.query({cypher, params})` | every handler | Reads the owner's graph under the separate `cypher_query` approval. See [graph queries](#graph-queries-and-view-references). |
| `ctx.gateway.channel.publish(...)`, `.position(...)`, `.publishBatch(...)` | every handler | Files events on the realm's own sources. See [publishing events](#publishing-events). |
| `ctx.deps.<name>` | every handler, when dependencies are declared | A mounted dependency, such as SQLite. See [dependencies](#dependencies). |
| `ctx.writePropose(proposal)` | every handler | Files a write for the owner to accept. See [write proposals](#write-proposals). |
| `ctx.frame`, `ctx.cursor`, `ctx.publish(...)` | channel handlers | The frame that caused the dispatch, the cursor the last dispatch kept, and a publish shortcut. |
| `ctx.headers` | webhook handlers | The headers of the verified request. |
| `ctx.stream.send(text)`, `ctx.stream.close()` | websocket handlers | Writes to the channel's own socket, or asks the host to reconnect it. |
| `ctx.frame`, `ctx.publish(...)` | consumer handlers | The published event, and a publish shortcut. |
| `ctx.assistant.chat(text, thread)` | consumers that declared `assistant: true` | Asks the owner's assistant and resolves to its final message. |

Every host call answers with its result or rejects. A refusal carries one fixed message and never
says which rule failed, so treat it as "not allowed at the moment" and carry on. The assistant call is
the one exception: it rejects with a code, `ASSISTANT_NOT_GRANTED` or `SENDER_NOT_PAIRED`, so a
realm can answer with its own pairing hint.

```typescript
export const reply: ReplyConsumerHandler = async (event, ctx) => {
  try {
    const answer = await ctx.assistant.chat(String(event.text), String(event.chatId));
    await ctx.gateway.telegram.sendMessage({ body: { chat_id: event.chatId, text: answer } });
  } catch (e) {
    if (String(e.message).includes("SENDER_NOT_PAIRED")) {
      await ctx.gateway.telegram.sendMessage({
        body: { chat_id: event.chatId, text: "Ask the owner for a pairing code, then send: pair <code>" },
      });
    }
  }
  return {};
};
```

## Credentials

A realm says what it needs to authenticate and never what the secret is. The owner binds a real
secret to each declared credential when approving the realm.

```typescript
credentials: {
  bot: {
    kind: "bearer",
    scheme: "Bot",
    provider: "discord",
    description: "A bot token for the bot the assistant answers as.",
    docs: "https://discord.com/developers/applications",
  },
},
```

| Field | Rule |
| --- | --- |
| key | The credential id: `[a-z][a-z0-9-]{0,63}`. At most 32 credentials. |
| `kind` | `bearer`, `api-key`, `basic`, `oauth2` or `public-key`. |
| `description` | Required, at most 512 characters. The approval screen shows it to the owner. |
| `provider` | Optional, `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. |
| `docs` | Optional `https://` link, at most 512 characters. |
| `scheme` | `bearer` only: the word sent before the token in `Authorization`, 1 to 32 printable characters with no spaces. Defaults to `Bearer`. |
| `scopes` | `oauth2` only, and required there: 1 to 32 scopes. |

`value`, `env`, `tokenEnv` and `walletItem` are refused, so a realm cannot ship or point at a
secret. A credential nothing references is refused, since it would ask the owner for a secret no
call uses. An API entry, a channel, a webhook signature or a GraphQL source can reference one.
Binding, rotation and revocation are described under
[credentials](HOSTED_EXECUTION.md#credentials) in the hosted contract. An `oauth2` credential is
accepted in the declaration, and binding one is refused by the reference host.

## APIs

A captured API entry vendors one OpenAPI document and names exactly the operations the realm may
call.

```typescript
apis: {
  statuspage: {
    url: "statuspage.json",          // a file under apis/, vendored
    name: "statuspage",              // the gateway namespace
    type: "openapi",
    auth: "api-key",
    credential: "statuspage-key",
    headers: { "X-Client": "realm-oncall-radar" },
    operationIds: ["listUnresolvedIncidents"],
    writeOperationIds: ["acknowledgeIncident"],
  },
},
```

The generated gateway has one typed method per listed operation, and nothing else:
`ctx.gateway.statuspage.listUnresolvedIncidents({ page_id })`. A write takes its request body under
the reserved `body` argument, so an operation may not declare a parameter named `body`. The
response comes back as the parsed JSON body with no envelope.

What synth checks, which is also what the host refuses at install:

- At most 32 entries and 128 operations across them. `name` is
  `[A-Za-z_][A-Za-z0-9_-]{0,63}` and unique.
- `url` is a bare `*.json` filename under `apis/`, at most 1 MiB, OpenAPI 3.x, with every `$ref`
  pointing under `#/components/`.
- Exactly one of `credential` or `tokenEnv`. `tokenEnv` is deprecated and turned into an implicit
  credential with a warning.
- `operationIds` lists 1 to 128 reads, each a `GET` with no request body. `writeOperationIds`
  lists up to 64 writes, each a `POST`, `PUT`, `PATCH` or `DELETE`. An operation is in one list,
  never both, and every listed id must exist in the document.
- The document has exactly one `https` server on port 443, with no user info, query, fragment or
  server variables, and no per-path or per-operation server override.
- Parameters are inline `query` or `path` scalars, at most 64 per operation. A request body is
  `application/json` with an object schema.
- Security is exactly one scheme with no scopes. For `bearer` it is an `http` scheme whose word
  matches the credential's `scheme`. For `api-key` it names a header or query field, and the
  header may not be one the host owns (`Authorization`, `Cookie`, `Host`, `Content-Type` and the
  like).
- `auth: "path"` puts the credential in the URL: the document writes `{credential}` once, in the
  server URL or an operation path, and nowhere else. The generated client takes no argument for
  it.
- Up to 16 fixed `X-` headers with printable ASCII values.

Each operation is approved by the owner on its own, reads and writes under separate grants; see
[captured API operations](HOSTED_EXECUTION.md#captured-api-operations) for what the host does on
every call.

## GraphQL

`defineRealm` has no GraphQL field, and synth does not write `graphql/operations.yml`. The host
reads that file when it is present, following the
[captured GraphQL operation profile](HOSTED_EXECUTION.md#me-captured-graphql-operation-profile):
one fixed HTTPS endpoint, persisted query documents only, and variables checked against their
declaration. The source may name a declared credential with `credential:` in place of
`token-env:`; a query then sends the secret the owner bound to that credential, and is refused
while nothing is bound. A realm that needs GraphQL adds that file to the synthesized output
itself, after synth has run.

## Channels

A channel is a live connection the host holds for the realm. Declare channels with `connecting`,
which checks that every credential, channel and source a declaration names is declared right
beside it:

```typescript
import { connecting, defineRealm } from "@embabel/realm-types";

export default defineRealm({
  name: "telegram",
  version: "0.1.0",
  host: "wasm",
  execution: "captured",
  handlers: {
    updates: { namespace: "telegram" },
    reply: { namespace: "telegram" },
  },
  ...connecting({
    credentials: {
      bot: { kind: "bearer", description: "The bot token BotFather gave you." },
    },
    channels: {
      updates: {
        transport: "long-poll",
        url: "https://api.telegram.org/bot{credential}/getUpdates",
        credential: "bot",
        onResponse: "telegram.updates",
        every: "2s",
      },
    },
    sources: { messages: { channel: "updates", description: "Messages people send the bot." } },
    consumers: { "assistant-reply": { source: "messages", handler: "telegram.reply", assistant: true } },
  }),
});
```

Channel, source and consumer keys are file names: `[a-z][a-z0-9-]{0,63}`. The host owns
reconnects, budgets, limits, cursors and whether a channel starts, so `name`, `cursor`,
`reconnect`, `autoStart`, `limits`, `budget`, `secret` and `secretRef` are refused on all three.

**Websocket.** The host dials `url` (`wss://`) with the bound credential and hands every frame
to `onFrame`.

```typescript
socket: {
  transport: "websocket",
  url: "wss://gateway.example.com/?v=10",
  credential: "bot",
  onFrame: "example.gateway",
  keepalive: { every: "40s", handler: "example.heartbeat" },
  handshake: { operation: "apps.connectionsOpen", field: "url" },
},
```

- A frame is the provider's text, or a control frame: `{kind: "open"}`, `{kind: "keepalive"}`
  or `{kind: "close", reason}`, with `reason` one of `remote`, `rotation`, `budget`, `revoked`,
  `error` or `guest`. Binary frames are dropped and counted.
- `open` arrives on every real connection, so authenticate there each time.
- `keepalive.every` is between 10 seconds and 5 minutes. Only the keepalive handler gets the
  tick, and only while the socket is up.
- `handshake` is for a provider that hands out its socket URL from an API call. The host calls
  the named operation, reads `field` from the answer and connects there. The operation must be
  one the realm's `apis` allow.
- `ctx.stream.send(text)` writes a frame; write `{credential}` where the token belongs and the
  host substitutes it on the way out. `ctx.stream.close()` ends the connection once the handler
  returns; the next frames are a `close` with reason `guest` and then an `open`.

**Long-poll.** The host fetches `url` (`https://`) every `every` and hands the body to
`onResponse`.

- `every` is at least `1s` and defaults to `5s`. The operator's floor wins over what the realm
  declares, so a realm cannot poll faster than the host allows.
- The handler returns `{cursor, cursorParam}` to say where the next fetch starts: `cursor` is
  the value and `cursorParam` the query parameter it travels as. Return `cursorParam` on every
  response so a restart keeps it.
- A handler that throws leaves the cursor where it was, so the same batch is fetched again.
  Make the handler safe to run twice on one batch.
- The host keeps a cursor only if it carries no secret. A cursor or parameter name that spells
  the credential refuses the request.
- A 429 or 5xx waits out the backoff. A 401 or 403 stops the channel and tells the owner.

**Webhook.** The provider calls the host, which verifies the signature and hands the verified
body to `onRequest`. The host mints the receiving URL when the owner approves the channel, so a
webhook declares no `url`.

```typescript
intake: {
  transport: "webhook",
  onRequest: "intake.receive",
  signature: {
    scheme: "hmac-sha256",
    credential: "signing-secret",
    header: "X-Signature-256",
    prefix: "sha256=",
    encoding: "hex",
    template: "{timestamp}.{body}",
    timestamp: { header: "X-Timestamp", toleranceSeconds: 300 },
  },
  verification: { when: { field: "type", equals: "url_verification" }, reply: { echo: "challenge" } },
},
```

- `scheme` is `hmac-sha256` (needs `header`) or `ed25519` (needs `timestamp`). `encoding` is
  `hex` or `base64`. `template` may use only `{method}`, `{fullUrl}`, `{body}` and `{timestamp}`.
  `timestamp.unit` is `s` or `ms`.
- A request is dispatched only after its signature verifies. A changed body or a timestamp
  outside the window is refused before any handler runs.
- `verification` answers a provider's endpoint check without dispatching anything: when
  `when.field` equals `when.equals`, the host replies with the named field's value (`echo`) or a
  constant (`body`, at most 1 KiB of JSON). It applies only after the signature passes.

For every transport: the URL may carry `{credential}` at most once, and may not point at
`localhost` or a bare IP address; a channel pointed at an origin the operator has not allowed
refuses to start. Frame budgets, reconnect backoff and the credential rules on outbound bytes are
in [channels](HOSTED_EXECUTION.md#channels).

## Sources, consumers and triggers

A **source** is a named stream of events. It is what the owner grants and what a consumer reads.
There are two ways to declare one:

- `sources` in `connecting`, fed by one of the realm's channels:
  `{ channel: "updates", description: "..." }`. The description is required; the owner reads it
  when deciding.
- `dataPipes.sources`, a stream the realm's own handlers publish to:
  `{ stream: "events", type: "note.changed" }`. At most 128, each value at most 256 bytes.

A name may be declared one way or the other, never both.

A **consumer** is a handler that reads one source. Declare it in `connecting`
(`{ source, handler, assistant? }`) or in `dataPipes.consumers` (`{ handler }`). The consumer is
handed each event as its first argument and as `ctx.frame`, and the host checkpoints only after
the handler succeeds. Delivery is at least once, so give every effect its own idempotency key.
`assistant: true` asks for the separate grant that lets the consumer call `ctx.assistant.chat`;
the owner also pairs each sender the assistant may answer (see
[pairing](HOSTED_EXECUTION.md#pairing)).

A consumer may read another realm's source. The owner grants each consumer one exact source: a
host channel's source, a source from the same realm, or a source another installed realm
declares. The realm does not name the other realm; the owner picks the source at approval, and
the consumer receives whatever that source carries.

A **trigger** narrows what a consumer sees and says what it may do:

```typescript
dataPipes: {
  sources: { changes: { stream: "notes", type: "note.changed" } },
  consumers: { index: { handler: "notes.index" } },
},
triggers: {
  "on-change": { source: "changes", consumer: "index", mode: "observe", input: ["eventId", "payload"] },
},
```

- `source` and `consumer` name `dataPipes` declarations.
- `input` picks from `offset`, `eventId`, `streamId`, `type`, `occurredAt`, `gap` and `payload`;
  left out, the consumer gets all seven.
- `mode: "observe"` lets the handler read and refuses, for the whole invocation, every publish,
  every write proposal and every approved API write. `mode: "apply"` type-checks, and the host
  refuses it at bind time.
- One trigger naming a missing source, consumer or handler stops delivery to every consumer of
  that installation until it is fixed, so check trigger names with care. The full behaviour is in
  the [trigger profile](HOSTED_EXECUTION.md#me-captured-trigger-profile).

## Publishing events

A channel or consumer handler publishes with the shortcut on its context:

```typescript
export const updates: UpdatesResponseHandler = async (body, ctx) => {
  const batch = JSON.parse(String(body));
  let offset: number | undefined;
  for (const update of batch.result) {
    await ctx.publish("messages", { text: update.message.text, chatId: update.message.chat.id },
      String(update.update_id), { streamId: String(update.message.chat.id) });
    offset = update.update_id + 1;
  }
  return offset === undefined ? {} : { cursor: String(offset), cursorParam: "offset" };
};
```

`ctx.publish(source, event, key, options)` files `event` under one of the realm's own sources and
resolves to `{id, offset, replayed}`. `key` is the event id. The journal matches a retry on
source, key, stream and payload, so a frame the host redelivers gets the first receipt back
(`replayed: true`) and keeps the first `occurredAt`. The same event id with a different payload
is refused. Only the realm's declared source names compile.

Any handler can use `ctx.gateway.channel.publish({source, eventId, streamId, occurredAt, payload})`,
and a poller can commit a page and its cursor together with `position` and `publishBatch`. The
limits and retry windows are under [publication](HOSTED_EXECUTION.md#publication) and
[polling positions](HOSTED_EXECUTION.md#polling-positions).

## Dependencies

A dependency is a WebAssembly module the host mounts beside the handlers, from a registry the
operator curates.

```typescript
dependencies: {
  db: {
    module: "sqlite3-wasi",
    version: "3.50",
    sha256: "<64 lowercase hex characters>",
    persistent: true,
    init: "db/schema.sql",
  },
},
```

```typescript
export const addExpense: AddExpenseHandler = async (input, ctx) => {
  await ctx.deps.db.exec("INSERT INTO expenses (amount, note) VALUES (?, ?)", [input.amount, input.note]);
  const rows = await ctx.deps.db.exec("SELECT sum(amount) AS total FROM expenses");
  return { total: rows[0].total };
};
```

- The key becomes `ctx.deps.<key>`: a JavaScript identifier, and not `log` or `gateway`.
- `module` is a registry id, `version` an exact version such as `3.50`, and `sha256` the digest
  of the module's bytes. The host refuses a module the operator has not allowed, and one whose
  bytes do not hash to `sha256`. Either refusal takes every handler in the realm dark, including
  the ones that never touch the dependency. The reference host allows `sqlite3-wasi` and
  `h3-wasi`, at most eight dependencies, and modules up to 32 MiB.
- SQLite has one method, `exec(sql, params)`, which resolves to rows as plain objects. Bind
  values through `params` (strings, numbers or null). A `sqlite3-wasi` dependency may not declare
  `methods`.
- Any other module declares the `methods` it calls, each with numeric `args` and a `returns`
  type from `i32`, `i64`, `f32` and `f64`. An `i64` travels as a decimal string, since values
  such as an H3 cell id do not fit a JavaScript number. The operator's allowlist decides what a
  module may really do; a declared method the operator has not allowed refuses at call time.
- Without `persistent`, state lives for one dispatch and starts empty each time.
- With `persistent: true`, the host keeps one database for each world, realm and dependency. It
  restores the database at the start of a dispatch and saves it only when the dispatch succeeds
  and the output passes validation; a failed or refused dispatch leaves the stored rows as they
  were.
- `init` is a script, relative to the realm, run against empty state: once per dispatch for
  ephemeral state, or once when a persistent database is created. The host copies it from the
  admitted capture (at most 1 MiB), so editing the file later changes nothing for the admitted
  version.
- The host records the module, version, digest and init script's hash beside a persistent
  database. Change any of them and the host reports a mismatch and refuses to reuse the database.
  It neither wipes nor migrates it, and there is no migration step, so settle the schema before
  the first install that persists, and ship a changed schema under a new dependency key.
- The types accept `layers` (`name@version`), and the reference host refuses a realm that
  declares them, so leave them out.

## Types

`types` works as in a conventional realm (see [`types/`](README.md#types)) and synth writes it to
`types/<realm name>.yml`. A captured producer's `targetLabel` and a proposal's `target.label` are
graph labels; declare the types they name here so a query and a person can find them.

## Producers

A captured producer makes a graph label fetchable on demand by calling one of the realm's own
handlers.

```typescript
producers: {
  "incidents-by-service": {
    handler: "oncall.incidents",
    keyArgument: "serviceIds",
    joins: [
      { targetLabel: "Incident", anchorLabel: "Service", relationship: "HAS_INCIDENT",
        keyField: "serviceId", recordKeyField: "serviceId" },
    ],
    page: { argument: "cursor", maxPages: 4 },
    pushdown: [
      { property: "impact", argument: "impact" },
      { property: "status", argument: "status" },
    ],
  },
},
```

**The handler contract.** The handler receives an object holding the anchor keys as a list of
strings under `keyArgument`. Without `page`, it returns an array of record objects. Each record
carries its anchor's key under `recordKeyField`, which is how the host links it back. Records may
not supply `userId`, `worldId`, `workspaceId`, `visibleTo` or any property starting with `__vc`;
the host owns those.

```typescript
export const incidents: IncidentsHandler = async (input, ctx) => {
  const page = await ctx.gateway.statuspage.listIncidents({
    services: input.serviceIds.join(","),
    impact: input.impact?.join(","),   // present only when the query pinned impact
    status: input.status?.join(","),
    after: input.cursor,               // absent on the first page
  });
  return { rows: page.items, next: page.nextCursor ?? null };
};
```

**Joins.** 1 to 8 joins, each naming the label it produces (`targetLabel`), the stored label it
starts from (`anchorLabel`), the relationship, the anchor property whose values become keys
(`keyField`), and the record field carrying the key back (`recordKeyField`).

**Paging.** With `page`, the handler returns `{rows, next}`. The host calls it again with
`next` under `page.argument` until `next` is null or `maxPages` (1 to 16) is reached. A repeated
cursor, a cursor over 2048 bytes, or a non-null `next` on the last allowed page refuses the whole
fetch; the host never returns a truncated result. The details are in the
[paging profile](HOSTED_EXECUTION.md#me-captured-producer-paging-profile).

**Pushdown.** Each rule maps a record property to a handler argument. When a query pins the
property with `=` or `IN`, the handler receives the allowed values as a list of strings under
that argument, on every page. The graph applies every filter to the returned rows again, so
pushdown changes cost and never answers. **Declare a rule for every property your source can
filter on.** A filter left undeclared makes the handler fetch every record the key allows, and
the answer is identical, so nothing tells you it happened. Where the host shows query
diagnostics, they name the arguments that reached the handler on each call; a filter missing
from that list is the next rule to declare. See the [pushdown profile](HOSTED_EXECUTION.md#me-captured-producer-pushdown-profile).

**Arguments.** `keyArgument` and join fields are identifiers. `page.argument` and every pushdown
`argument` match `[a-z][A-Za-z0-9]{0,63}`, and no two of the key, page and pushdown arguments may
share a name. At most 16 pushdown rules. If the handler's input schema sets
`additionalProperties: false`, list the page and pushdown arguments in its `properties`, or the
host refuses the producer at bind time.

**Reaching a producer.** A query reaches the target label only by traversing one of its joins
from a bound anchor: a stored node pinned by a value or narrowed by a predicate. A bare
`MATCH (i:Incident)` is refused. A producer's target may anchor another producer's join, so
producers chain, and the engine stages each hop after the one before it. See
[Virtual Cypher §2](VIRTUAL_CYPHER.md#two-concepts-the-rest-of-the-spec-leans-on).

**Limits and scope.** Each fetch is at most 256 keys of up to 2048 characters, 64 KiB of
arguments, 1 MiB of output and 1,024 rows, across all pages together. Producer results are never
cached. Only producers from the querying handler's own installation run, each as a nested call
that needs that handler's grants as well as its own.

## Graph queries and view references

A handler reads the owner's graph with `ctx.gateway.cypher.query`:

```typescript
export const openBySeverity: OpenBySeverityHandler = async (input, ctx) => {
  const { rows } = await ctx.gateway.cypher.query({
    cypher: `MATCH (s:Service)-[:HAS_INCIDENT]->(i:Incident)
             WHERE s.team = $team AND i.impact IN $impacts
             RETURN s.name AS service, i.incidentId AS incident
             LIMIT 100`,
    params: { team: input.team, impacts: ["critical", "major"] },
  });
  return { rows };
};
```

- The owner approves `cypher_query` on its own. Approving a handler never grants it.
- It resolves to `{rows, warnings, coverage}`; `coverage` is empty in this profile.
- Pass every value through `params`. `userId`, `worldId`, `workspaceId` and names starting with
  `__` are refused as parameters.
- Give every node you bind a label and a variable name, and end the statement with a literal
  `LIMIT` from 1 to 512.
- Only nodes the owner owns outright are visible. Nodes shared with the owner, variable-length
  and named paths, list and pattern comprehensions, procedures, and functions outside a fixed
  list are refused. The list and the size limits are in the
  [graph-query profile](HOSTED_EXECUTION.md#me-captured-graph-query-profile).
- The query may cross into the realm's own producers, as above. Nothing a producer returns is
  kept.

A realm may also read the owner's own named views, under aliases the owner approves one at a
time:

```typescript
queries: {
  views: [{ alias: "services", view: "Services" }],
},
```

A statement may then write `MATCH (s:services)`; the host inlines the view in its place.
`alias` is `[a-z][a-z0-9_]{0,63}`, `view` is `[A-Za-z][A-Za-z0-9_]{0,63}`, and the list holds at
most 32 entries, each alias and each view once. A view that references another view, takes
parameters or is materialized is refused. See
[view references](HOSTED_EXECUTION.md#view-references).

## Goals

A goal lets the owner's planner reach a handler from chat.

```typescript
goals: {
  "whats-down": {
    handler: "oncall.open",
    input: "UserInput",
    output: "IncidentDigest",
    description: "Tells the owner what is down across the services they depend on.",
  },
},
```

The key is `[a-z][a-z0-9-]{0,63}`. `input` and `output` are type names (`[A-Z][A-Za-z0-9]{0,63}`);
`input` may be `UserInput`, which reaches the handler as `{"content": text}`, and `output` may
not. The host publishes the goal as `<key>_goal` and binds the handler's object result as the
output type. See the [goal profile](HOSTED_EXECUTION.md#me-captured-goal-profile).

## Lenses and watches

A captured lens is a view the owner opens, produced by one of the realm's handlers. A watch
re-reads a lens on a schedule and tells the owner about new items. Declare them together with
`watching`, so a watch can only name a lens declared beside it:

```typescript
import { defineRealm, watching } from "@embabel/realm-types";

export default defineRealm({
  // ...
  ...watching({
    capturedLenses: {
      open: { name: "Open incidents", handler: "oncall.open", description: "Every unresolved incident." },
    },
    watches: {
      "new-incident": {
        lens: "open",
        schedule: "0 */5 * * * *",
        criteria: "MATCH (i:Incident) WHERE i.status <> 'resolved' RETURN i",
        judge: "Say yes only for an incident that affects a component the owner's services use",
      },
    },
  }),
});
```

**Lenses.** Use `capturedLenses`; the conventional `lenses` field is refused on a captured realm.
The key is the lens id (`[a-z][a-z0-9-]{0,63}`), `name` is at most 128 characters and
`description` at most 512. `result` is `"json"` (the default, data only) or `"content"`, where the
handler returns `focus`, `data`, `presentation` and `complete`, and the owner's `cypher_query`
approval is needed too. See [captured handler binding](README.md#captured-handler-binding).

**Watches.** At most 16. The schedule is six-field cron and may fire at most once every five
minutes; synth walks the expression over a two-year window and refuses one that fires too
often or never. `criteria` is at most 2048 bytes and `judge`, when present, at most 1024. A watch
has no field for where results go: the host alone decides how the owner hears about them.

For a watch, the lens handler returns a top-level `items` array. The first run takes a baseline
and tells the owner nothing. A run may carry at most 32 items, 8 of them new, and deliver at most
4 to the owner; a run past any of these is refused whole, and the host does not trim it. A run's outcome is `BASELINED`, `DELIVERED`, `NOTHING_NEW`,
`REFUSED` or `FAILED`. What a watch has seen survives an approved upgrade; a changed capture takes
a fresh baseline. The owner approves each watch on its own, and approving a watch approves
nothing else.

## Apps

A captured app is an HTML page the owner opens, running in a sandboxed frame with no network.

```typescript
apps: {
  "incidents.html": {
    handlers: ["oncall.open", "oncall.acknowledge"],
    resources: ["apps/incidents.html.assets/app.css", "apps/incidents.html.assets/app.js"],
  },
},
```

- The key is the page's file name, `[A-Za-z0-9][A-Za-z0-9_.-]{0,119}` ending in `.html` or
  `.htm`, and synth copies `apps/<key>` from the realm. At most 32 apps.
- `handlers` lists what the page may call, each a declared `namespace.verb`, at most 32. It may
  be empty. Each listed handler still needs its own approval, and the owner approves the app
  itself separately.
- `resources` lists stylesheets and scripts from `apps/<key>.assets/`, `.css` or `.js` only, each
  listed once. The host inlines each one in its own `<style>` or `<script>` block ahead of the
  page. A stylesheet containing `</style` or a script containing `</script` is refused.
- The operator sets the size limits. The defaults are 10 MiB for the page, 16 resources, 10 MiB
  for any one resource and 10 MiB for all resources together.

Inside the page, `realm.call(handler, args)` calls a handler and resolves to its result:

```javascript
const incidents = await realm.call("oncall.open", {});
await realm.call("oncall.acknowledge", { incidentId: incidents.items[0].id });
```

- One call runs at a time. A second call made while one is waiting rejects straight away, so
  `await` each call before starting the next.
- A call gives up after about two minutes. Every refusal rejects with the same message.
- The page cannot fetch, open sockets, load remote scripts, styles, images or fonts, read the
  owner's cookies or storage, open popups or submit forms. Scripts may be inline and may use
  `eval`. Images and fonts work as `data:` or `blob:` URLs. Bundle everything at build time.
- If the page reloads or navigates its own frame, the bridge stops answering until the owner
  opens the app again.

The session, approval and revocation rules are under
[captured browser apps](HOSTED_EXECUTION.md#captured-browser-apps).

## Write proposals

A captured realm never writes to the owner's graph directly. It files a proposal, and the owner
accepts or rejects it.

```typescript
export const recordIncident: RecordIncidentHandler = async (input, ctx) => {
  const { proposalId } = await ctx.writePropose({
    version: 1,
    kind: "method-write-back",
    target: { label: "Service", key: input.serviceId },
    method: "noteIncident",
    fields: { incidentId: input.incidentId },
    effect: "private-storage",
  });
  return { proposalId };
};
```

- `kind` is `method-write-back` (with `method`) or `decoration` (no `method`; sets `fields`
  directly). `effect` is `private-storage` or `external`.
- `target.label` is a label the operator has opened to proposals, and `target.key` (at most 2048
  bytes) must name exactly one private record the owner already holds.
- `fields` has 1 to 64 entries in any one object, nests at most four levels, and may not use
  `userId`, `worldId`, `workspaceId`, `visibleTo`, `owner`, `ownerId`, `labels` or any name
  starting with `_`, at any depth. The generated types turn most of these rules into compile
  errors. The document is at most 64 KiB.
- `expectedRevision` (optional, a whole number) makes the write conditional on the record's
  current revision.
- The promise resolves to `{proposalId}` once the proposal is filed. It never tells the handler
  whether the owner accepted.

The owner's approval to propose is separate from reading the graph. Each installation holds at
most 32 pending proposals, and a restart discards them. Accepting applies the write under the
operator's policy: which properties a decoration may set, which methods a write-back may call
with which arguments, flat scalar values only, and `private-storage` only. The outcomes and
routes are in the [write proposal profile](HOSTED_EXECUTION.md#me-captured-write-proposal-profile).

## Owner approval, step by step

Installing a realm grants it nothing. Every capability is a separate owner approval, and every
approval names the installation revision the owner read; a stale revision answers 409 and
changes nothing. This is what the owner walks through, in order, and what each step unlocks. All
routes are under `/api/v1`.

| Step | Route | Unlocks |
| --- | --- | --- |
| 1. The operator turns the realm runtime on | host setting | Captured realms run at all. |
| 2. Install the realm | the host's install tools | The host loads it and takes a verified copy. |
| 3. Preview | `POST /handlers/realms/{realm}/admission/preview` with `{}` | Shows what the capture declares and its digest. |
| 4. Adopt | `POST /handlers/realms/{realm}/admission/adopt` with `{previewDigest, expectedRevision, handlers}` | Approves the ticked handlers and creates the installation. |
| 5. API operations | `/handlers/realms/{realm}/api-approvals/{operation}/grant` | Each read or write operation. |
| 6. Graph read and view aliases | `/realms/{realm}/resource-approvals/{resource}/grant` | `cypher_query`, and each view alias on its own. |
| 7. Credentials | `/channels/credentials/{realm}/{credential}/bind` | Binds a secret to a declared credential. Nothing that needs it starts before. |
| 8. Sources | `/channels/sources/{realm}/{source}/grant` | Publication to the source. |
| 9. Consumers | `/channels/consumers/{realm}/{consumer}/grant` | Delivery of one exact source to the consumer. |
| 10. Assistant and pairing | `/channels/consumers/{realm}/{consumer}/assistant/grant`, `/pairing` | `ctx.assistant.chat` for that consumer, and each paired sender. |
| 11. Channels | `/channels/captured/{realm}/{channel}/start` | The host opens the connection. A websocket handshake has its own grant. |
| 12. Apps | `/realm-browser/{realm}/approvals/{app}/grant` | The page at `/apps/{realm}/{app}`. |
| 13. Watches | `/realms/{realm}/watch-approvals/{watch}/grant` | Scheduled runs; `/realms/{realm}/watches/{watch}/check-now` runs one on demand. |
| 14. Write proposals | through admission, with the other resources | `ctx.writePropose`; decisions at `/realms/{realm}/proposals`. |

Upgrading (`POST /handlers/realms/{realm}/admission/upgrade`) admits a new capture and keeps the
approvals it still asks for. Every approval, upgrade and revocation moves the installation to a
new revision, and an invocation keeps the authority it started with: a newer approval never
widens a call already running, and a revocation stops the next host call. Revoking the
installation (`.../admission/revoke`) closes its channels and makes its pending proposals
unusable.

## Limits at a glance

| What | Limit |
| --- | --- |
| Files per captured directory | 32, 8 KiB each, 64 KiB together |
| Credentials | 32 |
| API entries / operations | 32 / 128; 64 writes; 64 parameters per operation; 1 MiB per document |
| Data-pipe sources, consumers | 128 each |
| Websocket keepalive | 10 seconds to 5 minutes |
| Long-poll interval | at least 1 second, and never below the operator's floor |
| Webhook verification reply | 1 KiB |
| Dependencies | 8 on the reference host; modules up to 32 MiB; init script up to 1 MiB |
| Producer joins / pushdown rules / pages | 8 / 16 / 16 |
| Producer fetch | 256 keys, 64 KiB arguments, 1 MiB output, 1,024 rows |
| Graph query | 16 KiB statement, 128 parameters, `LIMIT` 1 to 512, 1 MiB of rows |
| View aliases | 32 |
| Watches | 16; at least 5 minutes apart; 32 items per run |
| Apps | 32 apps, 32 handlers each; defaults of 10 MiB page, 16 resources, 10 MiB per resource and in total |
| Write proposals | 64 KiB, 64 entries per object, 4 levels, 32 pending per installation |

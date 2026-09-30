# TypeScript realms

A TypeScript realm is one `realm.ts` file that describes the whole realm as a typed object, plus
the handler code it runs. `defineRealm` from
[`@embabel/realm-types`](https://github.com/embabel-worlds/embabel-ts) checks the object while you
write it, and `realm-synth` from the same repository turns it into the files this specification
describes: `realm.yml`, `dist/manifest.json`, `producers/`, `channels/`, `apps/` and the rest.
It also writes the TypeScript types the handlers import. The host never reads `realm.ts`. It reads
what synth wrote.

This document covers realms written with `execution: "captured"`. A captured realm runs from a
verified copy the owner has admitted, and every capability it reaches is approved by the owner on
its own. For each part of a realm it shows what you write, what synth accepts and refuses, and
what the host does with it. The host-side detail lives in
[hosted execution](HOSTED_EXECUTION.md), and each section here links to its part of it.

The rules for a conventional realm (no `execution`, or `execution: "conventional"`) are the rest of
this specification. The two never mix: `triggers`, `queries`, `apps`, `credentials`, `dataPipes`,
`capturedLenses`, `watches` and `graphql` are refused on a conventional realm, and `goals`,
`producers`, `apis` and `channels` take the captured forms described here once `execution` is
`"captured"`.

Most examples below come from one realm, `oncall-radar`, which reads a status page API and tells
the owner what is down. Channels, dependencies and data pipes use small realms of their own.

## Contents

- [Build a realm](#build-a-realm)
- [App limits and profiles](#app-limits-and-profiles)
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

Run synth from a checkout of the embabel-ts repository:

```bash
# Scaffold package.json, tsconfig.json, README.md, realm.ts and the handler file.
bun packages/realm-synth/src/cli.ts init my-realm --runtime typescript

# Write the specification files, and the handler types.
bun packages/realm-synth/src/cli.ts my-realm/realm.ts --out my-realm/dist \
  --types my-realm/.embabel/realm.d.ts

# Re-run on every change.
bun packages/realm-synth/src/cli.ts my-realm/realm.ts --out my-realm/dist \
  --types my-realm/.embabel/realm.d.ts --watch
```

- `init <dir>` refuses a directory that is not empty. `--runtime` is `typescript` (the default),
  `python` or `compiled`. The scaffolded `realm.ts` is a conventional realm written with
  `satisfies Realm`. For a captured realm, add `execution: "captured"` and wrap the object in
  `defineRealm`.
- With neither `--out` nor `--types`, synth prints every file it would write and writes nothing.
- `--types` picks its language from the realm's `runtime`: a `.d.ts` or `.ts` path for
  TypeScript, `.py` or `.pyi` for Python, and `.rs` for `compiled`. Any other pairing is refused.
  There is no types emitter for `ruby` or `lua`.
- `--watch` rebuilds in a fresh process on every change under the definition's directory. It
  ignores `.embabel/`, `dist/`, `node_modules/`, dotfiles, the `--out` directory and the
  `--types` file. A failed rebuild prints its message and keeps watching.
- `--profile` and the `--app-*` flags are described under
  [app limits and profiles](#app-limits-and-profiles).
- A refusal prints `synth failed: <message>` and exits with status 1. A usage error prints the
  reason and the usage text and exits with status 2. Usage errors are an unknown flag, a flag
  with no value, a second definition file, a size or count synth cannot read, an unknown
  profile name, and a profile file that is missing, is not JSON or does not follow the profile
  format.
- A flag that takes a value always takes the next argument, whatever it looks like: `--out
  --types` writes to a directory named `--types`. The one argument that is not a flag or a flag's
  value is the definition file.
- Warnings, such as a deprecated `tokenEnv`, an undeclared goal type or a feature the chosen
  profile does not load, go to standard error and do not stop the build.

Synth clears the output directory and writes it again on every run, so keep nothing by hand in
it. It sorts every key, so the same `realm.ts` always gives the same bytes. It refuses a value
with no file form: a function, a symbol, a `Date`, a `BigInt`, a `Map` or `Set`, a non-finite
number, a circular reference, or `undefined` in an array. An object key whose value is
`undefined` is left out. The text fields of goals, triggers, producers, lenses, watches, data
pipes, view references, apps, credentials and API entries refuse control characters, a newline
included, and unpaired surrogates.

Synth copies the handler entry, every file the entry reaches through a relative value import
(type-only imports are skipped), dependency init scripts, a file-path icon, app pages and app
resources into the output. It refuses any of them that is missing or that resolves outside the
realm directory, including through a symlink, and it refuses a copy or a vendored document that
would land on a path it already writes.

What lands where:

| You write | Synth writes |
| --- | --- |
| `name`, `version`, `host`, `description`, `author`, `url`, `icon`, `tags`, `exports`, `retry` | `realm.yml` |
| `handlers`, `entry`, `generatedAt` | `dist/manifest.json` |
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
| `actions`, `focuses`, `webhooks`, `events` | `actions/<name>.yml`, `focuses/<name>.yml`, `webhooks/<realm name>.yml`, `events/<name>.yml` |

The last row is the conventional form of those fields, and synth writes it for a captured realm
as well. With admission on, the reference host does not load a captured realm's
`actions/`, `events/` or `webhooks/`, and reports each of those kinds once as a loading problem
(see the [goal profile](HOSTED_EXECUTION.md#me-captured-goal-profile) and
[legacy event declarations](HOSTED_EXECUTION.md#legacy-event-declarations)). Leave them out.
`--profile reference-wasm` warns about each one.

Each captured directory (`goals/`, `triggers/`, `producers/`, `lenses/`, `watches/`) holds at most
32 files, 8 KiB each and 64 KiB together. The host refuses the whole directory past those limits,
so synth refuses first. Every captured file is stamped `version: 1`, and the name a file carries
comes from its key in `realm.ts`: `goal` in a goal, `trigger` in a trigger, `name` in a producer
or watch, `id` in a lens. You never write `version`, `name`, `goal`, `trigger` or `id` yourself;
the types make them compile errors, and synth writes its own values over them.

Wrap the realm in `defineRealm`. It is what makes every `namespace.verb` you write elsewhere a
checked name. Under `defineRealm`, a goal, producer or `dataPipes` consumer naming a handler the
realm does not declare is a compile error on that line. A lens declared through `watching`, or a
channel or consumer declared through `connecting`, is checked too; that error is reported on the
`defineRealm` argument and names the allowed handlers. An app's `handlers` list is not checked at
compile time. Written with `satisfies Realm`, none of these names are checked by the compiler.

Synth checks every one of these names as well, whichever way the realm is written. It refuses a
goal, producer, `dataPipes` consumer, lens, channel, keepalive, `connecting` consumer or app that
names a handler the realm does not declare, since the host dispatches only to handlers the
realm's manifest registers. A realm with no `handlers` block declares no handlers, so any handler
name anywhere in it is refused.

## App limits and profiles

A captured browser app is held to size limits (see [apps](#apps)). The defaults are 10 MiB for the
page, 10 MiB for any one resource, 10 MiB for all of one app's resources together, and 16
resources. They match what the reference host runs with out of the box. The host operator sets
the host's own limits, and a host with larger ones takes larger apps, so each limit synth
applies can be raised or lowered:

```bash
bun packages/realm-synth/src/cli.ts realm.ts --out dist --app-limit 32MiB
```

| Flag | Sets |
| --- | --- |
| `--app-limit <size>` | The page, per-resource and total byte limits together. |
| `--app-page-limit <size>` | The page. |
| `--app-resource-limit <size>` | Any one resource. |
| `--app-total-limit <size>` | All of one app's resources together. |
| `--app-resource-count <n>` | How many resources one app may list. |

- A size is a whole number of bytes, or a whole number with a unit: `K`, `KB` or `KiB`, `M`, `MB`
  or `MiB`, `G`, `GB` or `GiB`, in any letter case. Every unit is binary, so `32MB` and `32MiB`
  are both 33,554,432 bytes. A size or count comes to at least 1, and there is no upper cap.
- A per-limit flag wins over `--app-limit`.
- A refusal names the limit it hit and the flag that raises it.
- Raising a limit in synth does not raise the host's. An app over the host's limits is still
  refused when the owner opens it.

A realm can run in more than one execution environment, and they do not all load the same things.
`--profile` checks the realm against one of them:

```bash
bun packages/realm-synth/src/cli.ts realm.ts --out dist --profile reference-wasm
bun packages/realm-synth/src/cli.ts realm.ts --out dist --profile ./my-host.json
```

A profile only adds warnings and refusals, and may carry its own app limits. Synth writes every
file the realm declares whether a profile is given or not. A feature the profile marks `warn`
prints one warning, starting `PROFILE <name>:` and naming each place the realm uses it, and the
build carries on. A feature marked `refuse` stops the build with every place it is used. A
feature left out of the profile is supported.

The two built-in profiles describe the reference host running handlers under Wasm and under
Docker. They have the same rules and no app limits of their own:

| Feature id | What it finds | `reference-wasm`, `reference-docker` |
| --- | --- | --- |
| `layers` | A non-empty `layers` list | refuse |
| `captured-actions` | `actions` on a captured realm | warn |
| `captured-events` | `events` on a captured realm | warn |
| `captured-webhooks` | `webhooks` on a captured realm | warn |
| `captured-focuses` | `focuses` on a captured realm | supported |

Any other environment is described in a JSON file whose path ends in `.json`:

```json
{
  "name": "my-host",
  "features": { "layers": "supported", "captured-actions": "refuse" },
  "appLimits": { "pageBytes": 67108864 }
}
```

| Field | Rule |
| --- | --- |
| `name` | Required, not blank. Messages name the profile by it. |
| `description` | Optional text. |
| `features` | Optional. Maps a feature id from the table above to `"supported"`, `"warn"` or `"refuse"`. |
| `appLimits` | Optional. Any of `pageBytes`, `resourceBytes`, `resourcesTotalBytes` and `resourcesPerApp`, each a whole number of at least 1. |

An unknown field, feature id or limit is refused, so a typo cannot turn a check off. The app limits
a build uses come from the defaults, then the profile's `appLimits`, then the flags, and each
later one wins.

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
  handlers: {
    /* ... */
  },
});
```

| Field | Rule |
| --- | --- |
| `name`, `version` | Required, non-empty. |
| `host` | `"wasm"` or `"docker"`, written to `realm.yml` only when present. Declare `"wasm"` for a TypeScript realm. Left out, the host infers placement from the files on disk (see [placement](README.md#placement)), and a guess is the last thing a captured realm wants. |
| `execution` | `"captured"` switches synth to the captured profiles. It is not written to `realm.yml`; the host runs the realm captured once the owner admits it. |
| `runtime` | The guest language: `"typescript"` (the default), `"python"`, `"ruby"`, `"lua"` or `"compiled"`. TypeScript is the only one a host builds from source. Any other value is written to `dependencies/manifest.json`. A realm in any other language cannot declare channels, sources or consumers. |
| `entry` | The handler source file, relative to the realm, with no leading `/`, no `\` and no `..` segment. Defaults to `wasm/handlers.ts`, or `wasm/handlers.py` for Python and `wasm/src/lib.rs` for `compiled`. A declared entry must exist and is also written to `dist/manifest.json`. |
| `icon` | A URL starting `http://` or `https://`, written as is, or a realm-relative file, which must exist and which synth copies. |
| `description`, `author`, `url`, `tags`, `exports`, `retry` | Written to `realm.yml`. `tags` and `exports` are written only when non-empty. |
| `generatedAt` | The timestamp in `dist/manifest.json`. Defaults to `1970-01-01T00:00:00Z`, so the output does not change from run to run. |

## Handlers

A handler is a named verb in a namespace. Every other part of the realm names it as
`namespace.verb`.

```typescript
handlers: {
  incidents: {
    namespace: "oncall",
    description: "Unresolved incidents for a batch of services, a page at a time.",
    input: {
      type: "object",
      properties: {
        serviceIds: { type: "array", items: { type: "string" } },
        cursor: { type: "string" },
        impact: { type: "array", items: { type: "string" } },
        status: { type: "array", items: { type: "string" } },
      },
      required: ["serviceIds"],
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
import type { SweepHandler } from "../.embabel/realm.d.ts";

export const sweep: SweepHandler = async (_input, ctx) => {
  ctx.log("sweeping status pages");
  return {};
};
```

- The verb must be a JavaScript identifier. Two verbs whose generated aliases collide
  (`FooHandler`) are refused.
- `input` and `output` are JSON Schema fragments. Left out, each is `{"type": "object"}` in the
  manifest. The host holds them to the
  [handler schema profile](README.md#me-captured-handler-schema-profile): a bounded subset of JSON
  Schema, checked before binding, with input validated before the handler runs and output
  validated before the result is released. `$ref`, `pattern`, `format` and `uniqueItems` refuse
  the binding.
- The generated types name each verb three times: `<Verb>Input`, `<Verb>Output` and
  `<Verb>Handler`, where `<Verb>` is the verb with its first letter upper-cased. An input schema
  with no properties types as `Record<string, never>`, and an output schema with no properties as
  `unknown`. `<Verb>Handler` is `(input, ctx: HandlerContext) => Promise<Output>`.
- `schedule` is a six-field cron expression (second, minute, hour, day of month, month, day of
  week). A scheduled handler is called with `{}`, so its `input` may list no `required` field. A
  schedule may not sit on a handler with `onType`, and may not also be declared with
  `defineSchedule("<verb>", ...)` in a TypeScript entry.
- `onType` turns the handler into a method on a graph label, and may not be blank. `className`
  names the class the sandbox instantiates for that method: it needs `onType`, may not be blank,
  and is refused when `host` is `"wasm"`.
- Declaring a handler grants it nothing. The owner approves each handler at
  [admission](#owner-approval-step-by-step).

## The handler context

A handler is called as `handler(input, ctx)`. What `ctx` carries depends on how it was called, and
the generated types say which members each handler gets.

| Member | Where | What it does |
| --- | --- | --- |
| `ctx.log(message)` | every handler | Writes one line to the host log under the realm's name. |
| `ctx.gateway.<api>.<operation>(args)` | every handler | Calls an approved API operation. The host attaches the owner's bound credential; the guest never sees it. See [APIs](#apis). |
| `ctx.gateway.<graphql name>.<operation>({variables})` | every handler | Runs one of the realm's persisted GraphQL queries. See [GraphQL](#graphql). |
| `ctx.gateway.cypher.query({cypher, params})` | every handler | Reads the owner's graph under the separate `cypher_query` approval. See [graph queries](#graph-queries-and-view-references). |
| `ctx.gateway.channel.publish(...)`, `.position(...)`, `.publishBatch(...)` | every handler | Files events on the realm's own sources. See [publishing events](#publishing-events). |
| `ctx.deps.<name>` | every handler, when dependencies are declared | A mounted dependency, such as SQLite. See [dependencies](#dependencies). |
| `ctx.writePropose(proposal)` | every handler | Files a write for the owner to accept. See [write proposals](#write-proposals). |
| `ctx.frame`, `ctx.cursor`, `ctx.publish(...)` | channel handlers | The frame that caused the dispatch, the cursor the last dispatch kept, and a publish shortcut. |
| `ctx.headers` | webhook handlers | The headers of the verified request. |
| `ctx.stream.send(text)`, `ctx.stream.close()` | websocket handlers | Writes to the channel's own socket, or asks the host to reconnect it. |
| `ctx.frame`, `ctx.cursor`, `ctx.publish(...)` | consumers declared in `connecting` | The published event, the consumer's cursor, and a publish shortcut. |
| `ctx.assistant.chat(text, thread)` | consumers that declared `assistant: true` | Asks the owner's assistant and resolves to its final message. |

The generated `ctx.gateway` types each API namespace and the GraphQL namespace the realm
declares, and `ctx.gateway.channel` with the receipts the host returns (see
[publishing events](#publishing-events)). Every other namespace, `cypher` included, is typed
`unknown`, so a handler that calls one gives it a type of its own; the
[graph queries](#graph-queries-and-view-references) section shows one.

A channel or consumer handler has an alias of its own, named after the verb it points at:

| Declared as | Alias | Called as | Resolves to |
| --- | --- | --- | --- |
| websocket `onFrame` or `keepalive.handler` | `<Verb>FrameHandler` | `(frame, ctx: ChannelCtx & StreamCtx)` | `{cursor?}` |
| long-poll `onResponse` | `<Verb>ResponseHandler` | `(frame, ctx: ChannelCtx)` | `{cursor?, cursorParam?}` |
| webhook `onRequest` | `<Verb>RequestHandler` | `(frame, ctx: ChannelCtx & RequestCtx)` | `{cursor?}` |
| `connecting` consumer | `<Verb>ConsumerHandler` | `(event, ctx: HandlerContext & ConsumerCtx)`, plus `AssistantCtx` with `assistant: true` | a JSON object |

A frame is the provider's text or a control frame (`Frame`). Only the handler a channel names as
its `keepalive.handler` is typed to receive the keepalive tick; every other channel handler gets
`FrameWithoutKeepalive`. Two channels or consumers pointing at one verb share its alias, and synth
refuses them when they would need different ones. A `dataPipes` consumer gets the plain
`<Verb>Handler` and `HandlerContext`. The generated names may not collide with a type the realm
declares, so synth refuses a type named `RealmTypes`, `HandlerContext`, `Handlers` or
`WriteProposal`, and, in a realm with channels or consumers, `Frame` and the other channel
declarations.

Every `ctx.gateway.<namespace>.<operation>` call and `ctx.writePropose` returns a promise, which
resolves to the result or rejects. A refusal carries one fixed message and never says which rule
failed, so treat it as "not allowed at the moment" and carry on. The assistant call is the one
exception: it rejects with an `AssistantRefusal`, an `Error` whose `code` is
`ASSISTANT_NOT_GRANTED` (the consumer has no assistant grant) or `SENDER_NOT_PAIRED` (the owner
has not paired this sender), so a realm can answer with its own pairing hint. The code is a
property of the error and never part of its message. A refusal that gives no reason has no
`code`. The generated types export `AssistantRefusal` and `AssistantRefusalCode` for a realm that
declares channels or consumers.

```typescript
import type { AssistantRefusal, ReplyConsumerHandler } from "../.embabel/realm.d.ts";

export const reply: ReplyConsumerHandler = async (event, ctx) => {
  const chatId = String(event.chatId);
  try {
    const answer = await ctx.assistant.chat(String(event.text), chatId);
    await ctx.gateway.telegram.sendMessage({ body: { chat_id: chatId, text: answer } });
  } catch (e) {
    if ((e as AssistantRefusal).code === "SENDER_NOT_PAIRED") {
      await ctx.gateway.telegram.sendMessage({
        body: { chat_id: chatId, text: "Ask the owner for a pairing code, then send: pair <code>" },
      });
    }
  }
  return {};
};
```

## Credentials

A captured realm says what it needs to authenticate and never what the secret is. The owner binds
a real secret to each declared credential when approving the realm. This is the recommended way
for any new realm to ask for a secret.

A conventional realm asks for its keys another way, with [`keys.yml`](README.md#keysyml--the-keys-a-realm-needs)
entries that name the variable a key is stored under. Both declarations work, and each applies
to its own kind of realm; [keys and declared credentials](README.md#keys-and-declared-credentials)
says which applies where and what happens when both name one secret.

```typescript
credentials: {
  "statuspage-key": {
    kind: "api-key",
    provider: "statuspage",
    description: "An API key for the status page account the radar reads.",
    docs: "https://developer.statuspage.io",
  },
},
```

A bearer credential whose provider wants a word other than `Bearer` in front of the token names
it with `scheme`. A Discord bot token is sent as `Bot <token>`:

```typescript
bot: {
  kind: "bearer",
  scheme: "Bot",
  provider: "discord",
  description: "A bot token for the bot the assistant answers as.",
  docs: "https://discord.com/developers/applications",
},
```

| Field | Rule |
| --- | --- |
| key | The credential id: `[a-z][a-z0-9-]{0,63}`. At most 32 credentials. |
| `kind` | `bearer`, `api-key`, `basic`, `oauth2` or `public-key`. |
| `description` | Required, at most 512 characters. The approval screen shows it to the owner. |
| `provider` | Optional, `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. |
| `docs` | Optional `https://` link, at most 512 characters. |
| `scheme` | `bearer` only: the word sent before the token in `Authorization`, 1 to 32 printable ASCII characters with no spaces. Defaults to `Bearer`, which is not written to the file. |
| `scopes` | `oauth2` only, and required there: 1 to 32 distinct scopes, each at most 128 characters. |

`value`, `env`, `tokenEnv` and `walletItem` are refused, so a captured realm cannot ship or point
at a secret, and so is any other field not in the table. A credential nothing references is
refused, since it would ask the owner for a secret no call uses. Synth counts a reference from an
API entry's `credential` (or its deprecated `tokenEnv`), a channel's `credential`, a webhook
signature's `credential` and the [GraphQL](#graphql) source's `credential`. `credentials.yml` lists the credentials sorted by id. Binding, rotation
and revocation are described under [credentials](HOSTED_EXECUTION.md#credentials) in the hosted
contract. An `oauth2` credential is accepted in the declaration, and binding one is refused by
the reference host.

## APIs

A captured API entry vendors one OpenAPI document and names exactly the operations the realm may
call.

```typescript
apis: {
  statuspage: {
    url: "statuspage.json", // a file under apis/, vendored
    name: "statuspage", // the gateway namespace
    type: "openapi",
    auth: "api-key",
    credential: "statuspage-key",
    headers: { "X-Client": "realm-oncall-radar" },
    operationIds: ["listUnresolvedIncidents", "listIncidents"],
    writeOperationIds: ["acknowledgeIncident"],
  },
},
```

The generated gateway has one method per listed operation under `ctx.gateway.<name>`. A read takes
an untyped arguments object: `ctx.gateway.statuspage.listIncidents({ services })`. A write takes
an arguments interface built from the vendored document, holding its path and query parameters
and its request body under the reserved `body` argument, and a field the operation does not
declare is a compile error:

```typescript
await ctx.gateway.statuspage.acknowledgeIncident({
  incidentId: input.incidentId,
  body: { note: "Seen by the on-call radar" },
});
```

A write whose parameters or body synth cannot read from the document falls back to the untyped
arguments object, with a comment in the generated file saying why. An operation may not declare a
parameter named `body`. Every call resolves to `unknown`: the response comes back as the parsed
JSON body with no envelope, so narrow it before use.

What synth checks, which is also what the host refuses at install:

- At most 32 entries and 128 operations across them. The entry's key is a JavaScript identifier.
  `name` is `[A-Za-z_][A-Za-z0-9_-]{0,63}` and unique. Two operations may share an id in
  different namespaces, and are refused when their qualified names collide
  (`<name>.<id>`, `<name>_<id>`, or the two camel-cased and joined with `_`).
- `url` is a bare filename, `[A-Za-z0-9_-]+\.json`, under `apis/`, at most 1 MiB, OpenAPI 3.x,
  with every `$ref` pointing under `#/components/`, at most 256 paths, and each operation id
  declared once. `apis/apis.yml` is at most 64 KiB.
- Exactly one of `credential` or `tokenEnv`, and a `credential` must be declared in
  `credentials`. `tokenEnv` is deprecated in favour of a declared credential: it matches
  `[A-Za-z_][A-Za-z0-9_]{0,127}`, may not start with `__embabel_sql_v1__`, and becomes an
  implicit credential, with a warning. The implicit credential's id is the variable name spelled
  as written, which the declared-id pattern does not cover; the host reads a credential id in
  either spelling (see [credentials and databases](HOSTED_EXECUTION.md#credentials-and-databases)).
  Two entries reading one `tokenEnv` must declare the same `auth`. `apis.yml` always carries
  `credential:`, and `token-env:` beside it on the deprecated path. An `auth: "path"` entry
  cannot use `tokenEnv`.
- `operationIds` lists 1 to 128 reads, each a `GET` with no request body. `writeOperationIds`
  lists up to 64 writes, each a `POST`, `PUT`, `PATCH` or `DELETE`. An operation is in one list,
  never both, and every listed id must exist in the document.
- The document has exactly one `https` server on port 443, with no user info, query, fragment,
  server variables, percent-encoded path, `.` or `..` segment or `{` placeholder (other than
  `{credential}` under `auth: "path"`), and no per-path or per-operation server override.
- An operation path matches `^/[A-Za-z0-9_~./{}-]*$` with no `.` or `..` segment. Parameters are
  declared inline, in `query` or `path`, with a `string`, `integer`, `number` or `boolean`
  schema: at most 64 per operation, named `[A-Za-z_][A-Za-z0-9_-]{0,63}`, none repeated across
  the path item and the operation. A path parameter is `required`, and the path's placeholders
  and its path parameters match exactly. An `enum` holds at most 128 non-null scalars, and
  `minLength` and `maxLength` are whole numbers from 0 to 2048.
- A request body holds only `content`, with one media type, `application/json`, whose `schema`
  is an object.
- Security is exactly one requirement naming one scheme, with no scopes. For `bearer` it is an
  `http` scheme whose word matches the credential's `scheme`. For `api-key` it is an `apiKey`
  scheme in a header or the query, named `[A-Za-z][A-Za-z0-9-]{0,127}`, and the header may not
  be one the host owns (`Authorization`, `Cookie`, `Host`, `Content-Type` and the like). The
  field the credential travels in may not also be a fixed header or a parameter.
- `auth: "path"` puts the credential in the URL and needs `credential`. The document writes
  `{credential}` in the server URL or in the path of a declared operation, so that each declared
  operation's full URL carries it exactly once, in the path, never in a query string. `security`
  is absent or empty, and no operation takes a `credential` parameter. The generated client takes
  no argument for it.
- Up to 16 fixed headers, each named `X-...` and holding at most 1,024 printable ASCII
  characters, with no `${` substitution. Two header names that differ only in case are refused.

Each operation is approved by the owner on its own, reads and writes under separate grants; see
[captured API operations](HOSTED_EXECUTION.md#captured-api-operations) for what the host does on
every call.

## GraphQL

A captured realm may declare one GraphQL source with `graphql`: one fixed HTTPS endpoint and a
fixed set of persisted queries. Synth writes it to `graphql/operations.yml`, the only path the
host reads.

```typescript
credentials: {
  "catalog-token": { kind: "bearer", description: "A read token for the product catalog." },
},
graphql: {
  name: "catalog",
  endpoint: "https://api.example.com/graphql",
  auth: "bearer",
  credential: "catalog-token",
  operations: {
    productById: {
      document: "query($id: ID!) { product(id: $id) { name price } }",
      variables: [{ name: "id", type: "string", required: true, maxLength: 64 }],
    },
  },
},
```

A handler calls each operation under the source's `name`, passing only `variables`, and gets back
the response's `data` member:

```typescript
import type { ProductHandler } from "../.embabel/realm.d.ts";

interface ProductData {
  product: { name: string; price: number } | null;
}

export const product: ProductHandler = async (input, ctx) => {
  const data = (await ctx.gateway.catalog.productById({
    variables: { id: input.id },
  })) as ProductData;
  return { product: data.product };
};
```

The generated types give each operation an argument typed from its declared variables. A
required variable is a required field, an optional one may be left out or `null`, an `enum`
becomes a union of its values, and a variable the operation does not declare is a compile
error. An operation with no variables takes no argument, or `{}`. The result is `unknown`, so
narrow it before use.

| Field | Rule |
| --- | --- |
| `name` | The gateway namespace: `[A-Za-z_][A-Za-z0-9_-]{0,63}`. |
| `endpoint` | One fixed `https://` origin on the default port, with no user info, query, fragment, `.` or `..` segment, percent-encoded path or `{` placeholder. |
| `credential` | A credential the realm declares under `credentials`. Naming it here counts as a reference. |
| `auth` | `"bearer"`, sent in `Authorization`, or `"api-key"`, which needs `header`. |
| `header` | `"api-key"` only: the header the key travels in, `[A-Za-z][A-Za-z0-9-]{0,127}`, and not one the host sets itself (`Authorization`, `Cookie`, `Host`, `Idempotency-Key` and the like). |
| `headers` | Up to 16 fixed headers, each named `X-...`, used once and never the key's own header, holding at most 1,024 printable ASCII characters with no `${` substitution. |
| `operations` | 1 to 32 persisted queries, keyed by operation name, `[A-Za-z_][A-Za-z0-9_-]{0,63}`. |
| `operations.<name>.document` | The query text, at most 16 KiB. |
| `operations.<name>.variables` | Up to 32, each `{name, type, required?, minLength?, maxLength?, enum?}`. `type` is `string` (GraphQL `String` or `ID`), `integer` (`Int`), `number` (`Float`) or `boolean`. `minLength` and `maxLength` are whole numbers from 0 to 2048, and `enum` holds up to 128 strings, finite numbers or booleans. |

What synth checks, which is also what the host refuses at load:

- Each document is exactly one `query`. A mutation, subscription, fragment, `...` spread,
  `__schema` or `__type` introspection, a second operation or a variable default is refused.
- The document's variable signature matches the `variables` list exactly: the same names, each
  once, each `$name: Scalar` with `!` exactly where `required` is true. A list type such as
  `[String!]` is refused.
- An operation's call names (`<name>.<operation>`, `<name>_<operation>`, and the two camel-cased
  and joined with `_`) may not collide with an API operation's, and may not be a host call's own
  name such as `channel_publish` or `cypher_query`. The host refuses every operation in the realm
  over one such clash.
- `graphql/operations.yml` is at most 64 KiB.

A query sends the secret the owner bound to the credential and is refused while nothing is bound.
The host-side rules, including the checks on each
supplied value and on the response, are in the
[captured GraphQL operation profile](HOSTED_EXECUTION.md#me-captured-graphql-operation-profile).

## Channels

A channel is a live connection the host holds for the realm. Declare channels with `connecting`,
which checks that every credential, channel and source a declaration names is declared right
beside it. `connecting` takes all four blocks, `credentials`, `channels`, `sources` and
`consumers`; pass `{}` for one you do not need.

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
  apis: {
    telegram: {
      url: "telegram.json",
      name: "telegram",
      type: "openapi",
      auth: "path",
      credential: "bot",
      operationIds: ["getMe"],
      writeOperationIds: ["sendMessage"],
    },
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
reconnects, budgets, limits, cursors and whether a channel starts, so a channel refuses `name`,
`cursor`, `reconnect`, `autoStart`, `limits`, `budget`, `secret` and `secretRef`. A source refuses
`name`, `kind` and `installationId`, and a consumer refuses `name` and `checkpoint`. None of the
files carries a `name`; the file name is the name. Synth refuses a channel, keepalive or consumer
handler the realm does not declare, the same check `defineRealm` makes at compile time, and a
realm with no `handlers` block declares none. A duration is a whole number of seconds or minutes, greater
than zero: `"30s"` or `"5m"`.

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
  the named operation, reads `field` from the answer and connects there. Under `defineRealm`, a
  realm that declares `apis` gets a compile error for an operation none of them lists as a read
  or a write; the operation is written `<name>.<operationId>`.
- `ctx.stream.send(text)` writes a frame; write `{credential}` where the token belongs and the
  host substitutes it on the way out. `ctx.stream.close()` ends the connection once the handler
  returns; the next frames are a `close` with reason `guest` and then an `open`.

**Long-poll.** The host fetches `url` (`https://`) every `every` and hands the body to
`onResponse`.

- `every` is at least `1s` and defaults to `5s`, which synth writes into the file. The
  operator's floor wins over what the realm declares, so a realm cannot poll faster than the host
  allows.
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
webhook declares no `url` and no top-level `credential`; the signature names it.

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
  `timestamp.unit` is `s` or `ms`, and `timestamp.toleranceSeconds` is a whole number above zero.
- A request is dispatched only after its signature verifies. A changed body or a timestamp
  outside the window is refused before any handler runs.
- `verification` answers a provider's endpoint check without dispatching anything: when
  `when.field` equals `when.equals`, the host replies with the named field's value (`echo`) or a
  constant (`body`, at most 1 KiB of JSON). It applies only after the signature passes. Exactly
  one of `echo` or `body`. `when.field` and `echo` are dotted paths into the body with no empty
  step, and `when.equals` is a string or a finite number. A websocket or long-poll channel may not
  declare `verification`.

A websocket or long-poll URL may carry `{credential}` at most once, in its path or query, and
nothing else in braces: `{token}`, `{Credential}` or a lone `{` or `}` is refused, since the host
substitutes `{credential}` and nothing else. The URL may not point at `localhost`, a `.localhost`
name or a bare IPv4 or IPv6 address. Each `channels/<name>.yml` synth writes is at most 64 KiB,
the most the host reads from one channel file. A channel pointed at an origin
the operator has not allowed refuses to start. Frame budgets, reconnect backoff and the credential
rules on outbound bytes are in [channels](HOSTED_EXECUTION.md#channels).

## Sources, consumers and triggers

A **source** is a named stream of events. It is what the owner grants and what a consumer reads.
There are two ways to declare one:

- `sources` in `connecting`, fed by one of the realm's channels:
  `{ channel: "updates", description: "..." }`. The description is required and may not be
  blank; the owner reads it when deciding.
- `dataPipes.sources`, a stream the realm's own handlers publish to:
  `{ stream: "events", type: "note.changed" }`. At most 128; the name, `stream` and `type` are
  each at most 256 bytes.

A name may be declared one way or the other, never both.

A **consumer** is a handler that reads one source. Declare it in `connecting`
(`{ source, handler, assistant? }`) or in `dataPipes.consumers` (`{ handler }`, at most 128). A
`dataPipes` consumer's handler is written `namespace.verb`, and must be a handler the realm
declares: `defineRealm` checks it at compile time, and synth refuses one the realm does not
declare, since the host refuses that consumer and every trigger bound to it. `dataPipes` takes only `sources` and
`consumers`, and `data-pipes.yml` is at most 64 KiB.

The consumer is handed each event as its first argument and as `ctx.frame`, and the host
checkpoints only after the handler succeeds. Delivery is at least once, so give every effect its
own idempotency key. `assistant: true` asks for the separate grant that lets the consumer call
`ctx.assistant.chat`; the owner also pairs each sender the assistant may answer (see
[pairing](HOSTED_EXECUTION.md#pairing)).

A consumer may read another realm's source. The owner grants each consumer one exact source: a
host channel's source, a source from the same realm, or a source another installed realm
declares. The realm does not name the other realm; the owner picks the source at approval, and
the consumer receives whatever that source carries.

A **trigger** narrows what a consumer sees and says what it may do:

```typescript
handlers: {
  record: { namespace: "notes" },
  index: { namespace: "notes" },
},
dataPipes: {
  sources: { changes: { stream: "notes", type: "note.changed" } },
  consumers: { index: { handler: "notes.index" } },
},
triggers: {
  "on-change": { source: "changes", consumer: "index", mode: "observe", input: ["eventId", "payload"] },
},
```

- The key is `[a-z][a-z0-9-]{0,63}`. `source` and `consumer` name `dataPipes` declarations,
  which synth checks.
- `input` picks from `offset`, `eventId`, `streamId`, `type`, `occurredAt`, `gap` and `payload`,
  each once; left out, the consumer gets all seven. `description` is at most 512 characters.
- `mode: "observe"` lets the handler read and refuses, for the whole invocation, every publish,
  every write proposal and every approved API write. `mode: "apply"` type-checks, and the host
  refuses it at bind time.
- One trigger naming a missing source, consumer or handler stops delivery to every consumer of
  that installation until it is fixed, so check trigger names with care. The full behaviour is in
  the [trigger profile](HOSTED_EXECUTION.md#me-captured-trigger-profile).

## Publishing events

A channel or `connecting` consumer handler publishes with the shortcut on its context:

```typescript
import type { UpdatesResponseHandler } from "../.embabel/realm.d.ts";

export const updates: UpdatesResponseHandler = async (body, ctx) => {
  if (typeof body !== "string") return {};
  const batch = JSON.parse(body);
  let offset: number | undefined;
  for (const update of batch.result) {
    await ctx.publish(
      "messages",
      { text: update.message.text, chatId: update.message.chat.id },
      String(update.update_id),
      { streamId: String(update.message.chat.id) },
    );
    offset = update.update_id + 1;
  }
  return offset === undefined ? {} : { cursor: String(offset), cursorParam: "offset" };
};
```

`ctx.publish(source, event, key, options)` files `event`, a JSON object, under one of the realm's
own sources and resolves to a `Receipt`, `{id, offset, replayed}`, where `id` is the journal
receipt's id. `key` is the event id, and `options` may
carry `streamId` and `occurredAt`. The journal matches a retry on source, key, stream and
payload, so a frame the host redelivers gets the first receipt back (`replayed: true`) and keeps
the first `occurredAt`. The same event id with a different payload is refused. Only the names in
the realm's `sources` block compile as `source`.

Any handler in a captured realm can publish through `ctx.gateway.channel`, which the generated
types type with the receipts the host returns:

```typescript
import type { RecordHandler } from "../.embabel/realm.d.ts";

export const record: RecordHandler = async (_input, ctx) => {
  const { receiptId, offset, replayed } = await ctx.gateway.channel.publish({
    source: "changes",
    eventId: "note-42-v3",
    streamId: "note-42",
    occurredAt: new Date().toISOString(),
    payload: { noteId: "note-42" },
  });
  ctx.log(`filed ${receiptId} at ${offset}${replayed ? " (replayed)" : ""}`);
  return {};
};
```

| Call | Resolves to |
| --- | --- |
| `publish({source, eventId, streamId, occurredAt, payload})` | `ChannelPublishReceipt`: `{receiptId, offset, replayed}` |
| `publishBatch({source, batchId, expectedPosition, nextPosition, events})` | `ChannelBatchReceipt`: `{receiptId, offsets, replayed}`, one offset per event in order |
| `position({source})` | `{position}`, a string, or `null` before the first batch |

A poller commits a page and its cursor together with `position` and `publishBatch`; each event in
`events` is `{eventId, streamId, occurredAt, payload}`. The receipt from `ctx.gateway.channel`
names its id `receiptId`, and the `ctx.publish` shortcut names it `id`. The limits and retry
windows are under [publication](HOSTED_EXECUTION.md#publication) and
[polling positions](HOSTED_EXECUTION.md#polling-positions).

## Dependencies

A dependency is a WebAssembly module the host mounts beside the handlers, from a registry the
operator curates.

```typescript
dependencies: {
  db: {
    module: "sqlite3-wasi",
    version: "3.50",
    sha256: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    persistent: true,
    init: "db/schema.sql",
  },
},
```

```typescript
import type { AddExpenseHandler } from "../.embabel/realm.d.ts";

export const addExpense: AddExpenseHandler = async (input, ctx) => {
  await ctx.deps.db.exec("INSERT INTO expenses (amount, note) VALUES (?, ?)", [input.amount, input.note]);
  const rows = await ctx.deps.db.exec("SELECT sum(amount) AS total FROM expenses");
  return { total: rows[0]?.total ?? 0 };
};
```

- The key becomes `ctx.deps.<key>`: a JavaScript identifier, and not `log` or `gateway`.
  `ctx.deps` exists only when the realm declares a dependency.
- `module` is a registry id (`[a-z0-9][a-z0-9-]*`), `version` an exact version such as `3.50`
  (one to three dot-separated numbers), and `sha256` the digest of the module's bytes, 64
  lowercase hex characters. The host refuses a module the operator has not allowed, and one
  whose bytes do not hash to `sha256`. Either refusal takes every handler in the realm dark,
  including the ones that never touch the dependency. The reference host allows `sqlite3-wasi`
  and `h3-wasi`, at most eight dependencies, and modules up to 32 MiB.
- SQLite has one method, `exec(sql, params)`, which resolves to rows as plain objects. Bind
  values through `params` (strings, numbers or null). A `sqlite3-wasi` dependency may not declare
  `methods`.
- Any other module may declare the `methods` it calls, each with `args` and a `returns` type
  from `i32`, `i64`, `f32` and `f64`, and the generated types give `ctx.deps.<key>` exactly those
  methods. An `i64` travels as a decimal string, since values such as an H3 cell id do not fit a
  JavaScript number. A module with no declared methods is typed `unknown`. The operator's
  allowlist decides what a module may really do; a declared method the operator has not allowed
  refuses at call time.
- Without `persistent`, state lives for one dispatch and starts empty each time.
- With `persistent: true`, the host keeps one database for each world, realm and dependency. It
  restores the database at the start of a dispatch and saves it only when the dispatch succeeds
  and the output passes validation; a failed or refused dispatch leaves the stored rows as they
  were.
- `init` is a script, relative to the realm with no leading `/` and no `..`, run against empty
  state: once per dispatch for ephemeral state, or once when a persistent database is created.
  Synth refuses a missing file and copies it into the output. The host copies it from the
  admitted capture (at most 1 MiB), so editing the file later changes nothing for the admitted
  version.
- The host records the module, version, digest and init script's hash beside a persistent
  database. Change any of them and the host reports a mismatch and refuses to reuse the database.
  It neither wipes nor migrates it, and there is no migration step, so settle the schema before
  the first install that persists, and ship a changed schema under a new dependency key.
- `layers` takes `name@version` references (a registry id and one to three dot-separated
  numbers), which synth checks and writes, sorted, to `dependencies/manifest.json`. The reference
  host refuses a realm that declares them, so leave them out. `--profile reference-wasm` and
  `--profile reference-docker` refuse them too.

## Types

`types` works as in a conventional realm (see [`types/`](README.md#types)) and synth writes it to
`types/<realm name>.yml`. The generated `.d.ts` has one interface per type. A captured producer's
`targetLabel` and a proposal's `target.label` are graph labels; declare the types they name here
so a query and a person can find them. Goals resolve their `input` and `output` against the
World's types; synth warns about a goal type this realm does not declare (see [goals](#goals)).

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
import type { IncidentsHandler } from "../.embabel/realm.d.ts";

interface IncidentPage {
  items: Record<string, unknown>[];
  nextCursor?: string;
}

export const incidents: IncidentsHandler = async (input, ctx) => {
  const page = (await ctx.gateway.statuspage.listIncidents({
    services: input.serviceIds.join(","),
    impact: input.impact?.join(","), // present only when the query pinned impact
    status: input.status?.join(","),
    after: input.cursor, // absent on the first page
  })) as IncidentPage;
  return { rows: page.items, next: page.nextCursor ?? null };
};
```

**Joins.** 1 to 8 distinct joins, each naming the label it produces (`targetLabel`), the stored
label it starts from (`anchorLabel`), the relationship, the anchor property whose values become
keys (`keyField`), and the record field carrying the key back (`recordKeyField`).

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

**Names and arguments.** The producer's key is `[a-z][a-z0-9._-]{0,63}`. `keyArgument`, every
join field and every pushdown `property` are identifiers, `[A-Za-z_][A-Za-z0-9_]{0,63}`.
`page.argument` and every pushdown `argument` match `[a-z][A-Za-z0-9]{0,63}`, and no two of the
key, page and pushdown arguments may share a name. At most 16 pushdown rules, each listed once.
`handler` must be a handler the realm declares: `defineRealm` checks it at compile time, and synth
refuses one the realm does not declare, since the host refuses the producer. If the handler's
input schema sets `additionalProperties: false`, list
the page and pushdown arguments in its `properties`, or the host refuses the producer at bind
time.

**Reaching a producer.** A query reaches the target label only by traversing one of its joins
from a bound anchor: a stored node pinned by a value or narrowed by a predicate. A bare
`MATCH (i:Incident)` is refused. A producer's target may anchor another producer's join, so
producers chain, and the engine stages each hop after the one before it. See
[Virtual Cypher §2](VIRTUAL_CYPHER.md#two-concepts-the-rest-of-the-spec-leans-on).

**Limits and scope.** Each fetch is at most 256 keys of up to 2048 characters, 64 KiB of
arguments, 1 MiB of output and 1,024 rows, across all pages together. A refused fetch carries a
reason code. Producer results are never cached. Only producers from the querying handler's own installation run, each as a nested call
that needs that handler's grants as well as its own.

## Graph queries and view references

A handler reads the owner's graph with `ctx.gateway.cypher.query`. The generated types leave
`cypher` as `unknown`, so give the call a type in the handler:

```typescript
import type { OpenBySeverityHandler } from "../.embabel/realm.d.ts";

interface CypherGateway {
  cypher: {
    query(request: { cypher: string; params?: Record<string, unknown> }): Promise<{
      rows: Record<string, unknown>[];
      warnings: unknown[];
    }>;
  };
}

export const openBySeverity: OpenBySeverityHandler = async (input, ctx) => {
  const gateway = ctx.gateway as unknown as CypherGateway;
  const { rows } = await gateway.cypher.query({
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
most 32 entries, each alias and each view once. An empty list is written to the file too. A view
that references another view, takes parameters or is materialized is refused. See
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
not. `description` is at most 512 characters. Synth writes the file as `version`, `goal`,
`handler`, `input`, `output` and `description`. `handler` must be a handler the realm declares:
`defineRealm` checks it at compile time, and synth refuses one the realm does not declare. The
host resolves `input` and `output` against the World's declared types, publishes the goal as
`<key>_goal` and binds the handler's object result as the output type.

Synth warns when `input` or `output` names a type this realm does not declare (`UserInput` as
`input` excepted), and the build carries on. The type may come from another realm or from the
owner, which synth cannot see, so the goal may still work. If nothing in the World declares it, the host
drops the goal when it loads, and the warning is the first place the author hears of it. See the
[goal profile](HOSTED_EXECUTION.md#me-captured-goal-profile).

## Lenses and watches

A captured lens is a view the owner opens, produced by one of the realm's handlers. A watch
re-reads a lens on a schedule and tells the owner about new items. Declare them together with
`watching`, so a watch can only name a lens declared beside it. `watching` takes both blocks,
`capturedLenses` and `watches`:

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
`description` at most 512. Synth refuses a lens whose handler the realm does not declare.
`result` is `"json"` (the default, data only) or `"content"`, where the handler returns `focus`,
`data`, `presentation` and `complete`, and the owner's `cypher_query` approval is needed too. See
[captured handler binding](README.md#captured-handler-binding).

**Watches.** At most 16. The key is `[a-z][a-z0-9-]{0,63}`, and `lens` names a lens the realm
declares. The schedule is six-field cron, at most 64 characters, written with digits, `*`, `-`,
`,` and `/`, plus `?` in the two day fields; month and weekday names, `L`, `W`, `#` and macros
are refused. When both day fields are restricted, a day must match both. Synth walks the
expression in UTC from 30 December 2023 to 2 January 2026 and refuses one that fires less than
five minutes apart or never fires. `criteria` is one line of at most 2048 bytes, and `judge`,
when present, is not empty and at most 1024 bytes. A watch has no field for where results go: the
host alone decides how the owner hears about them.

For a watch, the lens handler returns a top-level `items` array. The first run takes a baseline
and tells the owner nothing. A run may carry at most 32 items, 8 of them new, and deliver at most
4 to the owner; a run past any of these is refused whole, and the host does not trim it. A run's
outcome is `BASELINED`, `DELIVERED`, `NOTHING_NEW`, `REFUSED` or `FAILED`. What a watch has seen
survives an approved upgrade; a changed capture takes a fresh baseline. The owner approves each
watch on its own, and approving a watch approves nothing else.

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
  `.htm`, and synth copies `apps/<key>` from the realm, refusing the app when the page is
  missing. At most 32 apps, and each `apps/<key>.app.json` is at most 8 KiB.
- `handlers` lists what the page may call, each a declared `namespace.verb`, at most 32, each
  once. It may be empty. The compiler does not check these names; synth refuses one the realm
  does not declare. Each listed handler still needs its own approval, and the owner approves the
  app itself separately.
- `resources` lists up to 16 stylesheets and scripts from `apps/<key>.assets/`, `.css` or `.js`
  only, each listed once, and synth copies each one. The host inlines each one in its own
  `<style>` or `<script>` block ahead of the page. A stylesheet containing `</style` or a script
  containing `</script` is refused.
- The host operator sets the host's size limits. The defaults are 10 MiB for the page, 16
  resources, 10 MiB for any one resource and 10 MiB for all resources together. Synth holds an app
  to the same defaults, and the `--app-*` flags or a profile change what it holds the app to for
  a host with other limits (see [app limits and profiles](#app-limits-and-profiles)).

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
import type { RecordIncidentHandler } from "../.embabel/realm.d.ts";

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
- `target.label` starts with an upper-case letter and `method` with a lower-case one; the host
  checks the rest of each name. `target.label` is a label the operator has opened to proposals,
  and `target.key` (at most 2048 bytes) must name exactly one private record the owner already
  holds.
- `fields` has 1 to 64 entries in any one object, nests at most four levels, and may not use
  `userId`, `worldId`, `workspaceId`, `visibleTo`, `owner`, `ownerId`, `labels` or any name
  starting with `_`, at any depth. The generated types make a reserved name, a fifth level or a
  field the proposal does not declare a compile error, even for a proposal built as a separate
  value first. The document is at most 64 KiB. `WRITE_PROPOSAL_LIMITS` in
  `@embabel/realm-types` holds these numbers.
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

Synth enforces every limit below except the ones marked host, which the reference host enforces
at run time.

| What | Limit |
| --- | --- |
| Files per captured directory | 32, 8 KiB each, 64 KiB together |
| Captured names (goal, trigger, lens, watch, channel, source, consumer, credential keys) | `[a-z][a-z0-9-]{0,63}` |
| Channel file | 64 KiB; `{credential}` at most once, nothing else in braces |
| Credentials | 32; description 512 characters; 1 to 32 oauth2 scopes |
| API entries / operations | 32 / 128; 64 writes; 64 parameters per operation; 256 paths and 1 MiB per document; 64 KiB `apis.yml`; 16 fixed headers |
| GraphQL | 1 to 32 operations, 32 variables each, 16 KiB per document, 64 KiB file, 16 fixed headers, 128 enum values |
| Data-pipe sources, consumers | 128 each; 256 bytes per source field; 64 KiB file |
| Websocket keepalive | 10 seconds to 5 minutes |
| Long-poll interval | at least 1 second (default 5), and never below the operator's floor (host) |
| Webhook verification reply | 1 KiB |
| Dependencies | 8 on the reference host, modules up to 32 MiB, init script up to 1 MiB (host) |
| Producer joins / pushdown rules / pages | 8 / 16 / 16 |
| Producer fetch | 256 keys, 64 KiB arguments, 1 MiB output, 1,024 rows (host) |
| Graph query | 16 KiB statement, 128 parameters, `LIMIT` 1 to 512, 1 MiB of rows (host) |
| View aliases | 32 |
| Watches | 16; at least 5 minutes apart; criteria 2048 bytes, judge 1024 bytes; 32 items per run (host) |
| Apps | 32 apps, 32 handlers each, 8 KiB manifest; by default 16 resources, 10 MiB page, 10 MiB per resource and in total, changed with the `--app-*` flags or a profile |
| Write proposals | 64 KiB, 64 entries per object, 4 levels, 2048-byte key, 32 pending per installation (host; the generated types also refuse a fifth level) |

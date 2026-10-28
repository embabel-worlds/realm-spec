# TypeScript realms

`realm.ts` is the preferred realm definition format. YAML realms remain supported as legacy,
without synthesis from TypeScript. `realm.ts` exports one default object,
assembled from as many definition files as the author needs. The host reads and evaluates it
directly. Nothing converts it to YAML, manifests or other generated declaration files, and
a realm repository commits no generated declaration files.

This document specifies the observable declaration contract. The
[composition guide](REALM_COMPOSITION.md) teaches how to assemble it. A realm's version is its
own compatibility label, not a host contract version or a module digest. This specification,
not an SDK's acceptance rules, decides what a declaration means.

Most examples below use `execution: "captured"`. A captured realm runs from a verified copy
the owner has admitted, with separately approved capabilities. A conventional realm omits
`execution` or sets it to `"conventional"`; its capabilities follow the conventional sections
of the [main specification](README.md). `triggers`, `queries`, `apps`, `credentials`,
`dataPipes`, `capturedLenses`, `watches`, `graphql`, `views`, `skills` and `capabilities` use
the captured profile here. `goals`, `producers`, `apis` and `channels` have different forms
in the two profiles. A host must refuse a declaration in the wrong profile, naming the field.

### Source selection and legacy compatibility

| Files present | Host behavior |
| --- | --- |
| `realm.ts` only | Evaluate it and validate its resulting declaration. |
| `realm.ts` plus `realm.yml` or legacy declaration folders | Use only the evaluated TypeScript declaration. Report the ignored declaration paths, whether they agree or conflict. Do not merge them or fill absent TypeScript fields from them. |
| Invalid or unsupported `realm.ts` plus valid YAML | Refuse the TypeScript declaration with its diagnostic. Never fall back to YAML. |
| No `realm.ts` | Keep reading the legacy `realm.yml` and its folders exactly as before, including committed `dist/` and `dependencies/manifest.json`. No migration is required. |

The precedence rule includes adjacent handler and dependency manifests and stale generated
declarations. It does not discard resources explicitly referenced by `realm.ts`, such as SQL,
handler source, an icon or a vendored API document. YAML is legacy and receives no new features.
Legacy decorator and YAML type declarations retain their existing duplicate-type checks;
neither contributes additional types when `realm.ts` is present.

### Definition evaluation

`realm.ts` and its transitive imports are definition code evaluated by the host, separate
from guest handler code. Only the evaluated default object's value counts. Object spread
therefore has ordinary TypeScript semantics: a later property replaces an earlier property
with the same key, and the host cannot recover the overwritten declaration.

Definition imports may reference captured, realm-relative TypeScript or JavaScript modules
and exact `#` subpath mappings in the realm's `package.json` `imports` object. These mappings
must resolve to relative files inside the realm. A `tsconfig.json` path alias alone does not
declare a runtime mapping. No import may escape the captured realm, including through a
symlink. Type-only imports are erased and confer no runtime capability. A host may offer
documented, versioned authoring helpers; it must refuse unsupported bare package imports,
host built-ins, remote imports and unresolved imports rather than install or fetch packages.
An authoring helper has the same evaluation restrictions as local definition code.

Evaluation must be deterministic and free of external side effects. It may construct values
with functions, loops and object spread. It may not read files except by the permitted import
resolver, write files, read environment variables, use the clock or randomness, open a network
connection, start a process or access host capabilities. Evaluation failure, an unsupported
import, a prohibited operation or a resource limit refuses the definition before admission,
with the offending file or operation and the reason. A host must enforce these restrictions
before effects occur; detecting an escape after executing it is not confinement.

The result is finite JSON-like data: strings, booleans, null, finite numbers, arrays and
plain records. Functions may build that data but cannot remain in it. Functions, symbols,
dates, big integers, maps, sets, cycles and undefined array entries in the result are refused.
Undefined object members are absent. The host validates the result regardless of SDK checks.
Schema helper values must be converted by a permitted pure authoring helper to the host's
supported JSON Schema subset before the host accepts the definition.

In the captured profile, the host must refuse control characters, including newlines, and
unpaired surrogates in the text fields of goals, triggers, producers, lenses, watches, data
pipes, view references, apps, credentials and API entries. This validation applies regardless
of SDK checks.

**Implementation status, 2026-10-27:** direct TypeScript reading exists, but complete import
confinement, deterministic evaluation and the source precedence above have not all been
established by conformance evidence. In particular, older loaders can still consult adjacent
manifests. Do not treat those behaviors as permission to depend on ambient files or stale
declarations. A host that cannot safely evaluate a definition must refuse it. Support for
arbitrary npm validators or package resolution is not implied.

### SDK assistance (non-normative)

The TypeScript SDK checks a definition as you write it. `satisfies Realm` checks its fields;
`defineRealm` can also check handler references. It accepts Standard Schema validators for
handler schemas and can derive input and output types. Those are SDK conveniences, not a
different host contract. The host re-checks everything regardless, including the resulting
JSON Schema and every handler input and output. SDK lint may be stricter than portable
metadata rules, but it cannot change the host's interpretation.

## Contents

- [Compose a realm from files](REALM_COMPOSITION.md)
- [Build a realm](#build-a-realm)
- [App limits and profiles](#app-limits-and-profiles)
- [Realm metadata](#realm-metadata)
- [Handlers](#handlers)
- [The handler context](#the-handler-context)
- [The model call](#the-model-call)
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
- [Declaration coverage and open contracts](#declaration-coverage-and-open-contracts)

## Build a realm

Write `realm.ts` and the source or resources it references. Start with the complete examples
in [Composing a realm](REALM_COMPOSITION.md). Check the definition with TypeScript, then ask
the host to validate and install the captured source. No declaration generation step exists.
Handler compilation is separate: compiling guest code does not create another realm declaration.

The host checks all references to handlers. An absent `handlers` block declares none. A goal,
producer, consumer, channel, lens or app naming an undeclared handler is refused with its name.
Captured `actions`, `events` and legacy `webhooks` remain unavailable in the governed profile;
the host reports them instead of silently executing them.

## App limits and profiles

The host publishes supported capabilities and finite limits. The reference app defaults are
10 MiB per page, 10 MiB per resource, 10 MiB for all resources of one app and 16 resources.
An author-side check can detect an oversized app; it cannot raise the host's limits.
Unsupported capabilities must be reported explicitly. A supported declaration does not grant
permission to execute it. See [apps](#apps) and [hosted execution](HOSTED_EXECUTION.md).

Legacy captured directories retain their limits: at most 32 files per declaration kind,
8 KiB each and 64 KiB together. These are legacy file limits, not a requirement to write
those files from `realm.ts`.

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
| `name`, `version` | Required. Name is kebab-case; version is the realm's semantic version. The legacy YAML default remains `0.0.0`. Neither value grants authority. |
| `host` | Optional `"wasm"` or `"docker"` placement hint. Absent means infer from the available handler source/artifact using [placement](README.md#placement). A data-only realm needs no handler artifact. |
| `execution` | `"conventional"` by default; `"captured"` selects the captured declaration forms and admission requirements. |
| `runtime` | Guest language, `"typescript"` by default; also `"python"`, `"ruby"`, `"lua"`, `"compiled"`. A recognized language does not promise host execution support. An unsupported runtime refuses handler binding explicitly. In the captured profile, a host must refuse `channels`, `sources` or `consumers` when the runtime is other than `"typescript"`, even if it supports that runtime for handlers. |
| `entry` | Realm-relative handler source path, with no leading slash, backslash or `..` segment. Defaults to `wasm/handlers.ts`, `wasm/handlers.py` for Python, or `wasm/src/lib.rs` for compiled guests. An explicit entry must exist. When handlers need compilation, the effective default must exist too; a realm with no handlers needs no entry. The current reference source builder supports the fixed `wasm/handlers.ts` or `.js` layout; other entry layouts need host support and must not silently select another file. |
| `icon` | Optional path to an existing file inside the realm. Remote URLs are refused, as in [Icons](README.md#icons). |
| `description`, `author`, `url` | Optional descriptive strings. `url` is the realm's information link, not an import or capability. |
| `tags` | Optional list of discovery strings; omission and an empty list both declare no tags. |
| `category` | Optional catalogue category. Unknown categories are reported and use the host's fallback; they do not refuse loading. |
| `maturity` | Readiness claim, compared case-insensitively: `experimental`, `beta`, `stable`, `deprecated`. Missing or unknown values mean unstated, never stable. See [maturity](README.md#maturity). |
| `exports` | Optional selection of public declarations. Complete wildcard, unknown-name and cross-kind selection semantics are not yet specified; do not rely on SDK-specific expansion for portable behavior. It never expands a grant. |
| `retry` | Optional retry request. A portable field/default and effect-safety contract is not yet specified. Do not assume automatic retry of an effectful call; captured retries retain the original authority. |
| `capabilities` | Captured-only list of requested grants. `"model"` asks for [the model call](#the-model-call); the owner may grant none. |
| `skills` | Captured-only list of shipped skill names under `skills/<name>/SKILL.md`. Skill content is captured and remains subject to model-call approval. |
| `generatedAt` | Optional legacy timestamp metadata; default `1970-01-01T00:00:00Z`. It neither triggers generation nor changes permission or proves freshness. |

### Shipped skills

A listed skill is a captured resource, not code to execute during definition evaluation.
Names must be unique and must resolve to a contained `skills/<name>/SKILL.md` file. A skill
cannot acquire tools or another realm's capabilities by naming them. Model calls use admitted
skill content, not later edits to the working tree. The complete portable frontmatter,
reference traversal, cycle and digest-format rules are not yet specified. SDK packaging
checks alone do not establish host enforcement of those rules.

## Handlers

Optional output fields whose value is null are treated as absent before validation when the
declared field is optional and nonnullable. This tolerance applies to outputs only, as in the
[handler schema profile](README.md#me-captured-handler-schema-profile). Required fields still
must satisfy their schema, and an explicitly nullable field retains null. SDK static types
may require authors to omit optional values; they do not remove the host's output tolerance.

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

The code lives in the entry file as exported functions named after the verbs. Optional SDK
handler types give each one its input, output and context. The reference snippets use
illustrative aliases from an ordinary author-side `handler-types.ts`; these are editor aids,
not generated realm declarations. The complete composition examples instead write their
handler signatures directly:

```typescript
// wasm/handlers.ts
import type { SweepHandler } from "../handler-types";

export const sweep: SweepHandler = async (_input, ctx) => {
  ctx.log("sweeping status pages");
  return {};
};
```

- The verb must be a JavaScript identifier.
- `input` and `output` are JSON Schema fragments. Left out, each is `{"type": "object"}` in the
  declaration. The host holds them to the
  [handler schema profile](README.md#me-captured-handler-schema-profile): a bounded subset of JSON
  Schema, checked before binding, with input validated before the handler runs and output
  validated before the result is released. `$ref`, `pattern`, `format` and `uniqueItems` refuse
  the binding.
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
the SDK's inferred types say which members each handler gets.

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
| `ctx.call("ai_complete", request)` | every handler, when the realm declares `capabilities: ["model"]` | Asks the owner's model by role, with skills by name. See [the model call](#the-model-call). |

Channel callbacks receive their frame and channel context; consumers receive their event
and consumer context. Websocket handlers also receive the stream operations. Only the
declared keepalive handler receives keepalive ticks. `assistant: true` requests assistant
access for that consumer, subject to its separate grant. SDK type aliases are non-normative
editor assistance; they neither supply context members nor authorize their use.

Every `ctx.gateway.<namespace>.<operation>` call and `ctx.writePropose` returns a promise, which
resolves to the result or rejects. A refusal carries one fixed message and never says which rule
failed, so treat it as "not allowed at the moment" and carry on. The assistant call is the one
exception: it rejects with an `AssistantRefusal`, an `Error` whose `code` is
`ASSISTANT_NOT_GRANTED` (the consumer has no assistant grant) or `SENDER_NOT_PAIRED` (the owner
has not paired this sender), so a realm can answer with its own pairing hint. The code is a
property of the error and never part of its message. A refusal that gives no reason has no
`code`. The following example gives that error an author-side TypeScript type.

```typescript
import type { AssistantRefusal, ReplyConsumerHandler } from "../handler-types";

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

## The model call

A realm that declares `capabilities: ["model"]` may put a question to the owner's model from any
handler. The owner grants the model on its own at admission, and may not; a realm should keep
working without it.

```typescript
const reply = ctx.call("ai_complete", {
  prompt,
  role: "best",
  skills: ["chess-plans"],
  maxOutputTokens: 1200,
});
// reply is { text: string, truncated: boolean }
```

- `prompt` is not blank. `role` is `"cheap"`, `"workhorse"` or `"best"`, or left out for the
  owner's default. The realm names a role and never a model: the host chooses the model behind
  each role and holds its credential.
- `skills` names up to eight skills, each 1 to 64 characters: this realm's own, bare or as
  `<realm>-<skill>`, or one the owner's World has. The host supplies the skill's text; the realm
  never sends it.
- `maxOutputTokens` is a positive whole number. The host cuts a longer reply and says so in
  `truncated`.
- Any other field is refused, and the SDK's inferred types make it a compile error.
- A refusal is thrown as an error whose `code` is `MODEL_NOT_GRANTED`, `MODEL_SKILL_UNKNOWN`,
  `MODEL_CALL_BUDGET`, `MODEL_DAILY_BUDGET` or `MODEL_PROMPT_TOO_LARGE`. A request the host
  cannot read is refused with no code.
- The call is budgeted per dispatch (calls, prompt bytes and output tokens), per day, and by
  the dispatch's own deadline; the reference values are in
  [the model call](HOSTED_EXECUTION.md#the-model-call).

A captured handler has no `gateway.ai`; that surface belongs to the conventional code-mode
sandbox. `ctx.call` with any other tool name is refused.

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
| `scheme` | `bearer` only: the word sent before the token in `Authorization`, 1 to 32 printable ASCII characters with no spaces. Defaults to `Bearer`. |
| `scopes` | `oauth2` only, and required there: 1 to 32 distinct scopes, each at most 128 characters. |

`value`, `env`, `tokenEnv` and `walletItem` are refused, so a captured realm cannot ship or point
at a secret, and so is any other field not in the table. A credential nothing references is
refused, since it would ask the owner for a secret no call uses. The host counts a reference from an
API entry's `credential` (or its deprecated `tokenEnv`), a channel's `credential`, a webhook
signature's `credential` and the [GraphQL](#graphql) source's `credential`. Binding, rotation
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

The typed gateway has one method per listed operation under `ctx.gateway.<name>`. A read takes
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

A write is checked against the admitted request schema. An operation may not declare a
parameter named `body`, which is reserved for its request body. The current portable response
is a parsed JSON body with no envelope; narrow it before use. Additional codecs, raw responses,
media parameters and streaming return types are not yet specified. SDK support for those
forms is not evidence that a host supports them. The separately marked NDJSON proposal in
the hosted contract does not change this current profile.

The host checks at installation:

- At most 32 entries and 128 operations across them. The entry's key is a JavaScript identifier.
  `name` is `[A-Za-z_][A-Za-z0-9_-]{0,63}` and unique. Two operations may share an id in
  different namespaces, and are refused when their qualified names collide
  (`<name>.<id>`, `<name>_<id>`, or the two camel-cased and joined with `_`).
- `url` is a bare filename, `[A-Za-z0-9_-]+\.json`, under `apis/`, at most 1 MiB, OpenAPI 3.x,
  with every `$ref` pointing under `#/components/`, at most 256 paths, and each operation id
  declared once. YAML OpenAPI documents are not in this captured profile; SDK acceptance does
  not extend it. Legacy `apis/apis.yml` remains limited to 64 KiB.
- For authenticated APIs, exactly one of `credential` or `tokenEnv`, and a `credential` must be declared in
  `credentials`. `tokenEnv` is deprecated in favour of a declared credential: it matches
  `[A-Za-z_][A-Za-z0-9_]{0,127}`, may not start with `__embabel_sql_v1__`, and becomes an
  implicit credential, with a warning. The implicit credential's id is the variable name spelled
  as written, which the declared-id pattern does not cover; the host reads a credential id in
  either spelling (see [credentials and databases](HOSTED_EXECUTION.md#credentials-and-databases)).
  Two entries reading one `tokenEnv` must declare the same `auth`. An `auth: "path"` entry
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
- For bearer or API-key authentication, security is exactly one requirement naming one scheme, with no scopes. For `bearer` it is an
  `http` scheme whose word matches the credential's `scheme`. For `api-key` it is an `apiKey`
  scheme in a header or the query, named `[A-Za-z][A-Za-z0-9-]{0,127}`, and the header may not
  be one the host owns (`Authorization`, `Cookie`, `Host`, `Content-Type` and the like). The
  field the credential travels in may not also be a fixed header or a parameter.
- `auth: "path"` puts the credential in the URL and needs `credential`. The document writes
  `{credential}` in the server URL or in the path of a declared operation, so that each declared
  operation's full URL carries it exactly once, in the path, never in a query string. `security`
  is absent or empty, and no operation takes a `credential` parameter. The typed client takes
  no argument for it.
- `auth: "none"` is a public read API: no credential or `tokenEnv`, absent or empty security,
  GET operations only, and no write grants. Keyless access still needs operation approval.
- Up to 16 fixed headers, each named `X-...` and holding at most 1,024 printable ASCII
  characters, with no `${` substitution. Two header names that differ only in case are refused.
  Authors cannot override `User-Agent`; the host owns it except when the admitted authentication
  scheme uses that header for its key.

Each operation is approved by the owner on its own, reads and writes under separate grants; see
[captured API operations](HOSTED_EXECUTION.md#captured-api-operations) for what the host does on
every call.

## GraphQL

A captured realm may declare one GraphQL source with `graphql`: one fixed HTTPS endpoint and a
fixed set of persisted queries. The host reads this block directly. YAML-only realms retain
the legacy `graphql/operations.yml` path.

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
import type { ProductHandler } from "../handler-types";

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

Operation arguments follow the declared variables. A required variable must be present; an
optional one may be omitted or null. An enum restricts its value, and undeclared variables
are refused. An operation with no variables takes no argument, or `{}`. Narrow the result
before use; SDK type inference does not replace these host checks.

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

The host checks at load:

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

Channel, source and consumer keys are declaration names: `[a-z][a-z0-9-]{0,63}`. The host owns
reconnects, budgets, limits, cursors and whether a channel starts, so a channel refuses `name`,
`cursor`, `reconnect`, `autoStart`, `limits`, `budget`, `secret` and `secretRef`. A source refuses
`name`, `kind` and `installationId`, and a consumer refuses `name` and `checkpoint`. None of the
records carries a `name`; the record key is the name. The host refuses a channel, keepalive or consumer
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

- `every` is at least `1s` and defaults to `5s`. The
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
name or a bare IPv4 or IPv6 address. In a legacy realm, each `channels/<name>.yml` is at most
64 KiB, the most the host reads from one channel file. A channel pointed at an origin
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
declares: `defineRealm` checks it at compile time, and the host refuses one the realm does not
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
  which the host checks.
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
import type { UpdatesResponseHandler } from "../handler-types";

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

Any handler in a captured realm can publish through `ctx.gateway.channel`, which the SDK
types type with the receipts the host returns:

```typescript
import type { RecordHandler } from "../handler-types";

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
| `read({source, after, limit})` (proposed) | `{entries, next, last}`: the Realm's own records of the source after `after`, oldest first, `limit` 1 to 100 |

A poller commits a page and its cursor together with `position` and `publishBatch`; each event in
`events` is `{eventId, streamId, occurredAt, payload}`. The receipt from `ctx.gateway.channel`
names its id `receiptId`, and the `ctx.publish` shortcut names it `id`. The limits and retry
windows are under [publication](HOSTED_EXECUTION.md#publication) and
[polling positions](HOSTED_EXECUTION.md#polling-positions).

Proposed: a handler reads back what its own Realm published with `read`, described under
[reading back a realm's own records](HOSTED_EXECUTION.md#reading-back-a-realms-own-records-proposed).
A handler that answers the newest signals it recorded, newest first, reads once to learn the
last offset and once below it:

```typescript
import type { RecentHandler } from "../handler-types";

export const recent: RecentHandler = async (input, ctx) => {
  const n = input.limit ?? 20; // 1 to 100
  const { last } = await ctx.gateway.channel.read({ source: "pulse", limit: 1 });
  const { entries } = await ctx.gateway.channel.read({ source: "pulse", after: Math.max(0, last - n), limit: n });
  return { signals: entries.reverse().map(({ offset, record }) => ({ offset, ...record.payload })) };
};
```

Called with `{limit: 2}` after three records, it answers the records at offsets 3 and 2, in that
order. A read never returns another Realm's records, so the handler needs no filter for them.

## Dependencies

A dependency is a WebAssembly module used through `ctx.deps.<key>`. Its declaration states
which bytes are needed and where to obtain them. It grants nothing. The operator's allowlist
admits by digest, kind and methods, whatever the source. For the same bytes, changing the
source does not change admission, dispatch, state identity or permission.

| Field | Contract |
| --- | --- |
| record key | Handler binding name, a JavaScript identifier other than `log` or `gateway`. |
| `module` | Required human-readable module name, `[a-z0-9][a-z0-9-]*`. It labels the dependency and its operator policy. |
| `version` | Required exact version, one to three dot-separated numbers. No range, `latest` or moving tag. This grammar is not full SemVer. |
| `sha256` | Required SHA-256 of the module bytes, exactly 64 lowercase hexadecimal characters. One digest per dependency for now. |
| `kind` | Required for new declarations; `[a-z][a-z0-9-]{0,63}`. The calling contract requested, such as `sqlite`, `pure-compute` or `string-method`. The allowlist, not this claim, determines permitted behavior. Unknown or incompatible kinds refuse the dependency before a call executes. |
| `methods` | Optional record of method signatures, with `args` and `returns`. It narrows what may be called; it never widens the allowlist. SQLite uses its fixed API and must omit this field. |
| `from` | Source string or one-tag object, described below. Omission selects the operator's default registry source. |
| `license` | Optional license identifier or expression describing the module. |
| `provenance` | Optional record: `repository` (source repository URL), `commit` (exact source commit), `toolchain` (build tool/version description), `lockDigest` (SHA-256 of the upstream build's dependency lock). These are provenance claims, not permission or independent verification. |
| `persistent`, `init`, `migrations` | State declarations, described under [dependency state](#dependency-state). |

License and provenance are optional in the portable declaration today. A host or registry may
require either as policy and must report what is missing. `lockDigest` describes an upstream
module build; it does not introduce a realm module lock file. A later `variants` list beside
`sha256` is reserved without defining its entries or selection rules. This version must not
silently select a variant it does not understand.

### Dependency sources

`from` is an extensible tagged union. Its current object form has exactly one source tag:

| Form | Meaning |
| --- | --- |
| `{ local: "modules/stockfish-19.0.0.wasm" }` | A regular file inside the captured realm. Paths are realm-relative, without leading slash, backslash, `.` or `..` components. A symbolic link or escape from the realm is refused. Human-readable filenames are encouraged. |
| `{ registry: "default" }` | The operator-configured source named `default`. Any nonempty configured source name may replace it; an unknown name is refused. Omitting `from` means this default. |
| `{ url: "https://modules.example.org/module.wasm" }` | Fetch at install if verified bytes are not already cached; verify and cache by digest. It is never fetched during a handler call. A URL must use HTTPS and contain no credentials or fragment. Its filename need not be the digest. Redirects require explicit host policy and must remain HTTPS; no redirects is the current digest-prefix source behavior. |
| `{ realm: "another-realm" }` | Reserved, refused with `DEPENDENCY_SOURCE_NOT_SUPPORTED_YET`, naming the dependency and `realm` source. Consent, pinning, cycles and upgrades remain to be specified. |

The unambiguous string shorthands are `"./modules/example.wasm"` for a local file and
`"https://modules.example.org/example.wasm"` for a URL. Strip the leading `./` when resolving
the local shorthand. Other strings are refused; a bare module name or version is not guessed
to be a path or registry. Use the registry object form. This string-or-object convention
does not import another package system's ranges, Git sources or lock file.

New source tags may be added independently with their own consent and pinning rules, without
changing existing tags. An unrecognized tag is refused explicitly as unsupported, naming the
dependency; it must never fall back to the default registry.

**Registry resolution today.** The module name and exact version describe the requested
module; operator policy checks those labels where configured. Current sources fetch bytes by
digest through an operator-configured digest-addressed store or HTTPS prefix, not by a
name/version lookup. Current admission does not independently verify the author's version
label against the bytes. A registry may later resolve `(module, exact version)` to a candidate,
but that candidate must still match the declared `sha256`. That lookup is reserved, not
required of today's hosts, and needs no second authored file.

Whatever the source, the digest is the identity of the bytes. A missing source or hash
mismatch is refused naming the dependency and its source. `DIGEST_MISMATCH` must identify
the expected digest without exposing secrets. Unverified bytes must not be cached or run.
A cache hit must still be verified. Declaring or shipping bytes grants nothing.

`realm.ts` `from` is the only place a dependency source is declared. There is no module lock
file or separate list to maintain. Legacy YAML realms keep loading
`modules/<sha256>.wasm` with `dependencies/manifest.json` unchanged; their existing kind
inference and module policy remain intact. This is legacy compatibility, not an alternate
source declaration for a TypeScript realm.

**Implementation status, 2026-10-27:** digest-addressed byte sources, verification and
per-dependency admission exist. The complete `from` parser, named registry selection,
install-time URL sourcing and explicit declared-kind validation above are the required
contract, not a claim that all current hosts enforce them. Older readers can ignore added
fields. A host advertising this contract must enforce them or refuse the unsupported source.

### Dependency examples

These three complete definition objects show the local, registry and URL forms. They parse
as TypeScript without SDK extensions. Installing them also requires the named bytes and an
operator grant. The digests identify the audited module builds; the example URL and named
registry are operator-provided locations, not a claim of a public download service.

Stockfish uses the non-SIMD build. Place those exact bytes in
`modules/stockfish-19.0.0.wasm`:

```ts
// realm.ts (local Stockfish)
export default {
  name: 'chess-modules',
  version: '1.0.0',
  dependencies: {
    engine: {
      module: 'stockfish',
      version: '19.0.0',
      sha256: 'b6e43bfbb09335610d64c93e343a2e42b03ebdf80aafa54db42a4dcc1f168056',
      kind: 'string-method',
      from: { local: 'modules/stockfish-19.0.0.wasm' },
      methods: { analyse: { args: ['string', 'i32', 'i32', 'i32'], returns: 'string' } },
      license: 'GPL-3.0-or-later',
    },
  },
}
```

SQLite from the operator's default registry, with ephemeral state and no init file:

```ts
// realm.ts (registry SQLite)
export default {
  name: 'sqlite-modules',
  version: '1.0.0',
  dependencies: {
    db: {
      module: 'sqlite3-wasi',
      version: '3.53',
      sha256: '9a5542e25e42fbbb48501bae0ab4295cdf0fd0f41219ec3b6c891c4a282e7779',
      kind: 'sqlite',
      from: { registry: 'default' },
    },
  },
}
```

H3 from an HTTPS location the operator permits. Substitute your actual module URL:

```ts
// realm.ts (URL module)
export default {
  name: 'geo-modules',
  version: '1.0.0',
  dependencies: {
    geo: {
      module: 'h3-wasi',
      version: '4.5',
      sha256: '45cf0ddff91e19c561d2b5f309b04eadbfdd2018688c4e20f749be8805903882',
      kind: 'pure-compute',
      from: { url: 'https://modules.example.org/h3-4.5.wasm' },
      methods: { latLngToCell: { args: ['f64', 'f64', 'i32'], returns: 'i64' } },
    },
  },
}
```

Renaming a local module changes captured realm identity because paths as well as bytes are
covered. See [readable dependency filenames](REALM_COMPOSITION.md#dependency-files-with-readable-names).

### Admission and method calls

A malformed dependency container or entry, or exceeding the reference limit of eight
dependencies, refuses the declaration. The reference module byte limit is 32 MiB.
An ordinary missing, unallowed or mismatched module refuses that dependency only. Other
dependencies and handlers remain available, including handlers that do not call it.
An uncaught refused call prevents a successful result; distinguishing every refused outcome
from a failed dispatch across host profiles is not yet specified.

SQLite exposes `exec(sql, params)`, returning rows as plain objects. Parameters are strings,
numbers or null; bind values with parameters rather than interpolating SQL. Other dependencies
may declare at most 64 methods, each an identifier of at most 64 characters, with exactly
`args` (at most 16 types) and `returns`. Scalar types are `i32`, `i64`, `f32`, `f64` and
`string`. An `i64` travels as a decimal string, not a potentially rounded JavaScript number.

If `methods` is present and nonempty, an undeclared method refuses with `METHOD_NOT_DECLARED`
before execution, even if allowlisted. If omitted, only the operator's permitted methods
are callable. A declared method absent from the allowlist or with a different signature
refuses that method only (`METHOD_UNKNOWN` or `SIGNATURE_MISMATCH`), with a
`DEPENDENCY_METHOD_REFUSED` load diagnostic. A module whose exports disagree with the
allowlist refuses the whole dependency. A realm does not choose how the host executes the
module and gains no permission to load native libraries.

String methods pass and return ordinary strings to handlers. The module ABI uses UTF-8:
each string argument is an `i32` pointer/length pair; a string result is an `i64` with the
pointer in the high 32 bits and length in the low 32 bits. Empty is `(0, 0)`. The module
exports `embabel_alloc(i32) -> i32` and `embabel_free(i32, i32)`. The host frees argument
buffers even after a trap and frees the result after copying it. Results cannot overlap
arguments or escape module memory. Each string is at most 1 MiB and per-dispatch allocations
at most 8 MiB. Invalid UTF-8, bounds or ownership violations fail the call.

### Dependency state

The implemented state profile is SQLite (`module: 'sqlite3-wasi'`, admitted as SQLite).
`persistent` defaults to false. Ephemeral state starts empty for each dispatch. With
`persistent: true`, a world, realm and dependency binding retains its private database.
The host publishes changes only after successful dispatch and output validation. Failure,
refusal or a conflicting concurrent publication leaves the previous stored state intact;
a publication conflict returns `STATE_CONFLICT`. This storage is separate from the graph.

`init` names a contained script, at most 1 MiB, read from the admitted capture. It runs on
empty state: each ephemeral dispatch or the first creation of persistent state. Editing the
working copy does not change an admitted script. `migrations` is an ordered list of at most
64 distinct contained `.sql` paths, each at most 1 MiB; it requires `init`. On empty state,
init runs before all migrations. On restored state, only the appended migrations run.

The stored fingerprint records admitted module identity/version/digest, the init hash and
ordered migration hashes. Applied migrations must remain an unchanged prefix. Reordering,
removing or editing one, or changing the base module/init identity, refuses reuse with
`DIGEST_MISMATCH`, naming the first difference. A failing migration reports `FAILED` and
does not publish its partial changes. The host neither silently wipes nor reinterprets old
state. Fingerprints predating migrations mean an empty applied list.

State options on `pure-compute` are refused. State and migration semantics for other module
kinds are not yet specified. Declaring `kind: 'sqlite'` on an arbitrary module does not grant
SQLite support. The currently implemented migration restriction is the SQLite module profile;
generalization to additional admitted stateful kinds remains open.

### Dependency batch calls

The SDK offers `ctx.deps.<key>.<method>.batch(calls)` for declared scalar methods, with
1 to 256 calls and ordered results. A single-argument method uses a list of scalar values;
a multi-argument method uses a list of argument tuples; a zero-argument method uses empty
tuples. That is an SDK surface, not evidence of a portable host batch protocol. Host-side
batch dispatch, partial results, failure ordering, cancellation and atomic state/commit
semantics are not yet specified or established by the grounding evidence. Do not infer a
transaction from a batch helper. Sequential awaited calls inside one dispatch use the
ordinary scalar-call and success-only persistence rules above.

`layers` remains unsupported in the reference profiles and is refused as `LAYERS_REFUSED`.
It is not an alternative to definition imports or a way to obtain another realm's grants.
Graph label composition remains separate from code and dependency-source composition.

## Types

`types` is a record as specified in [Declaring types](DECLARING_TYPES.md#typescript-object-declarations).
The host reads it directly. Optional SDK types can describe its records. A captured producer's
`targetLabel` and a proposal's `target.label` are graph labels; declare the types they name here
so a query and a person can find them. Goals resolve their `input` and `output` against the
World's types, including types contributed by other realms (see [goals](#goals)).

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
import type { IncidentsHandler } from "../handler-types";

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
`handler` must be a handler the realm declares: `defineRealm` checks it at compile time, and the host
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
[reason code](HOSTED_EXECUTION.md#me-captured-producer-paging-profile). Producer results are never cached. Only producers from the querying handler's own installation run, each as a nested call
that needs that handler's grants as well as its own.

## Graph queries and view references

A handler reads the owner's graph with `ctx.gateway.cypher.query`. The SDK's inferred types leave
`cypher` as `unknown`, so give the call a type in the handler:

```typescript
import type { OpenBySeverityHandler } from "../handler-types";

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
most 32 entries, each alias and each view once. An empty list declares no references. A view
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
not. `description` is at most 512 characters. The key names the goal.
`handler` must be a handler the realm declares:
`defineRealm` checks it at compile time, and the host refuses one the realm does not declare. The
host resolves `input` and `output` against the World's declared types, publishes the goal as
`<key>_goal` and binds the handler's object result as the output type.

A type may come from another realm or from the owner. If nothing in the World declares a
goal's `input` or `output` type (`UserInput` as input excepted), the host reports and drops that
goal when it loads. An SDK may warn earlier without treating an external type as an error. See the
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
`description` at most 512. The host refuses a lens whose handler the realm does not declare.
`result` is `"json"` (the default, data only) or `"content"`, where the handler returns `focus`,
`data`, `presentation` and `complete`, and the owner's `cypher_query` approval is needed too. See
[captured handler binding](README.md#captured-handler-binding).

**Watches.** At most 16. The key is `[a-z][a-z0-9-]{0,63}`, and `lens` names a lens the realm
declares. The schedule is six-field cron, at most 64 characters, written with digits, `*`, `-`,
`,` and `/`, plus `?` in the two day fields; month and weekday names, `L`, `W`, `#` and macros
are refused. When both day fields are restricted, a day must match both. The reference profile requires
a schedule that fires and has at least five minutes between occurrences. A finite SDK
schedule check is not a guarantee about all future occurrences. `criteria` is one line of at most 2048 bytes, and `judge`,
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
  `.htm`, and the host captures `apps/<key>` from the realm, refusing the app when the page is
  missing. At most 32 apps. Legacy `apps/<key>.app.json` files are limited to 8 KiB each.
- `handlers` lists what the page may call, each a declared `namespace.verb`, at most 32, each
  once. It may be empty. The compiler does not check these names; the host refuses one the realm
  does not declare. Each listed handler still needs its own approval, and the owner approves the
  app itself separately.
- `resources` lists up to 16 stylesheets and scripts from `apps/<key>.assets/`, `.css` or `.js`
  only, each listed once, and the host captures each one. The host inlines each one in its own
  `<style>` or `<script>` block ahead of the page. A stylesheet containing `</style` or a script
  containing `</script` is refused.
- The host operator sets the host's size limits. The defaults are 10 MiB for the page, 16
  resources, 10 MiB for any one resource and 10 MiB for all resources together. Author checks
  should use the target host's published limits (see [app limits and profiles](#app-limits-and-profiles)).

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
import type { RecordIncidentHandler } from "../handler-types";

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
  starting with `_`, at any depth. The SDK's inferred types make a reserved name, a fifth level or a
  field the proposal does not declare a compile error, even for a proposal built as a separate
  value first. The document is at most 64 KiB. `WRITE_PROPOSAL_LIMITS` in
  `@embabel/realm-types` holds these numbers.
- `expectedRevision` (optional, a whole number) makes the write conditional on the record's
  current revision. `null` has the same meaning as omission.
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

The reference profile applies the limits below. SDK checks are additional authoring assistance.
The host checks declarations at load and call limits at run time. File-byte limits below belong to legacy file representations; they
do not require generated files from a TypeScript realm.

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
| Apps | 32 apps, 32 handlers each, 8 KiB per legacy app manifest; by default 16 resources, 10 MiB page, 10 MiB per resource and in total, subject to the host's published limits |
| Write proposals | 64 KiB, 64 entries per object, 4 levels, 2048-byte key, 32 pending per installation (host; the SDK's inferred types also refuse a fifth level) |


## Declaration coverage and open contracts

This index separates the current contract from SDK features and unfinished proposals. A
field being accepted by an SDK does not extend a host profile or weaken a refusal below.
Where a complete portable schema is deferred, do not invent another declaration file to
work around it. The future declaration still belongs in `realm.ts`.

| Declaration | Normative destination and current boundary |
| --- | --- |
| Source and imports | [Source selection](#source-selection-and-legacy-compatibility) and [definition evaluation](#definition-evaluation); legacy loading remains supported. Enforcement gaps are stated there. |
| Metadata, profile and language | [Realm metadata](#realm-metadata); complete `exports` and `retry` semantics and target-contract negotiation remain unspecified. Realm, module, capture and installation identities are distinct; see [glossary](GLOSSARY.md#source-and-dependency-identity). |
| Handlers and schemas | [Handlers](#handlers) and the [schema profile](README.md#me-captured-handler-schema-profile). Standard Schema adapters and inferred types are SDK behavior. Only the evaluated supported JSON Schema reaches the host; optional-output null tolerance does not apply to inputs. |
| Dependencies | [Dependencies](#dependencies), including sources, methods, state and explicit batch limits of evidence. Bundled npm requirements have [legacy-only declaration status](HOSTED_EXECUTION.md#backends-and-dependencies). |
| Types and properties | [Declaring types](DECLARING_TYPES.md#typescript-object-declarations), including visibility and property validation. Complete population, method/retrieval defaults, examples/perspective selection, value enumeration and cardinality interactions remain unspecified. Existing lifecycle, spine and hub semantics are not removed because an SDK omits their fields. |
| Producers and joins | [Captured producers](#producers), [conventional producers](README.md#producers) and [Virtual Cypher](VIRTUAL_CYPHER.md). `persistMinted` remains refused at validation/install. An SDK accepting it does not permit persistence of minted anchors. Exhaustive nested-field/default tables and SDK coverage of query inputs, per-rule producer selection and paging remain deferred. |
| APIs and credentials | [APIs](#apis), [credentials](#credentials), [GraphQL](#graphql) and [hosted API operations](HOSTED_EXECUTION.md#captured-api-operations). Public reads use `auth: "none"`. The current captured profile uses JSON documents/responses and host-owned User-Agent. YAML API documents, additional codecs/raw responses and media negotiation require a later profile; the NDJSON section remains a proposal. |
| Channels and events | [Channels](#channels), [sources/consumers/triggers](#sources-consumers-and-triggers) and [publication](#publishing-events). Conventional event and channel forms remain governed by the [main specification](README.md). |
| Actions, goals and webhooks | [Captured goals](#goals) and the conventional [main specification](README.md) remain distinct. Spec-required goal inputs and webhook fields remain required even if an SDK makes them optional. Complete conventional OAuth, LLM-option and webhook field mappings are deferred. Retired filesystem secret sources must not be recommended; use the host's credential binding. |
| Lenses, focuses and agents | [Captured lenses](#lenses-and-watches) use handlers; conventional query and procedural/module lenses retain their separate forms in the [main specification](README.md). `vc` is an SDK formatting helper, not permission to replace procedural source with a graph query. Conventional focus null/default, builtin categories and skills follow that specification, even where SDK types are narrower. Agent-scope questions explicitly marked open there remain open, not portable defaults. |
| Views | `views` declares a captured list of named queries; `queries.views` instead references admitted views and does not declare them. Existing node/tabular, materialization and TTL semantics are in [Views](README.md#views--saved-queries-and-the-two-shapes-they-come-in) and [Virtual Cypher](VIRTUAL_CYPHER.md#8-views--a-saved-query-used-as-a-label). Parameter-choice coercion, audience, data-contract modes and whole-list refusal scope need a complete portable contract; SDK transformations are not normative. |
| Skills and model | [Shipped skills](#shipped-skills), [model call](#the-model-call) and [hosted model capability](HOSTED_EXECUTION.md#the-model-call). Full skill frontmatter/reference traversal and digest-format rules remain deferred. |
| Apps and write proposals | [Apps](#apps), [write proposals](#write-proposals); the host rechecks captured identity and grants before returning results or accepting effects. |
| Cross-realm composition | [Graph boundaries](LABELS_AND_COMPOSITION.md#definition-imports-and-realm-boundaries). `from.realm` is reserved and explicitly refused today. Future consent, version lookup, variants and policy-required provenance remain possible. |

The complete field-by-field conformance fixture suite remains future work. The worked
[composition examples](REALM_COMPOSITION.md) and dependency declarations are authoring
examples, not evidence that every host implements these rules. A host must publish its
supported profile and report unsupported behavior rather than claiming it ran successfully.

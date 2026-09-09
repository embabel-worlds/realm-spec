# Hosts retain Realm authority across sandbox execution

A host admits a captured Realm artifact and its requested capabilities before executing code.
The selected backend receives the program, bounded arguments and mediated callbacks. It does
not receive a World object, host filesystem path, credential store or provider token.

## Admission

An invocation retains its World, Realm installation, artifact digest, approval revision and
handler. Every host effect checks that retained authority. Retries and nested calls preserve
it; a newer approval does not authorize an older invocation. Removing a grant blocks later
operations but cannot undo an effect that has already completed.

A source grant has its own revision. It remains stable across unrelated handler or consumer
approval changes, allowing self-consumption and cyclic pipelines. Removing and reapproving a
source, changing its artifact or reinstalling the Realm invalidates the old source reference.
The host allocates revisions; Realm declarations and guest arguments cannot assign them.

```mermaid
flowchart LR
    Capture[Verified Realm capture] --> Target[Retained invocation]
    Approval[Owner grants] --> Target
    Target --> Backend[Selected sandbox backend]
    Backend --> Callback[Host callback]
    Approval --> Check[Current handler and source checks]
    Callback --> Check
    Check --> Journal[Bounded durable journal]
    Journal --> Receipt[Receipt after force]
    Journal --> Replay[Approved consumer replay]
    Replay --> Target
```

## Data pipes

A channel is a general data pipe. Discord messages, webhook events, database change feeds
and Realm-produced events can supply it. A channel may be inbound, outbound or bidirectional;
a live conversational connection is one provider adapter.

`data-pipes.yml` version 1 declares sources and consumers:

```yaml
version: 1
sources:
  - name: changes
    stream: events
    type: note.changed
consumers:
  - name: archive
    handler: notes.store
```

Either list may be omitted. Source and consumer names are unique within their own lists.
A source supplies its name, partition stream and event type. A consumer supplies its name
and a captured `namespace.function` handler. Neither declaration supplies credentials or
selects an owner World. Consumer names identify independent cursors.

Source approval grants publication. Consumer approval grants access to one exact source
reference and requires separate handler approval. Host-source references bind a World,
provider registration, source revision and stream. Realm-source references bind a World,
Realm installation, artifact digest, source name, source-grant revision and stream.

A host must reject unknown declaration fields, duplicate names or keys, YAML aliases/tags,
malformed Unicode and scalar coercion. The governed reference implementation limits the
file to 64 KiB and each list to 128 entries. Source field values are nonblank, exclude control
characters and occupy at most 256 UTF-8 bytes.

## Publication

A captured handler uses `gateway.channel.publish`; Wasm handlers access it through
`ctx.gateway.channel.publish`:

```typescript
const receipt = await gateway.channel.publish({
  source: "changes",
  eventId: input.eventId,
  streamId: input.streamId,
  occurredAt: input.occurredAt,
  payload: { noteId: input.noteId },
});
```

All five fields are required. `occurredAt` is an ISO instant and `payload` is a JSON object.
The host derives the owner, installation, event type and partition from the retained target
and verified declaration. `streamId` identifies a logical event stream within that partition.
It does not select another source or World.

Publication returns `{receiptId, offset, replayed}` after the durable append. Keep the event
ID, timestamp and payload stable on retry. An identical retry returns the original receipt;
conflicting content for the same event identity is refused. A receipt confirms acceptance,
not completed downstream effects.

The governed reference implementation accepts at most 64 KiB UTF-8 JSON with nesting depth
32. It rejects extra fields, duplicate keys, trailing JSON and invalid Unicode. Publication
requires a retained captured invocation; there is no generic HTTP publication tool.

## Polling positions

A captured poller reads its source cursor with `gateway.channel.position({source})`, which
returns `{position: string | null}`. It commits a page through `gateway.channel.publishBatch`:

```typescript
const { position } = await gateway.channel.position({ source: "changes" });
const receipt = await gateway.channel.publishBatch({
  source: "changes",
  batchId: page.id,
  expectedPosition: position,
  nextPosition: page.nextCursor,
  events: page.events,
});
```

Each event has `eventId`, `streamId`, `occurredAt` and object `payload`, with the same meaning
as single publication. All batch fields are required; only `expectedPosition` may be null.
The host appends the events and cursor change in one journal frame. A mismatched expected
position refuses the batch. An empty event list may advance the cursor. The receipt contains
`receiptId`, `offsets` and `replayed`.

Keep the batch ID, event identities, original timestamps, payloads and both positions stable
when retrying a page. An identical retry returns its original receipt; changed content under
the same batch ID is refused. A frame may already be durable when admission is revoked and
the response is refused. Admission is checked after force and before returning to the guest;
a retry still needs current authority. Receipt replay does not repeat the cursor update.

Position reads and batches require the current handler and same-installation source grant.
Requests cannot select an owner, World, installation or event type. A cursor belongs to the
logical source and its declared partition stream, not an event's `streamId`. Approving an
updated artifact preserves that logical cursor. A provider change or incompatible cursor
format needs a new source/stream identity or an explicit migration.

The reference host limits position requests to 8 KiB of UTF-8 JSON and batches to 1 MiB with
at most 256 events. Positions are nonblank opaque strings of at most 4 KiB UTF-8, without NUL.
Strict JSON parsing, journal payload limits and host/Realm storage caps also apply. These
callbacks work through Wasm and Docker. They support Realm-authored pollers using approved
schedules and API operations; automatic provider polling and webhook adapters remain separate.

## Replay

A consumer receives `offset`, `eventId`, `streamId`, `type`, `occurredAt`, `gap` and `payload`.
The envelope omits host paths, credentials and authority selectors. Processing retains the
source and consumer grants through host callbacks and nested calls. A checkpoint advances
only after the handler succeeds and admission remains current.

Delivery is at least once. A failed or interrupted handler keeps its durable offer for retry;
external effects need their own stable idempotency key. A completed Signal Bus handoff does
not confirm completion by every bus listener.

The reference implementation restores Realm source bindings on World load and rebuild.
After restart, replay begins when the owner World loads through startup warming or first
access. Provider connectors retain a separate approved lifecycle. Source discovery starts
no guest execution; the bounded replay scheduler performs delivery.

## Legacy event declarations

The reference host excludes live Realm `events/` files from runtime loading when captured
execution is selected. This covers scheduled polls, manual polls, webhook event projection
and declared-signal discovery, including a World previously loaded in compatibility mode.
The host checks the execution model before resolving live Realm directories.

Captured data-pipe publication and approved channel consumers keep their existing paths.
Generic captured polling and webhook event manifests remain unsupported. Explicit owner
webhook actions use a separate route. Declaration reads for authoring do not register a
source or grant execution.

## Capacity

Every Realm has finite host-enforced execution and storage limits. A dependency declaration
cannot increase them. Journal records, consumer control frames and recovery metadata count
against host storage policy. Exceeding a limit must refuse new writes without acknowledging
an uncommitted append or deleting unread records.

The reference journal defaults to 64 MiB shared across the host and 8 MiB of retained frame
bytes per World and Realm installation. A separate free-space check reserves 64 MiB. The
per-Realm charge spans all source names and streams. Reinstalling does not reclaim the old
installation's bytes from the shared limit.

By default, the reference journal reserves 25% of frame capacity for consumer control writes,
within both existing caps. The shared percentage applies after its metadata allowance.
Appends stop at the lower ceiling; adoption, offers and checkpoints may use the remaining
capacity. All frames consume append capacity. Hosts may configure 0–50%; zero disables the
reserve. Changing it affects new appends without rewriting existing data. A full total budget
can still block offers or checkpoints. Automatic compaction and retention are not implemented;
crash-safe replacement and recovery must also fit within the storage budget.

## Credentials and databases

Credentials remain in owner-scoped host storage. Guests refer to approved operations and
sources; they do not receive token values, wallet key names or a general credential lookup.
The host must constrain credential use to the approved destination and operation and keep
secrets out of guest results, error messages and logs. Ambient process environment variables
are not authority for a governed Realm.

External SQL belongs behind bound Virtual Cypher, approved producers or typed operations.
Use `params` for query values, including lists and nested objects. Raw `gateway.sql` access
is not a portable guest capability. Owner database setup selects a host-configured target
and its digest before storing credentials; target approval alone does not make it queryable.
Upgrade and revocation require the current installation and revision. Replacement approval
invalidates old access before removing its credentials. Revocation requires no database
connection and remains available when the configured target has been removed.

A private SQLite dependency serves the Realm's own computation or persistence. Its database,
WAL, snapshots and recovery overhead must fit that Realm's finite budget. It grants no access
to an external datasource. The host channel journal is a separate delivery facility.

## Captured API operations

A captured Realm may declare approved API operations in `apis/apis.yml` using vendored
OpenAPI documents. Each operation binds a fixed destination and a key from the owner's
wallet. In the governed profile, `token-env` identifies a wallet entry; it does not authorize
an environment-variable fallback. The guest supplies operation arguments, never credentials,
headers, server overrides or an alternative URL.

Owner preview shows the captured digest, installation revision, operation destination and
required wallet key name. Grant and revoke requests select the displayed installation and
revision. Granting an operation binds the current wallet value. Changing or deleting that
value prevents its use while the value is absent or differs from the approved value.
A different value requires approval. Restoring the identical approved value resumes access;
explicit operation or Realm revocation prevents that. Revocation remains available after
key deletion. These mutations advance the Realm installation revision, so
older retained invocations become stale.

The host checks the retained handler, consumer and operation grants and current credential
binding before network access and before returning data. API approval does not grant access
to another operation. Provider responses and errors must not expose the injected credential.
The provider itself is trusted with that credential: rejecting common echoes cannot prove
that a malicious provider has not transformed it into other response data. Revocation cannot
undo a request already accepted by the provider.

The reference profile supports:

| Declaration | Support |
| --- | --- |
| Specification | Vendored OpenAPI 3 JSON under `apis/`; no remote documents or external references. |
| Destination | One fixed HTTPS origin per API, port 443, validated public addresses and verified TLS hostname; no redirects. |
| Operations | Explicit GET operation IDs, at most 128 per Realm. |
| Arguments | At most 64 scalar path/query parameters and 64 KiB JSON; no body or caller headers. |
| Validation | Types, required fields, enum and string-length limits; numeric ranges and regex annotations remain provider validation. |
| Authentication | API key in a query parameter or header, or HTTP bearer token; optional fixed `X-` headers. |
| Response | At most 1 MiB of strict UTF-8 JSON; common credential echoes and diagnostic exception text are refused. |

The initial implementation rejects unsupported auth schemes, parameter references, alternative
servers, mutations and credential injection into HTTP framing/control headers. In captured
Worlds, live Realm API declarations do not create legacy tools or trigger credential
resolution. Approved operations are also available directly through the owner gateway and
its generated descriptors. An API-only Realm needs operation approval but no handler grant
or executable program. Previously discovered tools must refuse after an installation revision
change or revocation and while the wallet value differs from the approved value. Direct tools
retain the captured API contract even if source files change.

Captured API namespaces cannot shadow ordinary gateway tools or captured handlers. The
shared producer, enrichment, query-bound-operation and generic signal catalogs exclude
direct captured API tools until those callers carry retained authority. A legacy Realm
callback cannot use a direct owner tool to bypass its captured callback requirements.
Explicitly owner-authored World APIs keep their separate path. The API profile provides
neither a general credential lookup nor complete OpenAPI schema validation. Captured
handler producers can use the same approved API receiver. Graph-backed lens integration
remains open.

### Result admission

After a handler completes, the host rechecks its original retained target before returning
the result. Realm revocation, installation revision changes, lost consumer/source constraints
and interruption refuse a late result. The host does not replace stale authority with a
newer approval. Completed effects cannot be undone by this check.

## Backends and dependencies

The contract separates admission from backend selection. A host may implement Wasm, Docker
or another isolated backend while preserving retained identity, bounded I/O, mediated effects
and refusal behavior. A remote backend must preserve those checks and authenticate its
transport; backend placement does not grant access to credentials.

Captured Docker execution can load bundled CommonJS and JSON artifacts from
`dist/node_modules/`. The reference host verifies at most 256 runtime entries totaling 8 MiB
and resolves package main/index, subpaths, relative modules and cycles inside the container.
Missing imports have no host fallback. Package exports maps, ESM and native module loading
are unsupported. Bundled code receives no additional authority or credentials.

A Realm can declare exact package requirements in `dependencies/manifest.json`:

```json
{
  "version": 1,
  "runtime": "typescript",
  "dependencies": [
    { "ecosystem": "npm", "name": "formatters", "version": "1.2.3" }
  ]
}
```

The document is limited to 64 KiB and 128 unique ecosystem/name pairs. Nonempty
requirements need version 1. Unknown fields, duplicates, malformed values and version
ranges are refused. The optional runtime marker retains its existing language meaning.
An absent or empty dependency list requests no host packages.

The selected backend must admit every requirement before binding and execution. A backend
with no package support refuses nonempty requests. Requirements remain bound to captured
program content; editing source files does not change them. Declarations do not select a
sandbox, registry, command, path or credential.

The reference Docker adapter accepts bundled npm packages with matching name and exact
semantic version in `dist/node_modules/<name>/package.json`. Metadata is strict JSON with
a 64 KiB limit. The entrypoint must exist within the package, using supported CommonJS/JSON
file or index resolution. Exports maps, ESM and `gypfile: true` are refused; native modules
remain unsupported. These declarations check required root packages; they do not limit
imports from other modules already included in the same bounded capture.

No download, installation or registry resolution occurs. Libraries compiled into a Wasm
program remain part of that artifact; the reference Wasm backend supplies no host packages.
Other ecosystems, runtime provisioning and private database persistence remain open.
Unsupported storage requirements must be rejected before handler execution. No VFS syntax
is introduced here.

## Reference implementation

The governed implementation is tracked in [embabel/me#1091](https://github.com/embabel/me/pull/1091).
Its current support is narrower than some trusted-host examples in the main specification:

| Capability | State |
| --- | --- |
| Captured Wasm and Docker handlers, type methods and schedules | Retained approval checks; scheduled calls also require the action process caller to match the owner World. The bounded handler schema profile validates inputs before dispatch and outputs before final admission. |
| [Captured command aliases](README.md#commands) | Strict versioned metadata, owner discovery and direct chat dispatch to approved same-installation handlers. |
| Approved provider lifecycle and durable journal delivery | Implemented for Discord, Slack and Telegram. |
| Captured source/consumer approval and publication | Implemented with World-load source discovery. |
| Scheduled API-to-channel handlers | Verified composition of captured schedules, approved GET operations, durable publication and consumer replay. Provider cursor persistence remains open. |
| Captured callback to an approved sibling | Implemented within the same installation. |
| Captured API operations and wallet bindings | Implemented for the GET profile; Movie Wasm tests cover query-key and header-key authentication. |
| Captured handler lenses | Versioned same-installation bindings; bounded JSON results, original-target refresh and prepared background runs. Completion and response checks retain admission; revocation clears stored data. Active work and settled storage are capped. Cache reuse is disabled. Opt-in content results hydrate owned focus under retained graph approval and select compatible built-in views; executable presentations are excluded. |
| Legacy Realm lenses | Excluded in captured Worlds, including previously loaded definitions and retained views. Owner lenses remain available; cached results are isolated by owner. Versioned handler bindings use the captured route. |
| Captured handler producers | Version-1 same-installation bindings, JSON batch keys and bounded record arrays. Owner precedence, retained World/approval checks, cancellation and call budgets apply. No result cache, paging or pushdown. Graph materialization preserves owner boundaries and host metadata. |
| Collection sources and shared mirrors | Live and warmed Realm source metadata excluded in captured mode; public labels and shared mirrors require separate trusted host configuration. Captured source approval and mirror/coverage receivers remain open. |
| Captured Virtual Cypher and other host-resource callbacks | Refused pending retained resource receivers. |
| Owner database target approval | Adoption, upgrade and revocation implemented; runtime datasource use still needs integration. |
| Captured Docker CommonJS dependencies | Implemented for bounded, verified bundles; no runtime package installation. |
| Additional dependency ecosystems, private Realm database persistence and VFS | Not implemented on this path. |
| Firecracker, generalized remote backends and resumable arbitrary computation | Not implemented. |

Hosts must state which profile and capabilities they support. Generated types describe an
operation's contract; they do not grant permission or prove receiver availability.

## Me captured graph-query profile


`ctx.gateway.cypher.query({cypher, params})` reads owned graph data and returns
`{rows, warnings}`. Pass values through `params`, as a JSON object or a JSON string.
The owner must approve `cypher_query` separately from the handler. List resources at
`GET /realms/{realmName}/resource-approvals`; grant or revoke with
`POST /realms/{realmName}/resource-approvals/cypher_query/{grant|revoke}` and
`{installationId, expectedRevision}`. Each change advances the installation revision.

Name every node and end the statement with a literal `LIMIT` between 1 and 512.
Every matched node must carry consistent ownership for the caller. Shared-label
exemptions, explicit sharing, anonymous nodes, variable-length paths, collection
construction, procedures and model-backed functions are outside this profile.
Ordinary scalar functions and numeric aggregates are supported. Named host views,
source mirrors and diagnostic probes are not expanded or invoked.

Queries use the existing scoped Cypher executor and virtual join engine. Only
captured producers from the same installation can run. Their callbacks retain the
querying handler's admission and each API operation still needs its own approval.
Legacy SQL, model-backed producers and implicit identity enrichment are excluded.
Producer records have no shared query cache, and materialization is rolled back.

Requests are capped at 128 KiB, with 16 KiB statements and 128 parameters. Results
are capped at 512 rows and 1 MiB. The Neo4j runner uses a 15-second transaction
limit and buffers at most 4,096 rows or 4 MiB per internal statement. These buffering
limits apply after driver decoding; database memory limits remain deployment
configuration. Engines without a bounded runner refuse captured queries.

```typescript
const result = await ctx.gateway.cypher.query({
  cypher: "MATCH (b:Bill) WHERE b.status = $status RETURN b LIMIT 100",
  params: { status: "unpaid" },
});
```

`CapturedRealmQueriesTest` covers real Wasm and Docker, owned graph reads, retained grants,
same-installation producer materialization, rollback and nested API readmission.

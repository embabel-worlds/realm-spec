# World Provider Protocol

> **Status: proposal.** Nothing here is implemented yet. This document fixes the shape before any
> code exists, because a protocol, unlike a host feature, is hard to change after it ships. Section
> 10 describes the Spring Boot provider, which is the planned reference implementation. That section
> is informative; the rest is the contract.

An application that already holds business data should not need a realm author to work out its
API. Today every Virtual Cypher producer reaches into a system that does not know a world exists,
and a realm spends most of its YAML reverse-engineering what that system does: how it pages,
which filters it can apply itself, which key it echoes back, how expensive a call is, and how long
an answer stays true. `learn_source` exists because the other side will not say.

This protocol is the other side saying it. An application that speaks it — a **provider** —
publishes what it chooses to expose, in the shapes it chooses, with its own answers to batching,
filtering, paging, cost, caching and identity. A world that is given the provider's URL — the
**host** — reads that declaration and installs the provider as a realm. Nobody writes the realm.

Three things follow, and they are the reason for the protocol:

- **The world side is one URL.** The owner pastes the provider's URL into the world, supplies a
  credential if the provider asks for one, and is done. Types, joins, spine bindings, verbs and
  cache policy all come from the provider.
- **The world sees what the programmers decided it should see.** A provider exposes its
  application's own types and operations, through the same layer its user interface uses, with
  the same authorization. The host cannot reach anything the provider did not declare.
- **Identity bridging can live in code.** A provider can resolve a spine key — an email, a
  domain, a customer account — to its own records in its own code, where the knowledge of how
  its ids relate to the world's actually lives (§6).

The protocol is language-neutral: HTTP and JSON, with nothing that assumes the provider's language,
framework or data store. The reference provider is a Spring Boot starter; the conformance kit
(§11) is what makes a provider in any other language trustworthy.

---

## 1. Roles and direction

| Role | Who | Does |
|---|---|---|
| **Provider** | The application | Serves the protocol. Never needs to know a host exists. |
| **Host** | An Embabel world | Is given the provider's URL, reads its manifest, calls it at query time. |

**The host calls the provider. The provider never has to call the host.** An existing application
should not have to discover, register with, or hold a credential for a world in order to be useful
to one. Every provider-to-host direction in this document is an optional extension (§8), off unless
the application's owner configures it.

A provider may be installed into many worlds. It does not know or care how many.

## 2. Transport and conventions

- HTTPS. Plain HTTP is accepted only for a provider on the host's own network, and the host says so
  when installing it.
- Request and response bodies are JSON (`application/json`, UTF-8).
- Every operation lives at a fixed path relative to the **provider URL** — the URL the owner was
  given. Nothing in the protocol is located by a URL the manifest names, so a manifest cannot
  redirect the host somewhere else.

| Operation | Method and path | § |
|---|---|---|
| Manifest | `GET {provider}` | 3 |
| Fetch by keys | `POST {provider}/fetch` | 4.1 |
| Query | `POST {provider}/query` | 4.2 |
| Invoke a verb | `POST {provider}/verbs/{name}` | 5 |
| Changes | `GET {provider}/changes` | 7 |

- Errors are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details with a `code` from
  the table in §4.4. The host classifies by `code` and HTTP status, never by message text.
- Unknown fields are ignored on both sides. Evolution within a protocol version is additive.

### 2.1 Values

Records join on keys, and keys join only if both sides write them identically. So the value rules
are strict where a lenient rule would quietly break a join.

| Type | JSON form |
|---|---|
| `string` | string |
| `boolean` | `true` / `false` |
| `integer` | number when it fits in ±2^53, otherwise a string of decimal digits |
| `decimal` | **string** in plain decimal notation (`"1234.50"`), never exponent notation, never a JSON number |
| `date` | `"2026-10-10"` |
| `datetime` | RFC 3339 with an offset (`"2026-10-10T09:30:00Z"`) |
| `duration` | ISO 8601 (`"PT15M"`) |
| `enum` | string, one of the declared values |
| `list` | array of one scalar type |

**Keys are always strings on the wire**, in the canonical form of their declared type: an integer
key `42` is sent and echoed as `"42"`, never `42.0` or `"4.2E1"`. A provider that receives a key it
cannot parse as the declared type treats it as missing (§4.1), not as an error.

`null` means "this record has no value here". A property absent from a record means the same. The
two are never used to signal anything else.

## 3. The manifest

`GET {provider}` returns the manifest. It is the whole of what the host knows about the provider,
and the host builds the realm from it alone. It carries an `ETag`; the host revalidates with
`If-None-Match` and rebuilds the realm when it changes.

```json
{
  "protocol": "1",
  "name": "billing",
  "title": "Billing",
  "description": "Customers, invoices and payments from the billing system.",
  "auth": { "schemes": ["bearer"], "actingUser": "required" },
  "types": [ ... ],
  "verbs": [ ... ],
  "changes": { "supported": true }
}
```

| Field | Meaning |
|---|---|
| `protocol` | The protocol major version. A host refuses a version it does not speak, and says which. |
| `name` | The realm name the provider asks for. The host prefixes it (`provider-billing`) and resolves collisions; the provider does not choose the final name. |
| `title`, `description` | Shown to the owner on install and to models that read the realm brief. Write them for both. |
| `auth` | §3.4. |
| `types` | §3.1. |
| `verbs` | §5. |
| `changes` | Whether `GET /changes` exists (§7). |

### 3.1 Types

A type is what the provider exposes, **not its storage model**. In a layered application it is the
shape the service layer returns — a DTO or projection — and that is deliberate: the provider decides
what the world sees, at the layer where it already decides what its own UI sees.

```json
{
  "name": "Customer",
  "description": "A company that buys from us.",
  "identity": "id",
  "properties": {
    "id":      { "type": "integer" },
    "name":    { "type": "string" },
    "website": { "type": "string", "spine": "Organization" },
    "billingEmail": { "type": "string", "spine": "Person" },
    "tier":    { "type": "enum", "values": ["free", "pro", "enterprise"] },
    "balance": { "type": "decimal", "description": "Outstanding, in the account currency." }
  },
  "lookups": [
    { "by": "id", "maxKeys": 500 },
    { "by": "website", "maxKeys": 200 },
    { "by": "billingEmail", "maxKeys": 200 }
  ],
  "query": {
    "filters": {
      "tier":    ["eq", "in"],
      "balance": ["gt", "gte", "lt", "lte"],
      "name":    ["prefix"]
    },
    "sort": ["name", "balance"],
    "maxPageSize": 200,
    "total": true
  },
  "cache": { "scope": "user", "ttlSeconds": 300, "negativeTtlSeconds": 3600 },
  "cost": { "maxRequestsPerSecond": 20, "maxConcurrency": 4 }
}
```

| Field | Meaning |
|---|---|
| `name` | The label in the world, before the host applies the realm's namespace. |
| `identity` | The property that identifies a record of this type. It must also be a lookup. |
| `properties` | Name → `{type, description?, spine?, values?, item?}`. `item` is the element type of a `list`. Only declared properties are read from records; anything else a record carries is dropped. |
| `lookups` | The properties the provider can fetch by, in batches (§4.1). Relationships (§3.2) and identity bridging (§6) are lookups too. |
| `query` | Present if the type can be listed and filtered (§4.2). Absent means it cannot; the type is reached only through lookups. |
| `cache` | §3.3. |
| `cost` | Pacing the host must observe across all its calls to this type. |

**A lookup is the one join primitive.** Fetch by identity, follow a foreign key, resolve a spine
key to records: each is "give me the records whose property `P` is one of these values", and each
is declared once, with its own batch limit.

### 3.2 Relationships

A relationship is a foreign key the provider exposes, plus a lookup that makes it traversable.

```json
{
  "name": "Invoice",
  "identity": "number",
  "properties": {
    "number":     { "type": "string" },
    "customerId": { "type": "integer", "references": { "type": "Customer", "relationship": "BILLED", "direction": "in" } },
    "amount":     { "type": "decimal" },
    "dueDate":    { "type": "date" },
    "status":     { "type": "enum", "values": ["draft", "open", "paid", "void"] }
  },
  "lookups": [
    { "by": "number", "maxKeys": 500 },
    { "by": "customerId", "maxKeys": 100 }
  ]
}
```

`references` says `Invoice.customerId` holds a `Customer`'s identity. `direction: "in"` makes the
edge `(:Customer)-[:BILLED]->(:Invoice)`; `"out"` would point it from the invoice. The host
traverses it both ways:

- From a customer to its invoices, by the lookup on `customerId`. A reference with no lookup on its
  property is traversable only from the invoice side, and the host says so when it installs.
- From an invoice to its customer, by the lookup on `Customer.id`.

The referenced type must be in the same manifest. A provider never names another realm's types;
reaching across realms is what spines are for (§6).

### 3.3 Caching

The provider knows how long its answers stay true. The host does not, and every guess it makes is
wrong for somebody.

| Field | Meaning | Default |
|---|---|---|
| `scope` | `shared`: one answer for every user of the world. `user`: the answer depends on the acting user (§3.4), and the host caches per user or not at all. | `user` |
| `ttlSeconds` | How long a fetched record may be reused. `0` means never. | `0` |
| `negativeTtlSeconds` | How long "no record for this key" may be reused. | `0` |
| `immutable` | Records never change once they exist. Reference data. | `false` |

**The default scope is `user` because the safe mistake is a cache miss.** A provider that declares
`shared` is stating that its authorization does not vary the answer for this type. A host that has
the changes feed (§7) may hold records longer than `ttlSeconds` and invalidate on change instead.

A **failed** fetch is never negatively cached. "Could not ask" must not become "asked, and there was
nothing".

### 3.4 Authentication and the acting user

Two separate questions: whether the *host* may call the provider, and *on whose behalf*.

**The host authenticates as a client of the provider.** `auth.schemes` lists what the provider
accepts: `bearer`, `basic`, `mtls` or `none`. The owner supplies the credential when installing,
and the host keeps it in the world's wallet. It never appears in a realm file.

**The acting user travels separately**, in an `Embabel-Acting-User` header on every operation: a
signed JWT the host issues, carrying the world user's subject and verified email. The host
publishes its signing keys at a JWKS URL the provider is configured with. The provider maps that
identity onto its own principal, using its own rules, and applies its own authorization — the same
as it would for that person in its own UI.

| `auth.actingUser` | Meaning |
|---|---|
| `required` | Every call must carry an acting user. Calls that cannot (a scheduled job with no user) are refused by the provider, and the host does not attempt them. |
| `optional` | The provider uses the acting user when present and its service identity otherwise. |
| `ignored` | The provider answers the same for everyone. Implies `cache.scope: shared` is safe. |

The provider is the authority on what a user may see. The host never filters a provider's answer
for authorization; it only refrains from sharing an answer the provider said was per-user.

## 4. Reading

### 4.1 Fetch by keys

```http
POST {provider}/fetch
```

```json
{ "type": "Invoice", "by": "customerId", "keys": ["17", "42", "99"] }
```

```json
{
  "records": [
    { "number": "INV-1001", "customerId": "17", "amount": "1200.00", "dueDate": "2026-10-31", "status": "open" },
    { "number": "INV-1002", "customerId": "17", "amount": "80.00",   "dueDate": "2026-09-30", "status": "paid" }
  ],
  "missing": ["42"],
  "failed": ["99"]
}
```

The batch contract, which every provider must keep:

- **All keys in one call**, up to the lookup's `maxKeys`. The host splits larger batches; the
  provider never receives more than it declared.
- **Every record carries the lookup property** with a value equal to one of the requested keys, in
  canonical form. That is how the host attaches each record to its anchor; a record without it is
  dropped and reported.
- **Every requested key is accounted for**: it has at least one record, or it is in `missing` (the
  provider looked and there is nothing), or it is in `failed` (the provider could not answer for
  it). A key in none of the three is treated as `failed`.
- `missing` may be negatively cached (§3.3). `failed` never is.
- A lookup on a non-identity property may return many records per key. A lookup on `identity`
  returns at most one.

A provider that holds only a single-record operation internally — `findById` — may loop over the
keys itself. That loop runs inside the provider, next to its data, which is still far cheaper than
the host making one HTTP call per key. It should declare a modest `maxKeys` to match.

### 4.2 Query

```http
POST {provider}/query
```

```json
{
  "type": "Customer",
  "filters": [
    { "property": "tier", "op": "in", "value": ["pro", "enterprise"] },
    { "property": "balance", "op": "gt", "value": "10000" }
  ],
  "sort": [{ "property": "balance", "direction": "desc" }],
  "pageSize": 50,
  "cursor": null
}
```

```json
{
  "records": [ ... ],
  "applied": [0, 1],
  "sorted": true,
  "next": "eyJvZmZzZXQiOjUwfQ",
  "total": 312
}
```

**Filters are a conjunction.** Each names a property, an operator the type declared for it under
`query.filters`, and a value. The operators are `eq`, `in`, `gt`, `gte`, `lt`, `lte` and `prefix`.
The host sends only declared combinations. Anything else the query asks for — a disjunction, a
`CONTAINS`, a function of a value — the host evaluates itself over what the provider returns.

**`applied` and `sorted` say what the provider actually did.** `applied` lists the indexes of the
filters it applied; `sorted` says whether the records honour `sort`. The host re-applies every
filter to the returned records regardless, so a provider that applies less than it declared
returns the same answer more slowly. But the host pushes a `LIMIT` down only when every filter was
applied and the order was honoured, because only then are the first N records the right N. The
echo is what lets the host know that, per call, instead of trusting a declaration.

**Paging is by opaque cursor.** `next` is a string to send back as `cursor`, or `null` at the end.
`total`, if the type declared `query.total`, is the number of records the filters match across all
pages; it lets the host fetch the remaining pages concurrently.

**Nothing is ever silently cut short.** A provider that stops early for its own reasons — a cap, a
timeout — answers with `"truncated": { "reason": "..." }`, and the host carries that warning into
the query result. A page that ends a walk without `next` and without `truncated` is a promise that
the walk is complete.

### 4.3 Limits

| Limit | Value |
|---|---|
| Keys per fetch | the lookup's `maxKeys`, at most 1000 |
| Records per page | the type's `maxPageSize`, at most 1000 |
| Response body | 16 MiB |
| Cursor | 2048 bytes |

A provider that answers over a limit is refused with `RESULT_BOUND`, never truncated by the host.

### 4.4 Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `UNAUTHENTICATED` | 401 | The host's credential was missing or wrong. |
| `FORBIDDEN` | 403 | The acting user may not do this. |
| `ACTING_USER_REQUIRED` | 401 | The manifest said `required` and none was sent. |
| `UNKNOWN_TYPE` | 404 | Not a type in the current manifest. The host revalidates the manifest. |
| `UNSUPPORTED` | 400 | A lookup, filter, operator or sort the type did not declare. |
| `KEY_BOUND` | 400 | More keys than `maxKeys`. |
| `RATE_LIMITED` | 429 | With `Retry-After`. |
| `UNAVAILABLE` | 503 | Temporarily unable to answer. Never negatively cached. |
| `RESULT_BOUND` | — | Host-side: the answer was over a limit in §4.3. |

## 5. Verbs

A verb is an operation the provider lets the world perform: issue a refund, assign a ticket,
recalculate a quote. It is the application's own service operation, behind its own validation and
authorization.

```json
{
  "name": "sendReminder",
  "description": "Email the customer a reminder for an overdue invoice.",
  "subject": "Invoice",
  "input":  { "type": "object", "properties": { "number": { "type": "string" }, "note": { "type": "string" } }, "required": ["number"] },
  "output": { "type": "object", "properties": { "sentTo": { "type": "string" } } },
  "effect": "external",
  "idempotent": false
}
```

| Field | Meaning |
|---|---|
| `subject` | Optional. The type the verb acts on, so the host can offer it from a record. |
| `input`, `output` | JSON Schema (2020-12). The host validates `input` before calling. |
| `effect` | `read`: no change anywhere. `write`: changes the provider's own data. `external`: has an effect outside the provider that cannot be taken back — an email sent, a payment made. |
| `idempotent` | Whether repeating the same call is safe. |

`POST {provider}/verbs/{name}` carries the input as its body, the acting user, and an
`Idempotency-Key` header the host generates per logical attempt and reuses on retry. A provider
that has seen that key returns the first answer again.

**The host decides who may call a `write` or `external` verb, and when.** It routes them through the
world's approvals, exactly as it routes any other consequential action. The provider declares the
effect; the host decides what that effect requires. The provider still enforces its own
authorization on every call, approved or not.

## 6. Spines and identity bridging

A provider's records join the rest of the world through **spines** — the single node a person, a
company or another shared entity resolves to ([VIRTUAL_CYPHER.md §5.4](VIRTUAL_CYPHER.md#54-entity-canonicalization--the-spines-a-join-anchors-on)).
There are two ways for a provider to attach, and a provider can use both.

**A spine-bound property.** `"spine": "Organization"` on `Customer.website` is the protocol's form of
`hub: Organization`: the host normalizes the value by the spine's rules and the record attaches to
that company's `Organization` node. Nothing more is asked of the provider. The spine may be a
built-in (`Person`, `Organization`) or one a realm in the world declares (`CustomerAccount`); a
binding to a spine the world does not have is inert, and the host reports it on install rather than
failing.

**A lookup by a spine-bound property** turns that attachment into a two-way join. Because
`Customer` declares `{ "by": "website" }`, a query anchored on an `Organization` the world already
knows — from email, from a CRM realm, from anywhere — can ask the provider which customers that
company is, in one batched call. This is identity bridging, and **the provider does it in code**:

- It can match on whatever it knows. Several websites per customer, billing contacts, a domain
  alias table, a merger history — all of it is the provider's to consult when answering
  `fetch by website`.
- It returns records carrying the requested key, exactly as for any lookup (§4.1), so the host
  attaches each to the spine node it asked about.
- `missing` is a real answer: this company is not one of our customers. The host may cache that for
  `negativeTtlSeconds`.

The host normalizes keys **before** sending them: a provider looked up by `Organization` receives
registrable domains, lower-cased; by `Person`, lower-cased emails. It never sees the variety of
forms the world collected them in, and it need not normalize again.

What a provider cannot do is assert identity between spine nodes, or attach a record to a spine by
anything but a declared property. Spine resolution stays deterministic and stays the host's.

## 7. Changes

A provider that can say what changed lets the host stop guessing with TTLs.

```http
GET {provider}/changes?since={cursor}
```

```json
{
  "changes": [
    { "type": "Invoice", "key": "INV-1002", "op": "upsert", "at": "2026-10-10T09:30:00Z" },
    { "type": "Customer", "key": "42", "op": "delete", "at": "2026-10-10T09:31:12Z" }
  ],
  "next": "c-000173"
}
```

- Without `since`, the provider returns no changes and a `next` cursor for "from now".
- `key` is the record's identity. The host evicts and refetches; the feed is an invalidation
  signal, not a replication stream, so it carries no record bodies.
- A provider may answer `410 Gone` for a cursor it no longer holds. The host then drops its cache
  for that provider and starts again from now.
- The host polls. How often is the host's decision; the provider may answer `Retry-After`.

Because the host polls, a provider offering changes still never has to know the host exists.

## 8. Optional provider-to-host extensions

Some deployments want the provider to reach the host. Each of these is an extension the
application's owner turns on deliberately; none is required, and a host must work with a provider
that has none of them.

| Extension | Why |
|---|---|
| **Change push** | The provider POSTs its change entries (§7) to a host ingress URL, instead of being polled, for lower latency. |
| **Outbound tunnel** | The provider holds an outbound connection to the host and receives operations over it. For a provider behind a firewall the host cannot reach. The operations and their semantics are unchanged; only who opened the socket differs. |

Both require configuring the provider with a host URL and a credential, which is exactly the
coupling the core protocol avoids. They are specified separately when they are built.

An application that wants to *consume* a world — run its views, query its graph — uses the world's
existing REST and GraphQL doors. That is a client of the world, not this protocol.

## 9. How the host installs a provider

This is what makes the world side one URL. Given `https://billing.example.com/embabel`:

1. `GET` the manifest. Refuse an unsupported `protocol` and say which version the host speaks.
2. Ask the owner for a credential if `auth.schemes` needs one, and keep it in the wallet.
3. Synthesize a realm, entirely from the manifest:

| Manifest | Realm |
|---|---|
| `types[]` | `types/` entries, namespaced under the realm |
| `identity` | `identity: true` on that property |
| `spine` on a property | `hub: <spine>` on that property |
| each `lookup` | a producer of kind `provider`, keyed by that property, with the lookup's `maxKeys` as its batch size |
| `references` | a join between the two types, through the lookup on the referencing property |
| a lookup by a spine-bound property | a join anchored on that spine |
| `query` | a scan producer whose declared filters and sort are its pushdown |
| `cache`, `cost` | the producers' cache policy and pacing |
| `verbs[]` | gateway operations, with writes routed through approvals |

4. Validate it like any other realm, install it, and report anything inert: a spine the world does
   not have, a reference with no lookup behind it.

The synthesized realm is not written by anybody and is not edited by anybody. A change to the
manifest is a change to the realm. An owner who wants more — views over the provider's types, DERIVE
rules, an app — writes an ordinary realm that depends on it.

The `provider` producer kind is new. Its behaviour is the batch contract of §4.1 and the query
contract of §4.2 and nothing else; it takes no authored query and no configuration beyond what the
manifest says.

## 10. The Spring Boot provider (informative)

The reference provider is a Spring Boot starter. Adding the dependency exposes the protocol at a
configured path; nothing is exposed until the application marks something to expose.

### 10.1 It binds at the service layer, not the repository

A Spring application is layered on purpose. Its service layer is where transactions begin, where
`@PreAuthorize` and method security apply, where invariants hold and derived fields are computed,
and where the application decides what leaves it. A provider that read the repositories directly
would skip all of that. Spring Data REST took that road, and it is the main criticism of it.

So the starter is an **inbound adapter**, a peer of the application's `@RestController`s. It calls
the same service methods the web layer calls, through the Spring proxy, with the acting user
established in the `SecurityContext`. Every transaction boundary, security rule and audit hook
applies exactly as it does for a request from the UI.

```java
@Service
public class CustomerService {

    @WorldLookup(type = "Customer", by = "id", maxKeys = 500)
    @PreAuthorize("hasRole('ACCOUNTS')")
    public List<CustomerView> findByIds(Collection<Long> ids) { ... }

    @WorldLookup(type = "Customer", by = "website", maxKeys = 200)
    public List<CustomerView> findByWebsites(Collection<String> domains) {
        /* The identity bridge, in code: match primary sites, aliases and pre-merger domains. */
        ...
    }

    @WorldQuery(type = "Customer")
    public Page<CustomerView> search(CustomerFilter filter, Pageable pageable) { ... }

    @WorldVerb(effect = Effect.EXTERNAL)
    public ReminderResult sendReminder(String invoiceNumber, String note) { ... }
}
```

`@WorldLookup`, `@WorldQuery` and `@WorldVerb` are proposed names. The annotations mark what the
developer has decided the world may see; the developer still writes the method, which is the point.

### 10.2 Spring Data types are vocabulary, not a data path

The starter reads the method signature and declares only what it finds. Most of that vocabulary is
Spring Data's, which service methods already take and return:

| Signature | Manifest |
|---|---|
| `Collection<K>` parameter | a lookup that takes a batch |
| a single `K` parameter | a lookup the starter loops over, with a small `maxKeys` |
| `Pageable` | paging, and `maxPageSize` from the configured cap |
| `Sort`, or the sort in `Pageable` | sortable properties, from the type's properties |
| a filter object's fields | `eq` per scalar field, `in` per collection field, ranges per `Range<T>` field |
| `Page<T>` return | `query.total: true` |
| return element type | the type's properties, from its record or bean properties |
| `@PreAuthorize` / method security present | `cache.scope: user` unless the type says otherwise |

The JPA or Spring Data mapping metamodel may *suggest* relationships while the developer writes the
annotations, in tooling. It never becomes a way to fetch.

**One exception, explicit and per type:** reference data and CQRS read models often have no service
logic to skip. `@WorldType(repository = CountryRepository.class)` exposes a repository directly, and
the starter uses `findAllById` for the identity lookup and `JpaSpecificationExecutor` or
`QuerydslPredicateExecutor`, when the repository has one, for query pushdown. It is never the
default and never applied to a type that was not named.

## 11. Conformance

A protocol is only as good as the second implementation of it. The conformance kit is a test suite
that runs against any provider URL and checks every MUST in this document: the batch contract, key
canonical forms, `missing` versus `failed`, `applied` honesty against the declared filters, cursor
termination, truncation reporting, idempotency keys, error codes. A provider in C#, TypeScript,
Python, Go or anything else is conformant when the kit passes. Porting the Spring provider is not
the requirement.

## 12. Prior art

- **GraphQL Federation**'s `_entities(representations)` is batched entity resolution by key across
  services — the closest precedent for §4.1. This protocol adds declared cost, cache semantics,
  pushdown capability and the acting user, and drops the query language.
- **OData's capabilities vocabulary** (`FilterRestrictions`, `SortRestrictions`) is the precedent
  for declaring per property what a source can filter on (§3.1).
- **RFC 9457** problem details for errors; **JSON Schema 2020-12** for verb input and output.

## 13. Open questions

- **Acting-user trust.** A host-signed JWT needs the provider configured with the host's JWKS URL —
  one piece of host knowledge on the provider side. Is that acceptable as the price of per-user
  authorization, or should `actingUser` default to `ignored` and per-user be the opt-in?
- **Text search.** `prefix` is the only text operator. A provider with its own search (a
  `search(String)` service method) would serve the `remote-search` relevance contract; it needs a
  shape here.
- **Aggregates.** "Total balance by tier" fetches every customer. A declared aggregate operation
  would push the reduction down; it would also make the host's correctness depend on the provider's
  arithmetic.
- **Manifest size.** A provider with hundreds of types — an ERP — may need the manifest paged or
  split by module.
- **Writes as records.** Verbs cover consequential operations. Whether a provider should also accept
  plain creates and updates against its types, or whether those must always be verbs, is undecided.

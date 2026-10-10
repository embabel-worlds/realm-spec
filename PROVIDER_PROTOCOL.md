# World Provider Protocol

> **Status: proposal.** Nothing here is implemented yet. This document fixes the shape before any
> code exists, because a protocol, unlike a host feature, is hard to change after it ships. Section
> 10 summarizes the Spring Boot provider ([PROVIDER_SPRING.md](PROVIDER_SPRING.md)), the planned
> reference implementation, and §14 collects futures. Both are informative; the rest is the contract.

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
to one. Every provider-to-host direction in this document — push delivery (§7.3) and the tunnel (§8) — is optional, off unless
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
| Realm documents and skills | `GET {provider}/{about}`, `GET {provider}/skills/{name}/…` | 3.7 |
| Fetch by keys | `POST {provider}/fetch` | 4.2 |
| Query | `POST {provider}/query` | 4.3 |
| Aggregate | `POST {provider}/aggregate` | 4.4 |
| Invoke a verb | `POST {provider}/verbs/{name}` | 5 |
| Changes | `GET {provider}/changes` | 7.1 |
| Events | `GET {provider}/events` | 7.2 |
| Subscribe to push delivery | `POST {provider}/subscriptions` | 7.3 |

- Errors are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details with a `code` from
  the table in §4.6. The host classifies by `code` and HTTP status, never by message text.
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
| `list` | array of one scalar type, or of parts (§3.5) |
| `object` | a nested object with declared properties — a value (§3.5) |

**Keys are always strings on the wire**, in the canonical form of their declared type: an integer
key `42` is sent and echoed as `"42"`, never `42.0` or `"4.2E1"`. A provider that receives a key it
cannot parse as the declared type treats it as missing (§4.2), not as an error.

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
  "changes": { "supported": true },
  "events": [ ... ],
  "eventRetention": "P7D",
  "delivery": { "push": true }
}
```

| Field | Meaning |
|---|---|
| `protocol` | The protocol major version. A host refuses a version it does not speak, and says which. |
| `name` | The realm name the provider asks for. The host prefixes it (`provider-billing`) and resolves collisions; the provider does not choose the final name. |
| `title`, `description` | Shown to the owner on install and to models that read the realm brief. Write them for both. |
| `version`, `about`, `skills`, … | Realm metadata and skills (§3.7). |
| `auth` | §3.4. |
| `types` | §3.1. |
| `verbs` | §5. |
| `changes` | Whether `GET /changes` exists (§7.1). |
| `events`, `eventRetention` | The events the provider publishes, and how long it keeps them (§7.2). |
| `delivery` | Whether the provider can push events and changes to a host that subscribes (§7.3). |

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
  "filter": {
    "properties": {
      "tier":    ["eq", "ne", "in", "notIn"],
      "balance": ["eq", "gt", "gte", "lt", "lte", "between", "isNull"],
      "name":    ["eq", "ieq", "prefix", "iprefix", "icontains"]
    },
    "logic": ["and", "or", "not"],
    "exists": ["Invoice.customerId"]
  },
  "sort": ["name", "balance"],
  "project": true,
  "query": { "maxPageSize": 200, "total": true, "search": true },
  "aggregate": {
    "groupBy": ["tier"],
    "measures": { "count": true, "sum": ["balance"], "avg": ["balance"], "min": ["balance"], "max": ["balance"] }
  },
  "cache": { "scope": "user", "ttlSeconds": 300, "negativeTtlSeconds": 3600 },
  "cost": { "maxRequestsPerSecond": 20, "maxConcurrency": 4 }
}
```

| Field | Meaning |
|---|---|
| `name` | The label in the world, before the host applies the realm's namespace. |
| `identity` | The property that identifies a record of this type. It must also be a lookup. |
| `properties` | Name → `{type, description?, spine?, values?, item?, properties?, references?}`. `item` is the element type of a `list`; `properties` are an `object`'s (§3.5). Only declared properties are read from records; anything else a record carries is dropped. |
| `lookups` | The properties the provider can fetch by, in batches (§4.2). Relationships (§3.2) and identity bridging (§6) are lookups too. A lookup that can cap its records per key adds `"limitPerKey": true`. |
| `filter` | What the provider can evaluate itself, in fetches, queries and aggregates alike (§4.1). Absent means nothing. |
| `sort` | Properties the provider can order by. |
| `project` | The provider honours `fields` and returns only the properties asked for (§4.1). |
| `query` | Present if the type can be listed without keys (§4.3). Absent means it cannot; the type is reached only through lookups. |
| `aggregate` | Reductions the provider can compute itself (§4.4). |
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

The referenced type must be in the same manifest, or in a sibling realm of the same application (§3.6).
A provider never names any other realm's types; reaching across applications is what spines are for (§6).

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
the changes feed (§7.1) may hold records longer than `ttlSeconds` and invalidate on change instead.

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

### 3.5 Nested data: values and parts

Application data is rarely flat. An invoice has a billing address and a list of lines. These are two
different kinds of nesting, the distinction domain-driven design draws, and the protocol keeps them
apart because the world treats them differently.

**A value** has no identity of its own. An address is the invoice's address, and two invoices with
the same address do not share anything. It is declared as an `object` property:

```json
"billingAddress": { "type": "object", "properties": {
  "line1":    { "type": "string" },
  "city":     { "type": "string" },
  "postcode": { "type": "string" } } }
```

On the wire it is a nested JSON object. In the world it becomes flat properties on the owning node,
named by joining the path in camel case (`billingAddressPostcode`), because graph properties are
scalars. Filters, sorts and `fields` address it by path: `billingAddress.postcode`. A property inside
a value can carry `spine`, so an invoice's postcode can attach to the place it names. Values may
contain values, to a depth of 3, but not lists of values. A list of things that each have fields is a
list of parts.

**A part** has an identity, but only within its owner. Line 3 of `INV-1001` exists only as part of that
invoice, and it is created, changed and deleted with it. Parts are an aggregate's members. Each part
becomes a **type and a node** in the world, so it can be matched, filtered, joined and counted like any
other type:

```json
{
  "name": "InvoiceLine",
  "description": "One line of an invoice.",
  "partOf": { "type": "Invoice", "property": "lines", "relationship": "HAS_LINE", "ownerKey": "invoiceNumber" },
  "identity": "lineNo",
  "properties": {
    "lineNo":        { "type": "integer" },
    "invoiceNumber": { "type": "string" },
    "sku":           { "type": "string", "spine": "Product" },
    "quantity":      { "type": "integer" },
    "amount":        { "type": "decimal" }
  },
  "lookups": [{ "by": "sku", "maxKeys": 200 }, { "by": "invoiceNumber", "maxKeys": 200 }],
  "filter": { "properties": { "sku": ["eq", "in"], "amount": ["gt", "gte", "lt", "lte"] } },
  "aggregate": { "groupBy": ["sku"], "measures": { "count": true, "sum": ["quantity", "amount"] } }
}
```

The owner declares the parts as a list property:

```json
"lines": { "type": "list", "item": { "part": "InvoiceLine" } }
```

| `partOf` | Meaning |
|---|---|
| `type`, `property` | The owning type, and the property on it that holds the parts. |
| `relationship` | The edge the world draws from owner to part: `(:Invoice)-[:HAS_LINE]->(:InvoiceLine)`. |
| `ownerKey` | The part's property holding its owner's identity. A part returned outside its owner — by its own lookup or query — always carries it, so the world can attach it. |

A part is reachable in two ways, and the world uses whichever the query makes cheaper:

- **Inside its owner.** Fetching invoices with `"fields": ["number", "lines"]` returns each invoice
  with its lines embedded. `"lines.sku"` returns them with only that property, plus `lineNo`. Lines
  are not returned unless `fields` asks for them, so an invoice listing never pays for its lines.
- **On its own.** A part can declare lookups, a query and aggregates like any type. "Which invoices
  contain SKU X?" is a lookup on `InvoiceLine.sku` that returns lines carrying `invoiceNumber`, with
  no invoice scan. "Units sold per SKU" is an aggregate over lines, computed in the provider.

A part's identity is its owner's identity plus its own. It has no lookup by its own identity alone,
because `lineNo: 3` means nothing without an invoice. A change to a part is reported as a change to
its owner (§7.1), because the owner is the unit that changes. Parts may own parts — an order's
shipments, a shipment's packages — to a depth of 3.

**Filtering through parts.** `exists` (§4.1) takes a part property in place of a referencing type:

```json
{ "exists": { "part": "lines", "where": { "property": "sku", "op": "in", "value": ["SKU-1", "SKU-7"] } } }
```

On an `Invoice` read this keeps the invoices with a line for either SKU, evaluated by the provider in
one query. The capability is declared as `"lines"` in the owner's `filter.exists`.

The test for choosing between a value, a part and a referenced type is the same as the spine test in
[VIRTUAL_CYPHER.md §5.4.2](VIRTUAL_CYPHER.md#542-an-identity-is-a-spine-a-record-is-a-parent-label),
applied inside one application:
- If it has no identity, it is a **value**.
- If it has an identity only inside its owner, and lives and dies with it, it is a **part**.
- If something else refers to it independently, it is a **type** with a reference (§3.2).

### 3.6 Several realms from one application

One application may serve several realms. An ERP's billing, inventory and HR are different
realms to a world owner, who may want only one. A finance view and a sales view of the same data are
different realms, each behind its own credential. Each realm is a complete provider at its own
URL — its own manifest, credential, cache, events and subscriptions — so nothing else in this protocol
changes.

An application with several realms may serve an **index** at a root URL:

```http
GET https://erp.example.com/embabel
```

```json
{
  "protocol": "1",
  "application": "Acme ERP",
  "realms": [
    { "name": "billing",   "title": "Billing",   "url": "https://erp.example.com/embabel/billing",
      "description": "Customers, invoices, payments and refunds." },
    { "name": "inventory", "title": "Inventory", "url": "https://erp.example.com/embabel/inventory",
      "description": "Products, stock levels and warehouses." }
  ]
}
```

A response with `realms` and no `types` is an index, not a manifest. Given an index URL, the world
lists the realms and the owner chooses which to install. Given a realm's own URL, the world installs
that realm. The world side is still one URL. Every realm URL in an index must have the index's
origin, so an index cannot point a world at another application.

**Sibling references.** Realms from one index share the application's identities, so one may
reference another's type directly:

```json
"customerId": { "type": "integer", "references": { "realm": "crm", "type": "Customer", "relationship": "BILLED", "direction": "in" } }
```

A sibling reference is allowed only between realms of the same index. If the world installs one realm
without its sibling, the reference is inert, and the world reports it as it does a spine it does
not have. Anything outside the application is reached through spines (§6), never by raw id.

The index is also the answer to large applications. A manifest with hundreds of types is better
split into realms an owner can choose between, than paged.

### 3.7 Realm metadata and skills

A realm is more than its types. An owner choosing what to install, and a model deciding how to use
what was installed, both need to know what the realm is for and how it is meant to be used. The
manifest carries that at the top level, in the same terms as a git realm's `realm.yml`
([README](README.md#realmyml)), so a provider's realm and an authored one are described alike:

```json
{
  "protocol": "1",
  "name": "billing",
  "title": "Billing",
  "description": "Customers, invoices, payments and refunds from the billing system.",
  "version": "4.2.0",
  "author": "Acme Finance Engineering",
  "url": "https://wiki.acme.example/billing",
  "icon": "icon.svg",
  "category": "finance",
  "tags": ["invoicing", "payments"],
  "maturity": "beta",
  "about": "about.md",
  "skills": [
    { "name": "collections", "description": "Chase overdue invoices: who to remind, when to escalate, when a refund needs approval.",
      "files": ["references/escalation.md"], "digest": "sha256:9f2c…" }
  ],
  "types": [ ... ]
}
```

| Field | Meaning |
|---|---|
| `version`, `author`, `url`, `category`, `tags`, `maturity` | As in `realm.yml`. `maturity` is the provider's own readiness claim; absent is not a claim of being finished. |
| `icon` | A path relative to the provider URL, served from it. |
| `about` | A path to a Markdown document: what the realm holds, what its numbers mean, and what it does not cover. It is shown to the owner on install and is part of the realm's brief for models. Keep it a description and a pointer; how-to belongs in skills. |
| `skills` | Skills the realm brings, below. |

The index of §3.6 repeats `title`, `description`, `icon`, `category` and `maturity` for each realm, so
an owner can choose between realms without fetching every manifest.

**Skills.** A provider can ship [Agent Skills](https://agentskills.io/specification): instructions a
model activates when a user's request matches them, at no cost otherwise. They are the right place
for what the developers know about using their own application well. Examples: which verb to try
before which, what "overdue" means in this business, when a refund will need approval and how to say
so.

```http
GET {provider}/skills/{name}/SKILL.md
GET {provider}/skills/{name}/references/{file}
GET {provider}/skills/{name}/assets/{file}
```

- `SKILL.md` is a standard Agent Skills file: YAML front matter with `name` and `description`, then
  Markdown instructions. `references/` and `assets/` hold files the instructions point to. The
  manifest lists the files under each skill as `files`, so the host fetches exactly those.
- `digest` covers the whole skill. The host refetches a skill only when its digest changes.
- A skill arrives with its realm and leaves with it, like any realm's skills. An agent scoped to the
  realm gets its skills, and one that is not scoped to it does not.
- Instructions name the realm's types, verbs and events by their manifest names. The host checks
  those names on install and reports a skill that mentions a verb the manifest does not have, rather
  than letting a model try to call it.
- **No `scripts/`.** A provider's skill is instructions and reference material. A script would be
  code the application ships into the world to run, which needs a sandbox, an approval and a
  signature to trust. That is a future (§14.6), not version 1. A skill that declares scripts is
  installed without them, and the host says so.

## 4. Reading

The provider sits next to its data, with indexes, a query planner and its own authorization. Every
filter, ordering, limit and reduction it evaluates is a row that never crosses the wire and never
has to be evaluated twice. So the protocol is built to push down **as much of a query as the
provider can take**, and to make sure that whatever it takes is taken correctly.

### 4.1 Pushdown

**Expressions.** Fetches, queries and aggregates all carry an optional `where`, an expression tree:

```json
{ "and": [
  { "property": "status", "op": "in", "value": ["open", "draft"] },
  { "or": [
    { "property": "amount",  "op": "gt", "value": "1000" },
    { "property": "dueDate", "op": "lt", "value": "2026-10-01" }
  ] },
  { "not": { "property": "customerId", "op": "isNull" } }
] }
```

| Operator | Value | Applies to |
|---|---|---|
| `eq`, `ne` | one value | every scalar type |
| `in`, `notIn` | array | every scalar type |
| `gt`, `gte`, `lt`, `lte` | one value | `integer`, `decimal`, `date`, `datetime`, `duration` |
| `between` | `[low, high]`, both inclusive | as for `gt` |
| `isNull`, `isNotNull` | none | every type |
| `prefix`, `contains` | string | `string` |
| `ieq`, `iprefix`, `icontains` | string | `string`, compared after Unicode simple case folding |
| `has`, `hasAny` | one value / array | `list`: the list contains it / any of them |

Range operators are not defined on strings. Collations differ between stores, and a provider that
sorted `"Ä"` differently from the host would drop records that the host's re-check could never
bring back.

**Nulls.** A record whose property is null or absent satisfies only `isNull`. It fails every other
operator, `ne` and `notIn` included. That is SQL's and Cypher's rule, and a provider must apply it
even where its store differs.

**Existence across a relationship.** A type that declares `filter.exists` can test its related
records without returning them:

```json
{ "exists": { "type": "Invoice", "via": "customerId",
              "where": { "and": [
                { "property": "status",  "op": "eq", "value": "open" },
                { "property": "dueDate", "op": "lt", "value": "2026-10-10" } ] } } }
```

On a `Customer` query this keeps the customers that have an open, overdue invoice. `via` is the
referencing property (§3.2), and the capability is declared as `"Invoice.customerId"`. `exists` over
a part (§3.5) names the part property instead: `{ "exists": { "part": "lines", "where": … } }`. The inner
`where` is limited by `Invoice`'s own `filter` declaration. One level of `exists` is allowed; an
`exists` nested inside another is not.

**What the host sends.** The host normalizes a query's predicate into a conjunction and pushes every
conjunct the provider can evaluate **completely**: every property, operator, logical connective and
`exists` inside it must be declared. A disjunction with one unsupported branch is not pushed at all,
because pushing half of an `or` would drop the records the other half admits. Whatever is not pushed
the host evaluates itself, over what comes back.

Only declared properties can be filtered on. Every filterable property is also a returned property,
so filtering can never become a way to learn a value the provider chose not to expose.

**What the provider must do.** Evaluate everything it is sent, exactly. The host re-applies every
pushed predicate to the returned records, which catches a provider that returns *too much*, but no
re-check can find a record the provider wrongly left out. Exactness is what the conformance kit
(§11) tests hardest.

A provider that, on some call, cannot apply the whole `where` it was sent (a fallback path, a
degraded index) answers with `"applied": false` and **must not** then apply `limit` or
`limitPerKey`. The host then treats the response as unfiltered input. A provider that applied
everything answers with `"applied": true`. The echo lets the host rely on what happened on this call,
not just on what the manifest promised.

**Paths.** A filter, sort or field may name a property inside a value by its path
(`billingAddress.postcode`). The capability is declared under the same path.

**Projection.** `fields` lists the properties the host needs. Parts are returned only when `fields`
names them (§3.5). A provider that declared `project`
returns at least those, plus the identity and the lookup property. It may return more.

**Order and limit.** `sort` is a list of `{property, direction}`. The host sends `limit` (on a
query) or `limitPerKey` (on a fetch) only when the whole predicate was pushed and the sort is
declared, because only then are the first N records the right N. A provider confirms with
`"sorted": true`.

### 4.2 Fetch by keys

```http
POST {provider}/fetch
```

```json
{
  "type": "Invoice", "by": "customerId", "keys": ["17", "42", "99"],
  "where": { "property": "status", "op": "eq", "value": "open" },
  "fields": ["number", "amount", "dueDate"],
  "sort": [{ "property": "dueDate", "direction": "asc" }],
  "limitPerKey": 3
}
```

```json
{
  "records": [
    { "number": "INV-1001", "customerId": "17", "amount": "1200.00", "dueDate": "2026-10-31" },
    { "number": "INV-1007", "customerId": "17", "amount": "80.00",   "dueDate": "2026-11-30" }
  ],
  "missing": ["42"],
  "failed": ["99"],
  "applied": true,
  "sorted": true
}
```

That is "the three earliest open invoices of each of these customers", with only three columns read,
in one call. Without pushdown the same traversal moves every invoice the customers ever had.

The batch contract, which every provider must keep:

- **All keys in one call**, up to the lookup's `maxKeys`. The host splits larger batches; the
  provider never receives more than it declared.
- **Every record carries the lookup property** with a value equal to one of the requested keys, in
  canonical form. That is how the host attaches each record to its anchor; a record without it is
  dropped and reported.
- **Every requested key is accounted for**: it has at least one record, or it is in `missing` (no
  record matches the key *and* the `where`), or it is in `failed` (the provider could not answer for
  it). A key in none of the three is treated as `failed`.
- `missing` may be negatively cached (§3.3) only for a fetch with no `where`. `failed` never is.
- A lookup on a non-identity property may return many records per key. A lookup on `identity`
  returns at most one.
- `limitPerKey` is sent only to a lookup that declared it, and caps the records per key, in `sort`
  order.

A provider that holds only a single-record operation internally — `findById` — may loop over the
keys itself. That loop runs inside the provider, next to its data, which is still far cheaper than
the host making one HTTP call per key. It should declare a modest `maxKeys` to match.

### 4.3 Query

```http
POST {provider}/query
```

```json
{
  "type": "Customer",
  "where": { "and": [
    { "property": "tier", "op": "in", "value": ["pro", "enterprise"] },
    { "exists": { "type": "Invoice", "via": "customerId",
                  "where": { "property": "status", "op": "eq", "value": "open" } } }
  ] },
  "fields": ["id", "name", "balance"],
  "sort": [{ "property": "balance", "direction": "desc" }],
  "limit": 20,
  "pageSize": 20,
  "cursor": null
}
```

```json
{
  "records": [ ... ],
  "applied": true,
  "sorted": true,
  "next": null,
  "total": 312
}
```

**`search`** — present only if the type declared `query.search` — is free text for the
provider's own search, e.g. `"search": "acme logistics"`. It combines with `where`. Records come back in
the provider's relevance order and the host treats the result as a ranked lexical match, with the
same contract as a `remote-search` producer ([VIRTUAL_CYPHER.md §5.3](VIRTUAL_CYPHER.md#53-producer-kinds)):
rank, no similarity score.

**Paging is by opaque cursor.** `next` is a string to send back as `cursor`, or `null` at the end.
`total`, if the type declared `query.total`, is the number of records the `where` matches across all
pages; it lets the host fetch the remaining pages concurrently. `limit` ends the walk once that many
records have been returned.

**Nothing is ever silently cut short.** A provider that stops early for its own reasons — a cap, a
timeout — answers with `"truncated": { "reason": "..." }`, and the host carries that warning into
the query result. A page that ends a walk without `next` and without `truncated` is a promise that
the walk is complete.

### 4.4 Aggregate

```http
POST {provider}/aggregate
```

```json
{
  "type": "Invoice",
  "where": { "property": "status", "op": "eq", "value": "open" },
  "by": "customerId", "keys": ["17", "42"],
  "groupBy": [],
  "measures": [
    { "fn": "count", "as": "openInvoices" },
    { "fn": "sum", "property": "amount", "as": "outstanding" }
  ]
}
```

```json
{
  "groups": [
    { "key": { "customerId": "17" }, "values": { "openInvoices": "2", "outstanding": "1280.00" } }
  ],
  "missing": ["42"],
  "applied": true
}
```

The functions are `count`, `countDistinct`, `sum`, `avg`, `min` and `max`, over the properties the
type declared for each under `aggregate.measures`, grouped by the declared `aggregate.groupBy`
properties.

**Keyed aggregates** — `by` and `keys`, which require a lookup on `by` — return one group per key that
has rows. This is the reduction a traversal most often asks for ("each customer's open balance"). It
follows the batch contract of §4.2: a key with no matching rows is in `missing`, and the host reads
that as a count of zero and a null sum.

**Values follow §2.1.** Counts are integers; `sum`, `min` and `max` keep the property's type; `avg`
of an `integer` or `decimal` is a `decimal`. A sum is exact, never rounded through floating point.

This is the one operation whose answer the host cannot re-check, because it never sees the rows. So
a type declares exactly the measures it computes exactly, and the conformance kit compares every
declared measure with the same reduction over fetched rows. The host uses aggregate pushdown only
when the whole `where` was pushed, and falls back to fetching rows when `applied` is `false`.

### 4.5 Limits

| Limit | Value |
|---|---|
| Keys per fetch or keyed aggregate | the lookup's `maxKeys`, at most 1000 |
| Records per page | the type's `maxPageSize`, at most 1000 |
| Expression depth | 8 |
| Nodes in one `where` | 256 |
| Values in one `in` / `notIn` / `hasAny` | 1000 |
| Response body | 16 MiB |
| Cursor | 2048 bytes |

A provider that answers over a limit is refused with `RESULT_BOUND`, never truncated by the host.

### 4.6 Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `UNAUTHENTICATED` | 401 | The host's credential was missing or wrong. |
| `FORBIDDEN` | 403 | The acting user may not do this. |
| `ACTING_USER_REQUIRED` | 401 | The manifest said `required` and none was sent. |
| `UNKNOWN_TYPE` | 404 | Not a type in the current manifest. The host revalidates the manifest. |
| `UNSUPPORTED` | 400 | A lookup, operator, connective, `exists`, sort, measure or grouping the type did not declare. |
| `KEY_BOUND` | 400 | More keys than `maxKeys`. |
| `APPROVAL_REQUIRED` | 403 | The verb call needs an approval it did not carry, or carried one that is expired or does not match the call (§5.2). Nothing was done. |
| `APPROVER_NOT_AUTHORIZED` | 403 | The approval is valid, but the provider does not accept this approver (§5.2). |
| `EXPRESSION_BOUND` | 400 | A `where` over a limit in §4.5. |
| `RATE_LIMITED` | 429 | With `Retry-After`. |
| `UNAVAILABLE` | 503 | Temporarily unable to answer. Never negatively cached. |
| `RESULT_BOUND` | — | Host-side: the answer was over a limit in §4.5. |

## 5. Verbs

A verb is an operation the provider lets the world perform: issue a refund, assign a ticket,
recalculate a quote. It is the application's own service operation, behind its own validation and
authorization.

```json
{
  "name": "issueRefund",
  "description": "Refund part or all of a paid invoice to the customer's original payment method.",
  "subject": "Invoice",
  "input":  { "type": "object",
              "properties": { "number": { "type": "string" }, "amount": { "type": "string", "format": "decimal" }, "reason": { "type": "string" } },
              "required": ["number", "amount", "reason"] },
  "output": { "type": "object", "properties": { "refundId": { "type": "string" } } },
  "effect": "external",
  "idempotent": true,
  "approval": {
    "required": "when",
    "when": { "property": "amount", "op": "gt", "value": "500" },
    "reason": "Refunds over 500 need a second person."
  }
}
```

| Field | Meaning |
|---|---|
| `subject` | Optional. The type the verb acts on, so the host can offer it from a record. |
| `input`, `output` | JSON Schema (2020-12). The host validates `input` before calling. |
| `effect` | `read`: no change anywhere. `write`: changes the provider's own data. `external`: has an effect outside the provider that cannot be taken back — an email sent, a payment made. |
| `idempotent` | Whether repeating the same call is safe. |
| `approval` | §5.2. Absent means `{ "required": "never" }`. |

### 5.1 Calling a verb

`POST {provider}/verbs/{name}` carries the input as its body, the acting user, and an
`Idempotency-Key` header the host generates per logical attempt and reuses on retry. A provider
that has seen that key returns the first answer again.

### 5.2 Approval

Some operations must not happen on one person's say-so, still less on an agent's. The provider
knows which operations those are, because the rule is usually its own business rule — refunds over
a limit, a contract change, a deletion. So **the provider declares which verbs need approval, and
enforces it**. The host collects the approval through the world's approvals, from people the world
lets approve.

| `approval.required` | Meaning |
|---|---|
| `never` | The verb runs on the acting user's authority alone. |
| `always` | Every call needs an approval. |
| `when` | A call needs an approval when its input satisfies `approval.when`, an expression in the `where` grammar of §4.1 evaluated over the input's properties. |
| `decided` | The provider decides per call, by rules it cannot state as an expression — the customer's history, a running total. It answers `APPROVAL_REQUIRED` (below) for the calls that need one. |

`approval.reason` is shown to the person asked to approve, and to an agent planning the call, so it
can tell the user that the action will wait for someone.

**The host may ask for more approval, never less.** A world can require approval for any verb its
owner chooses, such as every `external` verb. It cannot waive approval for a verb the provider
says needs one, because the provider refuses the call without it.

**The flow:**

1. The host evaluates `approval`. If the call needs approval, it raises an approval request in the
   world with the verb, its input, the acting user and `reason`, and does not call the provider yet.
2. The provider may still require approval the host did not foresee (`decided`, or a rule that changed).
   It answers `403` with `code: "APPROVAL_REQUIRED"` and a `reason`, and **it must not have
   performed any part of the operation**. The host then raises the request as in step 1.
3. When someone approves, the host calls the verb again, with the same `Idempotency-Key`, carrying
   an `Embabel-Approval` header.

**The approval is evidence the provider can check, not a flag it has to trust.** `Embabel-Approval`
is a JWT signed with the same keys as the acting user (§3.4). It carries:
- the approval request's id;
- the approver's subject and verified email;
- the verb name;
- a SHA-256 digest of the canonical JSON input ([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785));
- the time of approval and an expiry.

The provider checks the signature, that the verb and digest match this call, and that the token has
not expired. It also checks that the approver is not the acting user, unless it declared
`approval.selfApproval: true`. It may then apply its own rules about who may approve. A finance
system might accept a refund approval only from someone it knows as a finance manager. It refuses
with `APPROVER_NOT_AUTHORIZED` when the approver fails those rules.

An approval authorizes **one** call with **that** input. Changing the amount after approval
changes the digest, and the provider refuses the call. Retrying with the same `Idempotency-Key`
returns the first answer, so one approval can never trigger the operation twice.

A rejected request is never sent to the provider. The host reports the rejection to whoever asked.

**Verbs the provider approves itself.** An application with its own approval workflow, such as a
purchase order that goes through the app's own sign-off, does not need the host to collect the
approval. It declares `required: "never"` and answers the call with `202 Accepted` and
`{ "status": "pending", "reference": "PO-88123" }`. The outcome arrives as an event or a change (§7)
like any other change to its records.

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
- It returns records carrying the requested key, exactly as for any lookup (§4.2), so the host
  attaches each to the spine node it asked about.
- `missing` is a real answer: this company is not one of our customers. The host may cache that for
  `negativeTtlSeconds`.

The host normalizes keys **before** sending them: a provider looked up by `Organization` receives
registrable domains, lower-cased; by `Person`, lower-cased emails. It never sees the variety of
forms the world collected them in, and it need not normalize again.

What a provider cannot do is assert identity between spine nodes, or attach a record to a spine by
anything but a declared property. Spine resolution stays deterministic and stays the host's.

## 7. Changes and events

Two kinds of news flow from a provider. **Changes** say that a record is different now, so the host
can stop guessing with TTLs. **Events** say that something happened that means something — an
invoice became overdue, a customer cancelled — so the world's handlers and agents can react. Both are
available to a host that only polls. A provider that can reach the host may also push them (§7.3).

### 7.1 Changes

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
- Changes are reported only after they are committed. A host told about an uncommitted change
  would refetch the old record and cache it as new.

### 7.2 Events

The manifest declares the events a provider publishes:

```json
"events": [
  {
    "name": "InvoiceOverdue",
    "description": "An open invoice passed its due date unpaid.",
    "subject": "Invoice",
    "payload": { "type": "object",
                 "properties": { "number": { "type": "string" }, "daysOverdue": { "type": "integer" } },
                 "required": ["number"] }
  }
]
```

| Field | Meaning |
|---|---|
| `name`, `description` | The event, as shown to the owner and to agents choosing what to react to. |
| `subject` | Optional. The type the event is about. The event's `key` is then that record's identity, and the host can traverse from the event to the record and on into the world. |
| `payload` | JSON Schema (2020-12) for the event's own data. Events carry what happened; the record itself is fetched. |

Each event becomes a **source** in the world: something a handler or an agent can be triggered by,
like any other realm's sources.

```http
GET {provider}/events?since={cursor}
```

```json
{
  "events": [
    { "id": "evt-90311", "name": "InvoiceOverdue", "key": "INV-1001",
      "occurredAt": "2026-10-10T00:00:05Z",
      "payload": { "number": "INV-1001", "daysOverdue": 1 },
      "changes": [{ "type": "Invoice", "key": "INV-1001", "op": "upsert" }] }
  ],
  "next": "e-004410"
}
```

- `id` is unique per provider and stable. The host deduplicates on it, so redelivery is harmless,
  and the same event arriving both by poll and by push (§7.3) is one event.
- `changes` is optional. An event that also changed records says so, and the host invalidates
  them as if they had arrived on the changes feed, so a handler reacting to the event reads the new
  record, not a cached old one.
- Events are published only after the transaction that produced them commits, and in commit order
  per `key`.
- The cursor rules are those of §7.1. A provider keeps events for at least as long as it declares
  in `eventRetention` (ISO 8601 duration, at least `P1D`), and answers `410 Gone` for an older
  cursor. A host that receives `410` reports the gap: events it can no longer get are lost, and the
  world should know that rather than assume a quiet day.

### 7.3 Push delivery

A provider whose application *can* reach the world may deliver events and changes as they happen,
rather than waiting to be polled. That is the application's choice, so it is declared in the
manifest, and the host still sets up delivery: the application never has to find the world itself.

```json
"delivery": { "push": true }
```

When it installs a provider that declares `push`, the host subscribes:

```http
POST {provider}/subscriptions
```

```json
{
  "callback": "https://world.example.com/api/v1/providers/billing/inbox",
  "secret": "<per-subscription signing secret>",
  "events": ["InvoiceOverdue"],
  "changes": true
}
```

The provider answers `201` with a subscription id. It then sends a `ping` to the callback and treats
the subscription as live only if the ping is acknowledged. A provider that cannot reach the
callback (a firewall, no route out) answers the subscription with `409` and code `UNREACHABLE`, and
the host polls instead. The host removes its subscription with `DELETE {provider}/subscriptions/{id}`
when the realm is removed.

Each delivery is a `POST` to the callback with a batch in the same shape as a poll response:
`events` and `changes`. It is signed per the [Standard Webhooks](https://www.standardwebhooks.com/)
scheme (`webhook-id`, `webhook-timestamp`, `webhook-signature`, an HMAC over the body with the
subscription's secret).

- **The host acknowledges with `2xx` only after it has durably stored the batch.** Anything else, or no
  answer, and the provider retries with backoff for at least `eventRetention`.
- **Push never replaces the cursor.** The host keeps its poll cursor and polls occasionally even while
  push is live, and the `id` dedupes the overlap. A delivery lost on both paths is then caught by
  the next poll, not lost silently.
- The secret authenticates deliveries to *this* callback only. It grants no other access to the
  world. It is not an API key, and the application holds no general credential for the world.

A provider may serve several subscriptions, one per world that installed it, and delivers to each
independently.

## 8. Other provider-to-host directions

| Extension | Why |
|---|---|
| **Outbound tunnel** | The provider holds an outbound connection to the host and receives operations over it. This is for a provider behind a firewall the host cannot reach. The operations and their semantics are unchanged; only who opened the socket differs. Specified separately when it is built. |

An application that wants to *consume* a world — run its views, query its graph — uses the world's
existing REST and GraphQL doors. That is a client of the world, not this protocol.

## 9. How the host installs a provider

This is what makes the world side one URL. Given `https://billing.example.com/embabel`:

1. `GET` the URL. If it is an index (§3.6), let the owner choose realms, and install each as below.
   Refuse an unsupported `protocol` and say which version the host speaks.
2. Ask the owner for a credential if `auth.schemes` needs one, and keep it in the wallet.
3. Synthesize a realm, entirely from the manifest:

| Manifest | Realm |
|---|---|
| `types[]` | `types/` entries, namespaced under the realm |
| `identity` | `identity: true` on that property |
| `spine` on a property | `hub: <spine>` on that property |
| each `lookup` | a producer of kind `provider`, keyed by that property, with the lookup's `maxKeys` as its batch size |
| `references` | a join between the two types, through the lookup on the referencing property |
| an `object` property | flat properties on the node, named by camel-cased path |
| a part type | a type whose nodes hang off the owner by `partOf.relationship`, filled from the owner's fetches or the part's own lookups |
| a lookup by a spine-bound property | a join anchored on that spine |
| `query` | a scan producer |
| `filter`, `sort`, `project` | the pushdown declared on every producer of that type, used by the planner as §4.1 describes |
| `aggregate` | aggregate pushdown for `count`/`sum`/… over that type, keyed or grouped |
| `cache`, `cost` | the producers' cache policy and pacing |
| metadata, `about` | the realm's `realm.yml` fields and brief |
| `skills[]` | the realm's skills, without scripts |
| `events[]` | world sources, delivered by poll or by push subscription |
| `verbs[]` | gateway operations; `approval` becomes the verb's approval policy in the world |

4. Validate it like any other realm, install it, and report anything inert: a spine the world does
   not have, a reference with no lookup behind it.

The synthesized realm is not written by anybody and is not edited by anybody. A change to the
manifest is a change to the realm. An owner who wants more — views over the provider's types, DERIVE
rules, an app — writes an ordinary realm that depends on it.

The `provider` producer kind is new. Its behaviour is the batch contract of §4.2, the query contract of §4.3 and
the aggregate contract of §4.4, and nothing else; it takes no authored query and no configuration beyond what the
manifest says.

## 10. The Spring Boot provider (informative)

The reference provider is a Spring Boot starter, described in
[PROVIDER_SPRING.md](PROVIDER_SPRING.md). In short:
- It binds at the **service layer**, as an inbound adapter beside the application's controllers. It
  never binds at the repositories, so transactions, method security and invariants apply to every
  call.
- It derives **pushdown from parameter types**. A service method that takes a Spring Data
  `Specification`, a Querydsl `Predicate` or a jOOQ `Condition` receives the whole filter tree,
  translated by the starter and tested by the conformance kit. `Sort`, `Limit`, `ScrollPosition`
  and `Window` carry ordering, limits and cursors.
- It enforces **approval** itself, from `@RealmVerb.Approval` on `@RealmVerb` methods.
- It follows the **Embabel agent framework's conventions**: annotations that a reader turns into
  metadata, Jackson descriptions, and an injected `EmbabelRealm` for registering things from code,
  as `AgentPlatform` is used for agents.

## 11. Conformance

A protocol is only as good as the second implementation of it. The conformance kit is a test suite
that runs against any provider URL and checks every MUST in this document:
- the batch contract and key canonical forms;
- `missing` versus `failed`;
- the exactness of every declared operator, null rule and `exists`, comparing pushed results with
  the same predicate evaluated over unfiltered fetches;
- `applied` and `sorted` honesty;
- every declared aggregate, against the same reduction over fetched rows;
- cursor termination and truncation reporting;
- idempotency keys, and approval enforcement with and without a valid token;
- error codes.

The kit reads the provider's own manifest and data, so it needs no fixtures. A provider in C#,
TypeScript, Python, Go or anything else is conformant when the kit passes. Porting the Spring
provider is not the requirement.

## 12. Prior art

- **GraphQL Federation**'s `_entities(representations)` is batched entity resolution by key across
  services — the closest precedent for §4.2. This protocol adds declared cost, cache semantics,
  pushdown capability and the acting user, and drops the query language.
- **OData's capabilities vocabulary** (`FilterRestrictions`, `SortRestrictions`) is the precedent
  for declaring per property what a source can filter on (§3.1), and OData's `$apply` for
  pushed-down aggregation (§4.4).
- **Spring Data's web support** binds request parameters to a Querydsl `Predicate` in a controller.
  The Spring provider does the same for the protocol's filter tree.
- **RFC 9457** problem details for errors; **JSON Schema 2020-12** for verb input and output;
  **RFC 8785** canonical JSON for approval digests.

## 13. Open questions

- **Acting-user trust.** A host-signed JWT needs the provider configured with the host's JWKS URL —
  one piece of host knowledge on the provider side. Is that acceptable as the price of per-user
  authorization and verifiable approvals, or should `actingUser` default to `ignored` and per-user
  be the opt-in?
- **Writes as records.** Verbs cover consequential operations. Whether a provider should also accept
  plain creates and updates against its types, or whether those must always be verbs, is undecided.
  §14.3 sketches one answer.
- **Collation.** Range operators are excluded from strings, and case folding is Unicode simple case
  folding. Whether a provider may declare a collation the host can match is open.

## 14. Futures

Version 1 is deliberately small: one manifest per provider, the same declaration for every caller,
reads, verbs and an invalidation feed. Each idea below makes providers more powerful, and each is
designed to be **additive**: a version 1 host that ignores it stays correct. Most of them become
cheap because of choices version 1 already makes. One expression grammar serves filters, approval
rules, preconditions and watches. Every call carries an acting user. The provider is the authority
on what each user may see.

### 14.1 Who sees what

**Role-scoped manifests.** The manifest today is the same for everyone. Instead, the provider could
answer the manifest differently depending on who connects:

- **Per connection.** Each installation authenticates with its own credential, so the provider can
  give each one a different manifest. A partner's world sees `Customer` without `balance` and no
  `Invoice` at all. The world's own finance installation sees everything. The provider decides by
  the credential, and the host just installs what it is given. This works within version 1 once the
  manifest's `ETag` is understood to be per credential. It is mainly a matter of saying so.
- **Per acting user.** Within one installation, different people see different fields and objects.
  The manifest would declare the full shape, with `visibility` on each type, property and verb
  saying which provider-side roles see it. The host would request a user's own view with the
  acting-user header on `GET {provider}`. That gives each user a manifest of their own: a model
  helping a sales rep would not even know `margin` exists, rather than meeting nulls. The provider
  still enforces visibility on every read, refusing a filter on a property the user cannot see,
  because a filter on a hidden value reveals it as surely as returning it.

In the Spring provider this maps onto Jackson's `@JsonView`. A view type already annotated for
different API audiences declares its role-scoped shapes with no new annotations, and a
`RealmViewResolver` maps the acting user's authorities to a view.

**Masking.** Some properties are useful in a form that does not disclose them: an IBAN shown as its
last four digits, an email hashed so it still joins. A property could declare
`mask: last4 | hash | redact` per role, using the same vocabulary as Virtual Cypher's `governance:`
grammar. A hashed spine key would then join without ever leaving the provider in clear.

**Data classification.** Properties could carry `classification: pii | financial | health |
secret`, and a `use` constraint that the host enforces: `display` (show to people, never send to a
model), `noCache`, and a retention limit. A provider could then expose a patient's diagnosis to the
clinician's world while guaranteeing it never reaches an LLM prompt. That would be a guarantee the
host can make, and the provider can audit through §14.6.

**Tenancy.** One provider serving many tenants, with the tenant taken from the connection's
credential. Each tenant's world sees only its own types, including tenant-specific custom fields
(the Spring provider's `EmbabelRealm` already registers those at run time).

### 14.2 Reading more, moving less

- **Statistics for planning.** The provider could declare cardinalities, the selectivity of common
  filters and per-call latency. The host's planner would then price a provider's lookups by their
  actual economics, not by producer kind: which side of a join to drive from, and whether an anchor
  set is worth pushing at all. A `count` operation that answers with an estimate in milliseconds
  serves the same purpose.
- **Consistent snapshots.** A multi-call traversal can see the source change between calls. A
  provider that supports it would return a `snapshot` token from the first call. The host sends it
  on every later call, so the whole query reads one state, e.g. a database transaction's snapshot
  or an `asOf` timestamp.
- **Time travel.** `asOf` on any read, for providers with history. "Customers who were enterprise
  tier at the start of the quarter" becomes a pushed-down read rather than an impossibility.
- **Semantic search.** A `similar` operator over a property the provider has embedded, with the
  embedding model declared. This serves the host's `vector` relevance contract when the provider
  already owns the index.
- **Expensive properties.** Properties declared `cost: high` — a computed risk score, a property
  backed by the provider's own model — are returned only when `fields` asks for them, and the host
  never asks for them unless the query needs them.
- **Bulk streaming.** NDJSON or Arrow responses for large scans and materialised views, so a
  million-row snapshot does not arrive as pages of JSON.
- **Explain.** `"explain": true` on a read returns the provider's own plan and cost. It would be
  shown beside the host's plan in query diagnostics, so a slow provider is visibly slow, not a
  mystery.

### 14.3 Acting, planning and proposing

- **Preconditions and effects on verbs.** A verb could declare `pre` and `post` as expressions over
  its subject in the §4.1 grammar: `sendReminder` requires `status = open` and
  `dueDate < today`, and afterwards `lastRemindedAt` is set. The Embabel framework's GOAP planner
  plans with exactly this shape, the `pre` and `post` of `@Action`. The world's agents could then
  chain a provider's verbs into plans, rather than calling them one at a time and hoping.
- **Dry runs.** `POST /verbs/{name}?dryRun=true` returns what the call would do — the records it
  would change, as a diff, and the money it would move — without doing it. The approver of a
  refund (§5.2) sees the diff, not just the input. An agent checks a plan before asking anyone.
- **Record proposals.** Instead of a verb per change, a world proposes record edits against a type:
  "set this invoice's due date". The provider validates the edit with its own rules, answers with
  the diff and the approval it requires, and applies it on approval. That is §13's open question
  answered in the same approval flow as verbs.
- **Compensation.** A verb could name its inverse (`issueRefund` ↔ `reverseRefund`). A failed
  multi-step plan could then be unwound by the planner, not by a person.

### 14.4 Events and time

- **Standing queries.** The world registers a `where` with the provider — "customers whose balance
  exceeds their limit" — and the provider reports records entering and leaving the set. That pushes
  down a watch, not just a filter, and the provider evaluates it on its own writes, which is where
  it is cheapest.
- **Scheduled verbs.** A verb invoked "at the end of the month", held by the provider, which owns
  the business calendar, not by the host.

### 14.5 Identity and joining

- **Provider-declared spines.** A provider that is the system of record for an identity — products
  by SKU, sites by site code — could declare the spine itself, with its normalization. Other realms
  would then join on it. Today only realms declare spines.
- **Suggested bridges.** Version 1 forbids a provider from asserting identity between spine nodes.
  A future version could let it *suggest* one, with a confidence and its evidence ("these two
  domains are the same company after a merger"). The host keeps the decision, through the same
  offline tier that does fuzzy resolution today.
- **Deep links.** A `link` template per type (`https://billing.example.com/invoices/{number}`). Every
  record in a world can take the user back to the application's own screen for it. This is small to
  build and very useful.

### 14.6 Trust, audit and economics

- **Skills with scripts.** A provider skill that ships a script, run in the world's sandbox under the
  same approval and capability rules as a captured realm's code, and trusted through a signed
  manifest.
- **Signed manifests.** The provider signs its manifest. A world pins the signer on install and is
  warned if a later manifest is signed by someone else: supply-chain protection for the realm
  itself.
- **Purpose and agent context.** Every call carries why it was made: the world, the agent, the run
  and the user's question, in an `Embabel-Context` header. The provider's audit log records that
  "the collections agent read these invoices for this account manager at 09:30 answering 'who owes us most'". For
  regulated data, that log is the difference between allowed and forbidden.
- **Quotas and metering.** A provider that is a commercial data product declares a price per call
  or per record, and the host meters it against a budget the owner sets. A data vendor publishing a
  provider URL becomes a paid realm, with no integration work on either side.
- **Directories.** A signed list of providers, published by an organization or a vendor. A world
  can then browse what it may install, the way realm sources are browsed today.

### 14.7 Presentation

- **Cards.** A provider supplies a small rendering for its types: an invoice card, a customer
  header. World apps and chat can then show a record the way the application's own users would
  recognize it. Content-security rules for embedded content need settling first.
- **Localization.** Descriptions, enum labels and approval reasons in several languages, chosen by
  the acting user's locale.

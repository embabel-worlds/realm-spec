# Virtual Cypher — Specification

**Spec version: 0.2.0**

> **Status: normative.** This document defines what a Virtual Cypher query means, what it
> guarantees, and what it refuses. It states OBSERVABLE behaviour only — never how the engine is
> built. Where an implementation and this document disagree, this document is the defect report.
> **Scope.** Accessibility is per PRINCIPAL and focus is per WORLD: a world decides which
> capabilities exist in it, not which of its owner's data may be seen. Between principals the
> boundary is absolute. §15 states this in full, because an earlier draft claimed worlds were
> mutually confidential for one owner and they are not.
>
> **Relationship to Cypher.** Virtual Cypher is not a new language. A query is ordinary Cypher, and
> everything the [openCypher](https://opencypher.org/) specification says about pattern matching,
> `WHERE`, `WITH`, aggregation and ordering holds unchanged. This document specifies only the
> additions: labels whose rows are fetched on demand rather than stored, the declarations that make
> such a label reachable, the functions that reduce or judge rows with a model, and the conditions
> under which a query is rejected before it runs. Anything not stated here behaves as plain Cypher.
>
> **Companions.** Teaching material and worked examples are in
> [`VIRTUAL_CYPHER_GUIDE.md`](VIRTUAL_CYPHER_GUIDE.md); a one-page summary is
> [`VIRTUAL_CYPHER_CHEATSHEET.html`](VIRTUAL_CYPHER_CHEATSHEET.html). The declarative surface a
> realm author writes is described in [`README.md`](./README.md).
---

## 1. What Virtual Cypher is

A normal knowledge-graph query reads nodes and edges that are **persisted** in Neo4j. Virtual
Cypher lets one Cypher query *also* traverse to data that is **not in the graph** — a HubSpot
contact, a GitHub issue, a semantically-related email thread — by **fetching it on demand** the
moment the query reaches for it, splicing it into the graph transiently for the life of that one
query, and then **rolling it back**. The query author writes ordinary Cypher; they do not know,
and do not need to know, which labels are persisted and which are fetched live.

The defining property: **one `MATCH` spans persisted and live data uniformly.**

```cypher
MATCH (me:AssistantUser)-[:EMAILED]->(p:Person)-[:HAS_GITHUB]->(g:GitHubIdentity)-[:RAISED]->(i:GitHubIssue)
RETURN p.name, i.title
```

`AssistantUser`, `EMAILED`, `Person` are **persisted** (the contact graph). `GitHubIdentity`,
`HAS_GITHUB`, `RAISED`, `GitHubIssue` are **virtual** — resolved from GitHub through the connecting
user's credentials when the query runs. The author wrote one query; the engine decided what to
fetch.

### The mental model

Think of a virtual label as a **view over an external system that materializes only the rows a
query touches**. The closest analogues:

- A SQL **foreign data wrapper** / external table — but reached through *graph traversal*, so the
  *anchor* you start from decides which external rows are fetched.
- A LOTUS / Cortex **semantic operator** — but expressed inside Cypher, so structure (who emailed
  whom) and meaning (which threads are *about* X) compose in one query (see §6, vector edges).

You never call Virtual Cypher directly. You **declare** the pieces and the engine plans and runs
the fetch.

---

## 2. The execution model

Every Virtual Cypher query runs the same five conceptual phases, inside a **write transaction that
always rolls back**:

```
   ┌─ parse + plan ──────────────────────────────────────────────────────────┐
   │                                                                          │
   │  1. PROBE    bind REAL anchors in the host-bound world                  │
   │  2. FETCH    call each producer ONCE with all anchor keys (batched)      │
   │  3. MATERIALIZE  splice fetched records in as transient :Virtual nodes   │
   │  4. RUN      run your query over the combined real + virtual graph       │
   │  5. ROLL BACK    discard everything materialized — nothing persists      │
   │                                                                          │
   └──────────────────────────────────────────────────────────────────────────┘
```

1. **Probe.** The engine runs the *real-graph prefix* of your query — the part that binds the
   **anchor** the virtual data hangs off — applying your own `WHERE` and pinned literals, so it
   selects only the anchors that will survive your filter. It collects each anchor's identity and
   its **key field** (the value a producer fetches by, e.g. an email address).

2. **Fetch.** For each virtual join the engine calls its **producer** *once* with the **union of
   all anchor keys** — never one call per anchor (no N+1). The producer is the source-specific
   fetcher (a REST op, a SQL query, a vector search, an in-process computation).

3. **Materialize.** Each returned record becomes a transient node carrying the extra `:Virtual`
   label, a `dateRetrieved` timestamp, and the host-bound `worldId`, `contextId`, and access-policy
   revision. The engine links it to the anchor it was fetched for (`keyField == recordKeyField`). A
   record may also carry its own **sub-graph** (`brings:`), materialized in the same pass.

4. **Run.** Your full query now runs over the combined graph. `WHERE`, `ORDER BY`, `RETURN`,
   aggregates — all of Cypher — apply to virtual nodes exactly as to real ones.

5. **Roll back.** The transaction is discarded. The virtual nodes vanish. A re-run re-fetches
   (cheap, because of caching). Nothing is ever persisted by a read query.

   *The one exception:* an identity **bridge** (`writeThrough`) is committed as a warm cache and
   re-resolved after `refreshAfter` (§5.2).

### Two concepts the rest of the spec leans on

**Bound anchor.** A virtual label may only be reached by **traversing a declared join from a
*bound* anchor** — a node the engine can resolve to a finite set. An anchor is bound when it is:

- pinned by an inline literal — `(p:Person {primaryEmail:'a@b.com'})`, or
- pinned by a `WHERE` equality — `WHERE p.primaryEmail = 'a@b.com'`, or
- narrowed by **any** property predicate — `WHERE toLower(p.name) CONTAINS 'grace'`, or
- the acting human principal — `(me:AssistantUser)` (the scope rewriter resolves the node linked to
  `principalId`; a service principal has no implicit `me` anchor), or
- reachable over a *required* edge from another bound node.

A naked `MATCH (hc:HubSpotContact)` — no anchor — is **rejected** (§4). This is what stops Virtual
Cypher from trying to fetch *every* contact in HubSpot.

**Per-world and per-context scope.** The world selects the outer data boundary; the context selects a
confidentiality boundary within it; the principal supplies authority. The probe runs through the
fail-closed scope rewriter under immutable host-bound `(worldId, contextId, access-policy revision)`,
while `principalId` remains separate for authorization and audit. Every anchor and virtual node
belongs to that scope. The caller supplies none of these identities. A query cannot reach another
context without an explicit policy-authorized bridge, and cannot reach another PRINCIPAL's data at
all. Between two worlds of the SAME principal the boundary is focus rather than confidentiality:
each world decides which types, realms, producers, views and skills exist in it, and a label whose
realm is not installed there cannot be named, fetched or viewed — but data the principal may see is
data the principal may see. See §15. Local single-user deployments use the same path and an explicit
default context.

---

## 3. Worked examples — see the User Guide

Worked examples, in teaching order, are in [`VIRTUAL_CYPHER_GUIDE.md`](VIRTUAL_CYPHER_GUIDE.md).
This document is the reference: it states what is guaranteed, what is rejected, and what each
declaration means, and keeps only the minimal fragments needed to make a rule unambiguous.


---

## 4. What is *not* possible — and why

These are **rejected at plan time** (fail-closed), with a message:

| Pattern | Why rejected |
|---|---|
| `MATCH (hc:HubSpotContact) RETURN hc` | **Naked virtual scan** — no anchor to probe. Virtual labels are reached only by traversing a declared join from a bound anchor; otherwise the engine would try to fetch *every* contact. |
| `MATCH (p:Person)-[:HAS_HUBSPOT_CONTACT]->(hc)` with no predicate on `p` | **Unbound anchor** — `p` matches every person; the fan-out is unbounded. Pin or filter the anchor. |
| `MATCH (i:Item)-[:MENTIONS]->(t:Tag)` where `Tag` is brought only via `TAGGED` | **Brought child off its declared edge** — a brought label is reachable only through the exact relationship its own `brings:` entry names, and only from the join whose target brought it. |
| `UNION`, `CALL { }` subqueries in a scoped query | Not scoped clause-by-clause by the rewriter → rejected (restructure as separate queries). |
| Anything the Cypher parser can't parse | **Fail closed** — an unparseable query is rejected, never run unscoped. |

A `brings:` entry naming a `childType` the realm does not declare is refused earlier still, when the
realm is validated — before any query reaches the planner. The remaining case is a **non-event**: a
producer that starts returning some extra child type cannot inject it, because materialization reads
only the `records:` paths the join declared. An unmodelled node has no way in, so there is nothing to
fail loud about; the risk `brings:` actually carries is the opposite one, a declared child arriving
without its `id`, which is [reported, not swallowed](#9-caps-cost-and-diagnostics).

And these run but are **capped** (never silently — see §9): a probe binding more than `maxAnchors`
anchors, or a materialization exceeding `maxFanoutTotal` nodes, is rejected or truncated with a
diagnostic.

> **Design principle.** Every rejection has the same root: *the engine must always know the fetch
> is bounded.* A bound anchor, a declared shape, and hard caps are what make "splice a live API
> into a graph query" safe.

---

## 5. The join surface (reference)

The full declarative field reference lives in
[`README.md`](./README.md#joining-types-on-demand-virtual-joins-not-mirrored). The execution-relevant
distinctions:

### 5.1 Two link shapes (same engine)

- **id-match** (§3.1) — anchor is a real domain node; `keyField` and `recordKeyField` name a shared
  value (email/domain). The fetched record links to the real node whose property matches.
- **bridge** (§3.2) — anchor is an external-identity node (`GitHubIdentity`, `HubSpotOwner`).
  Declared with a `resolve:` chain instead of a plain `keyField`.

A `keyField` naming a **list-valued** property yields one key per element, not one key for the whole
list. A trial's `collaborators` or `interventions` names several organizations or drugs, and each is
looked up in its own right; blank and duplicate elements are dropped, so two anchors naming the same
value fetch it once. A scalar property is unaffected — it yields exactly one key, as always.

The same holds for a composite `producerKeyFields`: a list-valued member expands to one composite per
element, and a member with no value keeps its slot so the composite's arity is fixed.

A type name may be declared by more than one realm, and the declarations **merge**: every
declaration's `virtualJoins` accumulate onto the one type, while its shape — properties, including
the `identity: true` merge key — may live in any one of them. This is how a domain realm contributes
its own edge into a type another realm owns: it re-declares the name with only `virtualJoins`, and
those joins converge on the owning realm's identity. Identical join declarations collapse, so a
re-declared file never double-fetches; and the requirement that a type reachable by more than one
join carry an identity property is judged over the merged type, not each declaration alone.


**Identity-less rows.** A virtual type may declare NO identity property — the natural shape for
rows unique only as a combination (a per-(petition, constituency) signature count, a
per-(place, month) tally). Such rows materialize under an engine-minted deterministic id:
identical rows still merge, distinct rows never collide, re-fetching is idempotent. A type that
DOES declare an identity and ships a record without it keeps the old behaviour — the record is
skipped, because that is a data error, not a modelling choice.

### 5.2 Identity bridges — `resolve:` chains

A bridge links a canonical `Person`/`Organization` to an external identity for **any** person/org,
not just the connecting user, via an **ordered rule chain** (first match wins), resolved **lazily**
at query time for the anchors a query actually binds, and **persisted** (`writeThrough`) so it is
reused — re-resolved only after `refreshAfter`.

| rule | how it resolves |
|---|---|
| `existingBridge` | A fresh bridge already linked to the anchor — use it, stop. |
| `learnedHandle: { property, as }` | An explicit handle stored on the anchor (e.g. `Person.githubLogin`). No lookup. |
| `canonicalIdentity: { producer }` | The anchor's spine keys — emails for a Person, domains for an Organization, whatever a realm-declared spine is keyed by (§5.17) → call the producer. |
| `canonicalEmail: { producer }` | **Alias of `canonicalIdentity`**, for an email-keyed anchor. |
| `canonicalDomain: { producer }` | **Alias of `canonicalIdentity`**, for a domain-keyed anchor. |

The two aliases are one function: what a canonical rule keys on is decided by the anchor's spine and
by nothing else, so writing `canonicalEmail` on an Organization resolves by domain regardless. The
names are kept because realms are written with them, and a name its anchor contradicts is reported
when the realm loads — but `canonicalIdentity` is the one to write. A kind outside this table is
**refused at validate/install**; nothing will ever answer it.

Resolution is **batched** (one producer call for many anchors) and **negatively cached** (an anchor
that resolved to nothing is not re-queried until `refreshAfter`), so a recurring "who that I email
is on GitHub" doesn't re-storm the source. A fetch that *failed* is never negatively cached — "could
not ask" must not become "asked, nothing there" and then stay that way past a fixed token. The
negative cache is recorded on the bridge store, so it rides `writeThrough`: a join that declares
`writeThrough: false` has nowhere to record a miss and re-asks every query.

### 5.3 Producer kinds

| kind | fetch | keyed by |
|---|---|---|
| `remote` (alias `api`) | a gateway op — realm handler or learned REST API | the anchor's id/email/login (list, string-template, or path-param mode) |
| `sql` | a relational TABLE joined by a column, or SCANNED (`scan:`) ordered and bounded — the SELECT is **generated**, never authored, so the `governance:` grammar (§5.15) is enforceable by construction: governed exposure compiles into the column list, row-level `where:` predicates (`:userId` binds the acting user) inject into every statement | the anchor key batch, bound into `WHERE <keyColumn> IN (…)`; rows echo the key column. A `scan:` producer takes no keys: the pinned value chooses the ordering column and is echoed under `echoKeyAs` |
| `compute` | an in-process function over the keys (scores, rollups, synthesis) | the anchor key; no external I/O |
| `vector` | top-k semantic relevance to the anchor's **text** — a fused semantic + lexical retrieval, ranked as one list (§6.6) | nothing — *relevance is the join* (§6) |
| `keyword` | top-k **lexical** (fulltext, exact-token) match to the anchor's text — the honest fit for "MENTIONS \<term\>" | nothing — same relevance contract as `vector`, only the mode differs (§6.6) |
| `agentic-rag` | a **bounded LLM retrieval loop** over the same index: reformulates, runs both modes, reads further into inconclusive candidates, returns only documents it *judges* fit the edge's `intent` brief | nothing — relevance as a judgment (§6.6); EXPENSIVE, select explicitly |
| `remote-search` | top-k **lexical** match via the REMOTE store's OWN search API (a gateway op with `{query}` substituted per anchor — e.g. Drive `fullText contains`); live, nothing ingested | nothing — same relevance contract as `keyword`, but the source searches itself; per-match `mode:'keyword'`/`rank` on the edge, score is a neutral 1.0 (matched, not similarity) |
| `generative` | an LLM **invents** plausible records ("suggest things like X"), each resolved onto the spine via `resolveVia`; demand-driven (re-probes with a growing exclusion until enough survive) | the anchor's name/text, batched into ONE prompt |
| `aggregate` | gathers the anchor's connected neighborhood and LLM-**reduces** it to ONE record (a taste summary, a digest) | the anchor's identity; one record per anchor |
| `extract` | gathers the anchor's neighborhood and **extracts typed records** from it — lazy ENTITIES, committed with real containment on first traversal (§5.6). `cardinality:` chooses fan-out (many records) or reshape (ONE record per anchor — §5.6.1) | the anchor key (per-anchor collect); many records per anchor, or exactly one |
| `tabular` | a published **CSV / TSV / XLSX / XML file** (optionally a zip of XML parts), downloaded lazily, cached deployment-wide, and joined on one of its COLUMNS (§5.8) | the value of `keyColumn`, compared to the anchor key under `keyMatch` |
| `feed` | an RSS/Atom **search feed** — one search per anchor key, each item a record; optionally FOLLOWING each item's page for phrase-anchored excerpts (§5.10) | the anchor key, substituted into the feed URL |
| `sparql` | a **SPARQL 1.1 endpoint** (Wikidata, UniProt, an enterprise triplestore) queried with an authored SELECT template; the whole key batch lands in one `VALUES` clause (§5.14) | the anchor key, serialized into the query's `{{keys}}` token; rows echo it under `keyVar` |
| `cypher` | a **remote openCypher graph** (Neo4j, Memgraph, Neptune — any engine speaking Bolt or openCypher-over-HTTP) queried with an authored read query; structurally read-only, governed by the shared `governance:` grammar (§5.15) | the anchor key batch, bound to `$keys`; rows echo it via the query's own RETURN |
| `elasticsearch` (alias `elastic`) | an **Elasticsearch index or alias** retrieved by relevance — lexical, semantic, or the two fused cluster-side in one search — with index / document id / score / mode on the edge, so every hit is citable (§5.16) | nothing — *relevance is the join* (§6); the anchor's text is the query |

All producers honour the **batch contract** (all keys at once, never N+1) and an orthogonal
`cache:` policy: `none` (alias `fresh`, the default — read live every query), `ttl` (a window in
seconds, with an opt-in `negativeTtlSeconds` for misses), `immutable` (reference data, held until
the process is restarted or maintenance clears it), and `graph` for aggregates and extraction
(§5.5/§5.6, where the committed graph itself is the cache tier).

> `kind: session` parses and is reported by the catalog, but the per-`AgentProcess` lifetime it
> names is **not wired** — it behaves as `none`, and validating a realm that declares it raises a
> warning saying so. Use `ttl` for a window you can state, or `immutable` for data that does not
> change.

#### Page-number origins

A `remote` producer with page-number paging starts at page 1 unless its declaration sets a
non-negative `startPage`. This lets a realm match a zero-based source without changing existing
one-based realms:

```yaml
paging:
  style: page
  param: page
  sizeParam: size
  startPage: 0
  size: 200
  maxPages: 2
```

This example fetches pages 0 and 1. `maxPages` always counts pages fetched, not the numeric value of
the final page. A short page ends the walk normally under either convention; reaching `maxPages`
on a full page produces the same truncation diagnostic. Omitting `startPage` fetches pages 1, 2,
and so on. A negative value is rejected. Cursor paging does not send or interpret `startPage`.

**`total`** names where a page says how many records the source holds in all (a JSONPath, e.g.
`data.meta.all_count`). With it, a page-number or offset walk reads page one, learns how many
pages remain, and fetches them **concurrently** rather than one after another — a 29-page sweep
costs about one page's latency instead of 29. Everything a serial walk promises still holds:
records come back in page order, a pushed-down `LIMIT` stops at the same page, a page that fails
ends the walk there with the pages before it and a warning, `maxPages` still caps and still warns
when it cuts, and the declared `cost.rate` still paces every call. Without `total` (or when the
page does not carry it) the walk is serial, because it cannot know how many pages there are until
a short one arrives. Cursor paging is always serial.

```yaml
paging: { style: page, param: page, size: 25, maxPages: 200, total: data.meta.all_count }
```

The **LLM-backed** kinds (`generative`'s `generator:`, `aggregate`'s `reduce:`, `extract`'s `extract:`) take optional
per-edge tuning — `role:` (a portable, world-defined model role id such as `chat_cheap`; **never a
concrete model name**, which stays an ops concern) and `temperature:`. A query can override both for one
fetch with the `ai.model` / `ai.temperature` edge directives (§7.2).

#### 5.3.1 Cost discipline for LLM-backed producers — `defaultWant` and `tools:`

Two producer knobs dominate the wall-clock of a generative fetch, and both default in the
expensive direction if authored carelessly:

- **Size `defaultWant` to the edge's real consumers, not to abundance.** The demand loop runs a
  FULL LLM generation round per iteration, sequentially, re-probing with a growing exclusion set
  until `want` survivors exist — and steering hints, confidence floors, and spine-resolution
  misses all shrink each round's survivor yield. A `defaultWant: 25` behind queries that
  `LIMIT 5` can burn ten-plus sequential LLM calls chasing survivors nobody will see (observed:
  12 rounds / 43 seconds from 2 anchors under a steering hint). Set it just above the largest
  LIMIT the edge's saved views and skill queries actually use; a filtered/steered run then
  converges in a round or two.

- **Scope `tools:` to the narrowest search surface that can answer.** A generator's `tools:` list
  is a capability grant, and every granted tool is an invitation the model will eventually
  accept: the broad `web` group attaches *every* web-ish tool in the world (brave AND
  wikipedia AND generic search), and a producer hunting one known site will wander into the
  irrelevant ones (observed: encyclopedia summary lookups with another site's page titles —
  guaranteed misses — plus retry churn). Name the concrete tool that serves the producer's
  source (`tools: [brave]`); reach for the broad group only when the producer genuinely cannot
  know where its answer lives.

### 5.4 Entity canonicalization — the spines a join anchors on

Every example above anchors on a canonical `Person` or `Organization`. Those are **spines**: the
single node a real human or company resolves to within one visibility scope, no matter how many
sources mention them. A world-visible spine is keyed deterministically — **Person by
`(worldId, WORLD, Person, email)`, Organization by `(worldId, WORLD, Organization, registrable domain)`**. A context-private
spine substitutes its `contextId` for `WORLD`, so two records
from different sources (a HubSpot contact and a GitHub commit author, both `rod@embabel.com`)
converge on **one** `Person`, and "my contacts' companies" lands on the same `Organization` the
email graph already built.

**Source records canonicalize onto a spine via projection metadata on the type** (not a separate
pipeline). A property tagged `hub: <Spine>` is the value that keys the spine; a property tagged
`relationship/target/matchBy` links the record to a second spine:

```yaml
- name: HubSpotContact
  properties:
    email:    { identity: true, hub: Person }             # → Person, by email
    company:  { metadata: { relationship: WORKS_FOR, target: Organization, matchBy: name } }
```

**`hub:` is the opt-in, and it is explicit.** `identity: true` alone says what identifies the
*record*; it never implies a spine, because most identities (an issue number, an invoice id) are
nobody's canonical person. A type with no `hub:` is not canonicalized.

**`hub:` may sit on any property, not only the identity one.** The two are often different facts. A
CRM partner is identified by the CRM's own id, and every join inside that realm keys on it; what
identifies the *company* is its website:

```yaml
- name: OdooCustomer
  properties:
    id:       { identity: true }                          # the record, for this realm's own joins
    website:  { hub: CustomerAccount }                    # the company, for everybody's
```

Several properties may carry the same `hub:` (a website and a billing email, say); each non-empty
value is normalized by the spine and contributes a key. A type attaches to ONE spine this way — the
first `hub:` names it.

The `relationship`'s **merge key is the spine's key, not the field text** — `company`'s value is
only the display name; the `Organization` is keyed by the contact's email **domain**. So two contacts
on `@acme.com` share one `Organization` however they spelled "Acme", and a freemail/no-domain contact
yields **no** `Organization` (a name alone never invents a spine — fuzzy name resolution is a
**separate tier, never in the query path**; it runs on the eager/offline population path, not on the
on-demand hop, because a per-entity model call over thousands of fetched records would be one LLM
call each and defeat the point of a deterministic hot path). The result is a durable
`(p:Person)-[:WORKS_FOR]->(o:Organization)` edge onto the current visibility-scope spine — read the contact's company
through its canonical Person, no source-specific company walk.

This runs **on demand, and persists ONLY the spine** — never the source record. When a query
materializes virtual records of a canonical-bearing type, a pre-pass resolves each record onto its
canonical Person/Organization, writes the durable derived edges (`HAS_CONTACT`, `WORKS_FOR`),
enriches the canonical fields straight from the fetched record, and stamps the source on the
canonical's `sources` provenance set — then the main query reads the deduped graph, so
`(p:Person {primaryEmail})-[:WORKS_FOR]->(o:Organization {name:'Acme'})` works on first ask. The
**source record itself stays virtual**: no `:HubSpotContact` mirror node is persisted, because its
mutable CRM state (lead status, last activity, owner) would only go stale — those fields are
re-fetched live each query. Identity and durable relationships are durable; source *state* is not.

**Resolution is O(log n), through indexed key-nodes.** Each spine has a key-node — `EmailAddress`
(`email-address:<addr>`) for Person, `Domain` (`dom:<domain>`) for Organization — with a uniqueness
constraint on `(worldId, visibilityScopeId, id)`. Resolving a key is one indexed hop
(`(:Domain {id})-[:USED_BY_ORG]->(o:Organization)`), never a scan, and the key-nodes are **shared**
with the email/sender graph inside that visibility scope, so a canonicalized record and an emailed
person dedupe to one spine. The
spine's own `(worldId, visibilityScopeId, id)` is uniqueness-constrained too, so the deterministic
MERGE can never fork a duplicate or merge contexts/customers. Context-private evidence cannot mutate
a `WORLD` spine without explicit policy-checked promotion. Organization-wide spines require an
explicit `orgId`, verified membership, and an organization-scoped key; a bare email or domain is
never cross-context or cross-world authority.

**The two built-in spines are not hardwired — they are config.** A spine is declared by a
`CanonicalSpec` (label, key property, id prefix, normalization primitives, key-node + edge); Person
and Organization are just the two built-ins. An operator may add a `Place`, `Repository`, or
`Product` spine in the host's configuration, and source types join it with `hub: <newLabel>` — the
engine builds the hub, applies the key-node uniqueness constraint, and the join surface above works
unchanged. A realm may declare one too, which is the next section.

#### 5.4.1 Spines a realm declares — `spine:` on a type

Person and Organization cover people and the companies in your correspondence. They do not cover a
*customer account*, a *product*, a *site*, a *vessel* — the business entities that several systems
each hold a record of, and that a cross-system realm exists to bring together. A realm says so by
declaring the type a spine:

```yaml
# realm-business-vocabulary/types/vocabulary.yml
- name: CustomerAccount
  description: A company the business sells to, whatever system knows about it.
  spine:
    key: accountKey                                   # the key property on the spine node
    identityProperties: [accountKey, website]         # fields, on anything attaching, that carry the key
    normalize: [lowercase, extractDomain, stripTrailingDot]   # ordered
    require: hasDot                                   # a value that fails this keys nothing
    exclude: freemail                                 # nor does a value in this set
  properties:
    accountKey: "The company's registrable domain."
```

| Field | Meaning | Default |
|---|---|---|
| `key` | The scalar key property on the spine node. The multi-valued form is `<key>s`. | required |
| `identityProperties` | Property names that may carry the key, on the spine and on records attaching to it. `key` and `<key>s` are always included. | `[]` |
| `normalize` | Ordered primitives: `lowercase`, `trim`, `extractDomain`, `stripWww`, `stripScheme`, `stripTrailingDot`. | `[trim]` |
| `require` | `containsAt` or `hasDot`. A value failing it keys nothing. | none |
| `exclude` | A named exclusion set. `freemail` is the one defined. | none |

Everything else is derived from the label and is not the realm's to choose — the key-node is
`<Label>Key`, linked `(:<Label>Key)-[:IDENTIFIES]->(:<Label>)`, with the same uniqueness constraints
and the same one-hop indexed resolution as the built-ins. A realm that could pick its own key-node
label could collide with another realm's.

**The normalization is the contract.** It is the single definition of "the same account", applied to
every value from every realm that opts in. `https://www.AcmeCorp.com/about` from a CRM,
`acmecorp.com` from a helpdesk and `Billing@acmecorp.com` from a billing system are one key,
`acmecorp.com`, and therefore one node. No realm normalizes on its own side, and no realm needs to
know how another spells things.

**Other realms opt in with `hub:`**, exactly as for a built-in (above). The spine's realm does not
know who attaches, and an attaching realm names only the label.

**A join anchored on the spine normalizes BOTH sides.** The anchor's key goes out normalized:
`CustomerAccount → ChatwootConversation` on `accountKey` asks the helpdesk for `acmecorp.com`
whatever shape the account's key arrived in. And where the join's `keyField` is one of the spine's
identity properties, each RECORD's `recordKeyField` is read through the spine too before it is
matched to an anchor. So a realm joins on the source's own field, in the source's own spelling:

```yaml
- { anchorLabel: CustomerAccount, relationship: BILLED_AS, keyField: accountKey,
    recordKeyField: url, producer: lagoCustomersByDomain }     # url is "https://www.Stark.com/"
```

This is what makes a SEARCH safe to join on. A source often cannot be asked for a key exactly —
only with a substring match that also returns `notstark.com` for `stark.com`. Do NOT `echoKeyAs`
on such a producer: stamping the asked key onto whatever came back makes every stray a match.
Let the record's own field be the key; the customer whose url IS that account is linked and the
stray is not. A value the spine refuses (a freemail address, a bare word) matches nothing.
`resolve:` chains (§5.2) treat a realm spine as they treat Person: `canonicalDomain` /
`canonicalEmail` normalize through it.

**An account exists once something has keyed it.** A spine node is created when a query
materializes records of a type that opts in — canonicalization is on demand, and only the spine
persists; the source record stays virtual. Until some realm's records have been read, the spine is
empty, and a view that starts `MATCH (a:CustomerAccount)` answers nothing, truthfully. A realm
whose views start at a spine should ship the small view that walks its door (`MATCH (:OdooBook)
-[:HAS_COMPANY]->(:OdooCustomer)`) and say in its README that a surface reads it first. Opt in
from EVERY system that can name the entity, not only the one that seems authoritative: a company
support is helping and nobody bills is exactly the account an account-level view must not miss.

**Scope is the world.** A realm's spine exists in the worlds that installed the realm. Its nodes
carry the world, and the world is part of their id, so two worlds in one store never share an
account. Removing the
realm removes the spine from resolution; nodes already written remain, as any persisted node does.

**What a host MUST refuse, at load, as a loading problem — and register no spine:**

- **A label the host owns** (`Person`, `Organization`, or any operator-configured spine). An
  installed realm must not be able to change what every other realm's `hub: Organization` keys on.
- **Two realms declaring one label differently — both.** Which loaded last must never decide what
  identity means. The *identical* declaration restated by a second realm is one spine, not a
  conflict; that is how a realm restates a vocabulary it cannot yet declare a dependency on.
- **An unknown `normalize`, `require` or `exclude` name**, listing the known ones. Skipping a
  misspelled `lowercase` would key `Acme.com` and `acme.com` as two companies, everywhere, silently.
- **A spine label in another type's `parents:`**, pointing the author at `hub:`. See §5.4.2.

A host SHOULD also report a `hub:` that names no spine in the world — a misspelling, or a vocabulary
realm that was never installed. Nothing downstream fails: the type is simply never canonicalized and
every join expecting the spine returns nothing.

#### 5.4.2 An identity is a spine; a record is a parent label

A shared vocabulary has two tools and they are not interchangeable.

- **`parents:`** ([LABELS_AND_COMPOSITION.md](LABELS_AND_COMPOSITION.md)) stamps the ancestor's label
  on your nodes. Right for **records of a kind**: every `ChatwootConversation` and every
  `ZendeskTicket` *is a* `SupportCase`, and `MATCH (c:SupportCase)` should return all of them, as
  separate things, because they are separate things.
- **`spine:` + `hub:`** resolves your records onto ONE shared node. Right for an **identity**: an
  `OdooCustomer` and a `LagoCustomer` for the same company are two records *about* one account.

The test: **if two systems each hold one, are those two things or one?** Two → parent label.
One → spine. Getting it wrong in the first direction is the expensive mistake: `parents:
[CustomerAccount]` on three realms' customer types yields three `:CustomerAccount` nodes per company
with nothing joining them, and "accounts with an open ticket and an overdue invoice" is empty for
every account — no error, because no single node has both.

#### 5.4.3 Joining across realms — which mechanism

Every cross-realm join is one of these. Choose by what the two sides actually share:

| The two realms share… | Use | Notes |
|---|---|---|
| A person (email) or a corresponded-with company (domain) | built-in spine: `hub: Person` / `hub: Organization` | nothing to declare |
| Some other real-world entity, held under differently *shaped* keys | a realm-declared spine (§5.4.1) | the spine's `normalize` is the agreement |
| The *same exact* key, already identical in both (a purl, an ISO code, a CIK) | a plain virtual join on `keyField` / `recordKeyField` | declare `joinKey:` on both so a mismatch is caught |
| A key one side must *look up* (a login → an email) | a `resolve:` chain (§5.2) | learned handles persist |
| A key that exists only sometimes, with a fallback | a join `policy:` ladder (§5.15) | `ask` is not yet honoured; see there |
| No key — only meaning | a vector edge (§6) or a generative producer (§5.3) | a score, not an identity |
| A conclusion over both | a DERIVE rule (§13) | after the join exists, not instead of it |

Two things that are NOT a join mechanism, however tempting: seeding the same key by hand into both
realms (it works until the second customer), and a per-producer rewrite that normalizes one side to
match the other's spelling (it encodes realm B's format inside realm A).

### 5.5 Graph-cached aggregates — `cache: {kind: graph}`

For an `aggregate` producer, `cache: {kind: graph}` makes **the committed graph itself the cache
tier**: the first traversal collects the anchor's neighborhood, LLM-reduces it, and persists the
result as a **real, committed, scope-stamped node**; while the inputs are unchanged, a repeat
traversal is a plain graph hit with **zero model calls**. The canonical use is the on-demand document
summary:

```yaml
# producers/summaries.yml
- name: docSummary
  kind: aggregate
  edgeType: HAS_SUMMARY
  collect:
    targetLabel: Chunk
    via: PART_OF
    incoming: true            # the neighbors point AT the anchor: (Chunk)-[:PART_OF]->(Document)
    anchorLabel: Document
    anchorKeyProperty: uri    # PER-ANCHOR mode: each key is one document, owner-guarded
    text: "{{ text }}"
  reduce: { using: summarize, into: summary, args: ["Summarize this document faithfully."] }
  identityField: id
  anchorKeyField: docUri
  cache: { kind: graph }
```

`MATCH (d:Document …)-[:HAS_SUMMARY]->(s:Summary) RETURN s.summary` then generates once per document
and serves from the graph thereafter.

The rules, all engine-enforced:

- **Per-anchor collection.** `collect.anchorKeyProperty` switches the aggregate from its default
  per-principal mode (the anchor is the acting principal's own node when it has one; one reduction for the whole batch) to
  per-ANCHOR: each producer key names one anchor (matched on that property, guarded to the acting
  user's own nodes), and each anchor's neighborhood reduces independently. `incoming: true` flips the
  traversal for containment shapes like `(Chunk)-[:PART_OF]->(Document)`.
- **Freshness is an INPUT HASH, not a clock.** The persisted node carries a hash of the collected
  items plus the full reduce fingerprint (function, effective instruction, role, temperature, band).
  Edit the document — or the realm's prompt, or the role — and exactly that node regenerates, in place.
  The re-check costs one graph read; the model runs only when something actually changed.
- **Wordcount BANDS.** A query's `{ai: {wordcount: N}}` quantizes to the nearest persisted band —
  gist (~40 words), standard (~200), long (~600) — and each band is its own committed node. The
  directive-free canonical **is** the standard band; a nearby request (250) is a hit on the same node.
  The band's own target (never the raw request) folds into the instruction, so one band has one
  stable fingerprint.
- **Semantic steering stays transient.** A `hint`, `voice`, `realm.*` parameter, or a `model`/
  `temperature` override makes the result a non-canonical artifact: it is reduced fresh for that
  query, returned with its own transient identity, and **never persisted, never served from, and
  never overwrites** the canonical node. `{ai: {fresh: true}}` bypasses the hash check but writes the
  regenerated canonical through.
- **An honest miss never earns a node.** A reduction that answers with the no-answer sentinel stays
  transient and is retried on the next traversal — fabrication can never become durable.
- **Regeneration is progressive — for reductions whose results compose.** When content changes,
  only the changed portions re-reduce: the reduction proceeds over content windows, unchanged
  windows reuse their previous partial results, and the partials combine into the answer — a
  re-reduction for prose (`summarize`, `synthesize`), a pure truth combination for a verdict
  (`holds`: any supporting window ⇒ true; a grounded no with no true ⇒ false; all silent ⇒ no
  answer), a union for a semantic filter (`relevant`). Appending to a large document costs a
  reduction proportional to the appended content, not the whole document; the same content always
  yields the same windows. A reduction that must read the whole group at once (`classify`, `score`,
  `themes`, `cluster`, `extract`, `argmax`) always re-reduces whole. `{ai: {fresh: true}}`
  regenerates everything. A window whose reduction honestly found nothing keeps that answer until
  its own content changes.
- **Node-only, scope-stamped writes.** The engine commits only the node, stamped with immutable
  `worldId`, `contextId`, and access-policy revision. Two contexts summarizing an identical URI do
  not share a node unless policy explicitly promotes the result to `WORLD` visibility; two worlds
  never share one. The anchor edge is re-linked transiently per query. The node's label is stamped by
  the engine from the join's own target type — a realm never declares it, so it can never drift.

Cost intuition: the expensive thing (the reduction) runs once per
`(worldId, contextId, access-policy revision, anchor, band)` and again only on
change — and on change, only over the windows that changed; everything else — the freshness probe,
the hit path, the re-link — is indexed graph reads.

### 5.6 Typed extraction — `kind: extract` (lazy entities)

Where an aggregate reduces an anchor's neighborhood to ONE record, `kind: extract` fans it OUT: one
model call per anchor extracts a **list** of typed records — the
`(d:Document)-[:HAS_CLAUSES]->(c:Clause)` shape. The defining property is what the records *are*:

> **Extracted records are entities — part of the model, created lazily.** The first traversal
> extracts and commits them; from then on they are ordinary graph, returned by a **regular Cypher
> query with no engine involved**.

With `cache: {kind: graph}` (the intended mode), the first traversal commits, per record:

- a **real, scope-stamped node** carrying the target label **and `__Entity__`** — so extracted
  records surface wherever entities do (entity views, canonical KG queries), not only through the
  producing join;
- a **display `name`** — the extraction prompt must emit one per record (the record's own heading,
  or a composed fallback like `<category> §<section>`); a nameless entity is invisible to entity
  surfaces, and the engine logs a warning when records arrive without one;
- a **real containment edge** `(anchor)-[:edgeType]->(record)` — committed right after the query's
  read transaction closes (the open materialization transaction can hold locks on the anchor, so
  the edge write queues and lands the moment those locks release), owner-guarded on both ends so
  identical keys under two owners never cross-link; a hit whose containment is missing (a crashed
  earlier run) is healed on the spot;
- any **declared record-to-record links** (`links:`) — e.g. a clause whose `references` cites a
  sibling's `section` commits `(citing)-[:REFERS_TO]->(cited)`, document-local by construction.

```yaml
# producers/clauses.yml (realm-authored — the host ships no domain prompt)
- name: clauseExtraction
  kind: extract
  edgeType: HAS_CLAUSES
  collect:
    targetLabel: Chunk
    via: PART_OF|HAS_PARENT*   # structured docs nest chunks under sections — traverse the containment path
    incoming: true
    anchorLabel: Document
    anchorKeyProperty: uri
    text: "{{ text }}"
  extract:
    role: workhorse            # a portable ROLE — never a concrete model name
    prompt: |
      Extract every clause as {name, category, text, section, references, sourceIndex} …
  links:
    - relationship: REFERS_TO
      fromField: references
      toField: section
  cache: { kind: graph }
```

The aggregate rules carry over with extraction-specific twists:

- **Freshness is the shared input hash** (collected items + the extract fingerprint, including the
  prompt and the `links` declaration). On change the anchor's **whole stale set is REPLACED** —
  extraction counts can shrink, so stale rows are `DETACH DELETE`d, taking their containment and
  link edges with them; the fresh set re-commits nodes and edges together. Changing the realm's
  prompt migrates every anchor's set the same way, on next traversal.
- **Vocabulary is enforced, not requested.** A `oneOf` validation rule on a target-type property
  (e.g. the category taxonomy) is a hard gate: the engine DROPS any extracted record that violates
  it before persisting — prompt discipline alone does not hold this line.
- **Honest-empty is a transient miss**: nothing extractable ⇒ nothing persisted, nothing deleted,
  retried next traversal.
- **Steering stays transient** — a `{ai: {hint: …}}` or model override extracts fresh with
  transient identities and never touches the committed canon.
- **Demand applies across anchors** — a cold `LIMIT 1` over many documents extracts from the first
  anchor(s) only, until produced records satisfy the budget.
- **Extraction cost tracks the missing work, not document size.** Extraction over a document
  proceeds in bounded batches, each cached independently. A repeat traversal over unchanged content
  makes no model calls — including for portions that extracted to zero records. Editing part of a
  document re-extracts only the affected portion; the rest of the committed record set is untouched.
  A cancelled extraction keeps its completed work; re-asking resumes rather than restarts.
- **Partial materialization converges.** A `LIMIT n` traversal over cold content may stop extracting
  as soon as `n` records exist, leaving the committed set partial; any later, broader traversal
  completes it by extracting only what is still missing. Whatever sequence of asks produced it, the
  set converges to the same records a single full extraction of today's content would produce.
  Declared record-to-record links (`links:`) appear as soon as both ends exist; until then the
  citing field still records the claim. The engine's cost estimate for a partially extracted
  document counts only the remaining work — a query refused as too expensive can become allowed
  after part of the corpus has been materialized (e.g. via a narrowed opt-in ask).

Because the containment edge is real, `RETURN c` returns the entity itself — prefer it over scalar
projections when the caller wants the records rather than a report about them.

#### 5.6.1 `cardinality:` — reshaping a document into ONE record

Not every extraction fans out. A filing, a certificate, a form or a statement is **one** record of a
declared type, and declaring that is not cosmetic: it changes what the engine guarantees.

```yaml
- name: registrationReshape
  kind: extract
  cardinality: one            # one | optional | many (default: many)
  edgeType: HAS_REGISTRATION
  collect: { … }              # unchanged
  extract:
    fromType: true            # the field list comes from the target type (§5.6.2)
    prompt: |
      The excerpts below come from a company registration filing. Prefer the registrar's own spellings.
  cache: { kind: graph }
```

```cypher
MATCH (d:Document)-[:HAS_REGISTRATION]->(r:CompanyRegistration)
RETURN d.title, r.companyNumber, r.incorporationDate, r.status
```

| Value | One anchor yields | Zero records means |
|---|---|---|
| `many` (default) | 0..N records — today's fan-out | honest-empty, retried |
| `one` | exactly one record | the declaration was wrong or the source is unreadable — honest-empty, and reported |
| `optional` | 0..1 records | an ordinary answer (not every document is a filing) |

What `one`/`optional` guarantee, beyond the count:

- **One row per anchor, always.** The record's identity is the anchor's, so a re-read **replaces** it.
  A document can never accumulate two registrations, and "the registration" is never a coin toss
  between generations.
- **Fields scattered through the document assemble into one record.** A long source is read in parts;
  each part reports only what it shows, and the parts are combined. Where two parts state the same
  field differently, the earlier statement wins and the disagreement is reported rather than silently
  resolved. A list-valued field (a filing's officers) **unions** across parts instead of stopping at
  the first.
- **All-or-nothing.** If any part of the source could not be read, nothing is written and nothing is
  returned: half a form is wrong, not incomplete. The next ask re-reads it. For the same reason, a
  `LIMIT` never truncates a single record mid-way — it stops between anchors, never inside one.
- **Freshness is whole-document.** A single record spans the whole source, so no part of it is fresh
  on its own: any change re-reads the form. (The `many` regime's part-by-part incrementality does not
  apply, and would have nothing to serve until the whole form had been read anyway.)
- **Declared types hold on the stored record.** A property declared `int`/`number`/`boolean` is stored as
  that type, not as the wording the source used: `1,240` is a number you can compare with `>`, and
  `$120,000.50` does not become 120. This holds for the record as later read by ORDINARY Cypher, not only
  through the join — which is the point, since the record becomes plain graph after first materialization.
  (This applies to every `kind: extract` producer, not only the single regime; it simply matters most here,
  where a form's fields are dates, counts and amounts rather than prose.)
- **A "not stated" answer is silence, not a value.** A source that states nothing for a field leaves
  it absent; the record never carries `N/A`, `unknown` or a placeholder as though it were data, and a
  source that states nothing at all yields no record rather than an empty shell.

Everything else in §5.6 is unchanged: records are entities, the containment edge is real, declared
vocabularies are enforced, steering stays transient.

#### 5.6.2 `fromType:` — the type states the shape, the prompt states the domain

With `fromType: true` the record's field contract — names, types, which are lists, and any declared
`oneOf` vocabulary — is taken from the **target type's own declaration** rather than restated in the
prompt. The prompt is then free to say only what the type cannot: what the document is, and what to
prefer when it is ambiguous.

This closes a gap that is otherwise silent. A typed extraction that spells its fields out in prose
states its shape twice — once for the model to read, once as `properties:`/`validation:` for the
engine to enforce — and the enforcing copy always wins. A vocabulary that has drifted out of the
prompt is one the model is never told about, whose records are dropped on arrival, and the symptom is
an empty result with no error. Derived, the two cannot disagree.

Default is off, so existing extractions are unaffected. Turning it on changes the extraction and
re-reads each anchor once, exactly as a prompt edit does.

The excerpts themselves are supplied whether or not the prompt renders them, so a prompt that carries
only domain guidance is a complete prompt. (A field list with no text to read is the one input that
reliably makes a model invent a plausible record.)

---

### 5.7 `keyTransform` — rewriting the key into the source's own query language

A source's query language is a property of the **source**, not of any question asked of it. Put the
knowledge in a lens and every lens re-implements it; declare it on the producer and every surface —
lenses, chat, MCP — gets the same translation, with no code shipped by the realm.

ClinicalTrials.gov reads `AND` / `OR` / `NOT` as operators only in UPPERCASE. So `parkinsons and
anxiety` returns 2 trials where `Parkinson AND anxiety` returns 64, and `respiratory diseases other
than covid` returns 0 where a `NOT` expression returns 51,961. The danger is the shape of the
failure: a plausible number rather than an error, with a confident answer built on top of it.

```yaml
- name: trialsByDisease
  kind: remote
  operation: searchByDisease
  keyArg: queries
  echoKeyAs: matchedFor          # REQUIRED with a transform — see "identity" below
  keyTransform:
    kind: ai
    instruction: |
      Rewrite a disease phrase as a ClinicalTrials.gov Essie expression.
      AND / OR / NOT are operators and MUST be uppercase; quote multi-word phrases.
    examples:                    # few-shot pairs YOU author: the cheapest way to pin a dialect
      - input: "parkinsons and anxiety"
        output: '(Parkinson Disease OR Parkinsonism) AND (Anxiety OR "Anxiety Disorders")'
    cacheSeconds: 604800
```

**Identity is never rewritten.** The transform applies to the outgoing argument only; the key's
identity — what the join matches on, and what `echoKeyAs` stamps onto each record — stays the
caller's phrase. Get this wrong and the failure is silent: if your records echo the *sent* string,
they no longer match the anchor's `keyField`, the join edge never forms, and every row vanishes while
the query still reports success. **A producer that declares `keyTransform` must also declare
`echoKeyAs`** (or otherwise guarantee its records carry the original key).

Three rules keep it honest, and none is optional:

- **Cached per phrase**, so the same question searches the same way instead of being re-rolled.
- **Echoed**, so the executed expression can be shown and challenged. Surface it — a rewrite a user
  cannot see is one they cannot argue with.
- **Falls back verbatim** on any failure, to the behaviour you had before, never to an empty result
  that would read as "there is nothing".

The cost to accept: a model now sits in the key path, so a fetch is no longer purely determined by
the query text. The cache and the echo are what make that auditable.

---

### 5.8 `tabular` — a published file as a joinable source

A large part of the open-data estate publishes no API. It publishes a **file**: a CSV, a
tab-delimited export named `.csv`, an XLSX with a provenance banner above the real header. A
`tabular` producer makes that file a first-class join target — the realm declares WHERE the table
is and WHICH column joins, and nothing else.

```yaml
producers:
  - name: paymentTimesByAbn
    kind: tabular
    url: "https://example.test/register/{today}-report.xlsx"
    format: auto              # csv | tsv | xlsx | xml | auto (default: sniff extension, then bytes)
    sheet: "Standard report"  # xlsx only; omit for the first sheet
    headerRow: auto           # or a 1-based row number
    keyColumn: "ABN"
    keyMatch: digits          # exact (default) | ci | digits
    keyAs: abn                # the join's recordKeyField
    rowIdAs: recordKey        # OPTIONAL synthesized per-row id — see below
    userAgent: browser        # some publishers 403 a bare client
    fileCacheSeconds: 21600    # TABULAR ONLY — see the note below
    maxRows: 200000
    maxRowsPerKey: 500
    project:
      businessName: "Business Name"
      paidWithinTerms: "% paid within terms"
```

**Guarantees**

- **Nothing is downloaded until a query traverses the edge.** Declaring a 200MB register costs
  nothing; a query that never reaches it never pays for it.
- **One copy per deployment, not per world or per key.** The file is cached by resolved URL and
  revalidated conditionally, so an unchanged register is not re-transferred. A batch of anchor
  keys reads one file.
- **`fileCacheSeconds` is THIS producer's, and an unknown field voids the whole file.** It caches a
  downloaded document, so it exists only on `tabular`. A `remote` producer caches with
  `cache: { kind: ttl, seconds: … }` alone. Putting it on a remote producer is not ignored, and the
  cost is not confined to that one field: the file fails to parse, so **every producer declared in
  it ceases to exist** — not some of them, the whole file. It is reported as a problem on the
  OWNING REALM, naming the file and the parse error, and logged as a warning, because a file of
  producers vanishing is not a detail to leave sitting in a list somebody has to go and read.

  It used to be silent, and that is worth knowing if you are reading older material: the realm said
  `problems: 0` while every producer in the failed file did not exist, and the only symptom was
  `Unknown producer '<name>' in plan` when a query finally needed one — surviving a refresh and a
  restart, because nothing was stale, the file had simply never parsed. Check each field against
  the producer's own `kind`.
- **A banner above the header does not become the schema.** With `headerRow: auto` (the default)
  the header is detected by column shape, so the "Generated on …" lines these exports carry are
  skipped rather than parsed as column names.
- **The same rows always yield the same records.** Detection, matching and projection are
  deterministic; no model is involved anywhere in this producer.
- **`keyMatch: digits` reconciles the four ways an identifier is published** — spaced, unspaced,
  as an integer, and as a float (`12345678901.0`). It is opt-in: `exact` never reconciles
  silently, so a realm chooses when identifier forms may be treated as equal.
- **A capped read says so.** Hitting `maxRows` is reported as a truncation warning — the rows
  returned are a prefix of the file, never presented as all of it.
- **A publisher outage does not become a factual claim.** If the download fails and a cached copy
  exists, the cached copy is served and the staleness reported. If none exists, the hop returns no
  rows *with a diagnostic* — never a silent empty that reads as "no such record".
- **A `keyColumn` that is not a column of the file is reported**, listing the columns that were
  found. Publishers rename columns; a realm that goes stale must fail visibly rather than return
  zero rows forever.

**`rowIdAs` — for registers whose rows carry no identifier.** A materialized record MUST carry the
target type's identity property; one that doesn't is DROPPED, and the fetch REPORTS how many it
dropped and which property they lacked. It did not always: a register with no usable id produced
nothing at all while every fetch log said it matched, which reads exactly like an empty source.

Two of the three cases need no declaration at all. A type that declares NO identity property — a
per-(petition, constituency) signature row, a per-(place, month) count, anything whose uniqueness is
the combination rather than a field — is given a deterministic id minted from the record's own
values: identical rows still MERGE, different rows never collide, and re-fetching is idempotent.
A type that DECLARES an identity and receives a record without it is a data error, and that record
is dropped and counted.

`rowIdAs` is for the third case: a type that MUST declare an identity because queries key on it,
fed by a register that has no per-row id to give (the NDIS compliance CSV's Provider Number is blank
on 98% of rows). `rowIdAs: recordKey` stamps a deterministic `<normalized key>:<ordinal>` id, and
the type declares that property as its identity. It is honest about what it is: a ROW POSITION within one file
version, not a source identity — stable enough for transient virtual rows, and not a key to store
or compare across file versions.

**Date tokens carry a FORMAT.** Report URLs use the publisher's own date format, not ISO:
`{today-90d|date:dd-MMM-yyyy}` renders `03-May-2026`. Without the format suffix a token is ISO
(`{today}`, `{today-7d}`). A `|`-separated composite anchor key can safely fill multiple report
parameters: `{key1|date:dd-MMM-yyyy}` and `{key2|date:dd-MMM-yyyy}` render the two ISO key parts
in the publisher's date format. Numbered parts are URL-encoded; malformed dates fail loudly.

**Costs and limits**

- `maxRows` bounds the parse; `maxRowsPerKey` bounds how much one popular key may contribute.
  Both are honest caps, both are reported.
- `url` accepts `{today}` / `{today-Nd}` for date-stamped filenames, and `{key}` or numbered
  composite parts `{key1}`..`{key9}` — any key token makes the producer **one download per
  anchor**, appropriate only for a genuine per-entity or per-window export.
- Every value is a **string**. A leading-zero identifier survives; arithmetic is the query's job.
- Omitting `keyColumn` returns the whole table for every key. Legitimate for a small catalogue,
  wrong for anything large.

**XML registers — `format: xml` + `recordElement`.** Some registers publish structured XML rather
than a table (the ABN Bulk Extract). Declaring `format: xml` requires `recordElement`, the element
that delimits ONE record; the declaration is rejected at load without it. Columns are then
**slash-joined paths relative to that element**, with `@attr` for attributes:

```yaml
  - name: abrByAbn
    kind: tabular
    format: xml
    recordElement: ABR
    url: "https://example.test/public_split_1_10.zip"
    urls:
      - "https://example.test/public_split_11_20.zip"
    keyColumn: "ABN"
    keyMatch: digits
    project:
      abnStatus: "ABN@status"                                    # attribute of a child element
      legalName: "MainEntity/NonIndividualName/NonIndividualNameText"
      otherNames: "OtherEntity/NonIndividualName/NonIndividualNameText"
      lastUpdated: "@recordLastUpdatedDate"                      # attribute of the record element itself
```

- A path that **repeats** within one record (trading names) yields ALL its values joined with
  ` | ` — no occurrence is silently dropped.
- A path absent from a record is **absent** from that record, never blank-filled.
- An `xml` file that is a **zip container** is read entry by entry (`.xml` members, in name
  order) as one logical file. The parse streams throughout: file size is bounded by `maxRows`,
  never by memory.
- `keyColumn` is a path like any other; `keyMatch` applies unchanged.

**`urls` — one register split across several files.** A register published as multiple files (the
ABN Bulk Extract is two ~500MB zips) is declared as ONE producer: `url` plus additional `urls`.
Every anchor key is matched against every file and the results concatenated — so a key found only
in the second file can never read as absent. Each file is fetched and cached independently,
deployment-wide, and any URL may carry the usual tokens. Two producers over the halves would force
every consumer to remember the union; forgetting it would silently halve the register, which is
why the split lives in the producer, not in queries.

**When NOT to use it.** A file that changes on a feed cadence and is small and static enough to
enumerate is still not reference data — but a source with a real API is better served by `remote`,
which can push predicates down to the server instead of filtering a downloaded file.

### 5.9 Range partitioning — `partition:` on a `remote` producer

A producer whose anchor key is a DATE RANGE (`<fromInstant>/<toInstant>`, ISO instants) meets a
hard limit on sources that cap one request: the page cap. A two-month window against a feed that
returns newest-first and caps at `maxPages * size` records silently yields the newest slice — a
result that LOOKS like a recent window, which is worse than an error. `partition:` fixes this at
the source declaration:

```yaml
- name: releasesPublishedInWindow
  kind: remote
  keyArgs: [from, to]
  echoKeyAs: publishedWindow        # REQUIRED with partition (see below)
  paging: { style: cursor, ..., maxPages: 12 }
  partition: { unit: day, maxUnits: 366 }
```

The engine splits each range key into per-`unit` sub-ranges (UTC-aligned; `hour` | `day` | `week`
| `month`), fetches each sub-range as its own request — **each with its own `maxPages` budget** —
and stamps every record back to the CALLER's key.

**Guarantees**

- **Nothing about queries changes.** The same `MATCH` on the same window key returns the same
  shape — just complete. The expansion is invisible to the join, the cache, and the query;
  records always link to the key the caller wrote, never to an engine-minted sub-range.
- **Union of parts = whole.** Sub-ranges tile the window exactly (contiguous, half-open, the
  caller's own `from`/`to` at the edges). A record a source returns on both sides of a boundary
  (inclusive-bounds sources) is deduplicated.
- **A key that is not a range — or spans a single unit — is fetched AS-IS.** Declaring
  `partition:` never adds calls to a small request, and a mixed batch (an id and a window)
  behaves.
- **Truncation is per sub-range and NAMED.** A day that still caps reports "truncated … for key
  '2026-06-30…/2026-07-01…'" — the caller knows which slice to re-ask, and every other day stays
  complete. COMPLETE now means "every sub-range exhausted its feed", a claim with a proof.
- **`maxUnits` is a backstop, not a result-shaper.** A range expanding past it keeps the MOST
  RECENT `maxUnits` sub-ranges and reports the uncovered head by name — loudly, never silently.
- **Overlapping ranges share sub-fetches.** Two windows in one batch that share days fetch each
  shared day once; each caller's records carry its own key.
- **Progress is per sub-range** — a long scan ticks "day 18 of 61" on the events stream instead
  of an unmoving spinner.

**`emptyErrorPatterns` — when a source says "no records" through an HTTP error.** Some APIs answer
an empty range with a failure status rather than an empty list (AusTender returns HTTP 400
`"No Records found for Date Range"`). Partitioning turns that from a rare edge case into a
CONSTANT one — every quiet weekend is an empty day — and a warning storm buries the real
diagnostics. Declaring the patterns on the producer maps a matching failure to an honest empty
page: no diagnostic, no retry, no breaker; the walk simply ends there.

```yaml
  emptyErrorPatterns: ["No Records found"]     # substring, case-insensitive
```

Declare it ONLY for text that unambiguously means zero results. Anything broader converts real
failures into silent empties — the exact deception the rest of this spec exists to prevent.

**Costs and rules**

- `partition` requires `echoKeyAs`: sub-fetches ask the source with keys the caller never wrote,
  so the source cannot echo the caller's key — the stamp is the only honest link. A spec without
  it fails at load time.
- A complete broad scan makes MORE calls (one-plus per unit) and takes proportionally longer.
  The producer's declared `cost.rate` paces them; pair broad scans with a watched/background
  invocation rather than a bigger client timeout.
- The realm picks `unit` from the source's real volume: a feed of hundreds/day partitions by
  day; a firehose by hour; a sparse register by month. `maxPages` then only has to cover the
  busiest single unit.

### 5.10 `feed` — an RSS/Atom feed as a keyed source

Some sources publish no JSON API — they publish a **search feed** (ParlInfo's Hansard search,
media-release feeds, gazettes). A `feed` producer makes one a join target: each anchor key becomes
one search, each feed item one record (`title`, `url`, `publishedAt`, `summary`), stamped with the
key under `keyAs`.

```yaml
- name: estimatesMentions
  kind: feed
  url: 'https://parlinfo.aph.gov.au/parlInfo/feeds/rss.w3p;query=Dataset:estimate Content:"{key}"'
  redirectMeansEmpty: true      # this source signals ZERO RESULTS with a redirect
  keyAs: searchPhrase
  maxItems: 8
  minIntervalMs: 1000
  cache: { kind: ttl, seconds: 3600, negativeTtlSeconds: 3600 }
```

**URL template.** `{key}` is the whole anchor key, percent-encoded. Composite keys split on `|`
into `{key1}`..`{key9}`, and a part can carry a DATE FORMAT: `{key2|date:dd/MM/yyyy}` parses that
part as an ISO date/instant and renders it in the source's own format — so a date-ranged search
(`Date:{key2|date:dd/MM/yyyy} >> {key3|date:dd/MM/yyyy}`) is first-class, never string-smuggled.
A non-ISO date part fails that key loudly rather than searching for garbage.

**Guarantees**

- **`publishedAt` is an ISO instant whenever the feed's date parses** (RFC-1123 with numeric
  offsets included); an unparseable date passes through raw rather than being dropped.
- **`redirectMeansEmpty: true` maps a redirect to an HONEST EMPTY**, never a failure and never a
  followed link — for sources that signal "no results" by redirecting to an error page. Without
  it, redirects are followed normally.
- **Every failure is a diagnostic plus zero rows** — an unreachable feed, a non-XML body, an HTTP
  error can never read as "no mentions".
- **A capped read says so** — hitting `maxItems` reports a truncation.

**`follow:` — the item's PAGE, reduced to phrase-anchored excerpts.** With
`follow: { maxPages: 3, match: '{key1}', excerptChars: 4000 }` the producer fetches the first
`maxPages` item pages, strips them to text, and keeps ONLY bounded windows around matches of the
`match` term (a key template, so a composite key's phrase part anchors the excerpt, never its
date parts) into a `content` property. The whole page is never stored; a followed page that never
mentions the term contributes no content; a page that cannot be read is reported as UNKNOWN
content — never as "the term does not occur". Speaker-attributed transcript prose survives inside
the windows, which is the point: `summarize(m.content, '…')` over followed Hansard fragments can
honestly answer "what was discussed, and by whom". Follow knobs are ceiling-clamped (pages ≤ 5,
excerpt ≤ 8000 chars) and page fetches ride the same pace gate as the feed itself.

**A rogue realm cannot consume ridiculous resources — by construction, not by convention.** The
engine enforces ceilings a spec may tighten but never exceed, rejected at LOAD time:
`maxItems` ≤ 200; at most **25 anchor keys per fetch** (the excess is dropped and REPORTED);
a fixed byte cap on every response (5MB); fixed connect/read timeouts; sequential fetching with
a **pace floor of 500ms** between requests (`minIntervalMs` may slow a producer, never speed it
past the floor). A feed source is someone's search endpoint, not a bulk API.

### 5.11 Enumerated anchors — `WHERE anchor.key IN [...]`

A virtual anchor is normally pinned to ONE value (`(q:IntegrityQuery {abn:'…'})`). The BATCH form
is an enumerated `IN` over literals, and it behaves identically — one anchor per value:

```cypher
MATCH (q:IntegrityQuery)-[:HAS_TAX_RECORD]->(x:TaxRecord)
WHERE q.abn IN ['31010545267', '29008423005', '46221314841']
RETURN q.abn, x.name, x.taxPayable
```

This is the shape every screening question takes — *these twenty suppliers against that register* —
and it fetches ONCE for the batch (the producer's batch contract), not once per value.

**Guarantees**

- **Each value is probed for a REAL node first**, exactly as a pinned anchor is; only values with
  no real node are minted as virtual anchors. A mixed list works.
- **Duplicates collapse**: one anchor per distinct value.
- **It composes with the rest of the WHERE.** An `IN` combined with other conditions by `AND` still
  seeds (this matters more than it looks: scope conditions are ANDed onto every query, so an
  enumerated anchor is essentially always inside a compound).

**What does NOT seed, and why**

- **A parameter list** — `WHERE q.abn IN $abns`. There is nothing to enumerate when the query is
  read, so nothing is minted and the traversal yields no rows. **Inline the literals** when the
  anchors are virtual. (A `$param` list is fine for filtering nodes that already exist.)
- **An `OR` alternative** — `WHERE q.abn IN [...] OR q.abn IN [...]`. One branch of a disjunction
  must not enumerate the whole anchor set.
- **The mirror form** — `WHERE 'X' IN n.someList` narrows a node by list membership; it is a
  filter, not an enumeration of identities.

### 5.12 Bounded variable-length traversal — self-recursive joins

A virtual join whose anchor and target are the **same type** (an ownership registry's
`Company -[:OWNED_BY]-> Company`, a stud book's `Pony -[:HAS_PARENT]-> Pony`) may be traversed
with a variable-length pattern:

```cypher
MATCH p=(c:Company {companyNumber:'X'})-[:OWNED_BY*1..6]->(o:Company)
RETURN o.companyNumber, [r IN relationships(p) | r.sourceId]
```

**Guarantees.**

- Every hop up to the declared bound is resolved before the query evaluates: the traversal
  composes what the graph already holds with on-demand fetches — a hop already present advances
  the walk without a fetch, and fetched hops extend past the held data. Convergent paths dedupe
  to one node.
- Cycles terminate. A loop's closing edge appears in results; nothing is fetched twice.
- Rollups and subtree sweeps (`count`, `sum`, generation slices `*k..k`, path predicates) compose
  as ordinary Cypher over the resolved tree, and the same rows always yield the same tree.

**Costs.** The traversal spends against the join's own declarations, cumulatively across hops:
total resolved nodes against `maxFanoutTotal`, each hop's frontier width against `maxAnchors`. An
unbounded `*` is additionally capped at 10 hops.

**Degradation.** If the walk stops short of the query's declared depth — budget, frontier width,
or the unbounded-`*` cap — the result carries an `INCOMPLETE_TRAVERSAL` warning naming the hop
reached and the bound hit. Results then cover only the hops walked and any subtree total is a
**lower bound**. Nothing is ever silently truncated; a tree that simply ends, or ends exactly at
the declared depth, carries no warning.

**Per-hop provenance.** Every edge the traversal fetched carries three queryable properties:
`sourceId` (the record's identity at its source), `sourceName` (the producer that asserted it),
and `hop` (1-based depth). The result envelope additionally carries one `AUDIT_TRAIL` note
listing every claim — `hop N: (from)-[REL]->(to) source=<producer> sourceId=<id>` — with hops
that were already held in the graph shown as `source=mirror`. The trail is capped at 500 claims
(a count of the remainder is appended).

**Limits.** A variable-length pattern whose endpoints are *different* types is not a recursive
join and resolves only its first hop. `min` bounds (`*2..`) filter results as ordinary Cypher;
they do not change what is resolved.

**Worked example.** With `Company {companyNumber identity} OWNED_BY Company` declared over an
ownership registry, and `SC-100 ← SC-220 ← {SC-310, SC-320} ← HOLD-1` at the source,
`MATCH (c:Company {companyNumber:'SC-100'})-[:OWNED_BY*1..6]->(o) RETURN count(DISTINCT o)`
answers `4`, each `OWNED_BY` edge cites the registry record that asserted it, and the envelope's
audit trail lists the four claims in hop order.

### 5.13 Timely sources — `cache:` currency and the `freshness` result block

A producer's `cache:` declares how CURRENT its answers are:

- `cache: {kind: fresh}` (an alias of `kind: none`, the default) declares a **timely** source:
  every query re-reads the source, so the answer is the current state as of the query — re-running
  the same query re-observes the source. This is the declaration behind "what is the current X,
  joined to my graph", and a scheduled re-run of such a query is a fresh observation each time.
  Within ONE query the same read is made once: a fresh source asked for the same keys by two joins,
  or by the engine's own pre-pass and its fetch, is read once and the records reused, and the
  envelope bills one call. Independent fresh sources in the same query are read concurrently (their
  cost is the slowest, not the sum), exactly as cached ones are.
- `cache: {kind: ttl, seconds: N}` declares that an answer up to `N` seconds old is acceptable:
  within the window the same lookup is served without re-reading the source; past it, the next
  query re-reads. A query may force one live re-read of a TTL source with `{ai: {fresh: true}}` on
  the virtual edge; the fresh result then serves subsequent queries within a new window.

**The `freshness` block.** Whenever a query touched an external source, its result envelope carries
a `freshness` array alongside `rows` and `warnings`: one entry per source read,
`{producer, source, observedAt, keys}`, where `source` is `"live"` (read during this query) or
`"cached"` (served within its TTL window) and `observedAt` is the ISO-8601 time the source was
**actually** read — for a cached entry, the original read, never the query time. A join may mix the
two (a live anchor layer joined to TTL-served enrichment); each layer reports its own observation.
Failed reads never appear in `freshness` — they are reported in `warnings`. Purely graph-resident
answers omit the block.

### 5.14 `sparql` — a SPARQL endpoint as a keyed source

A `sparql` producer joins any endpoint speaking the SPARQL 1.1 Protocol — a public knowledge
graph (Wikidata, UniProt, EU Cellar) or an organization's own triplestore. The realm authors the
SELECT query ONCE; consumers only ever see the virtual join, and no query author writes SPARQL.

```yaml
- name: orgByRegistryId
  kind: sparql
  endpoint: "https://query.example.org/sparql"
  query: |
    SELECT ?registryId ?org ?orgLabel ?parentLabel WHERE {
      VALUES ?registryId { {{keys}} }
      ?org <http://example.org/prop/registryId> ?registryId .
      OPTIONAL { ?org <http://example.org/prop/parent> ?parent . }
    }
  keyVar: registryId
  keyForm: literal          # literal (default) | iri | number
  fetch:
    maxKeysPerCall: 100     # keys per request; larger batches are split
    timeoutSeconds: 60
    maxRows: 10000
    userAgent: "MyRealm/1.0 (contact url)"   # public endpoints often require one
    bearerTokenEnv: MY_TRIPLESTORE_TOKEN     # env var; never a credential in YAML
  cache: { kind: ttl, seconds: 86400 }
```

**The contract:**

- **One batch, one query.** The whole key batch is serialized into the query at the `{{keys}}`
  token — the natural spot is a `VALUES` clause — so a key set is one request (chunked only by
  `fetch.maxKeysPerCall`). A query without the token is rejected at fetch time with a loud error,
  never an empty result.
- **Keys are serialized safely, never spliced raw.** `keyForm: literal` emits escaped quoted
  strings; `iri` emits `<key>` and rejects keys that cannot be an IRI; `number` admits only
  numerics. A key the form cannot represent is SKIPPED and reported in `warnings` — it can never
  inject query text, and it can never silently read as "no such record".
- **Rows are the SELECT bindings.** Each solution becomes one record, result variable → value.
  Common XSD numerics and booleans arrive as numbers/booleans; IRIs arrive as their full string;
  a variable absent from a solution (an unmatched `OPTIONAL`) is absent from the record.
- **`keyVar` is the identity echo.** The declared variable must be selected and must carry the
  anchor key back on every row — that is what links a row to its anchor. A `keyVar` the query
  does not select is reported as a warning (the join would otherwise silently never form).
- **Honesty.** A failed fetch (network, HTTP error, unparseable response) is a `warnings` entry
  plus an empty result — never a silent 0. Exceeding `fetch.maxRows` truncates and reports a
  TRUNCATED warning. When the endpoint answers 429/503 with `Retry-After`, the fetch waits once,
  bounded, and retries before giving up.
- **Credentials stay out of YAML.** An authenticated endpoint names an environment variable
  (`fetch.bearerTokenEnv`); public endpoints need nothing.

Cost every consumer should know: each key batch is one live query against an endpoint the realm
does not control. Public endpoints enforce their own timeouts and rate limits; a realm should
bound its batches, declare a TTL cache, and expect the occasional refused query at peak — which
surfaces as a reported fetch failure, not as missing data.

### 5.15 `cypher` — a remote graph as a keyed source, and the `governance:` grammar

A `cypher` producer joins a FOREIGN property graph — another Neo4j, Memgraph, Amazon Neptune,
or any engine speaking Bolt or openCypher-over-HTTP — using an authored read query. It is the
property-graph sibling of `sparql`, in the same language the rest of the system speaks.

```yaml
- name: officersByName
  kind: cypher
  uri: "bolt://graph.example.org:7687"        # or https://…:8182/openCypher with protocol: http
  query: |
    UNWIND $keys AS key
    MATCH (o:Officer) WHERE o.name = key
    RETURN key AS name, o.countries AS countries
  connection:
    protocol: bolt            # bolt (default) | http
    username: reader
    passwordEnv: GRAPH_PASSWORD   # env var; never a credential in YAML
  governance:
    mode: governed
    expose:
      Officer: { properties: [name, countries] }
    mask: { countries: hash }
    caps: { maxRows: 5000 }
```

**The contract:**

- **One batch, one query per chunk.** The whole key batch is bound to `$keys` (rename via
  `keysParam`); the natural shape is `UNWIND $keys AS key MATCH … RETURN key AS <echo>, …`.
  Rows must echo the key through the query's own RETURN (declare `recordKeyField` on the join).
- **Structurally read-only.** A query containing any write clause — or `CALL` — is rejected
  before anything is sent, regardless of engine. Server-side read modes, where the engine has
  them, are a second layer, never the guarantee.
- **Rows are the returned columns.** A returned node or relationship value flattens to a map of
  its properties plus `_labels` / `_type`; a returned PATH is rejected (return the columns you
  need instead).

**The `governance:` grammar** — declarable on **every producer kind**, not only the two documented
here. It is enforced at the dispatch seam, so a `governance:` block means the same thing over an
API, a CSV, a feed or an index as it does over Postgres. What differs between kinds is *where* the
rules are applied, which the source answers and the realm does not choose:

| tier | what it means | kinds |
|---|---|---|
| compiled | exposure enters the query; unexposed data never leaves the source | `sql` |
| filtered | the request is narrowed before the fetch; the source may still send more than is kept | |
| enforced | rows arrive whole and are stripped on receipt — the data crossed the wire | every other kind, `cypher` included |

Only a **compiled** source can honour a row-level `where:`, because only a generated query has a
clause to put it in. Declaring one anywhere else is refused when the realm loads.

One vocabulary regardless of what sits behind the source:

- `mode: open` (default) — everything the query returns is visible. Two rules hold even here:
  execution is read-only, and the **secret reflex** — fields whose names look like credentials
  (password, token, api-key, private-key, ssn, …) are never returned, in any mode.
- `mode: governed` — the default inverts: a label or field not listed under `expose:` does not
  exist. A governed query that names an unexposed label is rejected loudly. Flipping a working
  open configuration to governed changes no query that only touched exposed data. (Note: the
  key-echo alias must be listed among the exposed properties, or the join cannot form.)
- `mask:` — per-field strategies in both modes: `hash` (deterministic digest — joinable, not
  readable), `last4`, `drop`.
- `caps.maxRows` — exceeding it truncates AND reports truncation.
- **Withheld is said, never silent.** Every field governance removes is reported in `warnings`
  as withheld-by-policy, so an absent field can never read as "no data". And a governance rule
  the source cannot enforce (row-level `where:` on an authored template) is a loud error,
  never silently ignored — that rule is reserved for sources that generate their own queries.

Cost every consumer should know: each key chunk is one live query against an engine the realm
does not control; declare a TTL cache and bound `maxKeysPerCall` accordingly.

#### 5.15.1 `sql` — governance by construction, the schema miner, and stored procedures

The `sql` kind (see §5.3) is the first source where every governance rule is enforceable:
the statement is generated, so `expose` decides what is SELECTed (an unexposed column never
leaves the database), `where:` predicates are part of every query, and the caps are a limit
clause. The key column is implicitly exposed — it is the identity echo, and the caller
already holds every key value.

```yaml
- name: ordersByCustomerEmail
  kind: sql
  datasource: warehouse          # declared in <realm>/sql/datasources.yml
  table: orders
  keyColumn: customer_email
  governance:
    mode: governed
    expose:
      orders:
        properties: [id, total, placed_at]
        where: "tenant_id = :userId"    # enforceable HERE — the template kinds must reject it
    caps: { maxRows: 2000 }
```

**Scanning a table: `scan:` instead of `keyColumn:`.** A keyed fetch answers *"the rows for
these anchors"*, which is the right shape for a source that charges per key. A relational
table is not that source, and a realm whose every producer needs keys cannot ask the table's
OWN question — *the largest donations ever disclosed*, *the most recent returns* — because
there is no anchor to name. A `sql` producer may instead declare `scan:`, which reads the
table ordered and bounded in ONE statement:

```yaml
- name: donationsRanked
  kind: sql
  datasource: au_donations
  table: donations_made
  echoKeyAs: by                  # every row comes back carrying the pinned value
  scan:
    orderBy: value               # the DEFAULT ordering column
    descending: true
    limit: 200                   # the most rows this door will ever return
  governance:
    mode: governed
    expose:
      donations_made:
        properties: [id, donor_id, recipient_id, value, made_on]
```

Reached through a virtual join whose anchor is PINNED rather than matched:

```cypher
MATCH (:DonationsTop {by:'value'})-[:TOP_DONATION]->(d:Donation)
RETURN d.value, d.made_on ORDER BY d.value DESC
```

Guarantees:

- **`keyColumn` and `scan` are mutually exclusive.** A producer answers one question or the
  other; one that declared both would silently drop a contract. Declaring neither is
  rejected at load.
- **The pinned value chooses the ordering column**, so one door answers more than one
  superlative (`{by:'value'}` and `{by:'made_on'}` on the same producer). A pin that does
  not name an EXPOSED column falls back to `orderBy` — ordering by a column the caller
  cannot read would make it an oracle over hidden values.
- **A scan is bounded by declaration.** `limit` is required and capped again by
  `governance.caps.maxRows`, whichever is lower. There is no unbounded scan: a door that
  returns the table is an import, not a question.
- **`echoKeyAs` is required**, and is what makes a keyless read joinable — every returned row
  carries the pinned value under that property, which is the join's `recordKeyField`.
- Exposure, `where:` predicates and masks apply exactly as they do to a keyed fetch.

**A join may declare a POLICY instead of one key.** _Partly implemented — see the implementation-status
note at the end of this section for exactly which guarantees hold today._ `keyField` says "match this column"; a policy
says how to try, in order, and what to do when the rules disagree:

```yaml
- anchorLabel: Order
  relationship: PLACED_BY
  keyField: id
  producer: customersById
  policy:
    rules:
      - key: { on: customer_id, to: id }                          # the declared key, via `producer`
      - key: { on: customer_email, to: email, ci: true, confidence: medium,
               producer: customersByEmail }                       # a DIFFERENT door, keyed by email
      - ask: "Which customer placed this order?"                  # a person, when rules disagree
      - none                                                      # no link is a legitimate answer
```

**A `key` rule may name its own `producer`, and usually must.** A producer is keyed by ONE field —
`keyArg` for a remote op, `keyColumn` for SQL, `keyTemplate` for a query string — fixed in its own
declaration. So a rule that matches on a different target field needs the door that is keyed by that
field: `customersById` cannot be asked for a customer by email, however the rule is written. Omit
`producer` and the rule uses the join's, which is right for the rule whose `to` IS the join's key and
wrong for every other. This mirrors a `resolve:` chain, where `canonicalEmail: { producer: … }` names
its door the same way and for the same reason.

Guarantees:

- **Rules are tried IN ORDER and the first that yields wins.** A rule that yields nothing does not
  end the chain — that is what a fallback is for.
- **Each rule fetches ONCE for every anchor still unresolved**, through its own producer, and anchors
  a rule settles leave the chain. A chain of three rules over a thousand anchors is at most three
  fetches, never one per anchor.
- **More than one match is not a match.** The rows become the candidates offered to a later `ask`,
  and resolution continues rather than picking one.
- **`ask` never runs before the rules that could answer without a person**, and where nobody can be
  asked — a scheduled run, an expired question — the chain falls through to the next rule rather
  than blocking.
- **Every resolved edge records HOW it was found**: the rule that matched and that rule's
  `confidence`, with an `ask` answer recorded as `asserted` — a person's word, not a probability.
- **`none` ends the chain with no link**, which is an answer and not a failure.
- **A question outlives the session.** Where the run can park, an `ask` becomes a durable question
  against that run — answerable minutes later, from another device, by someone who was not the
  asker. It is not a modal dialog and it does not hold a transaction open.
- **An answered `ask` is not asked again.** The resolved edge is written with its `asserted`
  confidence and the identity it settled, so the next query keys on it directly. A person is asked
  once per ambiguity, not once per query.
- **A declined or vetoed identity stays declined.** An `ask` answered "not the same" records a
  negative assertion, and no later automatic rule may re-link what a person has separated.
- A join with no `policy:` behaves exactly as before: key on `keyField`, once.

**Implementation status, and what a host must do about it.** In the reference host the **key ladder
is implemented**: `key` rules run in order, each through its own producer, each fetching once for
the anchors still unresolved, and `none` ends the chain. A rung goes through the ordinary fetch path,
so it inherits caching, cost budgets, diagnostics — and, where the anchor is a spine, the spine's key
normalization.

**Honoured.** A realm may depend on these:

- **`confidence`** — stamped on the resolved edge as `confidence`, alongside `matchedBy` naming the
  rung that matched (`"email -> customerEmail"`). This is what makes `WHERE r.confidence = 'high'`
  answerable, so an edge found by a name match never reads like one found by an id.
- **"More than one match is not a match"** — enforced. A rung returning several records for one
  anchor settles none of them; that anchor falls through to the next rung, where a narrower key may
  still resolve it. Do NOT design around this by giving a fallback rung a key that is unique on the
  far side — that workaround was advice for an earlier host and is no longer needed.

**Refused, not ignored.** The host rejects these at validate/install time, naming the join, per the
rule below:

- **`ask`** — parking a query on a person's answer is not implemented.
- **`ci: false`** — a case-SENSITIVE match is not something this engine can offer: the link side
  lowercases both sides, on every rung. An explicit `false` is refused rather than silently given
  the looser comparison it asked not to have. Omitting `ci` says nothing and is always fine.

This block previously reported `confidence` and the ambiguity rule as unimplemented after both had
shipped. That is the more damaging direction for a status note to be wrong in: an author who
believes a safety property is absent designs around one that is already there, and declines
provenance they are already entitled to.

The normative rule stands, and is why `ask` is refused rather than skipped:

> **A host that cannot honour a declared `policy:` rule MUST reject the realm at validate/install
> time, naming the join.** It MUST NOT accept the declaration and silently resolve without it.

A realm author who writes a fallback ladder and an `ask` has said, in the only place the format lets
them, that automatic rules are not enough for this join. Quietly resolving it anyway produces exactly
the wrong answers the policy was written to prevent — silently, on customer data, with no warning at
the point of use. Refusing the realm is loud, immediate, and fixable.

**A ladder is not a substitute for a spine.** A ladder answers "this join has more than one possible
key". A spine answers "these realms mean the same entity". If the fallback rungs exist only because
two systems spell one key differently, declare the spine (§5.4.1) and the ladder disappears.

**Mining a database into a realm.** A relational schema already IS a graph — tables are
labels, primary keys identities, foreign keys edges. The host can mine a datasource's
metadata into a realm scaffold: one type per table, one `sql` producer + virtual join per
foreign key, with the full column list pre-written into an open-mode `expose:` block. The
scaffold is ordinary realm YAML: inspect it, prune the exposure, flip `mode: governed`,
and no query that touched only exposed data changes.

**Stored procedures.** A realm may publish stored procedures as TYPED verbs in
`<realm>/sql/procedures.yml` — the declaration IS the allowlist (a procedure the realm does
not name does not exist; nothing is ever exposed by introspection), mirroring the GraphQL
`mutations:` gate. Declared args become the verb's typed signature on the code-mode surface
(`gateway.<datasource>.<name>`); result rows never include credential-shaped columns.
Procedures are VERBS, not joins: they are never reachable from virtual cypher.

```yaml
- name: repriceOrder
  datasource: warehouse
  procedure: reprice
  description: "Reprice an order to a new total."
  args: { orderId: string, amount: number }
```

**Datasources are read-only by default.** A datasource declaration that does not say
`readOnly: false` can only ever be SELECTed: every write path — `update` statements and
stored-procedure calls, including DECLARED procedures — is refused, and no procedure verb is
even published against it. Whether anything can mutate a database is answered by the
declaration file alone, never by auditing call sites: grep the realm for `readOnly: false`.

### 5.16 `elasticsearch` — a search index as a relevance source

An `elasticsearch` producer joins an Elasticsearch index or alias — self-managed or hosted —
by RELEVANCE: the anchor's text is the query, each hit becomes a virtual node linked to the
anchor it was found for, and the retrieval provenance rides on the edge. It is the relevance
sibling of `sparql`/`cypher`: the realm declares WHICH cluster, index and retrieval; no query
author writes a search body.

```yaml
- name: contractSearch
  kind: elasticsearch          # alias: elastic
  index: contracts             # an index or alias; wildcards allowed (docs-*)
  connection:
    endpoint: "https://cluster.example.org:443"
    apiKeyEnv: ACME_ES_API_KEY # env var; never a credential in YAML. Omit for an open cluster
    timeoutSeconds: 30
  retrieval:
    mode: hybrid               # hybrid (default) | bm25 | semantic | knn
    fields: [title, body]      # the lexical leg
    semanticField: body_semantic   # a self-embedding field; required by every mode but bm25
    rankWindowSize: 50
    rankConstant: 60
    rerankInferenceId: my-reranker   # optional; needs rerankField
    rerankField: body
  hits:
    k: 5
    minScore: 0.0
    idField: contractNumber    # optional: a business key as identity, instead of the document id
    project: { counterparty: "party.name" }
  cache: { kind: ttl, seconds: 300 }
```

Query it like any relevance edge, selecting it with `via` where a target is reachable more than
one way:

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(t:ResearchTopic)
MATCH (t)-[rel:RELEVANT_TO {via: 'elasticsearch'}]->(d:IndexedDocument)
RETURN d.title, rel.score, rel.docId, rel.index
ORDER BY rel.score DESC
```

**The contract:**

- **One search per anchor, composed cluster-side.** Hybrid retrieval is a single request the
  cluster plans and fuses — not several searches merged afterwards — so a fused ranking is the
  cluster's, and `k` is what comes back per anchor.
- **`hybrid` is the default and fuses lexical with semantic by reciprocal rank.** `bm25` is
  purely lexical and needs no semantic field, no inference and no model access — the mode that
  runs against any cluster. `semantic` and `knn` query a self-embedding field by TEXT: the
  index owns the embedding, so nothing is vectorized outside the cluster.
- **Every hit is citable.** Each match carries `score`, `docId`, `index`, `mode` and `rank` on
  the EDGE, not on the node. So a document relevant to two anchors keeps a distinct score and
  rank for each — and an answer built on retrieved documents can cite the exact document in the
  exact index it came from.
- **Identity is the document id, or a business key you name.** With `hits.idField` declared,
  that field IS the identity and a hit lacking it is DROPPED and reported — never silently
  keyed by the document id instead, which would split one document across two identities. The
  document id remains available as `docId` provenance either way.
- **`minScore` filters at the source.** Fused (RRF) scores are small and not comparable to
  BM25 scores; leave the floor at 0 for `hybrid` unless you have measured the distribution.
- **Reranking is opt-in.** A declared reranker re-scores the retrieval it wraps. It is the one
  stage that requires a deployed model, which is why it is off by default.
- **Honesty.** A failed search — network, HTTP error, unparseable or non-search response — is a
  `warnings` entry plus an empty result, never a silent 0 that reads as "you have no such
  documents". A rejected key (HTTP 401) is reported as an authentication problem, distinct from
  a generic failure. A declared `apiKeyEnv` that is unset is reported BEFORE the cluster is
  called, because an unset variable and a refused key have different fixes. A retrieval that
  cannot be composed as declared — a semantic mode with no `semanticField`, a reranker with no
  field — is reported by name as an authoring error rather than degraded to a weaker search
  that would return plausible, quietly worse results.

Cost every consumer should know: one live search per anchor, against a cluster the realm does
not control. A fan-out over many anchors is many searches — bound it with a narrowing match
before the hop, and declare a TTL cache for repeated questions.

### 5.17 Calendar history — `periods:` on a `remote` producer

A DATE-ADDRESSABLE source — one whose operation takes a calendar period as an argument
(a street-crime API's `date=YYYY-MM`, a daily feed's `day=`) — holds its own history, so history
is a KEY dimension, not something to accumulate. `periods:` declares it:

```yaml
- name: crimeMonths
  kind: remote
  operation: streetCrimes
  keyArgs: [lat, lng]
  echoKeyAs: key                    # REQUIRED with periods (records stamp back to the caller's key)
  cost: { rate: "1/second" }        # the fan-out respects the source's declared pace
  periods: { param: date, unit: month, count: 12, lag: 2, stampAs: month }
```

Each join key fans out into one call per period — `count` consecutive `unit`s (`month` | `day`),
newest first, stepping `lag` periods back from now for sources that publish in arrears. Every
record is stamped with its period under `stampAs` — **declare that property on the target type**,
because it is how queries see time:

```cypher
MATCH (p:Place)-[:HAS_CRIME_MONTH]->(m:CrimeMonth)
WITH p, m ORDER BY m.month
WITH p, collect(m) AS months
RETURN p.name, months[-1].total AS now,
       round(100.0 * (months[-1].total - months[0].total) / months[0].total, 1) AS changePct
ORDER BY changePct DESC
```

**Guarantees**

- **The past is free after the first read.** A CLOSED period is immutable — June's recorded rows
  do not change in September — so its result caches effectively forever (per key, per period).
  Only the period containing now refreshes on the producer's ordinary `cache:` TTL. A cold read
  pays `keys x count` calls, paced by `cost.rate`; every later read pays only the open period.
- **A quiet closed period is an answer, and it is kept.** An empty result for a closed period
  caches as long as a full one; the open period's empty follows the ordinary negative-TTL rules.
- **A failure caches nothing.** "Could not ask" never becomes "asked, nothing there" — the next
  read retries exactly the failed (key, period) pairs.
- **History does not backfill past the window.** `count` bounds what exists; nothing about a
  query widens it. Deepening the window is a spec change, and only the ADDED periods are new
  cost — everything already cached stays paid.
- `periods` requires `echoKeyAs`, and is mutually exclusive with `partition:` (one fans out
  calendar periods; the other splits a range-shaped key).

Cost every consumer should know: the fan-out multiplies the anchor set by `count`. Bound the
anchors as usual (`maxAnchors` declares the join's appetite), and for a deep window over many
anchors, drive the cold fill with a **fill** (§9.1) instead of one long query.


## 6. Vector edges — semantic joins in depth

A `vector` producer is fundamentally different from the keyed kinds, and the difference is worth
stating precisely because it is the engine's answer to *"relationships that have no foreign key."*

### 6.1 Similarity *is* the join

A keyed join asks: *"which records have `email == ada@example.com`?"* — an exact match. A vector
join asks: *"which records are **most similar in meaning** to this anchor?"* — a ranked
approximation. There is **no key to match on**; the anchor's **text** (a person's name, a meeting's
subject) is embedded and compared against an index. So a vector join is the only way to express
relationships like *"threads **about** Ada"*, *"docs **like** this one"*, *"chunks **relevant to**
this question"* — where no stored edge or shared id exists.

### 6.2 The score lives on the edge

The crucial modelling decision: similarity is a property of the **relationship**, not the node.

```cypher
MATCH (p:Person {name:'Ada Lovelace'})-[r:RELEVANT_TO]->(t:RelevantEmailThread)
RETURN t.subject, r.score ORDER BY r.score DESC
```

`r.score` is *"how relevant is thread `t` **to Ada**"*. The same thread `t` reached from a
different anchor (a different person, an organization, a meeting) gets a **different** `r.score` on
*that* edge. Putting the score on the node would be wrong — a convergent match would overwrite it.
The engine routes a producer's edge data (the score) onto the relationship; node properties (the
thread's subject, snippet, id) stay on the node.

Always **`ORDER BY r.score DESC`** (and optionally a `LIMIT`) — a vector search returns a *ranked*
list, and the score is the only signal of how good each match is.

### 6.3 `k`, `minScore`, and why a floor is dangerous

- **`k`** — top-k hits per anchor (default 8). Bounds the fan-out per anchor inherently (a vector
  join can't fetch "everything" — it fetches the `k` nearest).
- **`minScore`** — a similarity floor (0..1; default 0 = no floor). Use with care: when the anchor
  text is short (a name, a subject) it embeds *far* from topical thread-summary vectors, so a high
  floor can return nothing. Prefer `minScore: 0` + top-k + `ORDER BY r.score`, and let the caller
  judge relevance from the score, rather than a hard cutoff.
  **A floor that culls is reported**, naming how many hits of how many it dropped and the best score
  it saw — so "nothing relevant" and "everything just missed the cutoff" are distinguishable, and
  the number to change is in the diagnostic. Where the floor is pushed into the index (the `vector`
  kind sends it as a similarity threshold) the cull happens at the source and only the floor itself
  is evidence.

### 6.4 Privacy: the source enforces world and context scope, not the rewriter

A vector search runs *inside* the producer (against an embedding index), **bypassing** the Cypher
scope rewriter that guards keyed traversals. So the **producer/index is responsible for per-world and
per-context scoping**: the search is filtered by host-bound `worldId`, `contextId`, and access-policy
revision, and a search missing any required scope returns **nothing** (fail-closed). `principalId`
authorizes access but never substitutes for either data scope. A `vector` producer over shared
infrastructure must apply the same filters; a vector join can never surface another context's or
world's documents.

### 6.5 Anchors and composition

`RelevantEmailThread` anchors on `Person`, `Organization`, **and** `Meeting` — three joins to the
same target, each embedding a different field (`name`, `name`, `subject`). And a vector edge
composes with keyed traversals in one query:

```cypher
MATCH (me:AssistantUser)-[:EMAILED]->(p:Person)-[r:RELEVANT_TO]->(t:RelevantEmailThread)
WHERE r.score > 0.7
RETURN p.name, t.subject, r.score ORDER BY r.score DESC
```

— structure (people I email) and meaning (threads relevant to each) in a single `MATCH`.

> **Not a factual edge.** `RELEVANT_TO` means *semantically similar*, never *corresponded with*.
> "Did I email Ada / how much" is the persisted `(:AssistantUser)-[:EMAILED]->(:Person)` edge;
> `RELEVANT_TO` is "threads that read as being about Ada." The join's `description` says so, so the
> query generator never confuses the two.

### 6.6 Relevance modes — the `via` selector and the `intent` brief

One anchor→target relationship can be served by **several joins**, each declaring the edge `via`
value it answers to. The query selects the mode *at the edge*; an edge with no `via` selects the
join declaring none (the default — conventionally the `vector` join):

```cypher
MATCH (c:Concept {value:'lotteries'})-[:RELEVANT_TO]->(d:Document)                     -- semantic (default)
MATCH (c:Concept {value:'lotteries'})-[:RELEVANT_TO {via:'keyword'}]->(d:Document)     -- lexical, exact tokens
MATCH (c:Concept {value:'Acme'})-[r:RELEVANT_TO {via:'agentic-rag',
                                                 intent:'renewal risk'}]->(d:Document) -- judged retrieval
```

The three modes answer three different questions — *about* X (vector), *mentions* X (keyword), and
*bears on this brief* (agentic-rag). Vector and keyword are deterministic single passes. The
`agentic-rag` mode hands retrieval to a **bounded LLM loop** that may reformulate the query, run
both deterministic modes, and read further into a candidate whose snippet is inconclusive — then
returns only the documents it judges fit the brief.

**The `vector` mode is FUSED, and `r.mode` says which retrieval actually ran.** Asking what a
corpus says *about* X is not answered by embedding similarity alone: an exact token the corpus
does contain — a clause number, a part number, an invoice id — can sit below the similarity
threshold while a passage that merely reads like the question sits above it. So the semantic lane
runs a semantic and a lexical retrieval over the same scope and interleaves them into one ranking,
and reports `r.mode:'fused'`. Three guarantees follow, and they are what a query may rely on:

- **A document either arm finds is reachable.** Adding a distinctive identifier to an otherwise
  prose question cannot lose the document that contains it.
- **`r.score` is a SIMILARITY, not a ranking artefact.** Comparisons and thresholds
  (`r.score > 0.7`) keep meaning what they meant before fusion. What fusion decides is the ORDER
  and the SET, not the number.
- **`r.rank` is the fused order, and is the ordering to trust.** The two retrievals score on
  scales that do not compare, so `ORDER BY r.score DESC` re-orders documents by a quantity that
  means something different in each half. Order by `r.rank` when the ranking matters.

`r.mode` always reports the retrieval that RAN, never the one requested: `fused` for the semantic
lane, `keyword` when a lexical retrieval produced the rows — including when a semantic lane found
nothing and fell back, which is why a `vector` edge may legitimately return `mode:'keyword'` rows.
A `keyword` edge never reports anything else: a lexical miss is an honest empty, because answering
"which documents MENTION X" with "documents ABOUT X" collapses the one distinction the two modes
exist to draw.

**The `intent` directive** is the loop's retrieval brief: a top-level edge property (like `via`,
not in the `ai:` namespace), read by the engine and passed to the producer. The producer may
declare a default `intent`; the query edge's value overrides it per query. Because a different
brief is a different result set, `intent` participates in the fetch cache key, and it is stamped
back onto the materialized edge (`r.intent`) alongside `r.score` (the judged 0..1 fit),
`r.snippet` (verbatim evidence the loop actually saw), `r.mode`, and `r.rank`.

Two guarantees keep the agentic mode honest:

- **Grounded**: the loop's verdict may only reference documents that appeared in its own tool
  results — a hallucinated id can never materialize a node.
- **Fail-open**: any loop failure degrades to the deterministic `vector` search for that anchor —
  an LLM hiccup costs precision, never an empty answer.

Cost guidance: an agentic edge spends several LLM calls **per anchor**. Select it explicitly
(never as a default), and pair it with a **materialized view** (§8.3) when the same brief is
queried repeatedly — the loop then runs on the view's refresh schedule and queries read the cached
subgraph.

---

## 7. LLM query primitives — filter, rerank, and steer with the `ai` namespace

Vector edges (§6) answer "which rows are *about* X" with an **embedding** — cheap, but only as good as
the similarity model, and blind to any judgment that isn't cosine distance. Sometimes the discriminator is
one no property and no embedding captures: *"news actually about **my** funding round"*, *"papers whose
method is **genuinely** transformer-based, not just name-dropping it"*, *"the issues most **relevant to this
outage**"*. For those, the query can call a **per-row LLM judgment** inline, expressed as a reserved
**`ai.*`** function.

These run at **execution time**, over the rows a query has already fetched — the LLM counterpart, at the
value level, of §9's generation-time `examples:` steering. Four primitives across the three query positions:

- **`{ai: {hint, model, temperature, confidence, fresh, voice, wordcount}}`** — *steer and tune* the
  fetch behind an edge, as a nested directive map (§7.2; the flat `ai_*` spellings are RETIRED);
- **`{realm: {…}}`** — the realm's OWN prompt parameters, passed verbatim (§7.2.2);
- **`WHERE ai.relevant(n, '<criterion>')`** — *filter* rows by subjective relevance;
- **`ORDER BY ai.score(n, '<criterion>') DESC`** — *rerank* rows by subjective fit;
- **`RETURN ai.classify(n, '<dimension>')`** — *label* each row along a subjective dimension.

### 7.1 The `ai` and `realm` namespaces are reserved

Any property or function in the **`ai`** namespace — the bare `ai` key, the flat `ai_*` prefix, or the
`ai.*` function form — is an **engine primitive, never data**, and the bare **`realm`** key is likewise
reserved (§7.2.2). A realm MUST NOT declare a stored property or a producer field named `ai`, `ai_*`, or
`realm`; the graph schema is open and realm-defined, so the reservation is what keeps the primitives
collision-free and self-documenting to the generator. `ai.relevant` and `ai.score` are **"fake" functions**:
they carry no stored value — the engine computes them for the rows a query touches and, having computed
them, writes the result onto the transient row as real data so ordinary Cypher (`WHERE`, `ORDER BY`) can
read it. They are defined **only over fetched / materialized rows** (a virtual join's targets, §2) — the
judgment is what the source could not express — so anchor them on a virtual collection, not a raw
persisted label.

### 7.2 The `{ai: {…}}` directive map — steer and tune a fetch

An LLM-backed edge takes its per-query directives as a **nested map** under the reserved `ai` key —
legal Cypher, structurally collision-free with real edge data, and fail-safe (a map is not a storable
property value, so it could never silently filter the read if it leaked):

```cypher
MATCH (p:Person {name:'…'})-[:RATED]->(seed:Movie)
MATCH (seed)-[:SIMILAR_TO {ai: {hint:'obscure, and French', model:'chat_cheap',
                                temperature: 0.2, confidence: 0.8}}]->(rec:Movie)
RETURN rec.title
```

The flat spellings (`ai_hint`, `ai_model`, …) are **RETIRED**: a query using one is rejected before
execution with the namespace replacement named in the error, so callers self-correct. The `ai`
namespace is **closed**: an unknown key inside it is warned about as a probable typo, never silently
ignored. Its keys:

- **`hint`** — the free-text steer the schema has no property for (a mood, a vibe, a language, an
  angle), reaching the generator's prompt as `{{ hint }}` or folding into an aggregate's reduce
  instruction. A **soft steer, not a filter**: everything the schema *can* express (genre, year, a
  rating floor) belongs in an ordinary `WHERE`.
- **`model`** — a portable, **world-defined role id** (e.g. `chat_cheap`, `code_best`), resolved
  through the world's role map exactly like the realm edge's own `role:` declaration. A query
  **never pins a concrete model name**; an unknown role falls back to the edge's declared tuning (with
  a warning), never a failure.
- **`temperature`** — a sampling temperature layered on whatever base the role (or the edge's default)
  resolves to.
- **`confidence`** — raises a **generative** edge's confidence floor for this query ("only picks you're
  sure of" vs "brainstorm wildly"); below-floor records are dropped before resolution, costing no lookup.
- **`fresh: true`** — bypasses the **cross-query TTL cache read** ("regenerate my taste summary *now*" /
  "re-check today's availability"); the fresh result still **writes through**. Applies to ANY TTL-cached
  producer, LLM-backed or remote.
- **`voice`** — the register/style of a PROSE-producing reduction ("second person, warm", "a noir
  narrator"). Aggregate reduce only: names have no voice, and grounded extracts must not be restyled.
- **`wordcount`** — a target length for a prose reduction (clamped to a sane range; a prompt-level
  target, never a token cap — truncation mid-sentence is worse than a 10% overshoot). On a
  **graph-cached** aggregate (§5.5) it is not free text at all: it quantizes to the nearest persisted
  BAND (gist ~40 / standard ~200 / long ~600), so sized requests stay cacheable — 250 hits the same
  committed node the directive-free ask created.
- **`text: {chars, keep, clean}`** — how much of each ROW's text a per-row judgment reads
  (`ai.relevant` / `ai.score` / `ai.classify`), which part of it, and whether markup is stripped first.
  `keep: 'around'` reads the passages nearest the criterion rather than the opening — on a FILTER that
  is the difference between a degraded answer and a row dropped because its deciding sentence sat too
  far in. Markup is stripped by default; `clean: 'none'` keeps it. Same map, same keys, as §7.7.
- **`sample: {size, subset}`** — on a **generative** edge, how many ANCHORS are rendered into the one
  prompt that seeds the generation, and which of them. A generative edge is exempt from `maxAnchors`
  (it makes no per-anchor call — every anchor goes into a single prompt), so the prompt is what bounds
  it: 200 by default, raisable to 1000, `subset` one of `first` (the default) / `last` / `longest` /
  `random`. It matters more here than it reads: the generation is seeded by the anchors in the prompt
  **and by no others**, so the rest of a larger set is not thinly covered, it is absent — which is why
  a bounded prompt now returns a `PARTIAL_RESULT` note saying how many anchors of how many it was
  seeded from. The same key, spelled the same way, bounds a holistic aggregation's evidence (§7.7).

**Precedence:** query directive → the realm edge's own declaration (§5.3 generator, aggregate `reduce`)
→ the deployment default. The directives apply to **generative** edges (the generator call) and
**aggregate** edges (the fan-in reduction) alike, for **that query only** — cached results are keyed by
the full steering, so a `chat_cheap`, breezy, 40-word run never serves from (or pins) the plain cache
entry. On a **graph-cached** aggregate (§5.5) the same principle splits three ways: `wordcount` selects
a persisted band (still cached), `fresh` regenerates-and-writes-through, and everything semantic
(`hint`/`voice`/`realm.*`/`model`/`temperature`) makes the result transient — it never touches the
committed canonical node. The whole block is **steering, not data**: stripped from the executed query, never stamped onto
a materialized edge. And since views are saved queries, a realm can bake any of it into a view
(a `CheapRecommendations` view with `{ai: {model:'chat_cheap'}}`) with no extra mechanism.

#### 7.2.2 The `{realm: {…}}` map — the realm's own prompt parameters

Where `ai` is the closed embabel-standard namespace, **`realm`** is the **open** one: its keys pass
through **verbatim** to the producer's prompt — a generative template variable, or a `key: value` line
folded into an aggregate's reduce instruction. The realm defines its own steering vocabulary by simply
referencing the variable in its prompt; an unreferenced key is inert:

```cypher
-- realm-movie's prompts opt into an `era` parameter ({% if era %} … {{ era }}):
MATCH (ts)-[:SUGGESTS {realm: {era: 'the 1970s'}, ai: {model: 'chat_cheap'}}]->(m:Movie)
RETURN m.title
```

Realm parameters are steering like everything above — stripped from the read, never stamped, part of the
cache key — and can never clobber the engine's reserved template variables (`anchors`, `exclude`,
`want`, `hint`, …).

### 7.3 `ai.relevant` — the per-row relevance filter

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(n:NewsItem)
WHERE ai.relevant(n, 'about my company\'s Series A funding round')
  AND n.published > date() - duration('P7D')
RETURN n.title, n.url
```

**Means:** "of the news fetched for me this week, keep only the items *actually about my funding round*" —
a discriminator no keyword and no embedding reliably draws (a piece can name "funding" yet not be about
*mine*; can be about mine yet never say "Series A").

**How it executes:**

- **Fetch** the `NewsItem` rows as any virtual join would (§2) — the source can't apply the criterion, so it
  returns the broad set.
- **Judge — one batched LLM call per criterion.** The fetched rows' text is scored 0..1 for fit to the
  criterion; rows below a threshold are **dropped**, keeping the **nodes** (unlike the `relevant(text,
  criterion)` fan-*in* aggregation of §5.3-adjacent LLM reducers, which returns text — this keeps the rows so
  the query can traverse and return them).
- **Stamp & run.** The criterion is written onto each surviving row under the internal `ai_relevant`
  stamp, and the executor rewrites `ai.relevant(n, '…')` in the executed query to a match against that
  stamp, so it filters as ordinary data. It **composes** with real
  predicates via `AND` (the date filter above) and with the other `ai.*` primitives.

Use it **only** for a subjective *about / relevant-to* that maps to **no** shown property; for a concrete
field, an ordinary `WHERE` is cheaper and exact.

### 7.4 `ai.score` — the per-row rerank

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(n:NewsItem)
RETURN n.title, n.url
ORDER BY ai.score(n, 'relevance to my Series A funding round') DESC
LIMIT 5
```

**Means:** "rank the fetched news by how well each fits, and give me the top five" — the highest-value
retrieval lever, a learned relevance sort where no orderable property exists.

**How it executes:**

- **Fetch** as above.
- **Judge — the same batched 0..1 scoring** as `ai.relevant` (the two share one judgment; a query using
  both scores once and both filters and ranks off it). Every row is **kept** and its score **stamped** under
  the internal `ai_score` property.
- **Rewrite & run.** Neo4j has no `ai.score` function, so the executor rewrites the call in the executed
  query to `coalesce(n.ai_score, 0.0)` (0.0 for any row that wasn't scored), and `ORDER BY … DESC LIMIT k`
  ranks and truncates against the stamp.

The idiomatic **filter-then-rank**: `WHERE ai.relevant(n, '…') … ORDER BY ai.score(n, '…') DESC LIMIT k` —
narrow to the relevant, then order the survivors by fit.

### 7.5 `ai.classify` — the per-row projection

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(n:NewsItem)
RETURN n.title,
       ai.classify(n, 'urgency: high, medium, or low')     AS urgency,
       ai.classify(n, 'topic in one word')                 AS topic
```

**Means:** "return the fetched news, and *label* each item along a dimension there is no column for" — a
computed, LLM-decided category rather than a stored field.

**How it executes:**

- **Fetch** as above.
- **Label — one batched call per dimension.** Each fetched row's text is labelled for the named dimension
  (if the dimension lists categories, the label is one of them; otherwise a short free label). Every row is
  **kept** and its label **stamped** under a **per-dimension slug property** (`ai_classify_urgency…`), so two
  classifications in one `RETURN` never collide.
- **Rewrite & run.** As with `ai.score`, the executor rewrites each `ai.classify(n, '…')` in the executed
  query to `coalesce(n.ai_classify_<slug>, '')` (blank for any unlabelled row), and the projection returns it.

Use it **only** for a subjective label no property holds; when a real field already carries the value, return
that. (It is a *projection*, not a filter — to keep only one category, classify and then `WHERE label = '…'`,
or use `ai.relevant` directly.)

### 7.6 Cost, determinism, and failure

These call an LLM, so they are the **non-deterministic** members of the surface (contrast §11): the same
query can score two runs slightly differently, and the model — not the graph — decides. Bound the cost —
each criterion is **one batched call** over the fetched rows (chunked for large sets), so they scale with
*rows fetched*, not rows × 1; keep the fetched set small (an anchor, a real `WHERE`, a `LIMIT` on the fetch)
before judging. They **fail open**: a row the model did not judge is scored at the **keep threshold**
(0.5), so a hiccup never silently *hides* results — it degrades to "no judgment applied". The threshold,
not 1.0: a perfect score would keep the row *and rank it above every row the model actually read*, which
is how a grants query for "youth mental health" once came back topped by aged-care infection research, at
fit 1.0, with its kept count swinging across identical runs. At the threshold an unjudged row is kept and
never promoted. It is also **visible** — a `PARTIAL_RESULT` (`TRUNCATED`) warning names how many rows of
how many carry no judgment, so a caller ranking or counting them knows how much of its answer the model
never read. Reach for
them only when the discriminator is genuinely subjective; a property, an embedding (§6), or a real predicate
is always cheaper and more repeatable.

---

### 7.6.1 Gating an expensive judgment — what actually narrows it

An `ai.*` primitive is **not** evaluated per row the way an ordinary Cypher function is, so the
position of the call in a `WHERE` decides nothing. Writing the cheap test first and the judgment last
does not make the judgment lazy, and `AND` does not short-circuit it — nothing in openCypher promises
an evaluation order for boolean operands anyway.

What does bound the cost is this: **every deterministic condition the engine can attach to the node is
applied before the judge runs, wherever it appears in the query.** A condition it cannot attach is
still honoured — the rows that come back are exactly right — but it is applied *after* judging, so the
model has already read everything fetched. The result looks identical. Only the bill differs, and
nothing in the answer says so.

So a gate has to be written in a shape the engine can attach:

| Condition | Bounds the judgment? |
|---|---|
| `r.amount >= 20000000` | yes |
| `toFloat(r.amount) >= 20000000` | yes — wrapping is fine |
| `size(trim(coalesce(r.description,''))) <= 60` | yes — see below: a length is screened by the engine, not by the source |
| `r.description CONTAINS 'lease'` | yes |
| `r.description IS NOT NULL` | **no** |
| `toLower(r.description) = toLower(r.title)` | **no** — compares two properties, not a value |
| a condition on a *different* node | **no** |
| `r.amount >= $threshold` **in a view** | yes — a view's declared params become literals before the query is read |
| `r.amount >= $threshold` **with caller-bound params** | **no** — the value is not known when the query is read |

**A wrapper that CHANGES the compared quantity gates too — but locally.** `toFloat(r.amount) >= 5`
still compares the amount, so it can be handed to the source. `size(r.description) <= 60` compares a
LENGTH the source has never heard of, so it is never handed to one; the engine evaluates it itself on
every fetched record before the judge is asked, and the judge sees only the rows it keeps. This holds
for a chain of `size` / `length` / `char_length` / `toString` over `coalesce` / `trim` / `toLower` /
`toUpper` / `toFloat` / `toInteger`. A record the engine cannot decide — a missing value whose
`coalesce` default it does not evaluate — is kept for the judge and settled by the query afterwards,
so the screen only ever admits rows, never drops one the query would keep. A wrapper outside that
set (`substring`, `reverse`, …) is not screened: the condition is honoured in full, after judging.

That last pair is the one that surprises people. The same text bounds the cost inside a view and does
not bound it when the parameter is bound by the caller at execution time. If a screen carries an
expensive judgment, define it as a **view** with declared parameters (§8) and the gates work as
written.

**Write the gate for cost, not as a finding.** A gate decides which rows are *worth asking about*; it
is not evidence about them. "Short description" is a good gate for a disclosure screen and a bad
finding: a lease naming a street address is brief and completely checkable, while a bare product noun
is brief and tells a reader nothing. Only the judgment can tell those apart — which is exactly why
the length test belongs in the `WHERE` and the verdict belongs to `ai.score`.

**One criterion, one judgment.** A filter and a projection sharing the *same* criterion string share a
single judgment, so this reads each row once:

```cypher
WHERE size(trim(coalesce(r.description,''))) <= 60
  AND ai.score(r, 'a reader could identify what this bought') < 0.4
RETURN r.cnId, ai.score(r, 'a reader could identify what this bought') AS disclosure
```

Two different spellings of the same idea are two judgments, at twice the cost, and they may disagree
about the same row.

---

### 7.7 Aggregations — reduce a whole GROUP to one cell

The primitives above judge rows one at a time. An **aggregation** goes the other way: it reduces the
group a traversal produced to a single cell, as the model sibling of `count()` / `collect()`. Neo4j's
implicit GROUP-BY supplies the grouping for free — `RETURN topic.name, summarize(n.description)`
yields one digest per topic.

```cypher
MATCH (t:ResearchTopic {name:'retrieval augmented generation'})-[:HAS_NEWS]->(n:NewsItem)
RETURN summarize(n.description, 'what is newest and most important') AS digest
```

| Function | Returns | Reduces a group to… |
|---|---|---|
| `summarize(text [, instruction])` | prose | a neutral overview |
| `render(text [, instruction])` | prose | the same items as prose — all of them, in order, hedges kept |
| `synthesize(text, goal)` | prose | a goal-directed answer (argues toward `goal`) |
| `classify(text, labels)` | one label | exactly one label from the closed set `'a,b,c'` |
| `extract(text, what)` | list | the distinct things asked for (deduped) |
| `themes(text [, focus] [, count])` | list | the recurring cross-item topics (labels only) |
| `cluster(text [, k])` | list of maps | semantic groups, each with a COUNTED size and examples |
| `score(text, rubric)` | number 0–1 | one terminal ordinal judgment of the whole group |
| `holds(text, question)` | boolean or null | a three-valued verdict on a claim |
| `relevant(text, criterion)` | list | only the items matching a subjective criterion |
| `argmax(key, text, criterion)` | winner payload | the best candidate under a comparative rubric |
| `correlate(x, y)` | map | the Pearson correlation of two numeric expressions: `{r, n, dropped, ci, detectable}` |
| `regress([x1, …], y, label)` | map | a least-squares fit of `y` on the predictors: fit quality, per-predictor strengths, and the rows most above and most below their prediction, one list per direction |

**`render` keeps what `summarize` compresses.** Both write prose from a group; they differ in what
they promise. `summarize` gives a neutral overview and will drop, merge and reword items to get
there — right for a group of items nobody has read. `render` promises the opposite: every item
appears, in the order given, with its figures as written and its qualifying clauses intact. It is
for rows a realm has already composed for a reader — a sentence per row, a status, a caveat — where
only the joins between them are missing.

The distinction matters most where it is least visible. A row that ends "stated, not verified as
current", "a name match to check", or "no record was found" is carrying the reader's warrant to
doubt it; compressed out by a digest, the same row reads as established fact, with its figures
still correct. Ask for `render` whenever losing such a clause would change what the prose means.

Neither function may ADD. Both are held to what the items literally state — no description of what
a subject is or does from outside the rows — and both report an honest miss rather than write from
nothing. `render` additionally never sums or combines figures across items: a total it calculated
would appear in none of them, and could not be checked against any row.

`render` COSTS A MODEL CALL AND VARIES BETWEEN RUNS, like every prose reduction. Where the same
words are required every time, build the sentence in Cypher from the row's own columns and return
it; `render` buys prose that reads well, never reproducibility.

**`correlate` and `regress` are arithmetic: no model call, and the same rows always yield the same
result.** They reduce a group's NUMERIC columns, not its text, and both report ASSOCIATION across
the group — never causation, and never a claim about any individual row.

```cypher
MATCH (d:District)
RETURN regress([d.medianPay, d.avgPrice, d.density], d.crimeRatePer1000, d.name) AS model
```

- `correlate(x, y)` returns `{r, n, dropped, ci, detectable}` — Pearson's r over the rows where
  BOTH operands were numeric, `n` counting those rows and `dropped` the rows that were not. `ci`
  is the 95% confidence interval for r (null when the group is too small to bound one), and
  `detectable` says whether that interval excludes zero — when it is false, the sample cannot
  distinguish the relationship from none, and the honest report is "no detectable relationship",
  never the bare r. It returns null rather than a map when fewer than three usable pairs remain
  or when either operand never varies.
- `regress([x1, x2, …], y, label)` fits `y` against the predictor LIST by ordinary least squares.
  The first argument is a Cypher list of numeric expressions (any number of them), the second the
  numeric outcome, the third an expression naming each row. It returns
  `{n, dropped, r2, adjustedR2, coefficients, abovePrediction, belowPrediction}`: `coefficients`
  carries one entry per predictor with a STANDARDISED beta — magnitudes are comparable across
  predictors of different units, the list is ordered strongest first, and each is named READABLY
  from the query (a coercion wrapper is unwrapped and a plain `variable.property` drops its
  variable, unless that would give two predictors the same name). The two residual lists name the
  rows (by the label expression) whose actual outcome sits furthest ABOVE and furthest BELOW the
  fit's prediction, in the outcome's own units — one list per direction, so a divergence that
  runs only one way is visible as an empty other side. It returns null rather than an unreliable
  fit when the group is too small for its predictor count, when a predictor is constant or a copy
  of another, or when the outcome never varies.
- Rows where any needed operand is null or non-numeric are dropped from the fit and counted in
  `dropped` — a thin join cannot masquerade as a strong signal.
- Grouping is the ordinary implicit GROUP-BY: `RETURN d.region, regress(…)` fits one model per
  region; drop the key for one fit over the whole group.
- **They belong in the RETURN**, where an aggregation is finalized. Written into a `WITH` they
  type-check, compute nothing, and hand back **null** — which reads as "no association" when it
  means "not computed". Two forms of the same mistake, both silent:

  ```cypher
  WITH pt, collect(…) AS seats, correlate(pay, sigs) AS r   // null: a WITH does not finalize
  RETURN correlate([x IN seats | x.pay], [x IN seats | x.sigs])  // null: these are AGGREGATES
                                                                 // over rows, not list functions
  ```

  Both are fixed the same way — accumulate the rows and let the RETURN reduce them:

  ```cypher
  WITH pt, toFloat(cp.annualPay) AS pay, toFloat(cs.signatures) AS sigs
  RETURN pt.action AS petition, correlate(pay, sigs) AS payVsSignatures
  ```

  If a view needs both a collected list and a coefficient, that is two views, not one clause.

**Ingested document content is aggregable.** When the accumulated row expression is an ingested
document's `content` (or `text`) — `holds(d.content, '…')`, `summarize(d.text, '…')` on a matched
`Document` — the aggregation reads the document's FULL ingested text, not a stored node property.
The same document always yields the same text; a document whose text was never ingested contributes
nothing. Cost scales with document length (the reduction is chunked internally), so prefer a
narrower match when the question targets one section. Cached document summaries remain available
and cheaper, but can omit specific findings; content is the exhaustive surface.

**A reduction with nothing to reduce says so.** When the accumulated expression is empty for a group
— no rows matched, or the property carries no values — the cell is an `UNAVAILABLE:` sentinel, never
a fabricated verdict or digest, and ask surfaces report the result as an honest miss rather than an
answer. An empty LIST accumulates as empty: `collect()` of zero rows never manufactures evidence.

**A verdict about a NAMED thing requires the name in the corpus.** When a `holds` verdict is
anchored through document relevance, the seed's words must appear together somewhere in the
corpus text. A seed that appears nowhere (an address, a name, an identifier the documents never
mention) yields an honest not-in-graph miss that names the seed — never a verdict judged against
whatever document happened to be semantically nearest. Topical reductions (summaries, filters,
themes) keep full semantic reach: aboutness without the literal words remains their contract.

**`holds` judges the claim as written.** Every specific the claim itself states (a year, a figure, a
name) must be supported by the evidence, or the verdict is `null` (UNKNOWN) — qualifiers the claim
does not state are assumed enforced by the query's own filters. Risk or possibility language in the
evidence ("may be present", "high risk of") never supports TRUE. A verdict of `false` requires
evidence that addresses the claim and answers no; material that does not bear on the claim cannot
veto such a grounded no, and if NOTHING bears on it the verdict is `null`, never a confident no.

**An aggregation's result can be filtered, ordered and grouped by.** Write it as you would any other
value:

```cypher
MATCH (e:Electorate)
WITH e, classify(e.member, 'female,male,unknown') AS gender
WHERE gender = 'female'
RETURN count(e) AS count, gender
```

The count is the database's, over real labels. The same holds for `ORDER BY score(...)`, for grouping
by an aggregated label in a later `WITH`, and for every aggregation in §5 — each reduces a group to one
cell, and a cell can be filtered on.

What this costs, and the one rule it imposes:

- The value is computed BEFORE the query runs, and only for the groups whose value can still reach
  the answer. Every part of the query that does not read the aggregation narrows that set first —
  a `WHERE` before the aggregating `WITH`, and equally a `WHERE` after it on any other column, a later
  `MATCH` that drops rows, a later `WITH … WHERE`. In

  ```cypher
  MATCH (l:Lead)
  WITH l, classify(l.notes, 'strategic,standard,at_risk') AS triage
  WHERE triage = 'at_risk' AND l.probability < 50
  MATCH (l)-[:OWNED_BY]->(u:User {active: true})
  RETURN l.name
  ```

  only the leads under 50% with an active owner are judged; the others are excluded whatever the
  judgement would have been, and are never sent to the model. The guarantee is one-directional: the
  set judged is never SMALLER than the set that can reach the answer, so the answer is exactly what
  judging every group would give. Where the aggregation flows into something other than a filter or a
  bare pass-through — an expression (`toUpper(triage)`), a pattern, an `UNWIND`, a `CALL`, a `UNION` —
  the query cannot be narrowed by it and every group is judged, as before.
- **A `LIMIT` stops the judging when the answer is full.** Under `ORDER BY … LIMIT n`, the groups
  are judged toward the top of the answer a few at a time, best rows first, and judging stops the
  moment the first `n` rows (or `SKIP s LIMIT n`: the first `s + n`) are all judged — every group
  below them is never sent to the model. "The ten biggest at-risk deals" costs judging the biggest
  deals until ten of them are at risk, not judging every deal. The answer is exactly what judging
  every group would give. This holds when the judgement only FILTERS rows; where its value shapes
  them — an `ORDER BY` on the judgement, a `RETURN` that is `DISTINCT` or aggregates, a later clause
  grouped by it, a `LIMIT` before the final `RETURN` — every candidate is judged as before. One
  residue is the store's own: rows that tie exactly at the boundary of the window are seated
  arbitrarily, as they are under any `LIMIT`; such a row can carry no label, never a wrong one.
  A query whose filter would still need more than a few hundred model calls is
  REFUSED with the count, rather than sampled quietly. The refusal names the
  cap it hit, and a query that MEANS to spend that much says so: `{ai: {maxGroups: 600}}` raises it
  (up to 2000 — past that, compute the value once and persist it), and a smaller number LOWERS it,
  which is how a shipped view holds its own spending line. This is a cost guard, so it is the
  author's to set; the completeness gate on a truncated fetch is a correctness guard and has no
  such override, by design.
- **The clause must carry the node the value belongs to.** `WITH e, classify(e.member, …) AS gender`
  works; `WITH e.name AS name, classify(e.member, …) AS gender` is refused, because an aggregate value
  belongs to a group and a group needs an identity to attach it to. The refusal says so and names the
  fix. Project the node itself and read its properties later.
- The value is attached to the group for the duration of the query only. It is never written to the
  graph: ask twice and it is computed twice, and nothing in the graph carries a stale label from a model
  run last week. To keep a classification, write it deliberately (§9 annotation writes) rather than
  relying on a query having filtered on it.
- Merely RETURNING an aggregation is unchanged and stays cheaper — `RETURN t.name, summarize(…) AS digest`
  reduces after the read, with no pre-pass.

Grouping follows Cypher's own rules: the non-aggregated keys of the clause define the groups, so
`WITH t, summarize(n.description, …)` is one digest per `t` over all its `n`s — not one per `n`.

#### What the arguments mean

Every signature above splits its arguments the same way, and getting the split wrong is the most
common authoring error:

- **The leading `text` is a ROW EXPRESSION, accumulated** — `n.description`, `n.title + ' — ' + n.body`,
  `coalesce(n.a, n.b)`: anything Cypher can evaluate per row. It is gathered across the group exactly
  as `collect()` gathers, so ONE cell is produced per group, not one per row. A quoted literal in this
  position is rejected: it would reduce the same constant N times.
- **`argmax` accumulates TWO row expressions** — `argmax(key, text, criterion)` collects `key` (what
  identifies the winner: a filename, a title, a name) and `text` (what is judged) together, so the
  answer can say WHICH item won and not merely what the winning text said. Every other function in the
  table accumulates exactly one.
- **Every argument after the accumulated ones is a LITERAL string** — the instruction, goal, labels,
  what, focus, rubric, criterion, question. A row expression there is not evaluated per row (there is
  nothing to evaluate it against once the group is reduced), so write the words themselves.
- **Optional arguments are POSITIONAL but type-disambiguated.** `themes(text [, focus] [, count])`
  reads a NUMERIC argument as the topic count and a string as the focus, in whichever order they
  arrive — `themes(n.title, 5)` and `themes(n.title, 'risks', 5)` both mean what they look like.
  `cluster(text [, k])` takes a number only.
- **`classify` labels are a single comma-separated string** — `classify(n.body, 'positive,neutral,negative')`,
  not three arguments and not a list. The set is CLOSED: the answer is always one of the labels given.
- **An honest miss is a value, not an error.** When the accumulated text does not contain what the
  instruction asks about — a group of document TITLES asked for a profit figure — a grounded reduction
  returns the exact sentence *"The provided items do not contain this information."* rather than
  inventing one. Treat that sentence as "no answer", never as the answer.

#### Steering ONE call — the trailing `{ai: {…}}` map

An aggregation may carry the same `{ai: {…}}` map as a virtual edge (§7.2), as its LAST argument. It
is steering, not data: stripped before the query runs, never part of the aggregated text.

```cypher
MATCH (t:ResearchTopic {name:'retrieval augmented generation'})-[:HAS_NEWS]->(n:NewsItem)
RETURN summarize(n.description, 'what is newest', {ai: {model:'chat_cheap', voice:'brisk', wordcount: 40}}) AS digest
```

Which keys are honoured depends on what the function returns — a list, a label, a number or a boolean
has no voice and no word count:

| Key | Applies to | Effect |
|---|---|---|
| `model` | EVERY aggregation | the world ROLE the reduction runs on; an unknown role falls back to the default, with a warning, never a failure |
| `temperature` | EVERY aggregation | sampling temperature layered on that role |
| `hint` | the PROSE reductions (`summarize`, `synthesize`) | a soft steer added alongside the instruction — never a filter, and never able to override grounding |
| `voice` | the PROSE reductions | register/style ("second person, warm") |
| `wordcount` | the PROSE reductions | a target length — a prompt-level target, never a mid-sentence cut |
| `punctuation` | the PROSE reductions | `'plain'` (the only value): the result never contains a semicolon — the ban is enforced after the model writes, not merely requested, so it holds on every run |
| `sample` | the HOLISTIC judgments (`score`, `classify`) | `{size, subset}` — how much of the group reaches the model, and which part |
| `text` | EVERY reduction | `{chars, keep, clean}` — how much of each ITEM reaches the model, which part, and what is stripped first |
| `maxGroups` | a FILTERABLE aggregation | the group cap this query intends to spend, up to 2000 |

`confidence`, `fresh` and `materialize` are EDGE keys (a generative floor, a producer's cache) and an
aggregation has neither, so they are rejected here rather than accepted and ignored. A prose key on a
non-prose function, an unknown key, and a `{realm: {…}}` map are all rejected the same way: warned
about, never silently inert. Because a map is a value the map cannot be confused with an instruction —
`summarize(n.body, {ai: {voice:'noir'}})` steers, it does not summarize toward the word "noir".

The map NESTS: `sample` groups two keys that are one decision, and the interior is ordinary Cypher
(quoted or back-ticked keys, strings containing braces, any depth) because the real parser reads it,
not a scanner. A trailing map carrying NEITHER `ai` nor `realm` is not steering at all — it stays the
caller's own positional argument.

#### `sample` — how much of a group a holistic judgment reads

`score` and `classify` reduce a group to ONE number or ONE label, so their evidence must fit a single
model call — unlike `summarize`, `themes`, `relevant` or `extract`, which fold a whole group in
batches. They therefore read a bounded sample of the group, and **say what they left out**: a group
larger than the sample returns a `PARTIAL_RESULT` note naming the counts and the strategy, so a
number over 40 of 500 items never renders as a number over all 500.

**Settle what you already know before the model is asked.** Wrap any reduction in a two-argument
`coalesce` whose first argument is a plain expression over the row: where that expression is not
null it IS the group's value and no model call is made; where it is null the reduction runs as
usual.

```cypher
MATCH (a:CustomerAccount)
WITH a, a.caseSubjects AS problems, coalesce(a.crmNotes, '') AS written
RETURN a.name,
       coalesce(CASE WHEN written = '' THEN 'unaware'
                     WHEN any(p IN problems WHERE toLower(written) CONTAINS toLower(p)) THEN 'aware' END,
                classify('OPEN: ' + problems + ' || CRM: ' + written, 'aware,unaware',
                         'aware: a note touches the same topic as a support item …')) AS crmAwareness
```

An account sales never wrote about is `unaware` by definition, and one whose case subject appears
verbatim in a note is `aware` by the same word test an app would apply — neither needs a model, and
neither is sent one. The guard settles a GROUP only when every row of it carries the same non-null
guard value; a group with one guarded row and one unguarded, or with guards that disagree, is judged
whole by the model over its values (the guards are never part of the evidence). The guard must be a
plain expression — one that aggregates is refused — and a reduction that collects two expressions
(`argmax`, `correlate`, `regress`) cannot be guarded. The guarded form can be filtered, ordered and
grouped by like any other reduction (§6.4), and there too the settled groups cost nothing.

**Many groups share a call.** A query that classifies per row is a query of many small groups, and
`classify` judges up to twenty of them in one model call — `RETURN c.id, classify(c.body, 'blocked,degraded,asking')`
over 150 cases costs about eight calls, not 150. Nothing about the answer changes: every group is
still judged on its own evidence, its label still comes from the closed set, and a group the model's
reply does not settle unambiguously (a number missing, given twice, or given a label off the set) is
judged again on its own rather than guessed. `llmCalls` in the result counts the calls actually made.
`score` shares a call the same way — `ORDER BY score(…)` over many rows is batched, not one call
per row — and keeps its contract: a batched score is the same 0–1 number, clamped, and a group
whose evidence is too long for one call is scored on its own. `holds` is **not** batched: a
verdict read from a numbered list was measured to differ from the verdict the same evidence
gets on its own (a small judge answered FALSE in a batch where it answers TRUE alone), and a
confidently wrong negative is a row silently missing from `WHERE holds(…) = true` — a
`holds` over many rows still costs one call per group.
The calls a reduction makes for independent groups (or batches of them) overlap, a few at a time,
so a query that judges many groups waits for the slowest few round trips rather than the sum of
all of them; the order of the rows and the count of the calls are unchanged by this.

**A `classify` judgement is repeatable.** It runs at temperature 0 unless the call says otherwise
(`{ai: {temperature: …}}`, or a role that carries its own), so the same evidence under the same
rubric yields the same label run after run — a materialised view refreshed on its `ttl` keeps its
labels where the words have not changed.

```cypher
MATCH (t:ResearchTopic)-[:HAS_NEWS]->(n:NewsItem)
RETURN t.name,
       score(n.description, 'relevance to enterprise AI',
             {ai: {sample: {size: 120, subset: 'longest'}}}) AS fit
```

| Key | Effect |
|---|---|
| `size` | items that reach the model. Capped at 200 — the evidence has to fit one call — and clamped with a warning rather than refused. Omit it to keep the function's own default |
| `subset` | which items: `first` (the default), `last`, `longest`, `random`. Omit it to keep `first` |

Choosing a `subset` is not a formality. `first` and `last` are only as meaningful as the group's
ORDER, which is the engine's unless the query put an `ORDER BY` before the clause that groups —
so **`longest` is the order-independent choice**, and usually the better one: the longest items carry
the most evidence per call. `random` is SEEDED from the call's own criterion, so the same question over
the same group always reads the same items; an unseeded spread would make identical queries disagree
with nothing in the result to explain why.

`sample` on a folding reduction is rejected like any inapplicable key — capping `summarize` would
quietly throw away evidence the author expected folded.

#### `text` — how much of each ITEM is read, and which part

Where `sample` chooses the ITEMS, `text` chooses what each of them contributes. Every reduction cuts a
long item to a per-item budget; this makes the budget, the part kept, and the cleaning explicit.

```cypher
RETURN score(n.body, 'relevance to my Series A funding round',
             {ai: {text: {chars: 2000, keep: 'around'}}}) AS fit
```

| Key | Effect |
|---|---|
| `chars` | characters of each item that reach the model (capped at 8000 — a per-item budget multiplies by the sample). Omit to keep the reduction's own default |
| `keep` | which part survives: `head` (the default), `tail`, `ends` (both, with a visible elision), `around` |
| `clean` | a CLEANER NAME, or `auto` (the default — every cleaner that detects its own noise) or `none`. Several compose: `'html,quoted-reply'` |

**`around` reads the passages nearest your criterion**, and it is the one to reach for on documents.
Every reduction that cuts text is holding the criterion it is cutting it for — a rubric, a label set, a
relevance criterion — so "the first N characters" can be "the N characters nearest the question" at no
extra cost. On `ai.relevant`, where the judgment DROPS rows, that is the difference between a degraded
answer and a row wrongly excluded because its deciding sentence sat in paragraph three.

**Markup is stripped by default.** A field carrying HTML spends most of a character budget on tags, so
the sentence that decides the answer is the one that does not fit; `clean: 'none'` keeps the markup for
the rare item whose markup IS the subject.

**Cleaning is a named strategy, not a fixed list.** `html` is the one the engine ships; a world adds
another by registering a cleaner — an email's quoted reply chain, a CMS field's shortcodes, a log's
escape codes — and it is then available to every reduction and every per-row judgment by name, with
nothing in the query language to change. `auto` runs whichever of them recognise their own noise in the
item; naming one runs it whether or not it recognised anything, which is the escape hatch for a source
the detector is deliberately too conservative for. A name that is registered nowhere cleans with
NOTHING and says so — a typo must neither silently clean with something else nor fail the query.

An item cut to its budget returns a `PARTIAL_RESULT` note naming the part read and how many items were
cut — cleaning alone does not, because removing markup loses nothing the model could have used.

The same `{ai: {text: {…}}}` map applies on a virtual EDGE, where it bounds what the per-row judgments
read: `WHERE ai.relevant(n, '…')`, `ORDER BY ai.score(n, '…')`, `RETURN ai.classify(n, '…')` (§7.3–7.5).

#### `cluster` — groups with sizes you can trust

`cluster` returns one entry per group — `{label, size, share, examples}` — where `examples` are the
most typical members of that group.

Its cost does not grow with the size of the group the way the others do: every other function in the
table is priced per batch of rows, so a few hundred items can exceed a lens's time budget, while
`cluster` stays flat. Reach for it on large groups.

```cypher
MATCH (scope:DiseaseScope {registryQuery:'insomnia'})-[:HAS_TRIAL_SEARCH]->(run:TrialSearchRun)
MATCH (run)-[:RETURNED]->(trial:ClinicalTrial)
RETURN cluster(trial.title, 6) AS clusters
```

Three properties follow, and they are the reason to prefer it when membership matters:

- **The sizes are counted, not estimated.** `size` is arithmetic over the rows the traversal returned.
  Every other function can describe a group but cannot say how big it is — a model asked for a count
  guesses. This is the difference between a claim and a number.
- **It is deterministic.** The same rows always yield the same clusters and the same sizes, run after
  run — so a page built on it does not move underfoot when re-read.
- **It degrades rather than fails.** If a group cannot be named, it still returns with its size and
  examples: the grouping is true whether or not anything named it.

Being a list of maps, `clusters[0].size` is addressable — which is what lets a surface make a cluster
filter the rows it came from. Prefer `themes` when only the recurring topics matter and membership
does not; prefer `cluster` for "what groups are in these, and how big is each".

---

## 8. Views — a saved query used as a label

A **view** is a named, saved Cypher body whose rows *are* a type, referenced in a later query by its name as a
plain **label**. It is the natural extension of a virtual join: a virtual label is a view over an external
system; a *view* is a view over the graph (real + virtual) itself. Two kinds, by cost:

- **Regular (inlined).** Expanded at query time — the view's `MATCH … RETURN <var>` body is spliced in and its
  return variable renamed to the outer alias, so `MATCH (c:my_key_accounts)-[:R]->(x)` becomes
  `MATCH <view body> MATCH (c)-[:R]->(x)`. Always fresh; no storage. (Flat inlining, **not** `CALL {}` — the
  scope rewriter rejects subqueries.)
- **Materialized (cached).** The result nodes are committed and a reference reads the cache instead of
  re-running the body, until a TTL / refresh policy invalidates it. This is the durable sibling of the
  ephemeral `keep(queryId)` option: the expensive fan-out (map) + agentic reduce runs on a **refresh
  schedule**, in the background under a big budget; the interactive query just reads the precomputed result.

### 8.1 No new grammar — usage is a label, definition is metadata

There is **no `DEFINE VIEW` statement.** The engine parses queries with the official Neo4j parser
(cypher-dsl); a non-standard statement would reintroduce pre-parse interception, and Neo4j never executes DDL
anyway. The concept splits cleanly:

- **Usage needs zero syntax** — a view is a plain label (`MATCH (c:my_key_accounts)-[:…]`); the parser accepts
  any label, the registry resolves it. Exactly how `Document` / `HubSpotContact` are used today.
- **Definition is a metadata / lifecycle action** (define / list / drop, + refresh / scope / TTL) — an API +
  YAML surface, never a query. The `RETURN`-bearing body is standard Cypher, parsed by the real parser.

```yaml
# config/views/key-accounts.yml — durable/shared, like a virtual type today (a realm or world can ship it)
- name: my_key_accounts
  materialized: false            # regular view — expands at query time
  outputLabel: HubSpotContact    # the type the view yields (its rows ARE this type)
  cypher: |
    MATCH (me:AssistantUser)-[:HAS_HUBSPOT_OWNER]->()-[:OWNS_CONTACT]->(c:HubSpotContact)
    WHERE c.arr > 100000
    RETURN c
```

The same body can be authored at runtime by the assistant on the acting principal's behalf
(`viewService.define(hostScope, name, cypher, materialized)`, surfaced as a `define_view` tool) —
"save this as my key accounts." `hostScope` contains the host-bound world, context, policy revision,
and principal; it is never a guest-supplied tool argument.

### 8.2 Output typing — identity preservation is the rule

A view you can **traverse from** always yields nodes of exactly ONE type. Whether it composes is governed by a
single rule — does it preserve node identity?

1. **Subset view** — `RETURN <whole node>`: the rows *are* instances of an existing type (real or virtual),
   keeping its identity, properties, and edges. Fully composable; the view name is a **named subtype**
   (`my_key_accounts ⊆ HubSpotContact`). Because virtual types materialize onto the **real** persisted node
   (prefer-real-node MERGE), a subset view over `Document` yields nodes that *are* the persisted documents,
   carrying `OWNED_BY` / `MENTIONS` — the real-vs-virtual distinction dissolves; only identity matters.
2. **Projection view** — a reshaping `RETURN c.email AS email, count(d) AS docCount`: mints the view's own
   derived type; composes only via edges the view declares (usually a leaf).
3. **Tabular view** — a `RETURN` of scalars/aggregates: a named result set (report-only), not traversable.

### 8.3 Composing views

A subset view's name is a label, so it composes with structural + relevance edges, and with other views
(staged materialization to fixpoint):

```cypher
-- a regular view + an agentic-rag edge + a structured filter, in one standard-parseable query
MATCH (c:my_key_accounts)                                  -- expands + materializes its HubSpotContacts
WHERE c.renewalDate < date('2026-10-01')
MATCH (c)-[r:RELEVANT_TO {via:'agentic-rag', intent:'renewal risk'}]->(d:Document)
RETURN c.email, d.title, r.snippet ORDER BY r.score DESC
```

A materialized view is queried the same way, but reads the **stored** subgraph — cheap, no producer calls
fire:

```yaml
# config/views/breach-watch.yml
- name: breach_mentions
  materialized: true
  outputLabel: Document
  refresh: "0 6 * * *"           # daily 06:00 — reuse the cron scheduler
  ttl: 30d                       # sweep rows this old if a refresh is missed
  cypher: |
    MATCH (o:Organization) WHERE o.isCustomer
    MATCH (o)-[:RELEVANT_TO {via:'agentic-rag', intent:'security incident / breach'}]->(d:Document)
    RETURN d
```
```cypher
MATCH (d:breach_mentions) RETURN count(DISTINCT d) AS incidents      -- an aggregate over a precomputed view
```

### 8.4 The materialization cache is pluggable

The materialized-view cache is a **strategy behind an interface**, not a fixed mechanism. The default strategy
is graph-colocated and transactional: a
`MaterializedView {view, worldId, contextId, accessPolicyRevision, principalId?, expiresAt}` marker node with
`[:MEMBER]` edges to the cached result nodes, swept by TTL. But the store is an SPI:

```kotlin
interface ViewMaterializationStore {
  data class CacheState(val expiresAt: Long, val memberCount: Long)
  data class RowSnapshot(val columns: List<String>, val rows: List<Map<String, Any?>>, val expiresAt: Long)

  fun state(view: String, scope: String): CacheState?
  fun clear(view: String, scope: String)
  fun sweepExpired()

  // A view whose body returns a NODE caches its members.
  fun materialize(view: String, scope: String, memberIds: List<String>, expiresAt: Long)
  fun bindClause(alias: String, outputLabel: String, view: String, scope: String): String

  // A TABULAR view has no node to point a MEMBER edge at, so it caches the rows themselves.
  fun materializeRows(view: String, scope: String, columns: List<String>, rows: List<Map<String, Any?>>, expiresAt: Long)
  fun rows(view: String, scope: String): RowSnapshot?
}
```

Two things in that shape are load-bearing.

**A view without an `outputLabel` is a row snapshot, not a member set.** Its body returns columns, and
there is no node to point a `MEMBER` edge at — so what is cached is the rows, which is what a client
reading the view by name wanted anyway. A store that implements only the member half silently fails
every tabular view.

**Members are bound by a clause, not returned as ids.** `bindClause` lets the default
graph-colocated store prepend pure Cypher (`-[:MEMBER]->` off its marker node) with no ids threaded
through the query; an off-graph store returns `elementId(alias) IN [...]` instead. Returning a member
list would have forced every store to pay the graph store's worst case.

`scope` is the acting caller's scope as §2 defines it; the store never interprets it, only keys on it.

**Every entry is keyed per caller**, unconditionally. A view body may use caller-specific
credentials, policy, inputs or anchors, and the reference host does not attempt to prove otherwise —
there is no analysis that marks a view caller-invariant and no sharing of one entry between callers.
That is the conservative choice and it costs: two callers asking for the same view materialize it
twice. A host that wants to share reference-data views across callers needs an invariance proof this
one does not have, and must not assume the absence of the parameter implies one.

An alternative strategy swaps in without touching the query path: an **in-memory LRU** for a single-process
deployment, an **external KV / Redis** for a horizontally-scaled one, or an **`immutable`** strategy (no TTL,
explicit invalidation only) for reference data. The refresh policy (`ttl`, cron `refresh:`) is orthogonal to
the store.

### 8.5 A general result / entity cache — and negative results

The same store generalizes beyond views to a **producer result cache** — the answer to "should API fetches be
cached?" A principal-dependent producer call is `(worldId, contextId, principalId, access-policy digest, realm/producer digest,
source/credential revision, producer args/key) → records`; every component participates in the cache
key. `principalId` may be omitted only for a producer the host verifies is principal-invariant.
Deployment-approved public/reference producers use a separate explicitly public namespace and
dataset revision. Caching is governed by the §9 diagnostics:

- **Positive result** — a genuine, successful fetch (**including a real "no records"**) is cacheable with a
  per-producer `ttl` (or `immutable` for stable reference data). A repeat query for the same key reads the
  cache; no producer call fires.
- **Negative (entity) result** — a *known miss* for an ENTITY (this login / email / domain resolves to
  nothing) is cached too, so a fan-out doesn't re-probe a dead key every query. This is a store with a
  TTL and **invalidate-on-reconnect**: reconnecting an integration re-attempts every key previously
  missed for that caller, so a miss recorded under a broken credential is never written off permanently.
  The miss is keyed, not stamped — earlier hosts wrote a `_bridgeMissAtMs_<target>` timestamp onto the
  **anchor itself**, which put a system property into `keys(n)` where schema snapshots, property
  enumerators and a plain `RETURN n` could all see it. A cache must not leak into the data model, and
  eviction must not be a scan of every property of every node a caller owns; keying the entry gives both.
- **Never cache a FAILURE.** A timeout / 5xx / expired-auth fetch is **not** a result — caching its emptiness
  would hide the data once the integration heals. Only a `PRODUCER_ERROR`-free outcome is cacheable (§9).

The identity **bridge** (who an external identity *is*, §5.2) is the one already-persistent positive cache; the
producer result cache and the entity negative-cache are the same idea applied to *what* a key holds, and to
keys that hold **nothing** — all behind one pluggable store, so a deployment picks graph-colocated, in-memory,
or external as it scales.

### 8.6 Persisted scopes, and consuming a scope as typed instances

A materialized view refreshes (it re-runs its body on TTL expiry). A **persisted query** is the other
lifecycle over the *same* MEMBER-set store: a saved result set addressed by an opaque handle
(`query:<uuid>`), that does **not** re-run — it is a scope of immutable results that survives until explicit
deletion. The two differ only in metadata, so the store from §8.4 generalizes with three fields rather than a
new mechanism:

- `expiresAt` becomes **nullable** — a TTL for a view, `null` (pinned) for a persisted query;
- a `refreshable` flag — true for a view (has a body to re-derive), false for a persisted query (immutable
  snapshot; any body is kept only as provenance);
- `list()` / GC — so pinned entries are enumerable and reclaimable.

Because a persisted scope is bound as a label (`MATCH (x:query_7f3a) …`) exactly like a materialized view,
nothing on the read path changes: a scope is a scope, whether named-and-refreshing or handle-and-pinned.

**Two properties are frozen at capture, decided per store:** *membership* (which nodes are in the scope) is
always frozen — that is the MEMBER edge set. *Values* are not, by default: the edges point at live nodes
whose properties keep changing. A store that needs a true point-in-time snapshot copies the projected columns
at capture; a virtual/fetched member is already a committed copy (prefer-real-node MERGE, §8.2·1), so it is
naturally frozen.

Consuming a scope: because a **subset** scope RETURNs whole, identity-preserving nodes (§8.2·1), a client
runtime can hydrate its members directly into typed instances — the type comes off the node's own label, so
the reader needs no per-query type argument. This is the source side of the type-and-function model: the saved
scope supplies the objects; their methods (pure compute, or effectful write-back through the producer) live on
the type. A **tabular** scope (§8.2·3) has no node to hydrate — it is a frozen values table, readable and
renderable but never bound as a label or hydrated into instances. The store records which kind a handle is and
refuses label-binding / hydration on a tabular one, so an unsupported consumption fails honestly rather than
producing wrong Cypher.

---

## 9. Caps, cost, and diagnostics

Because a Virtual Cypher query reaches into live external systems, it is bounded on every axis, and
a bound that bites is **always surfaced**, never silent.

**Caps (per join):**

- **`maxAnchors`** (default 200) — reject if the probe binds more anchors than this (a fan-out
  guard; pin/filter the anchor).

  The cap counts **anchors, not records**, and that distinction decides what helps. Pushing a
  predicate on the TARGET makes each call cheaper and leaves the NUMBER of calls exactly as it was;
  only narrowing the anchor set — or reaching the target through a different door — changes whether
  the query is refused.

  **Declare a second door where your source offers one.** A join is one call per anchor, so a realm
  that also declares the same target keyed on something else gives a query a way in that does not
  fan out at all:

  ```yaml
  virtualJoins:
    # One account's cases — one call per account.
    - { anchorLabel: CustomerAccount, relationship: HAS_CASE, keyField: accountKey,
        recordKeyField: accountKeyAsked, producer: casesByAccount }
    # Every open case — one call for the whole desk.
    - { anchorLabel: ChatwootDesk, relationship: HAS_CASE, keyField: status,
        recordKeyField: deskStatus, producer: casesByStatus }
  ```

  A query pinning `c.status` has already bound the second door's key, and the accounts fall out of
  the rows it returns. Pin it explicitly with `{via:'…'}`, and where the host enables access-path
  rewriting the engine may choose it for you — but only where it can show the answer is identical.
  It will decline, and say so, when the hop is `OPTIONAL` (anchors with no rows would be lost, and
  "absent from this list means none" is a real reading), when an aggregate folds the anchor, when
  another predicate on the target would go unapplied, or when the door's key is not pinned.

  So the second door is worth declaring whether or not the rewriter is on: it is what the author
  pins today, and the search space the engine gets tomorrow.
- **`maxFanoutTotal`** (default 5 000) — reject if materialization would create more nodes than
  this (primary + brought).

**Predicate pushdown, and what it does *not* change:** a producer may declare rules mapping query
predicates on its target to the source's own query language, so a `WHERE` scopes the fetch at the
source instead of after it. Equality, ranges, `CONTAINS`, and **membership in a list-valued
property** (`'OLDER_ADULT' IN t.ageGroups`) are all pushable when a rule exists for them.

The guarantee is that **pushdown changes cost and never rows**. Anything a source cannot answer is
still applied to the materialized graph, so the same query returns the same rows whether it was
pushed or not; only the number of records fetched differs. A value that does not fit the rule's
declared shape is left to the graph rather than embedded in a source query it would corrupt.

**Two ways to write a rule.** A rule renders either **text** or a **structured clause**, and it
declares exactly one of them.

```yaml
pushdown:
  # TEXT: a search qualifier or a `q=` conjunct, with a {value} slot.
  - property: html_url
    op: CONTAINS
    qualifier: "repo:{value}"

  # STRUCTURED: a clause placed in the producer's own args, for a source whose
  # query is JSON rather than a string — an Odoo domain, an Elasticsearch
  # bool.filter, a GraphQL where:.
  - property: status
    op: IN
    argPath: domain.-
    clause: ["status", "in", "{values}"]
```

`argPath` addresses the producer's `args` exactly as `keyArg` does, with one addition: a trailing
`-` means **append to the list there**. That is what lets a conjunction take another clause without
the rule knowing how many are already present — and without moving an index an existing `keyArg`
addresses, which inserting at the front would silently do.

Inside `clause`, `{value}` is substituted into a string, and a node that **is** exactly `"{values}"`
is replaced by the predicate's member list. The distinction matters: a set must reach the source as
real JSON (`["status", "in", ["open", "pending"]]`), not as text that happens to look like it.

**`linkPrevious`** is for a source that spells conjunction as a field on the PRECEDING element
rather than implicitly. Chatwoot's conversation filter is one: each clause carries `query_operator`
naming how it joins to the next, and the last must not carry one at all — so it cannot be declared
statically on the base payload, only written when a clause is appended.

```yaml
pushdown:
  - property: status
    op: IN
    argPath: payload.-
    clause: { attribute_key: status, filter_operator: equal_to, values: "{values}" }
    linkPrevious: { query_operator: AND }
```

Omit it for a source whose list is an implicit conjunction — an Odoo domain, an Elasticsearch
`bool.filter` — where appending is the whole operation.

**Verify a pushdown rule against the live source.** These shapes are unforgiving and fail loudly
rather than subtly: appending to a Chatwoot payload without `query_operator` is an HTTP 500, and
including it on the final clause is rejected outright. A rule that renders nothing is correctly
reported as absorbing nothing, so a wrong rule leaves the query slow rather than incorrect — but
slow is what the rule was for.

**Enumerated sets** (`WHERE c.status IN ['open','pending']`) push by **member expansion**. A text
rule renders them as an OR group, and only into a conjunction-style qualifier that has one — a
space-separated search qualifier does not, since `status:open status:pending` means AND to a search
API and matches nothing. Where a rule cannot express the set, it renders nothing and the predicate
stays a graph-side filter.

**What "absorbed" means, and why it is load-bearing.** A rule that renders nothing is reported as
having absorbed nothing, and the engine plans accordingly. This is not bookkeeping: the residual —
what the source did *not* take — is what decides whether a `LIMIT` may be pushed and whether a count
may be asked of the source instead of fetched. A rule that claimed a filter it did not send would
license the engine to read one page and call it the whole answer.

**Asking the source for a number instead of the records:** a producer may declare what it can
aggregate, so a query that only counts costs one call rather than one call per anchor.

```yaml
aggregates:
  - measure: count            # count | sum | min | max
    operation: cases.counts   # the source's own aggregate endpoint; omit to reuse `operation`
    valueField: total         # where the number is in the response
    keyField: accountKey      # which key the number belongs to
```

Every field is required for a reason:

- **`valueField`** — a response shaped `{"count": 12}` and one shaped `{"__count": 12}` are equally
  plausible, and reading the wrong one yields a plausible integer rather than an error.
- **`keyField`** — a grouped response with no key echo cannot be attributed, and attributing it by
  position is how one account's case count silently becomes another's.
- **`of:`** is required for `sum`/`min`/`max` — `sum` with no property is not a question a source
  can answer.

`avg` is deliberately not supported: an average over one page cannot be recombined across pages, so
a source reporting only an average cannot be trusted to have averaged everything. Declare `sum` and
`count` instead.

Declared rather than assumed. A database can always `GROUP BY`, but an arbitrary REST endpoint
cannot be presumed to count, and a producer that guessed would return a confident number from
whatever the endpoint happened to send back.

The engine pushes an aggregate only when it is **safe as well as declared**: the target must be
projected nowhere else (`RETURN c.subject, count(c)` needs the rows whatever else it asks), every
aggregate over it must be pushable (one `collect` means the records are needed anyway), `count(*)`
never pushes because it folds rows of the whole pattern, and any predicate on the target must be one
the source absorbs — a source can only count what it can also filter. Today `count` is executed;
`sum`/`min`/`max` are recognised and left unpushed, and the engine pushes only when EVERY measure in
the query is deliverable.

**This makes the SHAPE of a view a cost decision.** `collect(c.subject)` needs the records whatever
else the query asks, so a view that both counts and collects always pays the collecting price —
including when the question was triage across the whole book and nobody was going to read a subject.
Write the two questions as two views:

```yaml
# Triage across every account — answerable by the source.
- name: HealthOpenCaseCountsByAccount
  cypher: |
    MATCH (a:CustomerAccount)-[:HAS_CASE]->(c:SupportCase)
    WHERE c.status IN ['open', 'pending']
    RETURN a.accountKey AS accountKey, count(c) AS openCases

# The detail, for the accounts a pane is showing.
- name: HealthOpenCasesByAccount
  cypher: |
    MATCH (a:CustomerAccount)-[:HAS_CASE]->(c:SupportCase)
    WHERE c.status IN ['open', 'pending']
    RETURN a.accountKey AS accountKey, collect(c.subject) AS subjects
```

Each description should point at the other: the counts view names what to ask for detail, and the
detail view says to ask it about named accounts rather than the whole book.

**Cost (per producer):** a `cost:` block declares the source's shared **rate bucket** and limit.
The planner budgets producer calls against it and, when a query can't fit, emits `EXPLAIN`-style
**advice** (push a predicate, add a `LIMIT`, narrow the anchor) rather than silently over-calling.

**Query-shape advice:** `EXPLAIN` also names a shape the store runs correctly but quadratically —
an equality join between two matched sets with a function wrapping one side, `WHERE k.id =
toString(n.res_id)`, which a planner cannot hash-join and so filters every pair (measured: 13.6 s
against 2.5 s on 6,000 × 4,010 rows). The advice line quotes the clause and the spelling that
hashes: project the function first (`WITH n, toString(n.res_id) AS nResId`), then compare the two
plain values (`WHERE k.id = nResId`). Advice never changes what the query runs or answers; the
advised spelling answers the same rows and draws no advice of its own.

**Diagnostics — what a 0-row or partial result *means*:** a fetch that returns nothing is
indistinguishable from "genuinely no data" unless the engine says otherwise. Every producer failure
is classified and surfaced as a warning on the result:

| diagnostic | when | meaning |
|---|---|---|
| `PRODUCER_ERROR` (`FETCH_FAILURE`) | a timeout, a missing gateway tool, a non-auth error | the source could **not** be reached — *not* "no data". Fix the integration. |
| `PRODUCER_ERROR` (`AUTH_EXPIRED`) | a 401 / "token expired" / `EXPIRED_AUTHENTICATION` | the OAuth token has **expired** — reconnect to refresh. The empty result is because the source rejected the call. |
| `PARTIAL_RESULT` (`TRUNCATED`) | pagination hit `maxPages` with a still-full last page; a call budget ran out mid-fan-out; a declared floor or gate dropped records | the fetch **succeeded but is incomplete** — the source has more. *Not* a failure. The detail says which cause, because the fixes differ: raise the cap, or simply ask again (a budgeted run keeps its completed work and resumes rather than restarting). |
| `PARTIAL_RESULT` (`NOT_FOUND`) | the source answered a definitive 404 for one key of a fan-out | that key **does not exist** — as opposed to "we could not find out", which is `FETCH_FAILURE`. The answer is short by exactly the named keys; the source is not down, and the other keys' rows are good. |
| `PARTIAL_RESULT` (`DERIVED_LOWER_BOUND`) | a DERIVE rule set concluded while the facts its rules read were themselves incomplete (another diagnostic fired, or a demand went unmet) | membership and any aggregate over it are a **lower bound, not a total**. The fixpoint is correct over what was materialized and says nothing about what was not — a rule body cannot fetch (§13.6). Not a failure, and not "nothing was derived". |
| `INCOMPLETE_TRAVERSAL` | a variable-length traversal (§5.12) stopped short of its declared depth | the warning names the hop reached and the bound hit (`maxFanoutTotal`, frontier width, or the unbounded-`*` cap). Rows cover only the hops walked; any subtree total is a **lower bound**. |
| `UNKNOWN_VIA` | an edge pinned `{via:'…'}` that no declared join offers | the rows are **real but came from a different join** than the one named. The query still answers — a via that does not exist must not cost a good answer — and the warning lists the vias that do exist so it can be re-issued. Matters most where several joins converge on one label, since the substitution is otherwise invisible. |
| `AMBIGUOUS_LABEL` | the query named a parent label that more than one installed type answers to through the same edge | **nothing was fetched**, so the empty result is not "no data". The engine will not choose between a customer's two helpdesks on the caller's behalf; the detail names the types, so the query can be re-issued naming one. |
| `NEEDS_FILTER` | a source that cannot be swept was asked without a narrowing predicate | the answer is **unknown until the query is narrowed** — not "no data". |
| `FILTER_STARVED` | candidates were found, and the query's own filters rejected every one | a legitimate zero **that explains itself**: relax a filter rather than reading it as "no such data anywhere". The combination may be unsatisfiable at this source. |
| `FIELDS_WITHHELD` | governance removed fields — the secret reflex, `mask: drop`, or governed exposure (§5.15) | the **rows are complete**; named fields were removed by policy. An absent field here means "not exposed by this source's governance", never "no data". |
| `COMPUTE_FAILED` | a producer's `compute:` expression raised on some records | the rows are complete and the source is fine; **one property is absent** on the records named. Absent rather than null or zero, because either would read as an answer. |
| `MATERIALIZATION_FAILED` | the source returned data the graph could not store | the records **exist** but are missing from the result, so an answer of "none" is definitely wrong. The fix is the engine's, not the caller's. |
| `REDUCTION_FAILED` | an `aggregate` reduction or an `extract` call failed | the anchor's reduced or extracted records are **absent**, not empty. Retried on the next traversal. |

A failed fetch is **never cached** as an empty result (so a later call with a refreshed token finds
the data); only a genuine, successful "no records" is cacheable.

**When an answer takes longer than the asker will wait.** A cold traversal can legitimately run for
minutes, which is longer than many callers will hold a connection open. A caller may therefore give
a **patience budget** with its query. If the answer arrives inside that budget it is returned
normally and the budget is invisible. If it does not, the result comes back as a **run reference**
instead: an id, a state, and the addresses at which the run can be polled, stopped, or answered.

The guarantees:

- **Empty rows beside a run reference mean *not yet*, never *no data*.** A warning always
  accompanies them saying so. This is the one misreading that matters, because "no rows" and "no
  answer yet" look identical to a consumer that only reads rows.
- **The work is not abandoned when the caller stops waiting.** The same run continues, and its
  answer is collectable afterwards through the reference.
- **A run belongs to whoever started it** and is invisible to everyone else.
- **Waiting and watching return the same rows.** A patience budget changes only who waits, never
  what the query answers.
- **An over-budget-COST query still asks before it spends.** Where the cost gate would refuse a
  query outright, a watching caller instead receives a run in a *waiting* state carrying the
  question and its options; nothing is materialized until it is answered, and an unanswered
  question expires on its own rather than holding resources.

A caller that offers no budget is unaffected: the query runs to completion or to the execution
ceiling, exactly as before.

---

### 9.1 Fills — driving a large materialization slowly

Some materializations are too big for one query's patience: a 12-month history over many anchors,
an open catalog sweep. A **fill** drives one durably, slowly, and idempotently:

```
POST /api/v1/admin/kg/fills        { "cypher": "...", "budgetPerTick": 60, "label": "crime history" }
GET  /api/v1/admin/kg/fills        → [{ id, state, ticks, liveCallsTotal, lastError, ... }]
DELETE /api/v1/admin/kg/fills/{id} → cancelled (completed work stays cached; nothing rolls back)
```

The engine re-runs the fill's query on a schedule, each pass under a **call budget**: at most
`budgetPerTick` producer calls, stopped CLEANLY when spent — everything fetched stands, nothing
is recorded for the skipped remainder. Because finished work is cached (and closed periods never
expire), each pass advances past everything already done and spends its whole budget on new
ground. A pass that completes with ZERO live calls is the finish line: the fill turns `DONE`.

**Guarantees**

- **Idempotent and resumable by construction.** The fill's progress IS the caches. Restart the
  process, cancel and restart the fill, run the same query by hand in between — nothing is done
  twice and nothing is lost beyond the tick in flight.
- **Rate-limited twice over.** The per-tick budget bounds each pass; within a pass, every
  producer's own declared `cost.rate` paces its calls.
- **An error never finishes a fill.** A failing pass records its error and stays `RUNNING` —
  transient source trouble is retried on the next tick, and the error is visible on the fill.
- **A budget-exhausted ordinary query says so.** Outside fills, the same budgeted stop surfaces
  as a warning naming what was not fetched — a partial result is announced, never passed off as
  complete.


## 10. Steering the generator — type-level `examples:`

The schema tells the text-to-Cypher generator what *exists*; it does not tell it what to *prefer*.
When two legal paths answer the same question — a projected scalar vs. a resolvable edge, a
content property vs. a label — the generator can pick the plausible-but-wrong one and return an
empty or ungrounded result **without any error**. That preference knowledge must live somewhere
explicit, or it exists only as an accident of schema shape and dies on the next schema change.

The home for it is the **`examples:` key on the owning type** — a few-shot `q`/`cypher` pair
rendered into the generator prompt:

```yaml
- name: RelevantEmailThread
  virtualJoins: [ … ]
  examples:
    # STEERING — a "summarize my discussions with X" digest is built from thread CONTENT
    # (`t.snippet`), NEVER from topic labels and NEVER from a string literal:
    - q: "summarize my email discussions with Alex Doe"
      cypher: |
        MATCH (p:Person) WHERE toLower(p.name) CONTAINS 'alex' AND toLower(p.name) CONTAINS 'doe'
        MATCH (p)-[:RELEVANT_TO]->(t:RelevantEmailThread)
        RETURN summarize(t.snippet) AS digest
```

Mechanics:

- **Attribution.** Each example is attributed to its type's schema *segment* (the realm's group, or
  a host group like `email-topics`) and renders only when that segment does — under schema-relevance
  filtering an example loads exactly when the question needs its domain. Steering grows with the
  number of domains; per-question prompt cost stays flat.
- **Connection gating.** Examples gate with the type's joins: a disconnected integration
  contributes neither schema nor steering.
- **Placement rule.** An example lives on the type that OWNS the path it teaches. A bridge across
  realms (thread → topic) is taught by the type that owns the *target* of the lesson.

Discipline (how these earn their place):

1. **Steers follow pinned defects, never hunches.** First a mirror test that reproduces the wrong
   shape and asserts the exact defect (wrong shape absent AND right data present — "no error,
   non-empty" admits garbage). Then the example. Then the gate.
2. **Small.** One `q`/`cypher` pair per defect class, placeholder names only (never real people,
   orgs, or repos).
3. **Gated.** An example change is a generation change: it ships only past the full hermetic
   mirror and a live queries.txt check.

Proven cases (2026-07): `summarize(t.snippet)` (content, not `topic.name` labels — fixed a live
regression), `t.participantNames` (read the projected participant list, don't fan back over the
similarity edge), `p.authorNames` (the projected scalar; an `AUTHORED_BY` edge-walk in the same
query as the fetch is empty). Each was a 5-line example that fixed a defect three rounds of
schema-level engineering could not touch.

---

## 11. Determinism and guarantees

- **Read-only.** A user query never writes the graph. Materialization happens in a transaction that
  is **rolled back**; the sole persisted side effect is a write-through identity **bridge** (a
  cache of *who* an external identity is, not *what* data they hold). The single, explicitly
  opted-in exception is the dedicated annotation-write surface (§12) — ordinary queries remain
  read-only and continue to reject mutating clauses.
- **Scoped, fail-closed.** Every keyed probe goes through the world/context scope rewriter; vector
  searches are filtered by world, context, and access-policy revision at the source. A query can
  never read another context without an explicit authorized bridge, and never another PRINCIPAL's
  data; between two worlds of one principal the boundary is focus rather than confidentiality
  (§15). Deployment-approved, revisioned `Public`/reference datasets are the explicit exception. An
  unparseable or unscopable query is rejected, not run.
- **Bounded.** Every fetch is bounded by a bound anchor, `maxAnchors`/`maxFanoutTotal`, `paging`
  caps, `k`, and rate budgets. Truncation is reported.
- **Idempotent re-runs.** A re-run re-fetches; caching (`ttl`/`immutable`) and `temperature: 0` for
  any LLM-derived value make repeated runs of the same query agree — repeatability is a correctness
  property, not just a speed one.

---

## 12. Graph annotation writes — bounded local writes after federated selection

A realm may declare that a type's REAL nodes accept bounded local annotations: mark each writable
property `annotatable: true`, optionally mark one property `annotationVersion: true` as the
concurrency field, and the type must have an `identity: true` property. Deployments additionally
gate the whole surface off by default. Without both opt-ins, no write is possible.

```yaml
# types/person.yml (excerpt)
properties:
  id:           { type: string, identity: true }
  reviewStatus: { type: string, annotatable: true }
  reviewedAt:   { type: string, annotationVersion: true }
```

An annotation statement is: any read selection (it may traverse fetched, source-backed nodes), then
exactly `WITH DISTINCT <target>[, <expr> AS <alias>…] ORDER BY … LIMIT n`, then exactly
`SET <target>.<property> = <literal | $parameter | alias>`:

```cypher
MATCH (u:AssistantUser)-[:EMAILED]->(p:Person)-[:HAS_X]->(v:SomeFetchedLabel)
WHERE v.field = 'value'
WITH DISTINCT p ORDER BY p.id LIMIT 50
SET p.reviewStatus = 'follow-up'
RETURN p
```

**Guarantees.**

- The fetched node participates only in *selection*. The transient materialization rolls back as
  always; the selected real nodes are then updated in a separate write.
- The limit must be a positive whole number within the deployment maximum; the ordering is
  required. Everything else — writing a fetched binding, `SET +=`, dynamic property names, label
  changes, `CREATE`/`MERGE`/`DELETE`/`REMOVE`/`FOREACH`, procedure calls, subqueries, `UNION` — is
  rejected **before anything runs**. Writing a fetched binding names the durable binding you
  probably meant, and guarantees no fetch and no write occurred.
- A write never redirects to the source system, even if the source declares a writable operation.
  Changing the source record is always its own explicit action.
- Execution is two-phase: a **dry-run** returns the exact would-be changes under an expiring plan
  id; **confirming** applies that frozen plan — never a re-run selection. An expired plan requires
  a new dry-run; a plan applies at most once.
- At apply time each target is re-found by its identity within your scope: a target that vanished
  or is no longer yours is skipped (one combined count — the two are deliberately not
  distinguished), and one whose value (or version field) changed since the dry-run is reported as
  a conflict and left untouched.
- Results state committed values only, with `selected` / `applied` / `conflicted` /
  `disappearedOrUnauthorized` counts.
- Every applied change is journaled and can be undone. Undo restores the previous value only where
  your annotation is still the current value — it never overwrites a later edit.
- Fetched data may flow into an annotation only as a scalar captured at the selection barrier,
  frozen at dry-run time.

---

## 13. Derived labels and relationships — DERIVE rules

A **rule set** defines a **derived label**: a label that exists on no stored node, whose
membership is CONCLUDED from data by rules — including rules that refer to the label they are
defining. A rule set may equally define a **derived relationship** — an edge whose existence is
a conclusion (§13.4); everything in this section reads the same for both, with membership a
node for a label and an ordered pair for a relationship. That self-reference is the point: it expresses propagation no single query can —
ownership chains, phoenix succession, status that feeds back into further status. Where a view
(§8) saves *one* query, a rule set is *many unordered clauses of one definition*, evaluated to a
least fixpoint. A view cannot reference itself; a rule may.

```yaml
# rules/phoenix-succession.yml — one rule set per file (shipped by realm-gov-uk)
name: gov-uk/phoenix-succession
derives: PhoenixSuccessor
description: >-
  An appointment that follows the same officer's appointment at a company the register now
  records as dissolved; phoenixDepth counts dissolved predecessors in the chain.
rules:
  - derive: "(b:PhoenixSuccessor)"
    from: |
      MATCH (a:UkAppointment {companyStatus: 'dissolved'}), (b:UkAppointment)
      WHERE b.officerId = a.officerId AND b.companyNumber <> a.companyNumber
        AND a.appointedOn IS NOT NULL AND b.appointedOn IS NOT NULL
        AND b.appointedOn > a.appointedOn
  - derive: "(c:PhoenixSuccessor {phoenixDepth: d})"
    from: |
      MATCH (b:PhoenixSuccessor), (c:UkAppointment)
      WHERE c.officerId = b.officerId AND c.companyNumber <> b.companyNumber
        AND b.companyStatus = 'dissolved'
        AND b.appointedOn IS NOT NULL AND c.appointedOn IS NOT NULL
        AND c.appointedOn > b.appointedOn
      WITH c, max(coalesce(b.phoenixDepth, 1) + 1) AS d
```

Each rule is a **head and a body** — read it as an implication:

- **`derive`** is a node pattern — or, for a derived relationship, a relationship pattern
  (§13.4) — naming what the rule concludes: which body variable becomes a member, and
  (optionally) derived properties computed from body bindings. Its one label (or relationship
  type) must be the rule set's `derives`. Quote it: property maps contain `: `, which YAML would otherwise read
  as a nested mapping.
- **`from`** is ordinary read-only Virtual Cypher that BINDS variables and stops — **no
  RETURN**. The head is the projection; the host constructs the runnable query from the parsed
  head, and both productions are parsed by the real Cypher parser (the same §8.1 stance: no new
  grammar in queries, definition is metadata).

**Semantics in one sentence: a node carries the label — a pair of nodes carries the
relationship — if and only if some rule concludes it.**
Rules are unordered clauses — reordering them cannot change the result — and evaluation runs to a
fixpoint, so a member concluded by one rule can satisfy another rule's body; the second rule
above chains through its own conclusions, which is how a depth-unbounded pattern is expressed in
two clauses. Two rule sets may derive the same label: that is the union of their clauses, not a
conflict. The classic worked case is the OFAC 50 Percent Rule — blocked if listed, or if blocked
parties in AGGREGATE own ≥ 50%, recursively — where the entity that matters is on no list and no
fixed-depth query can be correct for all data.

### 13.1 Params, and anchoring a rule

A rule set may declare **params** in the same vocabulary as view params (type / `default` /
`description`), referenced as `$name` in any body:

```yaml
params:
  minStake: { type: int, default: 50, description: "Aggregate percentage at which status propagates" }
```

A query that merely MATCHes the derived label evaluates the rules **implicitly, on defaults** —
so a rule set meant for implicit evaluation should default every param. Anchoring a rule set to
one entity is nothing special: declare the key as a param (`{officerId: $officer}`). Param names
may not shadow the engine's reserved names or the scope pair (`userId`, `worldId`).

### 13.2 What a rule may say — the validated fragment

Validation at install time enforces the fragment that makes hosted rules safe — each restriction
is a leg of the guarantee that evaluation terminates:

| You may | You may not |
| --- | --- |
| conclude a label or a relationship, with derived properties | write the graph (`CREATE`/`MERGE`/`SET`/`DELETE` in a body) |
| reference the derived label positively — recursion, `any(…)`, `EXISTS` | reference it under a negation: `NOT`, or the quantifiers `none(…)` / `all(…)` / `single(…)` |
| aggregate in recursion with `sum` / `count` / `max` / `collect` | use `min` / `avg` / percentiles inside recursion |
| reference other labels, views and virtual joins as usual | `RETURN` in a body — the head is the projection |
| reference declared params as `$name` | reference a param the set does not declare |
| conclude the same kind in every rule of a set | mix a node head and a relationship head — one fixpoint cannot be both |
| declare `requires:` to bring the facts in first (§13.6) | write the graph in a demand — it is read-only like a body |

`none(…)` is `NOT any(…)`, and both `all(…)` and `single(…)` can be falsified by a member a later
round adds — all three are the same non-monotone self-reference as `NOT`, whatever they look like,
so all three are refused. Say it the monotone way instead: `any(…)` and `EXISTS` only become more
true as membership grows, which is exactly what the fixpoint needs. One caution, because the engine
does not yet catch it: a negation written as a COUNT COMPARISON (`size([x IN xs WHERE x:Derived])
= 0`) or as a `CASE` that inverts the label is equally unsound and is currently **admitted**. Such a
rule settles on the first or second round onto a set that contradicts its own body, and the round
cap will not save you because nothing is still moving. Do not write one.

A rule set that breaks the fragment fails validation with a message naming the rule and the
property it broke; it never half-installs. A conforming set's MEMBERSHIP is guaranteed to
terminate: rules can only conclude over nodes that exist, membership only grows, and a growing
subset of a finite set must stop growing. For a relationship set the finite set is the *square*
of the node count, which is why it carries its own budget (`maxPairs`, §13.4) on top of the
argument.

That argument is about membership, and it does not extend to a derived NUMERIC PROPERTY defined
in terms of its own value on a neighbour. `phoenixDepth` above is one: it settles because
appointment dates strictly increase, so the chain it climbs cannot close. On CYCLIC data — mutual
blocks in a tracker, cross-holdings in an ownership graph, dependency cycles in a registry — two
members lift each other by one every round and there is no ceiling for the fixpoint to stop at.
The evaluation then fails loudly at its round cap, naming the property that would not settle and
the rule that stamps it; it never truncates silently. Note that the aggregate is not what decides
this — `max` cannot shrink as membership grows, so the fragment admits it, while a grounded `min`
descending to a floor would converge and is refused; what bounds such a value is groundedness,
which lives in your data and not in the rule. **Conclude membership in the rule set and compute a
distance in the projection view** (§13.5), where `min(length(p))` is finite because a path may not
repeat a relationship.

### 13.3 Conclusions are computed, never stored — and they carry their why

Derived facts are an overlay: queries see conclusions consistent with the data at the moment they
ask, **no conclusion outlives the run that computed it**, and removing the realm removes the label —
there is no derived data to migrate or delete.

That guarantee is about what survives, not about what is never written. Under the transient
execution model the evaluator's writes happen inside a transaction that is rolled back, so they
never land. Under the **committed** model they do land, on real nodes, and end-of-run cleanup
reverses exactly them — recorded as they are applied, and journalled durably, so a run that dies
before reaching its own cleanup is still reversed rather than leaving stamped labels behind. An
author sees the same conclusions either way; an operator should know which model is in force,
because only one of them has a crash window to reason about.

Every
membership records its **firing chain** — which rule concluded it, in which round, with which
values, and how values grew as membership grew. That trace is the mechanical object an
explanation renders rather than reconstructs: "blocked because A (30%) and B (25%) together hold
55%" is read off the chain, not inferred after the fact. Rule bodies pass the same per-user
scoping as every query, so a rule can never read what its author's own query could not.

### 13.4 Derived relationships — an edge whose existence is a conclusion

A head may be a **relationship pattern**; the rule set then defines a derived relationship type,
named by `derives:` exactly as a label would be:

```yaml
# rules/shared-failures.yml
name: gov-uk/shared-failures
derives: SHARES_FAILURES
description: >-
  Two officers are related when the register shows both appointed at two or more of the same
  now-dissolved companies; `failures` counts the companies they share.
rules:
  - derive: "(a)-[:SHARES_FAILURES {failures: n}]->(b)"
    from: |
      MATCH (a:Officer)-[:APPOINTED_AT]->(c:Company {status: 'dissolved'})<-[:APPOINTED_AT]-(b:Officer)
      WHERE a.officerId < b.officerId
      WITH a, b, count(DISTINCT c.companyNumber) AS n
      WHERE n >= 2
```

The head's shape is validated the way a node head's is, and each restriction is a leg of the
same guarantee:

- **Exactly one relationship, directed.** `(a)<-[:T]-(b)` is accepted and normalised by swapping
  the endpoints; an undirected head is refused — a derived edge has to be written in one
  direction.
- **Endpoints are two bare, DISTINCT variables the body binds.** A label on an endpoint is
  refused: the body binds the variables, so a label there constrains nothing. A head naming the
  same variable twice is refused.
- **Membership is the ordered pair**, and a later round that re-concludes a pair UPDATES its
  properties rather than laying a parallel edge — the second clause of a recursive set settles
  values exactly as a derived label's properties settle.
- **One set concludes one kind.** Label rules and relationship rules are different fixpoints;
  mixing them in one set is refused (they remain free to reference each other across sets — a
  label rule may match a derived relationship, and vice versa).

Once concluded, the edge is ordinary: a later rule recurses over it, a query traverses it, and
the schema declares the relationship — with the endpoint kinds its bodies bind — before a single
pair exists, exactly as a derived label is declared before a single member is.

**`maxPairs` is the budget that node sets never needed.** Node membership is bounded by the node
count, and the fragment's own argument terminates it. Pair membership is bounded by the square of
the node count, so an under-constrained body is quadratic in time and in transient writes long
before `maxRounds` would notice. Exceeding `maxPairs` (default 250 000) fails loudly rather than
returning a truncated relation — a cross join is the first mistake an edge rule's author makes,
and a loud refusal is the correction; a silent truncation would be a wrong answer wearing a right
one's shape. The setting is ignored by a set that derives a label.

**A derived relationship is not transitive closure.** A path already in the graph needs no rule —
`*1..n` traverses it. Derive an edge when its *existence is a conclusion* no traversal states:
two officers related because they share two or more failed companies; a supplier `EXPOSED_TO` a
sanctioned party once the aggregated stake crosses a threshold. If the rule's body is nothing but
a path over existing edges with no aggregation, threshold, or judgment, write the path in the
query instead.

### 13.5 Guidance

- **Ship the projection view with the rule set.** Referencing the derived label is what triggers
  evaluation, so a small view (`MATCH (p:PhoenixSuccessor) WHERE p.phoenixDepth >= $minDepth
  RETURN …`) is how the label reaches every surface — the console, apps, the SQL door — with no
  client work. realm-gov-uk's `views/phoenix-succession.yml` is the model.
- **A distance belongs in the projection view, not in the fixpoint.** Chain length, depth and
  shortest route are what authors most often reach for as derived properties, and on cyclic data a
  property that recurses through its own value does not settle (§13.2). Conclude membership in the
  rule set; measure in the view — `MATCH p = (c:Exposed)-[:DEPENDS_ON*1..10]->(v) … min(length(p))`
  is bounded whatever the data does.
- **Rules conclude over data present in the graph** — see §13.6, which is the single most important
  thing to understand before writing a rule set over producer-backed types. Say the data contract in
  the rule-set description either way.
- **If the conclusion is plain reachability, use `*1..n` and not a rule.** A path that already
  exists in the graph needs no fixpoint: the traversal is cheaper, and it reports its own truncation
  (`INCOMPLETE_TRAVERSAL`, naming the hop it reached) where a rule set would simply answer. A rule
  earns its keep when the conclusion is NOT reachability — aggregation inside the recursion, a
  quorum ("cited by three already-influential papers"), a threshold, or a judgement propagated
  along a path.
- Derived labels participate in visibility/tenancy like any label a query names.
- Name derived properties from the head and prefix them for the realm (`phoenixDepth`, not
  `depth`) — the label's vocabulary outlives the file it was declared in.

### 13.6 What a rule set may assume about its facts

**A rule body reads what is already in the graph. It cannot fetch.**

That one sentence decides whether a rule set is sound, and it is the difference between a rule that
answers and a rule that answers *understatedly*. Three situations, and only the third needs work:

| Your facts | Complete? | What to do |
|---|---|---|
| Stored, seeded, promoted, or a materialized view | yes | nothing — write the rules |
| A producer returning a whole record per anchor | yes | nothing — one fetch is the entire fact set for that anchor |
| Gathered by WALKING — each hop is another fetch | not by default | declare `requires:` |

The second case is the common producer shape and it is why most rule sets need no thought here: one
call to a company register returns an officer's *entire* appointment history, so a rule about that
officer's appointments has everything.

The third case is a dependency tree, a citation graph, an ownership chain — anything where reaching
depth 3 means three rounds of fetching. Without a declared demand, such a rule set concludes over
whatever prefix the *consumer's query* happened to materialize, which its author never sees.

**Declare what you need:**

```yaml
name: npm/reaches-unmaintained
derives: ReachesUnmaintained
requires:
  - materialize: "MATCH (r:Release)-[:HAS_DEPENDENCY*1..$depth]->(:Dependency) RETURN 1"
    description: "The dependency tree has to exist before 'reaches' means anything."
params:
  depth: { type: int, default: 3 }
rules:
  - derive: "(d:ReachesUnmaintained)"
    from: |
      MATCH (d:Dependency)-[:HAS_HEALTH]->(h:ProjectHealth) WHERE h.overallScore < 5
```

A demand is ordinary read-only Cypher, validated like a rule body. It runs **before** any rule
evaluates, in the same transaction, and **after** the consumer's query has materialized its own
anchors — so it DEEPENS what is already there rather than re-anchoring it. It may reference the rule
set's declared params, so depth is tunable per invocation with a default you choose.

**When the facts are incomplete anyway, the engine says so.** A rule set that evaluates while any
fetch was capped, refused, truncated or left a demand unmet reports `PARTIAL_RESULT` and states that
its membership — and any count or total over it — is a **lower bound**, naming the unmet demand
where there is one. Report it to your reader as a lower bound; never present a derived count as a
total. This is not a failure and not "nothing was derived".

**The rule of thumb:** make the fact set complete, and prefer making it complete *cheaply*. Loading
the data (a local table, a promoted watchlist) beats demanding a deep walk, and a demand beats
hoping the consumer's query walked far enough.

### 13.7 What a rule set costs — quoted before it runs

Derivation spends **graph work**: rounds of your rule bodies, and a fact written for every row a
body binds. That is a different currency from the model calls a producer spends, and it is priced
separately.

Before any rule evaluates, the engine counts what each body binds — one `count(*)` over the body
itself, so nothing is materialized and nothing is written. Past the deployment's budget the query is
**refused** with the count, the budget, and which rule accounts for it:

```
TOO_EXPENSIVE: deriving :CO_LOCATED would bind at least 249500 row(s) on the first
round alone (gate: 50000). Rule 1 of 'probe/cartesian' accounts for 249500 of them —
an under-constrained body is quadratic in the nodes it binds, so narrow it (anchor one
side, add a filter) or raise the rule set's own limits deliberately if the estate is
genuinely that dense.
```

Almost always this means a relationship body that forgot to constrain one side. `MATCH (a:Peer),
(b:Peer)` binds every peer against every other; anchoring one side to the other through a real
relationship, or filtering it, is the fix.

**Expensive is not the same as forbidden.** Asked through a surface that supports it, an
over-budget query is *parked* rather than refused outright, and you are offered the same four
choices any expensive query gets: proceed, narrow it first, **run it in the background** and collect
the result later, or cancel. A derivation that genuinely is that large is a scheduling question, and
answering "background" is the normal answer to it. What the engine will not do is spend the time
without asking.

The count is a **lower bound**, and deliberately so. A recursive rule reads a label that has no
members on the first round, so a transitive closure is under-counted while an unanchored quadratic
body is counted exactly — the engine can let expensive work through, but it can never refuse cheap
work on a guess.

Two ceilings sit underneath as backstops, and you should never meet them:

| Ceiling | Default | What it means |
| --- | --- | --- |
| `maxPairs` | 250,000 | A relationship set derived more pairs than this. Bounds what reaches the graph; it is checked after a round has bound its rows, so treat it as a last resort rather than a budget. |
| `maxRounds` | 1,000 | The fixpoint did not settle. The message names what was still moving: a derived property climbing (§13.2), or simply an estate deeper than the cap. |

Both fail loudly. Neither truncates: you will never receive a derivation that quietly stopped early.

---

## 14. The contract, in one line

> **Bind a real anchor; declare how a label is fetched; the engine probes, fetches once per
> producer, materializes transiently, runs your Cypher over real + virtual together, and rolls
> back.** Persistence is the exception (warm-cached identity bridges), not the rule.

For the declarative surface (`virtualJoins:`, `producers/`, `resolve:`, `pushdown:`, `paging:`,
`brings:`, `cache:`, `views:`) see [`README.md`](./README.md#joining-types-on-demand-virtual-joins-not-mirrored).
Views (regular / materialized, output typing, the pluggable cache, persisted scopes, and hydrating a
scope into typed instances) are §8.

---

## 15. Scope — per-user accessibility, per-world focus

An earlier draft of this section read the reference host's scope handling as a defect against §2.
It is not. It is the intended model, and §2 overstated it; this section states what scope actually
guarantees so that no one else has to reverse-engineer the answer from a scope predicate.

### 15.1 The model

**Accessibility is per user. Focus is per world.**

A principal reaches their own data. A world does not fence one part of it off from another part of
the same principal's; a world selects WHICH CAPABILITIES EXIST — the types, realms, producers,
views, skills and actions installed in it. That is a real boundary and it is enforced by
construction rather than by predicate: a label whose realm is not installed in a world cannot be
named in a query there, has no producer to fetch it, and appears in no view.

So two worlds of one principal differ in what they can DO, not in what the principal may see. A
canonical spine that both worlds' realms declare is the same spine, which is the point of a spine.

**Between principals, the boundary is absolute.** A node is in scope when it carries the acting
principal's id, or names them in its share projection. That is the isolation a shared store depends
on, and it is the claim worth testing.

### 15.2 What this means when you are deciding something

- **Designing a realm:** a world is a capability surface. If two worlds should see different DATA of
  one owner, that difference has to come from what each realm exposes, not from a hope that the
  world boundary will filter it.
- **Reading a cache:** fetched records are reused per principal, which is consistent with the above
  — the same principal asking the same source the same question. It is not a leak across a
  confidentiality boundary, because between worlds of one principal there is no such boundary.
- **Making a deployment claim:** "isolated per user" is supported. "Worlds are mutually
  confidential" is not, and is not intended to be.

### 15.3 What a fetch is keyed by, which is easy to assume wrongly

Within a scope, a fetch is keyed by everything that changes the result set — the producer, the
resolved key, the pushed-down filter, any steer or tuning, and the limit and demand in force. A read
taken under a cap therefore never serves one taken without. This is what lets a warm-up in one
request populate the cache for another without a truncated answer being served as a complete one.

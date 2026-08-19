# Virtual Cypher — Specification

**Spec version: 0.2.0**

> **Status: normative.** This document defines what a Virtual Cypher query means, what it
> guarantees, and what it refuses. It states OBSERVABLE behaviour only — never how the engine is
> built. Where an implementation and this document disagree, this document is the defect report.
> The 0.2 world/principal separation and world-keyed cache/canonical guarantees are forward-looking
> host requirements. Current Me is not conformant. Multi-world or shared-store isolation is not a
> valid deployment claim until the corresponding release gates pass.
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
context without an explicit policy-authorized bridge, and cannot reach another world at all,
including one owned by the same user. Local single-user deployments use the same path and an explicit
default context. `userId` is never accepted as an alias for either scope.

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
| A producer returns a child type/edge the join didn't declare in `brings:` | **Undeclared brought child** — fail loud, so a source-shape change can't silently inject unmodelled nodes. |
| `UNION`, `CALL { }` subqueries in a scoped query | Not scoped clause-by-clause by the rewriter → rejected (restructure as separate queries). |
| Anything the Cypher parser can't parse | **Fail closed** — an unparseable query is rejected, never run unscoped. |

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

### 5.2 Identity bridges — `resolve:` chains

A bridge links a canonical `Person`/`Organization` to an external identity for **any** person/org,
not just the connecting user, via an **ordered rule chain** (first match wins), resolved **lazily**
at query time for the anchors a query actually binds, and **persisted** (`writeThrough`) so it is
reused — re-resolved only after `refreshAfter`.

| rule | how it resolves |
|---|---|
| `existingBridge` | A fresh bridge already linked to the anchor — use it, stop. |
| `learnedHandle: { property, as }` | An explicit handle stored on the anchor (e.g. `Person.githubLogin`). No lookup. |
| `canonicalEmail: { producer }` | The anchor's canonical email set → call the producer. |
| `canonicalDomain: { producer }` | An organization's canonical domains → call the producer. |

Resolution is **batched** (one producer call for many anchors) and **negatively cached** (an anchor
that resolved to nothing is not re-queried until `refreshAfter`), so a recurring "who that I email
is on GitHub" doesn't re-storm the source.

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
`cache:` policy (`none` / `ttl` / `session` / `immutable`, plus `graph` for aggregates and
extraction — §5.5/§5.6, where the committed graph itself is the cache tier).

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
pipeline). A property tagged `identity: true` is the merge key; a property tagged
`relationship/target/matchBy` links the record to a spine:

```yaml
- name: HubSpotContact
  properties:
    email:    { metadata: { identity: "true" } }          # → Person, by email
    company:  { metadata: { relationship: WORKS_FOR, target: Organization, matchBy: name } }
```

The `relationship`'s **merge key is the spine's key, not the field text** — `company`'s value is
only the display name; the `Organization` is keyed by the contact's email **domain**. So two contacts
on `@acme.com` share one `Organization` however they spelled "Acme", and a freemail/no-domain contact
yields **no** `Organization` (a name alone never invents a spine — fuzzy name resolution is a
separate, async, confidence-scored layer, never in the query path). The result is a durable
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
and Organization are just the two built-ins. Add a `Place`, `Repository`, or `Product` spine in
`application.yml` and source types join it by tagging a property `target: <newLabel>` — the engine
builds the hub, applies the key-node uniqueness constraint at boot, and the join surface above works
unchanged.

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
    fileCacheSeconds: 21600
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
target type's identity property; one that doesn't is DROPPED — silently, because a register with no
usable id then produces nothing at all while every fetch log says it matched. Many published
registers have no per-row id (the NDIS compliance CSV's Provider Number is blank on 98% of rows).
`rowIdAs: recordKey` stamps a deterministic `<normalized key>:<ordinal>` id, and the type declares
that property as its identity. It is honest about what it is: a ROW POSITION within one file
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

**The `governance:` grammar** — shared by every source of this family (a remote SQL database
navigated as a graph is next), one vocabulary regardless of what sits behind the source:

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

**A join may declare a POLICY instead of one key.** `keyField` says "match this column"; a policy
says how to try, in order, and what to do when the rules disagree:

```yaml
- anchorLabel: Order
  relationship: PLACED_BY
  keyField: id
  producer: customersById
  policy:
    rules:
      - key: { on: customer_id, to: id }                          # the declared key
      - key: { on: customer_email, to: email, ci: true, confidence: medium }
      - ask: "Which customer placed this order?"                  # a person, when rules disagree
      - none                                                      # no link is a legitimate answer
```

Guarantees:

- **Rules are tried IN ORDER and the first that yields wins.** A rule that yields nothing does not
  end the chain — that is what a fallback is for.
- **More than one match is not a match.** The rows become the candidates offered to a later `ask`,
  and resolution continues rather than picking one.
- **`ask` never runs before the rules that could answer without a person**, and where nobody can be
  asked — a scheduled run, an expired question — the chain falls through to the next rule rather
  than blocking.
- **Every resolved edge records HOW it was found**: the rule that matched and that rule's
  `confidence`, with an `ask` answer recorded as `asserted` — a person's word, not a probability.
- **`none` ends the chain with no link**, which is an answer and not a failure.
- A join with no `policy:` behaves exactly as before: key on `keyField`, once.

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
  judge relevance from the score, rather than a hard cutoff that silently drops everything.

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
before judging. They **fail open**: an LLM error scores the affected rows 1.0 (kept, neutral rank), so a
hiccup never silently *hides* results — it degrades to "no judgment applied", visible and safe. Reach for
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
| `size(trim(coalesce(r.description,''))) <= 60` | **no** — see below: a length is not the property's value |
| `r.description CONTAINS 'lease'` | yes |
| `r.description IS NOT NULL` | **no** |
| `toLower(r.description) = toLower(r.title)` | **no** — compares two properties, not a value |
| a condition on a *different* node | **no** |
| `r.amount >= $threshold` **in a view** | yes — a view's declared params become literals before the query is read |
| `r.amount >= $threshold` **with caller-bound params** | **no** — the value is not known when the query is read |

**A wrapper that CHANGES the compared quantity cannot gate.** `toFloat(r.amount) >= 5` still compares
the amount, so it gates. `size(r.description) <= 60` compares a LENGTH, and the engine has only the
property to offer a source — so the condition is honoured in full, but after the judgment rather than
before it. The rows are right; the bill is the same as if the gate were absent. `length`, `count` and
`toString` behave the same way.

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

- The value is computed BEFORE the query runs, so a query that filters on an aggregation pays for it
  whether or not the filter keeps anything. Narrow the rows FIRST — a `WHERE` before the aggregating
  `WITH` — and only groups that survive are computed. A query whose filter would need more than a few
  hundred model calls is REFUSED with the count, rather than sampled quietly.
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

`confidence`, `fresh` and `materialize` are EDGE keys (a generative floor, a producer's cache) and an
aggregation has neither, so they are rejected here rather than accepted and ignored. A prose key on a
non-prose function, an unknown key, and a `{realm: {…}}` map are all rejected the same way: warned
about, never silently inert. Because a map is a value the map cannot be confused with an instruction —
`summarize(n.body, {ai: {voice:'noir'}})` steers, it does not summarize toward the word "noir".

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
  fun freshUntil(view: String, worldId: String, contextId: String, accessPolicyRevision: String, principalId: String?): Long?
  fun materialize(view: String, worldId: String, contextId: String, accessPolicyRevision: String, principalId: String?, memberIds: List<NodeId>, expiresAt: Long)
  fun members(view: String, worldId: String, contextId: String, accessPolicyRevision: String, principalId: String?): List<NodeId>
  fun clear(view: String, worldId: String, contextId: String, accessPolicyRevision: String, principalId: String?)
  fun sweepExpired()
}
```

`principalId` is required when the view body uses principal-specific credentials, policy, inputs, a
principal anchor, or any producer not proven principal-invariant. It may be `null` only when the
planner verifies that the entire view is principal-invariant. A view that cannot prove either mode is
rejected rather than cached at context scope.

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
  nothing) is cached too, so a fan-out doesn't re-probe a dead key every query. This exists today ad-hoc as
  the bridge negative-cache (`_bridgeMissAtMs` per target); the SPI unifies it with a TTL and
  **invalidate-on-reconnect**.
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

**Cost (per producer):** a `cost:` block declares the source's shared **rate bucket** and limit.
The planner budgets producer calls against it and, when a query can't fit, emits `EXPLAIN`-style
**advice** (push a predicate, add a `LIMIT`, narrow the anchor) rather than silently over-calling.

**Diagnostics — what a 0-row or partial result *means*:** a fetch that returns nothing is
indistinguishable from "genuinely no data" unless the engine says otherwise. Every producer failure
is classified and surfaced as a warning on the result:

| diagnostic | when | meaning |
|---|---|---|
| `PRODUCER_ERROR` (`FETCH_FAILURE`) | a timeout, a missing gateway tool, a non-auth error | the source could **not** be reached — *not* "no data". Fix the integration. |
| `PRODUCER_ERROR` (`AUTH_EXPIRED`) | a 401 / "token expired" / `EXPIRED_AUTHENTICATION` | the OAuth token has **expired** — reconnect to refresh. The empty result is because the source rejected the call. |
| `PARTIAL_RESULT` (`TRUNCATED`) | pagination hit `maxPages` with a still-full last page | the fetch **succeeded but is incomplete** — the source has more. Narrow the query or raise the cap. *Not* a failure. |
| `PARTIAL_RESULT` (`TIME_BUDGET`) | the query's time budget expired mid-materialization | the fetch **stopped early at a safe boundary** — the rows returned are real and complete in themselves; the remainder was not attempted. Work already done is kept, so asking again continues rather than starting over. *Not* a failure. |
| `INCOMPLETE_TRAVERSAL` | a variable-length traversal (§5.12) stopped short of its declared depth | the warning names the hop reached and the bound hit (`maxFanoutTotal`, frontier width, or the unbounded-`*` cap). Rows cover only the hops walked; any subtree total is a **lower bound**. |
| `UNKNOWN_VIA` | an edge pinned `{via:'…'}` that no declared join offers | the rows are **real but came from a different join** than the one named. The query still answers — a via that does not exist must not cost a good answer — and the warning lists the vias that do exist so it can be re-issued. Matters most where several joins converge on one label, since the substitution is otherwise invisible. |

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
  never read another context without an explicit authorized bridge and never another world's
  private data; deployment-approved, revisioned `Public`/reference datasets are the explicit
  exception. An unparseable or unscopable query is rejected, not run.
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

## 13. The contract, in one line

> **Bind a real anchor; declare how a label is fetched; the engine probes, fetches once per
> producer, materializes transiently, runs your Cypher over real + virtual together, and rolls
> back.** Persistence is the exception (warm-cached identity bridges), not the rule.

For the declarative surface (`virtualJoins:`, `producers/`, `resolve:`, `pushdown:`, `paging:`,
`brings:`, `cache:`, `views:`) see [`README.md`](./README.md#joining-types-on-demand-virtual-joins-not-mirrored).
Views (regular / materialized, output typing, the pluggable cache, persisted scopes, and hydrating a
scope into typed instances) are §8.

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

A normal knowledge-graph query reads nodes and edges that are **persisted** in the graph. Virtual
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

**A Virtual Cypher query never writes.** On every surface that takes a query — asks, views, rule
bodies, code, captured-realm reads — a write clause anywhere in it (`CREATE`, `MERGE`, `SET`, `REMOVE`,
`DELETE`, `FOREACH`, `CALL { } IN TRANSACTIONS`, including after a `WITH`) refuses the query before
anything is fetched or run, naming the clause; a write clause that appears only inside a string,
comment or map key is data and the query runs. A realm persists changes only through its write
proposals, never by writing from a query — so nothing a query read from a live source is ever
stored by that query. The one surface that writes is the annotation surface (§12): a realm and a
deployment must both opt into it, it takes its own fixed statement shape, and it writes only
declared annotation properties of REAL nodes — never a fetched record.

Every Virtual Cypher query runs the same five conceptual phases, and **nothing it materializes
outlives the run**:

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

   **The probe binds what it can name, and a position it cannot name only widens it.** The probe
   binds the anchors it must project and the labelled nodes that constrain them. A position whose
   label it cannot name — the endpoint of a pattern predicate you left unnamed,
   `WHERE (s)-[:SUPPLIES]->()`, in any direction, negated, pinned by a property, or over a
   variable-length hop — is
   dropped from the prefix, with its relationship and any condition on it, exactly as a position
   only an `OPTIONAL MATCH` or a `NOT EXISTS` reaches is: a label-free `MATCH (x)` is a scan of the
   whole graph, and a scan is not a constraint. So such a filter lowers no fetch's cost — every
   anchor the rest of the query binds is fetched for — and your own `WHERE` still decides the
   answer, which is the same answer as over the same records stored. **A query is never refused
   over a position the probe chose to bind.** A node YOU bind with no label is unscopable (§11),
   as it always was; a node only a pattern predicate reaches is yours to leave unnamed.

   **An equality on a number or a boolean keeps every anchor it matches, whatever spelling holds
   the value.** `n.rating = 10` keeps a node that stores the number 10 and one that stores the text
   `'10'`; `f.isStatic = true` keeps a node that stores the boolean `true` and one that stores the
   text `'true'`. This holds for an anchor an earlier hop of the same query fetched as much as for a
   stored one, so a filter on a fetched node never empties the hop that follows it. The probe can
   only widen here, never drop: your own `WHERE` still decides the answer. Only the exact words
   `true` and `false` are read as booleans; `'True'` or `'yes'` stays text.

2. **Fetch.** For each virtual join the engine calls its **producer** *once* with the **union of
   all anchor keys** — never one call per anchor (no N+1). The producer is the source-specific
   fetcher (a REST op, a SQL query, a vector search, an in-process computation).

3. **Materialize.** Each returned record becomes a transient node carrying the extra `:Virtual`
   label, a `dateRetrieved` timestamp, and the host-bound `worldId`, `contextId`, and access-policy
   revision. The engine links it to the anchor it was fetched for (`keyField == recordKeyField`). A
   record may also carry its own **sub-graph** (`brings:`), materialized in the same pass.

   **A fetched node shows a query only what the same record would show stored.** The `:Virtual`
   label and the run's stamps are the engine's bookkeeping, and introspection leaves them out:
   `labels(n)`, `keys(n)`, `properties(n)`, `n {.*}` and a returned node or relationship answer as
   they would over the stored record, so `size(labels(n))`, `labels(n)[0]` and `'Virtual' IN
   labels(n)` are right. A query that names the bookkeeping explicitly — `n:Virtual`, or a property
   under the engine's reserved `__vc` prefix — still reads it. Both names are reserved to the
   engine, so hiding them never hides the caller's data.

   **A fetched record never sets the node's scope.** On every fetched node and brought child,
   `userId`, `worldId`, `workspaceId` and `visibleTo` are the scope the world stamps, never the
   record's own fields, so no source can hand a node to whichever user it names. A record's own
   field of one of those names is readable under its alias: `userId` as `_sourceUserId`, `worldId`
   as `_sourceWorldId`, `workspaceId` as `_sourceWorkspaceId`, and `visibleTo` as
   `_sourceVisibleTo`. The schema the generator is shown names them that way. A mirrored source's
   persisted nodes store a record's `userId` under the same name. A type keeps declaring the
   source's own field name, `userId`. A filter written on an alias reaches the source as the field
   it stands for: a `pushdown:` rule keeps naming the source field (`property: userId`), and a
   record screened before materialization is judged by that field. A record field under the
   engine's reserved `__vc` prefix is dropped: those names say which run may see a node, and a
   record does not choose its own visibility.

   A fetched type or brought child keyed by any of the four scope fields — the key would sit on a
   property the record never fills — or one that declares a scope field and also declares or keys
   on its alias, is a load problem against the declaring realm. Queries over such a realm still
   run, and the record's own field is what its alias holds. A type keyed by `userId` is identified
   by `_sourceUserId`: records with the same source `userId` are one node, however often they are
   fetched, and a pin on `_sourceUserId` finds it.

4. **Run.** Your full query now runs over the combined graph. `WHERE`, `ORDER BY`, `RETURN`,
   aggregates — all of Cypher — apply to virtual nodes exactly as to real ones. That includes
   Unicode normalization: `normalize(s[, NFC|NFD|NFKC|NFKD])` and `s IS [NOT] [form] NORMALIZED`
   answer over fetched records as over the same records stored, NFC when no form is written.

5. **Roll back.** The virtual nodes vanish. A re-run re-fetches (cheap, because of caching).
   Nothing is ever persisted by a read query.

   How they vanish is the deployment's execution model, and a query cannot tell which is in force.
   Under the **transient** model the run's transaction is rolled back. Under the **committed** model
   the materialized nodes are written, stamped with the run, and removed when it ends (§13.3).
   Overlapping runs that fetched the same record each keep seeing it for as long as they run, and
   each returns what it would return alone.

   *The one exception:* an identity **bridge** (`writeThrough`) is committed as a warm cache and
   re-resolved after `refreshAfter` (§5.2).

### Evidence when a lookup returns no matching rows

A fetched record is not the same thing as a matching query row. A producer may return records
that a query's predicate or join does not reach; an empty answer in that case does **not** prove
those records are absent. The result distinguishes records returned by producers before query-side
filtering, nodes made available to the query, and rows matched by the query. Cache-served records
count as fetched for that execution; a source that genuinely returns zero records does not.

When a query about one identity-pinned record matches nothing, a result may include a record
card with already-fetched fields and up to 20 rows per related section. The card is
**supporting context only**: it does not answer the original filter, prove omitted or truncated
related sections complete, or fetch additional sources. Its result identifies the Cypher that
produced the card and marks the answer partial.
An incomplete-source warning remains visible even if the card supplies useful context.

These distinctions appear in the result envelope next to `rows` and `warnings`. Each field below is omitted when it does not apply; presence can differ by surface, as noted.

| Field | Type | Present | Meaning |
|---|---|---|---|
| `fetchedRecords` | integer | on query, ask and saved-view results (the admin REST endpoints omit a zero) | Records the producers returned before query-side filtering, cache-served ones included. |
| `materializedNodes` | integer | on query, ask and saved-view results (the admin REST endpoints omit a zero) | Graph nodes made available to the query from those records. |
| `reason` | string | on query, ask, saved-view and admin REST results, only when the result is not a clean answer; absent on a clean answer, including a genuine zero | Why there is no clean answer, as a code a caller can branch on. The evidence codes are `FETCHED_NOT_MATCHED` (records were fetched and none matched), `PARTIAL_NOT_MATCHED` (an incomplete read matched nothing and no step failed) and `UNPUSHED_FILTER` (a bounded read omitted a declared filter); other codes report refusals and failures. Any of them means an empty result does not prove absence. |
| `incomplete` | string | on query, ask and saved-view results, only when the read was incomplete; the admin REST endpoints omit it | One line, such as `Incomplete: based on the first 100 rows, more exist`, that qualifies every row and figure in the result. |
| `answerBoundary` | object `{kind, unresolvedQuestion?}` | only on a non-empty record card | `kind: SUPPORTING_CONTEXT_ONLY`: the rows support the lookup but do not answer its original filter. `unresolvedQuestion` restates what is still unanswered. |
| `cypher` | string | an ask result (`kg_ask`): on an empty result, a requested explanation, or a record card. A saved-view result: only on a requested explanation. A direct query (`kg_query`) never echoes it, since the caller wrote it. The admin REST query endpoints always include it. | The executed query, when present. |

```json
{ "rows": [], "warnings": [], "fetchedRecords": 12, "materializedNodes": 12,
  "reason": "FETCHED_NOT_MATCHED", "cypher": "MATCH (e:Event) WHERE e.status = 'open' RETURN e" }
```

Twelve records arrived and none matched. The answer is "no fetched record matched", not "no such records exist".

### Two concepts the rest of the spec leans on

**Bound anchor.** A virtual label may only be reached by **traversing a declared join from a
*bound* anchor** — a node the engine can resolve to a finite set. An anchor is bound when it is:

- pinned by an inline literal — `(p:Person {primaryEmail:'a@b.com'})`, or
- pinned by a `WHERE` equality — `WHERE p.primaryEmail = 'a@b.com'`, or
- narrowed by **any** property predicate — `WHERE toLower(p.name) CONTAINS 'grace'`, or
- the acting human principal — `(me:AssistantUser)` (the scope rewriter resolves the node linked to
  `principalId`; a service principal has no implicit `me` anchor), or
- reachable over a *required* edge from another bound node.

A number pinned on an anchor key also matches the key's text form. `(q:EventQuery {eventId: 2779})`
and `WHERE q.eventId = 2779` find an anchor keyed `2779` or `'2779'`, whether it is a stored node or
one the engine created for the fetch; the quoted `{eventId: '2779'}` matches only the text key. Each
number in a key list does the same: `WHERE q.eventId IN [2779, 2780]` finds anchors keyed `2779` or
`'2779'` and `2780` or `'2780'`, while a quoted list matches only text keys. This applies only to
the key a join fetches by; every other property compares exactly, so `{age: 40}` does not match
`'40'`.

A naked `MATCH (hc:HubSpotContact)` — no anchor — is **rejected** (§4). This is what stops Virtual
Cypher from trying to fetch *every* contact in HubSpot.

**A declared everyone-door is taken implicitly.** A realm may declare a door whose identity has a
default — `scope: { metadata: { identity: "true", default: "all" } }` — meaning "the whole
population". When exactly one of a label's joins runs from such a door and is keyed on that
identity property, a bare `MATCH (i:Invoice)` is planned as if
`(:Books {scope:'all'})-[:HAS_INVOICE]->(i:Invoice)` had been written, and returns the same rows.
The rule is not loosened: declaring the door is the realm's opt-in, the same declaration that
already seeds `(:Books)` when the door is written without a pin. Predicates on the bare node are
pushed to the source exactly as they are through the written door. A label with no such door is
rejected as above, and so is a label with two or more, since "everyone" would then name more than
one population; the rejection names each door. A node pinned on a key a join declares as
`materializedKeyField` is still found by that key, not by listing everyone.

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
| `MATCH (hc:HubSpotContact) RETURN hc` | **Naked virtual scan** — no anchor to probe. Virtual labels are reached only by traversing a declared join from a bound anchor; otherwise the engine would try to fetch *every* contact. The one exception is a label with exactly one declared everyone-door (§2), which the engine takes for it. |
| `MATCH (p:Person)-[:HAS_HUBSPOT_CONTACT]->(hc)` with no predicate on `p` | **Unbound anchor** — `p` matches every person; the fan-out is unbounded. Pin or filter the anchor. |
| `MATCH (i:Item)-[:MENTIONS]->(t:Tag)` where `Tag` is brought only via `TAGGED` | **Brought child off its declared edge** — a brought label is reachable only through the exact relationship its own `brings:` entry names, and only from the join whose target brought it. |
| ``MATCH (`a b`:Repo)``, ``MATCH (`distinct`:Repo)`` | **A variable that needs backticks** — variables are plain names. Refused by name with the rename to use, never as a syntax error the caller did not make. A word that reads back bare (`count`, `match`, `all`) is a legal name; column aliases and property keys may be quoted as usual. |
| `COUNT { MATCH (s:Bill) RETURN s UNION MATCH (s:Meeting) RETURN s }` | **Two `UNION` branches inside a subquery binding the same new name** — inside a `CALL { }`, `COUNT { }`, `EXISTS { }` or `COLLECT { }` body the branches share one scope, so a name bound afresh in two of them would be one variable read two ways. Refused naming it, with the rename that answers: `MATCH (s:Bill) RETURN s AS item UNION MATCH (s2:Meeting) RETURN s2 AS item`. A name may be shared across branches when it is imported or bound before the subquery, or when it is the returned column written as an alias (`RETURN t AS s`) in every branch but at most one. A statement-level `UNION` has no such limit: its branches are independent queries. |
| `MATCH (s:Shop) CALL { MATCH (s)-[:TAGGED]->(t) RETURN t.tag AS tag } RETURN tag` | **A `CALL { }` body sharing a name with the statement around it without the two being one variable** — an outer name the body does not import (including under `CALL ()`), or a name the body binds and does not return that the outer query uses again after it. The body's `s` would be a second, unbound variable read as the caller's. Refused naming it, with the import (`CALL (s) { … }`) or the rename (`s2`) that answers. `CALL (*)` is refused with the explicit import list the body needs. `OPTIONAL CALL` is refused as a form this engine cannot read. Every other read-only `CALL { }` is answered on every engine, its body scoped like the statement around it — uncorrelated, side by side, nested, importing (`CALL (s) { … }` or a leading `WITH s`), returning rows or an aggregate, or feeding a hop outside it; a fetched hop inside a body is fetched for the rows that reach it. |
| `MATCH (n) RETURN n.name`, or a node left unnamed: `MATCH (p:Person)-[:ABOUT]->()` | **Unscopable node** — a node is reached by the labels it names, so one that names none cannot be held to the asking principal. The lever is per node: a named node is told to take a label; a node the query left unnamed is told to take a name AND a label, because a label alone on `(:Label)` leaves nothing for the scope to be attached to and is refused in turn. |
| Anything the Cypher parser can't parse | **Fail closed** — an unparseable query is rejected, never run unscoped. |
| `MATCH (n:!Topic)`, `n IS !Topic`, `WHERE n:!Person` | **Single-label negation** — refused before it runs, naming the spellings that work: `WHERE NOT n:Topic`, or a combined label expression such as `:Topic&!Person`. A `!` inside a string or comment is data. |
| `RETURN apoc.text.capitalize(p.name)`, `CALL db.labels()` | **A procedure or function library this engine does not provide** — refused as an unknown function, naming it, not as a write. The refusal points at the built-in functions to use instead, and for schema questions at the schema the query guide shows. |
| `MATCH (p)-[:AUTHORED]->(r) WHERE count(r) > 1 RETURN p.name` | **Aggregate in `WHERE`** — refused before anything is fetched: compute it in a `WITH` and filter on its alias, `WITH p, count(r) AS n WHERE n > 1`. An aggregate inside a subquery's own `WITH`/`RETURN`, and a `COUNT { }` subquery in `WHERE`, run. |
| `RETURN p.name AS passage, count(v) AS n ORDER BY n DESC, b.bookOrder` | **A variable the projection dropped** — after a `WITH` or `RETURN` that aggregates or is `DISTINCT`, `ORDER BY` may use only a projected alias or repeat a projected expression. Refused before any fetch, naming every out-of-scope variable at once. A realm view with this shape fails `realm_validate`; one already installed is reported against its realm at load, stays listed, and is refused with the defect named when called. |
| `x IS :: LIST<INTEGER>`, `x IS :: INTEGER \| STRING`, `x IS NOT :: INTEGER` | **A type predicate this surface cannot read faithfully** — refused for what it is, quoting the type as written, with the rewrite to use; never reported as a syntax error. A plain `x IS :: INTEGER` (or `IS :: INTEGER NOT NULL`) runs on every surface, and a missing value is of every nullable type. |
| `… WITH x MATCH (t:Tag {k: 2}) …` where `t` was bound before the `WITH` dropped it | **A dropped name re-bound with its own labels or properties, on a surface that cannot keep the two apart** — refused with the rename to use (`(t2:Tag {…})`), rather than letting the second node match any node the caller can see. |
| `MATCH ((a:Person)-[:KNOWS]->(b:Person)){1,3}`, `-[:KNOWS]->{1,3}` | **A quantified path pattern or quantified relationship** over the caller's own nodes, over a fetched label, or under a shortest-path selector — a repeated node cannot be scoped one repetition at a time, and a fetch is planned hop by hop. Refused naming the repetition, with the variable-length relationship of the same bounds and direction (`(a)-[:KNOWS*1..3]->(b)`), carrying an inner condition onto the path's nodes; a longer repeated pattern is written out hop by hop. One over nodes that need no per-user scope, outside a selector, runs as written. A fixed quantifier `{n}` is read as `{n,n}`. |
| `MATCH p = ANY 2 (a)-[:R*1..5]->(b)` | **The `ANY k` path selector** — refused. `SHORTEST k` keeps the k shortest paths between each pair of ends, and `ANY` keeps one. |

**A name a `WITH` drops is gone.** A later `MATCH` that binds the same name binds a NEW variable,
with its own pins, joins and filters — nothing carries over from the first. In
`MATCH (r:Repo {name:'widgets'})-[:HAS_ISSUE]->(x) WITH x MATCH (r)-[:HAS_PR]->(p) RETURN count(p)`
the second `r` is every repository, so it is an unbound anchor: the answer is flagged
`NEEDS_FILTER` naming `r`, never widgets' pull requests counted as if they were all of them. A name
the `WITH` carries — bare, `WITH g AS h`, or `WITH *` — stays the same variable, and `UNWIND list AS
x` is not a re-binding.

**A path selector keeps the paths it names.** `ALL` alone is Cypher's default and means every
path, never only the shortest. `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`, `SHORTEST k GROUPS`
and `ANY` select per pair of end nodes, shortest first: the selector picks among the pattern's paths,
and the `WHERE` filters what it picked.

**`UNION` and `UNION ALL` run, each branch scoped as its own query.** A branch is held to the
asking principal exactly as a standalone query of that shape would be: every node it binds is scoped,
and every refusal above applies to it — an unlabelled node, a write, a procedure call in any branch
refuses the whole statement, with that branch's own refusal. Cypher's rules for combining branches
apply. Every branch returns the same column names, and a statement whose branches differ is refused
before it runs, naming each branch's columns. `UNION` and `UNION ALL` cannot be mixed in one
statement. `UNION` removes duplicate rows by value equality; `UNION ALL` keeps them.

```cypher
MATCH (b:Bill)    WHERE b.due < date() RETURN b.title AS item, 'bill'    AS kind
UNION ALL
MATCH (m:Meeting) WHERE m.at  > datetime() RETURN m.subject AS item, 'meeting' AS kind
```

A `UNION` also runs inside a subquery — a `CALL { }` body, and `COUNT { }`, `EXISTS { }` and
`COLLECT { }`. In a `CALL` each branch imports for itself, `CALL (p) { MATCH (p)-[:OWES]->(b:Bill)
RETURN b.title AS item UNION MATCH (p)-[:ATTENDS]->(m:Meeting) RETURN m.subject AS item }`, and a
branch that reads an outer variable without importing it is refused as any `CALL { }` body is.
Inside a subquery the branches must name their own variables (the table above); a statement-level
`UNION` has no such limit.

Each statement-level branch is planned and fetched as its own query, so two branches that pin the
same variable name to different anchors each fetch their own rows: a virtual join in one branch is
never narrowed by a pin in another. A variable or alias literally named `union` that cannot be told
apart from the keyword may make the statement be refused rather than split in the wrong place; a
column alias named `union`, quoted or not (`AS union`, `` AS `union` ``), is read as a name.

**A refusal names only what the query named.** Every variable a refusal quotes is one the query wrote.
A node left unnamed is shown as `()`, as it was written, and a statement the ENGINE generated — a
join's own anchor probe, quoted when it is that probe rather than the query that could not be scoped —
shows the nodes it named for itself as holes, `?1`, `?2`. So nothing in a refusal can be pasted back
into a query as a variable that exists, and a refusal's lever is always one its reader can apply.

Strict schema validation also rejects a declared virtual relationship traversed from a label
outside its declared `anchorLabel` set, unless the recorded graph shape can answer that exact
relationship between the specified labels. Name a valid anchor or use a recorded edge; a matching
relationship name alone is not evidence that another anchor can fetch it.

A `brings:` entry naming a `childType` the realm does not declare is refused earlier still, when the
realm is validated — before any query reaches the planner. The remaining case is a **non-event**: a
producer that starts returning some extra child type cannot inject it, because materialization reads
only the `records:` paths the join declared. An unmodelled node has no way in, so there is nothing to
fail loud about; the risk `brings:` actually carries is the opposite one, a declared child arriving
without its `id`, which is [reported, not swallowed](#9-caps-cost-and-diagnostics).

And these run but are **capped** (never silently — see §9): a join that would ask its source for
more than `maxAnchors` distinct keys is refused before any call is made, and a materialization that
would create more than `maxFanoutTotal` nodes is truncated at the cap, each with a diagnostic.

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

**What a `keyField` may name.** Either a property the anchor type declares, or a field one of the
anchor type's OWN joins names as its `recordKeyField`. Anything else is a load problem reported
against the realm declaring the join.

The second case is how a foreign key is traversed in REVERSE, and it is sound rather than lenient.
A type may keep an FK out of its properties — a visible id is one a generator returns instead of
following the link — while its own forward join already declares that its records carry that
column. The reverse hop keyed on it traverses because materialization stores that column on the
node whether or not the type declares it: the stored-property allowlist is the declared set PLUS
the join's `recordKeyField`, the producer's projections and computed fields, and the echoed key.
So the column is on the anchor by the time the reverse hop reads it, and refusing the shape
reported a problem on joins that work.

The check applies where the anchor type is declared in the same world. A join whose anchor is a
type this validation does not hold — a realm keying on another realm's type — is not checked
here, because the properties that would answer live in the other realm's declaration.

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

**Identity is per owner for a user-owned type.** Source ids are global, so two users' records of the
same source can share an identity by construction. A fetched record of a type whose instances belong
to one user converges only with THAT user's node of the same identity — a user's own stored node is
still preferred over a second copy — and never binds, reads or re-owns another user's. A shared,
reference or public type converges on identity alone, so a fetched record still lands on the one
stored node everyone shares.

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

### 5.2.1 What a join may make DURABLE, and what it may not

A read query writes nothing durable except an identity bridge. That is the whole of the list, and
these are the two declarations an author reaches for when they want more.

**`persist: true` — eager enrichment, and NOT "this fetch, kept."** It is the older form of a
bridge. A join declaring it is run over **every** anchor of its anchor label on a schedule, and its
target and edge are **committed**. What follows is the part that surprises people: the join is
removed from the query path. The traversal that declares it is then answered from **stored data
alone** and never asks the producer — so before enrichment has run, the same query that answers five
rows without the flag answers none with it, and asks nothing. The schema marks such an edge
`STORED ONLY` for exactly this reason.

That is the right behaviour for a bridge, whose point is to become a real node other joins anchor
on. It is never the right behaviour for a plain data join, so a `persist: true` join with no
`resolve:` chain and **no join anchoring on its target** is **refused at validate/install**, naming
the traversal it would not answer. Three things answer instead, and the refusal names all three:
drop `persist:` and keep a query-time data join (records are fetched when a query traverses the
edge, materialized for the run, swept after); declare a `population:` on the target to POLL and KEEP
records; or declare a `resolve:` chain with `writeThrough: true` for an identity bridge, which
resolves per traversed anchor and self-heals. Prefer the last — `persist:` is kept for realms
written against it.

**A minted anchor is transient, and nothing keeps one.** When a back-hop's anchor is reached ONLY
through already-materialized targets — the "who raised the most issues in this repo" shape, with no
person or user binding the anchor — the engine mints one anchor per distinct `materializedKeyField`
value on those targets, so the answer includes identities **not in your graph**. That is what
`materializedKeyField` buys, and it needs no further declaration. The minted node lives for the
query: it is swept with the run, and the next such query mints again (a graph write off records
already fetched, not another source call).

There is no flag that keeps it, and a realm should not want one. A minted anchor's only edges point
at the run's own fetched targets, so keeping the node alone would leave a node joined to nothing —
one that anchors no later query and warms no fetch, since the mint reads the materialized records
and never a stored anchor. To keep a discovered identity, make the join a **bridge**: `resolve:` +
`writeThrough: true` writes it through off the anchor it resolved from, edge included, and the next
query reuses it. A realm declaring `persistMinted` is **refused at validate/install** — it never
persisted anything, and a declaration that reads as durability and delivers none is worse than its
absence.

### 5.3 Producer kinds

| kind | fetch | keyed by |
|---|---|---|
| `remote` (alias `api`) | a gateway op — realm handler or learned REST API | the anchor's id/email/login (list, string-template, or path-param mode) |
| `sql` | a relational TABLE joined by a column, SCANNED (`scan:`) ordered and bounded, or a stored PROCEDURE's result set (`procedure:`) — the SELECT is **generated**, never authored, so the `governance:` grammar (§5.15) is enforceable by construction: governed exposure compiles into the column list, row-level `where:` predicates (`:userId` binds the acting user) inject into every statement. A procedure is read as a read — no `readOnly: false` — and rolled back to keep it one (§5.15.1) | the anchor key batch, bound into `WHERE <keyColumn> IN (…)`; rows echo the key column. A `scan:` producer takes no keys: the pinned value chooses the ordering column and is echoed under `echoKeyAs`. A `procedure:` producer is called once per key, and echoes it |
| `compute` | an in-process function over the keys (scores, rollups, synthesis) | the anchor key; no external I/O |
| `vector` | top-k semantic relevance to the anchor's **text** — a fused semantic + lexical retrieval, ranked as one list (§6.6) | nothing — *relevance is the join* (§6) |
| `keyword` | top-k **lexical** (fulltext, exact-token) match to the anchor's text — the honest fit for "MENTIONS \<term\>" | nothing — same relevance contract as `vector`, only the mode differs (§6.6) |
| `agentic-rag` | a **bounded LLM retrieval loop** over the same index: reformulates, runs both modes, reads further into inconclusive candidates, returns only documents it *judges* fit the edge's `intent` brief | nothing — relevance as a judgment (§6.6); EXPENSIVE, select explicitly |
| `remote-search` | top-k **lexical** match via the REMOTE store's OWN search API (a gateway op with `{query}` substituted per anchor wherever it sits in `args`, nested maps and lists included — e.g. Drive `fullText contains`, or a stored query's `params: {q: "{query}"}`); live, nothing ingested | nothing — same relevance contract as `keyword`, but the source searches itself; per-match `mode:'keyword'`/`rank` on the edge, score is a neutral 1.0 (matched, not similarity) unless `recordScoreField` names the record field carrying the store's OWN score, which then rides the edge as `score` unrescaled — a record without it keeps 1.0. `compute:` maps the record onto the type's properties (an expression over `r`), as on every kind that returns a source's records |
| `generative` | an LLM **invents** plausible records ("suggest things like X"), each resolved onto the spine via `resolveVia`; demand-driven (re-probes with a growing exclusion until enough survive) | the anchor's name/text, batched into ONE prompt |
| `aggregate` | gathers the anchor's connected neighborhood and LLM-**reduces** it to ONE record (a taste summary, a digest) | the anchor's identity; one record per anchor |
| `extract` | gathers the anchor's neighborhood and **extracts typed records** from it — lazy ENTITIES, committed with real containment on first traversal (§5.6). `cardinality:` chooses fan-out (many records) or reshape (ONE record per anchor — §5.6.1) | the anchor key (per-anchor collect); many records per anchor, or exactly one |
| `tabular` | a published **CSV / TSV / XLSX / XML file** (optionally a zip of XML parts), downloaded lazily, cached deployment-wide, and joined on one of its COLUMNS (§5.8) | the value of `keyColumn`, compared to the anchor key under `keyMatch` |
| `feed` | an RSS/Atom **search feed** — one search per anchor key, each item a record; optionally FOLLOWING each item's page for phrase-anchored excerpts (§5.10) | the anchor key, substituted into the feed URL |
| `sparql` | a **SPARQL 1.1 endpoint** (Wikidata, UniProt, an enterprise triplestore) queried with an authored SELECT template; the whole key batch lands in one `VALUES` clause (§5.14) | the anchor key, serialized into the query's `{{keys}}` token; rows echo it under `keyVar` |
| `cypher` | a **remote openCypher graph** (Neo4j, Memgraph, Neptune — any engine speaking Bolt or openCypher-over-HTTP) queried with an authored read query; structurally read-only, governed by the shared `governance:` grammar (§5.15) | the anchor key batch, bound to `$keys`; rows echo it via the query's own RETURN |
| `jar` | a **Java jar's classes**, read from the jar when a query reaches it — packages, types, fields, methods, field accesses and calls, with source lines; nothing ingested or stored (§5.18) | a jar path, or `<jar path>!<value>` for a property the producer selects `by` |
| `source-tree` | a **project's source in fourteen languages**, parsed when a query reaches it — files, declarations with their annotations, imports, name-matched calls and the type names each file uses, in the standard model's code columns, and any syntax a realm's own query captures (§5.21) | a project's location: an https git URL (`@ref` optional) or a folder |
| `stacktrace` | the **Java stack trace in a piece of text** — its throwables and frames, each frame naming the jar that compiled its class with that jar's keys (§5.20) | the text: a pasted trace, or a log event's `content` |
| `files` | the world's **local files**, walked live under `data/` roots — one row per file, per line (`unit: line`) or per log event (`unit: event`, §5.20.1) | the owner key; free-text terms with `emit: search` |
| `elasticsearch` (alias `elastic`) | an **Elasticsearch index or alias** retrieved by relevance — lexical, semantic, or the two fused cluster-side in one search — with index / document id / score / mode on the edge, so every hit is citable (§5.16) | nothing — *relevance is the join* (§6); the anchor's text is the query |
| *captured handler* (no `kind`) | an approved handler in the realm's own captured installation, declared as a version-1 `producers/` file. It may walk its own cursor (`page:`) and receive `=`/`IN` filters as list arguments (`pushdown:`). No cache ([captured handler producers](README.md#captured-handler-producers)) | the anchor key batch, as a list under `keyArgument`; each record carries its key under `recordKeyField` |

All producers honour the **batch contract** (all keys at once, never N+1) and an orthogonal
`cache:` policy: `none` (alias `fresh`, the default — read live every query), `ttl` (a window in
seconds, with an opt-in `negativeTtlSeconds` for misses), `immutable` (reference data, held until
the process is restarted or maintenance clears it), and `graph` for aggregates and extraction
(§5.5/§5.6, where the committed graph itself is the cache tier). WHO a kept record is kept for — the
principal, the deployment, or the deployment's organisation, according to the label the fetch targets
— is §15.4, and it is what decides whether a second asker pays.

**`negativeTtlSeconds` is opt-in because an empty is not always durable.** Under `ttl` alone only
RECORDS are kept: a key that answered empty is asked again on the next query, for ever. That is the
right default for a source over data the owner is still filling, where empty means "nothing **yet**"
and keeping it would hide everything they add until the window closed. It is the wrong default for a
published register, where a point with no value does not acquire one this afternoon — so declaring
`negativeTtlSeconds` says "an empty answer from this source is a real, durable answer", and the
empties are kept for that window, on their own clock rather than the record window's. The engine
**says when the declaration is missing and the re-buy is real**: a fetch whose keys mostly answered
empty carries an `EMPTY_NOT_KEPT` note naming the count and printing the declaration. It is a note
about COST and never about the rows, and it is not raised after a fetch that was capped, refused or
throttled — an empty there may be a key the source never reached, which no window should pin.

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
per-edge tuning — `role:`, a portable, world-defined model role id such as `chat_cheap`; **never a
concrete model name**, which stays an ops concern. A query can override it for one fetch with the
`ai.model` edge directive (§7.2). These blocks take no sampling temperature: current models ignore or
reject one, so the host sets none, and a `temperature:` a realm still declares is ignored with a warning.

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

**A spine-anchored join can ride a book sweep — `ridesHub: true`.** An edge anchored on the spine
is answered by asking the source about each account, so it is refused above `maxAnchors` (200)
— and that caps every rule set absolutely, because a rule body cannot fetch and a `requires:`
demand written as `(a:CustomerAccount)-[:HAS_CASE]->(…)` is itself account-anchored. Declaring
`ridesHub: true` on the join says: in a query that has already swept this record type's BOOK —
`MATCH (d:ChatwootDesk {status:'all'})-[:HAS_CASE]->(c:SupportCase) MATCH (a:CustomerAccount)-[:HAS_CASE]->(c)`
— link each account to the swept records by the spine's own key (the record's `hub:` property,
normalized as the spine defines: a URL becomes the account's domain), with no fetch at all. The
cap does not apply to a ridden edge, so the book's size no longer matters.

```yaml
- { anchorLabel: CustomerAccount, relationship: HAS_CASE, keyField: accountKey,
    recordKeyField: accountKeyAsked, producer: chatwootConversationsByAccount, ridesHub: true }
```

What the author asserts by declaring it: that the sweep is COMPLETE for the edge. `{status:'open'}`
sweeps only open cases; an edge that means "this account's cases" ridden on it would silently
under-report, which is exactly the fault the opt-in exists to forbid. Sweep `all`, or do not opt in.
Three rules for the demand that rides: sweep first and name the account edge to the SAME alias;
PROJECT what is swept (`RETURN c.id` — a demand that only asks whether something exists is fetched
as one page, and one that counts is answered by a count and no records); and bind a per-customer
hop through its own sweep (`MATCH (b)-[:HAS_CUSTOMER]->(lc) MATCH (b)-[:HAS_INVOICE]->(i) MATCH (lc)-[:HAS_INVOICE]->(i)`,
the hop declaring `materializedKeyField: customerExternalId`) so it links rather than mints.
Measured on realm-account-health at 2,030 accounts: the three rule-backed views went from "none"
to answering in a few seconds, six book sweeps and no per-account call.

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

#### 5.4.4 `canonicalize()` — the spine as a function

A spine's `normalize` is the single definition of "the same entity", and `hub:` applies it to a
property. When a query holds a raw value that is not on a `hub:` property — an invoice's customer
URL, a sender's address, a parameter — it must not normalize the value itself:
`split(i.customerUrl, '//')[1]` strips the scheme and nothing else, so `https://www.Acme.com/` joins
nothing while the same company's customer record, keyed through `hub:`, joins fine. No error; the
invoices are simply missing. Ask the spine instead:

```cypher
MATCH (b:LagoBooks {scope:'all'})-[:HAS_INVOICE]->(i:LagoInvoice)
MATCH (a:CustomerAccount {accountKey: canonicalize(i.customerUrl, 'CustomerAccount')})
RETURN a.name, sum(i.amountDueCents) / 100.0 AS owed
```

| Call | Returns |
|---|---|
| `canonicalize(value, 'Spine')` | the spine's key for a raw value — `'Priya <priya@Northwind-Traders.example>'` → `'northwind-traders.example'`, `'https://www.Acme.com/'` → `'acme.com'` — or `null` |
| `canonicalize(n)` | for a node whose type marks a property `hub: <Spine>`, the key from the first such property that has a value; for a node of the spine type itself, its own key |
| `canonicalization(value, 'Spine')` | `{key, outcome, rule}` — `outcome` is `ok`, `excluded` (the spine's `exclude:` refused it, e.g. a freemail address) or `invalid` (it fails `require:`, e.g. no dot); `rule` names the spine |

**It is the same normalisation `hub:` applies, not a second copy** — a query and a `hub:` property can
never disagree about a value.

**`null` means "not an identity for this spine"** and nothing else. When the reason matters — telling
a declined personal address from a malformed one — ask `canonicalization`.

**It reads nothing and claims nothing.** No lookup, no model: `canonicalize` says what the key *would
be*, not that an entity with that key exists. Existence is the `MATCH` that uses it.

**Refused before anything is fetched**, as an invalid query: a spine name that is not a string
literal; an unknown spine; a type that is not a spine; the one-argument form on a type with no
`hub:`; a value that is not a string, a parameter, or a property of a matched node. In the
property form the node's label must be written in the statement (`MATCH (i:LagoInvoice)`), and a
list-valued property reads `null`.

**Spines are per world.** A realm-declared spine (§5.4.1) is visible to queries in the world it is
installed in, and unknown elsewhere.

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
  items plus the full reduce fingerprint (function, effective instruction, role, band).
  Edit the document — or the realm's prompt, or the role — and exactly that node regenerates, in place.
  The re-check costs one graph read; the model runs only when something actually changed.
- **Wordcount BANDS.** A query's `{ai: {wordcount: N}}` quantizes to the nearest persisted band —
  gist (~40 words), standard (~200), long (~600) — and each band is its own committed node. The
  directive-free canonical **is** the standard band; a nearby request (250) is a hit on the same node.
  The band's own target (never the raw request) folds into the instruction, so one band has one
  stable fingerprint.
- **Semantic steering stays transient.** A `hint`, `voice`, `realm.*` parameter, or a `model`
  override makes the result a non-canonical artifact: it is reduced fresh for that
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
  (This applies to every producer kind, not only `extract` and not only the single regime — any fetched
  property its type declares is stored as that type, a declared list element by element; it simply matters
  most here, where a form's fields are dates, counts and amounts rather than prose.)
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
- Every value is a **string** unless the target type declares the column otherwise. A leading-zero
  identifier survives; arithmetic over an undeclared column is the query's job.
- **An empty cell is absent**, not an empty string — as `LOAD CSV` reads it. `count(o.qty)` counts
  the rows that state a quantity, and `o.qty IS NULL` finds the ones that do not.
- **A column the target type declares numeric is read as the cell means it.** An exponent is part
  of the number (`1.2E3` is 1200), a typographic minus (`−5`, U+2212) is a minus, and a cell that is
  ONLY a parenthesised amount is negative (`(2.50)` is -2.5; `Box (15)` is still 15). A cell
  stating no number (`n/a`) is left as written.
- **A cell holding several values is one string until the realm says otherwise.** Published tables
  often store a one-to-many relation in one delimited cell — a person's children as
  `gershom_1302,eliezer_1114`. A producer's `compute:` turns it into a list, one Cypher expression
  over the record `r`:

  ```yaml
  compute:
    childIds: "[c IN split(r.children, ',') WHERE trim(c) <> '' | trim(c)]"
  ```

  A join keyed on `childIds` then looks up each element (§5.1, a list-valued `keyField`), at every hop of
  a variable-length walk (§5.12). Keyed on the raw cell, it looks up the whole string as one key and
  finds nobody — with no error, because a key that matches no row is an ordinary answer.
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
content — never as "the term does not occur". The same holds for an item past `maxPages`: its page
was never read, so its `content` is UNKNOWN, not empty. The answer says so — it is marked partial,
with a `FOLLOW_CAPPED` note naming the budget, how many items went unread, and the levers (raise
`maxPages` up to its ceiling, or narrow the query) — so a `WHERE m.content CONTAINS …` over those
items is never mistaken for a complete search. **A filter never answers for a page nobody opened.**
A `WHERE` that reads a followed field (`m.content IS NULL`, `NOT m.content CONTAINS …`, as much as
`CONTAINS`) leaves the unread items out rather than judging their missing text, and the note says
how many were left out and that an aggregate over the filtered rows is a LOWER bound. A query that
only projects the field keeps every item, with the field null where its page went unread, and the
note says whose value is unknown — a `count()` of the rows stands, a `count`/`collect` over the
field is a lower bound. Speaker-attributed transcript prose survives inside
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
- **An anchor the source answered for is there even when the answer is none.**
  `MATCH (r:GitHubRepository {full_name:'acme/empty'}) OPTIONAL MATCH (r)-[:HAS_ISSUE]->(i) RETURN
  r.full_name, count(i)` answers `acme/empty, 0`, and an `IN` list mixing an empty value with a full
  one keeps the empty one's row. A value the source answered 404 for, or whose fetch failed, is not
  minted; the answer carries that warning instead (§9).
- **An anchor nothing fetched is explained, not answered empty.**
  `MATCH (r:GitHubRepository {full_name:'acme/gears'}) RETURN r.full_name` traverses no join, so
  nothing asked the source whether the repository exists, and a row built from the query's own
  literal would assert it on no evidence. The empty answer is typed as a query defect,
  `ANCHOR_UNFETCHED`, and its hint names the label's joins and the `OPTIONAL MATCH` that would
  answer. A label with stored instances and no match for the pin is a true negative and gets no
  hint.
- **It composes with the rest of the WHERE.** An `IN` combined with other conditions by `AND` still
  seeds (this matters more than it looks: scope conditions are ANDed onto every query, so an
  enumerated anchor is essentially always inside a compound).
- **A `null` in the list seeds nothing, and voids nothing.** `IN ['a', null]` seeds `'a'` — as
  Cypher's `IN` is true only for `'a'`. A boolean member seeds as its token.
- **A member that is computed is resolved.** An expression (`toLower('ACME/WIDGETS')`), a value bound
  by an earlier `WITH` or `UNWIND`, or a list-valued variable (`WITH ['a','b'] AS ks … IN ks`) is
  evaluated before the fetch, exactly as `{key: expression}` is, and seeds what it evaluates to.
- **Alternatives on one key enumerate their union.** `k IN ['a'] OR k = 'b'` seeds `'a'` and `'b'` —
  the same set written two ways.
- **A list narrowed by a ranked `LIMIT` fetches for the anchors the `LIMIT` keeps.** In
  `MATCH (s:Shop) WHERE s.code IN ['s1', …, 's6'] WITH s ORDER BY s.rank LIMIT 3 MATCH (s)-[:HAS_STOCK]->(x)`
  the hop is asked for the three shops the ranking keeps, not the six the list names. That holds
  when every listed value resolves to a stored node and the `LIMIT` is ranked by an `ORDER BY` over
  this anchor. Where it does not — a value no stored node holds (a minted anchor has no sort key to
  rank by), an unranked `LIMIT` (the k a probe keeps need not be the k the query keeps), or an
  anchor label this query is itself fetching — every listed anchor is bound and fetched for, and the
  graph narrows afterwards: a fuller fetch, never a wrong k.

**A parameter list seeds exactly as the literal list does.** `WHERE q.abn IN $abns` with `abns`
supplied answers the same rows as the same values written inline — supplied parameters are
substituted before the query is read. A parameter nobody supplied is refused, never read as an empty
list.

**A fetched node pinned to a value bound upstream is narrowed to it.** In
`MATCH … WITH x MATCH (a)-[:HAS_FIELD]->(f:Field {key: x})-[:ACCESSED_BY]->(m)`, the node a join
FETCHES (`f`, not the anchor) is pinned to `x`, which an earlier clause bound. Its values are
resolved before the fetch, and only the matching rows are kept — handed to a source that applies `IN`
filters as one, filtered on receipt otherwise — so the next hop (`ACCESSED_BY`) is asked for those
keys alone, as it would be for `{key: 'C.f3'}` written inline. The same holds for `WHERE f.key = x`
(either operand order), `f.key IN xs`, and a pin to another node's property bound earlier
(`{owner: frame.className}`). `WHERE f.key = x` pins exactly as `{key: x}` does when the condition is
an `AND` of terms; under an `OR` it is a filter, and a comparison between the properties of two
nodes of the same `MATCH` (`a.id = b.ownerId`) is a join, never a pin. When an EARLIER `MATCH` bound
`b`, the comparison is the inline pin `{id: b.ownerId}` and pins as that does, either operand order.

What it guarantees and what it does not:

- **The same rows as without it.** Narrowing never drops a row the query keeps; `OPTIONAL MATCH`
  keeps its null rows.
- **It holds back rather than guess.** When the earlier part of the query still reads data not yet
  fetched, when there are more than 5,000 distinct values, when none resolve, or when a value is not
  a plain scalar, the node is fetched in full and the pin applied afterwards — a fuller fetch, never a
  wrong answer.
- **It narrows what is fetched only where the source can be asked for it.** A source keyed by
  something else (a whole-collection producer) still reads its collection; only what is kept, and
  every later hop, shrinks. A realm that wants the read itself narrowed declares a producer selected
  by that property.

**An anchor keyed by a value computed from fetched rows is fetched for each value.** In

```cypher
MATCH (me:AssistantUser)-[:HAS_LOG_EVENT]->(e:LogEvent)-[:HAS_FRAME]->(f:JavaStackFrame)
WITH DISTINCT f.jarPath AS jar
MATCH (j:Jar)-[:HAS_PACKAGE]->(p:JavaPackage) WHERE j.path = jar
RETURN jar, count(p)
```

the jar is keyed by every value `jar` holds once the frames are fetched — however many fetches
before it they are — exactly as `(j:Jar {path: 'jars/app.jar'})` keys it. The same holds for
`{path: jar}` inline, for a key read straight off a node an earlier `MATCH` bound
(`WHERE j.path = f.jarPath`), and for a key aggregated or unwound upstream; a computed pin on the
fetched node (`… UNWIND causes AS cause … WHERE j.path = jar AND c.calleeOwner = cause`) applies on
top, as above.

- **Never an empty answer that is not one.** If the values can never be read — the earlier part of
  the query reads data this query does not fetch — the join is not fetched and the answer carries a
  `PARTIAL_RESULT` warning naming the anchor, the value its key is computed from, and the join.

**What does NOT seed, and why**

- **A filter that cannot list keys** — `STARTS WITH`, `CONTAINS`, a range, a regex on the key. Nothing
  can be fetched, and the answer SAYS so: a `NEEDS_FILTER` warning names the label and the key to pin,
  so an empty result is never read as "there are none". The same warning accompanies an anchor that
  is not pinned at all.
- **An `OR` across different properties or nodes** — `WHERE q.abn IN [...] OR q.name = '…'`. One
  branch of such a disjunction must not enumerate the anchor set. (Alternatives on the SAME key are
  an enumeration, above.)
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
- A **list-valued** `keyField` is its elements at every hop, as it is for a single hop: a person whose
  `childIds` lists three children continues the walk three ways. A walk that read the list as one key
  stopped after the first generation without a warning, because the tree simply appeared to end.
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

**One read is shared, not repeated — including by queries running at the same instant.** A cold
lookup under `ttl` or `immutable` is read ONCE however many queries want it: the first to arrive
reads the source, and every query that wants the same lookup while that read is outstanding is
served its records rather than making a read of its own. This is the shape of every cold start and
every expiry under load — a view refreshed on a schedule, a dashboard opened by a team at once, a
handler fanning out — and for a source with a hard quota it is the difference between one call and
one call per asker. What each query says it spent stays honest: the query that read the source
bills the call, the queries served by it bill none and report the lookup as `cached`, observed when
that read happened — so `cached` can mean "read a moment ago, by someone else" and never means only
"old". Three bounds on the sharing, each of which a realm can rely on:

- **A failed read is never shared.** "Could not ask" is one query's verdict on one attempt, so a
  query whose share did not arrive asks the source for itself rather than inheriting a refusal it
  never made — and nothing is remembered either way.
- **Nothing is shared across owners.** A lookup is shared only between queries that would have been
  served the same cached entry: the same source, the same declaration, the same key, the same
  caller scope. One owner's outstanding read never answers another's question, exactly as one
  owner's cached entry never does.
- **`{ai: {fresh: true}}` and a live-only read share in neither direction.** A query that asked to
  read the source NOW is not served somebody else's read of a moment ago, and its own read is not
  offered to anyone else as a share.

`cache: {kind: none}` (the default) shares nothing between queries, by declaration; within one
query it is already read once (above). A **date-addressable** source (`periods:`) caches per
`(key, period)` as always, but concurrent queries may each read a period that is still open — the
period fan-out is not covered by the sharing above.

**What the cache is keyed on, and what a cached entry may answer.** A cached fetch is keyed per
anchor key AND per **what the fetch asked its source for**: the filter the producer's `pushdown:`
rules absorbed and rendered into the request, and the `LIMIT` the planner could push into the page
walk. Which predicates are considered at all is the attachment question (§7.6.1 lists the shapes; a
`WITH` does not end attachment); which of them reach the key is this one, and the two sets differ by
exactly the rules the door declares. A predicate no rule absorbs — a comparison through `toLower`, a
property with no rule — and a `LIMIT` the planner could not push leave the fetch byte-identical, so
they are no part of the key and the graph applies them to cached records exactly as to fresh ones.
The exact key is the first question the cache is asked, not the last: when it misses, a live,
complete entry for the same anchor key that answers a **broader** question than the one asked
serves it, with no call. A complete read under the same filter serves any shorter `LIMIT` and an
existence test; a complete read with no filter serves a question with a pushed filter, since what
the source would have returned is a subset of what it already did (a capped unfiltered prefix does
not, since the filtered records may lie past its cap); a cached `LIMIT 50` prefix serves
`LIMIT 10` in the same declared order — sound only because an early stop is licensed only in the
source's declared order, so a different `ORDER BY` or a longer `LIMIT` is a fresh fetch. Whatever
served it, the graph applies the query's own filter and `LIMIT` to the records exactly as it does
to a fresh fetch, and the result reports the entry as `cached`, observed when the broad read was.
The converse never holds: a narrower entry never serves a broader question; a truncated or partial
entry, and a one-record-per-key existence entry, serve nothing but themselves; and only producers
whose source returns a fixed collection narrowed by a pushed filter and a cap take part — a result
a demand or a model shapes (generative, aggregate, extraction) is keyed exactly, as is each window
of a `periods:` door.

**What a family of views over one door costs, and how to make it share a read.** Within one TTL
window the calls a family makes depend on the order it runs in: the broadest read first, and the
rest are served. No SPELLING changes that — a predicate written over a name a `WITH` introduced is
the predicate on the property it names and is pushed exactly as that property's is (§9) — so views
over different windows of one door pay one read per window however they are written. Three things a
family can do instead, each measured on the shipping engine (2026-10-17):

- **Let the broad view read first.** A complete unfiltered entry holds every record a pushed window
  would return, so every window after it is served with no call, in any order among them: one read
  for the whole family. The converse costs what it always did — a window read first serves neither
  the broad question nor a wider window, and each pays its own call.
- **Shape a terminal result with a list slice** (`ORDER BY … WITH collect(row) AS rows UNWIND
  rows[0..$limit] AS row`) rather than a `LIMIT` the planner can push, which leaves a prefix and not
  the collection; and keep a `WITH … LIMIT` for the place it earns its key, directly before a hop,
  where it bounds the hop's anchors (README, "Predicate pushdown").
- **Read it through a door declared `readWhole: true`.** Sharing is a property of the request, so a
  door that sends no filter is read once per key and serves every view of it in ANY order, narrowest
  first included. `readWhole: true` is how a door says so while keeping its `pushdown:` rules declared:
  every read asks the source for the key's whole collection, the rules are not sent, and the graph
  applies every filter (§9). That is also why a `periods:` door's history (§5.17) is free after the
  first read: its window is a key, not a narrowing. The price is the honest one — the whole collection
  crosses the wire once, and each read says the graph applied the filter.

A family whose reads the source narrows has no order-independent sharing: each read is keyed by the
filter it sent. Declaring the door `readWhole: true` is the way to ask for it, and it only pays with a
`ttl` or `immutable` cache to hold the read for the next view. Keep the rules on the read-whole door so
that a second, narrow door over the same operation can send them. `pushdown: []` reads the same way but
states that the source cannot filter; on a source that can, it makes every read's cost note untrue.

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
  TRUNCATED warning. A retryable refusal — a throttle, a gateway failure, a timeout — is attempted
  once more, honouring the endpoint's `Retry-After` where it sends one: the same law every producer
  kind gets (§9, *what a flaky source costs*), not a `sparql` speciality.
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

**Reading a stored procedure: `procedure:` instead of `table:`.** On PostgreSQL a read-only
routine is a FUNCTION, and a keyed fetch over `SELECT * FROM fn()` already reaches it. SQL
Server and Sybase ASE have no such form: `EXEC` is the only way to invoke any procedure, read
or write, and an operations estate is full of reporting procedures that are SELECT wrappers —
*queue depth right now*, *connections by host*, *items completed in the last fifteen minutes*.
A `sql` producer may declare `procedure:`, and the procedure's result set becomes typed graph
rows: joinable, viewable, cacheable, and served through every door the world has.

```yaml
- name: robotQueueByInstance
  kind: sql
  datasource: lumina_au            # a READ-ONLY datasource: no `readOnly: false` is needed
  echoKeyAs: instance              # every row comes back carrying the pinned key
  procedure:
    name: lumina_au.dbo.sp_database_monitor_lumina_robot_queue_statistics_pending
    args: []                       # ordered; "$key" binds the anchor key, anything else is a literal
  cache: { kind: none }            # "right now" means right now
  governance:
    mode: governed
    expose:
      lumina_au.dbo.sp_database_monitor_lumina_robot_queue_statistics_pending:
        properties: [queue_item_type, queue_item_sub_type, pending_queue_item_count]
```

Reached through a virtual join whose anchor is PINNED — a datasource instance, a site, a
region, whatever the procedure is *about*:

```cypher
MATCH (:SybaseInstance {name:'lumina_au'})-[:ROBOT_QUEUE]->(q:RobotQueueDepth)
RETURN q.queue_item_type, q.pending_queue_item_count ORDER BY q.pending_queue_item_count DESC
```

Guarantees:

- **Placement is the volatility declaration.** A producer is a read path: its rows are
  materialized for one query and rolled back with it. A procedure declared here runs against
  a read-only datasource with no opt-in. A procedure that WRITES is a verb, declared in
  `sql/procedures.yml` against a datasource that says `readOnly: false`, and stays gated
  exactly as before. "Can anything mutate this database?" is still answered by grepping for
  `readOnly: false`.
- **The declaration is made true, not trusted.** By default (`rollback: true`) the call runs
  inside a transaction that is rolled back unconditionally after the result set is read, so a
  procedure that writes leaves nothing behind. This matters on engines where a procedure runs
  with its owner's rights rather than its caller's. `rollback: false` exists for an engine
  whose procedures refuse to run inside a caller's transaction (Sybase ASE unchained-mode
  procedures); with it, the declaration is the only assurance, and the realm README should
  say so.
- **One call per key.** A procedure argument is a scalar, so there is no batch. Every
  returned row carries the pinned key under `echoKeyAs`, which is required and is the join's
  `recordKeyField`. A procedure with no arguments still needs a pinned anchor: the key it
  echoes is the door the query walked through.
- **The first result set is the rows.** A procedure that produces none reads as no rows. A
  procedure the datasource cannot run is a diagnostic and no rows, never a silent zero.
- **`procedure`, `keyColumn` and `scan` are mutually exclusive**, and exactly one is required.
  A procedure read needs no `table`.
- **Governance is enforced on receipt, and the tier says so.** There is no SELECT list to
  compile exposure into, so the rows cross the wire whole and unexposed columns are stripped
  on arrival; `expose` is keyed by the procedure's name. A row-level `where:` predicate has
  nowhere to go and is REFUSED at load, never silently ignored. Masks and the secret reflex
  apply as everywhere.
- **A procedure-backed label's values are not enumerable.** There is no column to list
  distinct values of; discovery says so rather than guessing.
- **SQL Server, Azure SQL and Sybase ASE datasources are supported**, for procedures and
  tables alike. A `jdbc:sqlserver:` or `jdbc:sybase:` URL selects the T-SQL dialect on its
  own; `dialect: sqlserver` or `dialect: sybase` on the producer names it explicitly.

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
anchors, drive the cold fill with a **fill** (§9.1) instead of one long query. A realm ships that
sweep WITH the producer rather than leaving it to be discovered: declare it as a `sweeps:` entry on
one of the realm's own agents (README, `agents/`), naming a view of yours that takes no arguments.

**A worked example: immutable records behind a date-filterable list.** GitHub's workflow-runs
endpoint is not date-addressable by design, but its `created` filter takes a month (`2026-09`)
or an exact date, and a completed run never changes — so the same endpoint declared twice gives
two doors to one collection (realm-github-actions, 2026-09-23):

```yaml
- name: runsByRepo              # LIVE: newest first, a literal since pushed to `created`
  operation: actions/list-workflow-runs-for-repo
  pushdown: [{ property: created_at, op: GREATER_THAN_OR_EQUAL, argPath: created, clause: ">={value}" }]
  cache: { kind: ttl, seconds: 600 }
- name: runHistoryByRepo        # HISTORY: this month and last, a closed month cached 400 days
  operation: actions/list-workflow-runs-for-repo
  paging: { style: page, param: page, sizeParam: per_page, size: 100, maxPages: 15 }
  periods: { param: created, unit: month, count: 2, lag: 0, stampAs: month }
  echoKeyAs: repository
  cache: { kind: ttl, seconds: 1800 }
```

`unit: month` sends `created=2026-09`. Two months always cover at least the last 31 days.
Measured: a cold read of one busy repository is one page per hundred runs in the two months
(13 calls, ~25 s); every later read of any window up to 31 days is 0 calls and 150–600 ms, because
the history door declares no rule a window could be pushed into, so every view's read of a period is
the same read whatever window the view asks for (§5.13). `unit: day` was tried first: 31 calls cold
for the same coverage, and a bigger refresh surface. "Right now" questions can stay on the live
door. State the edge in the realm's README: a record still changing when its period closed
(a run in progress when the month turned, a run re-run in a later month) keeps in history the
state it had when that period was last read.


### 5.18 `jar` — a Java jar's classes as a keyed source

A `jar` producer reads the bytecode of a Java jar when a query reaches it, and returns what the jar
declares: its packages and types, their fields and methods, which methods read and write which
fields, and which methods call which — into the jar, the JDK or any other library — with source
lines from the jar's debug information. Nothing is ingested, indexed in advance or stored: the rows
are transient for the query, like any fetch. No source code is needed or read.

```yaml
- { name: javaJarTypes,        kind: jar, emit: types }                 # key: a jar path
- { name: javaFieldsOfType,    kind: jar, emit: fields,   by: owner }   # key: <jar path>!<owner>
- { name: javaAccessesOfField, kind: jar, emit: accesses, by: field }   # key: <jar path>!<field>
```

```cypher
MATCH (j:Jar {path: 'data/jars/app.jar'})-[:HAS_TYPE]->(t:JavaType {name: 'com.example.Cache'})
      -[:DECLARES_FIELD]->(f:JavaField)-[:ACCESSED_BY]->(a:FieldAccess)
RETURN f.name, a.method, a.access, a.lines
```

**The contract:**

- **`emit` is the collection, `by` is the selector.** `emit` is one of `artifact`, `packages`,
  `types`, `fields`, `methods`, `accesses`, `calls`, `casts`, `methodBodies`. With `by` absent (or
  `jarPath`) the key is a jar
  path and every row of that collection is returned. With any other `by` the key is
  `<jar path>!<value>`, and the rows are those whose `by` property equals `value`, or — for a list
  property such as a type's `interfaces` — contains it. A `by` that is not a property of the
  collection, or an unknown `emit`, is refused when the realm loads.
- **Every row carries the key the next hop needs.** `id` is `<jar path>!<member>`, `jarPath` is the
  jar path as the key gave it, and every property naming another member has an `…Id` twin
  (`ownerId`, `methodId`, `fieldId`, `callerId`, `calleeId`, `superclassId`). A row also carries
  `anchorKey`, the key it was fetched for: that is the `recordKeyField` a join declares. So a hop
  from a type to its fields keys on the type's `id` with `by: owner`, and a hop from an access to its
  method keys on `methodId` with `by: key`.
- **Names are the JVM's.** A type is named by its binary name, `pkg.Outer$Inner`, as stack traces
  and heap dumps print it; an array type is written `T[]`. A method's `key` is
  `Owner.name(parameter types)`, constructors are `<init>` and a static initializer `<clinit>`.
- **Only the jar's own classes are rows.** A supertype, field or callee outside the jar (the JDK,
  another library) is a name on the row that refers to it — `superclass`, `fieldOwner`,
  `calleeOwner` — never a row of its own; `internal: false` marks those references. A call row says
  `resolution: exact`: bytecode names the method the runtime calls (§5.21). A field's
  `container` (`map`, `collection`, `array`, `threadlocal`, `reference`, `none`) is decided by its
  declared type and, for a type in the jar, that type's own supertypes down to the JDK.
- **Generics are read from the class files.** A field carries `genericType`, its declared type with
  type arguments as source writes it (`java.util.Map<com.x.Key, java.lang.String>`), and
  `typeArguments`, those arguments erased to binary names. A map's key and a set's element — the type
  the container hashes — is `keyType`; a map's value is `valueType`; a collection's, array's,
  ThreadLocal's or Reference's is `elementType`; each has an `…Id` twin. A method carries
  `genericParameters` and `genericReturnType`, a type its `typeParameters`. These hold for what a
  declaration says, never for what flows through it at run time.
- **A type says where its `hashCode` and `equals` come from.** `hashCodeFrom` and `equalsFrom` name the
  class that supplies each: the type itself, an ancestor in the jar, a JDK ancestor, or
  `java.lang.Object` — identity. They are absent for an interface, and when an ancestor in another
  library would decide.
- **Rows carry the keys a jar's source is read by** (§5.19). Types, fields, methods, calls and
  accesses carry `sourcePath` — the package path and the source file the class file records
  (`com/x/Cache.java`; a nested class shares its outer class's file) — and `sourceKey`,
  `<jar path>!<sourcePath>`. Methods, calls and accesses also carry `spanKey`,
  `<sourceKey>#<line>#<name>`: their first line and the word expected there (the member's name, the
  class's simple name for a constructor, `static` for an initializer). A class compiled without debug
  information has neither.
- **A method knows every line it has code on.** A method row carries `lines`, the source lines its
  line-number table holds, ascending; `lastLine`, the last of them; and `at`, one `Owner.name:line`
  per line. `line` is only where the method starts, and a constructor's code can start at a field
  initializer above another constructor, so the method a stack frame's line was in is the one whose
  `lines` hold it: `by: at` with key `<jar path>!<Owner>.<name>:<line>` returns exactly that method,
  overloads included. Empty without debug information.
- **An access or a call is grouped by its target.** A method that reads a field on six lines is one
  `READ` row with six `lines`; a `WRITE` is an assignment. Adding to a collection held in a field is
  a `READ` of the field plus a call (`put`, `add`) in the same method.
- **What the program casts at run time: `casts`.** One row per `checkcast` and `instanceof`
  instruction in the jar's own method bodies, never grouped: `kind` (`cast` or `instanceof`),
  `targetType` (binary name, an array as `T[]`; `targetTypeId` reaches the type when it is in the
  jar, `internal` says so), `targetElementType` (the type without its brackets) and `isArray`;
  `method`, the `methods` key of the method the instruction was written in, with `methodId`,
  `methodOwner` and `methodName`; `line`, the source line from debug information; and `ordinal`, its
  place among the method's casts and instanceofs, from 1. `key` is
  `<method key> <kind> <targetType> #<ordinal>`. A cast inside a lambda belongs to the method the
  lambda is written in, as a call or access there does, and `lambda` names the compiled lambda
  (`lambda$parse$0`); `inSyntheticMethod` marks every cast the compiler placed in a method of its
  own making. A row carries `sourceKey` and, with a line, `spanKey` `<sourceKey>#<line>#<word>`,
  where the word is the target's simple name (`Entry` for `Map$Entry`, `int` for `int[]`).
- **How a method's code branches: `methodBodies`.** One row per compiled method body — abstract
  and native methods have none — counting what the compiler emitted: `branches` (every conditional
  jump: `if`, `&&`, `||`, `?:`, a loop's test, a null check), `backEdges` (jumps to earlier code: one
  per loop, as compiled), `switches` (switch instructions), `handlers` (distinct exception
  handlers) and `catchAnyHandlers` (those catching anything: `finally`, `synchronized`), `casts`,
  `instanceofs`, `instructions`, and `line`, `lastLine` and `lineSpan` from the line table.
  `method` names the `methods` key the body belongs to — a lambda body (`isLambda`) belongs to
  the method it is written in, so selecting `by: method` returns a method's own body and one per
  lambda in it; sum them for the method as written. `key` is the
  body's own: the method's key, a lambda's compiled name, or for a bridge (`isBridge`), which shares
  its method's key, `<method key> returns <type>`. A synthetic accessor has no `method`.
- **Bytecode counts are not source counts.** Both collections read what the compiler wrote, and a
  reader comparing them with the source should expect:
  - casts the source never wrote: a generic method's erased result (`String s = list.get(0)` is a
    `checkcast String`), a bridge's argument, a pattern match (`o instanceof Foo f` is an
    `instanceof` and a `cast`), an enum's `values()` (a cast of the cloned array), a Kotlin
    smart cast;
  - no row for what source calls a conversion: widening and narrowing between primitives
    (`(int) aLong`), boxing and unboxing are other instructions, not casts;
  - a switch on a string is two switch instructions (one on the hash code, one on the position)
    plus an `equals` branch per label; a switch on an enum reads a synthetic lookup array first; a
    pattern switch is an `invokedynamic` that picks the case, a switch on its answer, and a cast
    per typed case;
  - `&&`, `||`, `?:` and `assert` are branches; `for`, `while` and `do` compile to one back edge
    each, and a `continue` that jumps back to a loop's test is another;
  - `finally` code is copied into every exit path, so its branches and casts count once per copy;
  - a compiler other than javac (kotlinc, scalac, a bytecode weaver) makes different choices, and
    Kotlin's inlined functions report line numbers past the end of the file, which stretch
    `lastLine` and `lineSpan`.
- **A key names a jar, a war, or a folder of classes.** A key ending `.jar` is a jar. A key ending
  `.war` is a web application's own code — what its `WEB-INF/classes` holds, the classes and the
  resources beside them — and not its `WEB-INF/lib`, which is other people's: `warLibs` names the
  library jars to read with it, by file name glob (`warLibs: [acme-*.jar]`); a library's class never
  replaces the application's, nor an earlier library's, and its `META-INF` is not read. Any other key
  is a folder of compiled classes: one module's `target/classes`, or a project's folder, whose every
  module's classes are read — except test output below the key (`test-classes`, Gradle's
  `classes/<language>/test`), which reads only when named as the key itself; where two modules compile
  one class, the first in path order is read. A war or a folder answers every collection a jar does,
  with the same properties, and its rows' ids start from the key as given:
  `apps/shop.war!com.acme.Cache`, `src/shop/target/classes!com.acme.Cache` (a folder key's trailing
  `/` is dropped, so both spellings give the same ids). In a folder's member keys the archive ends at
  the LAST `!`. The `artifact` row says which it was: `packaging` is `jar`, `war` or `classes`; a
  folder's `coordinate` is its project's folder name unless its classes carry a `pom.properties`,
  and its `sha256` is of the classes, not of any file.
- **Where a jar may be.** A relative path resolves against the world's `data/` tree, then against
  the declaring realm's own directory — so a realm can ship an example jar — and an absolute path
  must lie under a root the operator trusts. A key that names no readable jar, war or folder there
  yields no rows and a `PRODUCER_ERROR` naming the key; a jar or war larger than `maxJarMb` (default
  128) is refused the same way, never half read — for a war the size is what is read, its classes
  and the named libraries, and for a folder the size of its class files. A folder is read again when
  a file in it is added, removed or changed. On an appliance, `embabel data add <file|folder> --to jars`
  puts one under the world's `data/` and prints the key to read it by.
- **Filters in the MATCH narrow the read.** An equality, `IN`, `CONTAINS` or list membership on a
  property of the emitted collection is applied before rows reach the graph:
  `(j:Jar {path: $jar})-[:HAS_CALL]->(c:MethodCall {calleeOwner: 'java.lang.System'})` does not
  materialize every call in the jar. The graph re-applies every filter, so the answer never depends
  on it.

Cost: a jar is read once and kept for later hops of the same and subsequent queries until it
changes on disk, so the first query against a jar pays for reading it and the rest are lookups. A
war or a folder costs the same plus copying its classes once each time it is read; a folder is also
listed once per hop that reaches it, to see whether it changed. A
whole-jar hop over a large jar is still many rows — tens of thousands of calls in a mid-sized
library — and is subject to `maxFanoutTotal` like any other; reach those rows through a keyed hop, or
narrow them in the MATCH.

**Code labels are language-neutral parents.** The standard model declares `Package`, `CodeType`,
`Field`, `Method`, `Call`, `FieldAccess`, `Source`, `SourceSpan`, `SourceDeclaration` and `CallSite`,
each with the properties every language's rows carry; a realm declares its language's children
(`JavaMethod` with `parents: [Method]`) over its own producers, as memory systems are children of
`Memory` (§6.8). A query naming a parent is answered by every language with a join.

### 5.19 `source-tree` with `from: jar` — the source a jar was compiled from

The `source-tree` kind (§5.21) with `from: jar` reads a jar's source; the `source` kind that did before
is retired: a producer file that still writes `kind: source` does not load, and the realm reports it as a
problem naming the file.
Change `kind: source` to `kind: source-tree, from: jar` and `emit: callsites` to `emit: calls`: keys,
ids and columns are as they were.

A `from: jar` producer reads source files where they are, when a query reaches them, keyed by what a
`jar` row (§5.18) already carries. Nothing is ingested; the rows are transient like any fetch.

```yaml
- { name: javaSourceFile,  kind: source-tree, from: jar, emit: files,        roots: [src] }             # key: a sourceKey
- { name: javaSourceSpan,  kind: source-tree, from: jar, emit: spans,        roots: [src], context: 6 } # key: a spanKey
- { name: javaDeclaration, kind: source-tree, from: jar, emit: declarations, roots: [src] }             # sourceKey or spanKey
- { name: javaCallSites,   kind: source-tree, from: jar, emit: calls,        roots: [src] }             # key: a spanKey
- { name: javaLocals,      kind: source-tree, from: jar, emit: locals,       roots: [src] }             # sourceKey or spanKey
- { name: upstream,        kind: source-tree, from: jar, emit: spans,
    roots: [ { git: "https://github.com/acme/acme", ref: "v{version}" } ] }
```

```cypher
MATCH (j:Jar {path: 'data/jars/app.jar'})-[:HAS_CALL]->(c:JavaMethodCall {calleeOwner: 'java.util.Map', calleeName: 'put'})
      -[:AT_SITE]->(cs:JavaCallSite)
RETURN c.caller, cs.receiver, cs.arguments, cs.argumentTypes
```

**The contract:**

- **Five emits.** `files` returns the file a `sourceKey` names: `root`, `path`, `language`, `lines`,
  `sha256`, `package`, `candidates`, and for a git root `commit` and `url`. `spans` returns the numbered
  lines within `context` (default 6, at most 50) of a `spanKey`'s line, with `matches` — whether the
  word the key expects appears on them — and `inRange`. `declarations` returns, for a `sourceKey`,
  every type, field, constructor, method and initializer the file declares, or for a `spanKey` the
  innermost one around the line: `kind`, `name`, binary `owner`, `fromLine` / `toLine`, `signature`,
  `modifiers`, `annotations` (names), `annotationText` (each in full, as written), `javadoc`, and for
  a member its numbered `text`. `calls` returns the
  calls on a `spanKey`'s line whose method (or, for a constructor, class) is the key's word: `receiver`,
  `receiverType`, `arguments`, `argumentTypes`, `argumentTypesResolved`, `enclosing`, and
  `resolution`: `type` when the receiver's static type is known, else `name` (§5.21). `locals` returns,
  for a `sourceKey`, every local variable the file declares, or for a `spanKey` those of the method,
  constructor or initializer around the line: `kind` (`local`, `for`, `foreach`, `resource`,
  `pattern`), `name`, `line`, `declaredType` as written, `isVar`, `isFinal`, `initializer`,
  `initializerType`, `varEligible` and `varPreservesType` (below), `enclosing`, `enclosingKind`,
  `enclosingOwner`, and the numbered `text` of the declaration. Every row carries
  `id`, `sourceKey`, `jarPath` and `anchorKey`, so a span or declaration joins back to its file by
  `sourceKey`.
- **Where source is looked for, in order.** A `<jar name>-sources.jar` beside the jar — for a war,
  `<war name>-sources.jar` beside the war; for a folder of classes, the project it was built in, read
  as a source tree (the folder above `target` or `build`: `shop/target/classes` finds
  `shop/src/main/java/com/x/Cache.java`; a project folder named as the key is itself the tree); then each root,
  in the order declared — a `-sources.jar` named as a root, a `<jar name>-sources.jar` inside a root
  folder, the folder itself as a source tree, or a git repository. Paths resolve as a jar path does:
  the world's `data/` tree, an operator-trusted root, the declaring realm's own directory. In a tree a
  source path is found under any module and source folder (`core/src/main/java/com/x/Cache.java` for
  `com/x/Cache.java`); when more than one file matches, the first in path order is read and
  `candidates` says how many there were. The first root holding the path answers.
- **A git root is read at a commit.** `ref` is a commit, tag or branch; `{version}` in it is replaced
  by the jar's version. A tag or branch is resolved to its commit first, and rows report the commit, so
  the same rows come back whatever the tag later points at. Only https URLs are accepted, held to the
  same address rule as any fetched URL; a repository needing credentials is refused, not waited on.
  The first read of a commit lists its files; a file's content is fetched the first time it is read.
- **Declarations, call sites and locals need a syntax tree.** They answer for Java source; a file in
  another language answers `files` and `spans`, and these emits return nothing for it with a
  `PRODUCER_ERROR` warning saying so. A file with syntax errors answers around them. An argument's type is
  resolved from the file alone — `new X(…)`, a literal, a cast, a parameter, a local declared before
  the call, a field of an enclosing type — through the file's own types, single-type imports,
  `java.lang` and the file's package. A type only another file could explain is returned as written
  with `argumentTypesResolved` false; a method's return value is unknown.
- **Whether `var` would do.** `varEligible` is the language's rule: one variable, given a value that
  is not `null`, an array initializer, a lambda or a method reference (every enhanced-`for` variable;
  never a pattern binding). `varPreservesType` says whether `var` would give the variable the type it
  declares: true for `String s = "x"` or `Key k = new Key(id)`; false when the initializer's type is
  another one (`long n = 1`, `List<X> xs = new ArrayList<>()`), an anonymous class, or a diamond under
  a parameterised type; null when the initializer's type is not in the file — never guessed. It is
  null for a local already declared with `var` and for one `var` cannot replace.
- **What is honest about absence.** A key whose path no root holds returns nothing — a generated class
  has no source. A jar for which no root at all could be found, a declared root that could not be
  read, a git ref that names nothing, and a file larger than `maxFileKb` (default 1024) are each a
  `PRODUCER_ERROR` warning naming what was missing. A source that is not the jar's version shows as
  `matches: false` on its spans and declarations; its line numbers cannot be trusted.

Cost: a root is listed once and kept for later keys and queries (an archive until it changes on disk,
a commit for good); a folder tree is listed again when a lookup misses, at most once per fetch. Each
key is then one file read, and a syntax-tree emit parses a file once per fetch however many keys name
it. A git root's first query pays for a shallow, blob-less fetch of the commit; each file read from it
for the first time is one more fetch.

### 5.20 `stacktrace` — a Java stack trace as a keyed source

A `stacktrace` producer reads the Java stack trace in a piece of text, when a query reaches it. The
key IS the text — a trace a user pasted, or a log event's `content` (§5.20.1) — so a literal-seeded
anchor carries it:

```yaml
- { name: traceFrames,     kind: stacktrace, emit: frames,     jars: [jars] }
- { name: traceExceptions, kind: stacktrace, emit: exceptions, jars: [jars] }
```

```cypher
MATCH (t:StackTrace {text: $trace})-[:HAS_FRAME]->(f:StackFrame {firstInJar: true})-[:DECLARED_AT]->(d:JavaDeclaration)
RETURN f.exception, f.className, f.method, f.line, d.text
```

**The contract:**

- **The first trace in the text is read.** A header (`pkg.SomeException: message`, optionally after
  `Exception in thread "…"`) counts only when frames follow it; text before it (a log line's own
  message) is not part of the trace, and a wrapped message is kept whole. Each `Caused by:` and
  `Suppressed:` is a throwable of its own, in order, with its frames and the count of `... n more`
  frames it shares with the one before (`elided`). Module and class-loader prefixes (`java.base/`,
  `app//`) are not part of the class; a logging layout's packaging suffix (`~[lib.jar:1.0]`) is kept as
  `location`. Text with no trace answers nothing, with a `PRODUCER_ERROR` warning saying so.
- **Nesting is kept.** A suppressed throwable's own causes belong to it, not to the one thrown:
  `depth` is 0 on the chain from the thrown throwable to its root cause and one more inside each
  suppressed throwable, and `parentIndex` names the throwable each one caused or was suppressed by.
  `isRootCause` is the end of the depth-0 chain.
- **`exceptions`** returns a row per throwable: `index`, `relation` (`thrown`, `cause`,
  `suppressed`), `depth`, `parentIndex`, `exception`, `simpleName`, `message`, `frameCount`, `elided`, `isRootCause`,
  `topFrame`, and the first frame of it in a jar — `jarFrame`, `jarFrameLine`, `jarPath`, `sourceKey`,
  `spanKey`, `methodAtKey`. **`frames`** returns a row per frame: `exceptionIndex`, `relation`, `exception`, `frame`
  (its position), `isTop`, `firstInJar`, `className`, `packageName`, `method`, `file`, `line`, `module`,
  `native`, `location`, `text`, `sourcePath`, and `expectedName` — the name its line should show (the
  method; the class's simple name for a constructor; the enclosing method for a lambda body). Every row
  carries `traceId` (the same text, the same id) and `anchorKey`.
- **A frame finds its own jar.** Each frame's class is looked up in the jars under `jars` (each a jar
  or a folder of jars, nested folders included; `-sources.jar` and `-javadoc.jar` are not code),
  resolved as a jar path is: the world's `data/` tree, an operator-trusted root, the realm's own
  directory. The first root, then path order, wins; `jarCandidates` says how many jars had the class.
  A frame a jar compiled carries `jarPath`, `inJar: true`, `javaTypeId`, `sourceKey` and — when it
  names a file and a line — `spanKey` and `methodAtKey` (the key of the jar's `by: at`: the method
  the line was in, §5.18), spelled exactly as that jar's own rows spell them (§5.18), so
  it joins to the jar's types and the spans and declarations of its source (§5.19) with no
  translation. A frame no jar compiled (the JDK, a library not mounted, a generated proxy) is still a
  row, with `inJar: false` and none of those keys. A jar root that cannot be found is a
  `PRODUCER_ERROR` warning.
- **Whether the source is the jar's version** is answered by the declaration around a frame's line
  (§5.19 `declarations` for its `spanKey`): `matches` compares that declaration's name with the
  frame's `expectedName`. A span's `matches` looks for the name within `context` lines, and a frame's
  line sits inside a method's body, so it can read false on the right source.

Cost: a key is parsed in memory, and a jar's class list is read once and kept until the jar changes.
A text larger than `maxTraceKb` (default 256) is refused with a warning, never half-read.

#### 5.20.1 Log events — `files` with `unit: event`

A `files` producer with `unit: event` returns one row per LOG EVENT — from a line that starts one to
the next — so a logged exception is one row however many lines its trace takes:

```yaml
- { name: logEvents, kind: files, roots: [logs], include: ["**/*.log"], unit: event, contentCapKb: 8192 }
```

- **Where an event starts.** At a line containing a match of `eventStart`, when declared. Otherwise the
  file decides: lines beginning with a date or time when it has any; else lines beginning with a level
  word; else every line that is not a trace's continuation (indented, `Caused by:`, `Suppressed:`,
  `... n more`).
- **What a row says.** The file's fields, plus `line` and `endLine`, `content` (the event's text),
  `timestamp`, `level`, `severity` (the level on one scale: `SEVERE` is `ERROR`, `WARNING` is `WARN`,
  `FINE…` is `DEBUG`, `CONFIG` is `INFO`), `thread`, `logger`, `message`; and from the Java stack trace
  in it, read as §5.20 reads one, `hasTrace`, `exception`, `exceptionMessage`, `causes`, `rootCause`,
  `frameCount` and `fingerprint` — the same thrown and root exceptions at the same frames have the
  same fingerprint, so a failure can be counted across events. A field the layout does not show is
  null.
- **Layouts.** `eventPattern`, when declared, is a regex over an event's first line (or first two,
  joined by a newline) whose named groups `timestamp`, `level`, `thread`, `logger` and `message` fill
  the row; another group name is refused when the realm loads. Undeclared, the Spring Boot,
  Logback/Log4j, time-level-logger, timestamp-then-level, java.util.logging and level-first layouts are tried in turn.
- **Matching.** Under `emit: search` or a `content CONTAINS` filter, the term is judged against the
  whole event. A file is read up to `contentCapKb`; events past it are not returned.

### 5.21 `source-tree` — a project's source in any of fourteen languages

A `source-tree` producer reads a project's source files in TypeScript (and TSX), JavaScript (and JSX),
Python, Go, Rust, C, C++, C#, Ruby, PHP, Kotlin, Scala, Swift and Java, parsing each with that
language's grammar when a query reaches it. Nothing is ingested. Java has emits of its own besides,
which name types by binary name and say what the file alone shows about types (below), and the kind
also reads the source a jar was compiled from (`from: jar`), with the rows of §5.19.

```yaml
- { name: pyDeclarations, kind: source-tree, emit: declarations, languages: [python] }
- { name: allFiles,       kind: source-tree, emit: files }                 # every language
- { name: goCalls,        kind: source-tree, emit: calls, languages: [go], maxFileKb: 256 }
- { name: javaMetrics,    kind: source-tree, emit: captures, languages: [java], query: queries/java-metrics.scm }
```

```cypher
// Which handler serves a route, whatever the language: decorators, annotations and attributes alike
MATCH (p:CodeProject {key: 'https://github.com/acme/shop'})-[:DECLARES]->(d:SourceDeclaration)
WHERE any(a IN d.annotationText WHERE a CONTAINS '/items/{id}')
RETURN d.language, d.owner, d.name, d.annotationText, d.path, d.fromLine
```

**The contract:**

- **The key is a project's location**: an https git URL, optionally `@ref` (a commit, tag or branch;
  the default branch without one), read at the commit it resolves to; or a folder under the world's
  `data/` tree, an operator-trusted root, or the folder the operator mounted for project keys. A git
  project is read once per commit and kept; a folder is read afresh for each fetch. A tag or branch,
  the default branch included, is resolved to its commit at most once a minute, so a pushed commit is
  read by the first fetch a minute after it.
- **Five emits, each row in the columns of a standard-model parent** (and a sixth, `captures`, and a
  seventh, `version`, below), so a realm's language children
  of those parents (`PythonDeclaration` under `SourceDeclaration`) carry them under the same names as
  Java's:
  - `files` (`Source`): `root`, `path`, `language`, `lines`, `sha256`, `commit` (git), `url` (on a
    host with a file view), `parsed`, and `errors` — the number of syntax errors the file's tree holds.
    Error recovery keeps everything around a broken region, so a file with errors still answers.
  - `declarations` (`SourceDeclaration`): each class, interface, struct, enum, trait, module,
    namespace, `impl`, function, method, constructor, field, variable and constant the language
    has: `kind`, `name`, `owner` (the enclosing types, outermost first, `.`-joined; a Go receiver or
    C++'s `Order::total` names its type explicitly), `fromLine` / `toLine`, `signature` (up to the body,
    on one line, without annotations), `javadoc` (the doc comment above it, or a docstring), the
    numbered `text` of a non-type declaration (at most 400 lines), `annotations` (the names of its
    decorators, annotations or attributes) and `annotationText` (each in full).
  - `imports` (`SourceImport`): `imported` (what it imports from: a module, package, path or header),
    `names` (what it brings in, in source order; empty for a whole module), `alias`, `isStatic` (false).
  - `calls` (`CallSite`): `method` (the called name), `receiver` (what it is called on, as written),
    `arguments` (each as written), `enclosing` (the function or method it is in — for a call inside a
    decorator or attribute, the declaration it decorates), `receiverType` and `argumentTypes` (empty:
    syntax does not say) and `resolution`, always `name`.
  - `references` (`SourceReference`): each name used where a type goes — a parameter's, field's or
    return type, a base class or interface, a generic argument, an annotation, a constructor call — as
    `name` (the last segment, as written), `enclosing` (the innermost declaration it is used in: a
    field's type is used in the field; empty at the top level) and `resolution`, always `name`. A
    declaration's own name is not a reference (`class Order` does not use `Order`), nor is a generic
    parameter inside the declaration that declares it (`T` in `class Box<T>`). A built-in type
    (`string`, `int`) is a reference like any other; join to the project's declarations to keep the
    project's own.
  Every row carries `id`, `sourceId` (its file's `id`), `path`, `language`, `line`, `url`, `project`
  and `anchorKey`.
- **`version` says whether the project changed, without reading it.** One row per project key:
  `project` (as read), `commit` (a repository's, the default branch or `@ref` resolved as above) and
  `version` — the commit, or for a folder a digest of every file's path, size and modification time.
  No file is read or parsed, so it is cheap enough to ask every minute; it is what a `documents`
  source watches (README, `sync.watch`) to re-read a project only when a commit lands. A folder's
  `version` moves when a file is added, removed or rewritten, even with the same bytes.
- **`id` names a row where it was read, not what it is.** It holds the project as read
  (`host/repo@<commit>` for a repository) and the row's line and column, so it changes with every commit
  and whenever the code above it moves. It is the key to join rows of one read (`enclosingId = d.id`).
  To keep anything about a declaration from one read to the next — a document named after it, a stored
  note — name it by the project key, `path`, `kind`, `owner` and `name`, numbering the second and later
  of one name in a file by line; and leave `text`'s line numbers out of anything compared across reads.
- **A call or a reference is matched by name.** `resolution: name` says the callee or type is only
  known by its name: any function or type of that name may be the one meant. Present such a row as
  "calls something named `save`" or "uses a type named `Order`", never as a resolved edge; where two
  of the project's types share a name, say so. Java's rows say `exact` (from bytecode, §5.18) or `type` (the receiver's
  static type is known, §5.19).
- **`languages` narrows what is read** to the named languages (empty reads them all). A name no
  language has is refused with a `PRODUCER_ERROR` warning listing the languages there are.
- **`captures` runs the realm's own query.** `query:` names a tree-sitter query file (`.scm`) in the
  realm, relative to its root, and `languages:` names the one language whose grammar it is written
  against. Each node the query captures is one row: `capture` (the capture's name, without `@`),
  `nodeType` (the grammar's name for the node, `cast_expression`), `text` (the node's text, whitespace
  collapsed, at most 200 characters), `line` / `column` / `toLine` / `toColumn` (where its first and
  last characters are), `match` (an id shared by the captures of one match, so a cast and its
  `@cast.type` are read together), `pattern` (the pattern's index in the query, from 0), and the
  innermost declaration it is in: `enclosingId` (that declaration's `declarations` row `id`, so
  `WHERE c.enclosingId = d.id` joins them), `enclosing` (its name) and `enclosingKind` (empty at the top
  level). A node two patterns capture under one name is one row. Text predicates (`#eq?`, `#not-eq?`,
  `#match?`, `#any-of?`) are applied.

  ```scheme
  ; queries/java-metrics.scm
  (if_statement) @if
  [(for_statement) (enhanced_for_statement) (while_statement) (do_statement)] @loop
  (cast_expression type: (_) @cast.type) @cast
  ```

  ```cypher
  // Ifs per method, longest first; commented-out code is a comment node, so it never counts
  MATCH (p:CodeProject {key: $project})-[:CAPTURES]->(c:JavaCapture {capture: 'if'})
  RETURN c.path, c.enclosing, count(*) AS ifs ORDER BY ifs DESC
  ```

  Refused with a `PRODUCER_ERROR` warning and no rows: a query file the realm does not have, one with
  a character outside ASCII (tree-sitter would silently lose its end; the warning names the line), and
  one that does not compile against the grammar (the warning gives tree-sitter's row and column).
  Refused when the realm is loaded: `query:` on another emit, `captures` without `query:`, a `query:`
  that leaves the realm (`..`, a leading `/`), and `captures` naming other than one language. A file
  capturing more than `maxCaptures` nodes (default 10000, at most 100000) answers its first
  `maxCaptures` and is reported. Captures are not kept: each fetch parses the files again.
- **Each file is bounded.** A file larger than `maxFileKb` (default 512, at most 4096) is not read; a
  file that takes longer than `parseTimeoutMs` (default 2000, at most 60000) to parse is abandoned;
  past `maxFiles` (default 20000) source files the rest are not read. Each is a `PRODUCER_ERROR`
  warning naming the file, never a half-read file. A key that names no readable project is a warning
  with the reason.
- **What is not read.** Directories a build or package manager writes (`node_modules`, `target`,
  `build`, `out`, `.git`, …) are skipped. Generated files are read like any other.

- **Java's own emits, by binary name.** A name is resolved as the file resolves it, from the file
  alone: written qualified, a type the file declares (`pkg.Outer$Inner`), a single-type import,
  `java.lang`, or (with no on-demand import that could supply it) the file's own package. Where an
  on-demand import could, the name stays as written and the row says it is unresolved.
  - `types`: each class, interface, enum, record and annotation type a project declares outside a
    method or anonymous class — `name` (binary), `simpleName`, `packageName`, `kind`, `extends` and
    `implements` (resolved), `annotations` (resolved), `annotationText`, `modifiers`, `isTopLevel`,
    `line`, `lastLine`, `module` (the Maven module whose `pom.xml` directory holds the file; `''` for
    the root), `link`.
  - `members`: each field (one per variable), constructor and method of those types — `owner`
    (binary), `name`, `kind`, `signature`, `type` (a field's element type, resolved), `returnType`,
    `parameters`, `parameterTypes` (resolved), `annotations`, `modifiers`, and the declaration columns
    (`fromLine`, `toLine`, `text`, `javadoc`, `annotationText`). Id: `<project>!<owner>#<name>(<parameter types>)`.
  - `annotations`: each annotation written on a type, member or parameter, with its attributes as
    written — `name`, `qualifiedName` (null where the file cannot say), `attributes` (`name=value`),
    `value`/`values`, `text`, `targetKind`, `targetId`, `targetName`, `owner`.
  - `imports` of a Java file carry, beside every language's columns, `name`, `isStatic`, `isWildcard`
    and `packageName`.
  - `configs`: every key of the project's `.properties` and YAML files, flattened to a dotted path
    (`server.ssl.enabled`, `servers[0].url`), with `value` as written, `document` (of a multi-document
    YAML file, from 0), `fileName`, `module` and `line`. YAML is composed, never constructed.
  - `projectFiles`: every file of the project, whatever its language — `path`, `fileName`,
    `extension`, `module`, `link`.
- **`from: jar`: the source a jar was compiled from.** The key is what a `jar` row (§5.18) carries: a
  `sourceKey` (`<jar path>!com/x/Cache.java`) or a `spanKey` (`…#<line>#<name>`). The file is looked
  for beside the jar as a `-sources.jar`, then under `roots:` in order, as §5.19 says, with §5.19's
  emits, columns and ids: `files`, `spans` (`context`, default 6), `declarations`,
  `calls` (the calls on the key's line, with `receiverType`, `argumentTypes`,
  `argumentTypesResolved` and `resolution: type` where the receiver's static type is known) and
  `locals`. `maxFileKb` defaults to 1024 for jar keys. A file in another language answers `files` and
  `spans`, with a warning for the rest; a file with syntax errors answers around them.

  ```yaml
  - { name: javaSourceSpan,  kind: source-tree, from: jar, emit: spans, roots: [src], context: 6 }   # key: a spanKey
  - { name: javaCallSitesAt, kind: source-tree, from: jar, emit: calls, roots: [src] }               # key: a spanKey
  - { name: upstream,        kind: source-tree, from: jar, emit: declarations,
      roots: [ { git: "https://github.com/acme/acme", ref: "v{version}" } ] }
  ```

  An argument's type is what the file shows: `new X(…)`, a literal, a cast, a parameter (a method's, a
  typed lambda's, a catch clause's), a local declared before the call, a field of an enclosing type.
  A method's return value, an inherited field, a parenthesized expression and a lambda's inferred
  parameter are unknown (`""`), never guessed. Expressions (`arguments`, `receiver`, `initializer`,
  a call's `text`) are as written, whitespace collapsed.

Cost: the first query of a git project pays for a shallow, blob-less fetch of the commit and one
fetch of the language files' contents; each file is parsed once, the first time an emit needs it, and
kept with the commit. A folder is listed and its files parsed again on each fetch. A repository of a
few hundred files is read, from a cold git cache, in about ten seconds.

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

### 6.7 What a relevance join costs — `semanticCalls`

A result's `cost` block reports **three** kinds of call, and each counts one kind of purchase and no
other:

| counter | what it counts |
|---|---|
| `apiCalls` | producer fetches — a call to a source outside this world, including a relevance search sent to a store outside it (`remote-search`, `elasticsearch`) |
| `llmCalls` | reasoning: the reductions of §7, a generative producer's rounds, a concept-mode search's expansion of each anchor into probe terms, and (on `ask`) the one call that wrote the Cypher |
| `semanticCalls` | **relevance searches**: one per anchor, per materialization |

One `semanticCalls` is **one search of the index**, which for the `vector` mode is one embedding of
the anchor's text plus one similarity scan, for `keyword` one fulltext scan, and for `agentic-rag`
one retrieval — whose judging loop ALSO spends `llmCalls`, so an agentic edge shows on both. The
three are kept apart because a reader budgets them differently: a fetch is somebody else's rate
limit, a reduction is reasoning spend, and a search is retrieval. Adding them together would make
every one of the three numbers worth less.

**It is one search per distinct anchor key, not per anchor row.** Two anchors carrying the same
phrase embed it once in a query; a different phrase is its own search. A producer with a `cache:`
TTL searches nothing at all inside its window, which is the lever: a repeated question over a
cached relevance producer costs zero searches, and the counter is how you see that it worked.

**`EXPLAIN` prices it before the query runs**, as `~n semantic search(es)` on the group, the stage
and the total. For a first-stage anchor set the figure is **exact** — the anchor's own text is the
key, so the count is the number of anchors and nothing has to be guessed — including for the
pinned shape `(c:Concept {value: '…'})`, where the anchor exists only because the query named it.
Only a LATER hop, whose anchors are the first fetch's records, makes the total a floor, and it then
reads `at least ~n` like the other two.

> A semantic query that reports `apiCalls: 0, llmCalls: 0` is **not** free — it is a query whose
> whole cost was retrieval. Read `semanticCalls`. (This counter is new: before it existed a
> relevance search was counted by neither of the others, so a Concept-anchored fetch reported two
> zeroes for seconds of real work, and `EXPLAIN` priced it at nothing.)

**A relevance search sent outside the world is an `apiCalls`.** A `remote-search` or
`elasticsearch` relevance producer (§5.16) is relevance-shaped — the anchor's text is the query —
but each search is a request to a store somebody else runs, which is the purchase `apiCalls` names.
So it is counted there, one per distinct anchor key, and never on `semanticCalls`: every relevance
producer lands on exactly one of the two. A request is counted when it is sent, so a search the store
refuses or times out on is still a call. `EXPLAIN` prices it before the query runs, as
`~n API call(s)`, on the same terms as a `semanticCalls` figure — exact for a first-stage anchor set,
the pinned `(c:Concept {value: '…'})` shape included. The one exception is a `remote-search`
declared `agentic: true` (concept mode), which searches once per probe term chosen while the query
runs: its figure is the first search per anchor and reads `at least ~n API call(s)`. Bound these the
way you would a fetch — with `maxAnchors`, a narrower anchor set, and a `cache:` TTL.

**Concept mode also spends `llmCalls`.** The probe terms a concept-mode search runs are chosen by a
model before the first search: one model call per distinct anchor, counted on `llmCalls` when it is
asked — so a call that fails is still counted — and listed in the call log by its purpose, never by
the anchor's text. `EXPLAIN` prices it as one model call per distinct anchor, an exact figure for a
first-stage anchor set, and the group line says how many of its model calls are expansions. Because
the cost gate reads the model-call total, a concept-mode search over many anchors can be refused
as `TOO_EXPENSIVE` like any other model spend — narrow the anchor set, or opt in with
`{ai: {materialize: true}}`.
### 6.8 Memory — what the assistant remembers, as a relevance source

What the assistant remembers about the acting user is a relevance source like any other: the index
`memory`. A realm reaches it through the same producer kinds, the same `via` selector and the same
per-match edge vocabulary as documents and email threads, so a query that knows
`(:Concept)-[:RELEVANT_TO]->(:Document)` already knows memory.

```yaml
# producers/memory.yml
- name: memoryVector
  kind: vector
  index: memory           # the acting user's memory, in the context they are in
- name: memoryKeyword
  kind: keyword
  index: memory
- name: memoryAbout
  kind: participant       # memories that MENTION a known entity, by its resolved id
  index: memory
  identityField: entityId
```

**`Memory` is a shared parent label; each memory system is a child.** The standard model declares
`Memory` and the assistant's own `DiceMemory` with `parents: [Memory]`. A realm that brings another
memory system declares its own child — `ZepMemory`, `parents: [Memory]` — over its own producer
(a `remote-search` with `recordScoreField`, or a host-provided index). Ancestors are physically
present (LABELS_AND_COMPOSITION §2), so a query may name the parent and be answered by EVERY
system that has a join, or name one child and read that system alone:

```cypher
MATCH (:Concept {value:'coffee'})-[r:RELEVANT_TO]->(m:Memory)        -- every memory system
RETURN m.source, m.text, r.score, r.mode ORDER BY r.rank

MATCH (:Concept {value:'coffee'})-[r:RELEVANT_TO]->(m:DiceMemory)    -- the assistant's own
RETURN m.text, m.confidence, r.score

MATCH (p:Person {name:'Ada Lovelace'})-[:REMEMBERED_IN]->(m:Memory)  -- by fact, not by name
RETURN m.text
```

**The data contract every memory label carries.** `id` (identity), `text`, `confidence` (0..1),
`status`, `created`, `revised`, `source` (which system holds it — `dice`, `zep`, …), and when the
system knows them `validFrom` / `validTo`, `mentions` (names) and `entityIds` (resolved ids). A
child may add its own properties; it may not drop these. The per-match data is on the EDGE:
`r.score`, `r.mode`, `r.rank`, `r.snippet`, `r.matchedTerms`, and for the fused lane `r.probes`
(which arms found it).

**Three questions, three modes — the same three as a document.** The semantic lane (default,
`via:'vector'`) answers "what do you remember ABOUT X": a vector arm and a term-overlap arm over
the same scoped memories, fused by reciprocal rank, `r.mode:'fused'`; a fact both arms find
outranks a lone high hit, and `r.score` stays a similarity where one exists. With no vector arm the
lane falls back to lexical and says so (`r.mode:'keyword'`). The lexical lane (`via:'keyword'`)
answers "memories that MENTION X": every assertable term present, or an honest empty. The
`participant` kind answers "what do you know about THIS entity": memories whose resolved mentions
include the anchor's id — a fact, never a name's neighbourhood. An `agentic-rag` producer over
`memory` is accepted and answers with the semantic lane today; `r.mode` reports what ran.

**Scope and curation hold at the source.** A memory is read in the acting user's own context, and
no user — or a user with no context — reads nothing (§6.4). Reads are ACTIVE memories only. A
`status` constraint on the memory node pushes down and relaxes that to the statuses it names;
a CONTRADICTED memory is known-false and never answers, even when asked for by name — the rule the
scope rewriter already holds persisted `Proposition` nodes to (§15). A child label from another
system maps its own lifecycle onto the same vocabulary: ACTIVE for a current fact, SUPERSEDED or
STALE for a retired one, CONTRADICTED for one proven false.

**The lifecycle is declared, and every memory label is held to it.** `Memory` declares
`lifecycle: { active: [ACTIVE], never: [CONTRADICTED] }` (DECLARING_TYPES.md §3.3a), and a child
inherits it. So the rule above is not only the source's: a query naming `:Memory`, `:DiceMemory`
or a realm's `:ZepMemory` has the same curation predicate written into it that `:Proposition`
gets, whichever system fetched the node and wherever the node came from — a persisted projection
of a memory system's facts included. A memory node must therefore carry `status`; one without it
answers nothing.

**Systems a standard child exists for.** Beside the assistant's own `DiceMemory`: an Omnigraph graph
(`OmnigraphMemory`, a `remote-search` over the graph's stored BM25 query); markdown memory
(`MarkdownMemory` and its children for Claude Code's memory directory, OpenClaw's `MEMORY.md` and
daily logs, a Cline/Roo memory bank, plain notes — `files` search producers over the world's
`data/memory/`); a self-hosted Graphiti server (`GraphitiMemory`, `remote-search` over its `/search`,
with `valid_at` / `invalid_at` as `validFrom` / `validTo` and a fact Graphiti has invalidated
read as SUPERSEDED); Zep Cloud (`ZepMemory`, the same over Zep's graph search, keyed, with Zep's
score on the edge); and the MCP memory server (`McpMemory`, a `files` producer with `unit: line`
over its `memory.jsonl`, one entity per memory, `require: {type: entity}` leaving relation lines
out). Each is its own realm under embabel-worlds; each maps its system's own state onto the one
contract and lifecycle above, which is the whole of what a new system has to do.

Cost: one search per anchor, as for every relevance edge; the semantic lane is two probes over one
store. Nothing leaves the deployment for the assistant's own memory; a child over a remote memory
service pays that service's call per anchor, which `apiCalls` counts.

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

- **`{ai: {hint, model, confidence, fresh, voice, wordcount}}`** — *steer and tune* the
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
                                confidence: 0.8}}]->(rec:Movie)
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
- **No `temperature`.** The host sets no sampling temperature; a `temperature` key in the map is
  stripped with the rest of the steering and warned about as an unknown key, never applied.
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
(`hint`/`voice`/`realm.*`/`model`) makes the result transient — it never touches the
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

For a `remote` producer that declares scalar `queryArgs` (`string`, `integer`, `number`,
`boolean`), keys in the edge's `realm` map are **request inputs**, not prompt parameters or record
identities. Each supplied key must be declared and have a scalar value coercible to its declared
type. It can be a literal, a query parameter, or a property of a node bound in an earlier clause; an
unresolved, missing, non-scalar, or ambiguous value is rejected rather than silently dropped to
make an unfiltered request. A value the query computes (a function call, arithmetic, or a `WITH`
variable such as a date derived from `date()`) is not accepted: write it as a literal, for example
`{realm: {from: '2026-07-01'}}`, and the rejection says so. Omit an unused optional input to retain the source's default.
An input named in `requiredQueryArgs` must be supplied: a read without it is refused, naming the
missing `{realm: {…}}` entry, and never sent bare. For
example, a declared string `segment` can narrow a contact-list operation:

```cypher
MATCH (me:AssistantUser)
MATCH (me)-[:HAS_MAILBOX_CONTACT {realm:{segment:me.segment}}]->(c:MailboxContact)
RETURN c.email
```

Only declared `realm` inputs are forwarded alongside the producer's own arguments;
distinct input sets stay separate in the cache. A
single query cannot use different input sets for the same producer. A successfully executed
upstream query that binds no input rows makes **no downstream request**; a virtual upstream
stage that has not executed yet is **not evidence of absence** and cannot license a broad
request or a clean empty answer. If a graph predicate targets a source field already set by an
explicit request input, that input is not overwritten; a conflicting predicate is still checked
on the fetched graph rows, not claimed as a source-side match. A **declared filter** is a field named by `queryArgs` or `sourceFilters`. When a target-alias
condition on a declared filter was not sent — including a parameter or expression on its right-hand
side — the answer depends on whether the read was complete. After a **complete** read the graph
applies the filter exactly, so a miss is a real miss and the unsent filter costs only calls and
latency. After a **bounded** read — a page cap or declared limit reached on a full page, or a
LIMIT-capped fetch that came back full — a read that cannot establish a match carries a
`UNPUSHED_FILTER` warning, even when the source returned zero records: a bounded page fetched
without that predicate does not prove the requested record is absent. A failed read carries its failure diagnostic; a skipped read does not count as
source evidence. Neither is reported as an unfiltered successful read. A conflicting explicit
`realm` input preserves its own request value and does not suppress the warning after a
bounded read. Without `queryArgs`, existing producer-specific `realm`
steering keeps its ordinary meaning above.

A learned OpenAPI collection exposes scalar query parameters as declared `queryArgs`
except paging controls and conventional free-text search inputs, which are not treated as
filters; parameters the API marks required are also listed in `requiredQueryArgs`. A matching equality on a numeric or boolean response field, or an enum-constrained string field,
may be sent as a source filter; an unconstrained text equality is still checked on returned
records. An explicit `realm` input takes precedence over an inferred filter on the same field:
a conflicting graph predicate remains a graph filter and cannot silently change the request.

A GET of one object beneath a keyed parent (for example, `GET /containers/{containerId}/usage`)
can expose a navigable singleton edge from that parent even when the returned object has no own
identity key. Its lookup uses exactly one parent key per call, and that key is echoed on each
returned record, so results from different parents cannot join to each other. When the record
already has a property with the key's name, or the name is reserved, the echo uses a distinct
suffixed property name (for example `id_2`) and the edge joins on that name.
Learned properties declared as OpenAPI `date`, `date-time`, and `time` remain strings in the graph.
Use ISO string comparisons only where the source guarantees a consistent representation; otherwise
normalize explicitly before comparing or ordering.

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
before judging. Their calls are counted against the query's model-call limit before any is made
(§9), so a judgment over more rows than the query may pay for is refused rather than spent.

**A model that fails refuses the query.** When the call behind a judgment errors, the answer depended
on that judgment, so none is returned: a retryable `SOURCE_UNAVAILABLE` names the primitive and the
criterion. Never a `0` from `count(*)` over an `ai.relevant` filter, a column of `0.0` scores, or empty
labels — each of those would read as a real judgment. A run that was cancelled, or stopped by a
budget, keeps its own refusal.

Within an answer the model did return, a row it left **unjudged** is scored at the **keep threshold**
(0.5), so an omission never silently *hides* a result. The threshold,
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
| `classify(item, labels [, rubric])` | one label | exactly one label from the closed set `'a,b,c'` |
| `extract(text, what)` | list | the distinct things asked for (deduped) |
| `themes(text [, focus] [, count])` | list | the recurring cross-item topics (labels only) |
| `cluster(text [, k])` | list of maps | semantic groups, each with a COUNTED size and examples |
| `score(item, rubric)` | number 0–1 | one ordinal judgment of the whole group |
| `holds(item, question)` | boolean or null | a three-valued verdict on a claim |
| `relevant(item, criterion)` | list | only the items matching a subjective criterion — over nodes, the group's own nodes |
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
— no rows matched, or the property carries no values — a PROSE reduction (`summarize`, `synthesize`,
`render`) answers an `UNAVAILABLE:` sentence saying there was nothing to aggregate, and every TYPED
reduction (a score, a verdict, a label, a list, a pick) answers `null`. A sentence in a score column
would sort among real scores, and no comparison could tell it from an answer; `null` is what an
empty group means. A typed reduction whose model fails is also `null`, flagged `REDUCTION_FAILED`
(§9), so it is never bare. Neither is ever a fabricated verdict or digest, and ask surfaces report
the result as an honest miss rather than an answer. An empty LIST accumulates as empty: `collect()` of zero rows never manufactures evidence.

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

#### Judging nodes, not only text

`relevant`, `classify`, `holds` and `score` accept a NODE variable as their item, not only a property:

```cypher
MATCH (i:Issue)<-[:RAISED]-(:Attendee)-[:WORKS_FOR]->(:CustomerAccount)-[:HAS_CASE]->(c:SupportCase)
WHERE c.status IN ['open', 'pending']
WITH i, relevant(c, 'the same problem as: ' + i.summary) AS tracked
UNWIND tracked AS tc
MATCH (tc)-[:ASSIGNED_TO]->(e:Engineer)
RETURN i.summary, tc.subject, e.name
```

- **The model reads each node whole**: its labels, its properties, and what the world's types declare
  they mean — the `description` of the type and of each property (§ types). A `status: pending` is shown
  with its declared meaning, so a description written for query authors is read by the judge too; an
  undeclared type is shown with its labels and properties alone. Who may see a node (its scoping
  properties) and embeddings are never shown.
- **`relevant` over nodes keeps the group's own nodes.** The result is a subset of the nodes the group
  matched — the model can only keep what it was shown, by its position in what it was shown — so it can be
  `UNWIND`ed, traversed from and re-matched like the nodes it came from, and it is scoped as they were.
  A group whose candidates were all rejected keeps an empty list. A group that could not be judged is
  never an empty list: its cell is null with the reason in the result, or — where a later clause reads
  the kept nodes — the query fails and says so, since an answer built on a silently missing group would
  look complete.
- **Projected in the final `RETURN`**, the kept nodes come back as nodes.
- **A node is longer than a title**, and the cost check prices what is shown: a reduction over nodes is
  quoted on the size of the nodes as rendered, and a query over the inline limit is refused before it
  runs, never cut down to fit.
- What does NOT flow on: kept nodes from a variable that no node pattern bound (an `UNWIND`ed list, a
  comprehension), and any structured result (`correlate`, `regress`, `cluster`, `argmax`). Re-binding the
  matched name itself (`UNWIND tracked AS c` after matching `c`) is refused with a request to use a new
  name.
- **Inside a subquery.** A judgement may sit inside a unit `CALL { … }`, `OPTIONAL CALL { … }` or
  `CALL () { … }`, nested at any depth — the groups are read over the rest of that body. So a plan whose
  steps are unit subqueries can judge in one step what an earlier step projected. Refused, each for a
  reason and before any model call: an importing body (`CALL { WITH x … }`, `CALL (x) { … }` — a node
  grouped under two outer rows could collect different values and keep only one answer); inside
  `EXISTS {}`, `COUNT {}` or `COLLECT {}` (no clause boundary to read the groups up to); inside
  `CALL {} IN TRANSACTIONS` or any other braces; and a judging body that writes and runs more than once
  (later runs would form groups the judgement never saw).

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
  what, focus, rubric, criterion, question — with one exception, below. A row expression there is not
  evaluated per row (there is nothing to evaluate it against once the group is reduced), so write the
  words themselves.
- **The exception: a judgement's criterion may read the GROUPING KEY.** `relevant`'s criterion,
  `classify`'s rubric, `holds`' question and `score`'s rubric may be an expression over the clause's
  grouping keys — `WITH i, relevant(c, 'the same problem as: ' + i.summary) AS tracked` asks one question
  per issue. It is evaluated once per group, from that group's keys only. An expression that reads a
  variable the clause aggregates over (`relevant(c, 'like ' + c.title)` grouped by `i`) is REFUSED before
  the query runs: it has a different value on every row of the group, and none of them is the group's. A
  group whose criterion evaluates to null is not judged — its cell is null and the result says why —
  because no criterion would keep everything. `classify`'s label set is always a literal: it is the
  closed set every group's answer is checked against.
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

**A `classify` judgement asks the same question every run.** The same evidence reaches the model
cleaned the same way and in the same order, and the answer is snapped onto the declared label set,
so a label never changes because the question did. It is not guaranteed to be identical run to run:
the host sets no sampling temperature, which current models ignore or reject. A materialised view
refreshed on its `ttl` keeps its labels between refreshes.

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

### 7.8 `ai.fromText` — project a typed graph shape out of text

```cypher
MATCH (a:CustomerAccount)-[:HAS_CASE]->(c:SupportCase)-[:HAS_MESSAGE]->(m:SupportMessage)
WHERE c.status IN ['open', 'pending'] AND m.fromCustomer
CALL ai.fromText(m.body, '(m)-[:NAMES]->(k:Competitor)') YIELD k
RETURN k.name AS competitor, count(DISTINCT a) AS accounts
```

**Means:** "read this text, and give me the elements of this shape that it states" — as graph elements
the rest of the query matches, filters, joins and counts like any other. Standard procedure-call syntax,
so it works wherever a query runs: views, DERIVE rule bodies, handlers, `kg_query`.

**The pattern** is a string literal: directed single hops of one type, at most one label per node, no
inline properties, in one connected piece. Each variable is one of three things:

| Variable | What happens |
|---|---|
| no label (bound earlier in the query) | an **anchor**: what the text projects attaches to it; it is never created |
| a **projected** type | **created** for this run only, typed by its declaration |
| a **world** type | **resolved, never invented**: the text's mention is matched through the type's spine; a miss is reported |

**YIELD** names the pattern variables the call binds (`YIELD k`, `YIELD i AS issue`). Variables not
yielded do not enter the query's scope. An anchor is not yielded — it is already bound. `YIELD *`,
`YIELD … WHERE` and `OPTIONAL CALL` are refused; filter in a following `WITH … WHERE`.

**Guarantees:**

- **Nothing is stored.** Created elements exist for the run that made them and no other: graph counts are
  identical before and after, and a run never sees another run's projection.
- **Typed before anything is asked.** Every label and relationship in the pattern must be declared (below);
  an undeclared one, a world type with no spine or no description, or a pattern that creates nothing is
  refused before any text is read or any model call is made.
- **A row reaches only what its own text projected.** One extraction per distinct text; two rows with the
  same text share it.
- **Cardinality is the declaration's.** A relationship declared `many: false` attaches at most one target per
  source; when the text gives several, none is attached and the outcome is reported as ambiguous.
- **Provenance.** Every created element carries `sourceSpan` (the words it was read from) and `extractedBy`
  (the model role and model that read it).
- **Outcomes are not collapsed into empty.** A world mention its type's identity policy refuses (a freemail
  address on a domain-keyed spine) is reported `PROJECTION_DECLINED`; one that matches no stored entity,
  `PROJECTION_UNRESOLVED`; several candidates where one is allowed, `PROJECTION_AMBIGUOUS` — each a warning on
  the result. A value outside a declared closed set is dropped and reported `UNPARSEABLE_ANSWER`. A text that
  states nothing is an empty answer; a model call that fails refuses the query with a retryable
  `SOURCE_UNAVAILABLE`, never an empty one.
- **Resolution is spine-only for now.** A world-type mention resolves through its type's spine key
  (`normalize`, `require`, `exclude`) and nothing else: a company named only by name is unresolved.
- **Cached and priced.** The same text, pattern, declarations and model are not asked twice. Texts not
  already projected are counted against the query's model-call limit before any is asked (§9); over it,
  the query is refused `TOO_EXPENSIVE` rather than truncated. At most 200 distinct texts per call.
- **The model is a role's**: `vc_extraction` (remappable per world with `llmRoles`; where nothing maps it, it
  resolves as `vc_execution` does), or the role one call names with a third argument,
  `ai.fromText(text, pattern, {role: 'chat_best'})`. The option takes a ROLE only: a name that is not a role
  this world knows is refused, and a model name is refused as one. A call naming a role is a different
  question for caching, even when it lands on the same model.
- **Not in raw mode.** A raw-mode statement (the openCypher conformance surface) treats `ai.fromText` as an
  unknown procedure.
- **Where it may be called.** At the top level of a statement, or inside a `CALL { … }` subquery — a unit
  subquery (whose projection the rest of the statement, later subqueries included, can read), or an
  importing one (`CALL { WITH m … }`, reading each outer row's text with that row's anchors). A subquery no
  row reaches reads no text. Refused, each for a reason: inside `EXISTS {}`, `COUNT {}` or `COLLECT {}`
  (there is no point before the clause to read the inputs at); inside `OPTIONAL CALL {}` (a row that
  projects nothing would have to survive); inside `CALL {} IN TRANSACTIONS` (it commits as it goes, and a
  projection is never committed); inside `CALL (x) {}` (write it `CALL { WITH x … }`); and after a write
  anywhere earlier in the statement (put the call before the first write).

**Declaring local types.** A type `ai.fromText` may create is a realm type marked `projected: true`; its
relationships are declared on it with `relationships:`:

```yaml
- name: Attendee
  projected: true
  description: Someone from the customer's side, in a meeting or an email.
  properties:
    name: "Full name, as written."
  relationships:
    RAISED:    { to: Issue, many: true, description: "Problems this person raised." }
    WORKS_FOR: { to: CustomerAccount, many: false, description: "The customer account they work for." }

- name: Issue
  projected: true
  description: A problem the customer raised, not a request or a wish.
  properties:
    summary:  "One line: what is wrong, in the customer's words."
    severity: { type: string, enum: [high, medium, low], description: "How much it blocks them." }

- name: Competitor
  projected: true
  description: A rival product the customer names.
  properties:
    name: "Its name, as written."
  relationships:
    NAMES: { from: SupportMessage, many: true, description: "A competitor named in the message." }
```

Rules, each refused at load as an error against the declaring realm:

- A projected type has a description, and every property has one — the model reads them.
- It has no producer, join, population, spine, parent, method or lifecycle, and no join targets it; nothing
  persists it. It may not reuse a world type's name, and may not declare `sourceSpan` or `extractedBy`.
- A relationship names exactly one of `to:` (this type is the source) or `from:` (this type is the target —
  how an edge from a world type is declared without editing that type), a description, and a type this world
  declares. `many` defaults to `true`.
- `relationships:` on a type that is not projected is refused.
- `enum: [...]` on a property is the `values:` shorthand for a closed set.

An appliance that predates `projected:` reads a type file strictly and refuses the whole file, rather than
loading the type as an empty world type; keep projected types in a file of their own if the realm must also
load on older appliances.

### 7.9 Writing projected types inside a query — one query is a pipeline

A query may `CREATE` and `MERGE` projected types (§7.8), and `SET` what it made. The writes land in
the run's scratch: the rest of the same query sees them, as Cypher's read-your-writes promises, no other
run ever does, and nothing reaches the store. "Read-only" on the query surfaces means read-only **with
respect to the store**.

That is what makes one ordinary query a pipeline: project text, build on it, read what was built.

```cypher
CALL ai.fromText($notes, '(t:Attendee)-[:RAISED]->(i:Issue), (t)-[:WORKS_FOR]->(a:CustomerAccount)')
  YIELD t, i, a
WITH DISTINCT i, a
MATCH (a)-[:HAS_CASE]->(c:SupportCase) WHERE c.status IN ['open', 'pending']
WITH i, relevant(c, 'the same problem as: ' + i.summary) AS tracked
UNWIND tracked AS tc
CREATE (i)-[:TRACKED_BY]->(tc)
WITH count(*) AS linked
MATCH (t2:Attendee)-[:RAISED]->(untracked:Issue)
WHERE NOT EXISTS { (untracked)-[:TRACKED_BY]->() }
RETURN untracked.summary, untracked.severity, t2.name, t2.role
```

`Attendee` and `Issue` are projected types with no stored instances, so `MATCH (untracked:Issue)` reads
exactly what this run made — the label is the isolation. Steps can also be written as unit subqueries,
each run in order:

```cypher
CALL { CALL ai.fromText($email, '(t:Attendee)-[:RAISED]->(i:Issue)') YIELD t RETURN count(*) AS projected }
CALL { MATCH (i:Issue) … CREATE (i)-[:TRACKED_BY]->(c) RETURN count(*) AS linked }
MATCH (u:Issue) WHERE NOT EXISTS { (u)-[:TRACKED_BY]->() } RETURN u.summary
```

**What may be written** — anything else is refused before the query runs, with the rule it broke:

| Write | Allowed when |
|---|---|
| `CREATE` / `MERGE` a node | every label on it is a projected type |
| `CREATE` / `MERGE` a relationship | it is declared under `relationships:` on a projected type (§7.8), so one end is always projected — never an edge between two stored nodes |
| `SET` / `REMOVE` | on elements this run created |
| `DELETE` | of elements this run created; never of stored ones |

- **World types are never created.** `CREATE (:CustomerAccount …)` is refused in a query exactly as
  `ai.fromText` resolves a world type instead of inventing one.
- **Declared properties only.** A property set on a projected node must be declared on its type; a
  required property left `null` raises a `PROJECTION_INCOMPLETE` warning naming the row, rather than
  being admitted silently.
- **`MERGE` on a projected type is keyed construction** — one node per distinct key, how a query collapses
  duplicates.
- **Relationship ends are checked by type, and a variable is typed by where it came from.** `tc` above
  has no label written, but it was unwound from `relevant(c, …)` over `SupportCase` nodes, so it is a
  `SupportCase` and `TRACKED_BY` is admitted. A variable fed from a parameter or a literal list has no
  such origin and is refused; write the label (`MATCH (x:SupportCase)`) if you need one.
- **Use fresh names across stages.** A name dropped by a `WITH` and bound again by a later `MATCH`, or
  reused across `CALL {}` bodies, is refused (§4) — hence `untracked` and `t2` above.
- **A model call may not feed the rest of a statement from what that statement wrote.** A judgement or
  reduction written after a `CREATE`, whose result a later clause reads, is refused rather than run early.
  One whose result is only returned at the end is computed after the statement and may read what it
  made. Elements projected by `ai.fromText` are not "written" in this sense — the query above judges
  stored cases and links projected issues to them.

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

A view's query is checked when the realm is validated: a label that is a near miss for one the
realm or its world knows (`GitHubIsue` beside `GitHubIssue`) is an error at the view's file and line,
naming the likely intended label — at query time the same name is refused (§9), so a view that
carries one could never answer.

**A view's own variables are private to it.** Only what the view returns becomes the caller's
alias; every other variable its body declares is renamed for each use, so inlining never lets it
meet the caller's. `MATCH (o:VaOwner {name:'oc'}) MATCH (x:owned_tier1) RETURN o.name, x.name`
answers the same whether or not `owned_tier1`'s body also names an `o`, and two uses of one view
in a query never share its internals. A body that returns an alias of a node (`RETURN k AS s`) is a
node view like one that returns `s`.

**What a view may not be used as.** A view is refused, with what to do instead, rather than
answered quietly wrong:

- **A node view named like a label the world already holds.** Matching that label anywhere —
  including inside other views — would silently mean "the nodes this view selects". Rename the view.
- **A view that returns columns, matched as a label.** Its rows are not nodes, so `MATCH (x:that_view)`
  could only answer nothing; run it by name instead.
- **An argument the view never reads**, or **a fractional number for an `int` parameter** — the first
  would be ignored and the second truncated, so the answer would not be the one asked for. A view
  parameter holds one value: a view that needs a list should read it inside its own query, not as
  `IN $p`.

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
  cache, and so does a narrower question over the same key where §5.13 allows it; no producer call fires.
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

What a finished query reports it cost — `apiCalls`, `llmCalls` and `semanticCalls`, and which calls
land on which — is §6.7.

**What a refusal carries.** A refusal is read as often by a model about to rewrite the statement as
by a person reading a message, and a caller that regenerates has nothing to work from but the
refusal itself. So three things hold of every refusal this document names, whatever its kind
(`BUDGET_EXCEEDED`, `TOO_EXPENSIVE`, `INVALID_QUERY`, `SOURCE_UNAVAILABLE`), and each can be
observed by issuing a query and reading what comes back:

- **A refusal names its measure, its size and its limit, and it carries a lever.** The measure is
  what was counted — distinct keys, records, rows, match steps, model calls, pairs, rounds,
  characters — and it is named, because one statement can pass several different bounds and each has
  a different fix: `maxAnchors` counts distinct keys and not records, and its refusal says so. The
  size is what the statement would have spent against that measure; the limit is the bound it
  passed. The lever is what to change, given as a spelling, a clause or a declaration rather than as
  a category of them: a predicate to push, a `LIMIT` to add, a `MATCH` to narrow, an aggregate to
  move earlier, a second declared door to pin with `{via:'…'}`, a cap to raise deliberately. A lever
  applies to the statement it was given for — taking it and re-issuing is how a refusal is answered,
  so a lever that leaves the same statement refused the same way is a defect in the refusal rather
  than a matter of wording. It is also a lever the recipient can take: a source that applies no
  filters declares `pushdown: []`, and a door read whole declares `readWhole: true`, and each is then
  advised nothing, because advice to write a rule the source cannot apply, or one the door already
  declares, is advice no author can act on.
- **The same statement is refused the same way.** A refused statement, re-issued unchanged against
  unchanged declarations, is refused again with the same kind, the same measure and limit, and the
  same text. A refusal is a property of the statement and of what the realms declare, not of the
  attempt, so two identical attempts never disagree about what was wrong, and a caller that rewrites
  against a refusal is never sent after a bound it has already cleared. Where the outcome genuinely
  depends on what a source or a deployment did — a throttled call, a source that is down, a time
  bound one host sets and another does not — the result says which of those it was, and says it as
  something other than a fault in the statement.
- **A bound is labelled as a bound.** Where a figure a refusal or a warning carries is a floor and
  not a total, it says so in its own words — "at least 50001 row(s)", "of the records the source
  answered" — and never as a plain number. A count stopped one row past its budget (§13.7), an
  aggregate over a truncated read, a membership derived from incomplete facts: each is a floor, and
  a floor read as a total is a caller re-planning against a price nobody quoted it. The converse is
  the same guarantee: a figure given plainly is exact.

**Caps (per join):**

- **`maxAnchors`** (default 200) — refuse, before any call is made, a join that would ask its
  source for more distinct keys than this (a fan-out guard; pin/filter the anchor).

  The cap is spent in **distinct keys, not records — and not anchor rows either**. A per-key source
  is asked once per distinct key however many anchors share it, and the cap exists to bound those
  calls, so a thousand stored anchors in three categories cost three against it and every anchor
  keeps its records, while a thousand anchors with a thousand keys are refused, by the keys counted.
  The refusal says what it counted: the join *would ask the source for N distinct keys, exceeding
  `maxAnchors`*. That distinction decides what helps. Pushing a predicate on the TARGET makes each
  call cheaper and leaves the NUMBER of calls exactly as it was; only narrowing the anchor set — or
  reaching the target through a different door — changes whether the query is refused.

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
- **`maxFanoutTotal`** (default 5 000) — the most nodes one materialization of this join may create,
  counting each fetched record and every child its `brings:` would make a node of (primary +
  brought). A fetch that would create more is **truncated at the cap, never refused and never
  silent**: the records are materialized in anchor-key order until the next would pass the cap, the
  rest are held out of the graph, and the result carries `PARTIAL_RESULT` (`TRUNCATED`) naming the
  cap, how many records the source answered, how many were kept, and the join. A count over the
  target is then a lower bound, and an aggregate over it is gated as any truncated read is (§9,
  diagnostics). A fetch exactly at the cap is complete and carries no flag. An anchor the query
  pinned by literal whose records were held out gets no row rather than a row of zero, since its
  answer was not "none".

  The cap counts **nodes, not calls**, which decides what it can and cannot do. How many records an
  anchor answers is unknown until the source answers, so the engine cannot refuse this cap before
  spending the way it refuses `maxAnchors`; the calls are bounded by `maxAnchors`, and this bounds
  what they are allowed to put in the graph. Narrowing the anchor set is what lowers both. A
  variable-length traversal (§5.12) spends the same cap cumulatively across its hops, and a single
  hop that is itself too wide is truncated here as well.

**Predicate pushdown, and what it does *not* change:** a producer may declare rules mapping query
predicates on its target to the source's own query language, so a `WHERE` scopes the fetch at the
source instead of after it. Equality, ranges, `CONTAINS`, and **membership in a list-valued
property** (`'OLDER_ADULT' IN t.ageGroups`) are all pushable when a rule exists for them.

The guarantee is that **pushdown changes cost and never rows**. Anything a source cannot answer is
still applied to the materialized graph, so the same query returns the same rows whether it was
pushed or not; only the number of records fetched differs. A value that does not fit the rule's
declared shape is left to the graph rather than embedded in a source query it would corrupt.

**And the spelling does not change the fetch either.** A predicate written over a name a `WITH`
introduced — a renamed node (`WITH t AS u WHERE u.status = 'open'`) or a projected property
(`WITH t, t.status AS st WHERE st = 'open'`) — is the predicate on the property it names, and is
pushed exactly as `WHERE t.status = 'open'` is. Splitting a query into a pipeline for legibility
therefore costs what the one-line spelling costs.

A projection that **computes** holds a different value from the property, so it is not pushed:
`toLower(t.status) AS st`, an arithmetic, an aggregate, a `coalesce`. Pushing such a comparison as
the property's would drop rows the query keeps, which is a wrong answer and not a cheaper fetch. It
is applied to the materialized graph instead, and SAID so — on `EXPLAIN`'s residual line and in the
cost note of a read that filtered after fetching — because a filter applied after a wide fetch that
no surface reports is the one cost a realm author cannot find.

**A producer whose source applies no filters declares `pushdown: []`.** The empty list is a
statement and an absent key is not: without the key the engine treats every residual as a rule not
yet written — a load warning, a cost note with advice on each read of 25 records or more, and an
instruction on `EXPLAIN`'s residual line. With it, the engine accepts that every predicate on the
target is applied in the graph by construction, and says so without advising anything. The cost
note is still recorded on such a read, since it is the evidence that the read was complete and the
graph did the filtering, which is what makes an empty result an exact one. The declaration cannot
conflict with rules: it is the `pushdown:` key itself, holding either rules or nothing.

**A door that should be read whole declares `readWhole: true`.** A field on the producer, beside
`pushdown:` — not inside `cache:`, because it changes what the source is asked — on every kind that
declares `pushdown:` rules. Default false. Every read of the door asks the source for the key's whole
collection; the door's rules stay declared and none is sent; the graph applies every filter. What a
caller sees:

- every read of the door is keyed the same, so with a `ttl` or `immutable` cache one read serves every
  view of it in any order — a family of windowed views costs one read, not one per window;
- the request carries no filter from the rules, whatever the query's `WHERE`;
- the quote and `EXPLAIN` show the filters on the line for what the graph applies, none on the line
  for what the source applies, and name the declaration instead of advising a rule;
- the read keeps its cost note, which says the door is declared `readWhole: true` and advises nothing;
  as with `pushdown: []`, the note is the evidence that the read was complete, so an empty answer is
  exact;
- a filtered count over the door is counted in the graph from the whole read, because the source is
  not asked to filter what it would count.

Loading reports two things about it: `readWhole: true` without a `ttl` or `immutable` cache is a
warning — nothing keeps the read for the next view, so the door only fetches more — and with
`requiresFilter: true` it is refused, since the door would refuse every read. A read-whole door is not
warned for declaring no rules or for leaving source filters unused. The config catalog's
producer rows and `realm_status`'s surface name the doors that declare it.

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

An `OR` of equalities on ONE property of ONE fetched variable (`c.status = 'open' OR c.status =
'closed'`) is the same set spelled differently, and is pushed exactly as the `IN` it spells: the same
rule, the same OR group in the qualifier, the same residual, with a bound parameter among the arms
read as its value. An `OR` that mixes properties, variables or non-equalities — `c.status = 'open'
OR c.priority = 'high'`, `c.status = 'open' OR NOT c.closed`, an arm on another node — pushes
nothing and stays with the graph, since no fetch narrowed on one property's values returns every
row such a disjunction admits. The two spellings are also declined together: a rule declaring only
`EQUALS` absorbs neither, because the engine never splits a set into one call per value.

**What "absorbed" means, and why it is load-bearing.** A rule that renders nothing is reported as
having absorbed nothing, and the engine plans accordingly. This is not bookkeeping: the residual —
what the source did *not* take — is what decides whether a `LIMIT` may be pushed and whether a count
may be asked of the source instead of fetched. A rule that claimed a filter it did not send would
license the engine to read one page and call it the whole answer.

**A pushed `LIMIT` is a count of records that suffice, and a `SKIP` adds to it.** When every
predicate on the target is absorbed, a terminal `LIMIT n` bounds the fetch at `n` records and the
page walk stops at the page that holds them. `SKIP s LIMIT n` bounds it at `s + n`: the skipped rows
must be read to be skipped, and the number that suffices is written in the query, so the bound
widens rather than lapsing. `ORDER BY r.v SKIP 1000 LIMIT 10` over an offset-paged source that
declares and honours `orderedBy: v asc` reads the pages holding the first 1,010 records, not every
page. The store still applies `SKIP` and `LIMIT` to the rows. What the fetch can count is a `SKIP`
written as a literal in the top-level `RETURN`, or a parameter the caller supplied (substituted before
the query is read). A `SKIP` it cannot count — an expression (`SKIP 999 + 1`), a `SKIP` in a `WITH`,
a subquery or one arm of a `UNION`, a `RETURN SKIP` beside a `LIMIT` written in an earlier `WITH`,
or a sum too large to hold — never under-counts: it releases the bound, and the fetch reads the
source whole and still answers right.

**An existence test is capped at one record per key, and asked per key only where a page walk
could starve a key.** `EXISTS { (a)-[:R]->(:T) }` needs one record per anchor key to answer, so the
fetch behind it is capped at one. Where the source **pages**, the keys are asked one per call: a
batched page walk would stop at page one and declare the keys not on that page empty. Where the
source does not page — one call returns everything it holds for the keys asked — a batch under the
cap is complete per key, so the keys are asked in batches of `maxKeysPerCall`: three hundred
anchors on such a source are six calls of fifty, each anchor in exactly one, not three hundred. A
source declaring `batchSafe: false` is asked one key per call whether it pages or not, since that
declaration says a batched answer is not complete per key.

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

**Which kinds may declare `aggregates:`.** The capability is source-agnostic; the ABILITY to honour
it is not.

| kind | may declare | why |
|---|---|---|
| `remote` (`api`) | **yes** | the capability declares the source's own aggregate endpoint and where the number sits in its response |
| `sql` | **yes**, on a KEYED table read | the statement is generated, so `count` compiles to `SELECT COUNT(*) … GROUP BY <keyColumn>` with the same keys, the same governance `where:` and the same pushed filters |
| `cypher`, `sparql`, `graphql` | **no, not yet** | each could answer one — `count(o)`, `COUNT(DISTINCT ?x)`, a Relay `totalCount` — but its query is AUTHORED, and nothing in the declaration says which second query returns the number. Refused rather than guessed |
| `generative`, `compute`, `extract`, `aggregate` | **no** | there are no source rows to count: the records are produced here, so counting them means producing them |
| `tabular`, `files`, `jar`, `source`, `feed`, `vector`, `keyword`, `elasticsearch`, `publisher`, … | **no** | the unit of cost is the whole download or the whole retrieval, which has to happen before anything can be counted |

A `sql` producer's declaration is lighter, because the engine writes the statement: `measure` — and
`of`, the column, for `sum`/`min`/`max` — is the whole of it.

```yaml
- name: linesByOrder
  kind: sql
  datasource: warehouse
  table: order_lines
  keyColumn: order_id
  aggregates:
    - measure: count
      valueField: n          # any name for the number; the statement aliases it
    - measure: sum
      of: amount_cents
      valueField: total
```

`keyField` defaults to the producer's own `keyColumn`, since that is what the statement groups by.
`valueField` still has to be named — it is the alias the number comes back under — and must not be
the key column, which the same row already carries.

Four `sql` shapes are REFUSED when they declare an aggregate, each for its own reason: a `scan:` is
already a bounded TOP N (counting its rows answers a question about the bound, not about the table);
a `procedure:` returns whatever it returns, with no `SELECT` list to replace; `keyMatch: ci` answers
one key per statement and a row may satisfy several keys at once, so a `GROUP BY` over it would
attribute one key's number to another; and a key column under an identity `dialect:` comes back in
the source's own spelling, which links to no anchor. Under `mode: governed`, a `sum`/`min`/`max` over
a column that `expose` does not list is refused too — a total over a column the caller cannot read
is an oracle over hidden values — and so is one over a masked column, since a number computed in the
database arrives past the mask.

**A declaration on a kind that cannot honour it is an ERROR, not a dropped line.** `realm_validate`
names the kind, says it has no way to answer a number without returning its records, and lists the
kinds that can. That is deliberate: silently dropping it would leave a realm that reads as though
its source counts for itself, and the only symptom would be a query that stays exactly as slow as it
was.

Declared rather than assumed, for every kind including the relational one. "A database can always
`GROUP BY`" is a fact about databases, not about this table under this governance — and an arbitrary
REST endpoint cannot be presumed to count at all, so a producer that guessed would return a
confident number from whatever the endpoint happened to send back.

The engine pushes an aggregate only when it is **safe as well as declared**: the target must be
projected nowhere else (`RETURN c.subject, count(c)` needs the rows whatever else it asks), every
aggregate over it must be pushable (one `collect` means the records are needed anyway), `count(*)`
never pushes because it folds rows of the whole pattern, `count(c.property)` never pushes because it
counts VALUES rather than nodes, and any predicate on the target must be one the source absorbs — a
source can only count what it can also filter. All four measures execute; the engine pushes only
when EVERY measure in the query is deliverable, and two measures over one property refuse because
they would want the same slot.

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

**Bounds (per statement):** the caps above are declared per join and bound what a query asks of a
SOURCE. Three further bounds belong to the statement itself and bound what it may spend in the engine.
None is declared in a realm, none can be raised from a query, and any one stopping a
statement is reported as a refusal of kind `BUDGET_EXCEEDED` carrying the limit it exceeded and the
unit that limit is in:

- a **work** bound, counted in match steps — the candidate space a pattern walks. A statement that
  exceeds it returns nothing and is told which of the two causes is its own: a pattern with nothing
  to anchor it, or too many node sets matched at once, where the candidate space is the product of
  them even though each set is labelled.
- a **records** bound, counted in fetched records: how many records the statement's fetches may
  bring into the graph it runs on, across all its stages and `UNION` branches (200,000 unless the
  host sets another). A fetched record is in the graph before any aggregation or `LIMIT` reads it, so
  `count(*)` over every call site of a large project brings every call site in; a statement past the
  bound returns nothing and is told to fetch fewer. A filter on the fetched node's own properties or
  on parameters — in its property map or in the `WHERE` that reaches it (`WHERE c.method IN
  $methods`, `WHERE d.path STARTS WITH $dir`) — is applied before records are brought in, and is the
  lever; so is reading the source in parts, one statement per part. An aggregation or a `LIMIT` is not.
- a **time** bound, counted in milliseconds, off unless the host sets one. It is a **backstop**, not
  a second way to say the same thing: work is counted in match steps, and a statement whose cost
  lies somewhere those are not charged — a filter evaluated per candidate over a wide match is the
  shape to know — can run a long time while the work bound barely moves. The work bound is the one a
  query should ever meet, because it can say what to do about it; a statement that reaches the time
  bound is told what is usually true of one that does, which is that it is unbounded in a shape the
  other bound cannot see.

A host that sets no time bound has only the work and records bounds. Where a host does set one, it is a property of the deployment and not
of the query: the same statement may be answered on one appliance and declined on another, and a
realm cannot tell which from its own files. **So a realm must not rely on any of these bounds as control
flow.** They exist to make a runaway statement fail loudly and diagnosably instead of spinning; a
query whose correctness depends on being stopped is a query to rewrite, by narrowing the match
before filtering it — anchoring it, or staging the joins with `WITH` and aggregating as you go.

**A rate limit is never an empty answer.** When a source's rate bucket cannot fit every lookup a
query needs now, the lookups that fit are made and the rest are deferred. The answer is flagged
partial and says how many were looked up and how many are pending; asking again fills in more.
Zero rows with every lookup deferred mean "not looked up yet", never "none". When the deferred work
is more than re-asking will ever complete, the flag says so and asks for a narrower query instead
of promising that the rest fills in. A source that THROTTLES a call (an HTTP 429) is reported as
`RATE_LIMITED`. With no rows the query is refused as `SOURCE_UNAVAILABLE` with that code; with some
rows the answer is flagged partial. Either way the result is unanswered, not empty, and the
integration is fine: nothing needs reconnecting. Ask again shortly, or pin a specific entity so the
query needs fewer calls.

**Model calls are priced before they are spent.** Fetches that call a model (extraction,
generation, a model-backed producer), `ai.*` judgments (§7) and generative rounds all draw on one
per-query limit on cold model calls. The quote prices what it can measure before the run. Work that
only becomes known as the run goes — a later stage whose anchors are an earlier stage's results,
per-row judgments over rows not yet fetched, a generative producer's further rounds — is charged
against the same limit as it begins. A step that would exceed it refuses the whole query with
`TOO_EXPENSIVE`, naming the count and the limit, before that step's call is made: work no quote
showed can never be spent unasked. A warm anchor costs nothing. A query that means to pay says so
(`{ai: {materialize: true}}`) or runs as a background job.

**A bound that stops the run is `BUDGET_EXCEEDED`.** A statement that exceeds the graph engine's
work, row or records budget, or a rule set that exceeds `maxRounds` or `maxPairs` (§13.7), is refused with
`BUDGET_EXCEEDED`, naming the limit and its unit, and returns nothing: never a partial set presented
as complete. A statement budget is fixed and cannot be raised from a query. The refusal names the
levers: aggregate earlier, add a `LIMIT`, narrow the `MATCH`, filter before sorting.

**Some statements are refused by their shape, before anything parses them.** These bounds are read
from the statement's text on every query surface, so nothing is fetched or run; a string literal, a
comment or a quoted name is data and counts for nothing. Each refusal names what it found and the
spelling that answers. A rule body (§13) meets the nesting and regular-expression bounds too.

- **Nesting.** One expression nests inside another by brackets, `CASE` inside `CASE`, a prefix `NOT`,
  a unary sign, or a property read or subscript chained onto a value (`x.a.b`, `x[0][1]`). All of
  these count together toward one limit of 128 levels; past it the statement is refused as
  `BUDGET_EXCEEDED`, naming the constructs that made it deep.
- **Literal ranges.** A `range()` whose bounds or step are written as literals is checked before
  execution. One whose bounds are more than a 64-bit integer apart, so its size cannot be counted
  exactly, or that makes more values than a list holds, is refused as `INVALID_QUERY`, as is a FLOAT
  bound or step. `UNWIND`s of literal ranges, one directly after another, whose product exceeds
  10,000,000 rows are refused as `BUDGET_EXCEEDED`. A `LIMIT` after them is not counted as bounding
  them, since a sort, an aggregation or a `DISTINCT` before it reads every row first.
- **Regular expressions.** A `=~` whose pattern backtracks super-linearly on a text it does not
  match — a repetition of varying length nested in a repetition with nothing to separate one turn
  from the next (`(a+)+`, `(\w+\s?)*`), or a repeated alternation whose branches overlap (`(a|aa)*`,
  `(\w|\d)+`) — or whose pattern is longer than 4,096 characters, is refused as `BUDGET_EXCEEDED`.
  A match cannot be stopped once it has started, so it is refused rather than tried. `([a-z]+,)*`
  and `(cat|car)+` are linear and run.

What an expression costs is bounded as it runs, too. On the in-process engine a regular-expression
match is charged to the statement's work budget for every character it reads, and a STRING is
charged for the characters it builds, so a pattern only the run can see is still bounded. No STRING
may exceed 16,777,216 characters: the in-process engine refuses to build a longer one, and an answer
holding one is refused on either engine, as `BUDGET_EXCEEDED`, naming the expression that grew it.

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
| `PRODUCER_ERROR` (`RATE_LIMITED`) | the source throttled the call (an HTTP 429) | the source is up and the credentials are fine — the result is **unanswered, not empty**. Ask again shortly, or pin a specific entity so fewer calls are needed. Never "reconnect". |
| `PRODUCER_ERROR` (`AUTH_EXPIRED`) | a 401 / "token expired" / `EXPIRED_AUTHENTICATION` | the OAuth token has **expired** — reconnect to refresh. The empty result is because the source rejected the call. |
| `PARTIAL_RESULT` (`TRUNCATED`) | pagination hit `maxPages` with a still-full last page; a call budget ran out mid-fan-out; a join's `maxFanoutTotal` held part of what a fetch answered out of the graph; a declared floor or gate dropped records | the fetch **succeeded but is incomplete** — the source has more. *Not* a failure. The detail says which cause, because the fixes differ: raise the cap, narrow the anchor set, or simply ask again (a budgeted run keeps its completed work and resumes rather than restarting). |
| `PARTIAL_RESULT` (`TRUNCATED`) | a `singlePage` producer (one whose listing declares paging it cannot walk) returned any records | the source **may have more**: the producer cannot tell the API's default first page from the whole listing, so the warning appears even when nothing is missing. Raising `maxPages` or asking again cannot change it; declare `paging:` so the listing can be walked, or read a listing that returns its whole collection. |
| `PARTIAL_RESULT` (`NOT_FOUND`) | the source answered a definitive 404 for one key of a fan-out | that key **does not exist** — as opposed to "we could not find out", which is `FETCH_FAILURE`. The answer is short by exactly the named keys; the source is not down, and the other keys' rows are good. |
| `PARTIAL_RESULT` (`DERIVED_LOWER_BOUND`) | a DERIVE rule set concluded while the facts its rules read were themselves incomplete (another diagnostic fired, or a demand went unmet) | membership and any aggregate over it are a **lower bound, not a total**. The fixpoint is correct over what was materialized and says nothing about what was not — a rule body cannot fetch (§13.6). Not a failure, and not "nothing was derived". |
| `PARTIAL_RESULT` (`UNREACHED_BACK_HOP`) | a hop reached a fetched label from a node that has **no declared door onto it**, so the label could only match records the query had already fetched some other way | membership, and any count or list over it, is a **lower bound**; a total, average, minimum or maximum over it describes only the records it read and may be off in **either** direction. Every row returned is true — what is withdrawn is only the claim of completeness. The warning quotes the hop as the query wrote it and names the doors that would give the node rows of its own. Not a fetch failure, and not "no more data". |
| `INCOMPLETE_TRAVERSAL` | a variable-length traversal (§5.12) stopped short of its declared depth | the warning names the hop reached and the bound hit (`maxFanoutTotal`, frontier width, or the unbounded-`*` cap). Rows cover only the hops walked; any subtree total is a **lower bound**. |
| `UNKNOWN_VIA` | an edge pinned `{via:'…'}` that no declared join offers | the rows are **real but came from a different join** than the one named. The query still answers — a via that does not exist must not cost a good answer — and the warning lists the vias that do exist so it can be re-issued. Matters most where several joins converge on one label, since the substitution is otherwise invisible. |
| `AMBIGUOUS_LABEL` | the query named a parent label that more than one installed type answers to through the same edge | **nothing was fetched**, so the empty result is not "no data". The engine will not choose between a customer's two helpdesks on the caller's behalf; the detail names the types, so the query can be re-issued naming one. |
| `NEEDS_FILTER` | a source that cannot be swept was asked without a narrowing predicate | the answer is **unknown until the query is narrowed** — not "no data". |
| `FILTER_STARVED` | candidates were found, and the query's own filters rejected every one | zero matches among **fetched candidates**, not proof of absence elsewhere. If `UNPUSHED_FILTER` also appears, the requested record may be outside the fetched page. |
| `UNPUSHED_FILTER` | a bounded source read (page cap or limit reached) omitted a declared filter (`queryArgs` or `sourceFilters`) and could not establish a match for that target alias, including when it returned zero records | the bounded fetch **cannot prove absence**. Supply a valid declared request input or narrow the source request; do not turn this warning into a clean zero. A failed read carries its failure diagnostic; a skipped read does not establish absence. |
| `FIELDS_WITHHELD` | governance removed fields — the secret reflex, `mask: drop`, or governed exposure (§5.15) | the **rows are complete**; named fields were removed by policy. An absent field here means "not exposed by this source's governance", never "no data". |
| `COMPUTE_FAILED` | a producer's `compute:` expression raised on some records | the rows are complete and the source is fine; **one property is absent** on the records named. Absent rather than null or zero, because either would read as an answer. |
| `MATERIALIZATION_FAILED` | the source returned data the graph could not store | the records **exist** but are missing from the result, so an answer of "none" is definitely wrong. The fix is the engine's, not the caller's. |
| `REDUCTION_FAILED` | an `aggregate` reduction or an `extract` call failed | the anchor's reduced or extracted records are **absent**, not empty. Retried on the next traversal. |
| `EMPTY_NOT_KEPT` | keys of a `ttl`-cached fetch answered **empty**, and the policy declares no `negativeTtlSeconds` | a **cost note over a correct answer**, not a data warning: the empty is the real answer for those keys, and the only thing it costs is the NEXT run's call. The note names how many of how many keys, and prints the declaration that would keep them. Nothing about the rows is in doubt, so an answer carrying it is never caveated. |

A row is not proof of a complete answer. Rows and totals from an incomplete read are retained as
`PARTIAL` and accompanied by an `incomplete` explanation; they are not presented as complete
totals. The diagnostic still prevents a claim that the returned set is complete. An empty result
is not absence when records were fetched but none matched, or when `FILTER_STARVED` reports that
the query's filters rejected every fetched
candidate; such a result carries `FETCHED_NOT_MATCHED`. The exception is a read the engine
reports as complete with an unsent filter applied in the graph: that empty is exact and does not
carry `UNPUSHED_FILTER`. A direct query result reports how many
source records it fetched and how many nodes it materialized, so a caller can tell "fetched and
unmatched" from "nothing fetched". An incomplete read that matched nothing, with no failed step, carries
`PARTIAL_NOT_MATCHED`: it is neither a failure nor evidence of absence.

A month label derived from week-start buckets (for example `date.truncate('month', weekStart)`
over weekly totals, including suffixed names such as `week_start_date`) is reported as a total
by week-start, not by calendar month. It does not establish an exact calendar-month total, or that
each labelled week was fetched in full, unless the source filtered the underlying events to that
calendar window before grouping. When the request's end-date input falls inside a returned
week-start bucket, the result also says that bucket may cover only part of its week, depending on
how the source applies the end bound, so that month's total may be partial.

A result column whose value the query wrote as a constant is described as written by the query,
not returned by the source.

A warning about the result's columns (a column that holds whole nodes, or a column name that claims
more than the query computed) describes how the result was projected. It does not mean the read
failed or is incomplete.

A failed read is **never cached** as an empty result (so a later call with a refreshed token finds
the data); only a genuine, successful "no records" is cacheable — and only when the policy says it
may be, which is what `negativeTtlSeconds` is for. A diagnostic that leaves a key's records
unsettled also stops a NEGATION answering over it — see "A short fetch never answers a negation"
below, which lists exactly which of them do.

**A hop onto a fetched label with no door reads a lower bound.** A declared join is a door in one
direction: it says how to fetch the TARGET given the ANCHOR. Walking that edge the other way —
holding the target and asking for the anchor's own records — asks a question no source was given.

```cypher
MATCH (s:Shop {code: 'north'})-[:HAS_ORDER]->(o:Order)
MATCH (o)-[:FOR_CUSTOMER]->(c:Customer)<-[:FOR_CUSTOMER]-(o2:Order)
RETURN count(DISTINCT o2) AS n
```

`FOR_CUSTOMER` is declared on `Customer` anchored on `Order`: an order names its customer, and
nothing is ever asked which orders name a given customer. So `o2` has no rows of its own. It
matches whichever `Order` records the query fetched some other way — north's, through
`(:Shop)-[:HAS_ORDER]->` — and every other shop's orders for that customer are simply absent.
Nothing failed, so nothing else would report it, and `n` comes back looking like a total. The
arrow as written is not what decides it: the same hop spelled forwards, `MATCH
(o2:Order)-[:FOR_CUSTOMER]->(c)` with `c` already bound, asks the same unanswerable question and is
flagged the same way.

The query is **answered rather than refused**, because every row it yields is a true row. The
warning withdraws exactly the claim of completeness, quotes the hop as the query wrote it, and
prints the doors that would give the node rows of its own — here `(:Shop)-[:HAS_ORDER]->(o2)`. A
caller reporting a figure from such a hop must say the answer may be incomplete.

Only **fetched** labels are in question: a hop among persisted nodes is ordinary Cypher, complete
and unflagged. The flag is decided from the query's shape alone, before anything is fetched, and is
withheld in five cases — each a structural proof that the node's records are all there:

1. **the node has a door of its own in this query** — it is the target of a join the query walks,
   so its rows are fetched for it, not inherited;
2. **it is bound before anything is fetched** — pinned to a literal, or matched among persisted
   nodes;
3. **the join declares how an already-materialized target answers for its anchor**
   (`materializedKeyField`, `ridesHub`) — the author's own contract that riding those records IS
   the whole edge;
4. **every door into the label was walked here over the whole of its anchor's population** —
   nothing pinned or filtered on either end and no `LIMIT` that could cap the read, so the records
   materialized are every record there is;
5. **the hop is off an alias that only rebinds nodes another alias bound** — `WITH collect(o) AS
   os` then `UNWIND os AS o2` introduces no node, so `o2` ranges over exactly the records fetched
   for `o`, and a rebinding is not a match. A hop reached BEYOND such a rebinding is matched afresh
   against the graph and is flagged as before.

The fourth is judged strictly, and deliberately so: anything the query reads off either end of a
door — a predicate, a pin, or merely a projection — leaves the proof unavailable and the hop
flagged. The cost of that strictness is a caveat on an answer that happens to be whole, which is
the one direction this can safely be wrong in.

**A failure costs the keys of the request it failed, and no others.** A fan-out over many keys is
many requests — one per key for a source that answers per key, one per `maxKeysPerCall` batch for a
source that answers in batches — and the request is the unit of the answer, so it is the unit of the
caching decision too. A request that came back is cached for every key it carried, however its
siblings fared; a request that failed leaves every key it carried **unresolved**, so the next query
asks for exactly those again and nothing else. Three dead keys of two hundred therefore cost three
re-reads on a per-key source, not two hundred.

The split is by request and not by key, because a source that rejects a batch rarely says which of
its ids it choked on: a batch of fifty that answers `500` leaves all fifty unresolved. So a producer
the engine calls a key at a time — one the realm declared `batchSafe: false`, or whose source is
structurally single-key — has its failures priced per key as a consequence of how it is called,
never as something to declare for. Either shape is flagged the same way: the `warnings` are what say
the answer is short, whatever was cached.

**What a flaky source costs, and it is the same whichever producer kind reached it.** A failure is
retried for what it MEANS, never for how the producer was declared: `remote`/`api`, `graphql`,
`sparql`, `publisher` and the captured-handler kinds all answer to one table.

| the source said | retried | why |
|---|---|---|
| 429 Too Many Requests | once | it asked us to wait, and waiting is the whole of what it asked for |
| 502, 503, 504 | once | the upstream's own infrastructure, not the request |
| 408, a read timeout, a dropped or refused connection | once | it never answered; the next call may |
| 400, 422 | no | the source understood the request and refused what it ASKED. Retrying repeats it |
| 401, 403 | no | the credential is not working. The fix is to reconnect, not to ask again |
| 404 | no | the source looked. The answer is short by that key, and is reported as `PARTIAL_RESULT`, not an outage |
| 500 | no | the source answered about this request, and will answer the same way |

The bound is **two attempts per key** — one try and one retry — and it is **per key, never shared
across a fan-out**: ten failing keys cost twenty attempts, not two, and emphatically not two to the
tenth. A retried call is a request that left the machine, so both attempts are **billed and
reported** in `apiCalls`; a cost quote prices the happy path, and the gap between the quote and the
meter is the flakiness, readable rather than hidden.

**A wait the source asked for outranks ours, inside a window.** A `Retry-After` in delta-seconds is
honoured once, floored at one second (a source asking for "now" is still asking us to wait) and
capped at ten (a source asking for a quarter of an hour cannot hang a query someone is waiting on).
A `Retry-After` given as an HTTP date is read as no specific ask. With no readable header a throttle
waits about two seconds and the other retryable classes a fraction of one.

**Where a `Retry-After` cannot be read, the retry still happens.** A producer reached through a
gateway operation gets the header from the HTTP failure the operation reports, which is also where
its status comes from — so a source that answers over HTTP is honoured exactly. A producer whose
operation failed some other way (a realm handler that threw, a dispatch that was not there) reports
no HTTP response at all, so there is neither a status nor a header: the failure is classified from
its message, and a retry it earns waits the engine's own bounded wait rather than going unmade. The
degradation is the WAIT, never the attempt.

**A declared `cost: rate:` changes the wait, not the law.** A throttled call on a paced bucket slows
every sibling waiting on that bucket and then retries on a fresh slot, which is a better wait than
any single call could compute — and it is still one retry, so the two attempts per key hold.

**A statement with a mistake in its own text costs your source nothing to be told so.** A Virtual
Cypher statement runs only *after* its fetches, so the cost of a refusal depends on when the mistake
can be known. Two kinds, and which one a mistake falls into decides the bill:

- **Settled by reading the statement, under a rule of Cypher itself** — a variable the statement
  binds nowhere (`RETURN q.id` with no `q` in any clause), two result columns under one name
  (`RETURN p.id AS id, p.ms AS id`), a `SKIP` or `LIMIT` that is not a row count (`LIMIT -1`), an
  aggregate in a `WHERE`, an implicit grouping, a label or relationship type no vocabulary knows.
  Refused as `INVALID_QUERY` with **no producer call, no model call and nothing cached** — the
  anchor's data is as cold afterwards as it was before, so the next, correct query pays the honest
  cold price rather than reading a remembered answer. A typo over a two-hundred-anchor hop costs
  your rate budget nothing.

- **Settled only once a row reaches it** — a division by zero, an integer overflow, a value of the
  wrong type, a regex or a date built from fetched data. Whether these raise at all depends on the
  rows, and the rows are what the fetch produces, so the refusal arrives after the hop has been
  fetched and the records ARE cached (they are the source's own answer; only the fetch behind them
  was avoidable). Guard the value in the statement — `CASE WHEN d = 0 THEN null ELSE n / d END`,
  `n / toFloat(d)` — and the question costs one fetch instead of two.

An **unknown function name** is refused with the function named, but after the fetch: which
functions exist belongs to the store and the libraries it loads, and refusing up front on a list
that might be one version behind would refuse queries that work. The message names it either way.

**A short fetch never answers a ranking.** A short *list* is honest under its warning: every row
is right, some are missing. A short *ranking* is not, because the records left out may be the ones
that belong at the top. So a top-k — `ORDER BY … LIMIT k`, in a `RETURN` or a `WITH` — over a
fetch that came back short answers only when its first k are **provably** the first k there are,
and is otherwise refused as `INVALID_QUERY` (reason `INCOMPLETE_RANKING`), naming the cause, the k
and the levers (raise the cap, narrow the query, or drop the ranking). Two cases are provable:

- **A capped read of a source that declares its order.** When the fetch stopped at a cap (`maxItems`,
  a page cap, the 25-key ceiling), the unfetched records' sort keys are unknown, so only the source
  can vouch: the answer stands when the producer declares the order it returns records in
  (`orderedBy:`) and the query's sort keys are a prefix of that order — same properties, same
  directions, on the records that producer fetches. A capped prefix of an ordered source *is* its
  top. A graph-side filter over a vouched read still answers, flagged partial: short, not wrong.
  `ordering:` in `sources.yml` says whether a collection is newest-first, not on which field, so it
  vouches for nothing; a feed declares no `orderedBy:`, so a capped feed's ranking always refuses.
- **Records left out unread under `FOLLOW_CAPPED`.** Their sort keys *are* known — only the followed
  field went unread — so the answer stands when none of them could rank at or above the k-th row.
  A tie, a missing or incomparable key, or fewer than k rows leave room for them, and refuse; so
  does a top-k in a `WITH`, with `SKIP`, or keyed on another variable, which cannot be compared.
  When the answer stands, the `FOLLOW_CAPPED` note says the rows **are** the top k rather than
  "short".

A whole key that failed to fetch under a top-k still answers with its `PRODUCER_ERROR` warning; the
ranking gate does not yet decide that case.

**A short fetch never answers a negation.** A negation is the one read whose answer GROWS when the
fetch comes up short: a key the source did not answer for holds no records as far as the query can
see, and "no records" is exactly what the test asks for. So its rows are a **superset** of the
answer and a count over them an **upper** bound — the opposite of every warning above, each of
which says rows may be missing and a count is a floor. A caller acting on the warning as written
would under-report.

So a negation over a fetch that **did not settle** for every key it drove is refused as
`INVALID_QUERY` (reason `UNPROVEN_ABSENCE`) rather than answered. It is refused, not flagged,
because no flag can carry it: a reader who takes "may be incomplete" to mean "there may be more"
reads a longer answer as a shorter one, which is worse than no answer at all. This is the same
decision `maxAnchors` makes one step earlier — a fetch too wide to afford is refused rather than
answered from the keys it could pay for.

- **Every spelling of the question is treated alike**, because they ask the same thing:
  `NOT EXISTS { (a)-[:R]->(:T) }`, a negated pattern predicate `NOT (a)-[:R]->(:T)`, and the
  outer-join form — `OPTIONAL MATCH (a)-[:R]->(n) … WHERE n IS NULL` — which carries no `NOT` at
  all. A test on a *property* (`WHERE n.status IS NULL`) is not one of them: a property may be null
  on a record that did arrive, which says nothing about whether the record arrived.
- **"Did not settle" means absence is unproven for some key**: a fetch that failed or was refused
  (`FETCH_FAILURE`, `AUTH_EXPIRED`, `RATE_LIMITED`, `FILTER_REJECTED`), a read cut short
  (`TRUNCATED`, `INCOMPLETE_TRAVERSAL`), a key never asked (`NEEDS_FILTER`, `UNPUSHED_FILTER`, a
  request the engine declined to send, a case-folded spelling never covered), records fetched but
  not stored (`MATERIALIZATION_FAILED`), a node reached only backwards along a join, or a brought
  child the source gave no identity.
  Two diagnostics are deliberately NOT in that list, because under them "none" is exact rather than
  unknown: a definitive `NOT_FOUND` (the source says the key does not exist) and `FILTER_STARVED`
  (the source answered, and the query's own narrowing rejected every candidate). A `STALE_COPY` is
  not in it either — a copy is the whole file as the publisher last served it, so an absence in it
  is exact as of that date.
- **A complete fetch answers the negation as it always did**, including a paged one that read every
  page and a cap that was declared but never reached. The refusal is about the fetch, not the shape.
- **The levers, and each one answers:** narrow the query so the fetch settles for every key it
  drives (pin fewer keys, or add a filter the source applies); lift whatever stopped the fetch,
  which the refusal quotes in the producer's own words; or ask the same thing without the negation —
  the refusal prints the pattern as a plain `MATCH`, whose rows are the anchors that DO match, and
  which a short fetch leaves short rather than wrong, under the warning that says so.

**A name that exists nowhere is refused, not answered empty.** A query that reads a label or
relationship type that no declared type, virtual join, rule set or stored node in the caller's
graph knows is refused before it runs, with `INVALID_QUERY`. The refusal names the pattern where
the name was written and suggests the nearest names the caller can query — an empty answer to a
misspelling would read as "you have none". A label that is merely empty is different: a declared
type with no instances yet, or a derived label nothing satisfies, answers no rows as before. A
name a statement creates (`CREATE`, `MERGE`) is never judged, and property names are not judged
this way, because a type's declared properties are not a closed list.

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
GET  /api/v1/admin/kg/fills        → [{ id, state, ticks, liveCallsTotal, lastError, warning, ... }]
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

**A fill reaches `DONE` only if its producers keep what they fetch**

`DONE` is a pass that makes no live call at all, and work already done is skipped on the next
pass only while it is still fresh. So a producer whose records expire between passes is re-read
every pass: the fill keeps working, it never runs out of live calls to make, and it never turns
`DONE`. Nothing is broken — it has simply become a slow permanent poller. Whether a fill can
terminate is decided entirely by its producers' `cache:` declarations, and by nothing about the
query, the budget or the schedule.

That is a division of labour, not a limitation:

- A **fill** converges a COLD materialization of something that does not change once mined: a
  closed month of history, a catalog, a backfill of records that are what they are. Declare those
  producers so their records outlive the whole sweep — `cache: { kind: immutable }` for reference
  data, or a `ttl` in days — and the fill climbs to `DONE` and stops. `periods:` already does this
  for you: a closed period is held effectively forever whatever the producer's own `ttl` says,
  which is why a 12-month history fill finishes. Only the open period rides the ordinary TTL — and
  it is also the reason a `periods:` fill over a producer with a short TTL does not terminate
  either, since the open period expires under the sweep while the sweep is still running.
- Re-assessing something that keeps changing — a live queue, prices, today's state — is **scheduled
  work**, not a fill: a Realm Function on a `schedule`, or a routine bound to a signal. Those are
  built to re-run for ever and have no finish line to miss. A fill aimed at a live source only
  imitates one, at a fill's pacing and without a schedule's triggers.

A fill started over producers that cannot outlive a sweep is accepted and **carries a warning**
naming them, visible on the fill in the listing above. It is a warning rather than a refusal
because a slow permanent poll is sometimes exactly what someone wants; it should be chosen, not
stumbled into.

**A realm ships the sweep its own producer needs**

The calls above are the operator's door. A realm that declares an expensive producer should not have
to hope somebody finds out that fills exist, works out the right query and POSTs it: it declares the
sweep as a `sweeps:` entry on one of its own agents (README, [`agents/`](README.md#agents--agents-and-their-routines)),
each naming a view of the realm's that takes no arguments. The host then runs it as a fill with
everything above true of it — budgeted, paced, resumable, cancellable, warned about where it cannot
converge.

What a realm gets by declaring one, and what it does not:

- **Installing the realm starts nothing.** A realm agent arrives off duty with no sponsor and no
  signature, so there is no sweep to run. The declaration is visible on the agent's card — the sweep,
  the view it fills, the budget it asks for — and nothing is bought until somebody sponsors the agent,
  signs it and puts it on duty. Those are the same three acts every realm agent already needs; a
  sweep adds no consent step of its own, and the install is not one of them.
- **It spends the AGENT'S budget and reaches only what the AGENT may reach** — the `budget` and
  `authority.reach` its sponsor signed, never the installing operator's own allowance. An agent
  whose reach does not name the API behind a producer the sweep plans calls nothing: the pass is
  refused before it begins.
- **Anybody who can stop the agent stops the sweep.** Standing the agent down, retiring it or
  throwing the world's kill switch stops it; so does removing the realm, which cancels the fill
  rather than leaving one retrying a query whose realm is gone. Completed work stays cached, so
  putting the agent back on duty resumes rather than restarts.
- **A realm update cannot change what an adopted sweep asks.** The view's text is part of what the
  sponsor signed, so rewriting it shows as an unsigned change and the signed text keeps running
  until somebody signs again — as a routine's body does.
- **It is not a schedule.** A sweep converges a cold materialization and stops, under exactly the
  rules above; re-assessing something that keeps changing is a routine on a `schedule`.

```yaml
# agents/surveyor.yml
name: surveyor
job: Keep the crime history mined, so a question about a street answers from the graph.
sweeps:
  - name: crime-history            # stable within the agent; the fill is found by it
    view: street-crime-sweep       # a view of this realm's, taking no arguments
    budgetPerTick: 60              # optional; the paid calls one pass may make
```

| Sweep field | Required | Meaning |
|---|---|---|
| `name` | yes | Stable id within the agent. Asking for the same sweep twice is one fill, not two. |
| `view` | yes | A saved view this world has, declaring no `params`. Its body is the query each pass runs. |
| `budgetPerTick` | no | Producer calls, or inline-judgement groups, one pass may buy. Omitted takes the host's default. |

A sweep whose view the world does not have, or whose view takes arguments, is a **need on the agent**:
the agent cannot be put on duty until it is fixed, so the declaration is reported before anything runs
rather than failing a pass at a time. A host may cap `budgetPerTick`, and the number of fills it
advances per tick is the host's, so several sweeps in one world each advance more slowly.


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

- **Read-only.** A user query never writes the graph. Nothing it materializes outlives the run
  (§2); the sole persisted side effect is a write-through identity **bridge** (a
  cache of *who* an external identity is, not *what* data they hold). The single, explicitly
  opted-in exception is the dedicated annotation-write surface (§12) — ordinary queries remain
  read-only and continue to reject mutating clauses.
- **Scoped, fail-closed.** Every keyed probe goes through the world/context scope rewriter; vector
  searches are filtered by world, context, and access-policy revision at the source. A query can
  never read another context without an explicit authorized bridge, and never another PRINCIPAL's
  data; between two worlds of one principal the boundary is focus rather than confidentiality
  (§15). Deployment-approved, revisioned `Public`/reference datasets are the explicit exception. An
  unparseable or unscopable query is rejected, not run — and what the ENGINE writes is never the
  reason it is: a probe binds only positions it can scope, and drops the rest (§2). Which positions
  a statement must label for it to be scopable is §15.5, the same in either spelling of a subquery.
- **Bounded.** Every fetch is bounded by a bound anchor, `maxAnchors`/`maxFanoutTotal`, `paging`
  caps, `k`, and rate budgets. Truncation is reported.
- **One answer whichever engine holds the graph.** A deployment may keep the graph in Neo4j or in
  the appliance's own in-process engine, and a query answers the same on both: the same values,
  nulls and conversions, the same column names, the same refusals by type. A statement that fails
  changes nothing on either. A difference between the two is a defect in the engine that differs,
  not a dialect for queries to allow for.
- **Idempotent re-runs.** A re-run re-fetches; caching (`ttl`/`immutable`) makes repeated runs of the
  same query agree, including on any LLM-derived value — repeatability is a correctness property, not
  just a speed one. Without a cache, an LLM-derived value may differ between runs.
- **A refusal is stable, and it is actionable.** A refused statement, re-issued unchanged, is
  refused again with the same text; every refusal names what was counted, the size and the limit it
  passed, and a lever that changes the outcome; and a figure that is only a floor says so. §9
  states the contract in full, because a caller rewriting a query has nothing else to go on.

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
true as membership grows, which is exactly what the fixpoint needs.

The rule is monotonicity, not the word NOT, and it is checked position by position: a reference to
the derived label must sit where a new member can only make the body MORE true. A negation in any
other spelling is refused the same way — a count compared from above (`size([x IN xs WHERE
x:Derived]) = 0`, `COUNT { (p)-[:R]->(:Derived) } <= 3`), a `CASE` that inverts the label, an
`OPTIONAL MATCH` of it followed by `IS NULL`, a `SKIP`/`LIMIT` a new member could push a row out of.
Count members from below instead (`>= n`), or use `any(…)`/`EXISTS`; `sum(CASE WHEN x:Derived THEN 1
ELSE 0 END) >= n` is admitted because it only grows. Such a rule would otherwise settle at once on a
set its own body contradicts, which the round cap cannot notice because nothing is still moving — so
a body the host cannot prove monotone is refused rather than trusted.

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

**A rule body's labels are checked when the realm is validated.** A body label that is a near miss
for a known one (`Compnay` beside `Company`) is an error at the rule's `from`, naming the likely
intended label: a misspelled body matches nothing, so the rule would derive nothing and say nothing.

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

**What the graph already holds is never taken away by a run.** A conclusion may land where stored
data already is, and the run treats that data as data:

- a node that already carries the derived label in storage is a member as it stands, and still
  carries the label after the run — derived and stored membership are a union;
- a stored relationship of the derived type between a concluded pair IS that conclusion, and is
  left exactly as it was (no second edge, nothing stamped on it);
- a head property whose value is already stored on the member — or head properties bound for a
  stored relationship — **refuse the query**, naming the property and the node. A stored value
  cannot be unioned with a computed one, and overwriting it to remove it afterwards would destroy
  it. Rename the derived property (prefix it for the realm, §13.5) or stop storing it.

A run that fails part-way — at its round cap or its pair budget — leaves nothing behind either:
the graph after a failed run is the graph before it.

Every
membership records its **firing chain** — which rule concluded it, in which round, with which
values, and how values grew as membership grew. That trace is the mechanical object an
explanation renders rather than reconstructs: "blocked because A (30%) and B (25%) together hold
55%" is read off the chain, not inferred after the fact. Rule bodies pass the same per-user
scoping as every query, so a rule can never read what its author's own query could not.

**A conclusion is visible exactly where the nodes it annotates are.** A derived label on nodes only
its caller owns is the caller's; a derived label on shared nodes is visible to whoever can see those
nodes, and is answered as such — `MATCH (t:HotTopic)` over shared topics returns them to the caller
that derived them, never an empty answer. Because a conclusion inherits its nodes' audience, a rule
set that would conclude from **private** facts onto nodes **other users can read** is refused before
it runs: otherwise a shared node would carry a property computed from someone's private data (a
`heat` counting their private mail) for every reader to see. Conclude onto private nodes, or derive
only from facts the shared node's readers could see themselves.

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

Before any rule evaluates, the engine counts each body on its first round — counting and
discarding, so nothing is materialized and nothing is written. Two budgets are checked:

| Budget | Default | What is counted |
| --- | --- | --- |
| facts | 50,000 | the rows the whole body binds — the facts it would conclude |
| work | 1,000,000 | the rows the body examines before its first `WITH` that aggregates (`count`, `sum`, `collect`, `DISTINCT`, `ORDER BY`) or filters (`WITH … WHERE`) |
| deadline | the query's own | how long any one counting statement may run before the database stops it: by default, the time the query has left to run inline (its query timeout), so pricing is never a tighter wall than the query already has |

Each count **stops one row past its budget**, so pricing a body never costs more than the budget it
is priced against — a cartesian of a billion rows is priced in the time it takes to stream a million.
The work count exists because an aggregating body can conclude a handful of facts from ruinous work:
pair every verse of a corpus with every other, count the people each pair shares, keep the pairs
that share six. Its facts are few; the rows it must examine to find them are the square of the
corpus.

Past either budget the query is **refused** with the count, the budget, and which rule accounts for
it:

```
TOO_EXPENSIVE: deriving :CO_LOCATED would bind at least 50001 row(s) on the first
round alone (gate: 50000). Rule 1 of 'probe/cartesian' accounts for 50001 of them —
an under-constrained body is quadratic in the nodes it binds, so narrow it (anchor one
side, add a filter) or raise the rule set's own limits deliberately if the estate is
genuinely that dense.
```

Why the cut falls before a filter as well as an aggregation: a count stops at rows that *reach* it,
so behind a selective `WITH … WHERE` it measures output, not work — finding a million rows that pass
can mean examining most of a cartesian. A filter in a `MATCH`'s own `WHERE` cannot be cut away
without pricing a different query (an anchoring equality there is what makes a body cheap), and that
is what the deadline is for.

Slow is not the same as too expensive. A derivation that takes fifteen seconds of a query's
three-minute allowance is entitled to run inline; what is refused is a count that cannot finish
within the whole allowance, because the evaluation after it would need at least as long again.

A count that is **stopped** before it finishes — terminated, timed out, or out of the engine's own
work budget — is treated as evidence of cost, and the query is refused the same way. It is never
read as "no quote" and run unpriced. A body the engine cannot count at all (a dialect that rejects
the appended clauses) is not quoted, and the ceilings below remain underneath it.

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
members on the first round, so a transitive closure is under-counted; and every count stops past its
budget, so "at least N" is the most a refusal ever claims. The engine can let expensive work
through, but it can never refuse cheap work on a guess.

Two ceilings sit underneath as backstops, and you should never meet them:

| Ceiling | Default | What it means |
| --- | --- | --- |
| `maxPairs` | 250,000 | A relationship set derived more pairs than this. Bounds what reaches the graph; it is checked after a round has bound its rows, so treat it as a last resort rather than a budget. |
| `maxRounds` | 1,000 | The fixpoint did not settle. The message names what was still moving: a derived property climbing (§13.2), or simply an estate deeper than the cap. |

Both fail loudly, as `BUDGET_EXCEEDED` naming the ceiling and its unit (pairs or rounds), and the
run is discarded whole: nothing is concluded from it. Neither truncates: you will never receive a
derivation that quietly stopped early.

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
- **Reading a cache:** a fetched record is reused for whoever the data it was fetched INTO belongs
  to, which is the principal for their own data and WIDER for data the deployment declares shared —
  see §15.4. It is not a leak across a confidentiality boundary, because between worlds of one
  principal there is no such boundary, and because a declaration that rows are the same for
  everybody is a declaration that no principal owns them.
- **Making a deployment claim:** "isolated per user" is supported. "Worlds are mutually
  confidential" is not, and is not intended to be.

### 15.3 What a fetch is keyed by, which is easy to assume wrongly

Within a scope, a fetch is keyed by everything that changes the result set — the producer, the
resolved key, the pushed-down filter, any steer or tuning, and the limit and demand in force. A read
taken under a cap therefore never serves one taken without. The other direction is allowed, on the
conditions §5.13 states: a complete read taken without a cap or filter may serve the same key's
question under one, because the narrower answer is inside it. This is what lets a warm-up in one
request populate the cache for another without a truncated answer being served as a complete one.

### 15.4 Which scope a cached record is kept for

The scope a `ttl` or `immutable` entry is filed under is the scope the FETCHED data belongs to, not
the scope of whoever asked for it first. There are three, and the difference is a cost difference
and never a visibility one — no record is ever served to a principal who could not have fetched it
themselves:

| the label a fetch targets | kept for | what a second asker pays |
|---|---|---|
| the principal's own data — your realm's types, and anything the deployment has not declared otherwise | that principal | the full cold price, per principal |
| **reference** data the deployment declares (its own taxonomies and catalogues) | the deployment | nothing: one entry, whoever asks |
| **shared** data the deployment declares (its canonical people, organisations, addresses, documents) | the deployment's **organisation** | nothing within that organisation; the full price in another |

So a realm whose producer fills a label of its OWN pays per principal, and should budget for it. A
realm joining onto a label the deployment declares reference or shared pays once for the whole
deployment — which is also why a realm may not widen a label into either class: declaring
`visibility: public` over a label the deployment already declares shared is refused, and a realm's
own public register stays per principal in the cache, because its rows are its world's and not the
organisation's.

What stays per principal whatever the label says: nothing is inferred from a producer's
CREDENTIALS. If your producer authenticates as the acting user and you point it at a label the
deployment declares shared, you are declaring that its records are that label's — one row per
identity, the same for everybody — and they will be kept that way. Fill a label of your own
instead.

### 15.5 Which positions you must label, and what holds the rest

A node is held to you by the labels it names, so **a node YOU bind must name a label**: a bare
`MATCH (n)` or `MATCH (b:Bill)-[:ABOUT]->()` is refused, naming the node as you wrote it and
offering both halves it needs — a name and a label. That node is part of your answer: it decides
which rows exist and how many, and nothing can be said about which node it is.

**A position only a predicate reaches is yours to leave unlabelled.** The far end of a pattern
predicate, and the far end of a hop inside an `EXISTS`, `NOT EXISTS`, `COUNT` or `COLLECT`
subquery, produce no row and no column of your query. Each is held to you there by its own
condition — the labels the STORED node carries decide it: a node carrying a declared non-private
label is reference or shared data and answers; any other node must be yours. A relationship from
your own node proves nothing about the node at its other end, so this is a condition on the node
itself, never on how it is reached.

**A subquery answers the same question in either spelling.** `EXISTS { (s)-[:SUPPLIES]->() }` and
`EXISTS { MATCH (s)-[:SUPPLIES]->() }` are one construct written two ways, and so are the `COUNT`
forms; a position they both reach is held by the same condition, and neither spelling is refused
where the other answers. The same holds for a far end you name without a label (`(x)`), for an
undirected or variable-length hop, and for a subquery nested in another. A `COLLECT` body has only
the one spelling, and is held the same way.

Two limits stay, and they are the same in both spellings: the subquery's pattern must start from a
node bound OUTSIDE it, and a position no relationship reaches
(`EXISTS { MATCH (s)-[:R]->(:T) MATCH (y) }`) must name a label. Each of those is a scan of the
whole graph rather than a constraint, and holding one position states no scope over a scan.

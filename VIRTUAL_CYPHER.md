# Virtual Cypher — Specification

> **Status:** normative. This is the contract for what a Virtual Cypher query can do and how it
> runs. The declarative surface a pack author writes (`virtualJoins:`, `producers/`, bridge
> `resolve:` chains) is specified in [`README.md`](./README.md#joining-types-on-demand-virtual-joins-not-mirrored);
> this document specifies the **execution semantics** — what queries are possible, and, for each,
> what the engine does. It is example-driven on purpose: read the worked examples (§3) first.

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
   │  1. PROBE    bind the REAL anchors the query selects (scoped to you)     │
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
   label, a `dateRetrieved` timestamp, and your `userId`. The engine links it to the anchor it was
   fetched for (`keyField == recordKeyField`). A record may also carry its own **sub-graph**
   (`brings:`), materialized in the same pass.

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
- narrowed by **any** property predicate — `WHERE toLower(p.name) CONTAINS 'james'`, or
- the current user — `(me:AssistantUser)` (the scope rewriter pins it to you), or
- reachable over a *required* edge from another bound node.

A naked `MATCH (hc:HubSpotContact)` — no anchor — is **rejected** (§4). This is what stops Virtual
Cypher from trying to fetch *every* contact in HubSpot.

**Per-user scope.** The probe runs through the per-user **scope rewriter** (fail-closed). You can
only ever materialize virtual data off **your own** anchors; a virtual node is stamped with your
`userId` so the rewriter's scope predicate matches it. A query can never reach across users.

---

## 3. Worked examples

Each example shows the **query**, what the user **means**, and **how it executes** conceptually,
then points at **what you declare** to enable it. Read these in order; later ones build on earlier.

### 3.1 The simplest join — id-match (Person → HubSpot contact by email)

```cypher
MATCH (p:Person {name:'Ada Lovelace'})-[:HAS_HUBSPOT_CONTACT]->(c:HubSpotContact)
RETURN c.company, c.jobtitle
```

**Means:** "What does HubSpot say about Ada?"

**How it executes:**

- **Probe** — bind `p`: find the persisted `Person` named Ada (scoped to you), read her
  `primaryEmail` — say `ada@example.com`. That email is the **key**.
- **Fetch** — call the `contactsByEmail` producer once with `['ada@example.com']`. It returns
  Ada's HubSpot contact record `{ email, company, jobtitle, … }`.
- **Materialize** — make a transient `(:HubSpotContact:Virtual { … })` and an edge
  `(ada)-[:HAS_HUBSPOT_CONTACT]->(c)`, because the record's `email` (`recordKeyField`) equals
  Ada's `primaryEmail` (`keyField`).
- **Run** — your `RETURN c.company, c.jobtitle` reads the transient node. Done.
- **Roll back** — the contact node disappears.

**Declared:** a `HubSpotContact` type with one `virtualJoins` entry
`{ anchorLabel: Person, relationship: HAS_HUBSPOT_CONTACT, keyField: primaryEmail, recordKeyField: email, producer: contactsByEmail }`,
and a `producers/` entry `contactsByEmail` (`kind: remote`).

> This is the **id-match** shape: the anchor is a real domain node and the join links by a shared
> value (email). Contrast with the **bridge** shape (§3.2), where the anchor is itself an external
> identity node.

---

### 3.2 A bridge plus a downstream hop (Person → GitHub identity → issues)

```cypher
MATCH (p:Person {name:'James Governor'})-[:HAS_GITHUB]->(g:GitHubIdentity)-[:RAISED]->(i:GitHubIssue)
RETURN i.title, i.html_url
```

**Means:** "What GitHub issues has James raised?" — but the graph holds no GitHub data at all.
Two virtual hops: first resolve *which GitHub account is James*, then fetch *that account's
issues*.

**How it executes:**

- **Probe** — bind `p` (James), read his email.
- **Resolve the bridge** (`HAS_GITHUB` is an identity bridge — §5.2). Run James's `resolve:`
  chain: is there already a `GitHubIdentity` linked to him (`existingBridge`)? a learned
  `githubLogin` on his node (`learnedHandle`)? otherwise look his email up via the
  `githubUsersByEmail` producer (`canonicalEmail`). Say it resolves to login `monkchips`. The
  bridge `(james)-[:HAS_GITHUB]->(:GitHubIdentity {login:'monkchips'})` is **persisted**
  (write-through) so the next query skips this step.
- **Now `g` is a real, bound node.** Its key is `login = 'monkchips'`.
- **Fetch** the downstream join — call the `issuesByAuthor` producer with `['monkchips']`. It
  searches GitHub for `author:monkchips`, returns the issue records.
- **Materialize** each as `(:GitHubIssue:Virtual)` linked `(g)-[:RAISED]->(i)`.
- **Run / roll back** — `RETURN` reads the issues; the issues roll back (the *bridge* stays, as a
  warm cache).

**Declared:** `GitHubIdentity` with a `resolve:` bridge join from `Person`; `GitHubIssue` with a
plain `virtualJoins` entry `{ anchorLabel: GitHubIdentity, relationship: RAISED, keyField: login, producer: issuesByAuthor }`.

> **Why two declarations, not one.** The bridge (who-is-James) and the data (his issues) have
> different lifecycles — the identity is stable and worth persisting; the issues are volatile and
> roll back. Splitting them lets the engine cache the expensive identity resolution and re-fetch
> only the cheap, changing part.

---

### 3.3 A literal-seeded anchor — fetch *anyone's* data through your credentials

```cypher
MATCH (g:GitHubIdentity {login:'octocat'})-[:RAISED]->(i:GitHubIssue)
RETURN i.title
```

**Means:** "What has `octocat` raised?" — `octocat` is **not** someone in your graph; you just
named a GitHub login directly.

**How it executes:**

- **Probe** — try to bind `g` as a real node. There is no `GitHubIdentity {login:'octocat'}` in
  the graph, so the engine **seeds** a transient anchor from the literal: a virtual
  `GitHubIdentity` whose `login` is `octocat`.
- **Fetch / materialize / run** — exactly as §3.2 from the resolved-identity step onward, keyed on
  `octocat`, fetched with **your** GitHub credentials.
- **Roll back** — the seeded identity and its issues all vanish.

**Declared:** nothing extra — the same `GitHubIssue` join. Seeding falls out of the rule that a
pinned literal (inline `{login:'…'}` **or** `WHERE g.login = '…'`) can stand in for a missing real
anchor.

> **Why this matters.** It turns the connecting user's API access into a *query surface over the
> whole external system*, not just their own row. "Issues `octocat` raised", "contacts at
> `acme.com`", "the movie with imdb id `tt0133093`" are all literal-seeded fetches. Multiple
> seeded joins compose and intersect:
> `MATCH (me)-[:RAISED]->(i)<-[:ASSIGNED]-(:GitHubIdentity {login:'octocat'})` materializes both
> sides and keeps only issues you raised that octocat is assigned.

---

### 3.4 Predicate pushdown — scope the fetch at the source

```cypher
MATCH (p:Person {name:'James Governor'})-[:HAS_GITHUB]->(g)-[:RAISED]->(i:GitHubIssue)
WHERE i.html_url CONTAINS 'embabel/me'
RETURN i.title
```

**Means:** "James's issues **in the `embabel/me` repo**."

**How it executes (with pushdown):**

- Probe + resolve the bridge as before → `g.login = 'monkchips'`.
- **Fetch — pushed down.** Instead of fetching *all* of monkchips's issues and discarding the ones
  not in `embabel/me`, the engine renders the `WHERE i.html_url CONTAINS 'embabel/me'` predicate
  into the source's native filter: the GitHub search becomes `is:issue author:monkchips repo:embabel/me`.
  One scoped search returns only the matching issues.
- Materialize / run / roll back as usual. The same `WHERE` still runs in the graph too, so
  **correctness never depends on pushdown** — it only changes cost and coverage.

**How it executes *without* a pushdown rule declared:** the engine fetches monkchips's issues
broadly (paged, capped) and the graph-side `WHERE` drops non-matches. Correct, but wasteful, and
it can hit the source's result cap before your matches (see §3.5).

**Declared:** a `pushdown:` rule on the `issuesByAuthor` producer mapping the `html_url` predicate
to a `repo:{value}` qualifier (with a `valuePattern` regex to extract `owner/repo` from a URL).

---

### 3.5 Pagination, batching, and the starvation trap (`batchSafe`)

```cypher
MATCH (me:AssistantUser)-[:EMAILED]->(p:Person)-[:HAS_GITHUB]->(g)-[:RAISED]->(i:GitHubIssue)
RETURN p.name, i.title
```

**Means:** "Issues raised by everyone I email." This binds **many** anchors (every person you
email), each resolving to a GitHub login.

**How it executes:**

- Probe binds *all* the emailed people; the bridge resolves each to a login →
  `['monkchips', 'jamesward', 'chanezon', …]`.
- **Fetch — the subtlety.** Could the engine pass all logins to GitHub's issue search in one call,
  `author:monkchips author:jamesward …`? It **must not**, and this is why `batchSafe: false` exists
  on that producer: GitHub issue search returns **one globally-ranked, capped list** (most-recently
  updated first). A prolific author fills the cap; a low-volume colleague's issues fall off the end
  — so you'd see them for one question and find nothing for the next. With `batchSafe: false` the
  engine fetches **one author per call**, giving each their own budget.
- **Pagination.** Each per-author search **walks pages** (`paging: { style: page, size: 100, maxPages: 10 }`)
  and accumulates, so an author with 250 issues yields all 250 (3 pages), not just the first 100.
- Materialize / run / roll back.

**The cost levers, conceptually:**

- **`maxKeysPerCall`** — how many keys go in one call (the endpoint's `IN`/`OR` cap). Keeps a wide
  traversal from becoming N+1.
- **`batchSafe: false`** — a *capability*, not a number: "one call is not complete per key." Forces
  one key per call regardless of `maxKeysPerCall`, so a pack can't reintroduce starvation by
  tuning.
- **`paging:`** — capture beyond page 1; `maxPages` bounds the cost.
- If pagination hits `maxPages` with a still-full last page, the source **has more than was
  fetched** → the result carries a `PARTIAL_RESULT` truncation note (§7) — never a silent
  "that's everything."

---

### 3.6 Brought sub-graph — parent and children in one fetch

```cypher
MATCH (p:Person {name:'Ada Lovelace'})-[:HAS_HUBSPOT_CONTACT]->(c:HubSpotContact)-[:HAS_COMMENT]->(note:HubSpotComment)
RETURN c.company, note.text
```

**Means:** "Ada's HubSpot contact **and the notes on it**."

**How it executes:**

- Probe + fetch Ada's contact as in §3.1 — but the contact record *already embeds* its comments
  (`{ email, company, comments: [ {id, text}, … ] }`).
- **Materialize the brought sub-graph.** The engine extracts the embedded `comments[*]`, makes a
  transient `(:HubSpotComment:Virtual)` per comment, and links `(c)-[:HAS_COMMENT]->(note)` — all
  from the **single** fetch. No second call.
- Run / roll back.

**Declared:** a `brings:` entry on the contact join naming the child type, edge, the JSONPath to
the embedded list (`$.comments[*]`), and the child's identity property.

> **Why `brings` not a second join.** When the source already returns the children inline (an
> `expand`/`include`/sideload param), declaring them as `brings:` fetches the whole sub-graph in
> one call. A separate join would re-probe and re-fetch — slower, and it would need the children's
> own anchor key. Pair `brings` with the endpoint's sideload params so the children arrive together.

---

### 3.7 Filtered anchors — fetch only what survives the filter

```cypher
MATCH (p:Person)-[:HAS_GITHUB]->(g)-[:RAISED]->(i:GitHubIssue)
WHERE toLower(p.name) CONTAINS 'governor'
RETURN i.title
```

**Means:** "Issues by people named *Governor*" — not the whole address book.

**How it executes:**

- **Probe applies your `WHERE`.** The probe binds only people whose name contains "governor", so
  the bridge resolves *those* people's logins only, and the fetch is for *those* logins only.

The key point: **the query's own filter scopes the fan-out**. `WHERE p.name CONTAINS 'governor'`
is not just a post-filter — it decides *who gets resolved and fetched* in the first place, so a
filtered query over millions of people costs a handful of fetches, not millions.

---

### 3.8 Existence and intersection across sources (`EXISTS` / `NOT EXISTS` / `OR`)

```cypher
MATCH (me:AssistantUser)-[:EMAILED]->(p:Person)
WHERE EXISTS { (p)-[:HAS_GITHUB]->(:GitHubIdentity) }
  AND EXISTS { (p)-[:HAS_HUBSPOT_CONTACT]->(:HubSpotContact) }
RETURN p.name
```

**Means:** "People I email who are **both** on GitHub **and** in HubSpot."

**How it executes:**

- The engine sees the two virtual labels **inside the `EXISTS` subqueries** and materializes both,
  anchored on each emailed person `p`. (The edges inside `EXISTS`/`NOT EXISTS`/`OPTIONAL`/`COUNT`/
  `COLLECT` are treated as *non-required* — they do not narrow which anchors get probed, but their
  targets *are* materialized so the existence test can be evaluated.)
- After materialization, `EXISTS { … }` is a normal Cypher test: keep only people who got **both**
  a `GitHubIdentity` and a `HubSpotContact` materialized.

The same mechanism powers `NOT EXISTS` ("in HubSpot but **not** on GitHub"), `OR` ("on GitHub **or**
in HubSpot"), and `COUNT { … }`. Express existence with `EXISTS { }`, not an `OPTIONAL MATCH … WHERE
x IS NOT NULL` (which does not filter) and not a self-referential round-trip `(p)-[:R]->(x)<-[:R]-(p)`
(which matches nothing under Cypher's relationship-uniqueness rule).

---

### 3.9 Fan-out aggregate — count over fetched data

```cypher
MATCH (me:AssistantUser)-[:EMAILED]->(p:Person)-[:HAS_GITHUB]->(g)
WITH p, COUNT { (g)-[:RAISED]->(:GitHubIssue) } AS issues
ORDER BY issues DESC LIMIT 1
RETURN p.name, issues
```

**Means:** "Which person I email has raised the most GitHub issues?"

**How it executes:**

- Probe + resolve bridges for all emailed people.
- For the `COUNT { (g)-[:RAISED]->(:GitHubIssue) }`, the engine materializes each identity's issues
  — but because the issues are only **counted**, not returned, it can fetch an **existence/count**
  shape (a one-page semijoin per author) rather than every issue's full body.
- Run the aggregate over the materialized counts, order, take the top.

Aggregates (`COUNT`, `sum`, `collect`, `max`) work over virtual nodes exactly as over real ones;
the engine's job is to materialize *enough* to answer them within the caps.

---

### 3.10 Vector edge — similarity is the join (`RELEVANT_TO` + `r.score`)

```cypher
MATCH (p:Person {name:'Ada Lovelace'})-[r:RELEVANT_TO]->(t:RelevantEmailThread)
RETURN t.subject, t.snippet, r.score
ORDER BY r.score DESC
```

**Means:** "Email threads **about / related to** Ada" — by *meaning*, not by a recorded fact.

**How it executes:**

- **Probe** — bind `p` (Ada). The **key here is not an id — it is embeddable text**: Ada's *name*.
- **Fetch — a similarity search, not a keyed lookup.** The `relatedThreads` producer (`kind:
  vector`) embeds the anchor text ("Ada Lovelace") and runs a **top-k** vector search over your
  email-thread summaries, returning the `k` nearest threads, each with a **similarity score**.
- **Materialize — the score lands on the *edge*.** Each hit becomes a transient
  `(:RelevantEmailThread:Virtual)`, linked `(ada)-[r:RELEVANT_TO {score: 0.83}]->(t)`. The
  similarity is a property of the *relationship* — "how relevant is this thread *to Ada*" — not of
  the thread itself (the same thread can be more relevant to one anchor than another).
- **Run** — `ORDER BY r.score DESC` ranks the threads by relevance; `RETURN r.score` exposes it.
- **Roll back.**

**Declared:** a `RelevantEmailThread` type whose `virtualJoins` anchor on `Person` /
`Organization` / `Meeting` via `RELEVANT_TO`, with `keyField` = the embeddable text (`name` /
`subject`) and `recordKeyField: matchedFor`; and a `producers/` entry `relatedThreads`
(`kind: vector`, `index: email_threads`, `k`, `minScore`). See §6 for the full vector-edge model.

---

### 3.11 A bridge reachable only *through* another virtual node (staged re-planning)

```cypher
MATCH (o:HubSpotOwner)-[:OWNS_CONTACT]->(c:HubSpotContact)<-[:HAS_HUBSPOT_CONTACT]-(p:Person)-[:HAS_GITHUB]->(g:GitHubIdentity)-[:RAISED]->(i:GitHubIssue)
WHERE o.email = 'me@example.com'
RETURN p.name, i.title
```

**Means:** "For the contacts I *own* in HubSpot, which of those people are on GitHub, and what
issues did they raise?" The GitHub anchor `p` is reachable **only through** a virtual node (`c`),
which doesn't exist until HubSpot is fetched.

**How it executes — in waves:**

- **Wave 1.** Only `o` is bound (by the literal email). Materialize `c` (the owned contacts) from
  `o`. Now `c` is *real for this transaction*.
- **Wave 2.** With `c` real, the closure extends through it to `p` (the canonical Person behind
  each contact) — `p` is now bound. Resolve the `HAS_GITHUB` bridge for those people → materialize
  `g`.
- **Wave 3.** With `g` real, materialize `i` (their issues).
- **Run / roll back** over the fully-assembled graph.

The engine **re-plans after each wave**, treating everything materialized so far as real, until no
new virtual node becomes reachable (a fixpoint, bounded by a stage cap). You write one query; the
engine discovers the dependency order.

---

### 3.12 Convergence — the same node reached two ways

```cypher
MATCH (p1:Person {name:'Ada Lovelace'})-[:HAS_HUBSPOT_CONTACT]->(c:HubSpotContact)<-[:HAS_HUBSPOT_CONTACT]-(p2:Person {name:'Ada L.'})
RETURN c.company
```

**Means:** two graph aliases for the same person both resolve to the *same* HubSpot contact.

**How it executes:** both anchors fetch, but because `HubSpotContact` declares an **identity**
property (its `email`/`id`), the two fetched records **MERGE into one transient node** with two
incoming edges — not two duplicate contacts. Any join that can fan in this way **requires** an
identity property so convergent paths dedupe.

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

And these run but are **capped** (never silently — see §7): a probe binding more than `maxAnchors`
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
| `remote` (alias `api`) | a gateway op — pack handler or learned REST API | the anchor's id/email/login (list, string-template, or path-param mode) |
| `sql` | a `SELECT … IN (:keys)` against a pack datasource | the anchor key, expanded into the `IN` clause |
| `compute` | an in-process function over the keys (scores, rollups, synthesis) | the anchor key; no external I/O |
| `vector` | top-k semantic similarity to the anchor's **text** | nothing — *similarity is the join* (§6) |

All producers honour the **batch contract** (all keys at once, never N+1) and an orthogonal
`cache:` policy (`none` / `ttl` / `session` / `immutable`).

---

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

### 6.4 Privacy: the source enforces scope, not the rewriter

A vector search runs *inside* the producer (against an embedding index), **bypassing** the Cypher
scope rewriter that guards keyed traversals. So the **producer/index is responsible for per-user
scoping**: the search is filtered by `userId`, and a search with no user returns **nothing**
(fail-closed). For `relatedThreads` this is intrinsic — it searches *the acting user's own*
thread-summary index. A `vector` producer over shared data must apply the same `userId` filter; a
vector join can never surface another user's documents.

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

---

## 7. Caps, cost, and diagnostics

Because a Virtual Cypher query reaches into live external systems, it is bounded on every axis, and
a bound that bites is **always surfaced**, never silent.

**Caps (per join):**

- **`maxAnchors`** (default 200) — reject if the probe binds more anchors than this (a fan-out
  guard; pin/filter the anchor).
- **`maxFanoutTotal`** (default 5 000) — reject if materialization would create more nodes than
  this (primary + brought).

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

A failed fetch is **never cached** as an empty result (so a later call with a refreshed token finds
the data); only a genuine, successful "no records" is cacheable.

---

## 8. Determinism and guarantees

- **Read-only.** A user query never writes the graph. Materialization happens in a transaction that
  is **rolled back**; the sole persisted side effect is a write-through identity **bridge** (a
  cache of *who* an external identity is, not *what* data they hold).
- **Scoped, fail-closed.** Every keyed probe goes through the per-user scope rewriter; vector
  searches are user-filtered at the source. A query can never read across users; an unparseable or
  unscopable query is rejected, not run.
- **Bounded.** Every fetch is bounded by a bound anchor, `maxAnchors`/`maxFanoutTotal`, `paging`
  caps, `k`, and rate budgets. Truncation is reported.
- **Idempotent re-runs.** A re-run re-fetches; caching (`ttl`/`immutable`) and `temperature: 0` for
  any LLM-derived value make repeated runs of the same query agree — repeatability is a correctness
  property, not just a speed one.

---

## 9. The contract, in one line

> **Bind a real anchor; declare how a label is fetched; the engine probes, fetches once per
> producer, materializes transiently, runs your Cypher over real + virtual together, and rolls
> back.** Persistence is the exception (warm-cached identity bridges), not the rule.

For the declarative surface (`virtualJoins:`, `producers/`, `resolve:`, `pushdown:`, `paging:`,
`brings:`, `cache:`) see [`README.md`](./README.md#joining-types-on-demand-virtual-joins-not-mirrored).

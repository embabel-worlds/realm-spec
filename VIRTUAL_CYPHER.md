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
- narrowed by **any** property predicate — `WHERE toLower(p.name) CONTAINS 'grace'`, or
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
MATCH (p:Person {name:'Grace Hopper'})-[:HAS_GITHUB]->(g:GitHubIdentity)-[:RAISED]->(i:GitHubIssue)
RETURN i.title, i.html_url
```

**Means:** "What GitHub issues has Grace raised?" — but the graph holds no GitHub data at all.
Two virtual hops: first resolve *which GitHub account is Grace*, then fetch *that account's
issues*.

**How it executes:**

- **Probe** — bind `p` (Grace), read her email.
- **Resolve the bridge** (`HAS_GITHUB` is an identity bridge — §5.2). Run Grace's `resolve:`
  chain: is there already a `GitHubIdentity` linked to her (`existingBridge`)? a learned
  `githubLogin` on her node (`learnedHandle`)? otherwise look her email up via the
  `githubUsersByEmail` producer (`canonicalEmail`). Say it resolves to login `devone`. The
  bridge `(p)-[:HAS_GITHUB]->(:GitHubIdentity {login:'devone'})` is **persisted**
  (write-through) so the next query skips this step.
- **Now `g` is a real, bound node.** Its key is `login = 'devone'`.
- **Fetch** the downstream join — call the `issuesByAuthor` producer with `['devone']`. It
  searches GitHub for `author:devone`, returns the issue records.
- **Materialize** each as `(:GitHubIssue:Virtual)` linked `(g)-[:RAISED]->(i)`.
- **Run / roll back** — `RETURN` reads the issues; the issues roll back (the *bridge* stays, as a
  warm cache).

**Declared:** `GitHubIdentity` with a `resolve:` bridge join from `Person`; `GitHubIssue` with a
plain `virtualJoins` entry `{ anchorLabel: GitHubIdentity, relationship: RAISED, keyField: login, producer: issuesByAuthor }`.

> **Why two declarations, not one.** The bridge (who-is-Grace) and the data (her issues) have
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
MATCH (p:Person {name:'Grace Hopper'})-[:HAS_GITHUB]->(g)-[:RAISED]->(i:GitHubIssue)
WHERE i.html_url CONTAINS 'acme/app'
RETURN i.title
```

**Means:** "Grace's issues **in the `acme/app` repo**."

**How it executes (with pushdown):**

- Probe + resolve the bridge as before → `g.login = 'devone'`.
- **Fetch — pushed down.** Instead of fetching *all* of devone's issues and discarding the ones
  not in `acme/app`, the engine renders the `WHERE i.html_url CONTAINS 'acme/app'` predicate
  into the source's native filter: the GitHub search becomes `is:issue author:devone repo:acme/app`.
  One scoped search returns only the matching issues.
- Materialize / run / roll back as usual. The same `WHERE` still runs in the graph too, so
  **correctness never depends on pushdown** — it only changes cost and coverage.

**How it executes *without* a pushdown rule declared:** the engine fetches devone's issues
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
  `['devone', 'devtwo', 'devthree', …]`.
- **Fetch — the subtlety.** Could the engine pass all logins to GitHub's issue search in one call,
  `author:devone author:devtwo …`? It **must not**, and this is why `batchSafe: false` exists
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
  fetched** → the result carries a `PARTIAL_RESULT` truncation note (§9) — never a silent
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

**Means:** "Issues by people named *Hopper*" — not the whole address book.

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
| `keyword` | top-k **lexical** (fulltext, exact-token) match to the anchor's text — the honest fit for "MENTIONS \<term\>" | nothing — same relevance contract as `vector`, only the mode differs (§6.6) |
| `agentic-rag` | a **bounded LLM retrieval loop** over the same index: reformulates, runs both modes, reads further into inconclusive candidates, returns only documents it *judges* fit the edge's `intent` brief | nothing — relevance as a judgment (§6.6); EXPENSIVE, select explicitly |
| `remote-search` | top-k **lexical** match via the REMOTE store's OWN search API (a gateway op with `{query}` substituted per anchor — e.g. Drive `fullText contains`); live, nothing ingested | nothing — same relevance contract as `keyword`, but the source searches itself; per-match `mode:'keyword'`/`rank` on the edge, score is a neutral 1.0 (matched, not similarity) |
| `generative` | an LLM **invents** plausible records ("suggest things like X"), each resolved onto the spine via `resolveVia`; demand-driven (re-probes with a growing exclusion until enough survive) | the anchor's name/text, batched into ONE prompt |
| `aggregate` | gathers the anchor's connected neighborhood and LLM-**reduces** it to ONE record (a taste summary, a digest) | the anchor's identity; one record per anchor |

All producers honour the **batch contract** (all keys at once, never N+1) and an orthogonal
`cache:` policy (`none` / `ttl` / `session` / `immutable`).

The two **LLM-backed** kinds (`generative`'s `generator:`, `aggregate`'s `reduce:`) take optional
per-edge tuning — `role:` (a portable, workspace-defined model role id such as `chat_cheap`; **never a
concrete model name**, which stays an ops concern) and `temperature:`. A query can override both for one
fetch with the `ai_model` / `ai_temperature` edge directives (§7.2.1).

### 5.4 Entity canonicalization — the spines a join anchors on

Every example above anchors on a canonical `Person` or `Organization`. Those are **spines**: the
single node a real human or company resolves to, no matter how many sources mention them. A spine is
keyed deterministically — **Person by email, Organization by registrable domain** — so two records
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
`(p:Person)-[:WORKS_FOR]->(o:Organization)` edge onto the shared spine — read the contact's company
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
constraint on its `id`. Resolving a key is one indexed hop
(`(:Domain {id})-[:USED_BY_ORG]->(o:Organization)`), never a scan, and the key-nodes are **shared**
with the email/sender graph, so a canonicalized record and an emailed person dedupe to one spine. The
spine's own `id` is uniqueness-constrained too, so the deterministic MERGE can never fork a duplicate.

**The two built-in spines are not hardwired — they are config.** A spine is declared by a
`CanonicalSpec` (label, key property, id prefix, normalization primitives, key-node + edge); Person
and Organization are just the two built-ins. Add a `Place`, `Repository`, or `Product` spine in
`application.yml` and source types join it by tagging a property `target: <newLabel>` — the engine
builds the hub, applies the key-node uniqueness constraint at boot, and the join surface above works
unchanged.

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

## 7. LLM query primitives — filter, rerank, and steer with `ai_*`

Vector edges (§6) answer "which rows are *about* X" with an **embedding** — cheap, but only as good as
the similarity model, and blind to any judgment that isn't cosine distance. Sometimes the discriminator is
one no property and no embedding captures: *"news actually about **my** funding round"*, *"papers whose
method is **genuinely** transformer-based, not just name-dropping it"*, *"the issues most **relevant to this
outage**"*. For those, the query can call a **per-row LLM judgment** inline, expressed as a reserved
**`ai_*`** property or function.

These run at **execution time**, over the rows a query has already fetched — the LLM counterpart, at the
value level, of §9's generation-time `examples:` steering. Four primitives across the three query positions:

- **`{ai: {hint, model, temperature, confidence, fresh, voice, wordcount}}`** — *steer and tune* the
  fetch behind an edge, as a nested directive map (§7.2; flat `ai_*` spellings are aliases);
- **`{pack: {…}}`** — the pack's OWN prompt parameters, passed verbatim (§7.2.2);
- **`WHERE n.ai_relevant = '<criterion>'`** — *filter* rows by subjective relevance;
- **`ORDER BY ai_score(n, '<criterion>') DESC`** — *rerank* rows by subjective fit;
- **`RETURN ai_classify(n, '<dimension>')`** — *label* each row along a subjective dimension.

### 7.1 The `ai` and `pack` namespaces are reserved

Any property or function in the **`ai`** namespace — the bare `ai` key, the flat `ai_*` prefix, or the
`ai.*` function form — is an **engine primitive, never data**, and the bare **`pack`** key is likewise
reserved (§7.2.2). A pack MUST NOT declare a stored property or a producer field named `ai`, `ai_*`, or
`pack`; the graph schema is open and pack-defined, so the reservation is what keeps the primitives
collision-free and self-documenting to the generator. `ai_relevant` and `ai_score` are **"fake" columns**:
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

The flat spellings (`ai_hint`, `ai_model`, …) remain accepted **aliases** of the map form. The `ai`
namespace is **closed**: an unknown key inside it is warned about as a probable typo, never silently
ignored. Its keys:

- **`hint`** — the free-text steer the schema has no property for (a mood, a vibe, a language, an
  angle), reaching the generator's prompt as `{{ hint }}` or folding into an aggregate's reduce
  instruction. A **soft steer, not a filter**: everything the schema *can* express (genre, year, a
  rating floor) belongs in an ordinary `WHERE`.
- **`model`** — a portable, **workspace-defined role id** (e.g. `chat_cheap`, `code_best`), resolved
  through the workspace's role map exactly like the pack edge's own `role:` declaration. A query
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
  target, never a token cap — truncation mid-sentence is worse than a 10% overshoot).

**Precedence:** query directive → the pack edge's own declaration (§5.3 generator, aggregate `reduce`)
→ the deployment default. The directives apply to **generative** edges (the generator call) and
**aggregate** edges (the fan-in reduction) alike, for **that query only** — cached results are keyed by
the full steering, so a `chat_cheap`, breezy, 40-word run never serves from (or pins) the plain cache
entry. The whole block is **steering, not data**: stripped from the executed query, never stamped onto
a materialized edge. And since views are saved queries, a pack can bake any of it into a view
(a `CheapRecommendations` view with `{ai: {model:'chat_cheap'}}`) with no extra mechanism.

#### 7.2.2 The `{pack: {…}}` map — the pack's own prompt parameters

Where `ai` is the closed embabel-standard namespace, **`pack`** is the **open** one: its keys pass
through **verbatim** to the producer's prompt — a generative template variable, or a `key: value` line
folded into an aggregate's reduce instruction. The pack defines its own steering vocabulary by simply
referencing the variable in its prompt; an unreferenced key is inert:

```cypher
-- pack-movie's prompts opt into an `era` parameter ({% if era %} … {{ era }}):
MATCH (ts)-[:SUGGESTS {pack: {era: 'the 1970s'}, ai: {model: 'chat_cheap'}}]->(m:Movie)
RETURN m.title
```

Pack parameters are steering like everything above — stripped from the read, never stamped, part of the
cache key — and can never clobber the engine's reserved template variables (`anchors`, `exclude`,
`want`, `hint`, …).

### 7.3 `ai_relevant` — the per-row relevance filter

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(n:NewsItem)
WHERE n.ai_relevant = 'about my company''s Series A funding round'
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
- **Stamp & run.** The criterion is written onto each surviving row under `ai_relevant`, so the final
  `WHERE n.ai_relevant = '…'` matches as ordinary data — no query rewrite. It **composes** with real
  predicates via `AND` (the date filter above) and with other `ai_` primitives.

Use it **only** for a subjective *about / relevant-to* that maps to **no** shown property; for a concrete
field, an ordinary `WHERE` is cheaper and exact.

### 7.4 `ai_score` — the per-row rerank

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(n:NewsItem)
RETURN n.title, n.url
ORDER BY ai_score(n, 'relevance to my Series A funding round') DESC
LIMIT 5
```

**Means:** "rank the fetched news by how well each fits, and give me the top five" — the highest-value
retrieval lever, a learned relevance sort where no orderable property exists.

**How it executes:**

- **Fetch** as above.
- **Judge — the same batched 0..1 scoring** as `ai_relevant` (the two share one judgment; a query using
  both scores once and both filters and ranks off it). Every row is **kept** and its score **stamped** under
  `ai_score`.
- **Rewrite & run.** Neo4j has no `ai_score` function, so the executor rewrites the call in the executed
  query to `coalesce(n.ai_score, 0.0)` (0.0 for any row that wasn't scored), and `ORDER BY … DESC LIMIT k`
  ranks and truncates against the stamp.

The idiomatic **filter-then-rank**: `WHERE n.ai_relevant = '…' … ORDER BY ai_score(n, '…') DESC LIMIT k` —
narrow to the relevant, then order the survivors by fit.

### 7.5 `ai_classify` — the per-row projection

```cypher
MATCH (me:AssistantUser)-[:TRACKS]->(n:NewsItem)
RETURN n.title,
       ai_classify(n, 'urgency: high, medium, or low')     AS urgency,
       ai_classify(n, 'topic in one word')                 AS topic
```

**Means:** "return the fetched news, and *label* each item along a dimension there is no column for" — a
computed, LLM-decided category rather than a stored field.

**How it executes:**

- **Fetch** as above.
- **Label — one batched call per dimension.** Each fetched row's text is labelled for the named dimension
  (if the dimension lists categories, the label is one of them; otherwise a short free label). Every row is
  **kept** and its label **stamped** under a **per-dimension slug property** (`ai_classify_urgency…`), so two
  classifications in one `RETURN` never collide.
- **Rewrite & run.** As with `ai_score`, the executor rewrites each `ai_classify(n, '…')` in the executed
  query to `coalesce(n.ai_classify_<slug>, '')` (blank for any unlabelled row), and the projection returns it.

Use it **only** for a subjective label no property holds; when a real field already carries the value, return
that. (It is a *projection*, not a filter — to keep only one category, classify and then `WHERE label = '…'`,
or use `ai_relevant` directly.)

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
# config/views/key-accounts.yml — durable/shared, like a virtual type today (a pack or workspace can ship it)
- name: my_key_accounts
  materialized: false            # regular view — expands at query time
  outputLabel: HubSpotContact    # the type the view yields (its rows ARE this type)
  cypher: |
    MATCH (me:AssistantUser)-[:HAS_HUBSPOT_OWNER]->()-[:OWNS_CONTACT]->(c:HubSpotContact)
    WHERE c.arr > 100000
    RETURN c
```

The same body can be authored at runtime by the assistant on the user's behalf (`viewService.define(user, name,
cypher, materialized)`, surfaced as a `define_view` tool) — "save this as my key accounts."

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
is graph-colocated and transactional: a `MaterializedView {view, userId, expiresAt}` marker node with
`[:MEMBER]` edges to the cached result nodes, swept by TTL. But the store is an SPI:

```kotlin
interface ViewMaterializationStore {
  fun freshUntil(view: String, userId: String): Long?             // marker expiry epoch-ms, or null if absent
  fun materialize(view: String, userId: String, memberIds: List<NodeId>, expiresAt: Long)
  fun members(view: String, userId: String): List<NodeId>         // the cached node ids to bind the label off
  fun clear(view: String, userId: String)
  fun sweepExpired()
}
```

so an alternative strategy swaps in without touching the query path: an **in-memory LRU** for a single-process
deployment, an **external KV / Redis** for a horizontally-scaled one, or an **`immutable`** strategy (no TTL,
explicit invalidation only) for reference data. The refresh policy (`ttl`, cron `refresh:`) is orthogonal to
the store.

### 8.5 A general result / entity cache — and negative results

The same store generalizes beyond views to a **producer result cache** — the answer to "should API fetches be
cached?" A producer call is `(producer, key) → records`; caching keys on exactly that, governed by the §9
diagnostics:

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
the reader needs no per-query type argument. This is the source side of the type-and-verb model: the saved
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

- **Attribution.** Each example is attributed to its type's schema *segment* (the pack's group, or
  a host group like `email-topics`) and renders only when that segment does — under schema-relevance
  filtering an example loads exactly when the question needs its domain. Steering grows with the
  number of domains; per-question prompt cost stays flat.
- **Connection gating.** Examples gate with the type's joins: a disconnected integration
  contributes neither schema nor steering.
- **Placement rule.** An example lives on the type that OWNS the path it teaches. A bridge across
  packs (thread → topic) is taught by the type that owns the *target* of the lesson.

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

## 12. The contract, in one line

> **Bind a real anchor; declare how a label is fetched; the engine probes, fetches once per
> producer, materializes transiently, runs your Cypher over real + virtual together, and rolls
> back.** Persistence is the exception (warm-cached identity bridges), not the rule.

For the declarative surface (`virtualJoins:`, `producers/`, `resolve:`, `pushdown:`, `paging:`,
`brings:`, `cache:`, `views:`) see [`README.md`](./README.md#joining-types-on-demand-virtual-joins-not-mirrored).
Views (regular / materialized, output typing, the pluggable cache, persisted scopes, and hydrating a
scope into typed instances) are §8.

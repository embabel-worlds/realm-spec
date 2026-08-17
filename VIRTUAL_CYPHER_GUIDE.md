# Virtual Cypher — User Guide

**How to use Virtual Cypher**, by example. The normative reference is
[`VIRTUAL_CYPHER.md`](VIRTUAL_CYPHER.md); a one-page summary is
[`VIRTUAL_CYPHER_CHEATSHEET.html`](VIRTUAL_CYPHER_CHEATSHEET.html). Where the two disagree, the
spec wins — this guide teaches, it does not define.

Read the examples in order: later ones build on earlier.

---

## The idea in one paragraph

Your graph holds what you own. Everything else — a CRM contact, a GitHub issue, a paper, a clinical
trial — lives in somebody else's system. Virtual Cypher lets you **traverse into it as though it
were already in the graph**: you write one Cypher query, and the engine fetches the far side on
demand, materializes it for the life of the query, and rolls it back. Nothing is mirrored, so
nothing goes stale.

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
  Page numbering starts at 1 by default. For a zero-based source, declare
  `paging: { style: page, startPage: 0, size: 200, maxPages: 2 }`; that fetches pages 0 and 1.
  `maxPages` counts calls, not absolute page numbers.
- Materialize / run / roll back.

**The cost levers, conceptually:**

- **`maxKeysPerCall`** — how many keys go in one call (the endpoint's `IN`/`OR` cap). Keeps a wide
  traversal from becoming N+1.
- **`batchSafe: false`** — a *capability*, not a number: "one call is not complete per key." Forces
  one key per call regardless of `maxKeysPerCall`, so a realm can't reintroduce starvation by
  tuning.
- **`paging:`** — capture beyond the first page; `startPage` matches the source's page-number origin,
  while `maxPages` bounds how many pages are fetched.
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

### 3.13 One anchor, many keys — joining on a list-valued property

A property that holds several values is several keys, not one. If a trial lists three collaborators,
each is looked up in its own right:

```cypher
MATCH (t:ClinicalTrial)-[:COLLABORATES_WITH]->(c:CorporateEntity)
WHERE t.nctId = 'NCT01234567'
RETURN c.name, c.ultimateOwner
```

The join declares `keyField: collaborators`, and that property is a list. Blank and duplicate entries
are dropped, so a name shared by two trials is fetched once — and because `CorporateEntity` declares an
identity, both trials end up pointing at the *same* node. That is what makes counting possible: the
question "which company appears across the most trials" only has an answer if one company is one node.

### 3.14 Narrowing at the source — membership pushdown

```cypher
MATCH (s:DiseaseScope {registryQuery: 'Long COVID'})-[:HAS_TRIAL_SEARCH]->(r:TrialSearchRun)
MATCH (r)-[:RETURNED]->(t:ClinicalTrial)
WHERE t.overallStatus = 'RECRUITING' AND 'OLDER_ADULT' IN t.ageGroups
RETURN t.nctId, t.title
```

Both conditions can reach the registry, so the fetch returns the trials that match instead of every
trial for the disease. Nothing about the *result* depends on that: if the source could not apply
either filter, the same rows would come back after filtering the materialized graph, and only the
number of records fetched would differ.

Note the direction of the membership test. `'OLDER_ADULT' IN t.ageGroups` asks whether the record's
list contains a value; `t.overallStatus IN ['RECRUITING', 'COMPLETED']` asks whether the record's
value is in a list *you* wrote. They are different questions, and only the first describes a
list-valued property.

---

### 3.15 Attributed reporting — prose that arrives with its receipts

A realm that resolves a name against outside sources eventually wants to *say* what it found, in
prose. The moment it does, it inherits a problem no query has: a fluent sentence about who someone is
looks the same whether a source said it or the model did.

The shape that survives that is one call returning both:

```cypher
MATCH (f:PartyFamilyQuery {name: $familyName})-[:HAS_BACKER]->(b:FamilyBacker)
WITH b ORDER BY b.total DESC LIMIT $limit
OPTIONAL MATCH (c:CoverageQuery {phrase: b.donor_name})-[:HAS_READ_RESULT]->(h:SourceHit)
WITH b, collect({kind: …, title: h.title, url: h.url, text: left(h.excerpt, 700)})[0..3] AS srcs
WITH b.donor_name AS subject, srcs,
     b.donor_name + ' disclosed $' + toString(b.total) + '.' +
     reduce(acc = '', s IN srcs |
       acc + ' SOURCE, ' + s.kind + ' — ' + s.title + ' <' + s.url + '>: ' + s.text) AS line
RETURN subject,
       render(line, 'Report the facts, then who this is according to its SOURCE lines, naming each
                     source. Never assert a connection yourself; a source says it.') AS prose,
       head(collect(srcs)) AS attributions
```

Four things in that query are doing work, and each was learned by getting it wrong first.

**The evidence travels in the same row as the prose.** `render(...)` and `collect(...)` are two
aggregations over one group, so a caller cannot quote the sentence without the citations that support
it. Fetching citations in a second query looks equivalent and is not: the two can be separated, and
then every subjective statement in the prose is unsupported by construction.

**One composition per subject, not one per report.** Returning `subject` beside the aggregation makes
the reduction run once per subject. That is a correctness choice. Composing eight subjects in one
pass drifts — a synonym here, a connection there — and a single bad sentence condemns the whole
output; composing one subject at a time keeps each paragraph's world small, and a paragraph that
fails can be composed again while the others stand. It also makes coverage structural: N subjects in,
N rows out, and a missing subject is a missing row rather than a silently shorter paragraph.

**The quote is bounded.** A page excerpt can be thousands of characters; three of those per subject
exceeds what one composition call holds, and the reduction then folds its own partials and quietly
drops subjects. Cut the quote to the sentence that identifies the subject.

**The source's KIND is a value, not a footnote.** A substantial-holder notice lodged under law, a
government register and a masthead are different grades of evidence, and a reader must be able to
tell which they are being shown without opening anything. Rank by that grade before slicing, so what
survives is the strongest evidence rather than whatever the search engine ranked first.

#### Checking it

Return the same joined rows *unaggregated* from a sibling view. An aggregation consumes its input, so
that sibling is the only way to see what the composer actually read — and with it, every word of the
prose can be held against the sources for that subject: a word appearing in none of them is how a
fabrication reads. Judging per subject is stricter than judging a whole report, because a sentence
about one subject cannot then be "supported" by a page fetched for another.

What to do with a word that traces to nothing is a publishing decision, not a query one. Reporting it
beside the paragraph is honest; quietly smoothing it away is the failure the whole pattern exists to
prevent.

---

## Where to go next

- Something you wrote was rejected? [§4 of the spec](VIRTUAL_CYPHER.md#4-what-is-not-possible--and-why)
  lists every plan-time refusal and the reason for it.
- Declaring a producer or a join? [§5 The join surface](VIRTUAL_CYPHER.md#5-the-join-surface-reference).
- Asking a model to judge, group or summarise rows?
  [§7 LLM query primitives](VIRTUAL_CYPHER.md#7-llm-query-primitives--filter-rerank-and-steer-with-the-ai-namespace).

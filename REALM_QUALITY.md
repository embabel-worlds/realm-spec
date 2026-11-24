# Realm quality

**Spec version: 0.1.0**

Status: normative guidance for realm authors. Nothing here changes what a host accepts; it is the bar
a realm is brought up to before it is called finished.

A realm's declarations are all a model knows about the system behind it, and all a planner knows
about what that system can do. A model that is told `status: "Status."` guesses the values. A
planner that is told nothing about a filter fetches everything and filters afterwards. Neither guess
is visible in the answer: the rows come back, the number is confident, and it is wrong or slow.

This document says what good metadata is, rule by rule. Each rule has an id, a level, the reason in a
line, and a short good and bad example. MUST and SHOULD are used as in RFC 2119: a realm that breaks
a MUST is not finished; a SHOULD may be broken for a reason, and the reason belongs in a comment
beside the declaration.

Rules marked **checked** are scored from the realm's files by `embabel realm audit <path>` (see
[Checking a realm](#checking-a-realm)). Rules marked **review** need a person who knows the source:
whether a filter really narrows, whether a description is true. Both count.

**Contents.** [What a model is shown](#what-a-model-is-shown) ·
[Types](#1-types) · [Properties](#2-properties) · [Keys](#3-keys) ·
[Relationships](#4-relationships) · [Pushdown](#5-pushdown) · [Efficiency](#6-efficiency) ·
[Views](#7-views) · [Honest names](#8-honest-names) · [The realm](#9-the-realm) · [Examples](#10-examples) ·
[Checking a realm](#checking-a-realm) · [Rule index](#rule-index)

---

## What a model is shown

Informative: these are the reference host's limits. They are why the rules below put the important
words first.

| Declared | Where a model sees it | Limit |
|---|---|---|
| A type's `description` | The schema a model writes queries from | Cut at **320 characters**, at the last whole sentence that fits. A description that only repeats the type's name is dropped. |
| A property's `description` | Beside the property, when the question names it; whole wherever a type is described in full | **160 characters** in the query schema. |
| A property's `values:` | A "one of these, exactly" note beside the property; a generated query with a literal outside the list is refused | The list, up to 100 values. |
| A join's `description` | The schema, under the relationship it describes | Shown **whole**. This is where guidance for a traversal belongs. |
| A view's `description` | The view listing a model chooses from; whole when the view is described or selected | The listing shows the **first sentence, to 80 characters** (60 when the world has many views). |
| A view param's `description` | When the view is described or run | Shown whole. |
| A type's `examples:` | Rendered into the query generator's prompt when the type's part of the schema is relevant | A few per type. |
| `realm.yml` `description` | Whole, where a model decides which realms a question needs; by its **first sentence** in the guide's index of realms | First sentence to **120 characters** in the index. |
| Pushdown, paging, cache, `batchSafe`, `cost:` | Not shown to a model. Read by the planner. | Decide what is fetched and how often. |

The consequence: guidance a model must act on goes in a type's first 320 characters, in a property's
first 160, on the join the question traverses, or in a view's first sentence. Guidance in a YAML
comment or a README helps the next author and no model.

**A field the host does not read is a promise nothing keeps.** Unknown keys on types, properties,
producers and views are dropped at load, and validation warns about each one with the nearest key that
is read. `unit:`, `currency:` and `format:` on a property ARE read and shown to models (see
[Property measures](DECLARING_TYPES.md#property-measures--unit-currency-format)); `pattern:`,
`valuePattern:`, `examples:`, `default:` and `dimension:` on a *property* do nothing: guidance belongs in
the description, `valuePattern` on a pushdown rule. Rule [Z1](#z1--must-nothing-is-declared-that-the-host-ignores-checked)
covers this.

---

## 1. Types

### T1 — MUST: every type has a description. *Checked.*

*Why:* a type with no description is a label a model can only guess the meaning of. A description
that only says the type's name again is dropped before a model sees it, so it counts as none.

```yaml
# Bad
- name: LagoPlan
  properties: { code: "Plan code." }

# Good
- name: LagoPlan
  description: >-
    One billing plan in Lago, identified by its plan code: the price and interval a subscription
    is billed at. Plans change rarely; a customer's subscriptions name the plan they are on.
```

### T2 — MUST: the first 320 characters say what one node is and what identifies it. *Checked.*

*Why:* the guide stops at 320 characters. A description that opens with history and names its key
in the fourth sentence has, as far as a model is concerned, no key.

Lead with three things, in this order: what one node represents ("One invoice…", "Each row is…"),
the system it comes from, and the property that identifies it. Anything else follows.

```yaml
# Bad: the identity is after the cut
description: >-
  Lago is an open-source billing engine used by many companies. It supports usage-based billing,
  subscriptions, coupons and wallets, and has a rich API… (three more sentences) …Each invoice
  is identified by its lagoId.

# Good
description: >-
  One invoice Lago issued to a customer, identified by lagoId (the invoice number is
  `number`). Amounts are in major units of `currency`. A draft invoice has no number yet.
```

### T3 — MUST: a type reached by more than one path declares its identity. *Checked.*

*Why:* two paths to the same record must dedupe to one node. A type with more than one join, a
populated type, and a spine declare `identity: true` on the property that makes a record unique (or
`spine.key` on a spine).

### T5 — SHOULD: every other fetched type declares its identity too. *Checked.*

*Why:* on a single join nothing breaks without one, but the identity is what a model refers to a record
by, what a key-addressed producer looks it up by, and what T2 asks the description to name.

```yaml
# Bad
- name: ChatwootMessage
  properties: { id: "Message id.", body: "Text." }
  virtualJoins: [ … ]

# Good
- name: ChatwootMessage
  properties:
    id: { identity: true, description: "Chatwoot's message id." }
```

A vocabulary's parent types, which nothing fetches directly, are exempt from both: only the product
knows what makes its records unique.

### T4 — SHOULD: a type says how fresh it is and what it is not. *Review.*

*Why:* "live from the source on every query" and "a nightly mirror" answer "what is open now"
differently. And where two types look alike (a CRM's account and the billing customer for the same
company), the description says which one a question about the other wants.

---

## 2. Properties

### P1 — MUST: every property has a description that says more than its name. *Checked.*

*Why:* `status: "The status."` gives a model nothing it did not have from the name. Put the meaning in
the first 160 characters, which is what the query schema shows.

```yaml
# Bad
title: "Title."
# Good
title: "The headline as the publisher wrote it, unedited; may be in the source language."
```

### P2 — SHOULD: money and measures state their currency or unit. *Checked (heuristic).*

*Why:* `amount > 1000` means one thing in cents and another in dollars, and a sum across currencies
is meaningless. Declare `unit:` and, for money, `currency:` — the property holding each row's ISO 4217
code, or a fixed code — and the host shows both beside the property to every model
([Property measures](DECLARING_TYPES.md#property-measures--unit-currency-format)).

```yaml
# Bad
amount: { type: number, description: "Invoice amount." }
# Good
amountCents: { type: int, unit: cents, currency: currency, description: "Total incl. tax." }
durationMs: { type: int, unit: milliseconds, description: "Wall-clock run time." }
```

### P3 — SHOULD: an enumerated property lists its values, exactly as they appear. *Checked (heuristic).*

*Why:* a model filtering `status = 'Open'` against a source that says `open` gets nothing back and
reports "none". List every value in the case the data uses; where the source has more states than a
shared vocabulary, say which ones fold into which.

```yaml
# Bad
priority: "Priority of the case."
# Good
priority: "urgent, high, medium or low, lower case; empty when none was set."
```

Prefer `values:` on the property (`values: [urgent, high, medium, low]`). The model is told to use one
of them exactly, and a generated query that compares the property with anything else is refused
rather than run. That makes the list a contract: it must be **complete**, or a real value becomes
unaskable. Where the values are open-ended or too many, list the common ones in the description and
say the list is not exhaustive.

### P4 — SHOULD: a date says which moment it is and how it is written. *Checked (heuristic).*

*Why:* systems keep several clocks. `createdAt` may be when the customer raised a case or when an
import wrote the row. Say which (business date or system clock), and the format: ISO date, ISO
date-time with zone, or epoch seconds. A comparison against the wrong form silently matches nothing.

```yaml
# Bad
openedOn: "Opened."
# Good
openedOn: "The business day the customer raised the case, ISO YYYY-MM-DD; not when the row was created."
sentAt: { type: int, description: "When it was sent, epoch seconds UTC." }
```

### P5 — SHOULD: a numeric or boolean property declares its type. *Checked (heuristic).*

*Why:* an undeclared property keeps the source's encoding. A JSON source that quotes its numbers
sends strings, and `WHERE n.replyCount > 3` then compares a string to a number and matches nothing.
A declared `int`, `number` or `boolean` is converted on the way in.

### P6 — SHOULD: say what empty means. *Review.*

*Why:* "no value" can mean "not applicable", "not known", "not yet" or "the source does not keep
this". Each leads to a different answer. Say which: "empty while the case is open",
"empty when no CRM record keys the account".

---

## 3. Keys

### K1 — SHOULD: a key other systems hold is declared as one. *Checked (heuristic).*

*Why:* a company's domain or a person's email is what joins one product's records to another's.
Declared with `hub:` it keys a spine; declared with `joinKey:` a mismatch between two realms is
caught. Left undeclared, the join is something every query author has to discover.

```yaml
# Good
website: { hub: CustomerAccount, description: "The customer's website, as typed in. Keys the account spine." }
```

### K2 — MUST: a reference carries the name people use. *Review.*

*Why:* a property holding another record's id (`stageId`, `ownerId`) answers "which stage" with a
number. Declare the edge, or carry the name beside the id ([Declaring types §3.3](DECLARING_TYPES.md#33-properties)).

### K3 — SHOULD: a composite key is declared as its parts. *Review.*

*Why:* `owner/repo` as one string cannot be split back into two path parameters. Use
`producerKeyFields` and `keyArgs` ([README, composite-key joins](README.md#predicate-pushdown-pushdown--scope-the-fetch-at-the-source)).

---

## 4. Relationships

### J1 — MUST: every join has a description, written for the question that traverses it. *Checked.*

*Why:* the join's description is shown whole, and it is read at the moment a model is choosing a
path. It is the best place in a realm for traversal guidance.

Say the direction and cardinality in words, what traversing it means, and what it costs when that
matters: one call per anchor, a sweep of the whole book, a cap.

```yaml
# Bad
description: "A customer's invoices."
# Good
description: >-
  Every invoice issued to this customer, newest first: one Lago call per customer, so for
  "all overdue invoices" sweep (:LagoBooks)-[:HAS_INVOICE]-> instead.
```

### J2 — SHOULD: say which of two similar paths a question wants. *Review.*

*Why:* where an account reaches its cases both through a spine edge and through a product's own
door, a model picks one at random unless the description says which answers which question.

---

## 5. Pushdown

A filter the source applies is a filter that costs nothing. A filter the graph applies after the
fetch costs every record the source returned. The rules for what a producer declares, and how each
kind applies a pushed filter, are in the [README, predicate pushdown](README.md#predicate-pushdown-pushdown--scope-the-fetch-at-the-source).

### R1 — MUST: a producer that can filter at its source declares `pushdown:`. *Checked.*

*Why:* an absent `pushdown:` says nothing, so every `WHERE` on the producer is applied after a full
fetch. Declare the rules the source honours, or `pushdown: []` when it honours none, which is a
statement in its own right.

What each filter needs, by shape:

| Filter in the query | What the producer declares |
|---|---|
| `x.p = 'v'` | a rule on `p` with `op: EQUALS` |
| `x.p IN [...]` | `op: IN`; for a structured body, `{values}` in the rule's `clause` |
| `x.p >= '2026-01-01'` (a "since" window) | a range op (`GREATER_THAN_OR_EQUAL` …); `type: date` or `dateTime` on declared kinds; a `valuePattern` on remote rules that the canonical UTC spelling satisfies |
| `toLower(x.p) CONTAINS 'v'` | `op: CONTAINS` with `match: ci` |
| `ORDER BY x.p DESC LIMIT n` | `orderedBy: [{property: p, descending: true}]` on a remote producer, and no other filter left to the graph |
| a lookup by key | `keyArg` / `keyTemplate` / `keyArgs`, with `maxKeysPerCall` at the source's cap |
| a value only known at run time | nothing pushes it; take it as a view param, which becomes a literal |

Only a literal is pushed. A producer that must never scan its whole source declares
`requiresFilter: true`, and a query with no filter is then answered with a note instead of a scan.

### R8 — SHOULD: every remote pushdown rule states its `op`. *Checked.*

*Why:* a remote rule with no `op` is `CONTAINS`. An equality in the query does not ask for a
containment, so the rule never fires for it, and nothing says so.

### R7 — SHOULD: a single record is read by key, not found in a listing. *Checked (heuristic).*

*Why:* "show me invoice 42" through a list endpoint walks pages until it finds it. A producer over
the source's by-id or bulk-by-ids endpoint reads one. Where the source has
`GET /invoices/{id}` beside `GET /invoices`, declare a key-addressed producer for it (with
`materializedKeyField`, so `MATCH (i:Invoice {id: 42})` reaches it).

### R11 — SHOULD: every filter the source supports is declared. *Review.*

*Why:* the planner can only push what it was told about. Go through the source's filters (id, key,
status, date range, owner, company or contact, text search) and declare each one you have verified
narrows: call it with and without the filter and see the counts differ. A source that ignores an
unknown filter returns everything with a 200.

### R9 — SHOULD: ask only for the fields the join needs. *Review.*

*Why:* field selection (`fields`, `$select`, sparse fieldsets) is the cheapest saving most APIs offer.
Set it in `args`.

---

## 6. Efficiency

### R2 — MUST: a producer that reads a remote source declares a cache. *Checked.*

*Why:* the default is to read the source on every query. Choose a policy on purpose, matching how the
data changes: `immutable` for published records that never change (a filed document, a closed
period), a long `ttl` for slow-moving reference data, a short `ttl` for an inbox. `cache: { kind: none }`
is a valid choice when every read must be live; write it down so the next author knows it was one.

### R3 — SHOULD: a keyed producer remembers a clean miss. *Checked.*

*Why:* under `ttl` alone only records are kept; a key that answered empty is asked again on every
query. Where an empty answer is a real answer (most accounts have no open case), declare
`negativeTtlSeconds`.

### R4 — SHOULD: a paged producer states its page size and page cap. *Checked.*

*Why:* the defaults (100 per page, 5 pages) are nobody's choice. A walk that stops at the cap reports
a partial result; a cap sized to the source keeps answers whole.

### R5 — SHOULD: the page size is the source's maximum. *Checked (from the API document).*

*Why:* fifty pages of 20 cost five times the calls of ten pages of 100, for the same records.

### R6 — SHOULD: a count the source reports is counted at the source. *Checked.*

*Why:* where every page carries a total, "how many" is one call. Declare `aggregates:` with
`measure: count` so a count does not walk the pages.

```yaml
paging: { style: page, size: 25, maxPages: 2000, total: data.meta.all_count }
aggregates:
  - { measure: count, valueField: data.meta.all_count, records: "$" }
```

### R10 — SHOULD: no N+1 where the source has a batch or list form, and respect the rate limit. *Review.*

*Why:* one call per key over a thousand anchors is a thousand calls. Use the source's `IN`, bulk-by-ids
or list form with `maxKeysPerCall` set to its cap; keep `batchSafe: false` for sources that really take
one key. Declare `cost:` so the planner budgets calls against the source's shared rate limit.

---

## 7. Views

A view is a question the realm answers well. Its description is how a model chooses it, so it says
what the view answers and, as importantly, what it does not.

### V1 — MUST: every view has a description saying what it answers. *Checked.*

### V7 — SHOULD: the first sentence says what it answers, in 80 characters. *Checked.*

*Why:* the listing a model picks views from shows each view's first sentence and cuts it at 80
characters (60 on a busy world). A first sentence that spends those on background is a view nobody
picks.

```yaml
# Bad: the first 80 characters are preamble
description: "Reads the CRM's companies, the billing system's customers and the helpdesk's cases in full, so that…"
# Good
description: "How many accounts each system knows. Reads the CRM, billing and helpdesk in full, so that…"
```

### V5 — SHOULD: the description says what the view leaves out, or how it is bounded. *Checked (heuristic).*

*Why:* a model that picks "open cases by account" to answer "all cases" reports a wrong total with
confidence. Say the scope and the bound: open only, top 50 by value, the last page the source keeps.

```yaml
# Bad
description: "Cases by account."
# Good
description: >-
  Open support cases per account, counted at the helpdesk. Not resolved or pending cases;
  for every status use HealthCaseCountsByAccount.
```

### V2 — MUST: every param has a type and a description. *Checked.*

*Why:* a param is a contract. The type is enforced, and the description is the only place its
meaning and format are stated.

### V4 — SHOULD: every param has a default, or states whether it is required. *Checked.*

*Why:* a view with defaults runs bare, which is how it is browsed and tested.

### V3 — MUST: a name matches exactly, unless the param says otherwise. *Checked.*

*Why:* "the account named Acme" must not also return "Acme Holdings" and "Acmeson". A view param
matches exactly by default. Partial or case-insensitive matching is opt-in, and its param's
description says so.

```yaml
# Bad: partial, and silent about it
params:
  name: { type: string, description: "The company name." }
cypher: "MATCH (a:Account) WHERE toLower(a.name) CONTAINS toLower($name) RETURN a"

# Good
params:
  name: { type: string, description: "The company name, exactly as the CRM holds it." }
cypher: "MATCH (a:Account {name: $name}) RETURN a"

# Better: exact by default, partial when asked for
params:
  name:    { type: string, description: "The company name, exactly as the CRM holds it." }
  partial: { type: boolean, default: false, description: "true: every name containing it, ignoring case." }
cypher: |
  MATCH (a:Account)
  WHERE ($partial AND toLower(a.name) CONTAINS toLower($name)) OR (NOT $partial AND a.name = $name)
  RETURN a
```

---

## 8. Honest names

### V6 — SHOULD: a view's or column's name says what it counts. *Checked (heuristic).*

*Why:* a name is read before a body is. A view named `UrgentCaseCounts` that counts
`priority IN ['urgent', 'high']` will be quoted as "urgent cases", and the number will be wrong.

```yaml
# Bad
- name: UrgentCaseCounts
  cypher: "… WHERE c.priority IN ['urgent', 'high'] RETURN count(c) AS urgent"
# Good
- name: UrgentOrHighCaseCounts
  cypher: "… WHERE c.priority IN ['urgent', 'high'] RETURN count(c) AS urgentOrHigh"
```

The same holds for a column alias, a property name and a type name: say exactly what it holds.

---

## 9. The realm

### M1 — MUST: `realm.yml` has a description. *Checked.*

### M2 — SHOULD: its first sentence says what the realm holds, in 120 characters. *Checked.*

*Why:* the realm's description is read whole when a model decides which realms a question needs, and
its first sentence, to 120 characters, is the realm's line in the guide's index. Name the system and
the kind of record: "Chatwoot support conversations and messages, read live through its API."

### Z1 — MUST: nothing is declared that the host ignores. *Checked.*

*Why:* a declaration that does nothing looks like it works. The checked cases are the ones found in
real realms: `dimension:`, `valuePattern:`, `default:`, `examples:` and the like on a property (validation
names each unread key, with the nearest key that is read);
`ttlSeconds` where a `ttl` cache wants `seconds`; `cache: { kind: session }`, which is accepted and
read as none; `cache: { kind: graph }` on a producer other than `aggregate` or `extract`; and
`cost.latencyMs`, which nothing reads.

## 10. Examples

### X1 — SHOULD: a realm ships worked Cypher examples over its main joins. *Checked.*

*Why:* the schema says what exists; an example says which of two legal paths to prefer. A few
`q`/`cypher` pairs on the type that owns each main path ([Virtual Cypher §10](VIRTUAL_CYPHER.md#10-steering-the-generator--type-level-examples))
teach a model the realm's idiom. Keep them true: an example the realm cannot answer teaches the wrong
query with authority. An `EXAMPLES.md` in the realm counts for people, but only type `examples:` reach
a model.

---

## Checking a realm

```
embabel realm audit .                         # this realm's score and every finding
embabel realm audit ~/realms                  # every checkout in a directory, scored
embabel realm audit . --json --fail-under 80  # for CI
```

The audit reads the realm's files (YAML, or the value `realm.ts` evaluates to) and any vendored API
document under `apis/`. Nothing needs to be running. It scores the checked rules: each rule by the
share of the declarations it applies to that meet it, MUST rules weighing three times SHOULD rules.
Heuristic rules guess from names and API documents; a false positive is fixed by a better
description, which is never wasted.

A realm can pass every checked rule and still describe itself badly. The review rules are the rest of
the bar.

---

## Rule index

| Id | Level | Rule | How |
|---|---|---|---|
| T1 | MUST | Every type has a description | checked |
| T2 | MUST | The first 320 characters say what one node is and what identifies it | checked |
| T3 | MUST | A type reached by more than one path declares its identity | checked |
| T4 | SHOULD | A type says how fresh it is and what it is not | review |
| T5 | SHOULD | Every other fetched type declares its identity | checked |
| P1 | MUST | Every property is described beyond its name | checked |
| P2 | SHOULD | Money and measures state currency or unit | checked |
| P3 | SHOULD | Enumerations list their values exactly (`values:` preferred, and complete) | checked |
| P4 | SHOULD | Dates say which moment and which format | checked |
| P5 | SHOULD | Numeric and boolean properties declare their type | checked |
| P6 | SHOULD | Say what empty means | review |
| K1 | SHOULD | Cross-system keys are declared (`hub:`, `joinKey:`) | checked |
| K2 | MUST | A reference carries the name people use | review |
| K3 | SHOULD | Composite keys are declared as parts | review |
| J1 | MUST | Every join is described for the question that traverses it | checked |
| J2 | SHOULD | Say which of two similar paths a question wants | review |
| R1 | MUST | Producers that can filter declare `pushdown:` (or `[]`) | checked |
| R2 | MUST | Remote producers declare a cache | checked |
| R3 | SHOULD | Keyed producers declare `negativeTtlSeconds` | checked |
| R4 | SHOULD | Paging states `size` and `maxPages` | checked |
| R5 | SHOULD | Page size is the source's maximum | checked |
| R6 | SHOULD | A source-reported total is used for counts | checked |
| R7 | SHOULD | Single records are read by key | checked |
| R8 | SHOULD | Remote pushdown rules state their `op` | checked |
| R11 | SHOULD | Every verified source filter is declared | review |
| R9 | SHOULD | Field selection is set | review |
| R10 | SHOULD | No N+1; rate limits declared | review |
| V1 | MUST | Every view has a description | checked |
| V2 | MUST | Every param has a type and description | checked |
| V3 | MUST | Name params match exactly unless documented as partial | checked |
| V4 | SHOULD | Every param has a default or states whether it is required | checked |
| V5 | SHOULD | The description says what the view leaves out | checked |
| V6 | SHOULD | Names say what they count | checked |
| V7 | SHOULD | A view's first sentence says what it answers in 80 characters | checked |
| M1 | MUST | `realm.yml` has a description | checked |
| M2 | SHOULD | The realm's first sentence says what it holds in 120 characters | checked |
| Z1 | MUST | Nothing is declared that the host ignores | checked |
| X1 | SHOULD | Worked Cypher examples over the main joins | checked |

## Changelog

- 0.1.0 — first version.

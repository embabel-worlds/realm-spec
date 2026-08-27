# Labels and Composition

**Spec version: 0.1.0**

Normative. What a realm author can rely on when they declare a type hierarchy or a shared
capability label, stated as observable behaviour: things you can check by writing YAML or
TypeScript, installing the realm, and running a query.

Nothing here describes how the host implements any of it.

Types may be declared in YAML or in TypeScript — see `DECLARING_TYPES.md`. Every guarantee
below holds identically for both; the examples here use YAML for brevity.

---

## 1. A label is an interface

A node in the knowledge graph carries one or more **labels**. A label is not a tag: it
declares what the node supports.

A node's **effective type is the intersection of its labels**. A node labelled
`:Trust:Organisation:Party:Watchable` answers to everything declared for each of those four
labels. This is a set, not a chain — no label is privileged over the others except by the
specificity rule in §4.

---

## 2. Declaring a hierarchy

A type declares its parents:

```yaml
- name: Organisation
  parents: [Party]

- name: Trust
  parents: [Organisation]
```

**Guarantee — ancestors are physically present.** A node created as a `Trust` carries
`:Trust`, `:Organisation` and `:Party`. This holds however the node came to exist — persisted by an
ingest, or materialized on demand by a traversal that fetched it — so a realm whose population is
entirely virtual gets the same behaviour as one that stores its rows. This is observable:

```cypher
MATCH (t:Trust) RETURN labels(t)      // includes Organisation and Party
MATCH (p:Party) RETURN p              // returns every Trust
```

There is no synthetic `IMPLEMENTS` edge to traverse, and no need to enumerate subtypes in a
query. A query written against `:Party` before `:Trust` existed matches trusts once the type
is declared.

**Guarantee — properties are inherited.** A `Trust` has every property declared on
`Organisation` and `Party` without restating them. It may redeclare one to override it.

**Guarantee — the chain is transitive.** Declaring one parent is enough; grandparents follow.

**Guarantee — behaviours are inherited.** A method declared on `Party` is callable on any
`Trust`, and receives the trust's own property values.

### 2.1 Host types are not is-a

Naming a **host** type as a parent — `Person`, `Contact`, `Signal`, `Notification` — does
NOT put that label on your nodes.

Those declarations mean something else, and the spec is explicit about it so a realm author
is not surprised:

- `parents: [Person]` / `[Contact]` means **this type projects onto the canonical person**.
  Your nodes remain your type; the projection pipeline links them to a canonical record.
  If your mirror nodes were labelled `:Person`, every query for people would return a
  duplicate for every source record.
- `parents: [Signal]` / `[Notification]` means your type participates in that host
  mechanism, which already labels its own instances.

Only parents that are themselves **realm-declared types** contribute labels.

### 2.2 Cycles

A cyclic `parents:` chain is reported as a loading problem, and the edge that closes the
loop is dropped. The types still load. Do not rely on this: it is error recovery, not a
feature.

---

## 3. Capability labels (mixins)

A label need not be a kind of thing. It may be a **capability** that many unrelated kinds of
thing support:

```yaml
# realm-alerts
- name: Watchable
  description: "Anything worth being told about when it materially changes."
  methods:
    - name: watch
      gatewayTool: "alerts.watch"
      params: [{ name: reason, type: string }]
      args:   { subject: "$id", reason: "#reason" }
```

**Guarantee — capability applies across realms.** Any node carrying `:Watchable` answers to
`watch`, whether or not the realm that owns that node's primary type knows `Watchable`
exists. Neither realm imports the other, and neither is rebuilt when the other is installed.

**Guarantee — a capability may be reached from a behaviour.** A method authored in one realm
may call a method contributed by another on the same node, through the receiver. A `Trust`
behaviour may call `watch` even though its author never heard of it.

**Requirement — the data contract.** A capability's methods read properties from the node.
Declare which ones. A type carrying a label whose properties it does not have is reported as
a loading problem, because the alternative is a real call made with a blank argument.

---

## 4. When two labels declare the same method

A node may carry two labels that declare the same method name.

**Specificity resolves an ancestor relationship.** If one label extends the other, the more
specific one wins. `Trust.awards` overrides `Party.awards`, always, regardless of the order
labels happen to appear on the node.

**Unrelated labels are ambiguous, and are reported.** Two capability labels that neither
extends the other, both declaring `close`, is a loading problem naming both. The composed
surface currently resolves it by ordering; do not depend on which one you get. Rename one,
or declare an ancestor relationship so specificity decides deliberately.

---

## 5. Labels are a single global namespace — and the realm label qualifies it

Graph labels are global. Two realms declaring `Watchable` produce **one** label, and a node
carrying it answers to both realms' methods — which neither author intended.

This is reported at load, naming both realms. Treat a capability label name as a claim on
shared vocabulary: prefer a specific name (`ChangeWatchable`) over a generic one, and check
what is already installed.

For ENTITY types, the namespacing mechanism is the **realm provenance label**: every node of
a type a realm OWNS carries the realm's label beside its own.

**Guarantee — the realm label is physically present.** A `Constituency` declared by
`realm-gov-uk` carries `:Constituency:GovUk`, however the node came to exist — persisted or
materialized on demand. Observable:

```cypher
MATCH (c:GovUk:Constituency) RETURN c    // the QUALIFIED name — this realm's constituencies only
MATCH (c:Constituency) RETURN c          // the bare name still works, and still converges
MATCH (n:GovUk) RETURN labels(n)         // the realm's whole graph contribution, one label
```

**Guarantee — derivation is predictable, and overridable.** The label derives from the realm
name (`realm-gov-uk` → `GovUk`: strip the `realm-`/`pack-` prefix, capitalise each word). A
realm may override it wholesale with `realmLabel:` in `realm.yml`.

**Guarantee — a realm label never collides with a type.** A derived or declared realm label
that equals any declared type name is REFUSED at load, reported naming the realm, and that
realm stamps nothing — a realm named `realm-person` can never stamp `:Person`.

**Guarantee — the stamp means "owned by", never "touched by".** Only types the realm itself
declares carry its label. A shared or host type a realm merely enriches through a convergent
join (`Person`, `Organisation`) is never stamped, so the qualified form cannot silently mean
"the subset this realm happened to mint".

The realm label is inert unless used: bare-label queries, hierarchies (§2) and capability
composition (§3) behave identically with or without it. Vocabulary conventions still apply —
prefer a qualified specific type name (`UkPlace`) with a shared parent (`Place`) over coining
a generic name two realms will fight over; the realm label is the disambiguator of last
resort, not a licence to collide.

---

## 6. Results

A method may declare the type it returns:

```yaml
    - name: awards
      gatewayTool: "grants.awardsFor"
      returns: Award
```

**Guarantee — a declared entity result is navigable.** The returned value answers to
`Award`'s methods, and to the methods of `Award`'s ancestors. So a chain continues:

```ts
const awards = await party.awards({ since: '2025-01-01' });
await awards[0].dispute({ reason: 'mismatch' });
```

**Guarantee — a result read from the graph keeps its own labels.** If the returned entity
carries labels beyond the declared return type, those compose too. The declared type is the
floor, not the ceiling.

Scalar return types (`string`, `number`, `boolean`, `any`, `void`) declare no entity and the
result is returned unchanged.

---

## 7. What a method receives

A method's arguments come from two places, and the distinction is a guarantee:

- `$property` — read from **the node the method was called on**;
- `#param` — supplied by **the caller**.

**Guarantee — the caller cannot address a node it does not hold.** There is no identifier
parameter for a caller to supply. A method runs against the entity it was invoked on, and
that entity had to be retrieved before it could be invoked.

**Guarantee — `$property` may name a property the caller never read.** The node's full
property set is available to the method, whether or not the caller has seen it.

---

## 8. Walk bounds

Navigation is bounded per turn: a maximum number of entities acted on, and a maximum chain
depth from the originating query. Exceeding either refuses the call with an explanation
rather than failing the turn.

Do not design a realm around unbounded traversal. If a capability needs to touch thousands
of entities, it should take a collection and do the work inside one method, not be called
once per entity.

---

## Changelog

**0.1.0** — first published contract: label intersection, ancestor labels physically present,
property and behaviour inheritance, host parents excluded, cross-realm capability labels,
specificity and ambiguity, the global label namespace, navigable results, `$`/`#` argument
sources, walk bounds.

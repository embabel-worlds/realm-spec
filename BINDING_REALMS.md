# Binding realms — the ontology in one realm, the binding to a system in another

> **Status: proposal.** Nothing here is implemented in the reference host yet. It is written so the
> importer in [Open standards](OPEN_STANDARDS.md) can target it, and so the backward-compatibility
> rules in §5 are fixed before any host reads a new field.

## 1. The three layers a realm already has

A realm declares three kinds of thing in one file, and the [ontology import](OPEN_STANDARDS.md)
makes the seam between them visible:

| Layer | What it says | Who it belongs to | Standards that describe it |
|---|---|---|---|
| **Ontology** | what a thing is, its properties, which relationships are legal between things, how a derived fact follows from stated ones | the domain | OWL, RDFS, SKOS, Ossie's ontology layer |
| **Binding** | which system yields the things, by which query, keyed how, under whose credentials | one estate | none |
| **Behaviour** | what may be done to a thing, by whom, with what confirmation | the domain and the estate together | none |

Today a `virtualJoins` entry carries ontology and binding in one line: `anchorLabel`,
`relationship`, `direction` and the declaring type are the ontology half; `keyField`,
`recordKeyField`, `materializedKeyField` and `producer` are the binding half. A realm that binds its
own ontology is the common case and remains the common case. This page lets the two halves be
declared by different realms, without changing what any existing realm means.

**Why it is worth a declaration rather than a convention.** One ontology, many bindings: the same
FIBO-derived types bound to a CRM in one customer's world and to a triple store in another's. The
two halves version on different clocks, the ontology with the standard's release and the binding
with the customer's systems. The binding is where the credentials and the systems live, so it is
also the natural permission and licensing boundary: the ontology realm can be public, the binding
private. And it makes the per-customer work precise: a list of edges to bind, which the status
surface already knows how to show.

## 2. Unbound joins

A join may be declared without its binding half. The realm says it expects a binding from elsewhere:

```yaml
# realm.yml of the ontology realm
name: retail-ontology
binding: external          # NEW: this realm's unbound joins await a binding realm
```

```ts
// realm.ts, object form
types: {
  Order: {
    properties: { iri: { identity: true }, orderTotal: { type: "number" } },
    virtualJoins: [
      // Ontology half only: the edge exists in the model; nothing yet says where its rows come from.
      { anchorLabel: "Customer", relationship: "PLACED_ORDER" },
      { anchorLabel: "OrderQuery", relationship: "IS", materializedKeyField: "iri" },
    ],
  },
}
```

**Guarantee — an unbound join is a declared gap, not a defect.** In a realm that declares
`binding: external`, a join with no `producer` loads. The type exists, its properties and rules are
known, queries over the edge are planned, and until a binding arrives a traversal of it returns no
rows *with a diagnostic*: `UNBOUND_EDGE`, naming the type, the anchor and the relationship. The realm
is `active`; its status lists every unbound edge under `unbound`, each with the binding realm that
bound it or `awaiting`. This is the [optional label](README.md#optional-labels--reading-a-companion-realm-that-may-be-absent)
rule applied to an edge: an awaited binding is a note, and an empty answer from it means "not
bound", never "no data".

**Guarantee — without the declaration nothing changes.** A realm that does not declare
`binding: external` and omits a join's `producer` is refused at validation exactly as today, naming
the join. A typo in a producer name in an existing realm stays an error; it never silently becomes an
unbound edge.

**What an unbound join may still say.** `materializedKeyField`, because it is a statement about the
model (this type can be matched by this property) rather than about a source. `description`.
Nothing that names a source: `keyField`, `recordKeyField` and `producer` belong to the binding.

## 3. Bindings

A binding realm is an ordinary realm. It declares producers, and under a new top-level `bindings`
key it supplies the missing half of named joins in types it does not own:

```ts
// realm.ts of realm-retail-binding-crm
export default {
  name: "retail-binding-crm",
  version: "0.1.0",
  binds: ["retail-ontology"],          // NEW: the realms whose unbound joins this one may bind
  producers: {
    ordersByCustomer: { kind: "sql", datasource: "crm", table: "orders", keyColumn: "customer_id",
      compute: { iri: "'urn:crm:order:' + r.id", anchorIri: "'urn:crm:customer:' + r.customer_id" } },
    orderById: { kind: "sql", datasource: "crm", table: "orders", keyColumn: "id",
      compute: { iri: "'urn:crm:order:' + r.id" } },
  },
  bindings: [
    { type: "Order", anchorLabel: "Customer", relationship: "PLACED_ORDER",
      keyField: "iri", recordKeyField: "anchorIri", producer: "ordersByCustomer" },
    { type: "Order", anchorLabel: "OrderQuery", relationship: "IS",
      keyField: "iri", recordKeyField: "iri", producer: "orderById" },
  ],
} satisfies Realm;
```

A binding names a join by its identity, **(type, anchorLabel, relationship, direction)**, and
supplies exactly the fields an unbound join may not: `keyField`, `recordKeyField`, `producer`, and
optionally `brings`, `maxAnchors` and `maxFanoutTotal`. The producer it names is its own, or one
installed beside it; it runs with the binding realm's credentials, as every producer runs with its
realm's, so an ontology realm never needs a key and a binding never lends one.

**Guarantee — a join has at most one binding.** Two installed realms binding the same join are
reported at load naming both, as two realms declaring one label are, and the join stays unbound
until one is removed. There is no precedence between bindings: the ambiguity is the owner's to
resolve, not the host's to guess.

**Guarantee — a binding never overrides the owner.** A join its own realm bound (`producer` present)
cannot be rebound from outside. A binding naming such a join is refused at validation naming the
join and its realm. Existing realms therefore keep exactly their current meaning whatever is
installed beside them.

**Guarantee — a binding attaches only where it is invited.** A binding realm names the realms it
may bind (`binds`), and a join is bound only when the join's realm declares `binding: external`.
A binding for a realm not named in `binds`, or for a realm that did not open itself, is refused
naming both. The world's own types are never bindable this way.

**Guarantee — the record carries the identity the ontology declared.** The ontology realm owns the
type and its identity property. A producer bound to its join must return that property on every
record, computed if the source has no such column (`compute:`, as the Ossie flights realm computes a
composite key); a record without it is dropped and counted, which is the rule every producer already
lives under. A binding cannot add a property to the type: a field its records carry that the type
does not declare lands on the record and is reported as undeclared, as it is for any producer.

**Guarantee — the existing join checks apply unchanged.** `keyField` must be a property the anchor
type declares or a field one of its joins echoes; `recordKeyField` must be echoed by the producer;
a list of several joins onto one type needs an identity property. Validation of a binding realm runs
these checks against the ontology realm, which must be installed beside it (`--with` in a headless
run), and reports each failure against the binding, not the ontology.

## 4. What does not move

- **Types, properties, parents, spines, identity, lifecycle** stay in the ontology realm. The realm
  provenance label stays the owner's; a binding stamps nothing.
- **DERIVE rule sets, views, goals** stay in the ontology realm. They read edges by relationship
  name and need not know which realm bound them. A rule set over an unbound edge concludes nothing
  and says so (`UNBOUND_EDGE` beside `PARTIAL_RESULT`), never a silent empty.
- **Verbs, handlers, apps** may live in either. Behaviour that is about the concept (a verb every
  binding should offer) belongs with the ontology and is dispatched to the binding's gateway
  operations by the existing capability mechanisms; behaviour that is about one system belongs with
  the binding. This page does not change verb declaration.
- **Credentials** never cross. `keys.yml` and `credentials.yml` are the binding realm's.
- **The alignment** (`ontology/alignment.yml`) stays with the ontology realm; an export of the
  ontology realm alone reproduces the vocabulary, and the export report lists its unbound edges as
  edges, since OWL has no notion of a binding either.

## 5. Backward compatibility

1. **Every existing realm is unchanged.** It is the degenerate case where the ontology and its
   binding are the same realm. No field is added to a bound join; no file needs editing.
2. **`producer` stays required** unless the realm opts in with `binding: external`. The failure mode
   of an old realm, a missing or misspelled producer, remains an error with the same message.
3. **New keys are read only when present.** `binding`, `binds` and `bindings` are new. A host that
   does not implement this page refuses a realm declaring them, naming the field, as the spec
   requires of any unsupported declaration; it never loads the realm with the fields ignored, which
   would present an ontology realm as a realm that answers.
4. **No precedence is introduced.** Owner-bound joins cannot be rebound; competing bindings are a
   reported conflict. The merge rule for YAML beside `realm.ts` is untouched.
5. **Removal is clean.** Uninstalling a binding realm returns its joins to `awaiting`; the ontology
   realm stays installed and `active`. Installing a different binding is the whole migration.

## 6. Validation and status, in one table

| Situation | Headless `realm validate` | Installed status |
|---|---|---|
| Ontology realm alone, `binding: external`, unbound joins | passes; one NOTE per unbound join | `active`; `unbound: [{type, anchorLabel, relationship, boundBy: null}]` |
| Ontology realm alone, no `binding: external`, a join without `producer` | ERROR naming the join (today's behaviour) | not installed |
| Binding realm `--with` the ontology realm, every binding resolves | passes | ontology realm's `unbound[*].boundBy` names it |
| Binding names a join the owner bound | ERROR naming join and owner | binding not applied; reported on the binding realm |
| Two installed bindings for one join | — | both reported; join `awaiting` |
| Binding realm without the ontology realm beside it | ERROR: the bound type is unknown | `degraded`, as a join under an absent type is today |

## 7. The importer's part

`ontology-io import owl --split` writes two realms instead of one: `<name>` (types, rules,
alignment, views, unbound joins, `binding: external`) and `<name>-binding-sparql` (the SPARQL
producers and the bindings, `binds: [<name>]`). The single-realm output stays the default until a
host implements this page. A customer who already has the ontology realm then writes only the
binding, by hand or with a coding agent working from the `unbound` list in `realm_status`, which is
the per-customer work the [off-the-shelf argument](https://github.com/embabel-worlds/technical-competitors) says is all that should remain.

## 8. Open questions

- **Partial bindings.** Whether a binding realm may bind some of an ontology realm's joins and leave
  others awaiting (the rules above allow it; whether status should distinguish "partly bound" is
  not decided).
- **A binding to a different identity scheme.** When a source cannot compute the ontology's identity
  (a CRM with no stable id), whether the binding may declare a `resolve:` chain onto the type as a
  bridge rather than a plain join. The identity-bridge rules exist; their use from a binding is not
  specified.
- **Decorator form.** The `@Relationship` decorator requires `producer`; an `unbound: true` option is
  the obvious shape and is not specified here.

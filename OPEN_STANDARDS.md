# Open standards in, open standards out

A realm is declared in its own vocabulary because no existing standard says what a realm says: an
edge that executes against a live system, an action with preconditions and a permission resolved per
user, evidence on every hop. But the parts of a realm that other standards *do* describe — what a
thing is, what properties it has, which relationships are legal between things, how a derived fact
follows from stated ones — must come in from those standards and go back out to them. Nobody should
have to retype an ontology to get a realm, and nobody should be unable to leave with their model.

This page is the contract. It says, for each standard, what maps onto what, what is refused, and what
a round trip preserves. **Import, never conform:** a realm reads these standards; it does not adopt
their vocabulary as its own, join their committees, or let them govern the type system. A host that
offers an importer must publish the mapping report described in §1 and honour the rules in §2.

## 1. The mapping report

Every import produces a report before anything is installed. Every object in the source lands in
exactly one of four outcomes:

| Outcome | Meaning |
|---|---|
| **exact** | Mapped with no interpretation. |
| **inferred** | Mapped, but a choice was made; the row says which. |
| **noted** | Carried as information (a description, an alignment entry), not as a mechanism the engine enforces. |
| **refused** | Not mapped. The row quotes the source object and says why. |

Nothing is dropped silently. A refusal is a row, never an absence. The report is written into the
draft as `IMPORT-REPORT.md`, and an export writes the same shape beside its output.

## 2. The rules every importer keeps

1. **Import the schema; the instances federate.** An ontology's classes and properties become
   declarations. Its individuals are not copied into the world. They stay in the store that holds
   them and are reached through a producer (`sparql` for a triple store, `tabular` for a published
   file), exactly as a CRM's records are. This is "no new database" applied to the standard's own
   stores.
2. **Import gives you types with no producers of your own.** An ontology says what a `Customer` is,
   not which system yields one. An imported realm answers nothing until its producers point at a
   store. The report says so on its first line.
3. **Refuse by name.** An axiom the realm cannot state is quoted in the report with the reason. It is
   never approximated silently and never dropped.
4. **The alignment is part of the realm.** `ontology/alignment.yml` records which IRI every realm name
   came from, and the ontology facts a realm has no construct for (symmetry, transitivity,
   disjointness). The engine does not read it. An export reads it, so the names go back out as the
   IRIs they came in as.
5. **Round-trip before claiming.** A host may say it "reads" a standard only when it also writes it
   and the export of an imported realm reproduces the mapped part of the source.

## 3. OWL 2 and RDFS (Turtle, RDF/XML, N-Triples, JSON-LD)

Two shapes of ontology arrive, and they map differently. The importer decides from the ontology's
shape and says which it chose; `--mode schema|terminology` overrides it.

### 3.1 Schema mode — a domain ontology becomes types

For an ontology with tens to hundreds of classes, datatype properties and class-defining axioms.

| OWL / RDFS | Realm | Outcome |
|---|---|---|
| `owl:Class`, `rdfs:Class` (named) | a type; PascalCase of the local name | exact (inferred when the class is known only from use as a domain, range or parent, or when two namespaces' local names collide) |
| `rdfs:label`, `rdfs:comment`, `skos:definition`, `dcterms:description`, `IAO_0000115` | the type's `description` | exact |
| `rdfs:subClassOf` a named class | `parents` | exact |
| `rdfs:subClassOf <restriction>` (C ⊑ ∃P.D, C ⊑ ∀P.D, cardinality) | — | **refused**: a constraint on members, not a definition of them; an existential on the right would have to invent a node |
| `owl:equivalentClass <expr>`, `<expr> rdfs:subClassOf C` | a **derived label**: one DERIVE rule set, one rule per union branch (§3.3) | exact when every branch translates; refused per branch otherwise |
| `owl:DatatypeProperty` with `rdfs:domain` C and `rdfs:range` | a property on C; `xsd:integer` family → `int`, `xsd:decimal`/`float`/`double` → `number`, `xsd:boolean` → `boolean`, else string with the range named in the description | exact; inferred when `schema:domainIncludes` supplied the domain or several ranges were declared |
| `owl:DatatypeProperty` with no domain, or a domain that is a derived label | — | **refused**: a property needs a type to live on |
| `owl:FunctionalProperty` (datatype) | `cardinality: ONE` | exact |
| `owl:ObjectProperty` with domain C and range D | an edge `(C)-[:UPPER_SNAKE]->(D)` declared as two virtual joins: forward on D anchored at C, and `direction: TO_ANCHOR` on C anchored at D, each with its own producer, so the edge traverses both ways | exact; inferred when several domain/range pairs each get a declaration |
| `owl:ObjectProperty` with no typed domain or range (`owl:Thing` is not one) | — | **refused**: an edge needs a type at both ends |
| `owl:inverseOf` (declared on Q, pointing at P) | Q is a **derived relationship**: `(b)-[:Q]->(a)` from `(a:C)-[:P]->(b:D)`; P keeps its joins, Q gets none | exact; facts a store holds under Q directly are not read |
| `owl:propertyChainAxiom` on Q | Q is a derived relationship over the path | exact when every step has typed ends |
| `rdfs:subPropertyOf` | noted: traverse `-[:P\|Q]->` | noted; no derived edge, because Q also reads its own facts |
| `owl:SymmetricProperty` | noted: traverse undirected; recorded in the alignment | noted |
| `owl:TransitiveProperty` | noted: traverse `-[:P*]->`; recorded in the alignment. No closure edge is derived (VIRTUAL_CYPHER §13.4) | noted |
| `owl:FunctionalProperty`, `InverseFunctionalProperty`, `AsymmetricProperty`, `ReflexiveProperty` (object) | recorded in the alignment | noted |
| `owl:hasKey` | the key properties are kept as properties; every type is keyed on `iri` | noted |
| `owl:disjointWith` | recorded in the alignment | noted |
| `owl:deprecated true` | not emitted | noted |
| individuals | counted per class; not copied | noted |

Every type gets an `iri` identity property, a `<Type>Query` anchor with `materializedKeyField: iri`
so `MATCH (c:Customer {iri: '…'})` works, and a `sparql` producer per join whose `SELECT` returns the
target's datatype properties and echoes the anchor IRI under `anchorIri`. The producers' `endpoint`
is the one given, or a placeholder the report names.

### 3.2 Terminology mode — a vocabulary becomes data

For an ontology with thousands of classes, no datatype properties and relationships stated as
`subClassOf (R some X)`: the Gene Ontology, SNOMED CT, the Human Phenotype Ontology, any OBO
vocabulary. Treating each class as a type would give the world tens of thousands of labels; what a
terminology server does instead is serve the published hierarchy, and that is what the realm does.

| OWL / OBO | Realm | Outcome |
|---|---|---|
| every named class | a row of one type, `<Prefix>Term`: `id` (CURIE, identity), `iri`, `name`, `namespace`, `definition`, `synonyms`, `deprecated` | exact |
| `rdfs:subClassOf` a named class | an `IS_A` edge, both ways | exact |
| `rdfs:subClassOf (R some X)` | an edge named after R's label (`PART_OF`, `REGULATES`), both ways; one data file per R | exact |
| `owl:equivalentClass` (logical definitions) | — | noted: their asserted consequences are already edges |
| any other `rdfs:subClassOf <expression>` | — | refused by count |
| obsolete terms | rows with `deprecated: true`, so old codes resolve | exact |

The terms and edges are written as CSV under the realm's `data/` and served by `tabular` producers
from a URL the realm owner publishes (`--data-url-base`); subsumption is `-[:IS_A*]->`. The draft
ships `Ancestors`, `Descendants`, `IsA`, `TermsNamed` and `Related` views. To hold the vocabulary in
the world graph instead of reading the files per query, declare the collection in `sources.yml` with
`sync: {strategy: mirror}`.

A licensed terminology (SNOMED CT) ships no content: the owner runs the import on their own licensed
file and the realm is theirs.

### 3.3 Class expressions that become rules

A defining axiom becomes a DERIVE rule set with `derives: <Label>`. The fragment accepted is the one a
monotone rule can state; each row below is one clause of the generated body.

| Expression | Rule body |
|---|---|
| named class C (first in an intersection) | `MATCH (n:C)` |
| further named class D | `WHERE n:D` |
| `P some D` (object property) | `MATCH (n)-[:P]->(:D)` |
| `p some xsd:T[>= v]` and other facets | `WHERE n.p >= v` |
| `p some xsd:T` | `WHERE n.p IS NOT NULL` |
| `p some {v1, v2}` | `WHERE n.p IN [...]` |
| `p value v` (literal) / `P value i` (individual) | `WHERE n.p = v` / `MATCH (n)-[:P]->({iri: 'i'})` |
| `P min n D` | `MATCH (n)-[:P]->(x:D) WITH n, count(DISTINCT x) AS c WHERE c >= n` |
| `{i1, i2}` (oneOf) | `WHERE n.iri IN [...]` |
| `A or B` | one rule per branch |
| `P only D`, `not C`, `P max n`, `P exactly n`, `P Self`, a nested anonymous filler | **refused**, with the reason: universal and upper-bound readings are not monotone, and a closed-world count belongs in a view |

Note that the datatype facet (`HighValueCustomer ≡ Customer ⊓ ∃lifetimeValue.decimal[≥ 1000]`) and the
qualified minimum cardinality are outside OWL 2 RL, the profile reasoners run as rules, and inside
what a DERIVE rule states. The importer reads slightly more than RL; what it refuses it refuses by name.

### 3.4 Export — a realm as OWL

`realm-standards export owl <realm-dir>` writes Turtle. With the alignment present, every name goes
out as the IRI it came in as; without it, IRIs are minted under `--base` or
`https://realms.embabel.com/<realm>#`.

| Realm | OWL |
|---|---|
| type | `owl:Class` with `rdfs:label`, `rdfs:comment`; `parents` → `rdfs:subClassOf` |
| property | `owl:DatatypeProperty` with `rdfs:domain` (a `unionOf` when several types declare it) and `rdfs:range` from the type; `cardinality: ONE` or `identity` → `owl:FunctionalProperty`; `identity` → `owl:hasKey` |
| virtual join | `owl:ObjectProperty` with domain and range from the joins that declare it (`TO_ANCHOR` reverses them) |
| derived label whose rule bodies are a threshold or an existential over a named base | `owl:equivalentClass` of the intersection (a `unionOf` across rules) |
| derived relationship whose body is one reversed edge / one edge / a path | `owl:inverseOf` / `rdfs:subPropertyOf` / `owl:propertyChainAxiom` |
| any other rule body | the class or property, with the body as a `realm:derivedBy` annotation; **refused** in the report |
| alignment characteristics and disjointness | the property characteristic classes; `owl:disjointWith` |
| `<Type>Query` anchors, the `iri` property | not exported; noted as artefacts |
| producers | noted: a binding to a live system has no OWL form |
| views, verbs, handlers, apps | **refused**: no OWL form; this is the half of a realm no ontology language describes |

**Round trip.** Import then export reproduces, for the fixture `talisman-retail.ttl`: every class and
its parents, every datatype property with domain and range, every object property with domain and
range, the inverse, the chain, the threshold definition, symmetry, transitivity and disjointness.
What it does not reproduce is listed in the export report, and that list is the specification of
what a realm says that OWL cannot.

## 4. Apache Ossie

Layer 1 (semantic model) and Layer 4 (ontology and mapping) import as described in embabel/me#1796,
with the hand-ported flights example (`embabel-worlds/realm-ossie-flights`) as the golden output.
Datasets are types, fields are properties, relationships are joins, metrics are views (never producer
aggregates: `AVG` cannot be recombined and `SUM` over nothing is `0` in Cypher and `NULL` in SQL),
`EntityType.identify_by` is the identity (a composite becomes a computed key), `custom_extensions`
are kept and not interpreted, and `ai_context` is reachable by lookup and never concatenated into a
prompt. No exporter: a realm is not a subset of a warehouse spec. *Status: specified; importer not yet
shipped.*

## 5. SKOS

A concept scheme imports in terminology mode: `skos:Concept` rows, `skos:broader` as `BROADER` both
ways, `skos:related` as `RELATED`, `prefLabel`/`altLabel`/`definition` as properties. SKOS is RDF, so
the OWL reader reads it; the mapping is the terminology table with the predicates renamed. *Status:
not yet shipped.*

## 6. What has no standard

A verb — an action on an entity with preconditions, a permission resolved per user and a
confirmation — has no form in OWL, SKOS or Ossie. Neither does a producer, evidence per hop, or the
difference between when a fact was true and when it was recorded. The realm spec is the open reference
for those; this page will say "import" for them the day another standard describes them.

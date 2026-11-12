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
   store. The report says so on its first line. The seam this exposes, ontology in one realm and
   binding in another, is [Binding realms](BINDING_REALMS.md).
3. **Refuse by name.** An axiom the realm cannot state is quoted in the report with the reason. It is
   never approximated silently and never dropped.
4. **The alignment is part of the realm.** `ontology/alignment.yml` records which IRI every realm name
   came from, and the ontology facts a realm has no construct for (symmetry, transitivity,
   disjointness). The engine does not read it. An export reads it, so the names go back out as the
   IRIs they came in as.
5. **Round-trip before claiming.** A host may say it "reads" a standard only when it also writes it
   and the export of an imported realm reproduces the mapped part of the source.
6. **The source travels with the realm.** An imported realm carries what it was generated from, byte
   for byte, under `ontology/source/`: the ontology, every document its `owl:imports` closure brought
   in (under `source/imports/`), the Ossie files, the OKF bundle. `ontology/SOURCE.md` says what they
   are: the source's own title, version, licence and publisher as it declares them, each document's
   location, size and SHA-256, the closure as resolved, and the command that regenerates the realm.
   The same facts, machine-readable, are the `source:` block of `ontology/alignment.yml`. A document
   over 32 MB is described rather than copied. The realm is a derived work; it is never the only copy
   of the model, and a reader can always diff the two or re-run the import on a newer version.

## 3. OWL 2 and RDFS (Turtle, RDF/XML, N-Triples, JSON-LD)

### 3.0 Closure: what an ontology depends on

An ontology is read with what it depends on, and the report says what that was.

- **Declared imports** (`owl:imports`) are followed transitively and merged whole: an import is part
  of the ontology. Each is resolved from a catalog first (a directory of ontology files indexed by the
  ontology and version IRIs they declare, or a Protégé `catalog-v001.xml`), then fetched by IRI with
  content negotiation. FIBO's `FND/Parties/Parties` brings 28 documents (FIBO and OMG Commons) this way.
- **Undeclared reuse**: a property or class named from another vocabulary without an import (PKO names
  PROV-O, p-plan and Dublin Core terms; FIBO names Commons) is defined from that vocabulary's document,
  and only the terms used are copied, with the classes their domains and ranges name. A realm does not
  swallow PROV-O for one property.
- **Every document is a row**: resolved documents are exact rows (`owl:imports`, `namespace`) naming
  the file or URL and its size; one that could not be resolved is a refusal naming what was tried, and
  its terms stay undefined and are refused by name downstream.
- `--imports catalog` never fetches; `--imports none` reads the file as it is; a document cap (50)
  stops a runaway chain and says so.

Two shapes of ontology arrive, and they map differently. The importer decides from the ontology's
shape and says which it chose; `--mode schema|terminology` overrides it.

### 3.1 Schema mode — a domain ontology becomes types

For an ontology with tens to hundreds of classes, datatype properties and class-defining axioms.

| OWL / RDFS | Realm | Outcome |
|---|---|---|
| `owl:Class`, `rdfs:Class` (named) | a type; PascalCase of the local name | exact (inferred when the class is known only from use as a domain, range or parent, or when two namespaces' local names collide) |
| `rdfs:label`, `rdfs:comment`, `skos:definition`, `dcterms:description`, `IAO_0000115` | the type's `description` | exact |
| `rdfs:subClassOf` a named class | `parents` | exact |
| `rdfs:subClassOf <restriction>` on an object property (C ⊑ ∃P.D, C ⊑ ∀P.D, C ⊑ ≥n P.D, C ⊑ =n P.D, C ⊑ ≤n P.D with n ≥ 1) | the edge `(C)-[:P]->(D)`, declared as any other; nothing derives from it | inferred: "declared by a restriction on C". This is how FIBO and most Protégé-written OWL state their schema |
| `rdfs:subClassOf <restriction>` on a datatype property with a datatype or facets | the property on C with that type; facets as a `range` validation; `≤1` or `=1` as `cardinality: ONE` | inferred |
| `rdfs:subClassOf <restriction>` with `max 0`, `exactly 0`, `Self`, a complement or a nested anonymous filler | — | **refused**: a negative or nested constraint says nothing a schema can hold |
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

`ontology-io export owl <realm-dir>` writes Turtle. With the alignment present, every name goes
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

An Ossie document set — a Layer 1 semantic model, and where present the Layer 4 ontology and the
mapping that ties them — imports the way the hand-ported flights realm
(`embabel-worlds/realm-ossie-flights`) was written, and that realm is the golden output. Accepted
versions: 0.1.1 (the `semantic_model` wrapper), 0.2.0.dev0 and 0.3.0.dev0 (flat); any other is
refused by name.

| Ossie | Realm | Outcome |
|---|---|---|
| dataset | a type, named after the ontology concept that is the dataset where a mapping ties one (the concept whose mappings reference the most of its fields), else after the dataset; read by a `kind: sql` producer from the dataset's `source` table in a datasource the draft declares with a placeholder `jdbcUrl` | exact |
| field whose expression is a column | a property; `Integer` → `int`, `Decimal`/`Float` → `number`, `Boolean` → `boolean`; a renamed column is a `compute:` on every producer of the dataset | exact; inferred when renamed or declared only under `ANSI_SQL` |
| field whose expression is computed SQL | — | **refused**: the realm reads columns; the expression is quoted for a `compute:` by hand |
| `primary_key` (one field) | the identity | exact |
| `primary_key` (composite), or the ontology's `identify_by` | one computed key property, the parts joined by `/`, as the identity; every producer computes it | inferred |
| `unique_keys` | — | noted: the type is keyed once |
| relationship (`from` many → `to` one) | an edge in both directions, each traversal a keyed read; named as the ontology names it where the mapping ties the same field, else UPPER_SNAKE of the relationship name; composite columns through a computed key on both sides | exact |
| ontology relationship to an entity concept, mapped to a field | the same, named by the ontology (`ROUTE`, `DEPARTURE`); an identifying referent that is an entity (Runway.airport) is an edge as well as a key part | exact |
| ontology relationship to a value concept | the property's description (the concept and its description) and type; a value concept's `requires` bounds become a `range` validation | exact |
| `EntityType` with no dataset of its own (Market, City) | — | noted: it exists only as values of named columns; no type is minted |
| unary relationship (`canceled`) | — | noted: it is the boolean column the mapping filters on |
| ternary and higher relationships | — | **refused**: an edge has two ends |
| `requires` | — | noted: reconciliation checks, not rules |
| metric that is one aggregate, or two joined by an operator, over one dataset | one view per relationship from that dataset: the metric at each grain the model relates it to, `OPTIONAL MATCH`, SQL's null for `SUM`/`MIN`/`MAX` over nothing, `avg()` never rewritten as sum/count | inferred: the whole-table form is not available (me#2346) |
| metric over several datasets, or any other expression | — | **refused**, expression quoted |
| `derived_by` of the form `Role == AGG[Src.rel WHERE G == Src.path GROUP BY G]` or `… WHERE Src.rel(G) …` | a per-key view named `<Group><Relationship>` with `OPTIONAL MATCH` along the path | exact |
| any other `derived_by` or `requires` expression | — | **refused**, expression quoted |
| `ai_context` (model, dataset, field, relationship, metric) | `ontology/ai-context.yml`, by object | noted: reachable by lookup, never in a description, prompt or manifest |
| `nonportable_extensions` / `custom_extensions` | `ontology/ossie-extensions.yml`, verbatim | noted: kept, not interpreted |

No exporter: a realm is not a subset of a warehouse spec. *Status: shipped in `ontology-io` (embabel/me#3794).*

## 5. Open Knowledge Format (OKF)

Google's OKF v0.2 (`GoogleCloudPlatform/open-knowledge-format`, Apache-2.0; what Knowledge Studio's
context sets import and export): a bundle is a directory of Markdown files with YAML frontmatter,
`type` the only required field, `index.md` and `log.md` reserved, a trust tier read from `verified`
(unverified, machine-confirmed, human-reviewed), and a rule that a consumer must never rewrite an
`Attested Computation`. Every file is read best-effort, as the spec's conformance section asks; an
unknown type or a broken link is kept and reported, not rejected.

Import:

| OKF | Realm | Outcome |
|---|---|---|
| a concept whose `type` names a table (`BigQuery Table`, …) and carries a `# Schema` table | a type: columns as properties (SQL types to `string`/`int`/`number`/`boolean`/`datetime`), the first id-like column as identity, read by a `kind: sql` producer from the table the `resource` URL names, in a datasource named after the bundle with a placeholder `jdbcUrl` | exact |
| a Reference whose SQL fence joins two tables `ON a.x = b.y` | an edge in both directions between the two types, named from the reference's title | exact |
| every concept, of any type | an `OkfConcept` record seeded from `reference/okf-concepts.yml`: the bundle path as identity, type, title, description, `resource`, tags, status, `stale_after`, trust tier, who generated and who verified it, `sources`, the links it makes, its `not` terms, its body verbatim | exact |
| an Attested Computation | its `runtime`, `parameters` and `# Computation` kept verbatim on the record | noted: OKF forbids a consumer to rewrite it, so it is never a view; an agent runs it through the bundle's executor |
| `log.md` | `ontology/okf-log.yml` | noted |
| `index.md` | its `okf_version` is read; a major version this reader does not know is reported | noted |
| a Markdown file with no frontmatter | — | **refused** |

Views `ConceptsByType`, `ConceptLinks`, `StaleOrUnverified` and `Computations` come with the import,
so "what in this bundle is stale or unreviewed" is one query.

Export, the point of this format:

| Realm | OKF |
|---|---|
| a type (query anchors left out) | `types/<Label>.md`, type `Entity Type`, with a `# Schema` table of its properties, a `# Joins` list of its edges, a `# Binding` note naming the producers, and `resource` set to the IRI the alignment records |
| a saved view | `views/<Name>.md`, an `Attested Computation` with `runtime: embabel-virtual-cypher`, the parameters, an executor pointing at `skills/run-on-embabel.md`, and the Cypher as `# Computation` |
| a DERIVE rule set | `rules/<Derives>.md`, type `Derived Label` or `Derived Relationship`, `runtime: embabel-derive`, each rule's head and body |
| a producer | not a concept; named in its type's `# Binding` section and reported as noted |
| provenance | `generated.by: ontology-io/<version>` and `sources` (the realm, and the ontology it was imported from when `alignment.yml` records one) on every document; `index.md` with `okf_version: "0.2"`; `log.md` |

A realm exported this way and imported into Knowledge Studio as a context set makes its views
governed assets a Gemini or Antigravity agent finds, with the Cypher they run and the realm they run
on named. *Status: shipped in `ontology-io` (embabel/me#3794).*

## 6. SKOS

A concept scheme imports in terminology mode, always: SKOS has no classes to make types of.

| SKOS | Realm | Outcome |
|---|---|---|
| `skos:Concept` | a row of one type, `<Scheme>Term`: `id` (local name), `iri`, `name` (`prefLabel`), `definition` (`definition`, else `scopeNote`), `synonyms` (`altLabel`s), `namespace` (the scheme's label) | exact |
| `skos:broader`, and `skos:narrower` read the other way | the parent edge, `BROADER`, both ways; `Ancestors`, `Descendants` and `IsA` walk it | exact |
| `skos:related` | `RELATED`, both ways | exact |
| `exactMatch`, `closeMatch`, `broadMatch`, `narrowMatch` | an edge each, to a term of this scheme when the target is one; a target in another vocabulary is kept in the edge file's count, never minted as a row | exact |
| `skos:ConceptScheme` | the term's `namespace`; one scheme names the realm | exact |

*Status: shipped in `ontology-io`.*

## 7. What has no standard

A verb — an action on an entity with preconditions, a permission resolved per user and a
confirmation — has no form in OWL, SKOS or Ossie. Neither does a producer, evidence per hop, or the
difference between when a fact was true and when it was recorded. The realm spec is the open reference
for those; this page will say "import" for them the day another standard describes them.

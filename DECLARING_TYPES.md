# Declaring Types

**Spec version: 0.1.0**

Normative. New realms declare types in the `types` record of `realm.ts`. Definition fragments
may be imported and merged; see [Composing a realm](REALM_COMPOSITION.md). The host reads
the evaluated record directly, without YAML or decorator generation.

YAML and decorator declarations below describe existing legacy realms. They remain readable
unchanged and receive no new YAML features. In a realm with `realm.ts`, those legacy
declarations are ignored under the [source selection rules](TYPESCRIPT_REALMS.md#source-selection-and-legacy-compatibility).
The static class-reference guarantees below apply to legacy decorators, not string references
in a `realm.ts` object. The host checks those references after evaluation.

See [Labels and composition](LABELS_AND_COMPOSITION.md) for what a label means once declared.

## TypeScript object declarations

```ts
import type { Realm } from '@embabel/realm-types'

export default {
  name: 'movie-ratings',
  version: '1.0.0',
  types: {
    MovieRating: {
      visibility: 'public',
      properties: {
        imdbId: { identity: true, description: 'The rated film id.' },
        rating: { type: 'int', validation: [{ rule: 'range', min: 1, max: 10 }] },
      },
    },
  },
} satisfies Realm
```

The record key is the label. `properties` is a record keyed by property name. A string value
is shorthand for a property's description; an object can declare `description`, `type`
(`string`, `int`, `number`, `boolean`), `identity`, `required`, `cardinality`, `validation`,
`values`, `metadata`, `annotatable` and `annotationVersion`. `parents` names ancestor labels.
`visibility: 'internal'` corresponds to legacy `internal: true`; absent visibility is public.
Internal types are omitted from public discovery, not exempt from authorization.

`cardinality` names `OPTIONAL`, `ONE`, `LIST` or `SET`. It describes value multiplicity;
it does not grant write access. Complete precedence with `required` and `identity`, and
the portable `values` enumeration protocol, are not yet specified here.

### Property validation

`validation` is part of the declared property, for example
`validation: ["nonEmpty", { rule: "range", min: 1, max: 10 }]`.
A string names a rule; an object names it in `rule` and supplies its parameters. These are
property rules, separate from handler input/output JSON Schema. The host retains them with
the type declaration. Existing extraction behavior enforces `oneOf` on a target property:
a record violating the declared vocabulary is dropped before persistence, as described in
[extraction](VIRTUAL_CYPHER.md#56-typed-extraction--kind-extract-lazy-entities).
The complete rule vocabulary, `nonEmpty` and `range` parameter/default semantics, unknown-rule
behavior and enforcement across other write paths are not yet specified or established by
the available host evidence. Declaring a rule must not be presented as proof that every
write path enforces it. Authors needing a guaranteed handler boundary must also use the
[handler schema profile](README.md#me-captured-handler-schema-profile).

## Legacy declarations

The rest of this document describes the supported legacy type forms.

## 1. The two forms

Identical declarations.

```yaml
# types/movies.yml
- name: MovieRating
  properties:
    imdbId:
      identity: true
      description: "The rated film's IMDb id."
    rating:
      type: int
      description: "1–10."
```

```ts
// src/api/movies.ts
import { Entity } from "@embabel/runtime-types";
import { Id, Node, Property } from "@embabel/runtime-types/decorators";

@Node()
export class MovieRating extends Entity {
  /** The rated film's IMDb id. */
  @Id() declare imdbId: string;

  /** 1–10. */
  @Property({ type: "int" }) declare rating: number;
}
```

**Guarantee — the forms are equivalent.** A type declared either way is the same type: same
label, same identity key, same properties, same behaviour at query and dispatch time. A
realm may use both, for different types. Nothing about a consuming query or a calling model
can tell which was used.

**Guarantee — declarations do not execute.** The decorators are read when the realm is
built and are gone before any realm code runs. A decorator argument must be a literal; you
cannot compute one, and you must not rely on side effects from one.

---

## 2. Vocabulary

The decorator names are deliberately those of established object-relational mapping —
Jakarta Persistence and Spring Data Neo4j — so that an author who has mapped an object model
before does not have to learn new words for the same ideas.

| Decorator | Familiar as | Declares |
|---|---|---|
| `@Node({...})` | SDN `@Node` | the class is a node label |
| `@Id()` | JPA `@Id` | the identity key the store merges on |
| `@Property({...})` | SDN `@Property` | metadata the language cannot carry |
| `@Relationship({...})` | JPA `@ManyToOne` + `@JoinColumn` | an edge, on the side holding the key |
| `@Retrieval({...})` | — | the operation whose result binds as this type |

`@Retrieval` has no mapping-framework equivalent, because no such framework has to answer
"a model just looked this up — put it in scope so the next question can refer to it".

---

## 3. What each form expresses

### 3.1 The label

The class name is the label. `@Node()` marks the class as a declared type.

```ts
@Node({ description: "A film, keyed by IMDb id.", userAnchor: false, partial: false })
export class Movie extends Entity { /* Other members omitted. */ }
```

`description`, `userAnchor`, `partial` and `internal` mean exactly what the YAML keys of the
same name mean. Omitting `userAnchor` takes the framework default; see
`LABELS_AND_COMPOSITION.md` §2.

### 3.2 Ancestors and carried labels

Ancestors are `extends`. Capability labels are the declaration-merged interface:

```ts
@Node()
export class Trust extends Organisation { /* Other members omitted. */ }
export interface Trust extends Watchable {}
```

**Guarantee — neither is restated.** A type does not name its own parents in `@Node`; the
class hierarchy and the merged interface are the declaration. The YAML equivalent is
`parents: [Organisation]` plus carrying `Watchable`.

### 3.3 Properties

A `declare`d property is a declared property. `declare` because the value comes from the
graph, not from a constructor.

`@Property` supplies what TypeScript cannot:

```ts
@Property({ type: "int" }) declare year: number;
```

**Requirement — declare `int` where you mean `int`.** TypeScript has one numeric type; the
graph distinguishes integers from reals, and a source that returns `"1994"` is coerced
according to what you declared. A number property with no `@Property({ type })` is treated
as a real.

JSDoc on the property is its description.

### 3.3a Lifecycle — `lifecycle:` holds every node of a label to a curation rule

A type may declare which values of its `status` property a read admits, and which are never
returned:

```yaml
- name: Memory
  lifecycle:
    active: [ACTIVE]          # what a plain read returns — the default
    never:  [CONTRADICTED]    # known-false: not returned even when asked for by name — the default
```

**Guarantee — the rule is written into every read.** `MATCH (m:Memory)` reads only ACTIVE
memories. `MATCH (m:Memory) WHERE m.status = 'SUPERSEDED'`, or `(m:Memory {status: 'STALE'})`,
relaxes the read to anything but a `never` value: the constraint has to be on the node, in the
same clause. `WHERE m.status = 'CONTRADICTED'` answers nothing. This is the rule the platform's
`Proposition` has always been held to; a declared lifecycle holds your label the same way,
whichever source fetched the node and whether it is stored or transient.

**Guarantee — a child inherits it.** A type whose `parents:` chain reaches a type with a
lifecycle is held to the nearest one; a child that declares its own overrides it. So `DiceMemory`
under `Memory` is curated without restating anything, and so is a realm's `ZepMemory`.

**Guarantee — the declaration is the world's own.** It holds in the world whose types declare
it, and in no other; a platform-curated label (`Proposition`) keeps the platform's lifecycle and
a declaration naming it is refused and reported.

**Requirement — the property is `status`, and the node carries it.** A lifecycle is a shared
vocabulary, so there is one spelling of it; a node of a curated label with no `status` answers
nothing. `active` must name at least one value; a value may not be both `active` and `never`;
either breaks the declaration at load, naming the type.

### 3.4 Edges

An edge is declared as a **field on the side that holds the key**:

```ts
@Node()
export class MovieRating extends Entity {
  @Id() declare imdbId: string;

  /** The film this rating is OF. */
  @Relationship({ type: "OF", producer: "movieByImdbId",
                  keyField: "imdbId", recordKeyField: "imdbId" })
  declare movie: Movie;

  /** Films like this one. */
  @Relationship({ type: "SIMILAR_TO", producer: "similarMovies",
                  keyField: "title", recordKeyField: "similarTo" })
  declare similar: Movie[];
}
```

- `keyField` — the property **on this node** whose value is the fetch key.
- `recordKeyField` — the property the fetched record echoes it back in, so the edge links.
- `producer` — what fetches the target when a traversal crosses the edge.

**Guarantee — the key is one the anchor's records carry.** `keyField` must be a property the
anchor type declares, or a field one of the anchor type's own joins names as its
`recordKeyField` — a column its records are already said to carry, such as a foreign key a
type keeps out of its properties so queries follow the edge instead of returning the id. Any
other `keyField` is reported as a load problem against the declaring realm.

**Guarantee — the target is the field's type.** `Movie`, not the string `"Movie"`.

**Guarantee — cardinality is the field's arity.** `Movie` is one; `Movie[]` is many. The
YAML form has no way to say this.

**Guarantee — the direction of declaration does not change the graph.** The YAML declares a
join under the TARGET type naming its anchor; TypeScript declares it on the ANCHOR naming
its target. Both produce the same traversable edge. Write it where it reads better.

### 3.5 Retrieval

```ts
@Retrieval({ operation: "omdb.getMovie", nameFrom: "title",
             fieldMap: { imdbId: "imdbID", title: "Title" } })
export class Movie extends Entity { /* Other members omitted. */ }
```

`fieldMap` maps the source's own field names onto this type's. `nameFrom` chooses the
property whose value names the binding when the result is put in scope.

---

## 4. What TypeScript checks that YAML does not

Not a guarantee about behaviour — a guarantee about when you find out:

- a parent or carried label that does not exist is a compile error, not a load-time warning;
- an edge whose target type does not exist is a compile error;
- a renamed property breaks every declaration that reads it;
- a method's declared return type names a real type.

A realm authored in TypeScript and validated before install cannot be installed with these
mistakes in it. A realm authored in YAML can, and reports them as loading problems.

---

## 5. Where each legacy form is available

**YAML** — always. A realm needs no build to declare types.

**TypeScript** — where the realm already compiles TypeScript. Declarations live beside the
handlers they belong to. These decorator declarations need their existing build path. New source realms use the
`types` record in `realm.ts`, including realms with no handlers or build.

**Requirement — do not declare the same type twice.** A type declared in both forms is a
realm authoring error. Split by type, not by fact: `Movie` in one form, `MovieRating` in the
other, is fine; `Movie` in both is not.

---

## 6. What stays data

Bulk reference records (`reference/*.yml`) and vendored third-party API descriptions stay
data files in both worlds. They describe rows and remote contracts, not your type model, and
nothing checks them for you in either form.

---

## Changelog

**0.1.0** — first published contract: the two declaration forms and their equivalence, the
mapping-framework vocabulary, edges as fields with typed targets and arity-derived
cardinality, retrieval bindings, the check-time difference, and availability.

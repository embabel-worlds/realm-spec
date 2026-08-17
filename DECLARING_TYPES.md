# Declaring Types

**Spec version: 0.1.0**

Normative. A realm declares its types in **YAML** or in **TypeScript**. Both forms carry the
same facts and produce the same behaviour; this document specifies both and states what is
guaranteed about each.

Neither is deprecated. Choose by what your realm already needs: a realm that ships only
types and reference data needs no build and should use YAML; a realm that already compiles
TypeScript gets a compiler's help by declaring there too.

See `LABELS_AND_COMPOSITION.md` for what a label *means* once declared.

---

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
export class Movie extends Entity { … }
```

`description`, `userAnchor`, `partial` and `internal` mean exactly what the YAML keys of the
same name mean. Omitting `userAnchor` takes the framework default; see
`LABELS_AND_COMPOSITION.md` §2.

### 3.2 Ancestors and carried labels

Ancestors are `extends`. Capability labels are the declaration-merged interface:

```ts
@Node()
export class Trust extends Organisation { … }
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
export class Movie extends Entity { … }
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

## 5. Where each form is available

**YAML** — always. A realm needs no build to declare types.

**TypeScript** — where the realm already compiles TypeScript. Declarations live beside the
handlers they belong to. A single-file realm that ships handlers without a build cannot
declare types this way; use YAML.

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

# Composing a realm

`realm.ts` is the entry point, not a limit on the number of files. The host evaluates its
imports and reads the resulting default object. This guide is informative; the
[definition evaluation rules](TYPESCRIPT_REALMS.md#definition-evaluation) are normative.

Each numbered example is a separate directory. Install the TypeScript SDK for editor checks.
Use this `tsconfig.json` in each directory, then run `npx tsc --noEmit`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["**/*.ts"]
}
```

These examples have no generated declaration files. Definition-only examples need no handler
entry. The second example includes its guest source and needs host support for captured
handlers, producers and lenses, plus the owner's grants. Typechecking is not installation
or admission. Current host support for definition imports must be checked separately.

## 1. One definition file

Everything this realm declares fits in `realm.ts`. It contributes a type and needs no guest.

```ts
// realm.ts
import type { Realm } from '@embabel/realm-types'

export default {
  name: 'library',
  version: '1.0.0',
  types: {
    Book: {
      userAnchor: false,
      properties: {
        isbn: { identity: true, description: 'ISBN of this edition.' },
        title: 'Published title.',
      },
    },
  },
} satisfies Realm
```

## 2. Records in folders

Each folder exports a record. `realm.ts` assembles them. This captured realm exposes a small
catalogue through a handler, a producer and a lens. Its `lenses/` record goes in
`capturedLenses`; a conventional realm uses the conventional `lenses` declaration instead.

```text
realm.ts
types/index.ts
producers/index.ts
lenses/index.ts
wasm/handlers.ts
tsconfig.json
```

```ts
// types/index.ts
import type { TypeSpec } from '@embabel/realm-types'

export const types = {
  Book: {
    userAnchor: false,
    properties: {
      isbn: { identity: true },
      title: 'Published title.',
    },
  },
  Shelf: {
    properties: { shelfId: { identity: true }, name: 'Shelf name.' },
  },
} satisfies Record<string, TypeSpec>
```

```ts
// producers/index.ts
import type { CapturedProducerSpec } from '@embabel/realm-types'

export const producers = {
  books: {
    handler: 'library.books',
    keyArgument: 'shelfIds',
    joins: [{
      targetLabel: 'Book',
      anchorLabel: 'Shelf',
      relationship: 'HOLDS',
      keyField: 'shelfId',
      recordKeyField: 'shelfId',
    }],
  },
} satisfies Record<string, CapturedProducerSpec>
```

```ts
// lenses/index.ts
import type { CapturedLensSpec } from '@embabel/realm-types'

export const lenses = {
  catalogue: { name: 'Catalogue', handler: 'library.catalogue' },
} satisfies Record<string, CapturedLensSpec>
```

```ts
// realm.ts
import type { Realm } from '@embabel/realm-types'
import { types } from './types/index.ts'
import { producers } from './producers/index.ts'
import { lenses } from './lenses/index.ts'

export default {
  name: 'library',
  version: '1.0.0',
  execution: 'captured',
  host: 'wasm',
  types,
  producers,
  capturedLenses: lenses,
  handlers: {
    books: {
      namespace: 'library',
      input: {
        type: 'object',
        properties: { shelfIds: { type: 'array', items: { type: 'string' } } },
        required: ['shelfIds'],
      },
      output: { type: 'array', items: { type: 'object' } },
    },
    catalogue: { namespace: 'library', output: { type: 'object' } },
  },
} satisfies Realm
```

```ts
// wasm/handlers.ts
export async function books(input: { shelfIds: string[] }) {
  return input.shelfIds.map(shelfId => ({
    shelfId, isbn: '9780141439518', title: 'Pride and Prejudice',
  }))
}

export async function catalogue() {
  return { items: [{ isbn: '9780141439518', title: 'Pride and Prejudice' }] }
}
```

Call `library.books` with `{"shelfIds":["fiction"]}` to get the book with
`shelfId: "fiction"`. The producer uses stored `Shelf` anchors; it does not create shelves
by being declared. The catalogue lens needs no pre-existing graph data.

## 3. One file per type

These three files are another complete definition. Each part exports a record so its key
travels with the type.

```ts
// types/book.ts
import type { TypeSpec } from '@embabel/realm-types'
export const book = {
  Book: { properties: { isbn: { identity: true }, title: 'Published title.' } },
} satisfies Record<string, TypeSpec>
```

```ts
// types/reader.ts
import type { TypeSpec } from '@embabel/realm-types'
export const reader = {
  Reader: { properties: { readerId: { identity: true }, name: 'Reader name.' } },
} satisfies Record<string, TypeSpec>
```

```ts
// realm.ts
import type { Realm } from '@embabel/realm-types'
import { book } from './types/book.ts'
import { reader } from './types/reader.ts'

export default {
  name: 'library',
  version: '1.0.0',
  types: { ...book, ...reader },
} satisfies Realm
```

If both records declare `Book`, the later spread replaces the earlier value in full. It
does not merge the properties inside the type. The host sees only that evaluated result,
so it cannot report the lost key. Use a duplicate-key check in your authoring checks when
parts come from different maintainers. Do not expect a TypeScript warning for every spread
collision.

## 4. Reusing a fragment

A pure helper can return common property specifications. `satisfies` checks the fragment
while preserving literal types. Each call returns a fresh object, so extending one type
does not accidentally change another.

```ts
// types/common.ts
import type { PropertySpec } from '@embabel/realm-types'

export function commonProperties() {
  return {
    source: { type: 'string', description: 'Where the record came from.' },
    title: { type: 'string', required: true },
  } satisfies Record<string, PropertySpec>
}
```

```ts
// realm.ts
import type { Realm } from '@embabel/realm-types'
import { commonProperties } from './types/common.ts'

export default {
  name: 'publications',
  version: '1.0.0',
  types: {
    Book: { properties: { ...commonProperties(), isbn: { identity: true } } },
    Article: { properties: { ...commonProperties(), doi: { identity: true } } },
  },
} satisfies Realm
```

The helper may calculate values from its arguments. It may not read a file, environment
variable, clock or network service to decide what the realm declares.

## 5. Subpath imports

For a larger definition, `#types` can replace a long relative path. This complete example
uses the realm's `package.json` import map, which both the definition resolver and the
TypeScript configuration above can read. A `tsconfig.json` alias by itself is insufficient.

```json
{
  "type": "module",
  "imports": { "#types": "./types/index.ts" }
}
```

```ts
// types/index.ts
import type { TypeSpec } from '@embabel/realm-types'
export const types = {
  Book: { properties: { isbn: { identity: true }, title: 'Published title.' } },
} satisfies Record<string, TypeSpec>
```

```ts
// realm.ts
import type { Realm } from '@embabel/realm-types'
import { types } from '#types'

export default { name: 'library', version: '1.0.0', types } satisfies Realm
```

The relative spelling is `import { types } from './types/index.ts'`. Both identify the same
captured definition file. Neither spelling gives the definition access outside the realm.
Hosts that have not implemented subpath mappings must report the unsupported import.

Handlers run later, in the guest, under different import rules. The current reference
TypeScript handler profile accepts relative named value imports confined to the handler
folder (`wasm/`), for example `import { format } from './lib/format.ts'`. It refuses
`#types`, bare packages and `../types/index.ts`, even when an editor resolves them.
Type-only imports are erased; they do not make a runtime value import safe. Keep shared
guest helpers inside the handler folder and keep definition helpers outside guest execution.

## Dependency files with readable names

Declare a local module as `from: { local: 'modules/stockfish-19.0.0.wasm' }` and keep its
required `sha256` beside it in `realm.ts`. No manifest or module lock repeats that source.
See [dependency examples](TYPESCRIPT_REALMS.md#dependency-examples) for local, registry and
URL declarations.

A captured realm's identity includes every file's path as well as its digest and executable
bit. Renaming `modules/<sha256>.wasm` to a readable name creates a new realm revision even
when the module bytes stay identical. Update `from.local` in `realm.ts` and install that
revision through the normal admission flow. The module digest, methods and permissions do
not change just because the file has a new name. Legacy digest-named modules and their
dependency manifest continue loading unchanged in YAML-only realms.

# Session 2 frontier: architecture and plan

Use this reference only during Session 2, after `PRODUCT.md` and `SOURCE-FINDINGS.md` are confirmed as the approved baseline.

## 3. Domain and graph

Decide:

- anchor labels and keys;
- target types, identity properties, and collision risks;
- relationships and traversal direction;
- exact, bounded, inferred, and unknown values;
- source records versus canonical entities;
- identifier joins versus candidate, name, or geographic matches;
- provenance on nodes, edges, and rendered answers;
- public versus user-private data and user anchoring.

Completion: every graph-backed product question is expressible as a traversal without inventing identity or certainty; questions that should bypass the graph are explicit.

## 4. Retrieval and collection contracts

For each collection, decide:

- live, mirrored, reference-seeded, generated, or another strategy supported by the fetched specification;
- producer kind and operation;
- per-key versus batch behavior;
- predicate pushdown and evidence that it narrows at the source;
- pagination, page budget, and evidence that pages advance;
- projection, coercion, and missing-field behavior;
- cache and refresh behavior;
- cost or rate bucket and fan-out limits;
- identity and deduplication;
- source-contract shape, partition, ordering, visibility, and completeness;
- how failure, partial retrieval, truncation, and genuine emptiness differ.

Completion: each traversal has a bounded execution strategy and explicit complete, partial, empty, unavailable, and failed states.

## 5. User surface

Choose only surfaces needed by approved product questions:

- composable named views;
- lenses for procedural or focused experiences;
- skills for on-demand guidance;
- apps for interactive presentation;
- actions, events, handlers, commands, or personalities when the product requires them.

For every surface, define its primary question, evidence drill-down, warnings, empty state, partial state, and unavailable state.

Completion: each promised question has one primary route and no competing ceremonial surface.

## 6. Trust and operations

Decide:

- credential names and host-managed configuration;
- secret handling and redaction;
- retry policy grounded in measured source behavior;
- licensing and attribution shown to users;
- privacy, cache, graph-persistence, retention, and erasure boundaries;
- prohibited characterizations and required qualifications;
- deployment prerequisites and source-outage behavior;
- observability for partial reads, stale data, failed fetches, and refresh failures.

Completion: the realm can fail without rendering uncertainty as a confident claim, and retained data has an explicit lifecycle.

## 7. Implementation and validation

Choose the **first thin slice** by asking: “What single end-to-end path proves the architecture and answers one approved question?”

For that slice and each later slice, record:

- exact product question and acceptance example;
- anchor, source operation, producer/type, user surface, provenance, and completeness path;
- fixture and projection tests;
- executable source probes;
- host shape or contract tests;
- app or UI tests when applicable;
- expected validation command and result;
- assumptions the slice proves;
- explicit deferrals to later slices.

Plan one bounded capability per fresh implementation session. Scaffolding without a user-facing answer is not a slice.

Completion: every slice has a checkable result, the first slice proves the riskiest architectural path through one useful answer, and `IMPLEMENTATION.md` names exactly where the next session starts.

## Session procedure

Confirm `PRODUCT.md` and `SOURCE-FINDINGS.md` as the approved baseline. Use the realm architect and fresh adversarial reviewer required by `SKILL.md`.

When every completion criterion passes, present the shared understanding and proposed writes. Create only after explicit approval:

- `realm.yml` with the stable realm identity;
- `ARCHITECTURE.md` with graph model, provenance, producers, source contracts, completeness, caching, surfaces, credentials, and safety rules;
- `IMPLEMENTATION.md` with approved thin slices, status, evidence, and exact implementation entry point;
- `README.md` describing the intended current state once implemented.

Give consequential decisions stable IDs such as `PROD-1`, `SRC-1`, and `ARCH-1`. Supersede overturned decisions by linking replacements rather than erasing history. Create only capability directories used by an approved slice.

Pass the file gate from `SKILL.md`, report the exact implementation invocation, and stop.

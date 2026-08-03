# Realm creation design tree

Use this as a frontier map, not a questionnaire. Ask only decisions whose prerequisites are settled. Investigate facts before presenting a decision. After the first new realm is created with this workflow, simplify or extend this map only where actual use shows a gap.

## 1. Product

Settle before source or architecture choices:

- Who is the user, and what job are they trying to do?
- Which concrete questions must the realm answer?
- What is the smallest valuable promise?
- Which tempting questions are explicit non-goals?
- What language would overstate or characterize the evidence?
- What must a user be able to inspect behind every answer?

Completion: each promised question has an example input, expected answer shape, and explicit boundary.

## 2. Sources

For every promised question, establish with dated evidence:

- authoritative source, publisher, licence or usage rights;
- public, credentialed, paid, or restricted access;
- endpoint/file shape and stable identifiers;
- supported query axes versus axes users need;
- filtering behavior, including whether unknown filters are ignored;
- paging, caps, ordering, declared totals, and truncation signals;
- update cadence, corrections, deletion, and historical coverage;
- rate limits, retries, timeouts, and failure representations;
- fields needed for provenance and links back to records;
- privacy, personal-data, and redistribution constraints.

Use focused executable probes for assumptions that change correctness, completeness, or architecture. Compare filtered/unfiltered calls and adjacent pages rather than trusting documentation alone.

Completion: every product question is supported by a measured access path, or is narrowed/rejected.

## 3. Domain and graph

Decide:

- anchor labels and keys;
- target types, identity properties, and collision risks;
- relationships and traversal direction;
- exact, bounded, inferred, and unknown values;
- source records versus canonical entities;
- joins that are identifier-based versus candidate/name/geographic matches;
- provenance attached to nodes, edges, and rendered answers;
- public versus user-private data and user anchoring.

Completion: every product question can be written as a traversal without inventing identity or certainty.

## 4. Retrieval and collection contracts

For each collection, decide:

- live, mirrored, reference-seeded, generated, or another current spec-supported strategy;
- producer kind and operation;
- per-key versus batch behavior;
- predicate pushdown and proof that it narrows;
- pagination and proof that pages advance;
- projection, coercion, and missing-field behavior;
- cache and refresh behavior;
- cost/rate bucket and fan-out limits;
- identity and deduplication;
- source-contract shape, partition, ordering, visibility, and completeness;
- how failure differs from a genuine empty result.

Completion: each traversal has a bounded execution strategy and an honest partial/failure state.

## 5. User surface

Choose only surfaces needed by the product questions:

- composable named views;
- lenses for procedural or focused experiences;
- skills for on-demand usage guidance;
- apps for interactive presentation;
- actions, events, handlers, commands, or personalities when the product actually calls for them.

For every surface, define drill-down to evidence, warnings, empty states, and unavailable states.

Completion: each promised question has one primary route and no competing ceremonial surface.

## 6. Trust and operations

Decide:

- credential names and host-managed configuration;
- secret handling and redaction;
- retry policy based on measured behavior;
- licensing and attribution shown to users;
- privacy and retention boundaries;
- prohibited characterizations and required qualifications;
- deployment prerequisites and source outages;
- observability for partial reads, stale data, and failed fetches.

Completion: the realm can fail without turning uncertainty into a confident claim.

## 7. Implementation and validation

Plan:

- the thinnest end-to-end slice;
- later slices, one bounded capability at a time;
- fixture and projection tests;
- executable source probes;
- host shape/contract tests;
- app or UI tests when applicable;
- adversarial review and release checks.

Completion: every slice has a checkable result and the first slice proves the architecture rather than merely scaffolding it.

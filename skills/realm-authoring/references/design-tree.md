# Session 1 frontier: product and sources

Use this reference only during Session 1. Settle product decisions first, then establish the source facts needed to support them.

## 1. Product decisions

Settle:

- who the user is and what job they are trying to do;
- which concrete questions the realm must answer;
- the **first useful answer**, phrased plainly: “If the first version did only one useful thing, what single question must it answer?”;
- tempting questions that remain explicit non-goals;
- language that would overstate, characterize, or invent certainty;
- the evidence and uncertainty a user must be able to inspect.

For every promised question, record:

- one example input;
- expected answer shape;
- explicit boundary;
- evidence needed to distinguish an empty answer from partial or failed retrieval.

Completion: the first useful answer is one bounded question, and every broader promised question has an example, answer shape, and boundary.

## 2. Source facts

For every promised question, establish an **evidence ledger** containing:

- authoritative source and publisher;
- licence, usage-rights evidence, or a clearly labelled owner attestation;
- public, credentialed, paid, or restricted access;
- endpoint or file shape and stable identifiers;
- supported query axes compared with the axes the product needs;
- filtering behavior, including a measured unknown-filter result;
- default and maximum page sizes, ordering, declared totals, caps, and truncation signals;
- proof that adjacent pages advance and filtered retrieval narrows;
- update cadence, corrections, deletion, and historical coverage;
- rate limits, retries, timeouts, and failure representations;
- fields required for provenance and links back to source records;
- privacy, personal-data, retention, and redistribution constraints;
- evidence level: live probe, executable contract test, source inspection, documentation, or owner attestation;
- date, exact source revision, reproducible command, observed result, and remaining uncertainty.

Prefer focused executable probes for facts that affect correctness, completeness, or later architecture. Compare filtered and unfiltered calls and adjacent pages. A reproducible command identifies the tested revision and constructs or verifies a clean checkout; a mutable local path alone is not reproducible evidence.

When production access is unavailable, use executable local contract tests where they measure the same source behavior and label deployment behavior unmeasured. A correctness-critical unmeasured fact remains on the frontier until the product is narrowed, a different source path is chosen, or the user explicitly accepts the documented operational risk as a decision.

Completion: every product question has a measured access path, or has been narrowed or rejected; every correctness-critical uncertainty is visible and dispositioned; every evidence command is revision-stable and safe to rerun.

## Session procedure

Use the source investigator and adversarial reviewer required by `SKILL.md`. Source findings establish measured constraints and viable candidates; graph topology, producer strategy, surfaces, caching, and other architecture choices remain Session 2 decisions.

When both completion criteria pass, present the shared understanding and proposed writes. Create only after explicit approval:

- `PRODUCT.md` — user, concrete answerable questions, first useful answer, boundaries, and non-goals;
- `SOURCE-FINDINGS.md` — dated reproducible evidence, evidence level, rights basis, access, limits, uncertainties, and realm-spec commit.

List contradictions in candidate README or ADR documents before approval. Ask whether each should be marked superseded in this phase; change only those included in the approved writes.

Pass the file gate from `SKILL.md`, report the exact Session 2 invocation, and stop.

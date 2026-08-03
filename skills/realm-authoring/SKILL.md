---
name: realm-authoring
description: Design and create a new Embabel realm through evidence-led research, explicit decisions, thin implementation slices, and validation.
disable-model-invocation: true
compatibility: Requires a coding-agent harness with filesystem, shell, network, and sub-agent support.
---

# Create an Embabel realm

Create a new `realm-*` repository end to end. Do not use this skill to extend an established realm; resuming a realm started through this workflow is expected.

Work across fresh sessions. One session completes one phase; `IMPLEMENTATION.md` becomes the durable handoff once architecture is approved. Never commit, push, publish, create a remote, initialize Git, or overwrite a non-empty directory without explicit approval.

## Start or resume

1. Fail early if sub-agents are unavailable.
2. Run `scripts/fetch-spec.py --json` from this skill's directory. If fetching fails, stop. Read the fetched `README.md` and every document it links for the capabilities under consideration. The fetched commit is the contract; remembered realm syntax is not.
3. Inspect the requested target path and its Git status when applicable. Require a repository basename beginning with `realm-`. Do not create files yet.
4. If `PRODUCT.md`, `SOURCE-FINDINGS.md`, `ARCHITECTURE.md`, or `IMPLEMENTATION.md` exists, infer the current phase from their contents, show the evidence, and ask the user to confirm where to resume.

Completion: the target, specification commit, and current phase are explicit and user-confirmed.

## Design by frontier

Read [the design tree](references/design-tree.md). Interview the user until every branch is settled.

Map the work as a **design tree**: every decision branches into the decisions that depend on it. Work in rounds. The **frontier** is every unresolved decision whose prerequisites are settled. Ask the whole frontier in one numbered round, provide a recommended answer for each question, and then wait.

After each response, update the tree and recompute the frontier. A question that depends on an answer still pending belongs to a later round. Facts are the agent's responsibility: investigate the filesystem, fetched specification, source documentation, and live behavior rather than asking the user. Decisions belong to the user.

Across the two design sessions, dispatch at least three independent sub-agents:

- a **source investigator** to measure access, rights, response shape, filtering, paging, limits, identity, and failures;
- a **realm architect** to map approved product questions to types, producers, source contracts, surfaces, provenance, and completeness;
- an **adversarial reviewer** to challenge unsupported claims, silent incompleteness, privacy, credentials, safety, and characterization.

Keep raw sub-agent transcripts out of the realm. Bring their facts and disagreements back into the frontier. Do not write phase documents or implement anything until that phase's frontier is empty and the user explicitly confirms shared understanding.

### Session 1: product and sources

Exhaust branches 1-2 of the design tree. Use the source investigator and adversarial reviewer. After explicit approval, create `PRODUCT.md` with users, answerable questions, product promise, and non-goals, and `SOURCE-FINDINGS.md` with dated reproducible evidence, rights, access, limits, uncertainties, and the realm-spec commit used. Report the exact next invocation and stop.

Completion: each promised question has an example and boundary, and each depends on a measured access path or is narrowed/rejected.

### Session 2: architecture and plan

On a fresh invocation, confirm the approved product/source baseline. Exhaust branches 3-7. Use the realm architect and a fresh adversarial review. After explicit approval, create:

- `realm.yml` with the stable realm identity;
- `ARCHITECTURE.md` with graph model, provenance, producers, source contracts, completeness, caching, surfaces, credentials, and safety rules;
- `IMPLEMENTATION.md` with approved vertical slices, status, evidence, and the exact next-session entry point;
- `README.md` describing only the intended current state once implemented.

Give consequential decisions stable IDs such as `PROD-1`, `SRC-1`, and `ARCH-1`. If evidence later overturns one, mark it superseded and link its replacement rather than erasing the history. Create no empty capability directories; add one only when an approved slice uses it.

Completion: no decision is silently assumed, all three roles are accounted for across the design, the documents agree and record unresolved limits honestly, and one smallest vertical slice is explicit. Update `IMPLEMENTATION.md`, give the exact next invocation, and stop.

## Implement one slice per session

On a fresh invocation, confirm the resume point, reread the specification sections governing that slice, and implement the smallest complete path for one real product question: anchor → source → producer/type → user-facing result → provenance/completeness.

Start declarative. Add TypeScript handlers only for invariants or source behavior the current specification cannot express declaratively. Write tests before implementation wherever a runnable contract exists. Preserve source probes under the target realm's `scripts/` when they establish assumptions that affect correctness, completeness, or architecture. Probes must use environment variables for credentials and must not record secrets.

If implementation disproves an approved assumption, stop. Record the evidence, reopen every dependent design-tree branch, and wait for renewed approval before continuing.

Use an isolated Python environment with `requirements.txt`, then run `scripts/validate-realm.py <target>` from this skill's directory plus the closest host/project tests documented by the fetched specification. Update all four living documents and `README.md` to the implemented state. Record the next bounded slice in `IMPLEMENTATION.md`, report the exact next invocation, and stop.

Completion: one approved question works end to end, its assumptions have reproducible evidence, tests and validation pass, and documentation matches behavior.

## Expand and finish

Repeat one bounded capability slice per fresh session. When all approved questions are implemented, dispatch a fresh adversarial reviewer and resolve every finding. Run the full relevant validation suite and scan the diff for secrets, generated files, stale claims, and unrelated changes.

The realm is complete only when every approved question has an implemented path, every correctness-critical source assumption has evidence, completeness and failure states are surfaced honestly, validation passes, documentation describes current behavior, and the user accepts the final report.

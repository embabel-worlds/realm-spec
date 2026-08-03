# Thin-slice implementation

Use this reference only after architecture approval and `IMPLEMENTATION.md` identifies a bounded next slice.

## Implement one thin slice

Confirm the resume point in `IMPLEMENTATION.md` and reread only the fetched specification sections governing that slice. Implement one real product question end to end:

anchor → source → producer/type → user-facing result → provenance/completeness

Start declarative. Add TypeScript handlers only for invariants or source behavior the current specification cannot express declaratively. Write tests first wherever a runnable contract exists.

Preserve correctness-critical source probes under the target's `scripts/` and follow the evidence-safety rule in `SKILL.md`.

When implementation disproves an approved assumption:

1. record the evidence;
2. load the design reference containing the dependent decision;
3. reopen every affected decision;
4. wait for renewed approval.

Create a temporary isolated Python environment from `$SKILL_DIR/requirements.txt`. Run its Python against `"$SKILL_DIR/scripts/validate-realm.py" <target>`, then run the closest host or project tests named by the fetched specification.

Update `PRODUCT.md`, `SOURCE-FINDINGS.md`, `ARCHITECTURE.md`, `IMPLEMENTATION.md`, and `README.md` to the implemented state. Pass the file gate from `SKILL.md`. Record the next bounded slice in `IMPLEMENTATION.md`, report the exact next invocation, and stop.

Completion: one approved question works end to end; correctness-critical assumptions have revision-stable reproducible evidence; tests and validation pass; documentation matches behavior.

## Expand and finish

Repeat one thin slice per fresh session. When all approved questions work:

1. dispatch a fresh adversarial reviewer;
2. resolve every blocking finding and disposition each non-blocking finding;
3. run the full relevant validation suite;
4. pass the file gate;
5. inspect every accounted path for secrets, generated output, stale claims, and unrelated changes;
6. present the final report for user acceptance.

Completion: every approved question has an implemented path, every correctness-critical source assumption has evidence, partial and failure states remain explicit, validation passes, documentation describes current behavior, and the user accepts the final report.

---
name: realm-authoring
description: Design and create a new Embabel realm through evidence-led research, explicit decisions, thin implementation slices, and validation.
disable-model-invocation: true
compatibility: Requires a coding-agent harness with filesystem, shell, network, and sub-agent support.
---

# Create an Embabel realm

Use this skill only to create or resume a `realm-*` repository started through this process. Work in fresh sessions: one session completes one phase, and `IMPLEMENTATION.md` becomes the durable handoff after architecture approval.

Treat the target as read-only until the current phase gate permits writes. Commit, push, publish, remote creation, Git initialization, and changes inside a non-empty target require explicit approval.

## Start or resume

1. Resolve the directory containing this `SKILL.md` to an absolute `SKILL_DIR`. Use absolute paths for every bundled script.
2. Confirm the harness lists sub-agent support. Capability inspection is the availability check; reserve dispatches for the required roles. Report a blocker when support is absent.
3. Run `python3 "$SKILL_DIR/scripts/fetch-spec.py" --json`. Continue only when it returns successful JSON containing `commit` and `contract`. Read the fetched `README.md` and each document it links for capabilities under consideration. The fetched commit is the contract.
4. Inspect the target path and Git status. Require a repository basename beginning with `realm-`. Keep the target read-only.
5. Infer the phase from `PRODUCT.md`, `SOURCE-FINDINGS.md`, `ARCHITECTURE.md`, and `IMPLEMENTATION.md`. Treat other documents as candidate evidence until confirmed. Show the evidence and ask the user to confirm the phase.
6. Load only the material for the confirmed phase:
   - Session 1: [frontier mechanics](references/design-frontier.md) and [product and sources](references/design-tree.md)
   - Session 2: [frontier mechanics](references/design-frontier.md) and [architecture and plan](references/architecture-plan.md)
   - implementation or expansion: [thin-slice implementation](references/implementation.md), `IMPLEMENTATION.md`, and only the fetched specification sections governing the current slice; load a design reference only when evidence reopens one of its decisions.

Completion: `SKILL_DIR`, target, specification commit, and current phase are explicit; the user has confirmed the phase.

Evidence commands and probes use environment variables for credentials and emit only schema facts, status codes, counts, paging metadata, timings, redacted identifiers, and other non-sensitive aggregates. Keep production payloads, customer values, and secrets out of commands, output, fixtures, documents, and commits.

## File gate

At every phase handoff, pass the **file gate**:

- run `git diff --check` for tracked changes;
- for each untracked file, run `test -z "$(git diff --no-index --check /dev/null <file> 2>&1)"`;
- inspect `git status --short` and account for every changed or untracked path.

## Run the confirmed phase

Follow only the reference selected in Start or resume. Its completion criteria and phase procedure are authoritative. When it reports the exact next invocation and says stop, end the session.

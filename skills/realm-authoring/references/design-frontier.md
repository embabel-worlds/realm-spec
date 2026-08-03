# Design by frontier

Use this reference only during Sessions 1–2.

Map decisions as a **design tree**. The **frontier** is every unresolved decision whose prerequisites are settled. Ask the whole frontier in one numbered round, recommend an answer for each decision, and wait. Recompute the frontier after every response.

Every round has two distinct sections:

1. **FACTS** — verified evidence, provenance, disagreements, and uncertainty. Facts require no approval.
2. **DECISIONS** — numbered user choices with recommendations. Decisions require an explicit answer.

Investigate facts through the fetched specification, named source repositories, source documentation, focused probes, and live behavior. Search only explicitly relevant paths and file types; exclude private context, archives, logs, generated output, and customer-record stores. If an unexpected result contains sensitive record content, discard it and narrow the search.

Required independent roles:

- Session 1: a **source investigator** and an **adversarial reviewer**;
- Session 2: a **realm architect** and a fresh **adversarial reviewer**.

Keep raw sub-agent transcripts out of the realm. Reconcile their evidence and disagreements in FACTS.

The **phase gate** opens only when the current phase reference's completion criteria pass and the user explicitly confirms shared understanding and the proposed writes. Until then, continue the frontier interview without creating phase documents or implementation files.

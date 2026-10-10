# Publishers in an Embabel world

The [Realm Publishing Protocol](https://github.com/embabel-worlds/publisher/blob/main/spec/PROTOCOL.md) lets an existing application publish itself as a realm. The
protocol, its conformance suite, its adoption skill and its libraries live in
[embabel-worlds/publisher](https://github.com/embabel-worlds/publisher), under the Apache License 2.0,
and say what any world must do with a publisher. This document says how an Embabel world does it:
how a manifest becomes a realm on the Virtual Cypher engine, and what code mode offers scripts. It is
part of this specification and under its terms.

## 1. From manifest to realm

An Embabel world builds the realm from the manifest alone. Nobody writes it, and nobody edits it.

| Manifest | Realm |
|---|---|
| `types[]` | `types/` entries, namespaced under the realm |
| `identity` | `identity: true` on that property |
| `spine` on a property | `hub: <spine>` on that property |
| each `lookup` | a producer of kind `publisher` (§2), keyed by that property, with the lookup's `maxKeys` as its batch size |
| `references` | a join between the two types, through the lookup on the referencing property |
| an `object` property | flat properties on the node, named by camel-cased path |
| a part type | a type whose nodes hang off the owner by `partOf.relationship`, filled from the owner's fetches or the part's own lookups |
| a lookup by a spine-bound property | a join anchored on that spine |
| `query` | a scan producer |
| `filter`, `sort`, `project` | the pushdown declared on every producer of that type, used by the planner as the protocol's §4.1 describes |
| `aggregate` | aggregate pushdown for `count`/`sum`/… over that type, keyed or grouped |
| `cache`, `cost` | the producers' cache policy and pacing |
| metadata, `about` | the realm's `realm.yml` fields and brief |
| `skills[]` | the realm's skills, without scripts |
| `events[]` | world sources, delivered by poll or by push subscription |
| `verbs[]` | gateway operations, and methods on their subject types (§3); `approval` becomes the verb's approval policy in the world |
| `agents[]` | proposed agents, off duty, unsponsored and unsigned (the protocol's §5.3) |

## 2. The `publisher` producer kind

Each lookup and query becomes a producer of kind `publisher`. Its behaviour is the protocol's batch
contract (§4.2), query contract (§4.3) and aggregate contract (§4.4), and nothing else. It takes no
authored query and no configuration beyond what the manifest says. It is a pushdown source in the
engine's existing sense: it absorbs exactly the predicates the manifest declares, and the graph
applies everything else after the fetch, as for every other producer kind
([VIRTUAL_CYPHER.md §5.3](VIRTUAL_CYPHER.md#53-producer-kinds)).

## 3. What scripts see

A publisher ships no code into the world, and it does not need to for code to reach it. The world
generates the typed surface that scripts, routines and apps use from the manifest at install, and
regenerates it whenever the manifest's `ETag` changes. It appears in the world's capability listing
like any other realm's surface. The publisher author never writes TypeScript, whatever language the
publisher is written in.

```ts
/** An invoice issued to a customer. */
interface Invoice {
  number: string;
  customerId: string;
  amount: Decimal;              // a branded string: exact, never a float
  dueDate: string;              // ISO 8601 date
  status: "draft" | "open" | "paid" | "void";
  lines?: InvoiceLine[];        // a part list, present when asked for
}

declare namespace gateway.billing {
  /**
   * Refund part or all of a paid invoice to the customer's original payment method.
   * Needs approval when amount > 500: "Refunds over 500 need a second person."
   */
  function issueRefund(input: IssueRefundInput, options?: { dryRun?: boolean }):
      Promise<IssueRefundOutput | PendingApproval | DryRunResult>;
}
```

| Manifest | Generated |
|---|---|
| a type | an interface, with each property's description as JSDoc |
| `decimal`, `date`, `datetime` | branded strings, so exact values are never coerced to floats |
| an `object` property | a nested interface |
| a part list | an optional array of the part's interface |
| a verb | a function in the realm's namespace, with input and output types generated from its JSON Schemas by a standard converter, and its description and approval rule as JSDoc |
| a verb with a `subject` | also a **method on the subject type**, so code that has queried its way to an invoice calls `invoice.sendReminder({ note })` |
| an event | the typed `signal.properties` of a routine that matches it |

**Approval is in the return type.** A verb that can need approval returns
`Output | PendingApproval`. A script cannot assume the refund happened. The compiler makes it handle
the case where the call is waiting for a person, and `PendingApproval` carries the approval request's
id to wait on or report. A verb with `dryRun` accepts `{ dryRun: true }` and then returns `DryRunResult`.

**Reads are Cypher, not generated accessors.** The world generates no `billing.Invoice.byCustomerId(...)`.
A script reads a publisher's types the way it reads every type: through the world's Cypher query path,
which pushes down into the publisher (the protocol's §4.1) and joins it to the rest of the world in the same query.
The generated interfaces type the rows. A second, publisher-only read path would join nothing and would
duplicate a surface that already exists.


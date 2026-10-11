# Publishers in an Embabel world

The [Realm Publishing Protocol](https://github.com/embabel-worlds/publisher/blob/main/spec/PROTOCOL.md) lets an existing application publish itself as a realm. The
protocol, its conformance suite, its adoption skill and its libraries live in
[embabel-worlds/publisher](https://github.com/embabel-worlds/publisher), under the Apache License 2.0,
and say what any world must do with a publisher. This document says how an Embabel world does it:
how a manifest becomes a realm on the Virtual Cypher engine, and what code mode offers scripts. It is
part of this specification and under its terms.

## 1. From manifest to realm

An Embabel world builds the realm from the manifest alone. Nobody writes it, and nobody edits it.

The installer fetches the manifest and writes a realm named `publisher-<name>`. The realm is written
through the ordinary draft path (written, validated, installed), so it is checked like any authored
realm. It records the publisher URL, the manifest's `ETag` and the credential name in
`publisher/source.json`, and keeps the manifest it was built from. Reinstalling an unchanged manifest
rebuilds nothing. The code-door tool is `install_publisher(url, confirmed)`, available in developer
mode. An `experimental` publisher needs `confirmed: true`.

| Manifest | Realm | Status |
|---|---|---|
| `types[]` | `types/` entries. Labels carry the realm's prefix: `Owner` in a `petclinic` manifest is `PetclinicOwner`. | built |
| `identity` | `identity: true` on that property | built |
| `spine` on a property | `hub: <spine>` on that property | built |
| each `lookup` | a producer of kind `publisher` (§2), keyed by that property, with the lookup's `maxKeys` as its batch size, and a door so a query can pin the type by that property | built |
| `references` | a join each way between the two types, through the lookups | built |
| `query` | a scan producer behind a door every query may use, so a bare `MATCH (o:PetclinicOwner) WHERE …` is answered by the publisher's own query | built |
| `filter` | pushdown declared on every producer of the type (§2) | built |
| `cache` | the producers' cache policy | built |
| `verbs[]` | an OpenAPI document in `apis/`, one `POST /verbs/{name}` operation per verb, with operationIds prefixed by the realm (`petclinicAddVisit`) because operationIds resolve across every installed realm | built |
| `effect`, `approval` | `write` and `external` verbs are marked as effects. `external` verbs, and every verb whose approval is not `never`, are marked sensitive, which parks an agent's call as a Request. `when` and `decided` are treated as needing approval on every call. | built |
| `auth` | the credential is declared in `keys.yml`, so the owner is asked for it, and is resolved from the owner's wallet, then the environment. `actingUser: required` is refused at install, because the world does not yet send an acting user. | built |
| a lookup by a spine-bound property | a join anchored on that spine | planned: today only `hub:` is written |
| an `object` property | flat properties on the node, named by camel-cased path | planned |
| a part type | a type whose nodes hang off the owner by `partOf.relationship` | planned |
| `sort`, `project`, `limitPerKey` | ordered-limit and projection pushdown | planned: ordered-limit pushdown is specific to `remote` producers today |
| `aggregate` | aggregate pushdown | planned: aggregate pushdown is specific to `remote` producers today |
| `cost` | pacing | planned |
| metadata, `about`, `skills[]` | the realm's `realm.yml` fields, brief and skills | planned |
| `events[]` | world sources | planned |
| `agents[]` | proposed agents, off duty, unsponsored and unsigned | planned |
| an index URL | the owner chooses realms | planned: an index is refused, listing its realms |

A manifest section the world does not build yet is reported as inert at install. It is never
silently dropped.

## 2. The `publisher` producer kind

Each lookup and query becomes a producer of kind `publisher`. Its behaviour is the protocol's batch
contract (§4.2), query contract (§4.3) and aggregate contract (§4.4), and nothing else. It takes no
authored query and no configuration beyond what the manifest says. It is a pushdown source in the
engine's existing sense: it absorbs exactly the predicates the manifest declares, and the graph
applies everything else after the fetch, as for every other producer kind
([VIRTUAL_CYPHER.md §5.3](VIRTUAL_CYPHER.md#53-producer-kinds)).

**What is pushed.** A conjunction of declared comparisons whose operator has an engine predicate:
equality, `in`, the range comparisons and the case-insensitive forms. `prefix`, `ne`, `notIn`, the
null tests, `between`, `has` and `hasAny` have no engine predicate yet, so the graph evaluates them
after the fetch. `datetime` comparisons are never pushed, because the graph compares their text
while the publisher compares instants.

**Answers.**
- `missing` is a success with no records, cacheable for the type's `negativeTtlSeconds`.
- `failed` keys, keys the answer does not account for, and any non-2xx answer are recorded as
  failures by status and problem code, so the batch is never cached.
- `PUBLISHER_DISABLED` is reported as such and is not retried.
- `truncated` is reported as a truncation.
- The transport sends no `Accept-Encoding` and follows no redirect, so the credential cannot be
  carried to another host.

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
| a verb with a `subject` | also a **method on the subject type**, so code that has queried its way to an invoice calls `invoice.sendReminder({ note })`. Planned: today the verb is only a namespace function. |
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


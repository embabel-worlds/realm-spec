# The Spring Boot Provider

> **Status: proposal, informative.** This is the programming model planned for the reference
> implementation of the [World Provider Protocol](PROVIDER_PROTOCOL.md). The protocol is the
> contract. This document is one way to meet it from a Spring Boot application, and every name in
> it is a proposal.

A Spring developer adds a starter, annotates the view types and service methods they want a world
to see, and gets a realm. The world side is the application's URL. Everything else in this document
explains how the developer's choices become the manifest, and how the starter pushes down as much of
each query as their methods can take.

---

## 1. Principles

**The service layer is the boundary.** A Spring application is layered on purpose. Its service
layer is where transactions begin, where `@PreAuthorize` applies, where invariants hold and where
the application decides what leaves it. The starter is an inbound adapter, a peer of the
application's `@RestController`s. It calls service methods through the Spring proxy, with the
acting user in the `SecurityContext`, so every transaction boundary, security rule and audit hook
applies as it does for a request from the UI. It never reads a repository on its own initiative.

**Pushdown comes from parameter types.** The more expressive the types a service method accepts,
the more of a query the starter can hand it. A method that takes a Spring Data `Specification`
accepts the whole filter tree. A method that takes a plain filter object accepts equality on its
fields. The starter declares exactly what each signature can carry. The developer does not
describe capabilities by hand, so the description cannot drift from what the code can do.

**The method still owns the query.** A pushed-down filter reaches the method as a value the method
combines with its own rules (`where.and(visibleTo(user))`). It cannot remove those rules, because
it never replaces the method's query. It only narrows it.

**It looks like Embabel.** The annotations, the description conventions and the programmatic
interface follow the Embabel agent framework, so a developer who knows one reads the other (§8).

## 2. Setup

```xml
<dependency>
  <groupId>com.embabel.realm</groupId>
  <artifactId>embabel-realm-starter</artifactId>
</dependency>
```

```yaml
embabel:
  realm:
    name: billing
    title: Billing
    description: Customers, invoices, payments and refunds from the billing system.
    path: /embabel                       # the provider URL is https://<host>/embabel
    auth:
      schemes: [bearer]                  # the host's own credential, checked by Spring Security
    acting-user:
      mode: required                     # required | optional | ignored  (protocol §3.4)
      jwks-uri: https://world.example.com/.well-known/jwks.json
```

Nothing is exposed until something is annotated or registered. With no annotations, the manifest
has no types and the endpoint answers with an empty realm.

The starter detects what is on the classpath and enables the matching support:
- Spring Data JPA: `Specification` binding and the `RealmJpa` helpers.
- Querydsl: `Predicate` binding.
- jOOQ: `Condition` binding.
- Spring Data MongoDB: `Criteria` binding.
- Spring Security: acting-user mapping and approver authorities.
- `embabel-agent`: exported goals (§8.4).

None of them is required.

## 3. Types

A realm type is the view the service layer returns, not the entity. Annotate it:

```java
@RealmType(name = "Customer", entity = Customer.class)
@JsonClassDescription("A company that buys from us.")
public record CustomerView(
        @RealmId Long id,
        String name,
        @Spine("Organization") String website,
        @Spine("Person") String billingEmail,
        Tier tier,
        @JsonPropertyDescription("Outstanding, in the account currency.") BigDecimal balance) {
}

@RealmType(name = "Invoice", entity = Invoice.class)
@JsonClassDescription("An invoice issued to a customer.")
public record InvoiceView(
        @RealmId String number,
        @RealmPath("customer.id")
        @RealmReference(type = CustomerView.class, relationship = "BILLED", direction = Direction.IN)
        Long customerId,
        BigDecimal amount,
        LocalDate dueDate,
        InvoiceStatus status) {
}
```

| Annotation | Manifest |
|---|---|
| `@RealmType(name, entity)` | a type. `entity` is optional and lets the starter translate filters into queries on that entity (§4). |
| `@RealmId` | `identity` |
| `@Spine("Organization")` | `spine` on the property (protocol §6) |
| `@RealmReference` | `references` (protocol §3.2) |
| `@RealmPath("customer.id")` | where the property lives on `entity`, when it is not the same name |
| `@JsonClassDescription`, `@JsonPropertyDescription` | `description` |
| Java types | protocol types: `BigDecimal` → `decimal`, `LocalDate` → `date`, `Instant`/`OffsetDateTime` → `datetime`, an enum → `enum` with its constants, a `List<String>` → `list` of `string` |

Only the record's components are exposed, and only exposed properties can be filtered on. An entity
column that is not on the view cannot be filtered on.

## 4. Reading

Read methods are ordinary service methods with an annotation. They can live on any bean. The
starter finds them the way Spring finds `@Scheduled` and `@EventListener` methods, so an existing
`@Service` needs no new stereotype.

### 4.1 Lookups, with the filter pushed in

```java
@Service
@Transactional(readOnly = true)
class InvoiceService {

    private final InvoiceRepository invoices;
    private final RealmJpa realmJpa;

    @RealmLookup(by = "number", maxKeys = 500)
    List<InvoiceView> byNumbers(Collection<String> numbers, Specification<Invoice> where) {
        return invoices.findAll(InvoiceSpecs.numberIn(numbers).and(where).and(InvoiceSpecs.visibleToCurrentUser()))
                .stream().map(InvoiceView::from).toList();
    }

    @RealmLookup(by = "customerId", maxKeys = 100)
    List<InvoiceView> byCustomers(Collection<Long> customerIds, Specification<Invoice> where, Sort sort, Limit perKey) {
        /* "The three earliest open invoices per customer" as one windowed query, not N queries. */
        return realmJpa.topPerKey(Invoice.class, "customer.id", customerIds,
                        where.and(InvoiceSpecs.visibleToCurrentUser()), sort, perKey)
                .stream().map(InvoiceView::from).toList();
    }
}
```

When nothing is pushed, the starter passes a `Specification` that matches everything, never `null`, so a method can always `and` it.

The second method declares, without the developer stating any of it:
- a batched lookup on `customerId`, at most 100 keys;
- every filter operator that the `Specification` translator supports for each property's type,
  with `and`, `or` and `not`;
- `exists` over each `@RealmReference` whose entity association the translator can follow;
- sorting by every exposed property that maps to an entity attribute;
- `limitPerKey`, because the method takes a `Limit` alongside its keys.

`RealmJpa.topPerKey` compiles to a `row_number()` window over the key column, which Hibernate 6
supports. A method can of course write that query itself.

### 4.2 Queries and paging

```java
@RealmQuery(maxPageSize = 200)
Window<InvoiceView> search(Specification<Invoice> where, Sort sort, Limit limit, ScrollPosition position) {
    return invoices.findBy(where.and(InvoiceSpecs.visibleToCurrentUser()),
            q -> q.sortBy(sort).limit(limit.max()).scroll(position)).map(InvoiceView::from);
}
```

Spring Data's scroll API is the protocol's paging model: `ScrollPosition` in, `Window` out. The
starter serializes the position into the opaque cursor. Keyset positions keep a long walk stable
while rows are inserted.

### 4.3 What each parameter type declares

| Parameter or return type | Pushdown declared |
|---|---|
| `Collection<K>` | a batched lookup on the `by` property |
| a single `K` | a lookup the starter loops over in-process, `maxKeys` defaulting to 50 |
| `Specification<E>` | every operator the translator supports per property type, `and`/`or`/`not`, and `exists` over mapped associations |
| `@RealmPredicate(root = Invoice.class) Predicate` | the same, through Querydsl, the way `@QuerydslPredicate` binds Spring MVC parameters |
| jOOQ `Condition` | the same, for a field map the type registers |
| MongoDB `Criteria` | the same, minus `exists` |
| a plain filter object | `eq` for each scalar field, `in` for each collection field, `between` for each `Range<T>` field; `and` only |
| `RealmFilter` | the raw protocol tree, for a source the starter cannot translate into, such as a remote API. The method declares what it accepts with `@RealmFilters(...)` and walks the tree with a visitor. |
| `Sort` | sorting by exposed properties that map to the entity |
| `Limit` on a lookup | `limitPerKey` |
| `Limit` on a query | `limit` |
| `ScrollPosition` → `Window<T>` | cursor paging |
| `Pageable` → `Page<T>` | offset paging, and `total` |
| `Pageable` → `Slice<T>` | offset paging, no `total` |
| `@RealmFields Set<String>` | `project` |
| `@RealmSearch String` | `query.search` |
| `RealmCall` | nothing. It gives the method the acting user, the idempotency key and any approval. |

The translators belong to the starter, not to the application, and the conformance kit tests them.
Every operator, null rule and `exists` is checked against the protocol's semantics. Pushdown is
therefore as exact for an application that wrote three annotations as for one that wrote a
translator by hand.

A property whose `@RealmPath` does not resolve on the entity is still returned, but it is not
declared filterable or sortable. The host evaluates those filters itself.

### 4.4 Aggregates

```java
@RealmAggregate(groupBy = {"customerId", "status"}, count = true, sum = {"amount"}, min = {"dueDate"}, max = {"dueDate"})
List<RealmGroup> totals(Specification<Invoice> where, RealmAggregation aggregation) {
    return realmJpa.aggregate(Invoice.class, where.and(InvoiceSpecs.visibleToCurrentUser()), aggregation);
}
```

Aggregates are declared explicitly. Exactness is a promise about the arithmetic, and only the
developer can make it. `RealmJpa.aggregate` builds one JPA criteria `GROUP BY` query, and a keyed
aggregate (protocol §4.4) groups by the lookup property, restricted to the keys.

## 5. Verbs and approval

```java
@Service
class RefundService {

    @RealmVerb(description = "Refund part or all of a paid invoice to the original payment method.",
               subject = InvoiceView.class,
               effect = Effect.EXTERNAL,
               idempotent = true,
               approval = @Approval(
                       required = Required.WHEN,
                       when = "amount > 500",
                       reason = "Refunds over 500 need a second person.",
                       approverAuthority = "ROLE_FINANCE_MANAGER"))
    @PreAuthorize("hasRole('ACCOUNTS')")
    @Transactional
    public RefundResult issueRefund(RefundRequest request) { ... }

    @RealmVerb(description = "Write off an invoice's outstanding balance.",
               subject = InvoiceView.class,
               effect = Effect.WRITE,
               approval = @Approval(required = Required.DECIDED, reason = "Write-offs above a customer's limit need approval."))
    @Transactional
    public WriteOffResult writeOff(WriteOffRequest request, RealmCall call) {
        var invoice = invoices.require(request.number());
        if (invoice.outstanding().compareTo(limits.writeOffLimit(invoice.customer())) > 0) {
            call.requireApproval("Over this customer's write-off limit of " + limits.writeOffLimit(invoice.customer()));
        }
        ...
    }
}
```

| `@Approval` | Protocol (§5.2) |
|---|---|
| `required = NEVER` (the default) | `"never"` |
| `required = ALWAYS` | `"always"` |
| `required = WHEN, when = "amount > 500"` | `"when"`, with the SpEL compiled into the protocol's expression grammar |
| `required = DECIDED` | `"decided"`; the method calls `call.requireApproval(reason)` before it changes anything |
| `approverAuthority` | checked by the starter against the approver's mapped principal; `APPROVER_NOT_AUTHORIZED` if absent |
| `selfApproval = true` | the acting user may approve their own call |

`when` is SpEL, as in `@PreAuthorize` and `@Cacheable(condition = ...)`, with the verb's input as
its root object. The starter accepts only the part of SpEL that translates into the protocol's
expression grammar: comparisons, `and`, `or`, `not`, `null` checks and property references. An
expression outside that part fails at startup, not at the first refund.

The starter enforces approval itself. A host that declined to collect one does not get the
operation. Before the method is invoked the starter evaluates `when`. If an approval is needed, it
verifies the `Embabel-Approval` token: signature, expiry, verb, input digest, self-approval and
approver authority. It answers `APPROVAL_REQUIRED` when the approval is missing or invalid.
`call.requireApproval` throws the same answer from inside the method, which is why it must come
before anything with an effect; under `@Transactional`, an exception thrown there rolls back
anything the method already wrote.

Idempotency keys and their first answers are kept in an `IdempotencyStore`. The default is a JDBC
table when a `DataSource` exists, and in memory otherwise.

## 6. `EmbabelRealm`: registering from code

Annotations cover types and methods known at compile time. Some applications know theirs only at
run time: custom fields per tenant, a plugin system, a catalogue of document types. Others simply
prefer configuration in code. For these, inject `EmbabelRealm`:

```java
public interface EmbabelRealm {

    /** Register a type; an annotated class contributes its annotations, which the builder can override. */
    <T> RealmTypeBuilder<T> type(Class<T> type);

    /** Register a type with no class behind it; records are maps. */
    RealmTypeBuilder<Map<String, Object>> type(String name, RealmSchema schema);

    RealmVerbBuilder verb(String name);

    /** Read the annotations on an object that is not a bean, as scanning does for beans. */
    void register(Object instance);

    void unregister(String typeOrVerbName);

    /** Record that records changed, for the changes feed. */
    RealmChanges changes();

    /** Publish events declared at run time, inside the caller's transaction. */
    RealmEvents events();

    /** The manifest as the world will see it now. */
    RealmManifest manifest();
}
```

```java
@Component
class ShipmentRealm {

    ShipmentRealm(EmbabelRealm realm, ShipmentService shipments, CustomFieldRegistry customFields) {
        realm.type(ShipmentView.class)
                .identity("trackingNumber")
                .lookup("trackingNumber", shipments::byTrackingNumbers).maxKeys(500)
                .lookup("orderId", shipments::byOrders).maxKeys(100)
                .query(shipments::search)
                .cache(RealmCache.perUser().ttl(Duration.ofMinutes(2)));

        customFields.forEachEntity(entity -> realm.type(entity.name(), entity.schema())
                .lookup(entity.idField(), (keys, fetch) -> customFields.fetch(entity, keys, fetch.where()))
                .filters(entity.filterableFields()));
    }
}
```

A lookup registered in code is a function of the keys and a `RealmFetch`, which carries the
`where`, sort, per-key limit and fields. The same parameter-type rules apply to a method reference,
so `shipments::byOrders` declares what its signature can carry, exactly as an annotated method
would. A lambda that takes the raw `RealmFetch` declares what `.filters(...)` says.

Registering or unregistering changes the manifest's `ETag`. The host sees the change the next time
it revalidates, so a tenant's new custom field reaches the world without a restart.

### 6.1 Changes

```java
@Component
class InvoiceChanges {

    private final RealmChanges changes;

    InvoiceChanges(EmbabelRealm realm) {
        this.changes = realm.changes();
    }

    @TransactionalEventListener   /* AFTER_COMMIT: a host told before commit would refetch the old row. */
    void on(InvoiceUpdated event) {
        changes.upsert(InvoiceView.class, event.number());
    }
}
```

The change log is kept in a JDBC table when a `DataSource` exists, and in memory otherwise. An
in-memory log is lost on restart. The provider then answers `410 Gone` to old cursors, and the host
drops its cache and starts again. That is slower, but never wrong.

`@RealmType(trackChanges = true)` registers a JPA post-commit listener for the type's entity. That
catches direct changes. It cannot see a change to another entity that alters this view: renaming a
customer changes every `InvoiceView` that shows the customer's name. An explicit `upsert` is the
complete answer.

### 6.2 Events

An event is an ordinary Spring application event whose class is annotated:

```java
@RealmEvent(subject = InvoiceView.class, changes = true)
@JsonClassDescription("An open invoice passed its due date unpaid.")
public record InvoiceOverdue(@RealmEventKey String number, int daysOverdue) {
}
```

```java
@Transactional
public void markOverdue(Invoice invoice) {
    invoice.markOverdue();
    events.publishEvent(new InvoiceOverdue(invoice.number(), invoice.daysOverdue()));
}
```

The application publishes it with the `ApplicationEventPublisher` it already uses. The starter
declares the event in the manifest from the record: its name, its description, its subject and a
payload schema from its components. When the event is published inside a transaction, the starter
writes it to an **outbox table in the same transaction**. The event is therefore committed exactly
when the business change is, and never for a change that rolled back. `GET /events` reads the
outbox. `changes = true` adds the subject's upsert to the event (protocol §7.2).

When Spring Modulith is on the classpath, the starter uses its event publication registry rather
than its own outbox table, so an application that already externalizes events has one record of
them, not two.

Events need durable storage, and the starter refuses to start with `@RealmEvent` types and no
`DataSource`. A lost change only costs a refetch; a lost event is something the world never hears
about.

```yaml
embabel:
  realm:
    events:
      retention: P7D
      push: true          # this application may call out to worlds that subscribe (protocol §7.3)
```

`push` is the application owner's decision. With it off, the manifest does not declare
`delivery.push`, the application makes no outbound calls, and worlds poll. With it on, the starter
serves `POST /subscriptions`, pings each callback, and delivers from the outbox with signing, retries and
backoff. One outbox feeds both polls and pushes, which is why a world can use both safely.

## 7. The acting user

The starter adds a `SecurityFilterChain` for the realm path. It authenticates the host by the
configured schemes, verifies `Embabel-Acting-User` against the configured JWKS, and maps the world
user to the application's principal through a `RealmActingUserMapper` bean:

```java
@Bean
RealmActingUserMapper actingUsers(UserDetailsService users) {
    return worldUser -> users.loadUserByUsername(worldUser.email());
}
```

That mapper is the default when a `UserDetailsService` exists. The service call runs with the mapped
`Authentication` in the `SecurityContext`, so `@PreAuthorize`, `@PostFilter` and any security
predicate inside a `Specification` see the same user they would see in the UI.

Different fields and objects for different roles — per connection, and per acting user through Jackson's `@JsonView` — are a protocol future ([§14.1](PROVIDER_PROTOCOL.md#141-who-sees-what)).

A type whose methods carry method security, or whose query consults the current user, is declared
`cache.scope: user`. A type marked `@RealmType(cache = @RealmCacheScope(SHARED))` asserts that
authorization does not vary its answer.

## 8. Alignment with the Embabel agent framework

These conventions were checked against the `embabel-agent` sources. Where the framework already has
a way of saying something, the starter says it the same way.

### 8.1 Annotations describe; Spring finds

The framework marks agent classes with `@Agent` and `@EmbabelComponent`, which are Spring
stereotypes, and `AgentMetadataReader` reads `@Action` and `@AchievesGoal` methods from them. The
realm starter keeps the same split between annotation and reader. It does **not** add a class
stereotype, because a realm method lives on a bean that already has one, usually `@Service`. The
realm annotations describe how an existing bean is exposed, the way `@Transactional` does.

### 8.2 One description for every consumer

The framework builds tool and type schemas from Jackson's `@JsonClassDescription` and
`@JsonPropertyDescription`. The starter reads the same annotations for the manifest. A view type
described once is described the same way to the application's own LLM tools and to every world
that installs it.

### 8.3 Verbs read like tools

`@RealmVerb` takes `description` and `name` with the meanings `@LlmTool` gives them, so exposing an
operation to a world's agents reads like exposing a tool to an LLM. The two are not merged. An
`@LlmTool` is offered to the application's own model, inside the application's trust boundary. A
verb is offered to another system's agents, which is why it carries `effect` and `approval` and a
tool does not. Neither annotation implies the other.

### 8.4 Programmatic registration mirrors `AgentPlatform`

`EmbabelRealm` plays the role `AgentPlatform` plays for agents. It is injected, and a component
deploys things into it. `register(Object)` corresponds to `AgentScopeBuilder.fromInstance`, which
reads an object's annotations without requiring it to be a bean. `RealmCall` is resolved by type,
as `@Provided` parameters are resolved in action methods. Applications add their own parameter
bindings through a `RealmArgumentResolver`, which follows the framework's
`ActionMethodArgumentResolver` and Spring MVC's `HandlerMethodArgumentResolver`.

An application that also uses `embabel-agent` may expose goals marked
`@AchievesGoal(export = @Export(remote = true))` as verbs, with
`embabel.realm.export-goals: true`. An agent run is long, so such a verb answers `202` with a
reference (protocol §5.2) and reports its outcome as an event (protocol §7.2). This is off by default.
Whether `remote = true` should be enough on its own is a decision for the framework, not the
starter.

## 9. Testing

```java
@SpringBootTest
@AutoConfigureRealm
@RealmConformance          /* runs the protocol conformance kit against this application */
class BillingRealmTest {

    @Autowired RealmTester realm;

    @Test
    void openInvoicesPerCustomerArePushedDown() {
        realm.fetch("Invoice").by("customerId").keys("17", "42")
                .where(eq("status", "open")).limitPerKey(3)
                .expectApplied()
                .expectRecords(r -> r.allMatch("status", "open"));
    }
}
```

`@RealmConformance` needs no fixtures. It reads the application's own manifest and data. For each
declared operator it compares the pushed result with the unfiltered fetch evaluated in the test.
It checks every declared aggregate against the same reduction over fetched rows, and every declared
approval rule against calls with and without a token. A capability that the application declares
but does not implement exactly fails the build, not a world's query.

## 10. What the developer writes, and what the world gets

| The developer writes | The world gets |
|---|---|
| a starter dependency and five lines of YAML | a provider URL to paste |
| `@RealmType` on view records | types, with descriptions, spine bindings and relationships |
| `@RealmLookup` on batched service methods | joins from anywhere in the world into the application, including identity bridging in their code |
| `Specification`, `Sort`, `Limit`, `ScrollPosition` parameters | filters, ordering, per-key limits and paging evaluated next to the data |
| `@RealmAggregate` | counts and sums computed in the database |
| `@RealmVerb` with `@Approval` | operations its agents can propose, approved by the right people and enforced by the application |
| `realm.changes().upsert(...)` | caches that are invalidated when data changes, not merely when a TTL expires |

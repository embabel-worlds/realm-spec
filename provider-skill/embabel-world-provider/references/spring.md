# Spring Boot

The Spring provider is a Java starter. The full programming model is
[PROVIDER_SPRING.md](https://github.com/embabel-worlds/realm-spec/blob/main/PROVIDER_SPRING.md); this
is the working checklist.

## Recognize the stack

`pom.xml` or `build.gradle(.kts)` with `spring-boot-starter-*`. Service classes are `@Service` beans,
usually `@Transactional`. Security is Spring Security if `spring-boot-starter-security` is present.

## Add the starter

```xml
<dependency>
  <groupId>com.embabel.realm</groupId>
  <artifactId>embabel-realm-starter</artifactId>
</dependency>
```

Requires Java 17 and Spring Boot 3.2 or later. Configure under `embabel.realm`: `name`, `title`,
`description`, `path`, `auth.schemes` and `acting-user.mode` with `jwks-uri`. Keep secrets in the
application's existing secret configuration.

## Map the plan onto the model

| Plan | Spring |
|---|---|
| type | `@RealmType(name, entity)` on the view record; `@RealmType.Id`, `.Spine`, `.Reference`, `.Path` on components |
| value | a nested record with no annotation |
| part | `@RealmType.Part List<T>`, and `@RealmType.OwnerKey` on the part |
| lookup | `@RealmLookup(by, maxKeys)` on a service method taking `Collection<K>` |
| query | `@RealmQuery` on a method taking `Specification<E>` (or Querydsl `Predicate`, jOOQ `Condition`), `Sort`, `Limit`, `ScrollPosition`, returning `Window<T>` |
| aggregate | `@RealmAggregate(groupBy, count, sum, …)` |
| verb | `@RealmVerb(effect, idempotent, dryRun)` with `@RealmVerb.Approval(required, when, reason, approverAuthority)` |
| event | `@RealmEvent(subject)` on the application event record, `@RealmEvent.Key` on its key |
| agent | `src/main/resources/embabel/agents/<name>.yml` |
| realm skill | `src/main/resources/embabel/skills/<name>/SKILL.md` |
| about | `src/main/resources/embabel/realm/ABOUT.md` |
| several realms | `embabel.realm.realms.<name>.*`, and `realm =` on types or `@RealmPackage` |

## Spring-specific pitfalls

- **Combine, never replace.** A method receiving a `Specification` must `and` it with its own rules:
  `where.and(visibleToCurrentUser())`. The starter never passes `null`.
- **Call through the proxy.** Put realm annotations on the bean's public methods. A method the bean
  calls on itself bypasses `@Transactional` and `@PreAuthorize`, which is why the starter only
  invokes methods from outside.
- **Dry runs.** The starter rolls back the transaction, but rollback cannot recall an email or a
  payment. Check `call.isDryRun()` before every external effect.
- **Fetch plans.** If a part list is expensive, take `@RealmFields Set<String>` and load the parts
  only when they are asked for, for example through an `@EntityGraph` repository method.
- **Events need a `DataSource`.** The starter refuses to start without one. With Spring Modulith, it
  uses the event publication registry.
- **Acting user.** If there is a `UserDetailsService`, the default mapper uses it. Otherwise declare a
  `RealmActingUserMapper` bean that maps the world user's email to the application's principal.

## Verify

```java
@SpringBootTest
@AutoConfigureRealm
@RealmConformance
class RealmConformanceTest { }
```

Run it with the build's test task. Then start the application and fetch the manifest from
`http://localhost:<port><path>` to read it as a world owner would.

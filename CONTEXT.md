# Embabel Realm Domain

Canonical language for portable Realms and the worlds that adopt them. This glossary defines
identity boundaries without prescribing a host implementation.

## Identity and scope

**World**:
A durable isolation boundary for data, configuration, capabilities, credentials, and execution
state. A world can outlive, move between, or change the account that owns it.
_Avoid_: tenant, user workspace, user scope

**Principal**:
The stable human or service identity whose authority an execution uses. On-demand work uses the
authenticated caller; autonomous work uses the run-as principal selected by its adoption.
_Avoid_: user when the actor may be a service; executor; owner; grant subject

**Adoption**:
A host authorization record that makes autonomous Realm work runnable under one principal. It may
record creators and approvers for audit, but they do not become runtime authorities.
_Avoid_: installation, ownership

**Execution**:
One durably admitted invocation of Realm logic, retaining the same identity across recovery and
worker attempts.
_Avoid_: worker process, execution attempt

**Realm Function**:
A named, schema-described callable supplied by a Realm and executed by a host. A Realm Function may
be pure or effectful and may be invoked on demand or through an adopted Trigger Registration.
_Avoid_: verb, operation, action

**Trigger Binding**:
A declarative entry under `handlers/` connecting a signal match, a schedule, or both to executable
logic. Its target may be an inline TypeScript Handler or a Realm Function.
_Avoid_: verb binding, event handler

**Manifest Schedule**:
A schedule declared directly on a Realm Function's manifest entry. It is a Trigger Registration,
but not a Trigger Binding, and invokes the Function with empty arguments.
_Avoid_: scheduled binding, handler schedule

**Trigger Registration**:
The adopted identity of an autonomous trigger: either a Trigger Binding or a Manifest Schedule.
Adoption authorizes it to execute as exactly one principal.
_Avoid_: trigger when referring to the durable registration

**Handler**:
Code that implements a Realm Function or the inline TypeScript body of a Trigger Binding. A Handler
is an implementation, not the declared callable or trigger rule.
_Avoid_: Realm Function, Trigger Binding

**Knowledge Context**:
A named confidentiality boundary for knowledge or memory within one world. Its identity and access
policy are subordinate to the world and cannot authorize access across worlds.
_Avoid_: world, user context

**World Incarnation**:
The exclusively active runtime epoch of one durable world. A new incarnation fences stale execution
after restore, migration, or administrative transfer without changing the world's identity.
_Avoid_: world version, cloned world

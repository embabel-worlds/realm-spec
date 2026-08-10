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

**Knowledge Context**:
A named confidentiality boundary for knowledge or memory within one world. Its identity and access
policy are subordinate to the world and cannot authorize access across worlds.
_Avoid_: world, user context

**World Incarnation**:
The exclusively active runtime epoch of one durable world. A new incarnation fences stale execution
after restore, migration, or administrative transfer without changing the world's identity.
_Avoid_: world version, cloned world

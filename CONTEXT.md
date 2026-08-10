# Embabel Realm Domain

Canonical language for portable Realms and the worlds that adopt them. This glossary defines
identity boundaries without prescribing a host implementation.

## Identity and scope

**World**:
A durable isolation boundary for data, configuration, capabilities, credentials, and execution
state. A world can outlive, move between, or change the account that owns it.
_Avoid_: tenant, user workspace, user scope

**Principal**:
An authenticated human or service identity that can act in a world. A principal may act in several
worlds, and a world may admit several principals.
_Avoid_: user when the actor may be a service; owner when describing the current actor

**Owner**:
The account with administrative and lifecycle authority over a world. Ownership governs the
boundary but does not define or replace it.
_Avoid_: tenant, principal, world user

**Grant Subject**:
The principal whose authority an adopted trigger uses when it runs without a live caller. An inbound
sender is event data, never the grant subject.
_Avoid_: sender, triggering user, realm owner

**Knowledge Context**:
A named confidentiality boundary for knowledge or memory within one world. Its identity and access
policy are subordinate to the world and cannot authorize access across worlds.
_Avoid_: world, user context

**World Incarnation**:
The exclusively active runtime epoch of one durable world. A new incarnation fences stale execution
after restore, migration, or ownership transfer without changing the world's identity.
_Avoid_: world version, cloned world

**User ID**:
A host-specific identifier for a human account. It may identify a principal or owner but never a
world or a portable Realm scope.
_Avoid_: using `userId` as an alias for `worldId`

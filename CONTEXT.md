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

**App Link**:
A link that opens a Realm's app at a place inside it: `app://<scope>/<name>#<route>`. The address is the
app's own, so it cannot collide; the route is the app's to interpret and is untrusted input. The scope `host` is
reserved for the host's own places, whose names each host defines.
_Avoid_: URL scheme, deep link when meaning this contract

**Key Entry**:
A key a Realm declares it needs in `keys.yml`: a name, one or more fields each stored under a credential
variable, and optionally how the host checks a value. It is set once for the host and found by variable
name. The realm names the check; the host makes it, and realm code never sees a value.
_Avoid_: secret, config entry, API key when meaning the declaration rather than the value

**Credential**:
A secret a Realm declares it needs in `credentials.yml`: an id, a kind, and what it is for. An API entry
or channel names it by id. The owner connects it to a key in their wallet for one installation of the
Realm, and nothing is connected at install. The realm never names a wallet item or carries a value.
_Avoid_: Key Entry when meaning a host-wide key found by variable name, secret

**Knowledge Context**:
A named confidentiality boundary for knowledge or memory within one world. Its identity and access
policy are subordinate to the world and cannot authorize access across worlds.
_Avoid_: world, user context

**World Incarnation**:
The exclusively active runtime epoch of one durable world. A new incarnation fences stale execution
after restore, migration, or administrative transfer without changing the world's identity.
_Avoid_: world version, cloned world

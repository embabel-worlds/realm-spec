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

**Agent**:
A named colleague: a job, the routines that do its work, and the duties it keeps. A Realm proposes
agents under `agents/`; a world adopts one by putting it on duty, and decides who answers for it.
_Avoid_: bot, assistant, handler

**Sponsor**:
The person who answers for an agent in a world. Set by the world, never by a Realm. A sponsor signs
each version the agent runs.
_Avoid_: owner when meaning the one accountable person

**Stage**:
Whether an agent's routines run, and whether they may take effects: off duty (`off`), on duty
observing (`observing`, read-only gateway), or on duty (`on`). Set by the world, per agent or per
routine.
_Avoid_: autonomous, enabled, armed

**Routine**:
A declarative entry in an agent connecting a signal match, a schedule, or both to executable logic.
Its target may be an inline TypeScript Handler or a Realm Function.
_Avoid_: Trigger Binding, verb binding, event handler

**Duty**:
A condition an agent keeps true, named by the view, lens or DERIVE label that should hold.
_Avoid_: invariant in user-facing text, standing order, rule

**Manifest Schedule**:
A schedule declared directly on a Realm Function's manifest entry. It is a Trigger Registration,
but not a Routine, and invokes the Function with empty arguments. A host presents it as a routine of
an agent it proposes for the Realm, so it is adopted the same way.
_Avoid_: scheduled binding, handler schedule

**Trigger Registration**:
The adopted identity of an autonomous trigger: either a Routine or a Manifest Schedule.
Adoption authorizes it to execute as exactly one principal.
_Avoid_: trigger when referring to the durable registration

**Handler**:
Code that implements a Realm Function or the inline TypeScript body of a Routine. A Handler
is an implementation, not the declared callable or trigger rule.
_Avoid_: Realm Function, Routine

**App Link**:
A link that opens a Realm's app at a place inside it: `app://<scope>/<name>#<route>`. The address is the
app's own, so it cannot collide; the route is the app's to interpret and is untrusted input. The scope `host` is
reserved for the host's own places, whose names each host defines.
_Avoid_: URL scheme, deep link when meaning this contract

**Key Entry**:
A credential a Realm declares it needs: a name, one or more fields each stored under a credential
variable, and optionally how the host checks a value. The realm names the check; the host makes it,
and realm code never sees a value. A conventional Realm declares Key Entries in `keys.yml`; a
captured Realm uses Declared Credentials.
_Avoid_: secret, config entry, API key when meaning the declaration rather than the value

**Declared Credential**:
A credential a captured Realm declares it needs, by purpose: kind, provider, description and docs
link. It never names a variable or says where the secret lives. The recommended way for a new
Realm to ask for a secret.
_Avoid_: Key Entry, secret, token-env

**Credential Binding**:
The owner's choice of wallet item for one Declared Credential, made when approving the Realm. The
host reads that item and puts it on the wire itself; an approved API operation stays pinned to
the value it was approved with.
_Avoid_: key value, secret reference

**Knowledge Context**:
A named confidentiality boundary for knowledge or memory within one world. Its identity and access
policy are subordinate to the world and cannot authorize access across worlds.
_Avoid_: world, user context

**World Incarnation**:
The exclusively active runtime epoch of one durable world. A new incarnation fences stale execution
after restore, migration, or administrative transfer without changing the world's identity.
_Avoid_: world version, cloned world


## Channels

**Channel**:
A general data pipe carrying provider messages, webhook events, database changes or
Realm-produced events. A conversational provider connection is one channel adapter.

**Channel Source**:
An approved producer identity and stream within a World. Realm sources retain their
installation, artifact digest, source name and source-grant revision. Host provider sources
retain their provider registration and revision.

**Source Grant Revision**:
A host-assigned revision identifying one active source approval. Unrelated handler or consumer
approvals preserve it. Source removal/reapproval, artifact change and reinstall invalidate it.
It does not replace an invocation's retained approval revision.

**Channel Consumer**:
An independently approved reader of one exact source, with a durable cursor. A Realm consumer
maps its name to a captured handler and also requires handler approval.

**Journal Receipt**:
Confirmation that an event append is durable under the host's storage contract. It does not
confirm completion of consumer processing or external effects.

**Consumer Checkpoint**:
A durable position advanced after an offered record prefix succeeds under current admission.
An uncheckpointed offer may be replayed, so effects need stable idempotency keys. Records that
every adopted consumer has checkpointed past may be reclaimed by the host.

---
name: embabel-world-provider
description: Expose this application to Embabel worlds as a realm, through the World Provider Protocol and this stack's provider library. Survey the service layer, agree with the developer what the world may see, add the library, declare types, lookups, verbs with approvals, events and skills, and pass the conformance kit. Activate when the user wants their application to appear in an Embabel world, asks to "add Embabel", "expose this to worlds", "make this app a realm", or wants Embabel agents to query or act on this application's data.
---

# Exposing an application to Embabel worlds

The application becomes a **provider**: it serves a manifest and a few HTTP operations, and any
Embabel world given its URL installs it as a realm. The world sees exactly what this application
declares, through the same layer its own UI uses, with the same authorization. The contract is the
[World Provider Protocol](https://github.com/embabel-worlds/realm-spec/blob/main/PROVIDER_PROTOCOL.md).
How this stack meets it is in `references/`. Read the reference for this stack before writing code.

## Hard rules

1. **Expose through the service layer, never the repositories or the database.** Transactions,
   authorization, invariants and audit live in the service layer. A provider that bypasses them is
   a back door. If a needed operation exists only in a controller or a repository, add a service
   method for it.
2. **Expose views, not entities.** A realm type is the shape the service layer returns, usually an
   existing DTO. Never expose a persistence entity directly.
3. **Expose less by default.** Propose what to expose and get the developer's agreement before
   annotating anything. What the world sees is the application owner's decision, not yours.
4. **Every filterable property is a returned property.** Never declare a filter on a value the type
   does not expose, because filtering on a hidden value reveals it.
5. **Classify every verb honestly**: `read`, `write`, or `external` (an effect that cannot be taken
   back, such as an email, a payment or a call to another system). Money, anything
   customer-facing and anything irreversible gets an approval rule. Ask the developer what the
   business rule is. Do not invent thresholds.
6. **Reuse the application's identity and authorization.** Map the world's acting user onto the
   application's existing principal. Do not add a parallel permission model, and do not widen
   anyone's access.
7. **No credentials in committed files.** The host's credential and any secrets come from the
   application's existing secret configuration.
8. **Push delivery means outbound calls.** Enable it only if the developer confirms the application
   may call out to worlds. Polling works without it.
9. **Never weaken the conformance kit to pass.** A failure means a declared capability is not
   implemented exactly. Fix the code, or stop declaring the capability.

## Workflow

### 1. Survey (read only)

- Identify the stack from the build files, and open the matching `references/<stack>.md`. If there is
  none, stop and say this stack has no provider library yet. The protocol is plain HTTP and JSON, and
  a hand-written provider is possible, but that is the developer's call.
- Find the service layer, the domain aggregates and the existing view types or DTOs.
- Find how the current user is established (session, token, security context), and how
  authorization is expressed.
- Find side effects: email, payments, messaging, calls to other systems.
- Find existing domain events, and whether they are published after commit.
- Find identities other systems share: email addresses (`Person`), company websites or domains
  (`Organization`), and business keys such as SKUs or account numbers. These become **spine**
  bindings, which let the world join this application to everything else.

### 2. Propose an exposure plan, and wait for agreement

Present one table per section and ask the developer to confirm or trim it:

| Section | For each item |
|---|---|
| **Types** | view class, identity, properties, spine bindings, references, values and parts (protocol §3.5) |
| **Lookups** | the property, the existing batch method or the one to add, and `maxKeys` |
| **Queries** | which types can be listed, the filterable properties and operators, sorting, paging |
| **Aggregates** | only reductions the developer confirms are exact |
| **Verbs** | the service method, its effect, its approval rule and reason, whether it supports a dry run |
| **Events** | the domain events worth reacting to, with their subject type |
| **Agents** | only if the developer asks: proposed agents whose routines call verbs (protocol §5.3) |
| **Realms** | one, or several for distinct modules or audiences (protocol §3.6) |
| **Cache** | per type: `user` unless the developer confirms that authorization never varies the answer |

Flag anything you could not determine rather than guessing it.

### 3. Implement

Follow `references/<stack>.md`. In general:

- Add the provider library and its configuration: realm name, title, description, path, auth
  schemes and acting-user mode.
- Annotate or register the view types. Add batch lookup methods where only single-record methods
  exist, using the data layer's own batch call (an `IN` query), not a loop, where that is cheap.
- Give read methods the most expressive filter parameter the stack's library supports. That is
  what maximizes pushdown, and the library declares the capability from the signature.
- Add verbs with their approval rules. Before any external effect, check for a dry run, and require
  approval for `decided` verbs.
- Publish events after commit, through the library's outbox.
- Write the realm's `about` document and at least one **realm skill** for the world's agents
  (protocol §3.7). That skill explains how to use this application well: which verb to use when,
  what the business terms mean, and when approval will be needed. Name verbs and types exactly as
  the manifest does.

### 4. Verify

- Start the application and fetch the manifest. Read it as a world owner would: is anything there
  that should not be? Is anything missing that was agreed?
- Run the conformance kit as the stack's reference describes, and fix every failure.
- Exercise one lookup with a filter, one query with paging, one dry run, and one verb that needs
  approval, both without a token and with one.

### 5. Hand over

Tell the developer:
- the provider URL, or the index URL if there are several realms;
- what a world owner does: paste the URL and supply the host credential;
- how to issue that credential;
- a summary of what is exposed, and what was deliberately left out;
- the approval rules, in the business's words;
- anything inert, such as a spine binding the target world may not have.

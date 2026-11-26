# Realm requirements

**Spec version: 0.3.0**

Status: proposed. No host is required to implement this yet.

A realm may need another realm: its views read labels the other realm owns, or its handlers call the
other realm through the gateway. `requires` states that need, with the versions the author has made
it work with. A host resolves one version of each required realm per world, shows the owner the whole
plan before it installs anything, and reports a missing or incompatible realm when the realm is
installed and when it loads, before anything runs.

The model is Maven's: a requirement is a recommended version or a hard range in Maven's bracket
notation, requirements are followed transitively, and a world holds one version of each realm.
Versions themselves are ordered the way npm orders them, by Semantic Versioning (see
[Version order](#version-order)).

A realm can also say which versions of its host it needs, with `requiresHost` (see
[Host requirements](#host-requirements)).

A requirement grants nothing. It does not import another realm's source, module bytes, credentials,
handlers or grants. [Graph composition](LABELS_AND_COMPOSITION.md) and gateway calls work as before;
`requires` only says which realms must be present for them to mean anything.

## How requires fits with what exists

- **Module dependencies.** A [dependency](TYPESCRIPT_REALMS.md#dependencies) names WebAssembly bytes
  by exact version and digest and takes no range. Nothing here changes that, and a requirement never
  brings module bytes with it.
- **`layers`.** A layer (`"name@version"`) is a different thing: a request to build on another realm's
  definitions, which the reference profiles refuse as `LAYERS_REFUSED`. A requirement does not layer
  one realm on another, and declaring `requires` does not make `layers` work. A realm that only needs
  another realm present at a compatible version uses `requires`.
- **The reserved `from: { realm: ... }` dependency source.** It stays reserved and refused. When it is
  specified, the realm it names will be taken from `requires`, so the version comes from resolution and
  is not written twice.
- **Optional labels.** [Optional labels](README.md#optional-labels--reading-a-companion-realm-that-may-be-absent)
  cover a companion realm that may be absent. A required realm must be present.
- **An older host.** A host that does not implement this document treats `requires` as an unknown
  metadata field: it ignores it, notes the unknown field the way it notes any other, and loads the realm
  as if it declared no requirements. Nothing is held back and nothing extra is installed. An author who
  depends on `requires` being enforced must target a host that implements it.

## Declaring

`requires` is realm metadata. Each key is the required realm's `name` as its own metadata declares
it. Each value is a version requirement.

```typescript
import type { Realm } from '@embabel/realm-types'

export default {
  name: 'sales-pipeline',
  version: '1.4.0',
  requires: {
    'crm-core': '[2.0.0,3.0.0)', // any 2.x
    calendar: '[1.3.0,)',        // 1.3.0 or newer
    'currency-rates': '0.9.2',   // recommended, any version accepted
  },
} satisfies Realm
```

A realm with no `requires` behaves exactly as it did before this document.

- A key is a realm name, and realm names and `requires` keys share one syntax: kebab-case (lower-case
  letters, digits and hyphens, starting with a letter or digit), at most 64 characters. That leaves no
  room for a path separator, whitespace or a control character. A key of any other form is a malformed
  entry.
- A realm that requires itself has a malformed entry.
- A value that is not a valid requirement is a malformed entry.
- A malformed entry is a warning on the realm (`REALM_REQUIREMENT_MALFORMED`). That one entry is left
  out and the realm is not held back for it (see [At load](#at-load)). An SDK may refuse to build a
  realm with a malformed entry; that is stricter than a host and allowed.
- A `requires` that is not a record of realm names is ignored with a warning.
- A requirement names a realm and never a location. The host finds required realms in the realm
  sources its operator configured, so a realm cannot point the host at a repository of its choosing.

## Version requirements

```
requirement = soft / hard
soft        = version
hard        = set *( "," set )
set         = "[" exact "]"
            / ( "[" / "(" ) bound "," bound ( "]" / ")" )
            / ( "[" / "(" ) bound "," ")"        ; no upper bound
            / "(" "," bound ( "]" / ")" )        ; no lower bound
exact       = number "." number "." number [ "-" prerelease ]
bound       = number [ "." number [ "." number ] ] [ "-" prerelease ]
version     = exact [ "+" build ]
number      = "0" / ( %x31-39 *8DIGIT )          ; no leading zero, at most 9 digits
prerelease  = identifier *( "." identifier )
identifier  = number / 1*( ALPHA / DIGIT / "-" )  ; one that is all digits is a number
build       = 1*( ALPHA / DIGIT / "-" ) *( "." 1*( ALPHA / DIGIT / "-" ) )
```

A version is a [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) version with each
number limited to 9 digits. A number with a leading zero, such as `01` in `1.01.0` or `1.0.0-01`, is
not a version. An identifier is never empty, so `1.0.0-rc.` and `1.0.0-rc..1` are not versions.

- The exact set `[v]` names a whole version: all three numbers and no `+build`. `[2.0.0]` is
  accepted; `[2]`, `[2.1]` and `[2.0.0+build]` are refused.
- An interval has at least one bound, and no bound has a `+build`. A bound in an interval with fewer
  than three numbers is completed with zeros, so `[2,3)` means `[2.0.0,3.0.0)`.
- An end with no bound is always open, written with `(` or `)`: `(,2.0.0)` and `[1.3.0,)` are
  accepted, `[,2.0.0)` and `[1.3.0,]` are refused.
- No whitespace is allowed anywhere.

| Requirement | Accepts |
| --- | --- |
| `2.4.0` | Soft. Recommends 2.4.0 and accepts any version. |
| `[2.4.0]` | Exactly 2.4.0. |
| `[2.0.0,3.0.0)` | 2.0.0 up to, not including, 3.0.0. |
| `[1.3.0,)` | 1.3.0 or newer. |
| `(,2.0.0)` | Anything older than 2.0.0. |
| `(,1.0.0],[1.2.0,)` | 1.0.0 or older, or 1.2.0 or newer. Excludes the versions between. |

A **soft** requirement is a recommendation. It never causes a conflict and any installed version
satisfies it, including a realm whose version cannot be read. It still needs the realm to be
installed: a soft requirement on a realm that is absent is not met. A **hard** requirement must hold,
and a realm whose version cannot be read cannot meet it.

An exclusive upper bound that is a release also leaves out the pre-releases of itself, so
`[2.0.0,3.0.0)` does not accept `3.0.0-rc.1`. An upper bound that is itself a pre-release does not:
`(,3.0.0-rc.2)` accepts `3.0.0-rc.1`.

**A set that accepts no version is malformed.** Pre-releases count as versions here, so a set is
malformed only when no release and no pre-release falls inside it. That includes bounds that cross,
such as `[3.0.0,2.0.0]`; equal bounds where one is exclusive, such as `[2.0.0,2.0.0)`; neighbouring
releases with both ends exclusive, such as `(1.0.0,1.0.1)`; a pre-release low bound under an excluded
upper bound of the same three numbers, such as `[3.0.0-rc.1,3.0.0)`; a set below the oldest version
there is, such as `(,0.0.0)` and `(,0.0.0-0)` (`0.0.0-0` is the oldest version); and exclusive bounds
with nothing between them, such as `(1.0.0,1.0.1-0)` and `(1.0.0-rc.1,1.0.0-rc.1.0)`. Only a
version within the limits below counts, so a number never passes 9 digits: the first version after
`1.0.999999999` is `1.1.0-0`, which makes `(1.0.999999999,1.1.0-0)` and `(1.0.999999999,1.1.0)`
malformed, and nothing comes after `999999999.999999999.999999999`, which makes
`(999999999.999999999.999999999,)` malformed. A version is never longer than 64 characters either,
so when one more identifier does not fit, the next version steps an identifier instead: after
`1.0.0-` and 58 `a`s comes `1.0.0-` with 57 `a`s and a `b`, and nothing between those two bounds
is a version. Two requirements of different realms whose sets share no version are a conflict by the
same rule, counting the pre-releases an excluded release leaves out: `[1.0.0,2.0.0)` and
`[2.0.0-rc.1,2.0.0-rc.2]` conflict.

### Limits

These limits hold for every host and SDK, so the same text is accepted or refused everywhere.

| Input | Limit |
| --- | --- |
| A requirement's text | at most 256 characters |
| Sets in one hard requirement | at most 16 |
| A version's text, including any `+build` | at most 64 characters; a bound that leaves numbers off counts with each missing number written as `.0`, so `1-` and 61 more characters is too long |
| A number, in the three numbers or a pre-release identifier | at most 9 digits |
| A realm name or `requires` key | at most 64 characters |

Past a limit, the entry is malformed.

### Other notations

Other notations are malformed, and the warning names the bracket form that says the same thing:

| Written | Answered with |
| --- | --- |
| `^2.0.0` | `[2.0.0,3.0.0)` |
| `^0.2.3` | `[0.2.3,0.3.0)` |
| `~2.4.0` | `[2.4.0,2.5.0)` |
| `2.x` | `[2.0.0,3.0.0)` |
| `>=1.3.0` | `[1.3.0,)` |
| `>1` | `[2.0.0,)` |
| `<=2` | `(,3.0.0)` |

A short form is read the way npm reads it, by the number of parts written, so `>1` means anything
from 2.0.0 and is answered with `[2.0.0,)`. A value that contains whitespace, `latest`, a bare `*`,
a Git ref or a URL has no equivalent and is answered with the grammar.

### Version order

Versions are ordered by Semantic Versioning 2.0.0 precedence. This is the order npm uses. It is not
Maven's `ComparableVersion` order, even though the range notation is Maven's: there are no special
qualifier words such as `alpha`, `milestone` or `sp`, and a qualifier is not a release.

1. Compare the three numbers in order, as numbers. `2.10.0` is newer than `2.9.0`.
2. A version with a pre-release is older than the same three numbers without one:
   `2.0.0-rc.1` is older than `2.0.0`.
3. Two pre-releases compare identifier by identifier, left to right, until one differs. Two numeric
   identifiers compare as numbers, so `beta.2` is older than `beta.11`. Two other identifiers compare
   by ASCII, so `alpha` is older than `beta` and `RC` is older than `rc`. A numeric identifier is older
   than any other, so `rc.2` is older than `rc.a`. When one list runs out with every identifier equal,
   the shorter is older: `alpha` is older than `alpha.1`.
4. `+build` is ignored.

Since leading zeros are refused, two versions with the same precedence differ only in `+build`. This
is a total order: any two versions compare one way, and no three versions can each be older than the
next around a circle.

### Conformance fixtures

[`fixtures/requires/ranges.json`](fixtures/requires/ranges.json) holds the cases every host and SDK
must agree on: requirements that are accepted, each with its parsed sets; requirements that are
refused, each with a reason and, for an npm form, the bracket form to suggest; valid and invalid
versions; and versions listed oldest first in the order above. It includes each limit at its edge and
one past it. A host or SDK copies the file and tests that its copy is byte-equal to the published one,
so the copies cannot drift. A refused case must be refused; the reason says why and need not be
reported with the same word.

## Published versions

Resolution chooses among the versions a realm source publishes.

- **Tags.** A Git source publishes one version per tag named `v` followed by a version, such as
  `v2.4.1` or `v3.0.0-rc.1`, when the realm metadata at that tag declares the same version. This is
  the rule Go modules use. Every other tag is ignored, including a tag without the `v` (`2.4.1`), a tag
  that is not a version (`v2.4`, `release-2`) and a tag whose metadata declares a different version.
  When two tags name versions of the same precedence (they differ only after `+`), the one whose tag
  name sorts first by ASCII is published and the other is ignored.
- **No tags.** A source with no such tags publishes exactly one version: the one its metadata declares
  at the ref it is installed from. Tags named like versions whose metadata declares another version
  are not such tags, so a source whose only `v` tags all disagree with their metadata publishes the
  version at its ref.
- **A version that cannot be read.** Metadata whose version is not a version publishes nothing at that
  tag or ref. A host never takes it for `0.0.0` or any other version.
- **A local directory.** A realm installed from a local directory publishes the one version its
  metadata declares, and counts at that version in every plan and every load.
- **The right realm.** A source is the publisher of a required realm only when the metadata it holds
  declares that realm's name. A source that declares another name publishes nothing for it.
- **A bounded read.** A host reads a bounded number of a source's newest tags. A satisfying version
  older than that bound may be missed, and the requirement is then reported as not met.
- **An index source** may list versions explicitly. Its entry format is not specified here.

A published version does not change. If the content behind an installed version differs from what
the host recorded at install, the host reports the difference with a warning (see
[The lock](#the-lock)); it does not adopt the new content silently.

## Resolution

A host resolves per world, over every installed realm plus the change asked for. Requirements are
followed transitively: a required realm's own `requires` count.

**Identity is name plus source.** A realm is the realm of that name from that source. When the world
already holds a realm of the required name, that installed realm is the one meant, whichever source it
came from. When it does not, and two of the configured sources each publish a realm of that name, the
install is refused naming both sources: the host does not choose between publishers on the owner's
behalf. Two spellings of one repository are one source: a repository is its host, compared without
regard to case, its port unless that is the scheme's default (22 for `ssh:`, 443 for `https:`), and its
path. The scheme, a login or password, a default port, a query, a trailing `/` and a final `.git` do not
count, so `git@github.com:acme/crm.git` and `https://github.com/acme/crm` are one source, while
`https://github.com/acme/crm2`, and one host on two other ports, are two.

For each required realm:

1. Take the hard requirements of every realm that requires it. With none, every version is acceptable.
2. **Installed stays.** If the realm is installed at a version that satisfies every one of them, keep
   it. An installed realm is never changed to a newer version merely because one exists.
3. **Otherwise newest.** Choose among the published versions that satisfy every hard requirement: a
   soft recommendation that is one of them, the highest such if several realms recommend, or else the
   newest of them by [the version order](#version-order).
4. **Pre-releases are opt-in.** A pre-release is chosen only when a requirement on that realm names a
   pre-release of the same three numbers, as a bound or as a recommendation. `[2.0.0-rc.1,3.0.0)` can
   choose `2.0.0-rc.2` but never `2.1.0-beta.1`. This is npm's rule. A pre-release the owner installed
   still satisfies a requirement by the order above and stays.
5. **A version that undoes itself is passed over.** When a version chosen for a realm brings in
   requirements that refuse that same version, it is not chosen again in that plan while another
   version satisfies every hard requirement. If `crm` 2.0.0 requires `audit`, and `audit` requires
   `crm` `[1.0.0]`, a plan that only recommends `crm` 2.0.0 takes `crm` 1.0.0 without `audit`. This is
   the only choice a plan reconsiders; one that would need any other combination is a conflict.
6. If no version can satisfy every hard requirement, there is a **conflict**. If some version could
   but none is published, the requirement is **unsatisfied**.

The same installed realms and the same published versions always give the same plan. The order in
which realms were installed or declared does not matter.

**Bounds on needs of needs.** A plan follows requirements at most 8 realms deep, counting the realm
asked for as the first, and holds at most 64 realms. A requirement already met by an installed realm
is not followed further. Past either bound the install is refused, and the sentence names the chain it
was following.

**Cycles.** Requirements that lead back to a realm already on the chain are a cycle. At install the
change is refused naming the chain; at load each realm in the cycle is held back with
`REALM_REQUIREMENT_CYCLE`, and its sentence names the realms in order, starting and ending with
itself.

### At install

Before anything changes, the host computes a plan over the installed realms, the published versions
and the change asked for: an install, an update or a removal.

- **Nothing to change.** When every requirement is already met and no installed realm depends on the
  change, it goes on as it would for a realm with no requirements.
- **The plan adds, moves or holds back other realms.** Nothing happens yet. The host answers
  `409 Conflict` with the code `REALM_CONFIRMATION_REQUIRED`, the plan as a sentence, the plan as data
  and a `planId` (see [The plan reply](#the-plan-reply)).
- **Unmet requirements refuse the change.** If any requirement cannot be met, nothing changes and the
  host answers `409 Conflict` with the code `REALM_REQUIREMENTS_UNMET` (see
  [Install refusals](#install-refusals)).
- **A confirmed plan installs exactly what was planned.** Each version is installed at the commit the
  plan read it at. A plan step installs a tag as its `v<version>` tag, even when a branch has the same
  name. If a repository has moved since, the change is refused before anything is saved and the owner
  is asked again.
- **All or nothing.** If a step fails, the steps before it are undone and the world is as it was (see
  [Changes are all or nothing](#changes-are-all-or-nothing)).

A realm installed from a local directory is planned at the version and with the requirements it
declares. Switching an installed realm to a local checkout is an update. The owner confirms any
other realms the switch would install, update or hold back. The confirmation covers the checkout
contents read by the plan. If they change before the host loads the checkout, the host refuses
the change with `REALM_REQUIREMENTS_UNMET`, undoes any dependency steps and asks the owner to
request a fresh plan. If those contents change between showing the plan and confirming it, the
host returns the new plan for confirmation.

With no ref given, the realm asked for is planned and installed at the branch the repository's HEAD
names. A commit ref that the repository will not serve by id is refused with a sentence that asks for
a tag or branch. A commit ref is planned from that commit and no other: when the repository serves a
different commit by the time it is read, such as a branch that moved, the install is refused and
nothing is installed; the sentence asks the owner to install or update again, or to give a tag. In a world where no realm has `requires`, and no earlier update in the same
request brought one in, a repository that cannot be read does not
stop an install that would go on without a plan, since nothing it does can hold an installed realm
back. A requirement that is already met costs no lookup, so an unreachable source for it does not
refuse an unrelated install.

### The plan reply

```json
{
  "status": "needs-confirmation",
  "code": "REALM_CONFIRMATION_REQUIRED",
  "name": "sales-pipeline",
  "message": "Installing sales-pipeline 1.4.0 also updates crm-core from 1.9.0 to 2.4.1 from https://github.com/example/realm-crm-core, which sales-pipeline requires ([2.0.0,3.0.0)).",
  "planId": "sha256:5d1c0b6f2e9a8d7c4b3a29180f6e5d4c3b2a1908f7e6d5c4b3a2918070f6e5d4",
  "plan": [
    {
      "name": "crm-core",
      "version": "2.4.1",
      "installed": "1.9.0",
      "repository": "https://github.com/example/realm-crm-core",
      "stability": "stable",
      "action": "update",
      "requiredBy": ["sales-pipeline"]
    },
    {
      "name": "sales-pipeline",
      "version": "1.4.0",
      "repository": "https://github.com/example/realm-sales-pipeline",
      "stability": "stable",
      "action": "install"
    }
  ]
}
```

| Field | Rule |
| --- | --- |
| `status` | `needs-confirmation`. |
| `code` | `REALM_CONFIRMATION_REQUIRED`. |
| `name` | The realm the owner asked to change. |
| `message` | The plan in sentences, starting from what the owner asked for. When a step is experimental, it says so, because confirming the plan is the only question the owner is asked. |
| `planId` | An opaque identifier of this plan: a digest over at least every step's name, version, commit and action. A host may digest more of the plan, such as each step's repository and stability, so two host implementations need not give one plan the same id. The same plan always has the same id from one implementation, across restarts and instances, and a plan that differs in any of those has a different one. |
| `plan` | The steps, in the order they will be applied. |
| `plan[].name` | The realm the step changes. |
| `plan[].version` | The version it will be at after the step. For `remove`, the version being removed; for `hold-back`, its installed version. |
| `plan[].installed` | The version installed now. Absent for `install`. |
| `plan[].repository` | Where the version comes from, in the [normalised form](#the-lock). Absent for a realm from a local directory and for `hold-back`. |
| `plan[].stability` | `experimental` when the realm's author calls it experimental, `stable` otherwise. |
| `plan[].action` | `install`, `update`, `remove` or `hold-back`. |
| `plan[].requiredBy` | The realms whose requirements bring this step in. Absent for the realm asked for. |
| `heldBackNotListed` | In a removal or update plan, the number of realms that would be held back beyond the 64 `hold-back` steps listed. Absent when every one is listed. The `planId` covers this count, so a change in it is a different plan. |

**Confirming.** The owner confirms by repeating the same request with the `planId` it was shown. The
host plans again from scratch and keeps no memory of plans it has shown, so a restart, or another
instance of the host, answers the same. If the new plan has the same id, the host carries it out. If it
differs in any step (a tag or branch that moved, a new release, a realm installed meanwhile, a
changed experimental flag), the host answers a new `REALM_CONFIRMATION_REQUIRED` whose message starts
`The plan changed since it was shown.`, and nothing changes. This holds when the change no longer needs
a plan at all, for instance because a realm the plan would have installed was installed meanwhile: the
new plan has the requested realm's step alone, its message says so
(`The plan changed since it was shown. Installing sales-pipeline 1.4.0 changes no other realm.`), and
its `planId` confirms it. A request with no `planId` is answered with the plan, or, when nothing else
changes, goes ahead with none. Cancelling is not answering: a plan that is never confirmed changes nothing, and the
world, its realm list and its lock stay byte for byte as they were.

**Only the owner confirms.** A conversational assistant never sends a `planId`: a chat message can
come from someone other than the owner, so chat answers with the plan in words and points the owner to
where it can be confirmed.

**Removal and update plans.** Removing a realm that another installed realm requires, or updating it
to a version outside another realm's hard requirement or to a version that cannot be read, is planned
the same way. The plan has a
`remove` or `update` step for the realm, and a `hold-back` step for each installed realm that would
be held back by it, however long the chain, including any that are held back already. The message
names them:

`Removing crm-core holds back sales-pipeline and reports, which require it.`

`Updating crm-core from 2.4.1 to 3.0.0 holds back sales-pipeline, which requires [2.0.0,3.0.0).`

At most 64 `hold-back` steps are listed. Past that, `heldBackNotListed` counts the rest and the
message ends `... and <N> more realms`.

Once confirmed, the change happens and those realms are held back with their reasons. Removing or
updating a realm that no installed realm requires needs no plan and gives no `409`.

An update whose new version needs other realms installed or moved is planned as an install is: an
`install` or `update` step for each of them, then the realm's own `update` step, then any `hold-back`
steps. The message starts from the update:

`Updating sales-pipeline from 1.4.0 to 1.5.0 also installs crm-reports 1.0.0 from https://github.com/example/realm-crm-reports, which sales-pipeline requires ([1.0.0,2.0.0)).`

Two updates are refused rather than planned, and nothing changes:

- A new version that declares another name. A realm keeps its name from one version to the next, so
  the owner installs the new realm on its own instead:
  `The repository of <realm> now holds a realm named <other>, and a realm keeps its name from one version to the next, so <realm> was not updated. Install <other> as a realm of its own if you want it.`
- A new version that requires a realm the update would hold back, directly or through a realm the
  plan brings in. That realm needs the updated realm, so the two would require each other, and both
  would be held back. Moving the held realm to another range does not help while it still needs the
  updated realm, so the sentence names the two levers that do:
  `<realm> <version> requires <held>, which itself needs <realm>, so updating <realm> would hold back both. Two realms cannot require each other. Publish a version of <held> that no longer needs <realm>, or a version of <realm> that no longer requires <held>, then update <realm> again.`

**Updating several realms at once.** Each realm is planned against the world as the updates before it
in the same request leave it. That includes a realm whose new version cannot be read: it counts as
installed at a version that cannot be read, with the requirements that version declares, so a later
update that leaves one of its ranges holds it back and needs a plan. A host that updates many realms in one request cannot carry a
confirmation, so a realm whose update needs a plan is not updated and is answered with its plan, and
the owner confirms it on that realm's own update.

**Disconnecting a source.** When disconnecting a realm source would remove a realm the host installed
from it automatically, and other installed realms require that realm, the disconnect is refused and
nothing changes. The refusal is the removal plan's sentence followed by
`Remove <realms> first, then try again.`, naming the realms that require it.

### Install refusals

`REALM_REQUIREMENTS_UNMET` answers `409 Conflict` with `code` and a `message` of one sentence per
problem, in a stable order. Nothing was installed, moved, removed or written. The sentences:

| Problem | Sentence template |
| --- | --- |
| No source has the realm | `<realm> requires <needed> <range>, which is not installed and is in none of this installation's realm sources. Add the source that holds <needed>, then install <realm> again.` |
| No published version fits | `<realm> requires <needed> <range>, but no published version of <needed> is in that range. The newest published <needed> is <version>.` |
| Installed version outside, with a fix | `<realm> requires <needed> <range>, but <needed> <installed> is installed. Update <needed> to <version>.` |
| The realm asked for is out of range | `<needed> <version> is outside what <realm> requires (<range>). Install <needed> at v<other> instead.` |
| Conflict | `No version of <needed> satisfies both <a> (<range-a>) and <b> (<range-b>). Remove one of them, or install a release of one that accepts the other's range.` |
| Cycle | `<a> requires <b>, which requires <a>. Remove one of these requirements.` (every realm in the chain is named) |
| Too deep | `<a> requires <b>, which requires <c>, ... Requirements are followed at most 8 realms deep. Install <deepest> first, then install <a> again.` |
| Too many | `Installing <realm> would bring in more than 64 realms. Install some of the realms it requires first.` |
| Two publishers | `<needed> is offered by both <repository-1> and <repository-2>, and neither is installed. Install <needed> from the one you mean, then install <realm> again.` |
| Wrong realm at the source | `<realm> requires realm <needed>, but the repository found for it holds a realm named <other>. Point <needed> at the right repository.` |
| Two realms under one name | `<a> and <b> would both be saved as <name>. Install <b> first under another name.` |
| Could not be checked | `<needed> could not be checked: <reason>. Try again when its repository can be reached.` |
| A bound was reached | `Planning stopped at its <time or read> limit, so nothing was installed. Try again, or install some of the realms it requires first.` |
| Repository moved | `<needed>'s repository changed since the plan was made. Ask for the plan again.` |

A version is named as an action only when it exists: "Update crm-core to 2.4.1" is offered only when
2.4.1 is published and satisfies every realm that requires crm-core. When an update would break another
realm, the sentence says which, and does not offer it as the action.

### At load

Loading checks the installed realms against each other and fetches nothing, so a world loads
offline. A realm stays installed and listed, with a sentence saying why, and is **held back**, while
any of these holds:

- a realm it requires is not installed, or is itself held back. A required realm that is installed
  but failed in some other way still counts as installed. This applies to a soft requirement too;
- a realm it requires is installed at a version outside its hard requirement;
- a realm it requires under a hard requirement has a version that cannot be read, so it cannot be
  compared. A soft requirement accepts such a realm;
- its requirements are part of a cycle.

A realm that requires a held-back realm is held back too, however long the chain, and its sentence
names the chain. The realms it requires and every unrelated realm load normally. When two realms hold
hard requirements on one realm that share no version, the one the installed version satisfies loads,
unless it is held back for another reason, and the other is held back.

The requirement of a realm is judged against every installed realm, whether or not it has handlers.
A realm with handlers that requires a realm with none, such as a realm of only types and views, is
not held back. A realm read on its own, to inspect, bundle or publish it, has no world to be checked
against and is never held back.

**What held back means.** A held-back realm stays installed and listed, and its own problems say why.
It offers nothing to the world:

- no types, views, actions, commands, skills, apps or other declarations;
- no handler tools, type methods or routines;
- no scheduled work, watches, webhooks or channels, and a running channel is stopped;
- no credential prompts and no settings keys;
- no script namespace and no API namespace, so a later realm may take either name.

A caller that already held one of its handlers before it was held back is refused with the same
sentence the realm reports. A held-back realm still reports problems in its own declarations, so the
owner can see what else is wrong. It takes no part in the decisions between the realms that load, such
as two realms declaring the same type or sharing a function namespace. State that belongs to the
realm, such as stored data, grants and stored credentials, is left as it was. An approval given for
one version's content is not carried over to different content.

**Healing.** A held-back realm is whole again as soon as its requirements are met: when the missing
realm, or a version inside the range, joins the world, the realm comes back in that same change,
with its data as it was. Neither a restart nor a reload of the world is needed. One exception: a
realm installed from a local directory whose files changed while it was held back is not brought back
with content nobody loaded. It stays held back with `REALM_CHANGED_WHILE_HELD_BACK` until it is loaded
again, and then it loads from its current files. While it stays held back, so does every realm that
requires it, however long the chain. Realms heal in dependency order: a realm comes back only after
every realm it requires is whole, so a realm never offers anything, even for a moment, while a realm
it requires is still held back. When a realm leaves a
loaded world, every realm that required it is held back from that moment, and so is every realm that
requires one of those.

**On the realm reply.** Wherever a host lists realms or describes one, a held-back realm carries:

| Field | Rule |
| --- | --- |
| `heldBack` | `true` while the realm is held back, `false` otherwise. |
| `heldBackCode` | The problem code that holds it back, such as `REALM_REQUIREMENT_MISSING`. Absent when not held back. |
| `heldBackReason` | The sentence of that problem, as [gated text](#security). Absent when not held back. |

### A label no installed realm declares

A view that reads a label no installed realm declares can never return a row. `requires` is how a
realm says which realm owns what it reads, and a plan installs that realm first, so a label still
unowned once the plan is carried out means the realm is missing a requirement. One rule covers both
places a host meets it, and both say it with problem code `UNOWNED_LABEL` and the same message:

- **At install.** The install is refused and undone: nothing stays installed, by repository or by
  local directory. The answer is `REALM_INSTALL_REFUSED`, and it says why: each label, the views
  that read it, and the fix. When the host can see a realm that declares the label without fetching
  anything, such as a checkout mounted beside a local install, the fix names it and its version as
  the `requires` entry to write. Otherwise it says to require the realm that declares the label.
- **At load.** A realm already installed whose label has since gone unowned, because the realm that
  declared it was removed or no longer declares it, stays installed and is `degraded`, with the
  same problem. A run of one of its views carries `UNOWNED_LABEL` among its warnings. Taking the
  realm out of the world would trade one broken view for an outage, so a load never refuses it.

A label the realm lists under [`optionalLabels`](README.md#optional-labels--reading-a-companion-realm-that-may-be-absent)
and reads only under `OPTIONAL MATCH` is awaited, not unowned. It is a note in both places, and an
install that meets only notes goes ahead.

## Host requirements

A realm can also rely on its host: on behaviour a host gained in one release, such as a filter it
learned to send to a source or a count it learned to report. On an older host such a realm loads
and gives wrong answers, and nothing says why. `requiresHost` states that need.

```typescript
export default {
  name: 'support-desk',
  version: '0.3.0',
  requiresHost: {
    embabel: '[0.4.4,)', // 0.4.4 or newer
  },
} satisfies Realm
```

```yaml
requiresHost:
  embabel: "[0.4.4,)"
```

A realm with no `requiresHost` runs on any host, exactly as before. A host that does not implement
this section ignores the field with an unknown-field note, as an older host ignores `requires`.

### Why a field of its own

- **Not a key under `requires`.** Every key under `requires` is a realm name, and a host that reads
  `requires` looks for a realm of each name. A host is not a realm, so a host entry there would be
  reported as a missing realm. A reserved key that no realm name can spell would avoid the clash,
  but would make one record mean two things, so the need is a field of its own.
- **Not `host`.** [`host`](README.md#execution-hosts) names the runtime a realm's functions run on,
  such as `wasm` or `docker`, and says nothing about versions. `requiresHost` leaves it alone.
- **Keyed by product.** A version means something only along one product's own releases, so each
  entry names the host product it is about. The Embabel host is `embabel`. A host judges the entry
  that names it and only notes the others: a realm can state one range for each host it runs on.
- **realm.yml and realm.ts say the same thing.** The field has the same name and shape in both, and
  realm.ts wins when both declare it, as for every other field.

### Declaring

- `requiresHost` is a record. Each key is a host product name, with the realm name syntax:
  kebab-case, at most 64 characters. Each value is a hard requirement in the grammar of
  [Version requirements](#version-requirements): `[0.4.4,)`, `[0.4.4,0.6.0)`, `[0.5.0-rc.1,)`.
- **Only a range.** A plain version is a recommendation under `requires`, which accepts every
  version, and nothing installs a host, so here it would constrain nothing. An author who writes
  `0.4.4` almost always means 0.4.4 or newer. A plain version is a malformed entry, and the warning
  gives the range: `Write "[0.4.4,)" for 0.4.4 or newer.`
- A malformed entry, a key that is not a host name, or a value that is not text is
  `REALM_REQUIREMENT_MALFORMED`, a warning, with the entry left out, by the same rules as a
  malformed `requires` entry. A `requiresHost` that is not a record is left out whole.
- A host's versions are the versions it publishes. For the Embabel host they are its release tags
  without the `v`, such as `0.4.4` and `0.5.0-rc.1`, ordered by [Version order](#version-order), so
  `[0.4.4,)` does not accept `0.4.4-rc.2`.

### What version a host is

A host reports its own version as one of three things.

| A host is | When | Example |
| --- | --- | --- |
| **a release** | It knows it is a published version: it was built from that version's tag, or its operator chose that exact version when installing it and that version is not older than what the build contains. | `embabel 0.4.4` |
| **a development build** | It knows the newest published version it contains, and that it has changes beyond it. | a development build of embabel, 12 commits after 0.4.4-rc.2 (631c72a) |
| **unknown** | It knows neither, as a build made without its release tags is. | |

A development build is newer than the version it contains, and that is all it knows. It may hold a
change that a later release will carry, or not. A release can be the very same build as an earlier
development build, published again under a version once it was tested, so a build cannot always
name the release it became. Then the version its operator chose names it.

An operator's choice that is older than the version the build contains cannot describe that build
and is set aside. Any other version the operator chose is believed: it is their host.

### Judging a requirement

| Host | Met | Not met | Cannot tell |
| --- | --- | --- | --- |
| a release `V` | the range accepts `V` | the range does not accept `V` | never |
| a development build after `B` | every version newer than `B` is in one set of the range: a set with no upper bound and a lower bound at or below `B` | no version newer than `B` is in the range | otherwise |
| unknown | never | never | always |

| Requirement | Host | Answer |
| --- | --- | --- |
| `[0.4.4,)` | `0.4.4` | met |
| `[0.4.4,)` | `0.4.4-rc.2` | not met: a release candidate is older than its release |
| `[0.4.4,)` | development build after `0.4.4` | met |
| `[0.4.4,)` | development build after `0.4.4-rc.2` | cannot tell |
| `[0.4.0,0.5.0)` | development build after `0.4.4` | cannot tell: a newer build may be past `0.5.0` |
| `(,0.4.4)` | development build after `0.4.4` | not met |
| any | unknown | cannot tell |

Only a certain answer refuses. A build that may hold what the realm needs is never refused it, and
never passes without saying so: "cannot tell" is a warning wherever the realm is reported.

### At install, at load and in validation

| Where | Not met | Cannot tell | An entry for another host |
| --- | --- | --- | --- |
| Install | Refused once the realm's metadata is read, before anything is installed or changed: `409 Conflict` with the code `REALM_HOST_UNSATISFIED`. A realm an install plan would bring in is judged too, and the refusal names the realm that was asked for. | Installed, with the warning `REALM_HOST_UNVERIFIED`. | Installed, with the note `REALM_HOST_NOT_CHECKED`. |
| Load | The realm stays installed and loaded, and is `degraded` with the error `REALM_HOST_UNSATISFIED`. | The warning `REALM_HOST_UNVERIFIED`. | The note. |
| Validation | The error `REALM_HOST_UNSATISFIED`, so the realm does not pass. | The warning. | The note. |

**Why a load does not hold the realm back.** An unmet [realm requirement](#at-load) holds a realm
back. An unmet host requirement does not, because a host's version changes only when its operator
changes it, most often by moving back a release to get out of trouble. Taking realms out of the
world at that moment would turn a rollback into an outage. The realm is kept, its status says it is
degraded and why, and the owner decides. This is the rule for
[a label no installed realm declares](#a-label-no-installed-realm-declares), for the same reason.

Validation judges the realm against the host doing the validating. A validator that runs inside a
host's image judges it against that image.

The sentences, with names, versions and ranges shown as [gated text](#security):

| Code | Severity | Sentence template |
| --- | --- | --- |
| `REALM_HOST_UNSATISFIED` | error | `<realm> requires host <host> <range>, but this host is <shown>.` and the action, `Move the appliance to a release in <range>: ...`, naming how this host is upgraded. At install it ends `Then install <realm> again.`; at load it adds `<realm> stays installed, and what it relies on the newer host for may answer wrongly until the host is in range.` |
| `REALM_HOST_UNVERIFIED` | warning | `<realm> requires host <host> <range>, and this host is <shown>, so it cannot tell whether it is in that range.` The action: `Nothing to do if this build has what <realm> needs. If <realm> answers wrongly, move the appliance to a release in <range>: ...` |
| `REALM_HOST_NOT_CHECKED` | note | `<realm> requires host <other> <range>, which is not this host, so it is not checked here. This host is <host>.` |

`<shown>` is what the host is, in the words of [What version a host is](#what-version-a-host-is):
`embabel 0.4.3`, `a development build of embabel, 12 commits after 0.4.4-rc.2 (631c72a)`, or
`a build of embabel that does not know its own version`.

## The lock

A lock records what resolution chose: every realm that came into the world by a reference, each at
one exact version, with the identity of its content. The file is `realms.lock.json`. It is written by a
host or by tooling and is never edited by hand.

```json
{
  "lockVersion": 1,
  "realms": {
    "crm-core": {
      "version": "2.4.1",
      "source": "https://github.com/example/realm-crm-core",
      "commit": "9f2c1e7a5b3d4c6e8f0a1b2c3d4e5f6a7b8c9d0e",
      "digest": "sha256:3b7e0c1d9a4f5e6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
      "requires": { "calendar": "[1.3.0,)" }
    },
    "my-notes": {
      "version": "0.3.0",
      "source": { "kind": "path" },
      "digest": "sha256:0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b3b7e0c1d9a4f5e6b7c8d9e"
    },
    "sales-pipeline": {
      "version": "1.4.0",
      "source": "ssh://git.example.com/team/realm-sales-pipeline",
      "commit": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
      "digest": "sha256:7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b3b7e0c1d9a4f5e6b",
      "requires": { "crm-core": "[2.0.0,3.0.0)", "calendar": "[1.3.0,)" }
    }
  }
}
```

| Field | Rule |
| --- | --- |
| `lockVersion` | Required. `1`. A reader refuses a number it does not know and says which it reads. |
| `realms` | Required record keyed by realm name, written in name order. |
| `version` | Required. The exact version installed. |
| `source` | Required. A repository in its normalised form, or `{ "kind": "path" }`. |
| `commit` | The commit installed, for a Git source. Absent otherwise. |
| `digest` | Required. `sha256:` and 64 lowercase hexadecimal characters over the installed realm's files. |
| `requires` | That version's own requirements, copied from its metadata. Absent when it has none. |

**The normalised repository.** A repository is written `https://host/path` or `ssh://host/path`:

- the scheme and host are lower case, and a default port (443, 22) is left out;
- user-info, query and fragment are removed, so no user name, password or token reaches the file;
- a trailing `/` and a trailing `.git` are removed;
- the scp form `git@host:owner/repo.git` is written `ssh://host/owner/repo`.

Two spellings of one repository therefore lock the same. A realm installed from a local directory, or
from a `file:` repository where a host allows one for development, is written `{ "kind": "path" }`
with no path or URL, since a local path means something only on the machine that wrote it.

**Writing.** A host writes the world's lock whenever a realm is installed, updated or removed, in the
same step as the change, and that includes every realm a confirmed plan adds, moves or removes. A plan
that is only shown writes nothing, and a step that was undone never reaches the lock. A removal takes
the removed realms out and leaves every other entry as it was. A change leaves the entry of a realm it is
not about as it was, even when that realm is still installed but did not load or its version cannot be
read. One exception: a realm that did not load can only be matched to its entry by its name or by where
it came from. When that does not single out one entry, for example two realms installed from local
folders under names other than their own that both failed to load, the host may drop the entry rather
than risk keeping one that belongs to a removed realm. The entry is written again when the realm next
loads. If writing the lock fails after a
change that worked, the change stays and the world carries a warning that the lock no longer matches
what is installed.

**The lock is advisory.** It records. Resolution does not read it, and it never holds a realm back.

**At load:**

- **Absent.** A world with realms and no lock (a world from before this document) loads with no
  warning. The host writes a complete lock at the world's next realm change.
- **Corrupt.** A lock that cannot be read, is not a regular file, or is too large to be a lock is
  reported with a warning, and the installed realms are not checked against it. The world loads. The
  next realm change writes a complete lock in its place.
- **Stale.** When an installed realm's version differs from its entry, or its content differs from the
  entry's digest, the realm is reported with the warning `REALM_LOCK_MISMATCH` and stays loaded. The
  digest is not compared for a realm whose source is `{ "kind": "path" }`, whose files are its owner's
  working copy. The lock is not rewritten to accept the difference except by an install, update or
  removal of that realm.

**A realm's lock.** Tooling may write the same file beside `realm.ts`, recording the versions of the
required realms the author developed and tested against. It makes the author's tests and generated
types repeatable. A host installing the realm does not read it: the world's own resolution decides,
as a Maven build does not read a dependency's pinned versions. An author who needs an exact version
writes `[2.4.1]` in `requires`.

## Problems

Each problem is reported on the realm that declares the requirement. Each names the requiring realm
and the required realm and, except for a cycle, the requirement as written, and gives one action that
works when applied. A held-back realm is listed with the sentence of its problem.
`REALM_REQUIREMENT_MALFORMED` and `REALM_LOCK_MISMATCH` are warnings and the realm loads. Every other
code is an error that holds the realm back.

| Code | When | Sentence template |
| --- | --- | --- |
| `REALM_REQUIREMENT_MALFORMED` | The value is not a requirement or is not text, the key is not a realm name, the realm requires itself, a set accepts no version, or a limit is passed. Warning: the entry is left out. | `requires.<needed>: "<value>" is not a version requirement, so the requirement is left out. Write "<bracket form>".` When no bracket form says the same thing, the action is the grammar. A value that is not text: `requires.<needed>: the value is not text, so the requirement is left out.` A realm requiring itself: `requires.<realm>: a realm cannot require itself, so the requirement is left out. Remove it.` |
| `REALM_REQUIREMENT_MISSING` | A required realm is not installed, or is held back. | `<realm> requires realm <needed> <range>, which is not installed. Install <needed> at a version in <range>.` A soft requirement's action is `Install <needed>. Version <recommended> is recommended.` A held-back need names the chain: `<realm> requires realm <needed> <range>, which is held back because it requires <next>. Bring <next> back first.` A need held back because its files changed: `<realm> requires realm <needed> <range>, which is held back because its files changed. Load <needed> again.` |
| `REALM_REQUIREMENT_UNSATISFIED` | The installed version is outside a hard requirement, or cannot be read. | `<realm> requires <needed> <range>, but <needed> <installed> is installed. Install a version of <needed> in <range>.` For an unreadable version: `<realm> requires <needed> <range>, but the version of <needed> that is installed cannot be read. Give <needed> a version of three numbers, such as 1.0.0.` |
| `REALM_REQUIREMENT_CONFLICT` | The hard requirements of two or more realms on one realm share no version, and the installed version does not satisfy this realm's. | `<realm> requires <needed> <range>, but <needed> <installed> is installed, and no version of <needed> satisfies both <other> (<other-range>) and <realm> (<range>). Remove one of them, or install a release of one that accepts the other's range.` |
| `REALM_REQUIREMENT_CYCLE` | Requirements form a cycle. | `<realm> requires <b>, which requires <realm>. Remove one of these requirements.` (every realm in the chain is named, in order) |
| `REALM_CHANGED_WHILE_HELD_BACK` | A held-back realm installed from a local directory had its requirements met again, but its files changed while it was held back. It stays held back until it is loaded again. | `<realm>'s files changed while it was held back, so it was not brought back with content nobody loaded. Load <realm> again.` |
| `REALM_LOCK_MISMATCH` | An installed realm differs from its lock entry. Warning: the realm is not held back. | `<realm> <version> is locked at one content digest and its source now offers another. Update <realm> to accept the new content, or restore the locked commit <commit>.` For a version difference: `<realm> is locked at <locked> but <installed> is installed. Update or reinstall <realm> to record what is installed.` |

The same world reports the same text each time.

## Security

These promises hold for every read a plan or an install makes for `requires`.

- **Credentials stay with their host.** A host that holds a GitHub credential sends it only to
  `github.com` on the default port. A repository on any other host, including a GitHub Enterprise
  host, a look-alike name such as `github.com.example.net`, a URL with user-info such as
  `https://github.com@example.net/`, or `github.com` on another port, is read without it, and a
  redirect to another host does not carry it. No credential reaches a lock, a log, a reply or a
  sentence.
- **Two URL schemes.** A required realm's repository is `https:` or `ssh:` (the scp form
  `git@host:owner/repo` is read as `ssh:`, and its path is relative to the login's home, as Git reads
  it, so `git@host:realms/crm.git` and `ssh://git@host/realms/crm.git` can name different repositories
  even though the lock writes both as one source). Any other scheme, including `http:`, `git:` and `ext::`, is
  refused. A `file:` URL is accepted only when the host's operator turns it on for development; it is
  off by default.
- **No option smuggling.** A repository URL or ref that starts with `-`, or holds a control
  character such as a newline or NUL, is refused before anything is fetched.
- **Bounded reads.** Every remote read a plan makes is bounded in time and in size: the refs a
  repository advertises, the metadata read at a tag, and the clone of a version to install. Past a
  bound the change is refused with a sentence that says so, and nothing changes. An installed version holds only
  the planned commit's files, and none of its links leads outside the realm, judged by following
  every link on its way: a link that leaves only through another link is refused too, as is one
  whose chain of links never ends.
- **Realm text is gated.** A realm's name, version, ranges, ref names and URLs are written by its
  author, so a host shows them only as gated text. A name is printed only when it is made of letters,
  digits, dots, underscores and hyphens, at most 64 characters; otherwise the text shows `<word>` in
  its place. Version and range text longer than 64 characters is cut and ends in `...`. A URL is
  shown in its normalised form. No path, URL credential, full digest or host-internal name appears in
  a sentence, and a commit is shortened to seven characters. Text an author wrote is never repeated
  unless it prints as itself.
- **A requirement names no location.** Required realms are found only in the sources the host's
  operator configured.

## Worked examples

**Two realms agree.** `sales-pipeline` requires `crm-core` `[2.0.0,3.0.0)` and `billing` requires
`[2.3.0,)`. Both hold for `[2.3.0,3.0.0)`. Published versions are 1.8.0, 2.2.0, 2.4.1, 3.0.0-rc.1 and
3.0.0. Installing either realm into a world without `crm-core` plans `crm-core 2.4.1`, the newest
version both accept.

**Installed stays.** The same world already has `crm-core 2.3.0`. Nothing changes: 2.3.0 satisfies
both, so 2.4.1 is not installed.

**A recommendation.** `reports` requires `crm-core` `2.2.0`. Alone, in a world without `crm-core`,
it plans 2.2.0. Beside `billing` (`[2.3.0,)`) it plans 3.0.0, the newest version `billing` accepts,
and reports nothing, because a soft requirement never conflicts.

**A pre-release.** `preview` requires `crm-core` `[3.0.0-rc.1,4.0.0)` and 3.0.0 is not yet published.
It plans `3.0.0-rc.1`, because its bound names a pre-release of 3.0.0. A realm requiring `[2.0.0,)`
never gets `3.0.0-rc.1` planned.

**Needs of needs.** `sales-pipeline` requires `crm-core` `[2.0.0,3.0.0)`, and `crm-core` 2.4.1 requires
`calendar` `[1.3.0,)`. In an empty world, installing `sales-pipeline` plans three steps: `calendar`
(required by `crm-core`), `crm-core` (required by `sales-pipeline`) and `sales-pipeline`. A chain of
nine realms, each requiring the next, is refused naming all nine.

**Installing with a requirement.** The world has `crm-core` 1.9.0. Installing `sales-pipeline` answers
the plan reply above and installs nothing. The owner sends the request again with its `planId`;
`crm-core` moves to 2.4.1 and `sales-pipeline` installs.

**Identity by name plus source.** Two configured sources each publish a realm named `crm-core`, and the
world has none. Installing `sales-pipeline` is refused naming both repositories. The owner installs
`crm-core` from the one they mean; installing `sales-pipeline` again plans without a question about
`crm-core`, since the installed one is the one meant.

**A local directory.** The owner installs `my-notes` from a folder on disk; its metadata says `0.3.0`
and it requires `calendar` `[1.3.0,)`. The plan installs `calendar` from a configured source after the
owner confirms. A realm that requires `my-notes` `[0.3.0,0.4.0)` is satisfied by it.

**Cycle.** `sales-pipeline` requires `crm-core`, and `crm-core` requires `sales-pipeline`. Installing
either is refused with `sales-pipeline requires crm-core, which requires sales-pipeline. Remove one of
these requirements.`

**Conflict.** `billing` 1.0.0 requires `crm-core` `(,2.0.0)`. Beside `sales-pipeline` no version
satisfies both. Neither install proceeds, and the refusal names both realms and both ranges.

**Removing a needed realm.** The owner asks to remove `crm-core`. The host answers a plan with a
`remove` step for `crm-core` and a `hold-back` step for `sales-pipeline`. The owner confirms;
`crm-core` is removed and `sales-pipeline` stays installed and listed, held back with
`sales-pipeline requires realm crm-core [2.0.0,3.0.0), which is not installed. Install crm-core at a
version in [2.0.0,3.0.0).` It offers no types, views or tools until `crm-core` is installed again in
that range, and then it is back in that same change.

## Changes are all or nothing

A realm change (an install with its plan, an update, a removal, publishing a draft) writes more than once. A host
guarantees that the world is either as it was or fully changed, even if the host stops in the middle,
and tells the owner which.

- A change that fails is undone before the call returns. The realm list and the lock are as they
  were.
- If the host stops mid-change, the next time the world loads, before anything loads from it, the
  host finishes an interrupted removal, since deleting is what the owner asked for. Any other
  interrupted change is put back as it was. The world carries a warning saying which, such as
  `Removing crm-core was interrupted, so the removal was finished when the world loaded.` or
  `A change to this world's realms was interrupted before it finished, so the realm list and the lock were put back as they were before it.`
- A finished removal withdraws the removed realm's approval and takes it out of the lock, including
  when its source could not be loaded. The removed realm can no longer run from a stored copy.
  If approval withdrawal fails, the host keeps the removal journal and retries withdrawal on load.
  Other realms keep their approvals. Their lock entries follow the matching rules in [The lock](#the-lock).
- Publishing a draft over an installed realm of the same name leaves either the installed realm as
  it was or the draft wholly in its place, never neither and never a mix of the two. If the host stops
  before the draft is in place, the next load puts the installed realm back and the draft is still
  waiting to be published. Only the copy that publish replaced is ever put back: a realm that was
  removed never returns because an earlier publish of it was interrupted.
- If the repair cannot complete, the world still loads. It carries an error that says an earlier
  change was interrupted and could not be put right, that the world loaded with that change half
  done, and that changes to its realms are refused until it is. Any realm change asked for meanwhile
  is refused and nothing is changed: `The previous change to this world's realms could not be put
  right, so nothing was changed.` The repair is tried again at each load.
- If part of a removed realm's folder cannot be deleted, whether during the removal or while
  finishing an interrupted one, the removal is not finished. The realm is out of the realm list and
  the lock, and nothing left in its folder loads, runs or is offered (no command, artifact type or
  personality), even if the realm definition survived. A removal
  the owner asked for is answered as failed, and the world carries a warning such as
  `Removing crm-core is not finished: realm folder crm-core could not be deleted completely.` The
  deletion is tried again at each load. Any realm change asked for meanwhile is refused and nothing
  is changed, with a sentence naming the folder: `The previous removal from this world's realms is
  not finished: realm folder crm-core could not be deleted completely, so nothing was changed.`
- A change reported done stays done. If the host cannot clear its own record of a finished change
  but can mark the record finished, the change is reported done and the next load keeps it. If it
  can do neither, the next load would put the change back, so the change is not reported done: it
  is put back at once, and the call fails as a storage failure with `The change to this world's
  realms could not be completed: its record in the world's config folder could not be cleared, and
  the next load would undo it, so it was undone now.` A removal is the exception, since the next
  load finishes it again: it is reported done either way.

## Known limits

These are observable limits of the behaviour above.

1. **The lock is not read by resolution.** A mismatch is a warning and never holds a realm back.
2. **A satisfying version far back may be missed.** A host reads a bounded number of a source's
   newest tags, so a version older than that bound is not offered, and a requirement only it would
   meet is reported as not met.
3. **A held-back realm still wins its own name.** It takes no part in the decisions between realms
   that load, and holds no script or API namespace, but a realm of the same name with weaker
   precedence stays shadowed by it.
4. **Overlapping cycles.** When several cycles share a realm, the cycle sentence can name a chain
   that includes a requirement nobody declared.

## Not specified

- An owner's override that pins a version against a declared requirement.
- Requirements that apply only when another realm is present.
- The entry format by which an index source lists versions.
- How a host learns which release it is when its build cannot say, beyond its operator's choice.
- The dependency source `from: { realm: ... }`, which stays reserved (see
  [How requires fits with what exists](#how-requires-fits-with-what-exists)).

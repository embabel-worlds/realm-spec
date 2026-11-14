# Realm requirements

**Spec version: 0.1.0**

Status: proposed. No host is required to implement this yet. A host that does not reads `requires`
as an unknown field and reports it.

A realm may need another realm: its views read labels the other realm owns, or its handlers call the
other realm through the gateway. `requires` states that need, with the versions the author has made
it work with. A host resolves one version of each required realm per world, and reports a missing or
incompatible one when the realm is installed and when it loads, before anything runs.

The model is Maven's: a requirement is a recommended version or a hard range in bracket notation,
requirements are followed transitively, and a world holds one version of each realm.

A requirement grants nothing. It does not import another realm's source, module bytes, credentials,
handlers or grants. [Graph composition](LABELS_AND_COMPOSITION.md) and gateway calls work as before;
`requires` only says which realms must be present for them to mean anything.

Module dependencies are a separate contract. A [dependency](TYPESCRIPT_REALMS.md#dependencies) names
WebAssembly bytes by exact version and digest and takes no range. Nothing here changes that.

## Declaring

`requires` is realm metadata. Each key is the required realm's `name` as its own metadata declares
it. Each value is a version requirement.

```typescript
import { defineRealm } from "@embabel/realm-types";

export default defineRealm({
  name: "sales-pipeline",
  version: "1.4.0",
  requires: {
    "crm-core": "[2.0.0,3.0.0)", // any 2.x
    calendar: "[1.3.0,)",        // 1.3.0 or newer
    "currency-rates": "0.9.2",   // recommended, any version accepted
  },
});
```

```yaml
# realm.yml
name: sales-pipeline
version: "1.4.0"
requires:
  crm-core: "[2.0.0,3.0.0)"
  calendar: "[1.3.0,)"
  currency-rates: "0.9.2"
```

A realm with no `requires` behaves exactly as it did before this document. A realm must not require
itself; the entry is ignored with a warning. Only a realm whose name is kebab-case (lower-case
letters, digits and hyphens, starting with a letter or digit, at most 64 characters) can be
required; a key of any other form is refused as malformed. A `requires` that is not a record of
realm names is ignored with a warning. A requirement
names a realm and never a location: the host finds required realms in the realm sources its operator
configured. A value that is not a valid requirement is a warning on the realm and that one entry is
ignored; the realm is not held back for it (see [At load](#at-load)).

## Version requirements

```
requirement = soft / hard
soft        = version
hard        = set *( "," set )
set         = "[" version "]"
            / ( "[" / "(" ) [ bound ] "," [ bound ] ( "]" / ")" )
bound       = number [ "." number [ "." number ] ] [ "-" qualifier ]
number      = 1*9DIGIT
version     = number "." number "." number [ "-" qualifier ]
```

A qualifier is dot-separated parts of letters, digits and hyphens, and no part is empty, so `rc.`
and `rc..1` are not versions. An interval has at least one bound. A bound with fewer than three numbers is completed with zeros,
so `[2,3)` means `[2.0.0,3.0.0)`. No whitespace is allowed.

| Requirement | Accepts |
| --- | --- |
| `2.4.0` | Soft. Recommends 2.4.0 and accepts any version. |
| `[2.4.0]` | Exactly 2.4.0. |
| `[2.0.0,3.0.0)` | 2.0.0 up to, not including, 3.0.0. |
| `[1.3.0,)` | 1.3.0 or newer. |
| `(,2.0.0)` | Anything older than 2.0.0. |
| `(,1.0.0],[1.2.0,)` | 1.0.0 or older, or 1.2.0 or newer. Excludes the versions between. |

A **soft** requirement is a recommendation. It never causes a conflict and any installed version
satisfies it, including a realm whose version cannot be read as three numbers. It still needs the
realm to be installed: a soft requirement on a realm that is absent is not met. It decides which
version is installed when the realm is absent and no hard range says otherwise. A **hard**
requirement must hold, and a realm whose version cannot be read as three numbers cannot meet it.

A set that accepts no version is refused as malformed. That includes bounds that cross and a low
bound that is a pre-release of an excluded upper bound, such as `[3.0.0-rc1,3.0.0)`, because an
exclusive upper bound also leaves out pre-releases of itself. Two requirements whose sets share no
version are a conflict by the same rule.

Other notations are refused as `REALM_REQUIREMENT_MALFORMED`, naming the field and the bracket form
that says the same thing:

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
a Git ref or a URL has no equivalent and is refused with the grammar. A value is at most 256
characters.

### Version order

Versions compare by their three numbers, in order. A version with a `-qualifier` is a pre-release:
it sorts before the same numbers without one, and two qualifiers compare by their dot-separated
parts, left to right, until one part differs. Two parts of digits compare as numbers, so `2` sorts
before `10` and `01` equals `1`. A part of digits sorts before any part that is not all digits, and
two parts that are not all digits compare by ASCII, so `2` and `10` both sort before `1a`, and `1a`
sorts before `1b`. When every part of the shorter qualifier equals the matching part of the longer,
the shorter sorts first. This is a total order: no three versions can each sort before the next
around a circle. A `+suffix` on a realm's version is ignored when comparing.

Two rules differ from Maven on purpose, because Maven's behaviour here surprises people:

- An exclusive upper bound also excludes pre-releases of that bound. `[2.0.0,3.0.0)` does not accept
  `3.0.0-rc1`.
- Resolution never selects a pre-release by itself. A pre-release the owner installed still
  satisfies a requirement by the order above.

## Published versions

Resolution chooses among the versions a realm source publishes.

- A Git source publishes one version per tag named `v<version>`, when the realm metadata at that tag
  declares the same `version`. A tag whose metadata disagrees is not a published version.
- A source with no such tags publishes exactly one version: the one its metadata declares at the
  ref it is installed from. A realm installed from a local directory publishes the one version it
  declares.
- A source is the publisher of a required realm only when the metadata it holds declares that
  realm's name. A source that declares another name publishes nothing, and an install that needs it
  is refused with a sentence that names both realms, such as `sales-pipeline requires realm crm-core,
  but the repository found for it holds a realm named crm. Point crm-core at the right repository.`
- When a realm has many tags, a host reads a bounded number of them, newest first. Only tags named
  `v<version>` are candidates. For one realm, a host reads the metadata of the newest 20 candidates
  that every hard requirement known when planning accepts (every candidate, when the requirements
  are soft), and of the newest 20 that a hard requirement found in a version it has already read
  accepts. A tag read whose metadata disagrees counts among the 20 and is not published. A candidate
  outside those ranges is known by its name, so a refusal can say what is newest, and is read only if
  resolution then picks it, for at most 20 such reads per realm. A candidate inside the ranges that
  is older than the newest 20 is not offered to resolution, so a soft requirement whose recommended
  version is that old resolves to a newer version instead. A plan reads at most 60 versions in
  all; a plan that needs more is refused with a sentence saying so. A satisfying version is missed
  only when the newest 20 candidates inside the range are all unusable, because their metadata
  disagrees with their tag or declares another realm's name: an older tag that would meet the
  requirement is then not read, and the requirement is reported as not met.
- An index source may list versions explicitly. Its entry format is not specified here.

A published version does not change. If the content behind an installed version differs from what
the host recorded at install, the host reports the difference with a warning (see
[The lock](#the-lock)); it does not adopt the new content silently.

## Resolution

A host resolves per world, over every installed realm plus the realm being installed. Requirements
are followed transitively: a required realm's own `requires` count. For each required realm:

1. Intersect the hard requirements of every realm that requires it. With none, every version is
   acceptable.
2. If the realm is installed at a version inside the intersection, keep it. An installed realm is
   never changed to a newer version merely because one exists.
3. Otherwise choose among published releases inside the intersection: the highest soft
   recommendation that is one of them, or else the highest of them.
4. If the intersection is empty, there is a conflict. If it is not empty and no published release is
   inside it, the requirement is unsatisfied.

The same installed realms and the same published versions always resolve to the same result. The
order in which realms were installed or declared does not matter.

A cycle of requirements is refused as `REALM_REQUIREMENT_CYCLE`, naming the realms in order. Each
realm in the cycle reads the shortest route of requirements from itself back to itself (see
[Known limits](#known-limits) for overlapping cycles).

### At install

Before anything changes, the host computes a plan over the installed realms, the published versions
and the realm being installed.

- **Nothing to change.** When every requirement is already met, the install goes on as it would for a
  realm with no requirements.
- **The plan adds or moves other realms.** The install does not proceed. It answers that it needs
  confirmation, with the whole plan as a sentence and as data. Each step of the data names the
  `realm`, the `version`, the `change` (added, or moved from the installed version), the realm that
  `requiredBy` it, the `repository` it comes from, and `experimental: true` when its author calls it
  experimental (the field is absent otherwise). The sentence says the same, starting from what the
  owner asked for:

  `Installing sales-pipeline 1.4.0 also updates crm-core from 1.9.0 to 2.4.1 from https://github.com/example/realm-crm-core, which sales-pipeline requires ([2.0.0,3.0.0)).`

  When the realm asked for is experimental, the sentence says so too, because confirming the plan is
  the only question the owner is asked. Nothing is installed, moved or written until the owner
  confirms.
- **Only the owner confirms.** A confirmation counts for the plan this owner was last shown and no
  other. A confirmation with no plan shown (a first request that already says it is confirmed, or one
  after the host restarted) is answered with the plan and nothing is installed. If the plan computed
  at confirmation differs from the one shown, in the realm's repository, ref, commit or any step,
  including a step whose experimental flag changed or a tag or branch that moved, the answer is
  `The plan changed since it was shown.` followed by the new plan, and the owner is asked again.
  A conversational assistant never confirms: a chat message can come from someone other than the
  owner, so chat answers with the plan and points the owner to where it can be confirmed.
- **A confirmed install installs exactly what the plan read.** Each version is installed at the commit
  the plan read it at. If a repository has moved since, the install is refused before anything is
  saved, with a sentence saying the repository changed since the plan was made and to ask again.
  A plan step installs a tag as its `v<version>` tag, even when a branch has the same name.
- **Unmet requirements refuse the install.** If any requirement cannot be met, nothing is installed
  and the problems below are reported, one sentence each. A requirement that no published version
  meets is refused and names the newest published version, as in `the newest published crm-core is
  1.9.0`. Two realms that the plan would save under one name are refused naming both, and the
  sentence says to install the dependency first under another name; nothing is renamed behind the
  owner's back.
- **All or nothing.** If a step fails, the steps before it are undone and the world is as it was.

With no ref given, the realm asked for is planned and installed at the branch the repository's HEAD
names. A commit ref that the repository will not serve by id is refused with a sentence that asks for
a tag or branch. A repository that cannot be listed, a ref it lacks, or a ref that cannot be cloned
refuses the install whenever the world holds a realm with `requires`, with a sentence that starts
`could not be checked`. In a world where no realm has `requires`, the install goes on unchecked, since
nothing it does can hold an installed realm back.

Planning is bounded. All reads for one plan share a time limit, a read budget and a limit on the
refs a repository may advertise. Past a limit the install is refused with a sentence that says so,
and nothing changes. A requirement that is already met costs no lookup, so an unreachable source for
it does not refuse an unrelated install.

The host then writes [the lock](#the-lock) in the same step as the install.

### At load

Loading checks the installed realms against each other and fetches nothing, so a world loads
offline. A realm stays installed and listed with a sentence saying why, and is **held back**, while
any of these holds:

- a realm it requires is not installed or is itself held back. A required realm that is installed
  but failed in some other way still counts as installed. This applies to a soft requirement too: a
  recommendation accepts any version, and still needs the realm to be there;
- a realm it requires is installed at a version outside its hard requirement;
- a realm it requires under a hard requirement has a version that cannot be read as three numbers,
  so it cannot be compared. A soft requirement accepts such a realm;
- its requirements are part of a cycle.

A realm that requires a held-back realm is held back too, however long the chain. The realms it
requires and every unrelated realm load normally. When two realms hold requirements that share no
version, the one the installed version satisfies loads, unless it is held back for another reason,
and the other is held back.

A requirement that is malformed is a warning on the realm. That one entry is ignored and the realm
loads with its other requirements; it is not held back for it.

The requirement of a realm is judged against every installed realm, whether or not it has handlers.
A realm with handlers that requires a realm with none, such as a realm of only types and views, is
not held back.

**What held back means.** A held-back realm stays installed and listed, and its own problems say why.
It offers nothing to the world:

- no types, views, actions, commands, skills, apps or other declarations;
- no handler tools, type methods or routines;
- no scheduled work, watches or channels, and a running channel is stopped;
- no credential prompts and no settings keys;
- no script namespace and no API namespace, so a later realm may take either name.

A caller that already held one of its handlers before it was held back is refused with the same
sentence the realm reports, and the call works again when the requirement is met. A held-back realm
still reports problems in its own declarations, so the owner can see what else is wrong. It takes
no part in the decisions between the realms that load, such as two realms declaring the same type or
sharing a function namespace: a healthy realm keeps what it shares with a held-back one. State that
belongs to the realm, such as grants and stored credentials, is left as it was.

It is whole again when its requirements are met: installing the missing realm, or a version inside
the range, and loading the world again is enough. The host does not need a restart.

Requirements are checked where a whole world is loaded, and again each time a realm joins or leaves
a loaded world. A realm read on its own, to inspect, bundle or publish it, has no world to be
checked against and is never held back.

When a realm leaves a loaded world, every realm that required it is held back from that moment, and
so is every realm that requires one of those, however long the chain. When a realm joins and
completes what a held-back realm was waiting for, the held-back realm stays held back and reports
`REALM_REQUIREMENT_RELOAD_NEEDED` until the world is loaded again. Until then it counts as not
installed for the realms that require it, which are held back with `REALM_REQUIREMENT_MISSING`.

## The lock

A lock records what resolution chose: every realm that came into the world by a reference, each at
one exact version, with the identity of its content. The file is `realms.lock.json`. It is written by a host
or by tooling and is never edited by hand.

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
    "sales-pipeline": {
      "version": "1.4.0",
      "source": "https://github.com/example/realm-sales-pipeline",
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
| `version` | Required. The exact version resolved. |
| `source` | Required. For a realm from a Git repository, the repository URL as the world was given it, without credentials, query or fragment (nothing up to the last `@` after the scheme is kept, so a password never reaches the file); a `file://` URL stays as written and means something only on the machine that wrote it. For a realm installed from a local directory, `path:` followed by the directory's name, never its full path. |
| `commit` | The commit installed, for a Git source. Absent otherwise. |
| `digest` | Required. `sha256:` and 64 lowercase hexadecimal characters over the installed realm's files. It is not compared at load for a realm installed from a local directory, whose files are its owner's working copy. |
| `requires` | That version's own requirements, copied from its metadata. Absent when it has none. |

**A world's lock.** A host writes the lock for a world whenever a realm is installed, updated or
removed, in the same step as the change, and that includes every realm a confirmed plan adds or
moves. A plan that is only shown writes nothing, and a step that was undone never reaches the lock. A
removal takes the removed realms out of the lock and leaves every other entry as it was. The lock
records. Resolution does not read it, and it never holds a realm back. If writing the lock fails
after a change that worked, the change stays and the world carries a warning that the lock no longer
matches what is installed.

**At load.** If an installed realm's content does not match the digest in the world's lock, the realm
is reported with the warning `REALM_LOCK_MISMATCH` and stays loaded. The realm is not held back and
the lock is not rewritten to accept the new content, except by an install, update or removal of that
realm. An unrelated install does not accept it. A lock that cannot be read is reported with a warning
and the installed realms are not checked against it. If a world has realms and no lock (a world from
before this document), the host writes one from what is installed and reports nothing. A realm
installed from a local directory is locked by version and source, and its digest is not compared.

**A realm's lock.** Tooling may write the same file beside `realm.ts`, recording the versions of the
required realms the author developed and tested against. It makes the author's tests and generated
types repeatable. A host installing the realm does not read it: the world's own resolution decides,
as a Maven build does not read a dependency's pinned versions. An author who needs an exact version
writes `[2.4.1]` in `requires`.

## Problems

Each problem is reported on the realm that declares the requirement. Each names the requiring realm
and the required realm and, except for a cycle, the requirement as written, and gives one action that
works when applied. A held-back realm is listed with the sentence of its problem. `REALM_REQUIREMENT_MALFORMED` and
`REALM_LOCK_MISMATCH` are warnings and the realm loads. Every other code holds the realm back;
`REALM_REQUIREMENT_RELOAD_NEEDED` is reported as a warning and holds it back too.

| Code | When | Example |
| --- | --- | --- |
| `REALM_REQUIREMENT_MALFORMED` | The value is not a requirement, is not text, or the key is not a realm name. Warning: the entry is left out and the realm is not held back. | `requires.crm-core: "^2.0.0" is not a version requirement. The requirement is left out.` with the action `Write "[2.0.0,3.0.0)".` A value that is not text reads `requires.crm-core: the value is not text, so the requirement is left out`. |
| `REALM_REQUIREMENT_MISSING` | At load, the realm is not installed or is itself held back (`sales-pipeline requires realm crm-core [2.0.0,3.0.0), which is not installed or is itself held back. Install crm-core at a version in [2.0.0,3.0.0).`). A soft requirement on an absent realm reads the same, and its action is `Install crm-core. Version 0.9.2 is recommended.` At install, no configured source has it. | `sales-pipeline requires crm-core [2.0.0,3.0.0), which is not installed and is in none of this installation's realm sources. Add the source that holds crm-core, then install sales-pipeline again.` |
| `REALM_REQUIREMENT_UNSATISFIED` | The installed version is outside the requirement, no published release is inside it, or a hard requirement meets a realm whose installed version cannot be read. | At load, for an unreadable version: `sales-pipeline requires crm-core [2.0.0,3.0.0), but the version of crm-core that is installed cannot be read.` with the action `Give crm-core a version of three numbers, such as 1.0.0.` At load: `sales-pipeline requires crm-core [2.0.0,3.0.0), but crm-core 1.8.0 is installed. Install a version of crm-core in [2.0.0,3.0.0).` At install, which can name a published version: `sales-pipeline requires crm-core [2.0.0,3.0.0), but crm-core 1.8.0 is installed. Update crm-core to 2.4.1.` When no published version fits, the sentence names the newest: `... but crm-core 1.8.0 is installed. The newest published crm-core is 1.9.0.` When the realm out of range is the one being installed: `crm-core 3.0.0 is outside what sales-pipeline requires ([2.0.0,3.0.0)). Install crm-core at v2.4.1 instead.` |
| `REALM_REQUIREMENT_CONFLICT` | The hard requirements of two or more realms share no version. | At load: `sales-pipeline requires crm-core [2.0.0,3.0.0), but crm-core 1.8.0 is installed, and no version of crm-core satisfies both billing ((,2.0.0)) and sales-pipeline ([2.0.0,3.0.0)). Remove one of them, or install a release of one that accepts the other's range.` At install: `No version of crm-core satisfies both sales-pipeline ([2.0.0,3.0.0)) and billing ((,2.0.0)). Remove one of them, or install a release of one that accepts the other's range.` |
| `REALM_REQUIREMENT_CYCLE` | Requirements form a cycle. | `sales-pipeline requires crm-core, which requires sales-pipeline. Remove one of these requirements.` |
| `REALM_REQUIREMENT_RELOAD_NEEDED` | A realm that was held back now has every realm it requires, in a world that is already loaded. Warning, and the realm stays held back. | `sales-pipeline's required realms are all there now, but sales-pipeline was held back when the world was loaded. Load the world again to bring sales-pipeline back.` |
| `REALM_LOCK_MISMATCH` | An installed realm's content differs from what the lock records. Warning: the realm is not held back. | `crm-core 2.4.1 is locked at one content digest and its source now offers another. Update crm-core to accept the new content, or restore the locked commit 9f2c1e7.` |

Rules for the text:

- Name a version only when it exists: "Update crm-core to 2.4.1" is offered only when 2.4.1 is
  published and satisfies every realm that requires crm-core. Otherwise say what was found:
  `the newest published crm-core is 1.9.0`.
- When an update would break another realm, say which, and do not offer it as the action.
- The same world reports the same text each time.
- No path, URL credential, full digest or host-internal name appears in the text. A commit is
  shortened to seven characters.
- A realm name is printed only when it is made of letters, digits, dots, underscores and hyphens, at
  most 64 characters; otherwise the text shows `<word>` in its place. Version and range text longer
  than 64 characters is cut and ends in `...`. Text an author wrote is never repeated unless it
  prints as itself.

## Worked examples

**Two realms agree.** `sales-pipeline` requires `crm-core` `[2.0.0,3.0.0)` and `billing` requires
`[2.3.0,)`. The intersection is `[2.3.0,3.0.0)`. Published releases are 1.8.0, 2.2.0, 2.4.1 and
3.0.0. Installing either realm into a world without `crm-core` plans `crm-core 2.4.1`.

**Installed wins.** The same world already has `crm-core 2.3.0`. Nothing changes: 2.3.0 is inside
the intersection, so 2.4.1 is not installed.

**A recommendation.** `reports` requires `crm-core` `2.2.0`. Alone, in a world without `crm-core`,
it plans 2.2.0. Beside `billing` (`[2.3.0,)`) it plans 3.0.0, the highest release `billing` accepts,
and reports nothing, because a soft requirement never conflicts.

**Installing with a requirement.** The world has `crm-core` 1.9.0, and `sales-pipeline` requires
`[2.0.0,3.0.0)`. Installing `sales-pipeline` answers with the plan, as in [At install](#at-install),
and installs nothing. The owner confirms; `crm-core` moves to 2.4.1 and `sales-pipeline` installs.

**Held back, then whole.** The owner removes `crm-core`. `sales-pipeline` stays installed and listed
with `sales-pipeline requires realm crm-core [2.0.0,3.0.0), which is not installed or is itself held
back. Install crm-core at a version in [2.0.0,3.0.0).` It offers no types, views or tools until
`crm-core` is installed again in that range.

**Conflict.** `billing` 1.0.0 requires `crm-core` `(,2.0.0)`. Beside `sales-pipeline` the
intersection is empty. Neither install proceeds and the conflict above is reported.

## Changes are all or nothing

A realm change (an install with its plan, an update, a removal) writes more than once. A host
guarantees that the world is either as it was or fully changed, even if the host stops in the middle,
and tells the owner which.

- A change that fails is undone before the call returns. The realm list and the lock are as they
  were.
- If the host stops mid-change, the next time the world loads, before anything loads from it, the
  host finishes an interrupted removal, since deleting is what the owner asked for. Any other
  interrupted change is put back as it was. The world carries a warning saying which, such as
  `Removing crm-core was interrupted, so the removal was finished when the world loaded.` or
  `A change to this world's realms was interrupted before it finished, so the realm list and the lock were put back as they were before it.`
  A realm folder that a change had already moved into place is left where it is, as that warning
  says; the realm list and the lock are what is put back.
- A finished removal also leaves the lock. Every other lock entry is as it was.
- If the repair cannot complete, the world still loads. It carries an error that says an earlier
  change was interrupted and could not be put right, that the world loaded with that change half
  done, and that changes to its realms are refused until it is. Any realm change asked for meanwhile
  is refused and nothing is changed: `The previous change to this world's realms could not be put
  right, so nothing was changed.` The repair is tried again at each load.
- Finishing an interrupted removal also withdraws the removed realm's approval, so nothing of it can
  run afterwards. If that cannot be done, the repair has not completed.
- A record of a change that cannot be read is set aside and never written over, and the owner is
  told with a warning.

## Known limits

These are observable limits of the behaviour above.

1. **Local-directory installs are not planned.** Installing a realm from a local directory has no
   confirmation step and does not install the realms it requires. The realm is held back at load, with
   its sentence, until they are installed.
2. **The lock is not read by resolution.** A mismatch is a warning and never holds a realm back.
3. **At most 20 tags are read for a realm up front.** The newest 20 candidate tags inside the
   requirement's range are read, as set out under [Published versions](#published-versions). A range is
   not missed for lying far back, since tags outside it are not read. A satisfying version is missed
   only when the newest 20 candidates inside the range are all unusable; the requirement is then
   reported as not met even though an older tag would meet it. A soft requirement whose recommended
   version is older than the newest 20 resolves to a newer version.
4. **A held-back realm still wins its own name.** It takes no part in the decisions between realms
   that load, and holds no script or API namespace, but a realm of the same name with weaker
   precedence stays shadowed by it.
5. **Webhooks declared in a realm's files are registered at start-up** before the world is built, so a
   held-back realm's declared webhooks can be active until its world has been loaded.
6. **A step that installs another realm from a repository already saved under the same reference
   name** replaces what that name held, even when the repository now supplies a differently named
   realm. The realm it held disappears, and any realm that requires it is held back, although the
   plan said only that the new realm would be installed.
7. **A requested realm whose version cannot be read, against a hard range that includes `0.0.0`.**
   Planning treats the unreadable version as 0.0.0, so the plan is empty and the install reports
   success, and the load then holds the requiring realm back, as a hard range cannot be met by an
   unreadable version.
8. **Overlapping cycles.** When several cycles share a realm, the cycle sentence can name a chain
   that includes a requirement nobody declared.

## Not specified

- An owner's override that pins a version against a declared requirement.
- Requirements that apply only when another realm is present. [Optional labels](README.md#optional-labels--reading-a-companion-realm-that-may-be-absent)
  cover a companion realm that may be absent.
- The entry format by which an index source lists versions.
- The dependency source `from: { realm: ... }`, which stays reserved. When it is specified, the
  realm it names is taken from `requires`.

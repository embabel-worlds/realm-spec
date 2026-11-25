# The battery library

A realm battery (`tests/verify.sh`, `tests/*.py`, a smoke script) reconciles the figures a realm
reports against its source. A figure is only the realm's when the engine says the answer is whole,
and the engine says so beside the rows. A battery that reads `rows[0].n` or a view's `data` past
that reports a source that failed under load, a page it capped or a hop it refused as drift in
the realm. And a negative check ("no row is wrong") passes on rows that are not all there.

This directory holds the one definition of "whole" every battery uses, so it is decided once and
kept in step with the engine:

| file | what it is |
| --- | --- |
| `short.py` | `short(d, figure)`: `None` when whole, else `REFUSED: <why>` or `PARTIAL <figure>: <reason>`. Also a script: `curl … \| python3 short.py` prints the figure, or the verdict in its place. |
| `short.mjs` | the same, for JavaScript batteries and smoke scripts. |
| `short.sh` | POSIX sh helpers over `short.py`: `n`, `rows`, `whole`, `short_of`. |
| `canned/`, `expected.json` | answers of every shape (whole, partial, refused, tool fields, view outcomes) and the verdict each must get. |
| `test_short.py` | all four forms agree with `expected.json`, and the JS and Python code lists are equal. |
| `engine_codes.py` | the code lists against the engine's own (see below). |
| `pin.py` | copies the library into a realm, pinned, and checks a realm's copy against its pin. |

## What counts as short

There are three answer shapes, and `short()` reads each one:

- **Query** (`/api/v1/admin/kg/execute`, `/api/v1/admin/kg/ask`): checks `error`, an unfinished `run`, `answerBoundary`, a typed `reason` that is not a clean answer, and every `warnings` entry whose code is in `SHORT_CODES`.
- **Tool** (`/api/v1/tools/kg_ask`, `kg_query`, and the same answers over MCP): everything a query answer has, plus `incomplete`, the ask's own qualifying line, and `emptyCause: SOURCE_UNANSWERED`, an empty result where no source answered.
- **View** (`/api/v1/views/{name}/invoke`): `status` other than `SUCCEEDED` is a refusal. An `outcome` other than `OK` or `EMPTY` is short, and so is any warning code in `SHORT_PUBLIC`.

Every warning code the engine writes is decided in `short.py`:
- `SHORT_CODES` mean rows or values may be missing.
- `WHOLE_CODES` leave every row in place: cost notes, an honest empty (`FILTER_STARVED`), provenance, withheld fields, a dated copy, and judgement and projection notes.

A battery that asserts a refusal on purpose reads the answer itself; the helpers are for figures.

## Kept in step with the engine

The engine names its notes in three enums: `ProducerDiagnostics.Kind`, `ReductionDiagnostics.Kind` and `DiagnosticNotes.TraversalNote`. `engine_codes.py` reads them out of a published server image's bytecode, a jar, or a source checkout. It fails when:
- the engine writes a code that `short.py` has not decided;
- `short.py` decides a code the engine no longer writes anywhere;
- a reason or public code `short.py` relies on is gone.

The `Battery library` workflow runs it against `:canary`, which is main as merged, and against `:latest` with `--older`, since the stable release may predate newer codes. It runs on every change here and weekly, so a new kind of note fails here before a battery reads it as whole.

    python3 battery/engine_codes.py --image ghcr.io/embabel/assistant:canary
    python3 battery/engine_codes.py --source ../assistant

Adding a code means adding it to `SHORT_CODES` or `WHOLE_CODES` in `short.py`, and to the matching set in `short.mjs`. If the code changes a verdict, add a canned answer with the verdict it should get in `expected.json`.

## Using it in a realm

A realm carries a pinned copy in `tests/lib/`, so its battery runs with nothing fetched and a change
here never moves its verdicts behind its back:

    # from a realm-spec checkout at the tag to pin
    git checkout v0.2.2
    python3 battery/pin.py install ../realm-lago v0.2.2 short.py short.sh

That copies the files and writes `tests/lib/BATTERY`, which holds the tag and each file's sha256. Copy only the files the battery uses; `short.sh` needs `short.py` beside it.

- **sh**: `. "$(dirname "$0")/lib/short.sh"`, then `check "invoices" "$WANT" "$(n "$R")"`. A short or refused answer prints its verdict where the figure would be, so the check fails with the engine's words. `short.sh` finds `short.py` in the `lib/` beside the running battery (`$0`); set `SHORT_PY_FILE` when it lives elsewhere.
- **Python**: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib")); from short import short`. A heredoc leg can instead `exec(open(path).read())`.
- **JS**: `import { short } from './lib/short.mjs'`.

Check a copy against its pin, locally or in the realm's CI:

    python3 battery/pin.py check ../realm-lago             # against GitHub at the pinned tag
    # or, in the realm's workflows:
    #   uses: embabel-worlds/realm-spec/.github/workflows/battery-pin.yml@main

To upgrade, run `install` again at the newer tag. Never edit `tests/lib/` in a realm: change the library here and re-pin.

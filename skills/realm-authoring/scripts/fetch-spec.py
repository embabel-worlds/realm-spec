#!/usr/bin/env python3
"""Fetch a shallow, inert checkout of the current Embabel realm specification."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_REPOSITORY = "https://github.com/embabel/realm-spec.git"
DEFAULT_REF = "main"


def fail(message: str) -> int:
    print(f"fetch-spec: {message}", file=sys.stderr)
    return 2


def run(command: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(f"{' '.join(command)}: {detail}")
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if shutil.which("git") is None:
        return fail("git is required")

    destination = args.destination
    if destination is None:
        destination = Path(tempfile.mkdtemp(prefix="realm-spec-"))
        destination.rmdir()  # git clone requires the destination not to exist.
    else:
        destination = destination.expanduser().resolve()
        if destination.exists() and any(destination.iterdir()):
            return fail(f"destination is not empty: {destination}")
        if destination.exists():
            destination.rmdir()
        destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        run(
            [
                "git",
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--branch",
                args.ref,
                "--single-branch",
                "--no-tags",
                args.repository,
                str(destination),
            ]
        )
        commit = run(["git", "rev-parse", "HEAD"], cwd=destination)
    except (OSError, RuntimeError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        return fail(str(exc))

    payload = {
        "repository": args.repository,
        "ref": args.ref,
        "commit": commit,
        "path": str(destination),
        "contract": str(destination / "README.md"),
    }
    if args.as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Realm spec: {payload['path']}")
        print(f"Commit: {commit}")
        print(f"Contract: {payload['contract']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

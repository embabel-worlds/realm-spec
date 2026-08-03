#!/usr/bin/env python3
"""Conservative structural validation for an Embabel realm repository."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by running without dependencies
    print(
        "validate-realm: PyYAML is required; install skills/realm-authoring/requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
GITHUB_TOKEN = re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")
AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
CAPABILITY_DIRECTORIES = {
    "actions", "goals", "types", "apis", "producers", "views", "lenses", "src",
    "mcp", "commands", "webhooks", "events", "handlers", "decorations", "apps",
    "prompts", "skills", "personalities", "focuses", "reference",
}
IDENTIFIED_DIRECTORIES = {
    "actions": ("name",),
    "goals": ("name",),
    "types": ("name",),
    "producers": ("name",),
    "views": ("name",),
    "lenses": ("id", "name"),
    "commands": ("command", "name"),
    # A realm may declare webhook and poll entries for the same event type.
    "events": ("name",),
    "handlers": ("name", "id"),
    "decorations": ("name", "id"),
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None


class Validator:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.findings: list[Finding] = []
        self.documents: dict[Path, Any] = {}

    def add(
        self,
        rule: str,
        severity: str,
        message: str,
        path: Path | None = None,
        line: int | None = None,
    ) -> None:
        relative = None
        if path is not None:
            try:
                relative = str(path.relative_to(self.root))
            except ValueError:
                relative = str(path)
        self.findings.append(Finding(rule, severity, message, relative, line))

    def load_yaml(self, path: Path) -> Any:
        try:
            text = path.read_text(encoding="utf-8")
            value = yaml.safe_load(text)
            self.documents[path] = value
            return value
        except UnicodeDecodeError as exc:
            self.add("YAML_ENCODING", "error", str(exc), path)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            self.add(
                "YAML_SYNTAX",
                "error",
                str(exc).splitlines()[0],
                path,
                mark.line + 1 if mark else None,
            )
        return None

    def validate(self) -> list[Finding]:
        if not self.root.is_dir():
            self.add("REALM_DIRECTORY", "error", f"not a directory: {self.root}")
            return self.findings

        yaml_paths = sorted(
            path
            for path in self.root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".yml", ".yaml"}
            and ".git" not in path.parts
            and "node_modules" not in path.parts
            and "dist" not in path.parts
        )
        for path in yaml_paths:
            self.load_yaml(path)

        self.validate_manifest()
        self.validate_capabilities()
        self.validate_duplicate_ids()
        self.validate_producer_references()
        self.validate_skills()
        self.validate_secrets()
        return sorted(
            self.findings,
            key=lambda item: (item.file or "", item.line or 0, item.rule, item.message),
        )

    def validate_manifest(self) -> None:
        path = self.root / "realm.yml"
        if not path.is_file():
            self.add("MANIFEST_REQUIRED", "error", "realm.yml is required", path)
            return
        manifest = self.documents.get(path)
        if not isinstance(manifest, dict):
            self.add("MANIFEST_MAPPING", "error", "realm.yml must contain a mapping", path)
            return

        name = manifest.get("name")
        if not isinstance(name, str) or not KEBAB.fullmatch(name):
            self.add("MANIFEST_NAME", "error", "name must be a lowercase kebab-case string", path)
        expected_directory = f"realm-{name}" if isinstance(name, str) else None
        if expected_directory and self.root.name != expected_directory:
            self.add(
                "DIRECTORY_NAME",
                "warning",
                f"repository directory should be {expected_directory!r}, found {self.root.name!r}",
                path,
            )

        if "version" in manifest:
            version = manifest["version"]
            if not isinstance(version, str) or not SEMVER.fullmatch(version):
                self.add(
                    "MANIFEST_VERSION",
                    "error",
                    "version must be a quoted semantic version such as \"0.1.0\"",
                    path,
                )

    def validate_capabilities(self) -> None:
        present = sorted(name for name in CAPABILITY_DIRECTORIES if (self.root / name).is_dir())
        if not present:
            self.add(
                "CAPABILITY_REQUIRED",
                "warning",
                "no capability directory exists yet; an installable realm needs at least one",
                self.root / "realm.yml",
            )

    def top_level_items(self, directory: str) -> list[tuple[Path, dict[str, Any]]]:
        items: list[tuple[Path, dict[str, Any]]] = []
        base = self.root / directory
        if not base.is_dir():
            return items
        for path, document in self.documents.items():
            if base not in path.parents:
                continue
            if isinstance(document, list):
                items.extend((path, item) for item in document if isinstance(item, dict))
            elif isinstance(document, dict):
                items.append((path, document))
        return items

    def validate_duplicate_ids(self) -> None:
        for directory, keys in IDENTIFIED_DIRECTORIES.items():
            seen: dict[str, Path] = {}
            for path, item in self.top_level_items(directory):
                identity = next((item.get(key) for key in keys if item.get(key) is not None), None)
                if not isinstance(identity, str) or not identity.strip():
                    continue
                if identity in seen:
                    first = seen[identity].relative_to(self.root)
                    self.add(
                        "DUPLICATE_ID",
                        "error",
                        f"duplicate {directory} id {identity!r}; first declared in {first}",
                        path,
                    )
                else:
                    seen[identity] = path

    def validate_producer_references(self) -> None:
        producers = {
            item.get("name")
            for _, item in self.top_level_items("producers")
            if isinstance(item.get("name"), str)
        }
        references: list[tuple[Path, str, str]] = []

        sources_path = self.root / "sources.yml"
        sources = self.documents.get(sources_path)
        if isinstance(sources, dict) and isinstance(sources.get("sources"), list):
            for source in sources["sources"]:
                if isinstance(source, dict) and isinstance(source.get("producer"), str):
                    references.append((sources_path, source["producer"], "source"))

        for path, item in self.top_level_items("types"):
            joins = item.get("virtualJoins")
            if not isinstance(joins, list):
                continue
            for join in joins:
                if isinstance(join, dict) and isinstance(join.get("producer"), str):
                    references.append((path, join["producer"], "virtual join"))

        for path, producer, origin in references:
            if producer not in producers:
                self.add(
                    "PRODUCER_REFERENCE",
                    "error",
                    f"{origin} references undeclared producer {producer!r}",
                    path,
                )

    def validate_skills(self) -> None:
        skills = self.root / "skills"
        if not skills.is_dir():
            return
        for path in sorted(skills.rglob("SKILL.md")):
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---\n"):
                self.add("SKILL_FRONTMATTER", "error", "SKILL.md must start with YAML frontmatter", path, 1)
                continue
            end = text.find("\n---", 4)
            if end < 0:
                self.add("SKILL_FRONTMATTER", "error", "SKILL.md frontmatter is not closed", path, 1)
                continue
            try:
                frontmatter = yaml.safe_load(text[4:end])
            except yaml.YAMLError as exc:
                self.add("SKILL_FRONTMATTER", "error", str(exc).splitlines()[0], path, 1)
                continue
            if not isinstance(frontmatter, dict):
                self.add("SKILL_FRONTMATTER", "error", "skill frontmatter must be a mapping", path, 1)
                continue
            name = frontmatter.get("name")
            if not isinstance(name, str) or len(name) > 64 or not SKILL_NAME.fullmatch(name):
                self.add("SKILL_NAME", "error", "skill name must be 1-64 lowercase kebab-case characters", path, 1)
            description = frontmatter.get("description")
            if not isinstance(description, str) or not description.strip() or len(description) > 1024:
                self.add("SKILL_DESCRIPTION", "error", "skill description must contain 1-1024 characters", path, 1)

    def validate_secrets(self) -> None:
        patterns = (
            ("SECRET_PRIVATE_KEY", PRIVATE_KEY, "private key material"),
            ("SECRET_GITHUB_TOKEN", GITHUB_TOKEN, "GitHub token-shaped value"),
            ("SECRET_AWS_KEY", AWS_KEY, "AWS access-key-shaped value"),
        )
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or ".git" in path.parts or "node_modules" in path.parts or "dist" in path.parts:
                continue
            if path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for rule, pattern, label in patterns:
                match = pattern.search(text)
                if match:
                    line = text.count("\n", 0, match.start()) + 1
                    self.add(rule, "error", f"possible committed {label}", path, line)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("realm", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = Validator(args.realm).validate()
    if args.as_json:
        print(json.dumps({"realm": str(args.realm.resolve()), "findings": [asdict(item) for item in findings]}, indent=2))
    elif findings:
        for finding in findings:
            location = finding.file or str(args.realm)
            if finding.line is not None:
                location += f":{finding.line}"
            print(f"{location}: {finding.severity} {finding.rule}: {finding.message}")
    else:
        print(f"{args.realm}: valid")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

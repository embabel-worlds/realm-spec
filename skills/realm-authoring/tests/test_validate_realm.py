from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL / "scripts" / "validate-realm.py"
FETCHER = SKILL / "scripts" / "fetch-spec.py"


class RealmValidatorTest(unittest.TestCase):
    def run_validator(self, realm: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--json", str(realm)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_accepts_a_minimal_wired_realm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            realm = Path(temporary) / "realm-demo"
            (realm / "types").mkdir(parents=True)
            (realm / "producers").mkdir()
            (realm / "realm.yml").write_text('name: demo\nversion: "0.1.0"\n', encoding="utf-8")
            (realm / "producers" / "demo.yml").write_text(
                "- name: recordsById\n  kind: remote\n  operation: getRecord\n",
                encoding="utf-8",
            )
            (realm / "types" / "demo.yml").write_text(
                "- name: DemoRecord\n"
                "  properties:\n    id: Identifier\n"
                "  virtualJoins:\n"
                "    - anchorLabel: DemoAnchor\n"
                "      relationship: HAS_RECORD\n"
                "      keyField: id\n"
                "      producer: recordsById\n",
                encoding="utf-8",
            )

            result = self.run_validator(realm)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual([], json.loads(result.stdout)["findings"])

    def test_reports_syntax_duplicates_missing_references_and_bad_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            realm = Path(temporary) / "realm-broken"
            (realm / "types").mkdir(parents=True)
            (realm / "producers").mkdir()
            (realm / "realm.yml").write_text("name: broken\nversion: 0.1\n", encoding="utf-8")
            (realm / "producers" / "broken.yml").write_text("items: [\n", encoding="utf-8")
            (realm / "types" / "one.yml").write_text(
                "- name: Record\n  virtualJoins:\n    - producer: absent\n",
                encoding="utf-8",
            )
            (realm / "types" / "two.yml").write_text("- name: Record\n", encoding="utf-8")

            result = self.run_validator(realm)
            rules = {finding["rule"] for finding in json.loads(result.stdout)["findings"]}

            self.assertEqual(1, result.returncode)
            self.assertTrue(
                {"YAML_SYNTAX", "DUPLICATE_ID", "PRODUCER_REFERENCE", "MANIFEST_VERSION"}.issubset(rules),
                rules,
            )

    def test_reports_skill_frontmatter_and_secret_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            realm = Path(temporary) / "realm-demo"
            (realm / "types").mkdir(parents=True)
            (realm / "skills" / "bad").mkdir(parents=True)
            (realm / "realm.yml").write_text("name: demo\n", encoding="utf-8")
            (realm / "types" / "demo.yml").write_text("- name: Demo\n", encoding="utf-8")
            (realm / "skills" / "bad" / "SKILL.md").write_text("# Missing frontmatter\n", encoding="utf-8")
            token_shaped_value = "github" + "_pat_abcdefghijklmnopqrstuvwxyz1234567890"
            (realm / "notes.txt").write_text(token_shaped_value + "\n", encoding="utf-8")

            result = self.run_validator(realm)
            rules = {finding["rule"] for finding in json.loads(result.stdout)["findings"]}

            self.assertEqual(1, result.returncode)
            self.assertIn("SKILL_FRONTMATTER", rules)
            self.assertIn("SECRET_GITHUB_TOKEN", rules)


class FetchSpecTest(unittest.TestCase):
    def test_fetches_requested_ref_and_reports_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "checkout"
            source.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
            (source / "README.md").write_text("# Test realm spec\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True)
            expected_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

            result = subprocess.run(
                [
                    sys.executable,
                    str(FETCHER),
                    "--repository",
                    str(source),
                    "--ref",
                    "main",
                    "--destination",
                    str(destination),
                    "--json",
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(expected_commit, payload["commit"])
            self.assertEqual(destination.resolve(), Path(payload["path"]))
            self.assertTrue((destination / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()

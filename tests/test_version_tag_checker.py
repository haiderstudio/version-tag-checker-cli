#!/usr/bin/env python3
"""Tests for version_tag_checker. Standard library unittest only."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src" / "version_tag_checker.py"

sys.path.insert(0, str(ROOT / "src"))

import version_tag_checker as vtc  # noqa: E402


def run_cli(*args, input_text=None, cwd=None):
    """Run the CLI as a subprocess. Returns (exit code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SRC), *args],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=cwd or str(ROOT),
    )
    return proc.returncode, proc.stdout, proc.stderr


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


class TestVersionProblem(unittest.TestCase):
    def test_good_versions_pass(self):
        for value in [
            "1.2.3", "v1.2.3", "0.0.0", "10.20.30",
            "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-0.3.7",
            "1.0.0+build.1", "1.0.0-alpha+001",
        ]:
            with self.subTest(value=value):
                self.assertIsNone(vtc.version_problem(value), value)

    def test_bad_versions_fail(self):
        for value, reason in [
            ("1.2", "does not follow MAJOR.MINOR.PATCH"),
            ("1", "does not follow MAJOR.MINOR.PATCH"),
            ("01.2.3", "does not follow MAJOR.MINOR.PATCH"),
            ("1.2.3.4", "does not follow MAJOR.MINOR.PATCH"),
            ("release-2", "does not follow MAJOR.MINOR.PATCH"),
            ("v1.2.3-", "does not follow MAJOR.MINOR.PATCH"),
            ("", "no version found"),
            (None, "no version found"),
        ]:
            with self.subTest(value=value):
                self.assertEqual(vtc.version_problem(value), reason)

    def test_normalise_strips_v(self):
        self.assertEqual(vtc.normalise("v1.2.3"), "1.2.3")
        self.assertEqual(vtc.normalise("1.2.3"), "1.2.3")
        self.assertEqual(vtc.normalise("  v2.0.0 "), "2.0.0")


class TestReadVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_plain_version_file(self):
        path = write(self.tmp.name, "VERSION", "1.2.3\n")
        self.assertEqual(vtc.read_version(path), ("1.2.3", 1, None))

    def test_plain_skips_blanks_and_comments(self):
        path = write(self.tmp.name, "VERSION", "\n# release\n\nv2.0.0\n")
        self.assertEqual(vtc.read_version(path), ("v2.0.0", 4, None))

    def test_plain_empty_file(self):
        path = write(self.tmp.name, "VERSION", "")
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertEqual(problem, "no version found")

    def test_plain_non_utf8(self):
        path = Path(self.tmp.name) / "VERSION"
        path.write_bytes(b"\xff\xfe1.2.3\n")
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertEqual(problem, "file is not valid UTF-8")

    def test_json_version_key(self):
        path = write(self.tmp.name, "package.json",
                     '{\n  "name": "demo",\n  "version": "1.2.3"\n}\n')
        self.assertEqual(vtc.read_version(path), ("1.2.3", 3, None))

    def test_json_missing_key(self):
        path = write(self.tmp.name, "package.json", '{"name": "demo"}\n')
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertIn('no "version" key found', problem)

    def test_json_nested_key(self):
        path = write(self.tmp.name, "package.json",
                     '{"meta": {"version": "3.4.5"}}\n')
        value, line, problem = vtc.read_version(
            path, json_key="meta.version")
        self.assertEqual((value, problem), ("3.4.5", None))

    def test_json_bad_json(self):
        path = write(self.tmp.name, "package.json", '{"version": \n')
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertTrue(problem.startswith("not valid JSON"))

    def test_json_non_text_version(self):
        path = write(self.tmp.name, "package.json", '{"version": 123}\n')
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertIn("not a text value", problem)

    def test_toml_project_version(self):
        path = write(self.tmp.name, "pyproject.toml",
                     '[project]\nname = "demo"\nversion = "1.2.3"\n')
        self.assertEqual(vtc.read_version(path), ("1.2.3", 3, None))

    def test_toml_poetry_version(self):
        path = write(self.tmp.name, "pyproject.toml",
                     '[tool.poetry]\nname = "demo"\nversion = "0.9.0"\n')
        self.assertEqual(vtc.read_version(path), ("0.9.0", 3, None))

    def test_toml_no_version(self):
        path = write(self.tmp.name, "pyproject.toml",
                     '[project]\nname = "demo"\n')
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertIn("no version found", problem)

    def test_toml_bad_toml(self):
        path = write(self.tmp.name, "pyproject.toml", '[project\n')
        value, line, problem = vtc.read_version(path)
        self.assertIsNone(value)
        self.assertTrue(problem.startswith("not valid TOML"))

    def test_pattern_read(self):
        path = write(self.tmp.name, "__init__.py",
                     '__version__ = "1.2.3"\n')
        value, line, problem = vtc.read_version(
            path, kind="pattern",
            pattern=r'__version__\s*=\s*"([^"]+)"')
        self.assertEqual((value, line, problem), ("1.2.3", 1, None))

    def test_pattern_no_match(self):
        path = write(self.tmp.name, "__init__.py", 'x = 1\n')
        value, line, problem = vtc.read_version(
            path, kind="pattern", pattern=r'version = "([^"]+)"')
        self.assertIsNone(value)
        self.assertEqual(problem, "pattern did not match any line")

    def test_pattern_without_capture_group(self):
        path = write(self.tmp.name, "__init__.py", 'version = "1.2.3"\n')
        value, line, problem = vtc.read_version(
            path, kind="pattern", pattern=r"version")
        self.assertIsNone(value)
        self.assertEqual(problem, "pattern has no capture group")

    def test_kind_override(self):
        path = write(self.tmp.name, "data.txt", "1.2.3\n")
        self.assertEqual(
            vtc.read_version(path, kind="version"), ("1.2.3", 1, None))


class TestCheckPair(unittest.TestCase):
    def test_match(self):
        self.assertEqual(
            vtc.check_pair(("1.2.3", 1, None), ("v1.2.3", 1, None)), [])

    def test_mismatch(self):
        problems = vtc.check_pair(("1.2.3", 1, None), ("1.2.4", 1, None))
        self.assertEqual(len(problems), 1)
        self.assertIn("versions differ: 1.2.3 and 1.2.4", problems[0])

    def test_prerelease_differs(self):
        problems = vtc.check_pair(
            ("1.2.3", 1, None), ("1.2.3-alpha", 1, None))
        self.assertEqual(len(problems), 1)

    def test_bad_format_reported(self):
        problems = vtc.check_pair(("1.2", 1, None), ("1.2.3", 1, None))
        self.assertIn("first version: does not follow MAJOR.MINOR.PATCH",
                      problems)

    def test_missing_version_reported(self):
        problems = vtc.check_pair(
            (None, None, "no version found"), ("1.2.3", 1, None))
        self.assertIn("no version found", problems)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def pair(self, text_a, text_b, name_a="a.txt", name_b="b.txt"):
        path_a = write(self.tmp.name, name_a, text_a)
        path_b = write(self.tmp.name, name_b, text_b)
        return str(path_a), str(path_b)

    def test_matching_pair_exits_zero(self):
        a, b = self.pair("1.2.3\n", "v1.2.3\n")
        code, out, err = run_cli(a, b)
        self.assertEqual(code, 0)
        self.assertIn("PASS   versions match: 1.2.3", out)

    def test_mismatch_exits_one(self):
        a, b = self.pair("1.2.3\n", "1.3.0\n")
        code, out, err = run_cli(a, b)
        self.assertEqual(code, 1)
        self.assertIn("FAIL   versions differ: 1.2.3 and 1.3.0", out)

    def test_flags_a_and_b(self):
        a, b = self.pair("1.2.3\n", "1.2.3\n")
        code, out, err = run_cli("--a", a, "--b", b)
        self.assertEqual(code, 0)
        self.assertIn("PASS", out)

    def test_missing_file_exits_two(self):
        code, out, err = run_cli("nope.txt", "alsono.txt")
        self.assertEqual(code, 2)
        self.assertIn("file not found", err)

    def test_one_file_only_exits_two(self):
        a, _b = self.pair("1.2.3\n", "1.2.3\n")
        code, out, err = run_cli(a)
        self.assertEqual(code, 2)
        self.assertIn("give two files", err)

    def test_bad_flag_exits_two(self):
        code, out, err = run_cli("--nope")
        self.assertEqual(code, 2)

    def test_json_output_parses(self):
        a, b = self.pair("1.2.3\n", "1.3.0\n")
        code, out, err = run_cli("--json", a, b)
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["match"])
        self.assertEqual(data["first"]["version"], "1.2.3")
        self.assertEqual(data["second"]["version"], "1.3.0")
        self.assertIn("FAIL", err)

    def test_json_output_match(self):
        a, b = self.pair("1.2.3\n", "1.2.3\n")
        code, out, err = run_cli("--json", a, b)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["match"])
        self.assertEqual(data["problems"], [])
        self.assertIn("PASS", err)

    def test_version_flag(self):
        code, out, err = run_cli("--version")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "1.0.0")

    def test_input_files_unchanged(self):
        a, b = self.pair("1.2.3\n", "1.3.0\n")
        run_cli(a, b)
        self.assertEqual(Path(a).read_text(), "1.2.3\n")
        self.assertEqual(Path(b).read_text(), "1.3.0\n")

    def test_git_tag_match(self):
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"],
                       cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.name", "t"],
                       cwd=str(repo), check=True)
        (repo / "VERSION").write_text("1.2.3\n")
        subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-qm", "x"], cwd=str(repo),
                       check=True)
        subprocess.run(["git", "tag", "v1.2.3"], cwd=str(repo), check=True)
        code, out, err = run_cli("--git-tag", "VERSION", cwd=str(repo))
        self.assertEqual(code, 0)
        self.assertIn("PASS", out)

    def test_git_tag_mismatch(self):
        repo = Path(self.tmp.name) / "repo2"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"],
                       cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.name", "t"],
                       cwd=str(repo), check=True)
        (repo / "VERSION").write_text("1.2.4\n")
        subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-qm", "x"], cwd=str(repo),
                       check=True)
        subprocess.run(["git", "tag", "v1.2.3"], cwd=str(repo), check=True)
        code, out, err = run_cli("--git-tag", "VERSION", cwd=str(repo))
        self.assertEqual(code, 1)
        self.assertIn("versions differ: 1.2.4 and v1.2.3", out)

    def test_git_tag_no_tags(self):
        repo = Path(self.tmp.name) / "repo3"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        (repo / "VERSION").write_text("1.2.3\n")
        code, out, err = run_cli("--git-tag", "VERSION", cwd=str(repo))
        self.assertEqual(code, 1)
        self.assertIn("no git tags in this repo", out)

    def test_git_tag_not_a_repo(self):
        write(self.tmp.name, "VERSION", "1.2.3\n")
        code, out, err = run_cli("--git-tag", "VERSION", cwd=self.tmp.name)
        self.assertEqual(code, 1)
        self.assertIn("not a git repo", out)


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        proc = subprocess.run(
            ["sh", "examples/run-example.sh"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0)
        committed = (ROOT / "examples" / "sample-output.txt").read_text()
        self.assertEqual(proc.stdout, committed)

    def test_readme_quoted_outputs_are_real(self):
        readme = (ROOT / "README.md").read_text()
        for snippet in [
            "PASS   versions match: 1.2.3",
            "FAIL   versions differ: 1.3.0 and v1.2.3",
            "FAIL   second version: does not follow MAJOR.MINOR.PATCH",
        ]:
            self.assertIn(snippet, readme)
        sample = (ROOT / "examples" / "sample-output.txt").read_text()
        for snippet in [
            "PASS   versions match: 1.2.3",
            "FAIL   versions differ: 1.3.0 and v1.2.3",
            "FAIL   second version: does not follow MAJOR.MINOR.PATCH",
        ]:
            self.assertIn(snippet, sample)


class TestHygiene(unittest.TestCase):
    """Repo hygiene: no placeholders, no secrets, stdlib only."""

    def test_no_placeholder_text(self):
        banned = ["TODO", "FIXME", "coming soon", "lorem", "placeholder"]
        bad = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            if path.suffix in (".pyc",):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, ValueError):
                continue
            for word in banned:
                if word in text:
                    bad.append("%s: %s" % (path.relative_to(ROOT), word))
        self.assertEqual(bad, [])

    def test_no_absolute_paths_or_secrets(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, ValueError):
                continue
            self.assertNotIn("/home/hatch", text, str(path))
            self.assertNotIn("api_key", text.lower(), str(path))

    def test_stdlib_only_imports(self):
        allowed = {
            "argparse", "json", "re", "subprocess", "sys", "tomllib",
            "pathlib", "unittest", "tempfile", "os", "ast",
            "version_tag_checker",
        }
        import ast
        for path in [ROOT / "src" / "version_tag_checker.py",
                     HERE / "test_version_tag_checker.py"]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], allowed,
                                      str(path))
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn((node.module or "").split(".")[0],
                                  allowed, str(path))


if __name__ == "__main__":
    unittest.main()

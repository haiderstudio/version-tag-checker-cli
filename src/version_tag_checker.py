#!/usr/bin/env python3
"""Check the version tag in one file matches the other, fail CI on a mismatch.

Run: python3 src/version_tag_checker.py pyproject.toml VERSION
     python3 src/version_tag_checker.py --a package.json --b VERSION
     python3 src/version_tag_checker.py --git-tag pyproject.toml

The tool reads a version from each of two files and compares them.
A version looks like 1.2.3, with an optional leading "v" and optional
prerelease or build parts (1.2.3-alpha.1, 1.2.3+build.1). "1.2.3" and
"v1.2.3" are the same version; "1.2.3" and "1.2.4" are not. It prints
PASS or FAIL with both values, names the file and line each version
came from, and exits 1 on a mismatch — so it can fail a CI run.

How a version is read depends on the file:
- package.json (or any .json file): the "version" key, or the dotted
  key named by --json-key.
- pyproject.toml (or any .toml file): [project] version, or
  [tool.poetry] version when that is the one present.
- A plain VERSION file (or any other file): the first line that is
  not blank and not a "#" comment.
- Any file with --pattern REGEX: the first line whose text matches
  the pattern; the first capture group is the version. This covers
  files like "__version__ = \"1.2.3\"" in a Python module.

--git-tag compares one file's version against the latest git tag in
the current repo instead of a second file. The latest tag is the
highest version tag git knows (git tag --sort=-v:refname, first one).

It is report-only and runs fully offline: it never edits a file,
never bumps a version, never moves a tag, sends nothing anywhere,
and needs no API key.

Exit codes: 0 when the versions match, 1 when they disagree or a
version is missing or badly formed, 2 for a usage or input problem
(missing file, not a git repo, no tags to compare).

Python standard library only.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION = "1.0.0"

VERSION_RE = re.compile(
    r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def version_problem(value):
    """Return None when value is a well formed version, else a reason."""
    if value is None or value == "":
        return "no version found"
    if not VERSION_RE.match(value.strip()):
        return "does not follow MAJOR.MINOR.PATCH"
    return None


def normalise(value):
    """Strip a leading "v" so "v1.2.3" and "1.2.3" compare equal."""
    return value.strip()[1:] if value.strip().startswith("v") else value.strip()


def _line_of(lines, needle, start=0):
    for index in range(start, len(lines)):
        if needle in lines[index]:
            return index + 1
    return None


def read_plain(path):
    """Read a plain version file: first non-blank, non-comment line."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, None, "file is not valid UTF-8"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        return stripped, index + 1, None
    return None, None, "no version found"


def read_json(path, key="version"):
    """Read a version from a JSON file, by dotted key (default: version)."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, None, "file is not valid UTF-8"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, exc.lineno, "not valid JSON: %s" % exc.msg
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, None, 'no "%s" key found' % key
        node = node[part]
    if not isinstance(node, str):
        return None, None, '"%s" is not a text value' % key
    lines = text.splitlines()
    line_no = _line_of(lines, '"%s"' % key.split(".")[-1])
    return node.strip(), line_no, None


def read_toml(path):
    """Read a version from a TOML file: [project] or [tool.poetry]."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, str(exc)
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return None, None, "not valid TOML: %s" % exc
    value = None
    if isinstance(data.get("project"), dict):
        value = data["project"].get("version")
    if value is None and isinstance(data.get("tool"), dict):
        poetry = data["tool"].get("poetry")
        if isinstance(poetry, dict):
            value = poetry.get("version")
    if value is None:
        return None, None, "no version found under [project] or [tool.poetry]"
    if not isinstance(value, str):
        return None, None, "version is not a text value"
    lines = raw.decode("utf-8").splitlines()
    line_no = None
    in_section = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped in ("[project]", "[tool.poetry]")
            continue
        if in_section and re.match(r"version\s*=", stripped):
            line_no = index + 1
            break
    if line_no is None:
        line_no = _line_of(lines, "version")
    return value.strip(), line_no, None


def read_pattern(path, pattern):
    """Read a version with a regex: the first capture group is the version."""
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return None, None, "bad pattern: %s" % exc
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, None, "file is not valid UTF-8"
    for index, line in enumerate(text.splitlines()):
        match = compiled.search(line)
        if match:
            if not match.groups():
                return None, index + 1, "pattern has no capture group"
            return match.group(1).strip(), index + 1, None
    return None, None, "pattern did not match any line"


def detect_kind(path):
    """Guess how to read a version from the file name."""
    name = path.name.lower()
    if name.endswith(".json"):
        return "json"
    if name.endswith(".toml"):
        return "toml"
    return "version"


def read_version(path, kind=None, json_key="version", pattern=None):
    """Read one version. Returns (value, line_no, problem_or_None)."""
    kind = kind or detect_kind(path)
    if kind == "json":
        return read_json(path, json_key)
    if kind == "toml":
        return read_toml(path)
    if kind == "pattern":
        if pattern is None:
            return None, None, "--pattern is needed for kind pattern"
        return read_pattern(path, pattern)
    return read_plain(path)


def latest_git_tag(cwd):
    """Return (tag, problem_or_None) for the highest version tag."""
    try:
        proc = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
    except FileNotFoundError:
        return None, "git is not installed"
    if proc.returncode != 0:
        return None, "not a git repo (git tag failed)"
    tags = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not tags:
        return None, "no git tags in this repo"
    return tags[0], None


def check_pair(first, second):
    """Compare two (value, line, problem) reads. Returns a list of problems."""
    problems = []
    value_a, _line_a, problem_a = first
    value_b, _line_b, problem_b = second
    if problem_a is not None:
        problems.append(problem_a)
    if problem_b is not None:
        problems.append(problem_b)
    if problems:
        return problems
    bad_a = version_problem(value_a)
    bad_b = version_problem(value_b)
    if bad_a is not None:
        problems.append("first version: %s" % bad_a)
    if bad_b is not None:
        problems.append("second version: %s" % bad_b)
    if problems:
        return problems
    if normalise(value_a) != normalise(value_b):
        problems.append(
            "versions differ: %s and %s" % (value_a.strip(), value_b.strip())
        )
    return problems


def describe(path, read):
    """One line naming where a version came from, for the report."""
    value, line_no, problem = read
    if problem is not None:
        return "%s: %s" % (path, problem)
    where = "line %d" % line_no if line_no else "unknown line"
    return "%s: %s (%s)" % (path, value.strip(), where)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="version_tag_checker",
        description="Check the version tag in one file matches the other.",
    )
    parser.add_argument("files", nargs="*", help="two files to compare")
    parser.add_argument("--a", dest="a", help="first file to compare")
    parser.add_argument("--b", dest="b", help="second file to compare")
    parser.add_argument("--kind1", choices=["version", "json", "toml", "pattern"])
    parser.add_argument("--kind2", choices=["version", "json", "toml", "pattern"])
    parser.add_argument("--json-key", default="version",
                        help="dotted key for JSON files (default: version)")
    parser.add_argument("--pattern",
                        help="regex whose first capture group is the version")
    parser.add_argument("--git-tag", metavar="FILE",
                        help="compare FILE's version against the latest git tag")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--version", action="store_true",
                        help="print the tool version and exit")
    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0

    if args.git_tag:
        if args.files or args.a or args.b:
            print("error: --git-tag takes one file only",
                  file=sys.stderr)
            return 2
        file_path = Path(args.git_tag)
        if not file_path.is_file():
            print("error: file not found: %s" % file_path, file=sys.stderr)
            return 2
        read = read_version(file_path, args.kind1, args.json_key, args.pattern)
        tag, tag_problem = latest_git_tag(Path.cwd())
        second = (tag, None, tag_problem)
        label_a = str(file_path)
        label_b = "latest git tag"
        pair = (read, second)
    else:
        positional = list(args.files)
        if args.a or args.b:
            if positional or not args.a or not args.b:
                print("error: use either two files or --a and --b",
                      file=sys.stderr)
                return 2
            positional = [args.a, args.b]
        if len(positional) != 2:
            print("error: give two files to compare, or --git-tag FILE",
                  file=sys.stderr)
            return 2
        path_a, path_b = Path(positional[0]), Path(positional[1])
        for path in (path_a, path_b):
            if not path.is_file():
                print("error: file not found: %s" % path, file=sys.stderr)
                return 2
        read_a = read_version(path_a, args.kind1, args.json_key, args.pattern)
        read_b = read_version(path_b, args.kind2, args.json_key, args.pattern)
        label_a, label_b = str(path_a), str(path_b)
        pair = (read_a, read_b)

    problems = check_pair(pair[0], pair[1])

    if args.json:
        value_a, line_a, _ = pair[0]
        value_b, line_b, _ = pair[1]
        result = {
            "first": {"file": label_a, "version": value_a, "line": line_a},
            "second": {"file": label_b, "version": value_b, "line": line_b},
            "match": not problems,
            "problems": problems,
        }
        print(json.dumps(result, indent=2))
        print("FAIL: %s" % "; ".join(problems) if problems else "PASS: versions match",
              file=sys.stderr)
        return 1 if problems else 0

    print(describe(label_a, pair[0]))
    print(describe(label_b, pair[1]))
    if problems:
        for problem in problems:
            print("FAIL   %s" % problem)
        return 1
    print("PASS   versions match: %s" % normalise(pair[0][0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

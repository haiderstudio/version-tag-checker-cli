# version-tag-checker-cli

Check the version tag in one file matches the other, fail CI on a mismatch.

[![CI](https://github.com/haiderstudio/version-tag-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/version-tag-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`version_tag_checker` reads a version from each of two files and
checks they agree. A version looks like `1.2.3`, with an optional
leading `v` and optional prerelease or build parts
(`1.2.3-alpha.1`, `1.2.3+build.1`). `1.2.3` and `v1.2.3` are the
same version; `1.2.3` and `1.3.0` are not. It prints both values
with the file and line each came from, prints `PASS` or `FAIL`,
and exits 1 on a mismatch — so it can fail a CI run.

- It reads the version the way each file stores it:
  `package.json` (or any `.json` file) from the `version` key,
  `pyproject.toml` (or any `.toml` file) from `[project] version`
  or `[tool.poetry] version`, and a plain `VERSION` file from
  its first line that is not blank and not a `#` comment.
  `--pattern REGEX` reads a version from any other file — the
  first capture group is the version, so
  `__version__ = "1.2.3"` in a Python module works too.
- `--json-key` names a different dotted key in a JSON file, and
  `--kind1` / `--kind2` force how each file is read when the
  file name alone does not say enough.
- `--git-tag FILE` compares one file's version against the
  latest git tag in the current repo instead of a second file.
  The latest tag is the highest version tag git knows.
- A version that does not follow `MAJOR.MINOR.PATCH` fails with
  its reason, and a file with no version at all fails too —
  so a missing or broken version is never a silent pass.
- It is report-only and runs fully offline: it never edits a
  file, never bumps a version, never moves a tag, sends nothing
  anywhere, and needs no API key.

## What it does NOT do

- It does not bump a version, sync versions between files, or
  move a tag. A mismatch is reported; fixing it is your job.
- It does not check whether a version is the right one to
  release, whether a changelog mentions it, or whether a
  release exists for it — agreement between the two sources
  only.
- It does not check the shape of a git tag on its own. (That
  is the job of
  [git-tag-checker-cli](https://github.com/haiderstudio/git-tag-checker-cli).)
- It does not talk to GitHub or any remote. `--git-tag` reads
  only the local tags in the folder you run it in.

## Who it is for

Any project that keeps the same version in more than one place
and keeps finding them out of step: a developer who bumps
`pyproject.toml` and forgets `VERSION`, a maintainer adding a
CI step that fails the build when the package file and the
release file disagree, or anyone who tags a release and wants
proof the file and the tag say the same thing. If the versions
match, you get a clean report; if they do not, the report says
both values and where each came from.

## How this differs from similar tools

The quoted GitHub search for `"version-tag-checker-cli"`
returns 0 results, and `"version-tag-checker"` returns 0 too.
The unquoted search `version tag checker` returns 18 results,
and the top one is
jessehouwing/actions-semver-checker, 14 stars — a GitHub Action
that checks version TAGS for semver behaviour (tag shape, not
file-vs-file agreement, a different job). The rest are game
mods and tag checkers for other software. The search
`version mismatch checker` returns 7 results; the closest is
VersionGuard, 1 star — a checker that scans project
dependencies for version mismatches (dependencies, not your
own two version files). The search `version sync cli` returns
159 results, mostly noise; the closest real one is
bjesuiter/capacitor-sync-version-cli, 5 stars — it SYNCS the
npm package version into other files, rewriting them, which
is the opposite of a report-only check.

This tool does a narrower job: a Python standard-library-only
CLI that reads a version from two local files (or one file and
the latest git tag), reports both values with file and line,
and exits 1 for CI — no install beyond Python, no Action, no
remote, and it never changes a file.

## Install

Python standard library only — no packages to download. Clone
the repo and run it in place:

```sh
git clone https://github.com/haiderstudio/version-tag-checker-cli.git
cd version-tag-checker-cli
```

Python 3.10 or newer. Git is only needed for `--git-tag`;
comparing two files works without git.

## Usage

Compare a `pyproject.toml` with a `VERSION` file:

```sh
python3 src/version_tag_checker.py pyproject.toml VERSION
```

Real output, when they match:

```text
pyproject.toml: 1.2.3 (line 3)
VERSION: 1.2.3 (line 1)
PASS   versions match: 1.2.3
```

The command exits 0.

Compare a `package.json` with a `VERSION` file:

```sh
python3 src/version_tag_checker.py package.json VERSION
```

Real output, when they do not match:

```text
package.json: 1.3.0 (line 3)
VERSION: v1.2.3 (line 1)
FAIL   versions differ: 1.3.0 and v1.2.3
```

The command exits 1.

Compare one file against the latest git tag:

```sh
python3 src/version_tag_checker.py --git-tag pyproject.toml
```

Real output, when the tag and the file agree:

```text
pyproject.toml: 1.2.3 (line 3)
latest git tag: v1.2.3 (unknown line)
PASS   versions match: 1.2.3
```

The command exits 0.

Read a version out of a Python module with a pattern:

```sh
python3 src/version_tag_checker.py --kind1 pattern --pattern '__version__ = "([^"]+)"' src/mypackage/__init__.py VERSION
```

The first capture group of the pattern is the version. With
`--json`, the result is printed as JSON and the one-line
summary goes to standard error:

```sh
python3 src/version_tag_checker.py --json pyproject.toml VERSION
```

```text
{
  "first": {
    "file": "pyproject.toml",
    "version": "1.2.3",
    "line": 3
  },
  "second": {
    "file": "VERSION",
    "version": "1.2.3",
    "line": 1
  },
  "match": true,
  "problems": []
}
```

## Examples

### 1. Matching versions — `pyproject.toml` and `VERSION`

```sh
python3 src/version_tag_checker.py examples/matching/pyproject.toml examples/matching/VERSION
```

```text
examples/matching/pyproject.toml: 1.2.3 (line 3)
examples/matching/VERSION: 1.2.3 (line 1)
PASS   versions match: 1.2.3
```

The command exits 0.

### 2. Mismatched versions — `package.json` and `VERSION`

```sh
python3 src/version_tag_checker.py examples/mismatched/package.json examples/mismatched/VERSION
```

```text
examples/mismatched/package.json: 1.3.0 (line 3)
examples/mismatched/VERSION: v1.2.3 (line 1)
FAIL   versions differ: 1.3.0 and v1.2.3
```

The command exits 1.

### 3. A bad version format

```sh
python3 src/version_tag_checker.py examples/bad-format/pyproject.toml examples/bad-format/VERSION
```

```text
examples/bad-format/pyproject.toml: 1.2.3 (line 3)
examples/bad-format/VERSION: 1.2 (line 1)
FAIL   second version: does not follow MAJOR.MINOR.PATCH
```

The command exits 1. A version with only two parts is not a
version this tool accepts — it fails with its reason instead
of passing quietly.

## How it is tested

```sh
python3 tests/test_version_tag_checker.py
```

44 tests, standard library `unittest` only — no third-party
packages. They cover: the version shape (good versions,
missing parts, too many parts, leading zeros, prerelease and
build parts), reading versions (plain files, blank lines and
comments, JSON keys including a nested key, bad JSON, TOML
`[project]` and `[tool.poetry]`, bad TOML, regex patterns,
missing files, non-UTF-8 files), comparing two files
(match, mismatch, prerelease difference, bad format, missing
version), the CLI (exit 0/1/2, `--a`/`--b`, `--json` output,
`--version`, bad flags, input files left unchanged),
`--git-tag` in a real temporary git repo (match, mismatch, no
tags, not a repo), the bundled examples (the committed
`examples/sample-output.txt` is compared against a fresh run,
the example script, and every line the README quotes is
checked against the real output), and a check that the code
and the tests import standard library only.

The bundled example is a real run, not made-up output:

```sh
sh examples/run-example.sh
```

It checks the matching pair, the mismatched pair, and the
bad-format pair. The mismatch and bad-format checks exit 1 on
purpose — that is the expected result here.

## Contributing

Small, focused improvements are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Built from scratch for this repo. The version shape follows
semantic versioning as documented at semver.org; no code was
copied from any existing version checker.

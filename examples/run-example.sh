#!/bin/sh
# Run the checker on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The mismatch and bad-format checks exit 1 on purpose — that is
# the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- matching versions ---"
python3 src/version_tag_checker.py examples/matching/pyproject.toml examples/matching/VERSION || true
echo "--- mismatched versions ---"
python3 src/version_tag_checker.py examples/mismatched/package.json examples/mismatched/VERSION || true
echo "--- bad version format ---"
python3 src/version_tag_checker.py examples/bad-format/pyproject.toml examples/bad-format/VERSION || true

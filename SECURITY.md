# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the version files you name (and the local git tags of the repo you run it in, for `--git-tag`), and it never edits a file, never bumps a version, never moves a tag, and never changes a file. It writes nothing except the report on standard output (and usage errors on standard error).

If you find a case where the tool changes a file or a tag, or reports a pass for versions that do not match, please open an issue describing the exact commands and input. Do not include any real secret in the report.

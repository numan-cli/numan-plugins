---
kind: logging_system
name: Minimal stdout/stderr CLI logging pattern
category: logging_system
scope:
    - '**'
source_files:
    - scripts/package_plugin.py
    - scripts/gen_spec.py
    - scripts/release_transaction.py
    - scripts/validate_manifest.py
    - scripts/ensure_release_absent.py
---

The repository does not use a dedicated logging framework. All scripts in `scripts/` rely on Python's built-in `print()` to write human-readable status and error messages directly to stdout or stderr, with no structured log format, log levels, or centralized logger configuration.

**What system/approach is used**
- Plain `print(...)` calls for all output.
- Success/informational messages go to stdout; error/failure messages are written to `sys.stderr` via `print(..., file=sys.stderr)`.
- Machine-parseable output uses a simple tab-separated prefix convention: the string `PACKAGED\t<target>\t<filename>\t<sha256>\t<exe>` emitted by `package_plugin.py` is consumed downstream by `gen_spec.py`.
- Exit codes follow the Unix convention: `0` for success, `1` for failure, propagated through `raise SystemExit(main())` at each script's entry point.

**Key files and packages**
- `scripts/package_plugin.py` — emits `PACKAGED\t...` lines on stdout and diagnostic info on stderr.
- `scripts/gen_spec.py` — parses the `PACKAGED\t...` TSV stream, prints `FAIL:` messages to stderr on validation errors.
- `scripts/release_transaction.py` — prints `FAIL:`, `release is not the claimed draft; refusing cleanup`, and `release tag ownership changed; refusing cleanup` to stderr.
- `scripts/validate_manifest.py` — prints `OK: ...` and `FAIL: ...` lines to stderr.
- `scripts/ensure_release_absent.py` — prints `OK:` / `FAIL:` to stderr.

**Architecture and conventions**
- Each script is self-contained with its own `argparse` CLI and a `main() -> int` function that returns an exit code.
- Error paths consistently print a `FAIL: <message>` line to stderr and return `1`; success paths print an `OK:` or descriptive line to stderr (or stdout for machine-consumed data) and return `0`.
- No shared logging module exists; every script duplicates this pattern inline.
- There is no log-level configuration, no rotation, no sinks, and no structured JSON logs — output is intentionally minimal and human/machine readable for CI pipeline consumption.
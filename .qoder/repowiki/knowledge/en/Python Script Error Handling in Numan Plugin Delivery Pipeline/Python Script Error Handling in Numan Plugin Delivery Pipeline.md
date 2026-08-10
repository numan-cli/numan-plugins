---
kind: error_handling
name: Python Script Error Handling in Numan Plugin Delivery Pipeline
category: error_handling
scope:
    - '**'
source_files:
    - scripts/ensure_release_absent.py
    - scripts/gen_spec.py
    - scripts/release_transaction.py
    - scripts/package_plugin.py
    - scripts/validate_manifest.py
---

The Numan Plugin Binary Delivery Pipeline uses a consistent, structured error handling approach across all Python scripts in the `scripts/` directory. The codebase follows a clear pattern for defining, propagating, and presenting errors without relying on custom exception hierarchies or external logging frameworks.

**Error Types and Propagation Pattern**

All scripts use standard Python exceptions with specific semantics:
- `ValueError`: Used for validation failures, data integrity issues, and business logic violations (e.g., missing manifest fields, duplicate targets, hash mismatches)
- `RuntimeError`: Used for external system failures, particularly GitHub API operations that don't return expected results
- `subprocess.TimeoutExpired`: Explicitly caught when calling external commands like `gh` and `git`
- `SystemExit(1)`: Used as an immediate exit strategy in validation functions that encounter fatal parsing errors

Each script follows a uniform structure: core logic raises descriptive exceptions, while the `main()` function catches these exceptions, prints a standardized "FAIL:" message to stderr, and returns exit code 1. Successful execution returns 0 via `raise SystemExit(main())`.

**Consistent CLI Error Handling**

Every script implements the same CLI error pattern:
```python
def main(argv: list[str] | None = None) -> int:
    try:
        # ... operation logic ...
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: ...", file=sys.stderr)
    return 0
```

This pattern ensures consistent error reporting across all pipeline stages, making it easy to parse failure reasons in CI/CD workflows.

**External Command Error Handling**

Scripts that call external tools (`gh`, `git`) use a wrapper pattern with timeouts and explicit error checking:
- All subprocess calls use `check=False` with manual return code inspection
- A `COMMAND_TIMEOUT_SECONDS = 30` constant prevents hanging operations
- JSON responses are parsed with `json.loads()` wrapped in try/except blocks
- Network failures produce descriptive `RuntimeError` messages containing stderr output

**Transaction Safety Pattern**

The `release_transaction.py` script demonstrates sophisticated error recovery for multi-step operations:
- Draft release creation includes automatic cleanup of created tags if release creation fails
- Asset verification happens before publishing to prevent partial releases
- Cleanup operations check ownership before deletion to avoid accidental resource removal
- File I/O errors trigger rollback through nested try/except blocks

**Validation-Focused Design**

The error handling philosophy emphasizes early failure and clear diagnostics:
- Input validation occurs at function boundaries with descriptive error messages
- External state is verified before mutation (e.g., checking tag absence before creation)
- Hash verification ensures artifact integrity throughout the pipeline
- Manifest validation catches structural and semantic errors before build operations

**No Custom Exception Hierarchy**

The codebase deliberately avoids creating custom exception classes, instead using well-known Python exceptions with rich error messages. This keeps the error handling simple and maintainable while providing sufficient context for debugging.
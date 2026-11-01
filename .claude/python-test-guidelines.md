# Automated Tests Required (Python)
For **any new or updated Python implementation**, you MUST add or update **executable automated tests** (even if the user didn't explicitly ask).

## Requirements
- **No markdown-only substitutes**: do NOT create `TESTS.md`, comments, or prose-only test plans instead of real tests unless the user explicitly requests manual test cases.
- **Framework**:
  - Prefer **pytest** if the project already uses it or for new projects.
  - Use **unittest** if that is the existing framework.
  - If no test framework exists, introduce pytest with a runnable command.
- **Location**:
  - Place tests under `tests/` directory.
  - Name test files with `test_` prefix (e.g., `test_module.py`).
  - Follow project conventions for test organization.
- **Isolation**:
  - Mock or stub external dependencies using `unittest.mock` or pytest fixtures.
  - Avoid real network calls, file I/O, database connections, or system time unless explicitly requested.

## Coverage Requirements
Automated tests MUST cover:
- **Happy paths**: expected and normal behavior
- **Boundary conditions**: empty lists, None values, zero/negative numbers, large datasets
- **Invalid inputs**: wrong types, missing arguments, malformed data, invalid state
- **Failure scenarios**: exceptions, IOErrors, network failures, timeouts, permission errors
- **Regressions**: previously failing cases or fragile logic

## External Dependencies
- External APIs, databases, and services must be mocked using `unittest.mock.patch`, `@patch` decorator, or pytest fixtures.
- Integration tests are allowed only when explicitly requested or gated behind environment variables/flags.

## Clarity Rules
- **Avoid assumptions**: rely strictly on stated requirements and observable code behavior.
- **If requirements are unclear**:
  - Ask targeted, structured clarification questions
  - Do NOT guess or invent behavior
  - Wait for confirmation before finalizing tests

## When Generating or Modifying Code
- Tests must be written or updated alongside production code.
- Tests must be deterministic, isolated, and maintainable.
- Use descriptive test names following `test_<what>_<when>_<expected>` pattern.
- Prefer explicit assertions (`assert result == expected`) over vague checks.
- Use pytest fixtures or unittest setUp/tearDown for test setup when needed.

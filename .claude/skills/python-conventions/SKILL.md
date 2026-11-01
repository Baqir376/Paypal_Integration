---
name: python-conventions
description: Apply pragmatic, broadly accepted Python conventions centered on readability and maintainability without being overly prescriptive. Use when writing, refactoring, or reviewing Python code, or when designing APIs/modules.
---

# Python Conventions (Pragmatic)

## Goal
Write Python that is **readable and maintainable**, while matching the repo's existing style, Python version, framework conventions, and tooling.

## Common conventions (non-prescriptive)

Use these as defaults when they fit; follow the repo when they don't.

- **Consistency first**: mirror nearby patterns (naming, module layout, framework conventions, and tooling).
- **Lean on standard tooling**: if the repo uses formatters (Black, Ruff) or linters (pylint, flake8), follow them; otherwise, follow local style and PEP 8 as a baseline.
- **Clarity at boundaries**: be explicit where data crosses a boundary (public APIs, I/O, serialization, external services).
- **Pythonic, not clever**: prefer idiomatic constructs (list comprehensions, context managers, generators) when they improve readability; avoid cleverness that obscures intent.
- **Type hints where helpful**: add type hints to function signatures and module boundaries when they improve clarity and tooling; follow the repo's existing level of type coverage.
- **Explicit over implicit**: make dependencies, configuration, and side effects visible rather than hidden in module-level state or magic.
- **Testable design**: keep core logic deterministic; isolate side effects; inject dependencies rather than hard-coding globals or imports.

## Types & structure (quick notes)

- Use **dataclasses** or **attrs** for structured data; use plain classes when behavior dominates.
- Use **Enum** for fixed sets of values; avoid stringly-typed constants.
- Keep functions and classes focused; extract when complexity grows.
- If the repo uses type checkers (mypy, pyright), follow existing patterns rather than introducing inconsistent coverage.

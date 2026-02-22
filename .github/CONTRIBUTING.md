# Contributing to Hacxgent

First off, thanks for taking the time to contribute! ❤️

The following is a set of guidelines for contributing to Hacxgent. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## How Can I Contribute?

### Reporting Bugs

Bugs are tracked as GitHub issues. When creating a bug report, please include:
- A clear and concise description of the bug.
- Steps to reproduce the bug.
- Expected behavior vs actual behavior.
- Hacxgent version and OS/Terminal information.

### Suggesting Enhancements

Feature requests are also tracked as GitHub issues. Please explain:
- Why this enhancement is useful.
- How it should work.
- Any alternatives you've considered.

### Pull Requests

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints (we use `ruff`).

## Development Setup

We use `uv` for dependency management.

```bash
# Install uv if you haven't
pip install uv

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
uv pip install -e ".[dev]"
```

## Style Guide

- We follow standard Python conventions.
- Use `ruff` for formatting and linting.
- Aim for clear, concise, and well-documented code.

## License

By contributing, you agree that your contributions will be licensed under its Apache-2.0 License.

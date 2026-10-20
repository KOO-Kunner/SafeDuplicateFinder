# Contributing

Thanks for considering a contribution.

## Before opening a pull request

1. Open an issue describing the problem or proposed change.
2. Keep the project dependency-free unless a dependency is clearly justified.
3. Add or update tests for changed behavior, especially around moving/restoring files.
4. Run `python -m unittest discover -s tests -v`.
5. Update README and CHANGELOG when user-facing behavior changes.

## Pull request expectations

- Keep changes focused.
- Explain the reason for the change and how you tested it.
- Never include real user paths, personal documents, or other private data in fixtures.
- Do not add destructive cleanup behavior without explicit review and tests.

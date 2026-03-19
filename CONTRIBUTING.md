# Contributing Guide

Thanks for considering a contribution. This repo is a prototype, but we still keep a clean workflow.

## Quick Start
1. Fork the repo and create a feature branch.
2. Run `docker compose up --build` to start the app locally.
3. Run tests with `python -m pytest`.
4. Open a PR with a short summary and test results.

## Development Workflow
- Keep changes focused and small.
- Prefer adding or updating tests when behavior changes.
- Use descriptive commit messages.

## Local Checks
- `make ci`
- `python -m pytest`
- `python -m ruff check .`
- `python -m ruff format .`

## Pull Requests
- Describe the intent and scope.
- Link any issue or discussion if relevant.
- Include test results.


## PR Checklist
- [ ] Clear summary of changes
- [ ] Tests run (`python -m pytest`)
- [ ] Lint run (`python -m ruff check .`)
- [ ] Format run (`python -m ruff format .`)

## Data Updates
- If you touch `funds_database.json`, note the source and method.
- Avoid large unrelated data changes in the same PR.

## Questions
If anything is unclear, open an issue or draft PR and ask for guidance.

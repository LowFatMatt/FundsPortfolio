# Contributing Guide

Thanks for considering a contribution. It is highly appreciated!

Before your first pull request can be 
merged, you'll need to sign our [Contributor License Agreement](CLA.md).

## Why a CLA?

This project is dual-licensed: it is available under the AGPL-3.0 for 
the community, and under separate commercial license for organizations 
that need different terms. The CLA ensures we can continue offering both 
options. You retain copyright over your contributions.

## How to Sign

When you open your first PR, the CLA Assistant bot will prompt you. 
Just follow the link and sign electronically — it takes 30 seconds.

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

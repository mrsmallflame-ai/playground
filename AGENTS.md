# Codex Workspace Guide

## Scope

These instructions apply to the whole repository.

## Repository Shape

- This repo is a personal sandbox. Keep experiments isolated under `experiments/<name>/`.
- Use `./new <kebab-case-name>` to create a new experiment from `experiments/_template/`.
- Do not add runtime dependencies at the repo root unless they are repo-wide tooling.
- Keep each experiment self-contained with its own README, install steps, run command, and notes.
- Update the top-level project index in `README.md` whenever an experiment is added, renamed, or removed.

## Working Rules

- Prefer small, reversible changes that preserve the playground structure.
- Avoid editing generated or tool state such as `.kilo/` unless the user asks for it directly.
- Put throwaway notes inside the relevant experiment README, not in root-level scratch files.
- Use concise comments only where they explain non-obvious behavior.

## Validation

- Run `./scripts/check` before finishing changes to repo structure or experiment metadata.
- If an experiment has its own test, lint, build, or run command, execute the relevant command from that experiment directory and report the result.
- If a validation command cannot run because dependencies are missing or network access is blocked, say exactly what was skipped and why.

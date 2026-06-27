# CLAUDE.md — Playground

Personal sandbox for fun, throwaway, and side-project experiments. Each experiment is fully self-contained under `experiments/<name>/`. Languages, stacks, and states of completion vary freely — that's the point.

## Repository layout

```
playground/
├── experiments/
│   ├── _template/            Template for new experiments (must contain README.md)
│   └── functional-vm/        Stack-based VM: assembler, CLI, examples, tests, stress runner
├── scripts/
│   └── check                 Structural validator — run before finishing any change
├── new                       Shell script: bootstraps a new experiment from _template
├── AGENTS.md                 Codex / AI agent operating instructions
└── README.md                 Project index (must list every experiment)
```

## Creating a new experiment

```bash
./new my-cool-idea
# Then add a row to the project index table in README.md
```

Or manually:

```bash
cp -r experiments/_template experiments/my-cool-idea
# Edit experiments/my-cool-idea/README.md
# Add the entry to README.md project index
```

Experiment names must be **kebab-case**.

## Validation

Run `./scripts/check` before finishing any structural change or experiment metadata update:

```bash
./scripts/check
```

The check enforces:
- `README.md`, `AGENTS.md`, `new`, and `experiments/_template/README.md` all exist
- `new` is executable and passes shell syntax check
- Every `experiments/<name>/` (except `_template`) contains a `README.md`
- Every experiment directory has a corresponding entry in the README.md project index table in the format `| [name](experiments/name/) | ... |`

CI for each experiment: if the experiment has its own test, lint, build, or run command, run it from that experiment's directory and report the result.

## Current experiments

| Experiment | Description | Status |
|------------|-------------|--------|
| `functional-vm` | Stack-based virtual machine with assembler, CLI (`vm.py`), example programs (`examples/`), unit tests (`test_vm.py`), and a stress runner (`stress_vm.py`) | Working |

## Repository conventions

- **One folder per experiment** — no cross-experiment imports or shared runtime dependencies at the repo root
- **Each experiment has its own `README.md`** explaining what it is, how to install deps, and how to run it
- **Update the project index** in `README.md` whenever an experiment is added, renamed, or removed
- Root-level deps are for repo-wide tooling only (e.g., a future shared linter)
- Throwaway notes belong inside the relevant experiment's `README.md`, not in root-level scratch files
- Experiments can be deleted if they are no longer worth keeping

## AI agent (Codex) rules

From `AGENTS.md`:
- All work stays inside `experiments/<name>/`
- Use `./new <kebab-case-name>` to create new experiments from the template
- Run `./scripts/check` before finishing; fix any failures before reporting done
- If an experiment defines its own test/lint/build/run command, execute it from that experiment's directory and report the result
- If a command cannot run (missing deps, no network), explicitly state what was skipped and why
- Prefer small, reversible changes that preserve the playground structure
- Do not edit `.kilo/` or other generated/tool-state directories unless explicitly asked
- Concise comments only where they explain non-obvious behavior — no narrative docstrings

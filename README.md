# playground 🛝

A personal sandbox for fun, throwaway, and side projects. Each experiment lives
in its own self-contained folder under [`experiments/`](experiments/) so nothing
steps on anything else — different languages, stacks, and half-finished ideas can
all coexist happily.

## Project index

| Project | What it is | Status |
|---------|------------|--------|
| [functional-vm](experiments/functional-vm/) | A small stack-based virtual machine with an assembler, CLI, examples, and tests. | Working |
| [frisbee-throw-analytics](experiments/frisbee-throw-analytics/) | Desktop computer-vision app that analyses ultimate frisbee throws from video: disc tracking, kinematics metrics, charts, Tkinter GUI. | Working |

## Starting a new experiment

```bash
./new my-cool-idea
```

This copies [`experiments/_template/`](experiments/_template/) into
`experiments/my-cool-idea/`, ready to hack on. Then add a row to the table above.

Prefer to do it by hand? Just copy the template:

```bash
cp -r experiments/_template experiments/my-cool-idea
```

## Codex workflow

This repo is set up for Codex sessions through [`AGENTS.md`](AGENTS.md). When
Codex creates or changes experiments, it should keep work inside
`experiments/<name>/`, update the project index above, and run:

```bash
./scripts/check
```

## Conventions

- **One folder per experiment** under `experiments/`. Keep each one independent.
- **Each experiment has its own `README.md`** explaining what it is and how to run it.
- **No project is too small or silly.** That's the point.
- Anything not worth keeping can just be deleted — it's a playground.

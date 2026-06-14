# playground 🛝

A personal sandbox for fun, throwaway, and side projects. Each experiment lives
in its own self-contained folder under [`experiments/`](experiments/) so nothing
steps on anything else — different languages, stacks, and half-finished ideas can
all coexist happily.

## Project index

| Project | What it is | Status |
|---------|------------|--------|
| [desktop-manager](experiments/desktop-manager/) | Zero-dependency CLI that declutters & inspects a folder — sort by type/date/size/ext, plus stats, dedupe, find, tree, history & undo (29 features) | ✅ Working |

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

## Conventions

- **One folder per experiment** under `experiments/`. Keep each one independent.
- **Each experiment has its own `README.md`** explaining what it is and how to run it.
- **No project is too small or silly.** That's the point.
- Anything not worth keeping can just be deleted — it's a playground.

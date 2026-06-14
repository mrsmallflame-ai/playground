# desktop-manager

> A zero-dependency CLI that declutters and inspects a folder. It sorts loose
> files into tidy subfolders (by type, date, size, or extension), plus a toolbox
> of inspection and cleanup commands — all with a dry-run preview and undo.
> Default target is `~/Desktop`.

## Idea

Desktops and Downloads folders turn into chaos. This tool sweeps loose files
into sensible folders, and gives you a handful of utilities to understand and
clean up a directory — without ever leaving the terminal or installing anything.

## Running it

Requires only Python 3.9+ (standard library only — no `pip install`).

```bash
python3 desktop_manager.py status            # what's cluttering ~/Desktop?
python3 desktop_manager.py organize --dry-run # preview the sort
python3 desktop_manager.py organize           # do it (then `undo` to revert)
python3 desktop_manager.py organize ~/Downloads
```

Every command takes an optional path (default `~/Desktop`) and the global flags
`--json`, `--no-color`, `-q/--quiet`, `-v/--verbose`, `--config`.

## Commands

| Command | What it does |
|---------|--------------|
| `status` | Summarize loose files by category |
| `organize` | Move/copy files into folders |
| `stats` | Count + disk usage per category |
| `largest [-n N]` | List the N largest files |
| `find PATTERN` | Search files by glob (e.g. `'*.pdf'`) |
| `dedupe [--remove]` | Find duplicate files by content hash |
| `clean-empty` | Remove empty subdirectories |
| `tree` | Print a directory tree |
| `history` | Show past organize runs |
| `undo` | Revert the most recent move-based run |

## Feature reference (29)

**Organize strategies & traversal**
1. `--by type` — category folders *(default)*
2. `--by date` — `Year/Month/` folders
3. `--by size` — size buckets (Tiny → Huge)
4. `--by ext` — one folder per extension
5. `-r, --recursive` — descend into subfolders
6. `--max-depth N` — limit recursion depth
7. `--flatten` — route nested files up to root folders
8. `--copy` — copy instead of move

**Filtering** (on `organize`, `status`, `stats`, `largest`, `dedupe`)
9. `--ext EXT` — only these extensions (repeatable)
10. `--include GLOB` — only names matching glob (repeatable)
11. `--exclude GLOB` — skip names matching glob (repeatable)
12. `--min-size SIZE` — e.g. `10KB`, `4MB`
13. `--max-size SIZE` — e.g. `1GB`
14. `--older-than DAYS`
15. `--newer-than DAYS`

**Filename normalization** (on `organize`)
16. `--lowercase`
17. `--replace-spaces` — spaces → underscores
18. `--prefix STR`

**Config**
19. `--config FILE` — JSON file of custom categories (also auto-loaded from
    `~/.config/desktop_manager.json` or `~/.desktop_manager.json`)

**Commands**
20. `stats` — count + disk usage per category
21. `largest` — top-N largest files
22. `find` — glob search
23. `dedupe` — duplicate detection by SHA-256 (`--remove` quarantines into
    `_Duplicates/`, reversible via `undo`)
24. `clean-empty` — prune empty directories
25. `tree` — directory tree
26. `history` — list past organize runs

**Output / UX**
27. `--json` — machine-readable output
28. colored output (auto-detected; disable with `--no-color` or `NO_COLOR=1`)
29. `-q/--quiet` and `-v/--verbose` verbosity levels

### Example config

```json
{
  "categories": {
    "Pics": ["jpg", "jpeg", "png"],
    "Work": ["pdf", "docx", "xlsx"]
  }
}
```

## How it works

- Only **loose files** are touched — existing subfolders, dotfiles, the
  `_Duplicates/` folder, and the history file are left alone (re-running is safe).
- Name collisions get ` (1)`, ` (2)`, … suffixes rather than overwriting.
- Move-based runs (`organize`, `dedupe --remove`) append to a
  `.desktop_manager_history.json` manifest; `undo` replays the latest run in
  reverse and prunes emptied folders. `--copy` never records history.

## Notes

- Run tests with: `python3 test_desktop_manager.py` (23 tests).
- Ideas for later: a `watch` mode, `--by-author` (EXIF/mtime), trash integration.

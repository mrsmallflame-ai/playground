# desktop-manager

> A zero-dependency CLI that declutters a folder by sorting loose files into
> tidy category subfolders (Images/, Documents/, Archives/, …). Default target
> is `~/Desktop`.

## Idea

Desktops (and Downloads folders) turn into chaos. This tool sweeps the loose
files into sensible category folders by file type, with a **dry-run** preview so
you can see what it'll do first, and an **undo** so a bad sort is never
permanent.

## Running it

Requires only Python 3.9+ (standard library only — no `pip install`).

```bash
# See what's cluttering your desktop, grouped by category
python3 desktop_manager.py status

# Preview the sort without touching anything
python3 desktop_manager.py organize --dry-run

# Actually organize it
python3 desktop_manager.py organize

# Point it at any folder
python3 desktop_manager.py organize ~/Downloads

# Changed your mind? Revert the last organize run
python3 desktop_manager.py undo
```

Make it a handy command:

```bash
chmod +x desktop_manager.py
./desktop_manager.py status
```

## How it works

- Only **loose files** in the target folder are touched — existing subfolders,
  hidden/dotfiles, and the undo manifest are left alone (so re-running is safe).
- Files are matched to a category by extension; anything unrecognized goes to
  `Other/`.
- Name collisions are resolved by appending ` (1)`, ` (2)`, … rather than
  overwriting.
- Each `organize` writes a `.desktop_manager_undo.json` manifest in the target
  folder; `undo` replays it in reverse and removes the manifest.

## Notes

- Categories live in the `CATEGORIES` dict at the top of `desktop_manager.py` —
  tweak/extend them to taste.
- Run tests with: `python3 test_desktop_manager.py`
- Ideas: `--by-date` (sort into Year/Month folders), a config file for custom
  rules, recursive mode.

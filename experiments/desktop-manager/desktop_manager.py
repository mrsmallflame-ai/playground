#!/usr/bin/env python3
"""desktop-manager — tidy and inspect a cluttered folder. Zero dependencies (stdlib only).

Default target is ~/Desktop. See README.md for the full feature list.

Commands:
    organize     Move/copy files into folders (by type/date/size/ext).
    status       Summarize loose files by category.
    stats        Count + disk usage per category.
    largest      List the N largest files.
    find         Search for files by glob pattern.
    dedupe       Find duplicate files by content hash.
    clean-empty  Remove empty subdirectories.
    tree         Print a directory tree.
    history      Show past organize runs.
    undo         Revert the most recent move-based run.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# --- Defaults & constants ---------------------------------------------------

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Images": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "svg", "webp", "heic", "ico"],
    "Documents": ["pdf", "doc", "docx", "txt", "md", "rtf", "odt", "tex", "pages"],
    "Spreadsheets": ["xls", "xlsx", "csv", "ods", "numbers"],
    "Presentations": ["ppt", "pptx", "odp", "key"],
    "Audio": ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"],
    "Video": ["mp4", "mov", "avi", "mkv", "webm", "flv", "wmv", "m4v"],
    "Archives": ["zip", "tar", "gz", "bz2", "xz", "7z", "rar", "tgz"],
    "Code": ["py", "js", "ts", "json", "html", "css", "sh", "c", "cpp", "go", "rs", "java", "rb"],
    "Installers": ["dmg", "pkg", "exe", "msi", "deb", "rpm", "appimage"],
}
OTHER = "Other"
HISTORY_FILENAME = ".desktop_manager_history.json"
DUPLICATES_DIR = "_Duplicates"
CONFIG_PATHS = [
    Path.home() / ".config" / "desktop_manager.json",
    Path.home() / ".desktop_manager.json",
]
SIZE_BUCKETS = [  # (label, max_bytes_exclusive)
    ("Tiny", 100 * 1024),
    ("Small", 1024 * 1024),
    ("Medium", 100 * 1024 * 1024),
    ("Large", 1024 * 1024 * 1024),
]  # anything bigger -> "Huge"

# --- Output helpers (features 27-29: --json, color, verbosity) ---------------


class Out:
    """Tiny output controller: color, verbosity, and JSON-mode buffering."""

    COLORS = {"reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
              "green": "\033[32m", "yellow": "\033[33m", "blue": "\033[34m",
              "cyan": "\033[36m", "red": "\033[31m"}

    def __init__(self, *, json_mode=False, no_color=False, quiet=False, verbose=False):
        self.json_mode = json_mode
        self.quiet = quiet
        self.verbose = verbose
        self.use_color = (
            not no_color and not json_mode and sys.stdout.isatty()
            and os.environ.get("NO_COLOR") is None
        )

    def c(self, text: str, color: str) -> str:
        if not self.use_color:
            return text
        return f"{self.COLORS[color]}{text}{self.COLORS['reset']}"

    def line(self, text: str = "", *, level: str = "normal") -> None:
        if self.json_mode:
            return
        if level == "verbose" and not self.verbose:
            return
        if level == "detail" and self.quiet:
            return
        print(text)

    def emit_json(self, payload) -> None:
        if self.json_mode:
            print(json.dumps(payload, indent=2, default=str))


# --- Config (feature 19) -----------------------------------------------------


def load_categories(explicit: Path | None = None) -> dict[str, list[str]]:
    """Load category rules from config, falling back to the built-in defaults."""
    candidates = [explicit] if explicit else CONFIG_PATHS
    for path in candidates:
        if path and path.is_file():
            data = json.loads(path.read_text())
            cats = data.get("categories", data)
            return {k: [e.lower().lstrip(".") for e in v] for k, v in cats.items()}
    return {k: list(v) for k, v in DEFAULT_CATEGORIES.items()}


# --- Size / time parsing -----------------------------------------------------


def parse_size(text: str) -> int:
    """Parse '10', '10KB', '4.5MB', '1GB' into bytes."""
    text = text.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for unit in ("TB", "GB", "MB", "KB", "B"):
        if text.endswith(unit):
            return int(float(text[: -len(unit)] or 0) * units[unit])
    return int(float(text))


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# --- Filtering & gathering (features 5,6,9-15) -------------------------------


class Filters:
    def __init__(self, args: argparse.Namespace):
        self.exts = {e.lower().lstrip(".") for e in (getattr(args, "ext", None) or [])}
        self.include = getattr(args, "include", None) or []
        self.exclude = getattr(args, "exclude", None) or []
        self.min_size = parse_size(args.min_size) if getattr(args, "min_size", None) else None
        self.max_size = parse_size(args.max_size) if getattr(args, "max_size", None) else None
        older = getattr(args, "older_than", None)
        newer = getattr(args, "newer_than", None)
        now = time.time()
        self.min_mtime = (now - newer * 86400) if newer is not None else None  # newer-than -> mtime >=
        self.max_mtime = (now - older * 86400) if older is not None else None  # older-than -> mtime <=

    def accepts(self, path: Path) -> bool:
        name = path.name
        if self.exts and path.suffix.lower().lstrip(".") not in self.exts:
            return False
        if self.include and not any(fnmatch.fnmatch(name, p) for p in self.include):
            return False
        if any(fnmatch.fnmatch(name, p) for p in self.exclude):
            return False
        try:
            stat = path.stat()
        except OSError:
            return False
        if self.min_size is not None and stat.st_size < self.min_size:
            return False
        if self.max_size is not None and stat.st_size > self.max_size:
            return False
        if self.min_mtime is not None and stat.st_mtime < self.min_mtime:
            return False
        if self.max_mtime is not None and stat.st_mtime > self.max_mtime:
            return False
        return True


def gather(target: Path, *, recursive=False, max_depth=None, filters: Filters | None = None) -> list[Path]:
    """Return loose files under target. Skips dotfiles, category-mgmt files, and dirs."""
    results: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith(".") or entry.name == DUPLICATES_DIR:
                continue
            if entry.is_dir():
                if recursive and (max_depth is None or depth < max_depth):
                    walk(entry, depth + 1)
                continue
            if filters is None or filters.accepts(entry):
                results.append(entry)

    walk(target, 1)
    return results


# --- Destination strategy (features 1-4) -------------------------------------


def subdir_for(path: Path, strategy: str, categories: dict[str, list[str]]) -> str:
    ext = path.suffix.lower().lstrip(".")
    if strategy == "type":
        for category, extensions in categories.items():
            if ext in extensions:
                return category
        return OTHER
    if strategy == "ext":
        return ext.upper() if ext else "NO_EXT"
    if strategy == "date":
        dt = datetime.fromtimestamp(path.stat().st_mtime)
        return f"{dt.year}/{dt:%m-%B}"
    if strategy == "size":
        size = path.stat().st_size
        for label, limit in SIZE_BUCKETS:
            if size < limit:
                return label
        return "Huge"
    raise ValueError(f"unknown strategy: {strategy}")


# --- Filename normalization (features 16-18) ---------------------------------


def normalize_name(name: str, args: argparse.Namespace) -> str:
    if getattr(args, "lowercase", False):
        name = name.lower()
    if getattr(args, "replace_spaces", False):
        name = name.replace(" ", "_")
    prefix = getattr(args, "prefix", None)
    if prefix:
        name = f"{prefix}{name}"
    return name


def unique_destination(dest_dir: Path, name: str) -> Path:
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while (candidate := dest_dir / f"{stem} ({n}){suffix}").exists():
        n += 1
    return candidate


# --- History & undo (features 26 + undo) -------------------------------------


def load_history(target: Path) -> list[dict]:
    path = target / HISTORY_FILENAME
    if path.is_file():
        return json.loads(path.read_text())
    return []


def save_history(target: Path, history: list[dict]) -> None:
    path = target / HISTORY_FILENAME
    if history:
        path.write_text(json.dumps(history, indent=2))
    elif path.exists():
        path.unlink()


def record_run(target: Path, action: str, moves: list[tuple[str, str]]) -> None:
    history = load_history(target)
    history.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "moves": moves,
    })
    save_history(target, history)


# --- Commands ----------------------------------------------------------------


def cmd_status(target: Path, args, out: Out) -> int:
    categories = load_categories(getattr(args, "config", None))
    files = gather(target, recursive=getattr(args, "recursive", False),
                   max_depth=getattr(args, "max_depth", None), filters=Filters(args))
    grouped: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        grouped[subdir_for(f, "type", categories)].append(f)

    if out.json_mode:
        out.emit_json({c: [str(p) for p in ps] for c, ps in grouped.items()})
        return 0
    if not grouped:
        out.line(f"{target} has no loose files to organize. " + out.c("✨", "green"))
        return 0
    total = sum(len(v) for v in grouped.values())
    out.line(out.c(f"{target} — {total} loose file(s):", "bold"))
    out.line()
    for category in sorted(grouped):
        out.line(f"  {out.c(category, 'cyan'):<22} {len(grouped[category])}")
        for f in grouped[category]:
            out.line(out.c(f"      {f.name}", "dim"), level="detail")
    return 0


def cmd_organize(target: Path, args, out: Out) -> int:
    categories = load_categories(getattr(args, "config", None))
    files = gather(target, recursive=args.recursive, max_depth=args.max_depth, filters=Filters(args))
    moves: list[tuple[str, str]] = []
    verb = "copy" if args.copy else "move"

    if not files:
        out.line(f"Nothing to organize in {target}. " + out.c("✨", "green"))
        out.emit_json({"action": "organize", "moves": []})
        return 0

    for src in files:
        base = target if args.flatten else src.parent
        subdir = subdir_for(src, args.by, categories)
        dest_dir = base / subdir
        dest = unique_destination(dest_dir, normalize_name(src.name, args))
        word = ("would " + verb) if args.dry_run else (verb + ("d" if verb == "move" else "ied"))
        rel = dest.relative_to(target) if dest.is_relative_to(target) else dest
        out.line(f"  {out.c(word, 'yellow')}: {src.name}  {out.c('->', 'dim')}  {rel}", level="detail")
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if args.copy:
                shutil.copy2(str(src), str(dest))
            else:
                shutil.move(str(src), str(dest))
        moves.append((str(src), str(dest)))

    if args.dry_run:
        out.line(f"\nDry run: {len(moves)} file(s) would be organized.")
    else:
        if not args.copy:
            record_run(target, "organize", moves)
        out.line(f"\n{out.c('Organized', 'green')} {len(moves)} file(s)." +
                 ("" if args.copy else " Run 'undo' to revert."))
    out.emit_json({"action": "organize", "dry_run": args.dry_run, "copy": args.copy, "moves": moves})
    return 0


def cmd_stats(target: Path, args, out: Out) -> int:
    categories = load_categories(getattr(args, "config", None))
    files = gather(target, recursive=args.recursive, max_depth=args.max_depth, filters=Filters(args))
    counts: dict[str, int] = defaultdict(int)
    sizes: dict[str, int] = defaultdict(int)
    for f in files:
        cat = subdir_for(f, "type", categories)
        counts[cat] += 1
        sizes[cat] += f.stat().st_size

    if out.json_mode:
        out.emit_json({c: {"count": counts[c], "bytes": sizes[c]} for c in counts})
        return 0
    if not files:
        out.line(f"No matching files in {target}.")
        return 0
    out.line(out.c(f"{target} — usage by category:", "bold"))
    out.line()
    for cat in sorted(sizes, key=lambda c: sizes[c], reverse=True):
        out.line(f"  {out.c(cat, 'cyan'):<22} {counts[cat]:>4} file(s)   {human_size(sizes[cat]):>9}")
    out.line()
    out.line(f"  {'TOTAL':<13} {sum(counts.values()):>4} file(s)   {human_size(sum(sizes.values())):>9}")
    return 0


def cmd_largest(target: Path, args, out: Out) -> int:
    files = gather(target, recursive=args.recursive, max_depth=args.max_depth, filters=Filters(args))
    ranked = sorted(files, key=lambda f: f.stat().st_size, reverse=True)[: args.number]
    if out.json_mode:
        out.emit_json([{"path": str(f), "bytes": f.stat().st_size} for f in ranked])
        return 0
    if not ranked:
        out.line(f"No matching files in {target}.")
        return 0
    out.line(out.c(f"Top {len(ranked)} largest file(s) in {target}:", "bold"))
    for f in ranked:
        out.line(f"  {human_size(f.stat().st_size):>9}  {f.relative_to(target)}")
    return 0


def cmd_find(target: Path, args, out: Out) -> int:
    files = gather(target, recursive=args.recursive, max_depth=args.max_depth)
    matches = [f for f in files if fnmatch.fnmatch(f.name, args.pattern)]
    if out.json_mode:
        out.emit_json([str(f) for f in matches])
        return 0
    for f in matches:
        out.line(str(f.relative_to(target)))
    out.line(out.c(f"\n{len(matches)} match(es).", "dim"), level="detail")
    return 0


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_dedupe(target: Path, args, out: Out) -> int:
    files = gather(target, recursive=args.recursive, max_depth=args.max_depth, filters=Filters(args))
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_hash[_hash_file(f)].append(f)
    dupes = {h: ps for h, ps in by_hash.items() if len(ps) > 1}

    if out.json_mode:
        out.emit_json({h: [str(p) for p in ps] for h, ps in dupes.items()})
    if not dupes:
        out.line("No duplicates found. " + out.c("✨", "green"))
        return 0

    moves: list[tuple[str, str]] = []
    out.line(out.c(f"Found {len(dupes)} group(s) of duplicates:", "bold"))
    for paths in dupes.values():
        keep, extras = paths[0], paths[1:]
        out.line(f"  keep: {keep.relative_to(target)}")
        for extra in extras:
            if args.remove:
                dest = unique_destination(target / DUPLICATES_DIR, extra.name)
                (target / DUPLICATES_DIR).mkdir(exist_ok=True)
                shutil.move(str(extra), str(dest))
                moves.append((str(extra), str(dest)))
                out.line(f"    {out.c('quarantined', 'yellow')}: {extra.relative_to(target)}")
            else:
                out.line(out.c(f"    dup:  {extra.relative_to(target)}", "dim"))
    if moves:
        record_run(target, "dedupe", moves)
        out.line(f"\nMoved {len(moves)} duplicate(s) to {DUPLICATES_DIR}/. Run 'undo' to revert.")
    elif not args.remove:
        out.line(out.c("\nRe-run with --remove to quarantine the duplicates.", "dim"))
    return 0


def cmd_clean_empty(target: Path, args, out: Out) -> int:
    removed: list[str] = []
    for root, dirs, files in os.walk(target, topdown=False):
        root_path = Path(root)
        if root_path == target:
            continue
        if not any(root_path.iterdir()):
            if not args.dry_run:
                root_path.rmdir()
            removed.append(str(root_path.relative_to(target)))
    if out.json_mode:
        out.emit_json({"removed": removed, "dry_run": args.dry_run})
        return 0
    word = "Would remove" if args.dry_run else "Removed"
    for r in removed:
        out.line(f"  {word}: {r}")
    out.line(out.c(f"{word} {len(removed)} empty director(ies).", "green"))
    return 0


def cmd_tree(target: Path, args, out: Out) -> int:
    root_name = target.name or target.resolve().name or str(target)
    lines: list[str] = [out.c(root_name + "/", "blue")]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if args.max_depth is not None and depth > args.max_depth:
            return
        entries = [e for e in sorted(directory.iterdir()) if not e.name.startswith(".")]
        for i, entry in enumerate(entries):
            last = i == len(entries) - 1
            connector = "└── " if last else "├── "
            label = out.c(entry.name + "/", "blue") if entry.is_dir() else entry.name
            lines.append(prefix + connector + label)
            if entry.is_dir():
                walk(entry, prefix + ("    " if last else "│   "), depth + 1)

    walk(target, "", 1)
    if out.json_mode:
        out.emit_json(lines)
        return 0
    for line in lines:
        out.line(line)
    return 0


def cmd_history(target: Path, args, out: Out) -> int:
    history = load_history(target)
    if out.json_mode:
        out.emit_json(history)
        return 0
    if not history:
        out.line(f"No organize history in {target}.")
        return 0
    out.line(out.c(f"Organize history for {target}:", "bold"))
    for i, run in enumerate(history):
        marker = out.c("(latest)", "green") if i == len(history) - 1 else ""
        out.line(f"  [{i}] {run['timestamp']}  {run['action']:<9} "
                 f"{len(run['moves'])} file(s) {marker}")
    return 0


def cmd_undo(target: Path, args, out: Out) -> int:
    history = load_history(target)
    if not history:
        out.line(f"No undo history found in {target}.", )
        return 1
    run = history.pop()
    restored = 0
    for src, dest in reversed(run["moves"]):
        dest_path, src_path = Path(dest), Path(src)
        if not dest_path.exists():
            out.line(f"  skip (missing): {dest_path.name}", level="detail")
            continue
        final = unique_destination(src_path.parent, src_path.name)
        src_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest_path), str(final))
        out.line(f"  {out.c('restored', 'green')}: {dest_path.name}", level="detail")
        restored += 1
        if dest_path.parent.is_dir() and not any(dest_path.parent.iterdir()):
            dest_path.parent.rmdir()
    save_history(target, history)
    out.line(f"\nRestored {restored} file(s) from {run['action']} run at {run['timestamp']}.")
    out.emit_json({"restored": restored, "run": run})
    return 0


# --- Argument parsing --------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop-manager",
        description="Tidy and inspect a cluttered folder. Zero dependencies.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def base(p):  # path + output flags (features 27-29) on every command
        p.add_argument("path", nargs="?", default=str(Path.home() / "Desktop"),
                       help="Target folder (default: ~/Desktop)")
        p.add_argument("--json", dest="json_mode", action="store_true", help="Machine-readable output.")
        p.add_argument("--no-color", action="store_true", help="Disable colored output.")
        p.add_argument("-q", "--quiet", action="store_true", help="Less output.")
        p.add_argument("-v", "--verbose", action="store_true", help="More output.")
        p.add_argument("--config", type=Path, help="Path to a categories config file.")

    def traversal(p):  # features 5, 6
        p.add_argument("-r", "--recursive", action="store_true", help="Descend into subfolders.")
        p.add_argument("--max-depth", type=int, default=None, help="Max recursion depth.")

    def filters(p):  # features 9-15
        p.add_argument("--ext", action="append", help="Only these extensions (repeatable).")
        p.add_argument("--include", action="append", help="Only names matching glob (repeatable).")
        p.add_argument("--exclude", action="append", help="Skip names matching glob (repeatable).")
        p.add_argument("--min-size", help="Minimum size, e.g. 10KB, 4MB.")
        p.add_argument("--max-size", help="Maximum size, e.g. 1GB.")
        p.add_argument("--older-than", type=float, metavar="DAYS", help="Only files older than DAYS.")
        p.add_argument("--newer-than", type=float, metavar="DAYS", help="Only files newer than DAYS.")

    # organize
    p = sub.add_parser("organize", help="Move/copy files into folders.")
    base(p); traversal(p); filters(p)
    p.add_argument("--by", choices=["type", "date", "size", "ext"], default="type",
                   help="Sorting strategy (features 1-4).")
    p.add_argument("--flatten", action="store_true", help="Route nested files to root folders.")
    p.add_argument("--copy", action="store_true", help="Copy instead of move.")
    p.add_argument("--lowercase", action="store_true", help="Lowercase filenames.")
    p.add_argument("--replace-spaces", action="store_true", help="Replace spaces with underscores.")
    p.add_argument("--prefix", help="Prepend a prefix to filenames.")
    p.add_argument("--dry-run", action="store_true", help="Preview without changing anything.")

    p = sub.add_parser("status", help="Summarize loose files by category.")
    base(p); traversal(p); filters(p)

    p = sub.add_parser("stats", help="Count + disk usage per category.")
    base(p); traversal(p); filters(p)

    p = sub.add_parser("largest", help="List the N largest files.")
    base(p); traversal(p); filters(p)
    p.add_argument("-n", "--number", type=int, default=10, help="How many to show (default 10).")

    p = sub.add_parser("find", help="Search for files by glob pattern.")
    base(p); traversal(p)
    p.add_argument("pattern", help="Glob pattern, e.g. '*.pdf'.")

    p = sub.add_parser("dedupe", help="Find duplicate files by content hash.")
    base(p); traversal(p); filters(p)
    p.add_argument("--remove", action="store_true", help="Quarantine duplicates into _Duplicates/.")

    p = sub.add_parser("clean-empty", help="Remove empty subdirectories.")
    base(p)
    p.add_argument("--dry-run", action="store_true", help="Preview without removing.")

    p = sub.add_parser("tree", help="Print a directory tree.")
    base(p)
    p.add_argument("--max-depth", type=int, default=None, help="Max depth to show.")

    base(sub.add_parser("history", help="Show past organize runs."))
    base(sub.add_parser("undo", help="Revert the most recent move-based run."))
    return parser


COMMANDS = {
    "organize": cmd_organize, "status": cmd_status, "stats": cmd_stats,
    "largest": cmd_largest, "find": cmd_find, "dedupe": cmd_dedupe,
    "clean-empty": cmd_clean_empty, "tree": cmd_tree, "history": cmd_history,
    "undo": cmd_undo,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = Path(args.path).expanduser()
    if not target.is_dir():
        print(f"error: {target} is not a directory", file=sys.stderr)
        return 2
    out = Out(json_mode=args.json_mode, no_color=args.no_color,
              quiet=args.quiet, verbose=args.verbose)
    return COMMANDS[args.command](target, args, out)


if __name__ == "__main__":
    raise SystemExit(main())

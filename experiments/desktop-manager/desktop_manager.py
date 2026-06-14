#!/usr/bin/env python3
"""desktop-manager — tidy a cluttered folder by sorting files into category subfolders.

Zero dependencies (stdlib only). Default target is ~/Desktop.

Commands:
    organize [PATH]   Move files into category folders (Images/, Documents/, ...).
    status   [PATH]   Show a summary of files by category, without moving anything.
    undo     [PATH]   Revert the most recent organize run in PATH.

Examples:
    desktop_manager.py status
    desktop_manager.py organize --dry-run
    desktop_manager.py organize ~/Downloads
    desktop_manager.py undo
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Extension -> category. Lowercase, no leading dot.
CATEGORIES: dict[str, set[str]] = {
    "Images": {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "svg", "webp", "heic", "ico"},
    "Documents": {"pdf", "doc", "docx", "txt", "md", "rtf", "odt", "tex", "pages"},
    "Spreadsheets": {"xls", "xlsx", "csv", "ods", "numbers"},
    "Presentations": {"ppt", "pptx", "odp", "key"},
    "Audio": {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"},
    "Video": {"mp4", "mov", "avi", "mkv", "webm", "flv", "wmv", "m4v"},
    "Archives": {"zip", "tar", "gz", "bz2", "xz", "7z", "rar", "tgz"},
    "Code": {"py", "js", "ts", "json", "html", "css", "sh", "c", "cpp", "go", "rs", "java", "rb"},
    "Installers": {"dmg", "pkg", "exe", "msi", "deb", "rpm", "appimage"},
}

OTHER = "Other"
UNDO_FILENAME = ".desktop_manager_undo.json"


def category_for(path: Path) -> str:
    """Return the destination category folder name for a file."""
    ext = path.suffix.lower().lstrip(".")
    for category, extensions in CATEGORIES.items():
        if ext in extensions:
            return category
    return OTHER


def scan(target: Path) -> dict[str, list[Path]]:
    """Group the loose files directly inside target by category.

    Skips directories, hidden/dotfiles, and the undo manifest itself.
    """
    grouped: dict[str, list[Path]] = defaultdict(list)
    for entry in sorted(target.iterdir()):
        if entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        grouped[category_for(entry)].append(entry)
    return grouped


def unique_destination(dest_dir: Path, name: str) -> Path:
    """Pick a path inside dest_dir for `name`, adding ' (n)' if it already exists."""
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while True:
        candidate = dest_dir / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def cmd_status(target: Path) -> int:
    grouped = scan(target)
    if not grouped:
        print(f"{target} has no loose files to organize. ✨")
        return 0
    total = sum(len(v) for v in grouped.values())
    print(f"{target} — {total} loose file(s):\n")
    for category in sorted(grouped):
        files = grouped[category]
        print(f"  {category:<14} {len(files)}")
        for f in files:
            print(f"      {f.name}")
    return 0


def cmd_organize(target: Path, dry_run: bool) -> int:
    grouped = scan(target)
    moves: list[tuple[str, str]] = []  # (source, destination) absolute paths

    if not any(grouped.values()):
        print(f"Nothing to organize in {target}. ✨")
        return 0

    for category in sorted(grouped):
        dest_dir = target / category
        for src in grouped[category]:
            dest = unique_destination(dest_dir, src.name)
            arrow = "would move" if dry_run else "moved"
            print(f"  {arrow}: {src.name}  ->  {category}/{dest.name}")
            if not dry_run:
                dest_dir.mkdir(exist_ok=True)
                shutil.move(str(src), str(dest))
            moves.append((str(src), str(dest)))

    if dry_run:
        print(f"\nDry run: {len(moves)} file(s) would be organized. Re-run without --dry-run to apply.")
        return 0

    manifest = {"timestamp": datetime.now().isoformat(timespec="seconds"), "moves": moves}
    (target / UNDO_FILENAME).write_text(json.dumps(manifest, indent=2))
    print(f"\nOrganized {len(moves)} file(s). Run 'undo' to revert.")
    return 0


def cmd_undo(target: Path) -> int:
    manifest_path = target / UNDO_FILENAME
    if not manifest_path.exists():
        print(f"No undo history found in {target}.", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())
    moves = manifest.get("moves", [])
    restored = 0
    for src, dest in reversed(moves):
        dest_path, src_path = Path(dest), Path(src)
        if not dest_path.exists():
            print(f"  skip (missing): {dest_path.name}")
            continue
        final = unique_destination(src_path.parent, src_path.name)
        shutil.move(str(dest_path), str(final))
        print(f"  restored: {dest_path.name}  ->  {final.name}")
        restored += 1
        # Clean up now-empty category folders.
        if dest_path.parent.is_dir() and not any(dest_path.parent.iterdir()):
            dest_path.parent.rmdir()

    manifest_path.unlink()
    print(f"\nRestored {restored} file(s) from {manifest['timestamp']}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop-manager",
        description="Tidy a cluttered folder by sorting files into category subfolders.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_path(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "path",
            nargs="?",
            default=str(Path.home() / "Desktop"),
            help="Target folder (default: ~/Desktop)",
        )

    p_org = sub.add_parser("organize", help="Move files into category folders.")
    add_path(p_org)
    p_org.add_argument("--dry-run", action="store_true", help="Preview without moving anything.")

    add_path(sub.add_parser("status", help="Show a summary by category."))
    add_path(sub.add_parser("undo", help="Revert the most recent organize run."))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = Path(args.path).expanduser()

    if not target.is_dir():
        print(f"error: {target} is not a directory", file=sys.stderr)
        return 2

    if args.command == "status":
        return cmd_status(target)
    if args.command == "organize":
        return cmd_organize(target, args.dry_run)
    if args.command == "undo":
        return cmd_undo(target)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

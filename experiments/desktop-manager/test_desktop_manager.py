#!/usr/bin/env python3
"""Tests for desktop_manager. Run: python3 test_desktop_manager.py"""
import argparse
import os
import tempfile
import time
import unittest
from pathlib import Path

import desktop_manager as dm

OUT = dm.Out(json_mode=False, no_color=True, quiet=True)


def ns(**kw) -> argparse.Namespace:
    """Build an args namespace with sensible defaults for all flags."""
    defaults = dict(
        path=".", recursive=False, max_depth=None, by="type", flatten=False,
        copy=False, lowercase=False, replace_spaces=False, prefix=None,
        dry_run=False, number=10, remove=False, pattern="*", config=None,
        ext=None, include=None, exclude=None, min_size=None, max_size=None,
        older_than=None, newer_than=None, json_mode=False, no_color=True,
        quiet=True, verbose=False,
    )
    defaults.update(kw)
    return argparse.Namespace(**defaults)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, name, content="x", *, age_days=None):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        if age_days is not None:
            t = time.time() - age_days * 86400
            os.utime(p, (t, t))
        return p


class ParsingTest(Base):
    def test_parse_size(self):
        self.assertEqual(dm.parse_size("1024"), 1024)
        self.assertEqual(dm.parse_size("1KB"), 1024)
        self.assertEqual(dm.parse_size("2MB"), 2 * 1024**2)
        self.assertEqual(dm.parse_size("1.5GB"), int(1.5 * 1024**3))

    def test_human_size(self):
        self.assertEqual(dm.human_size(512), "512B")
        self.assertEqual(dm.human_size(1536), "1.5KB")

    def test_subdir_strategies(self):
        cats = dm.load_categories()
        self.assertEqual(dm.subdir_for(Path("a.PNG"), "type", cats), "Images")
        self.assertEqual(dm.subdir_for(Path("a.unknownext"), "type", cats), dm.OTHER)
        self.assertEqual(dm.subdir_for(Path("a.pdf"), "ext", cats), "PDF")


class OrganizeTest(Base):
    def test_by_type(self):
        self.touch("photo.jpg"); self.touch("report.pdf"); self.touch("mystery.xyz")
        dm.cmd_organize(self.dir, ns(), OUT)
        self.assertTrue((self.dir / "Images" / "photo.jpg").exists())
        self.assertTrue((self.dir / "Documents" / "report.pdf").exists())
        self.assertTrue((self.dir / "Other" / "mystery.xyz").exists())

    def test_dry_run_changes_nothing(self):
        self.touch("photo.jpg")
        dm.cmd_organize(self.dir, ns(dry_run=True), OUT)
        self.assertTrue((self.dir / "photo.jpg").exists())
        self.assertFalse((self.dir / "Images").exists())

    def test_by_extension(self):
        self.touch("a.pdf"); self.touch("b.pdf")
        dm.cmd_organize(self.dir, ns(by="ext"), OUT)
        self.assertTrue((self.dir / "PDF" / "a.pdf").exists())
        self.assertTrue((self.dir / "PDF" / "b.pdf").exists())

    def test_by_size(self):
        self.touch("small.bin", "x")
        self.touch("big.bin", "y" * (200 * 1024))
        dm.cmd_organize(self.dir, ns(by="size"), OUT)
        self.assertTrue((self.dir / "Tiny" / "small.bin").exists())
        self.assertTrue((self.dir / "Small" / "big.bin").exists())

    def test_copy_keeps_original_and_no_history(self):
        self.touch("photo.jpg")
        dm.cmd_organize(self.dir, ns(copy=True), OUT)
        self.assertTrue((self.dir / "photo.jpg").exists())
        self.assertTrue((self.dir / "Images" / "photo.jpg").exists())
        self.assertEqual(dm.load_history(self.dir), [])

    def test_normalization(self):
        self.touch("My Photo.JPG")
        dm.cmd_organize(self.dir, ns(lowercase=True, replace_spaces=True, prefix="2026_"), OUT)
        self.assertTrue((self.dir / "Images" / "2026_my_photo.jpg").exists())

    def test_recursive_and_flatten(self):
        self.touch("top.jpg")
        self.touch("sub/nested.jpg")
        dm.cmd_organize(self.dir, ns(recursive=True, flatten=True), OUT)
        self.assertTrue((self.dir / "Images" / "top.jpg").exists())
        self.assertTrue((self.dir / "Images" / "nested.jpg").exists())

    def test_collision_suffix(self):
        (self.dir / "Images").mkdir()
        (self.dir / "Images" / "photo.jpg").write_text("existing")
        self.touch("photo.jpg")
        dm.cmd_organize(self.dir, ns(), OUT)
        self.assertTrue((self.dir / "Images" / "photo (1).jpg").exists())

    def test_dotfiles_untouched(self):
        self.touch(".secret")
        dm.cmd_organize(self.dir, ns(), OUT)
        self.assertTrue((self.dir / ".secret").exists())


class FilterTest(Base):
    def test_ext_filter(self):
        self.touch("a.jpg"); self.touch("b.pdf")
        files = dm.gather(self.dir, filters=dm.Filters(ns(ext=["jpg"])))
        self.assertEqual([f.name for f in files], ["a.jpg"])

    def test_exclude_glob(self):
        self.touch("keep.txt"); self.touch("skip.tmp")
        files = dm.gather(self.dir, filters=dm.Filters(ns(exclude=["*.tmp"])))
        self.assertEqual([f.name for f in files], ["keep.txt"])

    def test_size_filter(self):
        self.touch("small.bin", "x")
        self.touch("big.bin", "y" * 5000)
        files = dm.gather(self.dir, filters=dm.Filters(ns(min_size="1KB")))
        self.assertEqual([f.name for f in files], ["big.bin"])

    def test_age_filter(self):
        self.touch("old.txt", age_days=30)
        self.touch("new.txt", age_days=0)
        older = dm.gather(self.dir, filters=dm.Filters(ns(older_than=10)))
        self.assertEqual([f.name for f in older], ["old.txt"])
        newer = dm.gather(self.dir, filters=dm.Filters(ns(newer_than=10)))
        self.assertEqual([f.name for f in newer], ["new.txt"])


class CommandTest(Base):
    def test_dedupe_quarantine_and_undo(self):
        self.touch("a.txt", "same"); self.touch("b.txt", "same"); self.touch("c.txt", "diff")
        dm.cmd_dedupe(self.dir, ns(remove=True), OUT)
        survivors = {p.name for p in self.dir.iterdir() if p.is_file() and not p.name.startswith(".")}
        self.assertEqual(survivors, {"a.txt", "c.txt"})
        self.assertTrue((self.dir / dm.DUPLICATES_DIR / "b.txt").exists())
        dm.cmd_undo(self.dir, ns(), OUT)
        self.assertTrue((self.dir / "b.txt").exists())

    def test_clean_empty(self):
        (self.dir / "empty").mkdir()
        (self.dir / "full").mkdir()
        (self.dir / "full" / "x.txt").write_text("x")
        dm.cmd_clean_empty(self.dir, ns(), OUT)
        self.assertFalse((self.dir / "empty").exists())
        self.assertTrue((self.dir / "full").exists())

    def test_find(self):
        self.touch("a.pdf"); self.touch("b.txt"); self.touch("sub/c.pdf")
        self.assertEqual(dm.cmd_find(self.dir, ns(pattern="*.pdf", recursive=True), OUT), 0)

    def test_history_and_undo(self):
        self.touch("photo.jpg"); self.touch("report.pdf")
        dm.cmd_organize(self.dir, ns(), OUT)
        self.assertEqual(len(dm.load_history(self.dir)), 1)
        dm.cmd_undo(self.dir, ns(), OUT)
        self.assertTrue((self.dir / "photo.jpg").exists())
        self.assertTrue((self.dir / "report.pdf").exists())
        self.assertEqual(dm.load_history(self.dir), [])

    def test_undo_without_history(self):
        self.assertEqual(dm.cmd_undo(self.dir, ns(), OUT), 1)

    def test_stats_largest_tree_smoke(self):
        self.touch("a.jpg", "x" * 100); self.touch("b.pdf", "y" * 5000)
        self.assertEqual(dm.cmd_stats(self.dir, ns(), OUT), 0)
        self.assertEqual(dm.cmd_largest(self.dir, ns(number=1), OUT), 0)
        self.assertEqual(dm.cmd_tree(self.dir, ns(max_depth=None), OUT), 0)

    def test_config_custom_categories(self):
        cfg = self.dir / "cfg.json"
        cfg.write_text('{"categories": {"Pics": ["jpg"]}}')
        cats = dm.load_categories(cfg)
        self.assertEqual(dm.subdir_for(Path("a.jpg"), "type", cats), "Pics")


if __name__ == "__main__":
    unittest.main(verbosity=2)

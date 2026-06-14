#!/usr/bin/env python3
"""Tests for desktop_manager. Run: python3 test_desktop_manager.py"""
import tempfile
import unittest
from pathlib import Path

import desktop_manager as dm


class DesktopManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _touch(self, name: str) -> Path:
        p = self.dir / name
        p.write_text("x")
        return p

    def test_category_for(self) -> None:
        self.assertEqual(dm.category_for(Path("a.PNG")), "Images")
        self.assertEqual(dm.category_for(Path("a.pdf")), "Documents")
        self.assertEqual(dm.category_for(Path("a.whatisthis")), dm.OTHER)
        self.assertEqual(dm.category_for(Path("noext")), dm.OTHER)

    def test_organize_moves_files_into_categories(self) -> None:
        self._touch("photo.jpg")
        self._touch("report.pdf")
        self._touch("mystery.xyz")
        rc = dm.cmd_organize(self.dir, dry_run=False)
        self.assertEqual(rc, 0)
        self.assertTrue((self.dir / "Images" / "photo.jpg").exists())
        self.assertTrue((self.dir / "Documents" / "report.pdf").exists())
        self.assertTrue((self.dir / "Other" / "mystery.xyz").exists())
        self.assertTrue((self.dir / dm.UNDO_FILENAME).exists())

    def test_dry_run_moves_nothing(self) -> None:
        self._touch("photo.jpg")
        dm.cmd_organize(self.dir, dry_run=True)
        self.assertTrue((self.dir / "photo.jpg").exists())
        self.assertFalse((self.dir / "Images").exists())
        self.assertFalse((self.dir / dm.UNDO_FILENAME).exists())

    def test_existing_dirs_and_dotfiles_untouched(self) -> None:
        (self.dir / "KeepMe").mkdir()
        self._touch(".secret")
        dm.cmd_organize(self.dir, dry_run=False)
        self.assertTrue((self.dir / "KeepMe").is_dir())
        self.assertTrue((self.dir / ".secret").exists())

    def test_name_collision_gets_suffixed(self) -> None:
        (self.dir / "Images").mkdir()
        (self.dir / "Images" / "photo.jpg").write_text("existing")
        self._touch("photo.jpg")
        dm.cmd_organize(self.dir, dry_run=False)
        self.assertTrue((self.dir / "Images" / "photo.jpg").exists())
        self.assertTrue((self.dir / "Images" / "photo (1).jpg").exists())

    def test_undo_restores_files(self) -> None:
        self._touch("photo.jpg")
        self._touch("report.pdf")
        dm.cmd_organize(self.dir, dry_run=False)
        rc = dm.cmd_undo(self.dir)
        self.assertEqual(rc, 0)
        self.assertTrue((self.dir / "photo.jpg").exists())
        self.assertTrue((self.dir / "report.pdf").exists())
        self.assertFalse((self.dir / "Images").exists())  # empty dir cleaned up
        self.assertFalse((self.dir / dm.UNDO_FILENAME).exists())

    def test_undo_without_history_errors(self) -> None:
        self.assertEqual(dm.cmd_undo(self.dir), 1)


if __name__ == "__main__":
    unittest.main()

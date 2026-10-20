import json
import tempfile
import unittest
from pathlib import Path

from safe_duplicate_finder import (
    quarantine_duplicates,
    restore_quarantine,
    save_report,
    scan,
)


class SafeDuplicateFinderTests(unittest.TestCase):
    def test_finds_identical_files_not_different_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "scan"
            root.mkdir()
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            (root / "c.txt").write_text("different", encoding="utf-8")
            result = scan(root)
            self.assertEqual(len(result.duplicate_groups), 1)
            self.assertEqual(len(result.duplicate_groups[0]), 2)
            self.assertEqual(result.duplicate_files, 1)
            self.assertEqual(result.reclaimable_bytes, 4)

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            result = scan(temp)
            self.assertEqual(result.duplicate_groups, [])
            self.assertEqual(result.duplicate_files, 0)

    def test_quarantine_and_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "scan"
            qroot = Path(temp) / "quarantine"
            root.mkdir()
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            result = scan(root)
            group = result.duplicate_groups
            # Quarantine only the extra copy, leaving one copy in the scan folder.
            manifest = quarantine_duplicates(group, qroot)
            self.assertTrue(manifest.exists())
            self.assertEqual(len(list(root.glob("*.txt"))), 1)
            restored, errors = restore_quarantine(qroot)
            self.assertEqual(restored, 1)
            self.assertEqual(errors, [])
            self.assertEqual(len(list(root.glob("*.txt"))), 2)
            self.assertEqual((root / "b.txt").read_text(encoding="utf-8"), "same")

    def test_restore_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "scan"
            qroot = Path(temp) / "quarantine"
            root.mkdir()
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            result = scan(root)
            quarantine_duplicates(result.duplicate_groups, qroot)
            # Re-create original path; restore must not overwrite it.
            (root / "b.txt").write_text("new data", encoding="utf-8")
            restored, errors = restore_quarantine(qroot)
            self.assertEqual(restored, 0)
            self.assertTrue(errors)
            self.assertEqual((root / "b.txt").read_text(encoding="utf-8"), "new data")

    def test_quarantine_refuses_file_changed_after_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "scan"
            qroot = Path(temp) / "quarantine"
            root.mkdir()
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            result = scan(root)
            (root / "b.txt").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                quarantine_duplicates(result.duplicate_groups, qroot)
            self.assertEqual((root / "b.txt").read_text(encoding="utf-8"), "changed")

    def test_restore_refuses_corrupted_quarantined_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "scan"
            qroot = Path(temp) / "quarantine"
            root.mkdir()
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            result = scan(root)
            quarantine_duplicates(result.duplicate_groups, qroot)
            quarantined = list((qroot / "files").rglob("b.txt"))[0]
            quarantined.write_text("corrupt", encoding="utf-8")
            restored, errors = restore_quarantine(qroot)
            self.assertEqual(restored, 0)
            self.assertTrue(errors)
            self.assertFalse((root / "b.txt").exists())


if __name__ == "__main__":
    unittest.main()

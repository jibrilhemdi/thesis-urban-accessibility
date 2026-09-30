"""Public snapshot excludes raw data, credentials and packaging artifacts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
import zipfile

from src.pipeline.release_snapshot import audit_archive, create_archive, excluded, release_files


class ReleaseSnapshotTests(unittest.TestCase):
    def test_current_allowlist_is_public_and_complete(self):
        paths = release_files()
        names = {path.as_posix() for path in paths}
        self.assertGreater(len(paths), 300)
        self.assertFalse(any("/data/raw/" in name or name.endswith("/.env") or
                             "/__MACOSX/" in name or name.endswith("/.DS_Store")
                             for name in names))
        self.assertTrue(any(name.endswith("/appendix_boundary_catchment_example.png")
                            for name in names))

    def test_exclusion_and_archive_audit(self):
        for name in (".DS_Store", "__MACOSX/._table.csv", "docs/._hidden",
                     "outputs/latex/table.aux", "outputs/latex/table.synctex.gz", ".env"):
            self.assertTrue(excluded(Path(name)), name)
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(bad, "w") as archive:
                archive.writestr("data/raw/inside_airbnb/listings.csv", "private")
                archive.writestr("old-snapshot/data/raw/listings.csv", "private")
                archive.writestr("__MACOSX/._data", "metadata")
                archive.writestr("docs/readme.md", "public")
            count, forbidden = audit_archive(bad)
            self.assertEqual(count, 4)
            self.assertEqual(len(forbidden), 3)

    def test_new_archive_has_checksum_manifest_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "README.md"
            document.write_text("public", encoding="utf-8")
            archive = root / "snapshot.zip"
            create_archive(archive, [document], root)
            with zipfile.ZipFile(archive) as handle:
                self.assertEqual(set(handle.namelist()), {"README.md", "release_manifest.json"})
                self.assertEqual(len(json.loads(handle.read("release_manifest.json"))["README.md"]), 64)
            with self.assertRaises(FileExistsError):
                create_archive(archive, [document], root)


if __name__ == "__main__":
    unittest.main()

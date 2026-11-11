import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from app.services import recent_docs, workspace_session


class RecentDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        settings_path = str(self.folder / "settings.ini")
        for service in (recent_docs, workspace_session):
            settings_patch = patch.object(
                service, "_settings",
                lambda: QSettings(settings_path, QSettings.Format.IniFormat),
            )
            settings_patch.start()
            self.addCleanup(settings_patch.stop)

    def test_missing_temp_entries_removed_but_open_temp_files_kept(self):
        pdf = self.folder / "opened.pdf"
        pdf.write_bytes(b"%PDF")
        recent_docs.add_recent(str(pdf))
        self.assertEqual(recent_docs.load_recent(), [str(pdf)])
        pdf.unlink()
        self.assertEqual(recent_docs.load_recent(), [])
        self.assertEqual(recent_docs._settings().value(recent_docs._KEY, []), [])

    def test_session_restore_does_not_add_recent_document(self):
        from app.main_window import MdiMainWindow

        pdf = self.folder / "restored.pdf"
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(str(pdf))
        workspace_session.save_session([{"path": str(pdf), "page": 0}])
        window = MdiMainWindow()
        self.addCleanup(window.close)
        window.restore_session()
        self.assertEqual(recent_docs.load_recent(), [])
        self.assertEqual(window.viewer.count(), 1)

    def test_direct_open_is_recent_even_in_temp_folder(self):
        from app.main_window import MdiMainWindow

        pdf = self.folder / "opened.pdf"
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(str(pdf))
        window = MdiMainWindow()
        self.addCleanup(window.close)
        self.assertTrue(window.open_pdf(str(pdf)))
        self.assertEqual(recent_docs.load_recent(), [str(pdf)])

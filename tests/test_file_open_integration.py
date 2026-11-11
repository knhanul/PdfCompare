import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PyQt6.QtCore import QEventLoop, QSettings, QTimer
from PyQt6.QtWidgets import QApplication

from app.services import file_association, recent_docs, single_instance, workspace_session


def _wait(predicate, ms=3000):
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    poll.start(10)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    poll.stop()
    return predicate()


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        settings_path = str(self.folder / "settings.ini")
        for service in (recent_docs, workspace_session):
            p = patch.object(service, "_settings",
                             lambda: QSettings(settings_path, QSettings.Format.IniFormat))
            p.start()
            self.addCleanup(p.stop)
        self.name = f"PdfCompareTest.{uuid.uuid4().hex}"

    def make_pdf(self, name):
        path = self.folder / name
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(str(path))
        return str(path)

    def test_pdf_args_keep_existing_pdfs_only(self):
        pdf = self.make_pdf("한글 문서.pdf")
        txt = self.folder / "note.txt"
        txt.write_text("x")
        self.assertEqual(single_instance.pdf_args([pdf, str(txt), str(self.folder / "missing.pdf")]),
                         [os.path.abspath(pdf)])

    def test_no_running_instance_returns_false(self):
        self.assertFalse(single_instance.send_to_running([], name=self.name))

    def test_second_launch_forwards_paths_to_window(self):
        from app.main_window import MdiMainWindow

        window = MdiMainWindow()
        self.addCleanup(window.close)
        server = single_instance.InstanceServer(self.name, parent=window)
        server.files_received.connect(window.open_external_files)
        self.assertTrue(server.listen())
        pdf = self.make_pdf("한글 a.pdf")
        code = ("import sys; from PyQt6.QtCore import QCoreApplication; a = QCoreApplication([]); "
                "from app.services import single_instance as si; "
                "sys.exit(0 if si.send_to_running(sys.argv[1:2], name=sys.argv[2]) else 1)")
        root = Path(__file__).resolve().parent.parent
        sender = subprocess.Popen([sys.executable, "-c", code, pdf, self.name], cwd=root)
        self.addCleanup(sender.wait)
        self.assertTrue(_wait(lambda: window.viewer.count() == 1, 8000))
        self.assertEqual(sender.wait(5), 0)
        self.assertIs(window.mode_stack.currentWidget(), window.viewer)
        self.assertEqual(recent_docs.load_recent(), [pdf])


@unittest.skipUnless(file_association.is_supported(), "Windows registry only")
class FileAssociationTests(unittest.TestCase):
    def setUp(self):
        self.prefix = rf"Software\PdfCompareTest\{uuid.uuid4().hex}" + "\\"
        self.addCleanup(self._drop_parent)
        self.addCleanup(file_association._delete_tree, self.prefix.rstrip("\\"))

    def _drop_parent(self):
        try:
            file_association.winreg.DeleteKey(file_association.winreg.HKEY_CURRENT_USER, r"Software\PdfCompareTest")
        except OSError:
            pass

    def test_register_and_unregister_under_sandbox_prefix(self):
        keys = file_association._keys(self.prefix)
        self.assertFalse(file_association.is_registered(self.prefix))
        file_association.register(self.prefix)
        self.assertTrue(file_association.is_registered(self.prefix))
        self.assertIn('"%1"', file_association._get(keys["progid"] + r"\shell\open\command"))
        self.assertEqual(file_association._get(keys["capabilities"] + r"\FileAssociations", ".pdf"),
                         file_association.PROG_ID)
        self.assertTrue(file_association._has_value(keys["openwith"], file_association.PROG_ID))
        file_association.unregister(self.prefix)
        self.assertFalse(file_association.is_registered(self.prefix))
        self.assertFalse(file_association._has_value(keys["openwith"], file_association.PROG_ID))
        self.assertFalse(file_association._has_value(keys["registered"], file_association.APP_ID))


if __name__ == "__main__":
    unittest.main()

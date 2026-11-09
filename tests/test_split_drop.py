import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication

from app.viewer.document_manager import DocumentManager
from app.viewer.split_view import SplitView
from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])


def drop(widget, path):
    md = QMimeData(); md.setUrls([QUrl.fromLocalFile(path)])
    ev = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.dropEvent(ev)


class TestSplitDrop(unittest.TestCase):
    def test_drop_opens_in_target_pane_only(self):
        with tempfile.TemporaryDirectory() as t:
            ps = []
            for n in ("a.pdf", "b.pdf", "c.txt"):
                p = os.path.join(t, n)
                with open(p, "wb") as f:
                    f.write(make_pdf(2))
                ps.append(p)
            sv = SplitView(DocumentManager())
            self.assertTrue(sv.left.acceptDrops() and sv.right.acceptDrops())
            drop(sv.right, ps[0])
            self.assertEqual(sv.paths(), [None, os.path.abspath(ps[0])])
            drop(sv.left, ps[1])
            self.assertEqual(sv.paths(), [os.path.abspath(ps[1]), os.path.abspath(ps[0])])
            drop(sv.left, ps[2])  # PDF 아님 → 무시
            self.assertEqual(sv.paths()[0], os.path.abspath(ps[1]))
            drop(sv.right, ps[1])  # 다른 뷰의 문서도 같은 DocumentManager 문서로 열림
            self.assertEqual(sv.paths()[1], os.path.abspath(ps[1]))
            self.assertTrue(sv.btn_print.isEnabled())
            for d in list(sv.dm._docs.values()):
                d.close()


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf
from PyQt6.QtWidgets import QApplication

from app.shell.print_dialog import SmartPrintDialog, PrintSource, open_print_dialog, start_from_canvas
from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])


def pages(dlg):
    plan, srcs = dlg._make_plan()
    from app.print_engine import build_pdf
    d = pymupdf.open("pdf", build_pdf(plan, srcs))
    n = len(d); d.close()
    return n


class TestPrintDialog(unittest.TestCase):
    def test_single_modes_and_ranges(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(3)), left_page=1)
        d.refresh()
        self.assertTrue(d.btn_print.isEnabled())
        self.assertFalse(d.align_box.isVisible())
        exp = {"normal": 1, "split2": 2, "a3": 1, "nup": 1}  # 현재 페이지(2p) 기준, nup=2p+3p→1장
        for i in range(d.cmb_mode.count()):
            d.cmb_mode.setCurrentIndex(i)
            self.assertEqual(pages(d), exp[d.cmb_mode.currentData()], d.cmb_mode.currentData())
        d.cmb_mode.setCurrentIndex(0)
        d.cmb_range.setCurrentIndex(1)  # 전체
        self.assertEqual(pages(d), 3)
        d.refresh()
        self.assertEqual(d.lbl_nav.text(), "1 / 3")
        d.close()

    def test_dual_defaults_to_side_by_side_and_targets(self):
        L, R = PrintSource("l.pdf", make_pdf(3)), PrintSource("r.pdf", make_pdf(3))
        d = SmartPrintDialog(L, R, left_page=0, right_page=1, left_y=100.0, right_y=300.0)
        self.assertEqual(d.cmb_target.currentData(), "side")
        self.assertEqual(d.align["R"], (1, 300.0))
        self.assertEqual(d.lbl_align_r.text(), "오른쪽: 2페이지 · 300pt")
        d.refresh()
        self.assertGreaterEqual(len(d._plan.sheets), 1)
        for key in ("L", "R"):
            d.cmb_target.setCurrentIndex(d.cmb_target.findData(key))
            d.cmb_mode.setCurrentIndex(1)
            self.assertEqual(pages(d), 2)
        d.close()

    def test_preview_equals_full_output_sheet(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(2)), left_page=0)
        d.cmb_mode.setCurrentIndex(1); d.cmb_range.setCurrentIndex(1)
        d.refresh()
        from app.print_engine import build_pdf
        full = pymupdf.open("pdf", build_pdf(d._plan, d._plan_src))
        one = pymupdf.open("pdf", build_pdf(d._plan, d._plan_src, [2]))
        self.assertEqual(full[2].get_pixmap(dpi=36).samples, one[0].get_pixmap(dpi=36).samples)
        d.close()

    def test_viewer_and_split_entry_points(self):
        from app.shell.viewer_workspace import ViewerWorkspace
        from app.viewer.document import PdfDocument
        from app.viewer.split_view import SplitView
        from app.viewer.document_manager import DocumentManager
        with tempfile.TemporaryDirectory() as t:
            paths = []
            for n in "ab":
                p = os.path.join(t, n + ".pdf")
                open(p, "wb").write(make_pdf(3)); paths.append(p)
            vw = ViewerWorkspace()
            self.assertFalse(vw.btn_print.isEnabled())  # 문서 없음 → 비활성
            doc = PdfDocument(paths[0])
            vw.add_document(doc)
            self.assertTrue(vw.btn_print.isEnabled())
            sv = SplitView(DocumentManager())
            self.assertFalse(sv.btn_print.isEnabled())
            sv.set_documents(left=doc, right=PdfDocument(paths[1]))
            self.assertTrue(sv.btn_print.isEnabled())
            page, y = start_from_canvas(sv.left.canvas)
            self.assertEqual(page, 0)
            for c in (vw, sv):
                c.close()
            doc.close(); sv.right.canvas.doc.close()


if __name__ == "__main__":
    unittest.main()

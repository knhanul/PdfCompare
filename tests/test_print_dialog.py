from app.print_engine import mm
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


def settle(d, timeout=10.0):
    """비동기 렌더(미리보기/썸네일)가 끝날 때까지 이벤트를 처리한다."""
    import time
    from PyQt6.QtWidgets import QApplication
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if d.render_idle():
            break
        time.sleep(0.01)
    QApplication.processEvents()


class TestPrintDialog(unittest.TestCase):
    def test_single_modes_and_ranges(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(3)), left_page=1)
        d.refresh()
        self.assertTrue(d.btn_print.isEnabled())
        self.assertFalse(d.align_box.isVisible())
        exp = {"normal": 1, "split": 2, "a3": 1, "nup": 1, "region": 1, "trim": 1, "booklet": 2, "long": 1}  # 현재 페이지(2p) 기준, nup=2p+3p→1장
        from app.print_engine import Box
        d.region = Box(10, 10, 200, 300)
        for i in range(d.cmb_mode.count()):
            d.cmb_mode.setCurrentIndex(i)
            self.assertEqual(pages(d), exp[d.cmb_mode.currentData()], d.cmb_mode.currentData())
        d.cmb_mode.setCurrentIndex(0)
        d.cmb_range.setCurrentIndex(1)  # 전체
        self.assertEqual(pages(d), 3)
        d.refresh()
        self.assertEqual(d.lbl_nav.text(), "1 / 3")
        d.close()

    def test_extended_modes_spec_and_errors(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(10)), left_page=0)
        mi = lambda key: [d.cmb_mode.itemData(i) for i in range(d.cmb_mode.count())].index(key)
        d.cmb_range.setCurrentIndex(1)                       # 전체 10p
        d.cmb_mode.setCurrentIndex(mi("split"))
        for n in (2, 4, 6, 9):
            d.cmb_n.setCurrentIndex([d.cmb_n.itemData(i) for i in range(d.cmb_n.count())].index(n))
            d.refresh()
            self.assertEqual(len(d._plan.sheets), 10 * n, n)
        d.cmb_mode.setCurrentIndex(mi("nup"))
        for n, sheets in ((4, 3), (6, 2), (9, 2), (16, 1)):
            d.cmb_n.setCurrentIndex([d.cmb_n.itemData(i) for i in range(d.cmb_n.count())].index(n))
            d.refresh()
            self.assertEqual(len(d._plan.sheets), sheets, n)
        d.cmb_range.setCurrentIndex(3)                       # 조합
        d.ed_spec.setText("1,3,5-8")
        d.cmb_mode.setCurrentIndex(0)
        d.refresh()
        self.assertEqual(len(d._plan.sheets), 6)
        d.ed_spec.setText("1,99")
        d.refresh()
        self.assertFalse(d.btn_print.isEnabled())
        self.assertIn("99", d.lbl_spec_err.text())
        d.close()

    def test_region_requires_selection_and_pairs(self):
        from app.print_engine import Box
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(3)), left_page=0)
        d.cmb_mode.setCurrentIndex([d.cmb_mode.itemData(i) for i in range(d.cmb_mode.count())].index("region"))
        d.refresh()
        self.assertFalse(d.btn_print.isEnabled())            # 영역 미지정 → 출력 불가 + 안내
        self.assertIn("영역", d.lbl_info.text())
        d.btn_pick.setChecked(False)
        d.region = Box(20, 20, 220, 320)
        d.refresh()
        self.assertTrue(d.btn_print.isEnabled())
        d.btn_clear_region.click()
        self.assertIsNone(d.region)
        d.close()
        L, R = PrintSource("l.pdf", make_pdf(3)), PrintSource("r.pdf", make_pdf(2))
        d = SmartPrintDialog(L, R)
        for key, n in (("inter", 5), ("fb", 6)):
            d.cmb_target.setCurrentIndex([d.cmb_target.itemData(i) for i in range(d.cmb_target.count())].index(key))
            d.refresh()
            self.assertEqual(len(d._plan.sheets), n, key)
        d.close()

    def test_region_drag_maps_to_pdf_points(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(1)), left_page=0)
        d.cmb_mode.setCurrentIndex([d.cmb_mode.itemData(i) for i in range(d.cmb_mode.count())].index("region"))
        d.show()
        self.assertTrue(d.btn_pick.isChecked())
        k = d.pick.px_per_pt
        QTest.mousePress(d.pick, Qt.MouseButton.LeftButton, pos=QPoint(int(72 * k), int(144 * k)))
        QTest.mouseMove(d.pick, QPoint(int(172 * k), int(244 * k)))
        QTest.mouseRelease(d.pick, Qt.MouseButton.LeftButton, pos=QPoint(int(172 * k), int(244 * k)))
        r = d.region
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.x0, 72, delta=1.5); self.assertAlmostEqual(r.y0, 144, delta=1.5)
        self.assertAlmostEqual(r.w, 100, delta=2); self.assertAlmostEqual(r.h, 100, delta=2)
        self.assertFalse(d.btn_pick.isChecked())             # 선택 후 출력 미리보기로 전환
        d.refresh(); self.assertTrue(d.btn_print.isEnabled())
        d.close()

    def test_zoom_and_cache(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(2)), left_page=0)
        d.show(); d.refresh(); settle(d)
        w_page = d.view.pixmap().width()
        self.assertGreater(w_page, 0)
        d.btn_fit_width.click(); settle(d)
        w_width = d.view.pixmap().width()
        self.assertGreaterEqual(w_width, w_page)
        d.btn_zoom_in.click(); settle(d)
        self.assertGreater(d.view.pixmap().width(), w_width)
        n = len(d._cache)
        d.btn_zoom_out.click(); d.btn_zoom_in.click(); settle(d)   # 같은 배율은 캐시 재사용
        self.assertLessEqual(len(d._cache), n + 1)
        d.refresh(); settle(d)
        self.assertEqual(len(d._cache), 1)                     # 새 계획 → 캐시 무효화
        d.close()

    def test_thumbnails_populate_and_navigate(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(6)), left_page=0)
        d.show(); d.cmb_range.setCurrentIndex(1); d.refresh(); settle(d)
        self.assertEqual(d.thumbs.count(), 6)
        self.assertTrue(all(not d.thumbs.item(i).icon().isNull() for i in range(6)))   # 전부 렌더됨
        d.thumbs.setCurrentRow(4)                                # 썸네일 클릭 = 해당 출력 장으로 이동
        settle(d)
        self.assertEqual(d.lbl_nav.text(), "5 / 6")
        self.assertGreater(d.view.pixmap().width(), 0)
        d.btn_thumbs.setChecked(False)
        self.assertTrue(d.thumbs.isHidden())
        d.close()

    def test_stale_render_results_are_discarded(self):
        from PyQt6.QtGui import QImage
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(4)), left_page=0)
        d.show(); d.refresh(); settle(d)
        old_gen = d._plan_id
        d.cmb_range.setCurrentIndex(1); d.refresh(); settle(d)
        marker = QImage(7, 7, QImage.Format.Format_RGB888)
        before = d.view.pixmap().width()
        d._on_rendered(old_gen, 0, d._dpi_for(d._plan.sheets[0]), marker)   # 늦게 도착한 이전 세대 결과
        self.assertEqual(d.view.pixmap().width(), before)
        self.assertFalse(any(k[0] == old_gen for k in d._cache))
        d.close()

    def test_printer_margin_and_paper_warning(self):
        from unittest import mock
        from app.common import print_output
        with mock.patch.object(print_output, "available_printers", return_value=(["TestPrinter"], "TestPrinter")),              mock.patch.object(print_output, "min_margin_mm", return_value=8.0),              mock.patch.object(print_output, "supports_paper", side_effect=lambda n, s: s != "A3"):
            d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(1)), left_page=0)
            self.assertIsNone(d.cmb_printer.currentData())          # 기본은 자동 조회 안 함
            d.cmb_printer.setCurrentIndex(d.cmb_printer.findData("TestPrinter"))
            d.chk_hw.setChecked(True)
            d.refresh()
            self.assertIn("8.0mm", d.lbl_printer.text())
            sh = d._plan.sheets[0]
            dst = sh.placements[0].dst
            self.assertGreaterEqual(dst.x0, mm(8.0) - 0.01)         # 사용자 5mm < 프린터 8mm → 8mm 반영
            self.assertLessEqual(dst.x1, sh.width - mm(8.0) + 0.01)
            # PDF 저장 결과도 같은 계획(같은 여백)을 사용
            self.assertAlmostEqual(d._effective_margin_pt(), mm(8.0))
            d.cmb_sheet.setCurrentIndex(d.cmb_sheet.findText("A3"))
            self.assertIn("지원하지 않습니다", d.lbl_printer.text())
            d.chk_hw.setChecked(False)
            d.refresh()
            self.assertAlmostEqual(d._effective_margin_pt(), mm(5.0))
            d.close()

    def test_async_output_matches_preview_plan(self):
        from unittest import mock
        from PyQt6.QtWidgets import QApplication
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(5)), left_page=0)
        d.cmb_range.setCurrentIndex(1)
        d.cmb_mode.setCurrentIndex([d.cmb_mode.itemData(i) for i in range(d.cmb_mode.count())].index("nup"))
        d.cmb_n.setCurrentIndex([d.cmb_n.itemData(i) for i in range(d.cmb_n.count())].index(4))
        d.refresh()
        got = []
        d._start_output(got.append, "t")
        self.assertFalse(d.btn_save.isEnabled())               # 생성 중 잠금
        d._start_output(got.append, "t")                       # 중복 요청 무시
        d._worker.wait(15000)
        for _ in range(20):
            QApplication.processEvents()
        self.assertEqual(len(got), 1)
        out = pymupdf.open("pdf", got[0])
        self.assertEqual(out.page_count, len(d._plan.sheets))  # 미리보기 계획과 동일 장수
        out.close()
        self.assertTrue(d.btn_save.isEnabled()); self.assertIsNone(d._worker)
        d.close()

    def test_release_while_building_is_safe(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(30)), left_page=0)
        d.cmb_range.setCurrentIndex(1); d.refresh()
        d._start_output(lambda b: self.fail("해제 후 콜백 금지"), "t")
        d.release()
        self.assertIsNone(d._worker); self.assertFalse(d._busy)
        d.close()

    def test_trim_detect_and_booklet_ui(self):
        import pymupdf
        doc = pymupdf.open(); pg = doc.new_page(width=400, height=600)
        pg.draw_rect(pymupdf.Rect(100, 150, 300, 350), color=None, fill=(0, 0, 0))
        data = doc.tobytes(); doc.close()
        d = SmartPrintDialog(PrintSource("t.pdf", data))
        d.cmb_mode.setCurrentIndex([d.cmb_mode.itemData(i) for i in range(d.cmb_mode.count())].index("trim"))
        d.refresh()
        c = d._plan.sheets[0].placements[0].clip
        self.assertAlmostEqual(c.x0, 100, delta=12); self.assertAlmostEqual(c.y1, 350, delta=12)
        d.trim_sp["l"].setValue(-5)                          # 수동 보정: 왼쪽으로 5mm 확장
        d.refresh()
        self.assertLess(d._plan.sheets[0].placements[0].clip.x0, c.x0)
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

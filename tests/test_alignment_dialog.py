import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.print_engine import mm
from app.print_engine.stream import src_to_out
from app.shell.alignment_dialog import AlignSide, AlignmentView
from app.shell.print_dialog import PrintSource, SmartPrintDialog
from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])
ACC, REJ = True, False


def make_dlg(pages=6, left=(0, 0.0), right=(0, 0.0)):
    return SmartPrintDialog(PrintSource("left.pdf", make_pdf(pages)), PrintSource("right.pdf", make_pdf(pages)),
                            left[0], right[0], left[1], right[1])


def run_tab(d, action, apply=True):
    """시작 위치 맞춤 탭을 열고 action(view) 수행 후 '정렬 적용'/'변경 취소' 버튼을 누른다."""
    d.open_alignment()
    action(d.align_view)
    (d.align_view.btn_ok if apply else d.align_view.btn_cancel).click()


class TestAlignmentFlow(unittest.TestCase):
    def test1_independent_pages_reach_preview(self):
        d = make_dlg()
        run_tab(d, lambda a: (a.panels[0].set_state(2, 80.0), a.panels[1].set_state(4, 135.0)), True)
        self.assertEqual(d.lbl_align_l.text(), "왼쪽: 3페이지 · 80pt")
        self.assertEqual(d.lbl_align_r.text(), "오른쪽: 5페이지 · 135pt")
        segs = d._plan.meta["segments"]
        self.assertEqual(segs["L"][0].page, 2)
        self.assertEqual(segs["R"][0].page, 4)
        self.assertEqual(len(segs["L"]), 4); self.assertEqual(len(segs["R"]), 2)
        d.close()

    def test2_different_y_same_height(self):
        d = make_dlg()
        run_tab(d, lambda a: (a.panels[0].set_state(2, 80.0), a.panels[1].set_state(4, 135.0)), True)
        ky, yl = src_to_out(d._plan, "L", 2, 80.0)
        kr, yr = src_to_out(d._plan, "R", 4, 135.0)
        self.assertEqual(ky, kr)
        self.assertAlmostEqual(yl, yr, places=6)
        d.close()

    def test3_nudge_1mm_moves_line_and_output(self):
        d = make_dlg(left=(0, 100.0), right=(0, 100.0))
        run_tab(d, lambda a: a.panels[1].nudge(1), True)
        self.assertAlmostEqual(d.align["R"][1], 100.0 + mm(1), places=6)
        self.assertAlmostEqual(d.align["L"][1], 100.0)
        # 출력 좌표: 오른쪽 첫 배치의 클립 시작이 정확히 1mm 아래로 이동
        first_r = [p for p in d._plan.sheets[0].placements if p.source_id == "R"][0]
        self.assertAlmostEqual(first_r.clip.y0, 100.0 + mm(1), places=6)
        # 두 기준선은 여전히 같은 출력 높이
        self.assertAlmostEqual(src_to_out(d._plan, "L", 0, 100.0)[1], src_to_out(d._plan, "R", 0, 100.0 + mm(1))[1], places=6)
        d.close()

    def test4_cancel_keeps_values_and_preview(self):
        d = make_dlg(left=(1, 50.0), right=(2, 70.0))
        d.refresh()
        before = (dict(d.align), d.lbl_nav.text(), d._plan.meta["baseline"])
        run_tab(d, lambda a: (a.panels[0].set_state(4, 300.0), a.panels[1].nudge(1)), False)
        self.assertEqual(before, (dict(d.align), d.lbl_nav.text(), d._plan.meta["baseline"]))
        d.close()

    def test5_reset_cancel_vs_apply(self):
        d = make_dlg(left=(1, 50.0), right=(2, 70.0))
        run_tab(d, lambda a: a.reset(), False)
        self.assertEqual(d.align, {"L": (1, 50.0), "R": (2, 70.0)})
        run_tab(d, lambda a: a.reset(), True)
        self.assertEqual(d.align, {"L": (0, 0.0), "R": (0, 0.0)})
        d.close()


class TestAlignmentViewUI(unittest.TestCase):
    def _dlg(self, pages=3, name="x.pdf", rot=0):
        data = make_pdf(pages, rotation=rot)
        d = AlignmentView([AlignSide(name, data), AlignSide(name, data)], [(0, 0.0), (0, 0.0)])
        d.show(); _app.processEvents(); d._relayout()
        return d

    def test6_click_maps_to_pt_independent_of_zoom_and_size(self):
        d = self._dlg()
        pv = d.panels[0].preview
        res = []
        for size, zoom in (((1050, 750), None), ((800, 600), None), ((1050, 750), 1.5)):
            d.resize(*size)
            _app.processEvents()
            if zoom: d._fit = False; d._zoom = zoom
            d._relayout()
            y_px = 200
            QTest.mouseClick(pv, Qt.MouseButton.LeftButton, pos=QPoint(10, y_px))
            self.assertAlmostEqual(d.panels[0].y(), y_px / pv.scale, places=6)
            res.append(pv.scale)
        self.assertGreater(len({round(r, 3) for r in res}), 1)  # 배율이 실제로 달랐다
        # 좌우 배율 동일
        self.assertAlmostEqual(d.panels[0].preview.scale, d.panels[1].preview.scale)
        # 저장값은 창 크기 변경 후에도 유지
        y = d.panels[0].y(); d.resize(900, 650); _app.processEvents(); d._relayout()
        self.assertAlmostEqual(d.panels[0].y(), y)
        d.close()

    def test6b_rotated_pdf_click_coordinates_match_engine(self):
        d = self._dlg(rot=90)
        pm = d.panels[0].doc[0]
        self.assertAlmostEqual(d.panels[0].preview.height() / d.panels[0].preview.scale, pm.rect.height, delta=2.0)
        d.close()

    def test7_long_name_and_100_pages(self):
        data = make_pdf(150)
        t0 = time.time()
        d = AlignmentView([AlignSide("아주아주긴파일이름_" * 12 + ".pdf", data)] * 2, [(0, 0.0)] * 2)
        d.show(); _app.processEvents(); d._relayout()
        d.panels[0].sp_page.setValue(120)
        _app.processEvents()
        self.assertLess(time.time() - t0, 3.0)
        self.assertLessEqual(d.panels[0].title.minimumSizeHint().width(), 200)
        self.assertIn("아주아주긴파일이름", d.panels[0].title.toolTip())
        self.assertNotEqual(d.panels[0].title.text(), d.panels[0].title.toolTip())
        d.close()

    def test_result_state_after_apply(self):
        d = self._dlg()
        d.panels[1].set_state(2, 55.0)
        self.assertEqual(d.result_state(), [(0, 0.0), (2, 55.0)])


class TestAlignmentTab(unittest.TestCase):
    def test_tab_flow_apply_cancel_esc_and_isolation(self):
        d = make_dlg(left=(1, 50.0), right=(2, 70.0))
        d.show(); d.refresh()
        self.assertTrue(d.tabs.isVisible())
        self.assertEqual(d.pv_stack.currentIndex(), 0)
        d.tabs.setCurrentIndex(1)                              # 탭 클릭 = 맞춤 화면(팝업 아님)
        self.assertEqual(d.pv_stack.currentIndex(), 1)
        self.assertIsNotNone(d.align_view)
        d.align_view.panels[0].set_state(3, 40.0)
        d.tabs.setCurrentIndex(0)                              # 미적용 상태로 미리보기 복귀 → 계획 변화 없음
        self.assertEqual(d.align["L"], (1, 50.0))
        d.tabs.setCurrentIndex(1)
        self.assertEqual(d.align_view.panels[0].page(), 3)    # 보관된 편집이 유지됨
        d._on_escape()                                         # Esc = 변경 취소 + 미리보기
        self.assertIsNone(d.align_view); self.assertEqual(d.pv_stack.currentIndex(), 0)
        self.assertEqual(d.align["L"], (1, 50.0))
        run_tab(d, lambda a: a.panels[0].set_state(3, 40.0), True)
        self.assertEqual(d.align["L"], (3, 40.0))
        self.assertEqual(d.pv_stack.currentIndex(), 0)         # 적용 후 미리보기 탭, 즉시 반영
        self.assertEqual(d._plan.meta["segments"]["L"][0].page, 3)
        self.assertEqual(d.tabs.currentIndex(), 0)
        d.close()

    def test_tab_hidden_for_single_and_disabled_for_single_target(self):
        s = SmartPrintDialog(PrintSource("a.pdf", make_pdf(2)), left_page=0)
        s.show(); self.assertFalse(s.tabs.isVisible()); s.open_alignment(); self.assertIsNone(s.align_view)
        s.close()
        d = make_dlg(); d.show()
        d.cmb_target.setCurrentIndex(1)                        # 왼쪽만 출력
        self.assertFalse(d.tabs.isTabEnabled(1))
        d.cmb_target.setCurrentIndex(0)
        self.assertTrue(d.tabs.isTabEnabled(1))
        d.close()

    def test_viewer_state_untouched_and_released(self):
        d = make_dlg(); d.show()
        d.open_alignment()
        view = d.align_view
        d.release()
        self.assertIsNone(d.align_view); self.assertEqual(view._docs, [])
        d.close()


if __name__ == "__main__":
    unittest.main()

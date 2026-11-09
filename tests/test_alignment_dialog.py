import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

from app.print_engine import mm
from app.print_engine.stream import src_to_out
from app.shell.alignment_dialog import AlignSide, AlignmentDialog
from app.shell.print_dialog import PrintSource, SmartPrintDialog
from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])
ACC, REJ = QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected


def make_dlg(pages=6, left=(0, 0.0), right=(0, 0.0)):
    return SmartPrintDialog(PrintSource("left.pdf", make_pdf(pages)), PrintSource("right.pdf", make_pdf(pages)),
                            left[0], right[0], left[1], right[1])


def fake_exec(action, result):
    def run(self):
        action(self)
        return result
    return run


class TestAlignmentFlow(unittest.TestCase):
    def test1_independent_pages_reach_preview(self):
        d = make_dlg()
        with mock.patch.object(AlignmentDialog, "exec", fake_exec(
                lambda a: (a.panels[0].set_state(2, 80.0), a.panels[1].set_state(4, 135.0)), ACC)):
            d.open_alignment()
        self.assertEqual(d.lbl_align_l.text(), "왼쪽: 3페이지 · 80pt")
        self.assertEqual(d.lbl_align_r.text(), "오른쪽: 5페이지 · 135pt")
        segs = d._plan.meta["segments"]
        self.assertEqual(segs["L"][0].page, 2)
        self.assertEqual(segs["R"][0].page, 4)
        self.assertEqual(len(segs["L"]), 4); self.assertEqual(len(segs["R"]), 2)
        d.close()

    def test2_different_y_same_height(self):
        d = make_dlg()
        with mock.patch.object(AlignmentDialog, "exec", fake_exec(
                lambda a: (a.panels[0].set_state(2, 80.0), a.panels[1].set_state(4, 135.0)), ACC)):
            d.open_alignment()
        ky, yl = src_to_out(d._plan, "L", 2, 80.0)
        kr, yr = src_to_out(d._plan, "R", 4, 135.0)
        self.assertEqual(ky, kr)
        self.assertAlmostEqual(yl, yr, places=6)
        d.close()

    def test3_nudge_1mm_moves_line_and_output(self):
        d = make_dlg(left=(0, 100.0), right=(0, 100.0))
        with mock.patch.object(AlignmentDialog, "exec", fake_exec(lambda a: a.panels[1].nudge(1), ACC)):
            d.open_alignment()
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
        with mock.patch.object(AlignmentDialog, "exec", fake_exec(
                lambda a: (a.panels[0].set_state(4, 300.0), a.panels[1].nudge(1)), REJ)):
            d.open_alignment()
        self.assertEqual(before, (dict(d.align), d.lbl_nav.text(), d._plan.meta["baseline"]))
        d.close()

    def test5_reset_cancel_vs_apply(self):
        d = make_dlg(left=(1, 50.0), right=(2, 70.0))
        with mock.patch.object(AlignmentDialog, "exec", fake_exec(lambda a: a.reset(), REJ)):
            d.open_alignment()
        self.assertEqual(d.align, {"L": (1, 50.0), "R": (2, 70.0)})
        with mock.patch.object(AlignmentDialog, "exec", fake_exec(lambda a: a.reset(), ACC)):
            d.open_alignment()
        self.assertEqual(d.align, {"L": (0, 0.0), "R": (0, 0.0)})
        d.close()


class TestAlignmentDialogUI(unittest.TestCase):
    def _dlg(self, pages=3, name="x.pdf", rot=0):
        data = make_pdf(pages, rotation=rot)
        d = AlignmentDialog([AlignSide(name, data), AlignSide(name, data)], [(0, 0.0), (0, 0.0)])
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
        d = AlignmentDialog([AlignSide("아주아주긴파일이름_" * 12 + ".pdf", data)] * 2, [(0, 0.0)] * 2)
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
        d.accept()
        self.assertEqual(d.result_state(), [(0, 0.0), (2, 55.0)])


if __name__ == "__main__":
    unittest.main()

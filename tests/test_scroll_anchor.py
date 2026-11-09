import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf
from PyQt6.QtWidgets import QApplication

from app.print_engine import mm
from app.viewer import scroll_anchor as sa
from app.viewer.document import PdfDocument
from app.viewer.document_manager import DocumentManager
from app.viewer.split_view import SplitView

_app = QApplication.instance() or QApplication([])
A4, A3 = (mm(210), mm(297)), (mm(297), mm(420))
TXT_SET = '⌖ 현재 위치 맞춤'
TXT_RESET = '⌖ 기준점 다시 맞춤'


def mkpdf(path, sizes):
    d = pymupdf.open()
    for i, (w, h) in enumerate(sizes):
        d.new_page(width=w, height=h).insert_text((40, 60), f"p{i}", fontsize=14)
    d.save(path)
    d.close()
    return path


class TestAnchorMath(unittest.TestCase):
    sizes_a = [A4] * 6
    sizes_b = [A4, A3, A4, A3, A4, A4, A4]

    def test_roundtrip_and_mixed_sizes(self):
        for sizes in (self.sizes_a, self.sizes_b):
            for pos in (0.0, 0.3, 1.5, 3.99, 5.5):
                d = sa.pos_to_coord(sizes, pos)
                self.assertAlmostEqual(sa.coord_to_pos(sizes, d), pos, places=6)

    def test_map_equal_pt_movement_and_clamp(self):
        la = sa.make_anchor("L", self.sizes_a, 2.2)
        rb = sa.make_anchor("R", self.sizes_b, 4.4)
        self.assertAlmostEqual(sa.map_position(self.sizes_a, la, self.sizes_b, rb, 2.2), 4.4, places=6)
        d0 = sa.pos_to_coord(self.sizes_b, 4.4)
        p2 = sa.map_position(self.sizes_a, la, self.sizes_b, rb, 3.0)
        delta = sa.pos_to_coord(self.sizes_a, 3.0) - sa.pos_to_coord(self.sizes_a, 2.2)
        self.assertAlmostEqual(sa.pos_to_coord(self.sizes_b, p2) - d0, delta, places=6)
        end = sa.map_position(self.sizes_a, la, self.sizes_b, rb, 6.0)
        self.assertLessEqual(end, len(self.sizes_b))
        self.assertGreaterEqual(sa.map_position(self.sizes_b, rb, self.sizes_a, la, 0.0), 0.0)


class SplitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.pl = mkpdf(os.path.join(t, "l.pdf"), [A4] * 8)
        self.pr = mkpdf(os.path.join(t, "r.pdf"), [A4, A3, A4, A3, A4, A3, A4, A4, A4, A4])
        self.short = mkpdf(os.path.join(t, "s.pdf"), [A4] * 3)
        self.docs = []
        self.sv = SplitView(DocumentManager())
        self.sv.resize(1500, 800)
        self.sv.show()
        _app.processEvents()
        self.dl, self.dr = self.open(self.pl), self.open(self.pr)
        self.sv.set_documents(left=self.dl, right=self.dr)
        _app.processEvents()
        self.sv.sync_zoom.setChecked(False)
        for p in (self.sv.left, self.sv.right):
            p.canvas.set_zoom(1.0)
        _app.processEvents()

    def tearDown(self):
        self.sv._toast_timer.stop()
        self.sv.close()
        # 백그라운드 렌더 스레드가 PyMuPDF/임시 파일을 잡은 채 다음 테스트로 넘어가면 간헐적 크래시/삭제 실패
        from app.viewer.render_service import reset_render_service
        reset_render_service()
        _app.processEvents()
        # 위젯을 결정적으로 파괴(순환 참조의 임의 시점 GC 파괴 방지)
        from PyQt6 import sip
        sip.delete(self.sv)
        import gc
        gc.collect()
        for d in self.docs:
            d.close()
        self.tmp.cleanup()

    def open(self, path):
        d = PdfDocument(path)
        self.docs.append(d)
        return d

    def coord(self, pane):
        return sa.pos_to_coord(pane.canvas.doc.page_sizes, sa.capture_pos(pane.canvas, 0.5))

    def scrolls(self):
        return (self.sv.left.canvas.verticalScrollBar().value(),
                self.sv.right.canvas.verticalScrollBar().value())

    def goto(self, pane, page, y_pt):
        pane.canvas.go_to_page(page, y_pt)
        _app.processEvents()

    def place(self, left, right):
        """사용자 흐름: 동기화 OFF 로 두 화면을 각각 맞춘 뒤(=이후 버튼 클릭)."""
        self.sv.sync_scroll.setChecked(False)
        self.goto(self.sv.left, *left)
        self.goto(self.sv.right, *right)

    def bump(self, pane, dv):
        sb = pane.canvas.verticalScrollBar()
        sb.setValue(sb.value() + dv)
        _app.processEvents()


class TestAnchorSync(SplitCase):
    def test1_general_sync_unchanged_without_anchor(self):
        self.sv.left.canvas.go_to_page(3)
        _app.processEvents()
        self.assertAlmostEqual(self.sv.left.canvas.position()[0], self.sv.right.canvas.position()[0], places=2)
        self.assertIsNone(self.sv._anchors)

    def test2_3_different_pages_and_y_both_directions_and_no_jump(self):
        sv = self.sv
        sv.sync_scroll.setChecked(False)
        self.place((2, mm(80)), (4, mm(135)))
        before = self.scrolls()
        sv.btn_anchor.click()
        _app.processEvents()
        self.assertEqual(self.scrolls(), before)  # 화면 점프 없음
        self.assertTrue(sv.sync_scroll.isChecked())
        self.assertEqual(sv.btn_anchor.text(), TXT_RESET)
        self.assertIn("기준으로 동기화", sv.lbl_toast.text())
        l0, r0 = self.coord(sv.left), self.coord(sv.right)
        self.bump(sv.left, 500)
        self.assertAlmostEqual(self.coord(sv.right) - r0, self.coord(sv.left) - l0, delta=2.5)
        self.assertNotEqual(self.scrolls()[1], before[1])
        l1, r1 = self.coord(sv.left), self.coord(sv.right)
        self.bump(sv.right, -300)
        self.assertAlmostEqual(self.coord(sv.right) - r1, self.coord(sv.left) - l1, delta=2.5)

    def test4_re_anchor_replaces_old(self):
        sv = self.sv
        self.place((1, 100), (1, 100))
        sv.btn_anchor.click()
        first = dict(sv._anchors)
        sv.sync_scroll.setChecked(False)
        self.place((5, 200), (7, 50))
        before = self.scrolls()
        sv.btn_anchor.click()
        _app.processEvents()
        self.assertEqual(self.scrolls(), before)
        self.assertNotEqual(first[sv.left], sv._anchors[sv.left])
        l0, r0 = self.coord(sv.left), self.coord(sv.right)
        self.bump(sv.left, 400)
        self.assertAlmostEqual(self.coord(sv.right) - r0, self.coord(sv.left) - l0, delta=2.5)

    def test5_on_off_keeps_anchor_and_prevents_jump(self):
        sv = self.sv
        self.place((2, 100), (4, 100))
        sv.btn_anchor.click()
        sv.sync_scroll.setChecked(False)
        anchors = dict(sv._anchors)
        r_before = self.scrolls()[1]
        self.bump(sv.left, 700)
        self.assertEqual(self.scrolls()[1], r_before)  # OFF -> 독립
        sv.sync_scroll.setChecked(True)
        _app.processEvents()
        self.assertEqual(sv._anchors, anchors)  # 기준점 유지
        self.assertTrue(sv._anchor_stale)  # 어긋남 감지
        self.assertEqual(self.scrolls()[1], r_before)  # ON 만으로 점프 없음
        self.bump(sv.left, 50)
        self.assertEqual(self.scrolls()[1], r_before)  # 보류 중에도 강제 이동 없음
        sv.btn_anchor.click()
        _app.processEvents()
        self.assertFalse(sv._anchor_stale)
        sv.sync_scroll.setChecked(False)
        sv.sync_scroll.setChecked(True)  # 어긋남 없이 OFF->ON: 그대로 복원
        self.assertFalse(sv._anchor_stale)

    def test6_zoom_and_window_size(self):
        sv = self.sv
        self.place((2, 100), (3, 100))
        sv.btn_anchor.click()
        anchor_before = dict(sv._anchors)
        sv.right.canvas.set_zoom(1.6)
        _app.processEvents()
        sv.resize(1100, 650)
        _app.processEvents()
        self.assertEqual(sv._anchors, anchor_before)  # 문서 좌표 기준점 유지
        self.assertLess(abs(sv._anchor_offset()), 3.0)  # 줌/리사이즈 직후에도 관계 유지(첫 스크롤에서 튀지 않음)
        l0, r0 = self.coord(sv.left), self.coord(sv.right)
        self.bump(sv.left, 400)
        self.assertAlmostEqual(self.coord(sv.right) - r0, self.coord(sv.left) - l0, delta=3.0)

    def test7_fast_scroll_no_feedback_loop(self):
        sv = self.sv
        self.place((1, 100), (2, 100))
        sv.btn_anchor.click()
        hits = {"n": 0}
        sv.right.canvas.verticalScrollBar().valueChanged.connect(lambda *_: hits.__setitem__("n", hits["n"] + 1))
        lb = sv.left.canvas.verticalScrollBar()
        for k in range(60):
            lb.setValue(lb.value() + (37 if k % 2 == 0 else -11))
        _app.processEvents()
        self.assertLessEqual(hits["n"], 60)  # 변경당 최대 1회
        rb = sv.right.canvas.verticalScrollBar()
        for k in range(60):
            rb.setValue(rb.value() + 29)
        _app.processEvents()
        l0, r0 = sv._anchors[sv.left], sv._anchors[sv.right]
        off = sa.relation_offset(sv.left.canvas.doc.page_sizes, l0, sa.capture_pos(sv.left.canvas, l0.viewport_ratio),
                                 sv.right.canvas.doc.page_sizes, r0, sa.capture_pos(sv.right.canvas, r0.viewport_ratio))
        self.assertLess(abs(off), 3.0)

    def test8_short_document_end_boundary(self):
        sv = self.sv
        sv.set_documents(right=self.open(self.short))
        _app.processEvents()
        sv.right.canvas.set_zoom(1.0)
        self.place((1, 100), (1, 100))
        sv.btn_anchor.click()
        lb = sv.left.canvas.verticalScrollBar()
        lb.setValue(lb.maximum())
        _app.processEvents()
        rb = sv.right.canvas.verticalScrollBar()
        self.assertEqual(rb.value(), rb.maximum())  # 짧은 쪽은 끝에서 멈춤
        lb.setValue(lb.value() - 10)
        _app.processEvents()  # 되돌아와도 오류 없음

    def test9_document_replacement_clears_anchor(self):
        sv = self.sv
        self.place((1, 100), (1, 100))
        sv.btn_anchor.click()
        self.assertIsNotNone(sv._anchors)
        sv.set_documents(right=self.open(self.short))
        _app.processEvents()
        self.assertIsNone(sv._anchors)
        self.assertEqual(sv.btn_anchor.text(), TXT_SET)
        sv.left.canvas.go_to_page(1)  # 이후는 기존 일반 동기화
        _app.processEvents()
        self.assertAlmostEqual(sv.left.canvas.position()[0], sv.right.canvas.position()[0], places=2)

    def test_button_disabled_without_both_docs(self):
        sv2 = SplitView(DocumentManager())
        self.assertFalse(sv2.btn_anchor.isEnabled())
        sv2.set_documents(left=self.open(self.pl))
        self.assertFalse(sv2.btn_anchor.isEnabled())
        sv2.set_documents(right=self.open(self.pr))
        self.assertTrue(sv2.btn_anchor.isEnabled())
        sv2.close()

    def test10_print_start_positions_independent(self):
        from app.shell.print_dialog import SmartPrintDialog, print_source_from_doc
        sv = self.sv

        def mk():
            return SmartPrintDialog(print_source_from_doc(self.dl), print_source_from_doc(self.dr),
                                    1, 2, 80.0, 135.0)

        from app.viewer.render_service import render_service
        render_service().pool.waitForDone(5000)  # 메인 스레드 PyMuPDF 사용 전 렌더 스레드 정리
        d1 = mk()
        a1 = dict(d1.align)
        d1.done(0)
        self.place((3, 200), (6, 10))
        sv.btn_anchor.click()
        self.bump(sv.left, 300)
        render_service().pool.waitForDone(5000)
        d2 = mk()
        self.assertEqual(a1, d2.align)  # 스크롤 기준점이 인쇄 시작 위치를 바꾸지 않음
        d2.done(0)


if __name__ == "__main__":
    unittest.main()

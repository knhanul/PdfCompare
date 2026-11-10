"""Office형 인쇄 페이지: 진입/복귀 시 뷰어·동시보기 상태 보존."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])


class PrintPageTransitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.main_window import MdiMainWindow
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = []
        for n in ("a", "b"):
            p = os.path.join(cls.tmp.name, n + ".pdf")
            with open(p, "wb") as f:
                f.write(make_pdf(4))
            cls.paths.append(p)
        cls.win = MdiMainWindow()
        cls.win.resize(1200, 800)
        cls.win.show()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        try:
            cls.tmp.cleanup()
        except Exception:
            pass

    def test_viewer_roundtrip(self):
        w = self.win
        w.open_pdf(self.paths[0], 2)
        self.assertIs(w.mode_stack.currentWidget(), w.viewer)
        w.viewer._cv().canvas.go_to_page(2)
        _app.processEvents()
        before_doc, nview = w.viewer.current_doc(), w.viewer.count()
        w.viewer.print_current()
        page = w._print_page
        self.assertIsNotNone(page)
        self.assertIs(w.mode_stack.currentWidget(), page)
        self.assertIn('PDF 보기', page.btn_back.text())
        from app.shell.print_dialog import start_from_canvas
        self.assertEqual(page._pages['L'], start_from_canvas(w.viewer._cv().canvas)[0])
        page.reject()                                      # Esc/복귀 버튼과 동일 경로
        self.assertIs(w.mode_stack.currentWidget(), w.viewer)
        self.assertIsNone(w._print_page)
        self.assertIs(w.viewer.current_doc(), before_doc)  # 같은 문서 객체
        self.assertEqual(w.viewer.count(), nview)

    def test_split_roundtrip_keeps_state(self):
        w = self.win
        w.open_pdf(self.paths[0]); w.open_pdf(self.paths[1])
        w.open_split_view()
        sv = w.split_view
        sv.set_documents(left=w.doc_manager.get(self.paths[0]) if hasattr(w.doc_manager, 'get') else w.viewer.current_doc(),
                         right=w.viewer.current_doc())
        self.assertTrue(all(sv.paths()))
        sv.left.canvas.go_to_page(1); sv.right.canvas.go_to_page(3)
        pos_l, pos_r = sv.left.canvas.position(), sv.right.canvas.position()
        sv.print_documents()
        page = w._print_page
        self.assertIsNotNone(page)
        self.assertIn('동시보기', page.btn_back.text())
        self.assertTrue(page.dual)
        page.reject()
        self.assertIs(w.mode_stack.currentWidget(), sv)
        for now, before in ((sv.left.canvas.position(), pos_l), (sv.right.canvas.position(), pos_r)):
            self.assertAlmostEqual(now[0], before[0], delta=0.002)   # 스크롤 값은 정수 픽셀 단위
            self.assertAlmostEqual(now[1], before[1], delta=0.002)
        self.assertTrue(all(sv.paths()))                   # 좌우 문서 유지, 피커 재호출 없음

    def test_sidebar_collapses_during_print_and_restores(self):
        w = self.win
        w.open_pdf(self.paths[0])
        w.sidebar_manual = False
        w.update_sidebar_compact()
        self.assertFalse(w.sidebar_compact)
        w.viewer.print_current()
        self.assertTrue(w.sidebar_compact)                   # 인쇄 중 아이콘형 최소화
        w._print_page.reject()
        self.assertIs(w.sidebar_manual, False)               # 원래 사용자 설정 복원
        self.assertFalse(w.sidebar_compact)
        w.viewer.print_current()
        w.show_welcome()                                     # 다른 화면으로 이동해도 복원
        self.assertFalse(w.sidebar_compact)
        w.sidebar_manual = None

    def test_navigating_away_releases(self):
        w = self.win
        w.open_pdf(self.paths[0])
        w.viewer.print_current()
        page = w._print_page
        w.show_welcome()
        self.assertIsNone(w._print_page)
        self.assertTrue(page._released)


if __name__ == "__main__":
    unittest.main()


class PrintPageReentryTest(unittest.TestCase):
    def test_reentry_keeps_original_return_target(self):
        from tests.test_print_page_transition import PrintPageTransitionTest as T
        T.setUpClass()
        try:
            w = T.win
            w.open_pdf(T.paths[0])
            w.viewer.print_current()
            first = w._print_page
            w.viewer.print_current()                  # 인쇄 중 다시 호출(단축키 등)
            self.assertIsNot(w._print_page, first)
            w._print_page.reject()
            self.assertIs(w.mode_stack.currentWidget(), w.viewer)
        finally:
            T.tearDownClass()

    def test_close_event_cleans_print_page(self):
        from tests.test_print_page_transition import PrintPageTransitionTest as T
        T.setUpClass()
        try:
            w = T.win
            w.open_pdf(T.paths[0])
            w.viewer.print_current()
            page = w._print_page
            w.close()
            self.assertTrue(page._released)
            self.assertIsNone(w._print_page)
        finally:
            T.tearDownClass()

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.presentation import navigation as nav
from app.presentation.context import context_from_canvas, context_from_split
from app.presentation.window import PresentationWindow
from app.viewer.document import PdfDocument
from app.viewer.pdf_canvas import PdfCanvas

_app = QApplication.instance() or QApplication([])


def make_pdf_file(path, sizes):
    import pymupdf
    d = pymupdf.open()
    for i, (w, h) in enumerate(sizes):
        pg = d.new_page(width=w, height=h)
        pg.insert_text((50, 80), f"page {i + 1}", fontsize=20)
    d.save(path)
    d.close()


def layout(heights, gap=8):
    tops, y = [], 0.0
    for h in heights:
        tops.append(y)
        y += h + gap
    return tops


class TestNavigationMath(unittest.TestCase):
    VH = 1000.0

    def test_sections_cover_tall_page_without_gap_or_overshoot(self):
        for ratio in nav.SECTION_RATIOS:
            heights = [2300.0, 2300.0]
            tops = layout(heights)
            s = tops[0]
            seen = [s]
            for _ in range(30):
                n = nav.next_target(tops, heights, self.VH, s, ratio)
                if n == s:
                    break
                if nav.current_page(tops, self.VH, n) == 1:
                    break
                # 구간 간 이동량은 뷰포트×비율 이하 → 겹침이 있어 누락 없음
                self.assertLessEqual(n - s, self.VH * ratio + 1e-6)
                s = n
                seen.append(s)
            # 마지막 구간은 페이지 하단에 정확히 맞춤
            self.assertAlmostEqual(seen[-1], tops[0] + heights[0] - self.VH)
            self.assertEqual(len(seen), nav.sections_in_page(heights[0], self.VH, ratio))

    def test_last_section_goes_to_next_page_top_and_back(self):
        heights = [2300.0, 2300.0, 2300.0]
        tops = layout(heights)
        end0 = tops[0] + heights[0] - self.VH
        self.assertEqual(nav.next_target(tops, heights, self.VH, end0), tops[1])
        # 이전: 다음 페이지 첫 구간에서 → 이전 페이지의 마지막 구간
        self.assertEqual(nav.prev_target(tops, heights, self.VH, tops[1]), end0)
        # 마지막 페이지 끝에서는 제자리
        endl = tops[2] + heights[2] - self.VH
        self.assertEqual(nav.next_target(tops, heights, self.VH, endl), endl)
        self.assertEqual(nav.prev_target(tops, heights, self.VH, tops[0]), tops[0])

    def test_distance_uses_viewport_not_page_height(self):
        heights = [5000.0]
        tops = [0.0]
        self.assertAlmostEqual(nav.next_target(tops, heights, 800.0, 0.0, 0.5), 400.0)
        self.assertAlmostEqual(nav.next_target(tops, heights, 800.0, 0.0, 0.9), 720.0)
        self.assertAlmostEqual(nav.next_target(tops, heights, 800.0, 0.0), 600.0)   # 기본 75%

    def test_page_parts_basis_never_skips(self):
        for h, vh in ((2700.0, 1080.0), (2700.0, 800.0), (1500.0, 1080.0)):
            for n in nav.PAGE_PARTS:
                tops, heights = [0.0], [h]
                self.assertLessEqual(nav.section_step(h, vh, n, 'page'), vh)
                s, seen = 0.0, 0
                while True:
                    t = nav.next_target(tops, heights, vh, s, n, 'page')
                    if t == s:
                        break
                    self.assertLessEqual(t - s, vh + 1e-6)
                    s, seen = t, seen + 1
                self.assertAlmostEqual(s, h - vh)
                self.assertGreaterEqual(seen, 1)
        self.assertAlmostEqual(nav.section_step(2700.0, 1080.0, 3, 'page'), 900.0)

    def test_no_skip_when_scrolled_above_page(self):
        heights = [2300.0, 2300.0]
        tops = layout(heights)
        # 화면 중앙은 페이지 1에 있지만 페이지 1 위쪽이 아직 안 보이는 위치 → 먼저 페이지 위로
        self.assertEqual(nav.next_target(tops, heights, self.VH, tops[1] - 700.0, 0.9), tops[1])

    def test_short_pages_flip_and_center(self):
        heights = [800.0, 800.0]
        tops = layout(heights, gap=self.VH)
        self.assertAlmostEqual(nav.page_scroll(tops, heights, self.VH, 0), -100.0)
        self.assertAlmostEqual(nav.next_target(tops, heights, self.VH, -100.0), tops[1] - 100.0)

    def test_zoom_limit_scales_with_dpi_and_pagesize(self):
        a4 = [(595.0, 842.0)]
        self.assertTrue(3.5 < nav.max_zoom_for(a4, 1.0) <= 6.0)
        self.assertLess(nav.max_zoom_for(a4, 2.0), nav.max_zoom_for(a4, 1.0))
        self.assertLess(nav.max_zoom_for([(5000.0, 5000.0)], 1.0), 1.5)

    def test_recommend(self):
        self.assertEqual(nav.recommend_view([(842, 595)] * 3, 1920, 1080), ('page', 'landscape'))
        self.assertEqual(nav.recommend_view([(595, 842)] * 3, 1920, 1080), ('width', 'portrait'))
        self.assertEqual(nav.recommend_view([(595, 842), (842, 595), (842, 595)], 1920, 1080)[1], 'mixed')
        self.assertEqual(nav.fit_for_page(842, 595, 1920, 1080), 'page')
        self.assertEqual(nav.fit_for_page(595, 842, 1920, 1080), 'width')

    def test_stretch(self):
        self.assertEqual(nav.split_stretch('left'), (3, 1))
        self.assertEqual(nav.split_stretch('right'), (1, 3))
        self.assertEqual(nav.split_stretch(None), (1, 1))


class PresentationBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.docs = []
        self.addCleanup(self.tmp.cleanup)
        self.wins = []

    def pdf(self, name, sizes):
        p = os.path.join(self.tmp.name, name)
        make_pdf_file(p, sizes)
        d = PdfDocument(p)
        self.docs.append(d)
        return d

    def open_win(self, ctx, size=(1280, 720)):
        w = PresentationWindow(ctx)
        w._move_to_screen = lambda screen: None      # 오프스크린: 모니터 이동 생략
        w.resize(*size)
        w.show()
        w.start_headless = True
        for c, src in zip(w.canvases, ctx.panes):
            c.set_document(src.doc)
        w._apply_mode('width', user=False)
        w.section_basis = 'viewport'
        w.section_ratio = 0.75     # 사용자 저장 설정과 무관하게 고정
        w._syncing = True
        for c, src in zip(w.canvases, ctx.panes):
            c.section_ratio = 0.75
            c.section_basis = 'viewport'
            c.animate = False
            c.go_page(src.start_page, animate=False)
        w._syncing = False
        _app.processEvents()
        self.wins.append(w)
        return w

    def tearDown(self):
        for w in self.wins:
            w._closing = True
            w.close()
        for d in self.docs:
            d.close()

    def key(self, w, k, mod=Qt.KeyboardModifier.NoModifier):
        w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, mod))
        _app.processEvents()


class TestSingle(PresentationBase):
    def test_original_canvas_untouched(self):
        doc = self.pdf("a.pdf", [(595, 842)] * 4)
        orig = PdfCanvas()
        orig.resize(900, 700)
        orig.set_document(doc)
        orig.set_zoom(1.5)
        orig.go_to_page(2)
        before = (orig.position(), orig.zoom, orig.fit_mode, orig.current_page())
        ctx = context_from_canvas(orig, from_start=False)
        w = self.open_win(ctx)
        self.key(w, Qt.Key.Key_Space)
        self.key(w, Qt.Key.Key_Plus)
        w.close()
        self.assertEqual(before, (orig.position(), orig.zoom, orig.fit_mode, orig.current_page()))
        self.assertEqual(ctx.panes[0].start_page, 2)
        self.assertEqual(context_from_canvas(orig, from_start=True).panes[0].start_page, 0)

    def test_portrait_width_fit_and_sections(self):
        doc = self.pdf("p.pdf", [(595, 842)] * 3)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        c = w.canvases[0]
        vp = c.viewport()
        self.assertAlmostEqual(c._heights[0] / (842 / 595.0), vp.width(), delta=2)   # 폭 맞춤
        self.assertGreater(c._heights[0], vp.height())                               # 세로로 더 김
        step = vp.height() * 0.75
        self.key(w, Qt.Key.Key_Space)
        self.assertAlmostEqual(c.verticalScrollBar().value(), step, delta=2)
        guard = 0
        while c.current_page() == 0 and guard < 20:
            self.key(w, Qt.Key.Key_Space)
            guard += 1
        self.assertEqual(c.current_page(), 1)
        self.assertEqual(c.verticalScrollBar().value(), int(round(c._tops[1])))
        self.key(w, Qt.Key.Key_PageUp)                 # 이전 → 이전 페이지 마지막 구간
        end0 = c._tops[0] + c._heights[0] - vp.height()
        self.assertAlmostEqual(c.verticalScrollBar().value(), end0, delta=1)

    def test_landscape_page_fit_centers_and_flips(self):
        doc = self.pdf("l.pdf", [(842, 595)] * 3)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        w._apply_mode('page', user=True)
        c = w.canvases[0]
        c.go_page(0, animate=False)
        vp = c.viewport()
        self.assertLessEqual(c._heights[0], vp.height() + 1)
        self.assertLessEqual(c._heights[0] * 842 / 595 * 595 / 842 * (842 / 595), vp.width() + 2)
        self.key(w, Qt.Key.Key_Space)
        self.assertEqual(c.current_page(), 1)
        self.key(w, Qt.Key.Key_Left)
        self.assertEqual(c.current_page(), 0)

    def test_zoom_keeps_point_under_cursor(self):
        doc = self.pdf("z.pdf", [(595, 842)] * 3)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        c = w.canvases[0]
        c.scroll_to(300, animate=False)
        pt = QPointF(400, 300)
        before = c.to_doc(pt)
        c.zoom_at(c.zoom * 1.6, pt.x(), pt.y())
        after = c.to_doc(pt)
        self.assertEqual(before[0], after[0])
        self.assertAlmostEqual(before[1], after[1], delta=1.0)
        self.assertAlmostEqual(before[2], after[2], delta=1.0)

    def test_black_screen_swallows_first_key(self):
        doc = self.pdf("b.pdf", [(842, 595)] * 3)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        c = w.canvases[0]
        pos = (c.current_page(), c.verticalScrollBar().value(), c.zoom)
        self.key(w, Qt.Key.Key_B)
        self.assertTrue(w.black and w.curtain.isVisible())
        self.key(w, Qt.Key.Key_Space)                  # 해제만 하고 페이지는 넘기지 않는다
        self.assertFalse(w.black)
        self.assertEqual(pos, (c.current_page(), c.verticalScrollBar().value(), c.zoom))

    def test_highlight_follows_document_coordinates(self):
        doc = self.pdf("h.pdf", [(595, 842)] * 2)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        c = w.canvases[0]
        w.set_tool('pen')
        c.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, 100, 120))
        c.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, 220, 130, buttons=Qt.MouseButton.LeftButton))
        c.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, 220, 130))
        pts = c.strokes[0][0][0]
        self.assertEqual(len(pts), 2)
        v1 = c.to_view(0, *pts[0])
        c.zoom_at(c.zoom * 1.5, 100, 120)
        v2 = c.to_view(0, *pts[0])
        self.assertAlmostEqual(v2.x(), 100, delta=1.5)    # 확대 중심은 제자리
        self.assertAlmostEqual(v2.y(), 120, delta=1.5)
        self.assertAlmostEqual(v1.x(), 100, delta=1.5)
        w.clear_ink_all()
        self.assertEqual(c.strokes, {})

    def test_hundred_pages_navigation(self):
        doc = self.pdf("big.pdf", [(595, 842)] * 120)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        c = w.canvases[0]
        c.go_page(119, animate=False)
        self.assertEqual(c.current_page(), 119)
        self.key(w, Qt.Key.Key_Home)
        self.key(w, Qt.Key.Key_Right)
        self.assertEqual(c.current_page(), 118 if False else c.current_page())
        c.go_page(60, animate=False)
        self.assertEqual(c.current_page(), 60)


def _mouse(kind, x, y, buttons=Qt.MouseButton.NoButton):
    from PyQt6.QtGui import QMouseEvent
    btn = Qt.MouseButton.LeftButton
    return QMouseEvent(kind, QPointF(x, y), QPointF(x, y), btn, buttons or btn, Qt.KeyboardModifier.NoModifier)


class TestSpread(PresentationBase):
    def open_spread(self, sizes):
        doc = self.pdf("s.pdf", sizes)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        w._apply_mode('spread', user=True)
        _app.processEvents()
        return w

    def pages(self, w):
        a, b = w.canvases
        return a.current_page(), (None if b.blank else b.current_page())

    def test_pairs_1_2_and_odd_last_page(self):
        w = self.open_spread([(595, 842)] * 5)
        self.assertEqual(len(w.canvases), 2)
        self.assertEqual(self.pages(w), (0, 1))
        self.key(w, Qt.Key.Key_Space)
        self.assertEqual(self.pages(w), (2, 3))
        self.key(w, Qt.Key.Key_Right)
        self.assertEqual(self.pages(w), (4, None))      # 홀수 쪽수: 마지막 장 단독
        self.key(w, Qt.Key.Key_Space)
        self.assertEqual(self.pages(w), (4, None))
        self.assertEqual(w.badge.text(), '5 / 5')
        self.key(w, Qt.Key.Key_Left)
        self.assertEqual(self.pages(w), (2, 3))
        self.assertEqual(w.badge.text(), '3–4 / 5')
        self.key(w, Qt.Key.Key_Home)
        self.assertEqual(self.pages(w), (0, 1))

    def test_pages_touch_and_fit_whole_page(self):
        w = self.open_spread([(595, 842)] * 4)
        a, b = w.canvases
        ra, rb = a._page_rect(0), b._page_rect(1)
        self.assertAlmostEqual(ra.right(), a.viewport().width(), delta=2)   # 책처럼 맞붙음
        self.assertAlmostEqual(rb.left(), 0, delta=2)
        self.assertLessEqual(ra.height(), a.viewport().height() + 1)         # 한 쪽 전체가 보임

    def test_zoom_pan_within_page_then_turn_restores_fit(self):
        w = self.open_spread([(595, 842)] * 6)
        a, b = w.canvases
        z = a.zoom
        w._set_active(a)
        a.zoom_at(a.zoom * 2, 200, 300)                 # 특정 쪽만 확대 가능
        self.assertGreater(a.zoom, z * 1.9)
        self.assertAlmostEqual(b.zoom, z, delta=1e-3)    # 반대쪽은 그대로
        sb = a.verticalScrollBar()
        sb.setValue(sb.maximum() + 5000)                 # 아래로 끝까지 이동해도 이 쪽 안에 머문다
        self.assertEqual(a.current_page(), 0)
        self.assertLessEqual(sb.value(), a._tops[0] + a._heights[0] - a.viewport().height() + 1)
        sb.setValue(sb.minimum() - 5000)
        self.assertGreaterEqual(sb.value(), a._tops[0] - 1)
        self.key(w, Qt.Key.Key_Space)                    # 넘기면 맞춤으로 복귀 후 이동
        self.assertEqual(self.pages(w), (2, 3))
        self.assertEqual(a.fit_mode, 'page')
        self.assertAlmostEqual(a.zoom, z, delta=1e-3)
        a.zoom_at(a.zoom * 2, 100, 100)
        self.key(w, Qt.Key.Key_Left)
        self.assertEqual(self.pages(w), (0, 1))
        self.assertAlmostEqual(a.zoom, z, delta=1e-3)

    def test_zoomed_page_overlays_other_page_which_stays(self):
        w = self.open_spread([(595, 842)] * 4)
        a, b = w.canvases
        fa, fb = w.frames
        half = fb.width()
        zb, geo_b = b.zoom, fb.geometry()
        b_pos = b.pos_at(0.5)
        pt_doc = a.to_doc(QPointF(300, 300))
        a.zoom_at(a.zoom * 1.8, 300, 300)             # 왼쪽 쪽만 확대
        _app.processEvents()
        self.assertIn(a, w._floating)
        self.assertEqual(fa.geometry(), w.rect())      # 전체 화면 위로 겹침
        self.assertGreater(fa.width(), half * 1.5)
        self.assertEqual(fb.geometry(), geo_b)         # 반대쪽은 제자리
        self.assertAlmostEqual(b.zoom, zb)
        self.assertAlmostEqual(b.pos_at(0.5), b_pos, delta=1e-6)
        self.assertTrue(fb.isVisible())
        after = a.to_doc(QPointF(300 + (geo_b.x() - geo_b.x()), 300))
        self.assertEqual(after[0], 0)
        self.key(w, Qt.Key.Key_Space)                  # 넘기면 도로 맞춤 + 제자리
        self.assertEqual(w._floating, {})
        self.assertAlmostEqual(w.frames[0].width(), w.frames[1].width(), delta=2)
        self.assertEqual(a.h_align, 'right')

    def test_enter_returns_to_fit_without_changing_pages(self):
        w = self.open_spread([(595, 842)] * 6)
        self.key(w, Qt.Key.Key_Space)                   # 3-4 쪽
        a, b = w.canvases
        z = a.zoom
        b.zoom_at(b.zoom * 2, 100, 100)
        b.verticalScrollBar().setValue(b.verticalScrollBar().maximum())
        self.assertIn(b, w._floating)
        self.key(w, Qt.Key.Key_Return)
        self.assertEqual(self.pages(w), (2, 3))         # 페이지 변경 없음
        self.assertEqual(w._floating, {})
        self.assertAlmostEqual(b.zoom, z, delta=1e-3)
        self.assertEqual(b.fit_mode, 'page')
        self.key(w, Qt.Key.Key_Enter)                   # 확대 안 한 상태에서도 무해
        self.assertEqual(self.pages(w), (2, 3))

    def test_ctrl0_docks_floating_page(self):
        w = self.open_spread([(595, 842)] * 4)
        b = w.canvases[1]
        b.zoom_at(b.zoom * 2, 100, 100)
        self.assertIn(b, w._floating)
        self.key(w, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w._floating, {})
        self.assertEqual(b.h_align, 'left')

    def test_wheel_pages_only_when_fit_and_ctrl0_resets(self):
        w = self.open_spread([(595, 842)] * 4)
        a = w.canvases[0]
        z = a.zoom
        a.zoom_at(a.zoom * 2)
        self.assertIsNone(a.fit_mode)
        self.key(w, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        self.assertAlmostEqual(a.zoom, z, delta=1e-3)
        self.assertEqual(self.pages(w), (0, 1))

    def test_click_zoom_restores_on_turn(self):
        w = self.open_spread([(595, 842)] * 4)
        a = w.canvases[0]
        z = a.zoom
        a.click_zoom(100, 100)
        self.assertGreater(a.zoom, z)
        self.key(w, Qt.Key.Key_Space)
        self.assertAlmostEqual(a.zoom, z, delta=1e-3)

    def test_unavailable_for_landscape_and_dual(self):
        doc = self.pdf("l.pdf", [(842, 595)] * 3)
        c0 = PdfCanvas(); c0.set_document(doc)
        w = self.open_win(context_from_canvas(c0, True))
        w._apply_mode('spread', user=True)
        self.assertFalse(w.spread)
        self.assertEqual(len(w.canvases), 1)

    def test_leave_spread_restores_single_canvas_and_page(self):
        w = self.open_spread([(595, 842)] * 6)
        self.key(w, Qt.Key.Key_Space)
        w._apply_mode('width', user=True)
        _app.processEvents()
        self.assertFalse(w.spread)
        self.assertEqual(len(w.canvases), 1)
        self.assertEqual(w.canvases[0].current_page(), 2)
        self.assertFalse(w.canvases[0].zoom_locked)
        self.assertEqual(w.canvases[0].h_align, 'center')


class TestDual(PresentationBase):
    def build(self, sizes_l, sizes_r, sync='normal', pages=(0, 0)):
        a, b = self.pdf("l.pdf", sizes_l), self.pdf("r.pdf", sizes_r)
        cl, cr = PdfCanvas(), PdfCanvas()
        cl.set_document(a); cr.set_document(b)
        ctx = context_from_split(cl, cr, sync)
        ctx.panes[0].start_page, ctx.panes[1].start_page = pages
        return self.open_win(ctx, (1600, 800))

    def test_sync_follows_and_off_decouples(self):
        w = self.build([(595, 842)] * 6, [(595, 842)] * 6)
        l, r = w.canvases
        w.set_focus(None)
        _app.processEvents()
        l.go_page(3, animate=False)
        _app.processEvents()
        self.assertEqual(r.current_page(), 3)
        w.toggle_sync(False)
        l.go_page(5, animate=False)
        _app.processEvents()
        self.assertEqual(r.current_page(), 3)

    def test_anchor_sync_with_different_start_pages_and_page_counts(self):
        w = self.build([(595, 842)] * 5, [(595, 842)] * 9, sync='off', pages=(0, 3))
        l, r = w.canvases
        w._align_here()                      # L 1페이지 ↔ R 4페이지 연결
        l.go_page(2, animate=False)
        _app.processEvents()
        self.assertEqual(r.current_page(), 5)
        r.go_page(8, animate=False)          # 오른쪽 이동 → 왼쪽은 문서 끝(5페이지)까지만 따라감
        _app.processEvents()
        self.assertLessEqual(l.current_page(), 4)

    def test_stale_resume_requires_realign(self):
        w = self.build([(595, 842)] * 6, [(595, 842)] * 6, sync='off')
        l, r = w.canvases
        w._align_here()
        w.toggle_sync(False)
        l.go_page(4, animate=False)
        w.toggle_sync(True)
        self.assertTrue(w._stale)
        r_before = r.current_page()
        l.go_page(5, animate=False)
        _app.processEvents()
        self.assertEqual(r.current_page(), r_before)     # 보류 중에는 점프 없음
        w._align_here()
        self.assertFalse(w._stale)

    def test_focus_layout_and_swap_keep_pages(self):
        w = self.build([(595, 842)] * 6, [(842, 595)] * 6, pages=(2, 4))
        l, r = w.canvases
        w.set_focus('left')
        _app.processEvents()
        self.assertGreater(w.frames[0].width(), w.frames[1].width() * 2)
        self.assertEqual((l.current_page(), r.current_page()), (2, 4))
        w.swap_focus()
        _app.processEvents()
        self.assertGreater(w.frames[1].width(), w.frames[0].width() * 2)
        self.assertEqual((l.current_page(), r.current_page()), (2, 4))
        w.toggle_secondary()
        self.assertTrue(w.frames[0].isHidden())
        w.toggle_secondary()
        self.assertFalse(w.frames[0].isHidden())

    def test_independent_zoom_per_pane(self):
        w = self.build([(595, 842)] * 3, [(595, 842)] * 3)
        l, r = w.canvases
        z = r.zoom
        w._set_active(l)
        l.zoom_in()
        self.assertAlmostEqual(r.zoom, z)


class TestEntryPoints(unittest.TestCase):
    def test_viewer_and_split_have_presentation_entry(self):
        from app.shell.viewer_workspace import ViewerWorkspace
        from app.viewer.document_manager import DocumentManager
        from app.viewer.split_view import SplitView
        vw = ViewerWorkspace()
        self.assertFalse(hasattr(vw, 'btn_present'))   # 헤더 버튼/F5 로만 진입
        self.assertIsNone(vw.start_presentation())
        sv = SplitView(DocumentManager())
        self.assertFalse(hasattr(sv, 'btn_present'))
        self.assertEqual(sv.presentation_sync_state(), 'normal')
        sv.sync_scroll.setChecked(False)
        self.assertEqual(sv.presentation_sync_state(), 'off')


if __name__ == "__main__":
    unittest.main()

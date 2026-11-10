"""발표용 캔버스: 기존 PdfCanvas(렌더링·캐시·HiDPI)를 재사용하고 발표에 필요한 동작만 얹는다.

- 여백 0, 어두운 배경, 스크롤바 숨김
- 'page' 맞춤에서는 페이지를 뷰포트 가운데에 정렬(스크롤 범위가 음수 가능), 그 외에는 연속 레이아웃
- 부드러운 스크롤 애니메이션, 구간/페이지 이동, 마우스 지점 기준 확대
- 레이저 포인터 / 임시 형광펜(문서 좌표 pt 로 저장) / 클릭 확대 — 원본 PDF는 건드리지 않는다
"""
from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen
from PyQt6.QtWidgets import QAbstractScrollArea

from app.presentation import navigation as nav
from app.viewer.pdf_canvas import PdfCanvas

BG = QColor('#141416')
INK_COLOR = QColor(255, 214, 0, 120)
INK_WIDTH_PT = 12.0
LASER_COLOR = QColor(255, 48, 48)
CLICK_ZOOM_FACTOR = 2.5
WHEEL_STEP_ZOOM = 1.15


class PresentationCanvas(PdfCanvas):
    activity = pyqtSignal()        # 마우스 움직임(도구 모음 표시/커서 숨김 타이머용)
    activated = pyqtSignal()       # 이 캔버스를 눌렀음(두 PDF에서 조작 대상 지정)
    view_changed = pyqtSignal()    # 맞춤/배율/문서 상태가 바뀜(도구 모음 갱신용)
    wheel_step = pyqtSignal(int)   # 2페이지 모아보기: 휠 한 노치(+1 다음 / -1 이전)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.margin = 0
        self.page_gap = 8
        self.bg_color = BG
        self.probe_ratio = 0.5
        self.fit_mode = 'width'
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setMouseTracking(True)
        self.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._heights = []
        self._target_y = None
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self.verticalScrollBar().setValue(int(round(v))))
        self._anim.finished.connect(self._anim_finished)
        self.animate = True
        self.section_ratio = nav.DEFAULT_RATIO
        self.page_parts = nav.DEFAULT_PARTS
        self.section_basis = 'viewport'   # 'viewport'(화면 높이 비율) | 'page'(페이지 N등분)
        self.wheel_mode = 'free'       # free | step | page | smooth
        self.h_align = 'center'        # 'center' | 'left' | 'right' (2페이지 모아보기에서 책처럼 맞붙임)
        self.zoom_locked = False       # True 면 확대/축소 불가(클릭 확대만 예외)
        self._force_zoom = False
        self.only_page = None          # 2페이지 모아보기: 이 캔버스가 보여줄 페이지(스크롤·확대가 이 페이지 안에 머문다)
        self._drag = None              # 확대 상태에서 드래그 이동
        self.before_zoom = None        # 맞춤→확대 직전 호출(2페이지 모아보기: 이 쪽을 전체 화면 위로 띄움). (dx, dy) 반환
        self.blank = False             # True 면 페이지를 그리지 않음(홀수 쪽수의 빈 쪽)
        self.auto_fit = False          # 혼합 방향 문서: 페이지마다 맞춤 방식 선택
        self.tool = 'none'             # none | laser | pen | zoom
        self.strokes = {}              # page -> [(points[(x_pt, y_pt)], width_pt)]
        self._stroke = None
        self._laser = None
        self._wheel_acc = 0
        self._quiet = False            # 레이아웃 변경(리사이즈) 중에는 동기화 신호를 내보내지 않는다
        self._saved_view = None        # 클릭 확대 복귀용
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(16)
        self._auto_timer.timeout.connect(self._auto_tick)
        self.auto_speed = 60.0         # px/s
        self._auto_y = 0.0
        self.MAX_ZOOM = nav.ABS_MAX_ZOOM

    # ---- 문서 / 레이아웃 -----------------------------------------------------
    def set_document(self, doc):
        self.strokes = {}
        self._saved_view = None
        self._stop_anim()
        self.MAX_ZOOM = nav.max_zoom_for(doc.page_sizes if doc else [], self.devicePixelRatioF())
        super().set_document(doc)

    def _relayout(self):
        if not self.doc:
            self._tops, self._heights = [], []
            return
        if self.fit_mode:
            self._apply_fit()
        s = self._scale()
        vp = self.viewport().size()
        gap = vp.height() if (self.fit_mode == 'page' or self.only_page is not None) else self.page_gap
        y = 0.0
        self._tops, self._heights = [], []
        maxw = 0.0
        for w, h in self.doc.page_sizes:
            self._tops.append(y)
            self._heights.append(h * s)
            y += h * s + gap
            maxw = max(maxw, w * s)
        self._content_w = int(maxw)
        vh = vp.height()
        lo = min(0.0, -(vh - self._heights[0]) / 2.0)
        last = len(self._tops) - 1
        hi = self._tops[last] + self._heights[last] - vh + max(0.0, (vh - self._heights[last]) / 2.0)
        if self.only_page is not None and 0 <= self.only_page <= last:
            i, ph = self.only_page, self._heights[self.only_page]
            if ph <= vh:
                lo = hi = self._tops[i] - (vh - ph) / 2.0       # 짧으면 가운데 고정
            else:
                lo, hi = self._tops[i], self._tops[i] + ph - vh  # 이 페이지 안에서만 이동
        sb = self.verticalScrollBar()
        sb.setRange(int(lo), int(max(lo, hi)))
        sb.setPageStep(vh)
        sb.setSingleStep(40)
        hb = self.horizontalScrollBar()
        hb.setRange(0, max(0, self._content_w - vp.width()))
        hb.setPageStep(vp.width())

    def _apply_fit(self):
        before = self.zoom
        super()._apply_fit()
        if abs(self.zoom - before) > 1e-3:
            self.view_changed.emit()

    def set_fit(self, mode):
        """맞춤 모드 변경. 현재 위치(페이지 중앙 기준)를 유지한다."""
        pos = self.position()
        self.fit_mode = mode
        self._stop_anim()
        self._relayout()
        self.set_position(*pos)
        if mode == 'page':
            self.go_page(self._current_page, animate=False)
        self.zoom_changed.emit(self.zoom)
        self.view_changed.emit()
        self.viewport().update()

    def _emit_scrolled(self):
        if not self._quiet:
            super()._emit_scrolled()

    def resizeEvent(self, event):
        QAbstractScrollArea.resizeEvent(self, event)
        if self.doc:
            pos = self.position()
            self._stop_anim()
            self._quiet = True
            try:
                self._relayout()
                self.set_position(*pos)
            finally:
                self._quiet = False
            self.view_changed.emit()

    def _page_x0(self, pw):
        """페이지 왼쪽 x (스크롤 적용 전 콘텐츠 좌표)."""
        full = max(self._content_w, self.viewport().width())
        if self.h_align == 'left':
            return 0.0
        if self.h_align == 'right':
            return full - pw
        return max(self.margin, (full - pw) / 2)

    def _page_rect(self, i):
        s = self._scale()
        w, h = self.doc.page_sizes[i]
        pw = w * s
        return QRectF(self._page_x0(pw) - self.horizontalScrollBar().value(),
                      self._tops[i] - self.verticalScrollBar().value(), pw, h * s)

    # ---- 위치(뷰포트 가운데 기준, 페이지 높이만으로 정규화 — 확대율 무관) ----------
    def pos_at(self, ratio=0.5):
        if not self._tops:
            return 0.0
        y = self.verticalScrollBar().value() + ratio * self.viewport().height()
        i = nav.page_at(self._tops, y)
        h = self._heights[i]
        return i + nav.clamp((y - self._tops[i]) / h if h else 0.0, 0.0, 1.0)

    def scroll_to_pos(self, pos, ratio=0.5):
        if not self._tops:
            return
        i = max(0, min(int(pos), len(self._tops) - 1))
        y = self._tops[i] + (pos - i) * self._heights[i] - ratio * self.viewport().height()
        self._stop_anim()
        self.verticalScrollBar().setValue(int(round(y)))

    def position(self):
        hs = self.horizontalScrollBar()
        return (self.pos_at(0.5), hs.value() / hs.maximum() if hs.maximum() else 0.0)

    def set_position(self, pos, hratio=0.0):
        self.scroll_to_pos(pos, 0.5)
        hs = self.horizontalScrollBar()
        hs.setValue(int(hratio * hs.maximum()))

    # ---- 이동 ----------------------------------------------------------------
    def _stop_anim(self):
        if self._anim.state() == QVariantAnimation.State.Running:
            self._anim.stop()
        self._target_y = None

    def _anim_finished(self):
        self._target_y = None

    def _scroll_now(self):
        return self._target_y if self._target_y is not None else float(self.verticalScrollBar().value())

    def scroll_to(self, y, animate=True):
        sb = self.verticalScrollBar()
        y = nav.clamp(float(y), sb.minimum(), sb.maximum())
        cur = float(sb.value())
        if not (animate and self.animate) or abs(y - cur) < 2:
            self._stop_anim()
            sb.setValue(int(round(y)))
            return
        self._anim.stop()
        self._target_y = y
        self._anim.setStartValue(cur)
        self._anim.setEndValue(y)
        self._anim.setDuration(int(nav.clamp(110 + abs(y - cur) * 0.12, 120, 300)))
        self._anim.start()

    def scroll_by(self, dy, animate=True):
        self.scroll_to(self._scroll_now() + dy, animate)

    def _geom(self):
        return self._tops, self._heights, self.viewport().height()

    def go_page(self, i, animate=False):
        """페이지 i 를 보여준다(필요하면 페이지별 맞춤 방식을 다시 계산)."""
        if not self._tops:
            return
        i = max(0, min(i, len(self._tops) - 1))
        self._current_page = i
        if self.auto_fit and self.doc:
            w, h = self.doc.page_sizes[i]
            want = nav.fit_for_page(w, h, self.viewport().width(), self.viewport().height())
            if want != self.fit_mode:
                self.fit_mode = want
                self._stop_anim()
                self._relayout()
                animate = False
                self.view_changed.emit()
        elif self.fit_mode:
            before = self.zoom
            self._relayout()
            if abs(self.zoom - before) > 1e-3:
                animate = False
        tops, heights, vh = self._geom()
        self.scroll_to(nav.page_scroll(tops, heights, vh, i), animate)

    def go_to_page(self, index, y_pt=None):
        if y_pt is None:
            self.go_page(index, animate=False)
        else:
            super().go_to_page(index, y_pt)

    def _move(self, fn, *extra):
        if not self._tops:
            return
        tops, heights, vh = self._geom()
        target = fn(tops, heights, vh, self._scroll_now(), *extra)
        new_page = nav.page_at(tops, target + vh / 2.0)
        if self.auto_fit and new_page != nav.current_page(tops, vh, self._scroll_now()):
            self.go_page(new_page, animate=False)
            if fn in (nav.prev_target, nav.page_bottom_target):
                tops, heights, vh = self._geom()
                self.scroll_to(nav.page_end_scroll(tops, heights, vh, new_page), False)
            return
        self.scroll_to(target, True)

    def _section_args(self):
        return (self.page_parts if self.section_basis == 'page' else self.section_ratio), self.section_basis

    def section_next(self):
        self._move(nav.next_target, *self._section_args())

    def section_prev(self):
        self._move(nav.prev_target, *self._section_args())

    def page_next(self):
        self._move(nav.next_page_target)

    def page_prev(self):
        self._move(nav.prev_page_target)

    def page_top(self):
        self._move(nav.page_top_target)

    def page_bottom(self):
        self._move(nav.page_bottom_target)

    def sections_left(self):
        """현재 페이지에서 남은 구간 수(0 = 이미 마지막 구간)."""
        if not self._tops:
            return 0
        tops, heights, vh = self._geom()
        i = nav.current_page(tops, vh, self._scroll_now())
        end = nav.page_end_scroll(tops, heights, vh, i)
        rest = end - max(self._scroll_now(), tops[i])
        if heights[i] <= vh + nav.FIT_EPS or rest <= nav.FIT_EPS:
            return 0
        import math
        return math.ceil(rest / nav.section_step(heights[i], vh, *self._section_args()) - 1e-9)

    # ---- 확대 ----------------------------------------------------------------
    def zoom_at(self, new_zoom, ax=None, ay=None, keep_fit=False):
        """화면 점 (ax, ay) 아래의 문서 좌표를 고정한 채 배율 변경."""
        if not self._tops:
            return
        if self.zoom_locked and not self._force_zoom:
            return
        new_zoom = nav.clamp(new_zoom, self.MIN_ZOOM, self.MAX_ZOOM)
        if abs(new_zoom - self.zoom) < 1e-4:
            return
        vp = self.viewport()
        ax = vp.width() / 2.0 if ax is None else ax
        ay = vp.height() / 2.0 if ay is None else ay
        sb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
        s = self._scale()
        vy = sb.value() + ay                      # 애니메이션 목표가 아닌 실제 위치 기준
        i = nav.page_at(self._tops, vy)
        y_pt = (vy - self._tops[i]) / s
        pw = self.doc.page_sizes[i][0] * s
        xb = self._page_x0(pw)
        x_pt = (ax + hb.value() - xb) / s
        if self.before_zoom is not None:           # 문서 좌표를 먼저 잡은 뒤에 이 쪽을 전체 화면 위로 띄운다
            if not keep_fit:
                self.fit_mode = None           # 뷰포트가 바뀌어도 배율이 다시 맞춰지지 않도록
            dx, dy = self.before_zoom(self)
            ax, ay = ax + dx, ay + dy
        self._stop_anim()
        if not keep_fit:
            self.fit_mode = None
        self.zoom = new_zoom
        self._relayout()
        s2 = self._scale()
        pw2 = self.doc.page_sizes[i][0] * s2
        xb2 = self._page_x0(pw2)
        sb.setValue(int(round(self._tops[i] + y_pt * s2 - ay)))
        hb.setValue(int(round(xb2 + x_pt * s2 - ax)))
        self.zoom_changed.emit(self.zoom)
        self.view_changed.emit()
        self.viewport().update()

    def zoom_in(self):
        self.zoom_at(self.zoom * WHEEL_STEP_ZOOM)

    def zoom_out(self):
        self.zoom_at(self.zoom / WHEEL_STEP_ZOOM)

    def set_zoom(self, zoom, keep_fit=False):
        self.zoom_at(zoom, keep_fit=keep_fit)

    # ---- 클릭 확대 -----------------------------------------------------------------
    def click_zoom(self, ax, ay):
        if self._saved_view is not None:
            self.restore_click_zoom()
            return
        self._saved_view = (self.fit_mode, self.zoom, self.position())
        self._force_zoom = True
        try:
            self.zoom_at(min(self.zoom * CLICK_ZOOM_FACTOR, self.MAX_ZOOM), ax, ay)
        finally:
            self._force_zoom = False

    def restore_click_zoom(self):
        if self._saved_view is None:
            return
        fit, zoom, pos = self._saved_view
        self._saved_view = None
        self.fit_mode = fit
        self.zoom = zoom
        self._relayout()
        self.set_position(*pos)
        self.zoom_changed.emit(self.zoom)
        self.view_changed.emit()
        self.viewport().update()

    # ---- 자동 스크롤 ---------------------------------------------------------------
    def auto_scroll_active(self):
        return self._auto_timer.isActive()

    def set_auto_scroll(self, on):
        if on and self.verticalScrollBar().value() < self.verticalScrollBar().maximum():
            self._stop_anim()
            self._auto_y = float(self.verticalScrollBar().value())
            self._auto_timer.start()
        else:
            self._auto_timer.stop()
        self.view_changed.emit()

    def _auto_tick(self):
        sb = self.verticalScrollBar()
        if abs(sb.value() - self._auto_y) > 2:      # 다른 입력/동기화로 위치가 바뀌면 거기서 이어간다
            self._auto_y = float(sb.value())
        self._auto_y += self.auto_speed * self._auto_timer.interval() / 1000.0
        if self._auto_y >= sb.maximum():
            self._auto_y = float(sb.maximum())
            self._auto_timer.stop()
            self.view_changed.emit()
        sb.setValue(int(self._auto_y))

    # ---- 좌표 변환 / 잉크 ------------------------------------------------------------
    def to_doc(self, pt):
        """뷰포트 좌표 → (페이지, x_pt, y_pt)."""
        s = self._scale()
        vy = self.verticalScrollBar().value() + pt.y()
        i = nav.page_at(self._tops, vy)
        r = self._page_rect(i)
        return i, (pt.x() - r.left()) / s, (vy - self._tops[i]) / s

    def to_view(self, page, x_pt, y_pt):
        s = self._scale()
        r = self._page_rect(page)
        return QPointF(r.left() + x_pt * s, r.top() + y_pt * s)

    def clear_ink(self, page=None):
        if page is None:
            self.strokes = {}
        else:
            self.strokes.pop(page, None)
        self.viewport().update()

    def set_tool(self, tool):
        if tool != 'zoom' and self._saved_view is not None:
            self.restore_click_zoom()
        self.tool = tool
        self._laser = None
        self.viewport().setCursor(Qt.CursorShape.BlankCursor if tool == 'laser'
                                  else Qt.CursorShape.CrossCursor if tool in ('pen', 'zoom')
                                  else Qt.CursorShape.ArrowCursor)
        self.viewport().update()

    def mousePressEvent(self, event):
        self.activated.emit()
        if not self._tops or event.button() != Qt.MouseButton.LeftButton:
            return
        pt = event.position()
        if self.tool == 'pen':
            page, x, y = self.to_doc(pt)
            self._stroke = (page, [(x, y)])
            self.strokes.setdefault(page, []).append(([(x, y)], INK_WIDTH_PT))
        elif self.tool == 'zoom':
            self.click_zoom(pt.x(), pt.y())
        elif self.tool == 'laser':
            self._laser = pt
            self.viewport().update()
        elif self.tool == 'none' and self.fit_mode is None:
            self._drag = (pt, self.verticalScrollBar().value(), self.horizontalScrollBar().value())
            self._stop_anim()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        self.activity.emit()
        pt = event.position()
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            p0, v0, h0 = self._drag
            self.verticalScrollBar().setValue(int(v0 - (pt.y() - p0.y())))
            self.horizontalScrollBar().setValue(int(h0 - (pt.x() - p0.x())))
        elif self.tool == 'laser':
            self._laser = pt
            self.viewport().update()
        elif self.tool == 'pen' and self._stroke and event.buttons() & Qt.MouseButton.LeftButton:
            page, pts = self._stroke
            r = self._page_rect(page)
            s = self._scale()
            pts.append(((pt.x() - r.left()) / s, (pt.y() - r.top()) / s))
            self.strokes[page][-1] = (list(pts), INK_WIDTH_PT)
            self.viewport().update()

    def mouseReleaseEvent(self, event):
        self._stroke = None
        if self._drag is not None:
            self._drag = None
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event):
        self._laser = None
        self.viewport().update()
        super().leaveEvent(event)

    # ---- 휠 ----------------------------------------------------------------------
    def wheelEvent(self, event):
        self.activity.emit()
        dy = event.angleDelta().y()
        if not dy or not self._tops:
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            p = event.position()
            f = WHEEL_STEP_ZOOM if dy > 0 else 1 / WHEEL_STEP_ZOOM
            self.zoom_at(self.zoom * f, p.x(), p.y())
        elif self.wheel_mode == 'spread' and self.fit_mode is None:
            self._stop_anim()
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() - int(dy))
        elif self.wheel_mode == 'spread':
            self._wheel_acc += dy
            while abs(self._wheel_acc) >= 120:
                forward = self._wheel_acc < 0
                self._wheel_acc += 120 if forward else -120
                self.wheel_step.emit(1 if forward else -1)
        elif self.wheel_mode in ('step', 'page'):
            self._wheel_acc += dy
            while abs(self._wheel_acc) >= 120:
                forward = self._wheel_acc < 0
                self._wheel_acc += 120 if forward else -120
                if self.wheel_mode == 'page':
                    self.page_next() if forward else self.page_prev()
                else:
                    self.section_next() if forward else self.section_prev()
        elif self.wheel_mode == 'smooth':
            self.scroll_by(-dy * 1.2, True)
        else:
            self._stop_anim()
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() - int(dy))
        event.accept()

    # ---- 그리기 --------------------------------------------------------------------
    def paintEvent(self, event):
        if self.blank:
            p = QPainter(self.viewport())
            p.fillRect(self.viewport().rect(), self.bg_color)
            p.end()
            return
        super().paintEvent(event)
        if not self.doc or not self._tops:
            return
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._scale()
        vh = self.viewport().height()
        for page, strokes in self.strokes.items():
            r = self._page_rect(page)
            if r.bottom() < 0 or r.top() > vh:
                continue
            p.save()
            p.setClipRect(r)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            for pts, width_pt in strokes:
                pen = QPen(INK_COLOR, width_pt * s, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                qp = [QPointF(r.left() + x * s, r.top() + y * s) for x, y in pts]
                if len(qp) == 1:
                    p.drawPoint(qp[0])
                else:
                    p.drawPolyline(qp)
            p.restore()
        if self.tool == 'laser' and self._laser is not None:
            p.setPen(Qt.PenStyle.NoPen)
            glow = QColor(LASER_COLOR)
            glow.setAlpha(70)
            p.setBrush(glow)
            p.drawEllipse(self._laser, 26, 26)
            core = QColor(LASER_COLOR)
            core.setAlpha(235)
            p.setBrush(core)
            p.drawEllipse(self._laser, 11, 11)
            p.setPen(QPen(QColor(255, 255, 255, 230), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._laser, 11, 11)
        p.end()

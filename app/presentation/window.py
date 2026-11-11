"""PresentationWindow: 전체화면 발표 창 (PDF 보기 1개 / 두 PDF 동시보기 2개 공용).

원래 작업 화면의 캔버스는 건드리지 않고 자체 PresentationCanvas 를 사용하므로
종료 후 열린 파일·페이지·스크롤·확대율·동기화 설정이 그대로 유지된다.
추후 발표자 화면은 이 창(관객용)과 분리된 PresenterWindow 가 같은 navigation/context 를 공유하도록 확장한다.
"""
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QActionGroup, QCursor, QGuiApplication
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QMenu, QWidget

from app.presentation import navigation as nav
from app.presentation.canvas import PresentationCanvas
from app.presentation.context import PresentationContext
from app.presentation.overlay import Curtain, FloatingToolbar, PageBadge, Toast
from app.services import app_settings
from app.viewer import scroll_anchor as sa

VIEW_MODES = (('page', '전체 페이지'), ('width', '화면 너비 맞춤'),
              ('section', '구간별 넘기기'), ('smooth', '부드러운 스크롤'),
              ('spread', '2페이지 모아보기'))
SYNC_TOLERANCE_PT = 3.0
IDLE_HIDE_MS = 2500
SYNC_RATIO = 0.5


class _PaneFrame(QFrame):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        lay.addWidget(canvas)
        self.set_active(False, False)

    def set_active(self, active, show_border):
        color = '#A44735' if (active and show_border) else 'transparent'
        self.setStyleSheet(f'QFrame {{ background: #141416; border: 2px solid {color}; }}')


class PresentationWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, context: PresentationContext, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('발표모드')
        self.setStyleSheet('PresentationWindow { background: #141416; }')
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.ctx = context
        self._screen = context.screen
        self._syncing = False
        self._anchors = None
        self._stale = False
        self.sync = context.sync            # off | normal | anchor
        self.focus_side = None              # None | 'left' | 'right'
        self.secondary_hidden = False
        self.black = False
        self.view_mode = 'width'
        self.user_chose_mode = context.view_mode is not None
        self._closing = False
        self.spread = False              # 2페이지 모아보기(세로형 문서의 PDF 보기 전용)
        self.spread_left = 0             # 왼쪽 쪽 인덱스(항상 짝수: 1-2, 3-4 ...)
        self._floating = {}              # 확대되어 전체 화면 위로 떠 있는 캔버스 -> 레이아웃 자리표시 위젯
        sizes0 = context.panes[0].doc.page_sizes
        self.portrait_doc = bool(sizes0) and all(wd < ht for wd, ht in sizes0)

        ratio = nav.clamp(int(app_settings.get('presentation/ratio_pct')) / 100.0, 0.3, 0.95)
        self.section_ratio = ratio
        self.section_basis = 'page' if app_settings.get('presentation/basis') == 'page' else 'viewport'
        self.page_parts = int(nav.clamp(int(app_settings.get('presentation/page_parts')), 2, 4))
        self.animate = bool(app_settings.get('presentation/animate'))
        self.auto_speed = float(app_settings.get('presentation/auto_speed'))

        self.canvases, self.frames = [], []
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4 if context.dual else 0)
        for src in context.panes:
            c = PresentationCanvas()
            c.section_ratio, c.animate, c.auto_speed = self.section_ratio, self.animate, self.auto_speed
            c.section_basis, c.page_parts = self.section_basis, self.page_parts
            f = _PaneFrame(c)
            root.addWidget(f, 1)
            self.canvases.append(c)
            self.frames.append(f)
        self.root = root
        self.active = self.canvases[0]

        self.toolbar = FloatingToolbar(self)
        self.toast = Toast(self)
        self.badge = PageBadge(self)
        self.curtain = Curtain(self, self._release_black)
        self._build_toolbar()

        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(IDLE_HIDE_MS)
        self._idle.timeout.connect(self._on_idle)

        for i, c in enumerate(self.canvases):
            c.activity.connect(self._on_activity)
            c.activated.connect(lambda c=c: self._set_active(c))
            c.page_changed.connect(lambda *_: self._update_badge())
            c.view_changed.connect(self._update_toolbar_state)
            c.wheel_step.connect(lambda d: self.spread_next() if d > 0 else self.spread_prev())
            c.scrolled.connect(lambda pos, hr, c=c: self._on_scrolled(c, pos, hr))
        QGuiApplication.instance().screenRemoved.connect(self._on_screen_removed)

    def _wire(self, c):
        c.activity.connect(self._on_activity)
        c.activated.connect(lambda c=c: self._set_active(c))
        c.page_changed.connect(lambda *_: self._update_badge())
        c.view_changed.connect(self._update_toolbar_state)
        c.wheel_step.connect(lambda d: self.spread_next() if d > 0 else self.spread_prev())
        c.activity.connect(lambda c=c: self._hover(c))

    def _hover(self, c):
        """2페이지 모아보기: 마우스가 올라간 쪽이 확대/이동 대상."""
        if self.spread and c is not self.active:
            self._set_active(c)

    # ---- 시작 ------------------------------------------------------------------
    def start(self):
        screen = self._screen or (self.parentWidget().screen() if self.parentWidget() else None) \
            or QGuiApplication.primaryScreen()
        self._move_to_screen(screen)
        self.show()
        self.activateWindow()
        self.setFocus()
        for c, src in zip(self.canvases, self.ctx.panes):
            c.set_document(src.doc)
        sizes = [s.doc.page_sizes for s in self.ctx.panes]
        mode, orient = nav.recommend_view(sizes[0], self.width(), self.height())
        if self.ctx.view_mode:
            mode, orient = self.ctx.view_mode, ''
        self._apply_mode(mode, user=False)
        if orient == 'mixed' and not self.user_chose_mode:
            for c in self.canvases:
                c.auto_fit = True
        self._syncing = True           # 좌우 시작 페이지가 달라도 초기 배치에서는 서로 끌지 않는다
        try:
            for c, src in zip(self.canvases, self.ctx.panes):
                c.go_page(src.start_page, animate=False)
        finally:
            self._syncing = False
        if self.ctx.dual and self.sync == 'anchor':
            self._align_here(quiet=True)   # 동시보기의 기준점 관계를 현재 화면 기준으로 이어받는다
        self._layout_all()
        label = dict(VIEW_MODES).get(mode, mode)
        hint = {'portrait': '세로형 문서', 'landscape': '가로형 문서', 'mixed': '혼합 방향 문서'}.get(orient, '')
        self._toast(f'추천 보기: {label}' + (f' ({hint})' if hint else '') + ' · 마우스를 아래로 내리면 도구 모음')
        self._idle.start()
        QTimer.singleShot(0, self._layout_all)

    # ---- 모니터 / 전체화면 ---------------------------------------------------------------
    def screens(self):
        return QGuiApplication.screens()

    def _move_to_screen(self, screen):
        self._screen = screen
        old = getattr(self, '_geo_screen', None)
        if old is not None:
            try:
                old.geometryChanged.disconnect(self._on_screen_geometry)
            except (TypeError, RuntimeError):
                pass
        if self.isVisible():
            self.showNormal()
        h = self.windowHandle()
        if h is not None:
            h.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self._geo_screen = screen
        screen.geometryChanged.connect(self._on_screen_geometry)

    def move_to_screen(self, screen):
        self._move_to_screen(screen)
        self._toast(f'발표 화면: {screen.name()}')
        self._after_screen_change()

    def _on_screen_geometry(self, *_):
        if self._screen is not None and not self._closing:
            self.setGeometry(self._screen.geometry())
            self._after_screen_change()

    def _on_screen_removed(self, screen):
        """프로젝터 분리 등으로 대상 모니터가 사라지면 기본 모니터로 옮긴다(비정상 종료 방지)."""
        if self._closing or screen is not self._screen:
            return
        primary = QGuiApplication.primaryScreen()
        if primary is not None:
            self._screen = None
            self._move_to_screen(primary)
            self._toast('발표 모니터가 분리되어 기본 모니터로 이동했습니다', 3500)
            self._after_screen_change()

    def _after_screen_change(self):
        for c in self.canvases:
            if c.doc:
                c.MAX_ZOOM = nav.max_zoom_for(c.doc.page_sizes, c.devicePixelRatioF())
                if c.zoom > c.MAX_ZOOM:
                    c.zoom_at(c.MAX_ZOOM, keep_fit=bool(c.fit_mode))
                c._relayout()
                c.viewport().update()
        self._layout_all()

    # ---- 툴바 ---------------------------------------------------------------------
    def _build_toolbar(self):
        tb = self.toolbar
        tb.add_button('prev', '◀', '이전 구간·페이지 (Shift+Space / PageUp)').clicked.connect(self.step_prev)
        self.lbl_page = tb.add_label('page', '')
        tb.add_button('next', '▶', '다음 구간·페이지 (Space / PageDown)').clicked.connect(self.step_next)
        tb.add_separator()
        tb.add_button('zout', '－', '축소 (-)').clicked.connect(lambda: self.active.zoom_out())
        self.btn_zoom = tb.add_button('zoom', '100%', '배율 선택', menu=self._zoom_menu())
        tb.add_button('zin', '＋', '확대 (+)').clicked.connect(lambda: self.active.zoom_in())
        tb.add_separator()
        self.btn_view = tb.add_button('view', '보기', '보기 방식', menu=self._view_menu())
        self.btn_ratio = tb.add_button('ratio', '화면 75%', '구간 이동 기준과 크기 (화면 높이 비율 / 페이지 N등분)', menu=self._ratio_menu())
        if self.ctx.dual:
            tb.add_separator()
            self.btn_layout = tb.add_button('layout', '구성', '좌우 동일 / 한쪽 집중', menu=self._layout_menu())
            self.btn_sync = tb.add_button('sync', '동기화', '스크롤 동기화 켜기/끄기', checkable=True)
            self.btn_sync.clicked.connect(self.toggle_sync)
            tb.add_button('align', '⌖ 위치 맞춤', '현재 두 위치를 기준점으로 맞추고 동기화 재개').clicked.connect(
                lambda: self._align_here())
        tb.add_separator()
        self.btn_laser = tb.add_button('laser', '레이저', '레이저 포인터 (L)', checkable=True)
        self.btn_laser.clicked.connect(lambda on: self.set_tool('laser' if on else 'none'))
        self.btn_pen = tb.add_button('pen', '형광펜', '형광펜 (P) — 드래그', checkable=True)
        self.btn_pen.clicked.connect(lambda on: self.set_tool('pen' if on else 'none'))
        self.btn_zoomtool = tb.add_button('ztool', '클릭확대', '클릭 확대 (Z) — 클릭: 확대 / 다시 클릭: 복귀', checkable=True)
        self.btn_zoomtool.clicked.connect(lambda on: self.set_tool('zoom' if on else 'none'))
        tb.add_button('black', '■', '화면 검게 (B)').clicked.connect(self.toggle_black)
        tb.add_separator()
        tb.add_button('settings', '⚙', '발표 설정', menu=self._settings_menu())
        tb.add_button('exit', '종료 ✕', '발표 종료 (Esc)').clicked.connect(self.close)
        self.toolbar.place()
        self.toolbar.raise_()

    def _mk_menu(self):
        return QMenu(self.toolbar)    # 툴바 스타일(밝은 글자/어두운 배경)을 상속

    def _zoom_menu(self):
        m = self._mk_menu()
        for pct in (50, 75, 100, 125, 150, 200, 300):
            m.addAction(f'{pct}%' + (' (실제 크기)' if pct == 100 else ''),
                        lambda p=pct: self.active.zoom_at(p / 100.0))
        m.addSeparator()
        m.addAction('전체 페이지 맞춤', lambda: self.active.set_fit('page'))
        m.addAction('화면 너비 맞춤', lambda: self.active.set_fit('width'))
        m.addAction('사용자 지정…', self._custom_zoom)
        return m

    def _custom_zoom(self):
        cur = int(round(self.active.zoom * 100))
        val, ok = QInputDialog.getInt(self, '확대율', '확대율(%)', cur, 10, int(self.active.MAX_ZOOM * 100))
        if ok:
            self.active.zoom_at(val / 100.0)

    def _view_menu(self):
        m = self._mk_menu()
        g = QActionGroup(m)
        self._view_actions = {}
        for key, text in VIEW_MODES:
            a = m.addAction(text)
            a.setCheckable(True)
            a.setActionGroup(g)
            a.triggered.connect(lambda _=False, k=key: self._apply_mode(k, user=True))
            self._view_actions[key] = a
        return m

    def _ratio_menu(self):
        """구간 이동 기준 토글(화면 높이 / 페이지 N등분) + 해당 기준의 값 목록. 열 때마다 다시 채운다."""
        m = self._mk_menu()
        m.aboutToShow.connect(lambda: self._fill_ratio_menu(m))
        self._fill_ratio_menu(m)
        return m

    def _fill_ratio_menu(self, m):
        m.clear()
        g = QActionGroup(m)
        for basis, text in (('viewport', '기준: 화면 높이 비율'), ('page', '기준: 페이지 N등분')):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked(self.section_basis == basis)
            a.setActionGroup(g)
            a.triggered.connect(lambda _=False, b=basis: self.set_basis(b))
        m.addSeparator()
        g2 = QActionGroup(m)
        if self.section_basis == 'page':
            for n in nav.PAGE_PARTS:
                a = m.addAction(f'페이지 {n}등분' + (' (기본)' if n == nav.DEFAULT_PARTS else ''))
                a.setCheckable(True)
                a.setChecked(n == self.page_parts)
                a.setActionGroup(g2)
                a.triggered.connect(lambda _=False, n=n: self.set_parts(n))
        else:
            for r in nav.SECTION_RATIOS:
                a = m.addAction(f'화면 높이의 {int(r * 100)}%' + (' (기본)' if r == nav.DEFAULT_RATIO else ''))
                a.setCheckable(True)
                a.setChecked(abs(r - self.section_ratio) < 1e-6)
                a.setActionGroup(g2)
                a.triggered.connect(lambda _=False, r=r: self.set_ratio(r))

    def _section_label(self):
        return f'페이지 ÷{self.page_parts}' if self.section_basis == 'page' else f'화면 {int(round(self.section_ratio * 100))}%'

    def _layout_menu(self):
        m = self._mk_menu()
        g = QActionGroup(m)
        self._layout_actions = {}
        for key, text in ((None, '좌우 동일 비율'), ('left', '왼쪽 집중 (75:25)'), ('right', '오른쪽 집중 (25:75)')):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setActionGroup(g)
            a.triggered.connect(lambda _=False, k=key: self.set_focus(k))
            self._layout_actions[key] = a
        m.addSeparator()
        m.addAction('집중 문서 전환', self.swap_focus)
        self._act_hide = m.addAction('보조 문서 숨기기', self.toggle_secondary)
        return m

    def _settings_menu(self):
        m = self._mk_menu()
        self._act_auto = m.addAction('자동 스크롤 (A)')
        self._act_auto.setCheckable(True)
        self._act_auto.triggered.connect(lambda on: self.toggle_auto(on))
        self._act_anim = m.addAction('이동 애니메이션')
        self._act_anim.setCheckable(True)
        self._act_anim.setChecked(self.animate)
        self._act_anim.toggled.connect(self.set_animate)
        sp = m.addMenu('자동 스크롤 속도')
        for label, v in (('느리게', 30), ('보통', 60), ('빠르게', 120)):
            sp.addAction(label, lambda v=v: self.set_auto_speed(v))
        m.addSeparator()
        m.addAction('현재 페이지 형광펜 지우기 (C)', self.clear_ink_page)
        m.addAction('모든 형광펜 지우기 (Shift+C)', self.clear_ink_all)
        m.addSeparator()
        self._screen_menu = m.addMenu('발표 모니터')
        self._screen_menu.aboutToShow.connect(self._fill_screen_menu)
        return m

    def _fill_screen_menu(self):
        self._screen_menu.clear()
        primary = QGuiApplication.primaryScreen()
        for i, s in enumerate(self.screens(), 1):
            g = s.geometry()
            tags = [t for t, ok in (('현재', s is self._screen), ('기본', s is primary)) if ok]
            text = f'모니터 {i}: {g.width()}×{g.height()}' + (f' ({", ".join(tags)})' if tags else '')
            a = self._screen_menu.addAction(text)
            a.setCheckable(True)
            a.setChecked(s is self._screen)
            a.triggered.connect(lambda _=False, s=s: self.move_to_screen(s))

    # ---- 상태 반영 ------------------------------------------------------------------
    def _update_toolbar_state(self):
        self._sync_overlay()
        c = self.active
        self.btn_zoom.setText(f'{int(round(c.zoom * 100))}%')
        self._act_auto.setChecked(c.auto_scroll_active())
        self.btn_ratio.setText(self._section_label())
        self.btn_view.setText(dict(VIEW_MODES).get(self.view_mode, '보기'))
        for k, a in self._view_actions.items():
            a.setChecked(k == self.view_mode)
        if self.ctx.dual:
            self.btn_sync.setChecked(self.sync != 'off')
            self.btn_sync.setText('동기화 중단됨' if self._stale else '동기화')
            for k, a in self._layout_actions.items():
                a.setChecked(k == self.focus_side)
            self._act_hide.setText('보조 문서 표시' if self.secondary_hidden else '보조 문서 숨기기')
        self.toolbar.buttons['ratio'].setEnabled(not self.spread)
        if hasattr(self, '_view_actions'):
            self._view_actions['spread'].setEnabled(self._spread_allowed())
        self.toolbar.place()
        self._update_badge()

    def _update_badge(self):
        if self.spread and len(self.canvases) > 1:
            n = self.canvases[0].page_count()
            L = self.spread_left
            text = f'{L + 1}–{L + 2} / {n}' if L + 1 < n else f'{L + 1} / {n}'
            self.badge.set_text(text)
            self.lbl_page.setText(text)
            return
        parts = []
        for i, c in enumerate(self.canvases):
            if c.doc and (not self.secondary_hidden or c is self.active or not self.ctx.dual):
                tag = ('L ' if i == 0 else 'R ') if self.ctx.dual else ''
                parts.append(f'{tag}{c.current_page() + 1} / {c.page_count()}')
        text = '   '.join(parts)
        self.badge.set_text(text)
        self.lbl_page.setText(f'{self.active.current_page() + 1} / {self.active.page_count()}')

    def _toast(self, text, ms=2200):
        self.toast.show_text(text, ms)

    def _set_active(self, c):
        self.active = c
        for f in self.frames:
            f.set_active(f.canvas is c, self.ctx.dual)
        self._update_toolbar_state()

    def _layout_all(self):
        self.curtain.setGeometry(self.rect())
        if self.black:
            self.curtain.raise_()
        self.toolbar.place()
        self._update_badge()
        self.toolbar.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for c in self._floating:
            self._frame_of(c).setGeometry(self.rect())
        self._layout_all()

    # ---- 보기 방식 / 이동 -----------------------------------------------------------------
    def _frame_of(self, c):
        return next(f for f in self.frames if f.canvas is c)

    def _float(self, c):
        """확대를 시작한 쪽을 전체 화면 위로 띄운다. 반대쪽은 제자리(맞춤 상태)로 남는다. 마우스 점의 이동량을 반환."""
        if not self.spread or c in self._floating:
            return 0.0, 0.0
        f = self._frame_of(c)
        before = c.viewport().mapToGlobal(QPoint(0, 0))
        idx = self.root.indexOf(f)
        ph = QWidget(self)
        self._floating[c] = ph
        self.root.removeWidget(f)
        self.root.insertWidget(idx, ph, 1)
        ph.show()
        c.h_align = 'center'
        f.setGeometry(self.rect())
        f.raise_()
        self._raise_overlays()
        after = c.viewport().mapToGlobal(QPoint(0, 0))
        return float(before.x() - after.x()), float(before.y() - after.y())

    def _dock(self, c):
        ph = self._floating.pop(c, None)
        if ph is None:
            return
        f = self._frame_of(c)
        idx = self.root.indexOf(ph)
        self.root.removeWidget(ph)
        ph.hide()
        ph.deleteLater()
        self.root.insertWidget(idx, f, 1)
        f.show()
        c.h_align = 'right' if c is self.canvases[0] else 'left'

    def _dock_all(self):
        for c in list(self._floating):
            self._dock(c)

    def _sync_overlay(self):
        for c in list(self._floating):
            if c.fit_mode is not None:        # 맞춤으로 돌아오면 제자리로
                self._dock(c)

    def _raise_overlays(self):
        for wdg in (self.badge, self.toast, self.toolbar):
            wdg.raise_()
        if self.black:
            self.curtain.raise_()

    def _spread_allowed(self):
        return self.portrait_doc and not self.ctx.dual

    def _apply_mode(self, mode, user=True):
        if mode == 'spread':
            if not self._spread_allowed():
                self._toast('2페이지 모아보기는 세로형 문서의 PDF 보기에서만 사용할 수 있습니다', 3000)
                self._update_toolbar_state()
                return
            if user:
                self.user_chose_mode = True
            self.view_mode = 'spread'
            self._enter_spread()
            self._update_toolbar_state()
            if user:
                self._toast('2페이지 모아보기 · 한 쪽 확대(Ctrl+휠): 반대쪽 위로 겹쳐 표시, 드래그 이동 · Enter: 맞춤으로 복귀 · 넘겨도 복귀')
            return
        leaving_page = None
        if self.spread:
            leaving_page = self.spread_left
            self._leave_spread()
        if user:
            self.user_chose_mode = True
            for c in self.canvases:
                c.auto_fit = False     # 사용자가 고른 방식은 임의로 바꾸지 않는다
        self.view_mode = mode
        fit = 'page' if mode == 'page' else 'width'
        wheel = {'page': 'page', 'width': 'free', 'section': 'step', 'smooth': 'smooth'}[mode]
        for c in self.canvases:
            c.wheel_mode = wheel
            c.set_fit(fit)
        if leaving_page is not None:
            self.canvases[0].go_page(leaving_page, animate=False)
        self._update_toolbar_state()
        if user:
            self._toast(dict(VIEW_MODES)[mode])

    # ---- 2페이지 모아보기 --------------------------------------------------------------
    def _enter_spread(self):
        first = self.canvases[0]
        cur = first.current_page()
        first.auto_fit = False
        if len(self.canvases) == 1:
            c = PresentationCanvas()
            c.set_document(self.ctx.panes[0].doc)
            c.set_tool(first.tool)
            f = _PaneFrame(c)
            self.root.addWidget(f, 1)
            self.frames.append(f)
            self.canvases.append(c)
            self._wire(c)
            f.show()
        self.spread = True
        self.root.setSpacing(0)
        self.root.activate()
        for c, align in zip(self.canvases, ('right', 'left')):
            c.restore_click_zoom()
            c.h_align, c.zoom_locked, c.wheel_mode, c.animate = align, False, 'spread', False
            c.before_zoom = self._float
        self.spread_left = cur // 2 * 2
        self._show_spread()

    def _leave_spread(self):
        self._dock_all()
        self.spread = False
        for cv in self.canvases:
            cv.before_zoom = None
        if len(self.canvases) > 1:
            second, frame = self.canvases.pop(1), self.frames.pop(1)
            if self.active is second:
                self.active = self.canvases[0]
            self.root.removeWidget(frame)
            frame.hide()
            frame.deleteLater()
        c = self.canvases[0]
        c.h_align, c.zoom_locked, c.blank, c.animate = 'center', False, False, self.animate
        c.only_page = None
        c._relayout()
        self.root.activate()

    def _show_spread(self):
        a, b = self.canvases[0], self.canvases[1]
        n = a.page_count()
        L = self.spread_left
        # 페이지를 넘기거나 'Ctrl+0'을 누르면 확대/이동을 버리고 항상 맞춤 화면으로 돌아온다
        self._dock_all()
        a.h_align, b.h_align = 'right', 'left'
        for cv in (a, b):
            cv.restore_click_zoom()
            cv._stop_anim()
        a.blank, a.only_page, a.fit_mode = False, L, 'page'
        a.go_page(L, animate=False)
        if L + 1 < n:
            b.blank, b.only_page, b.fit_mode = False, L + 1, 'page'
            b.go_page(L + 1, animate=False)
        else:
            b.blank, b.only_page = True, None        # 홀수 쪽수의 마지막 장은 단독 표시
        self._set_active(a)
        b.viewport().update()
        self._update_badge()

    def spread_next(self):
        if self.spread and self.spread_left + 2 < self.canvases[0].page_count():
            self.spread_left += 2
            self._show_spread()

    def spread_prev(self):
        if self.spread and self.spread_left >= 2:
            self.spread_left -= 2
            self._show_spread()

    def _spread_key(self, k, shift, ctrl=False):
        K = Qt.Key
        if k in (K.Key_Space, K.Key_PageDown, K.Key_Right):
            self.spread_prev() if (shift and k == K.Key_Space) else self.spread_next()
        elif k in (K.Key_PageUp, K.Key_Left):
            self.spread_prev()
        elif k == K.Key_Home:
            self.spread_left = 0
            self._show_spread()
        elif k == K.Key_End:
            self.spread_left = (self.canvases[0].page_count() - 1) // 2 * 2
            self._show_spread()
        elif k in (K.Key_Up, K.Key_Down):
            c = self.active
            if c.fit_mode is None:                 # 확대한 쪽만 위아래 이동
                c.scroll_by(-60 if k == K.Key_Up else 60)
        elif k in (K.Key_Plus, K.Key_Equal):
            self.active.zoom_in()
        elif k in (K.Key_Minus, K.Key_Underscore):
            self.active.zoom_out()
        elif (k == K.Key_0 and ctrl) or k in (K.Key_Return, K.Key_Enter):
            self._show_spread()                    # 확대/이동 해제 → 맞춤 화면 (페이지는 그대로)
        elif k == K.Key_A:
            pass
        else:
            return False
        return True

    def set_ratio(self, r):
        self.section_ratio = r
        self.section_basis = 'viewport'
        for c in self.canvases:
            c.section_ratio = r
            c.section_basis = 'viewport'
        app_settings.set('presentation/basis', 'viewport')
        app_settings.set('presentation/ratio_pct', int(round(r * 100)))
        self._update_toolbar_state()
        self._toast(f'구간 이동: 화면 높이의 {int(round(r * 100))}%')

    def set_basis(self, basis):
        self.section_basis = basis
        for c in self.canvases:
            c.section_basis = basis
        app_settings.set('presentation/basis', basis)
        self._update_toolbar_state()
        self._toast('구간 이동: ' + (f'페이지 {self.page_parts}등분' if basis == 'page'
                                  else f'화면 높이의 {int(round(self.section_ratio * 100))}%'))

    def set_parts(self, n):
        self.page_parts = int(n)
        self.section_basis = 'page'
        for c in self.canvases:
            c.page_parts = self.page_parts
            c.section_basis = 'page'
        app_settings.set('presentation/page_parts', self.page_parts)
        app_settings.set('presentation/basis', 'page')
        self._update_toolbar_state()
        self._toast(f'구간 이동: 페이지 {n}등분')

    def set_animate(self, on):
        self.animate = bool(on)
        for c in self.canvases:
            c.animate = self.animate
        app_settings.set('presentation/animate', self.animate)

    def set_auto_speed(self, v):
        self.auto_speed = float(v)
        for c in self.canvases:
            c.auto_speed = self.auto_speed
        app_settings.set('presentation/auto_speed', int(v))

    def step_next(self):
        if self.spread:
            return self.spread_next()
        self.active.section_next() if self.view_mode != 'page' else self.active.page_next()

    def step_prev(self):
        if self.spread:
            return self.spread_prev()
        self.active.section_prev() if self.view_mode != 'page' else self.active.page_prev()

    def toggle_auto(self, on=None):
        if self.spread:
            return
        c = self.active
        c.set_auto_scroll((not c.auto_scroll_active()) if on is None else bool(on))
        self._toast('자동 스크롤 ' + ('시작' if c.auto_scroll_active() else '정지'))
        self._update_toolbar_state()

    # ---- 도구 -----------------------------------------------------------------------------
    def set_tool(self, tool):
        for c in self.canvases:
            c.set_tool(tool)
        self.btn_laser.setChecked(tool == 'laser')
        self.btn_pen.setChecked(tool == 'pen')
        self.btn_zoomtool.setChecked(tool == 'zoom')
        if tool != 'none':
            self._toast({'laser': '레이저 포인터', 'pen': '형광펜: 드래그하여 강조',
                         'zoom': '클릭 확대: 클릭하면 확대, 다시 클릭하면 복귀'}[tool])

    def toggle_tool(self, tool):
        self.set_tool('none' if self.active.tool == tool else tool)

    def clear_ink_page(self):
        self.active.clear_ink(self.active.current_page())
        self._toast('현재 페이지 형광펜을 지웠습니다')

    def clear_ink_all(self):
        for c in self.canvases:
            c.clear_ink()
        self._toast('모든 형광펜을 지웠습니다')

    # ---- 검은 화면 ---------------------------------------------------------------------
    def toggle_black(self):
        if self.black:
            self._release_black()
        else:
            self.black = True
            self.curtain.setGeometry(self.rect())
            self.curtain.show()
            self.curtain.raise_()
            self.badge.hide()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def _release_black(self):
        self.black = False
        self.curtain.hide()
        self.badge.show()
        self.unsetCursor()
        self.setFocus()
        self._on_activity()

    # ---- 두 PDF: 동기화 / 화면 구성 ---------------------------------------------------------
    def _other(self, c):
        return self.canvases[1] if c is self.canvases[0] else self.canvases[0]

    def _on_scrolled(self, src, pos, hr):
        if not self.ctx.dual or self._syncing or self.sync == 'off' or self._stale:
            return
        dst = self._other(src)
        if not (src.doc and dst.doc):
            return
        if self._anchors is not None:
            ia, ib = self.canvases.index(src), self.canvases.index(dst)
            dst_pos = sa.map_position(src.doc.page_sizes, self._anchors[ia], dst.doc.page_sizes,
                                      self._anchors[ib], pos)
        else:
            dst_pos = pos
        dst_pos = min(dst_pos, float(dst.page_count()))
        self._syncing = True
        try:
            dst.scroll_to_pos(dst_pos, SYNC_RATIO)
            hs = dst.horizontalScrollBar()
            hs.setValue(int(hr * hs.maximum()))
        finally:
            self._syncing = False

    def _offset(self):
        a, b = self.canvases
        return sa.relation_offset(a.doc.page_sizes, self._anchors[0], a.pos_at(SYNC_RATIO),
                                  b.doc.page_sizes, self._anchors[1], b.pos_at(SYNC_RATIO))

    def _align_here(self, quiet=False):
        """현재 좌우 위치를 새 기준점으로 지정하고 동기화를 재개."""
        if not self.ctx.dual or not all(c.doc for c in self.canvases):
            return
        self._anchors = [sa.make_anchor(c.doc.path, c.doc.page_sizes, c.pos_at(SYNC_RATIO), SYNC_RATIO)
                         for c in self.canvases]
        self.sync = 'anchor'
        self._stale = False
        self._update_toolbar_state()
        if not quiet:
            self._toast('현재 위치를 기준으로 동기화했습니다')

    def toggle_sync(self, on=None):
        if not self.ctx.dual:
            return
        if on is None:
            on = self.sync == 'off'
        if not on:
            self.sync = 'off'
            self._stale = False
            self._toast('동기화 해제: 좌우 독립 이동 (⌖ 현재 위치 맞춤으로 재개)')
        else:
            if self._anchors is None:
                self._align_here(quiet=True)   # 재개 시 항상 현재 위치를 기준으로 연결(화면 튐 방지)
                self._toast('동기화 재개 (현재 위치 기준)')
                self._update_toolbar_state()
                return
            self.sync = 'anchor'
            if abs(self._offset()) > SYNC_TOLERANCE_PT:
                self._stale = True      # 점프를 막기 위해 보류 — '현재 위치 맞춤'으로 재개
                self._toast("위치가 달라졌습니다. '⌖ 현재 위치 맞춤'으로 연결하세요", 3500)
            else:
                self._stale = False
                self._toast('동기화 재개')
        self._update_toolbar_state()

    def set_focus(self, side):
        if not self.ctx.dual:
            return
        self.focus_side = side
        if side is None:
            self.secondary_hidden = False
        a, b = nav.split_stretch(side)
        self.root.setStretch(0, a)
        self.root.setStretch(1, b)
        self._apply_secondary_visibility()
        if side:
            self._set_active(self.canvases[0 if side == 'left' else 1])
        self._update_toolbar_state()

    def swap_focus(self):
        if not self.ctx.dual:
            return
        self.set_focus('right' if self.focus_side in (None, 'left') else 'left')
        self._toast('집중 문서: ' + ('오른쪽' if self.focus_side == 'right' else '왼쪽'))

    def toggle_secondary(self):
        if not self.ctx.dual:
            return
        if self.focus_side is None:
            self.set_focus('left')
        self.secondary_hidden = not self.secondary_hidden
        self._apply_secondary_visibility()
        self._update_toolbar_state()

    def _apply_secondary_visibility(self):
        sec = None
        if self.focus_side:
            sec = self.frames[1 if self.focus_side == 'left' else 0]
        for f in self.frames:
            f.setVisible(not (self.secondary_hidden and f is sec))

    # ---- 입력 -----------------------------------------------------------------------------
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        K = Qt.Key
        if k == K.Key_Escape:
            self.close()
            return
        if self.black:
            self._release_black()      # 첫 입력은 해제에만 사용 (페이지 이동 없음)
            return
        if self.spread and self._spread_key(k, shift, ctrl):
            e.accept()
            return
        c = self.active
        if k in (K.Key_Space, K.Key_PageDown):
            self.step_prev() if (shift and k == K.Key_Space) else self.step_next()
        elif k == K.Key_PageUp:
            self.step_prev()
        elif k == K.Key_Right:
            c.page_next()
        elif k == K.Key_Left:
            c.page_prev()
        elif k == K.Key_Down:
            c.scroll_by(60 if not ctrl else 160)
        elif k == K.Key_Up:
            c.scroll_by(-60 if not ctrl else -160)
        elif k == K.Key_Home:
            c.page_top()
        elif k == K.Key_End:
            c.page_bottom()
        elif k in (K.Key_Plus, K.Key_Equal):
            c.zoom_in()
        elif k in (K.Key_Minus, K.Key_Underscore):
            c.zoom_out()
        elif k == K.Key_0 and ctrl:
            c.set_fit('page' if self.view_mode == 'page' else 'width')
        elif k == K.Key_B or k == K.Key_Period:
            self.toggle_black()
        elif k == K.Key_L:
            self.toggle_tool('laser')
        elif k == K.Key_P:
            self.toggle_tool('pen')
        elif k == K.Key_Z:
            self.toggle_tool('zoom')
        elif k == K.Key_C:
            self.clear_ink_all() if shift else self.clear_ink_page()
        elif k == K.Key_A:
            self.toggle_auto()
        elif k == K.Key_Tab:
            self._toggle_toolbar()
        elif k == K.Key_Y and self.ctx.dual:
            self.toggle_sync()
        else:
            super().keyPressEvent(e)
            return
        e.accept()

    def wheelEvent(self, e):
        if self.black:
            e.accept()
            return
        super().wheelEvent(e)

    # ---- 툴바 자동 숨김 / 커서 ------------------------------------------------------------
    def _toggle_toolbar(self):
        if self.toolbar.isVisible():
            self.toolbar.hide()
        else:
            self._show_toolbar()

    def _show_toolbar(self):
        self.toolbar.place()
        self.toolbar.show()
        self.toolbar.raise_()
        self._idle.start()

    def _on_activity(self):
        if self.black:
            return
        for c in self.canvases:
            if c.tool == 'none':
                c.viewport().unsetCursor()
        self.unsetCursor()
        local = self.mapFromGlobal(QCursor.pos())
        if local.y() > self.height() - 130:      # 하단으로 가면 도구 모음 표시
            self._show_toolbar()
        self._idle.start()

    def mouseMoveEvent(self, e):
        self._on_activity()
        super().mouseMoveEvent(e)

    def _on_idle(self):
        if self.toolbar.keep_visible():
            self._idle.start()
            return
        self.toolbar.hide()
        self.toast.hide()
        if not self.black:
            for c in self.canvases:
                if c.tool == 'none':
                    c.viewport().setCursor(Qt.CursorShape.BlankCursor)

    # ---- 종료 -----------------------------------------------------------------------------
    def closeEvent(self, e):
        self._closing = True
        for c in self.canvases:
            c.set_auto_scroll(False)
            c._stop_anim()
        try:
            QGuiApplication.instance().screenRemoved.disconnect(self._on_screen_removed)
        except TypeError:
            pass
        self.closed.emit()
        super().closeEvent(e)


def start_presentation(context, parent=None):
    """발표 창을 열고 반환(호출자는 참조를 유지해야 한다)."""
    if context is None:
        return None
    win = PresentationWindow(context, parent)
    win.start()
    return win

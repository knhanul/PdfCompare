"""Tabbed viewer: tab bar + viewer toolbar + (nav | canvas) + form banner + search."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                             QStackedWidget, QTabBar, QVBoxLayout, QWidget)

from app.shell.global_search import GlobalSearchPanel
from app.shell.work_panel import WorkPanel
from app.viewer.nav_panel import NavPanel
from app.viewer.pdf_canvas import PdfCanvas


class FormBanner(QFrame):
    fill_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('formBanner')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        self.label = QLabel()
        btn = QPushButton('바로 작성하기')
        btn.setObjectName('primaryBtn')
        btn.clicked.connect(self.fill_requested.emit)
        close = QPushButton('✕')
        close.setObjectName('viewerToolBtn')
        close.setFixedWidth(28)
        close.clicked.connect(self.hide)
        lay.addWidget(self.label, 1)
        lay.addWidget(btn)
        lay.addWidget(close)
        self.hide()

    def show_count(self, n):
        self.label.setText(f'이 문서에는 입력 가능한 항목이 {n}개 있습니다.')
        self.show()


class DocView(QWidget):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.banner = FormBanner()
        lay.addWidget(self.banner)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = NavPanel()
        self.canvas = PdfCanvas()
        body.addWidget(self.nav)
        body.addWidget(self.canvas, 1)
        lay.addLayout(body, 1)
        self.nav.set_document(doc)
        self.canvas.set_document(doc)
        self.nav.page_selected.connect(self.canvas.go_to_page)
        self.canvas.page_changed.connect(self.nav.set_current)
        self.search_hits = []
        self.search_index = -1


class ViewerWorkspace(QWidget):
    form_fill_requested = pyqtSignal(str)   # path
    split_requested = pyqtSignal()
    open_requested = pyqtSignal()           # same as Ctrl+O / welcome open
    tab_count_changed = pyqtSignal(int)
    current_changed = pyqtSignal(object)    # doc or None
    close_doc = pyqtSignal(str)
    tool_requested = pyqtSignal(str, str, int)   # tool key, current path, compare slot(0=없음,1/2=viewer)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        tab_row = QWidget()
        tab_row.setObjectName('docTabRow')
        trl = QHBoxLayout(tab_row)
        trl.setContentsMargins(0, 0, 4, 0)
        trl.setSpacing(0)
        self.tabs = QTabBar()
        self.tabs.setObjectName('docTabs')
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setExpanding(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        trl.addWidget(self.tabs)
        self.btn_open_tab = QPushButton('＋ PDF 열기')
        self.btn_open_tab.setObjectName('openPdfTabBtn')
        self.btn_open_tab.setToolTip('PDF 열기 (Ctrl+O)')
        self.btn_open_tab.setMinimumSize(112, 32)
        self.btn_open_tab.clicked.connect(self.open_requested.emit)
        trl.addWidget(self.btn_open_tab, 0, Qt.AlignmentFlag.AlignVCenter)
        trl.addStretch(1)
        lay.addWidget(tab_row)

        lay.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.global_search = GlobalSearchPanel(lambda: [v.doc for v in self._views])
        self.global_search.result_activated.connect(self.jump_to)
        self.global_search.closed.connect(self.hide_global_search)
        self.global_search.hide()
        body.addWidget(self.global_search)
        self.work_panel = WorkPanel()
        self.work_panel.closed.connect(self.close_work_mode)
        self.work_panel.tool_requested.connect(self._request_tool)
        self.work_panel.field_selected.connect(lambda pg: self._cv() and self._cv().canvas.go_to_page(pg))
        body.addWidget(self.work_panel)
        lay.addLayout(body, 1)
        self.default_fit = 'width'
        self.nav_default_visible = True

        self.tabs.currentChanged.connect(self._on_tab)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.tabMoved.connect(self._on_moved)
        self._views = []

        QShortcut(QKeySequence('Ctrl+F'), self, activated=self.show_search)
        QShortcut(QKeySequence('Ctrl+Shift+F'), self, activated=self.show_global_search)
        QShortcut(QKeySequence('Ctrl+='), self, activated=lambda: self._cv() and self._cv().canvas.zoom_in())
        QShortcut(QKeySequence('Ctrl+-'), self, activated=lambda: self._cv() and self._cv().canvas.zoom_out())
        QShortcut(QKeySequence('Ctrl+P'), self, activated=self.print_current)
        QShortcut(QKeySequence('Ctrl+W'), self, activated=lambda: self._close_tab(self.tabs.currentIndex()))

    # ---- toolbar ---------------------------------------------------------
    def _btn(self, text, tip, slot, w=None):
        b = QPushButton(text)
        b.setObjectName('viewerToolBtn')
        b.setToolTip(tip)
        if w:
            b.setFixedWidth(w)
        b.clicked.connect(slot)
        return b

    def _tool_btn(self, text, tip, slot, w=36, h=32, font_px=13):
        """전체비교 PDF 뷰어 툴바(zoom_in_btn 등)와 같은 toolbarBtn 스타일."""
        b = QPushButton(text)
        b.setObjectName('toolbarBtn')
        b.setFixedSize(w, h)
        b.setStyleSheet(f'font-size: {font_px}px; padding: 0px; margin: 0px;')
        b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('viewerToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        bl.setSpacing(4)
        self.btn_nav = self._btn('☰', '페이지 탐색 패널 접기/펼치기', self.toggle_nav, 32)
        bl.addWidget(self.btn_nav)
        bl.addSpacing(8)
        # 전체비교와 동일한 순서: 확대, 축소, 너비, 페이지, 배율 입력, 페이지 이동
        bl.addWidget(self._tool_btn('🔍+', '확대 (Ctrl+=)', lambda: self._cv() and self._cv().canvas.zoom_in()))
        bl.addWidget(self._tool_btn('🔍-', '축소 (Ctrl+-)', lambda: self._cv() and self._cv().canvas.zoom_out()))
        bl.addWidget(self._tool_btn('↔', '너비에 맞춤', lambda: self._cv() and self._cv().canvas.set_fit('width'), font_px=14))
        bl.addWidget(self._tool_btn('📄', '페이지에 맞춤', lambda: self._cv() and self._cv().canvas.set_fit('page'), font_px=14))
        self.zoom_label = QLineEdit('100%')
        self.zoom_label.setObjectName('pageSpin')
        self.zoom_label.setFixedSize(64, 30)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet('font-size: 12px;')
        self.zoom_label.setToolTip('배율을 입력하세요. 예: 150')
        self.zoom_label.editingFinished.connect(self._apply_zoom_input)
        bl.addWidget(self.zoom_label)
        bl.addSpacing(12)
        page_lbl = QLabel('페이지')
        page_lbl.setObjectName('toolbarLabel')
        bl.addWidget(page_lbl)
        self.page_edit = QLineEdit()
        self.page_edit.setObjectName('pageEdit')
        self.page_edit.setFixedWidth(46)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.returnPressed.connect(self._goto_typed)
        bl.addWidget(self.page_edit)
        self.page_total = QLabel('/ 0')
        self.page_total.setObjectName('mutedLabel')
        bl.addWidget(self.page_total)
        bl.addWidget(self._tool_btn('◀', '이전 페이지', lambda: self._step(-1), 32, 30, 14))
        bl.addWidget(self._tool_btn('▶', '다음 페이지', lambda: self._step(1), 32, 30, 14))
        bl.addStretch()
        # 전체비교와 동일한 검색 셋트: 검색어 입력, 이전, 이후, 현재/총 건수
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName('toolbarSearch')
        self.search_edit.setPlaceholderText('검색어 입력')
        self.search_edit.setFixedWidth(150)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.search_edit.returnPressed.connect(lambda: self._search_next(1))
        bl.addWidget(self.search_edit)
        bl.addWidget(self._tool_btn('이전', '이전 결과', lambda: self._search_next(-1), 50, 28, 11))
        bl.addWidget(self._tool_btn('이후', '다음 결과', lambda: self._search_next(1), 50, 28, 11))
        self.search_count_label = QLabel('0/0')
        self.search_count_label.setObjectName('toolbarLabel')
        self.search_count_label.setFixedWidth(60)
        self.search_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_count_label.setStyleSheet('color: #8E8E93; font-size: 11px;')
        bl.addWidget(self.search_count_label)
        bl.addSpacing(8)
        bl.addWidget(self._btn('전체 찾기', '열린 PDF 전체에서 찾기 (Ctrl+Shift+F)', self.show_global_search))
        self.mode_buttons = {}
        for key, text, tip in (('info', '정보', '문서 정보 패널'), ('edit', '편집', '편집 작업 패널'),
                               ('form', '입력 항목', '이 문서의 입력 항목 패널')):
            b = self._btn(text, tip, lambda _=False, k=key: self.toggle_work_mode(k))
            b.setCheckable(True)
            self.mode_buttons[key] = b
            bl.addWidget(b)
        self.mode_buttons['form'].hide()  # shown only for PDFs that contain form fields
        bl.addWidget(self._btn('두 PDF 동시 보기', '현재 문서와 다른 문서를 나란히 보기', self.split_requested.emit))
        self.btn_print = self._btn('🖨 인쇄', '인쇄 / 확대·분할 / 모아찍기 (Ctrl+P)', self.print_current)
        self.btn_print.setEnabled(False)
        bl.addWidget(self.btn_print)
        return bar

    # ---- work modes --------------------------------------------------------
    def toggle_work_mode(self, mode):
        if self.work_panel.mode == mode:
            self.close_work_mode()
        else:
            self.open_work_mode(mode)

    def open_work_mode(self, mode):
        if not self._cv():
            return
        self.work_panel.open_mode(mode, self.current_doc())
        for m, b in self.mode_buttons.items():
            b.setChecked(m == mode)

    def close_work_mode(self):
        self.work_panel.close_panel()
        for b in self.mode_buttons.values():
            b.setChecked(False)

    def work_mode(self):
        return self.work_panel.mode

    def _request_tool(self, key):
        d = self.current_doc()
        if key in ('pdf_compare', 'pdf_hf_compare'):
            if not d:
                return
            menu = QMenu(self)
            act1 = menu.addAction('PDF1에 넣기')
            act2 = menu.addAction('PDF2에 넣기')
            chosen = menu.exec(QCursor.pos())
            if chosen is act1:
                self.tool_requested.emit(key, d.path, 1)
            elif chosen is act2:
                self.tool_requested.emit(key, d.path, 2)
            return
        self.tool_requested.emit(key, d.path if d else '', 0)

    # ---- global search -----------------------------------------------------
    def show_global_search(self):
        self.global_search.show()
        if self.search_edit.text().strip() and not self.global_search.edit.text():
            self.global_search.edit.setText(self.search_edit.text().strip())
        self.global_search.focus_input()

    def hide_global_search(self):
        self.global_search.hide()
        for v in self._views:
            v.canvas.highlights = {}
            v.canvas.viewport().update()

    def jump_to(self, path, page, rect=None):
        i = self.index_of(path)
        if i < 0:
            return False
        self.tabs.setCurrentIndex(i)
        v = self._views[i]
        v.canvas.highlights = {page: [tuple(rect)]} if rect else {}
        v.canvas.go_to_page(page, rect[1] if rect else None)
        v.canvas.viewport().update()
        return True

    def replace_current(self, doc, page=0):
        """Open doc in place of the current tab (기본 열기 방식 = 현재 탭 바꾸기)."""
        i = self.tabs.currentIndex()
        if self.index_of(doc.path) >= 0 or i < 0:
            return self.add_document(doc, page)
        self.add_document(doc, page)
        self._close_tab(i)

    # ---- docs ------------------------------------------------------------
    def _cv(self):
        w = self.stack.currentWidget()
        return w if isinstance(w, DocView) else None

    def current_doc(self):
        v = self._cv()
        return v.doc if v else None

    def index_of(self, path):
        for i, v in enumerate(self._views):
            if v.doc.path == path:
                return i
        return -1

    def add_document(self, doc, page=0):
        i = self.index_of(doc.path)
        if i >= 0:
            self.tabs.setCurrentIndex(i)
            return
        view = DocView(doc)
        view.canvas.fit_mode = None if self.default_fit == '100' else self.default_fit
        view.nav.setVisible(self.nav_default_visible)
        view.banner.fill_requested.connect(lambda p=doc.path: self.form_fill_requested.emit(p))
        view.canvas.page_changed.connect(self._sync_status)
        view.canvas.zoom_changed.connect(self._sync_status)
        self._views.append(view)
        self.stack.addWidget(view)
        idx = self.tabs.addTab(doc.title)
        self.tabs.setTabToolTip(idx, doc.path)
        self.tabs.setCurrentIndex(idx)
        self.stack.setCurrentWidget(view)
        if page:
            QTimer.singleShot(0, lambda: view.canvas.go_to_page(page))
        # form detection after first paint (banner, not a welcome shortcut)
        QTimer.singleShot(150, lambda v=view: self._detect_form(v))
        self.tab_count_changed.emit(len(self._views))

    def _detect_form(self, view):
        if view not in self._views:
            return
        n = view.doc.form_field_count()
        if n > 0:
            view.banner.show_count(n)
            if view is self._cv():
                self.mode_buttons['form'].setVisible(True)

    def _on_tab(self, i):
        if 0 <= i < len(self._views):
            self.stack.setCurrentWidget(self._views[i])
        self._sync_status()
        d = self.current_doc()
        self.mode_buttons['form'].setVisible(bool(d and d.form_field_count()))
        if self.work_panel.mode:
            if self.work_panel.mode == 'form' and not self.mode_buttons['form'].isVisible():
                self.close_work_mode()
            else:
                self.work_panel.refresh(d)
        self.current_changed.emit(d)

    def _on_moved(self, a, b):
        self._views.insert(b, self._views.pop(a))

    def _close_tab(self, i):
        if not (0 <= i < len(self._views)):
            return
        view = self._views.pop(i)
        self.tabs.removeTab(i)
        self.stack.removeWidget(view)
        path = view.doc.path
        view.deleteLater()
        self.close_doc.emit(path)
        if not self._views:
            self.close_work_mode()
        self.tab_count_changed.emit(len(self._views))

    def session_entries(self):
        return [{'path': v.doc.path, 'page': v.canvas.current_page()} for v in self._views]

    def count(self):
        return len(self._views)

    # ---- actions -----------------------------------------------------------
    def toggle_nav(self):
        vis = not (self._views and self._views[0].nav.isVisible())
        for v in self._views:
            v.nav.setVisible(vis)

    def set_nav_visible(self, vis):
        for v in self._views:
            v.nav.setVisible(vis)

    def _step(self, d):
        v = self._cv()
        if v:
            v.canvas.go_to_page(v.canvas.current_page() + d)

    def _goto_typed(self):
        v = self._cv()
        try:
            n = int(self.page_edit.text())
        except ValueError:
            return
        if v:
            v.canvas.go_to_page(n - 1)

    def _apply_zoom_input(self):
        v = self._cv()
        text = self.zoom_label.text().strip().replace('%', '').replace('％', '')
        try:
            percent = float(text)
        except ValueError:
            percent = 0.0
        if not v or percent <= 0:
            self._sync_status()
            return
        v.canvas.set_zoom(percent / 100.0)   # set_zoom이 MIN/MAX_ZOOM으로 클램프
        self._sync_status()

    def print_current(self):
        v = self._cv()
        if v is None:
            return
        from app.shell.print_dialog import open_print_dialog  # lazy
        open_print_dialog(self, v.canvas)

    def _sync_status(self, *_):
        v = self._cv()
        self.btn_print.setEnabled(v is not None)
        self._update_search_count()
        if not v:
            self.page_edit.setText('')
            self.page_total.setText('/ 0')
            return
        self.page_edit.setText(str(v.canvas.current_page() + 1))
        self.page_total.setText(f'/ {v.canvas.page_count()}')
        self.zoom_label.blockSignals(True)
        self.zoom_label.setText(f'{round(v.canvas.zoom * 100)}%')
        self.zoom_label.blockSignals(False)

    def show_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def hide_search(self):
        self.search_edit.clear()   # textChanged가 하이라이트·카운트를 정리

    def _on_search_text_changed(self, text):
        v = self._cv()
        text = text.strip()
        if not v or not text:
            if v:
                v._last_query = None
                v.search_hits = []
                v.search_index = -1
                v.canvas.highlights = {}
                v.canvas.viewport().update()
            self._update_search_count()
            return
        if getattr(v, '_last_query', None) != text:
            v._last_query = text
            v.search_hits = v.doc.search(text)
            v.search_index = -1
            hl = {}
            for p, r in v.search_hits:
                hl.setdefault(p, []).append(r)
            v.canvas.highlights = hl
            v.canvas.viewport().update()
        self._update_search_count()

    def _update_search_count(self):
        v = self._cv()
        total = len(v.search_hits) if v else 0
        cur = v.search_index + 1 if total and v.search_index >= 0 else 0
        self.search_count_label.setText(f'{cur}/{total}')

    def _search_next(self, step=1):
        v = self._cv()
        if not v:
            return
        text = self.search_edit.text().strip()
        if not text:
            return
        if getattr(v, '_last_query', None) != text:
            self._on_search_text_changed(text)
        if not v.search_hits:
            self._update_search_count()
            return
        v.search_index = (v.search_index + step) % len(v.search_hits)
        page, rect = v.search_hits[v.search_index]
        self._update_search_count()
        v.canvas.go_to_page(page, rect[1])
        v.canvas.viewport().update()

"""Tabbed viewer: tab bar + viewer toolbar + (nav | canvas) + form banner + search."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget,
                             QTabBar, QVBoxLayout, QWidget)

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
    tab_count_changed = pyqtSignal(int)
    current_changed = pyqtSignal(object)    # doc or None
    close_doc = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.tabs = QTabBar()
        self.tabs.setObjectName('docTabs')
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setExpanding(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        lay.addWidget(self.tabs)

        lay.addWidget(self._build_toolbar())

        self.search_bar = self._build_search()
        lay.addWidget(self.search_bar)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.tabs.currentChanged.connect(self._on_tab)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.tabMoved.connect(self._on_moved)
        self._views = []

        QShortcut(QKeySequence('Ctrl+F'), self, activated=self.show_search)
        QShortcut(QKeySequence('Ctrl+='), self, activated=lambda: self._cv() and self._cv().canvas.zoom_in())
        QShortcut(QKeySequence('Ctrl+-'), self, activated=lambda: self._cv() and self._cv().canvas.zoom_out())
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

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('viewerToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        bl.setSpacing(4)
        self.btn_nav = self._btn('☰', '페이지 탐색 패널 접기/펼치기', self.toggle_nav, 32)
        bl.addWidget(self.btn_nav)
        bl.addSpacing(8)
        bl.addWidget(self._btn('‹', '이전 페이지', lambda: self._step(-1), 30))
        self.page_edit = QLineEdit()
        self.page_edit.setObjectName('pageEdit')
        self.page_edit.setFixedWidth(46)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.returnPressed.connect(self._goto_typed)
        bl.addWidget(self.page_edit)
        self.page_total = QLabel('/ 0')
        self.page_total.setObjectName('mutedLabel')
        bl.addWidget(self.page_total)
        bl.addWidget(self._btn('›', '다음 페이지', lambda: self._step(1), 30))
        bl.addSpacing(12)
        bl.addWidget(self._btn('−', '축소 (Ctrl+-)', lambda: self._cv() and self._cv().canvas.zoom_out(), 30))
        self.zoom_label = QLabel('100%')
        self.zoom_label.setObjectName('zoomLabel')
        self.zoom_label.setFixedWidth(48)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self.zoom_label)
        bl.addWidget(self._btn('+', '확대 (Ctrl+=)', lambda: self._cv() and self._cv().canvas.zoom_in(), 30))
        bl.addWidget(self._btn('폭 맞춤', '페이지 폭에 맞춤', lambda: self._cv() and self._cv().canvas.set_fit('width')))
        bl.addWidget(self._btn('쪽 맞춤', '한 페이지 전체 보기', lambda: self._cv() and self._cv().canvas.set_fit('page')))
        bl.addStretch()
        bl.addWidget(self._btn('찾기', '문서에서 찾기 (Ctrl+F)', self.show_search))
        bl.addWidget(self._btn('두 PDF 동시 보기', '현재 문서와 다른 문서를 나란히 보기', self.split_requested.emit))
        return bar

    def _build_search(self):
        bar = QFrame()
        bar.setObjectName('contextToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('문서에서 찾기…')
        self.search_edit.returnPressed.connect(self._search_next)
        self.search_info = QLabel('')
        self.search_info.setObjectName('mutedLabel')
        bl.addWidget(self.search_edit, 1)
        bl.addWidget(self.search_info)
        bl.addWidget(self._btn('이전', '이전 결과', lambda: self._search_next(-1)))
        bl.addWidget(self._btn('다음', '다음 결과', lambda: self._search_next(1)))
        bl.addWidget(self._btn('✕', '찾기 닫기', self.hide_search, 28))
        bar.hide()
        return bar

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

    def _on_tab(self, i):
        if 0 <= i < len(self._views):
            self.stack.setCurrentWidget(self._views[i])
        self._sync_status()
        self.current_changed.emit(self.current_doc())

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

    def _sync_status(self, *_):
        v = self._cv()
        if not v:
            self.page_edit.setText('')
            self.page_total.setText('/ 0')
            return
        self.page_edit.setText(str(v.canvas.current_page() + 1))
        self.page_total.setText(f'/ {v.canvas.page_count()}')
        self.zoom_label.setText(f'{round(v.canvas.zoom * 100)}%')

    def show_search(self):
        self.search_bar.show()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def hide_search(self):
        self.search_bar.hide()
        v = self._cv()
        if v:
            v.canvas.highlights = {}
            v.canvas.viewport().update()

    def _search_next(self, step=1):
        v = self._cv()
        if not v:
            return
        text = self.search_edit.text().strip()
        if getattr(v, '_last_query', None) != text:
            v._last_query = text
            v.search_hits = v.doc.search(text)
            v.search_index = -1
            hl = {}
            for p, r in v.search_hits:
                hl.setdefault(p, []).append(r)
            v.canvas.highlights = hl
        if not v.search_hits:
            self.search_info.setText('결과 없음')
            v.canvas.viewport().update()
            return
        v.search_index = (v.search_index + step) % len(v.search_hits)
        page, rect = v.search_hits[v.search_index]
        self.search_info.setText(f'{v.search_index + 1} / {len(v.search_hits)}')
        v.canvas.go_to_page(page, rect[1])
        v.canvas.viewport().update()

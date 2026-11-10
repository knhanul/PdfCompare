"""Light side-by-side view of two PDFs with synchronized scroll and zoom.

This is *not* a comparison tool; it only shows two documents together.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSplitter, QVBoxLayout,
                             QWidget)

from PyQt6.QtCore import QTimer

from app.common.sync_toggle import SyncScrollToggle
from app.viewer import scroll_anchor as sa
from app.viewer.pdf_canvas import PdfCanvas

ANCHOR_TOLERANCE_PT = 3.0   # OFF 중 이동 후 ON 시 '앵커 관계가 유지됨'으로 보는 허용 오차
ANCHOR_TOAST_MS = 2000
# 기준 위치(뷰포트 세로 비율). 캔버스는 확대/창 크기 변경 시 '상단 위치'를 보존하므로 0.0(상단)이어야
# 줌·리사이즈 직후 첫 스크롤에서 화면이 튀지 않는다. (중앙=0.5 는 이동량은 같지만 그 순간 보정 점프가 생김)
ANCHOR_VIEWPORT_RATIO = 0.0


def _pdf_urls(event):
    return [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile().lower().endswith('.pdf')]


class _Pane(QWidget):
    file_dropped = pyqtSignal(str)   # 이 뷰에 드롭된 PDF 경로
    document_changed = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName('splitPane')
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame()
        bar.setObjectName('splitPaneBar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        # 전체비교와 동일한 순서: 확대, 축소, 너비에 맞춤, 페이지에 맞춤, 배율 입력
        self.zoom_in_btn = self._tool_btn('🔍+', '확대', 13)
        self.zoom_out_btn = self._tool_btn('🔍-', '축소', 13)
        self.fit_width_btn = self._tool_btn('↔', '너비에 맞춤', 14)
        self.fit_page_btn = self._tool_btn('📄', '페이지에 맞춤', 14)
        self.zoom_label = QLineEdit('100%')
        self.zoom_label.setObjectName('pageSpin')
        self.zoom_label.setFixedSize(64, 30)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet('font-size: 12px;')
        self.zoom_label.setToolTip('배율을 입력하세요. 예: 150')
        self.label = QLabel(title)
        self.label.setObjectName('splitPaneTitle')
        self.open_btn = QPushButton('열기…')
        self.open_btn.setObjectName('viewerToolBtn')
        self.page_label = QLabel('')
        self.page_label.setObjectName('mutedLabel')
        for w in (self.zoom_in_btn, self.zoom_out_btn, self.fit_width_btn,
                  self.fit_page_btn, self.zoom_label):
            bl.addWidget(w)
        bl.addWidget(self.label, 1)
        bl.addWidget(self.page_label)
        bl.addWidget(self.open_btn)
        self.canvas = PdfCanvas()
        lay.addWidget(bar)
        lay.addWidget(self.canvas, 1)
        self.canvas.page_changed.connect(self._upd)
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.fit_width_btn.clicked.connect(lambda: self.canvas.set_fit('width'))
        self.fit_page_btn.clicked.connect(lambda: self.canvas.set_fit('page'))
        self.zoom_label.editingFinished.connect(self._apply_zoom_input)
        self.canvas.zoom_changed.connect(lambda _z: self._update_zoom_label())

    @staticmethod
    def _tool_btn(text, tip, font_px):
        """전체비교 툴바(zoom_in_btn 등)와 동일한 36x32 toolbarBtn."""
        b = QPushButton(text)
        b.setObjectName('toolbarBtn')
        b.setFixedSize(36, 32)
        b.setStyleSheet(f'font-size: {font_px}px; padding: 0px; margin: 0px;')
        b.setToolTip(tip)
        return b

    def _update_zoom_label(self):
        self.zoom_label.blockSignals(True)
        self.zoom_label.setText(f'{int(round(self.canvas.zoom * 100))}%')
        self.zoom_label.blockSignals(False)

    def _apply_zoom_input(self):
        text = self.zoom_label.text().strip().replace('%', '').replace('％', '')
        try:
            percent = float(text)
        except ValueError:
            percent = 0.0
        if percent <= 0:
            self._update_zoom_label()
            return
        self.canvas.set_zoom(percent / 100.0)
        self._update_zoom_label()

    # ---- drag & drop: 드롭한 PDF를 이 뷰에서 연다 ----
    def _drag_highlight(self, on):
        self.setStyleSheet('QWidget#splitPane { border: 2px solid palette(highlight); }' if on else '')

    def dragEnterEvent(self, event):
        if _pdf_urls(event):
            self._drag_highlight(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drag_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drag_highlight(False)
        paths = _pdf_urls(event)
        if paths:
            event.acceptProposedAction()
            self.file_dropped.emit(paths[0])

    def set_document(self, doc):
        self.canvas.set_document(doc)
        self.label.setText(doc.title if doc else '문서 없음')
        self.label.setToolTip(doc.path if doc else '')
        self._upd()
        self.document_changed.emit()

    def _upd(self, *_):
        c = self.canvas
        self.page_label.setText(f'{c.current_page() + 1} / {c.page_count()}' if c.doc else '')


class SplitView(QWidget):
    is_split_view = True
    open_compare = pyqtSignal(str)   # tool key
    closed = pyqtSignal()

    def __init__(self, doc_manager, parent=None):
        super().__init__(parent)
        self.dm = doc_manager
        self._syncing = False
        self._anchors = None      # {pane: ScrollAnchor} — 현재 동시보기 세션에서만 유지
        self._anchor_stale = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setObjectName('contextToolbar')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 4, 10, 4)
        bl.setSpacing(6)
        title = QLabel('두 PDF 동시 보기')
        title.setObjectName('contextTitle')
        # 전체비교 '동시 스크롤'과 같은 토글 스위치/버튼 스타일
        self.sync_scroll = SyncScrollToggle('스크롤 동기화')
        self.sync_scroll.setObjectName('actionCheckBox')
        self.sync_scroll.setChecked(True)
        self.sync_zoom = SyncScrollToggle('확대 동기화')
        self.sync_zoom.setObjectName('actionCheckBox')
        self.sync_zoom.setChecked(True)
        self.btn_anchor = QPushButton('⌖ 현재 위치 맞춤')
        self.btn_anchor.setObjectName('viewerToolBtn')
        self.btn_anchor.clicked.connect(self.set_anchor)
        self.lbl_toast = QLabel('')
        self.lbl_toast.setObjectName('mutedLabel')
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)
        self.btn_print = QPushButton('🖨 인쇄')
        self.btn_print.setObjectName('viewerToolBtn')
        self.btn_print.setToolTip('두 PDF 인쇄 (Ctrl+P)')
        self.btn_print.clicked.connect(self.print_documents)
        btn_cmp = QPushButton('영역지정비교로 열기')
        btn_cmp.setObjectName('viewerToolBtn')
        btn_cmp.clicked.connect(lambda: self.open_compare.emit('pdf_compare'))
        btn_cmp2 = QPushButton('전체비교로 열기')
        btn_cmp2.setObjectName('viewerToolBtn')
        btn_cmp2.clicked.connect(lambda: self.open_compare.emit('pdf_hf_compare'))
        for w in (title, self.sync_scroll, self.btn_anchor, self.lbl_toast, self.sync_zoom):
            bl.addWidget(w)
        bl.addStretch()
        for w in (btn_cmp, btn_cmp2, self.btn_print):
            bl.addWidget(w)
        lay.addWidget(bar)

        self.left = _Pane('왼쪽 문서')
        self.right = _Pane('오른쪽 문서')
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self.left)
        sp.addWidget(self.right)
        sp.setChildrenCollapsible(False)
        lay.addWidget(sp, 1)

        for pane in (self.left, self.right):
            pane.file_dropped.connect(lambda path, pane=pane: self.open_in_pane(pane, path))
        QShortcut(QKeySequence('Ctrl+P'), self, activated=self.print_documents)
        self.left.open_btn.clicked.connect(lambda: self._pick(self.left))
        self.right.open_btn.clicked.connect(lambda: self._pick(self.right))
        for a, b in ((self.left, self.right), (self.right, self.left)):
            a.canvas.scrolled.connect(lambda pos, hr, a=a, b=b: self._on_scrolled(a, b, pos, hr))
            a.canvas.zoom_changed.connect(lambda z, a=a, b=b: self._sync_zoom(a, b, z))
        for pane in (self.left, self.right):
            pane.document_changed.connect(self._on_document_changed)
        self.sync_scroll.toggled.connect(self._on_sync_toggled)
        self._update_print_enabled()
        self._refresh_anchor_ui()

    def print_documents(self):
        from app.shell.print_dialog import open_print_dialog  # lazy
        open_print_dialog(self, self.left.canvas, self.right.canvas)

    def _update_print_enabled(self):
        self.btn_print.setEnabled(any(p.canvas.doc for p in (self.left, self.right)))
        if hasattr(self, 'lbl_toast'):
            self._refresh_anchor_ui()

    def paths(self):
        return [p.canvas.doc.path if p.canvas.doc else None for p in (self.left, self.right)]

    def set_documents(self, left=None, right=None):
        if left is not None:
            self.left.set_document(left)
        if right is not None:
            self.right.set_document(right)
        self._update_print_enabled()

    def _pick(self, pane):
        from app.shell.open_doc_picker import pick_document
        path = pick_document(self, self.dm, title='열린 문서에서 선택')
        if not path:
            return
        self.open_in_pane(pane, path)

    def open_in_pane(self, pane, path):
        try:
            doc, _ = self.dm.open(path)
        except Exception as e:
            QMessageBox.warning(self, 'PDF 열기 실패', str(e))
            return False
        pane.set_document(doc)
        self._update_print_enabled()
        return True

    # ---- 기준점(앵커) 기반 상대 동기화 -------------------------------------------
    # 상태: A=동기화 OFF / B=일반 동기화(기준점 없음, 기존 방식) / C=기준점 동기화
    def _both_loaded(self):
        return all(p.canvas.doc for p in (self.left, self.right))

    def _sizes(self, pane):
        return pane.canvas.doc.page_sizes

    def _clear_toast(self):
        self.lbl_toast.setText('')

    def _toast(self, text, ms=ANCHOR_TOAST_MS):
        self.lbl_toast.setText(text)
        self._toast_timer.start(ms)

    def _refresh_anchor_ui(self):
        has = self._anchors is not None
        self.btn_anchor.setEnabled(self._both_loaded())
        self.btn_anchor.setText('⌖ 기준점 다시 맞춤' if has else '⌖ 현재 위치 맞춤')
        self.btn_anchor.setToolTip(
            '현재 표시 중인 두 위치를 새로운 동기화 기준점으로 지정합니다.' if has else
            '왼쪽과 오른쪽 PDF의 현재 위치를 연결하여 스크롤을 동기화합니다.')
        if not self.sync_scroll.isChecked():
            tip = '동기화 OFF: 좌우 독립 스크롤'
        elif not has:
            tip = '일반 동기화: 같은 페이지·같은 위치로 이동'
        elif self._anchor_stale:
            tip = '기준점 동기화 일시 중지: 위치가 달라졌습니다. 기준점 다시 맞춤을 누르세요'
        else:
            tip = '기준점 동기화: 설정한 기준점 관계를 유지하며 이동'
        self.sync_scroll.setToolTip(tip)

    def _center_pos(self, pane):
        ratio = self._anchors[pane].viewport_ratio if self._anchors else ANCHOR_VIEWPORT_RATIO
        return sa.capture_pos(pane.canvas, ratio)

    def set_anchor(self):
        """현재 좌우 화면 위치를 기준점으로 저장하고 즉시 동기화. 화면은 움직이지 않는다."""
        if not self._both_loaded():
            return
        self._anchors = {
            p: sa.make_anchor(p.canvas.doc.path, self._sizes(p),
                           sa.capture_pos(p.canvas, ANCHOR_VIEWPORT_RATIO), ANCHOR_VIEWPORT_RATIO)
            for p in (self.left, self.right)}
        self._anchor_stale = False
        self.sync_scroll.setChecked(True)   # OFF 였다면 ON (토글 핸들러는 재정렬하지 않음)
        self._refresh_anchor_ui()
        self._toast('현재 위치를 기준으로 동기화했습니다')

    def clear_anchor(self):
        self._anchors = None
        self._anchor_stale = False
        self._refresh_anchor_ui()

    def _anchors_valid(self):
        if self._anchors is None:
            return False
        for p, a in self._anchors.items():
            if not p.canvas.doc or p.canvas.doc.path != a.document_id:
                self.clear_anchor()
                return False
        return True

    def _anchor_offset(self):
        """두 화면이 기준점 관계에서 벗어난 정도(pt)."""
        l, r = self.left, self.right
        return sa.relation_offset(self._sizes(l), self._anchors[l], self._center_pos(l),
                                  self._sizes(r), self._anchors[r], self._center_pos(r))

    def _on_document_changed(self):
        if self._anchors is not None:
            self.clear_anchor()   # 파일이 바뀌면 이전 기준점 무효화
        else:
            self._refresh_anchor_ui()

    def _on_sync_toggled(self, on):
        if on and self._anchors_valid() and self._both_loaded():
            # OFF 중 따로 움직였다면 화면 점프를 막기 위해 전파를 보류하고 재설정을 안내
            self._anchor_stale = abs(self._anchor_offset()) > ANCHOR_TOLERANCE_PT
            if self._anchor_stale:
                self._toast("위치가 달라졌습니다. '기준점 다시 맞춤'으로 현재 위치를 연결하세요", 4000)
        self._refresh_anchor_ui()

    def _on_scrolled(self, src, target, pos, hr):
        if self._syncing or not self.sync_scroll.isChecked():
            return
        if not self._anchors_valid() or not self._both_loaded():
            return self._sync_scroll(target, pos, hr)   # 기준점 없음 → 기존 일반 동기화 그대로
        if self._anchor_stale:
            if abs(self._anchor_offset()) > ANCHOR_TOLERANCE_PT:
                return
            self._anchor_stale = False
            self._refresh_anchor_ui()
        a_src, a_dst = self._anchors[src], self._anchors[target]
        dst_pos = sa.map_position(self._sizes(src), a_src, self._sizes(target), a_dst,
                                  sa.capture_pos(src.canvas, a_src.viewport_ratio))
        self._syncing = True
        try:
            sa.apply_pos(target.canvas, dst_pos, a_dst.viewport_ratio)
            hs = target.canvas.horizontalScrollBar()
            hs.setValue(int(hr * hs.maximum()))
        finally:
            self._syncing = False

    def _sync_scroll(self, target, pos, hr):
        if self._syncing or not self.sync_scroll.isChecked():
            return
        self._syncing = True
        try:
            target.canvas.set_position(pos, hr)
        finally:
            self._syncing = False

    def _sync_zoom(self, src, target, z):
        if self._syncing or not self.sync_zoom.isChecked():
            return
        self._syncing = True
        try:
            target.canvas.fit_mode = src.canvas.fit_mode
            target.canvas.set_zoom(z, keep_fit=src.canvas.fit_mode is not None)
        finally:
            self._syncing = False

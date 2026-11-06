"""Left navigation panel with lazily rendered page thumbnails."""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QListView, QListWidget, QListWidgetItem

from app.viewer.render_service import render_service

THUMB_ZOOM = 0.2


class NavPanel(QListWidget):
    page_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('navPanel')
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListView.Movement.Static)
        self.setIconSize(QSize(120, 160))
        self.setSpacing(6)
        self.setFixedWidth(168)
        self.doc = None
        self._svc = render_service()
        self._svc.rendered.connect(self._on_rendered)
        self.itemClicked.connect(lambda it: self.page_selected.emit(self.row(it)))
        self.verticalScrollBar().valueChanged.connect(self._request_visible)

    def set_document(self, doc):
        self.clear()
        self.doc = doc
        if not doc:
            return
        blank = QPixmap(90, 120)
        blank.fill(Qt.GlobalColor.white)
        for i in range(doc.page_count):
            it = QListWidgetItem(QIcon(blank), str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(it)
        self._request_visible()

    def set_current(self, page):
        if 0 <= page < self.count():
            self.blockSignals(True)
            self.setCurrentRow(page)
            self.blockSignals(False)
            self.scrollToItem(self.item(page))

    def _request_visible(self, *_):
        if not self.doc or not self.isVisible():
            return
        for i in range(self.count()):
            it = self.item(i)
            if not self.visualItemRect(it).intersects(self.viewport().rect()):
                continue
            img = self._svc.get(self.doc.path, i, THUMB_ZOOM)
            if img is not None:
                it.setIcon(QIcon(QPixmap.fromImage(img)))

    def _on_rendered(self, key):
        if self.doc and key[0] == self.doc.path and key[2] == int(THUMB_ZOOM * 1000):
            img = self._svc.cache.get(key)
            it = self.item(key[1])
            if img is not None and it is not None:
                it.setIcon(QIcon(QPixmap.fromImage(img)))

    def showEvent(self, e):
        super().showEvent(e)
        self._request_visible()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._request_visible()

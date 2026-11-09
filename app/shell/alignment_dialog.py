"""PDF 시작 위치 맞춤 대화상자 (사용자 입력 + 시각화 전용).

좌표는 항상 엔진의 '보이는 좌표(pt, 회전/cropbox 반영, 원점 좌상단)'로 저장한다.
화면 배율(zoom)과 무관하며, 값의 의미(정렬/출력)는 호출자(print_dialog → stream 엔진)가 처리한다.
인쇄 화면에 종속되지 않으므로 향후 PDF 전체비교에서도 재사용할 수 있다.
"""
from dataclasses import dataclass

import pymupdf
from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from app.print_engine.units import PT_PER_MM


@dataclass
class AlignSide:
    title: str
    data: object      # 파일 경로 또는 bytes (렌더링용, 대화상자가 한 번만 연다)
    tooltip: str = ''


def _accent():
    try:
        from app.services import app_settings
        from app.shell.theme import theme_tokens
        return theme_tokens(app_settings.get('ui/theme') or 'default')['accent']
    except Exception:
        return '#FF6B00'


class ElidedLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self._full = text
        self.setMinimumWidth(40)
        self.set_full_text(text)

    def set_full_text(self, text, tip=''):
        self._full = text
        self.setToolTip(tip or text)
        self._elide()

    def minimumSizeHint(self):
        return QSize(40, super().minimumSizeHint().height())

    def sizeHint(self):
        return QSize(120, super().sizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideMiddle,
                                                          max(20, self.width() - 4)))


class PagePreview(QWidget):
    """한 페이지 렌더 + 시작 기준선(클릭/드래그) + 기준선 위쪽 음영."""
    y_changed = pyqtSignal(float)

    def __init__(self, accent, parent=None):
        super().__init__(parent)
        self._pm = None
        self._scale = 1.0     # 논리 px / pt
        self._page_h = 1.0
        self.y_pt = 0.0
        self._accent = QColor(accent)
        self.setCursor(Qt.CursorShape.SplitVCursor)
        self.setMinimumSize(80, 80)

    @property
    def scale(self):
        return self._scale

    def set_page(self, pixmap, scale, page_h_pt):
        self._pm, self._scale, self._page_h = pixmap, scale, page_h_pt
        self.y_pt = max(0.0, min(self.y_pt, page_h_pt))
        self.setFixedSize(round(pixmap.width() / pixmap.devicePixelRatio()),
                          round(pixmap.height() / pixmap.devicePixelRatio()))
        self.update()

    def set_y(self, y):
        self.y_pt = max(0.0, min(float(y), self._page_h))
        self.update()

    def _from_mouse(self, e):
        self.set_y(e.position().y() / self._scale)
        self.y_changed.emit(self.y_pt)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._from_mouse(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._from_mouse(e)

    def paintEvent(self, _):
        p = QPainter(self)
        if self._pm is None:
            return
        p.drawPixmap(0, 0, self._pm)
        y = self.y_pt * self._scale
        shade = QColor(0, 0, 0, 90)
        p.fillRect(QRectF(0, 0, self.width(), y), shade)
        pen = QPen(self._accent, 2)
        p.setPen(pen)
        p.drawLine(QPoint(0, round(y)), QPoint(self.width(), round(y)))
        p.end()


class SidePanel(QFrame):
    changed = pyqtSignal()

    def __init__(self, side: AlignSide, doc, page, y, accent, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.page_count = len(doc)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.title = ElidedLabel(side.title)
        self.title.set_full_text(side.title, side.tooltip or side.title)
        self.title.setObjectName('splitPaneTitle')
        lay.addWidget(self.title)
        row = QHBoxLayout()
        row.addWidget(QLabel('시작 페이지'))
        self.sp_page = QSpinBox(); self.sp_page.setRange(1, self.page_count)
        row.addWidget(self.sp_page)
        self.lbl_total = QLabel(f'/ {self.page_count}'); self.lbl_total.setObjectName('mutedLabel')
        row.addWidget(self.lbl_total); row.addStretch(1)
        lay.addLayout(row)
        self.preview = PagePreview(accent)
        self.scroll = QScrollArea(); self.scroll.setWidget(self.preview)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.scroll, 1)
        self.lbl_y = QLabel(''); lay.addWidget(self.lbl_y)
        btns = QHBoxLayout()
        self.btn_up = QPushButton('▲ −1mm'); self.btn_dn = QPushButton('▼ +1mm')
        for b in (self.btn_up, self.btn_dn):
            b.setObjectName('viewerToolBtn')
            b.setToolTip('Shift+클릭: 5mm')
        self.btn_up.clicked.connect(lambda: self.nudge(-1))
        self.btn_dn.clicked.connect(lambda: self.nudge(1))
        btns.addWidget(self.btn_up); btns.addWidget(self.btn_dn); btns.addStretch(1)
        lay.addLayout(btns)
        self.sp_page.setValue(page + 1)
        self.preview._page_h = doc[page].rect.height  # 렌더 전에도 좌표 범위 유효
        self.preview.y_pt = min(y, self.preview._page_h)
        self.sp_page.valueChanged.connect(lambda *_: (self.render(), self.changed.emit()))
        self.preview.y_changed.connect(lambda *_: (self._upd(), self.changed.emit()))

    # 상태
    def page(self): return self.sp_page.value() - 1
    def y(self): return self.preview.y_pt

    def set_state(self, page, y):
        self.sp_page.blockSignals(True); self.sp_page.setValue(page + 1); self.sp_page.blockSignals(False)
        self.preview._page_h = self.doc[page].rect.height
        self.preview.y_pt = min(y, self.preview._page_h)
        self.render()

    def nudge(self, sign):
        step = 5 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        self.preview.set_y(self.preview.y_pt + sign * step * PT_PER_MM)
        self._upd(); self.changed.emit()

    def _upd(self):
        y = self.preview.y_pt
        self.lbl_y.setText(f'시작 위치: {y:.1f} pt ({y / PT_PER_MM:.1f} mm)')

    def render(self, zoom=None):
        zoom = zoom if zoom is not None else getattr(self, '_zoom', 1.0)
        self._zoom = zoom
        dpr = self.devicePixelRatioF() or 1.0
        pg = self.doc[self.page()]
        pm = pg.get_pixmap(matrix=pymupdf.Matrix(zoom * dpr, zoom * dpr), annots=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format.Format_RGB888).copy()
        qp = QPixmap.fromImage(img)
        qp.setDevicePixelRatio(dpr)
        self.preview.set_page(qp, zoom, pg.rect.height)
        self._upd()

    def page_size(self):
        r = self.doc[self.page()].rect
        return r.width, r.height


class AlignmentDialog(QDialog):
    """sides: [AlignSide, AlignSide], initial: [(page0, y_pt), (page0, y_pt)] → result_state()."""

    def __init__(self, sides, initial, parent=None):
        super().__init__(parent)
        self.setWindowTitle('PDF 시작 위치 맞춤')
        self.resize(1050, 750)
        self.setMinimumSize(640, 480)
        self._docs = [pymupdf.open('pdf', s.data) if isinstance(s.data, (bytes, bytearray))
                      else pymupdf.open(s.data) for s in sides]
        self._initial = [tuple(i) for i in initial]
        self._fit = True
        self._zoom = 1.0
        accent = _accent()
        root = QVBoxLayout(self)
        root.addWidget(QLabel('각 문서에서 출력 시작 위치를 클릭하거나 기준선을 드래그하세요. '
                              '기준선 위쪽(음영)은 출력에서 제외됩니다.'))
        zr = QHBoxLayout()
        zr.addWidget(QLabel('미리보기 배율 (좌우 동일)'))
        for text, fn in (('−', lambda: self._zoom_by(1 / 1.2)), ('+', lambda: self._zoom_by(1.2)),
                         ('맞춤', self._set_fit)):
            b = QPushButton(text); b.setObjectName('viewerToolBtn'); b.clicked.connect(fn); zr.addWidget(b)
        self.lbl_zoom = QLabel(''); zr.addWidget(self.lbl_zoom); zr.addStretch(1)
        root.addLayout(zr)
        panels = QHBoxLayout()
        self.panels = []
        for side, doc, (pg, y) in zip(sides, self._docs, initial):
            pg = max(0, min(pg, len(doc) - 1))
            p = SidePanel(side, doc, pg, y, accent)
            p.changed.connect(self._on_panel_changed)
            self.panels.append(p)
            panels.addWidget(p, 1)  # 동일 너비
        root.addLayout(panels, 1)
        foot = QHBoxLayout()
        self.btn_reset = QPushButton('초기화')
        self.btn_cancel = QPushButton('취소'); self.btn_ok = QPushButton('정렬 적용')
        self.btn_ok.setObjectName('actionBtn')
        self.btn_reset.clicked.connect(self.reset)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)
        foot.addWidget(self.btn_reset); foot.addStretch(1); foot.addWidget(self.btn_cancel); foot.addWidget(self.btn_ok)
        root.addLayout(foot)
        self._t = QTimer(self); self._t.setSingleShot(True); self._t.setInterval(80)
        self._t.timeout.connect(self._relayout)
        QTimer.singleShot(0, self._relayout)

    # 배율: 좌우 동일. 맞춤은 두 페이지가 모두 패널 폭에 들어가는 최소 배율.
    def _fit_zoom(self):
        zs = []
        for p in self.panels:
            w, h = p.page_size()
            vw = max(100, p.scroll.viewport().width() - 4)
            vh = max(100, p.scroll.viewport().height() - 4)
            zs.append(min(vw / w, vh / h))  # 페이지 전체가 보이도록
        return max(0.1, min(zs))

    def _relayout(self):
        if self._fit:
            self._zoom = self._fit_zoom()
        for p in self.panels:
            p.render(self._zoom)
        self.lbl_zoom.setText(f'{self._zoom * 100:.0f}%')

    def _zoom_by(self, f):
        self._fit = False
        self._zoom = max(0.1, min(4.0, self._zoom * f))
        self._relayout()

    def _set_fit(self):
        self._fit = True
        self._relayout()

    def _on_panel_changed(self):
        if self._fit:
            self._t.start()  # 페이지가 바뀌면 맞춤 배율 재계산

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit:
            self._t.start()

    def reset(self):
        for p in self.panels:
            p.set_state(0, 0.0)
        self._relayout()

    def result_state(self):
        return [(p.page(), p.y()) for p in self.panels]

    def done(self, r):
        self._t.stop()
        for d in self._docs:
            d.close()
        self._docs = []
        super().done(r)

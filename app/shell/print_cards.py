"""스마트 인쇄 화면의 목적별 출력 카드 / 결과 도식 위젯 (엔진 로직 없음, 표시 전용)."""
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

SPLIT_GRID = {2: (2, 1), 4: (2, 2), 6: (3, 2), 9: (3, 3)}
NUP_GRID = {2: (2, 1), 4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 16: (4, 4)}

# 단일 문서: (key, 제목, 한 줄 설명, target, mode) — key는 mode와 동일
SINGLE_PRIMARY = [
    ('a3', '크게 인쇄', '작은 글씨·도표를 크게', None, 'a3'),
    ('split', '대형 포스터', '한 페이지를 여러 장으로 크게', None, 'split'),
    ('nup', '모아찍기', '여러 페이지를 한 장에', None, 'nup'),
    ('region', '부분 확대', '필요한 부분만 크게', None, 'region'),
]
SINGLE_MORE = [
    ('normal', '일반 인쇄', None, 'normal'),
    ('booklet', '소책자 만들기', None, 'booklet'),
    ('trim', '여백 제거·자동 확대', None, 'trim'),
    ('long', '긴 페이지 분할 출력', None, 'long'),
]
# 두 PDF 동시보기
DUAL_PRIMARY = [
    ('side', '나란히 비교', '두 문서를 한 장에 좌우로', 'side', None),
    ('L', '왼쪽 PDF만', '왼쪽 문서만 출력', 'L', 'normal'),
    ('R', '오른쪽 PDF만', '오른쪽 문서만 출력', 'R', 'normal'),
    ('inter', '교차 출력', '원본·수정본을 번갈아', 'inter', None),
]
DUAL_MORE = [
    ('fb', '앞뒤 비교 출력', 'fb', None),
    ('ind_split', '개별 문서 확대·분할', 'L', 'split'),
    ('ind_nup', '개별 문서 모아찍기', 'L', 'nup'),
]

TAGLINES = {
    'a3': '작은 글씨와 표를 더 크게 확인할 수 있습니다.',
    'split': 'A3 프린터 없이도 여러 장을 이어 붙여 큰 안내문을 만들 수 있습니다.',
    'nup': '회의자료를 한 장에 정리하고 종이 사용을 줄일 수 있습니다.',
    'region': '계약서의 특정 조항이나 도면 일부만 크게 출력할 수 있습니다.',
    'normal': '문서를 선택한 용지에 맞춰 그대로 출력합니다.',
    'booklet': '교육자료나 업무 매뉴얼을 작은 책자로 만들 수 있습니다.',
    'trim': '불필요한 여백을 잘라내 내용을 용지에 꽉 차게 출력합니다.',
    'long': '세로로 긴 페이지를 여러 장으로 나눠 출력합니다.',
    'side': '두 문서의 내용을 같은 위치에 맞춰 비교할 수 있습니다.',
    'L': '왼쪽 문서만 출력합니다.',
    'R': '오른쪽 문서만 출력합니다.',
    'inter': '원본과 수정본을 한 장씩 번갈아 출력합니다.',
    'fb': '양면 인쇄하면 앞면은 원본, 뒷면은 수정본이 됩니다.',
    'ind_split': '선택한 문서 한 쪽을 여러 장으로 확대 분할합니다.',
    'ind_nup': '선택한 문서 한 쪽의 여러 페이지를 한 장에 모읍니다.',
}


def _page(p, r, fill=False):
    p.drawRect(r)
    if fill:
        p.save(); p.setBrush(p.pen().color()); p.setOpacity(0.25); p.drawRect(r); p.restore()


def _grid(p, r, c, rows, gap=1.5):
    w, h = (r.width() - gap * (c - 1)) / c, (r.height() - gap * (rows - 1)) / rows
    for j in range(rows):
        for i in range(c):
            p.drawRect(QRectF(r.x() + i * (w + gap), r.y() + j * (h + gap), w, h))


def draw_output(p, r, kind, n=4):
    """결과(출력 용지) 도식. r: 그릴 영역."""
    pw = min(r.width(), r.height() * 0.72)
    page = QRectF(r.center().x() - pw / 2, r.y(), pw, pw / 0.72) if pw / 0.72 <= r.height() \
        else QRectF(r.center().x() - r.height() * 0.36, r.y(), r.height() * 0.72, r.height())
    if kind == 'split':
        c, rows = SPLIT_GRID.get(n, (2, 2))
        _grid(p, QRectF(r.x() + 1, r.y() + 1, r.width() - 2, r.height() - 2), c, rows)
    elif kind in ('nup', 'ind_nup'):
        c, rows = NUP_GRID.get(n, (2, 2))
        _grid(p, QRectF(page.x() + 2, page.y() + 2, page.width() - 4, page.height() - 4), c, rows, 1.0)
        p.drawRect(page)
    elif kind in ('side',):
        w = QRectF(r.x(), r.y() + r.height() * 0.2, r.width(), r.height() * 0.6)
        p.drawRect(w); p.drawLine(QPointF(w.center().x(), w.top()), QPointF(w.center().x(), w.bottom()))
    elif kind in ('inter', 'fb'):
        a = QRectF(r.x(), r.y() + 2, r.width() * 0.55, r.height() - 4)
        _page(p, a); _page(p, a.translated(r.width() * 0.4, 0), fill=True)
    elif kind == 'region':
        p.drawRect(page)
        _page(p, QRectF(page.x() + 2, page.y() + page.height() * 0.3, page.width() - 4, page.height() * 0.35), fill=True)
    elif kind == 'booklet':
        h = QRectF(r.x(), r.y() + r.height() * 0.15, r.width() / 2 - 1, r.height() * 0.7)
        _page(p, h); _page(p, h.translated(r.width() / 2 + 1, 0))
    elif kind == 'long':
        _grid(p, QRectF(page.x(), page.y(), page.width(), page.height()), 1, 2, 2.5)
    elif kind == 'trim':
        p.drawRect(page)
        _page(p, QRectF(page.x() + 2, page.y() + 3, page.width() - 4, page.height() - 6), fill=True)
    else:  # a3 / normal / L / R
        p.drawRect(page if kind != 'a3' else r.adjusted(0, 0, 0, 0))


def draw_source(p, r, kind, n=4):
    """원본 도식."""
    sw = min(r.width() * 0.7, r.height() * 0.72)
    page = QRectF(r.center().x() - sw / 2, r.center().y() - sw / 1.44, sw, sw / 0.72)
    if kind in ('nup', 'ind_nup'):
        c, rows = NUP_GRID.get(n, (2, 2))
        _grid(p, r, c, rows, 1.0)
    elif kind in ('side', 'inter', 'fb'):
        a = QRectF(r.x(), r.y() + 2, r.width() * 0.6, r.height() - 4)
        _page(p, a); _page(p, a.translated(r.width() * 0.35, 0), fill=True)
    elif kind == 'region':
        p.drawRect(page)
        p.save(); pen = QPen(p.pen()); pen.setStyle(Qt.PenStyle.DashLine); p.setPen(pen)
        p.drawRect(QRectF(page.x() + 2, page.y() + page.height() * 0.3, page.width() - 4, page.height() * 0.35)); p.restore()
    elif kind == 'long':
        p.drawRect(QRectF(page.x() + page.width() * 0.2, r.y(), page.width() * 0.6, r.height()))
    elif kind == 'booklet':
        _page(p, page); _page(p, page.translated(2, 2))
    else:
        s = QRectF(r.center().x() - r.width() * 0.2, r.center().y() - r.height() * 0.28, r.width() * 0.4, r.height() * 0.56) \
            if kind in ('a3', 'trim') else page
        p.drawRect(s)


def _color():
    return QApplication.palette().color(QPalette.ColorRole.WindowText)


def make_icon(kind, n=4, size=28):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(_color()); pen.setWidthF(2.4); p.setPen(pen)
    m = size * 0.16
    draw_output(p, QRectF(m * 2, m * 2, size * 2 - m * 4, size * 2 - m * 4), kind, n)
    p.end()
    pm.setDevicePixelRatio(2.0)
    return QIcon(pm)


class Diagram(QWidget):
    """원본 → 출력 결과 개념도 (작은 벡터 도식, 실제 미리보기는 왼쪽 큰 화면)."""

    def __init__(self):
        super().__init__()
        self.kind, self.n = 'normal', 4
        self.setFixedSize(132, 54)

    def set_state(self, kind, n):
        self.kind, self.n = kind, n or 4
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = _color()
        pen = QPen(col); pen.setWidthF(1.3); p.setPen(pen)
        h = self.height() - 4
        draw_source(p, QRectF(2, 2, 48, h), self.kind, self.n)
        p.drawLine(QPointF(58, self.height() / 2), QPointF(74, self.height() / 2))
        p.drawLine(QPointF(69, self.height() / 2 - 4), QPointF(74, self.height() / 2))
        p.drawLine(QPointF(69, self.height() / 2 + 4), QPointF(74, self.height() / 2))
        draw_output(p, QRectF(82, 2, 48, h), self.kind, self.n)
        p.end()


class Card(QPushButton):
    """아이콘 + 기능명 + 한 줄 설명. 선택 상태는 팔레트 강조색 테두리로 표시(테마 공통)."""

    def __init__(self, key, title, desc, kind, n=4):
        super().__init__()
        self.key = key
        self.setObjectName('printCard')
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(66)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        self.ico = QLabel(); self.ico.setFixedSize(30, 30)
        self.ico.setPixmap(make_icon(kind, n).pixmap(QSize(28, 28)))
        txt = QVBoxLayout(); txt.setSpacing(1)
        self.t = QLabel(title); f = self.t.font(); f.setBold(True); self.t.setFont(f)
        self.d = QLabel(desc); self.d.setWordWrap(True); self.d.setObjectName('mutedLabel')
        txt.addWidget(self.t); txt.addWidget(self.d)
        lay.addWidget(self.ico); lay.addLayout(txt, 1)
        for w in (self.ico, self.t, self.d):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName(title)
        self.setToolTip(desc)

    def refresh_icon(self, kind, n):
        self.ico.setPixmap(make_icon(kind, n).pixmap(QSize(28, 28)))


CARD_STYLE = """
QPushButton#printCard { text-align:left; border:1px solid palette(mid); border-radius:8px; background:transparent; }
QPushButton#printCard:hover { border:1px solid palette(highlight); }
QPushButton#printCard:checked { border:2px solid palette(highlight); }
QPushButton#printMore { text-align:left; border:1px solid palette(mid); border-radius:6px; padding:4px 8px; background:transparent; }
QPushButton#printMore:hover { border:1px solid palette(highlight); }
QPushButton#printMore:checked { border:2px solid palette(highlight); font-weight:bold; }
QPushButton#printLink { border:none; background:transparent; text-align:left; padding:2px 0; color:palette(link); }
"""

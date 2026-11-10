"""공통 스마트 인쇄 대화상자.

PDF 보기(단일 문서)와 두 PDF 동시 보기(좌/우)에서 같은 대화상자를 호출한다.
엔진(app.print_engine)과 정렬 엔진(stream)을 그대로 재사용하고, 미리보기는 항상
실제 출력과 같은 build_pdf 결과(시트 단위)를 래스터화한다.
"""
import threading
from collections import deque

import pymupdf
from PyQt6.QtCore import QObject, QPoint, QRect, QSize, QThread, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QStackedWidget, QTabBar, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from app.print_engine import Box, Margins, SourceDoc, build_pdf, build_plan, mm
from app.print_engine.pairs import build_pairs_plan
from app.print_engine.pagespec import PageSpecError, parse as parse_pages
from app.print_engine.stream import StreamLayout, plan_side_by_side
from app.print_engine.stream import StreamSide
from app.common import print_output
from app.services import print_presets
from app.shell.alignment_dialog import AlignSide, AlignmentView
from app.shell import print_cards as pc


class PrintSource:
    def __init__(self, title, data, modified=False):
        self.title, self.data, self.modified = title, data, modified


def print_source_from_doc(doc):
    """뷰어 PdfDocument → PrintSource. 항상 현재 메모리 상태의 bytes 스냅샷을 사용한다
    (디스크 재오픈 시 뷰어와 다른 내용이 출력되는 것을 방지). 실패하면 경로로 대체."""
    try:
        return PrintSource(doc.title, doc._doc.tobytes(), modified=bool(getattr(doc, 'modified', False)))
    except Exception:
        return PrintSource(doc.title, doc.path)


def start_from_canvas(canvas):
    """뷰어 캔버스의 현재 스크롤 위치 → (시작 페이지, 페이지 내 y pt)."""
    pos, _ = canvas.position()
    page = max(0, min(int(pos), canvas.page_count() - 1))
    h = canvas.doc.page_sizes[page][1]
    return page, max(0.0, min(h, (pos - page) * h))


def open_print_dialog(parent, left_canvas, right_canvas=None):
    """공통 진입점. 캔버스에 열린 문서를 그대로 전달한다(재선택·재로딩 없음).
    메인 윈도우가 있으면 작업 영역(mode_stack)의 전용 페이지로, 없으면 독립 창으로 표시한다."""
    docs = [c.doc if c is not None else None for c in (left_canvas, right_canvas)]
    if docs[0] is None and docs[1] is not None:  # 왼쪽이 비어 있으면 오른쪽만 단일로
        left_canvas, right_canvas, docs = right_canvas, None, [docs[1], None]
    if docs[0] is None:
        return None
    back = 'PDF 보기로 돌아가기' if docs[1] is None and not getattr(parent, 'is_split_view', False)         else '두 PDF 동시보기로 돌아가기'
    try:
        lp, ly = start_from_canvas(left_canvas)
        l = print_source_from_doc(docs[0])
        if docs[1] is not None:
            rp, ry = start_from_canvas(right_canvas)
            page = SmartPrintDialog(l, print_source_from_doc(docs[1]), lp, rp, ly, ry, None, back_label=back)
        else:
            page = SmartPrintDialog(l, None, lp, 0, ly, 0.0, None, back_label=back)
    except Exception as e:
        QMessageBox.warning(parent, '인쇄', f'인쇄 창을 열 수 없습니다: {e}')
        return None
    host = parent.window() if parent is not None else None
    if host is not None and hasattr(host, 'show_print_page'):
        host.show_print_page(page)
    else:
        page.setWindowTitle('스마트 인쇄')
        page.resize(1180, 780)
        page.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        _STANDALONE.append(page)
        page.destroyed.connect(lambda *_: _STANDALONE.remove(page) if page in _STANDALONE else None)
        page.show()
    return page


SINGLE_MODES = [
    ('normal', '일반 인쇄 (용지에 맞춤)'),
    ('split', '확대 분할'),
    ('a3', 'A3 1장 확대'),
    ('nup', '모아찍기'),
    ('region', '영역 지정 출력'),
    ('trim', '여백 제거·자동 확대'),
    ('booklet', '소책자 (접으면 책)'),
    ('long', '긴 페이지 분할'),
]
SPLIT_N = [2, 4, 6, 9]
NUP_N = [2, 4, 6, 8, 9, 16]
ORDERS = [('Z', '왼쪽→오른쪽, 위→아래'), ('N', '위→아래, 왼쪽→오른쪽'),
          ('Z_rtl', '오른쪽→왼쪽, 위→아래'), ('N_rtl', '위→아래, 오른쪽→왼쪽')]
TARGETS = [('side', '나란히 출력'), ('L', '왼쪽만 출력'), ('R', '오른쪽만 출력'),
           ('inter', '교차 출력 (원본→수정본)'), ('fb', '앞뒤 비교 출력 (양면)')]
PAIR_TARGETS = ('side', 'inter', 'fb')
PICK_DPI = 100


PYMUPDF_LOCK = threading.RLock()   # PyMuPDF는 스레드 동시 사용이 안전하지 않다 → 이 모듈의 모든 사용을 직렬화
THUMB_DPI = 24   # 미리보기 최소 배율(30)보다 작아야 키가 겹치지 않는다


class _PreviewRenderer(QObject):
    """미리보기/썸네일 렌더 전용 스레드 객체. 자체 SourceDoc(스냅샷 bytes)을 지연 생성해 재사용한다.
    요청은 FIFO 큐(시그널)로 처리되며, 최신 세대가 아닌 요청은 건너뛴다(오래된 결과가 덮어쓰지 못함)."""
    rendered = pyqtSignal(int, int, int, object)   # gen, sheet index, dpi, QImage
    failed = pyqtSignal(int, str)

    def __init__(self, data, latest):
        super().__init__()
        self._data, self._latest, self._srcs = dict(data), latest, {}

    @pyqtSlot(int, object, int, int)
    def render(self, gen, plan, k, dpi):
        if gen != self._latest[0]:
            return
        try:
            with PYMUPDF_LOCK:
                for pl in plan.sheets[k].placements:
                    if pl.source_id not in self._srcs:
                        self._srcs[pl.source_id] = SourceDoc(self._data[pl.source_id], pl.source_id, bake=True)
                if gen != self._latest[0]:
                    return
                doc = pymupdf.open('pdf', build_pdf(plan, self._srcs, [k]))
                try:
                    pm = doc[0].get_pixmap(dpi=dpi)
                    img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format.Format_RGB888).copy()
                finally:
                    doc.close()
            self.rendered.emit(gen, k, dpi, img)
        except Exception as e:
            self.failed.emit(gen, str(e))

    def close_all(self):
        with PYMUPDF_LOCK:
            for x in self._srcs.values():
                try:
                    x.close()
                except Exception:
                    pass
            self._srcs = {}


_ORPHANS = []      # release 시 아직 실행 중인 워커 (UI를 막지 않고 끝날 때까지 보관)
_STANDALONE = []   # 호스트 없는 독립 창 참조 유지


def wait_orphan_workers(ms=15000):
    """앱 종료 직전 호출: 남은 출력 스레드가 끝날 때까지 대기."""
    for w in list(_ORPHANS):
        w.wait(ms)


class _BuildWorker(QThread):
    """출력용 PDF를 백그라운드에서 생성. PyMuPDF 문서는 스레드 간 공유가 안전하지 않으므로
    스냅샷 bytes로 자체 SourceDoc을 연다. plan은 읽기 전용 데이터다."""
    built = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, plan, data, parent=None):
        super().__init__(parent)
        self._plan, self._data = plan, dict(data)

    def run(self):
        srcs = {}
        try:
            with PYMUPDF_LOCK:
                ids = {p.source_id for sh in self._plan.sheets for p in sh.placements}
                for k in ids:
                    srcs[k] = SourceDoc(self._data[k], k, bake=True)
                data = build_pdf(self._plan, srcs)
            self.built.emit(data)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            with PYMUPDF_LOCK:
                for x in srcs.values():
                    x.close()


class RegionLabel(QLabel):
    """원본 페이지를 보여 주고 드래그로 영역을 지정한다. 좌표는 라벨 픽셀 → PDF 보이는 좌표(pt)로 변환."""
    region_changed = pyqtSignal(object)   # Box | None

    def __init__(self):
        super().__init__()
        self.px_per_pt = PICK_DPI / 72.0
        self.box = None          # pt
        self._drag = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_page(self, pixmap, px_per_pt):
        self.px_per_pt = px_per_pt
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        self.update()

    def set_box(self, box):
        self.box = box
        self.update()

    def _clamp(self, pt):
        pm = self.pixmap()
        x = min(max(pt.x(), 0), (pm.width() if pm else 0))
        y = min(max(pt.y(), 0), (pm.height() if pm else 0))
        return QPoint(int(x), int(y))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = [self._clamp(e.position().toPoint()), self._clamp(e.position().toPoint())]

    def mouseMoveEvent(self, e):
        if self._drag:
            self._drag[1] = self._clamp(e.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._drag:
            return
        a, b = self._drag
        self._drag = None
        r = QRect(a, b).normalized()
        if r.width() < 4 or r.height() < 4:       # 클릭만 한 경우 무시
            self.update()
            return
        k = self.px_per_pt
        self.box = Box(r.left() / k, r.top() / k, (r.right() + 1) / k, (r.bottom() + 1) / k)
        self.region_changed.emit(self.box)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        k = self.px_per_pt
        r = None
        if self._drag:
            r = QRect(*[v for pt in self._drag for v in (pt.x(), pt.y())][:2], 0, 0)
            r = QRect(self._drag[0], self._drag[1]).normalized()
        elif self.box:
            r = QRect(int(self.box.x0 * k), int(self.box.y0 * k), int(self.box.w * k), int(self.box.h * k))
        if r:
            p.fillRect(r, QColor(40, 120, 255, 50))
            p.setPen(QPen(QColor(40, 120, 255), 2, Qt.PenStyle.DashLine))
            p.drawRect(r)
        p.end()


class SmartPrintDialog(QWidget):
    """Office형 전용 인쇄 페이지(작업 영역에 삽입). 이름은 기존 호환을 위해 유지(SmartPrintPage 별칭)."""
    closed = pyqtSignal()
    _request = pyqtSignal(int, object, int, int)   # → _PreviewRenderer.render (큐 연결)

    def __init__(self, left, right=None, left_page=0, right_page=0, left_y=0.0, right_y=0.0,
                 parent=None, back_label='PDF 보기로 돌아가기'):
        super().__init__(parent)
        self._released = False
        self._hosted = False   # 호스트(MainWindow)가 mode_stack에 삽입하면 True
        self._srcs = {}
        self._plan = None
        self._k = 0
        self._busy = False
        self.dual = right is not None
        self._pages = {'L': left_page, 'R': right_page}
        self._open_sources(left, right)
        self._srcs_meta = [x for x in (left, right) if x]
        self._base_notice = ''

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_back = QPushButton('←  ' + back_label)
        self.btn_back.setObjectName('viewerToolBtn')
        self.btn_back.clicked.connect(self.reject)
        ttl = QLabel('스마트 인쇄')
        ttl.setObjectName('mutedLabel')
        top.addWidget(self.btn_back); top.addStretch(1); top.addWidget(ttl)
        root.addLayout(top)
        QShortcut(QKeySequence('Esc'), self, activated=self._on_escape,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence('Ctrl+P'), self, activated=self.print_pdf,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        # ── 왼쪽 65%: 상단 탭(인쇄 미리보기 / 시작 위치 맞춤) ──
        pv_outer = QVBoxLayout()
        self.tabs = QTabBar()
        self.tabs.addTab('인쇄 미리보기'); self.tabs.addTab('시작 위치 맞춤')
        self.tabs.setExpanding(False)
        self.tabs.setVisible(self.dual)
        self.pv_stack = QStackedWidget()
        preview_page = QWidget()
        pv = QVBoxLayout(preview_page)
        pv.setContentsMargins(0, 0, 0, 0)
        self.align_view = None
        self._align_host = QWidget()
        self._align_host_lay = QVBoxLayout(self._align_host)
        self._align_host_lay.setContentsMargins(0, 0, 0, 0)
        self.pv_stack.addWidget(preview_page)
        self.pv_stack.addWidget(self._align_host)
        pv_outer.addWidget(self.tabs)
        pv_outer.addWidget(self.pv_stack, 1)
        self.tabs.currentChanged.connect(self._on_tab)
        nav = QHBoxLayout()
        self.btn_prev, self.btn_next = QPushButton('◀'), QPushButton('▶')
        for b in (self.btn_prev, self.btn_next):
            b.setObjectName('viewerToolBtn')
        self.btn_prev.clicked.connect(lambda: self._go(-1))
        self.btn_next.clicked.connect(lambda: self._go(1))
        self.lbl_nav = QLabel('')
        self.lbl_info = QLabel('')
        self.lbl_info.setObjectName('mutedLabel')
        nav.addWidget(self.btn_prev); nav.addWidget(self.lbl_nav); nav.addWidget(self.btn_next)
        self._zoom = 'page'          # 'page' | 'width' | float 배율
        self._cache = {}
        self._plan_id = 0
        self._worker = None
        self._busy = False
        self._info_before = ''
        self.btn_zoom_out, self.btn_zoom_in = QPushButton('−'), QPushButton('+')
        self.btn_fit_width, self.btn_fit_page = QPushButton('너비 맞춤'), QPushButton('전체 맞춤')
        for b in (self.btn_zoom_out, self.btn_zoom_in, self.btn_fit_width, self.btn_fit_page):
            b.setObjectName('viewerToolBtn')
            nav.addWidget(b)
        self.btn_zoom_out.clicked.connect(lambda: self._set_zoom(factor=0.8))
        self.btn_zoom_in.clicked.connect(lambda: self._set_zoom(factor=1.25))
        self.btn_fit_width.clicked.connect(lambda: self._set_zoom(mode='width'))
        self.btn_fit_page.clicked.connect(lambda: self._set_zoom(mode='page'))
        nav.addStretch(1); nav.addWidget(self.lbl_info)
        self.lbl_render = QLabel(''); self.lbl_render.setObjectName('mutedLabel')
        self.btn_thumbs = QPushButton('썸네일'); self.btn_thumbs.setObjectName('viewerToolBtn')
        self.btn_thumbs.setCheckable(True); self.btn_thumbs.setChecked(True)
        nav.addWidget(self.btn_thumbs); nav.addWidget(self.lbl_render)
        pv.addLayout(nav)
        mid = QHBoxLayout()
        self.thumbs = QListWidget()
        self.thumbs.setIconSize(QSize(72, 100)); self.thumbs.setFixedWidth(128)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setUniformItemSizes(True)
        mid.addWidget(self.thumbs)
        mid_right = QVBoxLayout(); mid.addLayout(mid_right, 1)
        self.view = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setWidget(self.view)
        mid_right.addWidget(self.scroll, 1)
        self.pick = RegionLabel()
        self.pick_scroll = QScrollArea(); self.pick_scroll.setWidget(self.pick); self.pick_scroll.hide()
        mid_right.addWidget(self.pick_scroll, 1)
        pv.addLayout(mid, 1)
        body.addLayout(pv_outer, 65)

        # ── 오른쪽 35%: 설정 ──
        panel = QWidget()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 6, 0)
        panel.setMinimumWidth(340)
        form_box = QGroupBox('출력 설정')
        form = QFormLayout(form_box)
        self.cmb_target = QComboBox()
        for k, t in TARGETS:
            self.cmb_target.addItem(t, k)
        self.cmb_mode = QComboBox()
        for k, t in SINGLE_MODES:
            self.cmb_mode.addItem(t, k)
        self.cmb_sheet = QComboBox(); self.cmb_sheet.addItems(['A4', 'A3', 'B4'])
        self.cmb_range = QComboBox()
        self.cmb_range.addItem('현재 페이지', 'cur'); self.cmb_range.addItem('전체 페이지', 'all')
        self.cmb_range.addItem('페이지 범위', 'range'); self.cmb_range.addItem('페이지 조합 (1,3,5-8)', 'spec')
        self.sp_from = QSpinBox(); self.sp_to = QSpinBox()
        self.sp_margin = QDoubleSpinBox(); self.sp_margin.setRange(0, 30); self.sp_margin.setValue(5); self.sp_margin.setSuffix(' mm')
        self.sp_overlap = QDoubleSpinBox(); self.sp_overlap.setRange(0, 50); self.sp_overlap.setValue(10); self.sp_overlap.setSuffix(' mm')
        self.chk_marks = QCheckBox('이음선/번호 표시'); self.chk_marks.setChecked(True)
        self.cmb_n = QComboBox()
        self.cmb_order = QComboBox()
        for k, t in ORDERS:
            self.cmb_order.addItem(t, k)
        self.sp_gutter = QDoubleSpinBox(); self.sp_gutter.setRange(0, 30); self.sp_gutter.setValue(5); self.sp_gutter.setSuffix(' mm')
        self.chk_border = QCheckBox('페이지 경계선 표시')
        self.chk_numbers = QCheckBox('페이지 번호 표시')
        self.ed_spec = QLineEdit(); self.ed_spec.setPlaceholderText('예: 1,3,5-8,12 · odd · even')
        self.cmb_fit = QComboBox()
        for k, t in (('fit', '용지에 맞춤'), ('original', '원본 크기'), ('scale', '사용자 배율')):
            self.cmb_fit.addItem(t, k)
        self.sp_scale = QDoubleSpinBox(); self.sp_scale.setRange(10, 800); self.sp_scale.setValue(100); self.sp_scale.setSuffix(' %')
        self.btn_pick = QPushButton('영역 지정 (미리보기에서 드래그)'); self.btn_pick.setCheckable(True)
        self.btn_clear_region = QPushButton('선택 영역 초기화')
        self.lbl_region = QLabel(''); self.lbl_region.setObjectName('mutedLabel'); self.lbl_region.setWordWrap(True)
        self.trim_sp = {}
        for k, t in (('t', '위'), ('b', '아래'), ('l', '왼쪽'), ('r', '오른쪽')):
            sp = QDoubleSpinBox(); sp.setRange(-50, 100); sp.setValue(0); sp.setSuffix(' mm')
            self.trim_sp[k] = sp
        self.cmb_bind = QComboBox(); self.cmb_bind.addItem('왼쪽 제본', 'left'); self.cmb_bind.addItem('오른쪽 제본', 'right')
        self.cmb_printer = QComboBox()
        self.chk_hw = QCheckBox('프린터 인쇄 불가 영역 반영')
        self.lbl_printer = QLabel(''); self.lbl_printer.setObjectName('mutedLabel'); self.lbl_printer.setWordWrap(True)
        self._hw_cache = {}
        self._fill_printers()
        self.region = None           # Box (보이는 좌표 pt) — 문서별 설정, 프리셋에 저장하지 않음
        self._trim_cache = {}
        self.lbl_spec_err = QLabel(''); self.lbl_spec_err.setObjectName('mutedLabel'); self.lbl_spec_err.setWordWrap(True)
        self._fill_n()
        self.cmb_mode.setParent(panel); self.cmb_mode.hide()      # 상태 보관용(선택 UI는 카드)
        rows = {}
        def add(name, *args):
            form.addRow(*args)
            rows[name] = args[-1]
        add('target', '출력 대상', self.cmb_target)
        add('sheet', '용지', self.cmb_sheet)
        add('range', '페이지', self.cmb_range)
        rr = QHBoxLayout(); rr.addWidget(self.sp_from); rr.addWidget(QLabel('~')); rr.addWidget(self.sp_to)
        add('rangebox', '범위', rr)
        add('spec', '조합', self.ed_spec)
        add('specerr', self.lbl_spec_err)
        add('n', '매수 (분할/모아찍기)', self.cmb_n)
        add('order', '배치 순서', self.cmb_order)
        add('gutter', '간격', self.sp_gutter)
        add('overlap', '분할 겹침', self.sp_overlap)
        add('marks', self.chk_marks)
        add('fit', '영역 배율', self.cmb_fit)
        add('scale', '사용자 배율', self.sp_scale)
        add('pick', self.btn_pick)
        add('clear', self.btn_clear_region)
        add('region', self.lbl_region)
        for k, t in (('t', '여백 조정 위'), ('b', '아래'), ('l', '왼쪽'), ('r', '오른쪽')):
            add('trim_' + k, t, self.trim_sp[k])
        add('bind', '제본', self.cmb_bind)
        self.btn_adv = QPushButton('고급 설정 ▸'); self.btn_adv.setObjectName('printLink')
        self.btn_adv.setCheckable(True)
        add('adv', self.btn_adv)
        add('border', self.chk_border)
        add('numbers', self.chk_numbers)
        add('margin', '여백', self.sp_margin)
        add('printer', '프린터', self.cmb_printer)
        add('hw', self.chk_hw)
        add('printernote', self.lbl_printer)
        self._form, self._rows = form, rows
        self.btn_adv.toggled.connect(self._on_option)
        # 프리셋 (방식/용지/배율/여백/레이아웃만 저장 — 문서별 좌표·페이지는 제외)
        pre = QHBoxLayout()
        self.cmb_preset = QComboBox()
        self.btn_preset_save = QPushButton('저장'); self.btn_preset_del = QPushButton('삭제')
        pre.addWidget(QLabel('프리셋')); pre.addWidget(self.cmb_preset, 1)
        pre.addWidget(self.btn_preset_save); pre.addWidget(self.btn_preset_del)
        pl.addLayout(pre)
        self._reload_presets()
        self.cmb_preset.activated.connect(self._on_preset)
        self.btn_preset_save.clicked.connect(self.save_preset)
        self.btn_preset_del.clicked.connect(self.delete_preset)
        self._build_cards(pl)
        pl.addWidget(form_box)
        form_box.setTitle('설정')

        # 나란히 출력용 정렬 패널 (확장/접기 가능)
        self.align_box = QGroupBox('시작 위치 정렬')
        al = QVBoxLayout(self.align_box)
        # 정렬 상태: 문서 페이지(0-based) + 보이는 좌표 y(pt). 계산은 엔진(stream)이 수행.
        self.align = {'L': (left_page, float(left_y)), 'R': (right_page, float(right_y))}
        self._align_initial = dict(self.align)
        self.lbl_align_l, self.lbl_align_r = QLabel(), QLabel()
        al.addWidget(self.lbl_align_l); al.addWidget(self.lbl_align_r)
        self.btn_align = QPushButton('시작 위치 조정...')
        self.btn_align.clicked.connect(self.open_alignment)
        al.addWidget(self.btn_align)
        self._update_align_summary()
        if not self.dual:
            self.align_box.hide()
        pl.addWidget(self.align_box)
        self.lbl_notice = QLabel(''); self.lbl_notice.setWordWrap(True); self.lbl_notice.setObjectName('mutedLabel')
        pl.addWidget(self.lbl_notice)
        pl.addStretch(1)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(panel)
        self._panel_scroll = sc
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setMinimumWidth(360)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        body.addWidget(sc, 35)

        # ── 하단 ──
        foot = QHBoxLayout(); foot.addStretch(1)
        self.btn_cancel = QPushButton('닫기'); self.btn_save = QPushButton('PDF로 저장')
        self.btn_print = QPushButton('인쇄'); self.btn_print.setObjectName('actionBtn')
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.save_pdf)
        self.btn_print.clicked.connect(self.print_pdf)
        for b in (self.btn_cancel, self.btn_save, self.btn_print):
            foot.addWidget(b)
        root.addLayout(foot)

        n = self._srcs['L'].page_count
        for sp in (self.sp_from, self.sp_to):
            sp.setRange(1, n)
        self.sp_from.setValue(left_page + 1); self.sp_to.setValue(n)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)
        for w in (self.cmb_target, self.cmb_mode, self.cmb_sheet, self.cmb_range):
            w.currentIndexChanged.connect(self._on_option)
        for w in (self.cmb_n, self.cmb_order):
            w.currentIndexChanged.connect(self._schedule)
        self.ed_spec.textChanged.connect(self._schedule)
        for w in (self.chk_border, self.chk_numbers):
            w.toggled.connect(self._schedule)
        self.sp_gutter.valueChanged.connect(self._schedule)
        self.cmb_fit.currentIndexChanged.connect(self._on_option)
        self.cmb_printer.currentIndexChanged.connect(self._on_option)
        self.chk_hw.toggled.connect(self._on_option)
        self.cmb_bind.currentIndexChanged.connect(self._schedule)
        self.sp_scale.valueChanged.connect(self._schedule)
        for sp in self.trim_sp.values():
            sp.valueChanged.connect(self._schedule)
        self.btn_pick.toggled.connect(self._toggle_pick)
        self.btn_clear_region.clicked.connect(self._clear_region)
        self.pick.region_changed.connect(self._on_region)
        for w in (self.sp_from, self.sp_to, self.sp_margin, self.sp_overlap):
            w.valueChanged.connect(self._schedule)
        self.chk_marks.toggled.connect(self._schedule)
        if any(s.modified for s in (left, right) if s):
            self._base_notice = '저장되지 않은 변경 사항을 포함한 현재 문서 상태로 출력합니다.'
        if any(getattr(x, 'bake_failed', False) for x in self._srcs.values()):
            self._base_notice = (self._base_notice + ' ' if self._base_notice else '') + \
                '주석/양식 필드를 출력에 포함하지 못했을 수 있습니다.'
        if self._base_notice:
            self.lbl_notice.setText(self._base_notice)
        self._start_renderer()
        self.btn_thumbs.toggled.connect(self._toggle_thumbs)
        self.thumbs.currentRowChanged.connect(self._thumb_selected)
        self._on_option()

    # ── 목적별 출력 카드 / 동적 설정 ──
    def _build_cards(self, pl):
        box = QGroupBox()
        box.setStyleSheet(pc.CARD_STYLE)
        v = QVBoxLayout(box)
        h = QLabel('어떤 형태로 출력할까요?'); f = h.font(); f.setBold(True); f.setPointSizeF(f.pointSizeF() + 1); h.setFont(f)
        sub = QLabel('원하는 결과를 선택하면 알맞은 설정을 자동으로 준비합니다.')
        sub.setObjectName('mutedLabel'); sub.setWordWrap(True)
        v.addWidget(h); v.addWidget(sub)
        self._cards = {}       # key -> 버튼 (카드 + 추가 항목)
        self._items = {}       # key -> (target, mode)
        grid = QGridLayout(); grid.setSpacing(6)
        prim = pc.DUAL_PRIMARY if self.dual else pc.SINGLE_PRIMARY
        more = pc.DUAL_MORE if self.dual else pc.SINGLE_MORE
        for i, (key, title, desc, tgt, mode) in enumerate(prim):
            c = pc.Card(key, title, desc, key)
            c.clicked.connect(lambda _=False, k=key: self._on_card(k))
            self._cards[key] = c; self._items[key] = (tgt, mode)
            grid.addWidget(c, i // 2, i % 2)
        v.addLayout(grid)
        self.btn_more = QPushButton('더 많은 출력 방식 ▾'); self.btn_more.setObjectName('printLink')
        self.btn_more.setCheckable(True)
        v.addWidget(self.btn_more)
        self.more_box = QWidget(); ml = QVBoxLayout(self.more_box); ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(4)
        for key, title, tgt, mode in more:
            b = QPushButton(title); b.setObjectName('printMore'); b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._on_card(k, collapse=True))
            self._cards[key] = b; self._items[key] = (tgt, mode)
            ml.addWidget(b)
        self.more_box.hide()
        self.btn_more.toggled.connect(self.more_box.setVisible)
        self.btn_more.toggled.connect(lambda on: self.btn_more.setText('더 많은 출력 방식 ' + ('▴' if on else '▾')))
        v.addWidget(self.more_box)
        self.lbl_current = QLabel(''); self.lbl_current.setObjectName('mutedLabel'); self.lbl_current.setWordWrap(True)
        v.addWidget(self.lbl_current)
        # 예상 결과
        self.res_box = QGroupBox('예상 결과')
        rl = QHBoxLayout(self.res_box)
        self.diagram = pc.Diagram()
        rv = QVBoxLayout()
        self.lbl_result = QLabel(''); fb = self.lbl_result.font(); fb.setBold(True); self.lbl_result.setFont(fb)
        self.lbl_result.setWordWrap(True)
        self.lbl_tagline = QLabel(''); self.lbl_tagline.setWordWrap(True); self.lbl_tagline.setObjectName('mutedLabel')
        rv.addWidget(self.lbl_result); rv.addWidget(self.lbl_tagline)
        rl.addWidget(self.diagram); rl.addLayout(rv, 1)
        pl.addWidget(box)
        pl.addWidget(self.res_box)

    def card_key(self):
        """현재 (target, mode)에 해당하는 카드/항목 key."""
        mode = self.cmb_mode.currentData()
        if not self.dual:
            return mode
        t = self._target()
        if t in PAIR_TARGETS:
            return t
        return {'split': 'ind_split', 'nup': 'ind_nup'}.get(mode, t)

    def _on_card(self, key, collapse=False):
        tgt, mode = self._items[key]
        if tgt is not None and self.dual:
            self.cmb_target.setCurrentIndex(self.cmb_target.findData(tgt))
        if mode is not None:
            i = self.cmb_mode.findData(mode)
            if i >= 0:
                self.cmb_mode.setCurrentIndex(i)
        if key == 'a3' and self.cmb_sheet.currentText() == 'A4':
            self.cmb_sheet.setCurrentIndex(self.cmb_sheet.findText('A3'))   # 크게 인쇄 기본 용지
        if collapse:
            self.btn_more.setChecked(False)
        self._on_option()

    def _sync_cards(self):
        cur = self.card_key()
        for k, b in self._cards.items():
            b.setChecked(k == cur)
        b = self._cards.get(cur)
        title = (b.t.text() if isinstance(b, pc.Card) else b.text()) if b else ''
        self.lbl_current.setText(f'선택한 출력 방식: {title}')
        self.diagram.set_state(cur, self.cmb_n.currentData() or 4)
        self.lbl_tagline.setText(pc.TAGLINES.get(cur, ''))

    def _apply_visibility(self):
        mode = self.cmb_mode.currentData()
        t = self._target()
        pair = t in PAIR_TARGETS
        adv = self.btn_adv.isChecked()
        self.btn_adv.setText('고급 설정 ' + ('▾' if adv else '▸'))
        single = not pair
        rng = self.cmb_range.currentData()
        fit = self.cmb_fit.currentData()
        v = {
            'target': self.dual and t in ('L', 'R'),
            'sheet': True,
            'range': single and mode != 'region',
            'rangebox': single and mode != 'region' and rng == 'range',
            'spec': single and mode != 'region' and rng == 'spec',
            'specerr': single and mode != 'region' and rng == 'spec',
            'n': single and mode in ('split', 'nup'),
            'order': single and mode == 'nup',
            'gutter': single and mode == 'nup',
            'overlap': single and mode in ('split', 'long'),
            'marks': single and mode in ('split', 'long'),
            'fit': single and mode == 'region',
            'scale': single and mode == 'region' and fit == 'scale',
            'pick': single and mode == 'region',
            'clear': single and mode == 'region',
            'region': single and mode == 'region',
            'bind': single and mode == 'booklet',
            'adv': True,
            'border': adv and single and mode == 'nup',
            'numbers': adv and single and mode == 'nup',
            'margin': adv, 'printer': adv, 'hw': adv, 'printernote': adv,
        }
        for k in 'tblr':
            v['trim_' + k] = single and mode == 'trim'
        for name, w in self._rows.items():
            self._form.setRowVisible(w, bool(v.get(name, False)))
        lab = self._form.labelForField(self.cmb_n)
        if lab is not None:
            lab.setText('분할 장수' if mode == 'split' else '한 장에 넣을 페이지')

    @staticmethod
    def _paper_name(w, h):
        x, y = sorted((w, h))
        for name, (a, b) in (('A4', (595, 842)), ('A3', (842, 1191)), ('B4', (709, 1001)), ('A5', (420, 595))):
            if abs(x - a) / a < 0.03 and abs(y - b) / b < 0.03:
                return name
        return None

    def _update_result(self):
        """실제 계획(plan) 계산 결과로 예상 결과 문구를 만든다."""
        plan = self._plan
        if plan is None or not plan.sheets:
            self.lbl_result.setText('')
            return
        key = self.card_key()
        sh = plan.sheets[0]
        out = self._paper_name(sh.width, sh.height) or self.cmb_sheet.currentText()
        n_out = len(plan.sheets)
        n_in = getattr(self, '_n_in', (0,))
        src = ''
        wh = getattr(self, '_src_wh', None)
        if wh and len(n_in) == 1:
            src = (self._paper_name(*wh) or '원본') + ' '
        if self._target() in PAIR_TARGETS:
            txt = f'원본 {n_in[0]}페이지 + 수정본 {n_in[1]}페이지 → {out} {n_out}장'
            if self._target() == 'side':
                txt += ' (좌우 배치)'
            elif self._target() == 'fb':
                txt += ' (양면)'
        elif key == 'region':
            txt = f'선택 영역 → {out} {n_out}장'
        elif key == 'booklet':
            txt = f'{src}{n_in[0]}페이지 → {out} {n_out}면 ({(n_out + 1) // 2}장 양면)'
        else:
            txt = f'{src}{n_in[0]}페이지 → {out} {n_out}장'
        self.lbl_result.setText(txt)
        self.diagram.set_state(key, self.cmb_n.currentData() or 4)

    # ── 문서 ──
    def _open_sources(self, left, right):
        self._data, self._titles = {}, {}
        for key, s in (('L', left), ('R', right)):
            if s is None:
                continue
            self._data[key], self._titles[key] = s.data, s.title
            self._srcs[key] = SourceDoc(s.data, key, bake=True)

    def release(self):
        """타이머 중지 + SourceDoc 정리 (여러 번 호출해도 안전)."""
        if self._released:
            return
        self._released = True
        self._timer.stop()
        self._dispose_alignment()
        self._stop_renderer()
        if self._worker is not None:
            w, self._worker = self._worker, None
            w.blockSignals(True)              # 해제 후 늦은 콜백(저장/인쇄) 방지
            if w.isRunning():
                w.setParent(None)             # 페이지와 함께 파괴되지 않도록 분리
                _ORPHANS.append(w)
                w.finished.connect(lambda w=w: (_ORPHANS.remove(w) if w in _ORPHANS else None, w.deleteLater()))
        if self._busy:
            self._busy = False
            QApplication.restoreOverrideCursor()
        for s in self._srcs.values():
            s.close()
        self._srcs = {}

    def done(self, r=0):
        """복귀 요청. 실제 정리는 호스트가 화면을 전환할 때 release()로 수행한다."""
        self.closed.emit()
        if not self._hosted:
            self.release()
            self.close()

    def accept(self):
        self.done(1)

    def reject(self):
        self.done(0)

    def closeEvent(self, e):
        self.release()
        super().closeEvent(e)

    # ── 옵션 ──
    def _target(self):
        return self.cmb_target.currentData() if self.dual else 'L'

    def _on_option(self, *_):
        pair = self._target() in PAIR_TARGETS
        side = pair
        self.cmb_mode.setEnabled(not pair)
        self.cmb_range.setEnabled(not pair)
        self.align_box.setVisible(self.dual and pair)
        self.tabs.setTabEnabled(1, self.dual and pair)
        if not (self.dual and pair) and self.pv_stack.currentIndex() == 1:
            self._close_alignment()
        mode = self.cmb_mode.currentData()
        self._fill_n()
        self.cmb_n.setEnabled(mode in ('split', 'nup') and not pair)
        self.sp_overlap.setEnabled(mode in ('split', 'long') and not pair)
        self.chk_marks.setEnabled(mode in ('split', 'long') and not pair)
        for w in (self.cmb_order, self.sp_gutter, self.chk_border, self.chk_numbers):
            w.setEnabled(mode == 'nup' and not pair)
        reg = mode == 'region' and not pair
        for w in (self.cmb_fit, self.btn_pick, self.btn_clear_region):
            w.setEnabled(reg)
        self.sp_scale.setEnabled(reg and self.cmb_fit.currentData() == 'scale')
        for sp in self.trim_sp.values():
            sp.setEnabled(mode == 'trim' and not pair)
        self.cmb_bind.setEnabled(mode == 'booklet' and not pair)
        if reg and self.region is None and not self.btn_pick.isChecked():
            self.btn_pick.setChecked(True)
        elif not reg and self.btn_pick.isChecked():
            self.btn_pick.setChecked(False)
        rng = self.cmb_range.currentData()
        self.sp_from.setEnabled(rng == 'range' and not pair); self.sp_to.setEnabled(rng == 'range' and not pair)
        self.ed_spec.setEnabled(rng == 'spec' and not pair)
        notes = {'a3': '크게 인쇄: 선택한 용지(기본 A3)에 맞춰 확대합니다. 프린터가 A3를 지원하지 않으면 B4 등 지원 용지를 선택하세요.',
                 'booklet': '소책자: 가로 용지 양면 인쇄(짧은 변 기준 뒤집기)로 출력한 뒤 반으로 접으세요. '
                            '프린터 급지 방향이 다르면 PDF로 저장해 앞면/뒷면을 따로 인쇄하며 확인하세요.',
                 'trim': '여백 제거는 원본을 수정하지 않고 인쇄 영역만 잘라 확대합니다. 배경색이 있는 문서는 '
                         '전체가 내용으로 감지될 수 있으니 위/아래/좌/우 조정값으로 보정하세요.'}
        if self._target() == 'fb':
            self.lbl_notice.setText('앞뒤 비교: 홀수 면=원본, 짝수 면=수정본. 프린터에서 양면(긴 변 기준) 인쇄를 선택하세요.')
        elif self._target() == 'inter':
            self.lbl_notice.setText('교차 출력: 원본 1p, 수정본 1p, 원본 2p … 순서. 한쪽이 먼저 끝나면 남은 페이지를 이어서 출력합니다.')
        elif mode in notes:
            self.lbl_notice.setText(notes[mode])
        else:
            self.lbl_notice.setText(self._base_notice)
        # 대상 문서가 바뀌면 페이지 범위 최대값 갱신
        key = self._target() if self._target() not in PAIR_TARGETS else 'L'
        n = self._srcs[key].page_count
        for sp in (self.sp_from, self.sp_to):
            sp.blockSignals(True); sp.setMaximum(n); sp.blockSignals(False)
        self._update_printer_note()
        self._sync_cards()
        self._apply_visibility()
        self._schedule()

    # ── 프린터 / 인쇄 불가 영역 ──
    def _fill_printers(self):
        self.cmb_printer.blockSignals(True)
        self.cmb_printer.addItem('선택 안 함 (여백 설정만 사용)', None)
        names, _default = print_output.available_printers()
        for n in names:
            self.cmb_printer.addItem(n, n)
        # 기본 프린터를 자동 조회하지 않는다: 일부 드라이버(XPS/가상 프린터)는 페이지 레이아웃 조회가
        # 느리거나 COM 오류를 낸다. 사용자가 프린터를 직접 선택하고 반영을 켠 경우에만 질의한다.
        self.cmb_printer.blockSignals(False)

    def _hw_margin_mm(self):
        """선택한 프린터의 최소 여백(mm). 반영 안 함/알 수 없음이면 0."""
        name = self.cmb_printer.currentData()
        if not name or not self.chk_hw.isChecked():
            return 0.0
        if name not in self._hw_cache:
            self._hw_cache[name] = print_output.min_margin_mm(name)
        return self._hw_cache[name] or 0.0

    def _effective_margin_pt(self):
        """사용자 여백과 프린터 인쇄 불가 영역 중 큰 값 — 엔진 배치와 PDF 저장이 같은 값을 사용한다."""
        return mm(max(self.sp_margin.value(), self._hw_margin_mm()))

    def _update_printer_note(self):
        name = self.cmb_printer.currentData()
        if not name:
            self.lbl_printer.setText('')
            return
        notes = []
        hw = self._hw_margin_mm()
        if self.chk_hw.isChecked():
            if hw > self.sp_margin.value():
                notes.append(f'프린터 인쇄 불가 영역 {hw:.1f}mm를 여백에 반영했습니다 (설정 여백 {self.sp_margin.value():.1f}mm보다 큼).')
            elif hw > 0:
                notes.append(f'프린터 인쇄 불가 영역 {hw:.1f}mm — 설정 여백으로 충분합니다.')
        mode = self.cmb_mode.currentData()
        sheet = 'A3' if (mode == 'a3' and self._target() not in PAIR_TARGETS) else self.cmb_sheet.currentText()
        sup = print_output.supports_paper(name, sheet)
        if sup is False:
            notes.append(f'⚠ 선택한 프린터가 {sheet} 용지를 지원하지 않습니다. PDF로 저장하거나 다른 프린터를 선택하세요.')
        self.lbl_printer.setText('\n'.join(notes))

    # ── 비동기 미리보기 / 썸네일 ──
    def _start_renderer(self):
        self._latest = [0]
        self._outstanding = set()
        self._thumb_queue = deque()
        self._rthread = QThread(self)
        self._renderer = _PreviewRenderer(self._data, self._latest)
        self._renderer.moveToThread(self._rthread)
        self._renderer.rendered.connect(self._on_rendered)
        self._renderer.failed.connect(self._on_render_failed)
        self._request.connect(self._renderer.render)
        self._rthread.start()

    def _stop_renderer(self):
        self._latest[0] = -1
        self._outstanding.clear(); self._thumb_queue.clear()
        self._renderer.blockSignals(True)
        self._rthread.quit()
        if self._rthread.wait(3000):
            self._renderer.close_all()
        else:   # 렌더 중이면 UI를 막지 않고 분리해 끝날 때까지 보관
            self._rthread.setParent(None)
            _ORPHANS.append(self._rthread)
            r, t = self._renderer, self._rthread
            t.finished.connect(lambda: (_ORPHANS.remove(t) if t in _ORPHANS else None, r.close_all()))

    def _send(self, k, dpi):
        key = (self._plan_id, k, dpi)
        if key in self._outstanding:
            return
        self._outstanding.add(key)
        self._request.emit(self._plan_id, self._plan, k, dpi)
        self._update_render_label()

    def _update_render_label(self):
        busy = any(key[2] != THUMB_DPI for key in self._outstanding)
        self.lbl_render.setText('렌더링 중…' if busy else '')

    def render_idle(self):
        return not self._outstanding

    def _on_rendered(self, gen, k, dpi, img):
        if gen != self._plan_id or self._plan is None:
            return   # 오래된 결과는 최신 설정 화면을 덮어쓰지 못한다
        self._outstanding.discard((gen, k, dpi))
        pm = QPixmap.fromImage(img)
        if dpi == THUMB_DPI:
            it = self.thumbs.item(k)
            if it is not None:
                it.setIcon(QIcon(pm))
            self._pump_thumbs()
        else:
            if len(self._cache) >= 12:
                self._cache.pop(next(iter(self._cache)))
            self._cache[(gen, k, dpi)] = pm
            if k == self._k:
                if dpi == self._dpi_for(self._plan.sheets[k]):
                    self.view.setPixmap(pm)
                else:
                    self.view.setPixmap(pm)   # 우선 보여 주고(흐릿할 수 있음), 현재 창 크기에 맞는 배율을 다시 요청
                    self._show()
        self._update_render_label()

    def _on_render_failed(self, gen, msg):
        if gen == self._plan_id:
            self._outstanding = {x for x in self._outstanding if x[0] != gen}
            self.lbl_render.setText(f'미리보기 오류: {msg}')

    def _rebuild_thumbs(self):
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        self._thumb_queue.clear()
        if self._plan is not None:
            for i in range(len(self._plan.sheets)):
                self.thumbs.addItem(QListWidgetItem(str(i + 1)))
            self.thumbs.setCurrentRow(self._k)
            self._thumb_queue.extend(sorted(range(len(self._plan.sheets)), key=lambda i: abs(i - self._k)))
        self.thumbs.blockSignals(False)
        self._pump_thumbs()

    def _pump_thumbs(self):
        if self._plan is None or not self.btn_thumbs.isChecked():
            return
        while self._thumb_queue and sum(1 for x in self._outstanding if x[2] == THUMB_DPI) < 3:
            self._send(self._thumb_queue.popleft(), THUMB_DPI)

    def _toggle_thumbs(self, on):
        self.thumbs.setVisible(on)
        if on:
            self._pump_thumbs()

    def _thumb_selected(self, row):
        if self._plan is not None and 0 <= row < len(self._plan.sheets) and row != self._k:
            self._k = row
            self._show()

    # ── 프리셋 ──
    def _reload_presets(self, select=None):
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        self.cmb_preset.addItem('프리셋 선택…', None)
        for n in print_presets.names():
            self.cmb_preset.addItem(n, n)
        i = self.cmb_preset.findData(select) if select else 0
        self.cmb_preset.setCurrentIndex(max(0, i))
        self.cmb_preset.blockSignals(False)

    def collect_settings(self):
        return {'target': self._target(), 'mode': self.cmb_mode.currentData(),
                'sheet': self.cmb_sheet.currentText(), 'n': self.cmb_n.currentData(),
                'margin': self.sp_margin.value(), 'overlap': self.sp_overlap.value(),
                'marks': self.chk_marks.isChecked(), 'order': self.cmb_order.currentData(),
                'gutter': self.sp_gutter.value(), 'border': self.chk_border.isChecked(),
                'numbers': self.chk_numbers.isChecked(), 'fit': self.cmb_fit.currentData(),
                'scale': self.sp_scale.value(), 'bind': self.cmb_bind.currentData()}

    def apply_settings(self, d):
        """프리셋 적용. 현재 문서와 호환되지 않는 항목은 건너뛰고 안내문에 표시한다."""
        d = print_presets.clean(d)
        skipped = []

        def pick(combo, key, label):
            if key in d:
                i = combo.findData(d[key]) if combo.findData(d[key]) >= 0 else combo.findText(str(d[key]))
                if i >= 0:
                    combo.setCurrentIndex(i)
                else:
                    skipped.append(label)

        if 'target' in d:
            if self.dual and self.cmb_target.findData(d['target']) >= 0:
                self.cmb_target.setCurrentIndex(self.cmb_target.findData(d['target']))
            elif d['target'] in PAIR_TARGETS:
                skipped.append('출력 대상(두 PDF 필요)')
        if 'mode' in d and self.cmb_mode.isEnabled():
            pick(self.cmb_mode, 'mode', '출력 방식')
        elif 'mode' in d and self._target() in PAIR_TARGETS:
            pass
        pick(self.cmb_sheet, 'sheet', '용지')
        if d.get('mode') == 'a3' and 'sheet' not in d:
            self.cmb_sheet.setCurrentIndex(self.cmb_sheet.findText('A3'))
        self._fill_n()
        pick(self.cmb_n, 'n', '매수')
        for key, w in (('margin', self.sp_margin), ('overlap', self.sp_overlap), ('gutter', self.sp_gutter),
                       ('scale', self.sp_scale)):
            if key in d:
                w.setValue(float(d[key]))
        for key, w in (('marks', self.chk_marks), ('border', self.chk_border), ('numbers', self.chk_numbers)):
            if key in d:
                w.setChecked(bool(d[key]))
        pick(self.cmb_order, 'order', '배치 순서')
        pick(self.cmb_fit, 'fit', '영역 배율')
        pick(self.cmb_bind, 'bind', '제본')
        self._on_option()
        if skipped:
            self.lbl_notice.setText('프리셋에서 적용되지 않은 항목: ' + ', '.join(skipped))

    def _on_preset(self, _i):
        name = self.cmb_preset.currentData()
        if name:
            self.apply_settings(print_presets.get(name))

    def save_preset(self):
        name, ok = QInputDialog.getText(self, '프리셋 저장', '프리셋 이름:')
        if not ok:
            return
        try:
            print_presets.save(name, self.collect_settings())
        except ValueError as e:
            QMessageBox.warning(self, '프리셋', str(e))
            return
        self._reload_presets(name.strip())

    def delete_preset(self):
        name = self.cmb_preset.currentData()
        if not name:
            return
        try:
            print_presets.delete(name)
        except ValueError as e:
            QMessageBox.information(self, '프리셋', str(e))
            return
        self._reload_presets()

    # ── 영역 지정 ──
    def _pick_page(self):
        t = self._target()
        t = 'L' if t in PAIR_TARGETS else t
        return t, self._pages[t]

    def _toggle_pick(self, on):
        self.scroll.setVisible(not on)
        self.pick_scroll.setVisible(on)
        if on:
            self._show_pick()
        else:
            self._schedule()

    def _show_pick(self):
        key, page = self._pick_page()
        doc = self._srcs[key]._doc
        _lock = PYMUPDF_LOCK
        _lock.acquire()
        pg = doc[page]
        # SourceDoc는 회전을 0으로 정규화해 두므로, 미리보기용으로 원래 회전을 임시 복원한다.
        pg.set_rotation(self._srcs[key]._rot[page])
        try:
            pm = pg.get_pixmap(dpi=PICK_DPI, annots=True)
        finally:
            pg.set_rotation(0)
            _lock.release()
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format.Format_RGB888).copy()
        self.pick.set_page(QPixmap.fromImage(img), PICK_DPI / 72.0)
        self.pick.set_box(self.region)
        self._update_region_label()

    def _on_region(self, box):
        self.region = box
        self._update_region_label()
        self.btn_pick.setChecked(False)      # 선택 완료 → 출력 미리보기로

    def _clear_region(self):
        self.region = None
        self.pick.set_box(None)
        self._update_region_label()
        if self.cmb_mode.currentData() == 'region':
            self.btn_pick.setChecked(True)
            self._show_pick()
        self._schedule()

    def _update_region_label(self):
        r = self.region
        self.lbl_region.setText('선택 영역 없음 — 미리보기에서 드래그하세요.' if r is None else
                                f'선택 영역: {r.w / 72 * 25.4:.0f} × {r.h / 72 * 25.4:.0f} mm '
                                f'(왼쪽 {r.x0 / 72 * 25.4:.0f}, 위 {r.y0 / 72 * 25.4:.0f} mm)')

    def _trim_regions(self, key, idx):
        """페이지별 감지 영역 − 사용자 조정(mm). 원본 불변, 클리핑 경계만 계산."""
        src = self._srcs[key]
        ins = {k: mm(sp.value()) for k, sp in self.trim_sp.items()}
        out = {}
        for i in idx:
            if (key, i) not in self._trim_cache:
                with PYMUPDF_LOCK:
                    self._trim_cache[(key, i)] = src.detect_content(i)
            b = self._trim_cache[(key, i)]
            info = src.page_info(i)
            if b is None:
                b = Box(0, 0, info.width, info.height)
            nb = Box(b.x0 + ins['l'], b.y0 + ins['t'], b.x1 - ins['r'], b.y1 - ins['b'])
            out[i] = nb
        return out

    def _fill_n(self):
        mode = self.cmb_mode.currentData() if hasattr(self, 'cmb_mode') else 'normal'
        vals = SPLIT_N if mode == 'split' else NUP_N
        if [self.cmb_n.itemData(i) for i in range(self.cmb_n.count())] == vals:
            return
        self.cmb_n.blockSignals(True); self.cmb_n.clear()
        for v in vals:
            self.cmb_n.addItem(f'{v}장' if mode == 'split' else f'{v}페이지', v)
        self.cmb_n.blockSignals(False)

    def _schedule(self, *_):
        self._timer.start()

    # ── 시작 위치 정렬 ──
    def _stream_side(self, key):
        page, y = self.align[key]
        return StreamSide(key, self._srcs[key].infos()[page:], y)

    def _update_align_summary(self):
        for key, lbl, name in (('L', self.lbl_align_l, '왼쪽'), ('R', self.lbl_align_r, '오른쪽')):
            page, y = self.align[key]
            lbl.setText(f'{name}: {page + 1}페이지 · {y:.0f}pt')

    def open_alignment(self):
        """시작 위치 맞춤 탭으로 전환(팝업 없음). 뷰어의 스크롤/동기화 기준점은 건드리지 않는다."""
        if not self.dual:
            return
        if self.align_view is None:
            sides = [AlignSide(self._titles[k], self._data[k], self._titles[k]) for k in ('L', 'R')]
            v = AlignmentView(sides, [self.align['L'], self.align['R']], self._align_host)
            v.applied.connect(self._apply_alignment)
            v.cancelled.connect(self._close_alignment)
            self._align_host_lay.addWidget(v)
            self.align_view = v
        self.tabs.blockSignals(True); self.tabs.setCurrentIndex(1); self.tabs.blockSignals(False)
        self.pv_stack.setCurrentIndex(1)

    def _on_tab(self, i):
        if i == 1:
            self.open_alignment()
        else:
            self.pv_stack.setCurrentIndex(0)    # 미적용 편집은 탭에 보관(적용/취소 전까지)

    def _dispose_alignment(self):
        v, self.align_view = self.align_view, None
        if v is not None:
            v.release()
            self._align_host_lay.removeWidget(v)
            v.deleteLater()

    def _show_preview_tab(self):
        self.tabs.blockSignals(True); self.tabs.setCurrentIndex(0); self.tabs.blockSignals(False)
        self.pv_stack.setCurrentIndex(0)

    def _apply_alignment(self):
        if self.align_view is None:
            return
        (lp, ly), (rp, ry) = self.align_view.result_state()
        self.align = {'L': (lp, ly), 'R': (rp, ry)}
        self._dispose_alignment()
        self._update_align_summary()
        self._show_preview_tab()
        self.refresh()   # 최종 출력 배치 즉시 반영 (원본은 다시 열지 않음)

    def _close_alignment(self):
        self._dispose_alignment()
        self._show_preview_tab()

    def _on_escape(self):
        if self.pv_stack.currentIndex() == 1:   # 맞춤 탭에서는 Esc = 변경 취소 후 미리보기로
            self._close_alignment()
        else:
            self.reject()

    # ── 계획 ──
    def _make_plan(self):
        """(plan, sources) — 미리보기/저장/인쇄가 모두 이 결과를 사용."""
        m = self._effective_margin_pt()
        margins = Margins(m, m, m, m)
        target = self._target()
        if target in ('inter', 'fb'):
            li = self._srcs['L'].infos()[self.align['L'][0]:]
            ri = self._srcs['R'].infos()[self.align['R'][0]:]
            sheet = self.cmb_sheet.currentText()
            self._n_in = (len(li), len(ri))
            plan = build_pairs_plan('interleave' if target == 'inter' else 'front_back', li, ri,
                                    sheet=sheet, margins=margins)
            return plan, {'L': self._srcs['L'], 'R': self._srcs['R']}
        if target == 'side':
            self._n_in = (self._srcs['L'].page_count - self.align['L'][0], self._srcs['R'].page_count - self.align['R'][0])
            lay = StreamLayout(sheet=self.cmb_sheet.currentText(), landscape=True, margins=margins)
            plan = plan_side_by_side(self._stream_side('L'), self._stream_side('R'), lay)
            return plan, {'L': self._srcs['L'], 'R': self._srcs['R']}
        src = self._srcs[target]
        n = src.page_count
        rng = self.cmb_range.currentData()
        cur = self._pages[target]
        mode = self.cmb_mode.currentData()
        n_sel = self.cmb_n.currentData() or 2
        self.lbl_spec_err.setText('')
        if rng == 'all':
            idx = list(range(n))
        elif rng == 'range':
            a, b = self.sp_from.value() - 1, self.sp_to.value()
            if a >= b:
                raise ValueError('시작 페이지가 끝 페이지보다 큽니다.')
            idx = list(range(a, b))
        elif rng == 'spec':
            try:
                idx = parse_pages(self.ed_spec.text(), n)
            except PageSpecError as e:
                self.lbl_spec_err.setText(str(e))
                raise ValueError(str(e))
        else:
            idx = list(range(cur, min(cur + (n_sel if mode == 'nup' else 1), n)))
        allinfos = src.infos()
        infos = [allinfos[i] for i in idx]
        self._n_in = (len(infos),)
        self._src_wh = (infos[0].width, infos[0].height) if infos else None
        sheet = self.cmb_sheet.currentText()
        if mode == 'split':
            plan = build_plan('split', infos, sheet=sheet, n=n_sel, margins=margins,
                              overlap_mm=self.sp_overlap.value(), marks=self.chk_marks.isChecked(), src_id=target)
        elif mode == 'nup':
            plan = build_plan('nup', infos, sheet=sheet, n=n_sel, margins=margins, src_id=target,
                              gutter_mm=self.sp_gutter.value(), order=self.cmb_order.currentData(),
                              border=self.chk_border.isChecked(), numbers=self.chk_numbers.isChecked())
        elif mode == 'booklet':
            plan = build_plan('booklet', infos, sheet=sheet, margins=margins, binding=self.cmb_bind.currentData(),
                              src_id=target)
        elif mode == 'long':
            plan = build_plan('long', infos, sheet=sheet, margins=margins, overlap_mm=self.sp_overlap.value(),
                              marks=self.chk_marks.isChecked(), src_id=target)
        elif mode == 'region':
            if self.region is None:
                raise ValueError('영역을 지정하세요. (미리보기에서 드래그)')
            plan = build_plan('region', infos, sheet=sheet, margins=margins, regions=self.region,
                              fit=self.cmb_fit.currentData(), scale=self.sp_scale.value() / 100.0, src_id=target)
        elif mode == 'trim':
            plan = build_plan('region', infos, sheet=sheet, margins=margins, fit='fit', src_id=target,
                              regions=self._trim_regions(target, [i.index for i in infos]))
        else:
            plan = build_plan('fit', infos, sheet=sheet, margins=margins, src_id=target)
        return plan, {target: src}

    def refresh(self):
        try:
            self._plan, self._plan_src = self._make_plan()
            self._plan_id += 1
            self._latest[0] = self._plan_id
            self._outstanding.clear()
            self._cache.clear()
            n_out = len(self._plan.sheets)
            info = f'출력 {n_out}페이지 · 용지 {n_out}장(단면) / {(n_out + 1) // 2}장(양면)'
            ms = self._plan.meta.get('min_scale')
            if ms is not None and ms < 0.3 and self.cmb_mode.currentData() == 'nup' and self._target() not in PAIR_TARGETS:
                info += f' · 배율 {ms * 100:.0f}% — 글씨가 작아 읽기 어려울 수 있습니다'
            self.lbl_info.setText(info)
            self._update_result()
            self._k = max(0, min(self._k, len(self._plan.sheets) - 1))
            self._rebuild_thumbs()
            self._show()
        except Exception as e:
            self._plan = None
            self._latest[0] = -1
            self._outstanding.clear()
            self.thumbs.clear(); self._thumb_queue.clear()
            self.view.clear(); self.lbl_nav.setText(''); self.lbl_render.setText(''); self.lbl_info.setText(f'오류: {e}')
            self.lbl_result.setText('설정을 확인하세요: ' + str(e))
        ok = self._plan is not None and len(self._plan.sheets) > 0
        self.btn_print.setEnabled(ok); self.btn_save.setEnabled(ok)

    def _go(self, d):
        if self._plan:
            self._k = max(0, min(len(self._plan.sheets) - 1, self._k + d)); self._show()

    def _dpi_for(self, sh):
        vp = self.scroll.viewport()
        w_px, h_px = max(200, vp.width() - 20), max(200, vp.height() - 20)
        if self._zoom == 'width':
            d = 72 * w_px / sh.width
        elif self._zoom == 'page':
            d = 72 * min(w_px / sh.width, h_px / sh.height)
        else:
            d = 72 * self._zoom
        return int(round(max(30, min(300, d))))

    def _set_zoom(self, mode=None, factor=None):
        if mode:
            self._zoom = mode
        elif factor and self._plan:
            cur = self._dpi_for(self._plan.sheets[self._k]) / 72.0
            self._zoom = max(0.2, min(4.0, cur * factor))
        if self._plan:
            self._show()

    def _show(self):
        """현재 시트 표시. 캐시에 없으면 렌더 스레드에 요청하고(UI는 멈추지 않음) 결과가 오면 갱신한다."""
        sh = self._plan.sheets[self._k]
        dpi = self._dpi_for(sh)
        self.lbl_nav.setText(f'{self._k + 1} / {len(self._plan.sheets)}')
        self.thumbs.blockSignals(True); self.thumbs.setCurrentRow(self._k); self.thumbs.blockSignals(False)
        pm = self._cache.get((self._plan_id, self._k, dpi))
        if pm is not None:
            self.view.setPixmap(pm)
            return
        self._send(self._k, dpi)
        # 현재 장을 가장 앞에 두기 위해 썸네일 큐를 현재 위치 기준으로 재정렬
        if self._thumb_queue:
            self._thumb_queue = deque(sorted(self._thumb_queue, key=lambda i: abs(i - self._k)))

    # ── 출력 ──
    def _full_pdf(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            plan, srcs = self._make_plan()
            return build_pdf(plan, srcs)
        finally:
            QApplication.restoreOverrideCursor()

    def _start_output(self, on_built, label):
        """백그라운드로 출력 PDF 생성. 완료되면 on_built(bytes). 진행 중에는 버튼을 잠근다."""
        if self._worker is not None:
            return
        if self._timer.isActive():            # 미리보기에 아직 반영되지 않은 변경이 있으면 먼저 확정
            self._timer.stop()
            self.refresh()
        plan = self._plan                     # 화면에 표시된 계획 그대로 출력(미리보기=출력)
        if plan is None or not plan.sheets:
            QMessageBox.warning(self, label, self.lbl_info.text() or '출력할 내용이 없습니다.')
            return
        self._set_busy(True)
        w = _BuildWorker(plan, self._data, self)
        self._worker = w

        def finish():
            self._worker = None
            self._set_busy(False)
            w.deleteLater()

        def ok(data):
            if self._released:
                return
            finish()
            on_built(data)

        def bad(msg):
            if self._released:
                return
            finish()
            QMessageBox.warning(self, label, msg)

        w.built.connect(ok)
        w.failed.connect(bad)
        w.start()

    def _set_busy(self, busy):
        for b in (self.btn_save, self.btn_print):
            b.setEnabled(not busy)
        # PyMuPDF는 스레드 동시 사용이 안전하지 않으므로 생성 중에는 설정·미리보기 조작을 잠근다.
        self._panel_scroll.setEnabled(not busy)
        self.tabs.setEnabled(not busy)
        self.thumbs.setEnabled(not busy)
        for b in (self.btn_prev, self.btn_next, self.btn_zoom_in, self.btn_zoom_out,
                  self.btn_fit_width, self.btn_fit_page):
            b.setEnabled(not busy)
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            self._info_before = self.lbl_info.text()
            self.lbl_info.setText('PDF 생성 중…')
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            self.lbl_info.setText(self._info_before)
            QApplication.restoreOverrideCursor()

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, '출력 PDF 저장', 'print_output.pdf', 'PDF (*.pdf)')
        if not path:
            return

        def write(data):
            try:
                with open(path, 'wb') as f:
                    f.write(data)
            except Exception as e:
                QMessageBox.warning(self, '저장 실패', str(e))
        self._start_output(write, '저장 실패')

    def print_pdf(self):
        from app.common.print_output import print_pdf_bytes

        def go(data):
            if print_pdf_bytes(data, self):
                self.accept()  # 취소하면 페이지 유지, 완료 시 복귀 (뷰어 상태는 그대로)
        self._start_output(go, '인쇄 실패')


SmartPrintPage = SmartPrintDialog

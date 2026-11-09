"""공통 스마트 인쇄 대화상자.

PDF 보기(단일 문서)와 두 PDF 동시 보기(좌/우)에서 같은 대화상자를 호출한다.
엔진(app.print_engine)과 정렬 엔진(stream)을 그대로 재사용하고, 미리보기는 항상
실제 출력과 같은 build_pdf 결과(시트 단위)를 래스터화한다.
"""
import pymupdf
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from app.print_engine import Margins, SourceDoc, build_pdf, build_plan, mm
from app.print_engine.stream import StreamLayout, plan_side_by_side
from app.print_engine.stream import StreamSide
from app.shell.alignment_dialog import AlignSide, AlignmentDialog


class PrintSource:
    def __init__(self, title, data, modified=False):
        self.title, self.data, self.modified = title, data, modified


def print_source_from_doc(doc):
    """뷰어 PdfDocument → PrintSource. 미저장 변경이 있으면 현재 메모리 상태(bytes)를 사용."""
    if getattr(doc, 'modified', False):
        try:
            return PrintSource(doc.title, doc._doc.tobytes(), modified=True)
        except Exception:
            pass
    return PrintSource(doc.title, doc.path)


def start_from_canvas(canvas):
    """뷰어 캔버스의 현재 스크롤 위치 → (시작 페이지, 페이지 내 y pt)."""
    pos, _ = canvas.position()
    page = max(0, min(int(pos), canvas.page_count() - 1))
    h = canvas.doc.page_sizes[page][1]
    return page, max(0.0, min(h, (pos - page) * h))


def open_print_dialog(parent, left_canvas, right_canvas=None):
    """공통 진입점. 캔버스에 열린 문서를 그대로 전달한다(재선택·재로딩 없음)."""
    docs = [c.doc if c is not None else None for c in (left_canvas, right_canvas)]
    if docs[0] is None and docs[1] is not None:  # 왼쪽이 비어 있으면 오른쪽만 단일로
        left_canvas, right_canvas, docs = right_canvas, None, [docs[1], None]
    if docs[0] is None:
        return None
    try:
        lp, ly = start_from_canvas(left_canvas)
        l = print_source_from_doc(docs[0])
        if docs[1] is not None:
            rp, ry = start_from_canvas(right_canvas)
            dlg = SmartPrintDialog(l, print_source_from_doc(docs[1]), lp, rp, ly, ry, parent)
        else:
            dlg = SmartPrintDialog(l, None, lp, 0, ly, 0.0, parent)
    except Exception as e:
        QMessageBox.warning(parent, '인쇄', f'인쇄 창을 열 수 없습니다: {e}')
        return None
    dlg.exec()
    return dlg


SINGLE_MODES = [
    ('normal', '일반 인쇄 (용지에 맞춤)'),
    ('split2', '확대 2장 분할'),
    ('a3', 'A3 1장 확대'),
    ('nup', '2페이지 모아찍기'),
]
TARGETS = [('side', '나란히 출력'), ('L', '왼쪽만 출력'), ('R', '오른쪽만 출력')]


class SmartPrintDialog(QDialog):
    def __init__(self, left, right=None, left_page=0, right_page=0, left_y=0.0, right_y=0.0,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle('인쇄')
        self.resize(1180, 780)
        self._srcs = {}
        self._plan = None
        self._k = 0
        self._busy = False
        self.dual = right is not None
        self._pages = {'L': left_page, 'R': right_page}
        self._open_sources(left, right)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        # ── 왼쪽 65%: 미리보기 ──
        pv = QVBoxLayout()
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
        nav.addStretch(1); nav.addWidget(self.lbl_info)
        pv.addLayout(nav)
        self.view = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setWidget(self.view)
        pv.addWidget(self.scroll, 1)
        body.addLayout(pv, 65)

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
        self.cmb_sheet = QComboBox(); self.cmb_sheet.addItems(['A4', 'A3'])
        self.cmb_range = QComboBox()
        self.cmb_range.addItem('현재 페이지', 'cur'); self.cmb_range.addItem('전체 페이지', 'all')
        self.cmb_range.addItem('페이지 범위', 'range')
        self.sp_from = QSpinBox(); self.sp_to = QSpinBox()
        self.sp_margin = QDoubleSpinBox(); self.sp_margin.setRange(0, 30); self.sp_margin.setValue(5); self.sp_margin.setSuffix(' mm')
        self.sp_overlap = QDoubleSpinBox(); self.sp_overlap.setRange(0, 50); self.sp_overlap.setValue(10); self.sp_overlap.setSuffix(' mm')
        self.chk_marks = QCheckBox('이음선/번호 표시'); self.chk_marks.setChecked(True)
        if self.dual:
            form.addRow('출력 대상', self.cmb_target)
        form.addRow('출력 방식', self.cmb_mode)
        form.addRow('용지', self.cmb_sheet)
        form.addRow('페이지', self.cmb_range)
        rr = QHBoxLayout(); rr.addWidget(self.sp_from); rr.addWidget(QLabel('~')); rr.addWidget(self.sp_to)
        form.addRow('범위', rr)
        form.addRow('여백', self.sp_margin)
        form.addRow('분할 겹침', self.sp_overlap)
        form.addRow(self.chk_marks)
        pl.addWidget(form_box)

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
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setMinimumWidth(360)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        body.addWidget(sc, 35)

        # ── 하단 ──
        foot = QHBoxLayout(); foot.addStretch(1)
        self.btn_cancel = QPushButton('취소'); self.btn_save = QPushButton('PDF로 저장')
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
        for w in (self.sp_from, self.sp_to, self.sp_margin, self.sp_overlap):
            w.valueChanged.connect(self._schedule)
        self.chk_marks.toggled.connect(self._schedule)
        if any(s.modified for s in (left, right) if s):
            self.lbl_notice.setText('저장되지 않은 변경 사항을 포함한 현재 문서 상태로 출력합니다.')
        self._on_option()

    # ── 문서 ──
    def _open_sources(self, left, right):
        self._data, self._titles = {}, {}
        for key, s in (('L', left), ('R', right)):
            if s is None:
                continue
            self._data[key], self._titles[key] = s.data, s.title
            self._srcs[key] = SourceDoc(s.data, key, bake=True)

    def done(self, r):
        if self._srcs:
            self._timer.stop()
            for s in self._srcs.values():
                s.close()
            self._srcs = {}
        super().done(r)

    # ── 옵션 ──
    def _target(self):
        return self.cmb_target.currentData() if self.dual else 'L'

    def _on_option(self, *_):
        side = self._target() == 'side'
        self.cmb_mode.setEnabled(not side)
        self.cmb_range.setEnabled(not side)
        self.align_box.setVisible(self.dual and side)
        mode = self.cmb_mode.currentData()
        self.cmb_sheet.setEnabled(mode != 'a3' or side)
        self.sp_overlap.setEnabled(mode == 'split2' and not side)
        self.chk_marks.setEnabled(mode == 'split2' and not side)
        rng = self.cmb_range.currentData() == 'range'
        self.sp_from.setEnabled(rng and not side); self.sp_to.setEnabled(rng and not side)
        # 대상 문서가 바뀌면 페이지 범위 최대값 갱신
        key = self._target() if self._target() != 'side' else 'L'
        n = self._srcs[key].page_count
        for sp in (self.sp_from, self.sp_to):
            sp.blockSignals(True); sp.setMaximum(n); sp.blockSignals(False)
        self._schedule()

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
        sides = [AlignSide(self._titles[k], self._data[k], self._titles[k]) for k in ('L', 'R')]
        dlg = AlignmentDialog(sides, [self.align['L'], self.align['R']], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            (lp, ly), (rp, ry) = dlg.result_state()
            self.align = {'L': (lp, ly), 'R': (rp, ry)}
            self._update_align_summary()
            self.refresh()   # 즉시 미리보기 갱신 (원본은 다시 열지 않음)

    # ── 계획 ──
    def _make_plan(self):
        """(plan, sources) — 미리보기/저장/인쇄가 모두 이 결과를 사용."""
        m = mm(self.sp_margin.value())
        margins = Margins(m, m, m, m)
        target = self._target()
        if target == 'side':
            lay = StreamLayout(sheet=self.cmb_sheet.currentText(), landscape=True, margins=margins)
            plan = plan_side_by_side(self._stream_side('L'), self._stream_side('R'), lay)
            return plan, {'L': self._srcs['L'], 'R': self._srcs['R']}
        src = self._srcs[target]
        n = src.page_count
        rng = self.cmb_range.currentData()
        cur = self._pages[target]
        mode = self.cmb_mode.currentData()
        if rng == 'all':
            a, b = 0, n
        elif rng == 'range':
            a, b = self.sp_from.value() - 1, self.sp_to.value()
            if a >= b:
                raise ValueError('시작 페이지가 끝 페이지보다 큽니다.')
        else:
            a, b = cur, cur + (2 if mode == 'nup' else 1)
            b = min(b, n)
        infos = src.infos()[a:b]
        sheet = self.cmb_sheet.currentText()
        if mode == 'split2':
            plan = build_plan('split2', infos, sheet=sheet, margins=margins,
                              overlap_mm=self.sp_overlap.value(), marks=self.chk_marks.isChecked(), src_id=target)
        elif mode == 'nup':
            plan = build_plan('nup', infos, sheet=sheet, margins=margins, src_id=target)
        else:
            plan = build_plan('fit', infos, sheet='A3' if mode == 'a3' else sheet, margins=margins, src_id=target)
        return plan, {target: src}

    def refresh(self):
        try:
            self._plan, self._plan_src = self._make_plan()
            self.lbl_info.setText(f'출력 {len(self._plan.sheets)}장')
            self._k = max(0, min(self._k, len(self._plan.sheets) - 1))
            self._show()
        except Exception as e:
            self._plan = None
            self.view.clear(); self.lbl_nav.setText(''); self.lbl_info.setText(f'오류: {e}')
        ok = self._plan is not None and len(self._plan.sheets) > 0
        self.btn_print.setEnabled(ok); self.btn_save.setEnabled(ok)

    def _go(self, d):
        if self._plan:
            self._k = max(0, min(len(self._plan.sheets) - 1, self._k + d)); self._show()

    def _show(self):
        """실제 출력과 같은 경로(build_pdf)로 현재 시트만 생성해 표시."""
        data = build_pdf(self._plan, self._plan_src, [self._k])
        sh = self._plan.sheets[self._k]
        w_px = max(300, self.scroll.viewport().width() - 20)
        dpi = int(max(40, min(150, 72 * w_px / sh.width)))
        doc = pymupdf.open('pdf', data)
        pm = doc[0].get_pixmap(dpi=dpi)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format.Format_RGB888).copy()
        doc.close()
        self.view.setPixmap(QPixmap.fromImage(img))
        self.lbl_nav.setText(f'{self._k + 1} / {len(self._plan.sheets)}')

    # ── 출력 ──
    def _full_pdf(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            plan, srcs = self._make_plan()
            return build_pdf(plan, srcs)
        finally:
            QApplication.restoreOverrideCursor()

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, '출력 PDF 저장', 'print_output.pdf', 'PDF (*.pdf)')
        if not path:
            return
        try:
            data = self._full_pdf()
            with open(path, 'wb') as f:
                f.write(data)
        except Exception as e:
            QMessageBox.warning(self, '저장 실패', str(e))

    def print_pdf(self):
        from app.common.print_output import print_pdf_bytes
        try:
            data = self._full_pdf()
        except Exception as e:
            QMessageBox.warning(self, '인쇄 실패', str(e))
            return
        if print_pdf_bytes(data, self):
            self.accept()  # 취소하면 대화상자 유지, 완료 시 닫기 (뷰어 상태는 그대로)

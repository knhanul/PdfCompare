"""PDF bytes를 OS 표준 인쇄 대화상자(QPrintDialog)로 출력한다. 미리보기와 같은 bytes를 사용."""
import pymupdf
from PyQt6.QtCore import QRectF, QSizeF
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter


def print_pdf_bytes(data: bytes, parent=None) -> bool:
    """대화상자 취소 시 False. 페이지별 용지 크기/방향은 PDF 페이지 크기를 따른다."""
    doc = pymupdf.open("pdf", data)
    try:
        if len(doc) == 0:
            return False
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        _apply_page(printer, doc[0].rect)
        dlg = QPrintDialog(printer, parent)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return False
        painter = QPainter()
        if not painter.begin(printer):
            return False
        try:
            first, last = 0, len(doc) - 1
            if printer.printRange() == QPrinter.PrintRange.PageRange:
                first = max(0, printer.fromPage() - 1)
                last = min(last, printer.toPage() - 1)
            for n, i in enumerate(range(first, last + 1)):
                page = doc[i]
                QApplication.processEvents()  # 긴 문서에서도 UI 응답 유지
                if n > 0:
                    _apply_page(printer, page.rect)
                    printer.newPage()
                dpi = max(72, min(printer.resolution(), 300))
                pm = page.get_pixmap(dpi=dpi)
                img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                             QImage.Format.Format_RGB888).copy()
                target = printer.pageRect(QPrinter.Unit.DevicePixel)
                painter.drawImage(QRectF(0, 0, target.width(), target.height()), img)
        finally:
            painter.end()
        return True
    finally:
        doc.close()


def _apply_page(printer: QPrinter, rect):
    mm_w, mm_h = rect.width * 25.4 / 72, rect.height * 25.4 / 72
    portrait = mm_h >= mm_w
    short, long_ = (mm_w, mm_h) if portrait else (mm_h, mm_w)
    printer.setPageSize(QPageSize(QSizeF(short, long_), QPageSize.Unit.Millimeter))
    printer.setPageOrientation(QPageLayout.Orientation.Portrait if portrait
                               else QPageLayout.Orientation.Landscape)
    printer.setFullPage(True)  # 엔진이 이미 여백을 포함 → 하드웨어 여백으로 재축소/비율왜곡 방지

"""Quiet Brand line icons for the sidebar (no emoji), drawn with QPainter."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _doc(p):
    path = QPainterPath()
    path.moveTo(5, 2.5); path.lineTo(11.5, 2.5); path.lineTo(15, 6); path.lineTo(15, 17.5)
    path.lineTo(5, 17.5); path.closeSubpath()
    p.drawPath(path)
    p.drawPolyline([QPointF(11.5, 2.5), QPointF(11.5, 6), QPointF(15, 6)])


def _home(p):
    p.drawPolyline([QPointF(3, 9.5), QPointF(10, 3.5), QPointF(17, 9.5)])
    p.drawPolyline([QPointF(5, 8), QPointF(5, 16.5), QPointF(15, 16.5), QPointF(15, 8)])
    p.drawRect(QRectF(8.5, 11.5, 3, 5))


def _split(p):
    p.drawRoundedRect(QRectF(2.5, 4, 15, 12), 1.5, 1.5)
    p.drawLine(QPointF(10, 4), QPointF(10, 16))


def _compare(p):
    p.drawEllipse(QRectF(3, 3, 10, 10))
    p.drawLine(QPointF(11.5, 11.5), QPointF(17, 17))


def _header(p):
    _doc(p)
    p.drawLine(QPointF(7, 9), QPointF(13, 9))
    p.drawLine(QPointF(7, 14), QPointF(13, 14))


def _edit(p):
    path = QPainterPath()
    path.moveTo(4, 16); path.lineTo(4.8, 12.6); path.lineTo(13, 4.4); path.lineTo(15.6, 7)
    path.lineTo(7.4, 15.2); path.closeSubpath()
    p.drawPath(path)


def _create(p):
    _doc(p)
    p.drawLine(QPointF(10, 9), QPointF(10, 15))
    p.drawLine(QPointF(7, 12), QPointF(13, 12))


def _tag(p):
    path = QPainterPath()
    path.moveTo(3, 3); path.lineTo(10, 3); path.lineTo(17, 10); path.lineTo(10, 17)
    path.lineTo(3, 10); path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QRectF(6, 6, 2, 2))


def _form(p):
    p.drawRoundedRect(QRectF(4, 3.5, 12, 14), 1.5, 1.5)
    p.drawRect(QRectF(7.5, 2, 5, 3))
    for y in (9, 12, 15):
        p.drawLine(QPointF(7, y), QPointF(13, y))


def _settings(p):
    p.drawEllipse(QRectF(7.5, 7.5, 5, 5))
    import math
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(10 + 4.5 * math.cos(a), 10 + 4.5 * math.sin(a)),
                   QPointF(10 + 7 * math.cos(a), 10 + 7 * math.sin(a)))
    p.drawEllipse(QRectF(5.5, 5.5, 9, 9))


ICON_PAINTERS = {
    'home': _home, 'viewer': _doc, 'split': _split, 'settings': _settings,
    'pdf_compare': _compare, 'pdf_hf_compare': _header, 'pdf_editor': _edit,
    'pdf_create': _create, 'file_rename': _tag, 'pdf_form': _form, 'doc': _doc,
}


def line_icon(key, color, size=18, stroke=1.5):
    """Return a crisp line icon; unknown keys fall back to a document."""
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * scale / 20.0, size * scale / 20.0)
    pen = QPen(QColor(color), stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    ICON_PAINTERS.get(key, _doc)(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def brand_mark(color='#A44735', size=28):
    """Rounded terracotta mark with a white line document icon."""
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(scale, scale)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0, 0, size, size), 7, 7)
    p.translate(size * 0.2, size * 0.2)
    p.scale(size * 0.6 / 20.0, size * 0.6 / 20.0)
    pen = QPen(QColor('#FFFFFF'), 1.8)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _doc(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm

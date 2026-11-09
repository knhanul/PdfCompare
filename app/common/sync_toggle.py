"""토글 스위치 형태의 체크박스 (전체비교 '동시 스크롤', 두 PDF 동시보기 동기화에서 공용)."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton

from app.common.styles import COLOR_PRIMARY
from app.services import app_settings
from app.shell.theme import THEMES, theme_tokens


class SyncScrollToggle(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('QCheckBox::indicator { width: 36px; height: 20px; border: none; background: transparent; image: none; }')

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        track = QRectF(self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        painter.setPen(Qt.PenStyle.NoPen)
        theme_id = app_settings.get('ui/theme')
        checked_color = COLOR_PRIMARY if theme_id not in THEMES or theme_id == 'default' else theme_tokens(theme_id)['accent']
        painter.setBrush(QColor(checked_color if self.isChecked() else '#A0A0A0'))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        diameter = track.height() - 4
        x = track.right() - diameter - 2 if self.isChecked() else track.left() + 2
        painter.setBrush(QColor('white'))
        painter.drawEllipse(QRectF(x, track.top() + 2, diameter, diameter))
        painter.end()

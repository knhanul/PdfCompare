"""발표 화면 오버레이: 하단 플로팅 도구 모음, 쪽수 표시, 안내 토스트, 검은 화면 막."""
from PyQt6.QtCore import QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QToolButton,
                             QWidget)

TOOLBAR_QSS = """
QFrame#presToolbar { background: rgba(28, 28, 32, 205); border: 1px solid rgba(255,255,255,40);
                     border-radius: 14px; }
QToolButton { color: #F2EFEC; background: transparent; border: 1px solid transparent;
              border-radius: 8px; padding: 4px 6px; font-size: 12px; }
QToolButton:hover { background: rgba(255,255,255,30); }
QToolButton:checked { background: rgba(164,71,53,200); border-color: rgba(255,255,255,70); }
QToolButton:disabled { color: rgba(242,239,236,90); }
QToolButton::menu-indicator { image: none; width: 0px; }
QLabel#presSep { background: rgba(255,255,255,45); min-width: 1px; max-width: 1px; }
QLabel { color: #F2EFEC; font-size: 12px; }
QMenu { background: #26262A; color: #F2EFEC; border: 1px solid #44444A; }
QMenu::item:selected { background: #A44735; }
QMenu::separator { height: 1px; background: #44444A; margin: 4px 8px; }
"""


class FloatingToolbar(QFrame):
    """마우스가 올라가 있거나 메뉴가 열려 있는 동안은 숨기지 않는다."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('presToolbar')
        self.setStyleSheet(TOOLBAR_QSS)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(10, 6, 10, 6)
        self._lay.setSpacing(3)
        self.buttons = {}
        self._menus_open = 0

    def add_button(self, key, text, tip='', checkable=False, menu=None):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if menu is not None:
            b.setMenu(menu)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu.aboutToShow.connect(lambda: self._menu_state(1))
            menu.aboutToHide.connect(lambda: self._menu_state(-1))
        self._lay.addWidget(b)
        self.buttons[key] = b
        return b

    def add_label(self, key, text=''):
        lb = QLabel(text)
        lb.setMinimumWidth(46)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lay.addWidget(lb)
        self.buttons[key] = lb
        return lb

    def add_separator(self):
        sep = QLabel()
        sep.setObjectName('presSep')
        sep.setFixedHeight(22)
        self._lay.addSpacing(3)
        self._lay.addWidget(sep)
        self._lay.addSpacing(3)

    def _menu_state(self, d):
        self._menus_open = max(0, self._menus_open + d)

    def keep_visible(self):
        return self._menus_open > 0 or self.underMouse()

    def place(self):
        """부모 하단 중앙에 배치(PDF 내용을 가리는 면적을 줄이도록 낮고 얇게)."""
        self.adjustSize()
        p = self.parentWidget()
        w = min(self.sizeHint().width(), p.width() - 24)
        self.setFixedWidth(w)
        self.move((p.width() - w) // 2, p.height() - self.height() - 18)


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet('background: rgba(28,28,32,220); color: #F2EFEC; border-radius: 10px;'
                           ' padding: 8px 16px; font-size: 14px;')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_text(self, text, ms=2200):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, 28)
        self.show()
        self.raise_()
        self._timer.start(ms)


class PageBadge(QLabel):
    """현재 페이지 / 전체 페이지를 우하단에 간결하게."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet('color: rgba(242,239,236,170); background: rgba(20,20,22,120);'
                           ' border-radius: 8px; padding: 3px 10px; font-size: 12px;')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_text(self, text):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move(p.width() - self.width() - 14, p.height() - self.height() - 10)
        self.raise_()


class Curtain(QWidget):
    """B 키 검은 화면. 첫 해제 입력은 여기서만 소비되어 페이지가 넘어가지 않는다."""

    def __init__(self, parent, on_release):
        super().__init__(parent)
        self._on_release = on_release
        self.setStyleSheet('background: black;')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

    def mousePressEvent(self, event):
        event.accept()
        self._on_release()

    def wheelEvent(self, event):
        event.accept()

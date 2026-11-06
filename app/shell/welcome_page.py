"""Start screen shown immediately on launch (no PDF / tool imports).

Shortcuts intentionally exclude 「PDF 입력폼 관리」; that tool is reachable only from the sidebar menu.
"""
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout, QWidget)

# (action key, title, description) — no pdf_form here on purpose
WELCOME_SHORTCUTS = [
    ('split_view', '두 PDF 동시 보기', '두 문서를 나란히 열고 함께 스크롤'),
    ('pdf_compare', '영역지정비교', '지정한 영역의 글자를 비교'),
    ('pdf_hf_compare', '전체비교', '페이지 전체를 비교'),
    ('pdf_editor', 'PDF 편집', '분할·병합·페이지 편집'),
    ('pdf_create', 'PDF 생성', '문서·이미지를 PDF로 변환'),
]


class WelcomePage(QWidget):
    open_requested = pyqtSignal()
    open_path = pyqtSignal(str)
    action_requested = pyqtSignal(str)
    restore_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('welcomePage')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        center = QWidget()
        center.setMaximumWidth(760)
        col = QVBoxLayout(center)
        col.setSpacing(16)

        title = QLabel('PDF를 빠르게 열고, 필요한 작업을 한곳에서')
        title.setObjectName('welcomeTitle')
        col.addWidget(title)

        drop = QFrame()
        drop.setObjectName('dropZone')
        dl = QVBoxLayout(drop)
        dl.setContentsMargins(24, 22, 24, 22)
        hint = QLabel('여기에 PDF를 끌어다 놓거나')
        hint.setObjectName('mutedLabel')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        row.addStretch()
        btn = QPushButton('PDF 열기  (Ctrl+O)')
        btn.setObjectName('primaryBtn')
        btn.clicked.connect(self.open_requested.emit)
        row.addWidget(btn)
        self.restore_btn = QPushButton('지난 작업 복원')
        self.restore_btn.setObjectName('viewerToolBtn')
        self.restore_btn.clicked.connect(self.restore_requested.emit)
        self.restore_btn.hide()
        row.addWidget(self.restore_btn)
        row.addStretch()
        dl.addWidget(hint)
        dl.addLayout(row)
        col.addWidget(drop)

        sc_label = QLabel('주요 작업')
        sc_label.setObjectName('sectionLabel')
        col.addWidget(sc_label)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.shortcut_keys = []
        for i, (key, name, desc) in enumerate(WELCOME_SHORTCUTS):
            b = QPushButton(f'{name}\n{desc}')
            b.setObjectName('shortcutTile')
            b.clicked.connect(lambda _=False, k=key: self.action_requested.emit(k))
            grid.addWidget(b, i // 3, i % 3)
            self.shortcut_keys.append(key)
        col.addLayout(grid)

        rl = QLabel('최근 문서')
        rl.setObjectName('sectionLabel')
        col.addWidget(rl)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName('recentList')
        self.recent_list.setMaximumHeight(220)
        self.recent_list.itemActivated.connect(lambda it: self.open_path.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.recent_list.itemClicked.connect(lambda it: self.open_path.emit(it.data(Qt.ItemDataRole.UserRole)))
        col.addWidget(self.recent_list)

        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(center, 4)
        h.addStretch()
        outer.addLayout(h)
        outer.addStretch(2)

    def set_recent(self, paths):
        self.recent_list.clear()
        for p in paths:
            it = QListWidgetItem(f'{os.path.basename(p)}    —  {os.path.dirname(p)}')
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            if not os.path.isfile(p):
                it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(it)
        if not paths:
            it = QListWidgetItem('최근에 연 문서가 없습니다')
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(it)

    def set_restore_available(self, available):
        self.restore_btn.setVisible(bool(available))

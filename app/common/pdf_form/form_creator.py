from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.common.pdf_form.field_models import (
    ALIGN_LABELS,
    CREATABLE_FIELD_TYPES,
    FormError,
    WidgetInstance,
)
from app.common.pdf_form.form_service import FormDocumentSession


def _rgb_tuple_to_hex(rgb: tuple[float, float, float] | None, fallback: str = "#1A1A1A") -> str:
    if not rgb or len(rgb) != 3:
        return fallback
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _hex_to_rgb_tuple(text: str, fallback: tuple[float, float, float] = (0.1, 0.1, 0.1)) -> tuple[float, float, float]:
    col = QColor((text or "").strip())
    if not col.isValid():
        return fallback
    return (col.redF(), col.greenF(), col.blueF())


class FormCreatorPanel(QWidget):
    """탭 1 — 양식 만들기 오른쪽 패널 (도구 선택, 생성된 필드 목록, 필드 속성 편집)."""

    tool_mode_changed = pyqtSignal(object)     # None (select mode) or field_type str
    widget_focus_requested = pyqtSignal(int)   # xref
    document_mutated = pyqtSignal(int)         # selected xref after mutation
    save_form_requested = pyqtSignal()
    help_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: FormDocumentSession | None = None
        self.current_xref: int = 0
        self._loading_props = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(8)

        # 상단 안내 + 도움말 링크
        top_bar = QHBoxLayout()
        guide_lbl = QLabel("<b>PDF에서 입력받을 위치를 마우스로 지정하세요.</b>")
        guide_lbl.setStyleSheet("color: #2C2A29; font-size: 13px;")
        self.btn_help = QPushButton("이 기능은 무엇인가요?")
        self.btn_help.setObjectName("secondaryBtn")
        self.btn_help.clicked.connect(self.help_requested.emit)
        top_bar.addWidget(guide_lbl, 1)
        top_bar.addWidget(self.btn_help)
        outer.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 2, 4, 2)
        layout.setSpacing(10)

        # 1. 입력란 추가 도구 그룹
        tools_group = QGroupBox("1. 입력란 추가 도구")
        tools_grid = QGridLayout(tools_group)
        tools_grid.setSpacing(6)
        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.setExclusive(True)
        self.tool_buttons: dict[str | None, QPushButton] = {}

        btn_select = QPushButton("선택 / 위치 이동")
        btn_select.setCheckable(True)
        btn_select.setChecked(True)
        btn_select.setToolTip("이미 만든 입력란을 클릭해 선택하거나 이동·크기 조정합니다.")
        btn_select.clicked.connect(lambda: self._select_tool(None))
        self.tool_btn_group.addButton(btn_select)
        self.tool_buttons[None] = btn_select
        tools_grid.addWidget(btn_select, 0, 0, 1, 2)

        for idx, (ftype, title, desc) in enumerate(CREATABLE_FIELD_TYPES):
            btn = QPushButton(f"+ {title}")
            btn.setCheckable(True)
            btn.setToolTip(f"{title}: {desc}")
            btn.clicked.connect(lambda _checked=False, t=ftype: self._select_tool(t))
            self.tool_btn_group.addButton(btn)
            self.tool_buttons[ftype] = btn
            row = (idx // 2) + 1
            col = idx % 2
            tools_grid.addWidget(btn, row, col)

        self.lbl_tool_hint = QLabel("현재 모드: <b>선택 / 위치 이동</b> — 입력란을 클릭해 속성을 편집합니다.")
        self.lbl_tool_hint.setWordWrap(True)
        self.lbl_tool_hint.setStyleSheet("color: #55504D; font-size: 12px; padding: 2px;")
        tools_grid.addWidget(self.lbl_tool_hint, 5, 0, 1, 2)
        layout.addWidget(tools_group)

        # 2. 생성된 입력란 목록
        list_group = QGroupBox("2. 생성된 입력란 목록")
        list_layout = QVBoxLayout(list_group)
        list_layout.setSpacing(6)

        self.field_table = QTableWidget(0, 4)
        self.field_table.setHorizontalHeaderLabels(["표시 이름", "유형", "페이지", "필수"])
        self.field_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # ... (truncated for brevity in this example, but in real call include full)

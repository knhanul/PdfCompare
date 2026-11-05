from dataclasses import dataclass, field
from datetime import datetime
import re


class FormError(ValueError):
    """사용자 안내용 PDF 양식 처리 예외."""


FIELD_TYPE_LABELS = {
    "text": "한 줄 입력란",
    "multiline": "여러 줄 입력란",
    "date": "날짜 입력란",
    "checkbox": "체크박스",
    "radio": "라디오 버튼",
    "combobox": "드롭다운 목록",
    "listbox": "목록 상자",
    "signature": "전자서명",
    "button": "버튼",
}

CREATABLE_FIELD_TYPES = (
    ("text", "한 줄 입력란", "이름, 연락처, 주소 등의 문자열 입력"),
    ("multiline", "여러 줄 입력란", "의견, 비고, 상세 내용"),
    ("date", "날짜 입력란", "YYYY-MM-DD 형식의 날짜 입력"),
    ("checkbox", "체크박스", "동의 여부, 항목 선택"),
    ("radio", "라디오 버튼", "여러 선택지 중 하나 선택"),
    ("combobox", "드롭다운 목록", "사전에 정한 항목 중 선택"),
    ("listbox", "목록 상자", "목록 형태로 선택"),
)

FIELD_TYPE_PREFIXES = {
    "text": "text",
    "multiline": "multiline",
    "date": "date",
    "checkbox": "checkbox",
    "radio": "radio",
    "combobox": "dropdown",
    "listbox": "listbox",
}

ALIGN_LABELS = {
    0: "왼쪽 정렬",
    1: "가운데 정렬",
    2: "오른쪽 정렬",
}

_DATE_PATTERNS = (
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("%Y.%m.%d", re.compile(r"^\d{4}\.\d{2}\.\d{2}$")),
    ("%Y/%m/%d", re.compile(r"^\d{4}/\d{2}/\d{2}$")),
    ("%Y%m%d", re.compile(r"^\d{8}$")),
)


def validate_date_string(value: str) -> tuple[bool, str]:
    """날짜 문자열이 유효한지 검증하고 정규화된 YYYY-MM-DD 문자열을 반환한다."""
    text = (value or "").strip()
    if not text:
        return True, ""
    for fmt, pattern in _DATE_PATTERNS:
        if pattern.match(text):
            try:
                parsed = datetime.strptime(text, fmt)
                return True, parsed.strftime("%Y-%m-%d")
            except ValueError:
                return False, "존재하지 않는 날짜입니다. 예: 2026-05-01"
    return False, "날짜 형식이 올바르지 않습니다. 예: 2026-05-01"


def normalize_bool_value(raw, on_state: str = "Yes") -> tuple[bool, bool]:
    """외부 입력값을 체크박스용 bool로 변환한다. (성공 여부, bool 값) 반환."""
    if isinstance(raw, bool):
        return True, raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return True, bool(raw)
    text = str(raw if raw is not None else "").strip()
    lower = text.lower()
    on_lower = (on_state or "Yes").lower()
    if lower in ("1", "true", "yes", "y", "on", "checked", "체크", "선택", "동의", "예", on_lower):
        return True, True
    if lower in ("0", "false", "no", "n", "off", "unchecked", "", "미선택", "해제", "비동의", "아니오"):
        return True, False
    return False, False


@dataclass
class WidgetInstance:
    xref: int
    page_index: int
    rect: tuple[float, float, float, float]
    field_name: str
    field_label: str
    field_type: str
    value: object
    default_value: str = ""
    required: bool = False
    read_only: bool = False
    no_export: bool = False
    is_password: bool = False
    max_len: int = 0
    choices: list[str] = field(default_factory=list)
    on_state: str = "Yes"
    button_states: list[str] = field(default_factory=list)
    button_caption: str = ""
    font_size: float = 11.0
    text_color: tuple[float, float, float] = (0.1, 0.1, 0.1)
    fill_color: tuple[float, float, float] | None = None
    border_color: tuple[float, float, float] | None = None
    border_width: float = 0.0
    align: int = 0
    is_signed: bool | None = None

    @property
    def display_name(self) -> str:
        return (self.field_label or "").strip() or self.field_name

    @property
    def type_label(self) -> str:
        return FIELD_TYPE_LABELS.get(self.field_type, self.field_type)

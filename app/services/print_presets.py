"""스마트 인쇄 프리셋. 내장 + 사용자 정의(QSettings JSON).

프리셋에는 출력 방식/용지/배율/여백/레이아웃만 저장한다. PDF 경로, 영역 좌표, 시작 위치,
페이지 범위처럼 문서별 값은 저장하지 않는다(다른 문서에 무조건 적용되는 것을 방지).
"""
import json

from PyQt6.QtCore import QSettings

# 프리셋에 허용되는 키 (문서별 값 제외)
ALLOWED = ('target', 'mode', 'sheet', 'n', 'margin', 'overlap', 'marks', 'order', 'gutter',
           'border', 'numbers', 'fit', 'scale', 'bind')

BUILTIN = {
    '일반 A4 출력': {'target': 'L', 'mode': 'normal', 'sheet': 'A4'},
    'A4 → A3 확대': {'target': 'L', 'mode': 'a3'},
    'A4 2장 확대분할': {'target': 'L', 'mode': 'split', 'sheet': 'A4', 'n': 2},
    'A4 4장 확대분할': {'target': 'L', 'mode': 'split', 'sheet': 'A4', 'n': 4},
    'A4 2페이지 모아찍기': {'target': 'L', 'mode': 'nup', 'sheet': 'A4', 'n': 2},
    'A4 4페이지 모아찍기': {'target': 'L', 'mode': 'nup', 'sheet': 'A4', 'n': 4},
    'A3 나란히 비교 출력': {'target': 'side', 'sheet': 'A3'},
}

_KEY = 'print/presets'


def _store():
    return QSettings('PdfCompare', 'Workspace')


def clean(data):
    return {k: v for k, v in (data or {}).items() if k in ALLOWED}


def load_user():
    try:
        raw = _store().value(_KEY, '{}')
        d = json.loads(raw) if isinstance(raw, str) else {}
        return {str(n): clean(v) for n, v in d.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _save_user(d):
    _store().setValue(_KEY, json.dumps(d, ensure_ascii=False))


def names():
    return list(BUILTIN) + [n for n in load_user() if n not in BUILTIN]


def is_builtin(name):
    return name in BUILTIN


def get(name):
    return dict(BUILTIN[name]) if name in BUILTIN else dict(load_user().get(name, {}))


def save(name, data):
    name = (name or '').strip()
    if not name:
        raise ValueError('프리셋 이름을 입력하세요.')
    if name in BUILTIN:
        raise ValueError('기본 프리셋 이름은 사용할 수 없습니다.')
    d = load_user()
    d[name] = clean(data)
    _save_user(d)


def delete(name):
    if name in BUILTIN:
        raise ValueError('기본 프리셋은 삭제할 수 없습니다.')
    d = load_user()
    d.pop(name, None)
    _save_user(d)

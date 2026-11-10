"""문서 기준점 기반 상대 스크롤 동기화용 좌표 유틸리티 (Qt 비의존 부분 + 캔버스 어댑터).

좌표계: 캔버스의 `position()`과 같은 '위치 = 페이지 인덱스 + 페이지 내 비율(0~1)'.
확대율/창 크기와 무관하며, pt 단위 연속 좌표 D = (앞 페이지 높이 누적) + 비율 × 해당 페이지 높이 로 바꿔 쓴다.
두 문서의 이동량은 문서 좌표(pt)가 같도록 맞춘다(확대율이 달라도 같은 내용 길이만큼 이동).
전체비교 정렬 등에서 재사용할 수 있도록 인쇄/뷰어 UI에 의존하지 않는다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScrollAnchor:
    document_id: str
    page_index: int
    y_coordinate_pt: float      # 페이지 내부 Y (pt, 위 기준)
    viewport_ratio: float = 0.5  # 이 위치가 화면 세로에서 차지하던 비율 (0=위, 0.5=중앙)


def total_pt(page_sizes):
    return float(sum(h for _, h in page_sizes))


def pos_to_coord(page_sizes, pos):
    """위치(페이지+비율) → 연속 문서 좌표 D(pt)."""
    n = len(page_sizes)
    if n == 0:
        return 0.0
    pos = max(0.0, min(float(pos), float(n)))
    i = min(int(pos), n - 1)
    frac = pos - i
    return sum(h for _, h in page_sizes[:i]) + frac * page_sizes[i][1]


def coord_to_pos(page_sizes, d):
    """연속 문서 좌표 D(pt) → 위치. 문서 범위로 제한."""
    n = len(page_sizes)
    if n == 0:
        return 0.0
    d = max(0.0, min(float(d), total_pt(page_sizes)))
    acc = 0.0
    for i, (_, h) in enumerate(page_sizes):
        if d <= acc + h or i == n - 1:
            return i + (0.0 if h <= 0 else min(1.0, (d - acc) / h))
        acc += h
    return float(n)


def make_anchor(document_id, page_sizes, pos, ratio=0.5):
    n = len(page_sizes)
    i = max(0, min(int(pos), n - 1))
    frac = max(0.0, min(1.0, pos - i))
    return ScrollAnchor(document_id, i, frac * page_sizes[i][1], ratio)


def anchor_coord(page_sizes, a: ScrollAnchor):
    i = max(0, min(a.page_index, len(page_sizes) - 1))
    return sum(h for _, h in page_sizes[:i]) + max(0.0, min(a.y_coordinate_pt, page_sizes[i][1]))


def map_position(src_sizes, src_anchor, dst_sizes, dst_anchor, src_pos):
    """src 위치 → 같은 이동량(pt)만큼 떨어진 dst 위치. 상태 없이 앵커에서 계산하므로 오차가 누적되지 않는다."""
    delta = pos_to_coord(src_sizes, src_pos) - anchor_coord(src_sizes, src_anchor)
    return coord_to_pos(dst_sizes, anchor_coord(dst_sizes, dst_anchor) + delta)


def relation_offset(a_sizes, a_anchor, a_pos, b_sizes, b_anchor, b_pos):
    """두 화면이 앵커 관계와 얼마나 어긋났는지(pt). 0이면 일치."""
    return ((pos_to_coord(a_sizes, a_pos) - anchor_coord(a_sizes, a_anchor))
            - (pos_to_coord(b_sizes, b_pos) - anchor_coord(b_sizes, b_anchor)))


# ── 캔버스 어댑터 (PdfCanvas 의 내부 레이아웃을 읽기만 한다) ─────────────────────────
def capture_pos(canvas, ratio=0.5):
    """뷰포트 세로 ratio 지점의 위치(페이지+비율). 스크롤은 변경하지 않는다."""
    MARGIN, PAGE_GAP = canvas.margin, canvas.page_gap
    if not canvas.doc or not canvas._tops:
        return 0.0
    y = canvas.verticalScrollBar().value() + MARGIN + ratio * canvas.viewport().height()
    i = canvas._page_at(y)
    h = canvas.doc.page_sizes[i][1] * canvas._scale() + PAGE_GAP
    frac = (y - canvas._tops[i]) / h if h else 0.0
    return i + max(0.0, min(1.0, frac))


def apply_pos(canvas, pos, ratio=0.5):
    """capture_pos 의 역: ratio 지점이 pos 가 되도록 세로 스크롤. 범위는 스크롤바가 제한."""
    MARGIN, PAGE_GAP = canvas.margin, canvas.page_gap
    if not canvas.doc or not canvas._tops:
        return
    i = max(0, min(int(pos), len(canvas._tops) - 1))
    h = canvas.doc.page_sizes[i][1] * canvas._scale() + PAGE_GAP
    y = canvas._tops[i] + (pos - i) * h
    canvas.verticalScrollBar().setValue(int(round(y - MARGIN - ratio * canvas.viewport().height())))

"""여백 자동 감지 (파괴 없음: 클리핑 경계만 계산)."""
from __future__ import annotations
from .model import Box


def detect_content_box(page, dpi=36, threshold=245, pad_mm=2.0):
    """보이는 좌표(회전 적용) 기준 비백색 영역 Box. 렌더 기반이라 텍스트·이미지·도형·주석 모두 포함.
    배경색이 있는 페이지는 전체 페이지가 내용으로 판정될 수 있다(UI에서 사용자가 조정).
    내용이 전혀 없으면 None."""
    pix = page.get_pixmap(dpi=dpi, alpha=False, annots=True)
    w, h, n, st = pix.width, pix.height, pix.n, pix.stride
    data = pix.samples
    top = bottom = None
    left, right = w, -1
    for y in range(h):
        row = data[y * st:y * st + w * n]
        if min(row) >= threshold:
            continue
        if top is None:
            top = y
        bottom = y
        for x in range(w):
            if min(row[x * n:x * n + n]) < threshold:
                left = min(left, x)
                break
        for x in range(w - 1, -1, -1):
            if min(row[x * n:x * n + n]) < threshold:
                right = max(right, x)
                break
    if top is None:
        return None
    r = page.rect
    sx, sy = r.width / w, r.height / h
    pad = pad_mm * 72 / 25.4
    return Box(max(0.0, left * sx - pad), max(0.0, top * sy - pad),
               min(r.width, (right + 1) * sx + pad), min(r.height, (bottom + 1) * sy + pad))

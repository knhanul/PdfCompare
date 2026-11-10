"""발표모드 내비게이션 계산 (Qt 비의존, 단위 테스트 대상).

좌표계: 연속 문서 캔버스의 세로 픽셀 좌표.
  tops[i]    = 페이지 i 의 위쪽 y,   heights[i] = 페이지 i 의 높이(px),   vh = 뷰포트 높이(px)
  scroll     = 뷰포트 위쪽이 가리키는 y (페이지가 뷰포트보다 짧으면 가운데 정렬을 위해 음수가 될 수 있음)
이동 거리는 항상 '뷰포트 높이 × 비율' 이다(원본 PDF 페이지 높이가 아님).
"""
import bisect
import math

FIT_EPS = 2.0              # 이 px 이하의 차이는 '페이지가 뷰포트에 맞음'으로 본다
SECTION_RATIOS = (0.5, 0.75, 0.9)
DEFAULT_RATIO = 0.75
MAX_RENDER_PIXELS = 16_000_000   # 한 페이지 렌더링 상한(약 48MB RGB). 공용 캐시(256MB)에서 보이는 페이지+미리읽기가 서로 밀어내지 않게 함
ABS_MIN_ZOOM, ABS_MAX_ZOOM = 0.1, 6.0


def page_at(tops, y):
    """y 를 포함하는 페이지 인덱스(범위를 벗어나면 가장자리)."""
    if not tops:
        return 0
    return max(0, min(bisect.bisect_right(tops, y) - 1, len(tops) - 1))


def page_scroll(tops, heights, vh, i):
    """페이지 i 를 '보여주는' 스크롤: 큰 페이지는 위 맞춤, 작은 페이지는 가운데 정렬."""
    h = heights[i]
    if h <= vh + FIT_EPS:
        return tops[i] - (vh - h) / 2.0
    return float(tops[i])


def page_end_scroll(tops, heights, vh, i):
    """페이지 i 의 '마지막 구간' 스크롤: 큰 페이지는 아래 맞춤."""
    h = heights[i]
    if h <= vh + FIT_EPS:
        return tops[i] - (vh - h) / 2.0
    return tops[i] + h - vh


def current_page(tops, vh, scroll):
    return page_at(tops, scroll + vh / 2.0)


PAGE_PARTS = (2, 3, 4)
DEFAULT_PARTS = 3


def section_step(page_h, vh, value, basis='viewport'):
    """한 번에 이동할 px.
    basis='viewport': 화면 높이 x value(비율).
    basis='page'    : 페이지를 value 등분. 한 구간이 화면보다 크면 누락이 없도록 더 잘게 나눈다."""
    if basis == 'page':
        parts = max(int(value), math.ceil(page_h / max(vh, 1.0) - 1e-9), 1)
        return page_h / parts
    return vh * value


def next_target(tops, heights, vh, scroll, ratio=DEFAULT_RATIO, basis='viewport'):
    """'다음 구간'의 스크롤. 페이지 끝이면 다음 페이지 처음. 마지막 페이지 끝이면 그대로."""
    i = current_page(tops, vh, scroll)
    end = page_end_scroll(tops, heights, vh, i)
    start = page_scroll(tops, heights, vh, i)
    if scroll < start - FIT_EPS:
        return start                              # 페이지 위쪽이 아직 안 보이면 먼저 그 위치로 (누락 방지)
    if heights[i] > vh + FIT_EPS and scroll < end - FIT_EPS:
        return min(scroll + section_step(heights[i], vh, ratio, basis), end)     # 마지막 구간은 페이지 끝에 정확히 맞춰 누락 없음
    if heights[i] <= vh + FIT_EPS and scroll > start + FIT_EPS:
        return start                              # 짧은 페이지가 어긋나 있으면 먼저 정렬
    if i + 1 < len(tops):
        return page_scroll(tops, heights, vh, i + 1)
    return scroll


def prev_target(tops, heights, vh, scroll, ratio=DEFAULT_RATIO, basis='viewport'):
    """'이전 구간'의 스크롤. 페이지 시작이면 이전 페이지의 마지막 구간."""
    i = current_page(tops, vh, scroll)
    start = page_scroll(tops, heights, vh, i)
    if heights[i] > vh + FIT_EPS and scroll > tops[i] + FIT_EPS:
        return max(scroll - section_step(heights[i], vh, ratio, basis), float(tops[i]))
    if heights[i] <= vh + FIT_EPS and abs(scroll - start) > FIT_EPS:
        return start
    if i > 0:
        return page_end_scroll(tops, heights, vh, i - 1)
    return page_scroll(tops, heights, vh, 0)


def next_page_target(tops, heights, vh, scroll):
    i = current_page(tops, vh, scroll)
    return page_scroll(tops, heights, vh, min(i + 1, len(tops) - 1))


def prev_page_target(tops, heights, vh, scroll):
    i = current_page(tops, vh, scroll)
    return page_scroll(tops, heights, vh, max(i - 1, 0))


def page_top_target(tops, heights, vh, scroll):
    return page_scroll(tops, heights, vh, current_page(tops, vh, scroll))


def page_bottom_target(tops, heights, vh, scroll):
    return page_end_scroll(tops, heights, vh, current_page(tops, vh, scroll))


def sections_in_page(page_h_px, vh, ratio=DEFAULT_RATIO):
    """한 페이지를 처음부터 끝까지 구간 이동할 때의 화면 수(검증/표시용)."""
    if page_h_px <= vh + FIT_EPS:
        return 1
    return 1 + math.ceil((page_h_px - vh) / (vh * ratio) - 1e-9)


def max_zoom_for(page_sizes, dpr=1.0):
    """페이지 한 장 렌더링이 MAX_RENDER_PIXELS 를 넘지 않는 최대 배율(논리 zoom 기준)."""
    if not page_sizes:
        return ABS_MAX_ZOOM
    biggest = max(w * h for w, h in page_sizes) or 1.0
    px_per_zoom = (96.0 / 72.0) * max(dpr, 1.0)
    z = math.sqrt(MAX_RENDER_PIXELS / biggest) / px_per_zoom
    return max(0.25, min(ABS_MAX_ZOOM, z))


def recommend_view(page_sizes, screen_w, screen_h):
    """문서 방향·화면 비율로 추천 보기 방식. ('page'|'width', 방향)

    가로형(또는 화면보다 납작한 페이지가 다수)은 전체 페이지, 세로형은 너비 맞춤.
    혼합 방향은 다수결이며, 개별 페이지는 fit_for_page 로 따로 맞춘다.
    """
    if not page_sizes:
        return 'page', 'landscape'
    landscape = sum(1 for w, h in page_sizes if w >= h)
    portrait = len(page_sizes) - landscape
    if landscape == 0:
        return 'width', 'portrait'
    if portrait == 0:
        return 'page', 'landscape'
    return ('page', 'mixed') if landscape >= portrait else ('width', 'mixed')


def fit_for_page(page_w, page_h, screen_w, screen_h):
    """혼합 문서에서 페이지마다 적절한 맞춤: 가로형 페이지는 전체 페이지, 세로형 페이지는 너비 맞춤."""
    return 'page' if page_w >= page_h else 'width'


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def split_stretch(focus):
    """한쪽 집중 발표의 좌/우 폭 비율. focus: None(동일)|'left'|'right'."""
    return {'left': (3, 1), 'right': (1, 3)}.get(focus, (1, 1))

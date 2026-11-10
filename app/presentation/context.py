"""PresentationContext: 발표 시작 시점의 작업 화면 상태 스냅샷.

발표 창은 자체 PresentationCanvas 를 쓰므로 원래 작업 화면(캔버스)은 절대 변경되지 않는다.
context 는 (1) 발표 시작 위치 계산, (2) 종료 후 '원래 상태가 유지됐는지' 확인에 쓴다.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PaneSource:
    doc: object                      # PdfDocument (경로/페이지 크기만 사용 — 렌더링은 RenderService 가 담당)
    start_page: int = 0
    origin_position: tuple = (0.0, 0.0)   # 원래 캔버스 position() 스냅샷
    origin_zoom: float = 1.0
    origin_fit: Optional[str] = None
    origin_current_page: int = 0


@dataclass
class PresentationContext:
    panes: List[PaneSource] = field(default_factory=list)   # 1개(PDF 보기) 또는 2개(동시보기)
    sync: str = 'off'                # 'off' | 'normal' | 'anchor'  (동시보기 시작 시 상태)
    screen: object = None            # 대상 QScreen (None 이면 창이 있는 모니터)
    view_mode: Optional[str] = None  # None 이면 문서 방향으로 추천

    @property
    def dual(self):
        return len(self.panes) == 2


def _pane_from_canvas(canvas, from_start):
    cur = canvas.current_page()
    return PaneSource(doc=canvas.doc, start_page=0 if from_start else cur,
                      origin_position=canvas.position(), origin_zoom=canvas.zoom,
                      origin_fit=canvas.fit_mode, origin_current_page=cur)


def context_from_canvas(canvas, from_start=False, screen=None):
    if canvas is None or canvas.doc is None:
        return None
    return PresentationContext(panes=[_pane_from_canvas(canvas, from_start)], screen=screen)


def context_from_split(left_canvas, right_canvas, sync='normal', from_start=False, screen=None):
    panes = [_pane_from_canvas(c, from_start) for c in (left_canvas, right_canvas) if c.doc]
    if not panes:
        return None
    return PresentationContext(panes=panes, sync=sync if len(panes) == 2 else 'off', screen=screen)

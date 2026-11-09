"""동시보기 연속 스트림: 좌/우 PDF를 서로 다른 시작 위치에서 같은 기준선에 맞춰 나란히 출력.

스트림 좌표 u: 시트와 무관한 세로 거리(pt). 각 변(side)의 페이지 구간들이 u축에 빈틈없이 이어 붙고,
시트 띠(band)가 u축을 빈틈없이 덮으므로 페이지/시트 경계에서 내용이 누락되지 않는다.
전체비교에서 재사용 가능한 API: build_segments, src_to_out, out_to_src.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

from .model import Box, Margins, Mark, PageInfo, Placement, PrintPlan, Sheet
from .units import PT_PER_MM, mm, paper


@dataclass(frozen=True)
class StreamSide:
    source_id: str
    pages: list            # list[PageInfo]; pages[0] 이 시작 페이지
    start_y: float = 0.0   # 시작 페이지의 보이는 좌표 pt (기준선)
    lead: float = 0.0      # 기준선 위로 함께 출력할 원본 높이(pt)
    adjust_mm: float = 0.0  # + = 아래로
    trim_top: float = 0.0  # 2페이지부터 매 페이지 위에서 제외(머리말)
    trim_bottom: float = 0.0


@dataclass(frozen=True)
class StreamLayout:
    sheet: str = "A3"
    landscape: bool = True
    margins: Margins = Margins()
    gutter_mm: float = 6.0
    header_mm: float = 6.0
    common_scale: bool = True
    sheet_overlap_mm: float = 0.0
    draw_page_boundaries: bool = True


@dataclass(frozen=True)
class Segment:
    page: int
    src_y0: float
    src_y1: float
    u0: float

    def u1(self, scale): return self.u0 + scale * (self.src_y1 - self.src_y0)


def build_segments(side: StreamSide, scale: float, baseline_u: float):
    """baseline_u: 시작 기준선(원본 start_y)이 놓일 u. 미세조정 반영 후 값을 넘긴다."""
    segs = []
    u = None
    for n, info in enumerate(side.pages):
        if n == 0:
            y0 = max(side.start_y - side.lead, 0.0)
            u = baseline_u - scale * (side.start_y - y0)
        else:
            y0 = side.trim_top
        y1 = info.height - side.trim_bottom
        if y1 - y0 <= 1e-6:
            continue
        segs.append(Segment(info.index, y0, y1, u))
        u += scale * (y1 - y0)
    return segs


def _geometry(lay: StreamLayout):
    W, H = paper(lay.sheet, lay.landscape)
    m = lay.margins
    pw, ph = W - m.left - m.right, H - m.top - m.bottom
    g, header = mm(lay.gutter_mm), mm(lay.header_mm)
    col_w = (pw - g) / 2
    band = ph - header
    so = mm(lay.sheet_overlap_mm)
    return W, H, m, g, header, col_w, band, so


def plan_side_by_side(left: StreamSide, right: StreamSide, lay: StreamLayout = StreamLayout()) -> PrintPlan:
    W, H, m, g, header, col_w, band, so = _geometry(lay)
    if band - so <= 1e-6:
        raise ValueError("용지가 너무 작거나 겹침이 큽니다")
    sides = {"L": left, "R": right}
    sc = {k: col_w / max(p.width for p in s.pages) for k, s in sides.items()}
    if lay.common_scale:
        sc = {k: min(sc.values()) for k in sc}
    adj = {k: s.adjust_mm * PT_PER_MM for k, s in sides.items()}
    # 두 변의 가장 위쪽 내용이 u>=0 이 되도록 기준선 결정
    eff_lead = {k: s.start_y - max(s.start_y - s.lead, 0.0) for k, s in sides.items()}
    baseline = max(0.0, *[sc[k] * eff_lead[k] - adj[k] for k in sides])
    segs = {k: build_segments(s, sc[k], baseline + adj[k]) for k, s in sides.items()}
    u_end = max((sg.u1(sc[k]) for k in sides for sg in segs[k]), default=0.0)
    step = band - so
    n_sheets = max(1, math.ceil((u_end - so) / step - 1e-9))
    sheets = []
    for k in range(n_sheets):
        b0 = k * step
        b1 = b0 + band
        sh = Sheet(W, H)
        for i, key in enumerate(("L", "R")):
            col_x = m.left + i * (col_w + g)
            for sg in segs[key]:
                u1 = sg.u1(sc[key])
                a, b = max(sg.u0, b0), min(u1, b1)
                if b - a <= 1e-6:
                    continue
                info = next(p for p in sides[key].pages if p.index == sg.page)
                s = sc[key]
                y0 = sg.src_y0 + (a - sg.u0) / s
                y1 = sg.src_y0 + (b - sg.u0) / s
                dw = s * info.width
                x = col_x + (col_w - dw) / 2
                y = m.top + header + (a - b0)
                sh.placements.append(Placement(sides[key].source_id, sg.page,
                                               Box(0, y0, info.width, y1), Box(x, y, x + dw, y + (b - a))))
                if lay.draw_page_boundaries and sg.u0 > b0 and sg.u0 < b1 and sg is not segs[key][0]:
                    yy = m.top + header + (sg.u0 - b0)
                    sh.marks.append(Mark("page_boundary", (col_x, yy), (col_x + col_w, yy), f"p.{sg.page + 1}"))
        for i, key in enumerate(("L", "R")):
            bu = baseline + adj[key]
            if b0 <= bu < b1:
                col_x = m.left + i * (col_w + g)
                yy = m.top + header + (bu - b0)
                sh.marks.append(Mark("baseline", (col_x, yy), (col_x + col_w, yy)))
        sheets.append(sh)
    meta = {"mode": "side_by_side", "scale": sc, "baseline": baseline, "band": band, "step": step,
            "top": m.top + header, "segments": segs, "n_sheets": n_sheets}
    return PrintPlan(sheets, meta)


def src_to_out(plan: PrintPlan, side_id: str, page: int, y: float):
    """원본(보이는 좌표) → (시트 인덱스, 시트 y). 구간 밖이면 None. 겹침 시 첫 시트."""
    meta = plan.meta
    s = meta["scale"][side_id]
    for sg in meta["segments"][side_id]:
        if sg.page == page and sg.src_y0 - 1e-9 <= y <= sg.src_y1 + 1e-9:
            u = sg.u0 + s * (y - sg.src_y0)
            # 겹침 구간이면 그 점이 보이는 첫 시트: u < k*step + band 를 만족하는 최소 k
            k = max(0, math.ceil((u - meta["band"]) / meta["step"] - 1e-9))
            k = min(k, meta["n_sheets"] - 1)
            return k, meta["top"] + u - k * meta["step"]
    return None


def out_to_src(plan: PrintPlan, side_id: str, sheet: int, y: float):
    """시트 y → (page, 원본 y). 해당 변에 내용이 없으면 None."""
    meta = plan.meta
    if y < meta["top"] - 1e-9 or y > meta["top"] + meta["band"] + 1e-9:
        return None  # 머리 띠/하단 여백
    u = (y - meta["top"]) + sheet * meta["step"]
    s = meta["scale"][side_id]
    for sg in meta["segments"][side_id]:
        if sg.u0 - 1e-9 <= u <= sg.u1(s) + 1e-9:
            return sg.page, sg.src_y0 + (u - sg.u0) / s
    return None

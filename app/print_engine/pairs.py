"""두 PDF 교차 / 앞뒤 비교 출력 계획 (순수 계산, Qt 비의존)."""
from __future__ import annotations
from .layouts import plan_fit_to_paper
from .model import Margins, PrintPlan, Sheet
from .units import paper


def plan_interleave(left_infos, right_infos, sheet="A4", margins=Margins(), tail="append"):
    """L0,R0,L1,R1,... 페이지 수가 다르면 tail='append'(남은 쪽을 이어서 출력) 또는 'stop'(짧은 쪽에서 종료).
    left_infos/right_infos 는 사용자가 지정한 대응 시작 페이지부터의 목록."""
    sheets, n = [], max(len(left_infos), len(right_infos))
    for i in range(n):
        if tail == "stop" and (i >= len(left_infos) or i >= len(right_infos)):
            break
        if i < len(left_infos):
            sheets.append(plan_fit_to_paper(left_infos[i], sheet, margins, src_id="L"))
        if i < len(right_infos):
            sheets.append(plan_fit_to_paper(right_infos[i], sheet, margins, src_id="R"))
    return sheets


def plan_front_back(left_infos, right_infos, sheet="A4", margins=Margins()):
    """홀수 출력 페이지=원본(L), 짝수=수정본(R). 한쪽이 짧으면 빈 페이지 삽입. 앞뒤는 같은 방향으로 맞춘다."""
    sheets = []
    for i in range(max(len(left_infos), len(right_infos))):
        a = left_infos[i] if i < len(left_infos) else None
        b = right_infos[i] if i < len(right_infos) else None
        ref = a or b
        ls = ref.width > ref.height
        for info, sid in ((a, "L"), (b, "R")):
            if info is None:
                W, H = paper(sheet, ls)
                sheets.append(Sheet(W, H))
            else:
                sheets.append(plan_fit_to_paper(info, sheet, margins, src_id=sid, landscape=ls))
    return sheets


def build_pairs_plan(mode, left_infos, right_infos, **opts):
    fn = plan_interleave if mode == "interleave" else plan_front_back
    sheets = fn(left_infos, right_infos, **opts)
    meta = {"mode": mode}
    if mode == "front_back":
        meta["duplex"] = "long"
    return PrintPlan(sheets, meta)

from __future__ import annotations
import pymupdf
from .model import PrintPlan


def build_pdf(plan: PrintPlan, sources: dict, sheet_indices=None) -> bytes:
    """출력/미리보기/인쇄의 유일한 경로. 항상 새 문서를 만든다."""
    out = pymupdf.open()
    idxs = range(len(plan.sheets)) if sheet_indices is None else sheet_indices
    for k in idxs:
        sh = plan.sheets[k]
        page = out.new_page(width=sh.width, height=sh.height)
        for p in sh.placements:
            sources[p.source_id].place(page, p)
        for mk in sh.marks:
            if mk.kind == "seam":
                page.draw_line(mk.p0, mk.p1, color=(0.5, 0.5, 0.5), width=0.4, dashes="[3 3] 0")
            elif mk.kind == "page_boundary":
                page.draw_line(mk.p0, mk.p1, color=(0.7, 0.7, 0.7), width=0.3, dashes="[1 2] 0")
                if mk.text:
                    page.insert_text((mk.p0[0] + 2, mk.p0[1] - 1.5), mk.text, fontsize=5, color=(0.5, 0.5, 0.5))
            elif mk.kind == "baseline":
                page.draw_line(mk.p0, mk.p1, color=(0.9, 0.2, 0.2), width=0.4)
            elif mk.kind == "label" and mk.text:
                page.insert_text((mk.p0[0] + 4, mk.p0[1] + 10), mk.text, fontsize=7, color=(0.4, 0.4, 0.4))
    data = out.tobytes()
    out.close()
    return data

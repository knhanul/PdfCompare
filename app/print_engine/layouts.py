from __future__ import annotations
from .model import Box, Margins, Mark, Placement, PrintPlan, Sheet
from .units import mm, paper


def _area(sheet, landscape, m: Margins):
    W, H = paper(sheet, landscape)
    return W, H, W - m.left - m.right, H - m.top - m.bottom


def plan_tile_split(info, sheet="A4", tiles=2, margins=Margins(), overlap_mm=10.0,
                    marks=True, src_id="main"):
    """원본 1페이지를 확대해 tiles장으로 분할. 긴 축 방향으로 자른다.
    세로 원본: 위/아래 분할(위 타일은 아래 정렬). 가로 원본: 좌/우 분할(좌 타일은 오른쪽 정렬)."""
    w, h = info.width, info.height
    vertical = h >= w
    ov = mm(overlap_mm)
    best = None
    for landscape in (False, True):
        W, H, pw, ph = _area(sheet, landscape, margins)
        ovn = ov * (tiles - 1) / tiles
        if vertical:
            s = min(pw / w, (ph - ovn) / (h / tiles))
        else:
            s = min(ph / h, (pw - ovn) / (w / tiles))
        if tiles > 2:  # 가운데 타일은 양쪽에 겹침이 붙는다
            s = min(s, ((ph - ov) / (h / tiles)) if vertical else ((pw - ov) / (w / tiles)))
        if best is None or s > best[0]:
            best = (s, landscape, W, H, pw, ph)
    s, landscape, W, H, pw, ph = best
    m = margins
    L = h if vertical else w
    ov_s = ov / s
    out = []
    for k in range(tiles):
        a = max(k * L / tiles - (ov_s / 2 if k > 0 else 0), 0.0)
        b = min((k + 1) * L / tiles + (ov_s / 2 if k < tiles - 1 else 0), L)
        sh = Sheet(W, H)
        if vertical:
            clip = Box(0, a, w, b)
            dw, dh = s * w, s * (b - a)
            x = m.left + (pw - dw) / 2
            if k == 0 and tiles > 1:
                y = H - m.bottom - dh
            elif k == tiles - 1 and tiles > 1:
                y = m.top
            else:
                y = m.top + (ph - dh) / 2
        else:
            clip = Box(a, 0, b, h)
            dw, dh = s * (b - a), s * h
            y = m.top + (ph - dh) / 2
            if k == 0 and tiles > 1:
                x = W - m.right - dw
            elif k == tiles - 1 and tiles > 1:
                x = m.left
            else:
                x = m.left + (pw - dw) / 2
        dst = Box(x, y, x + dw, y + dh)
        sh.placements.append(Placement(src_id, info.index, clip, dst))
        if marks:
            sh.marks.append(Mark("label", (dst.x0, dst.y0), (dst.x0, dst.y0), f"{k + 1}/{tiles}"))
            for edge_k in (k, k + 1):
                if 0 < edge_k < tiles:
                    edge = edge_k * L / tiles
                    if vertical:
                        yy = dst.y0 + s * (edge - a)
                        sh.marks.append(Mark("seam", (dst.x0, yy), (dst.x1, yy)))
                    else:
                        xx = dst.x0 + s * (edge - a)
                        sh.marks.append(Mark("seam", (xx, dst.y0), (xx, dst.y1)))
        out.append(sh)
    return out


def plan_fit_to_paper(info, sheet="A3", margins=Margins(), allow_rotate=True, src_id="main"):
    w, h = info.width, info.height
    landscape = (w > h) if allow_rotate else False
    W, H, pw, ph = _area(sheet, landscape, margins)
    s = min(pw / w, ph / h)
    dw, dh = s * w, s * h
    x, y = margins.left + (pw - dw) / 2, margins.top + (ph - dh) / 2
    sh = Sheet(W, H)
    sh.placements.append(Placement(src_id, info.index, Box(0, 0, w, h), Box(x, y, x + dw, y + dh)))
    return sh


def plan_n_up(infos, sheet="A4", n=2, margins=Margins(), gutter_mm=5.0,
              auto_rotate=True, src_id="main"):
    if n != 2:
        raise ValueError("n=2만 지원")
    g, m = mm(gutter_mm), margins
    sheets = []
    for i in range(0, len(infos), n):
        group = infos[i:i + n]
        landscape = group[0].width <= group[0].height  # 세로 원본 → 가로 시트(좌/우 슬롯)
        W, H, pw, ph = _area(sheet, landscape, m)
        sh = Sheet(W, H)
        for j, info in enumerate(group):
            if landscape:
                sw, shh = (pw - g) / 2, ph
                sx, sy = m.left + j * (sw + g), m.top
            else:
                sw, shh = pw, (ph - g) / 2
                sx, sy = m.left, m.top + j * (shh + g)
            w, h = info.width, info.height
            s0 = min(sw / w, shh / h)
            s90 = min(sw / h, shh / w)
            rot = 0
            if auto_rotate and s90 > s0 * 1.01:
                rot, s = 90, s90
                dw, dh = s * h, s * w
            else:
                s = s0
                dw, dh = s * w, s * h
            x, y = sx + (sw - dw) / 2, sy + (shh - dh) / 2
            sh.placements.append(Placement(src_id, info.index, Box(0, 0, w, h),
                                           Box(x, y, x + dw, y + dh), rot))
        sheets.append(sh)
    return sheets


def build_plan(mode, infos, **opts):
    sheets = []
    if mode == "split2":
        for info in infos:
            sheets += plan_tile_split(info, **opts)
    elif mode == "fit":
        sheets = [plan_fit_to_paper(i, **opts) for i in infos]
    elif mode == "nup":
        sheets = plan_n_up(infos, **opts)
    else:
        raise ValueError(mode)
    return PrintPlan(sheets, {"mode": mode})

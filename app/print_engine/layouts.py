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


def plan_fit_to_paper(info, sheet="A3", margins=Margins(), allow_rotate=True, src_id="main", landscape=None):
    w, h = info.width, info.height
    if landscape is None:
        landscape = (w > h) if allow_rotate else False
    W, H, pw, ph = _area(sheet, landscape, margins)
    s = min(pw / w, ph / h)
    dw, dh = s * w, s * h
    x, y = margins.left + (pw - dw) / 2, margins.top + (ph - dh) / 2
    sh = Sheet(W, H)
    sh.placements.append(Placement(src_id, info.index, Box(0, 0, w, h), Box(x, y, x + dw, y + dh)))
    return sh


def _grid_candidates(n, extra=None):
    """n의 약수쌍 (cols, rows). 가로로 긴 격자를 먼저."""
    pairs = [(c, n // c) for c in range(1, n + 1) if n % c == 0]
    pairs.sort(key=lambda cr: (abs(cr[0] - cr[1]), -cr[0]))
    return pairs


def plan_grid_split(info, sheet="A4", n=4, cols=None, rows=None, margins=Margins(),
                    overlap_mm=5.0, marks=True, src_id="main", landscape=None):
    """원본 1페이지를 cols x rows 격자로 확대 분할(겹침 포함). n=2/4/6/9 등.
    cols/rows 미지정 시 n의 약수쌍과 용지 방향을 모두 시도해 배율이 가장 큰 조합 선택."""
    w, h = info.width, info.height
    ov = mm(overlap_mm)
    grids = [(cols, rows)] if cols and rows else _grid_candidates(n)
    orients = [landscape] if landscape is not None else [w > h, w <= h]
    best = None
    for c, r in grids:
        for ls in orients:
            W, H, pw, ph = _area(sheet, ls, margins)
            fx = 0 if c == 1 else (0.5 if c == 2 else 1.0)
            fy = 0 if r == 1 else (0.5 if r == 2 else 1.0)
            s = min((pw - fx * ov) / (w / c), (ph - fy * ov) / (h / r))
            if s > 0 and (best is None or s > best[0] * 1.001):
                best = (s, c, r, ls, W, H, pw, ph)
    if best is None:
        raise ValueError("분할할 수 없는 설정입니다. 겹침/여백을 줄이세요.")
    s, c, r, ls, W, H, pw, ph = best
    m = margins
    ov_s = ov / s
    sheets = []
    for j in range(r):
        for i in range(c):
            ax = max(i * w / c - (ov_s / 2 if i > 0 else 0), 0.0)
            bx = min((i + 1) * w / c + (ov_s / 2 if i < c - 1 else 0), w)
            ay = max(j * h / r - (ov_s / 2 if j > 0 else 0), 0.0)
            by = min((j + 1) * h / r + (ov_s / 2 if j < r - 1 else 0), h)
            dw, dh = s * (bx - ax), s * (by - ay)
            if c == 1:
                x = m.left + (pw - dw) / 2
            elif i == 0:
                x = W - m.right - dw
            elif i == c - 1:
                x = m.left
            else:
                x = m.left + (pw - dw) / 2
            if r == 1:
                y = m.top + (ph - dh) / 2
            elif j == 0:
                y = H - m.bottom - dh
            elif j == r - 1:
                y = m.top
            else:
                y = m.top + (ph - dh) / 2
            dst = Box(x, y, x + dw, y + dh)
            sh = Sheet(W, H)
            sh.placements.append(Placement(src_id, info.index, Box(ax, ay, bx, by), dst))
            if marks:
                sh.marks.append(Mark("label", (dst.x0, dst.y0), (dst.x0, dst.y0),
                                     f"{j * c + i + 1}/{c * r} (R{j + 1} C{i + 1})"))
                for ek in (i, i + 1):
                    if 0 < ek < c:
                        xx = dst.x0 + s * (ek * w / c - ax)
                        sh.marks.append(Mark("seam", (xx, dst.y0), (xx, dst.y1)))
                for ek in (j, j + 1):
                    if 0 < ek < r:
                        yy = dst.y0 + s * (ek * h / r - ay)
                        sh.marks.append(Mark("seam", (dst.x0, yy), (dst.x1, yy)))
            sheets.append(sh)
    return sheets


def _slot_index(k, cols, rows, order):
    """k번째 페이지의 (col,row). order: Z(가로우선) N(세로우선), *_rtl은 오른쪽에서 왼쪽."""
    if order.startswith("N"):
        col, row = k // rows, k % rows
    else:
        row, col = k // cols, k % cols
    if order.endswith("rtl"):
        col = cols - 1 - col
    return col, row


def plan_n_up(infos, sheet="A4", n=2, margins=Margins(), gutter_mm=5.0,
              auto_rotate=True, src_id="main", order="Z", border=False, numbers=False,
              landscape=None):
    """n페이지를 한 장에 격자 배치. n=2/4/6/8/9/16 등. 종횡비 유지, 빈 슬롯은 비워 둔다."""
    if n < 1:
        raise ValueError("n >= 1")
    g, m = mm(gutter_mm), margins
    sheets = []
    for i0 in range(0, len(infos), n):
        group = infos[i0:i0 + n]
        first_portrait = group[0].width <= group[0].height
        orients = [landscape] if landscape is not None else [first_portrait, not first_portrait]
        best = None
        for c, r in _grid_candidates(n):
            for ls in orients:
                W, H, pw, ph = _area(sheet, ls, m)
                sw, shh = (pw - (c - 1) * g) / c, (ph - (r - 1) * g) / r
                if sw <= 0 or shh <= 0:
                    continue
                smin = None
                for inf in group:
                    s0 = min(sw / inf.width, shh / inf.height)
                    if auto_rotate:
                        s0 = max(s0, min(sw / inf.height, shh / inf.width))
                    smin = s0 if smin is None else min(smin, s0)
                if best is None or smin > best[0] * 1.001:
                    best = (smin, c, r, ls, W, H, pw, ph, sw, shh)
        if best is None:
            raise ValueError("여백/간격이 너무 커서 배치할 수 없습니다.")
        _, c, r, ls, W, H, pw, ph, sw, shh = best
        sh = Sheet(W, H)
        for j, info in enumerate(group):
            col, row = _slot_index(j, c, r, order)
            sx, sy = m.left + col * (sw + g), m.top + row * (shh + g)
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
            if border:
                for a, b in (((x, y), (x + dw, y)), ((x + dw, y), (x + dw, y + dh)),
                             ((x + dw, y + dh), (x, y + dh)), ((x, y + dh), (x, y))):
                    sh.marks.append(Mark("page_boundary", a, b))
            if numbers:
                sh.marks.append(Mark("label", (x, y), (x, y), str(info.index + 1)))
        sheets.append(sh)
    return sheets


def _slot_placement(info, sx, sy, sw, shh, src_id, auto_rotate=True):
    w, h = info.width, info.height
    s0, s90 = min(sw / w, shh / h), min(sw / h, shh / w)
    if auto_rotate and s90 > s0 * 1.01:
        rot, dw, dh = 90, s90 * h, s90 * w
    else:
        rot, dw, dh = 0, s0 * w, s0 * h
    x, y = sx + (sw - dw) / 2, sy + (shh - dh) / 2
    return Placement(src_id, info.index, Box(0, 0, w, h), Box(x, y, x + dw, y + dh), rot)


def booklet_order(count):
    """소책자 면 순서(왼쪽 제본). 반환: [(앞면(왼,오), 뒷면(왼,오)), ...] 0-based, 빈 페이지는 None.
    8p → [((7,0),(1,6)), ((5,2),(3,4))]. 4의 배수로 패딩."""
    n = (count + 3) // 4 * 4
    f = lambda p: None if p >= count else p
    out = []
    for i in range(n // 4):
        out.append(((f(n - 1 - 2 * i), f(2 * i)), (f(2 * i + 1), f(n - 2 - 2 * i))))
    return out


def plan_booklet(infos, sheet="A4", margins=Margins(), binding="left", gutter_mm=0.0,
                 src_id="main", fold_mark=True):
    """접으면 책이 되는 소책자. 가로 용지 한 면에 2페이지, 시트 한 장당 앞/뒤 2면.
    짧은 변 뒤집기 양면 기준. binding='right'면 좌우를 맞바꾼다."""
    if not infos:
        return []
    g, m = mm(gutter_mm), margins
    W, H, pw, ph = _area(sheet, True, m)
    sw, shh = (pw - g) / 2, ph
    sheets = []
    for front, back in booklet_order(len(infos)):
        for pair in (front, back):
            if binding == "right":
                pair = (pair[1], pair[0])
            sh = Sheet(W, H)
            for col, pg in enumerate(pair):
                if pg is not None:
                    sh.placements.append(_slot_placement(infos[pg], m.left + col * (sw + g), m.top,
                                                         sw, shh, src_id))
            if fold_mark:
                sh.marks.append(Mark("seam", (W / 2, 0), (W / 2, 8)))
                sh.marks.append(Mark("seam", (W / 2, H - 8), (W / 2, H)))
            sheets.append(sh)
    return sheets


def plan_long_split(info, sheet="A4", margins=Margins(), overlap_mm=5.0, scale=None,
                    marks=True, src_id="main"):
    """세로로 긴 페이지를 용지 너비에 맞춰 여러 장으로 분할(내용 누락 없음).
    scale=None: 너비가 용지보다 크면 줄이고, 아니면 실제 크기(확대 안 함)."""
    w, h = info.width, info.height
    W, H, pw, ph = _area(sheet, False, margins)
    s = min(scale, pw / w) if scale else min(1.0, pw / w)   # 너비 초과로 오른쪽이 잘리지 않도록
    th, ov = ph / s, mm(overlap_mm) / s
    if th <= ov:
        raise ValueError("겹침이 용지 높이보다 큽니다.")
    sheets, y0 = [], 0.0
    while True:
        y1 = min(y0 + th, h)
        sh = Sheet(W, H)
        dw, dh = s * w, s * (y1 - y0)
        x = margins.left + max(0.0, (pw - dw) / 2)
        sh.placements.append(Placement(src_id, info.index, Box(0, y0, w, y1),
                                       Box(x, margins.top, x + dw, margins.top + dh)))
        sheets.append(sh)
        if y1 >= h - 0.5:   # 0.5pt 이하 잔여는 빈 장을 만들지 않음
            break
        y0 = y1 - ov
    n = len(sheets)
    if marks:
        for i, sh in enumerate(sheets):
            d = sh.placements[0].dst
            sh.marks.append(Mark("label", (d.x0, d.y0), (d.x0, d.y0), f"{i + 1}/{n}"))
            if i < n - 1:
                sh.marks.append(Mark("seam", (d.x0, d.y1), (d.x1, d.y1)))
            if i > 0:
                sh.marks.append(Mark("seam", (d.x0, d.y0), (d.x1, d.y0)))
    return sheets


def plan_region(info, region, sheet="A4", margins=Margins(), fit="fit", scale=1.0,
                landscape=None, src_id="main"):
    """원본 페이지의 region(보이는 좌표 Box)만 용지에 출력(클리핑+배율, 원본 불변).
    fit: 'fit'(용지에 맞춤) | 'original'(1:1) | 'scale'(사용자 배율)."""
    r = Box(max(0.0, region.x0), max(0.0, region.y0), min(info.width, region.x1), min(info.height, region.y1))
    if r.is_empty():
        raise ValueError("출력 영역이 비어 있습니다.")
    if (region.x1 > info.width + 0.5 or region.y1 > info.height + 0.5 or region.x0 < -0.5 or region.y0 < -0.5):
        raise ValueError("선택 영역이 이 페이지 크기를 벗어납니다. 페이지 크기가 같은 범위만 선택하세요.")
    ls = (r.w > r.h) if landscape is None else landscape
    W, H, pw, ph = _area(sheet, ls, margins)
    s = min(pw / r.w, ph / r.h) if fit == "fit" else (1.0 if fit == "original" else scale)
    dw, dh = s * r.w, s * r.h
    if dw > pw + 1e-6 or dh > ph + 1e-6:
        raise ValueError("선택 영역이 용지보다 큽니다. '용지에 맞춤'이나 더 작은 배율을 선택하세요.")
    x, y = margins.left + (pw - dw) / 2, margins.top + (ph - dh) / 2
    sh = Sheet(W, H)
    sh.placements.append(Placement(src_id, info.index, r, Box(x, y, x + dw, y + dh)))
    return sh


def build_plan(mode, infos, **opts):
    sheets = []
    if mode == "split2":
        for info in infos:
            sheets += plan_tile_split(info, **opts)
    elif mode == "fit":
        sheets = [plan_fit_to_paper(i, **opts) for i in infos]
    elif mode == "split":
        for info in infos:
            sheets += plan_grid_split(info, **opts)
    elif mode == "nup":
        sheets = plan_n_up(infos, **opts)
    elif mode == "booklet":
        sheets = plan_booklet(infos, **opts)
    elif mode == "long":
        for info in infos:
            sheets += plan_long_split(info, **opts)
    elif mode == "region":
        regions = opts.pop("regions")      # {page_index: Box} 또는 단일 Box
        for info in infos:
            reg = regions[info.index] if isinstance(regions, dict) else regions
            try:
                sheets.append(plan_region(info, reg, **opts))
            except ValueError as e:
                raise ValueError(f"{info.index + 1}페이지: {e}") from None
    else:
        raise ValueError(mode)
    meta = {"mode": mode, "min_scale": _min_scale(sheets)}
    if mode == "booklet":
        meta["duplex"] = "short"
        meta["sides"] = ["front" if i % 2 == 0 else "back" for i in range(len(sheets))]
    return PrintPlan(sheets, meta)


def _min_scale(sheets):
    vals = [min(p.dst.w, p.dst.h) / max(1e-9, min(p.clip.w, p.clip.h))
            for sh in sheets for p in sh.placements]
    return min(vals) if vals else 1.0

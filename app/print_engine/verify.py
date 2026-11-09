from __future__ import annotations


def coverage(plan):
    """{(source_id, page): [(y0, y1), ...]} 병합된 원본 y 구간(보이는 좌표)."""
    acc = {}
    for sh in plan.sheets:
        for p in sh.placements:
            acc.setdefault((p.source_id, p.page), []).append((p.clip.y0, p.clip.y1))
    res = {}
    for key, iv in acc.items():
        iv.sort()
        merged = [list(iv[0])]
        for a, b in iv[1:]:
            if a <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        res[key] = [tuple(x) for x in merged]
    return res

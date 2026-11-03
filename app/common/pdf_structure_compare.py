"""문서 구조 기반 비교 (PyMuPDF 구조 추출 활용).

기존 시각/텍스트 비교를 대체하지 않고, 구조 차이를 요약해 보여준다.
to_markdown / to_json 이 사용 가능하면 활용하고, 없으면 텍스트 블록 기반으로 폴백한다.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import pymupdf as fitz


def _extract_structure(path: str) -> dict[str, Any]:
    """PDF에서 구조 정보를 추출한다."""
    doc = fitz.open(path)
    try:
        result: dict[str, Any] = {
            "page_count": len(doc),
            "markdown": "",
            "blocks": [],
            "tables": [],
        }
        # PyMuPDF 2.0+ 구조 API 시도
        if hasattr(doc, "to_markdown"):
            try:
                result["markdown"] = doc.to_markdown() or ""
            except Exception:
                result["markdown"] = ""
        if hasattr(doc, "to_json"):
            try:
                result["json"] = doc.to_json()
            except Exception:
                result["json"] = None

        # 폴백: 페이지별 텍스트 블록
        for i, page in enumerate(doc):
            blocks = page.get_text("blocks") or []
            for b in blocks:
                if len(b) >= 5 and b[4]:
                    result["blocks"].append({
                        "page": i,
                        "bbox": tuple(b[:4]),
                        "text": str(b[4]).strip(),
                    })
            # 표 추출 시도
            try:
                tabs = page.find_tables()
                for t in (tabs.tables or []):
                    result["tables"].append({
                        "page": i,
                        "bbox": t.bbox,
                        "rows": t.extract() or [],
                    })
            except Exception:
                pass
        return result
    finally:
        doc.close()


def _normalize_blocks(blocks: list[dict]) -> list[str]:
    """비교용으로 텍스트 블록을 정규화한다 (공백 정리)."""
    out = []
    for b in blocks:
        text = " ".join(b.get("text", "").split())
        if text:
            out.append(f"[p{b['page']+1}] {text}")
    return out


def compare_structure(path1: str, path2: str) -> dict[str, Any]:
    """두 PDF의 구조를 비교하고 변경 요약을 반환한다."""
    s1 = _extract_structure(path1)
    s2 = _extract_structure(path2)

    # Markdown이 있으면 우선 사용, 없으면 블록 텍스트
    text1 = s1["markdown"] if s1["markdown"] else "\n".join(_normalize_blocks(s1["blocks"]))
    text2 = s2["markdown"] if s2["markdown"] else "\n".join(_normalize_blocks(s2["blocks"]))

    matcher = SequenceMatcher(None, text1.splitlines(), text2.splitlines(), autojunk=False)
    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        left = "\n".join(text1.splitlines()[i1:i2])[:200]
        right = "\n".join(text2.splitlines()[j1:j2])[:200]
        if tag == "delete":
            kind = "삭제"
        elif tag == "insert":
            kind = "추가"
        elif tag == "replace":
            # 내용이 거의 같고 위치만 다른 경우는 '이동'으로 간주 (간단한 휴리스틱)
            ratio = SequenceMatcher(None, left, right).ratio()
            kind = "위치 이동" if ratio > 0.85 else "수정"
        else:
            kind = "검토 필요"
        changes.append({
            "type": kind,
            "left": left,
            "right": right,
        })

    # 표 변경 간단 비교
    table_changes = []
    t1_rows = [r for t in s1["tables"] for r in t["rows"]]
    t2_rows = [r for t in s2["tables"] for r in t["rows"]]
    if t1_rows or t2_rows:
        tm = SequenceMatcher(None, [str(r) for r in t1_rows], [str(r) for r in t2_rows])
        for tag, a1, a2, b1, b2 in tm.get_opcodes():
            if tag != "equal":
                table_changes.append({
                    "type": tag,
                    "before": t1_rows[a1:a2],
                    "after": t2_rows[b1:b2],
                })

    summary = {
        "text_modified": sum(1 for c in changes if c["type"] == "수정"),
        "added": sum(1 for c in changes if c["type"] == "추가"),
        "deleted": sum(1 for c in changes if c["type"] == "삭제"),
        "moved": sum(1 for c in changes if c["type"] == "위치 이동"),
        "table_changes": len(table_changes),
        "uncertain": sum(1 for c in changes if c["type"] == "검토 필요"),
    }

    return {
        "summary": summary,
        "changes": changes[:50],  # 과도한 목록 방지
        "table_changes": table_changes[:20],
        "used_markdown": bool(s1["markdown"] and s2["markdown"]),
        "page_counts": (s1["page_count"], s2["page_count"]),
    }

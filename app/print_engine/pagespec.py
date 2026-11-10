"""페이지 조합 문자열 파서 (순수 함수, Qt 비의존).

예: "1,3,5-8,12", "7-", "-3", "odd", "even", "all"
단일 문서: parse(text, count) -> [0-based index, ...]
다중 문서: parse_multi(text, {'L': nL, 'R': nR}) -> [(key, index), ...]  (접두어 L3, R2-4)
"""
import re


class PageSpecError(ValueError):
    pass


def _expand(token, count):
    t = token.strip().lower()
    if t in ('all', '전체'):
        return list(range(count))
    if t in ('odd', '홀수'):
        return list(range(0, count, 2))     # 1,3,5.. (0-based 0,2,4..)
    if t in ('even', '짝수'):
        return list(range(1, count, 2))
    m = re.fullmatch(r'(\d*)\s*-\s*(\d*)', t)
    if m and (m.group(1) or m.group(2)):
        a = int(m.group(1)) if m.group(1) else 1
        b = int(m.group(2)) if m.group(2) else count
        if a < 1 or b < 1:
            raise PageSpecError(f"잘못된 범위: '{token}'")
        if a > b:
            raise PageSpecError(f"시작이 끝보다 큽니다: '{token}'")
        if b > count:
            raise PageSpecError(f"존재하지 않는 페이지 {b} (총 {count}페이지)")
        return list(range(a - 1, b))
    if t.isdigit():
        n = int(t)
        if n < 1 or n > count:
            raise PageSpecError(f"존재하지 않는 페이지 {n} (총 {count}페이지)")
        return [n - 1]
    raise PageSpecError(f"해석할 수 없는 입력: '{token}'")


def parse(text, count):
    """원본 페이지 기준 0-based 인덱스 목록(입력 순서 유지, 중복 허용)."""
    if count <= 0:
        raise PageSpecError('페이지가 없습니다.')
    if text is None or not text.strip():
        raise PageSpecError('페이지를 입력하세요.')
    out = []
    for tok in text.replace(';', ',').split(','):
        if not tok.strip():
            raise PageSpecError('빈 항목이 있습니다.')
        out.extend(_expand(tok, count))
    return out


def parse_multi(text, counts):
    """접두어(L/R)가 있는 조합. 접두어 없는 항목은 첫 번째 키에 적용."""
    keys = list(counts)
    out = []
    for tok in text.replace(';', ',').split(','):
        t = tok.strip()
        if not t:
            raise PageSpecError('빈 항목이 있습니다.')
        key = keys[0]
        if t[0].upper() in counts:
            key, t = t[0].upper(), t[1:]
        out.extend((key, i) for i in parse(t, counts[key]))
    return out

"""브랜드 로고(투명 PNG)에서 다중 해상도 ICO와 MSIX 아이콘 자산을 생성한다.

사용: python scripts/make_icons.py [--target posid] [--no-msix]
 - 입력 : assets/<target>/<target>_logo_512.png (알파 채널 필수)
 - 출력 : assets/<target>/<icon_file>.ico  (16~256 다중 해상도)
          assets/<target>/msix/*.png       (Square44/150, StoreLogo, altform-unplated)
로고의 색/디자인은 바꾸지 않는다(투명 여백 크롭 + 정사각형 패딩 + 축소만 수행).
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
TARGET_SIZES_44 = [16, 24, 32, 48, 256]
SCALES = {100: 1.0, 125: 1.25, 150: 1.5, 200: 2.0, 400: 4.0}

# 타겟별 설정: 원본 로고, ICO 파일명
TARGETS = {
    'posid': {'source': 'posid_logo_512.png', 'ico': 'posid_icon.ico'},
}


def master_square(src: Path, margin: float) -> Image.Image:
    """투명 여백을 크롭하고 margin 비율의 투명 패딩으로 정사각형을 만든다."""
    im = Image.open(src).convert('RGBA')
    bbox = im.getchannel('A').point(lambda v: 255 if v > 8 else 0).getbbox()
    if bbox is None:
        raise ValueError(f'{src}: 완전히 투명한 이미지')
    im = im.crop(bbox)
    side = round(max(im.size) * (1 + 2 * margin))
    out = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    out.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return out


def render_or_none(master, size):
    return render(master, size) if size <= master.width else None


def render(master: Image.Image, size: int) -> Image.Image:
    if size > master.width:  # 임의 확대 금지
        raise ValueError(f'원본({master.width}px)보다 큰 {size}px 요청')
    return master.resize((size, size), Image.LANCZOS)


def check_alpha(img: Image.Image, name: str):
    """코너가 완전 투명하고 알파 채널이 실제로 존재하는지 검사."""
    img = img.convert('RGBA')
    w, h = img.size
    a = img.getchannel('A')
    corners = [a.getpixel(p) for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
    if any(c != 0 for c in corners):
        raise AssertionError(f'{name}: 코너가 투명하지 않음 {corners}')
    lo, hi = a.getextrema()
    if not (lo == 0 and hi == 255):
        raise AssertionError(f'{name}: 알파 범위 이상 {lo}-{hi}')


def generate(target: str, msix: bool = True, root: Path = ROOT):
    cfg = TARGETS[target]
    asset_dir = root / 'assets' / target
    src = asset_dir / cfg['source']
    if not src.exists():
        print(f'[icons] {target}: 원본 {src.name} 없음 - 건너뜀')
        return []
    produced = []
    # ICO: 작은 크기에서 로고가 커 보이도록 여백 4%
    m_ico = master_square(src, 0.04)
    if m_ico.width < 256:
        raise ValueError(f'원본 해상도 부족({m_ico.width}px < 256px)')
    ico_path = asset_dir / cfg['ico']
    base = render(m_ico, 256)
    base.save(ico_path, format='ICO', sizes=[(s, s) for s in ICO_SIZES])
    check_alpha(base, ico_path.name)
    produced.append(ico_path)
    if msix:
        out_dir = asset_dir / 'msix'
        out_dir.mkdir(exist_ok=True)

        def save(name, img):
            if img is None:
                print(f'[icons] 건너뜀(원본 해상도 부족, 확대 금지): {name}')
                return
            check_alpha(img, name)
            p = out_dir / name
            img.save(p, format='PNG')
            produced.append(p)

        # 작업표시줄/제목표시줄용: 배경판(plate) 없는 unplated, 여백 최소
        m_small = master_square(src, 0.02)
        for s in TARGET_SIZES_44:
            img = render(m_small, s)
            save(f'Square44x44Logo.targetsize-{s}.png', img)
            save(f'Square44x44Logo.targetsize-{s}_altform-unplated.png', img)
        # 스케일 자산 (타일/시작 메뉴): 여백 8%
        m_tile = master_square(src, 0.08)
        for sc, f in SCALES.items():
            s44, s150, s50 = round(44 * f), round(150 * f), round(50 * f)
            save(f'Square44x44Logo.scale-{sc}.png', render(m_tile, s44))
            save(f'Square150x150Logo.scale-{sc}.png', render_or_none(m_tile, s150))
            save(f'StoreLogo.scale-{sc}.png', render(m_tile, s50))
    for p in produced:
        print(f'[icons] {p.relative_to(root)}')
    return produced


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', default='posid', choices=sorted(TARGETS))
    ap.add_argument('--no-msix', action='store_true')
    a = ap.parse_args()
    generate(a.target, msix=not a.no_msix)
    sys.exit(0)

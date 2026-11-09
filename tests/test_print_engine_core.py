import math
import unittest

import pymupdf

from app.print_engine import (Margins, PageInfo, SourceDoc, build_pdf, build_plan, mm,
                              plan_fit_to_paper, plan_n_up, plan_tile_split)
from app.print_engine.verify import coverage

Z = Margins(0, 0, 0, 0)


def make_pdf(pages=1, w=mm(210), h=mm(297), rotation=0, cropbox=None, step=20):
    """페이지마다 step pt 간격 고유 토큰을 가진 합성 PDF 바이트."""
    d = pymupdf.open()
    for p in range(pages):
        pg = d.new_page(width=w, height=h)
        y = 30.0
        while y < h - 20:
            pg.insert_text((40, y), f"P{p}Y{int(y)}", fontsize=8)
            y += step
        if cropbox:
            pg.set_cropbox(pymupdf.Rect(*cropbox))
        if rotation:
            pg.set_rotation(rotation)
    b = d.tobytes()
    d.close()
    return b


def red_corner_pdf():
    d = pymupdf.open()
    pg = d.new_page(width=200, height=300)
    pg.draw_rect(pymupdf.Rect(0, 0, 60, 60), color=None, fill=(1, 0, 0))
    b = d.tobytes()
    d.close()
    return b


def raster(pdf_bytes, page=0, dpi=36):
    d = pymupdf.open("pdf", pdf_bytes)
    pm = d[page].get_pixmap(dpi=dpi)
    d.close()
    return pm


class TestUnits(unittest.TestCase):
    def test_a4_mm(self):
        self.assertAlmostEqual(mm(210), 595.2756, 3)

    def test_fit_a4_to_a3_is_sqrt2(self):
        sh = plan_fit_to_paper(PageInfo(0, mm(210), mm(297)), "A3", Z)
        d = sh.placements[0].dst
        self.assertAlmostEqual(d.w / mm(210), math.sqrt(2), 3)
        self.assertAlmostEqual(d.h / mm(297), math.sqrt(2), 3)

    def test_nup_scales(self):
        i = [PageInfo(0, mm(210), mm(297)), PageInfo(1, mm(210), mm(297))]
        s = plan_n_up(i, "A4", 2, Z, gutter_mm=0)[0].placements[0].dst
        self.assertAlmostEqual(s.w / mm(210), 0.7071, 3)
        s = plan_n_up(i, "A3", 2, Z, gutter_mm=0)[0].placements[0].dst
        self.assertAlmostEqual(s.w / mm(210), 1.0, 6)


class TestSplit(unittest.TestCase):
    def test_geometry_portrait(self):
        info = PageInfo(0, mm(210), mm(297))
        ov = 10
        shs = plan_tile_split(info, "A4", 2, Margins(), ov)
        self.assertEqual(len(shs), 2)
        self.assertGreater(shs[0].width, shs[0].height)  # 가로 시트
        c0, c1 = shs[0].placements[0], shs[1].placements[0]
        self.assertAlmostEqual(c0.clip.y0, 0)
        self.assertAlmostEqual(c1.clip.y1, info.height)
        s = c0.dst.h / c0.clip.h
        self.assertAlmostEqual(c0.clip.y1 - c1.clip.y0, mm(ov) / s, 6)
        for sh in shs:
            p = sh.placements[0]
            self.assertAlmostEqual(p.dst.w / p.clip.w, p.dst.h / p.clip.h, 6)
            self.assertGreaterEqual(p.dst.x0, mm(5) - 1e-6)
            self.assertLessEqual(p.dst.x1, sh.width - mm(5) + 1e-6)
            self.assertGreaterEqual(p.dst.y0, mm(5) - 1e-6)
            self.assertLessEqual(p.dst.y1, sh.height - mm(5) + 1e-6)
        cov = coverage(build_plan("split2", [info]))
        self.assertEqual(len(cov[("main", 0)]), 1)
        self.assertAlmostEqual(cov[("main", 0)][0][1], info.height)

    def test_landscape_source_splits_horizontally(self):
        info = PageInfo(0, mm(297), mm(210))
        shs = plan_tile_split(info, "A4", 2, Margins(), 10)
        self.assertLess(shs[0].width, shs[0].height)  # 세로 시트
        self.assertAlmostEqual(shs[0].placements[0].clip.y1 - shs[0].placements[0].clip.y0, info.height)
        self.assertAlmostEqual(shs[1].placements[0].clip.x1, info.width)


class TestRender(unittest.TestCase):
    def _words(self, data):
        d = pymupdf.open("pdf", data)
        out = []
        for pg in d:
            out += [w[4] for w in pg.get_text("words")]
        d.close()
        return out

    def _tokens(self, pages, h):
        r = []
        for p in range(pages):
            y = 30.0
            while y < h - 20:
                r.append(f"P{p}Y{int(y)}")
                y += 20.0
        return r

    def test_split_no_token_missing(self):
        for rot, crop in [(0, None), (90, None), (180, None), (270, None), (0, (10, 20, 500, 800)),
                          (90, (10, 20, 500, 800))]:
            with self.subTest(rot=rot, crop=crop):
                src = SourceDoc(make_pdf(1, rotation=rot, cropbox=crop), "main")
                plan = build_plan("split2", src.infos(), overlap_mm=10)
                data = build_pdf(plan, {"main": src})
                words = set(self._words(data))
                orig = pymupdf.open("pdf", make_pdf(1, rotation=rot, cropbox=crop))
                expect = {w[4] for w in orig[0].get_text("words")}
                orig.close()
                self.assertTrue(expect)
                self.assertEqual(expect - words, set())

    def test_fit_and_nup_pages(self):
        src = SourceDoc(make_pdf(3), "main")
        d = pymupdf.open("pdf", build_pdf(build_plan("fit", src.infos(), sheet="A3"), {"main": src}))
        self.assertEqual(len(d), 3)
        self.assertAlmostEqual(d[0].rect.width, mm(297), 2)
        d.close()
        d = pymupdf.open("pdf", build_pdf(build_plan("nup", src.infos(), sheet="A4"), {"main": src}))
        self.assertEqual(len(d), 2)  # 홀수 페이지
        d.close()

    def test_source_unchanged_and_preview_equals_output(self):
        raw = make_pdf(2)
        src = SourceDoc(raw, "main")
        plan = build_plan("nup", src.infos(), sheet="A4")
        a = build_pdf(plan, {"main": src})
        b = build_pdf(plan, {"main": src}, [0])
        self.assertEqual(raster(a, 0).samples, raster(b, 0).samples)

    def test_extra_rotate_90_is_clockwise(self):
        src = SourceDoc(red_corner_pdf(), "main")
        info = src.page_info(0)
        from app.print_engine import Box, Placement, PrintPlan, Sheet
        sh = Sheet(300, 200, [Placement("main", 0, Box(0, 0, 200, 300), Box(0, 0, 300, 200), 90)])
        pm = raster(build_pdf(PrintPlan([sh]), {"main": src}), 0, 72)
        def red(x, y):
            p = pm.pixel(x, y)
            return p[0] > 200 and p[1] < 60
        # 시계방향 90°: 좌상단 → 우상단
        self.assertTrue(red(pm.width - 10, 10))
        self.assertFalse(red(10, 10))


if __name__ == "__main__":
    unittest.main()

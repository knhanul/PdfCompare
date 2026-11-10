import unittest

import pymupdf

from app.print_engine import (Margins, PageInfo, SourceDoc, build_pdf, build_plan, mm,
                              plan_fit_to_paper, plan_grid_split, plan_n_up)
from app.print_engine.units import paper
from tests.test_print_engine_core import Z, make_pdf

A4 = PageInfo(0, mm(210), mm(297))


def area(sheets):
    return sum(p.clip.w * p.clip.h for s in sheets for p in s.placements)


class GridSplitTest(unittest.TestCase):
    def test_counts_and_coverage(self):
        for n, cols, rows in ((2, None, None), (4, 2, 2), (6, None, None), (9, 3, 3)):
            sheets = plan_grid_split(A4, "A4", n=n, cols=cols, rows=rows, margins=Z, overlap_mm=5)
            self.assertEqual(len(sheets), n)
            xs = sorted({(p.clip.x0, p.clip.x1) for s in sheets for p in s.placements})
            ys = sorted({(p.clip.y0, p.clip.y1) for s in sheets for p in s.placements})
            self.assertAlmostEqual(min(a for a, _ in xs), 0)
            self.assertAlmostEqual(max(b for _, b in xs), A4.width)
            self.assertAlmostEqual(min(a for a, _ in ys), 0)
            self.assertAlmostEqual(max(b for _, b in ys), A4.height)
            # 인접 타일이 겹침(>=0)으로 이어짐: 격자 열/행 구간이 빈틈 없이 이어진다
            for iv in (xs, ys):
                cur = iv[0][1]
                for a, b in iv[1:]:
                    if a > cur + 1e-6 and b > cur:
                        self.assertLessEqual(a, cur + 1e-6, f"gap n={n}")
                    cur = max(cur, b)

    def test_dst_inside_printable_area_and_scale(self):
        m = Margins(mm(5), mm(5), mm(5), mm(5))
        for n in (2, 4, 6, 9):
            sheets = plan_grid_split(A4, "A4", n=n, margins=m, overlap_mm=10)
            for sh in sheets:
                for p in sh.placements:
                    d = p.dst
                    self.assertGreaterEqual(d.x0, m.left - 1e-6)
                    self.assertGreaterEqual(d.y0, m.top - 1e-6)
                    self.assertLessEqual(d.x1, sh.width - m.right + 1e-6)
                    self.assertLessEqual(d.y1, sh.height - m.bottom + 1e-6)
                    self.assertAlmostEqual(d.w / p.clip.w, d.h / p.clip.h, places=4)  # 종횡비

    def test_overlap_amount(self):
        sheets = plan_grid_split(A4, "A4", n=4, cols=2, rows=2, margins=Z, overlap_mm=10)
        s = sheets[0].placements[0]
        sc = s.dst.w / s.clip.w
        right = sheets[0].placements[0].clip.x1
        left2 = sheets[1].placements[0].clip.x0
        self.assertAlmostEqual((right - left2) * sc, mm(10), delta=0.5)

    def test_render_pdf_pages(self):
        src = SourceDoc(make_pdf(1), "main")
        plan = build_plan("split", src.infos(), sheet="A4", n=6, margins=Z, overlap_mm=5)
        data = build_pdf(plan, {"main": src})
        d = pymupdf.open("pdf", data)
        self.assertEqual(d.page_count, 6)
        d.close(); src.close()


class NUpTest(unittest.TestCase):
    def infos(self, n):
        return [PageInfo(i, mm(210), mm(297)) for i in range(n)]

    def test_sheet_counts(self):
        for n, pages, expect in ((2, 5, 3), (4, 9, 3), (6, 7, 2), (8, 8, 1), (9, 10, 2), (16, 17, 2)):
            sheets = plan_n_up(self.infos(pages), "A4", n=n, margins=Z)
            self.assertEqual(len(sheets), expect, f"n={n}")
            self.assertEqual(sum(len(s.placements) for s in sheets), pages)

    def test_no_overlap_inside_sheet(self):
        for n in (4, 6, 8, 9, 16):
            sh = plan_n_up(self.infos(n), "A4", n=n, margins=Z)[0]
            ps = [p.dst for p in sh.placements]
            for i, a in enumerate(ps):
                self.assertGreaterEqual(a.x0, -1e-6); self.assertLessEqual(a.x1, sh.width + 1e-6)
                for b in ps[i + 1:]:
                    sep = a.x1 <= b.x0 + 1e-6 or b.x1 <= a.x0 + 1e-6 or a.y1 <= b.y0 + 1e-6 or b.y1 <= a.y0 + 1e-6
                    self.assertTrue(sep, f"overlap n={n}")

    def test_4up_is_2x2_order(self):
        sh = plan_n_up(self.infos(4), "A4", n=4, margins=Z)[0]
        d = [p.dst for p in sh.placements]
        self.assertLess(d[0].x0, d[1].x0); self.assertAlmostEqual(d[0].y0, d[1].y0, delta=1)
        self.assertLess(d[0].y0, d[2].y0); self.assertAlmostEqual(d[0].x0, d[2].x0, delta=1)

    def test_orders(self):
        n_ord = plan_n_up(self.infos(4), "A4", n=4, margins=Z, order="N")[0].placements
        self.assertAlmostEqual(n_ord[0].dst.x0, n_ord[1].dst.x0, delta=1)   # 세로 우선
        rtl = plan_n_up(self.infos(4), "A4", n=4, margins=Z, order="Z_rtl")[0].placements
        self.assertGreater(rtl[0].dst.x0, rtl[1].dst.x0)

    def test_mixed_sizes_keep_aspect(self):
        infos = [PageInfo(0, mm(210), mm(297)), PageInfo(1, mm(297), mm(420)), PageInfo(2, 300, 100), PageInfo(3, 100, 300)]
        sh = plan_n_up(infos, "A4", n=4, margins=Z)[0]
        for p, inf in zip(sh.placements, infos):
            dw, dh = (p.dst.h, p.dst.w) if p.extra_rotate else (p.dst.w, p.dst.h)
            self.assertAlmostEqual(dw / dh, inf.width / inf.height, places=3)

    def test_min_scale_meta_for_legibility(self):
        plan = build_plan("nup", self.infos(16), sheet="A4", n=16, margins=Z)
        self.assertLess(plan.meta["min_scale"], 0.3)

    def test_borders_and_numbers(self):
        sh = plan_n_up(self.infos(4), "A4", n=4, margins=Z, border=True, numbers=True)[0]
        self.assertEqual(sum(m.kind == "page_boundary" for m in sh.marks), 16)
        self.assertEqual(sum(m.kind == "label" for m in sh.marks), 4)


class PaperTest(unittest.TestCase):
    def test_conversions_keep_aspect_and_orient(self):
        for src, dst in (((210, 297), "A3"), ((297, 420), "A4"), ((257, 364), "A4"), ((210, 297), "B4")):
            for land in (False, True):
                w, h = (mm(src[0]), mm(src[1])) if not land else (mm(src[1]), mm(src[0]))
                sh = plan_fit_to_paper(PageInfo(0, w, h), dst, Z)
                p = sh.placements[0]
                self.assertAlmostEqual(p.dst.w / p.dst.h, w / h, places=4)
                self.assertEqual(sh.width > sh.height, land)   # 방향 자동 조정
        self.assertAlmostEqual(paper("B4")[0], mm(257))


if __name__ == "__main__":
    unittest.main()


class TokenCoverageTest(unittest.TestCase):
    def test_no_token_lost_in_grid_split(self):
        import re
        for n, kw in ((4, dict(cols=2, rows=2)), (6, {}), (9, dict(cols=3, rows=3))):
            src = SourceDoc(make_pdf(1, step=14), "main")
            plan = build_plan("split", src.infos(), sheet="A4", n=n, margins=Margins(mm(5), mm(5), mm(5), mm(5)),
                              overlap_mm=8, marks=False, **kw)
            d = pymupdf.open("pdf", build_pdf(plan, {"main": src}))
            got = set(re.findall(r"P0Y\d+", "".join(pg.get_text() for pg in d)))
            ref = pymupdf.open("pdf", make_pdf(1, step=14))
            want = set(re.findall(r"P0Y\d+", ref[0].get_text()))
            self.assertEqual(want - got, set(), f"n={n}")
            d.close(); ref.close(); src.close()

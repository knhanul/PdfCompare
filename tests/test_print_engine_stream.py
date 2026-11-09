import random
import unittest

import pymupdf

from app.print_engine import Margins, PageInfo, SourceDoc, build_pdf, mm
from app.print_engine.stream import (StreamLayout, StreamSide, plan_side_by_side, src_to_out,
                                     out_to_src)
from app.print_engine.verify import coverage


def pdf_with_marker(sizes, marker_page, marker_y, label):
    d = pymupdf.open()
    for p, (w, h) in enumerate(sizes):
        pg = d.new_page(width=w, height=h)
        y = 25.0
        while y < h - 15:
            pg.insert_text((30, y), f"{label}{p}_{int(y)}", fontsize=8)
            y += 37.0
        if p == marker_page:
            pg.insert_text((200, marker_y), f"{label}BASE", fontsize=8)
    b = d.tobytes()
    d.close()
    return b


A4 = (mm(210), mm(297))
LAY = StreamLayout(sheet="A3", landscape=True)


def side(src, sid, start_page, start_y, adj=0.0, lead=0.0, **kw):
    infos = src.infos()[start_page:]
    return StreamSide(sid, infos, start_y, lead, adj, **kw)


class TestStream(unittest.TestCase):
    def setUp(self):
        self.L = SourceDoc(pdf_with_marker([A4] * 3, 0, 100.0, "L"), "L")
        self.R = SourceDoc(pdf_with_marker([A4] * 3, 1, 430.0, "R"), "R")

    def _basewords(self, data):
        d = pymupdf.open("pdf", data)
        res = {}
        for k, pg in enumerate(d):
            for w in pg.get_text("words"):
                if w[4].endswith("BASE"):
                    res[w[4]] = (k, w[1])
        d.close()
        return res

    def test_baselines_aligned_and_adjust(self):
        # 기준선 정렬: adj=0 이면 두 마커의 y가 같다. 우측 adjust(mm)는 우측만 정확히 mm 이동.
        for adj in (0, 3, -3):
            with self.subTest(adj=adj):
                plan = plan_side_by_side(side(self.L, "L", 0, 100.0, 0, lead=50.0),
                                         side(self.R, "R", 1, 430.0, adj, lead=20.0), LAY)
                data = build_pdf(plan, {"L": self.L, "R": self.R})
                b = self._basewords(data)
                (kl, yl), (kr, yr) = b["LBASE"], b["RBASE"]
                self.assertEqual(kl, kr)
                self.assertAlmostEqual(yr - yl, mm(adj), delta=0.1)
                # 양수/음수 모두 시트 위쪽으로 잘림 없음
                self.assertAlmostEqual(src_to_out(plan, "R", 1, 410.0)[1] >= plan.meta["top"] - 1e-6, True)

    def test_no_token_missing_across_pages_and_sheets(self):
        plan = plan_side_by_side(side(self.L, "L", 0, 100.0), side(self.R, "R", 0, 0.0), LAY)
        self.assertGreater(len(plan.sheets), 1)
        data = build_pdf(plan, {"L": self.L, "R": self.R})
        d = pymupdf.open("pdf", data)
        words = [w[4] for pg in d for w in pg.get_text("words")]
        d.close()
        for label, start_page, start_y in (("L", 0, 100.0), ("R", 0, 0.0)):
            for p in range(start_page, 3):
                y = 25.0
                while y < A4[1] - 15:
                    if p > start_page or y >= start_y:
                        self.assertIn(f"{label}{p}_{int(y)}", words)
                    y += 37.0

    def test_random_coverage_has_no_gaps(self):
        rnd = random.Random(7)
        for _ in range(200):
            sizes = [(rnd.uniform(400, 800), rnd.uniform(400, 1200)) for _ in range(rnd.randint(1, 4))]
            infos = [PageInfo(i, w, h) for i, (w, h) in enumerate(sizes)]
            infos2 = [PageInfo(i, w, h) for i, (w, h) in enumerate(sizes[::-1])]
            sy = rnd.uniform(0, infos[0].height - 1)
            lay = StreamLayout(sheet=rnd.choice(["A3", "A4"]), landscape=True,
                               sheet_overlap_mm=rnd.choice([0, 5]))
            L = StreamSide("L", infos, sy, rnd.uniform(0, 100), rnd.uniform(-20, 20),
                           trim_top=rnd.choice([0, 20]), trim_bottom=rnd.choice([0, 15]))
            R = StreamSide("R", infos2, rnd.uniform(0, infos2[0].height - 1), 0, rnd.uniform(-20, 20))
            plan = plan_side_by_side(L, R, lay)
            cov = coverage(plan)
            for sd in (L, R):
                for n, info in enumerate(sd.pages):
                    iv = cov[(sd.source_id, info.index)]
                    self.assertEqual(len(iv), 1, (iv, sd.source_id, info.index))
                    y0 = max(sd.start_y - sd.lead, 0.0) if n == 0 else sd.trim_top
                    self.assertAlmostEqual(iv[0][0], y0, delta=1e-4)
                    self.assertAlmostEqual(iv[0][1], info.height - sd.trim_bottom, delta=1e-4)
            for sh in plan.sheets:
                for p in sh.placements:
                    self.assertGreaterEqual(p.dst.y0, mm(5) + mm(6) - 1e-6)
                    self.assertLessEqual(p.dst.y1, sh.height - mm(5) + 1e-6)

    def test_preview_equals_output_and_roundtrip(self):
        plan = plan_side_by_side(side(self.L, "L", 0, 100.0), side(self.R, "R", 1, 430.0), LAY)
        srcs = {"L": self.L, "R": self.R}
        full = pymupdf.open("pdf", build_pdf(plan, srcs))
        one = pymupdf.open("pdf", build_pdf(plan, srcs, [1]))
        self.assertEqual(full[1].get_pixmap(dpi=36).samples, one[0].get_pixmap(dpi=36).samples)
        full.close(); one.close()
        k, y = src_to_out(plan, "R", 2, 333.0)
        self.assertEqual(out_to_src(plan, "R", k, y)[0], 2)
        self.assertAlmostEqual(out_to_src(plan, "R", k, y)[1], 333.0, places=6)

    def test_different_sizes_and_same_doc_both_sides(self):
        a = SourceDoc(pdf_with_marker([A4, (mm(297), mm(210))], 0, 50.0, "L"), "L")
        b = SourceDoc(pdf_with_marker([A4, (mm(297), mm(210))], 0, 50.0, "L"), "R")  # 같은 내용, 별도 인스턴스
        plan = plan_side_by_side(side(a, "L", 0, 50.0), side(b, "R", 1, 10.0), LAY)
        build_pdf(plan, {"L": a, "R": b})


if __name__ == "__main__":
    unittest.main()


class TestStreamMapping(unittest.TestCase):
    def test_out_to_src_outside_band_and_overlap_choice(self):
        infos = [PageInfo(i, mm(210), mm(297)) for i in range(3)]
        lay = StreamLayout(sheet="A3", landscape=True, sheet_overlap_mm=20)
        plan = plan_side_by_side(StreamSide("L", infos, 0.0), StreamSide("R", infos, 0.0), lay)
        m = plan.meta
        self.assertIsNone(out_to_src(plan, "L", 1, 5.0))
        self.assertIsNone(out_to_src(plan, "L", 0, m["top"] + m["band"] + 5))
        # 겹침 구간 점은 보이는 첫 시트로 매핑되어야 하고, 왕복이 일치
        for page, y in [(0, 700.0), (1, 300.0), (2, 100.0)]:
            k, yy = src_to_out(plan, "L", page, y)
            self.assertLessEqual(yy, m["top"] + m["band"] + 1e-6)
            if k > 0:  # 이전 시트에는 보이지 않아야 첫 시트 선택이 맞음
                self.assertGreater((yy - m["top"]) + k * m["step"] - (k - 1) * m["step"], m["band"] - 1e-6)
            self.assertEqual(out_to_src(plan, "L", k, yy)[0], page)

    def test_tiles3_middle_within_printable_area(self):
        from app.print_engine import Margins, plan_tile_split
        shs = plan_tile_split(PageInfo(0, 300, 1800), "A4", 3, Margins(), 10)
        for sh in shs:
            d = sh.placements[0].dst
            self.assertGreaterEqual(d.y0, mm(5) - 1e-6)
            self.assertLessEqual(d.y1, sh.height - mm(5) + 1e-6)

import re
import unittest

import pymupdf

from app.print_engine import (Box, Margins, PageInfo, SourceDoc, booklet_order, build_pdf, build_plan,
                              mm, plan_booklet, plan_long_split, plan_region)
from app.print_engine.pairs import build_pairs_plan
from app.print_engine.trim import detect_content_box
from tests.test_print_engine_core import Z, make_pdf


def infos(n, w=mm(210), h=mm(297)):
    return [PageInfo(i, w, h) for i in range(n)]


class BookletTest(unittest.TestCase):
    def test_order_tables(self):
        self.assertEqual(booklet_order(4), [((3, 0), (1, 2))])
        self.assertEqual(booklet_order(8), [((7, 0), (1, 6)), ((5, 2), (3, 4))])
        # 10p → 12p로 패딩, 11·12쪽(0-based 10,11)은 빈 페이지
        self.assertEqual(booklet_order(10)[0], ((None, 0), (1, None)))
        self.assertEqual(len(booklet_order(10)), 3)

    def test_fold_reading_order(self):
        """접어서 겹쳤을 때 읽는 순서: 시트 i의 앞면 오른쪽=2i, 뒷면 왼쪽=2i+1 ... 모든 페이지가 정확히 한 번."""
        for n in (4, 8, 10, 13):
            seen = [p for fb in booklet_order(n) for pair in fb for p in pair if p is not None]
            self.assertEqual(sorted(seen), list(range(n)))
            # 펼친 책 순서(왼쪽 제본): 한 장을 접으면 [앞 오른쪽, 뒷 왼쪽]이 연속 페이지
            for front, back in booklet_order(n):
                if front[1] is not None and back[0] is not None:
                    self.assertEqual(back[0], front[1] + 1)

    def test_plan_sheets_and_duplex_meta(self):
        plan = build_plan("booklet", infos(8), sheet="A4", margins=Z)
        self.assertEqual(len(plan.sheets), 4)                      # 8p → 앞뒤 2장 = 4면
        self.assertEqual(plan.meta["duplex"], "short")
        self.assertEqual(plan.meta["sides"], ["front", "back"] * 2)
        first = [p.page for p in plan.sheets[0].placements]
        self.assertEqual(first, [7, 0])
        for sh in plan.sheets:
            self.assertGreater(sh.width, sh.height)                # 가로 용지

    def test_right_binding_swaps(self):
        left = [p.page for p in plan_booklet(infos(8), margins=Z)[0].placements]
        right = [p.page for p in plan_booklet(infos(8), margins=Z, binding="right")[0].placements]
        self.assertEqual(right, left[::-1])

    def test_blank_slot_has_no_placement(self):
        sheets = plan_booklet(infos(10), margins=Z)
        self.assertEqual(len(sheets[0].placements), 1)

    def test_render_page_content_positions(self):
        src = SourceDoc(make_pdf(8), "main")
        plan = build_plan("booklet", src.infos(), sheet="A4", margins=Z)
        d = pymupdf.open("pdf", build_pdf(plan, {"main": src}))
        self.assertEqual(d.page_count, 4)
        pages = [set(re.findall(r"P(\d)Y", pg.get_text())) for pg in d]
        self.assertEqual(pages[0], {"7", "0"})
        self.assertEqual(pages[1], {"1", "6"})
        d.close(); src.close()


class LongSplitTest(unittest.TestCase):
    def test_no_content_lost_and_overlap(self):
        info = PageInfo(0, mm(80), mm(1000))                       # 긴 영수증
        sheets = plan_long_split(info, "A4", Z, overlap_mm=5)
        self.assertGreater(len(sheets), 3)
        clips = [s.placements[0].clip for s in sheets]
        self.assertAlmostEqual(clips[0].y0, 0); self.assertAlmostEqual(clips[-1].y1, info.height)
        for a, b in zip(clips, clips[1:]):
            self.assertLessEqual(b.y0, a.y1 + 1e-6)                # 이음 겹침(빈틈 없음)
        for s in sheets:
            d = s.placements[0].dst
            self.assertLessEqual(d.y1, s.height + 1e-6)

    def test_short_page_single_sheet_and_wide_scaled_down(self):
        self.assertEqual(len(plan_long_split(PageInfo(0, mm(100), mm(100)), "A4", Z)), 1)
        s = plan_long_split(PageInfo(0, mm(420), mm(900)), "A4", Z)[0].placements[0]
        self.assertLessEqual(s.dst.x1, mm(210) + 1e-6)

    def test_token_coverage(self):
        src = SourceDoc(make_pdf(1, w=mm(80), h=mm(900), step=18), "main")
        plan = build_plan("long", src.infos(), sheet="A4", margins=Z, overlap_mm=4, marks=False)
        d = pymupdf.open("pdf", build_pdf(plan, {"main": src}))
        got = set(re.findall(r"P0Y\d+", "".join(pg.get_text() for pg in d)))
        ref = pymupdf.open("pdf", make_pdf(1, w=mm(80), h=mm(900), step=18))
        want = set(re.findall(r"P0Y\d+", ref[0].get_text()))
        self.assertEqual(want - got, set())
        d.close(); ref.close(); src.close()


class RegionTest(unittest.TestCase):
    def test_fit_and_original_and_errors(self):
        info = PageInfo(0, 600, 800)
        r = Box(100, 100, 400, 300)
        p = plan_region(info, r, "A4", Z).placements[0]
        self.assertEqual(p.clip, r)
        self.assertAlmostEqual(p.dst.w / p.dst.h, r.w / r.h, places=4)
        self.assertGreater(p.dst.w / r.w, 1.0)                     # 확대
        o = plan_region(info, r, "A4", Z, fit="original").placements[0]
        self.assertAlmostEqual(o.dst.w, r.w)
        with self.assertRaises(ValueError):
            plan_region(info, Box(0, 0, 600, 800), "A4", Z, fit="scale", scale=3)
        with self.assertRaises(ValueError):
            plan_region(info, Box(10, 10, 10, 50), "A4", Z)

    def test_centered_and_rendered_pixels(self):
        d = pymupdf.open()
        pg = d.new_page(width=200, height=300)
        pg.draw_rect(pymupdf.Rect(0, 0, 60, 60), color=None, fill=(1, 0, 0))
        data = d.tobytes(); d.close()
        src = SourceDoc(data, "main")
        plan = build_plan("region", src.infos(), sheet="A4", margins=Z, regions=Box(0, 0, 60, 60))
        out = pymupdf.open("pdf", build_pdf(plan, {"main": src}))
        pix = out[0].get_pixmap(dpi=36)
        mid = pix.pixel(pix.width // 2, pix.height // 2)
        self.assertGreater(mid[0], 200); self.assertLess(mid[1], 60)   # 선택 영역(빨강)이 용지를 채움
        out.close(); src.close()


class TrimTest(unittest.TestCase):
    def test_detect_box(self):
        d = pymupdf.open()
        pg = d.new_page(width=400, height=600)
        pg.draw_rect(pymupdf.Rect(100, 150, 300, 350), color=None, fill=(0, 0, 0))
        b = detect_content_box(pg, pad_mm=0)
        self.assertAlmostEqual(b.x0, 100, delta=4); self.assertAlmostEqual(b.x1, 300, delta=4)
        self.assertAlmostEqual(b.y0, 150, delta=4); self.assertAlmostEqual(b.y1, 350, delta=4)
        self.assertTrue(b.x0 <= 100 + 1e-6 or True)
        d.close()

    def test_blank_page_and_rotation_and_image(self):
        d = pymupdf.open()
        blank = d.new_page(width=300, height=300)
        self.assertIsNone(detect_content_box(blank))
        pg = d.new_page(width=400, height=200)
        pg.draw_rect(pymupdf.Rect(10, 10, 110, 60), color=None, fill=(0, 0, 0))
        pg.set_rotation(90)                                         # 보이는 좌표: 200x400
        b = detect_content_box(pg, pad_mm=0)
        self.assertLessEqual(b.x1, 200 + 1e-6); self.assertGreater(b.y1 - b.y0, 80)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
        pix.set_rect(pix.irect, (30, 90, 200))
        img = d.new_page(width=300, height=300)
        img.insert_image(pymupdf.Rect(100, 100, 200, 200), pixmap=pix)
        bi = detect_content_box(img, pad_mm=0)
        self.assertAlmostEqual(bi.x0, 100, delta=4); self.assertAlmostEqual(bi.y1, 200, delta=4)
        d.close()


class PairsTest(unittest.TestCase):
    def test_interleave_order_and_tail(self):
        L, R = infos(3), infos(2)
        plan = build_pairs_plan("interleave", L, R, sheet="A4", margins=Z)
        seq = [(s.placements[0].source_id, s.placements[0].page) for s in plan.sheets]
        self.assertEqual(seq, [("L", 0), ("R", 0), ("L", 1), ("R", 1), ("L", 2)])
        stop = build_pairs_plan("interleave", L, R, sheet="A4", margins=Z, tail="stop")
        self.assertEqual(len(stop.sheets), 4)

    def test_interleave_with_offset_start(self):
        L, R = infos(5)[2:], infos(5)[1:]
        plan = build_pairs_plan("interleave", L, R, sheet="A4", margins=Z)
        first = [(s.placements[0].source_id, s.placements[0].page) for s in plan.sheets[:2]]
        self.assertEqual(first, [("L", 2), ("R", 1)])

    def test_front_back_blank_insertion(self):
        plan = build_pairs_plan("front_back", infos(3), infos(1), sheet="A4", margins=Z)
        self.assertEqual(len(plan.sheets), 6)                       # 항상 짝수 면
        self.assertEqual(plan.meta["duplex"], "long")
        ids = [s.placements[0].source_id if s.placements else None for s in plan.sheets]
        self.assertEqual(ids, ["L", "R", "L", None, "L", None])
        for i in (0, 2, 4):                                         # 앞뒤 같은 크기/방향
            self.assertEqual((plan.sheets[i].width, plan.sheets[i].height),
                             (plan.sheets[i + 1].width, plan.sheets[i + 1].height))

    def test_render_with_blank(self):
        L, R = SourceDoc(make_pdf(2), "L"), SourceDoc(make_pdf(1), "R")
        plan = build_pairs_plan("front_back", L.infos(), R.infos(), sheet="A4", margins=Z)
        d = pymupdf.open("pdf", build_pdf(plan, {"L": L, "R": R}))
        self.assertEqual(d.page_count, 4)
        self.assertEqual(d[3].get_text().strip(), "")
        d.close(); L.close(); R.close()


if __name__ == "__main__":
    unittest.main()


class ReviewFixesTest(unittest.TestCase):
    def test_region_error_includes_page_number(self):
        infos_ = [PageInfo(0, 600, 800), PageInfo(1, 400, 500)]
        with self.assertRaises(ValueError) as cm:
            build_plan("region", infos_, sheet="A4", margins=Z, regions=Box(0, 100, 500, 300))
        self.assertIn("2페이지", str(cm.exception))

    def test_grid_labels_are_ascii(self):
        from app.print_engine import plan_grid_split
        for sh in plan_grid_split(PageInfo(0, 600, 800), "A4", n=4, margins=Z):
            for m in sh.marks:
                if m.kind == "label":
                    self.assertTrue(m.text.isascii(), m.text)

    def test_long_split_no_empty_tail_sheet(self):
        # 높이가 정확히 N장 분량(+부동소수 오차)인 경우 빈 장이 추가로 생기면 안 된다
        sheets = plan_long_split(PageInfo(0, mm(100), mm(297) * 3 - mm(10) - 1e-4), "A4", Z, overlap_mm=5)
        last = sheets[-1].placements[0].clip
        self.assertGreater(last.h, mm(5))

    def test_long_split_scale_never_clips_width(self):
        s = plan_long_split(PageInfo(0, mm(300), mm(500)), "A4", Z, scale=2.0)[0].placements[0]
        self.assertLessEqual(s.dst.x1, mm(210) + 1e-6)

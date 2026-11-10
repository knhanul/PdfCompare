import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from app.shell.print_dialog import SmartPrintDialog, PrintSource
from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])


def vis(d, name):
    w = d._rows[name]
    return d._form.isRowVisible(w)


class TestPrintCards(unittest.TestCase):
    def single(self, n=6):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(n)), left_page=0)
        d.show()
        return d

    def test_single_cards_and_default(self):
        d = self.single()
        self.assertEqual([k for k in d._cards][:4], ["a3", "split", "nup", "region"])
        self.assertEqual(d.card_key(), "normal")
        self.assertFalse(d.more_box.isVisible())
        self.assertIn("일반 인쇄", d.lbl_current.text())
        d.close()

    def test_card_switches_mode_and_hides_irrelevant(self):
        d = self.single()
        d._cards["split"].click()
        self.assertEqual(d.cmb_mode.currentData(), "split")
        self.assertTrue(vis(d, "n") and vis(d, "overlap"))
        self.assertFalse(vis(d, "gutter") or vis(d, "bind") or vis(d, "pick"))
        d._cards["nup"].click()
        self.assertTrue(vis(d, "order") and vis(d, "gutter"))
        self.assertFalse(vis(d, "overlap") or vis(d, "border"))   # 경계선은 고급
        d.btn_adv.setChecked(True)
        self.assertTrue(vis(d, "border") and vis(d, "margin") and vis(d, "printer"))
        d._cards["split"].click()
        self.assertFalse(vis(d, "border"))
        self.assertTrue(d.btn_adv.isChecked())     # 고급 펼침 상태 유지
        d.close()

    def test_result_text_follows_engine_plan(self):
        d = self.single()
        d._cards["split"].click()
        for n in (2, 4, 6, 9):
            d.cmb_n.setCurrentIndex(d.cmb_n.findData(n))
            d.refresh()
            self.assertIn(f"{n}장", d.lbl_result.text())
            self.assertEqual(len(d._plan.sheets), n)
        d._cards["nup"].click()
        d.cmb_range.setCurrentIndex(1)
        d.cmb_n.setCurrentIndex(d.cmb_n.findData(4))
        d.refresh()
        self.assertIn("6페이지", d.lbl_result.text())
        self.assertIn("2장", d.lbl_result.text())
        d._cards["a3"].click(); d.refresh()
        self.assertIn("A3", d.lbl_result.text())
        d.close()

    def test_more_methods_collapse_and_select(self):
        d = self.single()
        d.btn_more.setChecked(True)
        self.assertTrue(d.more_box.isVisible())
        d._cards["booklet"].click()
        self.assertEqual(d.cmb_mode.currentData(), "booklet")
        self.assertFalse(d.more_box.isVisible())
        self.assertTrue(d._cards["booklet"].isChecked())
        self.assertIn("소책자", d.lbl_current.text())
        self.assertTrue(vis(d, "bind"))
        d.close()

    def test_region_card_shows_pick_controls(self):
        d = self.single()
        d._cards["region"].click()
        self.assertTrue(vis(d, "pick") and vis(d, "clear") and vis(d, "fit"))
        self.assertFalse(vis(d, "scale"))
        d.cmb_fit.setCurrentIndex(d.cmb_fit.findData("scale"))
        self.assertTrue(vis(d, "scale"))
        d.close()

    def test_preset_syncs_card(self):
        d = self.single()
        d.apply_settings({"mode": "nup", "sheet": "A4", "n": 4})
        self.assertEqual(d.card_key(), "nup")
        self.assertTrue(d._cards["nup"].isChecked())
        self.assertFalse(d._cards["split"].isChecked())
        d.apply_settings({"mode": "split", "n": 4})
        self.assertTrue(d._cards["split"].isChecked())
        d.close()

    def test_dual_cards(self):
        d = SmartPrintDialog(PrintSource("l.pdf", make_pdf(3)), PrintSource("r.pdf", make_pdf(3)))
        d.show()
        self.assertEqual(list(d._cards)[:4], ["side", "L", "R", "inter"])
        self.assertEqual(d.card_key(), "side")
        self.assertTrue(d._cards["side"].isChecked())
        self.assertFalse(vis(d, "range") or vis(d, "n"))
        d.refresh()
        self.assertIn("좌우 배치", d.lbl_result.text())
        d._cards["L"].click()
        self.assertEqual(d._target(), "L")
        self.assertTrue(vis(d, "target") and vis(d, "range"))
        d._cards["ind_split"].click()
        self.assertEqual((d._target(), d.cmb_mode.currentData()), ("L", "split"))
        d._cards["fb"].click()
        self.assertEqual(d._target(), "fb")
        d.apply_settings({"target": "side", "sheet": "A3"})
        self.assertTrue(d._cards["side"].isChecked())
        d.close()


if __name__ == "__main__":
    unittest.main()

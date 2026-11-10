import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from app.services import print_presets
from app.shell.print_dialog import PrintSource, SmartPrintDialog
from tests.test_print_engine_core import make_pdf

_app = QApplication.instance() or QApplication([])
_mem = {}


class FakeSettings:
    def __init__(self, *a): pass
    def value(self, k, d=None): return _mem.get(k, d)
    def setValue(self, k, v): _mem[k] = v


class PresetTest(unittest.TestCase):
    def setUp(self):
        _mem.clear()
        self.p = mock.patch.object(print_presets, "QSettings", FakeSettings)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_builtin_and_user_crud(self):
        self.assertIn("A3 나란히 비교 출력", print_presets.names())
        print_presets.save("내 설정", {"mode": "nup", "n": 4, "pdf_path": "C:/x.pdf", "region": [1, 2]})
        self.assertEqual(print_presets.get("내 설정"), {"mode": "nup", "n": 4})   # 문서별 값 제외
        self.assertIn("내 설정", print_presets.names())
        with self.assertRaises(ValueError):
            print_presets.save("일반 A4 출력", {})
        with self.assertRaises(ValueError):
            print_presets.delete("일반 A4 출력")
        print_presets.delete("내 설정")
        self.assertNotIn("내 설정", print_presets.names())

    def test_apply_in_dialog_and_roundtrip(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(8)), left_page=0)
        d.apply_settings(print_presets.get("A4 4페이지 모아찍기"))
        self.assertEqual((d.cmb_mode.currentData(), d.cmb_n.currentData()), ("nup", 4))
        d.cmb_range.setCurrentIndex(1); d.refresh()
        self.assertEqual(len(d._plan.sheets), 2)
        d.apply_settings(print_presets.get("A4 4장 확대분할"))
        self.assertEqual((d.cmb_mode.currentData(), d.cmb_n.currentData()), ("split", 4))
        # 단일 문서에서는 '나란히' 대상이 적용되지 않고 안내가 표시된다
        d.apply_settings(print_presets.get("A3 나란히 비교 출력"))
        self.assertIn("두 PDF", d.lbl_notice.text())
        self.assertEqual(d.cmb_sheet.currentText(), "A3")
        # 사용자 저장
        d.cmb_mode.setCurrentIndex([d.cmb_mode.itemData(i) for i in range(d.cmb_mode.count())].index("nup"))
        d.sp_margin.setValue(12)
        with mock.patch("app.shell.print_dialog.QInputDialog.getText", return_value=("여백12", True)):
            d.save_preset()
        self.assertEqual(d.cmb_preset.currentData(), "여백12")
        d.sp_margin.setValue(3)
        d.apply_settings(print_presets.get("여백12"))
        self.assertEqual(d.sp_margin.value(), 12)
        d.close()

    def test_preset_keeps_existing_notice(self):
        d = SmartPrintDialog(PrintSource("a.pdf", make_pdf(2), modified=True), left_page=0)
        self.assertIn("저장되지 않은", d.lbl_notice.text())
        d.apply_settings(print_presets.get("A4 2장 확대분할"))
        self.assertIn("저장되지 않은", d.lbl_notice.text())
        d.close()

    def test_dual_side_preset(self):
        d = SmartPrintDialog(PrintSource("l.pdf", make_pdf(2)), PrintSource("r.pdf", make_pdf(2)))
        d.cmb_target.setCurrentIndex(1)
        d.apply_settings(print_presets.get("A3 나란히 비교 출력"))
        self.assertEqual(d._target(), "side")
        self.assertEqual(d.cmb_sheet.currentText(), "A3")
        d.close()


if __name__ == "__main__":
    unittest.main()

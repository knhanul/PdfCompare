import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.tools.pdf_create import PdfCreateWidget
from app.tools.pdf_editor import PdfEditorWidget


class PdfToolLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_function_tabs_fit_beside_grid_at_compact_width(self):
        for tool_class in (PdfEditorWidget, PdfCreateWidget):
            with self.subTest(tool=tool_class.__name__):
                tool = tool_class()
                self.addCleanup(tool.close)
                tool.resize(850, 620)
                tool.show()
                self.app.processEvents()

                splitter = tool.splitter
                sidebar = splitter.widget(1)
                self.assertEqual(tool.width(), 850)
                self.assertGreaterEqual(sidebar.width(), sidebar.minimumWidth())
                self.assertLessEqual(sidebar.x() + sidebar.width(), splitter.width())
                self.assertFalse(sidebar.horizontalScrollBar().isVisible())

                tabs = tool.tabs if isinstance(tool, PdfEditorWidget) else tool.action_tabs
                for index in range(tabs.count()):
                    tabs.setCurrentIndex(index)
                    self.app.processEvents()
                    self.assertFalse(sidebar.horizontalScrollBar().isVisible())

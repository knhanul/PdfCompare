"""Theme persistence, actual widget palettes and live switching regressions."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app.shell.theme import THEMES, TOKENS, THEME_CHOICES, build_shell_qss, theme_tokens


@pytest.fixture
def theme_env(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    from app.services import app_settings, recent_docs, workspace_session
    app = QApplication.instance() or QApplication([])
    ini = str(tmp_path / 'workspace.ini')
    for module in (app_settings, recent_docs, workspace_session):
        monkeypatch.setattr(module, '_settings', lambda: QSettings(ini, QSettings.Format.IniFormat))
    yield app


def test_default_and_unknown_theme(theme_env):
    from app.services import app_settings
    assert app_settings.DEFAULTS['ui/theme'] == 'default'
    assert app_settings.get('ui/theme') == 'default'
    assert THEMES['default'] == TOKENS
    assert build_shell_qss() == build_shell_qss('unknown')
    palette = theme_tokens('silver')
    palette['accent'] = 'changed'
    assert THEMES['silver']['accent'] != 'changed'


@pytest.mark.parametrize('theme_id', list(THEMES))
def test_settings_persist_and_apply_live(theme_env, theme_id):
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QFrame, QPushButton
    from app.main_window import MdiMainWindow
    from app.services import app_settings
    from app.shell.settings_page import SettingsPage
    w = MdiMainWindow()
    try:
        w.show()
        w.show_settings()
        page = w.settings_page
        assert [page.theme.itemText(i) for i in range(page.theme.count())] == [t for _, t in THEME_CHOICES]
        # Always exercise a real change, including when testing the default.
        page.theme.setCurrentIndex(page.theme.findData('black' if theme_id != 'black' else 'silver'))
        changes = []
        page.settings_changed.connect(changes.append)
        page.theme.setCurrentIndex(page.theme.findData(theme_id))
        theme_env.processEvents()
        assert changes == ['ui/theme']
        assert app_settings.get('ui/theme') == theme_id
        assert build_shell_qss(theme_id) in w.styleSheet()
        tokens = theme_tokens(theme_id)
        assert w.sidebar.palette().color(QPalette.ColorRole.Window).name().upper() == tokens['sidebar_bg']
        header = w.findChild(QFrame, 'headerBar')
        assert header.palette().color(QPalette.ColorRole.Window).name().upper() == tokens['app_bg']
        assert w.header_title.palette().color(QPalette.ColorRole.WindowText).name().upper() == tokens['text']
        assert page.theme.palette().color(QPalette.ColorRole.Base).name().upper() == tokens['panel_bg']
        primary = w.welcome_page.findChild(QPushButton, 'primaryBtn')
        assert primary.palette().color(QPalette.ColorRole.Button).name().upper() == tokens['accent']
        # Recreating the settings page must load the saved key, not its label.
        restored = SettingsPage(w)
        assert restored.theme.currentData() == theme_id
        restored.deleteLater()
        # Changing chrome does not replace/rebuild the settings page.
        assert w.mode_stack.currentWidget() is page
        page._reset()
        theme_env.processEvents()
        assert app_settings.get('ui/theme') == 'default'
        assert page.theme.currentData() == 'default'
        assert build_shell_qss('default') in w.styleSheet()
    finally:
        w.close()
        w.deleteLater()
        theme_env.processEvents()


@pytest.mark.parametrize('theme_id', list(THEMES) + ['removed-theme'])
def test_saved_theme_used_at_startup(theme_env, theme_id):
    from app.main_window import MdiMainWindow
    from app.services import app_settings
    app_settings.set('ui/theme', theme_id)
    w = MdiMainWindow()
    try:
        assert build_shell_qss(theme_id) in w.styleSheet()
        w.blink_state = False
        w.toggle_button_blink()
        assert theme_tokens(theme_id)['selected'] in w.legend_caution_btn.styleSheet()
        w.apply_settings('ui/theme')
        assert not w.legend_caution_btn.styleSheet()
    finally:
        w.close()
        w.deleteLater()
        theme_env.processEvents()

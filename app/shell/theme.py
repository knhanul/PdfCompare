"""Design tokens for the viewer-first shell (warm greige + terracotta).

Appended after the legacy MODERN_QSS so existing tool styling is untouched.
"""
TOKENS = {
    'app_bg': '#F5F2F0',
    'sidebar_bg': '#EAE7E4',
    'canvas_bg': '#E7E3DF',
    'panel_bg': '#FBFAF9',
    'text': '#292D33',
    'text_muted': '#77706D',
    'accent': '#A44735',
    'accent_hover': '#873729',
    'selected': '#F5EAE6',
    'hover': '#EFEAE7',
    'warning_bg': '#FFF4E0',
    'border': '#DED8D5',
    'radius': '6px',
    'toolbar_h': '36px',
}

SHELL_QSS = """
QWidget#welcomePage {{ background: {app_bg}; }}
QLabel#welcomeTitle {{ font-size: 20px; font-weight: 600; color: {text}; }}
QLabel#sectionLabel {{ font-size: 12px; font-weight: 600; color: {text_muted}; margin-top: 6px; }}
QLabel#mutedLabel {{ color: {text_muted}; }}
QFrame#dropZone {{ background: {panel_bg}; border: 1px dashed {border}; border-radius: 8px; }}
QPushButton#primaryBtn {{ background: {accent}; color: white; border: none; border-radius: {radius};
    padding: 6px 16px; font-weight: 600; }}
QPushButton#primaryBtn:hover {{ background: {accent_hover}; }}
QPushButton#shortcutTile {{ background: {panel_bg}; border: 1px solid {border}; border-radius: 8px;
    padding: 10px 12px; text-align: left; color: {text}; min-height: 44px; }}
QPushButton#shortcutTile:hover {{ background: {selected}; border-color: {accent}; }}
QListWidget#recentList {{ background: {panel_bg}; border: 1px solid {border}; border-radius: 8px; padding: 4px; }}
QListWidget#recentList::item {{ padding: 5px 6px; border-radius: 4px; }}
QListWidget#recentList::item:hover {{ background: {hover}; }}
QTabBar#docTabs {{ background: {sidebar_bg}; }}
QTabBar#docTabs::tab {{ background: transparent; padding: 6px 12px; border: none; max-width: 220px;
    color: {text_muted}; }}
QTabBar#docTabs::tab:selected {{ background: {panel_bg}; color: {text}; border-top: 2px solid {accent}; }}
QTabBar#docTabs::tab:hover {{ background: {hover}; }}
QFrame#viewerToolbar, QFrame#contextToolbar, QFrame#splitPaneBar {{ background: {panel_bg};
    border-bottom: 1px solid {border}; }}
QLabel#contextTitle, QLabel#splitPaneTitle {{ font-weight: 600; color: {text}; }}
QPushButton#viewerToolBtn {{ background: transparent; border: 1px solid transparent; border-radius: {radius};
    padding: 4px 8px; min-height: 22px; color: {text}; }}
QPushButton#viewerToolBtn:hover {{ background: {hover}; border-color: {border}; }}
QLineEdit#pageEdit {{ padding: 2px; }}
QListWidget#navPanel {{ background: {sidebar_bg}; border: none; border-right: 1px solid {border}; }}
QListWidget#navPanel::item:selected {{ background: {selected}; color: {accent}; }}
QFrame#formBanner {{ background: {warning_bg}; border-bottom: 1px solid {border}; }}
QLabel#sidebarGroupLabel {{ color: {text_muted}; font-size: 11px; font-weight: 600; padding: 8px 4px 2px 4px; }}
""".format(**TOKENS)

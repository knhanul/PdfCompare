"""Selectable shell palettes (default: warm greige + terracotta).

Append generated QSS after MODERN_QSS. Tool-local styles stay independent.
"""
TOKENS = {
    'app_bg': '#F5F2F0',
    'sidebar_bg': '#F3F0ED',
    'sidebar_border': '#E2DED9',
    'sidebar_text': '#5C5550',
    'sidebar_icon': '#8A827A',
    'sidebar_group': '#A39B93',
    'sidebar_active_bg': 'rgba(164, 71, 53, 0.08)',
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

THEME_CHOICES = [('default', '기본'), ('energy', '역동'), ('silver', '실버'),
                 ('gold', '골드'), ('black', '블랙')]

# Keep the original TOKENS intact; only UI chrome, never official logos or PDF
# page content, uses these palettes.
THEMES = {
    'default': dict(TOKENS),
    'energy': dict(TOKENS, sidebar_active_bg='rgba(255, 72, 5, 0.08)', sidebar_border='#DED9D3', app_bg='#F7F5F2', sidebar_bg='#ECE9E5',
                   panel_bg='#FCFBF9', accent='#FF4805', accent_hover='#D83B00',
                   selected='#FFF0E6', hover='#F2EBE5', border='#DED9D3'),
    'silver': dict(TOKENS, sidebar_active_bg='rgba(83, 101, 119, 0.12)', sidebar_border='#C5CCD3',
                   sidebar_text='#3E4750', sidebar_icon='#6F7A85', sidebar_group='#7D8792', app_bg='#F1F3F5', sidebar_bg='#DDE1E5',
                   canvas_bg='#D7DCE1', panel_bg='#FAFBFC', text='#252B32',
                   text_muted='#626D78', accent='#536577', accent_hover='#3F5061',
                   selected='#E1E7EE', hover='#E9EDF1', warning_bg='#F0EDE4',
                   border='#C5CCD3'),
    'gold': dict(TOKENS, sidebar_active_bg='rgba(128, 99, 45, 0.12)', sidebar_border='#D5C9AB',
                 sidebar_text='#4A4232', sidebar_icon='#857859', sidebar_group='#968A6D', app_bg='#F6F3EB', sidebar_bg='#E7DFC9',
                 canvas_bg='#E3DDCF', panel_bg='#FCFAF4', text='#342F25',
                 text_muted='#786D55', accent='#80632D', accent_hover='#644C20',
                 selected='#EFE4C8', hover='#F0EBDD', warning_bg='#F6EBCF',
                 border='#D5C9AB'),
    'black': dict(TOKENS, sidebar_active_bg='rgba(175, 196, 218, 0.14)', sidebar_border='#2E3036',
                  sidebar_text='#D2D5DB', sidebar_icon='#9AA0AA', sidebar_group='#7E848E', app_bg='#202124', sidebar_bg='#17181B',
                  canvas_bg='#111214', panel_bg='#292B30', text='#ECEEF2',
                  text_muted='#ADB2BC', accent='#AFC4DA', accent_hover='#CDDEEF',
                  selected='#384452', hover='#34373D', warning_bg='#433B29',
                  border='#484C54'),
}


def theme_tokens(theme_id='default'):
    """Return an independent palette; unknown saved IDs use the default."""
    return dict(THEMES.get(theme_id, THEMES['default']))


_SHELL_TEMPLATE = """
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
QPushButton#viewerToolBtn:checked {{ background: {selected}; border-color: {accent}; color: {accent}; }}
QFrame#workPanel, QFrame#globalSearchPanel {{ background: {panel_bg}; border-left: 1px solid {border}; }}
QWidget#settingsPage {{ background: {app_bg}; }}
QDialog#commandPalette {{ background: {panel_bg}; border: 1px solid {border}; border-radius: 8px; }}
QDialog#commandPalette QListWidget {{ border: none; }}
QDialog#commandPalette QListWidget::item:selected {{ background: {selected}; color: {accent}; }}
QWidget#docTabRow {{ background: {sidebar_bg}; }}
QDialog#openDocPicker {{ background: {panel_bg}; }}
QListWidget#openDocList {{ background: {panel_bg}; border: 1px solid {border}; border-radius: {radius}; }}
QListWidget#openDocList::item {{ padding: 6px 8px; border-radius: 4px; }}
QListWidget#openDocList::item:selected {{ background: {selected}; color: {accent}; }}
QListWidget#openDocList::item:hover {{ background: {hover}; }}
"""


# Explicit ID/state selectors win over the legacy warm sidebar/header rules.
_CHROME_TEMPLATE = """
QWidget {{ color: {text}; background-color: {app_bg}; }}
QMainWindow, QDialog, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {app_bg}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; color: {text}; }}
QWidget:disabled {{ color: {text_muted}; }}
QFrame#sidebar {{ background: {sidebar_bg}; border: none; border-right: 1px solid {sidebar_border}; }}
QFrame#sidebar QLabel, QFrame#sidebarLogoCard, QFrame#sidebarFooter {{ background: transparent; }}
QFrame#sidebarLogoCard {{ border: none; }}
QFrame#sidebarFooter {{ border: none; border-top: 1px solid {sidebar_border}; }}
QLabel#sidebarBrandTitle {{ color: {text}; font-size: 13px; font-weight: 700; }}
QLabel#sidebarBrandSubtitle {{ color: {text_muted}; font-size: 11px; }}
QPushButton#hamburgerBtn {{ color: {accent}; }}
QLabel#headerTarget {{ color: {text_muted}; }}
QLabel#sidebarGroupLabel {{ color: {sidebar_group}; font-size: 11px; font-weight: 600; letter-spacing: 1px; padding: 12px 10px 4px 10px; }}
QPushButton#sidebarBtn {{ color: {sidebar_text}; background: transparent; border: none; border-left: 2px solid transparent;
    border-radius: 6px; padding: 0 10px; min-height: 34px; max-height: 34px; text-align: left; font-size: 13px; font-weight: 500; }}
QPushButton#sidebarBtn[collapsed='true'] {{ padding: 0; text-align: center; color: {sidebar_text}; }}
QPushButton#sidebarBtn:hover {{ background: {hover}; color: {text}; }}
QPushButton#sidebarBtn[active='true'] {{ background: {sidebar_active_bg}; color: {accent}; border-left: 2px solid {accent};
    border-top-left-radius: 0; border-bottom-left-radius: 0; font-weight: 600; }}
QFrame#headerBar {{ background: {app_bg}; border-bottom: 1px solid {border}; }}
QLabel#headerTitle {{ color: {text}; }}
QFrame#headerAccent {{ background: {accent}; }}
QPushButton#headerLegendBtn, QPushButton#headerFocusBtn {{ background: {panel_bg}; color: {accent}; border-color: {border}; }}
QPushButton#headerLegendBtn:hover, QPushButton#headerLegendBtn:pressed,
QPushButton#headerFocusBtn:hover, QPushButton#headerFocusBtn:checked {{ background: {selected}; color: {accent}; border-color: {accent}; }}
QPushButton#headerLegendBtn:disabled {{ background: {app_bg}; color: {text_muted}; border-color: {border}; }}
#infoBtn, #closeToolBtn {{ color: {text_muted}; }}
#infoBtn:hover, #infoBtn:pressed, #closeToolBtn:hover, #closeToolBtn:pressed,
QPushButton#hamburgerBtn:hover, QPushButton#hamburgerBtn:pressed {{ background: {hover}; }}
QPushButton {{ background: {panel_bg}; color: {text}; border-color: {border}; }}
QPushButton:hover, QPushButton:pressed {{ background: {hover}; color: {text}; border-color: {border}; }}
QPushButton:disabled {{ color: {text_muted}; background: {sidebar_bg}; }}
QPushButton#primaryBtn, QPushButton#primaryBtn:hover {{ color: {on_accent}; }}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
QListWidget, QTreeWidget, QComboBox QAbstractItemView {{
    background: {panel_bg}; color: {text}; border: 1px solid {border};
    selection-background-color: {selected}; selection-color: {text};
}}
QLineEdit, QSpinBox, QComboBox {{ border-radius: {radius}; padding: 4px 6px; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QListWidget#navPanel::item {{ color: {text}; }}
QListWidget#navPanel::item:hover {{ background: {hover}; }}
QListWidget#navPanel::item:selected {{ background: {selected}; color: {accent}; border-color: {accent}; }}
QListWidget#recentList::item:selected {{ background: {selected}; color: {accent}; }}
QCheckBox::indicator, QRadioButton::indicator {{ background: {panel_bg}; border: 1px solid {border}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QToolTip {{ background: {panel_bg}; color: {text}; border: 1px solid {border}; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {text_muted}; }}
QSplitter::handle {{ background: {border}; }}
QHeaderView::section {{
    background-color: {accent}; color: {on_accent}; font-weight: 600; border: none;
    border-right: 1px solid {accent_hover}; border-bottom: 2px solid {accent_hover}; padding: 6px 8px;
}}
"""


def header_section_qss(theme_id='default'):
    """QHeaderView::section colors for the active shell theme (tool tables)."""
    tokens = theme_tokens(theme_id)
    on_accent = '#202124' if theme_id in ('energy', 'black') else '#FFFFFF'
    return (
        'QHeaderView::section {'
        f" background-color: {tokens['accent']}; color: {on_accent}; font-weight: 600;"
        ' border: none;'
        f" border-right: 1px solid {tokens['accent_hover']};"
        f" border-bottom: 2px solid {tokens['accent_hover']};"
        ' padding: 6px 8px; }'
    )


def build_shell_qss(theme_id='default'):
    tokens = theme_tokens(theme_id)
    # Dark text has better small-label contrast on bright energy orange.
    tokens['on_accent'] = '#202124' if theme_id in ('energy', 'black') else '#FFFFFF'
    return (_SHELL_TEMPLATE + _CHROME_TEMPLATE).format(**tokens)


SHELL_QSS = build_shell_qss()  # compatibility for existing imports

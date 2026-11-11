from PyQt6.QtCore import QEventLoop
from PyQt6.QtWidgets import QProgressBar, QApplication
from app.common.styles import COLOR_PRIMARY


def _progress_qss(min_height=None):
    from app.services import app_settings
    from app.shell.theme import THEMES, theme_tokens

    theme_id = app_settings.get("ui/theme")
    height_rule = f"min-height: {min_height}px;" if min_height else ""
    if theme_id not in THEMES or theme_id == "default":
        return f"""
            QProgressBar {{
                border: 1px solid #E5E5EA;
                border-radius: 6px;
                background: #F2F2F7;
                text-align: center;
                color: #1C1C1E;
                font-size: 11px;
                {height_rule}
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_PRIMARY};
                border-radius: 5px;
            }}
        """
    tokens = theme_tokens(theme_id)
    return f"""
        QProgressBar {{
            border: 1px solid {tokens['border']};
            border-radius: 6px;
            background: {tokens['sidebar_bg']};
            text-align: center;
            color: {tokens['text']};
            font-size: 11px;
            {height_rule}
        }}
        QProgressBar::chunk {{
            background-color: {tokens['accent']};
            border-radius: 5px;
        }}
    """


def make_overlay_progress(parent):
    """로딩 오버레이 안의 진행률 막대."""
    bar = QProgressBar(parent)
    bar.setGeometry(36, 248, 328, 18)
    bar.setTextVisible(True)
    bar.setFormat("%p%")
    bar.setRange(0, 0)
    bar.setStyleSheet(_progress_qss())
    return bar


def update_overlay_progress(bar, current, total):
    if total <= 0:
        bar.setRange(0, 0)
        return 0
    percent = max(0, min(100, int(current * 100 / total)))
    bar.setRange(0, 100)
    bar.setFormat("%p%")
    bar.setValue(percent)
    return percent


def style_task_progress(bar):
    bar.setTextVisible(True)
    bar.setFormat("%p%")
    bar.setStyleSheet(_progress_qss(min_height=18))



def note_progress(bar, value):
    bar.setValue(value)
    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

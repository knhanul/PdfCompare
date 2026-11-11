"""Recent documents list (QSettings, metadata only)."""
import os
import tempfile

from PyQt6.QtCore import QSettings

_KEY = 'viewer/recent_docs'
MAX_RECENT = 12


def _settings():
    return QSettings('PdfCompare', 'Workspace')


def load_recent():
    v = _settings().value(_KEY, [])
    if isinstance(v, str):
        v = [v]
    items = [p for p in (v or []) if isinstance(p, str)]
    temp_dir = os.path.normcase(os.path.abspath(tempfile.gettempdir()))

    def is_stale_temp(path):
        try:
            return (os.path.commonpath((temp_dir, os.path.normcase(os.path.abspath(path)))) == temp_dir
                    and not os.path.isfile(path))
        except ValueError:
            return False
    visible = [p for p in items if not is_stale_temp(p)]
    if len(visible) != len(items):
        _settings().setValue(_KEY, visible)
    return visible


def add_recent(path):
    path = os.path.abspath(path)
    items = [p for p in load_recent() if os.path.normcase(p) != os.path.normcase(path)]
    items.insert(0, path)
    _settings().setValue(_KEY, items[:MAX_RECENT])


def remove_recent(path):
    _settings().setValue(_KEY, [p for p in load_recent() if p != path])


def clear_recent():
    _settings().setValue(_KEY, [])

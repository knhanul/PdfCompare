"""Register the app as a per-user (HKCU) PDF handler so it appears in Explorer's "Open with".

Windows does not let apps make themselves the default; the user picks it in the Default apps settings.
"""
import os
import sys

from app.common.resources import APP_ID, APP_NAME, get_icon_path

try:
    import winreg
except ImportError:  # non-Windows
    winreg = None

PROG_ID = f'{APP_ID}.Document'
EXT = '.pdf'


def is_supported():
    return winreg is not None


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


def open_command():
    """Command line Explorer runs, with "%1" replaced by the PDF path."""
    if is_frozen():
        return f'"{sys.executable}" "%1"'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'main.py')
    return f'"{pythonw if os.path.isfile(pythonw) else exe}" "{main}" "%1"'


def _icon_value():
    if is_frozen():
        return f'"{sys.executable}",0'
    icon = get_icon_path()
    return f'"{icon}"' if icon else ''


def _keys(prefix=''):
    classes = prefix + r'Software\Classes'
    exe_name = os.path.basename(sys.executable)
    return {
        'progid': rf'{classes}\{PROG_ID}',
        'openwith': rf'{classes}\{EXT}\OpenWithProgids',
        # Applications\<exe> only for a built exe; never claim python(w).exe in dev mode.
        'app': rf'{classes}\Applications\{exe_name}' if is_frozen() else None,
        'capabilities': prefix + rf'Software\{APP_ID}\Capabilities',
        'registered': prefix + r'Software\RegisteredApplications',
    }


def _set(path, name, value, kind=None):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, kind if kind is not None else winreg.REG_SZ, value)


def _get(path, name=''):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def _has_value(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.QueryValueEx(key, name)
            return True
    except OSError:
        return False


def _delete_tree(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(rf'{path}\{child}')
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


def _delete_value(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except OSError:
        pass


def _notify_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def register(prefix=''):
    keys = _keys(prefix)
    command = open_command()
    icon = _icon_value()
    _set(keys['progid'], '', f'{APP_NAME} PDF 문서')
    _set(keys['progid'], 'FriendlyTypeName', f'{APP_NAME} PDF 문서')
    if icon:
        _set(keys['progid'] + r'\DefaultIcon', '', icon)
    _set(keys['progid'] + r'\shell\open\command', '', command)
    _set(keys['openwith'], PROG_ID, b'', winreg.REG_NONE)
    if keys['app']:
        _set(keys['app'], 'FriendlyAppName', APP_NAME)
        _set(keys['app'] + r'\shell\open\command', '', command)
        _set(keys['app'] + r'\SupportedTypes', EXT, '')
    _set(keys['capabilities'], 'ApplicationName', APP_NAME)
    _set(keys['capabilities'], 'ApplicationDescription', f'{APP_NAME} PDF 보기')
    _set(keys['capabilities'] + r'\FileAssociations', EXT, PROG_ID)
    _set(keys['registered'], APP_ID, keys['capabilities'][len(prefix):])
    if not prefix:
        _notify_shell()


def unregister(prefix=''):
    keys = _keys(prefix)
    _delete_tree(keys['progid'])
    _delete_value(keys['openwith'], PROG_ID)
    if keys['app']:
        _delete_tree(keys['app'])
    _delete_tree(keys['capabilities'])
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, prefix + rf'Software\{APP_ID}')  # only if now empty
    except OSError:
        pass
    _delete_value(keys['registered'], APP_ID)
    if not prefix:
        _notify_shell()


def is_registered(prefix=''):
    return _get(_keys(prefix)['progid'] + r'\shell\open\command') == open_command()


def default_apps_url():
    return f'ms-settings:defaultapps?registeredAppUser={APP_ID}'

"""Single running instance: later launches hand their PDF paths to the first window."""
import getpass
import json
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from app.common.resources import APP_ID

TIMEOUT_MS = 1000


def server_name():
    try:
        user = getpass.getuser()
    except Exception:
        user = 'user'
    return f'{APP_ID}.{user}'


def pdf_args(argv):
    """Existing .pdf files among command-line arguments, as absolute paths."""
    return [os.path.abspath(a) for a in argv
            if a.lower().endswith('.pdf') and os.path.isfile(a)]


def _allow_foreground():
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:
        pass


def send_to_running(paths, name=None):
    """Forward paths to an already running instance. Returns True when one received them."""
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(TIMEOUT_MS):
        return False
    _allow_foreground()
    sock.write(json.dumps(list(paths), ensure_ascii=False).encode('utf-8') + b'\n')
    sock.flush()
    sock.waitForBytesWritten(TIMEOUT_MS)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    files_received = pyqtSignal(list)

    def __init__(self, name=None, parent=None):
        super().__init__(parent)
        self.name = name or server_name()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)

    def listen(self):
        if self.server.listen(self.name):
            return True
        QLocalServer.removeServer(self.name)  # stale name left by a crashed instance
        return self.server.listen(self.name)

    def _on_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            state = {'buf': bytearray(), 'done': False}

            def read(s=sock, st=state):
                if st['done']:
                    return
                st['buf'].extend(bytes(s.readAll()))
                if b'\n' not in st['buf'] and s.state() == QLocalSocket.LocalSocketState.ConnectedState:
                    return
                st['done'] = True
                try:
                    paths = json.loads(bytes(st['buf']).split(b'\n', 1)[0].decode('utf-8') or '[]')
                except ValueError:
                    paths = []
                self.files_received.emit([p for p in paths if isinstance(p, str)])
                s.deleteLater()

            sock.readyRead.connect(read)
            sock.disconnected.connect(read)
            read()  # data may already be buffered if the sender finished before we got here

    def close(self):
        self.server.close()

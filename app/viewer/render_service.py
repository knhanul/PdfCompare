"""Background page rendering.

Each worker thread opens its *own* PyMuPDF document by path (thread-local),
so no fitz.Document is ever shared across threads.
"""
import threading

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage

from app.viewer.page_cache import PageCache

_local = threading.local()


def _open_local(path):
    docs = getattr(_local, 'docs', None)
    if docs is None:
        docs = _local.docs = {}
    doc = docs.get(path)
    if doc is None:
        import pymupdf
        if len(docs) > 8:
            for d in docs.values():
                d.close()
            docs.clear()
        doc = docs[path] = pymupdf.open(path)
    return doc


class _Signals(QObject):
    done = pyqtSignal(object, QImage)


class _RenderJob(QRunnable):
    def __init__(self, key, signals):
        super().__init__()
        self.key = key
        self.signals = signals

    def run(self):
        path, page_no, zoom_milli = self.key
        try:
            import pymupdf
            doc = _open_local(path)
            zoom = zoom_milli / 1000.0
            pix = doc[page_no].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format.Format_RGB888).copy()
        except Exception:
            img = QImage()
        self.signals.done.emit(self.key, img)


class RenderService(QObject):
    rendered = pyqtSignal(object)  # key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = PageCache()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._pending = set()
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)

    @staticmethod
    def make_key(path, page_no, zoom):
        return (path, page_no, int(round(zoom * 1000)))

    def get(self, path, page_no, zoom):
        key = self.make_key(path, page_no, zoom)
        img = self.cache.get(key)
        if img is None and key not in self._pending:
            self._pending.add(key)
            self.pool.start(_RenderJob(key, self._signals))
        return img

    def _on_done(self, key, img):
        self._pending.discard(key)
        if not img.isNull():
            self.cache.put(key, img)
            self.rendered.emit(key)

    def forget(self, path):
        self.cache.drop_path(path)

    def shutdown(self):
        self.pool.clear()
        self.pool.waitForDone(2000)


_service = None


def render_service():
    global _service
    if _service is None:
        _service = RenderService()
    return _service

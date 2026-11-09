from __future__ import annotations
import pymupdf
from .model import PageInfo, Placement


class SourceDoc:
    """원본 PDF의 작업 사본. 회전 정규화는 place()에서만 수행한다."""

    def __init__(self, path_or_bytes, source_id="main", bake=False):
        self.source_id = source_id
        if isinstance(path_or_bytes, (bytes, bytearray)):
            self._doc = pymupdf.open("pdf", bytes(path_or_bytes))
        else:
            self._doc = pymupdf.open(str(path_or_bytes))
        if bake:
            try:
                self._doc.bake()
            except Exception:
                pass
        self._info, self._rot, self._derot = [], [], []
        for i, pg in enumerate(self._doc):
            r = pg.rect
            self._info.append(PageInfo(i, r.width, r.height, pg.rotation))
            self._rot.append(pg.rotation)
            self._derot.append(pymupdf.Matrix(pg.derotation_matrix))
        for pg in self._doc:
            pg.set_rotation(0)

    @property
    def page_count(self): return len(self._info)

    def page_info(self, i): return self._info[i]

    def infos(self): return list(self._info)

    def place(self, out_page, p: Placement):
        rot, D = self._rot[p.page], self._derot[p.page]
        c = p.clip
        clip_u = pymupdf.Rect(c.x0, c.y0, c.x1, c.y1) * D
        d = p.dst
        out_page.show_pdf_page(pymupdf.Rect(d.x0, d.y0, d.x1, d.y1), self._doc, p.page,
                               clip=clip_u, rotate=(-rot - p.extra_rotate) % 360,
                               keep_proportion=False)

    def close(self):
        self._doc.close()

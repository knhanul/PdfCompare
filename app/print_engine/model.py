from __future__ import annotations
from dataclasses import dataclass, field
from .units import mm


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self): return self.x1 - self.x0

    @property
    def h(self): return self.y1 - self.y0

    def is_empty(self, eps=1e-6): return self.w <= eps or self.h <= eps


@dataclass(frozen=True)
class PageInfo:
    index: int
    width: float
    height: float
    rotation: int = 0


@dataclass(frozen=True)
class Placement:
    source_id: str
    page: int
    clip: Box
    dst: Box
    extra_rotate: int = 0


@dataclass(frozen=True)
class Mark:
    kind: str
    p0: tuple
    p1: tuple
    text: str = ""


@dataclass
class Sheet:
    width: float
    height: float
    placements: list = field(default_factory=list)
    marks: list = field(default_factory=list)


@dataclass
class PrintPlan:
    sheets: list
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Margins:
    top: float = mm(5)
    right: float = mm(5)
    bottom: float = mm(5)
    left: float = mm(5)

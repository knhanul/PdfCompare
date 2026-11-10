PT_PER_MM = 72.0 / 25.4


def mm(v: float) -> float:
    return v * PT_PER_MM


PAPER = {"A4": (mm(210), mm(297)), "A3": (mm(297), mm(420)),
         "B4": (mm(257), mm(364)), "B5": (mm(182), mm(257)), "A5": (mm(148), mm(210))}  # B*: JIS


def paper(name: str, landscape: bool = False):
    w, h = PAPER[name.upper()]
    return (h, w) if landscape else (w, h)

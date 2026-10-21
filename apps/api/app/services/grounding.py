"""Whether the numbers in an Assistant reply came from its tools (docs/plans/10 AS-4).

A paragraph's numbers are matched against every number the turn's tools
returned (and the question and the page's note): exactly, rounded to a whole
or a tenth, or a share (0 to 1) said in percent, to a tenth or to 5 points as
the Forecast's chances are said. A ``m:ss`` moment is matched as its seconds. Whole numbers up
to :data:`ALWAYS` pass, being counts any sentence makes ("two maps", "five
players"). What is left the page marks "шалгах": the reply is not regenerated,
which would cost a second turn.
"""

from __future__ import annotations

import re

ALWAYS = 5
_ROUND_TOKEN = re.compile(r"\[(?:\d+\.\d+:)?R\d{1,2}(?: \d{1,2}:\d{2})?(?: @\d{5,20})?\]")
_CLOCK = re.compile(r"(?<![\w.:])(\d{1,2}):(\d{2})(?![\w:])")
_NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w]|[.,]\d)")
_SOURCE = re.compile(r"-?\d+(?:\.\d+)?")


def source_numbers(text: str) -> set[float]:
    """Every number in a tool's output (or the question)."""
    return {abs(float(n)) for n in _SOURCE.findall(text)}


def _said(value: float, sources: set[float]) -> bool:
    if value.is_integer() and value <= ALWAYS:
        return True
    for x in sources:
        if (
            abs(x - value) < 1e-9
            or round(x) == value
            or round(x, 1) == value
            # A share: below 1, or every id 1 would read as 100 percent.
            or (x < 1 and (round(100 * x) == value or round(100 * x, 1) == value))
            or (x < 1 and round(20 * x) * 5 == value)
        ):
            return True
    return False


def ungrounded(paragraph: str, sources: set[float]) -> list[str]:
    """The numbers in ``paragraph`` no source has, as written."""
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", _ROUND_TOKEN.sub(" ", paragraph))  # 1,400
    out = []
    for m in _CLOCK.finditer(text):
        if not _said(int(m.group(1)) * 60 + int(m.group(2)), sources):
            out.append(m.group(0))
    text = _CLOCK.sub(" ", text)
    for raw in _NUMBER.findall(text):
        if not _said(float(raw.replace(",", ".")), sources):
            out.append(raw)
    return list(dict.fromkeys(out))

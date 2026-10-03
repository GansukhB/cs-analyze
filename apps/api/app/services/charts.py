"""Inline SVG charts, rendered server-side.

Ported from cstat's ``hltv/services/charts.py``, where the pages had no client
chart library. The game plan API returns these strings and the React page drops
them in as-is, so both apps draw the same marks.

Interaction is a native ``<svg:title>`` on every mark. That gives a real browser
tooltip with zero JavaScript, is announced by screen readers, and survives with
scripting disabled -- which a JS tooltip layer would not.

**Colours are chart-mark steps, not the UI chrome steps.** ``--mine`` /
``--theirs`` / ``--h2h`` in ``index.css`` are tuned for headings and rails, where
the job is text contrast. As chart *marks* on the dark surface they fail the
lightness band a mark palette has to sit in (OKLCH L 0.48-0.67): the UI blue
measures 0.673 and the UI yellow 0.778. ``--mark-*`` are the same hues stepped
into that band -- #6e8ef3 and #b0902f -- and the pair validates clean on every
check, worst-case colour-blind separation dE 27.4 against a target of 8. Same
family, different step, different job. Do not swap one for the other.

Text never wears a series colour here: labels and values use the ink tokens and
identity comes from the swatch beside them.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

# Mark geometry, fixed across every chart in the project.
BAR_THICK = 20  # <= 24px; the band keeps the rest as air
BAR_RADIUS = 4  # rounded data-end, square at the baseline
GAP = 2  # surface gap between touching marks
AXIS = "var(--line)"  # hairline, solid, recessive

MINE = "var(--mark-mine)"
THEIRS = "var(--mark-theirs)"
H2H = "var(--mark-h2h)"
NEUTRAL = "var(--ink-3)"


def _esc(value) -> str:
    return escape(str(value), quote=True)


def _hbar_path(
    x: float, y: float, w: float, h: float, r: float = BAR_RADIUS, flip: bool = False
) -> str:
    """A horizontal bar: square where it meets the baseline, rounded at the tip.

    ``flip`` grows the bar leftwards from ``x`` instead of rightwards, which is
    what a diverging chart's negative arm needs.
    """
    r = max(0.0, min(r, abs(w), h / 2))
    if w <= 0.01:
        return ""
    if not flip:
        return (
            f"M{x:.2f},{y:.2f} H{x + w - r:.2f} A{r:.2f},{r:.2f} 0 0 1 "
            f"{x + w:.2f},{y + r:.2f} V{y + h - r:.2f} A{r:.2f},{r:.2f} 0 0 1 "
            f"{x + w - r:.2f},{y + h:.2f} H{x:.2f} Z"
        )
    return (
        f"M{x:.2f},{y:.2f} H{x - w + r:.2f} A{r:.2f},{r:.2f} 0 0 0 "
        f"{x - w:.2f},{y + r:.2f} V{y + h - r:.2f} A{r:.2f},{r:.2f} 0 0 0 "
        f"{x - w + r:.2f},{y + h:.2f} H{x:.2f} Z"
    )


def _open(width: int, height: int, label: str, fluid: bool = True) -> list[str]:
    """Open an SVG that scales with its container without wasting it.

    A fixed ``height`` attribute alongside ``width="100%"`` and ``meet`` is the
    trap: the scale becomes ``min(containerW/viewBoxW, h/h)`` = 1, so the drawing
    renders at its natural size, anchors top-left and leaves the rest of the box
    empty -- 45% of it at the width this page uses. Omitting the height and
    letting CSS take ``height:auto`` makes the viewBox aspect ratio drive it, so
    the chart scales uniformly to whatever space it is given.

    ``fluid=False`` keeps a pixel width for drawings that should not stretch: a
    3x4 matchup grid pulled across 1000px is mostly gap.
    """
    size = 'width="100%"' if fluid else f'width="{width}" height="{height}"'
    # "chart-fixed", not cstat's "fixed": on the React page that name is Tailwind's
    # position utility, which pulled the duel grid out of the layout.
    return [
        f'<svg class="chart{"" if fluid else " chart-fixed"}" viewBox="0 0 {width} {height}" '
        f'{size} role="img" aria-label="{_esc(label)}" '
        f'preserveAspectRatio="xMinYMin meet">'
    ]


# --------------------------------------------------------------- grouped -----
def team_compare_bars(
    rows: Sequence[dict],
    *,
    mine_label: str,
    theirs_label: str,
    value_suffix: str = "%",
    width: int = 980,
    title: str = "",
) -> str:
    """Two bars per category, one per team. The map-pool and side-rate chart.

    ``rows`` is ``[{"label", "mine", "theirs", "mine_note", "theirs_note"}]``
    with values already on a 0-100 scale. A row whose value is ``None`` renders
    as an explicit "no data" tick rather than as a zero, because a map neither
    team has played is a blind spot and drawing it at zero says the opposite.
    """
    if not rows:
        return ""
    label_w, pad_r = 150, 62
    row_h = BAR_THICK * 2 + GAP + 16
    top = 48 if title else 28  # room for the title and the legend above the plot
    height = top + row_h * len(rows) + 22
    plot_x = label_w
    plot_w = width - label_w - pad_r

    out = _open(width, height, title or f"{mine_label} against {theirs_label}")
    if title:
        out.append(f'<text x="0" y="14" class="c-title">{_esc(title)}</text>')
    # Two series, so a legend is mandatory rather than optional -- by the time a
    # reader reaches this chart the page-level key is several screens above it.
    lx = plot_x
    for colour, who in ((MINE, mine_label), (THEIRS, theirs_label)):
        out.append(f'<rect x="{lx}" y="{top - 20}" width="9" height="9" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{lx + 14}" y="{top - 12}" class="c-tick">{_esc(who)}</text>')
        lx += 22 + 7.0 * len(who)

    # Gridlines at 25/50/75 -- hairline, solid, behind the marks.
    for pct in (25, 50, 75, 100):
        gx = plot_x + plot_w * pct / 100
        out.append(
            f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" y2="{top + row_h * len(rows)}" '
            f'stroke="{AXIS}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{gx:.1f}" y="{height - 8}" class="c-tick" text-anchor="middle">{pct}</text>'
        )

    for i, row in enumerate(rows):
        y0 = top + i * row_h
        out.append(
            f'<text x="0" y="{y0 + BAR_THICK - 4}" class="c-label">{_esc(row["label"])}</text>'
        )
        for j, (key, colour, who) in enumerate(
            (("mine", MINE, mine_label), ("theirs", THEIRS, theirs_label))
        ):
            by = y0 + j * (BAR_THICK + GAP)
            value = row.get(key)
            note = row.get(f"{key}_note") or ""
            if value is None:
                out.append(
                    f'<text x="{plot_x + 4}" y="{by + BAR_THICK - 5}" '
                    f'class="c-nodata">no parsed games'
                    f"<title>{_esc(who)}: {_esc(row['label'])} — not parsed</title></text>"
                )
                continue
            w = plot_w * max(0.0, min(100.0, float(value))) / 100
            if w < 1.2:
                out.append(
                    f'<rect x="{plot_x}" y="{by}" width="2.5" height="{BAR_THICK}" '
                    f'fill="{colour}" opacity=".85">'
                    f"<title>{_esc(who)} — {_esc(row['label'])}: {_esc(value)}"
                    f"{_esc(value_suffix)} (played, won none)"
                    f"{' · ' + _esc(note) if note else ''}</title></rect>"
                )
                out.append(
                    f'<text x="{plot_x + 9}" y="{by + BAR_THICK - 5}" '
                    f'class="c-value">{_esc(value)}{_esc(value_suffix)}</text>'
                )
                continue
            out.append(
                f'<path d="{_hbar_path(plot_x, by, w, BAR_THICK)}" fill="{colour}">'
                f"<title>{_esc(who)} — {_esc(row['label'])}: {_esc(value)}{_esc(value_suffix)}"
                f"{' · ' + _esc(note) if note else ''}</title></path>"
            )
            out.append(
                f'<text x="{plot_x + w + 7:.1f}" y="{by + BAR_THICK - 5}" '
                f'class="c-value">{_esc(value)}{_esc(value_suffix)}</text>'
            )
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------- diverging -----
def diverging_bars(
    rows: Sequence[dict],
    *,
    width: int = 980,
    domain: float = 1.0,
    title: str = "",
    pos_label: str = "",
    neg_label: str = "",
) -> str:
    """Signed values around a zero baseline -- role fit, round difference.

    Two hues either side of a neutral centre line, which is the diverging rule:
    the polarity is the message, so the midpoint must be neutral and the arms
    must step equally.
    """
    if not rows:
        return ""
    label_w, pad = 168, 58
    row_h = BAR_THICK + 10
    top = 30 if title else 8
    height = top + row_h * len(rows) + 20
    plot_x = label_w
    plot_w = width - label_w - pad
    mid = plot_x + plot_w / 2
    domain = max(domain, max((abs(float(r["value"])) for r in rows), default=1.0))

    out = _open(width, height, title or "signed comparison")
    if title:
        out.append(f'<text x="0" y="14" class="c-title">{_esc(title)}</text>')
    out.append(
        f'<line x1="{mid:.1f}" y1="{top}" x2="{mid:.1f}" '
        f'y2="{top + row_h * len(rows)}" stroke="{AXIS}" stroke-width="1"/>'
    )

    for i, row in enumerate(rows):
        y = top + i * row_h
        value = float(row["value"])
        w = (plot_w / 2) * min(1.0, abs(value) / domain)
        colour = row.get("colour") or (MINE if value >= 0 else THEIRS)
        out.append(
            f'<text x="0" y="{y + BAR_THICK - 5}" class="c-label">{_esc(row["label"])}</text>'
        )
        if w > 0.5:
            out.append(
                f'<path d="{_hbar_path(mid, y, w, BAR_THICK, flip=value < 0)}" fill="{colour}">'
                f"<title>{_esc(row['label'])}: {_esc(row.get('display', value))}"
                f"{' · ' + _esc(row['note']) if row.get('note') else ''}</title></path>"
            )
        tx = mid + w + 7 if value >= 0 else mid - w - 7
        anchor = "start" if value >= 0 else "end"
        out.append(
            f'<text x="{tx:.1f}" y="{y + BAR_THICK - 5}" class="c-value" '
            f'text-anchor="{anchor}">{_esc(row.get("display", value))}</text>'
        )
    if pos_label or neg_label:
        out.append(
            f'<text x="{mid + 6:.1f}" y="{height - 6}" class="c-tick">{_esc(pos_label)}</text>'
        )
        out.append(
            f'<text x="{mid - 6:.1f}" y="{height - 6}" class="c-tick" '
            f'text-anchor="end">{_esc(neg_label)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------- heat grid -----
def matchup_grid(
    rows: Sequence[str], cols: Sequence[str], cells: dict, *, width: int = 420, title: str = ""
) -> str:
    """Who beats whom: rows are our players, columns theirs.

    Diverging, because the value has a polarity -- a cell is our favour, their
    favour, or level. Blue for us and yellow for them are the same two hues the
    rest of the page uses for the two teams, so the grid needs no key beyond the
    one the page already carries. Level sits at a neutral grey, never a third hue.

    ``cells`` maps ``(row, col)`` to ``{"net", "for", "against", "thin"}``.
    A pair with too few duels is drawn hatched rather than pale, because pale
    reads as "level" and the honest answer is "not enough duels to say".
    """
    if not rows or not cols:
        return ""
    label_w, head_h, cell, gap = 96, 84, 46, GAP
    width = max(width, label_w + len(cols) * (cell + gap) + 8)
    height = head_h + len(rows) * (cell + gap) + 26

    out = _open(width, height, title or "player matchups", fluid=False)
    out.append(
        '<defs><pattern id="thinhatch" width="6" height="6" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="6" height="6" fill="var(--surface-2)"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{NEUTRAL}" stroke-width="1.4" '
        'opacity=".5"/></pattern></defs>'
    )
    if title:
        out.append(f'<text x="0" y="14" class="c-title">{_esc(title)}</text>')

    for j, col in enumerate(cols):
        cx = label_w + j * (cell + gap) + cell / 2
        out.append(
            f'<text x="{cx:.1f}" y="{head_h - 10}" class="c-head" '
            f'text-anchor="end" transform="rotate(-40 {cx:.1f} {head_h - 10})">'
            f"{_esc(col)}</text>"
        )

    for i, row in enumerate(rows):
        y = head_h + i * (cell + gap)
        out.append(
            f'<text x="{label_w - 10}" y="{y + cell / 2 + 4:.1f}" class="c-label" '
            f'text-anchor="end">{_esc(row)}</text>'
        )
        for j, col in enumerate(cols):
            x = label_w + j * (cell + gap)
            data = cells.get((row, col))
            if not data:
                out.append(
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" '
                    f'fill="var(--surface-2)" opacity=".45">'
                    f"<title>{_esc(row)} vs {_esc(col)}: no duels</title></rect>"
                )
                continue
            net, kf, ka = data["net"], data["for"], data["against"]
            total = kf + ka
            if data.get("thin"):
                fill, op = "url(#thinhatch)", 1.0
            elif net > 0:
                fill, op = MINE, min(1.0, 0.30 + 0.70 * min(1.0, net / 4))
            elif net < 0:
                fill, op = THEIRS, min(1.0, 0.30 + 0.70 * min(1.0, -net / 4))
            else:
                fill, op = NEUTRAL, 0.35
            out.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" '
                f'fill="{fill}" opacity="{op:.2f}">'
                f"<title>{_esc(row)} vs {_esc(col)}: {kf}-{ka} ({net:+d})"
                f"{' — only ' + str(total) + ' duels, too few to read' if data.get('thin') else ''}"
                f"</title></rect>"
            )
            out.append(
                f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 4:.1f}" '
                f'class="c-cell" text-anchor="middle">{kf}-{ka}</text>'
            )
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------- share bar -----
def share_bar(
    segments: Sequence[dict], *, width: int = 980, height: int = 30, title: str = ""
) -> str:
    """One bar split into shares -- a bombsite split, a round-ending split.

    Segments are separated by a 2px surface gap rather than by a stroke, so the
    ink stays data.
    """
    total = sum(max(0.0, float(s["value"])) for s in segments)
    if total <= 0:
        return ""
    top = 22 if title else 0
    out = _open(width, height + top + 18, title or "share")
    if title:
        out.append(f'<text x="0" y="14" class="c-title">{_esc(title)}</text>')
    x = 0.0
    n = len(segments)
    for i, seg in enumerate(segments):
        w = (width - GAP * (n - 1)) * float(seg["value"]) / total
        if w <= 0.2:
            x += w + GAP
            continue
        r = BAR_RADIUS if (i == 0 or i == n - 1) else 0
        out.append(
            f'<rect x="{x:.1f}" y="{top}" width="{w:.1f}" height="{height}" rx="{r}" '
            f'fill="{seg.get("colour", MINE)}">'
            f"<title>{_esc(seg['label'])}: {_esc(seg['value'])}"
            f"{' · ' + _esc(seg['note']) if seg.get('note') else ''}</title></rect>"
        )
        if w > 34:
            out.append(
                f'<text x="{x + w / 2:.1f}" y="{top + height / 2 + 4:.0f}" '
                f'class="c-inset" text-anchor="middle">{_esc(seg["label"])}</text>'
            )
        x += w + GAP
    out.append("</svg>")
    return "".join(out)

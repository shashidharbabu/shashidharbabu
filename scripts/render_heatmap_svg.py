#!/usr/bin/env python3
"""Render data/contributions.json as an animated contribution heatmap SVG.

The reveal is CSS keyframes with a per-cell delay derived from (week + day),
so the grid wipes in diagonally, then freezes. No loop, no JS - GitHub renders
the file through <img>, which runs CSS animations but strips scripts.

Set STATIC=1 to emit a frozen frame (handy for local Quick Look previews).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "contributions.json"
OUT = ROOT / "contrib-heatmap.svg"

STATIC = os.environ.get("STATIC") == "1"

PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#69f0a0"]
#          none  ->  brightest (level 5 is a neon top end we derive ourselves)

BG = "#0d1117"
BORDER = "#21262d"
FG = "#c9d1d9"
MUTED = "#7d8590"
ACCENT = "#39d353"

CELL = 11
GAP = 3
PITCH = CELL + GAP
RADIUS = 2.5

PAD = 22
LABEL_W = 30           # gutter for Mon/Wed/Fri
TITLEBAR_H = 34
MONTH_H = 18
GRID_H = 7 * PITCH - GAP

WIDTH = 860
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sunday_index(d: date) -> int:
    """Python weekday() is Mon=0..Sun=6; GitHub's grid rows start on Sunday."""
    return (d.weekday() + 1) % 7


def boost_level(level: int, count: int, peak: int) -> int:
    """Promote the very top days to the neon level 5 GitHub doesn't have."""
    if level >= 4 and peak > 0 and count >= max(peak * 0.75, 1):
        return 5
    return level


def layout(days: list[dict], peak: int) -> tuple[list[dict], int]:
    """Assign each day a (week, row) grid position. Returns cells + week count."""
    cells = []
    week = 0
    prev_row = None
    for d in days:
        dt = date.fromisoformat(d["date"])
        row = sunday_index(dt)
        if prev_row is not None and row <= prev_row:
            week += 1
        prev_row = row
        cells.append({
            "date": d["date"],
            "dt": dt,
            "count": d["count"],
            "level": boost_level(d["level"], d["count"], peak),
            "week": week,
            "row": row,
        })
    return cells, week + 1


def month_ticks(cells: list[dict]) -> list[tuple[int, str]]:
    """First column of each month, skipping labels that would collide."""
    ticks: list[tuple[int, str]] = []
    seen: set[tuple[int, int]] = set()
    for c in cells:
        key = (c["dt"].year, c["dt"].month)
        if key in seen:
            continue
        seen.add(key)
        # Only label a month once its first full week has started.
        if ticks and c["week"] - ticks[-1][0] < 3:
            continue
        ticks.append((c["week"], MONTHS[c["dt"].month - 1]))
    return ticks


def build(payload: dict) -> str:
    days = payload["days"]
    stats = payload["stats"]
    peak = stats["max_count"]
    cells, weeks = layout(days, peak)

    grid_w = weeks * PITCH - GAP
    grid_x = PAD + LABEL_W
    grid_y = TITLEBAR_H + 16 + MONTH_H
    legend_y = grid_y + GRID_H + 26
    footer_y = legend_y + 30
    height = footer_y + 16

    # Centre the whole plot block inside the fixed 860 canvas.
    shift = max(0, (WIDTH - (grid_x + grid_w + PAD)) // 2)
    gx = grid_x + shift

    parts: list[str] = []
    add = parts.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(str(stats["total"]))} contributions in the last year">'
    )

    # ---- styles ------------------------------------------------------------
    if STATIC:
        anim = ".cell,.fade{opacity:1}"
    else:
        anim = (
            "@keyframes pop{"
            "from{opacity:0;transform:translateY(-7px) scale(.55)}"
            "to{opacity:1;transform:translateY(0) scale(1)}}"
            "@keyframes fadeup{"
            "from{opacity:0;transform:translateY(5px)}"
            "to{opacity:1;transform:translateY(0)}}"
            ".cell{opacity:0;transform-box:fill-box;transform-origin:center;"
            "animation:pop .5s cubic-bezier(.2,.8,.3,1) forwards}"
            ".fade{opacity:0;animation:fadeup .6s ease-out forwards}"
        )

    add(
        "<style>"
        f".mono{{font-family:{MONO};}}"
        f"{anim}"
        "</style>"
    )

    # ---- terminal chrome ---------------------------------------------------
    add(
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="10" '
        f'fill="{BG}" stroke="{BORDER}"/>'
    )
    add(
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{WIDTH}" y2="{TITLEBAR_H}" stroke="{BORDER}"/>'
    )
    for i, dot in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        add(f'<circle cx="{22 + i * 18}" cy="{TITLEBAR_H / 2}" r="5.5" fill="{dot}"/>')
    add(
        f'<text class="mono" x="82" y="{TITLEBAR_H / 2 + 4}" font-size="12" fill="{MUTED}">'
        f'contributions --user {escape(payload["username"])} --last-year</text>'
    )

    # ---- month labels ------------------------------------------------------
    for week, name in month_ticks(cells):
        x = gx + week * PITCH
        add(
            f'<text class="mono fade" x="{x}" y="{grid_y - 7}" font-size="10.5" '
            f'fill="{MUTED}" style="animation-delay:.15s">{name}</text>'
        )

    # ---- day-of-week labels ------------------------------------------------
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = grid_y + row * PITCH + CELL - 2
        add(
            f'<text class="mono fade" x="{gx - 8}" y="{y}" font-size="10" '
            f'fill="{MUTED}" text-anchor="end" style="animation-delay:.15s">{name}</text>'
        )

    # ---- the grid ----------------------------------------------------------
    for c in cells:
        x = gx + c["week"] * PITCH
        y = grid_y + c["row"] * PITCH
        # Diagonal sweep: cells on the same anti-diagonal light up together.
        delay = 0.25 + (c["week"] + c["row"] * 1.6) * 0.014
        style = "" if STATIC else f' style="animation-delay:{delay:.3f}s"'
        label = (
            f'{c["count"]} contribution{"" if c["count"] == 1 else "s"} on {c["date"]}'
        )
        add(
            f'<rect class="cell" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'rx="{RADIUS}" fill="{PALETTE[c["level"]]}"{style}>'
            f'<title>{escape(label)}</title></rect>'
        )

    tail = 0.25 + (weeks + 6 * 1.6) * 0.014  # when the last cell lands

    def delayed(extra: float) -> str:
        return "" if STATIC else f' style="animation-delay:{tail + extra:.2f}s"'

    # ---- legend ------------------------------------------------------------
    lx = gx + grid_w
    box = 10
    legend_boxes = len(PALETTE)
    lx_start = lx - (legend_boxes * (box + 3) - 3) - 74
    add(
        f'<text class="mono fade" x="{lx_start - 8}" y="{legend_y + 9}" font-size="10.5" '
        f'fill="{MUTED}" text-anchor="end"{delayed(0.05)}>Less</text>'
    )
    for i, colour in enumerate(PALETTE):
        # Kept out of the f-string: nested quotes/backslashes inside an f-string
        # expression are a syntax error before Python 3.12, and CI runs 3.11.
        style = "" if STATIC else f' style="animation-delay:{tail + 0.05 + i * 0.05:.2f}s"'
        add(
            f'<rect class="cell" x="{lx_start + i * (box + 3)}" y="{legend_y}" '
            f'width="{box}" height="{box}" rx="2" fill="{colour}"{style}/>'
        )
    add(
        f'<text class="mono fade" x="{lx_start + legend_boxes * (box + 3) + 5}" '
        f'y="{legend_y + 9}" font-size="10.5" fill="{MUTED}"{delayed(0.35)}>More</text>'
    )

    # ---- footer stats ------------------------------------------------------
    add(
        f'<text class="mono fade" x="{gx}" y="{footer_y}" font-size="12.5" fill="{FG}"'
        f'{delayed(0.15)}>'
        f'<tspan fill="{ACCENT}" font-weight="600">{stats["total"]:,}</tspan>'
        f'<tspan fill="{FG}"> contributions in the last year</tspan></text>'
    )

    right = (
        f'{stats["current_streak"]}d current  ·  '
        f'{stats["longest_streak"]}d longest  ·  '
        f'{stats["active_days"]} active days  ·  '
        f'peak {stats["max_count"]}'
    )
    add(
        f'<text class="mono fade" x="{gx + grid_w}" y="{footer_y}" font-size="11" '
        f'fill="{MUTED}" text-anchor="end"{delayed(0.25)}>{escape(right)}</text>'
    )

    add("</svg>")
    return "".join(parts)


def main() -> None:
    if not DATA.exists():
        raise SystemExit(f"missing {DATA} - run scripts/fetch_contributions.py first")
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    OUT.write_text(build(payload) + "\n", encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT.relative_to(ROOT)} ({size:,} bytes){' [static]' if STATIC else ''}")


if __name__ == "__main__":
    main()

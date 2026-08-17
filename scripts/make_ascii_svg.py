#!/usr/bin/env python3
"""Turn source-prepped.png into a self-typing monochrome ASCII portrait SVG.

Each pixel's brightness picks a glyph from a density ramp. Every row is wrapped
in a horizontal clip that wipes left-to-right - a small block cursor rides the
wipe edge - staggered top to bottom. The portrait prints once and freezes.

Two choices keep it clean instead of noisy:
  * monochrome - one light-grey fill; per-character rainbow is what makes most
    ASCII portraits look like static
  * high contrast - a washed-out background collapses to the space glyph, so
    only the subject prints

Set STATIC=1 to emit a frozen frame for local previews.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source-prepped.png"
OUT = ROOT / "avi-ascii.svg"

STATIC = os.environ.get("STATIC") == "1"

RAMP = " .`:-=+*cs#%@"   # bright (sparse) -> dark (dense)
#        ^ leading space clears the background to nothing

BG = "#0d1117"
BORDER = "#21262d"
INK = "#c9d1d9"          # one light-grey fill, monochrome on purpose
CURSOR = "#39d353"
MUTED = "#7d8590"

MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

FONT_SIZE = 10.0
CHAR_W = FONT_SIZE * 0.6      # monospace advance width
LINE_H = FONT_SIZE * 1.0      # tight leading keeps the portrait from stretching

PAD = 18

# The portrait is displayed at 370px from a ~660px canvas, the info card at
# 490px from 560px - so the portrait is scaled down ~1.56x harder. Enlarge its
# window chrome by that factor so both title bars look identical in the README.
CHROME_SCALE = 1.56
TITLEBAR_H = round(34 * CHROME_SCALE)


def to_glyph_grid(cols: int, rows: int) -> list[str]:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} - run scripts/prep_photo.py <photo> first")
    img = Image.open(SRC).convert("L").resize((cols, rows), Image.LANCZOS)
    px = np.asarray(img, dtype=np.float32)
    # bright -> index 0 (space), dark -> the densest glyph
    idx = np.clip(np.rint((255.0 - px) / 255.0 * (len(RAMP) - 1)), 0, len(RAMP) - 1)
    idx = idx.astype(int)
    return ["".join(RAMP[i] for i in row) for row in idx]


def build(lines: list[str], cols: int, stagger: float, row_dur: float) -> str:
    art_w = cols * CHAR_W
    rows = len(lines)
    art_h = rows * LINE_H

    width = round(art_w + PAD * 2)
    top = TITLEBAR_H + 14
    height = round(top + art_h + PAD)

    parts: list[str] = []
    add = parts.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="ASCII portrait">'
    )

    if STATIC:
        anim = ".wipe{transform:scaleX(1)}.cur{opacity:0}"
    else:
        steps = f"steps({cols},end)"
        anim = (
            "@keyframes wipe{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
            "@keyframes ride{from{transform:translateX(0)}"
            f"to{{transform:translateX({art_w:.1f}px)}}}}"
            "@keyframes blinkout{0%,92%{opacity:1}100%{opacity:0}}"
            ".wipe{transform-box:fill-box;transform-origin:left center;"
            f"transform:scaleX(0);animation:wipe var(--d) {steps} forwards}}"
            ".cur{transform-box:fill-box;transform-origin:left center;opacity:0;"
            f"animation:ride var(--d) {steps} forwards,"
            "blinkout var(--d) linear forwards}"
        )

    add(
        "<style>"
        f".art{{font-family:{MONO};font-size:{FONT_SIZE}px;fill:{INK};"
        "white-space:pre;dominant-baseline:hanging}"
        f"{anim}"
        "</style>"
    )

    # ---- terminal chrome ---------------------------------------------------
    add(
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" '
        f'fill="{BG}" stroke="{BORDER}"/>'
    )
    add(f'<line x1="0" y1="{TITLEBAR_H}" x2="{width}" y2="{TITLEBAR_H}" stroke="{BORDER}"/>')
    s = CHROME_SCALE
    for i, dot in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        add(
            f'<circle cx="{(22 + i * 18) * s:.1f}" cy="{TITLEBAR_H / 2}" '
            f'r="{5.5 * s:.1f}" fill="{dot}"/>'
        )
    add(
        f'<text x="{82 * s:.1f}" y="{TITLEBAR_H / 2 + 4 * s:.1f}" font-family="{MONO}" '
        f'font-size="{12 * s:.1f}" fill="{MUTED}">./portrait.sh</text>'
    )

    # ---- clip paths: one horizontal wipe per row ---------------------------
    add("<defs>")
    for r in range(rows):
        y = top + r * LINE_H
        delay = r * stagger
        style = "" if STATIC else f' style="--d:{row_dur}s;animation-delay:{delay:.3f}s"'
        add(
            f'<clipPath id="w{r}"><rect class="wipe" x="{PAD}" y="{y:.2f}" '
            f'width="{art_w:.2f}" height="{LINE_H:.2f}"{style}/></clipPath>'
        )
    add("</defs>")

    # ---- the portrait ------------------------------------------------------
    for r, line in enumerate(lines):
        y = top + r * LINE_H
        add(
            f'<text class="art" x="{PAD}" y="{y:.2f}" clip-path="url(#w{r})" '
            f'textLength="{art_w:.2f}" lengthAdjust="spacingAndGlyphs" '
            f'xml:space="preserve">{escape(line)}</text>'
        )

    # ---- cursor blocks riding each wipe edge -------------------------------
    for r in range(rows):
        y = top + r * LINE_H
        delay = r * stagger
        style = "" if STATIC else f' style="--d:{row_dur}s;animation-delay:{delay:.3f}s"'
        add(
            f'<rect class="cur" x="{PAD}" y="{y:.2f}" width="{CHAR_W:.2f}" '
            f'height="{LINE_H:.2f}" fill="{CURSOR}"{style}/>'
        )

    add("</svg>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cols", type=int, default=92)
    ap.add_argument("--rows", type=int, default=0,
                    help="0 = derive from the prepped photo's aspect ratio")
    ap.add_argument("--stagger", type=float, default=0.045, help="seconds between rows")
    ap.add_argument("--row-dur", type=float, default=0.5, help="seconds per row wipe")
    args = ap.parse_args()

    rows = args.rows
    if rows <= 0:
        w, h = Image.open(SRC).size if SRC.exists() else (1, 1)
        # Characters are taller than wide, so fewer rows than the pixel ratio.
        rows = max(1, int(round(args.cols * (h / w) * (CHAR_W / LINE_H))))

    lines = to_glyph_grid(args.cols, rows)
    OUT.write_text(build(lines, args.cols, args.stagger, args.row_dur) + "\n",
                   encoding="utf-8")

    ink = sum(1 for ln in lines for c in ln if c != " ")
    total = args.cols * rows
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)"
          f"{' [static]' if STATIC else ''}")
    print(f"  grid {args.cols}x{rows} | {ink / total * 100:.1f}% ink | "
          f"runtime {rows * args.stagger + args.row_dur:.1f}s")


if __name__ == "__main__":
    main()

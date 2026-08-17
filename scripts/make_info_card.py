#!/usr/bin/env python3
"""Hand-author the neofetch-style info card SVG.

The contribution graph already covers the numbers, so this panel carries the
story numbers can't tell: what I'm building, the stack, what I'm open to.
Each row fades and slides in on a short stagger so it looks like it's printing
next to the portrait.

Set STATIC=1 to emit a frozen frame for local previews.
"""

from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "info-card.svg"

STATIC = os.environ.get("STATIC") == "1"

BG = "#0d1117"
BORDER = "#21262d"
FG = "#c9d1d9"
MUTED = "#7d8590"
KEY = "#39d353"
ACCENT = "#58a6ff"
RULE = "#30363d"

MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

USER = "shashidhar"
HOST = "github"

# (key, value) - key is None for a spacer, "--" for a horizontal rule.
ROWS: list[tuple[str | None, str]] = [
    ("Name", "Shashidhar Babu P V D"),
    ("Role", "AI / ML Engineer · Embodied AI Researcher"),
    ("Location", "San Francisco Bay Area"),
    ("--", ""),
    ("Now", "Founding AI Engineer @ RocketRide"),
    ("", "Building RocketRide.ai — OSS & SaaS"),
    ("", "Grad Research Assistant, Embodied AI @ SJSU"),
    ("--", ""),
    ("Prev", "ML Engineer @ Mercedes-Benz R&D N.A."),
    ("", "Built the “Hey Mercedes” assistant"),
    ("", "Software Engineer, AI @ APARAVI"),
    ("", "ML Engineer @ Techolution"),
    ("", "Software Engineer, AI/ML @ PerspectAI"),
    ("", "ML & Robotics, founding team @ SegriTech"),
    ("", "ML Engineer @ Feynn Labs"),
    ("", "AI Intern @ E-Cell, IIT Kharagpur"),
    ("--", ""),
    ("Edu", "MS Applied Data Science — SJSU"),
    ("", "B.Tech ECE — IIIT Sri City"),
    ("--", ""),
    ("Focus", "Embodied AI · 3D ML · LLM systems · RAG"),
    ("", "Multimodal AI · Scalable data platforms"),
    ("--", ""),
    ("Languages", "Python · Go · Scala · Java · C · SQL · R"),
    ("ML", "PyTorch · TensorFlow · JAX · HuggingFace"),
    ("Agents", "LangGraph · CrewAI · RAG · LoRA · ONNX"),
    ("Data", "Spark · Kafka · Airflow · MLflow · Snowflake"),
    ("Stores", "Postgres · MongoDB · Neo4j · Redis"),
    ("--", ""),
    ("Shipping", "Multimodal RAG · Transformer from scratch"),
    ("", "Aerive Platform · AI NutriCoach"),
    ("Speaks", "English · Hindi · Telugu"),
    ("Open to", "OSS + applied AI engineering collabs"),
    ("--", ""),
    ("Links", "github.com/shashidharbabu"),
    ("", "linkedin.com/in/p-v-d-shashidhar-babu-9b91471b9"),
]

SWATCHES = ["#161b22", "#0e4429", "#006d32", "#26a641",
            "#39d353", "#69f0a0", "#58a6ff", "#c9d1d9"]

WIDTH = 560
PAD = 22
TITLEBAR_H = 34
LINE_H = 17
KEY_W = 86          # wide enough for the longest key ("Languages") plus its colon


def build() -> str:
    parts: list[str] = []
    add = parts.append

    y = TITLEBAR_H + 30           # first line baseline
    prompt_y = y
    y += LINE_H + 8

    body_start = y
    heights = []
    for key, _ in ROWS:
        heights.append(y)
        y += 9 if key == "--" else LINE_H

    swatch_y = y + 10
    height = swatch_y + 14 + PAD

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="Profile info card for {escape(USER)}">'
    )

    if STATIC:
        anim = ".row{opacity:1}"
    else:
        anim = (
            "@keyframes slidein{"
            "from{opacity:0;transform:translateX(-9px)}"
            "to{opacity:1;transform:translateX(0)}}"
            ".row{opacity:0;animation:slidein .42s ease-out forwards}"
        )

    add(f"<style>.mono{{font-family:{MONO};}}{anim}</style>")

    # ---- terminal chrome ---------------------------------------------------
    add(
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="10" '
        f'fill="{BG}" stroke="{BORDER}"/>'
    )
    add(f'<line x1="0" y1="{TITLEBAR_H}" x2="{WIDTH}" y2="{TITLEBAR_H}" stroke="{BORDER}"/>')
    for i, dot in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        add(f'<circle cx="{22 + i * 18}" cy="{TITLEBAR_H / 2}" r="5.5" fill="{dot}"/>')
    add(
        f'<text class="mono" x="82" y="{TITLEBAR_H / 2 + 4}" font-size="12" '
        f'fill="{MUTED}">neofetch</text>'
    )

    def delay(i: float) -> str:
        return "" if STATIC else f' style="animation-delay:{0.15 + i * 0.055:.3f}s"'

    # ---- user@host header --------------------------------------------------
    add(
        f'<text class="mono row" x="{PAD}" y="{prompt_y}" font-size="13.5"{delay(0)}>'
        f'<tspan fill="{KEY}" font-weight="600">{escape(USER)}</tspan>'
        f'<tspan fill="{MUTED}">@</tspan>'
        f'<tspan fill="{ACCENT}" font-weight="600">{escape(HOST)}</tspan></text>'
    )
    add(
        f'<line class="row" x1="{PAD}" y1="{prompt_y + 8}" x2="{WIDTH - PAD}" '
        f'y2="{prompt_y + 8}" stroke="{RULE}"{delay(1)}/>'
    )

    # ---- key/value rows ----------------------------------------------------
    for i, ((key, value), row_y) in enumerate(zip(ROWS, heights), start=2):
        if key == "--":
            add(
                f'<line class="row" x1="{PAD}" y1="{row_y}" x2="{WIDTH - PAD}" '
                f'y2="{row_y}" stroke="{RULE}"{delay(i)}/>'
            )
            continue

        add(f'<g class="row"{delay(i)}>')
        if key:
            add(
                f'<text class="mono" x="{PAD}" y="{row_y}" font-size="12" '
                f'fill="{KEY}" font-weight="600">{escape(key)}</text>'
            )
            add(
                f'<text class="mono" x="{PAD + KEY_W - 15}" y="{row_y}" font-size="12" '
                f'fill="{MUTED}">:</text>'
            )
        add(
            f'<text class="mono" x="{PAD + KEY_W}" y="{row_y}" font-size="12" '
            f'fill="{FG if key else MUTED}">{escape(value)}</text>'
        )
        add("</g>")

    # ---- neofetch colour blocks -------------------------------------------
    n = len(ROWS) + 2
    for i, colour in enumerate(SWATCHES):
        add(
            f'<rect class="row" x="{PAD + i * 20}" y="{swatch_y}" width="16" '
            f'height="10" rx="2" fill="{colour}"{delay(n + i * 0.4)}/>'
        )

    add("</svg>")
    return "".join(parts)


def main() -> None:
    OUT.write_text(build() + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)"
          f"{' [static]' if STATIC else ''}")


if __name__ == "__main__":
    main()

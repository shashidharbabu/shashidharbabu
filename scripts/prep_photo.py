#!/usr/bin/env python3
"""Prep a photo so it survives the trip through an ASCII density ramp.

A flatly-lit face converts to a dark, unreadable blob. Three steps fix that:

  1. isolate the subject          (rembg if available, else the plain-background
                                   white-point clamp below)
  2. boost local contrast         (CLAHE - contrast-limited adaptive histogram
                                   equalisation, implemented here in numpy so
                                   the pipeline runs on any Python version)
  3. composite onto pure white    (white maps to the blank end of the ramp, so
                                   the background prints as spaces)

Usage:
    python scripts/prep_photo.py source-photo.jpg
    python scripts/prep_photo.py me.jpg --crop 0.21,0.05,0.79,0.44 --gamma 1.9
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "source-prepped.png"

MAX_SIDE = 1400          # plenty of detail for a ~92-column grid
BINS = 256


def clahe(gray: np.ndarray, tiles: tuple[int, int] = (8, 8), clip: float = 2.6) -> np.ndarray:
    """Contrast-limited adaptive histogram equalisation, bilinearly blended."""
    h, w = gray.shape
    ty, tx = tiles
    pad_y, pad_x = (-h) % ty, (-w) % tx
    g = np.pad(gray, ((0, pad_y), (0, pad_x)), mode="edge")
    gh, gw = g.shape
    th, tw = gh // ty, gw // tx

    limit = max(1.0, clip * th * tw / BINS)
    maps = np.zeros((ty, tx, BINS), dtype=np.float32)
    for i in range(ty):
        for j in range(tx):
            tile = g[i * th:(i + 1) * th, j * tw:(j + 1) * tw]
            hist = np.bincount(tile.ravel(), minlength=BINS).astype(np.float32)
            excess = np.maximum(hist - limit, 0).sum()
            hist = np.minimum(hist, limit) + excess / BINS
            cdf = np.cumsum(hist)
            span = max(float(cdf[-1] - cdf[0]), 1e-6)
            maps[i, j] = (cdf - cdf[0]) / span * (BINS - 1)

    # Blend the four nearest tile mappings so tile seams don't show.
    fy = (np.arange(gh) + 0.5) / th - 0.5
    fx = (np.arange(gw) + 0.5) / tw - 0.5
    y0 = np.clip(np.floor(fy).astype(int), 0, ty - 1)
    x0 = np.clip(np.floor(fx).astype(int), 0, tx - 1)
    y1, x1 = np.clip(y0 + 1, 0, ty - 1), np.clip(x0 + 1, 0, tx - 1)
    wy = np.clip(fy - np.floor(fy), 0, 1)[:, None].astype(np.float32)
    wx = np.clip(fx - np.floor(fx), 0, 1)[None, :].astype(np.float32)

    def take(mi: np.ndarray, mj: np.ndarray) -> np.ndarray:
        return maps[mi[:, None], mj[None, :], g]

    out = ((1 - wy) * (1 - wx) * take(y0, x0)
           + (1 - wy) * wx * take(y0, x1)
           + wy * (1 - wx) * take(y1, x0)
           + wy * wx * take(y1, x1))
    return np.clip(out, 0, 255).astype(np.uint8)[:h, :w]


def background_mask(gray: np.ndarray, tol: float, scale: int = 4) -> np.ndarray:
    """Bright pixels *connected to the image border* - i.e. the backdrop.

    A plain studio background is never perfectly flat, and CLAHE happily
    amplifies its gradients into ASCII noise. A plain brightness threshold would
    also blow out teeth and shirt highlights, so we flood-fill inward from the
    border instead: only regions actually touching the edge get clamped.

    The cutoff is anchored to the backdrop's *own* measured brightness (median
    of the frame border), not to a percentile of the whole image. A percentile
    moves with the crop - widen the frame to include more dark suit and it
    slides down past skin tone, at which point the fill leaks through the
    hairline and erases the face. The border median doesn't move.

    Runs on a downscaled mask - the output is a ~92-column grid, so exact edge
    precision is irrelevant and this keeps the fill fast.
    """
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    base = float(np.median(border))
    if base < 110:
        print(f"  backdrop looks dark (border median {base:.0f}) - skipping clamp")
        return np.zeros(gray.shape, dtype=bool)

    thr = base * (1.0 - tol)
    print(f"  backdrop brightness {base:.0f}, clamp cutoff {thr:.0f}")
    bright = gray[::scale, ::scale] >= thr

    reach = np.zeros_like(bright)
    reach[0, :] |= bright[0, :]
    reach[-1, :] |= bright[-1, :]
    reach[:, 0] |= bright[:, 0]
    reach[:, -1] |= bright[:, -1]

    while True:
        before = int(reach.sum())
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        reach = grown & bright
        if int(reach.sum()) == before:
            break

    full = np.repeat(np.repeat(reach, scale, axis=0), scale, axis=1)
    return full[:gray.shape[0], :gray.shape[1]]


def strip_background(img: Image.Image) -> Image.Image:
    """rembg cutout composited on white. Falls back to the original on failure."""
    try:
        from rembg import remove  # noqa: PLC0415 - optional heavy dependency
    except ImportError:
        print("  rembg not installed - relying on the white-point clamp instead")
        return img
    cut = remove(img)
    canvas = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    canvas.alpha_composite(cut.convert("RGBA"))
    print("  rembg: background removed")
    return canvas.convert("RGB")


def crop_box(img: Image.Image, spec: str) -> Image.Image:
    """Pre-crop to a normalised left,top,right,bottom box (0..1) - used to pull a
    head-and-shoulders framing out of a full-body shot."""
    try:
        l, t, r, b = (float(v) for v in spec.split(","))
    except ValueError:
        raise SystemExit("--crop wants four comma-separated 0..1 numbers: L,T,R,B")
    if not (0 <= l < r <= 1 and 0 <= t < b <= 1):
        raise SystemExit(f"--crop out of range or inverted: {spec}")
    w, h = img.size
    return img.crop((int(l * w), int(t * h), int(r * w), int(b * h)))


def crop_to_aspect(img: Image.Image, aspect: float, bias: float) -> Image.Image:
    """Centre-crop to height/width == aspect. bias 0=top, .5=centre, 1=bottom."""
    w, h = img.size
    if h / w > aspect:                       # too tall -> trim vertically
        new_h = int(round(w * aspect))
        top = int(round((h - new_h) * bias))
        return img.crop((0, top, w, top + new_h))
    new_w = int(round(h / aspect))           # too wide -> trim horizontally
    left = (w - new_w) // 2
    return img.crop((left, 0, left + new_w, h))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo", type=Path)
    ap.add_argument("--crop", type=str, default=None,
                    help="pre-crop box as normalised L,T,R,B (e.g. 0.2,0.0,0.78,0.39) "
                         "to frame head-and-shoulders out of a wider shot")
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                    help="extra counter-clockwise rotation after EXIF correction")
    ap.add_argument("--aspect", type=float, default=1.00,
                    help="output height/width; tuned so the finished portrait renders "
                         "the same height as info-card.svg in the README (default 1.00)")
    ap.add_argument("--bias", type=float, default=0.28,
                    help="vertical crop bias, 0=keep top .. 1=keep bottom")
    ap.add_argument("--clip", type=float, default=2.2, help="CLAHE clip limit")
    ap.add_argument("--tiles", type=int, default=8, help="CLAHE tile grid (NxN)")
    ap.add_argument("--black", type=float, default=1.5,
                    help="percentile mapped to pure black")
    ap.add_argument("--white", type=float, default=93.0,
                    help="percentile mapped to pure white (raise to blow out the bg)")
    ap.add_argument("--gamma", type=float, default=1.9,
                    help=">1 lightens midtones, <1 darkens them")
    ap.add_argument("--bg-tol", type=float, default=0.16,
                    help="how much darker than the measured backdrop brightness still "
                         "counts as backdrop (0.16 = down to 84%% of it)")
    ap.add_argument("--no-bg-flood", action="store_true",
                    help="disable the border flood-fill backdrop clamp")
    ap.add_argument("--rembg", action="store_true", help="run rembg background removal")
    ap.add_argument("--no-clahe", action="store_true")
    ap.add_argument("--flip", action="store_true", help="mirror horizontally")
    args = ap.parse_args()

    if not args.photo.exists():
        raise SystemExit(f"no such photo: {args.photo}")

    img = Image.open(args.photo)
    img = ImageOps.exif_transpose(img).convert("RGB")
    print(f"loaded {args.photo.name} ({img.width}x{img.height})")

    if args.rotate:
        img = img.rotate(args.rotate, expand=True)
        print(f"  rotated {args.rotate} deg CCW -> {img.width}x{img.height}")
    if args.flip:
        img = ImageOps.mirror(img)
    if args.crop:
        img = crop_box(img, args.crop)
        print(f"  pre-cropped to {img.width}x{img.height}")
    if args.rembg:
        img = strip_background(img)

    img = crop_to_aspect(img, args.aspect, args.bias)
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    print(f"  cropped/resized to {img.width}x{img.height}")

    gray = np.asarray(img.convert("L"), dtype=np.uint8)

    # Decide what counts as backdrop *before* CLAHE touches the tonal range.
    bg = None
    if not args.no_bg_flood and not args.rembg:
        bg = background_mask(gray, args.bg_tol)
        print(f"  backdrop flood-fill: {bg.mean() * 100:.1f}% of the frame")

    if not args.no_clahe:
        gray = clahe(gray, (args.tiles, args.tiles), args.clip)
        print(f"  CLAHE applied (clip={args.clip}, tiles={args.tiles}x{args.tiles})")

    # Levels stretch: pin the chosen percentiles to pure black / pure white so
    # the background lands on the blank end of the ramp.
    lo, hi = np.percentile(gray, [args.black, args.white])
    if hi - lo < 1:
        lo, hi = 0.0, 255.0
    stretched = np.clip((gray.astype(np.float32) - lo) / (hi - lo), 0, 1)
    if abs(args.gamma - 1.0) > 1e-6:
        stretched = stretched ** (1.0 / args.gamma)
    final = (stretched * 255).astype(np.uint8)
    print(f"  levels: {lo:.0f}->0, {hi:.0f}->255, gamma={args.gamma}")

    if bg is not None:
        final[bg] = 255          # backdrop -> the blank end of the ramp

    Image.fromarray(final, mode="L").save(OUT)
    ink = float((final < 200).mean()) * 100
    print(f"wrote {OUT.relative_to(ROOT)}  |  {ink:.1f}% of pixels will print ink")
    if ink < 12:
        print("  hint: too sparse - lower --white or raise --gamma", file=sys.stderr)
    elif ink > 55:
        print("  hint: too dense - raise --white or lower --gamma", file=sys.stderr)


if __name__ == "__main__":
    main()

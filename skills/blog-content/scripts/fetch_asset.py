"""Download a Magnific creation (image or video) into the vault.

The skill calls the Magnific MCP, reads `url` (full-res) and `thumbnailUrl` /
`previewUrl` from `creations_get`, then invokes this to persist the files into
the vault assets folder. Videos cannot embed in Excel, so we always also pull a
still poster image for the workbook thumbnail.

Usage:
    python3 fetch_asset.py --url <full_url> --out <dest_path> \
        [--thumb-url <thumb_url>] [--thumb-out <thumb_dest>]

Prints JSON: {"out": ..., "thumb_out": ...}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

try:
    from PIL import Image as PILImage
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image as PILImage

UA = {"User-Agent": "Mozilla/5.0 (DigitalCLIQ social-media-manager)"}


def _download(url: str, dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        fh.write(resp.read())
    return dest


def _normalize_thumb(src: str, dest: str, max_px: int = 600) -> str:
    try:
        im = PILImage.open(src).convert("RGB")
        im.thumbnail((max_px, max_px))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "PNG")
        return dest
    except Exception:
        return src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thumb-url")
    ap.add_argument("--thumb-out")
    args = ap.parse_args()

    out = _download(args.url, args.out)
    thumb_out = None

    if args.thumb_url:
        raw = (args.thumb_out or os.path.splitext(args.out)[0] + "_thumb_raw") + ".img"
        _download(args.thumb_url, raw)
        thumb_out = args.thumb_out or (os.path.splitext(args.out)[0] + "_thumb.png")
        _normalize_thumb(raw, thumb_out)
        if os.path.exists(raw):
            os.remove(raw)
    else:
        # No thumb URL: if the full asset is itself an image, derive a thumb.
        ext = os.path.splitext(out)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            thumb_out = args.thumb_out or (os.path.splitext(args.out)[0] + "_thumb.png")
            _normalize_thumb(out, thumb_out)

    print(json.dumps({"out": out, "thumb_out": thumb_out}))


if __name__ == "__main__":
    main()

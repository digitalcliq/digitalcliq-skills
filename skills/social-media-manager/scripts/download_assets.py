"""Batch-download generated assets into the vault and merge paths back into the plan.

Offloads ALL file work to local so the skill spends no model tokens on per-file
downloads. Each plan['assets'][i] needs: id, src_url, optional src_thumb_url.
This sets a['file'] and a['thumb'] in place and rewrites the plan JSON.

Usage:
    python3 download_assets.py <plan.json> <outdir> <prefix>
e.g. python3 download_assets.py plan.json Projects/NCBMW/social-assets/2026-06 NCBMW
"""
import json
import os
import subprocess
import sys
import urllib.request

try:
    from PIL import Image
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (DigitalCLIQ social-media-manager)"}


def _dl(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())


def _thumb(src, dest, mx=600):
    try:
        im = Image.open(src).convert("RGB")
        im.thumbnail((mx, mx))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "PNG")
        return True
    except Exception:
        return False


def main():
    if len(sys.argv) != 4:
        print("Usage: python3 download_assets.py <plan.json> <outdir> <prefix>")
        sys.exit(2)
    plan_path, outdir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)

    n = 0
    for a in plan.get("assets", []):
        url = a.get("src_url")
        if not url:
            continue
        ext = os.path.splitext(url.split("?")[0])[1].lower() or ".png"
        file = os.path.join(outdir, f"{prefix}-{a['id']}{ext}")
        _dl(url, file)
        a["file"] = file

        tdest = os.path.join(outdir, f"{prefix}-{a['id']}_thumb.png")
        tu = a.get("src_thumb_url")
        if tu:
            raw = file + ".rawthumb"
            _dl(tu, raw)
            if _thumb(raw, tdest):
                a["thumb"] = tdest
            if os.path.exists(raw):
                os.remove(raw)
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            if _thumb(file, tdest):
                a["thumb"] = tdest
        n += 1
        print(f"  {a['id']} -> {file}")

    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1)
    print(f"downloaded {n} asset(s); plan updated: {plan_path}")


if __name__ == "__main__":
    main()

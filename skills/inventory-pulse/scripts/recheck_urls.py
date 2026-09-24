#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: emit the recheck URL list for one dealer.

Inventory is SAMPLED (3-4 VDPs per tracked model, per Drew 2026-08-15), so
"VIN missing this run" no longer implies delisted. Instead, every run
re-fetches the VDPs of VINs already in the registry for that dealer: a VDP
that 404s / no longer parses yields no row, and snapshot_diff then marks the
VIN delisted. A recheck 404 is DATA (vehicle gone), not a crawl error.

Usage: recheck_urls.py --state $STATE --dealer "Name" [--cap 40]
Prints one URL per line (empty output on baseline runs). Append to the
dealer's fetch list / MATCHES-independent recheck array.
"""
import argparse, json, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--dealer", required=True)
    ap.add_argument("--cap", type=int, default=40)
    args = ap.parse_args()
    reg_path = os.path.join(args.state, "registry.json")
    if not os.path.exists(reg_path):
        return
    reg = json.load(open(reg_path))
    urls = []
    for vin, e in reg.get("vin_registry", {}).items():
        if e.get("dealer") == args.dealer and not e.get("delisted_on") and e.get("vdp_url"):
            urls.append(e["vdp_url"])
    for u in urls[:args.cap]:
        print(u)


if __name__ == "__main__":
    main()

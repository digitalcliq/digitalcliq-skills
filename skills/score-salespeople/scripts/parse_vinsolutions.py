"""VINSolutions adapter — placeholder for v3.

v1 does not support VINSolutions. Use Tekion exports for now.
"""
from __future__ import annotations


def parse_vinsolutions(export_path: str):
    raise NotImplementedError(
        "VINSolutions adapter not yet supported in v1. "
        "Use Tekion exports via parse_tekion(). "
        "Roadmap: v3."
    )

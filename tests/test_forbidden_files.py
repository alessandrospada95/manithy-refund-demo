import os
from pathlib import Path

FORBIDDEN = {
    "VectorState.json",
    "KnowledgeLayer.json",
    "GeometryScore.json",
    "AuthorityExplanation.txt",
}

def test_forbidden_files_absent():
    root = Path(__file__).resolve().parents[1]
    # only check within repo (not venv)
    for p in root.rglob("*"):
        if p.is_file() and p.name in FORBIDDEN:
            raise AssertionError(f"Forbidden file exists: {p}")

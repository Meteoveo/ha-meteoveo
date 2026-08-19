#!/usr/bin/env python3
"""Pre-publication audit.

Run before pushing; exits non-zero on a finding so it can gate a commit.

This exists because a real station identifier once reached a test file as
sample data. Example values must be recognisably fake.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "scripts"}
SUFFIXES = {".py", ".json", ".md", ".ini", ".txt", ".yaml", ".yml"}

PATTERNS = {
    # A station identifier that is not the documented example.
    "live station identifier": re.compile(r"\bMV(?!EXAMPLE)[A-Z0-9]{8}\b"),
    "credential-shaped literal": re.compile(
        r"(?i)(secret|api_key|token)\s*=\s*['\"][A-Za-z0-9_\-]{20,}"
    ),
    "private infrastructure": re.compile(r"178\.105\.\d+\.\d+|192\.168\.\d+\.\d+|:3001\b"),
}


def main() -> int:
    findings: list[str] = []
    checked = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        checked += 1
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{number}: {label}")

    print(f"checked {checked} files")
    for finding in findings:
        print(f"  {finding}")
    print("clean" if not findings else f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

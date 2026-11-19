#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install the profile roles as native MCode Agents.

Since 16.11.2026 a role is not a profile agent anymore: the role cards are
built into the built-in Agent assets (runtime/build_role_assets.py), so the
runtime itself knows the roles, shows them in its own agent list and lets the
model call them as first-class delegation targets.

Copying the cards into <DATA_DIR>/agents/<role>/ would create a manual agent
with the same name as a roster entry, and the runtime fails its startup seed
with a builtin name conflict.

Usage:
    python -X utf8 scripts/install_roles.py            # build the built-in assets
    python -X utf8 scripts/install_roles.py --check    # report only
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILDER = REPO / "runtime" / "build_role_assets.py"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args()
    if not BUILDER.exists():
        print("NO BUILDER: %s" % BUILDER, file=sys.stderr)
        return 2
    cmd = [sys.executable, str(BUILDER)] + (["--check"] if args.check else [])
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())

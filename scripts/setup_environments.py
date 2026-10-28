#!/usr/bin/env python3
"""Set up the exact pandas pair; print and persist the resulting manifest."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from featureshift.runner import setup_environments, verify_install_failure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--offline", action="store_true", help="Only use previously cached pinned wheels")
    parser.add_argument("--verify-install-failure", action="store_true")
    args = parser.parse_args()
    if args.verify_install_failure:
        result = verify_install_failure(args.root)
        exit_code = 0 if result.get("verified") and result.get("environment_unchanged") else 1
    else:
        result = setup_environments(args.root, offline=args.offline)
        exit_code = 0 if result["status"] == "ok" else 1
    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

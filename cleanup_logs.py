"""Cleanup utility for snapshots, MP4 clips, and log files older than N days."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List


def cleanup_old_files(logs_dir: str | Path = "logs", days: int = 7, dry_run: bool = False) -> List[Path]:
    """Delete files older than `days` inside logs_dir (including snapshots/ and videos/)."""
    base = Path(logs_dir)
    if not base.exists():
        return []

    cutoff = time.time() - (days * 86400)
    targets: List[Path] = []

    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".pid", ".signal"}:
            continue
        if path.stat().st_mtime < cutoff:
            targets.append(path)
            if not dry_run:
                try:
                    path.unlink()
                except OSError:
                    pass

    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up old RTSP monitor logs and media.")
    parser.add_argument("--days", type=int, default=7, help="Retention days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="List files without deleting")
    parser.add_argument("--logs-dir", default="logs", help="Logs directory path")
    args = parser.parse_args()

    files = cleanup_old_files(args.logs_dir, days=args.days, dry_run=args.dry_run)
    prefix = "[DRY-RUN]" if args.dry_run else "[CLEANED]"
    print(f"{prefix} Target files older than {args.days} day(s): {len(files)}")
    for item in files:
        print(f"  - {item}")


if __name__ == "__main__":
    main()

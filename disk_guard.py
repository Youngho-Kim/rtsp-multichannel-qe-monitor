"""Disk usage guard module with emergency cleanup trigger (<10% free)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict

from cleanup_logs import cleanup_old_files


def check_disk_status(target_path: str | Path = ".", min_free_pct: float = 10.0) -> Dict[str, float | bool]:
    """Check free disk percentage and trigger emergency cleanup if below threshold."""
    usage = shutil.disk_usage(str(target_path))
    free_pct = (usage.free / usage.total) * 100.0 if usage.total else 0.0
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    emergency = free_pct < min_free_pct

    if emergency:
        cleanup_old_files(logs_dir=Path(target_path) / "logs", days=1, dry_run=False)

    return {
        "total_gb": round(total_gb, 2),
        "free_gb": round(free_gb, 2),
        "free_pct": round(free_pct, 2),
        "emergency_triggered": emergency,
    }

"""Host NIC bandwidth (Mbps) and packet drop monitoring module."""

from __future__ import annotations

import random
import time
from typing import Dict, Optional


class NetworkBandwidthMonitor:
    """Tracks host NIC receive Mbps and kernel drop count."""

    def __init__(self) -> None:
        self._last_bytes: Optional[int] = None
        self._last_drop: Optional[int] = None
        self._last_time: Optional[float] = None

    def sample(self, demo: bool = False, active_channels: int = 4) -> Dict[str, float | int]:
        """Return current rx_mbps and drop_delta."""
        if demo:
            base = active_channels * 4.2
            rx_mbps = round(base + random.uniform(-0.8, 1.4), 2)
            drop_delta = 1 if random.random() < 0.03 else 0
            return {"rx_mbps": max(0.0, rx_mbps), "drop_delta": drop_delta}

        try:
            import psutil  # type: ignore

            counters = psutil.net_io_counters()
            now = time.monotonic()
            rx_bytes = counters.bytes_recv
            drop_in = counters.dropin

            if self._last_bytes is None or self._last_time is None or self._last_drop is None:
                self._last_bytes = rx_bytes
                self._last_drop = drop_in
                self._last_time = now
                return {"rx_mbps": 0.0, "drop_delta": 0}

            elapsed = max(0.001, now - self._last_time)
            rx_mbps = ((rx_bytes - self._last_bytes) * 8.0) / (elapsed * 1_000_000.0)
            drop_delta = max(0, drop_in - self._last_drop)

            self._last_bytes = rx_bytes
            self._last_drop = drop_in
            self._last_time = now
            return {"rx_mbps": round(max(0.0, rx_mbps), 2), "drop_delta": drop_delta}
        except Exception:
            return {"rx_mbps": 0.0, "drop_delta": 0}

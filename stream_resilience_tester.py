"""Network fault injection and MTTR measurement for RTSP stream resilience QA."""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Callable


@dataclass
class FaultEvent:
    timestamp: str
    fault_type: str  # disconnect, frame_drop, high_latency
    duration_sec: float
    recovered: bool
    reconnect_attempts: int


@dataclass
class ResilienceMetrics:
    channel_id: str
    vendor: str
    total_checks: int
    successful_checks: int
    availability_pct: float
    frame_drop_rate_pct: float
    fault_count: int
    recovered_count: int
    mttr_sec: float
    max_recovery_sec: float
    events: list[FaultEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_resilience_check(
    channel_id: str,
    vendor: str,
    probe_fn: Callable[[], bool],
    total_checks: int = 20,
    max_reconnect_attempts: int = 3,
    retry_delay_sec: float = 0.05,
) -> ResilienceMetrics:
    """Run repeated health checks and measure reconnect attempts & MTTR on failures."""
    successful_checks = 0
    dropped_frames = 0
    events: list[FaultEvent] = []
    recovery_times: list[float] = []

    for _ in range(total_checks):
        if probe_fn():
            successful_checks += 1
            continue

        dropped_frames += 1
        fault_start = time.monotonic()
        recovered = False
        attempts = 0

        for attempt in range(1, max_reconnect_attempts + 1):
            attempts = attempt
            if retry_delay_sec > 0:
                time.sleep(retry_delay_sec)
            if probe_fn():
                recovered = True
                break

        duration = round(time.monotonic() - fault_start, 3)
        if recovered:
            recovery_times.append(duration)
            successful_checks += 1

        events.append(
            FaultEvent(
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                fault_type="disconnect",
                duration_sec=duration,
                recovered=recovered,
                reconnect_attempts=attempts,
            )
        )

    availability = round((successful_checks / total_checks) * 100, 2) if total_checks else 0.0
    drop_rate = round((dropped_frames / total_checks) * 100, 2) if total_checks else 0.0
    mttr = round(sum(recovery_times) / len(recovery_times), 3) if recovery_times else 0.0
    max_rec = round(max(recovery_times), 3) if recovery_times else 0.0

    return ResilienceMetrics(
        channel_id=channel_id,
        vendor=vendor,
        total_checks=total_checks,
        successful_checks=successful_checks,
        availability_pct=availability,
        frame_drop_rate_pct=drop_rate,
        fault_count=len(events),
        recovered_count=len(recovery_times),
        mttr_sec=mttr,
        max_recovery_sec=max_rec,
        events=events,
    )


def make_simulated_probe(
    fault_probability: float = 0.15,
    recover_probability: float = 0.8,
    seed: int = 42,
) -> Callable[[], bool]:
    """Deterministic simulated probe for demo & CI environments without physical cameras."""
    rng = random.Random(seed)
    in_fault = {"active": False}

    def _probe() -> bool:
        if in_fault["active"]:
            if rng.random() < recover_probability:
                in_fault["active"] = False
                return True
            return False
        if rng.random() < fault_probability:
            in_fault["active"] = True
            return False
        return True

    return _probe
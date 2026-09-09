from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Callable

from .model import Snapshot, normalize_mac


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    reason: str
    polls: int
    elapsed_seconds: float
    final_bssid: str | None
    traffic_ok: bool | None

    def to_dict(self):
        return asdict(self)


class OutcomeVerifier:
    def __init__(
        self,
        observer,
        *,
        traffic_probe: Callable[[str], bool] | None = None,
        association_probe: Callable[[str], str | None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self.observer = observer
        self.traffic_probe = traffic_probe
        self.association_probe = association_probe
        self.sleeper = sleeper
        self.monotonic = monotonic
        self.cancelled = cancelled or (lambda: False)

    def verify(
        self,
        sta_mac: str,
        target_bssid: str,
        *,
        timeout_seconds: float,
        poll_seconds: float = 1,
    ) -> VerificationResult:
        sta_mac = normalize_mac(sta_mac)
        target_bssid = normalize_mac(target_bssid)
        started = self.monotonic()
        polls = 0
        final_bssid = None
        while self.monotonic() - started <= timeout_seconds:
            if self.cancelled():
                return VerificationResult(False, "verification_cancelled", polls,
                                          self.monotonic() - started, final_bssid, None)
            if self.association_probe is not None:
                final_bssid = self.association_probe(sta_mac)
            else:
                snapshot: Snapshot = self.observer.observe()
                client = snapshot.client(sta_mac)
                final_bssid = client.connected_bssid if client else None
            polls += 1
            if final_bssid == target_bssid:
                traffic = self.traffic_probe(sta_mac) if self.traffic_probe else None
                return VerificationResult(
                    success=traffic is not False,
                    reason=(
                        "target_association_observed"
                        if traffic is None
                        else "association_and_traffic_converged"
                        if traffic
                        else "traffic_failed"
                    ),
                    polls=polls,
                    elapsed_seconds=self.monotonic() - started,
                    final_bssid=final_bssid,
                    traffic_ok=traffic,
                )
            self.sleeper(poll_seconds)
        return VerificationResult(
            success=False,
            reason="association_timeout",
            polls=polls,
            elapsed_seconds=self.monotonic() - started,
            final_bssid=final_bssid,
            traffic_ok=None,
        )

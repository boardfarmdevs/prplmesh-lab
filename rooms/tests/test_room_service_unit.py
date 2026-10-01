from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_service_signals_owner_before_children_and_retains_kill_deadline():
    service = (ROOT / "deploy/guest/prplmesh-room-service.service").read_text()
    assert "KillMode=mixed\n" in service
    assert "TimeoutStopSec=180\n" in service

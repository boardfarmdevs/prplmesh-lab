import copy
from datetime import datetime, timezone

import pytest

from optimizer.candidates import CandidateMetricsError, CandidateMetricsUnavailable
from optimizer.model import CandidateObservation, ClientObservation
from optimizer.cli import parser
from optimizer.prplmesh import PrplMeshCandidateProvider, PrplMeshObserver, _first_json


NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)
STAMP = "2026-08-28T18:00:00.000Z"
METRIC_STAMP = "2026-08-28T17:59:57.125Z"


def _topology():
    return {
        "generated_at": STAMP,
        "devices": [
            {
                "id": "02:00:00:27:01:01",
                "name": "controller",
                "radios": [
                    {
                        "id": "02:00:00:00:01:00",
                        "band": "5 GHz",
                        "channel": 36,
                        "opclass": 115,
                        "bsses": [
                            {
                                "bssid": "02:00:00:00:01:00",
                                "ssid": "private_ssid",
                                "clients": [
                                    {
                                        "id": "02:00:00:10:01:00",
                                        "signal_raw": 88,
                                        "signal_updated_at": METRIC_STAMP,
                                        "last_connect_seconds": 42,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "02:00:00:27:02:01",
                "name": "agent-1",
                "radios": [
                    {
                        "id": "02:00:00:00:04:00",
                        "band": "5 GHz",
                        "channel": 36,
                        "opclass": 115,
                        "bsses": [
                            {
                                "bssid": "02:00:00:00:04:00",
                                "ssid": "private_ssid",
                                "clients": [],
                            }
                        ],
                    }
                ],
            },
        ],
    }


def test_observer_normalizes_prplmesh_topology_without_inventing_candidate_metrics():
    observer = PrplMeshObserver(fetcher=lambda _url: _topology(), clock=lambda: NOW)
    snapshot = observer.observe()
    assert snapshot.health.devices == 2
    assert snapshot.health.radios == 2
    assert snapshot.health.bsses == 2
    assert snapshot.health.clients == 1
    assert snapshot.clients[0].rcpi == 88
    assert snapshot.clients[0].metric_observed_at == METRIC_STAMP
    assert snapshot.clients[0].band == "5"
    assert snapshot.clients[0].cohort == "private"
    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0].bssid == "02:00:00:00:04:00"
    assert snapshot.candidates[0].rcpi is None
    assert snapshot.candidates[0].measurement_source == "prplmesh_bss_inventory_only"


def test_observer_does_not_replace_missing_metric_time_with_http_sample_time():
    topology = copy.deepcopy(_topology())
    del topology["devices"][0]["radios"][0]["bsses"][0]["clients"][0][
        "signal_updated_at"
    ]
    observer = PrplMeshObserver(fetcher=lambda _url: topology, clock=lambda: NOW)
    assert observer.observe().clients[0].metric_observed_at is None


def test_observer_retries_non_atomic_roaming_snapshot(monkeypatch):
    duplicate = _topology()
    duplicate["devices"][1]["radios"][0]["bsses"][0]["clients"] = copy.deepcopy(
        duplicate["devices"][0]["radios"][0]["bsses"][0]["clients"])
    snapshots = iter([duplicate, _topology()])
    monkeypatch.setattr("optimizer.prplmesh.time.sleep", lambda seconds: None)
    observer = PrplMeshObserver(fetcher=lambda url: next(snapshots), clock=lambda: NOW)
    assert observer.observe().health.clients == 1


def test_ambiguous_ownership_and_transport_failure_are_unavailable(monkeypatch):
    duplicate = _topology()
    duplicate["devices"][1]["radios"][0]["bsses"][0]["clients"] = copy.deepcopy(
        duplicate["devices"][0]["radios"][0]["bsses"][0]["clients"])
    monkeypatch.setattr("optimizer.prplmesh.time.sleep", lambda seconds: None)
    observer = PrplMeshObserver(fetcher=lambda url: duplicate, clock=lambda: NOW)
    with pytest.raises(CandidateMetricsUnavailable, match="duplicate client ownership"):
        observer.observe()
    assert observer.last_raw is None

    def unavailable(url):
        raise OSError("temporary adapter interruption")

    observer = PrplMeshObserver(fetcher=unavailable, clock=lambda: NOW)
    with pytest.raises(CandidateMetricsUnavailable, match="collection failed"):
        observer.observe()


def test_candidate_provider_requires_explicit_simulated_metric_authority():
    provider = PrplMeshCandidateProvider()
    with pytest.raises(CandidateMetricsError, match="allow-simulated-candidates"):
        list(provider((), (), [], STAMP))


class _Provider(PrplMeshCandidateProvider):
    def __init__(self):
        super().__init__(allow_simulated=True, timeout_seconds=0.01)
        self.calls = []

    def _radio_objects(self):
        return {
            ("02:00:00:27:02:01", "02:00:00:00:04:00"):
                "Device.WiFi.DataElements.Network.Device.2.Radio.2"
        }

    def _call(self, obj, method, payload):
        self.calls.append((obj, method, payload))
        return {"status": "ok"}

    def _radio_metrics(self, radio):
        assert radio.endswith("Radio.2")
        updates = sum(method == "UpdateUnassociatedStationsStats" for _, method, _ in self.calls)
        timestamp = STAMP if updates else METRIC_STAMP
        return {"02:00:00:10:01:00": (122, timestamp)}


def test_candidate_provider_registers_updates_and_returns_standard_metric():
    provider = _Provider()
    client = ClientObservation(
        sta_mac="02:00:00:10:01:00",
        connected_device_id="02:00:00:27:01:01",
        connected_device_name="controller",
        connected_bssid="02:00:00:00:01:00",
        rcpi=88,
        association_uptime_seconds=42,
        metric_observed_at=STAMP,
        measurement_source="prplmesh_associated_sta_link_metrics",
        band="5",
        ssid="private_ssid",
        cohort="private",
    )
    candidate = CandidateObservation(
        sta_mac=client.sta_mac,
        bssid="02:00:00:00:04:00",
        device_id="02:00:00:27:02:01",
        device_name="agent-1",
        rcpi=None,
        metric_observed_at=None,
        measurement_source="prplmesh_bss_inventory_only",
        band="5",
    )
    bss = {
        "bssid": candidate.bssid,
        "device_id": candidate.device_id,
        "radio_id": "02:00:00:00:04:00",
        "channel": 36,
        "opclass": 115,
    }
    measured = list(provider((client,), (candidate,), [bss], STAMP))
    assert len(measured) == 1
    assert measured[0].rcpi == 122
    assert measured[0].metric_observed_at == STAMP
    assert measured[0].measurement_source.endswith(":simulated")
    assert any(method == "AddUnassociatedStation" for _, method, _ in provider.calls)
    assert any(method == "UpdateUnassociatedStationsStats" for _, method, _ in provider.calls)


def test_candidate_provider_can_limit_measurement_to_selected_client():
    provider = _Provider()
    sta_mac = "02:00:00:10:01:00"
    provider.client_selector = lambda client, _observed_at: client.sta_mac != sta_mac
    client = ClientObservation(
        sta_mac=sta_mac,
        connected_device_id="02:00:00:27:01:01",
        connected_device_name="controller",
        connected_bssid="02:00:00:00:01:00",
        rcpi=88,
        association_uptime_seconds=42,
        metric_observed_at=STAMP,
        measurement_source="prplmesh_associated_sta_link_metrics",
        band="5",
        ssid="private_ssid",
        cohort="private",
    )
    candidate = CandidateObservation(
        sta_mac=sta_mac,
        bssid="02:00:00:00:04:00",
        device_id="02:00:00:27:02:01",
        device_name="agent-1",
        rcpi=None,
        metric_observed_at=None,
        measurement_source="prplmesh_bss_inventory_only",
        band="5",
    )
    bss = {
        "bssid": candidate.bssid,
        "device_id": candidate.device_id,
        "radio_id": "02:00:00:00:04:00",
        "channel": 36,
        "opclass": 115,
    }

    assert list(provider((client,), (candidate,), [bss], STAMP)) == []
    assert not any(method == "AddUnassociatedStation" for _, method, _ in provider.calls)


def test_candidate_provider_rejects_cached_metrics_after_update():
    provider = _Provider()
    provider._radio_metrics = lambda radio: {"02:00:00:10:01:00": (122, METRIC_STAMP)}
    observer = PrplMeshObserver(fetcher=lambda url: _topology(),
                                candidate_provider=provider, clock=lambda: NOW)
    with pytest.raises(CandidateMetricsError, match="incomplete"):
        observer.observe()


def test_missing_serving_metric_uses_only_explicit_fallback():
    from dataclasses import replace

    topology = _topology()
    topology["devices"][0]["radios"][0]["bsses"][0]["clients"][0]["signal_raw"] = None
    observer = PrplMeshObserver(fetcher=lambda url: topology, clock=lambda: NOW,
        current_link_fallback=lambda client: replace(client, rcpi=90,
            metric_observed_at=STAMP, measurement_source="test_kernel_sample"))
    sample = observer.observe().clients[0]
    assert sample.rcpi == 90
    assert sample.measurement_source == "test_kernel_sample"


def test_first_json_accepts_ubus_prefix_noise_and_rejects_non_objects():
    assert _first_json('  {"answer": 42}\nwarning') == {"answer": 42}
    with pytest.raises(CandidateMetricsError):
        _first_json("[]")


def test_live_candidate_timeout_is_operator_configurable():
    args = parser().parse_args([
        "recommend", "--journal", "/tmp/journal.jsonl",
        "--policy", "configs/threshold-policy.yaml",
        "--candidate-timeout", "300",
    ])
    assert args.candidate_timeout == 300


def test_live_candidate_timeout_must_be_positive():
    with pytest.raises(SystemExit):
        parser().parse_args([
            "recommend", "--journal", "/tmp/journal.jsonl",
            "--policy", "configs/threshold-policy.yaml",
            "--candidate-timeout", "0",
        ])

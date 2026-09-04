from __future__ import annotations

from datetime import datetime, timezone
import json
import subprocess
import time
from typing import Any, Callable, Iterable
from urllib.request import urlopen

from .candidates import CandidateMetricsError
from .model import (
    CandidateObservation,
    ClientObservation,
    MeshHealth,
    Snapshot,
    format_time,
    normalize_band,
    normalize_mac,
    sorted_candidates,
    sorted_clients,
)


def _band(value: str | None) -> str | None:
    return normalize_band(value.replace(" ", "") if value else value)


def _fetch(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:  # nosec: operator lab endpoint
        return json.load(response)


def _flatten(topology: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    devices: list[dict] = []
    bsses: list[dict] = []
    clients: list[dict] = []
    for device in topology.get("devices", []):
        device_id = normalize_mac(device["id"])
        devices.append({"id": device_id, "name": device.get("name", "")})
        for radio in device.get("radios", []):
            radio_id = normalize_mac(radio["id"])
            band = _band(radio.get("band"))
            for bss in radio.get("bsses", []):
                record = {
                    "bssid": normalize_mac(bss["bssid"]),
                    "device_id": device_id,
                    "device_name": device.get("name", ""),
                    "radio_id": radio_id,
                    "band": band,
                    "channel": int(radio.get("channel") or 0),
                    "opclass": int(radio.get("opclass") or 0),
                    "ssid": bss.get("ssid") or "",
                }
                bsses.append(record)
                for client in bss.get("clients", []):
                    clients.append({**client, **record})
    return devices, bsses, clients


class PrplMeshObserver:
    """Normalize the prplMesh topology adapter without reading RF truth."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8092",
        *,
        fetcher=None,
        candidate_provider=None,
        trust_api_metric_timestamp: bool = True,
        clock=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetcher = fetcher or _fetch
        self.candidate_provider = candidate_provider
        self.trust_api_metric_timestamp = trust_api_metric_timestamp
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sequence = 0
        self.last_raw: dict[str, Any] | None = None

    def observe(self) -> Snapshot:
        topology = self.fetcher(f"{self.base_url}/api/topology")
        sampled_at = topology.get("generated_at") or format_time(self.clock())
        devices, bsses, raw_clients = _flatten(topology)
        clients: list[ClientObservation] = []
        for item in raw_clients:
            rcpi_value = int(item.get("signal_raw") or 0)
            metric_time = item.get("signal_updated_at")
            clients.append(
                ClientObservation(
                    sta_mac=normalize_mac(item["id"]),
                    connected_device_id=item["device_id"],
                    connected_device_name=item["device_name"],
                    connected_bssid=item["bssid"],
                    rcpi=rcpi_value if rcpi_value > 0 else None,
                    association_uptime_seconds=int(
                        item.get("last_connect_seconds") or 0
                    ),
                    metric_observed_at=(
                        metric_time if self.trust_api_metric_timestamp else None
                    ),
                    measurement_source="prplmesh_associated_sta_link_metrics",
                    band=item["band"],
                    ssid=item["ssid"],
                    cohort=(
                        "iot" if item["ssid"] == "iot_ssid"
                        else "private" if item["ssid"] == "private_ssid"
                        else "other"
                    ),
                )
            )
        normalized_clients = sorted_clients(clients)
        candidates: list[CandidateObservation] = []
        for client in normalized_clients:
            for bss in bsses:
                if bss["bssid"] == client.connected_bssid or bss["ssid"] != client.ssid:
                    continue
                candidates.append(
                    CandidateObservation(
                        sta_mac=client.sta_mac,
                        bssid=bss["bssid"],
                        device_id=bss["device_id"],
                        device_name=bss["device_name"],
                        rcpi=None,
                        metric_observed_at=None,
                        measurement_source="prplmesh_bss_inventory_only",
                        band=bss["band"],
                    )
                )
        provider_raw = None
        if self.candidate_provider is not None:
            measured = list(
                self.candidate_provider(
                    normalized_clients,
                    sorted_candidates(candidates),
                    bsses,
                    sampled_at,
                )
            )
            measured_keys = {(item.sta_mac, item.bssid) for item in measured}
            candidates = [
                item
                for item in candidates
                if (item.sta_mac, item.bssid) not in measured_keys
            ] + measured
            provider_raw = getattr(self.candidate_provider, "last_raw", None)

        observed_at = format_time(self.clock())
        self.last_raw = {
            "sample_started_at": sampled_at,
            "sampled_at": observed_at,
            "topology": topology,
        }
        if provider_raw is not None:
            self.last_raw["candidate_transactions"] = provider_raw
        snapshot = Snapshot(
            schema_version=1,
            sequence=self.sequence,
            observed_at=observed_at,
            controller_url=self.base_url,
            health=MeshHealth(
                devices=len(devices),
                clients=len(normalized_clients),
                radios=len({bss["radio_id"] for bss in bsses}),
                bsses=len(bsses),
                source="prplmesh_nbapi",
            ),
            clients=normalized_clients,
            candidates=sorted_candidates(candidates),
        )
        self.sequence += 1
        return snapshot


def _first_json(text: str) -> dict[str, Any]:
    try:
        value, _ = json.JSONDecoder().raw_decode(text.lstrip())
    except json.JSONDecodeError as error:
        raise CandidateMetricsError(f"invalid prplMesh NBAPI response: {text!r}") from error
    if not isinstance(value, dict):
        raise CandidateMetricsError("prplMesh NBAPI response is not an object")
    return value


class PrplMeshCandidateProvider:
    """Collect candidate RCPI through prplMesh's standard NBAPI transaction."""

    NETWORK = "Device.WiFi.DataElements.Network"

    def __init__(
        self,
        *,
        controller: str = "prpl-controller",
        allow_simulated: bool = False,
        timeout_seconds: float = 30,
        client_selector: Callable[[ClientObservation, str], bool] | None = None,
    ) -> None:
        self.controller = controller
        self.allow_simulated = allow_simulated
        self.timeout_seconds = timeout_seconds
        self.client_selector = client_selector
        self.registered: set[tuple[str, str]] = set()
        self.object_cache: dict[tuple[str, str], str] = {}
        self.last_raw: list[dict[str, Any]] = []

    def _call(self, obj: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                [
                    "lxc", "exec", self.controller, "--", "ubus", "call",
                    obj, method, json.dumps(payload, separators=(",", ":")),
                ],
                check=True,
                text=True,
                capture_output=True,
                timeout=12,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise CandidateMetricsError(
                f"prplMesh NBAPI call failed: {obj} {method}"
            ) from error
        return _first_json(completed.stdout)

    def _instances(self, rel_path: str) -> list[str]:
        value = self._call(
            self.NETWORK,
            "_get_instances",
            {"rel_path": rel_path, "depth": 1},
        )
        return sorted(key.rstrip(".") for key in value)

    def _get(self, obj: str, depth: int = 0) -> dict[str, Any]:
        value = self._call(obj, "_get", {"rel_path": "", "depth": depth})
        return value.get(obj + ".", value.get(obj, {}))

    def _radio_objects(self) -> dict[tuple[str, str], str]:
        if self.object_cache:
            return self.object_cache
        device_ids = {}
        for device in self._instances("Device."):
            device_value = self._get(device)
            device_ids[device] = normalize_mac(device_value["ID"])
        for radio in self._instances("Device.*.Radio."):
            device = radio.split(".Radio.", 1)[0]
            device_id = device_ids.get(device)
            if device_id is None:
                raise CandidateMetricsError(
                    f"NBAPI radio {radio} has no discovered parent device"
                )
            radio_value = self._get(radio)
            radio_id = normalize_mac(radio_value["ID"])
            self.object_cache[(device_id, radio_id)] = radio
        return self.object_cache

    def _radio_metrics(self, radio: str) -> dict[str, tuple[int, str]]:
        value = self._call(
            radio + ".UnassociatedSTA",
            "_get",
            {"rel_path": "", "depth": 2},
        )
        result = {}
        for key, item in value.items():
            if not key.rstrip(".").split(".")[-1].isdigit() or not isinstance(item, dict):
                continue
            mac = item.get("MACAddress")
            timestamp = item.get("X_PRPLWARE-COM_TimeStamp")
            signal = int(item.get("SignalStrength") or 0)
            if mac and timestamp and not str(timestamp).startswith("0001-") and signal > 0:
                result[normalize_mac(mac)] = (signal, str(timestamp))
        return result

    def __call__(
        self,
        clients: tuple[ClientObservation, ...],
        inventory: tuple[CandidateObservation, ...],
        bsses: list[dict[str, Any]],
        observed_at: str,
    ) -> Iterable[CandidateObservation]:
        if not self.allow_simulated:
            raise CandidateMetricsError(
                "prplMesh candidate provider is hwsim/wmediumd-backed; "
                "use --allow-simulated-candidates in this lab"
            )
        clients_by_mac = {item.sta_mac: item for item in clients}
        bss_by_id = {item["bssid"]: item for item in bsses}
        radio_objects = self._radio_objects()
        targets: dict[tuple[str, str], list[CandidateObservation]] = {}
        radio_metadata: dict[str, dict[str, Any]] = {}
        for candidate in inventory:
            client = clients_by_mac.get(candidate.sta_mac)
            bss = bss_by_id.get(candidate.bssid)
            if client is None or bss is None or candidate.band != client.band:
                continue
            if self.client_selector is not None and not self.client_selector(
                client, observed_at
            ):
                continue
            key = (bss["device_id"], bss["radio_id"])
            radio = radio_objects.get(key)
            if radio is None:
                raise CandidateMetricsError(f"no NBAPI radio object for {key}")
            targets.setdefault((radio, candidate.sta_mac), []).append(candidate)
            radio_metadata[radio] = bss

        self.last_raw = []
        for radio, sta_mac in sorted(targets):
            if (radio, sta_mac) in self.registered:
                continue
            meta = radio_metadata[radio]
            request = {
                "un_station_mac": sta_mac,
                "channel": int(meta["channel"]),
                "operating_class": int(meta["opclass"]),
                "agent_mac": meta["device_id"],
            }
            response = self._call(radio, "AddUnassociatedStation", request)
            self.last_raw.append(
                {"operation": "register", "radio": radio, "request": request,
                 "response": response}
            )
            self.registered.add((radio, sta_mac))

        response = self._call(self.NETWORK, "UpdateUnassociatedStationsStats", {})
        self.last_raw.append({"operation": "update", "response": response})
        deadline = time.monotonic() + self.timeout_seconds
        expected = set(targets)
        metrics: dict[tuple[str, str], tuple[int, str]] = {}
        while time.monotonic() < deadline:
            metrics.clear()
            for radio in sorted({radio for radio, _ in expected}):
                for sta_mac, value in self._radio_metrics(radio).items():
                    metrics[(radio, sta_mac)] = value
            if expected.issubset(metrics):
                break
            time.sleep(0.5)
        missing = sorted(expected - set(metrics))
        if missing:
            raise CandidateMetricsError(
                f"prplMesh candidate metrics incomplete after {self.timeout_seconds}s: {missing}"
            )

        measured = []
        for key, mapped in sorted(targets.items()):
            rcpi, timestamp = metrics[key]
            for candidate in mapped:
                measured.append(
                    CandidateObservation(
                        sta_mac=candidate.sta_mac,
                        bssid=candidate.bssid,
                        device_id=candidate.device_id,
                        device_name=candidate.device_name,
                        rcpi=rcpi,
                        metric_observed_at=timestamp,
                        measurement_source=(
                            "easy_mesh_unassociated_sta_link_metrics:"
                            "prplmesh-nl80211-hwsim-wmediumd:simulated"
                        ),
                        band=candidate.band,
                    )
                )
        self.last_raw.append(
            {"operation": "complete", "measurements": len(measured)}
        )
        return measured

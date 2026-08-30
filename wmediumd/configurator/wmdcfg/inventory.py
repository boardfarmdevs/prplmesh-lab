from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .model import ScenarioError


MESH_NAME = re.compile(r"^(prpl-controller|prpl-agent-\d{2})$")
CLIENT_NAME = re.compile(r"^prpl-client-\d{2}$")


def _run(*args: str, attempts: int = 2, timeout_seconds: float = 5.0) -> str:
    """Run a read-only inventory probe with bounded LXC transport recovery."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                args,
                check=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if attempt == attempts:
                raise ScenarioError(
                    "inventory probe failed after "
                    f"{attempts} attempts: {' '.join(args)}"
                ) from error
            time.sleep(0.5 * attempt)
    raise AssertionError("unreachable")


def _exec(container: str, command: str) -> str:
    return _run("lxc", "exec", container, "--", "sh", "-c", command)


def _tx_mac(permanent: str) -> str:
    raw = bytearray.fromhex(permanent.replace(":", ""))
    if len(raw) != 6:
        raise ScenarioError(f"invalid radio MAC {permanent!r}")
    raw[0] |= 0x40
    return ":".join(f"{value:02x}" for value in raw)


def _band(frequency_mhz: int | None) -> str | None:
    if not frequency_mhz:
        return None
    if frequency_mhz < 2500:
        return "2.4"
    if frequency_mhz < 5925:
        return "5"
    return "6"


def _parse_iw(text: str) -> list[dict[str, Any]]:
    interfaces: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    phy: str | None = None
    for line in text.splitlines():
        value = line.strip()
        if value.startswith("phy#"):
            phy = f"phy{value[4:]}"
            current = None
        elif value.startswith("Interface "):
            current = {"name": value.split(None, 1)[1], "phy": phy}
            interfaces.append(current)
        elif current is not None and value.startswith("addr "):
            current["mac"] = value.split()[1].lower()
        elif current is not None and value.startswith("ssid "):
            current["ssid"] = value.split(None, 1)[1]
        elif current is not None and value.startswith("channel "):
            match = re.search(r"\((\d+) MHz\)", value)
            if match:
                current["frequency_mhz"] = int(match.group(1))
    return interfaces


def _permanent_radios(container: str) -> dict[str, str]:
    text = _exec(
        container,
        "for p in /sys/class/ieee80211/phy*; do "
        "[ -r \"$p/macaddress\" ] || continue; "
        "printf '%s %s\\n' \"${p##*/}\" \"$(cat \"$p/macaddress\")\"; done",
    )
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2:
            result[fields[0]] = fields[1].lower()
    return result


def discover(client_names: set[str] | None = None) -> dict[str, Any]:
    names = sorted(
        [
            name
            for line in _run("lxc", "list", "-c", "ns", "--format", "csv").splitlines()
            for name, _, state in [line.partition(",")]
            if state.strip().upper() == "RUNNING"
            and (
                MESH_NAME.fullmatch(name)
                or (
                    CLIENT_NAME.fullmatch(name)
                    and (client_names is None or name in client_names)
                )
            )
        ],
        key=lambda name: [
            int(part) if part.isdigit() else part
            for part in re.split(r"(\d+)", name)
        ],
    )
    if not names:
        raise ScenarioError("no active prplMesh or WLAN client containers found")

    def inspect(name: str) -> dict[str, Any]:
        permanent_by_phy = _permanent_radios(name)
        if not permanent_by_phy:
            raise ScenarioError(f"{name}: no hwsim radio found")
        interfaces = _parse_iw(_exec(name, "iw dev 2>/dev/null"))
        if CLIENT_NAME.fullmatch(name):
            permanent = next(iter(permanent_by_phy.values()))
            wlan = next(
                (item for item in interfaces if item.get("name") == "wlan0"),
                None,
            )
            if wlan is None or not wlan.get("mac"):
                raise ScenarioError(f"{name}: wlan0 station interface is absent")
            link = _exec(name, "iw dev wlan0 link 2>/dev/null || true")
            match = re.search(r"Connected to ([0-9a-f:]{17})", link, re.I)
            ssid_match = re.search(r"^\s*SSID:\s*(.+?)\s*$", link, re.M)
            frequency_match = re.search(r"^\s*freq:\s*(\d+)\s*$", link, re.M)
            frequency = (
                int(frequency_match.group(1))
                if frequency_match
                else wlan.get("frequency_mhz")
            )
            ssid = ssid_match.group(1) if ssid_match else wlan.get("ssid")
            return {
                "container": name,
                "kind": "station",
                "permanent_mac": permanent,
                "tx_mac": _tx_mac(permanent),
                "station_mac": wlan["mac"],
                "interfaces": interfaces,
                "associated_bssid": match.group(1).lower() if match else None,
                "frequency_mhz": frequency,
                "band": _band(frequency),
                "ssid": ssid,
                "cohort": (
                    "iot" if ssid == "iot_ssid"
                    else "private" if ssid == "private_ssid"
                    else "other"
                ),
            }

        band_radios: dict[str, dict[str, Any]] = {}
        for phy, permanent in permanent_by_phy.items():
            phy_interfaces = [item for item in interfaces if item.get("phy") == phy]
            frequencies = {
                int(item["frequency_mhz"])
                for item in phy_interfaces
                if item.get("frequency_mhz")
            }
            if len(frequencies) != 1:
                raise ScenarioError(
                    f"{name}: {phy} does not expose one unambiguous frequency"
                )
            frequency = next(iter(frequencies))
            band = _band(frequency)
            if band is None or band in band_radios:
                raise ScenarioError(f"{name}: duplicate or unknown radio band {band}")
            band_radios[band] = {
                "phy": phy,
                "permanent_mac": permanent,
                "tx_mac": _tx_mac(permanent),
                "frequency_mhz": frequency,
                "interfaces": phy_interfaces,
            }
        if set(band_radios) != {"2.4", "5", "6"}:
            raise ScenarioError(
                f"{name}: expected tri-band radio inventory, found {sorted(band_radios)}"
            )
        default = band_radios["5"]
        return {
            "container": name,
            "kind": "mesh",
            "permanent_mac": default["permanent_mac"],
            "tx_mac": default["tx_mac"],
            "interfaces": interfaces,
            "band_radios": band_radios,
        }

    with ThreadPoolExecutor(max_workers=min(8, len(names))) as executor:
        radios = list(executor.map(inspect, names))
    return {
        "schema": "wmdcfg.inventory.v1",
        "backend": "prplmesh-nbapi",
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "radios": radios,
    }


def save(inventory: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")

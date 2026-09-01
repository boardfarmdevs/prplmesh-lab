#!/usr/bin/env python3
"""Select a deterministic, non-no-op optimizer acceptance stimulus."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise SystemExit(f"optimizer stimulus selection failed: {message}")


def main() -> None:
    if len(sys.argv) != 3:
        fail(f"usage: {Path(sys.argv[0]).name} INVENTORY TARGET")

    inventory = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    target_name = sys.argv[2]
    radios = inventory.get("radios", [])
    mesh = {
        radio.get("container"): radio
        for radio in radios
        if radio.get("kind") == "mesh"
    }
    target = mesh.get(target_name)
    if target is None:
        fail(f"unknown mesh target: {target_name}")

    owner_by_bssid = {
        str(interface.get("mac", "")).lower(): name
        for name, radio in mesh.items()
        for interface in radio.get("interfaces", [])
        if interface.get("mac")
    }
    target_networks = {
        (str(band), interface.get("ssid"))
        for band, radio in target.get("band_radios", {}).items()
        for interface in radio.get("interfaces", [])
        if interface.get("ssid") and interface.get("ssid") != "mesh_backhaul"
    }

    stations = sorted(
        (radio for radio in radios if radio.get("kind") == "station"),
        key=lambda radio: str(radio.get("container", "")),
    )
    for station in stations:
        serving_bssid = str(station.get("associated_bssid", "")).lower()
        owner = owner_by_bssid.get(serving_bssid)
        network = (str(station.get("band")), station.get("ssid"))
        if owner and owner != target_name and network in target_networks:
            print(station["container"], target_name)
            return

    fail(
        f"no associated station outside {target_name} has a compatible "
        "target BSS"
    )


if __name__ == "__main__":
    main()

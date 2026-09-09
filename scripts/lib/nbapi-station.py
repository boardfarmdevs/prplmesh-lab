#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys


def station_object(document: str, station: str) -> str:
    values, _ = json.JSONDecoder().raw_decode(document.lstrip())
    matches = [
        path.rstrip(".") for path, value in values.items()
        if re.fullmatch(r"Device\.WiFi\.DataElements\.Network\.Device\.\d+\.Radio\.\d+\.BSS\.\d+\.STA\.\d+\.", path)
        and isinstance(value, dict)
        and str(value.get("MACAddress", "")).lower() == station.lower()
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one NBAPI owner for {station}, found {len(matches)}")
    return matches[0]


if __name__ == "__main__":
    try:
        print(station_object(sys.stdin.read(), sys.argv[1]))
    except (ValueError, TypeError, AttributeError) as error:
        sys.exit(str(error))

#!/usr/bin/env python3
"""Generate the fixed base-radio roster for one portable lab profile."""

from __future__ import annotations

import argparse
from pathlib import Path


def render(radios: int, default_snr: int) -> str:
    if not 1 <= radios <= 128:
        raise ValueError("radio count must be between 1 and 128")
    if not -100 <= default_snr <= 100:
        raise ValueError("default SNR must be between -100 and 100")
    identities = [f'"42:00:00:00:{index:02x}:00"' for index in range(radios)]
    rows = []
    for offset in range(0, len(identities), 4):
        rows.append("        " + ", ".join(identities[offset : offset + 4]))
    return (
        "ifaces:\n{\n"
        f"    count = {radios};\n"
        "    ids = [\n"
        + ",\n".join(rows)
        + "\n    ];\n};\n\n"
        "model:\n{\n"
        '    type = "snr";\n'
        f"    default_snr = {default_snr};\n"
        "};\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radios", type=int, required=True)
    parser.add_argument("--default-snr", type=int, default=40)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = render(args.radios, args.default_snr)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

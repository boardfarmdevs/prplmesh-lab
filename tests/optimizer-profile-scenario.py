#!/usr/bin/env python3
"""Render the live optimizer scenario for a provisioned client profile."""

import argparse
import re
from pathlib import Path


DESTINATION_HOLD = re.compile(
    r"(?m)^(\s*phase\s+destination_hold\s+for\s+)(\d+)s(\s*\{)"
)


def hold_seconds(client_count):
    if client_count <= 0:
        raise ValueError("client count must be positive")
    # Active candidate collection is serialized through the controller and
    # scales approximately linearly. Six seconds per client includes the
    # measured 100-client sweep plus a bounded scheduling margin.
    return max(90, 6 * client_count)


def render(text, client_count):
    matches = list(DESTINATION_HOLD.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            "optimizer scenario must contain exactly one destination_hold phase"
        )
    seconds = hold_seconds(client_count)
    return DESTINATION_HOLD.sub(
        lambda match: "%s%ds%s" % (match.group(1), seconds, match.group(3)),
        text,
        count=1,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", type=int, required=True)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        output = render(args.source.read_text(encoding="utf-8"), args.clients)
    except ValueError as error:
        parser.error(str(error))
    args.output.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
